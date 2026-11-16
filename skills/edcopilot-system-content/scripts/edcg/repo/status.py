"""The derived workflow checklist behind ``edcg status`` (G1).

State comes from the repository and files only (D4): the config file, the
house-rules file, the system's dossier and rules pair, the commits that touched
that pair, the authored content in EDCoPilot's custom file, and the ``UPDATEDB``
markers under it. Nothing is stored, so a fresh session sees exactly the state a
previous one left behind.

Two derivations are deliberately narrow:

* The content line uses ``tag.system == system_name`` and nothing else (D8).
  It does not call :func:`edcg.content.rewrite.get_system_content`, whose read
  also keeps tags that declare a station without their own system. That fallback
  is right when reading a running file and wrong for a checklist: an approximate
  "content exists" is the "checklist that lies" the spec rules out.
* The marker line reads the same parsed tags (``Tag.marker_line``), the only
  marker reader the package has, so a marker is reported only where one is.

Conversation-side steps cannot be seen here at all. The missing-definition line
says so in words (the interview is conversation), so its absence is not mistaken
for a forgotten step.

The report is prose on stdout. ``status`` exits 0 for every state (D9): a report
is not a failed check.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from edcg.common.config import CONFIG_FILENAME, Config, resolve_edcopilot_root
from edcg.common.layout import (
    CUSTOM_FILE_NAME,
    PROVENANCE_RE,
    dossier_path,
    rules_path,
    slugify,
    systems_dir,
)
from edcg.repo.gitrepo import GitRepo
from edcg.rules.validation import (
    ALL_RULES,
    RULE_DATA_DIR,
    Tag,
    load_base_config,
    load_kinds,
    parse_content,
)

HEADING = (
    "edcg status - the workflow's mechanical state "
    "(repo + files; the conversation is invisible)"
)

HOUSE_RULES_STEP = (
    "create it from the skill's rules example and review each section with the "
    "user (SKILL.md Setup step 3)"
)


@dataclass(frozen=True)
class SystemState:
    """Everything one system's checklist needs, already derived."""

    name: str
    slug: str
    named: bool
    has_dossier: bool
    has_rules: bool
    definition_commits: int
    content_tags: int
    marked_tags: int
    content_problem: str | None

    @property
    def has_definition(self) -> bool:
        """A definition is the dossier AND rules pair, the rule ``is_new`` uses."""
        return self.has_dossier and self.has_rules

    @property
    def definition_saved(self) -> bool:
        """A saved definition is the pair AND a commit: history holds it."""
        return self.has_definition and self.definition_commits > 0

    @property
    def content_readable(self) -> bool:
        return self.content_problem is None


# ---------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------


def build_status(config: Config, system_name: str | None = None) -> str:
    """The workflow checklist for the repository, or for one system.

    Args:
        config: The content repository's configuration; its root supplies
            ``systems/`` and the git history the report derives from.
        system_name: When given, the full checklist for that system. When None,
            the repository-wide lines plus one state line per system (D7).

    Returns:
        One prose block, lines joined by ``\\n``; no trailing newline.

    Raises:
        ConfigError: When the configuration cannot be read. The CLI reports that
            as the repository's state rather than as a failed check (D9).
    """
    tags_by_system, content_problem = _authored_tags(config)
    if system_name is not None:
        return _render_system(config, system_name, tags_by_system, content_problem)
    return _render_repository(config, tags_by_system, content_problem)


def build_unreadable_status(reason: str) -> str:
    """The report for a repository whose configuration cannot be read.

    A status report is not a failed check, so the CLI prints this and exits 0
    even when the content root or its config file is unusable (D9): the caller
    asked where things stand, and the honest answer is "nowhere until this is
    fixed".
    """
    return "\n".join(
        [
            HEADING,
            "",
            f"[ ] repository: cannot read the repository: {reason}",
            "    next: fix the reported path or file, then re-run edcg.py status "
            "(edcg.py doctor names the failing check)",
        ]
    )


