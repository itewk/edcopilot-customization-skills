"""Configuration loading and path resolution for EDCoPilot skill content.

Everything here is stdlib only: environment parsing, content-root resolution and
EDCoPilot-root resolution (environment variable, then the content repository's
config file, then "ask").
"""

import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

CONFIG_FILENAME = "edcopilot-customization-generator.toml"
DEFAULT_RAVEN_API_URL = "https://ravencolonial100-awcbdvabgze4c5cq.canadacentral-01.azurewebsites.net"


class ConfigError(Exception):
    """Raised when configuration is invalid."""


class ContentRootError(ConfigError):
    """Raised when the content root cannot be resolved or used."""


@dataclass
class EdcopilotRootResult:
    """Result of resolving EDCoPilot's "User custom files" folder.

    ``path`` is the resolved folder when it is usable. ``source`` says where the
    answer came from: ``"env"``, ``"config"`` or ``"ask"``. ``stale`` carries a
    configured-but-missing path so callers can report it by name.
    """

    path: Optional[Path]
    source: str
    stale: Optional[Path]


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    # Paths
    content_definitions_root: Path
    edcopilot_logs_dir: Optional[Path] = None

    # Optional settings
    auto_commit: bool = True
    raven_api_url: str = DEFAULT_RAVEN_API_URL
    inara_api_key: Optional[str] = None
    spansh_enabled: bool = True


def _get_env_var(env: Mapping[str, str], key: str) -> Optional[str]:
    """Get an environment value with case-insensitive lookup."""
    for k, v in env.items():
        if k.upper() == key.upper():
            return v
    return None


def _env_value(env: Mapping[str, str], key: str) -> Optional[str]:
    """Get a non-empty environment value, treating "" as unset."""
    value = _get_env_var(env, key)
    if value is None or value == "":
        return None
    return value


def _str_to_bool(value: str) -> bool:
    """Convert a string to a boolean, case-insensitively.

    An unrecognised value is a configuration error, never a silent ``False``:
    a typo in a boolean setting must be reported rather than misread.
    """
    text = value.strip().lower()
    if text in ("true", "1", "yes", "on"):
        return True
    if text in ("false", "0", "no", "off"):
        return False
    raise ConfigError(f"Invalid boolean value: {value!r}")


def _current_dir() -> Path:
    """Return the process working directory, as a ContentRootError if it is gone."""
    try:
        return Path.cwd()
    except OSError as exc:
        raise ContentRootError(
            f"Current working directory is not available: {exc}"
        ) from exc


# Prefix for the temporary file that proves the content root accepts writes.
_PROBE_PREFIX = ".edcg_probe_"


def _probe_writable(directory: Path) -> None:
    """Raise ``ContentRootError`` unless ``directory`` accepts a new file.

    The probe name comes from ``tempfile.mkstemp``, so it can never collide
    with, and therefore never overwrite or trip over, an existing file or
    directory. Creating and writing the probe is the writability test; removing
    it afterwards is best-effort cleanup, because a probe briefly locked by an
    antivirus scanner or a sync client says nothing about whether the root
    accepts writes.
    """
    try:
        descriptor, probe_name = tempfile.mkstemp(dir=directory, prefix=_PROBE_PREFIX)
    except OSError as exc:
        raise ContentRootError(f"Content root is not writable: {directory}") from exc

    probe = Path(probe_name)
    try:
        # mkstemp hands back an open descriptor; close it before writing so the
        # probe is not left open if the write itself fails.
        os.close(descriptor)
        probe.write_text("test", encoding="utf-8")
    except OSError as exc:
        raise ContentRootError(f"Content root is not writable: {directory}") from exc
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            # Cleanup failure is not a writability verdict: reporting it as one
            # would turn a transient lock into a false "unwritable" error.
            pass


def _resolve_content_root(cwd: Path, raw_value: Optional[str]) -> Path:
    """Resolve the content root: a configured directory, else ``cwd``."""
    if raw_value is not None:
        candidate = Path(raw_value)
        if not candidate.is_dir():
            raise ContentRootError(
                f"Content root does not exist or is not a directory: {candidate}"
            )
        return candidate

    cwd = Path(cwd)
    if not cwd.is_dir():
        raise ContentRootError(f"Content root does not exist or is not a directory: {cwd}")

    # os.access(W_OK) is unreliable on Windows; write a real file instead.
    _probe_writable(cwd)
    return cwd


