"""Four-source audit for a colonised system (Story 6.2).

Compares the aggregated :class:`~.facts.SystemFacts` from Journal, Raven
Colonial, Inara and Spansh and reports every disagreement as a structured
:class:`AuditDiscrepancy`. The comparison is pure: it performs no network or
file I/O and expects the caller to have gathered the facts already.

Severity policy:

* ``error`` - the sources disagree about whether a station has landing pads.
  This affects content policy, so it fails the audit.
* ``warning`` - a real inconsistency worth reviewing before an update: a
  source conflict, a journal-only station, a market ID disagreement, a
  station only present in Inara or Spansh, Raven being unavailable, or Raven
  returning a system record without its site list.
* ``info`` - expected or merely contextual: a Raven site the player has never
  docked at, journal stations that cannot be verified without Raven site data,
  or Inara/Spansh/Journal being unavailable or unconfigured.

``AuditReport.passed`` is false only when at least one ``error`` exists.
Raven revision and the last journal visit are top-level report fields rather
than discrepancies: they are context, not disagreements between sources.

Inara exposes no system station-list endpoint. ``gather_facts`` therefore
looks up Inara station records one candidate at a time, using names from usable
Raven sites, journal docks and Spansh stations. A system with no stations in
those sources yields an available Inara system record but zero station records;
the audit reports that honestly rather than inventing stations.

Absence claims about Raven (journal-only, Inara-only and Spansh-only stations)
are only made when Raven supplied site evidence: a successful site-list call,
or sites carried directly on ``SystemFacts``. A system record without a site
list is reported as ``raven_site_data_unavailable`` instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from edcg.common.config import Config
from edcg.facts.facts import (
    SystemFacts,
    _latest_station_per_name,
    _names_match,
)
from edcg.facts.journal import JournalStation
from edcg.facts.raven import (
    RavenSite,
    is_placeholder_name,
    is_unresolved_site,
)
from edcg.rules.engine import is_landable_build_type

SEVERITIES = ("info", "warning", "error")
SOURCES = ("journal", "raven", "inara", "spansh")


@dataclass
class AuditDiscrepancy:
    """One disagreement, or one unavailable source, found by the audit."""

    category: str
    severity: str
    message: str
    sources: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceStatus:
    """Availability and record count for one of the four sources."""

    available: bool
    records: int
    detail: str | None = None


@dataclass
class AuditReport:
    """Structured audit of one system across the four data sources."""

    system_name: str
    sources: dict[str, SourceStatus]
    discrepancies: list[AuditDiscrepancy] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    passed: bool = True
    raven_revision: int | None = None
    last_journal_visit: datetime | None = None


def build_audit_report(
    facts: SystemFacts, config: Config | None = None
) -> AuditReport:
    """Compare the four sources already gathered into ``facts``.

    Args:
        facts: Aggregated system facts, normally produced by ``gather_facts``.
        config: Optional configuration, used only to explain *why* Inara or
            Spansh has no data (missing key, disabled, or empty response).

    Returns:
        An :class:`AuditReport`; no I/O is performed.
    """
    journal_stations = _journal_stations(facts)
    raven_records = _raven_records(facts)
    # Absence from Raven may only be claimed when Raven actually supplied site
    # data. Directly constructed facts with sites count too, even if the flag
    # was not set.
    raven_site_evidence = (
        facts.raven_sites_loaded
        or bool(facts.raven_sites)
        or bool(facts.landable_stations)
        or bool(facts.non_landable_sites)
    )
    sources = _source_statuses(facts, config, journal_stations, raven_records)

    discrepancies: list[AuditDiscrepancy] = []

    # 1. Conflicts already detected while aggregating the facts.
    for conflict in facts.conflicts:
        discrepancies.append(
            AuditDiscrepancy(
                category="source_conflict",
                severity="warning",
                message=conflict.details
                or f"Sources disagree on {conflict.field}: {conflict.value}",
                sources=list(conflict.sources),
                details={"field": conflict.field, "value": conflict.value},
            )
        )

    # 2. Docked in the journal but absent from Raven. Without Raven site
    # evidence this cannot be asserted; report the journal records as
    # unverified instead.
    if raven_site_evidence:
        for journal_only in facts.journal_only_stations:
            discrepancies.append(
                AuditDiscrepancy(
                    category="journal_only_station",
                    severity="warning",
                    message=(
                        f"Journal station '{journal_only.name}' is missing from Raven."
                    ),
                    sources=["journal", "raven"],
                    details={
                        "station": journal_only.name,
                        "system": journal_only.system,
                        "timestamp": journal_only.timestamp.isoformat(),
                        "market_id": journal_only.market_id,
                    },
                )
            )
    else:
        unverified_names = [station.name for station in journal_stations]
        if not unverified_names:
            unverified_names = [
                station.name for station in facts.journal_only_stations
            ]
        if unverified_names:
            discrepancies.append(
                AuditDiscrepancy(
                    category="journal_station_unverified",
                    severity="info",
                    message=(
                        "Journal stations cannot be checked against Raven because "
                        "Raven supplied no site list."
                    ),
                    sources=["journal", "raven"],
                    details={"stations": unverified_names},
                )
            )

    # 2b. A system record without a site list is not evidence that any station
    # is absent from Raven; say so instead of silently treating it as empty.
    if facts.raven_system is not None and not raven_site_evidence:
        discrepancies.append(
            AuditDiscrepancy(
                category="raven_site_data_unavailable",
                severity="warning",
                message=(
                    "Raven returned a system record but no site list; station "
                    "absence from Raven cannot be determined."
                ),
                sources=["raven"],
                details={
                    "system": facts.raven_system.name,
                    "revision": facts.raven_system.revision,
                },
            )
        )

    # 3. A Raven site the player has not docked at. This is expected for a
    # site they have never visited, so it is informational. Without journal
    # data the absence means nothing, so it is suppressed entirely.
    if facts.journal_data is not None:
        journal_names = [station.name for station in journal_stations]
        for record in raven_records:
            if not any(_names_match(record["name"], name) for name in journal_names):
                discrepancies.append(
                    AuditDiscrepancy(
                        category="raven_site_not_in_journal",
                        severity="info",
                        message=(
                            f"Raven site '{record['name']}' has no matching journal "
                            "dock record."
                        ),
                        sources=["raven", "journal"],
                        details={
                            "station": record["name"],
                            "build_type": record["build_type"],
                            "body": record["body"],
                            "status": record["status"],
                        },
                    )
                )

    # 4. Journal and Spansh report different market IDs for the same station.
    for journal_station in journal_stations:
        if journal_station.market_id is None:
            continue
        for spansh_station in facts.spansh_stations:
            if spansh_station.market_id is None:
                continue
            if _names_match(journal_station.name, spansh_station.name) and (
                journal_station.market_id != spansh_station.market_id
            ):
                discrepancies.append(
                    AuditDiscrepancy(
                        category="market_id_mismatch",
                        severity="warning",
                        message=(
                            f"Market ID for '{journal_station.name}' is "
                            f"{journal_station.market_id} in the journal but "
                            f"{spansh_station.market_id} in Spansh."
                        ),
                        sources=["journal", "spansh"],
                        details={
                            "station": journal_station.name,
                            "journal_market_id": journal_station.market_id,
                            "spansh_market_id": spansh_station.market_id,
                        },
                    )
                )

    # 5. Raven and Spansh disagree about whether a site has landing pads.
    for record in raven_records:
        raven_landable = is_landable_build_type(record["build_type"])
        for spansh_station in facts.spansh_stations:
            if not _names_match(record["name"], spansh_station.name):
                continue
            spansh_pads = {
                "large": spansh_station.large_pads,
                "medium": spansh_station.medium_pads,
                "small": spansh_station.small_pads,
            }
            spansh_landable = any(count > 0 for count in spansh_pads.values())
            if raven_landable != spansh_landable:
                discrepancies.append(
                    AuditDiscrepancy(
                        category="landability_mismatch",
                        severity="error",
                        message=(
                            f"Raven says '{record['name']}' is "
                            f"{'landable' if raven_landable else 'not landable'}, "
                            f"but Spansh reports "
                            f"{'landing pads' if spansh_landable else 'no landing pads'}."
                        ),
                        sources=["raven", "spansh"],
                        details={
                            "station": record["name"],
                            "raven_build_type": record["build_type"],
                            "raven_landable": raven_landable,
                            "spansh_type": spansh_station.type,
                            "spansh_landable": spansh_landable,
                            "spansh_pads": spansh_pads,
                        },
                    )
                )

    # 6. Stations present in Inara or Spansh but not in Raven. Only emit these
    # when the non-Raven source returned station records *and* Raven supplied
    # site evidence to compare them against.
    raven_names = [record["name"] for record in raven_records]

    if raven_site_evidence and facts.inara_stations:
        for inara_station in facts.inara_stations:
            if not any(_names_match(inara_station.name, name) for name in raven_names):
                discrepancies.append(
                    AuditDiscrepancy(
                        category="inara_only_station",
                        severity="warning",
                        message=f"Inara station '{inara_station.name}' is not in Raven.",
                        sources=["inara", "raven"],
                        details={
                            "station": inara_station.name,
                            "inara_type": inara_station.type,
                        },
                    )
                )

    if raven_site_evidence and facts.spansh_stations:
        for spansh_station in facts.spansh_stations:
            if not any(_names_match(spansh_station.name, name) for name in raven_names):
                discrepancies.append(
                    AuditDiscrepancy(
                        category="spansh_only_station",
                        severity="warning",
                        message=f"Spansh station '{spansh_station.name}' is not in Raven.",
                        sources=["spansh", "raven"],
                        details={
                            "station": spansh_station.name,
                            "spansh_type": spansh_station.type,
                            "market_id": spansh_station.market_id,
                        },
                    )
                )

    # 7. One item per source that supplied no data at all.
    for name in SOURCES:
        status = sources[name]
        if status.available:
            continue
        discrepancies.append(
            AuditDiscrepancy(
                category="source_unavailable",
                severity=_unavailable_severity(name),
                message=f"Source '{name}' is unavailable: {status.detail}",
                sources=[name],
                details={"source": name, "reason": status.detail},
            )
        )

    counts = _counts(discrepancies)
    return AuditReport(
        system_name=facts.system_name,
        sources=sources,
        discrepancies=discrepancies,
        counts=counts,
        passed=counts["error"] == 0,
        raven_revision=facts.raven_system.revision if facts.raven_system else None,
        last_journal_visit=_last_visit(journal_stations),
    )


def _journal_stations(facts: SystemFacts) -> list[JournalStation]:
    """Return journal dock records for this system, latest per station."""
    if facts.journal_data is None:
        return []
    system_stations = [
        station
        for station in facts.journal_data.docked_stations
        if _names_match(station.system, facts.system_name)
    ]
    return _latest_station_per_name(system_stations)


def _raven_records(facts: SystemFacts) -> list[dict[str, Any]]:
    """Return usable Raven sites (skipping placeholders and unresolved rows).

    ``gather_facts`` also flattens Raven sites into ``landable_stations`` and
    ``non_landable_sites``. Those lists are used as a fallback so a directly
    constructed ``SystemFacts`` is still auditable.
    """
    records: list[dict[str, Any]] = []
    for site in facts.raven_sites:
        record = _raven_record_from_site(site, facts)
        if record is not None:
            records.append(record)

    if records:
        return records

    for station in facts.landable_stations:
        records.append(
            {
                "name": station.name,
                "build_type": station.build_type,
                "body": station.body,
                "status": station.status,
            }
        )
    for non_landable_site in facts.non_landable_sites:
        records.append(
            {
                "name": non_landable_site.name,
                "build_type": non_landable_site.build_type,
                "body": non_landable_site.body,
                "status": non_landable_site.status,
            }
        )
    return records


def _raven_record_from_site(
    site: RavenSite, facts: SystemFacts
) -> dict[str, Any] | None:
    """Convert one Raven site to an audit record, or skip it if unusable."""
    if site.name is None:
        return None
    if is_placeholder_name(site.name) or is_unresolved_site(site):
        return None

    body = "Unknown"
    if facts.raven_system:
        body = facts.raven_system.body_name(site.body_num)

    return {
        "name": site.name,
        "build_type": site.build_type or "",
        "body": body,
        "status": site.status,
    }


def _source_statuses(
    facts: SystemFacts,
    config: Config | None,
    journal_stations: list[JournalStation],
    raven_records: list[dict[str, Any]],
) -> dict[str, SourceStatus]:
    """Build the availability and record-count block for all four sources."""
    raven_available = facts.raven_system is not None or bool(raven_records)
    journal_available = facts.journal_data is not None
    inara_available = facts.inara_system is not None or bool(facts.inara_stations)
    spansh_available = facts.spansh_system is not None or bool(facts.spansh_stations)

    return {
        "journal": SourceStatus(
            available=journal_available,
            records=len(journal_stations),
            detail=(
                f"{len(journal_stations)} docked station(s) recorded for this system."
                if journal_available
                else "No journal data found (journal directory missing or unreadable)."
            ),
        ),
        "raven": SourceStatus(
            available=raven_available,
            records=len(raven_records),
            detail=(
                f"Raven system record at revision "
                f"{facts.raven_system.revision if facts.raven_system else 'unknown'}."
                if raven_available
                else "Raven returned no system record (request failed or system not found)."
            ),
        ),
        "inara": SourceStatus(
            available=inara_available,
            records=len(facts.inara_stations),
            detail=(
                f"{len(facts.inara_stations)} station record(s)."
                if inara_available
                else _inara_unavailable_detail(config)
            ),
        ),
        "spansh": SourceStatus(
            available=spansh_available,
            records=len(facts.spansh_stations),
            detail=(
                f"{len(facts.spansh_stations)} station record(s)."
                if spansh_available
                else _spansh_unavailable_detail(config)
            ),
        ),
    }


def _inara_unavailable_detail(config: Config | None) -> str:
    """Explain why Inara supplied no data."""
    if config is None:
        return "Inara data was not gathered (no API key configured or the request failed)."
    if not config.inara_api_key:
        return "Inara API key is not configured."
    return "Inara returned no system record for this system."


def _spansh_unavailable_detail(config: Config | None) -> str:
    """Explain why Spansh supplied no data."""
    if config is None:
        return "Spansh data was not gathered (disabled or the request failed)."
    if not config.spansh_enabled:
        return "Spansh is disabled in configuration."
    return "Spansh returned no system record for this system."


def _unavailable_severity(source: str) -> str:
    """Raven is the primary plan, so its absence is a warning, not just info."""
    return "warning" if source == "raven" else "info"


def _last_visit(journal_stations: list[JournalStation]) -> datetime | None:
    """Return the most recent dock timestamp in this system."""
    if not journal_stations:
        return None
    return max(station.timestamp for station in journal_stations)


def _counts(discrepancies: list[AuditDiscrepancy]) -> dict[str, int]:
    """Count discrepancies by severity and by category."""
    counts = {"total": len(discrepancies), "info": 0, "warning": 0, "error": 0}
    for item in discrepancies:
        counts[item.severity] += 1
        counts[item.category] = counts.get(item.category, 0) + 1
    return counts


__all__ = [
    "AuditDiscrepancy",
    "AuditReport",
    "SourceStatus",
    "build_audit_report",
]
