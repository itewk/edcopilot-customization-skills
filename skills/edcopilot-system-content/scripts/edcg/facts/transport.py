"""Shared HTTP transport for EDCoPilot fact clients.

Provides a unified async HTTP client with retry, timeout, and rate limiting
for all API clients (Spansh, Raven, Inara).
"""

import asyncio
import time
from typing import Optional

import httpx


class HTTPTransport:
    """Shared async HTTP transport with retry, timeout, and rate limiting."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        rate_limit: float = 10.0,  # requests per second
    ):
        """Initialize the HTTP transport.
        
        Args:
            base_url: Base URL for API endpoints.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts for failed requests.
            rate_limit: Maximum requests per second (0 = no limit).
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limit = rate_limit
        self._client: Optional[httpx.AsyncClient] = None
        self._last_request_time: float = 0.0
        self._rate_lock = asyncio.Lock()

    async def __aenter__(self) -> "HTTPTransport":
        """Enter async context manager."""
        await self._ensure_client()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        """Exit async context manager."""
        await self.close()

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure the HTTP client is created."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
                headers={"User-Agent": "EDCoPilot-Customization-Generator/0.1.0"},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _rate_limit_wait(self) -> None:
        """Wait if necessary to respect rate limit."""
        if self.rate_limit <= 0:
            return

        min_interval = 1.0 / self.rate_limit
        async with self._rate_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            self._last_request_time = time.monotonic()

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make an HTTP request with retry logic."""
        await self._ensure_client()
        await self._rate_limit_wait()

        last_exception: Optional[BaseException] = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except (httpx.RequestError, httpx.TimeoutException) as e:
                last_exception = e
                if attempt < self.max_retries:
                    # Exponential backoff: 1s, 2s, 4s, ...
                    await asyncio.sleep(2 ** attempt)
                    continue
                break
            except httpx.HTTPStatusError as e:
                # Don't retry client errors (4xx), only server errors (5xx)
                if 400 <= e.response.status_code < 500:
                    raise
                last_exception = e
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                break

        # All retries exhausted
        if isinstance(last_exception, httpx.TimeoutException):
            raise httpx.HTTPError(f"Request timed out after {self.max_retries + 1} attempts") from last_exception
        elif isinstance(last_exception, httpx.RequestError):
            raise httpx.HTTPError(f"Network error: {last_exception}") from last_exception
        else:
            raise httpx.HTTPError(f"Request failed after {self.max_retries + 1} attempts: {last_exception}") from last_exception