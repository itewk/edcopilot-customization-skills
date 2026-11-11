"""Tests for Spansh API client."""

import httpx
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from edcg.facts.spansh import (
    SpanshClient,
    SpanshSystem,
    SpanshStation,
    SpanshAPIError,
)


class TestSpanshDataStructures:
    """Tests for Spansh data structures."""

    def test_spansh_system_creation(self):
        """Test SpanshSystem dataclass creation."""
        system = SpanshSystem(
            id64=3382051836930,
            name="Bleia Eohn SX-F c12",
            coordinates=[-212.5625, -34.46875, 1514.21875],
            population=373069,
            government="Feudal",
            allegiance="Independent",
            state="Expansion",
            security="Low",
            primary_economy="Refinery",
            secondary_economy="Industrial",
            controlling_minor_faction="The Dukes of Mikunn",
            stations=[],
            bodies=[],
            updated=datetime(2026, 10, 17, 2, 50, 47, tzinfo=timezone.utc),
        )
        assert system.id64 == 3382051836930
        assert system.name == "Bleia Eohn SX-F c12"
        assert system.coordinates == [-212.5625, -34.46875, 1514.21875]
        assert system.population == 373069
        assert system.government == "Feudal"
        assert system.allegiance == "Independent"
        assert system.state == "Expansion"
        assert system.security == "Low"
        assert system.primary_economy == "Refinery"
        assert system.secondary_economy == "Industrial"
        assert system.controlling_minor_faction == "The Dukes of Mikunn"
        assert system.stations == []
        assert system.bodies == []
        assert system.updated == datetime(2026, 10, 17, 2, 50, 47, tzinfo=timezone.utc)

    def test_spansh_station_creation(self):
        """Test SpanshStation dataclass creation."""
        station = SpanshStation(
            market_id=4394738435,
            name="Cold Probabilities (ii42)",
            type="Planetary Outpost",
            controlling_minor_faction="The Dukes of Mikunn",
            controlling_minor_faction_state="Expansion",
            distance_to_arrival=442.196384,
            has_large_pad=True,
            has_market=True,
            large_pads=4,
            medium_pads=4,
            small_pads=4,
            services=[
                "Dock",
                "Autodock",
                "Market",
                "Contacts",
                "Missions",
                "Crew Lounge",
                "Restock",
                "Refuel",
                "Repair",
                "Workshop",
            ],
        )
        assert station.market_id == 4394738435
        assert station.name == "Cold Probabilities (ii42)"
        assert station.type == "Planetary Outpost"
        assert station.controlling_minor_faction == "The Dukes of Mikunn"
        assert station.controlling_minor_faction_state == "Expansion"
        assert station.distance_to_arrival == 442.196384
        assert station.has_large_pad is True
        assert station.has_market is True
        assert station.large_pads == 4
        assert station.medium_pads == 4
        assert station.small_pads == 4
        assert station.services == [
            "Dock",
            "Autodock",
            "Market",
            "Contacts",
            "Missions",
            "Crew Lounge",
            "Restock",
            "Refuel",
            "Repair",
            "Workshop",
        ]


