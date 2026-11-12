"""Shared fixtures for the hermetic test suite.

The suite builds temporary git repositories, isolates the CLI from the
developer's environment, and mocks the three network clients; those are the
shapes every test module used to re-declare for itself. Anything that can be
shared is defined once here (or in ``support.py`` when a module-level helper
needs to call it rather than a fixture).
"""

import sys
from pathlib import Path

import pytest

SKILL_SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "edcopilot-system-content" / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

from support import seed_repo  # noqa: E402


@pytest.fixture
def git_repo(tmp_path):
    """Factory for a committed repository under ``tmp_path``.

    ``git_repo(files={"README.md": "# Test\\n"})`` returns the repository path;
    the identity is configured and everything is committed as ``initial``.
    """

    def make(
        name: str = "repo",
        files: dict[str, str] | None = None,
        message: str = "initial",
    ) -> Path:
        return seed_repo(tmp_path / name, files=files, message=message)

    return make


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Run a CLI test from an empty cwd with no configured roots."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EDCG_CONTENT_DEFINITIONS_ROOT", raising=False)
    monkeypatch.delenv("EDCG_EDCOPILOT_ROOT", raising=False)
    monkeypatch.delenv("EDCG_JOURNAL_DIR", raising=False)
    return tmp_path
