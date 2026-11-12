"""Tests for Fact Aggregation & Diff Engine."""

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from edcg.facts.facts import (
    FactsDiff,
    JournalOnlyStation,
    LandableStation,
    NonLandableSite,
    SourceAttribution,
    StatusChange,
    SystemFacts,
    _names_match,
    compute_facts_diff,
    gather_facts,
)
from edcg.facts.inara import InaraAPIError, InaraStation, InaraSystem
from edcg.facts.journal import JournalData, JournalStation, JournalVisit
from edcg.facts.raven import RavenAPIError, RavenSite, RavenSystem
from edcg.facts.spansh import SpanshStation, SpanshSystem

# ============================================================================
# Module-level fixtures
# ============================================================================

@pytest.fixture
def mock_config():
    """Create a mock config."""
    config = MagicMock()
    config.raven_api_url = "https://test.raven.api"
    config.inara_api_key = None
    config.spansh_enabled = False
    return config


@pytest.fixture
def mock_raven_client():
    """Create a mock RavenClient."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.fixture
def mock_inara_client():
    """Create a mock InaraClient."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.fixture
def mock_spansh_client():
    """Create a mock SpanshClient."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


def _spansh_system(name: str, bodies: list[dict]) -> SpanshSystem:
    """Build a SpanshSystem with just the fields these tests need."""
    return SpanshSystem(
        id64=123456,
        name=name,
        coordinates=[0.0, 0.0, 0.0],
        population=1000,
        government="Democracy",
        allegiance="Alliance",
        state="Boom",
        security="Medium",
        primary_economy="Industrial",
        secondary_economy="Refinery",
        controlling_minor_faction="Test Faction",
        stations=[],
        bodies=bodies,
        updated=datetime.now(UTC),
    )


# ============================================================================
# Data Structure Tests
# ============================================================================

class TestDataStructures:
    """Tests for fact data structures."""

    def test_system_facts_creation(self):
        """Test SystemFacts dataclass creation."""
        facts = SystemFacts(
            system_name="Test System",
            raven_system=RavenSystem(name="Test System", architect="Test", revision=1, bodies=[]),
            raven_sites=[],
            journal_data=JournalData(docked_stations=[], visited_systems=[], last_play_session=None),
            inara_system=None,
            spansh_system=None,
            landable_stations=[],
            non_landable_sites=[],
            journal_only_stations=[],
            conflicts=[],
        )
        assert facts.system_name == "Test System"
        assert facts.raven_system.revision == 1
        assert facts.landable_stations == []
        assert facts.non_landable_sites == []
        assert facts.journal_only_stations == []
        assert facts.conflicts == []

    def test_landable_station_creation(self):
        """Test LandableStation dataclass creation."""
        station = LandableStation(
            name="Test Station",
            build_type="outpost",
            facility_class="outpost",
            facility_name="Civilian Surface Outpost",
            body="Body 1",
            status="complete",
            source="raven",
            placement="surface",
            is_landable=True,
        )
        assert station.name == "Test Station"
        assert station.build_type == "outpost"
        assert station.facility_class == "outpost"
        assert station.is_landable is True

    def test_non_landable_site_creation(self):
        """Test NonLandableSite dataclass creation."""
        site = NonLandableSite(
            name="Test Hub",
            build_type="hub",
            facility_class="hub",
            facility_name="Civilian Hub",
            body="Body 1",
            status="plan",
            source="raven",
            placement="orbital",
            is_landable=False,
        )
        assert site.name == "Test Hub"
        assert site.build_type == "hub"
        assert site.is_landable is False

    def test_journal_only_station_creation(self):
        """Test JournalOnlyStation dataclass creation."""
        station = JournalOnlyStation(
            name="Journal Station",
            system="Test System",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            market_id=12345,
        )
        assert station.name == "Journal Station"
        assert station.system == "Test System"
        assert station.market_id == 12345

    def test_source_attribution_creation(self):
        """Test SourceAttribution dataclass creation."""
        attr = SourceAttribution(
            field="station_name",
            value="Test Station",
            sources=["raven", "journal"],
            conflict=False,
        )
        assert attr.field == "station_name"
        assert attr.value == "Test Station"
        assert attr.sources == ["raven", "journal"]
        assert attr.conflict is False

    def test_source_attribution_with_conflict(self):
        """Test SourceAttribution with conflict flag."""
        attr = SourceAttribution(
            field="system_name",
            value="Raven Name",
            sources=["raven"],
            conflict=True,
            details="Journal has 'Journal Name'",
        )
        assert attr.conflict is True
        assert attr.details == "Journal has 'Journal Name'"


# ============================================================================
# Gather Facts Tests
# ============================================================================

class TestGatherFacts:
    """Tests for gather_facts function."""

    @pytest.mark.asyncio
    async def test_gather_facts_basic_merge(self, mock_config, mock_raven_client):
        """Test basic fact gathering merges Raven and journal data."""
        # Setup Raven data - use actual build type names from catalogue
        raven_system = RavenSystem(
            name="Test System",
            architect="Test Architect",
            revision=42,
            bodies=["Body 1", "Body 2"],
        )
        raven_sites = [
            RavenSite(id=1, name="Alpha Station", status="complete", build_type="ananke", body_num=0),  # outpost class
            RavenSite(id=2, name="Beta Station", status="plan", build_type="aphrodite", body_num=1),  # starport class
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        # Mock journal parsing
        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            journal_station = JournalStation(
                name="Alpha Station",
                system="Test System",
                timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                market_id=12345,
            )
            journal_data = JournalData(
                docked_stations=[journal_station],
                visited_systems=[JournalVisit(system="Test System", timestamp=datetime.now(UTC))],
                last_play_session=datetime.now(UTC),
            )
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            # Inara/Spansh disabled
            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False

            # Call gather_facts with injected mock client
            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client)

            # Verify results
            assert facts.system_name == "Test System"
            assert facts.raven_system is not None
            assert facts.raven_system.revision == 42
            assert len(facts.raven_sites) == 2
            assert len(facts.landable_stations) == 2  # ananke (outpost) and aphrodite (starport) are landable
            assert len(facts.non_landable_sites) == 0
            assert len(facts.journal_only_stations) == 0  # Alpha Station is in Raven
            assert facts.raven_sites_loaded is True

    @pytest.mark.asyncio
    async def test_gather_facts_uses_the_journal_directory_override(
        self, tmp_path, monkeypatch, mock_config, mock_raven_client
    ):
        """EDCG_JOURNAL_DIR reaches parse_journal through gather_facts.

        find_journal_dir is deliberately *not* patched here: facts.py must pass
        os.environ to the probe and the override must win over the real machine,
        which is what makes a user-supplied journal folder visible at all.
        """
        journal_dir = tmp_path / "journal"
        journal_dir.mkdir()
        (journal_dir / "Journal.20240101.log").write_text(
            '{"timestamp": "2024-01-15T10:00:00Z", "event": "FSDJump", '
            '"StarSystem": "Test System", "StarPos": [0.0, 0.0, 0.0]}\n'
            '{"timestamp": "2024-01-15T10:30:00Z", "event": "Docked", '
            '"StationName": "Override Station", "StarSystem": "Test System", '
            '"MarketID": 128049152}\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("EDCG_JOURNAL_DIR", str(journal_dir))
        mock_raven_client.get_system.return_value = RavenSystem(
            name="Test System", architect="Test Architect", revision=1, bodies=[]
        )
        mock_raven_client.get_sites.return_value = []
        mock_config.inara_api_key = None
        mock_config.spansh_enabled = False

        facts = await gather_facts(
            "Test System", mock_config, raven_client=mock_raven_client
        )

        assert facts.journal_data is not None
        assert [s.name for s in facts.journal_data.docked_stations] == [
            "Override Station"
        ]
        assert facts.journal_data.docked_stations[0].market_id == 128049152
        assert facts.journal_data.last_play_session == datetime(
            2024, 1, 15, 10, 30, 0, tzinfo=UTC
        )
        # The dock is cross-referenced into the facts, not merely parsed.
        assert [s.name for s in facts.journal_only_stations] == [
            "Override Station"
        ]

    @pytest.mark.asyncio
    async def test_gather_facts_passes_os_environ_to_the_journal_probe(
        self, mock_config, mock_raven_client
    ):
        """facts.py must hand os.environ to find_journal_dir explicitly.

        Today the zero-argument call behaves identically (the probe defaults to
        os.environ), so only the call shape pins the wiring against regression;
        the end-to-end override test above covers the observable behaviour.
        """
        mock_raven_client.get_system.return_value = RavenSystem(
            name="Test System", architect="Test", revision=1, bodies=[]
        )
        mock_raven_client.get_sites.return_value = []
        mock_config.inara_api_key = None
        mock_config.spansh_enabled = False

        with patch("edcg.facts.facts.find_journal_dir", return_value=None) as probe:
            await gather_facts(
                "Test System", mock_config, raven_client=mock_raven_client
            )

        probe.assert_called_once_with(os.environ)

    @pytest.mark.asyncio
    async def test_gather_facts_maps_body_num_by_raven_body_id(self, mock_config, mock_raven_client):
        """A site's bodyNum is a body id, so the body must be a string name, not a dict or index."""
        raven_system = RavenSystem(
            name="Test System",
            architect="Test Architect",
            revision=61,
            bodies=["Test System", "Test System 1", "Test System 3 a", "Test System 5 c"],
            body_nums={
                0: "Test System",
                13: "Test System 1",
                16: "Test System 3 a",
                36: "Test System 5 c",
            },
        )
        raven_sites = [
            RavenSite(id=1, name="Alpha Station", status="complete", build_type="ananke", body_num=16),
            RavenSite(id=2, name="Beta Station", status="complete", build_type="ananke", body_num=36),
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        with patch("edcg.facts.facts.find_journal_dir", return_value=None):
            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False

            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client)

        by_name = {st.name: st for st in facts.landable_stations}
        assert isinstance(by_name["Alpha Station"].body, str)
        assert by_name["Alpha Station"].body == "Test System 3 a"
        assert by_name["Beta Station"].body == "Test System 5 c"

    @pytest.mark.asyncio
    async def test_gather_facts_placement_follows_build_type(self, mock_config, mock_raven_client):
        """Placement comes from the build type, not the facility class.

        'prometheus' is a Scientific Outpost: class 'outpost' but orbital.
        """
        raven_system = RavenSystem(
            name="Test System",
            architect="Test",
            revision=61,
            bodies=["Body 1", "Body 2", "Body 3"],
        )
        raven_sites = [
            RavenSite(id=1, name="Scientific Outpost", status="complete", build_type="prometheus", body_num=0),
            RavenSite(id=2, name="Surface Science", status="complete", build_type="ananke", body_num=1),
            RavenSite(id=3, name="Planetary Port", status="complete", build_type="aphrodite", body_num=2),
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        with patch("edcg.facts.facts.find_journal_dir", return_value=None):
            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False
            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client)

        by_name = {st.name: st for st in facts.landable_stations}
        assert by_name["Scientific Outpost"].placement == "orbital"
        assert by_name["Scientific Outpost"].facility_class == "outpost"
        assert by_name["Surface Science"].placement == "surface"
        assert by_name["Planetary Port"].placement == "surface"

    @pytest.mark.asyncio
    async def test_gather_facts_placement_ignores_station_names(self, mock_config, mock_raven_client):
        """Placement must come from the build type, never from a name string."""
        raven_system = RavenSystem(
            name="Test System",
            architect="Test",
            revision=61,
            bodies=["Body 1"],
        )
        raven_sites = [
            # Name screams surface/orbital, build types say the opposite.
            RavenSite(id=1, name="Surface Station Orbital Hub", status="complete", build_type="prometheus", body_num=0),
            RavenSite(id=2, name="Orbital Installation Ground", status="complete", build_type="ananke", body_num=0),
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        with patch("edcg.facts.facts.find_journal_dir", return_value=None):
            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False
            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client)

        by_name = {st.name: st for st in facts.landable_stations}
        assert by_name["Surface Station Orbital Hub"].placement == "orbital"
        assert by_name["Orbital Installation Ground"].placement == "surface"

    @pytest.mark.asyncio
    async def test_gather_facts_collects_station_body_flavour(self, mock_config, mock_raven_client, mock_spansh_client):
        """Only bodies with stations are included, with Spansh values mapped."""
        raven_system = RavenSystem(
            name="Test System",
            architect="Test",
            revision=61,
            bodies=["Test System 1", "Test System 2"],
            body_nums={13: "Test System 1", 16: "Test System 2"},
        )
        raven_sites = [
            RavenSite(id=1, name="Orbital Outpost", status="complete", build_type="prometheus", body_num=13),
            RavenSite(id=2, name="Surface Lab", status="complete", build_type="ananke", body_num=16),
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        mock_spansh_client.get_system.return_value = _spansh_system("Test System", bodies=[
            {
                "name": "Test System 1",
                "subType": "Icy body",
                "atmosphereType": "Thick Methane-rich",
                "surfaceTemperature": 394.668976,
                "surfacePressure": 3420.39180853689,
                "gravity": 0.736962373814622,
                "radius": 8331.1455,
                "volcanismType": "Water Geysers",
                "orbitalPeriod": 762.053765356539,
                "isLandable": False,
                "terraformingState": "Not terraformable",
            },
            {"name": "Test System 2", "subType": "Rocky Ice world"},
            {"name": "Test System 9", "subType": "Gas giant"},  # no station on it
        ])

        with patch("edcg.facts.facts.find_journal_dir", return_value=None):
            mock_config.inara_api_key = None
            mock_config.spansh_enabled = True
            facts = await gather_facts(
                "Test System", mock_config,
                raven_client=mock_raven_client, spansh_client=mock_spansh_client,
            )

        assert [b.name for b in facts.station_bodies] == ["Test System 1", "Test System 2"]

        first = facts.station_bodies[0]
        assert first.sub_type == "Icy body"
        assert first.atmosphere == "Thick Methane-rich"
        assert first.temperature_k == pytest.approx(394.668976)
        assert first.pressure_atm == pytest.approx(3420.39180853689)
        assert first.gravity_g == pytest.approx(0.736962373814622)
        assert first.radius_km == pytest.approx(8331.1455)
        assert first.volcanism == "Water Geysers"
        assert first.orbital_period_days == pytest.approx(762.053765356539)
        assert first.landable is False
        assert first.terraforming_state == "Not terraformable"

        # Fields Spansh did not supply stay empty rather than becoming blanks.
        second = facts.station_bodies[1]
        assert second.sub_type == "Rocky Ice world"
        assert second.atmosphere is None
        assert second.temperature_k is None

    @pytest.mark.asyncio
    async def test_gather_facts_station_bodies_without_spansh(self, mock_config, mock_raven_client):
        """Spansh disabled still names station bodies, without flavour."""
        raven_system = RavenSystem(
            name="Test System",
            architect="Test",
            revision=61,
            bodies=["Body 1"],
            body_nums={5: "Body 1"},
        )
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = [
            RavenSite(id=1, name="Station", status="complete", build_type="ananke", body_num=5),
        ]

        with patch("edcg.facts.facts.find_journal_dir", return_value=None):
            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False
            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client)

        assert [b.name for b in facts.station_bodies] == ["Body 1"]
        assert facts.station_bodies[0].sub_type is None

    @pytest.mark.asyncio
    async def test_gather_facts_landable_computation(self, mock_config, mock_raven_client):
        """Test landable stations are correctly computed from build types."""
        raven_system = RavenSystem(
            name="Test System",
            architect="Test",
            revision=1,
            bodies=["Body 1", "Body 2", "Body 3"],
        )
        raven_sites = [
            RavenSite(id=1, name="Starport Site", status="complete", build_type="aphrodite", body_num=0),  # starport - landable
            RavenSite(id=2, name="Outpost Site", status="complete", build_type="ananke", body_num=1),  # outpost - landable
            RavenSite(id=3, name="Settlement Site", status="complete", build_type="aerecura", body_num=2),  # settlement - landable
            RavenSite(id=4, name="Hub Site", status="plan", build_type="aegle", body_num=0),  # hub - NOT landable
            RavenSite(id=5, name="Installation Site", status="plan", build_type="alastor", body_num=1),  # installation - NOT landable
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            journal_data = JournalData(docked_stations=[], visited_systems=[], last_play_session=None)
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False

            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client)

            # 3 landable (starport, outpost, settlement)
            assert len(facts.landable_stations) == 3
            landable_names = {s.name for s in facts.landable_stations}
            assert "Starport Site" in landable_names
            assert "Outpost Site" in landable_names
            assert "Settlement Site" in landable_names

            # 2 non-landable (hub, installation)
            assert len(facts.non_landable_sites) == 2
            non_landable_names = {s.name for s in facts.non_landable_sites}
            assert "Hub Site" in non_landable_names
            assert "Installation Site" in non_landable_names

    @pytest.mark.asyncio
    async def test_gather_facts_journal_only_stations(self, mock_config, mock_raven_client):
        """Test journal-only stations (docked but not in Raven) are detected."""
        raven_system = RavenSystem(
            name="Test System",
            architect="Test",
            revision=1,
            bodies=["Body 1"],
        )
        raven_sites = [
            RavenSite(id=1, name="Raven Station", status="complete", build_type="ananke", body_num=0),  # outpost
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            # Journal has a station not in Raven
            journal_station1 = JournalStation(
                name="Raven Station",
                system="Test System",
                timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                market_id=11111,
            )
            journal_station2 = JournalStation(
                name="Journal Only Station",
                system="Test System",
                timestamp=datetime(2024, 1, 15, 11, 30, 0, tzinfo=UTC),
                market_id=22222,
            )
            journal_data = JournalData(
                docked_stations=[journal_station1, journal_station2],
                visited_systems=[],
                last_play_session=datetime.now(UTC),
            )
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False

            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client)

            assert len(facts.landable_stations) == 1
            assert len(facts.journal_only_stations) == 1
            assert facts.journal_only_stations[0].name == "Journal Only Station"

    @pytest.mark.asyncio
    async def test_gather_facts_collapses_repeated_journal_docks(self, mock_config, mock_raven_client):
        """Repeated dock events collapse to the latest per station."""
        raven_system = RavenSystem(
            name="Test System",
            architect="Test",
            revision=1,
            bodies=["Body 1"],
        )
        raven_sites = [
            RavenSite(id=1, name="Raven Station", status="complete", build_type="ananke", body_num=0),
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            raven_t1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
            raven_t2 = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
            journal_t1 = datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC)
            journal_t2 = datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC)
            journal_data = JournalData(
                docked_stations=[
                    JournalStation(name="Raven Station", system="Test System", timestamp=raven_t1, market_id=111),
                    JournalStation(name="Raven Station", system="Test System", timestamp=raven_t2, market_id=222),
                    JournalStation(name="Journal Only Station", system="Test System", timestamp=journal_t1, market_id=333),
                    JournalStation(name="Journal Only Station", system="Test System", timestamp=journal_t2, market_id=444),
                ],
                visited_systems=[],
                last_play_session=datetime.now(UTC),
            )
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False

            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client)

            assert len(facts.journal_only_stations) == 1
            journal_only = facts.journal_only_stations[0]
            assert journal_only.name == "Journal Only Station"
            assert journal_only.timestamp == journal_t2
            assert journal_only.market_id == 444

            [landable] = facts.landable_stations
            assert landable.last_docked == raven_t2
            assert landable.market_id == 222

    @pytest.mark.asyncio
    async def test_gather_facts_conflict_detection_name_mismatch(self, mock_config, mock_raven_client):
        """Station names differing only inside parentheses are different stations."""
        raven_system = RavenSystem(
            name="Test System",
            architect="Test",
            revision=1,
            bodies=["Body 1"],
        )
        raven_sites = [
            RavenSite(id=1, name="Station (OldSuffix)", status="complete", build_type="ananke", body_num=0),
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            journal_station = JournalStation(
                name="Station (NewSuffix)",
                system="Test System",
                timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                market_id=12345,
            )
            journal_data = JournalData(
                docked_stations=[journal_station],
                visited_systems=[],
                last_play_session=datetime.now(UTC),
            )
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False

            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client)

            # The journal station is not merged into the differently named Raven site.
            assert [s.name for s in facts.journal_only_stations] == ["Station (NewSuffix)"]
            # Exact-name matching means there is no rename conflict to report.
            assert [c for c in facts.conflicts if c.field == "station_name"] == []

    @pytest.mark.asyncio
    async def test_gather_facts_rename_history_does_not_flag_conflict(
        self, mock_config, mock_raven_client
    ):
        """Repeated docks under the same station name collapse to the latest event.

        Conflict detection must compare the collapsed latest-per-station
        names, not the raw dock history.
        """
        raven_system = RavenSystem(
            name="Test System",
            architect="Test",
            revision=1,
            bodies=["Body 1"],
        )
        raven_sites = [
            RavenSite(
                id=1,
                name="Cold Probabilities (ii-42)",
                status="complete",
                build_type="ananke",
                body_num=0,
            ),
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            old_t = datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC)
            new_t = datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC)
            journal_data = JournalData(
                docked_stations=[
                    JournalStation(
                        name="Cold Probabilities (ii-42)",
                        system="Test System",
                        timestamp=old_t,
                        market_id=111,
                    ),
                    JournalStation(
                        name="Cold Probabilities (ii-42)",
                        system="Test System",
                        timestamp=new_t,
                        market_id=222,
                    ),
                ],
                visited_systems=[],
                last_play_session=datetime.now(UTC),
            )
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False

            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client)

            # The station matched Raven by its exact name: no journal-only entry.
            assert facts.journal_only_stations == []
            # Only the latest dock is retained.
            [landable] = facts.landable_stations
            assert landable.last_docked == new_t
            assert landable.market_id == 222
            # No false-positive station_name conflict.
            name_conflicts = [c for c in facts.conflicts if c.field == "station_name"]
            assert name_conflicts == []

    @pytest.mark.asyncio
    async def test_gather_facts_inara_integration(self, mock_config, mock_raven_client, mock_inara_client):
        """Test Inara data is integrated when API key is present."""
        raven_system = RavenSystem(
            name="Test System",
            architect="Test",
            revision=1,
            bodies=["Body 1"],
        )
        raven_sites = [
            RavenSite(id=1, name="Test Station", status="complete", build_type="outpost", body_num=0),
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            journal_data = JournalData(docked_stations=[], visited_systems=[], last_play_session=None)
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            # Enable Inara
            mock_config.inara_api_key = "test-key"
            inara_system = InaraSystem(
                name="Test System",
                coordinates=[0.0, 0.0, 0.0],
                population=1000,
                government="Democracy",
                allegiance="Alliance",
                state="Boom",
                security="Medium",
                primary_economy="Industrial",
                updated=datetime.now(UTC),
            )
            mock_inara_client.search_system.return_value = inara_system
            inara_station = InaraStation(
                name="Test Station",
                type="Outpost",
                services=["Market"],
                economy="Industrial",
                updated=datetime.now(UTC),
            )
            mock_inara_client.get_station.return_value = inara_station

            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client, inara_client=mock_inara_client)

            assert facts.inara_system is not None
            assert facts.inara_stations == [inara_station]
            mock_inara_client.search_system.assert_called_once()
            mock_inara_client.get_station.assert_awaited_once_with("Test System", "Test Station")

    @pytest.mark.asyncio
    async def test_gather_facts_inara_station_failure_does_not_lose_others(
        self, mock_config, mock_raven_client, mock_inara_client
    ):
        """One failing Inara station lookup must not discard the other stations."""
        raven_system = RavenSystem(
            name="Test System",
            architect="Test",
            revision=1,
            bodies=["Body 1"],
        )
        raven_sites = [
            RavenSite(id=1, name="Bad Station", status="complete", build_type="ananke", body_num=0),
            RavenSite(id=2, name="Good Station", status="complete", build_type="ananke", body_num=0),
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            journal_data = JournalData(docked_stations=[], visited_systems=[], last_play_session=None)
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            mock_config.inara_api_key = "test-key"
            mock_config.spansh_enabled = False
            mock_inara_client.search_system.return_value = InaraSystem(
                name="Test System",
                coordinates=[0.0, 0.0, 0.0],
                population=1000,
                government="Democracy",
                allegiance="Alliance",
                state="Boom",
                security="Medium",
                primary_economy="Industrial",
                updated=datetime.now(UTC),
            )

            async def fake_get_station(system: str, station: str):
                if station == "Bad Station":
                    raise InaraAPIError("station lookup failed")
                return InaraStation(
                    name=station,
                    type="Outpost",
                    services=["Market"],
                    economy="Industrial",
                    updated=datetime.now(UTC),
                )

            mock_inara_client.get_station.side_effect = fake_get_station

            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client, inara_client=mock_inara_client)

            assert [station.name for station in facts.inara_stations] == ["Good Station"]
            assert mock_inara_client.get_station.await_count == 2

    @pytest.mark.asyncio
    async def test_gather_facts_inara_candidates_include_journal_and_spansh(
        self, mock_config, mock_raven_client, mock_inara_client, mock_spansh_client
    ):
        """Inara station lookups draw candidate names from Raven, journal and Spansh."""
        raven_system = RavenSystem(
            name="Test System",
            architect="Test",
            revision=1,
            bodies=["Body 1"],
        )
        raven_sites = [
            RavenSite(id=1, name="Raven Station", status="complete", build_type="ananke", body_num=0),
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            journal_data = JournalData(
                docked_stations=[
                    JournalStation(
                        name="Journal Station",
                        system="Test System",
                        timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
                        market_id=111,
                    )
                ],
                visited_systems=[],
                last_play_session=None,
            )
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            mock_config.inara_api_key = "test-key"
            mock_config.spansh_enabled = True
            mock_inara_client.search_system.return_value = InaraSystem(
                name="Test System",
                coordinates=[0.0, 0.0, 0.0],
                population=1000,
                government="Democracy",
                allegiance="Alliance",
                state="Boom",
                security="Medium",
                primary_economy="Industrial",
                updated=datetime.now(UTC),
            )
            spansh_station = SpanshStation(
                market_id=222,
                name="Spansh Station",
                type="Outpost",
                controlling_minor_faction="Test Faction",
                controlling_minor_faction_state="Boom",
                distance_to_arrival=100.0,
                has_large_pad=False,
                has_market=True,
                large_pads=0,
                medium_pads=1,
                small_pads=0,
                services=["Market"],
            )
            mock_spansh_client.get_system.return_value = SpanshSystem(
                id64=123456,
                name="Test System",
                coordinates=[0.0, 0.0, 0.0],
                population=1000,
                government="Democracy",
                allegiance="Alliance",
                state="Boom",
                security="Medium",
                primary_economy="Industrial",
                secondary_economy="Refinery",
                controlling_minor_faction="Test Faction",
                stations=[spansh_station],
                bodies=[],
                updated=datetime.now(UTC),
            )

            async def fake_get_station(system: str, station: str):
                return InaraStation(
                    name=station,
                    type="Outpost",
                    services=["Market"],
                    economy="Industrial",
                    updated=datetime.now(UTC),
                )

            mock_inara_client.get_station.side_effect = fake_get_station

            facts = await gather_facts(
                "Test System",
                mock_config,
                raven_client=mock_raven_client,
                inara_client=mock_inara_client,
                spansh_client=mock_spansh_client,
            )

            looked_up = {call.args[1] for call in mock_inara_client.get_station.await_args_list}
            assert looked_up == {"Raven Station", "Journal Station", "Spansh Station"}
            assert {station.name for station in facts.inara_stations} == {
                "Raven Station",
                "Journal Station",
                "Spansh Station",
            }

    @pytest.mark.asyncio
    async def test_gather_facts_spansh_integration(self, mock_config, mock_raven_client, mock_spansh_client):
        """Test Spansh data is integrated when enabled."""
        raven_system = RavenSystem(
            name="Test System",
            architect="Test",
            revision=1,
            bodies=["Body 1"],
        )
        raven_sites = [
            RavenSite(id=1, name="Test Station", status="complete", build_type="outpost", body_num=0),
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            journal_data = JournalData(docked_stations=[], visited_systems=[], last_play_session=None)
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            # Enable Spansh
            mock_config.spansh_enabled = True
            mock_config.inara_api_key = None
            spansh_station = SpanshStation(
                market_id=12345,
                name="Test Station",
                type="Outpost",
                controlling_minor_faction="Test Faction",
                controlling_minor_faction_state="Boom",
                distance_to_arrival=100.0,
                has_large_pad=False,
                has_market=True,
                large_pads=0,
                medium_pads=2,
                small_pads=4,
                services=["Market", "Refuel"],
            )
            spansh_system = SpanshSystem(
                id64=123456,
                name="Test System",
                coordinates=[0.0, 0.0, 0.0],
                population=1000,
                government="Democracy",
                allegiance="Alliance",
                state="Boom",
                security="Medium",
                primary_economy="Industrial",
                secondary_economy="Refinery",
                controlling_minor_faction="Test Faction",
                stations=[spansh_station],
                bodies=[],
                updated=datetime.now(UTC),
            )
            mock_spansh_client.get_system.return_value = spansh_system

            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client, spansh_client=mock_spansh_client)

            assert facts.spansh_system is not None
            mock_spansh_client.get_system.assert_called_once()

    @pytest.mark.asyncio
    async def test_gather_facts_placeholder_filtering(self, mock_config, mock_raven_client):
        """Test that placeholder/unresolved Raven sites are filtered out."""
        raven_system = RavenSystem(
            name="Test System",
            architect="Test",
            revision=1,
            bodies=["Body 1"],
        )
        raven_sites = [
            RavenSite(id=1, name="Real Station", status="complete", build_type="ananke", body_num=0),  # outpost
            RavenSite(id=2, name="Xray Hotel", status="plan", build_type="ananke", body_num=1),  # NATO placeholder
            RavenSite(id=3, name="[Unknown]", status="plan", build_type="outpost?", body_num=-1),  # Unresolved
            RavenSite(id=4, name="Zulu Yankee", status="plan", build_type="aphrodite", body_num=1),  # NATO placeholder
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            journal_data = JournalData(docked_stations=[], visited_systems=[], last_play_session=None)
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False

            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client)

            # Only "Real Station" should be in landable_stations
            assert len(facts.landable_stations) == 1
            assert facts.landable_stations[0].name == "Real Station"

    @pytest.mark.asyncio
    async def test_gather_facts_excludes_null_name_sites(self, mock_config, mock_raven_client):
        """Sites with a null Raven name never reach station matching or the results."""
        raven_system = RavenSystem(
            name="Test System",
            architect="Test",
            revision=1,
            bodies=["Body 1"],
        )
        raven_sites = [
            # Landable and non-landable build types, both with a null name.
            RavenSite(id=1, name=None, status="complete", build_type="ananke", body_num=0),
            RavenSite(id=2, name=None, status="plan", build_type="aegle", body_num=0),
            RavenSite(id=3, name="Real Station", status="complete", build_type="ananke", body_num=0),
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            # A journal station exercises the name-matching path that used to
            # receive the null name and raise TypeError.
            journal_station = JournalStation(
                name="Journal Station",
                system="Test System",
                timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                market_id=22222,
            )
            journal_data = JournalData(
                docked_stations=[journal_station],
                visited_systems=[],
                last_play_session=datetime.now(UTC),
            )
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False

            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client)

            assert [station.name for station in facts.landable_stations] == ["Real Station"]
            assert facts.non_landable_sites == []
            assert all(station.name is not None for station in facts.landable_stations)
            assert all(station.name is not None for station in facts.non_landable_sites)
            assert [station.name for station in facts.journal_only_stations] == ["Journal Station"]

    @pytest.mark.asyncio
    async def test_gather_facts_source_attribution(self, mock_config, mock_raven_client):
        """Test source attribution is tracked per field."""
        raven_system = RavenSystem(
            name="Test System",
            architect="Test Architect",
            revision=42,
            bodies=["Body 1"],
        )
        raven_sites = [
            RavenSite(id=1, name="Test Station", status="complete", build_type="ananke", body_num=0),
        ]
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = raven_sites

        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            journal_station = JournalStation(
                name="Test Station",
                system="Test System",
                timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                market_id=12345,
            )
            journal_data = JournalData(
                docked_stations=[journal_station],
                visited_systems=[],
                last_play_session=datetime.now(UTC),
            )
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False

            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client)

            # Check that landable station has source attribution
            assert len(facts.landable_stations) == 1
            station = facts.landable_stations[0]
            assert station.source == "raven"  # Primary source
            assert station.market_id == 12345  # Updated from journal
            assert station.last_docked is not None


