"""Tests for save_definition.

Tests edcg.repo.dossier.save_definition(system_name: str, dossier_md: str, rules_toml: str) -> SaveResult
"""

from pathlib import Path
import pytest
from unittest.mock import patch

from edcg.repo.dossier import save_definition
from edcg.rules.validation import SaveResult


# ============================================================
# Test fixtures - valid dossier and rules
# ============================================================

VALID_DOSSIER = """# Test System — system dossier

## 1. Identity and canon

| Fact | Value |
|---|---|
| System name | `Test System` |

## 2. Lore and theme

Test lore.

## 3. Tone rules (hard constraints)

Test tone.

## 4. Canon site table

### Complete (3)

| Site | Build type | Body |
|---|---|---|
| Primary Improbable Discoveries (ii-42) | `prometheus` Scientific Outpost | `4 d` |
| Infinite Redshirts (ii-42) | `nemesis` Military Outpost | star |
| Cold Probabilities (ii-42) | `nona` Civilian Surface Outpost | `3 a` |
| Refined Industrial Probabilities (ii-42) | `quad_truss` Coriolis Starport | `3 a` |
| Plundered Probabilities (ii-42) | `dysnomia` Pirate Outpost | `5 d` |
| Probably Redshirts (ii-42) | `nemesis` Military Outpost | `4 a` |

## 5. Corrections log (do not reintroduce these)

## 6. Site list maintenance

## 7. Coverage

Primary Improbable Discoveries · Infinite Redshirts · Cold Probabilities ·
Refined Industrial Probabilities · Plundered Probabilities · Probably Redshirts

## 8. Writing rules

### Voices used

- **Crew:** `[<Foreman>]`, `[<Welder>]`, `[<Researcher>]`, `[<LabTech>]`
- **Garrison:** `[<GuardSarge>]`, `[<GuardTrooper>]`

## 9. Open threads (TODO)

- Test thread
"""

VALID_RULES = """[system]
names = ["Test System"]
dossier = "systems/test-system.md"
voices = ["Foreman", "Welder", "Researcher", "LabTech", "GuardSarge", "GuardTrooper"]
"""


