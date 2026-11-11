"""Git operations wrapper for the EDCoPilot custom speech content skill.

Provides a safe GitRepo class for commit/diff/status operations that handles
non-repo paths gracefully with warnings instead of exceptions.
"""

import warnings
import atexit
import re
import time
from pathlib import Path
from typing import Optional

from git import Repo, InvalidGitRepositoryError, GitCommandError
from git.exc import NoSuchPathError

_BRANCH_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-/]*$")


def slugify_branch_name(description: str | None = None) -> str:
    """Generate a branch name from an optional description.

    Lowercases, replaces spaces/special chars with hyphens, strips
    leading/trailing hyphens, prefixes with ``gen/``. Appends a short
    timestamp (Unix epoch seconds) if no description is given.
    """
    if description:
        slug = re.sub(r"[^a-z0-9]+", "-", description.lower()).strip("-")
        if not slug:
            slug = "change"
        return f"gen/{slug}"
    return f"gen/{int(time.time())}"


class GitRepo:
    """Safe wrapper around git operations.

    All methods handle non-repo paths gracefully by returning empty/no-op
    results and emitting a warning instead of raising exceptions.
    """

    # Track all repo instances for cleanup on exit (Windows file handle issue)
    _instances: list["GitRepo"] = []

    def __init__(self, path: Path):
        """Initialize GitRepo for the given path.

        Args:
            path: Path to the git repository (or directory that should be a repo).
        """
        self.path = Path(path).resolve()
        self._repo: Optional[Repo] = None
        self._is_valid_repo = False
        self._init_repo()
        GitRepo._instances.append(self)

    def _init_repo(self) -> None:
        """Initialize the internal Repo object if path is a valid git repo."""
        try:
            self._repo = Repo(self.path, search_parent_directories=False)
            self._is_valid_repo = True
        except (InvalidGitRepositoryError, NoSuchPathError):
            self._repo = None
            self._is_valid_repo = False

    def close(self) -> None:
        """Close the repo and release file handles (important on Windows)."""
        if self._repo is not None:
            try:
                self._repo.close()
            except Exception:
                pass
            self._repo = None
        if self in GitRepo._instances:
            GitRepo._instances.remove(self)

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.close()

    @classmethod
    def _cleanup_all(cls) -> None:
        """Clean up all repo instances (called on exit)."""
        for instance in cls._instances[:]:
            instance.close()

    @classmethod
    def init(cls, path: Path) -> "GitRepo":
        """Initialize a new git repository at the given path.

        Args:
            path: Path where the new repository should be created.

        Returns:
            GitRepo instance for the newly created repository.
        """
        path = Path(path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        Repo.init(path)
        return cls(path)

    @classmethod
    def is_repo(cls, path: Path) -> bool:
        """Check if the given path is a valid git repository.

        Args:
            path: Path to check.

        Returns:
            True if path is a git repository, False otherwise.
        """
        try:
            Repo(Path(path).resolve(), search_parent_directories=False)
            return True
        except (InvalidGitRepositoryError, NoSuchPathError):
            return False

    def _warn_not_repo(self, operation: str) -> None:
        """Emit a warning that the path is not a git repository."""
        warnings.warn(
            f"GitRepo.{operation}() called on path that is not a git repository: {self.path}",
            UserWarning,
            stacklevel=3,
        )

    def _require_repo(self, operation: str) -> Optional[Repo]:
        """Check if we have a valid repo, warn and return None if not."""
        if not self._is_valid_repo or self._repo is None:
            self._warn_not_repo(operation)
            return None
        return self._repo

    def _has_head(self) -> bool:
        """Check if the repository has at least one commit (HEAD exists)."""
        if self._repo is None:
            return False
        try:
            self._repo.head.commit
            return True
        except ValueError:
            return False

    def _run_git(self, *args: str) -> str:
        """Run a git command and return stdout.

        This is a low-level method for internal use and testing.
        """
        if self._repo is None:
            return ""
        try:
            return self._repo.git.execute(["git"] + list(args), with_extended_output=False)
        except GitCommandError:
            return ""

    def status(self) -> dict[str, list[str] | bool]:
        """Get repository status.

        Returns:
            Dict with keys: 'staged', 'unstaged', 'untracked' (lists of file paths),
            and 'clean' (bool indicating if working tree is clean).
            Returns empty status with clean=True for non-repos.
        """
        repo = self._require_repo("status")
        if repo is None:
            return {"staged": [], "unstaged": [], "untracked": [], "clean": True}

        try:
            has_head = self._has_head()

            if has_head:
                # Get staged changes (index vs HEAD)
                staged = [item.a_path for item in repo.index.diff("HEAD")]

                # Get unstaged changes (working tree vs index)
                unstaged = [item.a_path for item in repo.index.diff(None)]
            else:
                # No commits yet: staged = everything in index (extract paths from tuples)
                staged = [entry[0] for entry in repo.index.entries.keys()]
                unstaged = []

            # Get untracked files
            untracked = repo.untracked_files

            return {
                "staged": staged,
                "unstaged": unstaged,
                "untracked": untracked,
                "clean": len(staged) == 0 and len(unstaged) == 0 and len(untracked) == 0,
            }
        except GitCommandError:
            # Fallback
            untracked = repo.untracked_files
            return {
                "staged": [],
                "unstaged": [],
                "untracked": untracked,
                "clean": len(untracked) == 0,
            }

    def diff(self, staged: bool = False) -> str:
        """Get diff output for unstaged (or staged) changes.

        Args:
            staged: If True, show staged changes (index vs HEAD).
                    If False (default), show unstaged changes (working tree vs index).

        Returns:
            Diff output as string, empty string for non-repos or no changes.
        """
        repo = self._require_repo("diff")
        if repo is None:
            return ""

        try:
            if staged:
                if self._has_head():
                    return repo.git.diff("--cached")
                else:
                    # No HEAD yet, show staged content
                    return repo.git.diff("--cached")
            else:
                if self._has_head():
                    return repo.git.diff()
                else:
                    # No HEAD yet, no unstaged diff meaningful
                    return ""
        except GitCommandError:
            return ""

    def add_all(self) -> None:
        """Stage all changes (new, modified, deleted files).

        No-op with warning for non-repos.
        """
        repo = self._require_repo("add_all")
        if repo is None:
            return

        try:
            repo.git.add(A=True)
        except GitCommandError:
            pass

    def commit(self, message: str) -> Optional[str]:
        """Commit all staged changes with the given message.

        Uses the author configured in git config (user.name, user.email).

        Args:
            message: Commit message.

        Returns:
            Commit hash (short) if commit was created, None if nothing to commit
            or if not a repository.
        """
        repo = self._require_repo("commit")
        if repo is None:
            return None

        try:
            has_head = self._has_head()

            if has_head:
                # Check if there's anything staged to commit
                staged = [item.a_path for item in repo.index.diff("HEAD")]
                if not staged:
                    return None
            else:
                # No commits yet: check if index has anything
                if len(list(repo.index.entries.keys())) == 0:
                    return None

            commit = repo.index.commit(message)
            return commit.hexsha[:8]
        except (GitCommandError, ValueError):
            # No HEAD (no commits yet) or hook issues — retry if index has entries
            try:
                if len(list(repo.index.entries.keys())) > 0:
                    commit = repo.index.commit(message)
                    return commit.hexsha[:8]
            except (GitCommandError, ValueError):
                pass
            return None

    def log(self, n: int = 10) -> list[str]:
        """Get recent commit messages.

        Args:
            n: Maximum number of commits to return (default 10).

        Returns:
            List of commit message strings (most recent first).
            Empty list for non-repos.
        """
        repo = self._require_repo("log")
        if repo is None:
            return []

        try:
            if not self._has_head():
                return []
            commits = list(repo.iter_commits(max_count=n))
            return [commit.summary for commit in commits]
        except (GitCommandError, ValueError):
            # ValueError can occur if there are no commits
            return []

    @staticmethod
    def _validate_branch_name(name: str) -> None:
        """Validate a branch name.

        Raises:
            ValueError: If the name contains spaces or disallowed characters.
        """
        if not name or not _BRANCH_NAME_RE.match(name):
            raise ValueError(f"Invalid branch name: {name!r}")

    def create_branch(self, name: str) -> Optional[str]:
        """Create and check out a new branch (git checkout -b).

        Args:
            name: Branch name (validated).

        Returns:
            The branch name if created, None if not a repo or command failed.
        """
        repo = self._require_repo("create_branch")
        if repo is None:
            return None
        self._validate_branch_name(name)

        try:
            repo.git.checkout("-b", name)
            return name
        except GitCommandError:
            return None

    def checkout(self, branch: str) -> None:
        """Switch to an existing branch."""
        repo = self._require_repo("checkout")
        if repo is None:
            return None
        self._validate_branch_name(branch)

        try:
            repo.git.checkout(branch)
        except GitCommandError:
            pass
        return None

    def merge(self, branch: str) -> Optional[str]:
        """Merge the given branch into the current branch.

        Returns:
            Merge commit hash (short) if successful, None otherwise.
        """
        repo = self._require_repo("merge")
        if repo is None:
            return None
        self._validate_branch_name(branch)

        try:
            repo.git.merge(branch)
            return repo.head.commit.hexsha[:8]
        except GitCommandError:
            return None

    def push(self, remote: str = "origin") -> Optional[bool]:
        """Push the current branch to the given remote.

        Returns:
            True when the push succeeded, False when git refused it (for
            example there is no such remote), and None for a non-repository.
            Callers report the outcome instead of assuming success.
        """
        repo = self._require_repo("push")
        if repo is None:
            return None

        try:
            repo.git.push(remote)
            return True
        except GitCommandError:
            return False

    def current_branch(self) -> str:
        """Return the current branch name, or '' if detached/not a repo."""
        repo = self._require_repo("current_branch")
        if repo is None:
            return ""

        try:
            return repo.active_branch.name
        except Exception:
            return ""

    def list_branches(self) -> list[str]:
        """Return all local branch names."""
        repo = self._require_repo("list_branches")
        if repo is None:
            return []

        try:
            return [head.name for head in repo.heads]
        except Exception:
            return []

    def default_branch(self) -> str:
        """Detect the repository's default branch via symbolic-ref.

        Falls back to 'main' if detection fails.
        """
        repo = self._require_repo("default_branch")
        if repo is None:
            return "main"

        try:
            ref = repo.git.symbolic_ref("refs/remotes/origin/HEAD")
            return ref.strip().split("/")[-1] or "main"
        except Exception:
            return "main"


# Register cleanup on exit to avoid Windows file handle issues
atexit.register(GitRepo._cleanup_all)