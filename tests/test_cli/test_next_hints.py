"""Tests for the ``next:`` hints printed after each command's JSON.

Hints are stderr prose on the channel doctor already uses for ``fix:`` lines,
so stdout stays the parseable data answer. The hint texts are pinned literally
because each one names the reference file the workflow has to read next.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from edcg import cli
from edcg.facts.facts import LandableStation, SystemFacts
from edcg.facts.raven import RavenSystem

# Every key the gather-facts payload carried before hints existed.
FACTS_KEYS = {
    "system_name",
    "raven_system",
    "raven_sites_loaded",
    "landable_stations",
    "non_landable_sites",
    "journal_only_stations",
    "station_bodies",
    "station_bodies_omitted",
    "conflicts",
}

# Every key the audit payload carried before hints existed.
AUDIT_KEYS = {
    "system_name",
    "sources",
    "discrepancies",
    "counts",
    "passed",
    "raven_revision",
    "last_journal_visit",
}


@pytest.fixture(autouse=True)
def _isolated(clean_env):
    """Run every test from an empty cwd with no configured roots."""
    return clean_env


def _raven_facts() -> SystemFacts:
    return SystemFacts(
        system_name="Test System",
        raven_system=RavenSystem(
            name="Test System", architect="A", revision=42, bodies=["3 a"]
        ),
        raven_sites_loaded=True,
        landable_stations=[
            LandableStation(
                name="Test Station",
                build_type="nona",
                facility_class="outpost",
                facility_name="Civilian Surface Outpost",
                body="3 a",
                status="complete",
                source="raven",
                placement="surface",
            )
        ],
    )


def _patch_gather(monkeypatch, facts: SystemFacts) -> None:
    async def fake_gather(system_name, config, **kwargs):
        assert system_name == "Test System"
        return facts

    monkeypatch.setattr(cli, "gather_facts", fake_gather)


def test_init_success_prints_the_house_rules_hint(capsys):
    assert cli.main(["init", "--no-git"]) == 0

    captured = capsys.readouterr()
    assert captured.err == (
        "next: adopt the house rules (SKILL.md Setup step 3) - copy "
        "assets/all.rules.toml.example to systems/all.rules.toml and review each "
        "section with the user, then gather facts for the system\n"
    )
    data = json.loads(captured.out)
    assert set(data) == {"content_root", "state", "created", "git"}
    assert data["state"] == "blank"


def test_gather_facts_with_a_raven_entry_prints_the_interview_with_facts_hint(
    monkeypatch, capsys
):
    _patch_gather(monkeypatch, _raven_facts())

    assert cli.main(["gather-facts", "--system", "Test System"]) == 0

    captured = capsys.readouterr()
    assert captured.err == (
        "next: interview with these Raven facts - read "
        "references/new-system-interview.md Phase 1 (high-level concept); "
        "do not re-ask what Raven answered\n"
    )
    data = json.loads(captured.out)
    assert set(data) == FACTS_KEYS
    assert data["system_name"] == "Test System"
    assert data["raven_system"]["revision"] == 42


def test_gather_facts_without_a_raven_entry_prints_the_description_hint(
    monkeypatch, capsys
):
    _patch_gather(monkeypatch, SystemFacts(system_name="Test System"))

    assert cli.main(["gather-facts", "--system", "Test System"]) == 0

    captured = capsys.readouterr()
    assert captured.err == (
        "next: no Raven entry - start the interview from the user's description; "
        "read references/new-system-interview.md Phase 1 (high-level concept)\n"
    )
    data = json.loads(captured.out)
    assert set(data) == FACTS_KEYS
    assert data["raven_system"] is None
    assert data["raven_sites_loaded"] is False


def test_audit_with_a_definition_prints_the_update_interview_hint(
    monkeypatch, tmp_path, capsys
):
    systems = Path(tmp_path) / "systems"
    systems.mkdir()
    (systems / "test-system.md").write_text(
        "# Test System — system dossier\n", encoding="utf-8"
    )
    (systems / "test-system.rules.toml").write_text(
        '[system]\nnames = ["Test System"]\n', encoding="utf-8"
    )
    _patch_gather(monkeypatch, SystemFacts(system_name="Test System"))

    assert cli.main(["audit", "--system", "Test System"]) == 0

    captured = capsys.readouterr()
    assert captured.err == (
        "next: this system has a definition - read references/update-interview.md "
        "and run the seven phases\n"
    )
    data = json.loads(captured.out)
    assert set(data) == AUDIT_KEYS
    assert data["system_name"] == "Test System"


def test_audit_without_a_definition_prints_the_new_system_interview_hint(
    monkeypatch, capsys
):
    _patch_gather(monkeypatch, SystemFacts(system_name="Test System"))

    assert cli.main(["audit", "--system", "Test System"]) == 0

    captured = capsys.readouterr()
    assert captured.err == (
        "next: this system has no definition - read "
        "references/new-system-interview.md and run the six phases\n"
    )
    data = json.loads(captured.out)
    assert set(data) == AUDIT_KEYS
    assert data["system_name"] == "Test System"
