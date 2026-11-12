"""Plain helpers shared by the hermetic test suite.

Pytest fixtures cannot be called from module-level helper functions, so the
git plumbing lives here. ``tests/conftest.py`` re-exports it as fixtures where
a fixture reads better, and the test modules import it directly where a helper
already wraps the call.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(repo: Path, *args: str) -> str:
    """Run git in *repo* and return its stdout, raising on a non-zero exit."""
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def init_repo(root: Path) -> Path:
    """Initialise *root* as a git repository with a configured identity."""
    from edcg.repo.gitrepo import GitRepo

    root.mkdir(parents=True, exist_ok=True)
    GitRepo.init(root).close()
    run_git(root, "config", "user.name", "Test User")
    run_git(root, "config", "user.email", "test@example.com")
    return root


def commit_all(root: Path, message: str) -> None:
    """Stage everything in *root* and commit it."""
    run_git(root, "add", "-A")
    run_git(root, "commit", "-m", message)


def seed_repo(
    root: Path,
    files: dict[str, str] | None = None,
    message: str = "initial",
) -> Path:
    """Create a repository at *root* with an identity and one commit.

    ``files`` maps repository-relative paths to their text; a README is written
    when none are given, because git refuses to commit an empty tree.
    """
    init_repo(root)
    for relative, text in (files or {"README.md": "# Test\n"}).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    commit_all(root, message)
    return root
