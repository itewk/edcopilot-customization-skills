"""Fact Aggregation & Diff Engine for the EDCoPilot system content skill.

Merges data from Raven Colonial, player journal, Inara, and Spansh into
a unified SystemFacts object with conflict detection and source attribution.
Provides diff computation between dossier versions for LLM prompt building.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, Protocol, overload

from edcg.facts.journal import JournalData, JournalStation, find_journal_dir, parse_journal
from edcg.facts.raven import RavenSite, RavenSystem, is_placeholder_name, is_unresolved_site
from edcg.facts.inara import InaraStation, InaraSystem
from edcg.facts.spansh import SpanshStation, SpanshSystem
from edcg.common.config import Config
from edcg.rules.engine import is_landable_build_type, get_facility_class, get_facility_name, get_placement


# Protocol definitions for dependency injection (testing)
class RavenClientProtocol(Protocol):
    async def __aenter__(self) -> "RavenClientProtocol": ...
    async def __aexit__(self, *args: object) -> None: ...
    async def get_system(self, system_name: str) -> RavenSystem: ...
    async def get_sites(self, system_name: str) -> list[RavenSite]: ...


class InaraClientProtocol(Protocol):
    async def __aenter__(self) -> "InaraClientProtocol": ...
    async def __aexit__(self, *args: object) -> None: ...
    async def search_system(self, system_name: str) -> Optional[InaraSystem]: ...
    async def get_station(self, system: str, station: str) -> Optional[InaraStation]: ...


class SpanshClientProtocol(Protocol):
    async def __aenter__(self) -> "SpanshClientProtocol": ...
    async def __aexit__(self, *args: object) -> None: ...
    async def get_system(self, system_name: str) -> SpanshSystem: ...


@dataclass
class SourceAttribution:
    """Tracks the source(s) of a fact and any conflicts."""
    field: str
    value: str
    sources: list[str]
    conflict: bool = False
    details: Optional[str] = None


@dataclass
class Site:
    """A colonisation site: a landable station or a hub/installation.

    Landable and non-landable sites carry the same facts and differ only in
    ``is_landable``, so one record serves both. ``LandableStation`` and
    ``NonLandableSite`` remain as the names the callers and type hints use.
    """
    name: str
    build_type: str
    facility_class: str
    facility_name: str
    body: str
    status: str
    source: str  # "raven", "journal", "inara", "spansh"
    placement: str  # "surface", "orbital", or "unknown"
    is_landable: bool = True
    market_id: Optional[int] = None
    last_docked: Optional[datetime] = None


LandableStation = Site


@dataclass
class NonLandableSite(Site):
    """A non-landable site (hub or installation)."""
    is_landable: bool = False


@dataclass
class JournalOnlyStation:
    """A station the player docked at but not found in Raven."""
    name: str
    system: str
    timestamp: datetime
    market_id: Optional[int] = None


@dataclass
class StationBody:
    """Environmental summary for a body that has stations on or around it.

    Populated from the Spansh body data already fetched by gather_facts, so
    station content can describe what a Commander sees from it. Values are
    None when Spansh did not supply the field.
    """
    name: str
    sub_type: Optional[str] = None
    atmosphere: Optional[str] = None
    temperature_k: Optional[float] = None
    pressure_atm: Optional[float] = None
    gravity_g: Optional[float] = None
    radius_km: Optional[float] = None
    volcanism: Optional[str] = None
    orbital_period_days: Optional[float] = None
    landable: Optional[bool] = None
    terraforming_state: Optional[str] = None


@dataclass
class SystemFacts:
    """Aggregated facts for a system from all sources."""
    system_name: str
    raven_system: Optional[RavenSystem] = None
    raven_sites: list[RavenSite] = field(default_factory=list)
    raven_sites_loaded: bool = False
    journal_data: Optional[JournalData] = None
    inara_system: Optional[InaraSystem] = None
    inara_stations: list[InaraStation] = field(default_factory=list)
    spansh_system: Optional[SpanshSystem] = None
    spansh_stations: list[SpanshStation] = field(default_factory=list)
    landable_stations: list[LandableStation] = field(default_factory=list)
    non_landable_sites: list[NonLandableSite] = field(default_factory=list)
    journal_only_stations: list[JournalOnlyStation] = field(default_factory=list)
    station_bodies: list[StationBody] = field(default_factory=list)
    conflicts: list[SourceAttribution] = field(default_factory=list)


@dataclass
class StatusChange:
    """Represents a status change for a site."""
    name: str
    old_status: str
    new_status: str
    build_type: str = ""


@dataclass
class BuildTypeChange:
    """Represents a build type change for a site."""
    name: str
    old_build_type: str
    new_build_type: str


@dataclass
class RenamedStation:
    """Represents a renamed station."""
    old_name: str
    new_name: str
    build_type: str = ""


@dataclass
class FactsDiff:
    """Diff between two system fact sets."""
    system_name: str
    old_revision: int
    new_revision: int
    raven_revision_delta: int
    new_landable_stations: list[LandableStation] = field(default_factory=list)
    lost_landable_stations: list[LandableStation] = field(default_factory=list)
    renamed_stations: list[RenamedStation] = field(default_factory=list)
    build_type_changes: list[BuildTypeChange] = field(default_factory=list)
    status_changes: list[StatusChange] = field(default_factory=list)
    new_non_landable_sites: list[NonLandableSite] = field(default_factory=list)
    lost_non_landable_sites: list[NonLandableSite] = field(default_factory=list)
    journal_only_stations: list[JournalOnlyStation] = field(default_factory=list)
    inara_discrepancies: list[SourceAttribution] = field(default_factory=list)
    spansh_discrepancies: list[SourceAttribution] = field(default_factory=list)
    conflicts: list[SourceAttribution] = field(default_factory=list)

    def has_changes(self) -> bool:
        """Check if this diff contains any changes."""
        return any([
            self.new_landable_stations,
            self.lost_landable_stations,
            self.renamed_stations,
            self.build_type_changes,
            self.status_changes,
            self.new_non_landable_sites,
            self.lost_non_landable_sites,
            self.journal_only_stations,
            self.inara_discrepancies,
            self.spansh_discrepancies,
            self.conflicts,
            self.raven_revision_delta != 0,
        ])

def _site_record(
    *,
    name: str,
    build_type: str,
    facility_class: str,
    facility_name: str,
    body: str,
    status: str,
    source: str,
    placement: str,
    landable: bool,
) -> Site:
    """Build a site record, choosing the class that carries the default."""
    site_type = LandableStation if landable else NonLandableSite
    return site_type(
        name=name,
        build_type=build_type,
        facility_class=facility_class,
        facility_name=facility_name,
        body=body,
        status=status,
        source=source,
        placement=placement,
        is_landable=landable,
    )


async def gather_facts(
    system_name: str,
    config: Config,
    *,
    raven_client: Optional[RavenClientProtocol] = None,
    inara_client: Optional[InaraClientProtocol] = None,
    spansh_client: Optional[SpanshClientProtocol] = None,
) -> SystemFacts:
    """Gather and merge facts for a system from all configured sources.

    Args:
        system_name: Name of the system to gather facts for.
        config: Application configuration with API settings.
        raven_client: Optional pre-configured Raven client (for testing).
        inara_client: Optional pre-configured Inara client (for testing).
        spansh_client: Optional pre-configured Spansh client (for testing).

    Returns:
        SystemFacts with merged data, conflict flags, and source attribution.
    """
    # Initialize result
    facts = SystemFacts(system_name=system_name)

    # --- Fetch from Raven Colonial ---
    if raven_client is None:
        from edcg.facts.raven import RavenClient
        raven_client = RavenClient(config.raven_api_url)  # type: ignore[assignment]

    async with raven_client:  # type: ignore[union-attr]
        try:
            raven_system = await raven_client.get_system(system_name)  # type: ignore[union-attr]
            facts.raven_system = raven_system

            raven_sites = await raven_client.get_sites(system_name)  # type: ignore[union-attr]
            facts.raven_sites = raven_sites
            # Only a successful site-list call is evidence that a station is
            # absent from the Raven plan.
            facts.raven_sites_loaded = True
        except Exception:
            # Raven is primary source; if it fails, we still continue with other sources
            pass

    # --- Parse Journal ---
    journal_dir = find_journal_dir(os.environ)
    if journal_dir:
        journal_data = parse_journal(journal_dir)
        facts.journal_data = journal_data

        # Filter journal stations for this system and collapse repeated dock
        # events to the latest event per station name.
        system_stations = [
            s for s in journal_data.docked_stations if s.system == system_name
        ]
        system_stations = _latest_station_per_name(system_stations)
    else:
        system_stations = []

    # --- Fetch from Spansh (if enabled) ---
    # Spansh is fetched before Inara because its station names are candidates
    # for the per-station Inara lookups below.
    if config.spansh_enabled:
        if spansh_client is None:
            from edcg.facts.spansh import SpanshClient
            spansh_client = SpanshClient()  # type: ignore[assignment]

        async with spansh_client:  # type: ignore[union-attr]
            try:
                spansh_system = await spansh_client.get_system(system_name)  # type: ignore[union-attr]
                facts.spansh_system = spansh_system
                facts.spansh_stations = spansh_system.stations
            except Exception:
                pass

    # --- Fetch from Inara (if configured) ---
    if config.inara_api_key:
        if inara_client is None:
            from edcg.facts.inara import InaraClient
            inara_client = InaraClient(config.inara_api_key)  # type: ignore[assignment]

        async with inara_client:  # type: ignore[union-attr]
            try:
                inara_system = await inara_client.search_system(system_name)  # type: ignore[union-attr]
                facts.inara_system = inara_system

                # Inara has no system station-list endpoint, so station records
                # are fetched one candidate at a time. Candidates come from the
                # sources that expose station names: usable Raven sites, journal
                # docks and Spansh stations. A failed lookup must not lose the
                # stations already collected.
                if inara_system is not None:
                    for station_name in _inara_candidate_station_names(facts, system_stations):
                        try:
                            inara_station = await inara_client.get_station(  # type: ignore[union-attr]
                                system_name, station_name
                            )
                        except Exception:
                            continue
                        if inara_station is not None:
                            facts.inara_stations.append(inara_station)
            except Exception:
                pass

    # --- Process Raven sites into landable/non-landable ---
    raven_station_names = set()
    for site in facts.raven_sites:
        # Skip placeholder and unresolved sites
        if is_placeholder_name(site.name):
            continue
        if is_unresolved_site(site):
            continue

        raven_station_names.add(site.name)

        # Determine landability from build_type
        landable = is_landable_build_type(site.build_type)
        facility_class = get_facility_class(site.build_type)
        facility_name = get_facility_name(site.build_type)

        # Resolve the body by its Raven num (bodyNum is an id, not an index)
        body_name = "Unknown"
        if facts.raven_system:
            body_name = facts.raven_system.body_name(site.body_num)

        # Placement is a property of the build type, not the facility class:
        # some outposts and starports orbit while their surface variants do not.
        placement = get_placement(site.build_type)

        record = _site_record(
            name=site.name,
            build_type=site.build_type,
            facility_class=facility_class,
            facility_name=facility_name,
            body=body_name,
            status=site.status,
            source="raven",
            placement=placement,
            landable=landable,
        )
        if landable:
            facts.landable_stations.append(record)
        else:
            facts.non_landable_sites.append(record)

    # --- Cross-reference with Journal ---
    for journal_station in system_stations:
        # Check if this journal station matches a Raven site
        matched = False
        for record in (*facts.landable_stations, *facts.non_landable_sites):
            if _names_match(journal_station.name, record.name):
                # Update with journal data
                record.market_id = journal_station.market_id
                record.last_docked = journal_station.timestamp
                matched = True
                break

        if not matched:
            # Journal-only station
            facts.journal_only_stations.append(JournalOnlyStation(
                name=journal_station.name,
                system=journal_station.system,
                timestamp=journal_station.timestamp,
                market_id=journal_station.market_id,
            ))

    # --- Detect conflicts between sources ---
    _detect_conflicts(facts, system_stations)

    # --- Body flavour for bodies carrying stations ---
    facts.station_bodies = _collect_station_bodies(facts)

    return facts


def _latest_station_per_name(stations: list[JournalStation]) -> list[JournalStation]:
    """Collapse repeated dock events, keeping the latest event per station."""
    latest: list[JournalStation] = []
    for station in stations:
        for index, existing in enumerate(latest):
            if _names_match(station.name, existing.name):
                if station.timestamp > existing.timestamp:
                    latest[index] = station
                break
        else:
            latest.append(station)
    return latest


def _inara_candidate_station_names(
    facts: SystemFacts, journal_stations: list[JournalStation]
) -> list[str]:
    """Return unique station names to ask Inara about, in source order.

    Inara exposes no system station-list endpoint, so candidates must come from
    sources that do expose names: usable Raven sites (placeholders and
    unresolved rows skipped), journal docks and Spansh stations.
    """
    names: list[str] = []

    def add(name: str | None) -> None:
        if not name:
            return
        if any(_names_match(name, existing) for existing in names):
            return
        names.append(name)

    for site in facts.raven_sites:
        if site.name is None:
            continue
        if is_placeholder_name(site.name) or is_unresolved_site(site):
            continue
        add(site.name)

    for journal_station in journal_stations:
        add(journal_station.name)

    for spansh_station in facts.spansh_stations:
        add(spansh_station.name)

    return names


def _names_match(name1: str, name2: str) -> bool:
    """Check if two station names match, ignoring case and surrounding whitespace."""
    return name1.strip().casefold() == name2.strip().casefold()


def _collect_station_bodies(facts: SystemFacts) -> list[StationBody]:
    """Summarise Spansh data for the bodies that stations sit on or orbit.

    Only bodies carrying a station are included: systems can hold dozens of
    bodies, and prompt budget follows station count, not body count.

    Args:
        facts: Merged facts, after stations and Spansh data are resolved.

    Returns:
        One StationBody per distinct station body, in station order.
    """
    names: list[str] = []
    for station in [*facts.landable_stations, *facts.non_landable_sites]:
        name = (station.body or "").strip()
        if name and name != "Unknown" and name not in names:
            names.append(name)

    by_name: dict[str, dict] = {}
    if facts.spansh_system:
        for body in facts.spansh_system.bodies:
            body_name = body.get("name")
            if isinstance(body_name, str):
                by_name[body_name] = body

    summaries: list[StationBody] = []
    for name in names:
        data = by_name.get(name, {})
        summaries.append(StationBody(
            name=name,
            sub_type=data.get("subType"),
            atmosphere=data.get("atmosphereType"),
            temperature_k=data.get("surfaceTemperature"),
            pressure_atm=data.get("surfacePressure"),
            gravity_g=data.get("gravity"),
            radius_km=data.get("radius"),
            volcanism=data.get("volcanismType"),
            orbital_period_days=data.get("orbitalPeriod"),
            landable=data.get("isLandable"),
            terraforming_state=data.get("terraformingState"),
        ))
    return summaries


def _detect_conflicts(
    facts: SystemFacts, journal_stations: list[JournalStation]
) -> None:
    """Detect and record conflicts between sources.

    Args:
        facts: Merged facts to inspect.
        journal_stations: System-filtered journal dock stations collapsed to
            the latest event per station name. Using the collapsed names
            (rather than the raw dock history) prevents pre-rename dock
            events from producing false-positive name-mismatch conflicts.
    """
    # Conflict: Raven system name vs journal system name
    if facts.raven_system and facts.journal_data:
        journal_systems = {v.system for v in facts.journal_data.visited_systems}
        if facts.raven_system.name not in journal_systems and journal_systems:
            facts.conflicts.append(SourceAttribution(
                field="system_name",
                value=facts.raven_system.name,
                sources=["raven", "journal"],
                conflict=True,
                details=f"Raven name '{facts.raven_system.name}' not in journal visited systems: {journal_systems}",
            ))

    # Conflict: Station names between Raven and Journal
    # Compare against the collapsed latest-per-station journal names, not the
    # raw dock history, so rename history does not flag a false conflict.
    raven_names = {s.name for s in facts.landable_stations} | {s.name for s in facts.non_landable_sites}
    journal_names = {s.name for s in journal_stations}

    # Check for stations in both but with different canonical names
    for j_name in journal_names:
        for r_name in raven_names:
            if _names_match(j_name, r_name) and j_name != r_name:
                facts.conflicts.append(SourceAttribution(
                    field="station_name",
                    value=r_name,
                    sources=["raven", "journal"],
                    conflict=True,
                    details=f"Name mismatch: Raven='{r_name}', Journal='{j_name}'",
                ))

    # Conflict: Inara vs Raven/Spansh (if both present)
    if facts.inara_system and facts.spansh_system:
        if facts.inara_system.name != facts.spansh_system.name:
            facts.conflicts.append(SourceAttribution(
                field="system_name",
                value=facts.inara_system.name,
                sources=["inara", "spansh"],
                conflict=True,
                details=f"Inara name '{facts.inara_system.name}' != Spansh name '{facts.spansh_system.name}'",
            ))


def compute_facts_diff(existing_dossier: dict, new_facts: SystemFacts) -> FactsDiff:
    """Compute diff between existing dossier and new facts.

    Args:
        existing_dossier: Parsed existing dossier data (from previous run).
        new_facts: Freshly gathered SystemFacts.

    Returns:
        FactsDiff with all detected changes.
    """
    old_revision = existing_dossier.get("raven_revision", 0)
    new_revision = new_facts.raven_system.revision if new_facts.raven_system else 0

    # Build lookup maps for existing stations
    # The existing dossier may have "stations" (all) and "non_landable_sites" (explicit)
    # We need to classify them by build_type
    existing_landable = {}
    existing_non_landable = {}

    # Process explicit non_landable_sites first
    for s in existing_dossier.get("non_landable_sites", []):
        if s.get("build_type"):
            existing_non_landable[s["name"]] = s

    # Process stations list - classify by build_type
    for s in existing_dossier.get("stations", []):
        if not s.get("build_type"):
            continue
        name = s["name"]
        if is_landable_build_type(s["build_type"]):
            existing_landable[name] = s
        else:
            existing_non_landable[name] = s

    new_landable_map = {s.name: s for s in new_facts.landable_stations}
    new_non_landable_map = {s.name: s for s in new_facts.non_landable_sites}

    diff = FactsDiff(
        system_name=new_facts.system_name,
        old_revision=old_revision,
        new_revision=new_revision,
        raven_revision_delta=new_revision - old_revision,
    )

    # New landable stations
    for name, station in new_landable_map.items():
        if name not in existing_landable:
            diff.new_landable_stations.append(station)

    # Lost landable stations
    for name, station_data in existing_landable.items():
        if name not in new_landable_map:
            diff.lost_landable_stations.append(_lost_site(name, station_data, landable=True))

    # Renamed stations (same build_type+body, different name)
    # This is a heuristic: match by build_type and body
    for new_name, new_station in new_landable_map.items():
        for old_name, old_station in existing_landable.items():
            if (old_name != new_name and
                old_station.get("build_type") == new_station.build_type and
                old_station.get("body") == new_station.body):
                diff.renamed_stations.append(RenamedStation(
                    old_name=old_name,
                    new_name=new_name,
                    build_type=new_station.build_type,
                ))
                # Remove from new/lost since it's a rename
                if new_station in diff.new_landable_stations:
                    diff.new_landable_stations.remove(new_station)
                # Find and remove from lost
                for lost in diff.lost_landable_stations:
                    if lost.name == old_name:
                        diff.lost_landable_stations.remove(lost)
                        break
                break

    # Build type changes (same name, different build_type)
    for name, new_station in new_landable_map.items():
        if name in existing_landable:
            old_bt = existing_landable[name].get("build_type")
            if old_bt and old_bt != new_station.build_type:
                diff.build_type_changes.append(BuildTypeChange(
                    name=name,
                    old_build_type=old_bt,
                    new_build_type=new_station.build_type,
                ))

    # Status changes (same name, different status)
    for name, new_station in new_landable_map.items():
        if name in existing_landable:
            old_status = existing_landable[name].get("status")
            if old_status and old_status != new_station.status:
                diff.status_changes.append(StatusChange(
                    name=name,
                    old_status=old_status,
                    new_status=new_station.status,
                    build_type=new_station.build_type,
                ))

    # Non-landable sites: new
    for name, site in new_non_landable_map.items():
        if name not in existing_non_landable:
            diff.new_non_landable_sites.append(site)

    # Non-landable sites: lost
    for name, site_data in existing_non_landable.items():
        if name not in new_non_landable_map:
            diff.lost_non_landable_sites.append(_lost_site(name, site_data, landable=False))

    # Journal-only stations
    diff.journal_only_stations = new_facts.journal_only_stations.copy()

    # Inara discrepancies (compare key fields)
    if new_facts.inara_system and existing_dossier.get("inara"):
        diff.inara_discrepancies.extend(_compare_fields(
            existing_dossier["inara"],
            new_facts.inara_system,
            _COMMON_SYSTEM_FIELDS,
            source="inara",
        ))

    # Spansh discrepancies
    if new_facts.spansh_system and existing_dossier.get("spansh"):
        diff.spansh_discrepancies.extend(_compare_fields(
            existing_dossier["spansh"],
            new_facts.spansh_system,
            _COMMON_SYSTEM_FIELDS + _SPANSH_ONLY_FIELDS,
            source="spansh",
        ))

    # Conflicts from new_facts
    diff.conflicts = new_facts.conflicts.copy()

    return diff


# The fields both API sources report identically; Spansh adds one of its own.
_COMMON_SYSTEM_FIELDS = (
    ("population", "population"),
    ("government", "government"),
    ("allegiance", "allegiance"),
    ("state", "state"),
    ("security", "security"),
    ("primary_economy", "primary_economy"),
)
_SPANSH_ONLY_FIELDS = (("controlling_minor_faction", "controlling_minor_faction"),)


def _compare_fields(
    existing: dict,
    new: object,
    fields: tuple[tuple[str, str], ...],
    source: str,
) -> list[SourceAttribution]:
    """Record where one API source now disagrees with the saved dossier."""
    discrepancies: list[SourceAttribution] = []
    for old_key, new_attr in fields:
        old_val = existing.get(old_key)
        new_val = getattr(new, new_attr, None)
        if old_val is not None and new_val is not None and str(old_val) != str(new_val):
            discrepancies.append(SourceAttribution(
                field=old_key,
                value=str(new_val),
                sources=[source],
                conflict=True,
                details=f"Changed from {old_val} to {new_val}",
            ))
    return discrepancies


@overload
def _lost_site(name: str, data: dict, *, landable: Literal[True]) -> LandableStation: ...


@overload
def _lost_site(name: str, data: dict, *, landable: Literal[False]) -> NonLandableSite: ...


def _lost_site(name: str, data: dict, *, landable: bool) -> Site:
    """Reconstruct a site that the saved dossier listed and the plan no longer does."""
    build_type = data.get("build_type", "unknown")
    return _site_record(
        name=name,
        build_type=build_type,
        facility_class=get_facility_class(build_type),
        facility_name=get_facility_name(build_type),
        body=data.get("body", "Unknown"),
        status=data.get("status", "unknown"),
        source="dossier",
        placement=get_placement(build_type),
        landable=landable,
    )


__all__ = [
    "SystemFacts",
    "Site",
    "LandableStation",
    "NonLandableSite",
    "JournalOnlyStation",
    "SourceAttribution",
    "FactsDiff",
    "StatusChange",
    "BuildTypeChange",
    "RenamedStation",
    "gather_facts",
    "compute_facts_diff",
]