# ============================================================================
# Compute Facts Diff Tests
# ============================================================================

class TestComputeFactsDiff:
    """Tests for compute_facts_diff function."""

    def create_existing_dossier(self, system_name="Test System", revision=40):
        """Create a mock existing dossier data."""
        return {
            "system_name": system_name,
            "raven_revision": revision,
            "architect": "Test Architect",
            "stations": [
                {"name": "Old Station", "build_type": "ananke", "status": "complete", "body": "Body 1"},  # outpost
            ],
            "non_landable_sites": [
                {"name": "Old Hub", "build_type": "aegle", "status": "plan", "body": "Body 2"},  # hub
            ],
        }

    def create_new_facts(self, system_name="Test System", revision=45):
        """Create new SystemFacts for comparison."""
        return SystemFacts(
            system_name=system_name,
            raven_system=RavenSystem(name=system_name, architect="Test Architect", revision=revision, bodies=["Body 1", "Body 2"]),
            raven_sites=[
                RavenSite(id=1, name="Old Station", status="complete", build_type="ananke", body_num=0),
                RavenSite(id=2, name="New Station", status="build", build_type="aphrodite", body_num=1),
            ],
            journal_data=JournalData(docked_stations=[], visited_systems=[], last_play_session=None),
            inara_system=None,
            spansh_system=None,
            landable_stations=[
                LandableStation(name="Old Station", build_type="ananke", facility_class="outpost", facility_name="Scientific Surface Outpost", body="Body 1", status="complete", source="raven", placement="surface", is_landable=True),
                LandableStation(name="New Station", build_type="aphrodite", facility_class="starport", facility_name="Large Planetary Port", body="Body 2", status="build", source="raven", placement="surface", is_landable=True),
            ],
            non_landable_sites=[
                NonLandableSite(name="Old Hub", build_type="aegle", facility_class="hub", facility_name="Civilian Hub", body="Body 2", status="plan", source="raven", placement="orbital", is_landable=False),
                NonLandableSite(name="New Installation", build_type="alastor", facility_class="installation", facility_name="Military Installation", body="Body 1", status="plan", source="raven", placement="orbital", is_landable=False),
            ],
            journal_only_stations=[],
            conflicts=[],
        )

    def test_compute_facts_diff_new_landable_station(self):
        """Test diff detects new landable station."""
        existing = self.create_existing_dossier()
        new_facts = self.create_new_facts()

        diff = compute_facts_diff(existing, new_facts)

        assert len(diff.new_landable_stations) == 1
        assert diff.new_landable_stations[0].name == "New Station"
        assert diff.new_landable_stations[0].status == "build"

    def test_compute_facts_diff_lost_landable_station(self):
        """Test diff detects lost landable station."""
        existing = {
            "system_name": "Test System",
            "raven_revision": 40,
            "architect": "Test Architect",
            "stations": [
                {"name": "Old Station", "build_type": "ananke", "status": "complete", "body": "Body 1"},
                {"name": "Lost Station", "build_type": "ananke", "status": "complete", "body": "Body 3"},  # Different body
            ],
            "non_landable_sites": [],
        }
        new_facts = self.create_new_facts()  # Only has Old Station, New Station (on Body 2)

        diff = compute_facts_diff(existing, new_facts)

        assert len(diff.lost_landable_stations) == 1
        assert diff.lost_landable_stations[0].name == "Lost Station"

    def test_compute_facts_diff_renamed_station(self):
        """Test diff detects renamed station (same ID/build_type, different name)."""
        existing = self.create_existing_dossier()
        new_facts = SystemFacts(
            system_name="Test System",
            raven_system=RavenSystem(name="Test System", architect="Test Architect", revision=45, bodies=["Body 1"]),
            raven_sites=[
                RavenSite(id=1, name="Renamed Station", status="complete", build_type="ananke", body_num=0),  # Same ID, different name
            ],
            journal_data=JournalData(docked_stations=[], visited_systems=[], last_play_session=None),
            inara_system=None,
            spansh_system=None,
            landable_stations=[
                LandableStation(name="Renamed Station", build_type="ananke", facility_class="outpost", facility_name="Scientific Surface Outpost", body="Body 1", status="complete", source="raven", placement="surface", is_landable=True),
            ],
            non_landable_sites=[],
            journal_only_stations=[],
            conflicts=[],
        )

        diff = compute_facts_diff(existing, new_facts)

        assert len(diff.renamed_stations) == 1
        assert diff.renamed_stations[0].old_name == "Old Station"
        assert diff.renamed_stations[0].new_name == "Renamed Station"

    def test_compute_facts_diff_build_type_change(self):
        """Test diff detects build type change."""
        existing = self.create_existing_dossier()
        new_facts = SystemFacts(
            system_name="Test System",
            raven_system=RavenSystem(name="Test System", architect="Test Architect", revision=45, bodies=["Body 1"]),
            raven_sites=[
                RavenSite(id=1, name="Old Station", status="complete", build_type="aphrodite", body_num=0),  # Changed from ananke
            ],
            journal_data=JournalData(docked_stations=[], visited_systems=[], last_play_session=None),
            inara_system=None,
            spansh_system=None,
            landable_stations=[
                LandableStation(name="Old Station", build_type="aphrodite", facility_class="starport", facility_name="Large Planetary Port", body="Body 1", status="complete", source="raven", placement="surface", is_landable=True),
            ],
            non_landable_sites=[],
            journal_only_stations=[],
            conflicts=[],
        )

        diff = compute_facts_diff(existing, new_facts)

        assert len(diff.build_type_changes) == 1
        assert diff.build_type_changes[0].name == "Old Station"
        assert diff.build_type_changes[0].old_build_type == "ananke"
        assert diff.build_type_changes[0].new_build_type == "aphrodite"

    def test_compute_facts_diff_status_change(self):
        """Test diff detects status change (plan -> build -> complete)."""
        existing = {
            "system_name": "Test System",
            "raven_revision": 40,
            "architect": "Test Architect",
            "stations": [
                {"name": "Progressing Station", "build_type": "ananke", "status": "plan", "body": "Body 1"},
            ],
            "non_landable_sites": [],
        }
        new_facts = SystemFacts(
            system_name="Test System",
            raven_system=RavenSystem(name="Test System", architect="Test Architect", revision=45, bodies=["Body 1"]),
            raven_sites=[
                RavenSite(id=1, name="Progressing Station", status="build", build_type="ananke", body_num=0),
            ],
            journal_data=JournalData(docked_stations=[], visited_systems=[], last_play_session=None),
            inara_system=None,
            spansh_system=None,
            landable_stations=[
                LandableStation(name="Progressing Station", build_type="ananke", facility_class="outpost", facility_name="Scientific Surface Outpost", body="Body 1", status="build", source="raven", placement="surface", is_landable=True),
            ],
            non_landable_sites=[],
            journal_only_stations=[],
            conflicts=[],
        )

        diff = compute_facts_diff(existing, new_facts)

        assert len(diff.status_changes) == 1
        assert diff.status_changes[0].name == "Progressing Station"
        assert diff.status_changes[0].old_status == "plan"
        assert diff.status_changes[0].new_status == "build"

    def test_compute_facts_diff_new_non_landable_site(self):
        """Test diff detects new non-landable site."""
        existing = self.create_existing_dossier()
        new_facts = self.create_new_facts()

        diff = compute_facts_diff(existing, new_facts)

        assert len(diff.new_non_landable_sites) == 1
        assert diff.new_non_landable_sites[0].name == "New Installation"
        assert diff.new_non_landable_sites[0].build_type == "alastor"

    def test_compute_facts_diff_lost_non_landable_site(self):
        """Test diff detects lost non-landable site."""
        existing = {
            "system_name": "Test System",
            "raven_revision": 40,
            "architect": "Test Architect",
            "stations": [],
            "non_landable_sites": [
                {"name": "Old Hub", "build_type": "hub", "status": "plan", "body": "Body 2"},
                {"name": "Lost Hub", "build_type": "hub", "status": "plan", "body": "Body 1"},
            ],
        }
        new_facts = SystemFacts(
            system_name="Test System",
            raven_system=RavenSystem(name="Test System", architect="Test Architect", revision=45, bodies=["Body 1", "Body 2"]),
            raven_sites=[
                RavenSite(id=1, name="Old Hub", status="plan", build_type="hub", body_num=1),
            ],
            journal_data=JournalData(docked_stations=[], visited_systems=[], last_play_session=None),
            inara_system=None,
            spansh_system=None,
            landable_stations=[],
            non_landable_sites=[
                NonLandableSite(name="Old Hub", build_type="hub", facility_class="hub", facility_name="Civilian Hub", body="Body 2", status="plan", source="raven", placement="orbital", is_landable=False),
            ],
            journal_only_stations=[],
            conflicts=[],
        )

        diff = compute_facts_diff(existing, new_facts)

        assert len(diff.lost_non_landable_sites) == 1
        assert diff.lost_non_landable_sites[0].name == "Lost Hub"

    def test_compute_facts_diff_raven_revision_delta(self):
        """Test diff reports Raven revision delta."""
        existing = self.create_existing_dossier(revision=40)
        new_facts = self.create_new_facts(revision=45)

        diff = compute_facts_diff(existing, new_facts)

        assert diff.raven_revision_delta == 5
        assert diff.old_revision == 40
        assert diff.new_revision == 45

    def test_compute_facts_diff_journal_only_stations(self):
        """Test diff reports journal-only stations."""
        existing = self.create_existing_dossier()
        new_facts = SystemFacts(
            system_name="Test System",
            raven_system=RavenSystem(name="Test System", architect="Test Architect", revision=45, bodies=["Body 1"]),
            raven_sites=[
                RavenSite(id=1, name="Old Station", status="complete", build_type="outpost", body_num=0),
            ],
            journal_data=JournalData(
                docked_stations=[
                    JournalStation(name="Old Station", system="Test System", timestamp=datetime.now(UTC)),
                    JournalStation(name="Journal Only", system="Test System", timestamp=datetime.now(UTC)),
                ],
                visited_systems=[],
                last_play_session=None,
            ),
            inara_system=None,
            spansh_system=None,
            landable_stations=[
                LandableStation(name="Old Station", build_type="outpost", facility_class="outpost", facility_name="Civilian Surface Outpost", body="Body 1", status="complete", source="raven", placement="surface", is_landable=True),
            ],
            non_landable_sites=[],
            journal_only_stations=[
                JournalOnlyStation(name="Journal Only", system="Test System", timestamp=datetime.now(UTC), market_id=12345),
            ],
            conflicts=[],
        )

        diff = compute_facts_diff(existing, new_facts)

        assert len(diff.journal_only_stations) == 1
        assert diff.journal_only_stations[0].name == "Journal Only"