class TestSpanshClient:
    """Tests for SpanshClient."""

    @pytest.fixture
    def client(self):
        """Create a SpanshClient instance for testing."""
        return SpanshClient()

    @pytest.fixture
    def mock_httpx_client(self):
        """Create a mock httpx AsyncClient."""
        with patch("edcg.facts.spansh.httpx.AsyncClient") as mock_class:
            mock_client = AsyncMock()
            mock_class.return_value = mock_client
            yield mock_client

    def _make_mock_response(self, json_data, status_code=200):
        """Create a mock response with proper json() method."""
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=json_data)
        if status_code >= 400:
            mock_response.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError(
                    f"{status_code} Error", request=MagicMock(), response=MagicMock(status_code=status_code)
                )
            )
        else:
            mock_response.raise_for_status = MagicMock()
        return mock_response

    @pytest.mark.asyncio
    async def test_get_system_success(self, client, mock_httpx_client):
        """Test successful get_system call."""
        # First call: field_values lookup
        lookup_response = self._make_mock_response({
            "min_max": [
                {"id64": 3382051836930, "name": "Bleia Eohn SX-F c12", "x": -212.5625, "y": -34.46875, "z": 1514.21875}
            ]
        })
        # Second call: dump endpoint - controllingFaction is an object with 'name' field
        dump_response = self._make_mock_response({
            "system": {
                "id64": 3382051836930,
                "name": "Bleia Eohn SX-F c12",
                "coords": {"x": -212.5625, "y": -34.46875, "z": 1514.21875},
                "population": 373069,
                "government": "Feudal",
                "allegiance": "Independent",
                "state": "Expansion",
                "security": "Low",
                "primaryEconomy": "Refinery",
                "secondaryEconomy": "Industrial",
                "controllingFaction": {
                    "name": "The Dukes of Mikunn",
                    "allegiance": "Independent",
                    "government": "Feudal",
                    "state": "Expansion",
                    "activeStates": [{"state": "Expansion"}]
                },
                "stations": [
                    {
                        "id": 4394738435,
                        "name": "Cold Probabilities (ii42)",
                        "type": "Planetary Outpost",
                        "controllingFaction": "The Dukes of Mikunn",
                        "controllingFactionState": "Expansion",
                        "distanceToArrival": 442.196384,
                        "has_large_pad": True,
                        "has_market": True,
                        "landingPads": {"large": 4, "medium": 4, "small": 4},
                        "services": ["Dock", "Autodock", "Market", "Contacts", "Missions"],
                    }
                ],
                "bodies": [
                    {"name": "Bleia Eohn SX-F c12", "type": "Star", "subType": "K (Yellow-Orange) Star"},
                    {"name": "Bleia Eohn SX-F c12 1", "type": "Planet", "subType": "Water world"},
                ],
                "updateTime": "2026-10-17T02:50:47Z",
            }
        })

        # Mock request to return different responses for each call
        mock_httpx_client.request = AsyncMock(side_effect=[lookup_response, dump_response])

        result = await client.get_system("Bleia Eohn SX-F c12")

        assert isinstance(result, SpanshSystem)
        assert result.id64 == 3382051836930
        assert result.name == "Bleia Eohn SX-F c12"
        assert result.coordinates == [-212.5625, -34.46875, 1514.21875]
        assert result.population == 373069
        assert result.government == "Feudal"
        assert result.allegiance == "Independent"
        assert result.state == "Expansion"
        assert result.security == "Low"
        assert result.primary_economy == "Refinery"
        assert result.secondary_economy == "Industrial"
        assert result.controlling_minor_faction == "The Dukes of Mikunn"
        assert len(result.stations) == 1
        assert result.stations[0].market_id == 4394738435
        assert result.stations[0].name == "Cold Probabilities (ii42)"
        assert len(result.bodies) == 2
        assert result.updated == datetime(2026, 10, 17, 2, 50, 47, tzinfo=timezone.utc)
        assert mock_httpx_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_get_system_not_found(self, client, mock_httpx_client):
        """Test get_system raises SpanshAPIError on 404."""
        mock_response = self._make_mock_response({}, status_code=404)
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        with pytest.raises(SpanshAPIError) as exc_info:
            await client.get_system("Nonexistent System")

        assert "404" in str(exc_info.value) or "Not Found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_system_network_error(self, client, mock_httpx_client):
        """Test get_system raises SpanshAPIError on network error."""
        mock_httpx_client.request = AsyncMock(side_effect=httpx.RequestError("Connection failed"))

        with pytest.raises(SpanshAPIError) as exc_info:
            await client.get_system("Test System")

        assert "Connection failed" in str(exc_info.value) or "network" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_system_timeout(self, client, mock_httpx_client):
        """Test get_system handles timeout."""
        mock_httpx_client.request = AsyncMock(side_effect=httpx.TimeoutException("Request timed out"))

        with pytest.raises(SpanshAPIError) as exc_info:
            await client.get_system("Test System")

        assert "timed out" in str(exc_info.value).lower() or "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_system_url_encoding(self, client, mock_httpx_client):
        """Test that system names with special characters are URL encoded."""
        lookup_response = self._make_mock_response({
            "min_max": [{"id64": 12345, "name": "System With Spaces & Symbols", "x": 0.0, "y": 0.0, "z": 0.0}]
        })
        dump_response = self._make_mock_response({
            "system": {
                "id64": 12345,
                "name": "System With Spaces & Symbols",
                "coords": {"x": 0.0, "y": 0.0, "z": 0.0},
                "population": 0,
                "government": "None",
                "allegiance": "None",
                "state": "None",
                "security": "None",
                "primaryEconomy": "None",
                "secondaryEconomy": "None",
                "stations": [],
                "bodies": [],
                "updateTime": "2024-01-01T00:00:00Z",
            }
        })
        mock_httpx_client.request = AsyncMock(side_effect=[lookup_response, dump_response])

        await client.get_system("System With Spaces & Symbols")

        # Check first call URL has encoded name
        call_args = mock_httpx_client.request.call_args_list[0]
        url = call_args[0][1]
        assert "System%20With%20Spaces%20%26%20Symbols" in url

    @pytest.mark.asyncio
    async def test_search_systems_success(self, client, mock_httpx_client):
        """Test successful search_systems call."""
        mock_response = self._make_mock_response({
            "count": 1,
            "from": 0,
            "results": [
                {
                    "id64": 3382051836930,
                    "name": "Bleia Eohn SX-F c12",
                    "distance": 1529.45,
                    "population": 373069,
                    "government": "Feudal",
                    "allegiance": "Independent",
                    "state": "Expansion",
                    "security": "Low",
                    "primary_economy": "Refinery",
                    "secondary_economy": "Industrial",
                    "x": -212.5625,
                    "y": -34.46875,
                    "z": 1514.21875,
                    "updated_at": "2026-10-17T02:50:47Z",
                }
            ],
            "search": {"filters": {"name": {"value": "Bleia Eohn"}}},
        })
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        result = await client.search_systems({"name": {"value": "Bleia Eohn"}})

        assert isinstance(result, list)
        assert len(result) == 1
        system = result[0]
        assert isinstance(system, SpanshSystem)
        assert system.id64 == 3382051836930
        assert system.name == "Bleia Eohn SX-F c12"
        assert system.distance == 1529.45
        mock_httpx_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_systems_empty_results(self, client, mock_httpx_client):
        """Test search_systems returns empty list when no results."""
        mock_response = self._make_mock_response({
            "count": 0,
            "from": 0,
            "results": [],
            "search": {"filters": {"name": {"value": "Nonexistent"}}},
        })
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        result = await client.search_systems({"name": {"value": "Nonexistent"}})

        assert result == []

    @pytest.mark.asyncio
    async def test_search_systems_network_error(self, client, mock_httpx_client):
        """Test search_systems raises SpanshAPIError on network error."""
        mock_httpx_client.request = AsyncMock(side_effect=httpx.RequestError("Connection failed"))

        with pytest.raises(SpanshAPIError) as exc_info:
            await client.search_systems({"name": {"value": "Test"}})

        assert "Connection failed" in str(exc_info.value) or "network" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_client_custom_timeout(self):
        """Test client can be configured with custom timeout."""
        client = SpanshClient(timeout=30.0)
        assert client.timeout == 30.0

    @pytest.mark.asyncio
    async def test_client_custom_retries(self):
        """Test client can be configured with custom retry count."""
        client = SpanshClient(max_retries=5)
        assert client.max_retries == 5

    @pytest.mark.asyncio
    async def test_client_context_manager(self):
        """Test client works as async context manager."""
        async with SpanshClient() as client:
            assert client._client is not None


