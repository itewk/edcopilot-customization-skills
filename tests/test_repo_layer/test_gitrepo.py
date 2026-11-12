"""Tests for Git operations wrapper."""

import shutil
import tempfile
import warnings
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from edcg.repo.gitrepo import GitRepo, slugify_branch_name
from support import run_git as _git


class TestGitRepoInit:
    """Tests for GitRepo initialization and repo detection."""

    def test_init_creates_repo_at_path(self):
        """Test GitRepo.init() creates a new git repository."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / "test_repo"
            repo = GitRepo.init(repo_path)
            assert repo_path.exists()
            assert (repo_path / ".git").exists()
            assert repo.path == repo_path
            repo.close()

    def test_init_existing_repo_returns_repo(self):
        """Test GitRepo.init() on existing repo returns the repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / "test_repo"
            repo1 = GitRepo.init(repo_path)
            repo2 = GitRepo.init(repo_path)
            assert repo1.path == repo2.path
            repo1.close()
            repo2.close()

    def test_is_repo_returns_true_for_git_repo(self):
        """Test GitRepo.is_repo() returns True for valid git repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / "test_repo"
            repo = GitRepo.init(repo_path)
            repo.close()
            assert GitRepo.is_repo(repo_path) is True

    def test_is_repo_returns_false_for_non_repo(self):
        """Test GitRepo.is_repo() returns False for non-git directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            non_repo = Path(tmpdir) / "not_a_repo"
            non_repo.mkdir()
            assert GitRepo.is_repo(non_repo) is False

    def test_is_repo_returns_false_for_nonexistent_path(self):
        """Test GitRepo.is_repo() returns False for nonexistent path."""
        assert GitRepo.is_repo(Path("/nonexistent/path")) is False


class TestGitRepoOperations:
    """Tests for GitRepo operations on a valid repository."""

    @pytest.fixture
    def repo(self):
        """Create a temporary git repo for testing."""
        tmpdir = tempfile.mkdtemp()
        repo_path = Path(tmpdir) / "test_repo"
        repo = GitRepo.init(repo_path)
        # Configure git user for commits
        _git(repo_path, "config", "user.name", "Test User")
        _git(repo_path, "config", "user.email", "test@example.com")
        yield repo
        repo.close()
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_status_clean_repo(self, repo):
        """Test status() on clean repo returns empty changes."""
        status = repo.status()
        assert status["staged"] == []
        assert status["unstaged"] == []
        assert status["untracked"] == []
        assert status["clean"] is True

    def test_status_with_untracked_files(self, repo):
        """Test status() detects untracked files."""
        test_file = repo.path / "new_file.txt"
        test_file.write_text("content")
        status = repo.status()
        assert "new_file.txt" in status["untracked"]
        assert status["clean"] is False

    def test_status_with_staged_changes(self, repo):
        """Test status() detects staged changes."""
        test_file = repo.path / "staged.txt"
        test_file.write_text("staged content")
        repo.add_all()
        status = repo.status()
        assert "staged.txt" in status["staged"]
        assert status["clean"] is False

    def test_status_with_unstaged_changes(self, repo):
        """Test status() detects unstaged changes to tracked files."""
        test_file = repo.path / "tracked.txt"
        test_file.write_text("initial")
        repo.add_all()
        repo.commit("Initial commit")
        test_file.write_text("modified")
        status = repo.status()
        assert "tracked.txt" in status["unstaged"]
        assert status["clean"] is False

    def test_diff_returns_diff_output(self, repo):
        """Test diff() returns diff for unstaged changes."""
        test_file = repo.path / "diff_test.txt"
        test_file.write_text("line1\nline2\n")
        repo.add_all()
        repo.commit("Initial")
        test_file.write_text("line1\nline2 modified\nline3\n")
        diff_output = repo.diff()
        assert "line2 modified" in diff_output or "line3" in diff_output

    def test_add_all_stages_all_changes(self, repo):
        """Test add_all() stages all untracked and modified files."""
        file1 = repo.path / "file1.txt"
        file2 = repo.path / "file2.txt"
        file1.write_text("content1")
        file2.write_text("content2")
        repo.add_all()
        status = repo.status()
        assert "file1.txt" in status["staged"]
        assert "file2.txt" in status["staged"]

    def test_commit_creates_commit_with_message(self, repo):
        """Test commit() creates a commit with the given message."""
        test_file = repo.path / "commit_test.txt"
        test_file.write_text("commit content")
        repo.add_all()
        commit_hash = repo.commit("Test commit message")
        assert commit_hash is not None
        assert len(commit_hash) > 0
        # Verify commit exists
        assert _git(repo.path, "log", "-1", "--format=%s").strip() == "Test commit message"

    def test_commit_returns_none_on_empty_commit(self, repo):
        """Test commit() returns None when there's nothing to commit."""
        result = repo.commit("Empty commit")
        assert result is None

    def test_commit_records_each_commit_in_order(self, repo):
        """Test successive commits appear most-recent-first in git's log."""
        for i in range(3):
            test_file = repo.path / f"file{i}.txt"
            test_file.write_text(f"content{i}")
            repo.add_all()
            repo.commit(f"Commit {i}")
        log = _git(repo.path, "log", "-5", "--format=%s").splitlines()
        assert log == ["Commit 2", "Commit 1", "Commit 0"]


