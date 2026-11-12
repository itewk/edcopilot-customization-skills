"""Tests for the write_content function in the content layer.

Ported from the old `tests/test_tool_write_content.py`: the calls are sync and
the config is supplied through the environment (the content layer resolves
roots lazily per call). No gate/pause case existed in the old suite.
"""

import subprocess

import pytest

from edcg.content.custom_file import write_content
from support import run_git


# ============================================================
# Test fixtures
# ============================================================

EXISTING_CUSTOM_CONTENT = (
    "# EDCoPilot Speech Extensions\n\n"
    "<!-- provenance: edcopilot_customization_generator 0.1.0 — TestModel — 2024-01-01T00:00:00 -->\n\n"
    "@ExistingTag <~> Existing System\n"
    "[<Voice>] Existing content.\n"
)

SAMPLE_CONTENT_BLOCK = """@SystemGreeting<~>Test System
[<Foreman>] Welcome to Test System, <Commander>!
[<Foreman>](allbusiness) Welcome to Test System, <Commander>!

@StationGreeting<~>Test System<~>Primary Improbable Discoveries (ii-42)
[<Welder>] Docking complete at Primary Improbable Discoveries.
[<Welder>](allbusiness) Docking complete at Primary Improbable Discoveries.

@StationFact<~>Test System<~>Primary Improbable Discoveries (ii-42)
img_url=https://example.com/logo.png
Primary Improbable Discoveries
This station was built by Raven Colonial.
"""

SAMPLE_CONTENT_BLOCK_NO_PROVENANCE = SAMPLE_CONTENT_BLOCK  # Same but without provenance marker


