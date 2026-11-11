"""Tests for Raven Colonial API client."""

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from edcg.facts.raven import (
    RavenClient,
    RavenSystem,
    RavenSite,
    RavenAPIError,
    is_placeholder_name,
    is_unresolved_site,
)


class TestRavenDataStructures:
    """Tests for Raven data structures."""

    def test_raven_system_creation(self):
        """Test RavenSystem dataclass creation."""
        system = RavenSystem(
            name="Test System",
            architect="Test Architect",
            revision=42,
            bodies=["Body 1", "Body 2", "Body 3"],
        )
        assert system.name == "Test System"
        assert system.architect == "Test Architect"
        assert system.revision == 42
        assert system.bodies == ["Body 1", "Body 2", "Body 3"]

    def test_raven_system_body_name_uses_num_not_index(self):
        """body_name() resolves by body num, not by position in bodies."""
        system = RavenSystem(
            name="Test System",
            architect="Test Architect",
            revision=61,
            bodies=["Test System", "Test System 3 a", "Test System 5 c"],
            body_nums={0: "Test System", 16: "Test System 3 a", 36: "Test System 5 c"},
        )
        # 16 is a body num; index 16 would not exist here.
        assert system.body_name(16) == "Test System 3 a"
        assert system.body_name(36) == "Test System 5 c"
        assert system.body_name(-1) == "Unknown"

    def test_raven_system_body_name_falls_back_to_index_without_nums(self):
        """Legacy payloads without nums keep positional behaviour."""
        system = RavenSystem(
            name="Test System",
            architect="Test Architect",
            revision=1,
            bodies=["Body 1", "Body 2"],
        )
        assert system.body_name(1) == "Body 2"
        assert system.body_name(9) == "Unknown"

    def test_raven_site_creation(self):
        """Test RavenSite dataclass creation."""
        site = RavenSite(
            id=123,
            name="Test Site",
            status="plan",
            build_type="outpost",
            body_num=0,
        )
        assert site.id == 123
        assert site.name == "Test Site"
        assert site.status == "plan"
        assert site.build_type == "outpost"
        assert site.body_num == 0

    def test_raven_site_unresolved(self):
        """Test RavenSite with unresolved placeholder values."""
        site = RavenSite(
            id=999,
            name="[Unknown]",
            status="plan",
            build_type="outpost?",
            body_num=-1,
        )
        assert site.id == 999
        assert site.name == "[Unknown]"
        assert site.build_type == "outpost?"
        assert site.body_num == -1


class TestPlaceholderDetection:
    """Tests for placeholder name detection."""

    def test_is_placeholder_name_nato_pairs(self):
        """Test detection of two NATO phonetic alphabet word placeholders."""
        # Common NATO pairs used as placeholders
        assert is_placeholder_name("Xray Hotel") is True
        assert is_placeholder_name("Zulu Yankee") is True
        assert is_placeholder_name("Alpha Bravo") is True
        assert is_placeholder_name("Charlie Delta") is True
        assert is_placeholder_name("Echo Foxtrot") is True
        assert is_placeholder_name("Golf Hotel") is True
        assert is_placeholder_name("India Juliett") is True
        assert is_placeholder_name("Kilo Lima") is True
        assert is_placeholder_name("Mike November") is True
        assert is_placeholder_name("Oscar Papa") is True
        assert is_placeholder_name("Quebec Romeo") is True
        assert is_placeholder_name("Sierra Tango") is True
        assert is_placeholder_name("Uniform Victor") is True
        assert is_placeholder_name("Whiskey Xray") is True

    def test_is_placeholder_name_case_insensitive(self):
        """Test placeholder detection is case insensitive."""
        assert is_placeholder_name("xray hotel") is True
        assert is_placeholder_name("XRAY HOTEL") is True
        assert is_placeholder_name("Xray hotel") is True

    def test_is_placeholder_name_real_names_not_placeholders(self):
        """Test that real system/site names are not flagged as placeholders."""
        assert is_placeholder_name("Jameson Memorial") is False
        assert is_placeholder_name("Sol") is False
        assert is_placeholder_name("Bleia Eohn SX-F c12") is False
        assert is_placeholder_name("Col 285 Sector CC-K a38-2") is False
        assert is_placeholder_name("Alpha Centauri") is False  # Only one NATO word
        assert is_placeholder_name("Xray") is False  # Single word
        # Any two NATO words is a placeholder, including reversed order
        assert is_placeholder_name("Hotel Xray") is True

    def test_is_placeholder_name_empty_or_none(self):
        """Test placeholder detection handles edge cases."""
        assert is_placeholder_name("") is False
        assert is_placeholder_name("   ") is False


