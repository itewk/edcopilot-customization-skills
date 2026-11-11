"""Tests for the init command."""

from __future__ import annotations

import json
import subprocess

import pytest

from edcg import cli
from edcg.rules.engine import get_template


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EDCG_CONTENT_DEFINITIONS_ROOT", raising=False)
    monkeypatch.delenv("EDCG_EDCOPILOT_ROOT", raising=False)
    return tmp_path


def _json(capsys):
    return json.loads(capsys.readouterr().out)


def _git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout


def test_init_scaffolds_a_blank_root_without_git(tmp_path, capsys):
    assert cli.main(["init", "--no-git"]) == 0
    data = _json(capsys)

    assert data["content_root"] == str(tmp_path)
    assert data["state"] == "blank"
    assert data["git"] == {"initialized": False, "commit": None}
    assert not (tmp_path / ".git").exists()

    assert (tmp_path / cli.CONFIG_FILENAME).is_file()
    assert (tmp_path / "systems").is_dir()
    example = tmp_path / "systems" / "all.rules.toml.example"
    assert example.read_text(encoding="utf-8") == get_template(
        "all.rules.toml.example"
    )
    assert set(data["created"]) == {
        cli.CONFIG_FILENAME,
        "systems/",
        "systems/all.rules.toml.example",
    }


def test_init_makes_one_scaffolding_commit_with_git(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Init Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "init@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Init Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "init@example.com")

    assert cli.main(["init"]) == 0
    data = _json(capsys)

    assert data["git"]["initialized"] is True
    assert data["git"]["commit"]
    assert (tmp_path / ".git").is_dir()
    assert _git(tmp_path, "log", "--format=%s").strip() == (
        "edcg: scaffold content repository"
    )
    body = _git(tmp_path, "log", "-1", "--format=%B")
    assert "Co-authored-by" not in body
    assert _git(tmp_path, "status", "--porcelain").strip() == ""


def test_init_refuses_when_systems_already_exists(tmp_path, capsys):
    (tmp_path / "systems").mkdir()
    (tmp_path / "systems" / "keep.md").write_text("keep", encoding="utf-8")

    assert cli.main(["init", "--no-git"]) == 1
    error = _json(capsys)["error"]
    assert "already a content repository" in error
    assert (tmp_path / "systems" / "keep.md").read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / cli.CONFIG_FILENAME).exists()


def test_init_refuses_when_a_config_file_already_exists(tmp_path, capsys):
    (tmp_path / cli.CONFIG_FILENAME).write_text("[roots]\n", encoding="utf-8")

    assert cli.main(["init", "--no-git"]) == 1
    assert "already a content repository" in _json(capsys)["error"]
    assert not (tmp_path / "systems").exists()


def test_init_refuses_a_second_run(tmp_path, capsys):
    assert cli.main(["init", "--no-git"]) == 0
    capsys.readouterr()
    assert cli.main(["init", "--no-git"]) == 1
    assert "already a content repository" in _json(capsys)["error"]
