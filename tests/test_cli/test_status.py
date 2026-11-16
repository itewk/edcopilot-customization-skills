"""Tests for the ``status`` command surface.

The report is prose on stdout and exits 0 in every repository state (D9): exit 1
would read as a stop signal on exactly the states a human may choose to push
through with an override. Usage errors keep argparse's exit 2.
"""

from __future__ import annotations

import pytest

from edcg import cli
from edcg.common.config import CONFIG_FILENAME
from edcg.common.layout import CUSTOM_FILE_NAME
from edcg.repo.status import HEADING
from support import commit_all, seed_repo

NAME = "Test System"

RULES = """[system]
names = ["Test System"]
dossier = "systems/test-system.md"
voices = ["PortAuthority"]
"""

DOSSIER = "# Test System — system dossier\n"


@pytest.fixture(autouse=True)
def _isolated(clean_env):
    """Run every test from an empty cwd with no configured roots."""
    return clean_env


def _write_definition(root):
    systems = root / "systems"
    systems.mkdir(exist_ok=True)
    (systems / "test-system.md").write_text(DOSSIER, encoding="utf-8")
    (systems / "test-system.rules.toml").write_text(RULES, encoding="utf-8")


def _house_rules(root):
    (root / CONFIG_FILENAME).write_text("[roots]\n", encoding="utf-8")
    (root / "systems").mkdir()
    (root / "systems" / "all.rules.toml").write_text("[rules]\n", encoding="utf-8")


def _runtime(monkeypatch, root):
    runtime = root / "edcopilot-runtime"
    runtime.mkdir(exist_ok=True)
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(runtime))
    return runtime


def _runtime_with(monkeypatch, root, text):
    runtime = _runtime(monkeypatch, root)
    (runtime / CUSTOM_FILE_NAME).write_text(text, encoding="utf-8")
    return runtime


def _build_state(state, monkeypatch, tmp_path):
    """Set up one repository state and return a marker its report must carry."""
    if state == "blank":
        return "  (none yet"

    if state == "house-rules-only":
        _house_rules(tmp_path)
        return f"[x] house rules: {tmp_path / 'systems' / 'all.rules.toml'}"

    seed_repo(tmp_path)
    _house_rules(tmp_path)
    _write_definition(tmp_path)
    commit_all(tmp_path, "edcg: scaffold Test System — system definition")

    if state == "definition-saved":
        _runtime(monkeypatch, tmp_path)
        return f"  [x] {NAME} - definition committed, no content; next:"

    if state == "content-written":
        _runtime_with(
            monkeypatch, tmp_path, "@SystemGreeting<~>Test System\nHello.\n"
        )
        return (
            f"  [x] {NAME} - definition committed, 1 authored tag, none marked; "
            "next:"
        )

    if state == "markers-set":
        _runtime_with(
            monkeypatch,
            tmp_path,
            "@SystemGreeting<~>Test System\nUPDATEDB\nHello.\n",
        )
        return (
            f"  [x] {NAME} - definition committed, 1 authored tag, all marked "
            "for update; next:"
        )

    raise AssertionError(state)


@pytest.mark.parametrize(
    "state",
    ["blank", "house-rules-only", "definition-saved", "content-written", "markers-set"],
)
def test_status_exits_zero_in_every_repository_state(
    state, monkeypatch, tmp_path, capsys
):
    expected = _build_state(state, monkeypatch, tmp_path)

    assert cli.main(["status"]) == 0

    captured = capsys.readouterr()
    assert captured.out.startswith(HEADING)
    assert expected in captured.out
    # A report is not a failed check, and it writes no diagnostics.
    assert captured.err == ""
    assert not captured.out.lstrip().startswith("{")


def test_the_system_flag_prints_that_systems_full_checklist(
    monkeypatch, tmp_path, capsys
):
    seed_repo(tmp_path)
    _house_rules(tmp_path)
    _write_definition(tmp_path)
    commit_all(tmp_path, "edcg: scaffold Test System — system definition")
    _runtime_with(
        monkeypatch,
        tmp_path,
        "@SystemGreeting<~>Test System\nUPDATEDB\nHello.\n",
    )

    assert cli.main(["status", "--system", NAME]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"edcg status for {NAME} (systems/test-system)"
    boxes = [line for line in lines if line.startswith("[")]
    assert len(boxes) == 6
    assert boxes == [
        f"[x] repository: {tmp_path}",
        f"[x] config: {CONFIG_FILENAME}",
        f"[x] house rules: {tmp_path / 'systems' / 'all.rules.toml'}",
        "[x] definition: systems/test-system.md and systems/test-system.rules.toml "
        "are committed",
        "[x] content: 1 authored tag for Test System - review with edcg.py "
        "get-content; edit in place with edcg.py rewrite-tag",
        "[x] markers: every authored tag for Test System is marked for update - "
        "restart EDCoPilot, run edcg.py check-logs, then edcg.py markdb remove "
        "after the in-game upload (SKILL.md Process steps 13-16)",
    ]


def test_usage_errors_keep_argparse_exit_two():
    with pytest.raises(SystemExit) as caught:
        cli.main(["status", "--bogus"])

    assert caught.value.code == 2


def test_a_broken_configuration_is_reported_and_still_exits_zero(tmp_path, capsys):
    """D9 covers an unreadable repository too: the answer is "cannot tell"."""
    (tmp_path / CONFIG_FILENAME).write_text("[roots\n", encoding="utf-8")

    assert cli.main(["status"]) == 0

    captured = capsys.readouterr()
    assert captured.out.startswith(HEADING)
    assert "[ ] repository: cannot read the repository: Cannot parse config file" in (
        captured.out
    )
    assert "next: fix the reported path or file, then re-run edcg.py status" in (
        captured.out
    )