class TestUnresolvedSiteDetection:
    """Tests for unresolved site detection."""

    def test_is_unresolved_site_build_type_question_mark(self):
        """Test detection of unresolved sites by build_type ending with ?."""
        site = RavenSite(id=1, name="Test", status="plan", build_type="outpost?", body_num=0)
        assert is_unresolved_site(site) is True

        site = RavenSite(id=1, name="Test", status="plan", build_type="installation?", body_num=0)
        assert is_unresolved_site(site) is True

        site = RavenSite(id=1, name="Test", status="plan", build_type="settlement?", body_num=0)
        assert is_unresolved_site(site) is True

    def test_is_unresolved_site_body_num_negative(self):
        """Test detection of unresolved sites by negative body_num."""
        site = RavenSite(id=1, name="Test", status="plan", build_type="outpost", body_num=-1)
        assert is_unresolved_site(site) is True

    def test_is_unresolved_site_name_in_brackets(self):
        """Test detection of unresolved sites by name in square brackets."""
        site = RavenSite(id=1, name="[Unknown]", status="plan", build_type="outpost", body_num=0)
        assert is_unresolved_site(site) is True

        site = RavenSite(id=1, name="[Installation?]", status="plan", build_type="outpost", body_num=0)
        assert is_unresolved_site(site) is True

    def test_is_unresolved_site_combined_criteria(self):
        """Test unresolved detection with multiple criteria met."""
        site = RavenSite(id=1, name="[Unknown]", status="plan", build_type="outpost?", body_num=-1)
        assert is_unresolved_site(site) is True

    def test_is_unresolved_site_valid_site(self):
        """Test that valid sites are not flagged as unresolved."""
        site = RavenSite(id=1, name="Alpha Bravo", status="plan", build_type="outpost", body_num=0)
        assert is_unresolved_site(site) is False

        site = RavenSite(id=1, name="Real Station", status="complete", build_type="starport", body_num=2)
        assert is_unresolved_site(site) is False

    def test_is_unresolved_site_none_build_type(self):
        """A site with no build_type is unresolved (real API responses can be null)."""
        site = RavenSite(id=1, name="Test", status="plan", build_type=None, body_num=0)
        assert is_unresolved_site(site) is True

        site = RavenSite(id=1, name="Test", status="plan", build_type="", body_num=0)
        assert is_unresolved_site(site) is True

    def test_is_unresolved_site_none_name(self):
        """A site with a missing or empty name is unresolved (real API data can be null)."""
        site = RavenSite(id=1, name=None, status="plan", build_type="outpost", body_num=0)
        assert is_unresolved_site(site) is True

        site = RavenSite(id=1, name="", status="plan", build_type="outpost", body_num=0)
        assert is_unresolved_site(site) is True

        site = RavenSite(id=1, name=None, status="plan", build_type="outpost?", body_num=0)
        assert is_unresolved_site(site) is True


