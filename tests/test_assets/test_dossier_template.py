"""Tests for the static dossier template asset.

These are ports of the old ``tests/test_templates_render.py`` dossier tests in
the generator repo. The old tests rendered ``dossier.md.j2`` through Jinja2; the
new design ships the zero-iteration render as a static asset, so each surviving
test asserts the same property against the static text. Where an old test
asserted loop expansion, the port asserts that no loop artifacts remain and
that the zero-iteration table/section structure is present instead.

The old Jinja template ``rules.toml.j2`` was dropped by the new design, so its
tests are deleted. ``all.rules.toml.example`` still ships: ``init`` copies it
into every new content repository, and ``tests/test_skill/test_assets.py``
guards its neutrality, so there is nothing to assert here.
"""

import pytest

from edcg.rules.engine import get_template

ASSET = "dossier-template.md"


def _section(text: str, start: str, end: str) -> str:
    """Return the slice of ``text`` from ``start`` up to ``end``."""
    begin = text.index(start)
    finish = text.index(end, begin)
    return text[begin:finish]


def _assert_table_header(text: str, header: str) -> None:
    """Assert ``header`` exists and is followed by its separator row."""
    lines = text.splitlines()
    assert header in lines, f"Missing table header: {header}"
    index = lines.index(header)
    columns = header.count("|") - 1
    assert lines[index + 1] == "|" + "---|" * columns


def _assert_no_table_rows(text: str, header: str) -> None:
    """Assert a zero-iteration table (header only, no data rows)."""
    rows = [line for line in text.splitlines() if line.startswith("| ")]
    assert rows == [header], f"Unexpected table rows for {header!r}: {rows[1:]}"


