"""Tests for Journal Parser module."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from edcg.facts.journal import (
    JournalData,
    JournalStation,
    JournalVisit,
    find_journal_dir,
    parse_journal,
)


class TestJournalDataStructures:
    """Tests for Journal data structures."""

    def test_journal_station_creation(self):
        """Test JournalStation dataclass creation."""
        station = JournalStation(
            name="Jameson Memorial",
            system="Shinrarta Dezhra",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            market_id=128049152,
        )
        assert station.name == "Jameson Memorial"
        assert station.system == "Shinrarta Dezhra"
        assert station.timestamp == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert station.market_id == 128049152

    def test_journal_visit_creation(self):
        """Test JournalVisit dataclass creation."""
        visit = JournalVisit(
            system="Sol",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            coordinates=(-23.125, 41.375, -1.875),
        )
        assert visit.system == "Sol"
        assert visit.timestamp == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert visit.coordinates == (-23.125, 41.375, -1.875)

    def test_journal_visit_without_coordinates(self):
        """Test JournalVisit can be created without coordinates."""
        visit = JournalVisit(
            system="Col 285 Sector CC-K a38-2",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            coordinates=None,
        )
        assert visit.system == "Col 285 Sector CC-K a38-2"
        assert visit.coordinates is None

    def test_journal_data_creation(self):
        """Test JournalData dataclass creation."""
        station = JournalStation(
            name="Test Station",
            system="Test System",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            market_id=12345,
        )
        visit = JournalVisit(
            system="Test System",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            coordinates=(0.0, 0.0, 0.0),
        )
        data = JournalData(
            docked_stations=[station],
            visited_systems=[visit],
            last_play_session=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )
        assert len(data.docked_stations) == 1
        assert len(data.visited_systems) == 1
        assert data.last_play_session == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)


class TestFindJournalDir:
    """Tests for find_journal_dir() function."""

    def test_find_journal_dir_windows(self):
        """Test find_journal_dir finds Windows journal directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # Create the Windows journal directory structure
            journal_dir = tmp_path / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
            journal_dir.mkdir(parents=True)
            # Create a dummy journal file
            (journal_dir / "Journal.0001.log").write_text('{"timestamp": "2024-01-15T10:00:00Z", "event": "Docked"}\n')

            with patch("edcg.facts.journal.Path.home") as mock_home:
                mock_home.return_value = tmp_path
                with patch("platform.system", return_value="Windows"):
                    result = find_journal_dir()
                    assert result is not None
                    assert result == journal_dir

    def test_find_journal_dir_linux(self):
        """Test find_journal_dir finds Linux journal directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # Create the Linux journal directory structure (native)
            journal_dir = tmp_path / ".local" / "share" / "Frontier Developments" / "Elite Dangerous"
            journal_dir.mkdir(parents=True)
            (journal_dir / "Journal.0001.log").write_text('{"timestamp": "2024-01-15T10:00:00Z", "event": "Docked"}\n')

            with patch("edcg.facts.journal.Path.home") as mock_home:
                mock_home.return_value = tmp_path
                with patch("platform.system", return_value="Linux"):
                    result = find_journal_dir()
                    assert result is not None
                    assert result == journal_dir

    def test_find_journal_dir_macos(self):
        """Test find_journal_dir finds macOS journal directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # Create the macOS journal directory structure
            journal_dir = tmp_path / "Library" / "Application Support" / "Frontier Developments" / "Elite Dangerous"
            journal_dir.mkdir(parents=True)
            (journal_dir / "Journal.0001.log").write_text('{"timestamp": "2024-01-15T10:00:00Z", "event": "Docked"}\n')

            with patch("edcg.facts.journal.Path.home") as mock_home:
                mock_home.return_value = tmp_path
                with patch("platform.system", return_value="Darwin"):
                    result = find_journal_dir()
                    assert result is not None
                    assert result == journal_dir

    def test_find_journal_dir_returns_none_when_not_found(self):
        """Test find_journal_dir returns None when no journal directory exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch("edcg.facts.journal.Path.home") as mock_home:
                mock_home.return_value = tmp_path
                with patch("platform.system", return_value="Windows"):
                    result = find_journal_dir()
                    assert result is None

    def test_find_journal_dir_prefers_first_candidate(self):
        """Test find_journal_dir returns the first candidate that exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # Create both Windows candidate paths
            journal_dir1 = tmp_path / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
            journal_dir2 = tmp_path / "OneDrive" / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
            journal_dir1.mkdir(parents=True)
            journal_dir2.mkdir(parents=True)
            (journal_dir1 / "Journal.0001.log").write_text('{"timestamp": "2024-01-15T10:00:00Z", "event": "Docked"}\n')
            (journal_dir2 / "Journal.0001.log").write_text('{"timestamp": "2024-01-15T10:00:00Z", "event": "Docked"}\n')

            with patch("edcg.facts.journal.Path.home") as mock_home:
                mock_home.return_value = tmp_path
                with patch("platform.system", return_value="Windows"):
                    result = find_journal_dir()
                    # Should return the first candidate (Saved Games, not OneDrive)
                    assert result == journal_dir1


