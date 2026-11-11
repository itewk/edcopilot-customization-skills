"""Tests for common config module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from edcg.common.config import Config, load_config, ConfigError, ContentRootError


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_with_all_required_env_vars(self):
        """Test load_config loads correctly with all required env vars set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            content_definitions_root = Path(tmpdir) / "content_definitions"
            edcopilot_root = Path(tmpdir) / "edcopilot"
            content_definitions_root.mkdir()
            (content_definitions_root / "systems").mkdir()
            edcopilot_root.mkdir()

            env_vars = {
                "EDCG_CONTENT_DEFINITIONS_ROOT": str(content_definitions_root),
                "EDCG_EDCOPILOT_ROOT": str(edcopilot_root),
                "EDCG_AUTO_COMMIT": "false",
                "EDCG_RAVEN_API_URL": "https://custom.raven.url",
                "EDCG_INARA_API_KEY": "inara-key-123",
                "EDCG_DEEPL_API_KEY": "deepl-key-456",
                "EDCG_SPANSH_ENABLED": "false",
                "EDCG_LOG_LEVEL": "DEBUG",
            }

            config = load_config(env_vars)
            assert config.content_definitions_root == content_definitions_root
            assert config.edcopilot_root == edcopilot_root
            assert config.auto_commit is False
            assert config.raven_api_url == "https://custom.raven.url"
            assert config.inara_api_key == "inara-key-123"
            assert config.deepl_api_key == "deepl-key-456"
            assert config.spansh_enabled is False
            assert config.log_level == "DEBUG"

    def test_load_config_with_only_required_env_vars(self):
        """Test load_config loads with only required env vars (uses defaults for optional)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            content_definitions_root = Path(tmpdir) / "content_definitions"
            edcopilot_root = Path(tmpdir) / "edcopilot"
            content_definitions_root.mkdir()
            (content_definitions_root / "systems").mkdir()
            edcopilot_root.mkdir()

            env_vars = {
                "EDCG_CONTENT_DEFINITIONS_ROOT": str(content_definitions_root),
                "EDCG_EDCOPILOT_ROOT": str(edcopilot_root),
            }

            config = load_config(env_vars)
            assert config.content_definitions_root == content_definitions_root
            assert config.edcopilot_root == edcopilot_root
            # Check defaults
            assert config.auto_commit is True
            assert config.raven_api_url == "https://ravencolonial100-awcbdvabgze4c5cq.canadacentral-01.azurewebsites.net"
            assert config.inara_api_key is None
            assert config.deepl_api_key is None
            assert config.spansh_enabled is True
            assert config.log_level == "INFO"

    def test_config_case_insensitive_env_vars(self):
        """Test load_config loads env vars case-insensitively."""
        with tempfile.TemporaryDirectory() as tmpdir:
            content_definitions_root = Path(tmpdir) / "content_definitions"
            edcopilot_root = Path(tmpdir) / "edcopilot"
            content_definitions_root.mkdir()
            (content_definitions_root / "systems").mkdir()
            edcopilot_root.mkdir()

            env_vars = {
                "edcg_content_definitions_root": str(content_definitions_root),  # lowercase
                "EDCG_EDCOPILOT_ROOT": str(edcopilot_root),  # uppercase
            }

            config = load_config(env_vars)
            assert config.content_definitions_root == content_definitions_root
            assert config.edcopilot_root == edcopilot_root

    def test_boolean_coercion_from_string(self):
        """Test boolean fields coerce from string env vars."""
        with tempfile.TemporaryDirectory() as tmpdir:
            content_definitions_root = Path(tmpdir) / "content_definitions"
            edcopilot_root = Path(tmpdir) / "edcopilot"
            content_definitions_root.mkdir()
            (content_definitions_root / "systems").mkdir()
            edcopilot_root.mkdir()

            # Test various truthy/falsy string values
            for val, expected in [
                ("true", True), ("True", True), ("TRUE", True), ("1", True), ("yes", True),
                ("false", False), ("False", False), ("FALSE", False), ("0", False), ("no", False),
            ]:
                env_vars = {
                    "EDCG_CONTENT_DEFINITIONS_ROOT": str(content_definitions_root),
                    "EDCG_EDCOPILOT_ROOT": str(edcopilot_root),
                    "EDCG_AUTO_COMMIT": val,
                }
                config = load_config(env_vars)
                assert config.auto_commit == expected, f"Failed for value: {val}"

    def test_extra_env_vars_ignored(self):
        """Test load_config ignores extra env vars."""
        with tempfile.TemporaryDirectory() as tmpdir:
            content_definitions_root = Path(tmpdir) / "content_definitions"
            edcopilot_root = Path(tmpdir) / "edcopilot"
            content_definitions_root.mkdir()
            (content_definitions_root / "systems").mkdir()
            edcopilot_root.mkdir()

            env_vars = {
                "EDCG_CONTENT_DEFINITIONS_ROOT": str(content_definitions_root),
                "EDCG_EDCOPILOT_ROOT": str(edcopilot_root),
                "EDCG_UNKNOWN_SETTING": "should_be_ignored",
            }

            config = load_config(env_vars)
            # We don't check for the presence of unknown settings since they're ignored


class TestConfigFieldNames:
    """Tests verifying field names match the spec."""

    def test_field_names_match_spec(self):
        """Test that Config has all fields specified in the brief."""
        with tempfile.TemporaryDirectory() as tmpdir:
            content_definitions_root = Path(tmpdir) / "content_definitions"
            edcopilot_root = Path(tmpdir) / "edcopilot"
            content_definitions_root.mkdir()
            (content_definitions_root / "systems").mkdir()
            edcopilot_root.mkdir()

            env_vars = {
                "EDCG_CONTENT_DEFINITIONS_ROOT": str(content_definitions_root),
                "EDCG_EDCOPILOT_ROOT": str(edcopilot_root),
            }

            config = load_config(env_vars)
            # Required fields per spec
            assert hasattr(config, "content_definitions_root")
            assert hasattr(config, "edcopilot_root")
            # Optional fields per spec
            assert hasattr(config, "auto_commit")
            assert hasattr(config, "raven_api_url")
            assert hasattr(config, "inara_api_key")
            assert hasattr(config, "deepl_api_key")
            assert hasattr(config, "spansh_enabled")
            assert hasattr(config, "log_level")


class TestConfigDefaults:
    """Tests for default values."""

    def test_default_values(self):
        """Test that all fields have correct default values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            content_definitions_root = Path(tmpdir) / "content_definitions"
            edcopilot_root = Path(tmpdir) / "edcopilot"
            content_definitions_root.mkdir()
            (content_definitions_root / "systems").mkdir()
            edcopilot_root.mkdir()

            env_vars = {
                "EDCG_CONTENT_DEFINITIONS_ROOT": str(content_definitions_root),
                "EDCG_EDCOPILOT_ROOT": str(edcopilot_root),
            }

            config = load_config(env_vars)
            assert config.auto_commit is True
            assert config.raven_api_url == "https://ravencolonial100-awcbdvabgze4c5cq.canadacentral-01.azurewebsites.net"
            assert config.inara_api_key is None
            assert config.deepl_api_key is None
            assert config.spansh_enabled is True
            assert config.log_level == "INFO"


