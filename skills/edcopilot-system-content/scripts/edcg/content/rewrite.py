"""Per-tag content rewrite functions for EDCoPilot custom speech extensions.

A rewrite edits one tag's dialog in place, carrying every other line forward
unchanged. Removals and replacements apply to every authored occurrence;
additions go to the latest occurrence only. The file is written but not
committed: the next ``write_content`` owns the content commit.
"""

import os
import re
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional

from edcg.common.config import Config, load_config, resolve_edcopilot_root
from edcg.content.custom_file import CUSTOM_FILE_NAME, _collapse_provenance
from edcg.rules.validation import (
    PROVENANCE_RE,
    RULE_DATA_DIR,
    load_base_config,
    load_kinds,
    parse_content,
    resolve_bounds,
    rewrite_tag_lines,
    validate_content,
)


def _slugify(name: str) -> str:
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


def _system_rules_path(config: Config, system_name: str) -> Path:
    """The system's own rules file inside the content repository."""
    return (
        config.content_definitions_root
        / "systems"
        / f"{_slugify(system_name)}.rules.toml"
    )


def _system_bounds(
    system_name: str, config: Config, base: dict
) -> tuple[dict, dict]:
    """Effective bounds for a system, read from base plus its own rules file."""
    system_cfg = None
    rules_path = _system_rules_path(config, system_name)
    if rules_path.is_file():
        system_cfg = tomllib.loads(rules_path.read_text(encoding="utf-8"))
    return resolve_bounds(base, system_cfg)


def rewrite_tag(
    system_name: str,
    tag: str,
    remove: Optional[List[str]] = None,
    replace: Optional[Dict[str, str]] = None,
    add: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Rewrite one tag's dialog, carrying every other line forward unchanged.

    Removal, replacement and addition are one atomic edit. Removals and
    replacements apply to every authored occurrence of the tag; additions go to
    the latest occurrence only. The rewritten file is validated first: if it
    introduces an error, nothing is written.

    Args:
        system_name: Name of the system the tag belongs to.
        tag: The exact tag line to rewrite.
        remove: Exact dialog lines to delete (each is removed everywhere).
        replace: Mapping of exact old line to its replacement.
        add: Lines to append to the latest occurrence's body.

    Returns:
        Dictionary with removed, replaced, added, commit_hash (always None;
        the next write_content commits the staged edit) and file_path.

    Raises:
        FileNotFoundError: When EDCoPilot's root or the content file is missing.
        ValueError: When the tag or a named line is not there, when there is
            nothing to change, or when the edit introduces a validation error.
    """
    config = load_config(os.environ)
    root = resolve_edcopilot_root(config.content_root, os.environ).path
    if root is None:
        raise FileNotFoundError("Could not resolve EDCoPilot root")

    custom_file = root / CUSTOM_FILE_NAME
    if not custom_file.is_file():
        raise FileNotFoundError(f"content file not found: {custom_file}")

    text = custom_file.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    lines, counts = rewrite_tag_lines(
        lines, tag, remove=remove, replace=replace, add=add,
    )
    new_text = "\n".join(lines) + "\n"

    # Validate the rewritten file, blocking only errors the edit introduces:
    # pre-existing findings must not stop a fix that leaves them untouched.
    before = validate_content(_collapse_provenance(text), system_name)
    before_errors = {
        (finding.rule, finding.message)
        for finding in before.findings
        if finding.severity == "error"
    }

    result = validate_content(_collapse_provenance(new_text), system_name)
    errors = [
        finding for finding in result.findings
        if finding.severity == "error"
        and (finding.rule, finding.message) not in before_errors
    ]
    if errors:
        detail = "; ".join(
            f"{finding.rule}: {finding.message}" for finding in errors[:5]
        )
        raise ValueError(f"rewrite failed validation, nothing written: {detail}")

    custom_file.write_text(new_text, encoding="utf-8", newline="\r\n")

    # Stage nothing and commit nothing: write_content owns the content commit,
    # so a rewrite and an append land in one predictable commit.
    return {
        **counts,
        "commit_hash": None,
        "file_path": str(custom_file),
        "tag": tag,
    }


def get_system_content(
    system_name: str,
) -> Dict[str, Any]:
    """Return the authored content for a system, with its section bounds.

    Use this before removing or replacing dialog: it reports every authored tag,
    the lines currently under it, how many there are, and the minimum and
    maximum that apply.

    Args:
        system_name: Name of the system whose content to read.

    Returns:
        Dictionary with system_name and tags. Each tag carries: tag (exact tag
        line), kind, station, lines (from the latest occurrence), occurrences
        (how many blocks contain it), duplicate_lines (lines present in more
        than one block), count, min and max. For a StationFact, count is the
        number of paragraphs after the title; the title is not counted.
    """
    config = load_config(os.environ)
    root = resolve_edcopilot_root(config.content_root, os.environ).path
    if root is None:
        return {"system_name": system_name, "tags": []}

    custom_file = root / CUSTOM_FILE_NAME
    base = load_base_config(RULE_DATA_DIR)
    kinds, stations = _system_bounds(system_name, config, base)

    if not custom_file.is_file():
        return {"system_name": system_name, "tags": []}

    parsed = parse_content(custom_file, PROVENANCE_RE, load_kinds(base))
    authored = [
        tag for tag in parsed.authored_tags()
        if tag.system == system_name or (tag.decl and tag.station)
    ]

    grouped: Dict[str, Dict] = {}
    for tag in authored:
        raw_tag = parsed.lines[tag.line - 1].strip()
        entry = grouped.setdefault(raw_tag, {
            "tag": raw_tag,
            "kind": tag.kind,
            "station": tag.station,
            "occurrences": 0,
            "lines": [],
            "seen": {},
        })
        entry["occurrences"] += 1
        entry["lines"] = [phrase.raw for phrase in tag.phrases]
        for phrase in tag.phrases:
            entry["seen"][phrase.raw] = entry["seen"].get(phrase.raw, 0) + 1

    tags_out = []
    for entry in grouped.values():
        bound = None
        if entry["station"]:
            bound = stations.get(entry["station"], {}).get(entry["kind"])
        if bound is None:
            bound = kinds.get(entry["kind"])
        count = len(entry["lines"])
        if entry["kind"] == "StationFact":
            count = max(count - 1, 0)
        tags_out.append({
            "tag": entry["tag"],
            "kind": entry["kind"],
            "station": entry["station"],
            "lines": entry["lines"],
            "occurrences": entry["occurrences"],
            "duplicate_lines": sorted(
                line for line, n in entry["seen"].items() if n > 1
            ),
            "count": count,
            "min": bound[0] if bound else None,
            "max": bound[1] if bound else None,
        })

    return {"system_name": system_name, "tags": tags_out}