def _authored_tags(config: Config) -> tuple[dict[str, list[Tag]], str | None]:
    """Authored tags grouped by their strict system name, and why if unreadable.

    A custom file that does not exist yet is readable and empty: no content has
    been written, which is a state, not a problem. An unresolved EDCoPilot root
    is different - the probe could not run - and the caller says so instead of
    reporting absence.
    """
    resolved = resolve_edcopilot_root(config.content_definitions_root, os.environ)
    if resolved.path is None:
        if resolved.stale is not None:
            return {}, (
                "EDCoPilot's root is configured but no longer exists "
                f"({resolved.stale})"
            )
        return {}, "EDCoPilot's root is not configured"

    custom_file = resolved.path / CUSTOM_FILE_NAME
    if not custom_file.is_file():
        return {}, None

    base = load_base_config(RULE_DATA_DIR)
    try:
        parsed = parse_content(custom_file, PROVENANCE_RE, load_kinds(base))
    except UnicodeDecodeError:
        # A file in another encoding is not a readable custom file. Unicode
        # errors are ValueErrors, not OSErrors, so they would otherwise reach
        # main's ValueError handler and turn a report into exit 1.
        return {}, "the custom file cannot be read (not valid UTF-8)"
    except OSError as exc:
        # A locked or unreadable file is a probe that could not run, not an
        # empty file (EDCoPilot itself may hold it open on Windows). Saying so
        # keeps the report honest and keeps D9: no exit 1 from a report.
        return {}, f"the custom file cannot be read ({exc.strerror or exc})"
    by_system: dict[str, list[Tag]] = {}
    for tag in parsed.authored_tags():
        if tag.system:
            by_system.setdefault(tag.system, []).append(tag)
    return by_system, None


def _system_slugs(config: Config) -> list[str]:
    """Every slug with a dossier or rules file, excluding the house rules."""
    directory = systems_dir(config)
    if not directory.is_dir():
        return []
    slugs = {path.stem for path in directory.glob("*.md")}
    for path in directory.glob(f"*.rules.toml"):
        if path.name != ALL_RULES:
            slugs.add(path.name[: -len(".rules.toml")])
    return sorted(slugs)


