"""Tests for Inara API client."""

import httpx
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from edcg.facts.inara import (
    InaraClient,
    InaraStation,
    InaraSystem,
    InaraAPIError,
)


class TestInaraDataStructures:
    """Tests for Inara data structures."""

    def test_inara_station_creation(self):
        """Test InaraStation dataclass creation."""
        station = InaraStation(
            name="Jameson Memorial",
            type="Orbis",
            services=["Market", "Shipyard", "Outfitting", "Rearm", "Refuel"],
            economy="Extraction",
            updated=datetime(2024, 1, 15, 12, 30, 0),
        )
        assert station.name == "Jameson Memorial"
        assert station.type == "Orbis"
        assert station.services == ["Market", "Shipyard", "Outfitting", "Rearm", "Refuel"]
        assert station.economy == "Extraction"
        assert station.updated == datetime(2024, 1, 15, 12, 30, 0)

    def test_inara_station_minimal(self):
        """Test InaraStation with minimal fields."""
        station = InaraStation(
            name="Test Station",
            type="Coriolis",
            services=[],
            economy="None",
            updated=datetime.now(),
        )
        assert station.name == "Test Station"
        assert station.type == "Coriolis"
        assert station.services == []
        assert station.economy == "None"

    def test_inara_system_creation(self):
        """Test InaraSystem dataclass creation."""
        system = InaraSystem(
            name="Sol",
            coordinates=[0.0, 0.0, 0.0],
            population=1000000000,
            government="Democracy",
            allegiance="Federation",
            state="Boom",
            security="High",
            primary_economy="High Tech",
            updated=datetime(2024, 1, 15, 12, 30, 0),
        )
        assert system.name == "Sol"
        assert system.coordinates == [0.0, 0.0, 0.0]
        assert system.population == 1000000000
        assert system.government == "Democracy"
        assert system.allegiance == "Federation"
        assert system.state == "Boom"
        assert system.security == "High"
        assert system.primary_economy == "High Tech"
        assert system.updated == datetime(2024, 1, 15, 12, 30, 0)