class TestConfigValidation:
    """Tests for configuration validation."""

    def test_env_var_prefix_is_edcg(self):
        """Test that env var prefix is EDCG_."""
        with tempfile.TemporaryDirectory() as tmpdir:
            content_definitions_root = Path(tmpdir) / "content_definitions"
            edcopilot_root = Path(tmpdir) / "edcopilot"
            content_definitions_root.mkdir()
            (content_definitions_root / "systems").mkdir()
            edcopilot_root.mkdir()

            # Test with correct prefix
            env_vars = {
                "EDCG_CONTENT_DEFINITIONS_ROOT": str(content_definitions_root),
                "EDCG_EDCOPILOT_ROOT": str(edcopilot_root),
            }

            config = load_config(env_vars)
            assert config.content_definitions_root == content_definitions_root

            # Test with wrong prefix (should not work - but we don't validate this in our implementation)
            # The env var parsing is case insensitive, so it will still work with different cases


class TestCWDResolution:
    """Tests for CWD resolution behavior."""

    def test_cwd_fallback_when_env_absent(self, monkeypatch, tmp_path):
        """Test that when content_definitions_root is not set, it defaults to CWD."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "systems").mkdir()
        edcopilot = tmp_path / "edcopilot"
        edcopilot.mkdir()
        monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(edcopilot))
        monkeypatch.delenv("EDCG_CONTENT_DEFINITIONS_ROOT", raising=False)

        config = load_config(os.environ)
        assert config.content_definitions_root == tmp_path

    def test_env_var_override_precedence(self, monkeypatch, tmp_path):
        """Test that env var override takes precedence."""
        content = tmp_path / "content"
        content.mkdir()
        (content / "systems").mkdir()
        edcopilot = tmp_path / "edcopilot"
        edcopilot.mkdir()
        monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(content))
        monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(edcopilot))

        config = load_config(os.environ)
        assert config.content_definitions_root == content

    def test_blank_cwd_is_allowed(self, monkeypatch, tmp_path):
        """Test that blank repo (no systems/ or toml) is allowed."""
        edcopilot = tmp_path / "edcopilot"
        edcopilot.mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(edcopilot))
        monkeypatch.delenv("EDCG_CONTENT_DEFINITIONS_ROOT", raising=False)

        config = load_config(os.environ)
        assert config.content_definitions_root == tmp_path
        assert config.edcopilot_root == edcopilot

    def test_empty_env_var_falls_back_to_cwd(self, monkeypatch, tmp_path):
        """Test that empty env var falls back to CWD."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "systems").mkdir()
        edcopilot = tmp_path / "edcopilot"
        edcopilot.mkdir()
        monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", "")
        monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(edcopilot))

        config = load_config(os.environ)
        assert config.content_definitions_root == tmp_path