class TestGitRepoNonRepoHandling:
    """Tests for graceful handling of non-repo paths."""

    @pytest.fixture
    def non_repo(self):
        """Create a GitRepo instance pointing to a non-repo path."""
        tmpdir = tempfile.mkdtemp()
        non_repo_path = Path(tmpdir) / "not_a_repo"
        non_repo_path.mkdir()
        repo = GitRepo(non_repo_path)
        yield repo
        repo.close()
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_status_on_non_repo_returns_empty_with_warning(self, non_repo):
        """Test status() on non-repo returns empty dict with warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            status = non_repo.status()
            assert status == {"staged": [], "unstaged": [], "untracked": [], "clean": True}
            assert len(w) == 1
            assert "not a git repository" in str(w[0].message).lower()

    def test_diff_on_non_repo_returns_empty_with_warning(self, non_repo):
        """Test diff() on non-repo returns empty string with warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            diff = non_repo.diff()
            assert diff == ""
            assert len(w) == 1
            assert "not a git repository" in str(w[0].message).lower()

    def test_add_all_on_non_repo_noops_with_warning(self, non_repo):
        """Test add_all() on non-repo is no-op with warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            non_repo.add_all()
            assert len(w) == 1
            assert "not a git repository" in str(w[0].message).lower()

    def test_commit_on_non_repo_returns_none_with_warning(self, non_repo):
        """Test commit() on non-repo returns None with warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = non_repo.commit("Test")
            assert result is None
            assert len(w) == 1
            assert "not a git repository" in str(w[0].message).lower()


class TestGitRepoAuthorConfig:
    """Tests for commit author configuration."""

    def test_commit_uses_git_config_author(self):
        """Test commit uses author from git config."""
        tmpdir = tempfile.mkdtemp()
        repo_path = Path(tmpdir) / "test_repo"
        repo = GitRepo.init(repo_path)
        _git(repo_path, "config", "user.name", "Configured User")
        _git(repo_path, "config", "user.email", "configured@example.com")

        test_file = repo.path / "author_test.txt"
        test_file.write_text("content")
        repo.add_all()
        commit_hash = repo.commit("Author test")

        # Verify author in commit
        author_name = _git(repo.path, "log", "-1", "--format=%an", commit_hash).strip()
        author_email = _git(repo.path, "log", "-1", "--format=%ae", commit_hash).strip()
        assert author_name == "Configured User"
        assert author_email == "configured@example.com"

        repo.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


