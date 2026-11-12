"""Per-section content bounds: defaults, overrides, and enforcement."""

import shutil
from pathlib import Path

import pytest

from edcg.rules.validation import RULE_DATA_DIR, validate_content

BASE_RULES = RULE_DATA_DIR / "base.toml"
SYSTEM = "Test System"
STATION = "Test Station (ii-42)"


def _tag(kind: str, n: int, station: str | None = None) -> str:
    """Build one tag block with n phrase lines (first two carry filters)."""
    if kind.startswith("Station"):
        header = f"@{kind}<~>{SYSTEM}<~>{station or STATION}"
    else:
        header = f"@{kind}<~>{SYSTEM}"
    lines = [header, "UPDATEDB"]
    for i in range(n):
        if i == 0:
            lines.append(f"(allbusiness)Line {i + 1} for {kind}.")
        elif i == 1:
            lines.append(f"Unfiltered line {i + 1} for {kind}.")
        else:
            lines.append(f"Line {i + 1} for {kind}.")
    return "\n".join(lines)


def _document(*blocks: str) -> str:
    provenance = "<!-- provenance: tool=test model=test -->"
    return provenance + "\n" + "\n\n".join(blocks) + "\n"


def _facts(n: int) -> str:
    """A StationFact block with n paragraphs."""
    lines = [f"@StationFact<~>{SYSTEM}<~>{STATION}", "UPDATEDB",
             "img_url=https://example.invalid/logo.jpg", "Station facts"]
    lines += [f"Paragraph {i + 1}." for i in range(n)]
    return "\n".join(lines)


def _bounds(content: str, systems_dir: Path):
    result = validate_content(
        content, SYSTEM, base_rules_path=BASE_RULES, systems_dir=systems_dir,
    )
    return [f for f in result.findings if f.rule == "content.bounds"]


def test_below_minimum_is_an_error(tmp_path):
    """SystemGreeting defaults to min 3; two lines is under-filled."""
    findings = _bounds(_document(_tag("SystemGreeting", 2)), tmp_path)

    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert "3" in findings[0].message


def test_at_minimum_passes_with_filter_lines_counted(tmp_path):
    """Exactly 3 lines passes, even though 2 of them are filter-mandated."""
    assert _bounds(_document(_tag("SystemGreeting", 3)), tmp_path) == []


def test_above_maximum_is_a_warning(tmp_path):
    """SystemGreeting defaults to max 6; seven lines is a warning, not an error."""
    findings = _bounds(_document(_tag("SystemGreeting", 7)), tmp_path)

    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert "6" in findings[0].message


def test_station_chatter_uses_its_own_bounds(tmp_path):
    """Chatter has a higher floor than a greeting."""
    findings = _bounds(_document(_tag("StationChatter", 5)), tmp_path)

    assert len(findings) == 1
    assert findings[0].severity == "error"


def test_station_fact_counts_paragraphs_after_the_title(tmp_path):
    """The title line is not a content paragraph."""
    assert _bounds(_document(_facts(3)), tmp_path) == []

    findings = _bounds(_document(_facts(0)), tmp_path)
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert "0 paragraph(s)" in findings[0].message


def test_station_fact_above_maximum_names_paragraphs(tmp_path):
    findings = _bounds(_document(_facts(4)), tmp_path)

    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert "4 paragraph(s)" in findings[0].message


def _system_rules(tmp_path: Path, body: str) -> Path:
    systems = tmp_path / "systems"
    systems.mkdir()
    (systems / "test-system.md").write_text("# dossier\n", encoding="utf-8")
    (systems / "test-system.rules.toml").write_text(
        f'[system]\nnames = ["{SYSTEM}"]\ndossier = "test-system.md"\n\n{body}\n',
        encoding="utf-8",
    )
    return systems


def test_system_rules_override_a_kind(tmp_path):
    """The system's own rules replace the base bound for that kind."""
    systems = _system_rules(tmp_path, "[content.bounds]\nSystemGreeting = [5, 10]")

    findings = _bounds(_document(_tag("SystemGreeting", 3)), systems)

    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert "5" in findings[0].message


def test_station_override_applies_only_to_that_station(tmp_path):
    """A per-station override raises chatter only for the named station."""
    systems = _system_rules(
        tmp_path,
        '[content.bounds.stations."Busy Port (ii-42)"]\nStationChatter = [10, 20]',
    )
    content = _document(
        _tag("StationChatter", 6, station="Busy Port (ii-42)"),
        _tag("StationChatter", 6, station=STATION),
    )

    findings = _bounds(content, systems)

    assert len(findings) == 1
    assert "Busy Port" in findings[0].message
    assert findings[0].severity == "error"


def test_unknown_station_override_warns(tmp_path):
    """A station name that is not in the content is a warning, not silence."""
    systems = _system_rules(
        tmp_path,
        '[content.bounds.stations."Ghost Station (ii-42)"]\nStationChatter = [10, 20]',
    )

    findings = _bounds(_document(_tag("StationChatter", 6)), systems)

    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert "Ghost Station" in findings[0].message


def test_unknown_bounds_kind_warns(tmp_path):
    """A bounds key naming no tag kind can never match: warn, not silence."""
    systems = _system_rules(tmp_path, "[content.bounds]\nNotAKind = [1, 2]")

    findings = _bounds(_document(_tag("SystemGreeting", 3)), systems)

    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert "NotAKind" in findings[0].message
    # The author is told which spellings the key could have meant.
    assert "SystemGreeting" in findings[0].message


def test_unknown_bounds_station_kind_warns(tmp_path):
    """A station sub-key naming no tag kind names both station and key."""
    systems = _system_rules(
        tmp_path,
        f'[content.bounds.stations."{STATION}"]\nAlsoNotAKind = [1, 2]',
    )

    findings = _bounds(_document(_tag("StationChatter", 6)), systems)

    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert STATION in findings[0].message
    assert "AlsoNotAKind" in findings[0].message
    assert "StationChatter" in findings[0].message


def test_known_bounds_produce_no_unknown_kind_warning(tmp_path):
    """A real kind in [content.bounds] is a valid override, not an unknown key."""
    systems = _system_rules(tmp_path, "[content.bounds]\nSystemGreeting = [4, 8]")

    findings = _bounds(_document(_tag("SystemGreeting", 5)), systems)

    assert findings == []


def test_unknown_base_bounds_kind_warns(tmp_path):
    """The base [content.bounds] is checked too: a bogus key there is inert."""
    data = tmp_path / "data"
    shutil.copytree(RULE_DATA_DIR, data)
    base_toml = data / "base.toml"
    text = base_toml.read_text(encoding="utf-8")
    assert "[content.bounds]\n" in text
    base_toml.write_text(
        text.replace("[content.bounds]\n", "[content.bounds]\nNotAKind = [1, 2]\n", 1),
        encoding="utf-8",
    )
    systems = _system_rules(tmp_path, "[content.bounds]\nSystemGreeting = [3, 6]")

    result = validate_content(
        _document(_tag("SystemGreeting", 3)), SYSTEM,
        base_rules_path=data / "base.toml", systems_dir=systems,
    )
    findings = [f for f in result.findings if f.rule == "content.bounds"]

    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert "NotAKind" in findings[0].message
