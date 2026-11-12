"""Tests for markdb_add / markdb_remove in the content layer.

Ported from the old `tests/test_tool_markdb.py`: the calls are sync and the
config is supplied through the environment (the content layer resolves roots
lazily per call). No gate/pause case existed in the old suite.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from edcg.content.markdb import markdb_add, markdb_remove


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout


# ============================================================
# Test fixtures
# ============================================================

SAMPLE_CUSTOM_CONTENT = """@SystemGreeting<~>Test System
Welcome to Test System, <Commander>!
[<Foreman>](allbusiness) Welcome to Test System, <Commander>!

@StationGreeting<~>Test System<~>Primary Station (ii-42)
Docking complete at Primary Station.
[<Welder>](allbusiness) Docking complete at Primary Station.

@StationFact<~>Test System<~>Primary Station (ii-42)
img_url=https://example.com/logo.png
Primary Station
This station was built by Raven Colonial.

@StationChatter<~>Test System<~>Primary Station (ii-42)
[<Foreman>] Just another day at Primary Station.
[<Welder>](allbusiness) Still welding, still building.
"""

SAMPLE_CUSTOM_CONTENT_WITH_UPDATEDB = """@SystemGreeting<~>Test System
UPDATEDB
Welcome to Test System, <Commander>!
[<Foreman>](allbusiness) Welcome to Test System, <Commander>!

@StationGreeting<~>Test System<~>Primary Station (ii-42)
UPDATEDB
Docking complete at Primary Station.
[<Welder>](allbusiness) Docking complete at Primary Station.

@StationFact<~>Test System<~>Primary Station (ii-42)
img_url=https://example.com/logo.png
Primary Station
This station was built by Raven Colonial.

