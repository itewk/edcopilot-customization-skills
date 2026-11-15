"""Tests for the init command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from edcg import cli
from support import run_git as _git


@pytest.fixture(autouse=True)
def _isolated(clean_env):
    """Apply the shared environment isolation to every test in this module."""
    return clean_env


def _json(capsys):
    return json.loads(capsys.readouterr().out)


def test_init_scaffolds_a_blank_root_without_git(tmp_path, capsys):
    assert cli.main(["init", "--no-git"]) == 0
    data = _json(capsys)

    assert data["content_root"] == str(tmp_path)
    assert data["state"] == "blank"
    assert data["git"] == {"initialized": False, "commit": None}
    assert not (tmp_path / ".git").exists()

    assert (tmp_path / cli.CONFIG_FILENAME).is_file()
    assert (tmp_path / "systems").is_dir()
    assert not (tmp_path / "systems" / "all.rules.toml.example").exists()
    assert (
        Path(__file__).resolve().parents[2] / "skills" / "edcopilot-system-content" / "assets" / "all.rules.toml.example"
    ).is_file()
    assert set(data["created"]) == {
        cli.CONFIG_FILENAME,
        "systems/",
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


def test_init_stages_only_config(tmp_path, monkeypatch, capsys):
    # D8: the skeleton commit stages ONLY the config file — never a sweep.
    # Build an existing repo with an unrelated untracked file, run init,
    # and assert the commit contains only the config file while the
    # unrelated file stays untracked.
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Init Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "init@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Init Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "init@example.com")

    # An existing repository with a commit and an unrelated untracked file.
    from edcg.repo.gitrepo import GitRepo

    GitRepo.init(tmp_path).close()
    (tmp_path / "README.md").write_text("# existing\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "existing")
    (tmp_path / "unrelated.txt").write_text("keep me\n", encoding="utf-8")

    assert cli.main(["init"]) == 0
    _json(capsys)

    committed = _git(tmp_path, "show", "--name-only", "--format=", "HEAD").split()
    assert "unrelated.txt" not in committed
    assert committed == [cli.CONFIG_FILENAME]
    status = _git(tmp_path, "status", "--porcelain")
    assert "?? unrelated.txt" in status

def test_init_scaffold_message_without_co_author(tmp_path, monkeypatch, capsys):
    # The invariant: without --co-author the scaffolding commit is unchanged.
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Init Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "init@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Init Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "init@example.com")

    assert cli.main(["init"]) == 0
    data = _json(capsys)

    assert data["git"]["initialized"] is True
    assert data["git"]["commit"]
    body = _git(tmp_path, "log", "-1", "--format=%B")
    assert body.strip() == "edcg: scaffold content repository"
    assert "Co-authored-by" not in body


def test_init_scaffold_appends_co_author_trailer(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Init Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "init@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Init Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "init@example.com")
    co_author = "🤖 Test Harness (test-model) <test@example.com>"

    assert cli.main(["init", "--co-author", co_author]) == 0
    data = _json(capsys)

    assert data["git"]["initialized"] is True
    assert data["git"]["commit"]
    body = _git(tmp_path, "log", "-1", "--format=%B")
    assert body.strip() == (
        f"edcg: scaffold content repository\n\nCo-authored-by: {co_author}"
    )


def test_init_scaffold_blank_co_author_is_ignored(tmp_path, monkeypatch, capsys):
    # The helper swallows blank values, so a whitespace-only flag adds nothing.
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Init Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "init@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Init Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "init@example.com")

    assert cli.main(["init", "--co-author", "   "]) == 0
    data = _json(capsys)

    assert data["git"]["initialized"] is True
    assert data["git"]["commit"]
    body = _git(tmp_path, "log", "-1", "--format=%B")
    assert body.strip() == "edcg: scaffold content repository"
    assert "Co-authored-by" not in body