class TestParseJournal:
    """Tests for parse_journal() function."""

    def create_journal_file(self, tmpdir: Path, entries: list[dict], filename: str = "Journal.0001.log") -> Path:
        """Helper to create a journal file with given entries."""
        journal_path = tmpdir / filename
        with journal_path.open("w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        return journal_path

    def test_parse_empty_journal(self):
        """Test parsing an empty journal directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # Create empty journal file
            (tmp_path / "Journal.0001.log").write_text("")
            result = parse_journal(tmp_path)
            assert result.docked_stations == []
            assert result.visited_systems == []
            assert result.last_play_session is None

    def test_parse_journal_with_docked_event(self):
        """Test parsing Docked event extracts station info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            entries = [{
                "timestamp": "2024-01-15T10:30:00Z",
                "event": "Docked",
                "StationName": "Jameson Memorial",
                "StarSystem": "Shinrarta Dezhra",
                "MarketID": 128049152,
            }]
            self.create_journal_file(tmp_path, entries)
            result = parse_journal(tmp_path)
            assert len(result.docked_stations) == 1
            station = result.docked_stations[0]
            assert station.name == "Jameson Memorial"
            assert station.system == "Shinrarta Dezhra"
            assert station.market_id == 128049152
            assert station.timestamp == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_parse_journal_with_fsdjump_event(self):
        """Test parsing FSDJump event extracts system visit info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            entries = [{
                "timestamp": "2024-01-15T10:30:00Z",
                "event": "FSDJump",
                "StarSystem": "Sol",
                "StarPos": [-23.125, 41.375, -1.875],
            }]
            self.create_journal_file(tmp_path, entries)
            result = parse_journal(tmp_path)
            assert len(result.visited_systems) == 1
            visit = result.visited_systems[0]
            assert visit.system == "Sol"
            assert visit.coordinates == (-23.125, 41.375, -1.875)
            assert visit.timestamp == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_parse_journal_with_location_event(self):
        """Test parsing Location event extracts system visit info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            entries = [{
                "timestamp": "2024-01-15T10:30:00Z",
                "event": "Location",
                "StarSystem": "Col 285 Sector CC-K a38-2",
                "StarPos": [100.0, 200.0, -50.0],
            }]
            self.create_journal_file(tmp_path, entries)
            result = parse_journal(tmp_path)
            assert len(result.visited_systems) == 1
            visit = result.visited_systems[0]
            assert visit.system == "Col 285 Sector CC-K a38-2"
            assert visit.coordinates == (100.0, 200.0, -50.0)
            assert visit.timestamp == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_parse_journal_with_multiple_events(self):
        """Test parsing multiple events in chronological order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            entries = [
                {
                    "timestamp": "2024-01-15T10:00:00Z",
                    "event": "FSDJump",
                    "StarSystem": "System A",
                    "StarPos": [0.0, 0.0, 0.0],
                },
                {
                    "timestamp": "2024-01-15T10:15:00Z",
                    "event": "Docked",
                    "StationName": "Station A",
                    "StarSystem": "System A",
                    "MarketID": 11111,
                },
                {
                    "timestamp": "2024-01-15T10:30:00Z",
                    "event": "FSDJump",
                    "StarSystem": "System B",
                    "StarPos": [10.0, 10.0, 10.0],
                },
                {
                    "timestamp": "2024-01-15T10:45:00Z",
                    "event": "Docked",
                    "StationName": "Station B",
                    "StarSystem": "System B",
                    "MarketID": 22222,
                },
            ]
            self.create_journal_file(tmp_path, entries)
            result = parse_journal(tmp_path)
            assert len(result.visited_systems) == 2
            assert len(result.docked_stations) == 2
            # Check last_play_session is the most recent Docked/FSDJump
            assert result.last_play_session == datetime(2024, 1, 15, 10, 45, 0, tzinfo=timezone.utc)

    def test_parse_journal_handles_rotation_multiple_files(self):
        """Test parsing handles journal rotation (multiple Journal.*.log files)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # First journal file (older)
            entries1 = [{
                "timestamp": "2024-01-14T10:00:00Z",
                "event": "Docked",
                "StationName": "Old Station",
                "StarSystem": "Old System",
                "MarketID": 99999,
            }]
            self.create_journal_file(tmp_path, entries1, "Journal.0001.log")
            # Second journal file (newer)
            entries2 = [{
                "timestamp": "2024-01-15T10:00:00Z",
                "event": "Docked",
                "StationName": "New Station",
                "StarSystem": "New System",
                "MarketID": 88888,
            }]
            self.create_journal_file(tmp_path, entries2, "Journal.0002.log")
            result = parse_journal(tmp_path)
            assert len(result.docked_stations) == 2
            # Should be in chronological order
            assert result.docked_stations[0].name == "Old Station"
            assert result.docked_stations[1].name == "New Station"
            assert result.last_play_session == datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    def test_parse_journal_ignores_non_relevant_events(self):
        """Test parsing ignores events other than Docked, FSDJump, Location."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            entries = [
                {
                    "timestamp": "2024-01-15T10:00:00Z",
                    "event": "Scan",
                    "BodyName": "Planet 1",
                },
                {
                    "timestamp": "2024-01-15T10:15:00Z",
                    "event": "Docked",
                    "StationName": "Station",
                    "StarSystem": "System",
                    "MarketID": 12345,
                },
                {
                    "timestamp": "2024-01-15T10:30:00Z",
                    "event": "SupercruiseEntry",
                    "StarSystem": "System",
                },
            ]
            self.create_journal_file(tmp_path, entries)
            result = parse_journal(tmp_path)
            assert len(result.docked_stations) == 1
            assert len(result.visited_systems) == 0

    def test_parse_journal_handles_corrupt_line(self):
        """Test parsing handles corrupt/invalid JSON lines gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            journal_path = tmp_path / "Journal.0001.log"
            with journal_path.open("w") as f:
                f.write('{"timestamp": "2024-01-15T10:00:00Z", "event": "Docked", "StationName": "Station", "StarSystem": "System", "MarketID": 12345}\n')
                f.write("this is not valid json\n")
                f.write('{"timestamp": "2024-01-15T10:30:00Z", "event": "Docked", "StationName": "Station2", "StarSystem": "System2", "MarketID": 67890}\n')
            result = parse_journal(tmp_path)
            assert len(result.docked_stations) == 2

    def test_parse_journal_incremental_since_timestamp(self):
        """Test incremental parsing with since_timestamp parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            entries = [
                {
                    "timestamp": "2024-01-15T10:00:00Z",
                    "event": "Docked",
                    "StationName": "Old Station",
                    "StarSystem": "Old System",
                    "MarketID": 11111,
                },
                {
                    "timestamp": "2024-01-15T11:00:00Z",
                    "event": "Docked",
                    "StationName": "New Station",
                    "StarSystem": "New System",
                    "MarketID": 22222,
                },
                {
                    "timestamp": "2024-01-15T12:00:00Z",
                    "event": "FSDJump",
                    "StarSystem": "Latest System",
                    "StarPos": [1.0, 2.0, 3.0],
                },
            ]
            self.create_journal_file(tmp_path, entries)
            since = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
            result = parse_journal(tmp_path, since_timestamp=since)
            assert len(result.docked_stations) == 1
            assert result.docked_stations[0].name == "New Station"
            assert len(result.visited_systems) == 1
            assert result.visited_systems[0].system == "Latest System"

    def test_parse_journal_handles_missing_fields_gracefully(self):
        """Test parsing handles events with missing optional fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            entries = [
                {
                    "timestamp": "2024-01-15T10:00:00Z",
                    "event": "Docked",
                    "StationName": "Station Without MarketID",
                    "StarSystem": "System",
                    # MarketID missing
                },
                {
                    "timestamp": "2024-01-15T11:00:00Z",
                    "event": "FSDJump",
                    "StarSystem": "System Without Coords",
                    # StarPos missing
                },
            ]
            self.create_journal_file(tmp_path, entries)
            result = parse_journal(tmp_path)
            assert len(result.docked_stations) == 1
            assert result.docked_stations[0].market_id is None
            assert len(result.visited_systems) == 1
            assert result.visited_systems[0].coordinates is None

    def test_parse_journal_handles_fsdjump_without_starpos(self):
        """Test FSDJump event without StarPos still creates visit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            entries = [{
                "timestamp": "2024-01-15T10:00:00Z",
                "event": "FSDJump",
                "StarSystem": "System Without Coords",
            }]
            self.create_journal_file(tmp_path, entries)
            result = parse_journal(tmp_path)
            assert len(result.visited_systems) == 1
            assert result.visited_systems[0].system == "System Without Coords"
            assert result.visited_systems[0].coordinates is None

    def test_parse_journal_sorts_by_timestamp_across_files(self):
        """Test events are sorted by timestamp across multiple rotated files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # File 1 has later timestamp
            entries1 = [{
                "timestamp": "2024-01-15T12:00:00Z",
                "event": "Docked",
                "StationName": "Later Station",
                "StarSystem": "Later System",
                "MarketID": 11111,
            }]
            self.create_journal_file(tmp_path, entries1, "Journal.0001.log")
            # File 2 has earlier timestamp
            entries2 = [{
                "timestamp": "2024-01-15T10:00:00Z",
                "event": "Docked",
                "StationName": "Earlier Station",
                "StarSystem": "Earlier System",
                "MarketID": 22222,
            }]
            self.create_journal_file(tmp_path, entries2, "Journal.0002.log")
            result = parse_journal(tmp_path)
            assert len(result.docked_stations) == 2
            # Should be sorted by timestamp, not file order
            assert result.docked_stations[0].name == "Earlier Station"
            assert result.docked_stations[1].name == "Later Station"

    def test_parse_journal_last_play_session_from_docked(self):
        """Test last_play_session uses most recent Docked event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            entries = [
                {
                    "timestamp": "2024-01-15T10:00:00Z",
                    "event": "Docked",
                    "StationName": "Station A",
                    "StarSystem": "System A",
                    "MarketID": 11111,
                },
                {
                    "timestamp": "2024-01-15T11:00:00Z",
                    "event": "Docked",
                    "StationName": "Station B",
                    "StarSystem": "System B",
                    "MarketID": 22222,
                },
            ]
            self.create_journal_file(tmp_path, entries)
            result = parse_journal(tmp_path)
            assert result.last_play_session == datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc)

    def test_parse_journal_last_play_session_from_fsdjump(self):
        """Test last_play_session uses most recent FSDJump when no Docked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            entries = [
                {
                    "timestamp": "2024-01-15T10:00:00Z",
                    "event": "FSDJump",
                    "StarSystem": "System A",
                    "StarPos": [0.0, 0.0, 0.0],
                },
                {
                    "timestamp": "2024-01-15T11:00:00Z",
                    "event": "FSDJump",
                    "StarSystem": "System B",
                    "StarPos": [1.0, 1.0, 1.0],
                },
            ]
            self.create_journal_file(tmp_path, entries)
            result = parse_journal(tmp_path)
            assert result.last_play_session == datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc)

    def test_parse_journal_last_play_session_picks_latest_of_both(self):
        """Test last_play_session picks latest timestamp from Docked or FSDJump."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            entries = [
                {
                    "timestamp": "2024-01-15T10:00:00Z",
                    "event": "Docked",
                    "StationName": "Station A",
                    "StarSystem": "System A",
                    "MarketID": 11111,
                },
                {
                    "timestamp": "2024-01-15T11:00:00Z",
                    "event": "FSDJump",
                    "StarSystem": "System B",
                    "StarPos": [1.0, 1.0, 1.0],
                },
            ]
            self.create_journal_file(tmp_path, entries)
            result = parse_journal(tmp_path)
            assert result.last_play_session == datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc)


class TestParseJournalEdgeCases:
    """Edge case tests for parse_journal()."""

    def create_journal_file(self, tmpdir: Path, entries: list[dict], filename: str = "Journal.0001.log") -> Path:
        """Helper to create a journal file with given entries."""
        journal_path = tmpdir / filename
        with journal_path.open("w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        return journal_path

    def test_parse_nonexistent_directory(self):
        """Test parsing nonexistent directory returns empty data."""
        result = parse_journal(Path("/nonexistent/path"))
        assert result.docked_stations == []
        assert result.visited_systems == []
        assert result.last_play_session is None

    def test_parse_directory_with_no_journal_files(self):
        """Test parsing directory with no Journal.*.log files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "other.txt").write_text("not a journal")
            result = parse_journal(tmp_path)
            assert result.docked_stations == []
            assert result.visited_systems == []
            assert result.last_play_session is None

    def test_parse_journal_handles_timestamp_formats(self):
        """Test parsing handles various ISO timestamp formats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            entries = [
                {"timestamp": "2024-01-15T10:00:00Z", "event": "Docked", "StationName": "A", "StarSystem": "Sys", "MarketID": 1},
                {"timestamp": "2024-01-15T10:00:00.123Z", "event": "Docked", "StationName": "B", "StarSystem": "Sys", "MarketID": 2},
                {"timestamp": "2024-01-15T10:00:00+00:00", "event": "Docked", "StationName": "C", "StarSystem": "Sys", "MarketID": 3},
            ]
            self.create_journal_file(tmp_path, entries)
            result = parse_journal(tmp_path)
            assert len(result.docked_stations) == 3

    def test_parse_journal_handles_undocked_event(self):
        """Test that Undocked event is ignored (not Docked)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            entries = [{
                "timestamp": "2024-01-15T10:00:00Z",
                "event": "Undocked",
                "StationName": "Station",
                "StarSystem": "System",
                "MarketID": 12345,
            }]
            self.create_journal_file(tmp_path, entries)
            result = parse_journal(tmp_path)
            assert len(result.docked_stations) == 0

    def test_parse_journal_docked_without_market_id(self):
        """Test Docked event without MarketID still creates station entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            entries = [{
                "timestamp": "2024-01-15T10:00:00Z",
                "event": "Docked",
                "StationName": "Station",
                "StarSystem": "System",
                # MarketID intentionally omitted
            }]
            self.create_journal_file(tmp_path, entries)
            result = parse_journal(tmp_path)
            assert len(result.docked_stations) == 1
            assert result.docked_stations[0].market_id is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])