def _declared_name(directory: Path, slug: str) -> str | None:
    """The canonical name a rules file declares, or None when it declares none."""
    rules_file = directory / f"{slug}.rules.toml"
    try:
        data = tomllib.loads(rules_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        # Unreadable, wrongly encoded or unparsable: a file the report cannot
        # name a system from, not a crash and not exit 1 (D9).
        return None
    system = data.get("system")
    if not isinstance(system, dict):
        # `system = 5` is valid TOML and not a system table: a shape the report
        # cannot name, not a crash.
        return None
    names = system.get("names", [])
    if isinstance(names, list) and names and isinstance(names[0], str):
        return names[0]
    return None


def _definition_commits(config: Config, slug: str) -> int:
    """How many commits touched the system's dossier or rules file."""
    root = config.content_definitions_root
    if not GitRepo.is_repo(root):
        # A directory that is not a repository has no history to report. The
        # repository line already reports the root, so this probe stays quiet:
        # GitRepo's non-repo methods warn, and a report must not write a
        # diagnostic it cannot act on.
        return 0
    with GitRepo(root) as repo:
        return len(repo.log_paths(f"systems/{slug}.md", f"systems/{slug}.rules.toml"))


def _observe(
    config: Config,
    name: str,
    slug: str,
    *,
    named: bool,
    tags_by_system: dict[str, list[Tag]],
    content_problem: str | None,
) -> SystemState:
    """Derive one system's state from its files, commits, content and markers."""
    tags = tags_by_system.get(name, []) if named else []
    return SystemState(
        name=name,
        slug=slug,
        named=named,
        has_dossier=dossier_path(config, name).is_file(),
        has_rules=rules_path(config, name).is_file(),
        definition_commits=_definition_commits(config, slug),
        content_tags=len(tags),
        marked_tags=sum(1 for tag in tags if tag.marker_line is not None),
        content_problem=content_problem,
    )


def _listed_states(
    config: Config,
    tags_by_system: dict[str, list[Tag]],
    content_problem: str | None,
) -> list[SystemState]:
    """One state per system the repository shows, name-sorted."""
    directory = systems_dir(config)
    states: list[SystemState] = []
    seen: set[str] = set()
    for slug in _system_slugs(config):
        seen.add(slug)
        declared = _declared_name(directory, slug)
        states.append(
            _observe(
                config,
                declared or slug,
                slug,
                named=declared is not None,
                tags_by_system=tags_by_system,
                content_problem=content_problem,
            )
        )

    # Content written without a definition still exists in the repository, so a
    # listing built from systems/ alone would hide a skip the human made.
    for name in sorted(tags_by_system):
        slug = slugify(name)
        if slug in seen:
            continue
        states.append(
            _observe(
                config,
                name,
                slug,
                named=True,
                tags_by_system=tags_by_system,
                content_problem=content_problem,
            )
        )

    states.sort(key=lambda state: state.name.casefold())
    return states


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _box(done: bool, text: str) -> str:
    return f"{'[x]' if done else '[ ]'} {text}"


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


def _repository_lines(config: Config) -> list[str]:
    """The lines that describe the repository itself, in checklist order."""
    root = config.content_definitions_root
    lines = [_box(True, f"repository: {root}")]

    if (root / CONFIG_FILENAME).is_file():
        lines.append(_box(True, f"config: {CONFIG_FILENAME}"))
    else:
        lines.append(
            _box(
                False,
                f"config: no {CONFIG_FILENAME} - run edcg.py init to scaffold "
                "the repository (SKILL.md Setup step 2)",
            )
        )

    house_rules = systems_dir(config) / ALL_RULES
    if house_rules.is_file():
        lines.append(_box(True, f"house rules: {house_rules}"))
    else:
        lines.append(
            _box(False, f"house rules: no systems/{ALL_RULES} - {HOUSE_RULES_STEP}")
        )
    return lines


def _render_repository(
    config: Config,
    tags_by_system: dict[str, list[Tag]],
    content_problem: str | None,
) -> str:
    lines = [HEADING, "", *_repository_lines(config)]
    lines.append("")
    lines.append(
        "systems (the box is the saved definition; each line names what runs next):"
    )
    states = _listed_states(config, tags_by_system, content_problem)
    if not states:
        lines.append(
            "  (none yet - read references/new-system-interview.md and run the "
            "interview)"
        )
        return "\n".join(lines)
    lines.extend("  " + _summary_line(state) for state in states)
    return "\n".join(lines)


def _summary_line(state: SystemState) -> str:
    """One system, one line: its definition box and the next action."""
    if not state.named:
        return (
            f"[ ] {state.slug} - no readable rules file names this system; "
            "next: save the dossier and rules pair "
            "(references/new-system-interview.md Phase 5)"
        )
    boxed = "[x]" if state.definition_saved else "[ ]"
    return f"{boxed} {state.name} - {_summary_text(state)}"


def _summary_text(state: SystemState) -> str:
    if not state.has_dossier and not state.has_rules:
        return (
            "no definition; next: the new-system interview "
            "(references/new-system-interview.md)"
        )
    if not state.has_definition:
        return (
            "definition incomplete: the dossier and rules pair is the definition; "
            "next: save both files (references/new-system-interview.md Phase 5)"
        )
    if not state.definition_commits:
        return (
            "definition files are uncommitted; next: run edcg.py save-definition "
            "so the pair lands in git"
        )
    if not state.content_readable:
        return (
            f"definition committed; content cannot be read: {state.content_problem}; "
            "next: run edcg.py doctor"
        )
    if not state.content_tags:
        return (
            "definition committed, no content; next: edcg.py writing-brief-data, "
            "then validate-content and write-content (references/writing-brief.md)"
        )
    if state.marked_tags == state.content_tags:
        return (
            "definition committed, "
            f"{_plural(state.content_tags, 'authored tag')}, all marked for "
            "update; next: restart EDCoPilot, check-logs, then markdb remove "
            "after the in-game upload"
        )
    if state.marked_tags:
        return (
            "definition committed, "
            f"{_plural(state.content_tags, 'authored tag')}, "
            f"{state.marked_tags} marked for update; next: edcg.py markdb add "
            "the rest"
        )
    return (
        "definition committed, "
        f"{_plural(state.content_tags, 'authored tag')}, none marked; "
        "next: after the review gate, edcg.py markdb add"
    )


def _render_system(
    config: Config,
    system_name: str,
    tags_by_system: dict[str, list[Tag]],
    content_problem: str | None,
) -> str:
    state = _observe(
        config,
        system_name,
        slugify(system_name),
        named=True,
        tags_by_system=tags_by_system,
        content_problem=content_problem,
    )
    lines = [
        f"edcg status for {system_name} (systems/{state.slug})",
        "",
        *_repository_lines(config),
        _definition_line(state),
        _content_line(state),
        _marker_line(state),
    ]
    return "\n".join(lines)


def _definition_line(state: SystemState) -> str:
    dossier = f"systems/{state.slug}.md"
    rules = f"systems/{state.slug}.rules.toml"
    if state.definition_saved:
        return _box(True, f"definition: {dossier} and {rules} are committed")
    if state.has_definition:
        return _box(
            False,
            f"definition: files exist at {dossier} and {rules} but no commit "
            f"touches systems/{state.slug} - run edcg.py save-definition so the "
            "pair lands in git (references/new-system-interview.md Phase 6)",
        )
    if state.has_dossier or state.has_rules:
        present = dossier if state.has_dossier else rules
        missing = rules if state.has_dossier else dossier
        return _box(
            False,
            f"definition: incomplete - {present} exists without {missing}; the "
            "dossier and rules pair is the definition (is_new semantics) - run "
            "edcg.py save-definition with both files "
            "(references/new-system-interview.md Phase 5, then Phase 6)",
        )
    return _box(
        False,
        "definition: none - the interview is conversation - status cannot see "
        "it; a missing definition here means the definition steps have not run "
        "yet; read references/new-system-interview.md (Phase 5 validation, "
        "Phase 6 save)",
    )


def _content_line(state: SystemState) -> str:
    if not state.content_readable:
        return _box(
            False,
            f"content: {state.content_problem} - run edcg.py doctor "
            "(SKILL.md Setup step 4)",
        )
    if not state.content_tags:
        return _box(
            False,
            f"content: no authored tag for {state.name} - run edcg.py "
            "writing-brief-data, validate-content and write-content "
            "(references/writing-brief.md)",
        )
    return _box(
        True,
        f"content: {_plural(state.content_tags, 'authored tag')} for "
        f"{state.name} - review with edcg.py get-content; edit in place with "
        "edcg.py rewrite-tag",
    )


def _marker_line(state: SystemState) -> str:
    if not state.content_readable:
        return _box(
            False,
            "markers: unknown - the custom file cannot be read, so no marker "
            "is claimed",
        )
    if not state.content_tags:
        return _box(
            False,
            "markers: nothing is authored yet, so there is no marker to set",
        )
    if state.marked_tags == state.content_tags:
        return _box(
            True,
            f"markers: every authored tag for {state.name} is marked for update - "
            "restart EDCoPilot, run edcg.py check-logs, then edcg.py markdb "
            "remove after the in-game upload (SKILL.md Process steps 13-16)",
        )
    unmarked = state.content_tags - state.marked_tags
    if not state.marked_tags:
        return _box(
            False,
            "markers: no authored tag is marked for update - after the review "
            "gate run edcg.py markdb add (SKILL.md Process step 12)",
        )
    return _box(
        False,
        f"markers: {_plural(unmarked, 'authored tag')} not marked for update - "
        "run edcg.py markdb add for the rest (SKILL.md Process step 12)",
    )


__all__ = ["HEADING", "SystemState", "build_status", "build_unreadable_status"]
