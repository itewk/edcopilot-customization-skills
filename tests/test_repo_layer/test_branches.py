"""Tests for branch orchestration - ported from test_tool_branch.py."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from support import commit_all, init_repo, run_git as _git

# Import the functions directly from our implementation (the new module paths)
from edcg.repo.branches import (
    start_branch,
    branch_status,
    finalize_branch,
    abort_branch,
)
from edcg.repo.gitrepo import GitRepo


@pytest.fixture
def branch_paths(tmp_path, monkeypatch):
    """A config mock plus the runtime root, supplied through the environment.

    ``Config`` carries no EDCoPilot-root field, so the fixture sets the
    environment exactly as the CLI does and returns the path for assertions.
    """
    content_root = tmp_path / "content"
    content_root.mkdir(parents=True, exist_ok=True)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(runtime_root))

    cfg = MagicMock()
    cfg.content_definitions_root = content_root
    return cfg, runtime_root


def test_start_branch_non_git_runtime_creates_backup(branch_paths):
    cfg, runtime_root = branch_paths
    (runtime_root / "EDCoPilot.SpeechExtensions.Custom.txt").write_text("x", encoding="utf-8")
    with patch("edcg.repo.branches.get_config", return_value=cfg):
        with patch("edcg.repo.branches.GitRepo") as GR:
            GR.is_repo.return_value = False
            r = start_branch("test desc")
    assert r.backup_path is not None


def test_branch_status_no_repos(branch_paths):
    cfg, _ = branch_paths
    with patch("edcg.repo.branches.get_config", return_value=cfg):
        with patch("edcg.repo.branches.GitRepo") as GR:
            GR.is_repo.return_value = False
            r = branch_status()
    assert r.active_branch is None


def test_finalize_no_active_branch_merged_false(branch_paths):
    cfg, _ = branch_paths
    with patch("edcg.repo.branches.get_config", return_value=cfg):
        with patch("edcg.repo.branches.GitRepo") as GR:
            GR.is_repo.return_value = False
            r = finalize_branch(merge=True, push=False)
    assert r.merged is False


def test_finalize_merge_false_keeps_the_feature_branch(branch_paths):
    """``--no-merge`` leaves both repositories on the feature branch."""
    cfg, runtime_root = branch_paths
    _init_repo_with_commit(cfg.content_definitions_root, "README.md")
    _init_repo_with_commit(
        runtime_root, "EDCoPilot.SpeechExtensions.Custom.txt", ""
    )

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        started = start_branch("stay on branch")
        r = finalize_branch(merge=False, push=False)

    assert r.merged is False
    assert r.message == "stayed on feature branch"
    for root in (cfg.content_definitions_root, runtime_root):
        assert _git(root, "branch", "--show-current").strip() == started.branch_name


def test_abort_without_confirm_discards_nothing(branch_paths):
    """The default is a preview; nothing is deleted until confirmation."""
    cfg, _ = branch_paths
    with patch("edcg.repo.branches.get_config", return_value=cfg):
        with patch("edcg.repo.branches.GitRepo") as GR:
            GR.is_repo.return_value = False
            r = abort_branch(confirm=False)
    assert r.confirmed is False
    assert r.discarded == []


# ---------------------------------------------------------------------------
# Push reporting
# ---------------------------------------------------------------------------


def test_finalize_push_with_nothing_to_attempt_reports_nothing_to_push(branch_paths):
    cfg, runtime_root = branch_paths
    _init_repo_with_commit(cfg.content_definitions_root, "README.md")
    _init_repo_with_commit(
        runtime_root, "EDCoPilot.SpeechExtensions.Custom.txt", ""
    )

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        result = finalize_branch(merge=True, push=True)

    assert result.pushed is False
    assert result.push_status == "nothing_to_push"


def _init_repo_with_commit(root: Path, filename: str, content: str = "x\n") -> None:
    init_repo(root)
    (root / filename).write_text(content, encoding="utf-8")
    commit_all(root, "initial")


def _start_and_commit(cfg) -> str:
    result = start_branch("push feature")
    (cfg.content_definitions_root / "systems").mkdir(exist_ok=True)
    (cfg.content_definitions_root / "systems" / "change.txt").write_text(
        "change\n", encoding="utf-8"
    )
    _git(cfg.content_definitions_root, "add", "-A")
    _git(cfg.content_definitions_root, "commit", "-m", "change")
    return result.branch_name


def test_finalize_push_failure_is_reported_honestly(branch_paths):
    cfg, runtime_root = branch_paths
    _init_repo_with_commit(cfg.content_definitions_root, "README.md")
    _init_repo_with_commit(
        runtime_root, "EDCoPilot.SpeechExtensions.Custom.txt", ""
    )
    calls: list[str] = []

    def failing_push(self, remote: str = "origin"):
        calls.append(remote)
        return False

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        _start_and_commit(cfg)
        with patch.object(GitRepo, "push", failing_push):
            result = finalize_branch(merge=True, push=True)

    assert calls == ["origin", "origin"]
    assert result.merged is True
    assert result.pushed is False
    assert result.push_status == "failed"


def test_finalize_push_success_is_reported(branch_paths):
    cfg, runtime_root = branch_paths
    _init_repo_with_commit(cfg.content_definitions_root, "README.md")
    _init_repo_with_commit(
        runtime_root, "EDCoPilot.SpeechExtensions.Custom.txt", ""
    )
    calls: list[str] = []

    def successful_push(self, remote: str = "origin"):
        calls.append(remote)
        return True

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        _start_and_commit(cfg)
        with patch.object(GitRepo, "push", successful_push):
            result = finalize_branch(merge=True, push=True)

    assert calls == ["origin", "origin"]
    assert result.pushed is True
    assert result.push_status == "pushed"


# ---------------------------------------------------------------------------
# Foreign checkouts are not workflow branches
# ---------------------------------------------------------------------------


def _checkout_foreign_branch(cfg, runtime_root) -> None:
    for root in (cfg.content_definitions_root, runtime_root):
        _git(root, "checkout", "-b", "release")


def test_foreign_branch_is_not_an_active_workflow_branch(branch_paths):
    cfg, runtime_root = branch_paths
    _init_repo_with_commit(cfg.content_definitions_root, "README.md")
    _init_repo_with_commit(
        runtime_root, "EDCoPilot.SpeechExtensions.Custom.txt", ""
    )
    _checkout_foreign_branch(cfg, runtime_root)

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        status = branch_status()

    assert status.active_branch is None
    assert status.content_current_branch == "release"
    assert status.runtime_current_branch == "release"
    assert status.foreign_checkout is True


def test_finalize_refuses_a_foreign_branch_without_touching_it(branch_paths):
    cfg, runtime_root = branch_paths
    _init_repo_with_commit(cfg.content_definitions_root, "README.md")
    _init_repo_with_commit(
        runtime_root, "EDCoPilot.SpeechExtensions.Custom.txt", ""
    )
    _checkout_foreign_branch(cfg, runtime_root)

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        result = finalize_branch(merge=True, push=False)

    assert result.merged is False
    assert result.merge_commits == [None, None]
    for root in (cfg.content_definitions_root, runtime_root):
        assert _git(root, "branch", "--show-current").strip() == "release"
        assert "release" in _git(root, "branch", "--format=%(refname:short)")


def test_abort_refuses_to_delete_a_foreign_branch(branch_paths):
    cfg, runtime_root = branch_paths
    _init_repo_with_commit(cfg.content_definitions_root, "README.md")
    _init_repo_with_commit(
        runtime_root, "EDCoPilot.SpeechExtensions.Custom.txt", ""
    )
    _checkout_foreign_branch(cfg, runtime_root)

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        result = abort_branch(confirm=True)

    assert result.discarded_branch is None
    assert result.content_discarded is False
    assert result.runtime_discarded is False
    assert "nothing to discard" in result.message
    for root in (cfg.content_definitions_root, runtime_root):
        assert "release" in _git(root, "branch", "--format=%(refname:short)")
        assert _git(root, "branch", "--show-current").strip() == "release"


def test_generated_branch_names_are_managed_branches():
    from edcg.repo.branches import is_managed_branch
    from edcg.repo.gitrepo import slugify_branch_name

    assert is_managed_branch(slugify_branch_name("add station lore"))
    assert is_managed_branch(slugify_branch_name("add station lore") + "-20260101T120000Z")
    assert is_managed_branch(slugify_branch_name())
    assert is_managed_branch("gen/42")
    assert not is_managed_branch("release")
    assert not is_managed_branch("main")
    assert not is_managed_branch("gen/")
    assert not is_managed_branch(None)


def test_finalize_without_push_does_not_push(branch_paths):
    cfg, runtime_root = branch_paths
    _init_repo_with_commit(cfg.content_definitions_root, "README.md")
    _init_repo_with_commit(
        runtime_root, "EDCoPilot.SpeechExtensions.Custom.txt", ""
    )
    calls: list[str] = []

    def push_spy(self, remote: str = "origin"):
        calls.append(remote)
        return True

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        _start_and_commit(cfg)
        with patch.object(GitRepo, "push", push_spy):
            result = finalize_branch(merge=True, push=False)

    assert calls == []
    assert result.pushed is False
    assert result.push_status == "not_pushed"