"""Tests for CLI dispatch, exit codes and JSON output.

Commands are exercised in-process so failures point at the handler rather than
at a subprocess exit status. Only the entry point itself is run as a subprocess,
to prove the launcher works from a shell.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from edcg import __version__, cli
from edcg.content.custom_file import CUSTOM_FILE_NAME, VERSION
from edcg.facts.facts import LandableStation, SystemFacts
from edcg.facts.raven import RavenSystem

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "skills" / "edcopilot-system-content" / "scripts" / "edcg.py"

DOSSIER = """\
# Test System — system dossier

## 1. Identity and canon

| Fact | Value |
|---|---|
| Raven revision | 7 |
| System name | `Test System` |

## 2. Lore and theme

Test lore.

## 3. Tone rules (hard constraints)

Test tone.

## 4. Canon site table

### Complete (1)

| Site | Build type | Body |
|---|---|---|
| Test Station (ii-42) | `nona` Civilian Surface Outpost | `3 a` |

## 5. Corrections log (do not reintroduce these)

## 6. Site list maintenance

## 7. Coverage

### Stations covered

Test Station (ii-42)

## 8. Writing rules

### Voices used

- [<GarrettControl>]

## 9. Open threads (TODO)
"""

RULES = """\
[system]
names = ["Test System"]
dossier = "test-system.md"
voices = ["Foreman"]
"""

RULES_WITH_STATION_BOUNDS = """\
[system]
names = ["Test System"]
dossier = "test-system.md"
voices = ["Foreman"]

[content.bounds]
SystemGreeting = [4, 5]

