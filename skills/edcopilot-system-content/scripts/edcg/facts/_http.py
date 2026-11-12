"""Shared async HTTP transport for the EDCoPilot fact clients.

Retry, backoff and rate limiting are one policy, so they live here rather than
in each client. A client supplies its URL building and response parsing, plus
the few settings that genuinely differ:

- ``follow_redirects``: Spansh and Raven follow them; Inara does not, because
  its API key travels in the POST body.
- ``retry_statuses``: Inara retries 429; the other two do not.
- ``default_headers``: only Spansh sends a User-Agent.
- ``request_verb``: Raven and Spansh call ``client.request(method, url)``;
  Inara always POSTs JSON to one endpoint, so it names the verb instead.

Each client keeps its own exception class (callers and tests import them by
name); they share ``ApiError`` so the transport can raise ``self.error_type``.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import httpx


class ApiError(Exception):
    """Base class for API client errors."""


class ApiClient:
    """Async HTTP client with retry, timeout and rate limiting."""

    error_type: type[ApiError] = ApiError
    follow_redirects: bool = True
    retry_statuses: frozenset[int] = frozenset()
    default_headers: dict[str, str] = {}
    request_verb: Optional[str] = None

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        rate_limit: float = 10.0,  # requests per second
    ) -> None:
        """Initialise the transport.

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

    async def __aenter__(self) -> "ApiClient":
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
        """Create the HTTP client on first use."""
        if self._client is None:
            kwargs: dict[str, Any] = {
                "timeout": httpx.Timeout(self.timeout),
                "follow_redirects": self.follow_redirects,
            }
            if self.default_headers:
                kwargs["headers"] = dict(self.default_headers)
            self._client = httpx.AsyncClient(**kwargs)
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

    async def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Make an HTTP request with retry logic."""
        client = await self._ensure_client()
        await self._rate_limit_wait()

        last_exception: Optional[BaseException] = None
        for attempt in range(self.max_retries + 1):
            try:
                if self.request_verb is not None:
                    response = await getattr(client, self.request_verb)(url, **kwargs)
                else:
                    response = await client.request(method, url, **kwargs)
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
                # Don't retry client errors (4xx), except those a client
                # explicitly names (Inara retries 429).
                status = e.response.status_code
                if 400 <= status < 500 and status not in self.retry_statuses:
                    raise self.error_type(f"HTTP {status}: {e}") from e
                last_exception = e
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                break

        # All retries exhausted
        if isinstance(last_exception, httpx.TimeoutException):
            raise self.error_type(
                f"Request timed out after {self.max_retries + 1} attempts"
            ) from last_exception
        elif isinstance(last_exception, httpx.RequestError):
            raise self.error_type(f"Network error: {last_exception}") from last_exception
        else:
            raise self.error_type(
                f"Request failed after {self.max_retries + 1} attempts: {last_exception}"
            ) from last_exception
