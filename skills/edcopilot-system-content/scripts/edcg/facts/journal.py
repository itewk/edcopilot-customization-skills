"""Journal Parser module for the EDCoPilot system content skill.

Parses Elite Dangerous journal files to extract docked stations, visited systems,
and play session timestamps.
"""

import json
import os
import platform
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Mapping


@dataclass
class JournalStation:
    """Represents a station the player has docked at."""
    name: str
    system: str
    timestamp: datetime
    market_id: Optional[int] = None


@dataclass
class JournalVisit:
    """Represents a system the player has visited."""
    system: str
    timestamp: datetime
    coordinates: Optional[tuple[float, float, float]] = None


@dataclass
class JournalData:
    """Aggregated journal data from parsing."""
    docked_stations: list[JournalStation]
    visited_systems: list[JournalVisit]
    last_play_session: Optional[datetime]


def find_journal_dir(env: Mapping[str, str] | None = None) -> Optional[Path]:
    """Find the Elite Dangerous journal directory for the current platform.

    When ``EDCG_JOURNAL_DIR`` is present in the environment, that path is
    checked first and returned only if it contains ``Journal.*.log`` files. An
    unset, invalid, or unreadable override falls through to the per-platform
    candidates unchanged.

    Args:
        env: Environment mapping to read; defaults to ``os.environ``.

    Returns:
        Path to the journal directory if found, None otherwise.
    """
    environment = os.environ if env is None else env

    override = environment.get("EDCG_JOURNAL_DIR")
    if override:
        candidate = Path(override)
        # Only return the override if it is a readable dir holding journals.
        if candidate.is_dir():
            try:
                has_journals = any(candidate.glob("Journal.*.log"))
            except OSError:
                # An unreadable override means "no journals here", not a crash.
                has_journals = False
            if has_journals:
                return candidate

    # Fall through to existing platform-specific logic
    home = Path.home()
    system = platform.system()

    candidate_paths: list[Path] = []

    if system == "Windows":
        # Windows: %USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous
        candidate_paths.append(home / "Saved Games" / "Frontier Developments" / "Elite Dangerous")
        # Also check OneDrive location which is common
        candidate_paths.append(home / "OneDrive" / "Saved Games" / "Frontier Developments" / "Elite Dangerous")
    elif system == "Linux":
        # Linux (Steam): ~/.local/share/Steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous
        # Linux (native/Epic): ~/.local/share/Frontier Developments/Elite Dangerous
        candidate_paths.append(home / ".local" / "share" / "Steam" / "steamapps" / "compatdata" / "359320" / "pfx" / "drive_c" / "users" / "steamuser" / "Saved Games" / "Frontier Developments" / "Elite Dangerous")
        candidate_paths.append(home / ".local" / "share" / "Frontier Developments" / "Elite Dangerous")
        candidate_paths.append(home / ".steam" / "steam" / "steamapps" / "compatdata" / "359320" / "pfx" / "drive_c" / "users" / "steamuser" / "Saved Games" / "Frontier Developments" / "Elite Dangerous")
    elif system == "Darwin":
        # macOS: ~/Library/Application Support/Frontier Developments/Elite Dangerous
        candidate_paths.append(home / "Library" / "Application Support" / "Frontier Developments" / "Elite Dangerous")

    for path in candidate_paths:
        if path.exists() and path.is_dir():
            # Verify it contains journal files
            journal_files = list(path.glob("Journal.*.log"))
            if journal_files:
                return path

    return None


def _parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Parse ISO format timestamp string to datetime."""
    try:
        # Handle various ISO formats
        # 2024-01-15T10:30:00Z
        # 2024-01-15T10:30:00.123Z
        # 2024-01-15T10:30:00+00:00
        if timestamp_str.endswith("Z"):
            timestamp_str = timestamp_str[:-1] + "+00:00"
        return datetime.fromisoformat(timestamp_str)
    except (ValueError, AttributeError):
        return None


def _parse_coordinates(star_pos) -> Optional[tuple[float, float, float]]:
    """Parse StarPos array into coordinate tuple."""
    if not star_pos or not isinstance(star_pos, (list, tuple)):
        return None
    if len(star_pos) != 3:
        return None
    try:
        return (float(star_pos[0]), float(star_pos[1]), float(star_pos[2]))
    except (ValueError, TypeError):
        return None


def parse_journal(
    journal_dir: Path,
    since_timestamp: Optional[datetime] = None,
) -> JournalData:
    """Parse Elite Dangerous journal files in the given directory.

    Args:
        journal_dir: Path to the directory containing Journal.*.log files.
        since_timestamp: If provided, only parse events after this timestamp (incremental parse).

    Returns:
        JournalData containing docked stations, visited systems, and last play session.
    """
    docked_stations: list[JournalStation] = []
    visited_systems: list[JournalVisit] = []
    last_play_session: Optional[datetime] = None

    if not journal_dir.exists() or not journal_dir.is_dir():
        return JournalData(
            docked_stations=docked_stations,
            visited_systems=visited_systems,
            last_play_session=last_play_session,
        )

    # Find all journal files and sort by name (which corresponds to rotation order)
    journal_files = sorted(journal_dir.glob("Journal.*.log"))

    # Collect all events from all files
    all_events: list[tuple[datetime, dict]] = []

    for journal_file in journal_files:
        try:
            with journal_file.open("r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        # Skip corrupt lines
                        continue

                    # Extract timestamp
                    timestamp_str = event.get("timestamp")
                    if not timestamp_str:
                        continue
                    timestamp = _parse_timestamp(timestamp_str)
                    if not timestamp:
                        continue

                    # Filter by since_timestamp if provided
                    if since_timestamp and timestamp <= since_timestamp:
                        continue

                    all_events.append((timestamp, event))

        except (OSError, UnicodeDecodeError):
            # Skip unreadable files
            continue

    # Sort all events by timestamp
    all_events.sort(key=lambda x: x[0])

    # Process events in chronological order
    for timestamp, event in all_events:
        event_type = event.get("event")

        if event_type == "Docked":
            station_name = event.get("StationName")
            star_system = event.get("StarSystem")
            market_id = event.get("MarketID")

            if station_name and star_system:
                station = JournalStation(
                    name=station_name,
                    system=star_system,
                    timestamp=timestamp,
                    market_id=market_id if isinstance(market_id, int) else None,
                )
                docked_stations.append(station)
                # Update last_play_session
                if last_play_session is None or timestamp > last_play_session:
                    last_play_session = timestamp

        elif event_type == "FSDJump":
            star_system = event.get("StarSystem")
            star_pos = event.get("StarPos")

            if star_system:
                coordinates = _parse_coordinates(star_pos)
                visit = JournalVisit(
                    system=star_system,
                    timestamp=timestamp,
                    coordinates=coordinates,
                )
                visited_systems.append(visit)
                # Update last_play_session
                if last_play_session is None or timestamp > last_play_session:
                    last_play_session = timestamp

        elif event_type == "Location":
            star_system = event.get("StarSystem")
            star_pos = event.get("StarPos")

            if star_system:
                coordinates = _parse_coordinates(star_pos)
                visit = JournalVisit(
                    system=star_system,
                    timestamp=timestamp,
                    coordinates=coordinates,
                )
                visited_systems.append(visit)
                # Note: Location events don't update last_play_session per spec

    return JournalData(
        docked_stations=docked_stations,
        visited_systems=visited_systems,
        last_play_session=last_play_session,
    )


__all__ = [
    "JournalStation",
    "JournalVisit",
    "JournalData",
    "find_journal_dir",
    "parse_journal",
]