class TestGitRepoIntegration:
    """Integration tests with real repo scenarios."""

    def test_full_workflow_staged_and_unstaged(self):
        """Test complete workflow with staged and unstaged changes."""
        tmpdir = tempfile.mkdtemp()
        repo_path = Path(tmpdir) / "integration_repo"
        repo = GitRepo.init(repo_path)
        _git(repo_path, "config", "user.name", "Integration Test")
        _git(repo_path, "config", "user.email", "integration@test.com")

        try:
            # Initial commit
            file1 = repo.path / "file1.txt"
            file1.write_text("initial")
            repo.add_all()
            repo.commit("Initial commit")

            # Modify tracked file (unstaged)
            file1.write_text("modified")

            # Add new file (untracked)
            file2 = repo.path / "file2.txt"
            file2.write_text("new file")

            # Stage new file
            _git(repo.path, "add", "file2.txt")

            status = repo.status()
            assert "file1.txt" in status["unstaged"]
            assert "file2.txt" in status["staged"]
            assert status["clean"] is False

            # Diff should show unstaged changes
            diff_output = repo.diff()
            assert "modified" in diff_output

            # Commit staged
            repo.commit("Add file2")

            # Now stage and commit the modification
            repo.add_all()
            repo.commit("Modify file1")

            log = _git(repo.path, "log", "-3", "--format=%s").splitlines()
            assert log == ["Modify file1", "Add file2", "Initial commit"]
        finally:
            repo.close()
            shutil.rmtree(tmpdir, ignore_errors=True)

