"""Raven Colonial API client for the EDCoPilot system content skill.

Provides async HTTP client for fetching system plans and site data from
the Raven Colonial API.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote

from edcg.facts.transport import HTTPTransport


@dataclass
class RavenSystem:
    """Represents a system plan from Raven Colonial."""
    name: str
    architect: str
    revision: int
    bodies: list[str]
    body_nums: dict[int, str] = field(default_factory=dict)

    def body_name(self, body_num: int) -> str:
        """Resolve a site's bodyNum to the name of the body it identifies.

        Raven's ``bodyNum`` is the body's ``num`` identifier (the same numbering
        Spansh uses), not a position in ``bodies``. The list contains stars,
        belts and planets, so positional indexing returns the wrong body.

        Args:
            body_num: The ``bodyNum`` value from a Raven site.

        Returns:
            The body name, or "Unknown" when it cannot be resolved.
        """
        if body_num in self.body_nums:
            return self.body_nums[body_num]
        # Payloads or fixtures without nums fall back to positional lookup.
        if not self.body_nums and 0 <= body_num < len(self.bodies):
            return self.bodies[body_num]
        return "Unknown"


@dataclass
class RavenSite:
    """Represents a colonisation site from Raven Colonial."""
    id: int
    name: Optional[str]
    status: str
    build_type: Optional[str]
    body_num: int


class RavenAPIError(Exception):
    """Exception raised for Raven API errors."""
    pass


# NATO phonetic alphabet words used for placeholder detection
_NATO_WORDS = {
    "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
    "india", "juliett", "kilo", "lima", "mike", "november", "oscar", "papa",
    "quebec", "romeo", "sierra", "tango", "uniform", "victor", "whiskey",
    "xray", "yankee", "zulu",
}


def _parse_bodies(raw: list) -> tuple[list[str], dict[int, str]]:
    """Split the API's body objects into an ordered name list and a num lookup.

    The system endpoint returns bodies as objects (``name``, ``num`` and orbital
    data). ``bodies`` keeps the names in API order for display, while
    ``body_nums`` maps each body's ``num`` to its name so sites can be resolved
    by ``bodyNum``.

    Args:
        raw: The ``bodies`` value from the system endpoint.

    Returns:
        A tuple of (body names in order, mapping of body num to name).
    """
    bodies: list[str] = []
    body_nums: dict[int, str] = {}
    for item in raw:
        if isinstance(item, str):
            bodies.append(item)
            continue
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name:
            continue
        bodies.append(name)
        num = item.get("num")
        if isinstance(num, int):
            body_nums[num] = name
    return bodies, body_nums


def is_placeholder_name(name: Optional[str]) -> bool:
    """Check if a name is a two-NATO-word placeholder.

    Raven uses pairs of NATO phonetic alphabet words (e.g., "Xray Hotel",
    "Zulu Yankee") as placeholder names for tentatively planned sites.

    Args:
        name: The name to check.

    Returns:
        True if the name consists of exactly two NATO words, False otherwise.
    """
    if not name or not name.strip():
        return False

    words = name.strip().split()
    if len(words) != 2:
        return False

    # Check if both words are NATO phonetic alphabet words (case-insensitive)
    return words[0].lower() in _NATO_WORDS and words[1].lower() in _NATO_WORDS


def is_unresolved_site(site: RavenSite) -> bool:
    """Check if a site is an unresolved placeholder entry.

    Unresolved entries are not part of the actual colonisation plan. They
    appear to be hand-entered duplicates and have one or more of:
    - no name at all
    - no build_type at all
    - build_type ending with "?" (e.g., "outpost?", "installation?")
    - body_num == -1
    - name wrapped in square brackets (e.g., "[Unknown]", "[Installation?]")

    Args:
        site: The RavenSite to check.

    Returns:
        True if the site appears to be an unresolved placeholder, False otherwise.
    """
    if not site.name:
        return True
    if not site.build_type:
        return True
    if site.build_type.endswith("?"):
        return True
    if site.body_num == -1:
        return True
    if site.name.startswith("[") and site.name.endswith("]"):
        return True
    return False


class RavenClient:
    """Async HTTP client for the Raven Colonial API.

    Provides methods to fetch system plans and colonisation site data
    with configurable retry, timeout, and rate limiting.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        rate_limit: float = 10.0,  # requests per second
    ):
        """Initialize the Raven client.

        Args:
            base_url: Base URL of the Raven Colonial API.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts for failed requests.
            rate_limit: Maximum requests per second (0 = no limit).
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limit = rate_limit
        self._transport = HTTPTransport(base_url, timeout, max_retries, rate_limit)

    async def __aenter__(self) -> "RavenClient":
        """Enter async context manager."""
        await self._transport.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager."""
        await self._transport.__aexit__(exc_type, exc_val, exc_tb)

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure the HTTP client is created."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._transport.close()

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
        return await self._transport._request_with_retry(method, url, **kwargs)

    async def get_system(self, system_name: str) -> RavenSystem:
        """Fetch a system plan from Raven Colonial.

        Args:
            system_name: Name of the system to fetch.

        Returns:
            RavenSystem with architect, revision, and bodies.

        Raises:
            RavenAPIError: If the request fails.
        """
        # URL encode the system name (spaces become %20, etc.)
        encoded_name = quote(system_name, safe="")
        url = f"{self.base_url}/api/v2/system/{encoded_name}"

        response = await self._request_with_retry("GET", url)
        data = response.json()

        # Handle both "revision" and "rev" field names (API uses "rev" per raven.toml)
        revision = data.get("revision") or data.get("rev")
        if revision is None:
            raise RavenAPIError("Response missing revision/rev field")

        bodies, body_nums = _parse_bodies(data.get("bodies") or [])

        return RavenSystem(
            name=data["name"],
            architect=data["architect"],
            revision=revision,
            bodies=bodies,
            body_nums=body_nums,
        )

    async def get_sites(self, system_name: str) -> list[RavenSite]:
        """Fetch colonisation sites for a system from Raven Colonial.

        Args:
            system_name: Name of the system to fetch sites for.

        Returns:
            List of RavenSite objects (including unresolved placeholders).

        Raises:
            RavenAPIError: If the request fails.
        """
        encoded_name = quote(system_name, safe="")
        url = f"{self.base_url}/api/v2/system/{encoded_name}/sites"

        response = await self._request_with_retry("GET", url)
        data = response.json()

        sites = []
        for item in data:
            site = RavenSite(
                id=item["id"],
                name=item["name"],
                status=item["status"],
                build_type=item["buildType"],
                body_num=item["bodyNum"],
            )
            sites.append(site)

        return sites


__all__ = [
    "RavenClient",
    "RavenSystem",
    "RavenSite",
    "RavenAPIError",
    "is_placeholder_name",
    "is_unresolved_site",
]