class TestDossierTemplateAsset:
    """Tests for the static dossier-template.md asset."""

    def test_dossier_template_has_all_sections(self):
        """Old test: template contains all 9 spine sections (static asset)."""
        template_str = get_template(ASSET)
        expected_sections = [
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
        for section in expected_sections:
            assert section in template_str, f"Missing section: {section}"

    def test_dossier_template_renders_minimal_context(self):
        """Old test: minimal context renders. Static port: placeholders present.

        The old test supplied "Test System", "Test Architect", "Test Group",
        revision "123", lore text and two tone rules, then asserted each landed
        in the output. The static asset keeps a placeholder for every scalar and
        renders the tone-rule loop at zero iterations, so the port asserts the
        placeholders and the empty list structure.
        """
        template_str = get_template(ASSET)
        assert "<system name>" in template_str
        assert "<architect>" in template_str
        assert "<colonising group>" in template_str
        assert "<raven revision>" in template_str
        assert "<lore_theme>" in template_str

        tone_rules = _section(
            template_str, "## 3. Tone rules (hard constraints)", "\n---\n"
        )
        assert "Rule 1" not in tone_rules
        assert "Rule 2" not in tone_rules
        assert not [ln for ln in tone_rules.splitlines() if ln.startswith("- ")]

    def test_dossier_template_with_bodies(self):
        """Old test: body map shows bodies. Static port: header, zero rows."""
        template_str = get_template(ASSET)
        body_map = _section(template_str, "### Body map", "> **<body_map_notes_title>**")
        header = "| Body | Type | Role in the theme |"
        _assert_table_header(body_map, header)
        _assert_no_table_rows(body_map, header)
        assert "Body 1" not in body_map
        assert "Main world" not in body_map

    def test_dossier_template_with_bridge_systems(self):
        """Old test: bridge systems section. Static port: guidance, zero rows."""
        template_str = get_template(ASSET)
        bridge = _section(
            template_str,
            "| System | Distance from here | Contents | Attachment |",
            "They are also <bridge_distance_between>",
        )
        header = "| System | Distance from here | Contents | Attachment |"
        _assert_table_header(bridge, header)
        _assert_no_table_rows(bridge, header)
        assert "Two nearby systems were colonised for one reason only" in template_str
        assert "Bridge 1" not in bridge

    def test_dossier_template_with_body_map_notes(self):
        """Old test: body map notes. Static port: title placeholder, zero notes."""
        template_str = get_template(ASSET)
        notes = _section(
            template_str, "> **<body_map_notes_title>**", "### The bridge systems"
        )
        assert "> **<body_map_notes_title>**" in notes
        assert "Note 1" not in notes
        assert "Note 2" not in notes
        note_lines = [
            ln
            for ln in notes.splitlines()
            if ln.startswith("> ") and ln != "> **<body_map_notes_title>**"
        ]
        assert not note_lines

    def test_dossier_template_with_stations(self):
        """Old test: station table. Static port: header, zero rows."""
        template_str = get_template(ASSET)
        stations = _section(
            template_str,
            "| Station | Where it is | Evidence |",
            "**`prometheus` outposts are space based**",
        )
        header = "| Station | Where it is | Evidence |"
        _assert_table_header(stations, header)
        _assert_no_table_rows(stations, header)
        assert "Station A" not in stations

    def test_dossier_template_with_no_pad_sites(self):
        """Old test: no-pad table. Static port: header, zero rows."""
        template_str = get_template(ASSET)
        no_pad = _section(
            template_str, "The sites here with no pads", "### Complete (<complete_count>)"
        )
        header = "| Site with no pads | Build type | Where its material is instead |"
        _assert_table_header(no_pad, header)
        _assert_no_table_rows(no_pad, header)
        assert "Hub 1" not in no_pad
        assert "aegle" not in no_pad

    def test_dossier_template_with_site_lists(self):
        """Old test: four site tables. Static port: four headers, zero rows."""
        template_str = get_template(ASSET)
        header = "| Site | Build type | Body |"
        sections = [
            (
                "Complete (<complete_count>)",
                "Under construction (<building_count>)",
            ),
            (
                "Under construction (<building_count>)",
                "Definitely planned (<planned_count>)",
            ),
            (
                "Definitely planned (<planned_count>)",
                "Tentatively planned (<tentative_count>)",
            ),
            (
                "Tentatively planned (<tentative_count>)",
                "Security balance, mapped",
            ),
        ]
        for start, end in sections:
            table = _section(template_str, f"### {start}", f"### {end}")
            _assert_table_header(table, header)
            _assert_no_table_rows(table, header)
            assert "Site 1" not in table
        assert "Two NATO words = placeholder name." in template_str

    def test_dossier_template_with_corrections(self):
        """Old test: corrections log. Static port: header, zero rows."""
        template_str = get_template(ASSET)
        corrections = _section(
            template_str,
            "## 5. Corrections log (do not reintroduce these)",
            "\n---\n",
        )
        header = "| Wrong | Right | Note |"
        _assert_table_header(corrections, header)
        _assert_no_table_rows(corrections, header)
        assert "Wrong Name" not in corrections

    def test_dossier_template_with_unresolved_sites(self):
        """Old test: unresolved sites render.

        The old test rendered ``unresolved_sites=["[Unknown]", "[Facility?]"]``
        and asserted both names appeared. The static asset is the zero-iteration
        render, so the loop contributes nothing and the source sentence ends at
        ``parentheses: .``. There is no ``<unresolved_sites>`` token; asserting
        one would assert a render that does not exist.
        """
        template_str = get_template(ASSET)
        section_6 = _section(template_str, "## 6. Site list maintenance", "## 7. Coverage")
        assert "names use square brackets rather than\nparentheses: ." in section_6
        assert "<unresolved_sites>" not in template_str
        assert "[Unknown]" not in template_str
        assert "[Facility?]" not in template_str
        assert "They look like hand-entered duplicates and are not part of the plan" in section_6

    def test_dossier_template_with_covered_stations(self):
        """Old test: covered stations list. Static port: guidance, zero entries."""
        template_str = get_template(ASSET)
        covered = _section(
            template_str, "### Stations covered", "### Where the remaining themes are heard"
        )
        assert "sites are deliberately excluded" in covered
        assert "<!-- Covered stations list would be populated here -->" in covered
        assert "Station A" not in covered
        assert " · " not in covered

    def test_dossier_template_with_voices(self):
        """Old test: voices by category. Static port: heading, zero entries."""
        template_str = get_template(ASSET)
        voices = _section(template_str, "### Voices used", "### Addressing the player")
        assert "### Voices used" in voices
        assert "<!-- Voices by category would be populated here -->" in voices
        assert "ControlVoice1" not in voices
        assert "CharVoice1" not in voices
        assert not [ln for ln in voices.splitlines() if ln.startswith("- ")]

    def test_dossier_template_with_open_threads(self):
        """Old test: open threads. Static port: heading, zero entries."""
        template_str = get_template(ASSET)
        threads = template_str[template_str.index("## 9. Open threads (TODO)"):]
        assert "<!-- Open threads would be populated here -->" in threads
        assert "Thread 1" not in threads
        assert "Description 1" not in threads
        assert not [ln for ln in threads.splitlines() if ln.startswith("- ")]

    def test_dossier_template_missing_required_context_raises(self):
        """Old test: missing ``system_name`` raises StrictUndefined.

        The static asset is never rendered, so nothing can raise. The port
        asserts the scaffold still supplies every scalar the old minimal context
        had to provide, which is what the raising test protected.
        """
        template_str = get_template(ASSET)
        for placeholder in (
            "<system name>",
            "<architect>",
            "<colonising group>",
            "<raven revision>",
            "<lore_theme>",
            "<conversation_types>",
            "<token_usage_description>",
            "<voices_description>",
        ):
            assert placeholder in template_str
        assert "{{" not in template_str
        assert "{%" not in template_str

    def test_templates_use_correct_syntax(self):
        """Old test: templates parse as Jinja. Static port: no Jinja constructs.

        The old test parsed ``dossier.md.j2``, ``rules.toml.j2`` and
        ``all.rules.toml.example``. The Jinja templates were dropped by the
        design change; only the static dossier asset remains to check here, and
        it must contain no Jinja syntax at all.
        """
        template_str = get_template(ASSET)
        assert template_str
        assert "{{" not in template_str
        assert "}}" not in template_str
        assert "{%" not in template_str
        assert "%}" not in template_str
        assert "<%" not in template_str

    def test_dossier_template_asset_has_no_jinja_syntax(self):
        """Test the asset contains no Jinja or pseudo-directive residue."""
        template_str = get_template(ASSET)
        assert "{{" not in template_str
        assert "{%" not in template_str
        assert "<for" not in template_str
        assert "<endfor" not in template_str
        assert "<if" not in template_str
        assert "<else" not in template_str
        assert "loop." not in template_str
        assert "|length" not in template_str
        assert ".items()" not in template_str

    def test_dossier_template_asset_has_placeholder_values(self):
        """Test dossier template asset has placeholder values."""
        template_str = get_template(ASSET)
        for placeholder in (
            "<system name>",
            "<architect>",
            "<colonising group>",
            "<raven revision>",
            "<review date>",
            "<body_map_notes_title>",
            "<complete_count>",
            "<building_count>",
            "<planned_count>",
            "<tentative_count>",
            "<conversation_types>",
            "<token_usage_description>",
            "<bridge systems dossier>",
            "<bridge dossier>",
            "<bridge_distance_between>",
        ):
            assert placeholder in template_str, f"Missing placeholder: {placeholder}"

    def test_dossier_template_asset_has_guidance_text(self):
        """Test dossier template asset has guidance text intact."""
        template_str = get_template(ASSET)
        assert "Section 4 is the census" in template_str
        assert "Two NATO words = placeholder name" in template_str
        assert "The player is addressed by token everywhere" in template_str
        assert "Station tag naming rule:" in template_str
        assert "content.station_landable" in template_str
        assert "The speech format rules" in template_str

    def test_dossier_template_asset_has_no_mojibake(self):
        """Test dossier template asset has no mojibake and keeps real em dashes."""
        template_str = get_template(ASSET)
        assert "\uFFFD" not in template_str
        for mojibake in ("ΓÇö", "┬╖", "Γê⌐┐╜"):
            assert mojibake not in template_str, f"Mojibake sequence present: {mojibake}"
        assert template_str.count("\u2014") >= 1

    def test_dossier_template_asset_has_em_dash(self):
        """Test dossier template asset uses U+2014 in the H1."""
        template_str = get_template(ASSET)
        first_line = template_str.splitlines()[0]
        assert first_line == "# <system name> \u2014 system dossier"
        assert "# <system name> - system dossier" not in template_str

    def test_dossier_template_asset_has_zero_iteration_structures(self):
        """Test every zero-iteration table keeps its header and has no rows."""
        template_str = get_template(ASSET)
        for header in (
            "| Fact | Value |",
            "| Body | Type | Role in the theme |",
            "| System | Distance from here | Contents | Attachment |",
            "| Station | Where it is | Evidence |",
            "| Site with no pads | Build type | Where its material is instead |",
            "| Site | Build type | Body |",
            "| Wrong | Right | Note |",
        ):
            _assert_table_header(template_str, header)
        for heading in (
            "### Complete (<complete_count>)",
            "### Under construction (<building_count>)",
            "### Definitely planned (<planned_count>)",
            "### Tentatively planned (<tentative_count>)",
        ):
            assert heading in template_str

    def test_dossier_template_asset_has_correct_section_6_content(self):
        """Test section 6 carries the source's unresolved-site text, once."""
        template_str = get_template(ASSET)
        section_6 = _section(template_str, "## 6. Site list maintenance", "## 7. Coverage")
        assert "They look like hand-entered duplicates and are not part of the plan" in section_6
        assert "parentheses: ." in section_6
        assert "Orbital Construction Site:" not in section_6
        assert template_str.count("Orbital Construction Site:") == 1

    def test_dossier_template_asset_has_correct_section_7_broadcast(self):
        """Test section 7 keeps the true zero-iteration broadcast/in-progress forms."""
        template_str = get_template(ASSET)
        section_7 = _section(template_str, "## 7. Coverage", "## 8. Writing rules")
        assert "and it mixes announcements," in section_7
        assert "monologues and multi-character conversations: ." in section_7
        assert "The  currently report an" in section_7
        assert "The 0 currently report an" not in section_7
        assert "for those 0 goes live when each site completes." in section_7


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
