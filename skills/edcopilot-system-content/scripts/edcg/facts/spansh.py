"""Spansh API client for the EDCoPilot system content skill.

Provides async HTTP client for fetching system and station data from
the Spansh API (https://spansh.co.uk/api).
No authentication required.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote

# The shared transport creates the client through this module-level httpx
# binding, which is the seam the client tests patch.
import httpx  # noqa: F401

from edcg.facts._http import ApiClient, ApiError


@dataclass
class SpanshStation:
    """Represents a station from Spansh."""
    market_id: int
    name: str
    type: str
    controlling_minor_faction: str
    controlling_minor_faction_state: Optional[str]
    distance_to_arrival: float
    has_large_pad: bool
    has_market: bool
    large_pads: int
    medium_pads: int
    small_pads: int
    services: list[str]


@dataclass
class SpanshSystem:
    """Represents a star system from Spansh."""
    id64: int
    name: str
    coordinates: list[float]
    population: int
    government: str
    allegiance: str
    state: str
    security: str
    primary_economy: str
    secondary_economy: str
    controlling_minor_faction: Optional[str]
    stations: list[SpanshStation]
    bodies: list[dict[str, Any]]
    updated: datetime
    distance: Optional[float] = None


class SpanshAPIError(ApiError):
    """Exception raised for Spansh API errors."""
    pass


class SpanshClient(ApiClient):
    """Async HTTP client for the Spansh API.

    Provides methods to fetch system and station data with configurable
    retry, timeout, and rate limiting. No authentication required.
    """

    error_type = SpanshAPIError
    default_headers = {"User-Agent": "EDCoPilot-Customization-Generator/0.1.0"}

    def __init__(
        self,
        base_url: str = "https://spansh.co.uk/api",
        timeout: float = 30.0,
        max_retries: int = 3,
        rate_limit: float = 10.0,  # requests per second
    ):
        """Initialize the Spansh client.

        Args:
            base_url: Base URL of the Spansh API.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts for failed requests.
            rate_limit: Maximum requests per second (0 = no limit).
        """
        super().__init__(base_url, timeout, max_retries, rate_limit)

    async def get_system(self, system_name: str) -> SpanshSystem:
        """Fetch a system from Spansh by name.

        This performs a two-step process:
        1. Look up system name to get id64 and coordinates via field_values endpoint
        2. Fetch full system data including stations via dump endpoint

        Args:
            system_name: Name of the system to fetch.

        Returns:
            SpanshSystem with full system info, stations, and bodies.

        Raises:
            SpanshAPIError: If the request fails or system not found.
        """
        # Step 1: Resolve system name to id64
        encoded_name = quote(system_name, safe="")
        lookup_url = f"{self.base_url}/systems/field_values/system_names?q={encoded_name}"

        response = await self._request_with_retry("GET", lookup_url)
        data = response.json()

        min_max = data.get("min_max", [])
        if not min_max:
            raise SpanshAPIError(f"System not found: {system_name}")

        # Find exact name match
        system_info = None
        for entry in min_max:
            if entry.get("name") == system_name:
                system_info = entry
                break

        if not system_info:
            raise SpanshAPIError(f"System not found (no exact match): {system_name}")

        id64 = system_info["id64"]

        # Step 2: Fetch full system data via dump endpoint
        dump_url = f"{self.base_url}/dump/{id64}"
        response = await self._request_with_retry("GET", dump_url)
        dump_data = response.json()

        system_data = dump_data.get("system")
        if not system_data:
            raise SpanshAPIError(f"No system data in response for: {system_name}")

        return self._parse_system(system_data)

    def _parse_system(self, data: dict[str, Any]) -> SpanshSystem:
        """Parse system data from Spansh dump response."""
        # Parse controlling faction - can be string or object with 'name' field
        controlling_faction = data.get("controllingFaction") or data.get("controlling_minor_faction")
        if isinstance(controlling_faction, dict):
            controlling_faction = controlling_faction.get("name")

        # Parse stations
        stations = []
        for station_data in data.get("stations", []):
            # Station controlling faction can also be string or object
            station_faction = station_data.get("controllingFaction") or station_data.get("controlling_minor_faction", "Unknown")
            if isinstance(station_faction, dict):
                station_faction = station_faction.get("name", "Unknown")

            station = SpanshStation(
                market_id=station_data.get("id") or station_data.get("market_id", 0),
                name=station_data.get("name", "Unknown"),
                type=station_data.get("type", "Unknown"),
                controlling_minor_faction=station_faction,
                controlling_minor_faction_state=station_data.get("controllingFactionState") or station_data.get("controlling_minor_faction_state"),
                distance_to_arrival=station_data.get("distanceToArrival") or station_data.get("distance_to_arrival", 0.0),
                has_large_pad=station_data.get("has_large_pad", False),
                has_market=station_data.get("has_market", False),
                large_pads=station_data.get("landingPads", {}).get("large", station_data.get("large_pads", 0)),
                medium_pads=station_data.get("landingPads", {}).get("medium", station_data.get("medium_pads", 0)),
                small_pads=station_data.get("landingPads", {}).get("small", station_data.get("small_pads", 0)),
                services=station_data.get("services", []),
            )
            stations.append(station)

        # Parse bodies (keep as raw dict for flexibility)
        bodies = data.get("bodies", [])

        # Parse coordinates
        coords = data.get("coords", {})
        if isinstance(coords, dict):
            coordinates = [coords.get("x", 0.0), coords.get("y", 0.0), coords.get("z", 0.0)]
        else:
            coordinates = [0.0, 0.0, 0.0]

        # Parse updated timestamp
        updated_str = data.get("updateTime") or data.get("updated_at", "")
        try:
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00")) if updated_str else datetime.now(timezone.utc)
        except Exception:
            updated = datetime.now(timezone.utc)

        return SpanshSystem(
            id64=data.get("id64", 0),
            name=data.get("name", "Unknown"),
            coordinates=coordinates,
            population=data.get("population", 0),
            government=data.get("government", "Unknown"),
            allegiance=data.get("allegiance", "Unknown"),
            state=data.get("state", "Unknown"),
            security=data.get("security", "Unknown"),
            primary_economy=data.get("primaryEconomy") or data.get("primary_economy", "Unknown"),
            secondary_economy=data.get("secondaryEconomy") or data.get("secondary_economy", "Unknown"),
            controlling_minor_faction=controlling_faction,
            stations=stations,
            bodies=bodies,
            updated=updated,
        )

    async def search_systems(self, filters: dict[str, Any]) -> list[SpanshSystem]:
        """Search for systems using Spansh search API.

        Args:
            filters: Search filters dict (e.g., {"name": {"value": "Bleia Eohn"}}).
                Note: filter values should be strings, not arrays.

        Returns:
            List of SpanshSystem objects (summary info from search results).

        Raises:
            SpanshAPIError: If the request fails.
        """
        search_url = f"{self.base_url}/systems/search"

        # Build request payload - Spansh expects filter values as strings
        payload = {
            "filters": filters,
            "size": 50,
            "page": 0,
        }

        response = await self._request_with_retry("POST", search_url, json=payload)
        data = response.json()

        results = []
        for item in data.get("results", []):
            system = self._parse_search_result(item)
            results.append(system)

        return results

    def _parse_search_result(self, data: dict[str, Any]) -> SpanshSystem:
        """Parse system from search results (less detailed than dump)."""
        # Parse coordinates
        coordinates = [data.get("x", 0.0), data.get("y", 0.0), data.get("z", 0.0)]

        # Parse updated timestamp
        updated_str = data.get("updated_at", "")
        try:
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00")) if updated_str else datetime.now(timezone.utc)
        except Exception:
            updated = datetime.now(timezone.utc)

        # Search results have limited fields - use defaults for missing ones
        return SpanshSystem(
            id64=data.get("id64", 0),
            name=data.get("name", "Unknown"),
            coordinates=coordinates,
            population=data.get("population", 0),
            government=data.get("government", "Unknown"),
            allegiance=data.get("allegiance", "Unknown"),
            state=data.get("state", "Unknown"),
            security=data.get("security", "Unknown"),
            primary_economy=data.get("primary_economy", "Unknown"),
            secondary_economy=data.get("secondary_economy", "Unknown"),
            controlling_minor_faction=data.get("controlling_minor_faction") or data.get("controllingFaction"),
            stations=[],  # Search results don't include full station details
            bodies=data.get("bodies", []),
            updated=updated,
            distance=data.get("distance"),
        )


__all__ = [
    "SpanshClient",
    "SpanshSystem",
    "SpanshStation",
    "SpanshAPIError",
]