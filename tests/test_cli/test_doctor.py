"""Tests for the doctor command.

The checks are exercised in-process with a temporary environment and the two
impure probes (package imports and git identity) patched, so the test does not
depend on the machine's installed packages or git configuration.
"""

from __future__ import annotations

import pytest

from edcg import cli


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EDCG_CONTENT_DEFINITIONS_ROOT", raising=False)
    monkeypatch.delenv("EDCG_EDCOPILOT_ROOT", raising=False)
    monkeypatch.setattr(cli, "_check_import", lambda module: (True, "importable"))
    monkeypatch.setattr(
        cli, "_git_identity", lambda: ("Test User", "test@example.com")
    )
    return tmp_path


def _lines(capsys):
    return capsys.readouterr().out.splitlines()


def _status(lines):
    return [line for line in lines if line.startswith(("OK", "FAIL"))]


def test_doctor_passes_every_check(tmp_path, capsys):
    (tmp_path / "runtime").mkdir()
    cli.os.environ["EDCG_EDCOPILOT_ROOT"] = str(tmp_path / "runtime")

    assert cli.main(["doctor"]) == 0
    lines = _status(_lines(capsys))
    assert len(lines) == 6
    assert all(line.startswith("OK") for line in lines)
    assert any("python:" in line for line in lines)
    assert any("EDCoPilot root:" in line for line in lines)


def test_doctor_fails_on_an_old_python(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_python_version", lambda: (3, 8))

    assert cli.main(["doctor"]) == 1
    lines = _lines(capsys)
    assert any(line.startswith("FAIL python:") for line in lines)
    assert any("install Python 3.12" in line for line in lines)


def test_doctor_reports_missing_packages_with_the_install_hint(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "_check_import",
        lambda module: (False, f"No module named {module!r}")
        if module == "httpx"
        else (True, "importable"),
    )

    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "FAIL httpx:" in out
    assert "fix: pip install httpx gitpython" in out


def test_doctor_fails_without_git_identity(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_git_identity", lambda: (None, None))

    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "FAIL git identity:" in out
    assert "missing user.name, user.email" in out
    assert "git config --global user.name" in out


def test_doctor_names_a_stale_configured_edcopilot_root(tmp_path, capsys):
    missing = tmp_path / "gone"
    (tmp_path / cli.CONFIG_FILENAME).write_text(
        f'[roots]\nedcopilot = "{missing.as_posix()}"\n', encoding="utf-8"
    )

    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert f"FAIL EDCoPilot root: configured path no longer exists: {missing}" in out
    assert "update roots.edcopilot" in out


def test_doctor_fails_when_the_edcopilot_root_is_unconfigured(tmp_path, capsys):
    (tmp_path / cli.CONFIG_FILENAME).write_text("[roots]\n", encoding="utf-8")

    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "FAIL EDCoPilot root: not configured" in out
    assert "set EDCG_EDCOPILOT_ROOT" in out


def test_doctor_reports_an_unusable_content_root(monkeypatch, tmp_path, capsys):
    missing = tmp_path / "missing-content"
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(missing))

    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert f"FAIL content root:" in out
    assert str(missing) in out
    assert "FAIL EDCoPilot root: content root unavailable" in out
