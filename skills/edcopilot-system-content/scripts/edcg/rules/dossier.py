"""Dossier markdown parsing for the EDCoPilot system content skill.

A dossier is prose plus a handful of machine-readable conventions: numbered
sections, a site table in section 4, a ``Voices used`` list in section 8 and a
station-coverage list in section 7. Reading those is one subject, so it lives
here rather than among the speech-content rules in ``validation.py``.

The names are public because ``rules/validation.py`` and ``repo/brief.py`` both
consume them; nothing imports a leading underscore across a module boundary.
"""

import re

DOSSIER_SECTIONS = [
    "Identity and canon",
    "Lore and theme",
    "Tone rules (hard constraints)",
    "Canon site table",
    "Corrections log (do not reintroduce these)",
    "Site list maintenance",
    "Coverage",
    "Writing rules",
    "Open threads (TODO)",
]

SECTION_RE = re.compile(r"^##\s+(\d+)\.\s*(.*?)\s*$")
VOICE_TAG_RE = re.compile(r"\[<([^>]+)>\]")

_DESCRIPTIVE_PREFIXES = (
    "Built", "Tentative", "and ", "so ", "the ", "a ", "an ",
)


def parse_sections(dossier: str) -> tuple[dict[int, tuple[str, list[str]]], list[int]]:
    """Parse a dossier into ``{section_num: (title, lines)}`` and section order."""
    sections: dict[int, tuple[str, list[str]]] = {}
    section_order: list[int] = []
    current_num = None
    current_title = None
    current_lines: list[str] = []

    for line in dossier.splitlines():
        match = SECTION_RE.match(line)
        if match:
            if current_num is not None:
                sections[current_num] = (current_title, current_lines)
            current_num = int(match.group(1))
            current_title = match.group(2).strip()
            current_lines = []
            section_order.append(current_num)
        else:
            current_lines.append(line)

    if current_num is not None:
        sections[current_num] = (current_title, current_lines)

    return sections, section_order


def extract_site_table(lines: list[str]) -> list[dict]:
    """Extract site table rows from section 4 lines.

    Returns list of {name, build_type, body, status} dicts.
    Looks for tables with "Build type" column and a site name column.
    Handles variations like "Site | Build type | Body" or "System | Site | Build type | Orbits".
    Status is one of: complete, build, plan, tentative.
    """
    sites = []
    i = 0
    current_status = "unknown"

    while i < len(lines):
        line = lines[i].strip()

        # Track subsection status
        if line.startswith("### Complete"):
            current_status = "complete"
        elif line.startswith("### Under construction"):
            current_status = "build"
        elif line.startswith("### Definitely planned"):
            current_status = "plan"
        elif line.startswith("### Tentatively planned"):
            current_status = "tentative"

        # Look for the header row - must have "Build type" column
        if line.startswith("|") and "Build type" in line:
            # Found a potential site table header, check for separator row next
            if i + 1 < len(lines):
                sep_line = lines[i + 1].strip()
                if sep_line.startswith("|") and all(
                    c.startswith("-") or c.startswith(":")
                    for c in [c.strip() for c in sep_line.strip("|").split("|")]
                ):
                    # This is a site table, parse header to find column indices
                    header_cells = [c.strip() for c in line.strip("|").split("|")]
                    name_col = None
                    build_type_col = None
                    body_col = None

                    for idx, cell in enumerate(header_cells):
                        cell_lower = cell.lower()
                        if "site" in cell_lower and name_col is None:
                            name_col = idx
                        elif "build type" in cell_lower:
                            build_type_col = idx
                        elif "body" in cell_lower or "orbits" in cell_lower:
                            body_col = idx

                    # If we can't find columns by name, use positional defaults
                    if name_col is None:
                        name_col = 0 if "system" not in header_cells[0].lower() else 1
                    if build_type_col is None:
                        build_type_col = 1 if name_col == 0 else 2
                    if body_col is None:
                        body_col = 2 if build_type_col == 1 else 3

                    # Parse data rows
                    i += 2
                    while i < len(lines):
                        data_line = lines[i].strip()
                        if not data_line.startswith("|"):
                            break
                        cells = [c.strip() for c in data_line.strip("|").split("|")]
                        max_col = max(name_col, build_type_col, body_col)
                        if len(cells) > max_col:
                            name = cells[name_col].strip().strip("`").strip("*").strip("**").strip()
                            build_type_cell = cells[build_type_col].strip()
                            body = cells[body_col].strip().strip("`").strip() if body_col < len(cells) else ""

                            # Extract build type from backticks
                            build_type_match = re.search(r"`([a-z][a-z0-9_]*)`", build_type_cell)
                            build_type = build_type_match.group(1) if build_type_match else ""

                            if name and build_type:
                                sites.append({
                                    "name": name,
                                    "build_type": build_type,
                                    "body": body,
                                    "status": current_status,
                                })
                        i += 1
                    continue  # Continue looking for more tables
        i += 1

    return sites


