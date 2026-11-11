"""Tests for the doctor command.

The checks are exercised in-process with a temporary environment and the two
impure probes (package imports and git identity) patched, so the test does not
depend on the machine's installed packages or git configuration.
"""

from __future__ import annotations

import pytest

from edcg import cli
from edcg.cli import _git_binary as real_git_binary


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EDCG_CONTENT_DEFINITIONS_ROOT", raising=False)
    monkeypatch.delenv("EDCG_EDCOPILOT_ROOT", raising=False)
    monkeypatch.setattr(cli, "_check_import", lambda module: (True, "importable"))
    monkeypatch.setattr(cli, "_git_binary", lambda: "git version 2.44.0")
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
    assert len(lines) == 7
    assert all(line.startswith("OK") for line in lines)
    assert any("python:" in line for line in lines)
    assert any("git:" in line for line in lines)
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


def test_doctor_reports_a_missing_git_binary_without_a_config_hint(
    monkeypatch, capsys
):
    """A missing binary is not a missing identity, so the hints must differ."""
    monkeypatch.setattr(cli, "_git_binary", lambda: None)

    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "FAIL git: git not found on PATH" in out
    assert "git config --global" not in out
    assert "FAIL git identity:" not in out


def test_git_binary_returns_none_when_git_is_not_installed(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(cli, "_git_binary", real_git_binary)
    monkeypatch.setattr(cli.subprocess, "run", missing)
    assert cli._git_binary() is None


def test_git_binary_reports_the_version(monkeypatch):
    class Result:
        returncode = 0
        stdout = "git version 2.44.0\n"

    monkeypatch.setattr(cli, "_git_binary", real_git_binary)
    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: Result())
    assert cli._git_binary() == "git version 2.44.0"


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


def test_doctor_first_run_shape_is_only_the_root_check(tmp_path, capsys):
    """A fresh blank directory fails only the unconfigured EDCoPilot root."""
    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out

    status = [line for line in out.splitlines() if line.startswith(("OK", "FAIL"))]
    failures = [line for line in status if line.startswith("FAIL")]
    assert len(status) == 7
    assert failures == [
        "FAIL EDCoPilot root: not configured (expected on first run)"
    ]
    assert "expected on first run" in out
    assert f"OK   content root: {tmp_path} (blank)" in out


def test_doctor_accepts_a_plausible_edcopilot_root_without_a_warning(
    tmp_path, capsys
):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "EDCoPilot.SpeechExtensions.Custom.txt").write_text(
        "", encoding="utf-8"
    )
    cli.os.environ["EDCG_EDCOPILOT_ROOT"] = str(runtime)

    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "WARN EDCoPilot root" not in out


def test_doctor_warns_when_the_edcopilot_root_has_no_edcopilot_files(
    tmp_path, capsys
):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cli.os.environ["EDCG_EDCOPILOT_ROOT"] = str(runtime)

    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "WARN EDCoPilot root:" in out
    assert "does not look like EDCoPilot's User custom files folder" in out
    assert "confirm with the user" in out


def test_doctor_reports_an_unusable_content_root(monkeypatch, tmp_path, capsys):
    missing = tmp_path / "missing-content"
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(missing))

    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert f"FAIL content root:" in out
    assert str(missing) in out
    assert "FAIL EDCoPilot root: content root unavailable" in out
