"""Tests for per-tag content rewrite (removal, replacement, addition)."""

import pytest

from edcg.content.markdb import markdb_add, markdb_remove
from edcg.rules.validation import (
    PROVENANCE_RE,
    RULES_DIR,
    load_base_config,
    load_kinds,
    parse_content,
    rewrite_tag_lines,
)

TAG = "@StationChatter<~>Test System<~>Test Station (ii-42)"
OTHER = "@SystemGreeting<~>Test System"

FILE = [
    "@ConfirmedCommander",
    "Default EDCoPilot content.",
    "<!-- provenance: tool=old model=old -->",
    TAG,
    "UPDATEDB",
    "(allbusiness)Old line one.",
    "(allbusiness)Old line two.",
    "(allbusiness)Old line three.",
    "",
    "@SystemGreeting<~>Test System",
    "UPDATEDB",
    "(allbusiness)Greeting line.",
    "Greeting unfiltered.",
    "Greeting third.",
    "",
    "<!-- provenance: tool=new model=new -->",
    TAG,
    "UPDATEDB",
    "(allbusiness)New line one.",
    "(allbusiness)New line two.",
    "(allbusiness)New line three.",
]


def _lines():
    return list(FILE)


def test_removal_applies_to_every_occurrence():
    lines, counts = rewrite_tag_lines(
        _lines(), TAG, remove=["(allbusiness)Old line two.", "(allbusiness)New line two."]
    )

    assert counts["removed"] == 2
    assert "(allbusiness)Old line two." not in lines
    assert "(allbusiness)New line two." not in lines
    # Untouched lines are carried forward byte-for-byte.
    assert "(allbusiness)Old line one." in lines
    assert "(allbusiness)New line one." in lines


def test_additions_land_once_on_the_latest_occurrence():
    lines, counts = rewrite_tag_lines(
        _lines(), TAG, add=["(allbusiness)A brand new line."]
    )

    assert counts["added"] == 1
    assert lines.count("(allbusiness)A brand new line.") == 1
    # It sits in the second (latest) block, not the first.
    first_tag = lines.index(TAG)
    second_tag = lines.index(TAG, first_tag + 1)
    new_line = lines.index("(allbusiness)A brand new line.")
    assert new_line > second_tag


def test_replacement_is_exact_and_carries_the_rest():
    lines, counts = rewrite_tag_lines(
        _lines(),
        TAG,
        replace={"(allbusiness)New line three.": "(allbusiness)Rewritten line three."},
    )

    assert counts["replaced"] == 1
    assert "(allbusiness)Rewritten line three." in lines
    assert "(allbusiness)New line one." in lines


def test_unknown_line_is_refused():
    with pytest.raises(ValueError, match="not found"):
        rewrite_tag_lines(_lines(), TAG, remove=["(allbusiness)Not a real line."])


def test_unknown_tag_is_refused():
    with pytest.raises(ValueError, match="tag not found"):
        rewrite_tag_lines(_lines(), "@NoSuchTag<~>X", remove=["anything"])


def test_removing_the_marker_is_refused():
    with pytest.raises(ValueError, match="UPDATEDB"):
        rewrite_tag_lines(_lines(), TAG, remove=["UPDATEDB"])


def test_nothing_to_change_is_refused():
    with pytest.raises(ValueError, match="nothing to change"):
        rewrite_tag_lines(_lines(), TAG)


def test_rewritten_file_still_parses(tmp_path):
    lines, _ = rewrite_tag_lines(
        _lines(),
        TAG,
        remove=["(allbusiness)Old line two.", "(allbusiness)New line two."],
        add=["(allbusiness)Extra line."],
    )
    path = tmp_path / "content.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    base = load_base_config(RULES_DIR)
    parsed = parse_content(path, PROVENANCE_RE, load_kinds(base))

    counts = [
        len(tag.phrases) for tag in parsed.tags if tag.line and tag.phrases
    ]
    assert counts, "no tags parsed after rewrite"


def test_tag_roundtrip_byte_exact(tmp_path, monkeypatch):
    """Parse, rewrite and markdb all carry untouched bytes forward unchanged."""
    path = tmp_path / "content.txt"
    path.write_text("\n".join(FILE) + "\n", encoding="utf-8")

    base = load_base_config(RULES_DIR)
    parsed = parse_content(path, PROVENANCE_RE, load_kinds(base))
    assert parsed.lines == FILE

    lines, counts = rewrite_tag_lines(
        _lines(),
        TAG,
        remove=["(allbusiness)Old line two."],
        add=["(allbusiness)Extra line."],
    )
    assert counts["removed"] == 1
    # Every untouched line survives in order, byte-for-byte; the removal and the
    # addition are the only differences, and the addition lands last.
    expected = [line for index, line in enumerate(FILE) if index != 6]
    expected.append("(allbusiness)Extra line.")
    assert lines == expected

    # markdb add then remove restores the exact bytes on disk.
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    custom = runtime / "EDCoPilot.SpeechExtensions.Custom.txt"
    plain = (
        "@SystemGreeting<~>Test System\r\n"
        "(allbusiness)Hello there.\r\n"
        "Hello there.\r\n"
        "Hello once more.\r\n"
    )
    custom.write_bytes(plain.encode("utf-8"))
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(runtime))
    monkeypatch.setenv("EDCG_AUTO_COMMIT", "false")

    added = markdb_add(["@SystemGreeting<~>Test System"])
    assert added["modified_tags"] == ["@SystemGreeting<~>Test System"]
    assert "UPDATEDB" in custom.read_text(encoding="utf-8")

    markdb_remove(["@SystemGreeting<~>Test System"])
    assert custom.read_bytes() == plain.encode("utf-8")

    # Tag matching is exact: a case-differing tag is a different tag.
    mismatched = markdb_add(["@SystemGreeting<~>test system"])
    assert mismatched["modified_tags"] == []
    assert custom.read_bytes() == plain.encode("utf-8")

    with pytest.raises(ValueError, match="tag not found"):
        rewrite_tag_lines(
            _lines(), "@StationChatter<~>test system<~>Test Station (ii-42)",
            remove=["(allbusiness)New line one."],
        )