def extract_voices(lines: list[str], known_tokens: set[str]) -> set[str]:
    """Extract voice names from dossier section 8 (Writing rules).

    Only extracts from the "Voices used" subsection. ``known_tokens`` is the
    lower-cased set of EDCoPilot vocabulary tokens, which are substitutions
    rather than voices; the caller supplies it from the rule data so this list
    has one owner.

    Args:
        lines: The section's lines.
        known_tokens: Lower-cased tokens to exclude from the voice set.
    """
    voices = set()
    in_voices_used = False

    for line in lines:
        stripped = line.strip()

        # Check for "Voices used" header
        if stripped.startswith("###") and "Voices used" in stripped:
            in_voices_used = True
            continue

        # Stop at next subsection header
        if in_voices_used and stripped.startswith("###"):
            break

        if in_voices_used:
            for match in VOICE_TAG_RE.finditer(line):
                voice = match.group(1)
                # Exclude known tokens (case-insensitive)
                if voice.lower() not in known_tokens:
                    voices.add(voice)

    return voices


def normalize_station_name(name: str) -> str:
    """Normalize station name for comparison: strip markdown formatting."""
    return name.strip("`").strip("*").strip()


def known_token_names(vocab: dict) -> list[str]:
    """EDCoPilot vocabulary tokens in ``vocab``, documented and not.

    These are substitution tokens rather than voices, so ``extract_voices``
    filters them out. The list has one owner: the rule data.
    """
    return list(vocab.get("documented", {})) + list(vocab.get("undocumented", []))


def _is_descriptive(line: str) -> bool:
    """True when a coverage line is prose rather than a station name."""
    stripped = line.strip()
    return (
        stripped.startswith(_DESCRIPTIVE_PREFIXES)
        or "deliberately excluded" in stripped
        or "sites with no pads" in stripped
    )


def _parse_station_list(text: str) -> set[str]:
    """Split one coverage line on its separators and keep station-like names."""
    stations: set[str] = set()
    for part in re.split(r"[·•,\n]", text):
        part = part.strip().strip("`").strip("*").strip()
        if part and len(part) > 2 and not part.lower().startswith(
            ("the ", "a ", "an ")
        ):
            stations.add(normalize_station_name(part))
    return stations


def _starts_simple_station_list(stripped: str) -> bool:
    """True when a line without the header looks like the simple list format."""
    return (
        ("·" in stripped or "•" in stripped)
        and not stripped.startswith(("Built", "Tentative"))
        and "deliberately" not in stripped
    )


def extract_coverage_stations(lines: list[str]) -> set[str]:
    """Station names from section 7: a ``### Stations covered`` list or a simple one."""
    stations: set[str] = set()
    in_station_list = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("###") and "Stations covered" in stripped:
            in_station_list = True
            continue
        if in_station_list and stripped.startswith("###"):
            break
        if in_station_list:
            if stripped and not _is_descriptive(stripped):
                stations |= _parse_station_list(stripped)
            continue
        if stripped and _starts_simple_station_list(stripped):
            in_station_list = True
            if not _is_descriptive(stripped):
                stations |= _parse_station_list(stripped)
    return stations


__all__ = [
    "DOSSIER_SECTIONS",
    "SECTION_RE",
    "parse_sections",
    "extract_site_table",
    "extract_voices",
    "extract_coverage_stations",
    "known_token_names",
    "normalize_station_name",
]
