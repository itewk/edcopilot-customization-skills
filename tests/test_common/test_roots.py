"""Tests for common roots resolution module."""

import os
import tempfile
from pathlib import Path

import pytest

from edcg.common.config import (
    ConfigError,
    ContentRootError,
    load_config,
    resolve_content_root,
    content_root_state,
    resolve_edcopilot_root,
    read_stored_root,
    write_stored_root,
    EdcopilotRootResult
)


class TestContentRootResolution:
    """Tests for content root resolution logic."""

    def test_blank_dir_requires_init(self, tmp_path):
        """Test that blank directory returns state 'blank'."""
        # Create a blank directory (no systems/ or config file)
        assert content_root_state(tmp_path) == "blank"

    def test_existing_content_root_state(self, tmp_path):
        """Test that existing content root returns state 'existing'."""
        # Create a directory with systems/
        systems_dir = tmp_path / "systems"
        systems_dir.mkdir()
        
        assert content_root_state(tmp_path) == "existing"

    def test_existing_content_root_with_config_file(self, tmp_path):
        """Test that existing content root with config file returns state 'existing'."""
        # Create a directory with config file
        config_file = tmp_path / "edcopilot-customization-generator.toml"
        config_file.write_text('[roots]\nedcopilot = "C:/EDCoPilot/User custom files"\n')
        
        assert content_root_state(tmp_path) == "existing"

    def test_env_content_root_must_exist(self, tmp_path):
        """Test that a missing EDCG_CONTENT_DEFINITIONS_ROOT raises ContentRootError."""
        env = {"EDCG_CONTENT_DEFINITIONS_ROOT": str(tmp_path / "missing")}

        with pytest.raises(ContentRootError):
            resolve_content_root(tmp_path, env)

    def test_env_content_root_used_when_it_exists(self, tmp_path):
        """Test that an existing EDCG_CONTENT_DEFINITIONS_ROOT is used."""
        content = tmp_path / "content"
        content.mkdir()

        env = {"EDCG_CONTENT_DEFINITIONS_ROOT": str(content)}

        assert resolve_content_root(tmp_path, env) == content


