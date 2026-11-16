"""Tests for the four-source audit report (Story 6.2).

The core audit is pure: it receives an already-gathered ``SystemFacts`` and
compares Journal, Raven Colonial, Inara and Spansh without any I/O. The report
is built and serialised directly here; no wrapper gathers facts.

No network, no real journal and no real EDCoPilot folder are touched.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from types import SimpleNamespace

from edcg.cli import _json_default

from edcg.repo.audit import (
    AuditDiscrepancy,
    AuditReport,
    SourceStatus,
    build_audit_report,
)
from edcg.facts.facts import (
    JournalOnlyStation,
    SourceAttribution,
    SystemFacts,
)
from edcg.facts.journal import JournalStation
from facts_builders import (
    DT,
    inara_station,
    inara_system,
    journal_data,
    journal_station,
    landable_station,
    raven_site,
    raven_system,
    spansh_station,
    spansh_system,
)


# ---------------------------------------------------------------------------
# Fact builders
# ---------------------------------------------------------------------------
# The shared constructors live in tests/facts_builders.py; the audit-specific
# helpers stay here.


def categories(report: AuditReport) -> set[str]:
    return {item.category for item in report.discrepancies}


def only(report: AuditReport, category: str) -> list[AuditDiscrepancy]:
    return [item for item in report.discrepancies if item.category == category]


def empty_config(*, inara_api_key: str | None = None, spansh_enabled: bool = False):
    return SimpleNamespace(inara_api_key=inara_api_key, spansh_enabled=spansh_enabled)


# ---------------------------------------------------------------------------
# Clean report
# ---------------------------------------------------------------------------


def test_clean_report_has_no_discrepancies_and_passes() -> None:
    station = spansh_station()
    facts = SystemFacts(
        system_name="Alpha",
        raven_system=raven_system(revision=7),
        raven_sites=[raven_site()],
        journal_data=journal_data([journal_station()]),
        inara_system=inara_system(),
        spansh_system=spansh_system([station]),
        spansh_stations=[station],
        landable_stations=[landable_station()],
    )

    report = build_audit_report(facts, empty_config(inara_api_key="key", spansh_enabled=True))

    assert isinstance(report, AuditReport)
    assert report.system_name == "Alpha"
    assert report.discrepancies == []
    assert report.passed is True
    assert report.counts["error"] == 0
    assert set(report.sources) == {"journal", "raven", "inara", "spansh"}
    assert all(status.available for status in report.sources.values())
    assert report.sources["raven"].records == 1
    assert report.sources["journal"].records == 1
    assert report.sources["spansh"].records == 1
    # Raven revision and last journal visit are top-level report fields.
    assert report.raven_revision == 7
    assert report.last_journal_visit == DT


# ---------------------------------------------------------------------------
# Category 1: source_conflict (from facts.conflicts)
# ---------------------------------------------------------------------------


def test_source_conflict_is_reported_from_facts_conflicts() -> None:
    facts = SystemFacts(
        system_name="Alpha",
        raven_system=raven_system(),
        raven_sites=[raven_site("Raven Only")],
        journal_data=journal_data([journal_station("Journal Only")]),
        conflicts=[
            SourceAttribution(
                field="station_name",
                value="Raven Only",
                sources=["raven", "journal"],
                conflict=True,
                details="Name mismatch: Raven='Raven Only', Journal='Journal Only'",
            )
        ],
    )

    report = build_audit_report(facts)
    [item] = only(report, "source_conflict")

    assert item.severity == "warning"
    assert item.sources == ["raven", "journal"]
    assert item.details["field"] == "station_name"
    assert "Name mismatch" in item.message
    assert report.passed is True


# ---------------------------------------------------------------------------
# Category 2: journal_only_station
# ---------------------------------------------------------------------------


def test_journal_only_station_is_a_warning() -> None:
    facts = SystemFacts(
        system_name="Alpha",
        raven_system=raven_system(),
        raven_sites=[raven_site()],
        journal_data=journal_data([journal_station("Unplanned Station")]),
        journal_only_stations=[
            JournalOnlyStation(
                name="Unplanned Station",
                system="Alpha",
                timestamp=DT,
                market_id=999,
            )
        ],
    )

    report = build_audit_report(facts)
    [item] = only(report, "journal_only_station")

    assert item.severity == "warning"
    assert item.sources == ["journal", "raven"]
    assert item.details["station"] == "Unplanned Station"
    assert item.details["market_id"] == 999
    assert item.details["timestamp"] == DT.isoformat()
    assert report.passed is True


def test_raven_down_does_not_claim_journal_station_is_missing() -> None:
    """Without any Raven evidence, absence from Raven cannot be asserted."""
    spansh_only = spansh_station("Spansh Only", market_id=333)
    facts = SystemFacts(
        system_name="Alpha",
        journal_data=journal_data([journal_station("Unverified Station")]),
        journal_only_stations=[
            JournalOnlyStation(
                name="Unverified Station",
                system="Alpha",
                timestamp=DT,
                market_id=999,
            )
        ],
        inara_system=inara_system(),
        inara_stations=[inara_station("Inara Only")],
        spansh_system=spansh_system([spansh_only]),
        spansh_stations=[spansh_only],
    )

    report = build_audit_report(
        facts, empty_config(inara_api_key="key", spansh_enabled=True)
    )

    found = categories(report)
    assert "journal_only_station" not in found
    assert "inara_only_station" not in found
    assert "spansh_only_station" not in found
    assert "raven_site_data_unavailable" not in found
    assert report.sources["raven"].available is False

    [unverified] = only(report, "journal_station_unverified")
    assert unverified.severity == "info"
    assert unverified.sources == ["journal", "raven"]
    assert unverified.details["stations"] == ["Unverified Station"]
    assert report.passed is True


def test_raven_site_list_failure_is_reported_and_blocks_absence_claims() -> None:
    """A system record without a site list is not evidence that a station is absent."""
    spansh_only = spansh_station("Spansh Only", market_id=333)
    facts = SystemFacts(
        system_name="Alpha",
        raven_system=raven_system(),  # get_sites() failed, so this is all Raven returned.
        journal_data=journal_data([journal_station("Unverified Station")]),
        journal_only_stations=[
            JournalOnlyStation(
                name="Unverified Station",
                system="Alpha",
                timestamp=DT,
                market_id=999,
            )
        ],
        inara_system=inara_system(),
        inara_stations=[inara_station("Inara Only")],
        spansh_system=spansh_system([spansh_only]),
        spansh_stations=[spansh_only],
    )

    report = build_audit_report(
        facts, empty_config(inara_api_key="key", spansh_enabled=True)
    )

    found = categories(report)
    assert "journal_only_station" not in found
    assert "inara_only_station" not in found
    assert "spansh_only_station" not in found
    assert report.sources["raven"].available is True

    [site_data] = only(report, "raven_site_data_unavailable")
    assert site_data.severity == "warning"
    assert site_data.sources == ["raven"]
    assert site_data.details["revision"] == 7

    [unverified] = only(report, "journal_station_unverified")
    assert unverified.severity == "info"
    assert report.passed is True


# ---------------------------------------------------------------------------
# Category 3: raven_site_not_in_journal (informational)
# ---------------------------------------------------------------------------


def test_raven_site_without_journal_dock_is_informational() -> None:
    facts = SystemFacts(
        system_name="Alpha",
        raven_system=raven_system(),
        raven_sites=[raven_site("Unvisited Station")],
        journal_data=journal_data([]),
    )

    report = build_audit_report(facts)
    [item] = only(report, "raven_site_not_in_journal")

    assert item.severity == "info"
    assert item.sources == ["raven", "journal"]
    assert item.details["station"] == "Unvisited Station"
    assert report.passed is True


def test_raven_site_not_in_journal_is_suppressed_without_journal_data() -> None:
    facts = SystemFacts(
        system_name="Alpha",
        raven_system=raven_system(),
        raven_sites=[raven_site("Unvisited Station")],
    )

    report = build_audit_report(facts)

    assert "raven_site_not_in_journal" not in categories(report)


# ---------------------------------------------------------------------------
# Category 4: market_id_mismatch
# ---------------------------------------------------------------------------


def test_market_id_mismatch_between_journal_and_spansh() -> None:
    station = spansh_station("Alpha Station", market_id=222)
    facts = SystemFacts(
        system_name="Alpha",
        raven_system=raven_system(),
        raven_sites=[raven_site()],
        journal_data=journal_data([journal_station(market_id=111)]),
        spansh_system=spansh_system([station]),
        spansh_stations=[station],
    )

    report = build_audit_report(facts)
    [item] = only(report, "market_id_mismatch")

    assert item.severity == "warning"
    assert item.sources == ["journal", "spansh"]
    assert item.details["station"] == "Alpha Station"
    assert item.details["journal_market_id"] == 111
    assert item.details["spansh_market_id"] == 222
    assert report.passed is True


def test_repeated_journal_docks_do_not_duplicate_findings() -> None:
    """Repeated dock events collapse before comparison and counting."""
    t1 = datetime(2026, 10, 18, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
    t3 = datetime(2026, 10, 18, 11, 0, tzinfo=UTC)
    station = spansh_station("Alpha Station", market_id=999)
    facts = SystemFacts(
        system_name="Alpha",
        raven_system=raven_system(),
        raven_sites=[
            raven_site("Alpha Station"),
            raven_site("Beta Station", site_id=2),
        ],
        journal_data=journal_data(
            [
                JournalStation(name="Alpha Station", system="Alpha", timestamp=t1, market_id=111),
                JournalStation(name="Alpha Station", system="Alpha", timestamp=t2, market_id=222),
                JournalStation(name="Beta Station", system="Alpha", timestamp=t3, market_id=333),
            ]
        ),
        spansh_system=spansh_system([station]),
        spansh_stations=[station],
    )

    report = build_audit_report(facts)

    [mismatch] = only(report, "market_id_mismatch")
    assert mismatch.details["journal_market_id"] == 222
    assert report.sources["journal"].records == 2
    assert report.last_journal_visit == t2
    assert "journal_only_station" not in categories(report)
    assert "journal_station_unverified" not in categories(report)


# ---------------------------------------------------------------------------
# Category 5: landability_mismatch (the error that fails an audit)
# ---------------------------------------------------------------------------


def test_landability_mismatch_between_raven_and_spansh_is_an_error() -> None:
    station = spansh_station("Alpha Station", large_pads=0, medium_pads=0, small_pads=0)
    facts = SystemFacts(
        system_name="Alpha",
        raven_system=raven_system(),
        raven_sites=[raven_site()],  # 'nona' is a landable outpost.
        journal_data=journal_data([journal_station()]),
        spansh_system=spansh_system([station]),
        spansh_stations=[station],
    )

    report = build_audit_report(facts)
    [item] = only(report, "landability_mismatch")

    assert item.severity == "error"
    assert item.sources == ["raven", "spansh"]
    assert item.details["raven_landable"] is True
    assert item.details["spansh_landable"] is False
    assert item.details["spansh_pads"] == {"large": 0, "medium": 0, "small": 0}
    assert report.passed is False
    assert report.counts["error"] == 1


# ---------------------------------------------------------------------------
# Category 6: inara_only_station / spansh_only_station
# ---------------------------------------------------------------------------


def test_stations_only_in_inara_or_spansh_are_warnings() -> None:
    spansh_only = spansh_station("Spansh Only", market_id=333)
    facts = SystemFacts(
        system_name="Alpha",
        raven_system=raven_system(),
        raven_sites=[raven_site()],
        inara_system=inara_system(),
        inara_stations=[inara_station("Inara Only")],
        spansh_system=spansh_system([spansh_only]),
        spansh_stations=[spansh_only],
    )

    report = build_audit_report(
        facts, empty_config(inara_api_key="key", spansh_enabled=True)
    )

    [inara_item] = only(report, "inara_only_station")
    [spansh_item] = only(report, "spansh_only_station")

    assert inara_item.severity == "warning"
    assert inara_item.details["station"] == "Inara Only"
    assert spansh_item.severity == "warning"
    assert spansh_item.details["station"] == "Spansh Only"
    assert report.passed is True


def test_no_only_in_source_warnings_when_that_source_has_no_records() -> None:
    facts = SystemFacts(
        system_name="Alpha",
        raven_system=raven_system(),
        raven_sites=[raven_site()],
        inara_system=inara_system(),
        spansh_system=spansh_system([]),
        spansh_stations=[],
    )

    report = build_audit_report(facts)

    assert "inara_only_station" not in categories(report)
    assert "spansh_only_station" not in categories(report)


# ---------------------------------------------------------------------------
# Category 7: source_unavailable
# ---------------------------------------------------------------------------


def test_all_sources_unavailable_is_reported_without_errors() -> None:
    facts = SystemFacts(system_name="Alpha")

    report = build_audit_report(
        facts, empty_config(inara_api_key=None, spansh_enabled=False)
    )

    unavailable = only(report, "source_unavailable")
    assert {item.sources[0] for item in unavailable} == {
        "journal",
        "raven",
        "inara",
        "spansh",
    }
    assert all(status.available is False for status in report.sources.values())
    assert all(status.records == 0 for status in report.sources.values())

    reasons = {item.details["source"]: item.details["reason"] for item in unavailable}
    assert "Raven" in reasons["raven"]
    assert "journal" in reasons["journal"].lower()
    assert "not configured" in reasons["inara"].lower()
    assert "disabled" in reasons["spansh"].lower()

    raven_item = next(item for item in unavailable if item.details["source"] == "raven")
    assert raven_item.severity == "warning"
    assert report.passed is True
    assert report.counts["error"] == 0


def test_configured_but_empty_sources_explain_that_they_returned_nothing() -> None:
    facts = SystemFacts(system_name="Alpha")

    report = build_audit_report(
        facts, empty_config(inara_api_key="key", spansh_enabled=True)
    )

    reasons = {
        item.details["source"]: item.details["reason"]
        for item in only(report, "source_unavailable")
    }
    assert "returned no" in reasons["inara"].lower()
    assert "returned no" in reasons["spansh"].lower()


# ---------------------------------------------------------------------------
# Report serialisation
# ---------------------------------------------------------------------------


def test_audit_report_returns_json_serializable_report() -> None:
    """The built report serialises to the shape the workflow used to return."""
    facts = SystemFacts(
        system_name="Alpha",
        raven_system=raven_system(revision=7),
        raven_sites=[raven_site()],
        journal_data=journal_data([journal_station()]),
        inara_system=inara_system(),
        spansh_system=spansh_system([spansh_station()]),
        spansh_stations=[spansh_station()],
    )
    config = empty_config(inara_api_key="key", spansh_enabled=True)

    report = build_audit_report(facts, config)
    data = json.loads(json.dumps(asdict(report), default=_json_default))

    assert json.loads(json.dumps(data)) == data
    assert {
        "system_name",
        "sources",
        "discrepancies",
        "counts",
        "passed",
        "raven_revision",
        "last_journal_visit",
    } <= set(data)
    assert data["system_name"] == "Alpha"
    assert set(data["sources"]) == {"journal", "raven", "inara", "spansh"}
    assert data["sources"]["raven"]["available"] is True
    assert data["sources"]["raven"]["records"] == 1
    assert data["discrepancies"] == []
    assert data["counts"]["error"] == 0
    assert data["passed"] is True
    assert data["raven_revision"] == 7
    assert data["last_journal_visit"] == DT.isoformat()


def test_source_status_and_report_dataclasses_have_expected_defaults() -> None:
    status = SourceStatus(available=False, records=0)
    report = AuditReport(system_name="Alpha", sources={"raven": status})

    assert status.detail is None
    assert report.discrepancies == []
    assert report.counts == {}
    assert report.passed is True
    assert report.raven_revision is None
    assert report.last_journal_visit is None


def test_audit_cli_injects_gather_facts_and_prints_the_report(
    monkeypatch, capsys, tmp_path
) -> None:
    """The CLI audit gathers once, with the loaded config, and prints JSON.

    Carries the two gather-injection assertions dropped from the Task 8 port:
    the system name reaches the gatherer, and it receives the CLI's config.
    """
    from edcg import cli

    facts = SystemFacts(
        system_name="Alpha",
        raven_system=raven_system(revision=7),
        raven_sites=[raven_site()],
        journal_data=journal_data([journal_station()]),
        inara_system=inara_system(),
        spansh_system=spansh_system([spansh_station()]),
        spansh_stations=[spansh_station()],
    )
    config = empty_config(inara_api_key="key", spansh_enabled=True)
    # The command's next-step hint looks for the system's dossier under the
    # content root, so the stub config carries the root it resolves against.
    config.content_definitions_root = tmp_path

    async def fake_gather(system_name: str, received_config):
        assert system_name == "Alpha"
        assert received_config is config
        return facts

    monkeypatch.setattr(cli, "get_config", lambda: config)
    monkeypatch.setattr(cli, "gather_facts", fake_gather)

    assert cli.main(["audit", "--system", "Alpha"]) == 0
    data = json.loads(capsys.readouterr().out)

    assert json.loads(json.dumps(data)) == data
    assert {
        "system_name",
        "sources",
        "discrepancies",
        "counts",
        "passed",
        "raven_revision",
        "last_journal_visit",
    } <= set(data)
    assert data["system_name"] == "Alpha"
    assert set(data["sources"]) == {"journal", "raven", "inara", "spansh"}
    assert data["sources"]["raven"]["available"] is True
    assert data["sources"]["raven"]["records"] == 1
    assert data["discrepancies"] == []
    assert data["counts"]["error"] == 0
    assert data["passed"] is True
    assert data["raven_revision"] == 7
    assert data["last_journal_visit"] == DT.isoformat()