@StationChatter<~>Test System<~>Primary Station (ii-42)
[<Foreman>] Just another day at Primary Station.
[<Welder>](allbusiness) Still welding, still building.
"""


@pytest.fixture
def temp_edcopilot_root():
    """Create a temporary git repo for EDCoPilot root."""
    tmpdir = tempfile.mkdtemp()
    repo_path = Path(tmpdir) / "edcopilot_root"
    repo_path.mkdir(parents=True)

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, capture_output=True)

    # Create initial commit so repo has HEAD
    readme = repo_path / "README.md"
    readme.write_text("# Test EDCoPilot Root")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, capture_output=True)

    # Create the target file with sample content
    custom_file = repo_path / "EDCoPilot.SpeechExtensions.Custom.txt"
    custom_file.write_text(SAMPLE_CUSTOM_CONTENT, encoding="utf-8", newline="\r\n")
    subprocess.run(["git", "add", "EDCoPilot.SpeechExtensions.Custom.txt"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial content"], cwd=repo_path, check=True, capture_output=True)

    yield repo_path

    # Cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def temp_edcopilot_root_with_markers():
    """Create a temporary git repo for EDCoPilot root with UPDATEDB markers already present."""
    tmpdir = tempfile.mkdtemp()
    repo_path = Path(tmpdir) / "edcopilot_root"
    repo_path.mkdir(parents=True)

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, capture_output=True)

    # Create initial commit so repo has HEAD
    readme = repo_path / "README.md"
    readme.write_text("# Test EDCoPilot Root")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, capture_output=True)

    # Create the target file with sample content WITH markers
    custom_file = repo_path / "EDCoPilot.SpeechExtensions.Custom.txt"
    custom_file.write_text(SAMPLE_CUSTOM_CONTENT_WITH_UPDATEDB, encoding="utf-8", newline="\r\n")
    subprocess.run(["git", "add", "EDCoPilot.SpeechExtensions.Custom.txt"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial content with markers"], cwd=repo_path, check=True, capture_output=True)

    yield repo_path

    # Cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def mock_config(temp_edcopilot_root, monkeypatch):
    """Point the content layer at the temp EDCoPilot root (env-based config)."""
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(temp_edcopilot_root))
    monkeypatch.setenv("EDCG_AUTO_COMMIT", "true")
    # Return just the path, since Config no longer has edcopilot_root field
    return temp_edcopilot_root


@pytest.fixture
def mock_config_with_markers(temp_edcopilot_root_with_markers, monkeypatch):
    """As mock_config, for the fixture whose content already carries markers."""
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(temp_edcopilot_root_with_markers))
    monkeypatch.setenv("EDCG_AUTO_COMMIT", "true")
    return temp_edcopilot_root_with_markers


# ============================================================
# Tests for markdb_add
# ============================================================

class TestMarkdbAddTool:
    """Tests for markdb_add content layer function."""

    def test_markdb_add_adds_marker_to_existing_tag(self, mock_config):
        """Test that markdb_add adds UPDATEDB marker after a tag."""
        result = markdb_add(
            tags=["@SystemGreeting<~>Test System"],
        )

        # Should return a result with modified tags and commit hashes
        assert isinstance(result, dict)
        assert "modified_tags" in result
        assert "commit_hashes" in result
        assert "@SystemGreeting<~>Test System" in result["modified_tags"]
        assert len(result["commit_hashes"]) == 1
        assert result["commit_hashes"][0] is not None

        # File should have UPDATEDB marker added
        custom_file = mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        content = custom_file.read_text(encoding="utf-8")

        # Find the tag line and verify UPDATEDB is on the next line
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if line.strip() == "@SystemGreeting<~>Test System":
                assert i + 1 < len(lines)
                assert lines[i + 1].strip() == "UPDATEDB"
                break
        else:
            pytest.fail("Tag @SystemGreeting<~>Test System not found in file")

    def test_markdb_add_multiple_tags(self, mock_config):
        """Test that markdb_add can add markers to multiple tags at once."""
        tags_to_mark = [
            "@SystemGreeting<~>Test System",
            "@StationGreeting<~>Test System<~>Primary Station (ii-42)",
        ]

        result = markdb_add(tags=tags_to_mark)

        assert isinstance(result, dict)
        assert "modified_tags" in result
        assert "commit_hashes" in result
        assert set(result["modified_tags"]) == set(tags_to_mark)
        assert len(result["commit_hashes"]) == 1  # One commit for the whole pass

        # File should have UPDATEDB markers for both tags
        custom_file = mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        content = custom_file.read_text(encoding="utf-8")
        lines = content.splitlines()

        for tag in tags_to_mark:
            found = False
            for i, line in enumerate(lines):
                if line.strip() == tag:
                    assert i + 1 < len(lines), f"No line after tag {tag}"
                    assert lines[i + 1].strip() == "UPDATEDB", f"UPDATEDB not found after {tag}"
                    found = True
                    break
            assert found, f"Tag {tag} not found in file"

    def test_markdb_add_idempotent_on_existing_marker(self, mock_config_with_markers):
        """Test that markdb_add is idempotent - doesn't add duplicate markers."""
        result = markdb_add(
            tags=["@SystemGreeting<~>Test System"],
        )

        # Should still succeed but not create duplicate markers
        assert isinstance(result, dict)
        assert "@SystemGreeting<~>Test System" in result["modified_tags"]

        # File should still have only one UPDATEDB marker
        custom_file = mock_config_with_markers / "EDCoPilot.SpeechExtensions.Custom.txt"
        content = custom_file.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Count UPDATEDB markers after the tag
        marker_count = 0
        for i, line in enumerate(lines):
            if line.strip() == "@SystemGreeting<~>Test System":
                # Check consecutive UPDATEDB lines
                j = i + 1
                while j < len(lines) and lines[j].strip() == "UPDATEDB":
                    marker_count += 1
                    j += 1
                break

        assert marker_count == 1, f"Expected 1 UPDATEDB marker, found {marker_count}"

    def test_markdb_add_creates_one_commit_for_all_tags(self, mock_config):
        """Two markers are one write and one commit."""
        before = int(_git(mock_config, "rev-list", "--count", "HEAD"))

        result = markdb_add(
            tags=[
                "@SystemGreeting<~>Test System",
                "@StationGreeting<~>Test System<~>Primary Station (ii-42)",
            ],
        )

        assert len(result["commit_hashes"]) == 1
        assert result["commit_hashes"][0] is not None
        after = int(_git(mock_config, "rev-list", "--count", "HEAD"))
        assert after == before + 1

        subject = _git(mock_config, "log", "-1", "--format=%s").strip()
        assert subject == "edcg: markdb add 2 tags"
        body = _git(mock_config, "log", "-1", "--format=%B")
        assert "@SystemGreeting<~>Test System" in body
        assert "@StationGreeting<~>Test System<~>Primary Station (ii-42)" in body

    def test_markdb_add_appends_co_author_trailer(self, mock_config):
        """The single marker commit carries the trailer."""
        co_author = "🤖 Test Harness (Model One, Model Two) <noreply@example.com>"
        result = markdb_add(
            tags=[
                "@SystemGreeting<~>Test System",
                "@StationGreeting<~>Test System<~>Primary Station (ii-42)",
            ],
            commit_co_author=co_author,
        )

        assert len(result["commit_hashes"]) == 1
        body = _git(
            mock_config, "log", "-1", result["commit_hashes"][0],
            "--format=%B",
        )
        assert f"Co-authored-by: {co_author}" in body

    def test_markdb_add_idempotent_call_makes_no_second_commit(self, mock_config):
        """A second call for already-marked tags returns no new hash."""
        tags = ["@SystemGreeting<~>Test System"]
        first = markdb_add(tags=tags)
        second = markdb_add(tags=tags)

        assert len(first["commit_hashes"]) == 1
        assert second["modified_tags"] == tags
        assert second["commit_hashes"] == []

    def test_markdb_add_keeps_tag_intact_without_final_newline(self, mock_config):
        """A tag as the last line must not fuse with the inserted marker."""
        custom_file = (
            mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        )
        custom_file.write_bytes(b"@SystemGreeting<~>Test System")
        _git(mock_config, "add", "-A")
        _git(mock_config, "commit", "-m", "no trailing newline")

        result = markdb_add(
            tags=["@SystemGreeting<~>Test System"],
        )

        raw = custom_file.read_bytes()
        assert b"Test SystemUPDATEDB" not in raw
        assert b"\r\r\n" not in raw
        lines = custom_file.read_text(encoding="utf-8").splitlines()
        i = lines.index("@SystemGreeting<~>Test System")
        assert lines[i + 1] == "UPDATEDB"
        assert len(result["commit_hashes"]) == 1

    def test_markdb_add_preserves_other_content(self, mock_config):
        """Test that markdb_add doesn't modify other content in the file."""
        result = markdb_add(
            tags=["@SystemGreeting<~>Test System"],
        )

        custom_file = mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        content = custom_file.read_text(encoding="utf-8")

        # All original content should still be there
        assert "Welcome to Test System, <Commander>!" in content
        assert "Docking complete at Primary Station." in content
        assert "Primary Station" in content
        assert "This station was built by Raven Colonial." in content
        assert "Just another day at Primary Station." in content
        assert "Still welding, still building." in content

        # Other tags should not have markers added
        assert "UPDATEDB" not in content.split("@StationGreeting<~>Test System<~>Primary Station (ii-42)")[1].split("@")[0]
        assert "UPDATEDB" not in content.split("@StationFact<~>Test System<~>Primary Station (ii-42)")[1].split("@")[0]
        assert "UPDATEDB" not in content.split("@StationChatter<~>Test System<~>Primary Station (ii-42)")[1].split("@")[0]


