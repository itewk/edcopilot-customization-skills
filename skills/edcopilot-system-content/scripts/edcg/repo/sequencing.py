"""The definition prerequisite and the human override (G2, G3, D6).

Five commands author or mark content, and all of them need the system's
definition: ``writing-brief-data`` reads it, ``validate-content`` and
``write-content`` judge and write against it, ``rewrite-tag`` edits what it
bounds, and ``markdb`` marks what it produced. Without one, the work is blind,
so each command refuses - naming the missing step, the cost of skipping it, and
the flag that skips it anyway.

The wording lives here and nowhere else: the refusal, the warning that records a
human-directed skip, and the check that chooses between them are one answer, so
a command cannot drift from its siblings.

Three rulings shape the module:

* A definition is the dossier AND rules pair, the same rule ``is_new`` and
  ``status`` use. Half a pair is no definition.
* The override is per command and changes nothing on disk. The warning goes to
  stderr, next to the answer rather than inside it, and the transcript is the
  record (G3).
* ``markdb`` carries no system field, so its systems come from the tag lines
  (D6). A kind that declares no system part is exempt: a systemless marker is
  never stranded by a prerequisite about systems.
"""

from __future__ import annotations

import sys
from typing import Iterable, Mapping

from edcg.common.config import Config
from edcg.common.layout import dossier_path, rules_path
from edcg.rules.validation import (
    RULE_DATA_DIR,
    TAG_RE,
    Kind,
    load_base_config,
    load_kinds,
)

#: The per-command flag a human uses to skip the prerequisite deliberately.
SKIP_FLAG = "--allow-no-definition"

#: What skipping a definition costs, in the spec's own words (B2). The refusal
#: and the warning quote it identically, so the human is told the same thing
#: whether they are reading why a command stopped or why it went ahead.
CONSEQUENCES = (
    "without a definition there are no bounds, voices or tag lines - content "
    "will be written blind, validation will be weak, and EDCoPilot coverage "
    "cannot be verified"
)


class DefinitionMissingError(ValueError):
    """A content command needs the system's definition and the repository has none.

    A ValueError so the CLI's established check-failure path reports it: exit 1
    with ``{"error": ...}`` on stdout, exactly like every other refused check,
    and never a traceback.
    """


def has_definition(config: Config, system_name: str) -> bool:
    """Whether the system's definition is saved.

    The definition is the dossier AND rules pair: the rule ``is_new`` applies
    when it decides whether to scaffold, and the rule ``status`` reports. One
    file alone is not a definition.
    """
    return (
        dossier_path(config, system_name).is_file()
        and rules_path(config, system_name).is_file()
    )


def refusal_message(system_name: str) -> str:
    """The refusal: the missing step and its fix, the cost, then the override."""
    return "\n".join(
        (
            f"no definition saved for {system_name} - run the interview, then "
            "validate-definition and save-definition",
            CONSEQUENCES,
            f"if the human chooses to skip this prerequisite, re-run with "
            f"{SKIP_FLAG}",
        )
    )


def require_definition(config: Config, system_name: str) -> None:
    """Refuse unless the system's definition is saved.

    Raises:
        DefinitionMissingError: When the dossier or rules file is absent. The
            message is :func:`refusal_message`, so every command refuses in the
            same words.
    """
    if not has_definition(config, system_name):
        raise DefinitionMissingError(refusal_message(system_name))


def warn_skip(config: Config, system_name: str) -> None:
    """Record a human-directed skip on stderr, restating the same cost (B3).

    Nothing is stored: the transcript is the record (G3). The block names the
    system, the pair that is missing, and the consequences, so a skip can never
    be silent.
    """
    expected = (
        f"{dossier_path(config, system_name)} and "
        f"{rules_path(config, system_name)}"
    )
    print(
        f"warning: no definition saved for {system_name} - {expected} are not "
        f"both present; continuing because {SKIP_FLAG} was given",
        file=sys.stderr,
    )
    print(f"warning: {CONSEQUENCES}", file=sys.stderr)


def ensure_definition(
    config: Config, system_name: str, *, allow_missing: bool
) -> None:
    """Refuse a gated command without a definition, unless the human allowed it.

    ``allow_missing`` is the command's ``--allow-no-definition``. The warning
    fires only when a definition is actually missing: passing the flag where
    nothing is skipped must not invent a warning about a cost nobody paid.
    """
    if has_definition(config, system_name):
        return
    if allow_missing:
        warn_skip(config, system_name)
        return
    require_definition(config, system_name)


def tag_systems(
    tags: Iterable[str], kinds: Mapping[str, Kind] | None = None
) -> list[str]:
    """Every system a ``markdb`` call's tag lines name, in first-seen order.

    ``markdb``'s payload has no system field, so the systems are derived the way
    :func:`edcg.rules.validation.parse_content` reads a tag: split the line after
    ``@Kind`` on ``<~>`` and take the field the kind's ``parts`` names ``system``
    (the first ``<~>`` field for every shipped kind that declares one). A kind
    that declares no system part, an unknown kind and a malformed line name no
    system, so they are exempt rather than stranded (D6): the override covers
    those edges.

    Args:
        tags: The exact tag lines a ``markdb`` call was given.
        kinds: The ``[kinds]`` declarations; loaded from the shipped rule set
            when not supplied.

    Returns:
        Distinct system names with duplicates removed, in the order the tags
        named them.
    """
    declarations = (
        kinds
        if kinds is not None
        else load_kinds(load_base_config(RULE_DATA_DIR))
    )
    systems: list[str] = []
    for raw in tags:
        if not isinstance(raw, str):
            # The payload's tag list is not type-checked per entry; a stray
            # value names no system rather than crashing the refusal path.
            continue
        match = TAG_RE.match(raw.strip())
        if match is None:
            continue
        declaration = declarations.get(match.group("kind"))
        if declaration is None or "system" not in declaration.parts:
            continue
        rest = match.group("rest")
        parts = (
            [part.strip() for part in rest.split("<~>") if part.strip()]
            if "<~>" in rest
            else []
        )
        index = declaration.parts.index("system")
        if index < len(parts) and parts[index] not in systems:
            systems.append(parts[index])
    return systems


__all__ = [
    "CONSEQUENCES",
    "SKIP_FLAG",
    "DefinitionMissingError",
    "ensure_definition",
    "has_definition",
    "refusal_message",
    "require_definition",
    "tag_systems",
    "warn_skip",
]
