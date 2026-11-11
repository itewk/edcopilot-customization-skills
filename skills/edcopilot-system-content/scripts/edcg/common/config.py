"""Configuration loading and path resolution for EDCoPilot skill content.

Everything here is stdlib only: environment parsing, content-root resolution and
EDCoPilot-root resolution (environment variable, then the content repository's
config file, then "ask").
"""

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

CONFIG_FILENAME = "edcopilot-customization-generator.toml"
DEFAULT_RAVEN_API_URL = "https://ravencolonial100-awcbdvabgze4c5cq.canadacentral-01.azurewebsites.net"
DEFAULT_LOG_LEVEL = "INFO"

# "[roots]" with an optional trailing comment, e.g. "[roots]  # where it lives"
_ROOTS_HEADER = re.compile(r"^\[\s*roots\s*\]\s*(?:#.*)?$")
# "edcopilot =", '"edcopilot" =' or "'edcopilot' ="
_EDCOPILOT_KEY = re.compile(r"""^\s*(?:"edcopilot"|'edcopilot'|edcopilot)\s*=""")


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
    content_root: Path
    edcopilot_root: Optional[Path] = None

    # Optional settings
    auto_commit: bool = True
    raven_api_url: str = DEFAULT_RAVEN_API_URL
    inara_api_key: Optional[str] = None
    deepl_api_key: Optional[str] = None
    spansh_enabled: bool = True
    log_level: str = DEFAULT_LOG_LEVEL


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
    """Convert a string to a boolean, case-insensitively."""
    return value.strip().lower() in ("true", "1", "yes", "on")


def _current_dir() -> Path:
    """Return the process working directory, as a ContentRootError if it is gone."""
    try:
        return Path.cwd()
    except OSError as exc:
        raise ContentRootError(
            f"Current working directory is not available: {exc}"
        ) from exc


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
    if not os.access(cwd, os.W_OK):
        raise ContentRootError(f"Content root is not writable: {cwd}")
    return cwd


def load_config(env: Mapping[str, str]) -> Config:
    """Load configuration from environment variables."""
    content_root = resolve_content_root(_current_dir(), env)

    edcopilot_root = _env_value(env, "EDCG_EDCOPILOT_ROOT")

    return Config(
        content_definitions_root=content_root,
        content_root=content_root,
        edcopilot_root=Path(edcopilot_root) if edcopilot_root is not None else None,
        auto_commit=_str_to_bool(_env_value(env, "EDCG_AUTO_COMMIT") or "true"),
        raven_api_url=_env_value(env, "EDCG_RAVEN_API_URL") or DEFAULT_RAVEN_API_URL,
        inara_api_key=_env_value(env, "EDCG_INARA_API_KEY"),
        deepl_api_key=_env_value(env, "EDCG_DEEPL_API_KEY"),
        spansh_enabled=_str_to_bool(_env_value(env, "EDCG_SPANSH_ENABLED") or "true"),
        log_level=_env_value(env, "EDCG_LOG_LEVEL") or DEFAULT_LOG_LEVEL,
    )


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
    anything else is blank (and blank is not an error).
    """
    systems_dir = root / "systems"
    if systems_dir.is_dir():
        return "existing"

    config_file = root / CONFIG_FILENAME
    if config_file.is_file():
        return "existing"

    return "blank"


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


def read_stored_root(root: Path) -> Optional[Path]:
    """Read the stored EDCoPilot root from the content repo's config file."""
    stored_raw = _read_stored_raw(root)
    return _stored_path(root, stored_raw) if stored_raw is not None else None


def _toml_string(value: str) -> str:
    """Escape a value for a TOML basic string."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def write_stored_root(root: Path, path: Path) -> None:
    """Store the EDCoPilot root in the content repo's config file.

    The file is created when absent. Only the ``edcopilot`` key inside the
    ``[roots]`` table is touched, so any other keys, tables and comments survive.
    The path is stored with forward slashes. A malformed config file raises
    ``ConfigError`` instead of being rewritten blindly.
    """
    config_file = _config_file(root)
    _read_config_data(config_file)

    line = f'edcopilot = "{_toml_string(Path(path).as_posix())}"'

    text = config_file.read_text(encoding="utf-8") if config_file.exists() else ""
    lines = text.splitlines()

    roots_start = next(
        (index for index, existing in enumerate(lines) if _ROOTS_HEADER.match(existing.strip())),
        None,
    )

    if roots_start is None:
        while lines and not lines[-1].strip():
            lines.pop()
        if lines:
            lines.append("")
        lines.extend(["[roots]", line])
    else:
        section_end = len(lines)
        for index in range(roots_start + 1, len(lines)):
            if lines[index].lstrip().startswith("["):
                section_end = index
                break

        replaced = False
        for index in range(roots_start + 1, section_end):
            if _EDCOPILOT_KEY.match(lines[index]):
                lines[index] = line
                replaced = True
                break

        if not replaced:
            lines.insert(roots_start + 1, line)

    new_text = "\n".join(lines) + "\n"
    try:
        tomllib.loads(new_text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Cannot write config file {config_file}: {exc}") from exc

    config_file.write_text(new_text, encoding="utf-8", newline="\n")