class TestInaraClient:
    """Tests for InaraClient."""

    @pytest.fixture
    def client(self):
        """Create an InaraClient instance for testing."""
        return InaraClient("test-api-key-123")

    @pytest.fixture
    def client_no_key(self):
        """Create an InaraClient instance without API key."""
        return InaraClient(None)

    @pytest.fixture
    def mock_httpx_client(self):
        """Create a mock httpx AsyncClient."""
        with patch("edcg.facts.inara.httpx.AsyncClient") as mock_class:
            mock_client = AsyncMock()
            mock_class.return_value = mock_client
            yield mock_client

    @pytest.mark.asyncio
    async def test_get_station_success(self, client, mock_httpx_client):
        """Test successful get_station call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "header": {"eventStatus": 200},
            "events": [
                {
                    "eventStatus": 200,
                    "eventData": {
                        "stationName": "Jameson Memorial",
                        "stationType": "Orbis",
                        "stationServices": ["Market", "Shipyard", "Outfitting", "Rearm", "Refuel"],
                        "stationEconomy": "Extraction",
                        "stationUpdated": "2024-01-15T12:30:00Z",
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        result = await client.get_station("Shinrarta Dezhra", "Jameson Memorial")

        assert isinstance(result, InaraStation)
        assert result.name == "Jameson Memorial"
        assert result.type == "Orbis"
        assert result.services == ["Market", "Shipyard", "Outfitting", "Rearm", "Refuel"]
        assert result.economy == "Extraction"
        assert result.updated == datetime(2024, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
        mock_httpx_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_station_missing_key(self, client_no_key):
        """Test get_station returns None when no API key configured."""
        result = await client_no_key.get_station("Sol", "Test Station")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_station_not_found(self, client, mock_httpx_client):
        """Test get_station handles 204 (not found) response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "header": {"eventStatus": 200},
            "events": [
                {
                    "eventStatus": 204,
                    "eventStatusText": "No results found.",
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        result = await client.get_station("Unknown System", "Unknown Station")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_station_rate_limit(self, client, mock_httpx_client):
        """Test get_station handles rate limit (429) gracefully."""
        mock_httpx_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=MagicMock(),
                response=MagicMock(status_code=429)
            )
        )

        with pytest.raises(InaraAPIError) as exc_info:
            await client.get_station("Sol", "Test Station")

        assert "429" in str(exc_info.value) or "rate limit" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_station_network_error(self, client, mock_httpx_client):
        """Test get_station raises InaraAPIError on network error."""
        mock_httpx_client.post = AsyncMock(side_effect=httpx.RequestError("Connection failed"))

        with pytest.raises(InaraAPIError) as exc_info:
            await client.get_station("Sol", "Test Station")

        assert "Connection failed" in str(exc_info.value) or "network" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_station_timeout(self, client, mock_httpx_client):
        """Test get_station handles timeout."""
        mock_httpx_client.post = AsyncMock(side_effect=httpx.TimeoutException("Request timed out"))

        with pytest.raises(InaraAPIError) as exc_info:
            await client.get_station("Sol", "Test Station")

        assert "timed out" in str(exc_info.value).lower() or "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_search_system_success(self, client, mock_httpx_client):
        """Test successful search_system call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "header": {"eventStatus": 200},
            "events": [
                {
                    "eventStatus": 200,
                    "eventData": {
                        "starSystemName": "Sol",
                        "starSystemCoordinates": [0.0, 0.0, 0.0],
                        "starSystemPopulation": 1000000000,
                        "starSystemGovernment": "Democracy",
                        "starSystemAllegiance": "Federation",
                        "starSystemState": "Boom",
                        "starSystemSecurity": "High",
                        "starSystemPrimaryEconomy": "High Tech",
                        "starSystemUpdated": "2024-01-15T12:30:00Z",
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        result = await client.search_system("Sol")

        assert isinstance(result, InaraSystem)
        assert result.name == "Sol"
        assert result.coordinates == [0.0, 0.0, 0.0]
        assert result.population == 1000000000
        assert result.government == "Democracy"
        assert result.allegiance == "Federation"
        assert result.state == "Boom"
        assert result.security == "High"
        assert result.primary_economy == "High Tech"
        assert result.updated == datetime(2024, 1, 15, 12, 30, 0, tzinfo=timezone.utc)

    @pytest.mark.asyncio
    async def test_search_system_missing_key(self, client_no_key):
        """Test search_system returns None when no API key configured."""
        result = await client_no_key.search_system("Sol")
        assert result is None

    @pytest.mark.asyncio
    async def test_search_system_not_found(self, client, mock_httpx_client):
        """Test search_system handles 204 (not found) response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "header": {"eventStatus": 200},
            "events": [
                {
                    "eventStatus": 204,
                    "eventStatusText": "No results found.",
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        result = await client.search_system("Unknown System")
        assert result is None

    @pytest.mark.asyncio
    async def test_client_context_manager(self):
        """Test client works as async context manager."""
        async with InaraClient("test-key") as client:
            assert client._client is not None

    @pytest.mark.asyncio
    async def test_client_custom_timeout(self):
        """Test client can be configured with custom timeout."""
        client = InaraClient("test-key", timeout=30.0)
        assert client.timeout == 30.0

    @pytest.mark.asyncio
    async def test_client_custom_retries(self):
        """Test client can be configured with custom retry count."""
        client = InaraClient("test-key", max_retries=5)
        assert client.max_retries == 5


class TestInaraClientIntegration:
    """Integration tests for InaraClient (require network and API key)."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_api_get_station(self):
        """Test real API call for a known station."""
        # This test requires network and valid API key
        # Run with: pytest -m integration
        import os
        api_key = os.environ.get("INARA_API_KEY")
        if not api_key:
            pytest.skip("INARA_API_KEY not set")

        client = InaraClient(api_key)

        try:
            station = await client.get_station("Shinrarta Dezhra", "Jameson Memorial")
            if station:
                assert station.name == "Jameson Memorial"
                assert station.type is not None
                assert isinstance(station.services, list)
                assert station.economy is not None
                assert station.updated is not None
        finally:
            await client.close()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_api_search_system(self):
        """Test real API call for a known system."""
        import os
        api_key = os.environ.get("INARA_API_KEY")
        if not api_key:
            pytest.skip("INARA_API_KEY not set")

        client = InaraClient(api_key)

        try:
            system = await client.search_system("Sol")
            if system:
                assert system.name == "Sol"
                assert system.coordinates is not None
                assert isinstance(system.coordinates, list)
                assert len(system.coordinates) == 3
        finally:
            await client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])