def environ_edcopilot_root(env: Mapping[str, str]) -> Optional[Path]:
    """The EDCoPilot root the environment names, if any.

    Returns the raw path even when it does not name an existing directory, so
    callers can report an unusable value by name; ``resolve_edcopilot_root``
    only ever returns usable directories.
    """
    value = _env_value(env, "EDCG_EDCOPILOT_ROOT")
    return Path(value) if value is not None else None


def load_config(env: Mapping[str, str]) -> Config:
    """Load configuration from environment variables."""
    content_root = resolve_content_root(_current_dir(), env)

    environment_root = environ_edcopilot_root(env)
    edcopilot_logs_value = _env_value(env, "EDCG_EDCOPILOT_LOGS_DIR")
    edcopilot_logs_dir: Optional[Path]
    if edcopilot_logs_value is not None:
        edcopilot_logs_dir = Path(edcopilot_logs_value)
    elif environment_root is not None:
        # EDCoPilot keeps its logs beside the "User custom files" folder.
        candidate = environment_root.parent / "logs"
        edcopilot_logs_dir = candidate if candidate.is_dir() else None
    else:
        edcopilot_logs_dir = None

    return Config(
        content_definitions_root=content_root,
        edcopilot_logs_dir=edcopilot_logs_dir,
        auto_commit=_str_to_bool(_env_value(env, "EDCG_AUTO_COMMIT") or "true"),
        raven_api_url=_env_value(env, "EDCG_RAVEN_API_URL") or DEFAULT_RAVEN_API_URL,
        inara_api_key=_env_value(env, "EDCG_INARA_API_KEY"),
        spansh_enabled=_str_to_bool(_env_value(env, "EDCG_SPANSH_ENABLED") or "true"),
    )


def get_config(env: Mapping[str, str] | None = None) -> Config:
    """Load configuration from the environment, once per call.

    Callers resolve roots lazily rather than caching a stale answer, and tests
    patch this module-level name to inject a configuration.
    """
    return load_config(os.environ if env is None else env)


def resolve_content_root(cwd: Path, env: Mapping[str, str]) -> Path:
    """Resolve the content root: env var when usable, else ``cwd``.

    A blank directory is a valid content root. ``ContentRootError`` is raised
    when ``EDCG_CONTENT_DEFINITIONS_ROOT`` is set but does not name a directory,
    or when ``cwd`` itself is missing, not a directory, or not writable.
    """
    return _resolve_content_root(cwd, _env_value(env, "EDCG_CONTENT_DEFINITIONS_ROOT"))


def content_root_state(root: Path) -> str:
    """Return ``"blank"`` or ``"existing"`` for a content root.

    A root is "existing" when it has a ``systems/`` directory or a config file;
    anything else is blank (and blank is not an error). The layout knowledge
    lives in :mod:`edcg.common.layout`; this name stays here for callers that
    think of it as root resolution.
    """
    from edcg.common.layout import content_root_state as _state

    return _state(root)


def _config_file(root: Path) -> Path:
    return Path(root) / CONFIG_FILENAME


def _read_config_data(config_file: Path) -> dict:
    """Parse the config file, failing loudly when it is malformed."""
    if not config_file.exists():
        return {}

    try:
        with open(config_file, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Cannot parse config file {config_file}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read config file {config_file}: {exc}") from exc


def _read_stored_raw(root: Path) -> Optional[str]:
    """Read the stored EDCoPilot path text from the content repo's config file."""
    data = _read_config_data(_config_file(root))

    roots = data.get("roots")
    if not isinstance(roots, dict):
        return None

    value = roots.get("edcopilot")
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _stored_path(root: Path, raw: str) -> Path:
    """Turn a stored value into a path, relative to the content root."""
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = Path(root) / candidate
    return candidate


def resolve_edcopilot_root(root: Path, env: Mapping[str, str]) -> EdcopilotRootResult:
    """Resolve EDCoPilot's root: env var, then stored config, then ask.

    The env var only wins when it names an existing directory; a stale env var
    must not shadow a valid stored path. Stored relative paths resolve against
    the content root (the config file's directory). A stored path that no longer
    exists is reported in ``stale`` and is never rewritten here.
    """
    env_value = _env_value(env, "EDCG_EDCOPILOT_ROOT")
    if env_value is not None:
        env_path = Path(env_value)
        if env_path.is_dir():
            return EdcopilotRootResult(path=env_path, source="env", stale=None)

    stored_raw = _read_stored_raw(root)
    if stored_raw is not None:
        stored_path = _stored_path(root, stored_raw)
        if stored_path.is_dir():
            return EdcopilotRootResult(path=stored_path, source="config", stale=None)
        return EdcopilotRootResult(path=None, source="config", stale=stored_path)

    return EdcopilotRootResult(path=None, source="ask", stale=None)

