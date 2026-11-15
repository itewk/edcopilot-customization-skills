"""Git operations wrapper for the EDCoPilot custom speech content skill.

Provides a safe GitRepo class for commit/diff/status operations that handles
non-repo paths gracefully with warnings instead of exceptions.
"""

import warnings
import re
import time
from pathlib import Path
from typing import Optional, Self

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

    def __init__(self, path: Path):
        """Initialize GitRepo for the given path.

        Args:
            path: Path to the git repository (or directory that should be a repo).
        """
        self.path = Path(path).resolve()
        self._repo: Optional[Repo] = None
        self._is_valid_repo = False
        self._init_repo()

    def _init_repo(self) -> None:
        """Initialize the internal Repo object if path is a valid git repo."""
        try:
            self._repo = Repo(self.path, search_parent_directories=False)
            self._is_valid_repo = True
        except (InvalidGitRepositoryError, NoSuchPathError):
            self._repo = None
            self._is_valid_repo = False

    def close(self) -> None:
        """Close the repo and release file handles (important on Windows).

        Idempotent: closing twice is safe, so ``with`` blocks and explicit
        calls can coexist.
        """
        if self._repo is not None:
            try:
                self._repo.close()
            except Exception:
                pass
            self._repo = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

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

    def diff_stat(self, ref: str | None = None) -> dict[str, list[str] | int]:
        """Summarise a diff as changed files plus added/removed line counts.

        Args:
            ref: Branch to compare against. The summary then covers the commits
                 on HEAD since it diverged from ``ref`` (``ref...HEAD``). With
                 ``ref=None`` it covers the working tree and includes untracked
                 file names, so a review counts the same changes ``status()``
                 shows.

        Returns:
            ``{"files": sorted names, "insertions": int, "deletions": int}``.
            Empty zeroed summary for non-repos or when git refuses the diff.
        """
        repo = self._require_repo("diff_stat")
        if repo is None:
            return {"files": [], "insertions": 0, "deletions": 0}

        try:
            if ref is None:
                names = repo.git.diff("--name-only").splitlines()
                names += repo.git.diff("--cached", "--name-only").splitlines()
                names += list(repo.untracked_files)
                # The working-tree patches come from this wrapper's own diff()
                # so there is one reader: it answers "" rather than the index
                # diff when HEAD does not exist yet, which is what review_branch
                # counted before the consolidation.
                patches = [self.diff(), self.diff(staged=True)]
            else:
                names = repo.git.diff(f"{ref}...HEAD", "--name-only").splitlines()
                patches = [repo.git.diff(f"{ref}...HEAD")]
        except GitCommandError:
            return {"files": [], "insertions": 0, "deletions": 0}

        insertions = 0
        deletions = 0
        for patch in patches:
            for line in patch.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    insertions += 1
                elif line.startswith("-") and not line.startswith("---"):
                    deletions += 1

        return {
            "files": sorted({name for name in names if name}),
            "insertions": insertions,
            "deletions": deletions,
        }

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

    def add(self, *paths: str) -> None:
        """Stage only the named paths (relative to the repository root).

        Unlike :meth:`add_all` this leaves unrelated untracked files alone, so
        scaffolding in an existing repository cannot sweep them into a commit.
        No-op with warning for non-repos.
        """
        repo = self._require_repo("add")
        if repo is None:
            return

        try:
            repo.git.add(*[str(path) for path in paths])
        except GitCommandError:
            pass

    def is_untracked(self, path: str | Path) -> bool:
        """Check whether a path is untracked inside this repository.

        Git reports paths with forward slashes, so a Windows ``Path`` is
        normalised with ``as_posix()`` before it is compared with
        :meth:`status`'s untracked list. Paths outside the repository, and any
        path in a non-repository, are reported as not untracked.

        Args:
            path: Path to check (relative to the repository root or absolute).

        Returns:
            True when the path exists inside this repository, is not tracked,
            and is not ignored; False otherwise.
        """
        repo = self._require_repo("is_untracked")
        if repo is None:
            return False

        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.path / candidate

        try:
            relative = candidate.resolve().relative_to(self.path.resolve())
        except ValueError:
            return False

        return relative.as_posix() in self.status()["untracked"]

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

    def commit_files(self, rev: str = "HEAD") -> list[str]:
        """Return the repository-relative paths one commit actually changed.

        The names come from ``git show --name-only --format=``, so they are what
        git recorded rather than what a caller intended to stage: an ``add``
        that git refused cannot inflate the list. Git reports paths with
        forward slashes on every platform, so the result uses posix separators,
        sorted for a stable report. ``core.quotepath=false`` keeps a non-ASCII
        name readable instead of git's default quoted octal escapes.

        Args:
            rev: Revision to inspect (a commit hash, ``HEAD``, or anything else
                git accepts).

        Returns:
            Sorted posix paths, or an empty list for a non-repository or a
            revision git cannot read.
        """
        repo = self._require_repo("commit_files")
        if repo is None:
            return []

        try:
            names = repo.git(c="core.quotepath=false").show(
                "--name-only", "--format=", rev
            ).splitlines()
        except GitCommandError:
            return []
        return sorted({name.strip() for name in names if name.strip()})

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

        A conflicted merge is left in place for the caller to resolve or abort
        with :meth:`abort_merge`; this method never decides that for it.

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

    def abort_merge(self) -> None:
        """Abort an in-progress merge, restoring the pre-merge working tree."""
        repo = self._require_repo("abort_merge")
        if repo is None:
            return

        try:
            repo.git.merge("--abort")
        except GitCommandError:
            pass

    def delete_branch(self, name: str) -> bool:
        """Force-delete a local branch.

        Returns:
            True when git deleted the branch, False otherwise (including a
            branch that cannot be deleted because it is checked out).
        """
        repo = self._require_repo("delete_branch")
        if repo is None:
            return False
        self._validate_branch_name(name)

        try:
            repo.git.branch("-D", name)
            return True
        except GitCommandError:
            return False

    def commits_between(self, base: str, branch: str) -> list[str]:
        """Return the summaries of commits on ``branch`` that are not on ``base``."""
        repo = self._require_repo("commits_between")
        if repo is None:
            return []

        try:
            return [commit.summary for commit in repo.iter_commits(f"{base}..{branch}")]
        except (GitCommandError, ValueError):
            return []

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
        """Detect the repository's default branch.

        Prefers a branch that exists locally (``main``, then ``master``, then
        whatever ``symbolic-ref`` names for the remote), then the first local
        branch, and finally ``main``. A repository whose default branch is its
        only branch therefore reports that branch rather than a name the
        checkout does not have.
        """
        repo = self._require_repo("default_branch")
        if repo is None:
            return "main"

        branches = self.list_branches()
        for name in ("main", "master"):
            if name in branches:
                return name

        try:
            ref = repo.git.symbolic_ref("refs/remotes/origin/HEAD")
            detected = ref.strip().split("/")[-1]
        except Exception:
            detected = ""

        if detected and detected in branches:
            return detected
        if branches:
            return branches[0]
        return detected or "main"