class TestGitRepoBranches:
    """Tests for GitRepo branch operations."""

    @pytest.fixture
    def repo(self):
        """Create a temporary git repo for testing."""
        tmpdir = tempfile.mkdtemp()
        repo_path = Path(tmpdir) / "test_repo"
        repo = GitRepo.init(repo_path)
        _git(repo_path, "config", "user.name", "Test User")
        _git(repo_path, "config", "user.email", "test@example.com")
        # Create initial commit so branches work properly
        test_file = repo_path / "initial.txt"
        test_file.write_text("initial")
        repo.add_all()
        repo.commit("Initial commit")
        yield repo
        repo.close()
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_create_branch_creates_and_checks_out_new_branch(self, repo):
        """Test create_branch creates and checks out new branch."""
        original = repo.current_branch()
        repo.create_branch("feature")
        assert repo.current_branch() == "feature"
        assert original != repo.current_branch()

    def test_create_branch_returns_branch_name(self, repo):
        """Test create_branch returns branch name."""
        result = repo.create_branch("newbranch")
        assert result == "newbranch"

    def test_create_branch_invalid_name_raises_value_error(self, repo):
        """Test create_branch invalid name raises ValueError."""
        with pytest.raises(ValueError):
            repo.create_branch("invalid branch name")

    def test_create_branch_on_non_repo_returns_none(self):
        """Test create_branch on non-repo returns None."""
        tmpdir = tempfile.mkdtemp()
        non_repo_path = Path(tmpdir) / "not_a_repo"
        non_repo_path.mkdir()
        non_repo = GitRepo(non_repo_path)
        try:
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                result = non_repo.create_branch("feature")
                assert result is None
        finally:
            non_repo.close()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_checkout_switches_to_existing_branch(self, repo):
        """Test checkout switches to existing branch."""
        repo.create_branch("feature")
        repo.checkout("master") if repo.current_branch() == "feature" else repo.checkout("main")
        # Create another branch and switch back
        current = repo.current_branch()
        repo.checkout("feature")
        assert repo.current_branch() == "feature"
        repo.checkout(current)
        assert repo.current_branch() == current

    def test_checkout_invalid_name_raises_value_error(self, repo):
        """Test checkout invalid name raises ValueError."""
        with pytest.raises(ValueError):
            repo.checkout("bad branch name!")

    def test_checkout_non_existent_branch_doesnt_raise(self, repo):
        """Test checkout non-existent branch doesn't raise."""
        # Should not raise even if branch doesn't exist
        repo.checkout("nonexistent-branch-xyz")
        # Current branch might change or stay same depending on behavior
        # But it shouldn't crash

    def test_merge_merges_branch_and_returns_commit_hash(self, repo):
        """Test merge merges branch and returns commit hash."""
        original_branch = repo.current_branch()
        repo.create_branch("feature-branch")
        # Make a commit on feature branch
        test_file = repo.path / "feature.txt"
        test_file.write_text("feature content")
        repo.add_all()
        repo.commit("Feature commit")
        # Switch back to original branch
        repo.checkout(original_branch)
        # Merge feature branch
        result = repo.merge("feature-branch")
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_merge_invalid_name_raises_value_error(self, repo):
        """Test merge invalid name raises ValueError."""
        with pytest.raises(ValueError):
            repo.merge("invalid branch!")

    def test_merge_non_repo_returns_none(self):
        """Test merge on non-repo returns None."""
        tmpdir = tempfile.mkdtemp()
        non_repo_path = Path(tmpdir) / "not_a_repo"
        non_repo_path.mkdir()
        non_repo = GitRepo(non_repo_path)
        try:
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                result = non_repo.merge("feature")
                assert result is None
        finally:
            non_repo.close()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_current_branch_returns_current_branch_name(self, repo):
        """Test current_branch returns current branch name."""
        branch = repo.current_branch()
        assert isinstance(branch, str)
        assert len(branch) > 0

    def test_current_branch_on_non_repo_returns_empty_string(self):
        """Test current_branch on non-repo returns ""."""
        tmpdir = tempfile.mkdtemp()
        non_repo_path = Path(tmpdir) / "not_a_repo"
        non_repo_path.mkdir()
        non_repo = GitRepo(non_repo_path)
        try:
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                result = non_repo.current_branch()
                assert result == ""
        finally:
            non_repo.close()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_list_branches_returns_all_branches(self, repo):
        """Test list_branches returns all branches."""
        original = repo.current_branch()
        repo.create_branch("branch1")
        repo.checkout(original)
        repo.create_branch("branch2")
        branches = repo.list_branches()
        assert isinstance(branches, list)
        assert original in branches
        assert "branch1" in branches
        assert "branch2" in branches

    def test_list_branches_on_non_repo_returns_empty_list(self):
        """Test list_branches on non-repo returns []"""
        tmpdir = tempfile.mkdtemp()
        non_repo_path = Path(tmpdir) / "not_a_repo"
        non_repo_path.mkdir()
        non_repo = GitRepo(non_repo_path)
        try:
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                result = non_repo.list_branches()
                assert result == []
        finally:
            non_repo.close()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_default_branch_prefers_a_branch_that_exists(self, repo):
        """With no remote, the answer is the branch the repository actually has."""
        result = repo.default_branch()
        assert result in repo.list_branches()
        assert result == repo.current_branch()

    def test_default_branch_prefers_main_over_master(self, committed_repo):
        """Both exist: ``main`` wins regardless of which branch is checked out."""
        if committed_repo.current_branch() != "main":
            _git(committed_repo.path, "branch", "-m", "main")
        _git(committed_repo.path, "branch", "master")

        assert {"main", "master"} <= set(committed_repo.list_branches())
        assert committed_repo.default_branch() == "main"

    def test_default_branch_prefers_master_when_main_is_absent(self, committed_repo):
        """A ``master`` repository answers ``master``, not the ``main`` literal."""
        if committed_repo.current_branch() != "master":
            _git(committed_repo.path, "branch", "-m", "master")

        assert "main" not in committed_repo.list_branches()
        assert committed_repo.default_branch() == "master"

    def test_default_branch_uses_symbolic_ref_for_a_non_conventional_name(
        self, committed_repo
    ):
        """No main/master: the remote HEAD wins over the first local branch."""
        _git(committed_repo.path, "branch", "-m", "work")
        _git(committed_repo.path, "branch", "alpha")
        _git(committed_repo.path, "branch", "release")
        _git(
            committed_repo.path,
            "update-ref",
            "refs/remotes/origin/release",
            "HEAD",
        )
        _git(
            committed_repo.path,
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            "refs/remotes/origin/release",
        )

        assert committed_repo.default_branch() == "release"

    def test_default_branch_falls_back_to_the_first_branch(self, committed_repo):
        """No main/master and no remote HEAD: the first local branch answers."""
        _git(committed_repo.path, "branch", "-m", "work")
        _git(committed_repo.path, "branch", "alpha")
        _git(committed_repo.path, "branch", "zeta")

        assert committed_repo.default_branch() == "alpha"

    def test_push_on_non_repo_returns_none(self):
        """Test push on non-repo returns None."""
        tmpdir = tempfile.mkdtemp()
        non_repo_path = Path(tmpdir) / "not_a_repo"
        non_repo_path.mkdir()
        non_repo = GitRepo(non_repo_path)
        try:
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                result = non_repo.push()
                assert result is None
        finally:
            non_repo.close()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_create_branch_with_slash_in_name_works(self, repo):
        """Test create_branch with slash in name works (e.g., 'feature/test')."""
        result = repo.create_branch("feature/test")
        assert result == "feature/test"
        assert repo.current_branch() == "feature/test"