class TestSaveDefinitionTool:
    """Tests for save_definition."""

    @pytest.fixture
    def temp_content_definitions(self, git_repo):
        """A committed repository with the content layout ``save_definition`` expects."""
        repo_path = git_repo(files={"README.md": "# Test Content Definitions\n"})
        (repo_path / "systems").mkdir()
        return repo_path

    @pytest.fixture
    def mock_config(self, temp_content_definitions):
        """Create a mock config with the temp content definitions path."""
        from edcg.common.config import Config
        config = Config(
            content_definitions_root=temp_content_definitions,
            auto_commit=True,
        )
        return config

    def test_save_definition_creates_files_and_commits(self, mock_config):
        """Test that save_definition writes files and creates a git commit."""
        with patch("edcg.repo.dossier.get_config", return_value=mock_config):
            result = save_definition(
                system_name="Test System",
                dossier_md=VALID_DOSSIER,
                rules_toml=VALID_RULES,
            )

        # Should return SaveResult
        assert isinstance(result, SaveResult)
        assert result.commit_hash is not None
        assert len(result.commit_hash) > 0
        assert len(result.files_changed) >= 2

        # Files should exist
        systems_dir = mock_config.content_definitions_root / "systems"
        dossier_file = systems_dir / "test-system.md"
        rules_file = systems_dir / "test-system.rules.toml"

        assert dossier_file.exists()
        assert rules_file.exists()

        # Content should match input
        assert dossier_file.read_text(encoding="utf-8") == VALID_DOSSIER
        assert rules_file.read_text(encoding="utf-8") == VALID_RULES

        # Commit message should be correct format (scaffold for new system)
        import subprocess
        log = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=mock_config.content_definitions_root,
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        commit_msg = log.stdout.strip()
        assert "edcg: scaffold Test System" in commit_msg
        assert "edcopilot_customization_generator: scaffold" not in commit_msg
        # Check for em dash (U+2014, ord=8212) or similar separator
        assert any(ord(c) == 8212 for c in commit_msg) or "--" in commit_msg, f"No separator found in: {commit_msg!r}"

    def test_save_definition_appends_co_author_trailer(self, mock_config):
        """A supplied co-author is written into the commit body."""
        import subprocess

        co_author = "🤖 Test Harness (Model One, Model Two) <noreply@example.com>"
        with patch("edcg.repo.dossier.get_config", return_value=mock_config):
            result = save_definition(
                system_name="Test System",
                dossier_md=VALID_DOSSIER,
                rules_toml=VALID_RULES,
                commit_co_author=co_author,
            )

        assert result.commit_hash is not None

        log = subprocess.run(
            ["git", "log", "-1", "--format=%B"],
            cwd=mock_config.content_definitions_root,
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        assert f"Co-authored-by: {co_author}" in log.stdout

    def test_save_definition_update_existing_system(self, mock_config, temp_content_definitions):
        """Test that updating an existing system uses 'update' in commit message."""
        import subprocess

        # First, create the system files (simulate existing system)
        systems_dir = temp_content_definitions / "systems"
        dossier_file = systems_dir / "test-system.md"
        rules_file = systems_dir / "test-system.rules.toml"
        dossier_file.write_text(VALID_DOSSIER)
        rules_file.write_text(VALID_RULES)
        subprocess.run(["git", "add", "."], cwd=temp_content_definitions, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial system"], cwd=temp_content_definitions, check=True, capture_output=True)

        # Now update with new content
        updated_dossier = VALID_DOSSIER.replace("Test lore.", "Updated lore.")
        updated_rules = VALID_RULES.replace('dossier = "systems/test-system.md"', 'dossier = "systems/test-system.md"')

        with patch("edcg.repo.dossier.get_config", return_value=mock_config):
            result = save_definition(
                system_name="Test System",
                dossier_md=updated_dossier,
                rules_toml=updated_rules,
            )

        # Should return SaveResult
        assert isinstance(result, SaveResult)
        assert result.commit_hash is not None

        # Commit message should use 'update' for existing system
        log = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=mock_config.content_definitions_root,
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        commit_msg = log.stdout.strip()
        assert "edcg: update Test System" in commit_msg
        assert "edcopilot_customization_generator: update" not in commit_msg
        # Check for em dash (U+2014, ord=8212) or similar separator
        assert any(ord(c) == 8212 for c in commit_msg) or "--" in commit_msg, f"No separator found in: {commit_msg!r}"

    def test_save_definition_slug_generation(self, mock_config):
        """Test that system name is properly slugified for filenames."""
        test_cases = [
            ("Test System", "test-system"),
            ("Bleia Eohn SX-F c12", "bleia-eohn-sx-f-c12"),
            ("System (With) Parentheses", "system-with-parentheses"),
            ("UPPER CASE", "upper-case"),
            ("Special@Chars!", "special-chars"),
        ]

        for system_name, expected_slug in test_cases:
            rules = f"""[system]
names = ["{system_name}"]
dossier = "systems/{expected_slug}.md"
voices = ["Voice1"]
"""
            with patch("edcg.repo.dossier.get_config", return_value=mock_config):
                result = save_definition(
                    system_name=system_name,
                    dossier_md=VALID_DOSSIER.replace("Test System", system_name),
                    rules_toml=rules,
                )

            systems_dir = mock_config.content_definitions_root / "systems"
            assert (systems_dir / f"{expected_slug}.md").exists(), f"Failed for {system_name}"
            assert (systems_dir / f"{expected_slug}.rules.toml").exists(), f"Failed for {system_name}"

            # Clean up for next iteration
            (systems_dir / f"{expected_slug}.md").unlink()
            (systems_dir / f"{expected_slug}.rules.toml").unlink()
            import subprocess
            subprocess.run(["git", "add", "."], cwd=mock_config.content_definitions_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"Cleanup {system_name}"], cwd=mock_config.content_definitions_root, check=True, capture_output=True)

    def test_save_definition_returns_files_changed(self, mock_config):
        """Test that SaveResult includes the list of changed files."""
        with patch("edcg.repo.dossier.get_config", return_value=mock_config):
            result = save_definition(
                system_name="Test System",
                dossier_md=VALID_DOSSIER,
                rules_toml=VALID_RULES,
            )

        assert isinstance(result.files_changed, list)
        assert len(result.files_changed) >= 2

        # Should contain the two files we created
        file_names = [Path(f).name for f in result.files_changed]
        assert "test-system.md" in file_names
        assert "test-system.rules.toml" in file_names

    def test_save_definition_commit_hash_format(self, mock_config):
        """Test that commit hash is short format (8 chars)."""
        with patch("edcg.repo.dossier.get_config", return_value=mock_config):
            result = save_definition(
                system_name="Test System",
                dossier_md=VALID_DOSSIER,
                rules_toml=VALID_RULES,
            )

        assert result.commit_hash is not None
        assert len(result.commit_hash) == 8  # Short hash
        assert all(c in "0123456789abcdef" for c in result.commit_hash.lower())

    def test_save_definition_handles_special_characters_in_name(self, mock_config):
        """Test save_definition handles special characters in system name."""
        system_name = "Test-System (Alpha)"
        expected_slug = "test-system-alpha"
        rules = f"""[system]
names = ["{system_name}"]
dossier = "systems/{expected_slug}.md"
voices = ["Voice1"]
"""

        with patch("edcg.repo.dossier.get_config", return_value=mock_config):
            result = save_definition(
                system_name=system_name,
                dossier_md=VALID_DOSSIER.replace("Test System", system_name),
                rules_toml=rules,
            )

        assert result.commit_hash is not None
        systems_dir = mock_config.content_definitions_root / "systems"
        assert (systems_dir / f"{expected_slug}.md").exists()
        assert (systems_dir / f"{expected_slug}.rules.toml").exists()