# ============================================================================
# FactsDiff Formatting Tests
# ============================================================================

class TestFactsDiffFormatting:
    """Tests for FactsDiff formatting methods."""

    def create_sample_diff(self):
        """Create a sample FactsDiff for formatting tests."""
        diff = FactsDiff(
            system_name="Test System",
            old_revision=40,
            new_revision=45,
            raven_revision_delta=5,
            new_landable_stations=[
                LandableStation(name="New Station", build_type="starport", facility_class="starport", facility_name="Large Planetary Port", body="Body 2", status="build", source="raven", placement="surface", is_landable=True),
            ],
            lost_landable_stations=[],
            renamed_stations=[],
            build_type_changes=[],
            status_changes=[
                StatusChange(name="Progressing Station", old_status="plan", new_status="build"),
            ],
            new_non_landable_sites=[
                NonLandableSite(name="New Hub", build_type="hub", facility_class="hub", facility_name="Civilian Hub", body="Body 1", status="plan", source="raven", placement="orbital", is_landable=False),
            ],
            lost_non_landable_sites=[],
            journal_only_stations=[
                JournalOnlyStation(name="Journal Station", system="Test System", timestamp=datetime.now(UTC), market_id=12345),
            ],
            inara_discrepancies=[],
            spansh_discrepancies=[],
            conflicts=[],
        )
        return diff

    def test_format_for_llm_basic(self):
        """Test format_for_llm produces structured output."""
        diff = self.create_sample_diff()
        llm_format = diff.format_for_llm()

        assert isinstance(llm_format, str)
        assert "Test System" in llm_format
        assert "Raven revision: 40 -> 45 (+5)" in llm_format
        assert "New landable stations (1):" in llm_format
        assert "New Station" in llm_format
        assert "starport" in llm_format
        assert "Status changes (1):" in llm_format
        assert "Progressing Station" in llm_format
        assert "plan -> build" in llm_format
        assert "New non-landable sites (1):" in llm_format
        assert "New Hub" in llm_format
        assert "Journal-only stations (1):" in llm_format
        assert "Journal Station" in llm_format

    def test_present_changes_basic(self):
        """Test present_changes produces human-readable summary."""
        diff = self.create_sample_diff()
        summary = diff.present_changes()

        assert isinstance(summary, str)
        assert "Test System" in summary
        assert "Raven revision 40 → 45 (+5)" in summary
        assert "New Station" in summary
        assert "Progressing Station" in summary
        assert "New Hub" in summary
        assert "Journal Station" in summary

    def test_format_for_llm_no_changes(self):
        """Test format_for_llm when no changes."""
        diff = FactsDiff(
            system_name="Test System",
            old_revision=40,
            new_revision=40,
            raven_revision_delta=0,
            new_landable_stations=[],
            lost_landable_stations=[],
            renamed_stations=[],
            build_type_changes=[],
            status_changes=[],
            new_non_landable_sites=[],
            lost_non_landable_sites=[],
            journal_only_stations=[],
            inara_discrepancies=[],
            spansh_discrepancies=[],
            conflicts=[],
        )

        llm_format = diff.format_for_llm()
        assert "No changes detected" in llm_format

    def test_present_changes_no_changes(self):
        """Test present_changes when no changes."""
        diff = FactsDiff(
            system_name="Test System",
            old_revision=40,
            new_revision=40,
            raven_revision_delta=0,
            new_landable_stations=[],
            lost_landable_stations=[],
            renamed_stations=[],
            build_type_changes=[],
            status_changes=[],
            new_non_landable_sites=[],
            lost_non_landable_sites=[],
            journal_only_stations=[],
            inara_discrepancies=[],
            spansh_discrepancies=[],
            conflicts=[],
        )

        summary = diff.present_changes()
        assert "No changes detected" in summary


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Edge case tests."""

    @pytest.mark.asyncio
    async def test_gather_facts_empty_raven_sites(self, mock_config, mock_raven_client):
        """Test gather_facts handles system with no Raven sites."""
        raven_system = RavenSystem(
            name="Empty System",
            architect="Test",
            revision=1,
            bodies=[],
        )
        mock_raven_client.get_system.return_value = raven_system
        mock_raven_client.get_sites.return_value = []

        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            journal_data = JournalData(docked_stations=[], visited_systems=[], last_play_session=None)
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False

            facts = await gather_facts("Empty System", mock_config, raven_client=mock_raven_client)

            assert facts.system_name == "Empty System"
            assert facts.landable_stations == []
            assert facts.non_landable_sites == []

    @pytest.mark.asyncio
    async def test_gather_facts_raven_api_error(self, mock_config, mock_raven_client):
        """Test gather_facts handles Raven API error gracefully."""
        mock_raven_client.get_system.side_effect = RavenAPIError("API Error")

        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            journal_data = JournalData(docked_stations=[], visited_systems=[], last_play_session=None)
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False

            # Raven errors are caught and logged; facts returned with raven_system=None
            facts = await gather_facts("Error System", mock_config, raven_client=mock_raven_client)
            assert facts.raven_system is None
            assert facts.raven_sites == []

    @pytest.mark.asyncio
    async def test_gather_facts_site_failure_leaves_site_evidence_false(
        self, mock_config, mock_raven_client
    ):
        """A system record without a successful site list carries no site evidence."""
        mock_raven_client.get_system.return_value = RavenSystem(
            name="Test System",
            architect="Test",
            revision=1,
            bodies=["Body 1"],
        )
        mock_raven_client.get_sites.side_effect = RavenAPIError("site list failed")

        with patch("edcg.facts.facts.find_journal_dir") as mock_find_journal, \
             patch("edcg.facts.facts.parse_journal") as mock_parse_journal:

            journal_data = JournalData(docked_stations=[], visited_systems=[], last_play_session=None)
            mock_find_journal.return_value = "/fake/journal/dir"
            mock_parse_journal.return_value = journal_data

            mock_config.inara_api_key = None
            mock_config.spansh_enabled = False

            facts = await gather_facts("Test System", mock_config, raven_client=mock_raven_client)

            assert facts.raven_system is not None
            assert facts.raven_sites == []
            assert facts.raven_sites_loaded is False


def test_names_match_compares_exact_station_names():
    """Parenthetical parts are part of the station name, not a removable suffix."""
    assert _names_match("Station (II-42)", "station (ii-42)")
    assert not _names_match("Station (Old)", "Station (New)")
    assert not _names_match("Cold Probabilities (ii42)", "Cold Probabilities (ii-42)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
