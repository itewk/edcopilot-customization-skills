"""Tests for branch orchestration - ported from test_tool_branch.py."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Import the functions directly from our implementation (the new module paths)
from edcg.repo.branches import (
    start_branch,
    branch_status,
    finalize_branch,
    abort_branch,
)
from edcg.repo.gitrepo import GitRepo


@pytest.fixture(autouse=True)
def reset_state():
    # Import the module with global state that we need to reset
    import edcg.repo.branches as branches_module
    branches_module._active_branch = None
    branches_module._branch_systems = set()
    yield
    branches_module._active_branch = None
    branches_module._branch_systems = set()


def _mock_config(tmp_path):
    cfg = MagicMock()
    cfg.content_definitions_root = tmp_path / "content"
    cfg.edcopilot_root = tmp_path / "runtime"
    cfg.content_definitions_root.mkdir(parents=True, exist_ok=True)
    cfg.edcopilot_root.mkdir(parents=True, exist_ok=True)
    return cfg


def test_start_branch_non_git_runtime_creates_backup(tmp_path):
    cfg = _mock_config(tmp_path)
    (cfg.edcopilot_root / "EDCoPilot.SpeechExtensions.Custom.txt").write_text("x", encoding="utf-8")
    with patch("edcg.repo.branches.get_config", return_value=cfg):
        with patch("edcg.repo.branches.GitRepo") as GR:
            GR.is_repo.return_value = False
            r = start_branch("test desc")
    assert r.backup_path is not None


def test_start_branch_sets_active_branch(tmp_path):
    cfg = _mock_config(tmp_path)
    with patch("edcg.repo.branches.get_config", return_value=cfg):
        with patch("edcg.repo.branches.GitRepo") as GR:
            GR.is_repo.return_value = False
            start_branch("desc")
    # Import and check the global state that was set by start_branch
    import edcg.repo.branches as branches_module
    assert branches_module._active_branch is not None


def test_branch_status_no_repos(tmp_path):
    cfg = _mock_config(tmp_path)
    with patch("edcg.repo.branches.get_config", return_value=cfg):
        with patch("edcg.repo.branches.GitRepo") as GR:
            GR.is_repo.return_value = False
            r = branch_status()
    assert r.active_branch is None


def test_finalize_no_active_branch_merged_false(tmp_path):
    cfg = _mock_config(tmp_path)
    with patch("edcg.repo.branches.get_config", return_value=cfg):
        with patch("edcg.repo.branches.GitRepo") as GR:
            GR.is_repo.return_value = False
            r = finalize_branch(merge=True, push=False)
    assert r.merged is False


def test_finalize_merge_false(tmp_path):
    cfg = _mock_config(tmp_path)

    # Set up the global state to simulate an active branch
    import edcg.repo.branches as branches_module
    branches_module._active_branch = "feat-x"

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        with patch("edcg.repo.branches.GitRepo") as GR:
            GR.is_repo.return_value = False
            r = finalize_branch(merge=False, push=False)
    assert r.merged is False


def test_abort_no_confirm(tmp_path):
    cfg = _mock_config(tmp_path)

    # Set up the global state to simulate an active branch
    import edcg.repo.branches as branches_module
    branches_module._active_branch = "feat-x"

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        with patch("edcg.repo.branches.GitRepo") as GR:
            GR.is_repo.return_value = False
            r = abort_branch(confirm=False)
    assert r.confirmed is False


def test_abort_confirm_clears_active(tmp_path):
    cfg = _mock_config(tmp_path)

    # Set up the global state to simulate an active branch
    import edcg.repo.branches as branches_module
    branches_module._active_branch = "feat-x"

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        with patch("edcg.repo.branches.GitRepo") as GR:
            GR.is_repo.return_value = False
            r = abort_branch(confirm=True)

    # Check that global state was cleared
    assert branches_module._active_branch is None
    assert r.confirmed is True


def test_abort_tolerant_mocked_repo(tmp_path):
    cfg = _mock_config(tmp_path)

    # Set up the global state to simulate an active branch
    import edcg.repo.branches as branches_module
    branches_module._active_branch = "feat-x"

    repo = MagicMock()
    repo.list_branches.return_value = ["main", "feat-x"]
    repo._repo = None

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        with patch("edcg.repo.branches.GitRepo") as GR:
            GR.is_repo.return_value = True
            GR.return_value = repo
            r = abort_branch(confirm=True)
    assert r is not None


# ---------------------------------------------------------------------------
# Push reporting
# ---------------------------------------------------------------------------


def test_finalize_push_with_nothing_to_attempt_reports_nothing_to_push(tmp_path):
    cfg = _mock_config(tmp_path)
    _init_repo_with_commit(cfg.content_definitions_root, "README.md")
    _init_repo_with_commit(
        cfg.edcopilot_root, "EDCoPilot.SpeechExtensions.Custom.txt", ""
    )

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        result = finalize_branch(merge=True, push=True)

    assert result.pushed is False
    assert result.push_status == "nothing_to_push"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def _init_repo_with_commit(root: Path, filename: str, content: str = "x\n") -> None:
    GitRepo.init(root).close()
    _git(root, "config", "user.name", "Push Test")
    _git(root, "config", "user.email", "push@example.com")
    (root / filename).write_text(content, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "initial")


def _start_and_commit(cfg) -> str:
    result = start_branch("push feature")
    (cfg.content_definitions_root / "systems").mkdir(exist_ok=True)
    (cfg.content_definitions_root / "systems" / "change.txt").write_text(
        "change\n", encoding="utf-8"
    )
    _git(cfg.content_definitions_root, "add", "-A")
    _git(cfg.content_definitions_root, "commit", "-m", "change")
    return result.branch_name


def test_finalize_push_failure_is_reported_honestly(tmp_path):
    cfg = _mock_config(tmp_path)
    _init_repo_with_commit(cfg.content_definitions_root, "README.md")
    _init_repo_with_commit(
        cfg.edcopilot_root, "EDCoPilot.SpeechExtensions.Custom.txt", ""
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


def test_finalize_push_success_is_reported(tmp_path):
    cfg = _mock_config(tmp_path)
    _init_repo_with_commit(cfg.content_definitions_root, "README.md")
    _init_repo_with_commit(
        cfg.edcopilot_root, "EDCoPilot.SpeechExtensions.Custom.txt", ""
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


def _checkout_foreign_branch(cfg) -> None:
    for root in (cfg.content_definitions_root, cfg.edcopilot_root):
        _git(root, "checkout", "-b", "release")


def test_foreign_branch_is_not_an_active_workflow_branch(tmp_path):
    cfg = _mock_config(tmp_path)
    _init_repo_with_commit(cfg.content_definitions_root, "README.md")
    _init_repo_with_commit(
        cfg.edcopilot_root, "EDCoPilot.SpeechExtensions.Custom.txt", ""
    )
    _checkout_foreign_branch(cfg)

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        status = branch_status()

    assert status.active_branch is None
    assert status.content_current_branch == "release"
    assert status.runtime_current_branch == "release"
    assert status.foreign_checkout is True


def test_finalize_refuses_a_foreign_branch_without_touching_it(tmp_path):
    cfg = _mock_config(tmp_path)
    _init_repo_with_commit(cfg.content_definitions_root, "README.md")
    _init_repo_with_commit(
        cfg.edcopilot_root, "EDCoPilot.SpeechExtensions.Custom.txt", ""
    )
    _checkout_foreign_branch(cfg)

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        result = finalize_branch(merge=True, push=False)

    assert result.merged is False
    assert result.merge_commits == [None, None]
    for root in (cfg.content_definitions_root, cfg.edcopilot_root):
        assert _git(root, "branch", "--show-current").strip() == "release"
        assert "release" in _git(root, "branch", "--format=%(refname:short)")


def test_abort_refuses_to_delete_a_foreign_branch(tmp_path):
    cfg = _mock_config(tmp_path)
    _init_repo_with_commit(cfg.content_definitions_root, "README.md")
    _init_repo_with_commit(
        cfg.edcopilot_root, "EDCoPilot.SpeechExtensions.Custom.txt", ""
    )
    _checkout_foreign_branch(cfg)

    with patch("edcg.repo.branches.get_config", return_value=cfg):
        result = abort_branch(confirm=True)

    assert result.discarded_branch is None
    assert result.content_discarded is False
    assert result.runtime_discarded is False
    assert "nothing to discard" in result.message
    for root in (cfg.content_definitions_root, cfg.edcopilot_root):
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


def test_finalize_without_push_does_not_push(tmp_path):
    cfg = _mock_config(tmp_path)
    _init_repo_with_commit(cfg.content_definitions_root, "README.md")
    _init_repo_with_commit(
        cfg.edcopilot_root, "EDCoPilot.SpeechExtensions.Custom.txt", ""
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