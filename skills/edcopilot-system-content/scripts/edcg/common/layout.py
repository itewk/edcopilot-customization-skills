"""Content-repository layout: where files live inside a content root.

Root resolution — which directory is the content root, and how EDCoPilot's
custom-files folder is found — stays in :mod:`edcg.common.config`. This module
owns only the layout *inside* a root, so every consumer derives the same paths
and the missing-root answer is written once.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:  # pragma: no cover - import cycle avoidance, typing only
    from edcg.common.config import Config

CUSTOM_FILE_NAME = "EDCoPilot.SpeechExtensions.Custom.txt"

# A provenance comment opens the authored region; everything above the first
# one is EDCoPilot's own text.
PROVENANCE_RE = re.compile(r"^<!--\s*provenance:(?P<body>.*?)-->\s*$")

SYSTEMS_DIR_NAME = "systems"


def slugify(name: str) -> str:
    """Convert a system name to a filesystem-safe slug.

    - Lowercase
    - Replace spaces and special chars with hyphens
    - Remove parentheses but keep their contents
    - Collapse multiple hyphens
    - Strip leading/trailing hyphens
    """
    # Replace parentheses with spaces (keep contents)
    name = name.replace("(", " ").replace(")", " ")
    # Replace non-alphanumeric with hyphens
    name = re.sub(r"[^a-zA-Z0-9]+", "-", name)
    # Collapse multiple hyphens
    name = re.sub(r"-+", "-", name)
    # Strip leading/trailing hyphens and lowercase
    return name.strip("-").lower()


def systems_dir(config: Config | Path) -> Path:
    """The directory holding every system's dossier and rules file."""
    root = config if isinstance(config, Path) else config.content_definitions_root
    return Path(root) / SYSTEMS_DIR_NAME


def dossier_path(config: Config, system_name: str) -> Path:
    """The system's dossier file inside the content repository."""
    return systems_dir(config) / f"{slugify(system_name)}.md"


def rules_path(config: Config, system_name: str) -> Path:
    """The system's own rules file inside the content repository."""
    return systems_dir(config) / f"{slugify(system_name)}.rules.toml"


def has_definition(config: Config, system_name: str) -> bool:
    """Whether the system's definition - the dossier AND rules pair - is saved.

    The shared definition semantics for the content commands' gate, ``status``
    and the next-step hints: half a pair is not a definition. The
    ``save_definition`` ``is_new`` check still uses ``.exists()`` on the same
    pair, so a directory at either path counts as present there and absent
    here; adopting this predicate is a deferred follow-up.
    """
    return (
        dossier_path(config, system_name).is_file()
        and rules_path(config, system_name).is_file()
    )


def content_root_state(root: Path) -> str:
    """Return ``"blank"`` or ``"existing"`` for a content root.

    A root is "existing" when it has a ``systems/`` directory or a config file;
    anything else is blank (and blank is not an error).
    """
    from edcg.common.config import CONFIG_FILENAME

    if systems_dir(root).is_dir():
        return "existing"
    if (Path(root) / CONFIG_FILENAME).is_file():
        return "existing"
    return "blank"


def resolve_custom_file(
    env: Mapping[str, str] | None = None,
) -> tuple[Path, Config]:
    """Resolve EDCoPilot's custom file and the config used to reach it.

    Resolution is lazy, per call, because the roots can change between calls
    (the skill resolves them from the environment and the content repo's config
    file each time rather than caching a stale answer). The single failure
    answer is ``FileNotFoundError``, so callers that want an empty payload
    catch it at the call site instead of re-deriving the condition.
    """
    from edcg.common.config import get_config, resolve_edcopilot_root

    environment = os.environ if env is None else env
    config = get_config(environment)
    root = resolve_edcopilot_root(config.content_definitions_root, environment).path
    if root is None:
        raise FileNotFoundError(
            "Could not resolve EDCoPilot's root: set EDCG_EDCOPILOT_ROOT or store "
            "roots.edcopilot in the content repo's config file"
        )
    return root / CUSTOM_FILE_NAME, config