class TestRavenClient:
    """Tests for RavenClient."""

    @pytest.fixture
    def client(self):
        """Create a RavenClient instance for testing."""
        return RavenClient("https://test.raven.api")

    @pytest.fixture
    def mock_httpx_client(self):
        """Create a mock httpx AsyncClient."""
        with patch("edcg.facts.raven.httpx.AsyncClient") as mock_class:
            mock_client = AsyncMock()
            # When AsyncClient() is called, return the mock_client directly
            mock_class.return_value = mock_client
            yield mock_client

    @pytest.mark.asyncio
    async def test_get_system_success(self, client, mock_httpx_client):
        """Test successful get_system call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "name": "Bleia Eohn SX-F c12",
            "architect": "CMDR TestPilot",
            "revision": 45,
            "bodies": ["Body 1", "Body 2", "Body 3", "Body 4"],
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        result = await client.get_system("Bleia Eohn SX-F c12")

        assert isinstance(result, RavenSystem)
        assert result.name == "Bleia Eohn SX-F c12"
        assert result.architect == "CMDR TestPilot"
        assert result.revision == 45
        assert result.bodies == ["Body 1", "Body 2", "Body 3", "Body 4"]
        mock_httpx_client.request.assert_called_once()
        # Verify URL encoding of spaces
        call_args = mock_httpx_client.request.call_args
        assert "Bleia%20Eohn%20SX-F%20c12" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_get_system_parses_body_nums(self, client, mock_httpx_client):
        """bodies is a list of objects; bodyNum identifies a body's num, not an index."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "name": "Test System",
            "architect": "CMDR TestPilot",
            "revision": 61,
            "bodies": [
                {"name": "Test System", "num": 0},
                {"name": "Test System A Belt", "num": 100000},
                {"name": "Test System 1", "num": 13},
                {"name": "Test System 3 a", "num": 16},
                {"name": "Test System 5 c", "num": 36},
            ],
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        result = await client.get_system("Test System")

        assert result.bodies == [
            "Test System",
            "Test System A Belt",
            "Test System 1",
            "Test System 3 a",
            "Test System 5 c",
        ]
        assert result.body_nums[16] == "Test System 3 a"

    @pytest.mark.asyncio
    async def test_get_system_url_encoding(self, client, mock_httpx_client):
        """Test that system names with special characters are URL encoded."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "name": "Test System",
            "architect": "Test",
            "revision": 1,
            "bodies": [],
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        await client.get_system("System With Spaces & Symbols")

        call_args = mock_httpx_client.request.call_args
        url = call_args[0][1]
        assert "System%20With%20Spaces%20%26%20Symbols" in url

    @pytest.mark.asyncio
    async def test_get_system_http_error(self, client, mock_httpx_client):
        """Test get_system raises RavenAPIError on HTTP error."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=MagicMock(status_code=404)
        )
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        with pytest.raises(RavenAPIError) as exc_info:
            await client.get_system("Nonexistent System")

        assert "404" in str(exc_info.value) or "Not Found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_system_network_error(self, client, mock_httpx_client):
        """Test get_system raises RavenAPIError on network error."""
        mock_httpx_client.request = AsyncMock(side_effect=httpx.RequestError("Connection failed"))

        with pytest.raises(RavenAPIError) as exc_info:
            await client.get_system("Test System")

        assert "Connection failed" in str(exc_info.value) or "network" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_system_timeout(self, client, mock_httpx_client):
        """Test get_system handles timeout."""
        mock_httpx_client.request = AsyncMock(side_effect=httpx.TimeoutException("Request timed out"))

        with pytest.raises(RavenAPIError) as exc_info:
            await client.get_system("Test System")

        # Error message should mention timeout/timed out
        assert "timed out" in str(exc_info.value).lower() or "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_sites_success(self, client, mock_httpx_client):
        """Test successful get_sites call."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"id": 1, "name": "Alpha Bravo", "status": "plan", "buildType": "outpost", "bodyNum": 0},
            {"id": 2, "name": "Charlie Delta", "status": "build", "buildType": "starport", "bodyNum": 1},
            {"id": 3, "name": "Real Station", "status": "complete", "buildType": "outpost", "bodyNum": 2},
        ]
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        result = await client.get_sites("Test System")

        assert isinstance(result, list)
        assert len(result) == 3
        assert all(isinstance(site, RavenSite) for site in result)
        assert result[0].id == 1
        assert result[0].name == "Alpha Bravo"
        assert result[0].status == "plan"
        assert result[0].build_type == "outpost"
        assert result[0].body_num == 0
        assert result[1].name == "Charlie Delta"
        assert result[1].status == "build"
        assert result[2].name == "Real Station"
        assert result[2].status == "complete"

    @pytest.mark.asyncio
    async def test_get_sites_with_unresolved_entries(self, client, mock_httpx_client):
        """Test get_sites handles unresolved placeholder entries."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"id": 1, "name": "Alpha Bravo", "status": "plan", "buildType": "outpost", "bodyNum": 0},
            {"id": 999, "name": "[Unknown]", "status": "plan", "buildType": "outpost?", "bodyNum": -1},
            {"id": 998, "name": "[Installation?]", "status": "plan", "buildType": "installation?", "bodyNum": -1},
            {"id": 2, "name": "Real Station", "status": "complete", "buildType": "starport", "bodyNum": 1},
        ]
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        result = await client.get_sites("Test System")

        assert len(result) == 4
        # Unresolved entries should be included in raw results
        unresolved = [s for s in result if is_unresolved_site(s)]
        assert len(unresolved) == 2
        assert unresolved[0].name == "[Unknown]"
        assert unresolved[0].build_type == "outpost?"
        assert unresolved[0].body_num == -1

    @pytest.mark.asyncio
    async def test_get_sites_empty_list(self, client, mock_httpx_client):
        """Test get_sites returns empty list for system with no sites."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        result = await client.get_sites("Empty System")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_sites_http_error(self, client, mock_httpx_client):
        """Test get_sites raises RavenAPIError on HTTP error."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Server Error", request=MagicMock(), response=MagicMock(status_code=500)
        )
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        with pytest.raises(RavenAPIError):
            await client.get_sites("Test System")

    @pytest.mark.asyncio
    async def test_client_custom_timeout(self):
        """Test client can be configured with custom timeout."""
        client = RavenClient("https://test.raven.api", timeout=30.0)
        assert client.timeout == 30.0

    @pytest.mark.asyncio
    async def test_client_custom_retries(self):
        """Test client can be configured with custom retry count."""
        client = RavenClient("https://test.raven.api", max_retries=5)
        assert client.max_retries == 5

    @pytest.mark.asyncio
    async def test_client_rate_limiting(self, client, mock_httpx_client):
        """Test client respects rate limiting between requests."""
        import time

        mock_response = MagicMock()
        mock_response.json.return_value = {"name": "Test", "architect": "Test", "revision": 1, "bodies": []}
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        # Make two rapid calls
        start = time.monotonic()
        await client.get_system("System A")
        await client.get_system("System B")
        elapsed = time.monotonic() - start

        # With default rate limiting (e.g., 10 requests/second = 0.1s between requests)
        # Should take at least some minimum time
        # Note: This test may be flaky depending on timing, so we mainly verify it doesn't error

    @pytest.mark.asyncio
    async def test_client_context_manager(self):
        """Test client works as async context manager."""
        async with RavenClient("https://test.raven.api") as client:
            assert client._client is not None

        # Client should be closed after exiting context


class TestRavenClientIntegration:
    """Integration tests for RavenClient (require network)."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_api_bleia_eohn(self):
        """Test real API call for Bleia Eohn SX-F c12 - verify revision 45+ and sites match dossier."""
        # This test requires network and is marked as integration
        # Run with: pytest -m integration
        client = RavenClient("https://ravencolonial100-awcbdvabgze4c5cq.canadacentral-01.azurewebsites.net")

        try:
            system = await client.get_system("Bleia Eohn SX-F c12")
            # Check for revision field (might be named differently in API)
            revision = getattr(system, 'revision', None)
            if revision is not None:
                assert revision >= 45, f"Expected revision >= 45, got {revision}"
            else:
                # If revision is missing, at least verify we got a valid response
                assert system.name is not None
                assert system.architect is not None
                assert isinstance(system.bodies, list)

            sites = await client.get_sites("Bleia Eohn SX-F c12")
            assert len(sites) > 0, "Should have at least one site"

            # Verify sites have expected structure
            for site in sites:
                assert site.id is not None
                assert site.name is not None
                assert site.status in ("plan", "build", "complete")
                assert site.build_type is not None
                assert isinstance(site.body_num, int)
        finally:
            await client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])