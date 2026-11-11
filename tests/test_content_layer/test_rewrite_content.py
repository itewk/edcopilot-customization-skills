"""Tests for reading and rewriting a system's authored content.

Ported from the old `tests/test_tool_rewrite_content.py`: the calls are sync and
the config is supplied through the environment (the content layer resolves
roots lazily per call). No gate/pause case existed in the old suite.
"""

import subprocess
from pathlib import Path

import pytest

from edcg.content.rewrite import get_system_content, rewrite_tag


SYSTEM = "Test System"
TAG = f"@StationChatter<~>{SYSTEM}<~>Test Station (ii-42)"
FACT_TAG = f"@StationFact<~>{SYSTEM}<~>Test Station (ii-42)"

CONTENT = f"""<!-- provenance: tool=test model=test -->
{TAG}
UPDATEDB
(allbusiness)Old line one.
(allbusiness)Old line two.
(allbusiness)Old line three.
Unfiltered line four.
Extra line five.
Extra line six.
Extra line seven.


@SystemGreeting<~>{SYSTEM}
UPDATEDB
(allbusiness)Greeting one.
Greeting two.
Greeting three.
"""


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True,
        text=True, encoding="utf-8",
    )
    return result.stdout


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch):
    content_root = tmp_path / "content"
    (content_root / "systems").mkdir(parents=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    _git(runtime, "init")
    _git(runtime, "config", "user.email", "t@example.com")
    _git(runtime, "config", "user.name", "T")
    (runtime / "README.md").write_text("x", encoding="utf-8")
    _git(runtime, "add", "-A")
    _git(runtime, "commit", "-m", "init")

    custom = runtime / "EDCoPilot.SpeechExtensions.Custom.txt"
    custom.write_text(CONTENT, encoding="utf-8", newline="\r\n")

    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(content_root))
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(runtime))
    monkeypatch.setenv("EDCG_AUTO_COMMIT", "true")
    yield {"runtime": runtime, "custom": custom}


def test_get_system_content_reports_lines_and_bounds(workspace):
    data = get_system_content(SYSTEM)

    tags = {entry["tag"]: entry for entry in data["tags"]}
    assert TAG in tags
    entry = tags[TAG]
    assert entry["count"] == 7
    assert entry["min"] == 6 and entry["max"] == 12
    assert entry["occurrences"] == 1
    assert "(allbusiness)Old line one." in entry["lines"]


def test_get_system_content_counts_fact_paragraphs_not_the_title(workspace):
    workspace["custom"].write_text(
        f"<!-- provenance: tool=test model=test -->\n"
        f"{FACT_TAG}\n"
        "img_url=https://example.invalid/logo.jpg\n"
        "Test Station\n"
        "One paragraph.\n"
        "Two paragraphs.\n",
        encoding="utf-8",
        newline="\r\n",
    )

    data = get_system_content(SYSTEM)

    entry = {e["tag"]: e for e in data["tags"]}[FACT_TAG]
    assert entry["count"] == 2
    assert entry["min"] == 1
    assert entry["max"] == 3


def test_rewrite_removes_lines_and_stages_without_commit(workspace):
    """The rewrite writes the file but leaves the commit to write_content."""
    before = _git(workspace["runtime"], "rev-parse", "HEAD")

    result = rewrite_tag(
        SYSTEM, TAG, remove=["(allbusiness)Old line two."],
    )

    assert result["removed"] == 1
    assert result["commit_hash"] is None
    assert _git(workspace["runtime"], "rev-parse", "HEAD") == before
    text = workspace["custom"].read_text(encoding="utf-8")
    assert "(allbusiness)Old line two." not in text
    assert "EDCoPilot.SpeechExtensions.Custom.txt" in _git(
        workspace["runtime"], "status", "--porcelain"
    )


def test_rewrite_takes_no_commit_co_author():
    """The rewrite no longer owns a commit, so it no longer takes attribution."""
    import inspect

    parameters = inspect.signature(rewrite_tag).parameters
    assert "commit_co_author" not in parameters


def test_rewrite_refuses_a_bad_validating_edit(workspace):
    """Dropping below the minimum is refused; the file is untouched."""
    before = workspace["custom"].read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="failed validation"):
        rewrite_tag(
            SYSTEM,
            TAG,
            remove=[
                "(allbusiness)Old line one.",
                "(allbusiness)Old line two.",
                "(allbusiness)Old line three.",
            ],
        )

    assert workspace["custom"].read_text(encoding="utf-8") == before


def test_rewrite_adds_within_bounds(workspace):
    """Adding one line keeps a 6-line tag inside its 6-12 bound."""
    result = rewrite_tag(
        SYSTEM, TAG, add=["(allbusiness)Brand new line."],
    )

    assert result["added"] == 1
    text = workspace["custom"].read_text(encoding="utf-8")
    assert text.count("(allbusiness)Brand new line.") == 1


def test_edit_lands_despite_preexisting_errors(workspace):
    """Pre-existing errors do not block an edit; only introduced errors do."""
    workspace["custom"].write_text(
        f"<!-- provenance: tool=test model=test -->\n"
        f"{TAG}\n"
        "UPDATEDB\n"
        "(allbusiness)Old line one.\n"
        "(allbusiness)Old line two.\n"
        "(allbusiness)Old line three.\n"
        "Unfiltered line four.\n"
        "Extra line five.\n"
        "Extra line six.\n"
        "Extra line seven.\n"
        "\n"
        f"{FACT_TAG}\n"
        "Test Station\n"
        "One paragraph.\n",
        encoding="utf-8",
        newline="\r\n",
    )

    # The StationFact above has no img_url line: a pre-existing error.
    result = rewrite_tag(
        SYSTEM, TAG, remove=["(allbusiness)Old line two."],
    )

    assert result["removed"] == 1
    text = workspace["custom"].read_text(encoding="utf-8")
    assert "(allbusiness)Old line two." not in text

    # An edit that introduces an error is still refused, and writes nothing.
    with pytest.raises(ValueError, match="failed validation"):
        rewrite_tag(
            SYSTEM,
            TAG,
            remove=[
                "(allbusiness)Old line one.",
                "(allbusiness)Old line three.",
                "Unfiltered line four.",
            ],
        )
    assert workspace["custom"].read_text(encoding="utf-8") == text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