class TestWriteContentTool:
    """Tests for write_content content layer function."""

    @pytest.fixture
    def temp_edcopilot_root(self, git_repo):
        """A committed EDCoPilot root with the custom file in place."""
        repo_path = git_repo(files={"README.md": "# Test EDCoPilot Root"})
        custom_file = repo_path / "EDCoPilot.SpeechExtensions.Custom.txt"
        custom_file.write_text(
            EXISTING_CUSTOM_CONTENT, encoding="utf-8", newline="\r\n"
        )
        run_git(repo_path, "add", "-A")
        run_git(repo_path, "commit", "-m", "Initial content")
        return repo_path

    @pytest.fixture
    def temp_edcopilot_root_no_git(self, tmp_path):
        """A plain EDCoPilot root (no git) with the custom file in place."""
        repo_path = tmp_path / "edcopilot_root"
        repo_path.mkdir()
        (repo_path / "EDCoPilot.SpeechExtensions.Custom.txt").write_text(
            EXISTING_CUSTOM_CONTENT, encoding="utf-8", newline="\r\n"
        )
        return repo_path

    @pytest.fixture
    def mock_config(self, temp_edcopilot_root, monkeypatch):
        """Point the content layer at the temp EDCoPilot root (env-based config)."""
        monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(temp_edcopilot_root))
        monkeypatch.setenv("EDCG_AUTO_COMMIT", "true")
        # Return just the path, since Config no longer has edcopilot_root field
        return temp_edcopilot_root

    @pytest.fixture
    def mock_config_no_git(self, temp_edcopilot_root_no_git, monkeypatch):
        """As mock_config, for a root that is not a git repository."""
        monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(temp_edcopilot_root_no_git))
        monkeypatch.setenv("EDCG_AUTO_COMMIT", "true")
        # Return just the path, since Config no longer has edcopilot_root field
        return temp_edcopilot_root_no_git

    def test_write_content_appends_to_file(self, mock_config):
        """Test that write_content appends content to the custom file."""
        result = write_content(
            system_name="Test System",
            content_block=SAMPLE_CONTENT_BLOCK,
        )

        # Should return the file that was written
        assert result.file_path.name == "EDCoPilot.SpeechExtensions.Custom.txt"

        # File should exist and contain both old and new content
        custom_file = mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        content = custom_file.read_text(encoding="utf-8")

        # Original content should still be there
        assert "@ExistingTag <~> Existing System" in content
        assert "[<Voice>] Existing content." in content

        # New content should be appended
        assert "@SystemGreeting<~>Test System" in content
        assert "@StationGreeting<~>Test System<~>Primary Improbable Discoveries (ii-42)" in content
        assert "@StationFact<~>Test System<~>Primary Improbable Discoveries (ii-42)" in content
        assert "Welcome to Test System" in content
        assert "Docking complete" in content
        assert "This station was built by Raven Colonial" in content
        # write_content must not pre-seed the database marker; markdb_add owns it.
        assert "UPDATEDB" not in content

    def test_write_content_labels_each_tag_block(self, mock_config):
        """Every tag block carries its own provenance marker."""
        write_content(
            system_name="Test System",
            content_block=SAMPLE_CONTENT_BLOCK,
        )

        custom_file = mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        content = custom_file.read_text(encoding="utf-8")

        import re
        markers = re.findall(
            r"^<!--\s*provenance:\s*edcopilot_customization_generator.*?-->\s*$",
            content, re.MULTILINE,
        )
        # One existing marker plus one per block in the sample.
        tag_count = sum(
            1 for line in SAMPLE_CONTENT_BLOCK.splitlines() if line.strip().startswith("@")
        )
        assert len(markers) == 1 + tag_count

        # Each authored tag is immediately preceded by its own marker.
        lines = [line for line in content.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            if line.strip().startswith("@"):
                assert "provenance:" in lines[index - 1]

    def test_write_content_prepends_provenance_comment(self, mock_config):
        """Test that write_content prepends a provenance comment to the content block."""
        result = write_content(
            system_name="Test System",
            content_block=SAMPLE_CONTENT_BLOCK,
        )

        custom_file = mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        content = custom_file.read_text(encoding="utf-8")

        # Should have a provenance comment for the new content
        # Format: <!-- provenance: edcopilot_customization_generator {version} — {model} — {timestamp} -->
        import re
        provenance_pattern = r"<!--\s*provenance:\s*edcopilot_customization_generator\s+[\d.]+.*—.*—.*\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*-->"
        provenance_matches = re.findall(provenance_pattern, content)

        # Should have at least 2 provenance comments (original + new)
        assert len(provenance_matches) >= 2

        # The last one should be for our new content
        last_provenance = provenance_matches[-1]
        assert "edcopilot_customization_generator" in last_provenance
        assert "0.1.0" in last_provenance  # version from the packaged generator

    def test_write_content_uses_crlf_line_endings(self, mock_config):
        """Test that write_content uses CRLF line endings."""
        result = write_content(
            system_name="Test System",
            content_block=SAMPLE_CONTENT_BLOCK,
        )

        custom_file = mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        raw_bytes = custom_file.read_bytes()

        # Should use CRLF line endings
        assert b"\r\n" in raw_bytes
        # Should not have bare LF (except possibly at end)
        # Actually, the file should use CRLF consistently
        lines = raw_bytes.split(b"\r\n")
        # At least some lines should end with CRLF
        assert len(lines) > 1

    def test_write_content_creates_git_commit(self, mock_config):
        """Test that write_content creates a git commit when EDCoPilot root is a repo."""
        result = write_content(
            system_name="Test System",
            content_block=SAMPLE_CONTENT_BLOCK,
        )

        # Should return commit hash
        assert result.commit_hash is not None
        assert len(result.commit_hash) == 8  # Short hash

        # Check commit message format
        log = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=mock_config,
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        commit_msg = log.stdout.strip()
        assert commit_msg == "edcg: content Test System"
        assert "tags" not in commit_msg.lower()

    def test_write_content_commits_staged_edits_with_empty_block(self, mock_config):
        """An empty block is the rewrite-only path: commit what is staged."""
        custom_file = (
            mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        )
        custom_file.write_text(
            custom_file.read_text(encoding="utf-8")
            + "\n[<Voice>] A staged line.\n",
            encoding="utf-8",
            newline="\r\n",
        )
        staged = custom_file.read_text(encoding="utf-8")

        result = write_content(
            system_name="Existing System",
            content_block="",
        )

        assert result.commit_hash is not None
        # Nothing is appended on the empty-block path: only the staged edit moves.
        assert custom_file.read_text(encoding="utf-8") == staged
        assert staged.count("<!-- provenance:") == 1
        subject = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=mock_config,
            capture_output=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()
        assert subject == "edcg: content Existing System"
        changed = subprocess.run(
            ["git", "show", "--format=", "--name-only", "HEAD"],
            cwd=mock_config,
            capture_output=True,
            encoding="utf-8",
            check=True,
        ).stdout
        assert "EDCoPilot.SpeechExtensions.Custom.txt" in changed
        assert "A staged line." in custom_file.read_text(encoding="utf-8")

    def test_write_content_empty_block_with_no_changes_makes_no_commit(self, mock_config):
        before = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=mock_config,
            capture_output=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()

        result = write_content(
            system_name="Test System",
            content_block="",
        )

        assert result.commit_hash is None
        after = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=mock_config,
            capture_output=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()
        assert after == before

    def test_write_content_treats_none_block_as_empty(self, mock_config):
        """A null content_block from a client means 'commit staged edits'."""
        custom_file = (
            mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        )
        custom_file.write_text(
            custom_file.read_text(encoding="utf-8") + "\n[<Voice>] A staged line.\n",
            encoding="utf-8",
            newline="\r\n",
        )
        staged = custom_file.read_text(encoding="utf-8")

        result = write_content(
            system_name="Existing System",
            content_block=None,
        )

        assert result.commit_hash is not None
        assert custom_file.read_text(encoding="utf-8") == staged

    def test_write_content_appends_co_author_trailer(self, mock_config):
        """A supplied co-author is written into the generated commit body."""
        co_author = "🤖 Test Harness (Model One, Model Two) <noreply@example.com>"
        result = write_content(
            system_name="Test System",
            content_block=SAMPLE_CONTENT_BLOCK,
            commit_co_author=co_author,
        )

        assert result.commit_hash is not None

        log = subprocess.run(
            ["git", "log", "-1", "--format=%B"],
            cwd=mock_config,
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        assert f"Co-authored-by: {co_author}" in log.stdout

    def test_write_content_no_commit_when_not_git_repo(self, mock_config_no_git):
        """Test that write_content returns None commit_hash when not a git repo."""
        result = write_content(
            system_name="Test System",
            content_block=SAMPLE_CONTENT_BLOCK,
        )

        # No commit is made, but the file is still written
        assert result.commit_hash is None

        # But file should still be written
        custom_file = mock_config_no_git / "EDCoPilot.SpeechExtensions.Custom.txt"
        content = custom_file.read_text(encoding="utf-8")
        assert "@SystemGreeting<~>Test System" in content

    def test_write_content_subject_carries_no_tag_count(self, mock_config):
        """The content commit subject names the system and nothing else."""
        # Content has 3 tags: SystemGreeting, StationGreeting, StationFact
        result = write_content(
            system_name="Test System",
            content_block=SAMPLE_CONTENT_BLOCK,
        )

        log = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=mock_config,
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        commit_msg = log.stdout.strip()
        assert commit_msg == "edcg: content Test System"
        assert "tag" not in commit_msg.lower()

    def test_write_content_returns_file_path(self, mock_config):
        """Test that WriteResult includes the file path."""
        result = write_content(
            system_name="Test System",
            content_block=SAMPLE_CONTENT_BLOCK,
        )

        assert result.file_path == mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"

    def test_write_content_handles_empty_file(self, mock_config):
        """Test write_content works when the target file is empty."""
        # Clear the file
        custom_file = mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        custom_file.write_text("", encoding="utf-8", newline="\r\n")
        subprocess.run(["git", "add", "EDCoPilot.SpeechExtensions.Custom.txt"], cwd=mock_config, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Clear file"], cwd=mock_config, check=True, capture_output=True)

        result = write_content(
            system_name="Test System",
            content_block=SAMPLE_CONTENT_BLOCK,
        )

        assert result.commit_hash is not None
        content = custom_file.read_text(encoding="utf-8")
        assert "@SystemGreeting<~>Test System" in content
        # Should have provenance comment
        assert "provenance:" in content

    def test_write_content_does_not_overwrite(self, mock_config):
        """Test that write_content appends, not overwrites."""
        # Write first block
        write_content(
            system_name="System A",
            content_block="@SystemGreeting<~>System A\n[<Voice>] Hello A.\n",
        )
        # Write second block
        write_content(
            system_name="System B",
            content_block="@SystemGreeting<~>System B\n[<Voice>] Hello B.\n",
        )

        custom_file = mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        content = custom_file.read_text(encoding="utf-8")

        # Both should be present
        assert "Hello A." in content
        assert "Hello B." in content
        assert "@SystemGreeting<~>System A" in content
        assert "@SystemGreeting<~>System B" in content

    def test_write_content_provenance_includes_timestamp(self, mock_config):
        """Test that provenance comment includes ISO timestamp."""
        result = write_content(
            system_name="Test System",
            content_block=SAMPLE_CONTENT_BLOCK,
        )

        custom_file = mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        content = custom_file.read_text(encoding="utf-8")

        # Find the last provenance comment
        import re
        provenance_matches = re.findall(r"<!--\s*provenance:([^>]+)-->", content)
        assert len(provenance_matches) >= 2
        last_provenance = provenance_matches[-1].strip()

        # Should have timestamp in ISO format (YYYY-MM-DDTHH:MM:SS)
        import re
        timestamp_match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", last_provenance)
        assert timestamp_match is not None, f"No ISO timestamp found in: {last_provenance}"

    def test_write_content_provenance_includes_model(self, mock_config):
        """Test that provenance comment includes model name."""
        result = write_content(
            system_name="Test System",
            content_block=SAMPLE_CONTENT_BLOCK,
            model="TestModel-1.0",  # Pass model parameter
        )

        custom_file = mock_config / "EDCoPilot.SpeechExtensions.Custom.txt"
        content = custom_file.read_text(encoding="utf-8")

        import re
        provenance_matches = re.findall(r"<!--\s*provenance:([^>]+)-->", content)
        last_provenance = provenance_matches[-1].strip()

        # Should include the model name
        assert "TestModel-1.0" in last_provenance

