"""Fact builders shared by the tests that construct ``SystemFacts``.

The audit report tests build a whole four-source system in nearly every case.
Keeping the constructors here gives those tests one definition of "a clean
system" instead of a per-test copy, and lets a facts-layer test import the same
builders if it needs a full report fixture.

Deliberately plain functions, not fixtures: they are called from ``pytest.mark``
parameters and module-level setup in more than one test directory.
"""

from __future__ import annotations

from datetime import UTC, datetime

from edcg.facts.facts import LandableStation
from edcg.facts.inara import InaraStation, InaraSystem
from edcg.facts.journal import JournalData, JournalStation, JournalVisit
from edcg.facts.raven import RavenSite, RavenSystem
from edcg.facts.spansh import SpanshStation, SpanshSystem

DT = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def raven_system(name: str = "Alpha", revision: int = 7) -> RavenSystem:
    return RavenSystem(
        name=name,
        architect="Test Architect",
        revision=revision,
        bodies=["Alpha 1"],
    )


def raven_site(
    name: str = "Alpha Station",
    build_type: str = "nona",
    status: str = "complete",
    site_id: int = 1,
    body_num: int = 0,
) -> RavenSite:
    return RavenSite(
        id=site_id,
        name=name,
        status=status,
        build_type=build_type,
        body_num=body_num,
    )


def journal_station(
    name: str = "Alpha Station",
    system: str = "Alpha",
    market_id: int | None = 123,
) -> JournalStation:
    return JournalStation(name=name, system=system, timestamp=DT, market_id=market_id)


def journal_data(stations: list[JournalStation] | None = None) -> JournalData:
    stations = stations or []
    return JournalData(
        docked_stations=stations,
        visited_systems=[JournalVisit(system="Alpha", timestamp=DT)],
        last_play_session=DT,
    )


def inara_system(name: str = "Alpha") -> InaraSystem:
    return InaraSystem(
        name=name,
        coordinates=[0.0, 0.0, 0.0],
        population=1000,
        government="Democracy",
        allegiance="Independent",
        state="None",
        security="Low",
        primary_economy="Industrial",
        updated=DT,
    )


def inara_station(name: str, station_type: str = "Outpost") -> InaraStation:
    return InaraStation(
        name=name,
        type=station_type,
        services=["Market"],
        economy="Industrial",
        updated=DT,
    )


def spansh_station(
    name: str = "Alpha Station",
    market_id: int = 123,
    large_pads: int = 0,
    medium_pads: int = 1,
    small_pads: int = 0,
) -> SpanshStation:
    return SpanshStation(
        market_id=market_id,
        name=name,
        type="Outpost",
        controlling_minor_faction="Test Faction",
        controlling_minor_faction_state=None,
        distance_to_arrival=100.0,
        has_large_pad=large_pads > 0,
        has_market=True,
        large_pads=large_pads,
        medium_pads=medium_pads,
        small_pads=small_pads,
        services=["Market"],
    )


def spansh_system(stations: list[SpanshStation] | None = None) -> SpanshSystem:
    stations = stations or []
    return SpanshSystem(
        id64=1,
        name="Alpha",
        coordinates=[0.0, 0.0, 0.0],
        population=1000,
        government="Democracy",
        allegiance="Independent",
        state="None",
        security="Low",
        primary_economy="Industrial",
        secondary_economy="",
        controlling_minor_faction="Test Faction",
        stations=stations,
        bodies=[],
        updated=DT,
    )


def landable_station(name: str = "Alpha Station") -> LandableStation:
    return LandableStation(
        name=name,
        build_type="nona",
        facility_class="outpost",
        facility_name="Civilian Surface Outpost",
        body="Alpha 1",
        status="complete",
        source="raven",
        placement="surface",
        market_id=None,
    )