class TestSpanshClientIntegration:
    """Integration tests for SpanshClient (require network)."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_api_bleia_eohn(self):
        """Test real API call for Bleia Eohn SX-F c12 - verify station list."""
        client = SpanshClient()

        try:
            system = await client.get_system("Bleia Eohn SX-F c12")
            assert system.name == "Bleia Eohn SX-F c12"
            assert system.id64 == 3382051836930
            assert system.population == 373069
            assert system.government == "Feudal"
            # controlling_minor_faction is now correctly parsed from controllingFaction
            assert system.controlling_minor_faction == "The Dukes of Mikunn"
            assert len(system.stations) > 0

            # Verify the station payload parsed. Do not assert on specific
            # station names: carriers move between systems and construction
            # sites are renamed when finished, so any particular name makes
            # this test flaky.
            station_names = [s.name for s in system.stations]
            assert all(station_names)
            assert all(s.type for s in system.stations)
            assert len(station_names) == len(set(station_names))
        finally:
            await client.close()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_api_search_systems(self):
        """Test real API call for system search."""
        client = SpanshClient()

        try:
            # Search API expects string value, not array
            results = await client.search_systems({"name": {"value": "Bleia Eohn"}})
            assert len(results) > 0
            # Should find multiple Bleia Eohn systems
            names = [r.name for r in results]
            assert any("Bleia Eohn" in n for n in names)
        finally:
            await client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])