# ============================================================
# Tests for markdb_remove
# ============================================================

class TestMarkdbRemoveTool:
    """Tests for markdb_remove content layer function."""

    def test_markdb_remove_removes_marker(self, mock_config_with_markers):
        """Test that markdb_remove removes UPDATEDB marker after a tag."""
        result = markdb_remove(
            tags=["@SystemGreeting<~>Test System"],
        )

        assert isinstance(result, dict)
        assert "modified_tags" in result
        assert "commit_hashes" in result
        assert "@SystemGreeting<~>Test System" in result["modified_tags"]
        assert len(result["commit_hashes"]) == 1

        # File should no longer have UPDATEDB marker for that tag
        custom_file = mock_config_with_markers / "EDCoPilot.SpeechExtensions.Custom.txt"
        content = custom_file.read_text(encoding="utf-8")
        lines = content.splitlines()

        for i, line in enumerate(lines):
            if line.strip() == "@SystemGreeting<~>Test System":
                assert i + 1 < len(lines)
                assert lines[i + 1].strip() != "UPDATEDB", "UPDATEDB marker should have been removed"
                break
        else:
            pytest.fail("Tag @SystemGreeting<~>Test System not found in file")

    def test_markdb_remove_multiple_tags(self, mock_config_with_markers):
        """Test that markdb_remove can remove markers from multiple tags."""
        tags_to_unmark = [
            "@SystemGreeting<~>Test System",
            "@StationGreeting<~>Test System<~>Primary Station (ii-42)",
        ]

        result = markdb_remove(tags=tags_to_unmark)

        assert isinstance(result, dict)
        assert set(result["modified_tags"]) == set(tags_to_unmark)
        assert len(result["commit_hashes"]) == 1

        # File should no longer have UPDATEDB markers for those tags
        custom_file = mock_config_with_markers / "EDCoPilot.SpeechExtensions.Custom.txt"
        content = custom_file.read_text(encoding="utf-8")
        lines = content.splitlines()

        for tag in tags_to_unmark:
            found = False
            for i, line in enumerate(lines):
                if line.strip() == tag:
                    assert i + 1 < len(lines), f"No line after tag {tag}"
                    assert lines[i + 1].strip() != "UPDATEDB", f"UPDATEDB still present after {tag}"
                    found = True
                    break
            assert found, f"Tag {tag} not found in file"

    def test_markdb_remove_idempotent_on_missing_marker(self, mock_config):
        """Test that markdb_remove is idempotent - doesn't fail if marker not present."""
        result = markdb_remove(
            tags=["@SystemGreeting<~>Test System"],
        )

        # Should still succeed
        assert isinstance(result, dict)
        assert "@SystemGreeting<~>Test System" in result["modified_tags"]

        # File should be unchanged (no marker was there to remove)
        custom_file = mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        content = custom_file.read_text(encoding="utf-8")
        lines = content.splitlines()

        for i, line in enumerate(lines):
            if line.strip() == "@SystemGreeting<~>Test System":
                assert i + 1 < len(lines)
                assert lines[i + 1].strip() != "UPDATEDB"
                break

    def test_markdb_remove_creates_one_commit_for_all_tags(self, mock_config_with_markers):
        """Two marker removals are one write and one commit."""
        before = int(
            _git(mock_config_with_markers, "rev-list", "--count", "HEAD")
        )

        result = markdb_remove(
            tags=[
                "@SystemGreeting<~>Test System",
                "@StationGreeting<~>Test System<~>Primary Station (ii-42)",
            ],
        )

        assert len(result["commit_hashes"]) == 1
        after = int(
            _git(mock_config_with_markers, "rev-list", "--count", "HEAD")
        )
        assert after == before + 1

        subject = _git(
            mock_config_with_markers, "log", "-1", "--format=%s"
        ).strip()
        assert subject == "edcg: markdb remove 2 tags"

    def test_markdb_remove_appends_co_author_trailer(self, mock_config_with_markers):
        """The single marker removal commit carries the trailer."""
        co_author = "🤖 Test Harness (Model One, Model Two) <noreply@example.com>"
        result = markdb_remove(
            tags=["@SystemGreeting<~>Test System", "@StationGreeting<~>Test System<~>Primary Station (ii-42)"],
            commit_co_author=co_author,
        )

        assert len(result["commit_hashes"]) == 1
        body = _git(
            mock_config_with_markers,
            "log", "-1", result["commit_hashes"][0], "--format=%B",
        )
        assert f"Co-authored-by: {co_author}" in body