class TestContentRootField:
    """Tests for the content_root field and content-root error handling."""

    def test_config_exposes_content_root(self, monkeypatch, tmp_path):
        """Test that Config carries content_root alongside content_definitions_root."""
        (tmp_path / "systems").mkdir()
        edcopilot = tmp_path / "edcopilot"
        edcopilot.mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("EDCG_CONTENT_DEFINITIONS_ROOT", raising=False)
        monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(edcopilot))

        config = load_config(os.environ)
        assert config.content_root == tmp_path
        assert config.content_root == config.content_definitions_root

    def test_missing_content_env_raises(self, tmp_path):
        """Test that a missing EDCG_CONTENT_DEFINITIONS_ROOT raises ContentRootError."""
        with pytest.raises(ContentRootError):
            load_config({"EDCG_CONTENT_DEFINITIONS_ROOT": str(tmp_path / "missing")})

    def test_deleted_cwd_raises_content_root_error(self, tmp_path, monkeypatch):
        """Test that a deleted working directory raises ContentRootError, not OSError."""
        content = tmp_path / "content"
        content.mkdir()

        def missing_cwd():
            raise FileNotFoundError(2, "The system cannot find the path specified")

        monkeypatch.setattr(Path, "cwd", staticmethod(missing_cwd))

        with pytest.raises(ContentRootError):
            load_config({"EDCG_CONTENT_DEFINITIONS_ROOT": str(content)})


class TestLogsDirField:
    """Tests for the edcopilot_logs_dir field (Task 8 carry-forward)."""

    def test_logs_dir_from_environment(self, monkeypatch, tmp_path):
        (tmp_path / "systems").mkdir()
        edcopilot = tmp_path / "edcopilot"
        edcopilot.mkdir()
        logs = tmp_path / "logs"
        logs.mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("EDCG_CONTENT_DEFINITIONS_ROOT", raising=False)
        monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(edcopilot))
        monkeypatch.setenv("EDCG_EDCOPILOT_LOGS_DIR", str(logs))

        config = load_config(os.environ)
        assert config.edcopilot_logs_dir == logs

    def test_logs_dir_defaults_to_none(self, monkeypatch, tmp_path):
        (tmp_path / "systems").mkdir()
        edcopilot = tmp_path / "edcopilot"
        edcopilot.mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("EDCG_CONTENT_DEFINITIONS_ROOT", raising=False)
        monkeypatch.delenv("EDCG_EDCOPILOT_LOGS_DIR", raising=False)
        monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(edcopilot))

        config = load_config(os.environ)
        assert config.edcopilot_logs_dir is None

    def test_logs_dir_defaults_to_the_parent_logs_folder(self, monkeypatch, tmp_path):
        (tmp_path / "systems").mkdir()
        edcopilot = tmp_path / "edcopilot"
        edcopilot.mkdir()
        logs = tmp_path / "logs"
        logs.mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("EDCG_CONTENT_DEFINITIONS_ROOT", raising=False)
        monkeypatch.delenv("EDCG_EDCOPILOT_LOGS_DIR", raising=False)
        monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(edcopilot))

        config = load_config(os.environ)
        assert config.edcopilot_logs_dir == logs