class TestEddcopilotRootResolution:
    """Tests for EDCoPilot root resolution logic."""

    def test_stale_edcopilot_root_reported_not_overwritten(self, tmp_path):
        """Test that when stored path is nonexistent, result reports stale but doesn't overwrite."""
        # Create a config file with stale path
        config_file = tmp_path / "edcopilot-customization-generator.toml"
        config_file.write_text('[roots]\nedcopilot = "C:/nonexistent/path"\n')
        
        # Set up env to not override
        os.environ["EDCG_EDCOPILOT_ROOT"] = ""
        
        result = resolve_edcopilot_root(tmp_path, os.environ)
        assert result.path is None
        assert result.source == "config"
        assert result.stale is not None
        # Compare normalized forms: the separator spelling is platform-dependent
        assert os.path.normcase(os.path.normpath(str(result.stale))) == os.path.normcase(
            os.path.normpath("C:/nonexistent/path")
        )

    def test_env_var_root_must_exist_falls_through(self, tmp_path, monkeypatch):
        """Test that an env var root must exist to win, else the stored path is used."""
        # A stored path that exists, for the fall-through assertions below
        stored_root = tmp_path / "stored_root"
        stored_root.mkdir()
        config_file = tmp_path / "edcopilot-customization-generator.toml"
        config_file.write_text(f'[roots]\nedcopilot = "{stored_root.as_posix()}"\n')

        # An existing env var directory takes precedence over the stored path
        env_root = tmp_path / "env_root"
        env_root.mkdir()
        monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(env_root))

        result = resolve_edcopilot_root(tmp_path, os.environ)
        assert result.path == env_root
        assert result.source == "env"
        assert result.stale is None

        # A set-but-nonexistent env var falls through to the stored path
        monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(tmp_path / "missing_env_root"))

        result = resolve_edcopilot_root(tmp_path, os.environ)
        assert result.path == stored_root
        assert result.source == "config"
        assert result.stale is None

        # With no usable stored path either, the answer is "ask"
        config_file.unlink()

        result = resolve_edcopilot_root(tmp_path, os.environ)
        assert result.path is None
        assert result.source == "ask"
        assert result.stale is None

    def test_write_stored_root_creates_config(self, tmp_path):
        """Test that write_stored_root creates config file if it doesn't exist."""
        config_file = tmp_path / "edcopilot-customization-generator.toml"
        
        # Ensure config file doesn't exist
        if config_file.exists():
            config_file.unlink()
        
        write_stored_root(tmp_path, Path("test/path"))
        
        assert config_file.exists()
        content = config_file.read_text()
        assert "[roots]" in content
        assert "edcopilot = \"test/path\"" in content

    def test_write_stored_root_replaces_entry_under_commented_header(self, tmp_path):
        """Test that a '[roots]  # note' header is reused, not duplicated."""
        config_file = tmp_path / "edcopilot-customization-generator.toml"
        config_file.write_text('[roots]  # where EDCoPilot lives\nedcopilot = "C:/old"\n')

        write_stored_root(tmp_path, Path("C:/new/root"))

        content = config_file.read_text()
        assert content.count("[roots]") == 1
        assert "C:/old" not in content
        assert read_stored_root(tmp_path) == Path("C:/new/root")

    def test_write_stored_root_replaces_quoted_key_in_place(self, tmp_path):
        """Test that a quoted '"edcopilot" = ...' entry is replaced, not duplicated."""
        config_file = tmp_path / "edcopilot-customization-generator.toml"
        config_file.write_text('[roots]\n"edcopilot" = "C:/old"\nauthor = "ian"\n')

        write_stored_root(tmp_path, Path("C:/new"))

        content = config_file.read_text()
        assert content.count("edcopilot") == 1
        assert 'author = "ian"' in content
        assert read_stored_root(tmp_path) == Path("C:/new")

    def test_write_stored_root_preserves_unrelated_keys_and_tables(self, tmp_path):
        """Test that writing one key preserves everything else in the file."""
        config_file = tmp_path / "edcopilot-customization-generator.toml"
        config_file.write_text(
            '# header\nauthor = "ian"\n\n[roots]\nother = 1\n\n[other]\nkey = "v"\n'
        )

        write_stored_root(tmp_path, Path("C:/edc"))

        content = config_file.read_text()
        assert "# header" in content
        assert 'author = "ian"' in content
        assert "other = 1" in content
        assert '[other]\nkey = "v"' in content
        assert read_stored_root(tmp_path) == Path("C:/edc")

    def test_malformed_config_raises_config_error(self, tmp_path):
        """Test that an unparsable config file fails loudly instead of vanishing."""
        config_file = tmp_path / "edcopilot-customization-generator.toml"
        config_file.write_text('[roots\nedcopilot = "C:/x"\n')

        with pytest.raises(ConfigError) as excinfo:
            read_stored_root(tmp_path)
        assert str(config_file) in str(excinfo.value)

        with pytest.raises(ConfigError):
            resolve_edcopilot_root(tmp_path, {})

        with pytest.raises(ConfigError):
            write_stored_root(tmp_path, Path("C:/new"))

    def test_relative_stored_root_resolves_against_content_root(self, tmp_path, monkeypatch):
        """Test that a relative stored path resolves against the content root."""
        content_root = tmp_path / "A"
        content_root.mkdir()
        (content_root / "rel_edcopilot").mkdir()
        config_file = content_root / "edcopilot-customization-generator.toml"
        config_file.write_text('[roots]\nedcopilot = "rel_edcopilot"\n')

        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

        result = resolve_edcopilot_root(content_root, {})
        assert result.path == content_root / "rel_edcopilot"
        assert result.source == "config"
        assert result.stale is None
        assert read_stored_root(content_root) == content_root / "rel_edcopilot"

        # A missing relative entry is reported as the content-root-relative candidate
        config_file.write_text('[roots]\nedcopilot = "missing_rel"\n')

        result = resolve_edcopilot_root(content_root, {})
        assert result.path is None
        assert result.source == "config"
        assert result.stale == content_root / "missing_rel"

    def test_existing_root_not_rescaffolded(self, tmp_path):
        """Test that existing root returns state 'existing'."""
        # Create a directory with systems/
        systems_dir = tmp_path / "systems"
        systems_dir.mkdir()
        
        assert content_root_state(tmp_path) == "existing"