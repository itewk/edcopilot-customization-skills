"""Inara API client for the EDCoPilot system content skill.

Provides async HTTP client for fetching station and system data from
the Inara API v2.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from edcg.facts._http import ApiClient, ApiError


@dataclass
class InaraStation:
    """Represents a station from Inara."""
    name: str
    type: str
    services: list[str]
    economy: str
    updated: datetime


@dataclass
class InaraSystem:
    """Represents a star system from Inara."""
    name: str
    coordinates: list[float]
    population: int
    government: str
    allegiance: str
    state: str
    security: str
    primary_economy: str
    updated: datetime


class InaraAPIError(ApiError):
    """Exception raised for Inara API errors."""
    pass


class InaraClient(ApiClient):
    """Async HTTP client for the Inara API v2.

    Provides methods to fetch station and system data with configurable
    retry, timeout, and rate limiting.

    Redirects are deliberately not followed. The old package followed them,
    but this client POSTs a JSON body carrying the Inara API key: replaying
    that body cross-origin on a 307/308 is an unnecessary exposure, and a
    redirect from the API endpoint signals a configuration problem rather
    than a legitimate move. A redirect therefore reaches the caller
    unfollowed: the 3xx body is usually HTML, so parsing it fails and the
    request surfaces as ``InaraAPIError("Invalid JSON response")`` rather
    than a successful response.
    """

    error_type = InaraAPIError
    follow_redirects = False
    retry_statuses = frozenset({429})
    request_verb = "post"

    def __init__(
        self,
        api_key: Optional[str],
        base_url: str = "https://inara.cz/inapi/v1/",
        timeout: float = 30.0,
        max_retries: int = 3,
        rate_limit: float = 5.0,  # requests per second
    ):
        """Initialize the Inara client.

        Args:
            api_key: Inara API key (personal or generic). If None, client
                operates in degraded mode (all queries return None).
            base_url: Base URL of the Inara API.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts for failed requests.
            rate_limit: Maximum requests per second (0 = no limit).
        """
        self.api_key = api_key
        super().__init__(base_url, timeout, max_retries, rate_limit)

    def _build_request(self, event_name: str, event_data: dict[str, Any]) -> dict[str, Any]:
        """Build the Inara API request payload."""
        return {
            "header": {
                "appName": "EDCoPilot-Customization-Generator",
                "appVersion": "0.1.0",
                "isBeingDeveloped": True,
                "APIkey": self.api_key or "",
            },
            "events": [
                {
                    "eventName": event_name,
                    "eventTimestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "eventData": event_data,
                }
            ],
        }

    def _parse_response(self, response: httpx.Response, event_name: str) -> Optional[dict[str, Any]]:
        """Parse Inara API response and extract event data."""
        try:
            data: dict[str, Any] = response.json()
        except Exception as e:
            raise InaraAPIError(f"Invalid JSON response: {e}") from e

        # Check header status
        header = data.get("header", {})
        header_status = header.get("eventStatus")
        if header_status == 400:
            raise InaraAPIError("API request failed: invalid request or authorization")

        # Find the matching event in response
        events = data.get("events", [])
        for event in events:
            # Response events may not have eventName, but we match by order
            event_status = event.get("eventStatus")
            if event_status == 204:
                # Not found - soft error
                return None
            elif event_status == 200:
                event_data = event.get("eventData")
                if isinstance(event_data, dict):
                    return event_data
                return {}
            elif event_status == 202:
                # Warning - still return data if present
                event_data = event.get("eventData")
                if isinstance(event_data, dict):
                    return event_data
                return {}
            elif event_status and event_status >= 400:
                status_text = event.get("eventStatusText", "Unknown error")
                raise InaraAPIError(f"API error {event_status}: {status_text}")

        # No valid event found
        return None

    async def get_station(self, system: str, station: str) -> Optional[InaraStation]:
        """Fetch station data from Inara.

        Args:
            system: Star system name.
            station: Station name.

        Returns:
            InaraStation object or None if not found or no API key.

        Raises:
            InaraAPIError: If the request fails.
        """
        # Graceful degradation: no API key configured
        if not self.api_key:
            return None

        payload = self._build_request(
            "getStation",
            {
                "starSystemName": system,
                "stationName": station,
            }
        )

        response = await self._request_with_retry("POST", self.base_url, json=payload)
        event_data = self._parse_response(response, "getStation")

        if event_data is None:
            return None

        # Parse station data
        try:
            updated_str = event_data.get("stationUpdated", "")
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00")) if updated_str else datetime.now(timezone.utc)

            return InaraStation(
                name=event_data.get("stationName", station),
                type=event_data.get("stationType", "Unknown"),
                services=event_data.get("stationServices", []),
                economy=event_data.get("stationEconomy", "Unknown"),
                updated=updated,
            )
        except Exception as e:
            raise InaraAPIError(f"Failed to parse station data: {e}") from e

    async def search_system(self, name: str) -> Optional[InaraSystem]:
        """Search for a star system by name.

        Args:
            name: Star system name.

        Returns:
            InaraSystem object or None if not found or no API key.

        Raises:
            InaraAPIError: If the request fails.
        """
        # Graceful degradation: no API key configured
        if not self.api_key:
            return None

        payload = self._build_request(
            "getStarSystem",
            {
                "starSystemName": name,
            }
        )

        response = await self._request_with_retry("POST", self.base_url, json=payload)
        event_data = self._parse_response(response, "getStarSystem")

        if event_data is None:
            return None

        # Parse system data
        try:
            updated_str = event_data.get("starSystemUpdated", "")
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00")) if updated_str else datetime.now(timezone.utc)

            coords = event_data.get("starSystemCoordinates", [0.0, 0.0, 0.0])
            if isinstance(coords, list) and len(coords) == 3:
                coordinates = [float(c) for c in coords]
            else:
                coordinates = [0.0, 0.0, 0.0]

            return InaraSystem(
                name=event_data.get("starSystemName", name),
                coordinates=coordinates,
                population=int(event_data.get("starSystemPopulation", 0) or 0),
                government=event_data.get("starSystemGovernment", "Unknown"),
                allegiance=event_data.get("starSystemAllegiance", "Unknown"),
                state=event_data.get("starSystemState", "Unknown"),
                security=event_data.get("starSystemSecurity", "Unknown"),
                primary_economy=event_data.get("starSystemPrimaryEconomy", "Unknown"),
                updated=updated,
            )
        except Exception as e:
            raise InaraAPIError(f"Failed to parse system data: {e}") from e


__all__ = [
    "InaraClient",
    "InaraStation",
    "InaraSystem",
    "InaraAPIError",
]