"""Tests for Git operations wrapper."""

import tempfile
import warnings
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from edcg.repo.gitrepo import GitRepo, slugify_branch_name


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
        repo._run_git("config", "user.name", "Test User")
        repo._run_git("config", "user.email", "test@example.com")
        yield repo
        repo.close()
        import shutil
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
        log = repo.log(1)
        assert "Test commit message" in log[0]

    def test_commit_returns_none_on_empty_commit(self, repo):
        """Test commit() returns None when there's nothing to commit."""
        result = repo.commit("Empty commit")
        assert result is None

    def test_log_returns_recent_commits(self, repo):
        """Test log() returns recent commit messages."""
        for i in range(3):
            test_file = repo.path / f"file{i}.txt"
            test_file.write_text(f"content{i}")
            repo.add_all()
            repo.commit(f"Commit {i}")
        log = repo.log(5)
        assert len(log) == 3
        assert "Commit 2" in log[0]
        assert "Commit 1" in log[1]
        assert "Commit 0" in log[2]

    def test_log_respects_limit(self, repo):
        """Test log() respects the n parameter."""
        for i in range(5):
            test_file = repo.path / f"file{i}.txt"
            test_file.write_text(f"content{i}")
            repo.add_all()
            repo.commit(f"Commit {i}")
        log = repo.log(3)
        assert len(log) == 3


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
        import shutil
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

    def test_log_on_non_repo_returns_empty_with_warning(self, non_repo):
        """Test log() on non-repo returns empty list with warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            log = non_repo.log()
            assert log == []
            assert len(w) == 1
            assert "not a git repository" in str(w[0].message).lower()


class TestGitRepoAuthorConfig:
    """Tests for commit author configuration."""

    def test_commit_uses_git_config_author(self):
        """Test commit uses author from git config."""
        tmpdir = tempfile.mkdtemp()
        repo_path = Path(tmpdir) / "test_repo"
        repo = GitRepo.init(repo_path)
        repo._run_git("config", "user.name", "Configured User")
        repo._run_git("config", "user.email", "configured@example.com")
        
        test_file = repo.path / "author_test.txt"
        test_file.write_text("content")
        repo.add_all()
        commit_hash = repo.commit("Author test")
        
        # Verify author in commit
        author_name = repo._run_git("log", "-1", "--format=%an", commit_hash).strip()
        author_email = repo._run_git("log", "-1", "--format=%ae", commit_hash).strip()
        assert author_name == "Configured User"
        assert author_email == "configured@example.com"
        
        repo.close()
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


class TestGitRepoIntegration:
    """Integration tests with real repo scenarios."""

    def test_full_workflow_staged_and_unstaged(self):
        """Test complete workflow with staged and unstaged changes."""
        tmpdir = tempfile.mkdtemp()
        repo_path = Path(tmpdir) / "integration_repo"
        repo = GitRepo.init(repo_path)
        repo._run_git("config", "user.name", "Integration Test")
        repo._run_git("config", "user.email", "integration@test.com")
        
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
            repo._run_git("add", "file2.txt")
            
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
            
            log = repo.log(3)
            assert len(log) == 3
            assert "Modify file1" in log[0]
            assert "Add file2" in log[1]
            assert "Initial commit" in log[2]
        finally:
            repo.close()
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

class TestGitRepoBranches:
    """Tests for GitRepo branch operations."""

    @pytest.fixture
    def repo(self):
        """Create a temporary git repo for testing."""
        tmpdir = tempfile.mkdtemp()
        repo_path = Path(tmpdir) / "test_repo"
        repo = GitRepo.init(repo_path)
        repo._run_git("config", "user.name", "Test User")
        repo._run_git("config", "user.email", "test@example.com")
        # Create initial commit so branches work properly
        test_file = repo_path / "initial.txt"
        test_file.write_text("initial")
        repo.add_all()
        repo.commit("Initial commit")
        yield repo
        repo.close()
        import shutil
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
            import shutil
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
            import shutil
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
            import shutil
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
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_default_branch_returns_main_fallback_for_non_remote_repos(self, repo):
        """Test default_branch returns 'main' fallback for non-remote repos."""
        result = repo.default_branch()
        assert result == "main"

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
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_create_branch_with_slash_in_name_works(self, repo):
        """Test create_branch with slash in name works (e.g., 'feature/test')."""
        result = repo.create_branch("feature/test")
        assert result == "feature/test"
        assert repo.current_branch() == "feature/test"


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
        import shutil
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
        import shutil
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