[content.bounds.stations."Test Station (ii-42)"]
StationGreeting = [5, 9]
"""


def _run(argv, stdin=None):
    if stdin is None:
        return cli.main(argv)

    class _Stdin:
        def read(self):
            return stdin

    original = sys.stdin
    sys.stdin = _Stdin()
    try:
        return cli.main(argv)
    finally:
        sys.stdin = original


def _write_system(root: Path, dossier: str = DOSSIER, rules: str = RULES) -> None:
    systems = root / "systems"
    systems.mkdir(parents=True, exist_ok=True)
    (systems / "test-system.md").write_text(dossier, encoding="utf-8")
    (systems / "test-system.rules.toml").write_text(rules, encoding="utf-8")


def test_entry_point_help_lists_every_subcommand():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
    for name in (
        "doctor", "init", "gather-facts",
        "validate-definition",
        "save-definition", "writing-brief-data", "validate-content",
        "write-content", "get-content", "update-scan", "rewrite-tag", "markdb",
        "check-logs", "audit", "branch", "version",
    ):
        assert name in result.stdout


@pytest.mark.parametrize(
    "argv",
    [
        ["doctor"],
        ["init"],
        ["gather-facts"],
        ["validate-definition"],
        ["save-definition"],
        ["writing-brief-data"],
        ["validate-content"],
        ["write-content"],
        ["get-content"],
        ["update-scan"],
        ["rewrite-tag"],
        ["markdb", "add"],
        ["markdb", "remove"],
        ["check-logs"],
        ["audit"],
        ["branch", "start"],
        ["branch", "status"],
        ["branch", "review"],
        ["branch", "finalize"],
        ["branch", "abort"],
        ["version"],
    ],
)
def test_every_subcommand_resolves(argv):
    with pytest.raises(SystemExit) as raised:
        cli.main([*argv, "--help"])
    assert raised.value.code == 0


def test_unknown_command_is_a_usage_error():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "not-a-command"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 2


def test_version_prints_the_release_version(capsys):
    assert cli.main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __version__
    assert __version__ == "1.0.0"
    # The provenance string written into the custom file stays pinned to the
    # old package version and is deliberately distinct from the release.
    assert VERSION == "0.1.0"


def test_validate_definition_prints_json_and_fails_on_errors(capsys):
    payload = json.dumps(
        {"dossier": "# not a dossier\n", "rules": "not toml", "system_name": "X"}
    )
    assert _run(["validate-definition"], stdin=payload) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["passed"] is False
    assert data["findings"]
    assert "rule_table" not in data


def test_validate_content_prints_json(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    payload = json.dumps(
        {"content": "@SystemGreeting<~>Test System\nHello.\n", "system_name": "Test System"}
    )
    code = _run(["validate-content"], stdin=payload)
    data = json.loads(capsys.readouterr().out)
    assert code in (0, 1)
    assert set(data) == {"passed", "findings", "rule_summary"}


def test_missing_payload_is_a_usage_error(capsys):
    assert _run(["validate-definition"], stdin="") == 2
    assert "JSON payload" in json.loads(capsys.readouterr().out)["error"]


def test_invalid_json_is_a_usage_error(capsys):
    assert _run(["validate-definition"], stdin="{not json") == 2
    assert "invalid JSON" in json.loads(capsys.readouterr().out)["error"]


def test_payload_missing_a_required_field_is_a_usage_error(capsys):
    assert _run(["validate-definition"], stdin='{"dossier": "x"}') == 2
    assert "required field" in json.loads(capsys.readouterr().out)["error"]


def test_gather_facts_requires_a_system(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    assert cli.main(["gather-facts"]) == 2
    assert "--system" in json.loads(capsys.readouterr().out)["error"]


def test_gather_facts_emits_the_facts_payload(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    facts = SystemFacts(
        system_name="Test System",
        raven_system=RavenSystem(
            name="Test System", architect="A", revision=7, bodies=["3 a"]
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

    async def fake_gather(system_name, config, **kwargs):
        assert system_name == "Test System"
        return facts

    monkeypatch.setattr(cli, "gather_facts", fake_gather)
    assert cli.main(["gather-facts", "--system", "Test System"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["system_name"] == "Test System"
    assert data["raven_system"]["revision"] == 7
    assert data["landable_stations"][0]["name"] == "Test Station"
    assert data["conflicts"] == []


def test_writing_brief_data_emits_tag_bounds_and_voice_data(
    monkeypatch, tmp_path, capsys
):
    _write_system(tmp_path)
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    assert cli.main(["writing-brief-data", "--system", "Test System"]) == 0
    data = json.loads(capsys.readouterr().out)

    assert data["system_name"] == "Test System"
    assert data["raven_revision"] == 7
    assert data["tag_lines"]["all"] == [
        "@SystemGreeting<~>Test System",
        "@SystemBroadcast<~>Test System",
        "@StationGreeting<~>Test System<~>Test Station (ii-42)",
        "@StationChatter<~>Test System<~>Test Station (ii-42)",
        "@StationFact<~>Test System<~>Test Station (ii-42)",
    ]
    assert data["tag_lines"]["total"] == 5
    assert data["bounds"]["default"]["SystemGreeting"] == [3, 6]
    assert data["voices"]["dossier"] == ["GarrettControl"]
    assert data["voices"]["rules"] == ["Foreman"]
    assert data["voices"]["declarations"] == ["[<Foreman>]", "[<GarrettControl>]"]


def test_writing_brief_data_resolves_station_bounds_overrides(
    monkeypatch, tmp_path, capsys
):
    """A per-station override overrides the kind bound for that station only."""
    _write_system(tmp_path, rules=RULES_WITH_STATION_BOUNDS)
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))

    assert cli.main(["writing-brief-data", "--system", "Test System"]) == 0
    data = json.loads(capsys.readouterr().out)

    # The kind-level override applies to the default map.
    assert data["bounds"]["default"]["SystemGreeting"] == [4, 5]
    # Unrelated kinds keep their base bounds.
    assert data["bounds"]["default"]["StationGreeting"] == [4, 8]
    # The per-station override applies under the exact station name.
    assert data["bounds"]["stations"]["Test Station (ii-42)"]["StationGreeting"] == [
        5,
        9,
    ]
    assert data["tag_lines"]["total"] == 5


def test_writing_brief_data_fails_cleanly_for_an_unknown_system(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    assert cli.main(["writing-brief-data", "--system", "Missing"]) == 1
    assert "not found" in json.loads(capsys.readouterr().out)["error"]


def test_update_scan_emits_per_system_deltas(monkeypatch, tmp_path, capsys):
    dossier = DOSSIER.replace(
        "### Complete (1)\n\n| Site | Build type | Body |\n|---|---|---|\n"
        "| Test Station (ii-42) | `nona` Civilian Surface Outpost | `3 a` |\n",
        "",
    )
    _write_system(tmp_path, dossier=dossier)
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))

    facts = SystemFacts(
        system_name="Test System",
        raven_system=RavenSystem(
            name="Test System", architect="A", revision=9, bodies=["3 a"]
        ),
        raven_sites_loaded=True,
        landable_stations=[
            LandableStation(
                name="New Station",
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

    async def fake_gather(system_name, config, **kwargs):
        return facts

    monkeypatch.setattr(cli, "gather_facts", fake_gather)
    assert cli.main(["update-scan"]) == 0
    data = json.loads(capsys.readouterr().out)

    [entry] = data["systems"]
    assert entry["system_name"] == "Test System"
    assert entry["fact_availability"]["raven"] is True
    assert entry["fact_availability"]["journal"] is False
    assert entry["new_stations"] == ["New Station"]
    assert entry["raven_revision"] == {"old": 7, "new": 9}
    assert entry["dossier_coverage"] == []
    assert entry["has_changes"] is True


def test_get_content_emits_json(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(tmp_path / "runtime"))
    (tmp_path / "runtime").mkdir()
    assert cli.main(["get-content", "--system", "Test System"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "system_name": "Test System",
        "tags": [],
    }


def test_markdb_requires_a_payload_or_tags(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    assert _run(["markdb", "add"], stdin="") == 2
    assert "JSON payload" in json.loads(capsys.readouterr().out)["error"]


def test_markdb_without_an_action_is_a_usage_error(capsys):
    assert cli.main(["markdb"]) == 2


def test_markdb_add_marks_the_tag(monkeypatch, tmp_path, capsys):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    tag = "@SystemGreeting<~>Test System"
    (runtime / CUSTOM_FILE_NAME).write_text(
        f"{tag}\nHello.\n", encoding="utf-8"
    )
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(runtime))
    monkeypatch.setenv("EDCG_AUTO_COMMIT", "false")

    assert cli.main(["markdb", "add", "--tag", tag]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data == {"modified_tags": [tag], "commit_hashes": [None]}
    lines = (runtime / CUSTOM_FILE_NAME).read_text(encoding="utf-8").splitlines()
    assert lines[:2] == [tag, "UPDATEDB"]


def test_markdb_add_warns_on_a_tag_that_matched_nothing(
    monkeypatch, tmp_path, capsys
):
    """A mistyped tag stays a no-op, but the no-op is made observable."""
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    tag = "@SystemGreeting<~>Test System"
    typo = "@StationGreeting<~>Test System<~>Misspelt Station"
    (runtime / CUSTOM_FILE_NAME).write_text(
        f"{tag}\nHello.\n", encoding="utf-8"
    )
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(runtime))
    monkeypatch.setenv("EDCG_AUTO_COMMIT", "false")

    assert cli.main(["markdb", "add", "--tag", tag, "--tag", typo]) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["modified_tags"] == [tag]
    assert "warning" in captured.err.lower()
    assert typo in captured.err
    assert tag not in captured.err
    assert "matched no authored content" in captured.err


def test_markdb_remove_warns_on_a_tag_that_matched_nothing(
    monkeypatch, tmp_path, capsys
):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    tag = "@SystemGreeting<~>Test System"
    typo = "@StationChatter<~>Test System<~>Misspelt Station"
    (runtime / CUSTOM_FILE_NAME).write_text(
        f"{tag}\nUPDATEDB\nHello.\n", encoding="utf-8"
    )
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(runtime))
    monkeypatch.setenv("EDCG_AUTO_COMMIT", "false")

    assert cli.main(["markdb", "remove", "--tag", tag, "--tag", typo]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["modified_tags"] == [tag]
    assert typo in captured.err
    assert "matched no authored content" in captured.err


def test_markdb_remove_with_no_custom_file_fails_clearly(
    monkeypatch, tmp_path, capsys
):
    """A missing custom file causes a clear error instead of silent no-op."""
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(runtime))
    monkeypatch.setenv("EDCG_AUTO_COMMIT", "false")

    tag = "@SystemGreeting<~>Test System"
    assert cli.main(["markdb", "remove", "--tag", tag]) == 1
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert CUSTOM_FILE_NAME in data["error"]
    assert f"EDCoPilot root: {runtime}" in data["error"]


def test_markdb_add_with_no_custom_file_fails_clearly(
    monkeypatch, tmp_path, capsys
):
    """A missing custom file causes a clear error instead of silent no-op."""
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(runtime))
    monkeypatch.setenv("EDCG_AUTO_COMMIT", "false")

    tag = "@SystemGreeting<~>Test System"
    assert cli.main(["markdb", "add", "--tag", tag]) == 1
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert CUSTOM_FILE_NAME in data["error"]
    assert f"EDCoPilot root: {runtime}" in data["error"]


def test_rewrite_tag_replaces_a_line(monkeypatch, tmp_path, capsys):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    tag = "@SystemGreeting<~>Test System"
    (runtime / CUSTOM_FILE_NAME).write_text(
        f"{tag}\nHello.\n", encoding="utf-8"
    )
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(runtime))

    payload = json.dumps(
        {"system_name": "Test System", "tag": tag, "replace": {"Hello.": "Hi."}}
    )
    assert _run(["rewrite-tag"], stdin=payload) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["tag"] == tag
    assert "Hi." in (runtime / CUSTOM_FILE_NAME).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# check-logs
# ---------------------------------------------------------------------------

LOG_FAILURE = (
    "#*:00:07:46   INFO - skipping UPDATEDB for tag "
    "StationGreetingAlpha Station as station cannot be validated."
)


def _check_logs_environment(monkeypatch, tmp_path, log_text="nothing to see"):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    logs = tmp_path / "logs"
    logs.mkdir()
    custom_file = runtime / CUSTOM_FILE_NAME
    custom_file.write_text("", encoding="utf-8")

    moment = datetime.fromtimestamp(custom_file.stat().st_mtime).astimezone()
    stamp = (moment + timedelta(minutes=1)).strftime("%Y%m%d.%H%M%S")
    log_path = logs / f"EDCoPilotGUI.log.{stamp}.txt"
    log_path.write_text(log_text + "\n", encoding="utf-8")

    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(runtime))
    monkeypatch.setenv("EDCG_EDCOPILOT_LOGS_DIR", str(logs))
    return moment


def _write_system_rules(root: Path, slug: str, name: str) -> None:
    systems = root / "systems"
    systems.mkdir(parents=True, exist_ok=True)
    (systems / f"{slug}.rules.toml").write_text(
        f'[system]\nnames = ["{name}"]\ndossier = "{slug}.md"\n', encoding="utf-8"
    )


def test_check_logs_defaults_since_to_the_custom_file_mtime(
    monkeypatch, tmp_path, capsys
):
    _check_logs_environment(monkeypatch, tmp_path)

    assert cli.main(["check-logs"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["checked"] is True
    assert report["log_path"]
    assert report["since"] is not None
    assert report["ok"] is True


def test_check_logs_since_override_selects_the_log(monkeypatch, tmp_path, capsys):
    moment = _check_logs_environment(monkeypatch, tmp_path)
    since = moment - timedelta(minutes=5)

    assert cli.main(["check-logs", "--since", since.isoformat()]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["checked"] is True
    assert report["since"] == since.astimezone(timezone.utc).isoformat()


def test_check_logs_since_override_can_exclude_every_log(
    monkeypatch, tmp_path, capsys
):
    moment = _check_logs_environment(monkeypatch, tmp_path)
    future = moment + timedelta(hours=1)

    assert cli.main(["check-logs", "--since", future.isoformat()]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["checked"] is False
    assert report["ok"] is False


def test_check_logs_scopes_failures_to_the_named_system(
    monkeypatch, tmp_path, capsys
):
    moment = _check_logs_environment(
        monkeypatch, tmp_path, log_text=LOG_FAILURE
    )
    _write_system_rules(tmp_path, "alpha", "Alpha")
    _write_system_rules(tmp_path, "beta", "Beta")
    since = moment - timedelta(minutes=5)

    assert cli.main(
        ["check-logs", "--since", since.isoformat(), "--system", "Beta"]
    ) == 0
    beta = json.loads(capsys.readouterr().out)
    assert beta["system"] == "Beta"
    assert beta["failures"] == []
    assert beta["ok"] is True

    assert cli.main(
        ["check-logs", "--since", since.isoformat(), "--system", "Alpha"]
    ) == 1
    alpha = json.loads(capsys.readouterr().out)
    assert alpha["system"] == "Alpha"
    assert alpha["failures"]
    assert alpha["ok"] is False


def test_check_logs_system_stays_unchecked_without_a_matching_log(
    monkeypatch, tmp_path, capsys
):
    """Scoping must not turn an unchecked log into an ok result."""
    moment = _check_logs_environment(monkeypatch, tmp_path)
    _write_system_rules(tmp_path, "beta", "Beta")
    future = moment + timedelta(hours=1)

    assert cli.main(
        ["check-logs", "--since", future.isoformat(), "--system", "Beta"]
    ) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["system"] == "Beta"
    assert report["checked"] is False
    assert report["ok"] is False
    assert report["failures"] == []


def test_check_logs_reports_an_unresolved_edcopilot_root(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    monkeypatch.delenv("EDCG_EDCOPILOT_ROOT", raising=False)

    assert cli.main(["check-logs"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["checked"] is False
    assert "Could not resolve EDCoPilot's root" in report["summary"]


def test_check_logs_without_a_custom_file_names_that_condition(
    monkeypatch, tmp_path, capsys
):
    """No custom file means the markers were never added, not that a log is missing."""
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(runtime))

    assert cli.main(["check-logs"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["checked"] is False
    assert "No custom file found" in report["summary"]
    assert "add the markers first" in report["summary"]