# ============================================================
# Round-trip tests
# ============================================================

class TestMarkdbRoundTrip:
    """Tests for add/remove round-trip preserving content."""

    def test_add_then_remove_preserves_content(self, mock_config):
        """Test that add then remove preserves all original content."""
        # Capture original content
        custom_file = mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        original_content = custom_file.read_text(encoding="utf-8")

        tags = ["@SystemGreeting<~>Test System", "@StationGreeting<~>Test System<~>Primary Station (ii-42)"]

        # Add markers
        markdb_add(tags=tags)

        # Remove markers
        markdb_remove(tags=tags)

        # Content should be identical to original (except for provenance/git metadata)
        final_content = custom_file.read_text(encoding="utf-8")

        # Normalize line endings for comparison
        original_normalized = original_content.replace("\r\n", "\n")
        final_normalized = final_content.replace("\r\n", "\n")

        assert final_normalized == original_normalized, "Round-trip did not preserve content"

    def test_remove_then_add_preserves_content(self, mock_config_with_markers):
        """Test that remove then add preserves all original content."""
        # Capture original content
        custom_file = mock_config_with_markers / "EDCoPilot.SpeechExtensions.Custom.txt"
        original_content = custom_file.read_text(encoding="utf-8")

        tags = ["@SystemGreeting<~>Test System", "@StationGreeting<~>Test System<~>Primary Station (ii-42)"]

        # Remove markers
        markdb_remove(tags=tags)

        # Add markers back
        markdb_add(tags=tags)

        # Content should be identical to original
        final_content = custom_file.read_text(encoding="utf-8")

        original_normalized = original_content.replace("\r\n", "\n")
        final_normalized = final_content.replace("\r\n", "\n")

        assert final_normalized == original_normalized, "Round-trip did not preserve content"