class TestGitRepoContextManager:
    """GitRepo is a resource: a ``with`` block closes it, twice is harmless."""

    def test_with_block_closes_the_repository(self, tmp_path):
        repo_path = tmp_path / "ctx"
        GitRepo.init(repo_path).close()

        with GitRepo(repo_path) as opened:
            assert opened.path == repo_path
            assert opened.status()["clean"] is True

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            opened.status()
        assert any("not a git repository" in str(w.message).lower() for w in caught)

    def test_close_is_idempotent(self, tmp_path):
        repo_path = tmp_path / "ctx"
        GitRepo.init(repo_path).close()

        repo = GitRepo(repo_path)
        repo.close()
        repo.close()


@pytest.fixture
def committed_repo(tmp_path):
    """A repository with one commit, ready for diff and branch operations."""
    repo = GitRepo.init(tmp_path / "committed")
    _git(repo.path, "config", "user.name", "Test User")
    _git(repo.path, "config", "user.email", "test@example.com")
    (repo.path / "README.md").write_text("base\n", encoding="utf-8")
    repo.add_all()
    repo.commit("base")
    yield repo
    repo.close()


class TestGitRepoDiffStat:
    """diff_stat is the one counting rule review and callers share."""

    def test_diff_stat_counts_working_tree_changes(self, committed_repo):
        (committed_repo.path / "README.md").write_text(
            "changed\nadded\n", encoding="utf-8"
        )

        stats = committed_repo.diff_stat()

        assert stats["files"] == ["README.md"]
        assert stats["insertions"] == 2
        assert stats["deletions"] == 1

    def test_diff_stat_includes_untracked_files(self, committed_repo):
        (committed_repo.path / "draft.txt").write_text("draft\n", encoding="utf-8")

        stats = committed_repo.diff_stat()

        assert stats["files"] == ["draft.txt"]
        assert stats["insertions"] == 0

    def test_diff_stat_for_a_ref_counts_committed_changes(self, committed_repo):
        default = committed_repo.default_branch()
        committed_repo.create_branch("feature")
        (committed_repo.path / "feature.txt").write_text("feature\n", encoding="utf-8")
        committed_repo.add_all()
        committed_repo.commit("feature work")

        stats = committed_repo.diff_stat(default)

        assert stats["files"] == ["feature.txt"]
        assert stats["insertions"] == 1
        assert stats["deletions"] == 0

    def test_diff_stat_counts_staged_files_before_the_first_commit(self, tmp_path):
        """No HEAD: diff() answers "" for unstaged, the index diff still counts."""
        repo = GitRepo.init(tmp_path / "no-head")
        try:
            (repo.path / "first.txt").write_text("one\ntwo\n", encoding="utf-8")
            repo.add_all()

            stats = repo.diff_stat()

            assert stats["files"] == ["first.txt"]
            assert stats["insertions"] == 2
            assert stats["deletions"] == 0
        finally:
            repo.close()

    def test_diff_stat_on_non_repo_is_zeroed(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        repo = GitRepo(plain)
        try:
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                stats = repo.diff_stat()
            assert stats == {"files": [], "insertions": 0, "deletions": 0}
        finally:
            repo.close()


class TestGitRepoBranchDeletion:
    def test_delete_branch_removes_it(self, committed_repo):
        default = committed_repo.default_branch()
        committed_repo.create_branch("doomed")
        committed_repo.checkout(default)

        assert committed_repo.delete_branch("doomed") is True
        assert "doomed" not in committed_repo.list_branches()

    def test_delete_branch_reports_a_checked_out_branch_as_not_deleted(
        self, committed_repo
    ):
        committed_repo.create_branch("current")

        assert committed_repo.delete_branch("current") is False
        assert "current" in committed_repo.list_branches()

    def test_delete_branch_on_non_repo_returns_false(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        repo = GitRepo(plain)
        try:
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                assert repo.delete_branch("feature") is False
        finally:
            repo.close()


class TestGitRepoCommitsBetween:
    def test_commits_between_lists_only_the_branch_commits(self, committed_repo):
        default = committed_repo.default_branch()
        committed_repo.create_branch("feature")
        (committed_repo.path / "feature.txt").write_text("feature\n", encoding="utf-8")
        committed_repo.add_all()
        committed_repo.commit("feature work")

        assert committed_repo.commits_between(default, "feature") == ["feature work"]

    def test_commits_between_with_no_divergence_is_empty(self, committed_repo):
        default = committed_repo.default_branch()

        assert committed_repo.commits_between(default, default) == []


class TestGitRepoAbortMerge:
    def test_abort_merge_restores_a_conflicted_tree(self, committed_repo):
        default = committed_repo.default_branch()
        shared = committed_repo.path / "shared.txt"
        shared.write_text("base\n", encoding="utf-8")
        committed_repo.add_all()
        committed_repo.commit("base file")

        committed_repo.create_branch("feature")
        shared.write_text("feature\n", encoding="utf-8")
        committed_repo.add_all()
        committed_repo.commit("feature edit")

        committed_repo.checkout(default)
        shared.write_text("default\n", encoding="utf-8")
        committed_repo.add_all()
        committed_repo.commit("default edit")

        assert committed_repo.merge("feature") is None
        committed_repo.abort_merge()

        assert committed_repo.status()["clean"] is True
        assert committed_repo.current_branch() == default


class TestSlugifyBranchName:
    def test_no_description_includes_timestamp(self):
        name = slugify_branch_name()
        assert name.startswith("gen/")
        assert name[4:].isdigit()

    def test_description_slugified(self):
        assert slugify_branch_name("My Feature!") == "gen/my-feature"

    def test_empty_description_uses_timestamp(self):
        name = slugify_branch_name("")
        assert name.startswith("gen/")
        assert name[4:].isdigit()


class TestPushMock:
    def test_push_calls_repo_git_push(self):
        import tempfile
        from pathlib import Path
        tmpdir = tempfile.mkdtemp()
        repo_path = Path(tmpdir) / "r"
        repo = GitRepo.init(repo_path)
        repo._repo = MagicMock()
        repo._is_valid_repo = True
        repo.push("origin")
        repo._repo.git.push.assert_called_with("origin")
        repo.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


class TestDefaultBranchSymbolicRef:
    def test_symbolic_ref_detection(self):
        import tempfile
        from pathlib import Path
        tmpdir = tempfile.mkdtemp()
        repo_path = Path(tmpdir) / "r"
        repo = GitRepo.init(repo_path)
        repo._repo = MagicMock()
        repo._is_valid_repo = True
        repo._repo.git.symbolic_ref.return_value = "refs/remotes/origin/main"
        assert repo.default_branch() == "main"
        repo.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_non_repo_root_warns_and_succeeds(tmp_path):
    import warnings
    from edcg.repo.gitrepo import GitRepo
    plain = tmp_path / "plain"
    plain.mkdir()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        repo = GitRepo(plain)
        # Call a method to trigger the warning (since constructor doesn't warn in our implementation)
        repo.status()
    assert len(caught) > 0  # a warning was issued, no exception


if __name__ == "__main__":
    pytest.main([__file__, "-v"])