# ============================================================
# Edge case tests
# ============================================================

class TestMarkdbEdgeCases:
    """Tests for edge cases."""

    def test_markdb_add_tag_not_found(self, mock_config):
        """Test that markdb_add handles missing tags gracefully."""
        result = markdb_add(
            tags=["@NonExistentTag<~>NonExistent System"],
        )

        # Should not include the missing tag in modified_tags
        assert "@NonExistentTag<~>NonExistent System" not in result.get("modified_tags", [])
        # Should not create commits for missing tags
        assert len(result.get("commit_hashes", [])) == 0

    def test_markdb_remove_tag_not_found(self, mock_config):
        """Test that markdb_remove handles missing tags gracefully."""
        result = markdb_remove(
            tags=["@NonExistentTag<~>NonExistent System"],
        )

        # Should not include the missing tag in modified_tags
        assert "@NonExistentTag<~>NonExistent System" not in result.get("modified_tags", [])
        assert len(result.get("commit_hashes", [])) == 0

    def test_markdb_add_preserves_crlf(self, mock_config):
        """Test that markdb_add preserves CRLF line endings."""
        markdb_add(tags=["@SystemGreeting<~>Test System"])

        custom_file = mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        raw_bytes = custom_file.read_bytes()

        # Should use CRLF line endings
        assert b"\r\n" in raw_bytes

    def test_markdb_remove_preserves_crlf(self, mock_config_with_markers):
        """Test that markdb_remove preserves CRLF line endings."""
        markdb_remove(tags=["@SystemGreeting<~>Test System"])

        custom_file = mock_config_with_markers / "EDCoPilot.SpeechExtensions.Custom.txt"
        raw_bytes = custom_file.read_bytes()

        # Should use CRLF line endings
        assert b"\r\n" in raw_bytes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
