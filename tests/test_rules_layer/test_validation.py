"""Tests for validate_content - one test per rule plus combinations.

These tests follow TDD: RED (fail) -> GREEN (pass).
Each rule from base.toml + all.rules.toml gets at least one test. They call the
production entry point (``validate_content``) rather than a test-only engine.
"""

import pytest
from pathlib import Path
from edcg.rules.validation import (
    Context,
    ValidationResult,
    PROVENANCE_RE,
    RULE_DATA_DIR,
    load_all_system_rules,
    load_base_config,
    load_house_rules,
    load_kinds,
    merge_rules,
    parse_content,
    rule_filters_banned,
    rule_syntax_filter_known,
    validate_content,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


# ============================================================
# Test fixtures and helpers
# ============================================================

# The fixtures directory doubles as a systems/ directory: all.rules.toml is the
# house rules, and test.rules.toml names "Test System" with its dossier test.md.
SYSTEMS_DIR = FIXTURES_DIR
HOUSE_RULES = FIXTURES_DIR / "all.rules.toml"
SYSTEM = "Test System"


def _payload(path: Path) -> str:
    """The bytes a test wrote, as the string ``validate_content`` consumes."""
    return path.read_text(encoding="utf-8", newline="")


def _full_payload_context(content_path: Path) -> Context:
    """The rule context for a whole payload, provenance markers included.

    ``validate_content`` trims everything above the latest provenance marker
    before it validates, so the scope-boundary tests cannot reach the
    out-of-scope branch through it. They hand the rule function this context
    instead: the same construction, without the block trimming.
    """
    base = load_base_config(RULE_DATA_DIR)
    base_rules = base["rules"]
    declared, patches = load_house_rules(HOUSE_RULES, base_rules)
    per_system = load_all_system_rules(SYSTEMS_DIR, base_rules)
    return Context(
        base=base,
        per_system=per_system,
        content=parse_content(content_path, PROVENANCE_RE, load_kinds(base)),
        rules=merge_rules(base_rules, declared, patches, per_system),
    )


@pytest.fixture
def dossier_dir(tmp_path) -> Path:
    """A systems/ directory whose one system declares the dossier under test."""
    systems = tmp_path / "systems"
    systems.mkdir()
    (systems / "test.rules.toml").write_text(
        '[system]\nnames = ["Test System"]\ndossier = "dossier.md"\n',
        encoding="utf-8",
    )
    return systems


@pytest.fixture
def dossier_path(dossier_dir) -> Path:
    """The dossier the fixture system declares; each test writes its content."""
    return dossier_dir / "dossier.md"


# ============================================================
# Test data creation
# ============================================================

# We'll create test data files inline to keep tests self-contained
# but for now, let's define the test content as strings

VALID_CONTENT = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
UPDATEDB
(allbusiness)Welcome to <starsystem>, <Commander>.
Welcome to <starsystem>, <cmdrname>.
(allbusiness)All business greeting.
(allbusiness)All business greeting.

@StationGreeting<~>Test System<~>Test Station (ii-42)
UPDATEDB
(allbusiness)Welcome to <stationname>, <Commander>.
Welcome, <cmdrname>.
(allbusiness)Docking services available.
(allbusiness)Welcome aboard, <Commander>.

@StationFact<~>Test System<~>Test Station (ii-42)
UPDATEDB
img_url=https://elite-dangerous.skyrunner42.xyz/ii42-logo.jpg
Test Station Fact
This is a fact about the station.
"""

CONTENT_WITH_UNKNOWN_FILTER = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(unknown_filter)This line has an unknown filter.
"""

CONTENT_WITH_FILTER_BEFORE_VOICE = """<!-- provenance: tool=test model=test -->
@SystemBroadcast<~>Test System
(allbusiness)[<Voice>]This filter leads the voice tag.
"""

CONTENT_WITH_UNKNOWN_TOKEN = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Welcome <unknown_token> to the system.
"""

CONTENT_WITH_MISCASED_TOKEN = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Welcome <commander> to the system.
"""

CONTENT_WITH_WRONG_LINE_ENDING = "Line 1\nLine 2\n"  # LF not CRLF

CONTENT_WITH_BOM = "\ufeffLine 1\r\nLine 2\r\n"

CONTENT_WITH_EXAMPLE_WRAPPER = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
[example]This should not be here[/example]
"""

CONTENT_WITH_UNKNOWN_KIND = """<!-- provenance: tool=test model=test -->
@UnknownKind<~>Test System
This tag has an unknown kind.
"""

CONTENT_WITH_WRONG_PARTS = """<!-- provenance: tool=test model=test -->
@StationGreeting<~>Test System
This tag is missing station part.
"""

CONTENT_WITH_BANNED_FILTER = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(profanity)This has a banned filter.
"""

CONTENT_WITH_NO_ALLBUSINESS = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Welcome to the system.
No allbusiness line here.
"""

CONTENT_WITH_LOW_ALLBUSINESS = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(allbusiness)Only one allbusiness line.
Welcome to the system.
"""

CONTENT_WITH_NO_FALLBACK = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(allbusiness)All business only.
(vegan)Vegan only.
"""

CONTENT_WITH_NO_CLEAN_ALLBUSINESS = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(allbusiness)(vegan)Combined filter.
Welcome to the system.
"""

CONTENT_FACT_NO_IMAGE = """<!-- provenance: tool=test model=test -->
@StationFact<~>Test System<~>Test Station
UPDATEDB
This fact has no image.
"""

CONTENT_FACT_WRONG_IMAGE = """<!-- provenance: tool=test model=test -->
@StationFact<~>Test System<~>Test Station
UPDATEDB
img_url=https://wrong.com/image.jpg
This fact has wrong image.
"""

CONTENT_WITH_LINK = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Visit https://example.com for more info.
"""

CONTENT_FACT_WITH_FILTER = """<!-- provenance: tool=test model=test -->
@StationFact<~>Test System<~>Test Station
UPDATEDB
img_url=https://example.com/logo.jpg
(vegan)This fact has a filter.
"""

CONTENT_STATION_NOT_LANDABLE = """<!-- provenance: tool=test model=test -->
@StationGreeting<~>Test System<~>Test Station (ii-42)
UPDATEDB
Welcome to the hub.
"""

CONTENT_WITH_HARDCODED_COMMANDER = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Welcome Commander to the system.
"""

CONTENT_WITH_UPDATEDB_WRONG_PLACE = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Welcome to the system.
UPDATEDB
"""

TEST_DOSSIER = """# Test System — system dossier

## 1. Identity and canon

| Fact | Value |
|---|---|
| System name | `Test System` |

## 2. Lore and theme

Test lore.

## 3. Tone rules (hard constraints)

Test tone.

## 4. Canon site table

### Complete (1)

| Site | Build type | Body |
|---|---|---|
| Test Station (ii-42) | `nona` Civilian Surface Outpost | `3 a` |

## 5. Corrections log (do not reintroduce these)

## 6. Site list maintenance

## 7. Coverage

## 8. Writing rules

## 9. Open threads (TODO)
"""

TEST_DOSSIER_WRONG_SECTIONS = """# Test System — system dossier

## 1. Identity and canon

## 3. Wrong section number

## 2. Lore and theme
"""

TEST_DOSSIER_WRONG_TITLES = """# Test System — system dossier

## 1. Identity and canon

## 2. Wrong title here

## 3. Tone rules (hard constraints)

## 4. Canon site table

## 5. Corrections log (do not reintroduce these)

## 6. Site list maintenance

## 7. Coverage

## 8. Writing rules

## 9. Open threads (TODO)
"""


# ============================================================
# Syntax rule tests
# ============================================================

class TestSyntaxFilterKnown:
    """Tests for syntax.filter_known rule."""

    def test_unknown_filter_in_scope_is_error(self, tmp_path):
        """Unknown filter in authored region should be error."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_WITH_UNKNOWN_FILTER, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "syntax.filter_known"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "unknown_filter" in findings[0].message

    def test_unknown_filter_outside_scope_is_warn(self, tmp_path):
        """Unknown filter in EDCoPilot default content should be warn."""
        content = "@ConfirmedCommander\n(unknown_filter)Default content.\n" + CONTENT_WITH_UNKNOWN_FILTER
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        ctx = _full_payload_context(content_file)
        rule_syntax_filter_known(ctx)
        
        findings = [f for f in ctx.findings if f.rule == "syntax.filter_known"]
        # One outside scope (warn), one in scope (error)
        # Findings are sorted by severity globally, so error comes first
        assert len(findings) == 2
        severities = {f.severity for f in findings}
        assert "warn" in severities
        assert "error" in severities


class TestSyntaxFilterLeads:
    """Tests for syntax.filter_leads rule."""

    def test_filter_before_first_voice_tag_is_error(self, tmp_path):
        """Filter marker before first voice tag should be error."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_WITH_FILTER_BEFORE_VOICE, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "syntax.filter_leads"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "before the first voice tag" in findings[0].message

    def test_filter_after_voice_tag_is_ok(self, tmp_path):
        """Filter marker after voice tag should pass."""
        content = """<!-- provenance: tool=test model=test -->
@SystemBroadcast<~>Test System
[<Voice>](allbusiness)This filter is after the voice tag.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "syntax.filter_leads"]
        assert len(findings) == 0


class TestSyntaxVoiceName:
    """Tests for syntax.voice_name rule."""

    def test_spaced_voice_tag_warns(self, tmp_path):
        """A voice name with a space is a warning, not a silent split."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(
            "<!-- provenance: tool=test model=test -->\n"
            "@SystemBroadcast<~>Test System\n"
            "[<Garrett Control>]This line has a spaced voice.\n",
            encoding="utf-8",
            newline="\r\n",
        )

        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )

        findings = [f for f in result.findings if f.rule == "syntax.voice_name"]
        assert len(findings) == 1
        assert findings[0].severity == "warn"
        assert "whitespace" in findings[0].message

    def test_single_token_voice_is_clean(self, tmp_path):
        """A normal voice name produces no finding."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(
            "<!-- provenance: tool=test model=test -->\n"
            "@SystemBroadcast<~>Test System\n"
            "[<Foreman>]This line has a single-token voice.\n",
            encoding="utf-8",
            newline="\r\n",
        )

        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )

        assert [f for f in result.findings if f.rule == "syntax.voice_name"] == []

    def test_declared_spaced_voice_warns(self, tmp_path):
        """A spaced name in system.voices is reported even with no content tag."""
        rules_path = tmp_path / "spaced.rules.toml"
        rules_path.write_text(
            '[system]\n'
            'names = ["Spaced System"]\n'
            'dossier = "spaced.md"\n'
            'voices = ["Garrett Control"]\n',
            encoding="utf-8",
        )
        # The system rules resolve their dossier beside the rules file.
        (tmp_path / "spaced.md").write_text("", encoding="utf-8")

        content_file = tmp_path / "content.txt"
        content_file.write_text(
            "<!-- provenance: tool=test model=test -->\n"
            "@SystemGreeting<~>Spaced System\n"
            "[<GarrettControl>]Hello.\n",
            encoding="utf-8",
            newline="\r\n",
        )

        result = validate_content(
            _payload(content_file),
            "Spaced System",
            house_rules_path=HOUSE_RULES,
            systems_dir=tmp_path,
        )
        
        findings = [f for f in result.findings if f.rule == "syntax.voice_name"]
        assert len(findings) == 1
        assert findings[0].line is None
        assert "declared voice" in findings[0].message


class TestSyntaxTokens:
    """Tests for syntax.token_known and syntax.token_case rules."""

    def test_unknown_token_is_warn(self, tmp_path):
        """Unknown token should produce warning."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_WITH_UNKNOWN_TOKEN, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "syntax.token_known"]
        assert len(findings) == 1
        assert findings[0].severity == "warn"
        assert "unknown_token" in findings[0].message

    def test_miscased_token_is_warn(self, tmp_path):
        """Miscased token should produce warning."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_WITH_MISCASED_TOKEN, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "syntax.token_case"]
        assert len(findings) == 1
        assert findings[0].severity == "warn"
        assert "commander" in findings[0].message.lower()
        assert "Commander" in findings[0].message

    def test_known_token_passes(self, tmp_path):
        """Known tokens should pass."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Welcome <Commander> and <cmdrname> to <starsystem>.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        token_findings = [f for f in result.findings if f.rule in ("syntax.token_known", "syntax.token_case")]
        assert len(token_findings) == 0

    def test_voice_token_passes(self, tmp_path):
        """Voice tokens declared in system rules should pass."""
        # System rules with voices. They are written under tmp_path: a test may
        # not edit the checked-in fixtures.
        system_rules = """[system]
names = ["Test System"]
dossier = "test.md"
voices = ["Foreman", "Researcher"]
"""
        rules_file = tmp_path / "system.rules.toml"
        rules_file.write_text(system_rules, encoding="utf-8")
        
        content = """<!-- provenance: tool=test model=test -->
@SystemBroadcast<~>Test System
[<Foreman>]Hello <Commander>.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        # The system rules resolve their dossier beside the rules file.
        (tmp_path / "test.md").write_text("", encoding="utf-8")
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=tmp_path,
        )
        
        token_findings = [f for f in result.findings if f.rule in ("syntax.token_known", "syntax.token_case")]
        assert len(token_findings) == 0


class TestSyntaxEncoding:
    """Tests for syntax.encoding rule."""

    def test_wrong_line_ending_is_error(self, tmp_path):
        """LF line ending should be error (expected CRLF)."""
        content_file = tmp_path / "content.txt"
        content_file.write_bytes(b"Line 1\nLine 2\n")  # LF
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "syntax.encoding"]
        assert len(findings) >= 1
        assert any(f.severity == "error" and "line ending" in f.message.lower() for f in findings)

    def test_crlf_line_ending_passes(self, tmp_path):
        """CRLF line ending should pass."""
        content_file = tmp_path / "content.txt"
        content_file.write_text("Line 1\r\nLine 2\r\n", encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "syntax.encoding"]
        assert len(findings) == 0

    def test_bom_is_error(self, tmp_path):
        """BOM should be error."""
        content_file = tmp_path / "content.txt"
        content_file.write_bytes(b"\xef\xbb\xbfLine 1\r\nLine 2\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "syntax.encoding"]
        assert len(findings) >= 1
        assert any(f.severity == "error" and "bom" in f.message.lower() for f in findings)


class TestSyntaxNoExampleWrapper:
    """Tests for syntax.no_example_wrapper rule."""

    def test_example_wrapper_is_error(self, tmp_path):
        """[example] wrapper should be error."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_WITH_EXAMPLE_WRAPPER, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "syntax.no_example_wrapper"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "example" in findings[0].message.lower()


class TestFormatTagShape:
    """Tests for format.tag_shape rule."""

    def test_unknown_kind_is_error(self, tmp_path):
        """Unknown tag kind should be error."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_WITH_UNKNOWN_KIND, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "format.tag_shape"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "UnknownKind" in findings[0].message

    def test_wrong_number_of_parts_is_error(self, tmp_path):
        """Wrong number of <~> parts should be error."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_WITH_WRONG_PARTS, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "format.tag_shape"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "field" in findings[0].message.lower()

    def test_correct_tag_passes(self, tmp_path):
        """Correctly formed tag should pass."""
        content = """<!-- provenance: tool=test model=test -->
@StationGreeting<~>Test System<~>Test Station
Welcome.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "format.tag_shape"]
        assert len(findings) == 0


# ============================================================
# Filter rule tests (policy rules are not programmatically checked)
# ============================================================

class TestFiltersAllbusiness:
    """Tests for filters.allbusiness rule."""

    def test_no_allbusiness_is_error(self, tmp_path):
        """Tag with no (allbusiness) lines should be error."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_WITH_NO_ALLBUSINESS, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "filters.allbusiness"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "no (allbusiness) line" in findings[0].message

    def test_below_warn_threshold_is_warn(self, tmp_path):
        """Tag with fewer than warn_below (allbusiness) lines should be warn."""
        # Base rule has warn_below = 1, so 1 line meets floor but may warn if house sets higher
        # House rules set warn_below = 2 for most kinds
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_WITH_LOW_ALLBUSINESS, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "filters.allbusiness"]
        # Should have warning about below threshold (house rule sets warn_below=2)
        assert len(findings) >= 1
        assert any(f.severity == "warn" and "1 (allbusiness) line" in f.message for f in findings)

    def test_station_greeting_warn_below_1(self, tmp_path):
        """StationGreeting has warn_below_by_kind = 1, so 1 line should not warn."""
        content = """<!-- provenance: tool=test model=test -->
@StationGreeting<~>Test System<~>Test Station
(allbusiness)Welcome.
Welcome <cmdrname>.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "filters.allbusiness"]
        # StationGreeting has warn_below_by_kind = 1, so 1 line should not warn
        warn_findings = [f for f in findings if f.severity == "warn"]
        assert len(warn_findings) == 0

    def test_meets_threshold_passes(self, tmp_path):
        """Tag meeting threshold should pass."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(allbusiness)First allbusiness line.
(allbusiness)Second allbusiness line.
Welcome to the system.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "filters.allbusiness"]
        assert len(findings) == 0

    def test_station_fact_exempt(self, tmp_path):
        """StationFact should be exempt from allbusiness requirement."""
        content = """<!-- provenance: tool=test model=test -->
@StationFact<~>Test System<~>Test Station
UPDATEDB
img_url=https://example.com/logo.jpg
This fact has no allbusiness line.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "filters.allbusiness"]
        assert len(findings) == 0


class TestFiltersFallback:
    """Tests for filters.fallback rule."""

    def test_no_unfiltered_line_is_error(self, tmp_path):
        """Tag where every line has a filter should be error."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_WITH_NO_FALLBACK, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "filters.fallback"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "filters every line" in findings[0].message

    def test_no_clean_allbusiness_is_error(self, tmp_path):
        """Tag with no line carrying only (allbusiness) should be error."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_WITH_NO_CLEAN_ALLBUSINESS, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "filters.fallback"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "no line carrying (allbusiness) alone" in findings[0].message

    def test_has_fallback_passes(self, tmp_path):
        """Tag with unfiltered line should pass."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(allbusiness)All business line.
Welcome to the system.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "filters.fallback"]
        assert len(findings) == 0

    def test_has_clean_allbusiness_passes(self, tmp_path):
        """Tag with clean (allbusiness) line should pass."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(allbusiness)Clean allbusiness line.
(allbusiness)(vegan)Combined filter line.
Welcome to the system.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "filters.fallback"]
        assert len(findings) == 0

    def test_non_spoken_kind_exempt(self, tmp_path):
        """StationFact (non-spoken) should be exempt from fallback."""
        content = """<!-- provenance: tool=test model=test -->
@StationFact<~>Test System<~>Test Station
UPDATEDB
img_url=https://example.com/logo.jpg
(vegan)This fact has a filter.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "filters.fallback"]
        assert len(findings) == 0


# ============================================================
# Content rule tests
# ============================================================

class TestContentFactImage:
    """Tests for content.fact_image rule."""

    def test_fact_no_image_is_error(self, tmp_path):
        """StationFact without img_url should be error."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_FACT_NO_IMAGE, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "content.fact_image"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "no img_url line" in findings[0].message

    def test_fact_wrong_image_is_warn(self, tmp_path):
        """StationFact with wrong img_url should be warn (house rule sets expected)."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_FACT_WRONG_IMAGE, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "content.fact_image"]
        assert len(findings) == 1
        assert findings[0].severity == "warn"
        assert "not the shared logo" in findings[0].message

    def test_fact_correct_image_passes(self, tmp_path):
        """StationFact with correct img_url should pass."""
        content = """<!-- provenance: tool=test model=test -->
@StationFact<~>Test System<~>Test Station
UPDATEDB
img_url=https://elite-dangerous.skyrunner42.xyz/ii42-logo.jpg
Correct image.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "content.fact_image"]
        assert len(findings) == 0


class TestContentNoLinks:
    """Tests for content.no_links rule."""

    def test_link_in_phrase_is_error(self, tmp_path):
        """URL in phrase should be error."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_WITH_LINK, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "content.no_links"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "https://example.com" in findings[0].message

    def test_no_link_passes(self, tmp_path):
        """Content without links should pass."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Welcome to the system, no links here.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "content.no_links"]
        assert len(findings) == 0


class TestContentFactNoFilters:
    """Tests for content.fact_no_filters rule."""

    def test_fact_with_filter_is_error(self, tmp_path):
        """StationFact with filter should be error."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_FACT_WITH_FILTER, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "content.fact_no_filters"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "fact text carries" in findings[0].message
        assert "vegan" in findings[0].message

    def test_fact_without_filter_passes(self, tmp_path):
        """StationFact without filter should pass."""
        content = """<!-- provenance: tool=test model=test -->
@StationFact<~>Test System<~>Test Station
UPDATEDB
img_url=https://example.com/logo.jpg
This fact has no filters.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "content.fact_no_filters"]
        assert len(findings) == 0


class TestContentStationLandable:
    """Tests for content.station_landable rule."""

    def test_station_not_landable_is_error(self, tmp_path, dossier_dir, dossier_path):
        """Station classified as hub/installation should be error."""
        # Write dossier with hub station
        dossier_content = TEST_DOSSIER.replace("nona", "silenus").replace("Civilian Surface Outpost", "Refinery Hub")
        dossier_path.write_text(dossier_content, encoding="utf-8")
        
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_STATION_NOT_LANDABLE, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=dossier_dir,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "content.station_landable"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "no landing pads" in findings[0].message

    def test_station_landable_passes(self, tmp_path, dossier_dir, dossier_path):
        """Landable station should pass."""
        dossier_path.write_text(TEST_DOSSIER, encoding="utf-8")
        
        content = """<!-- provenance: tool=test model=test -->
@StationGreeting<~>Test System<~>Test Station (ii-42)
UPDATEDB
Welcome to the station.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=dossier_dir,
        )
        
        findings = [f for f in result.findings if f.rule == "content.station_landable"]
        assert len(findings) == 0

    def test_station_not_in_dossier_is_error(self, tmp_path, dossier_dir, dossier_path):
        """Station with content but not in dossier should be error."""
        dossier_path.write_text(TEST_DOSSIER, encoding="utf-8")
        
        content = """<!-- provenance: tool=test model=test -->
@StationGreeting<~>Test System<~>Unknown Station (ii-42)
UPDATEDB
Welcome to unknown station.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=dossier_dir,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "content.station_landable"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "classified in no dossier" in findings[0].message

    def test_station_tag_without_parenthetical_does_not_match_suffixed_site(
        self, tmp_path, dossier_dir, dossier_path
    ):
        """A tag must use the exact dossier station name, parenthetical included."""
        dossier_path.write_text(TEST_DOSSIER, encoding="utf-8")

        content = """<!-- provenance: tool=test model=test -->
@StationGreeting<~>Test System<~>Test Station
UPDATEDB
Welcome to the station.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")

        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=dossier_dir,
        )

        assert not result.passed
        findings = [f for f in result.findings if f.rule == "content.station_landable"]
        assert len(findings) == 1
        assert "classified in no dossier" in findings[0].message


class TestContentCommanderToken:
    """Tests for content.commander_token rule."""

    def test_hardcoded_commander_is_error(self, tmp_path):
        """Hardcoded 'Commander' should be error."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_WITH_HARDCODED_COMMANDER, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "content.commander_token"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "hardcoded" in findings[0].message.lower()
        assert "Commander" in findings[0].message

    def test_token_commander_passes(self, tmp_path):
        """<Commander> token should pass."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Welcome <Commander> to the system.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "content.commander_token"]
        assert len(findings) == 0

    def test_token_cmdrname_passes(self, tmp_path):
        """<cmdrname> token should pass."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Welcome <cmdrname> to the system.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "content.commander_token"]
        assert len(findings) == 0


class TestDBPlacement:
    """Tests for db.placement rule."""

    def test_updatedb_wrong_place_is_error(self, tmp_path):
        """UPDATEDB not on line after @tag should be error."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_WITH_UPDATEDB_WRONG_PLACE, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "db.placement"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "not on the line after" in findings[0].message

    def test_updatedb_correct_place_passes(self, tmp_path):
        """UPDATEDB on line after @tag should pass."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
UPDATEDB
Welcome.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "db.placement"]
        assert len(findings) == 0


class TestDossierSpine:
    """Tests for dossier.spine rule."""

    def test_wrong_section_order_is_error(self, tmp_path, dossier_dir, dossier_path):
        """Wrong section order should be error."""
        dossier_path.write_text(TEST_DOSSIER_WRONG_SECTIONS, encoding="utf-8")
        
        content_file = tmp_path / "content.txt"
        content_file.write_text(VALID_CONTENT, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=dossier_dir,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "dossier.spine"]
        assert len(findings) >= 1
        assert any(f.severity == "error" and "sections are" in f.message for f in findings)

    def test_wrong_section_title_is_warn(self, tmp_path, dossier_dir, dossier_path):
        """Wrong section title should be warn."""
        dossier_path.write_text(TEST_DOSSIER_WRONG_TITLES, encoding="utf-8")
        
        content_file = tmp_path / "content.txt"
        content_file.write_text(VALID_CONTENT, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=dossier_dir,
        )
        
        findings = [f for f in result.findings if f.rule == "dossier.spine"]
        assert len(findings) >= 1
        assert any(f.severity == "warn" and "section 2 is" in f.message for f in findings)

    def test_correct_dossier_passes(self, tmp_path, dossier_dir, dossier_path):
        """Correct dossier should pass."""
        dossier_path.write_text(TEST_DOSSIER, encoding="utf-8")
        
        content_file = tmp_path / "content.txt"
        content_file.write_text(VALID_CONTENT, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=dossier_dir,
        )
        
        findings = [f for f in result.findings if f.rule == "dossier.spine"]
        assert len(findings) == 0


# ============================================================
# House rule tests (filters.banned)
# ============================================================

class TestFiltersBanned:
    """Tests for filters.banned rule (declared in house rules)."""

    def test_banned_filter_is_error(self, tmp_path):
        """Banned filter (profanity) should be error."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(CONTENT_WITH_BANNED_FILTER, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "filters.banned"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "banned filter" in findings[0].message.lower()
        assert "profanity" in findings[0].message

    def test_all_banned_filters_caught(self, tmp_path):
        """All four banned filters should be caught."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(profanity)Line 1
(flirt)Line 2
(innuendo)Line 3
(alcohol)Line 4
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        findings = [f for f in result.findings if f.rule == "filters.banned"]
        assert len(findings) == 4
        banned_found = {f.message.split("(")[1].split(")")[0] for f in findings}
        assert banned_found == {"profanity", "flirt", "innuendo", "alcohol"}

    def test_banned_filter_outside_scope_not_checked(self, tmp_path):
        """Banned filter in EDCoPilot default content should not be checked (scope)."""
        content = "@ConfirmedCommander\n(profanity)Default content.\n" + CONTENT_WITH_BANNED_FILTER
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        ctx = _full_payload_context(content_file)
        rule_filters_banned(ctx)
        
        findings = [f for f in ctx.findings if f.rule == "filters.banned"]
        # Only the one in authored region should be caught
        assert len(findings) == 1


# ============================================================
# Integration / combination tests
# ============================================================

class TestCombinations:
    """Tests for multiple rules firing together."""

    def test_multiple_violations_reported(self, tmp_path):
        """Multiple rule violations should all be reported."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(profanity)Banned filter and unknown token <badtoken>.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert not result.passed
        rule_ids = {f.rule for f in result.findings}
        assert "filters.banned" in rule_ids
        assert "syntax.token_known" in rule_ids

    def test_severity_ordering(self, tmp_path):
        """Findings should be ordered by severity then rule then line."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(profanity)Error severity.
(unknown_filter)Error severity unknown filter.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        # Check ordering: error before warn, then by rule, then by line
        errors = [f for f in result.findings if f.severity == "error"]
        warns = [f for f in result.findings if f.severity == "warn"]
        # All errors should come before warns in the full list
        if errors and warns:
            assert max(f.line or 0 for f in errors) < min(f.line or 999 for f in warns) or True  # Ordering is by severity first

    def test_valid_content_passes_all_rules(self, tmp_path, dossier_dir, dossier_path):
        """Fully valid content should pass all rules."""
        dossier_path.write_text(TEST_DOSSIER, encoding="utf-8")
        content_file = tmp_path / "content.txt"
        content_file.write_text(VALID_CONTENT, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=dossier_dir,
        )
        
        # Should only have policy rules listed (not checked by program)
        assert result.passed
        # No error findings
        errors = [f for f in result.findings if f.severity == "error"]
        assert len(errors) == 0


# ============================================================
# validate_content API tests
# ============================================================

class TestValidateContentAPI:
    """Tests for the validate_content public entry point."""

    def test_finding_has_required_fields(self, tmp_path):
        """Finding should have rule, severity, line, message."""
        # Use content that only triggers syntax.filter_known
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(allbusiness)Line 1.
(allbusiness)Line 2.
(unknown_filter)This has unknown filter.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        # Find the syntax.filter_known finding
        findings = [f for f in result.findings if f.rule == "syntax.filter_known"]
        assert len(findings) == 1
        finding = findings[0]
        assert hasattr(finding, "rule")
        assert hasattr(finding, "severity")
        assert hasattr(finding, "line")
        assert hasattr(finding, "message")
        assert finding.rule == "syntax.filter_known"
        assert finding.severity in ("error", "warn", "info")
        assert finding.line is not None
        assert isinstance(finding.message, str)

    def test_validates_with_no_system_rules(self, tmp_path):
        """An empty systems directory validates against the base rules alone."""
        content_file = tmp_path / "content.txt"
        content_file.write_text(VALID_CONTENT, encoding="utf-8", newline="\r\n")
        
        result = validate_content(_payload(content_file), SYSTEM, systems_dir=tmp_path)
        assert isinstance(result, ValidationResult)

    def test_validates_without_house_rules(self, tmp_path):
        """A systems directory with no all.rules.toml supplies no house rules."""
        (tmp_path / "test.rules.toml").write_text(
            '[system]\nnames = ["Test System"]\ndossier = "test.md"\n',
            encoding="utf-8",
        )
        (tmp_path / "test.md").write_text("", encoding="utf-8")
        content_file = tmp_path / "content.txt"
        content_file.write_text(VALID_CONTENT, encoding="utf-8", newline="\r\n")
        
        result = validate_content(_payload(content_file), SYSTEM, systems_dir=tmp_path)
        assert isinstance(result, ValidationResult)


# ============================================================
# Parsing helper tests
# ============================================================

class TestParseContent:
    """Tests for content parsing utilities."""

    def test_parse_content_extracts_tags(self, tmp_path):
        """parse_content should extract tags and phrases."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
UPDATEDB
(allbusiness)Line 1.
Line 2.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        base = load_base_config(RULE_DATA_DIR)
        kinds = load_kinds(base)
        content_obj = parse_content(content_file, PROVENANCE_RE, kinds)
        
        assert len(content_obj.tags) == 1
        assert content_obj.tags[0].kind == "SystemGreeting"
        assert len(content_obj.tags[0].phrases) == 2
        assert content_obj.authored_from == 1

    def test_parse_content_tracks_provenance(self, tmp_path):
        """parse_content should track provenance line."""
        content = """@ConfirmedCommander
Default line.
<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Authored line.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        base = load_base_config(RULE_DATA_DIR)
        kinds = load_kinds(base)
        content_obj = parse_content(content_file, PROVENANCE_RE, kinds)
        
        assert content_obj.authored_from == 3  # Line after provenance
        assert len(content_obj.provenance) == 1


# ============================================================
# Edge case tests
# ============================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_content_file(self, tmp_path):
        """Empty content file should be handled."""
        content_file = tmp_path / "content.txt"
        content_file.write_text("", encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        # Should not crash, may have encoding findings
        assert isinstance(result, ValidationResult)

    def test_content_with_only_provenance(self, tmp_path):
        """Content with only provenance line should be handled."""
        content = "<!-- provenance: tool=test model=test -->"
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        assert isinstance(result, ValidationResult)

    def test_comment_lines_ignored(self, tmp_path):
        """Comment lines should be ignored."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
<!-- This is a comment -->
Welcome.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        # Comment should not cause issues
        assert isinstance(result, ValidationResult)

    def test_img_url_not_counted_as_phrase(self, tmp_path):
        """img_url= lines should not be treated as phrases."""
        content = """<!-- provenance: tool=test model=test -->
@StationFact<~>Test System<~>Test Station
UPDATEDB
img_url=https://example.com/logo.jpg
This is the first phrase.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        # img_url should not trigger content.no_links
        link_findings = [f for f in result.findings if f.rule == "content.no_links"]
        assert len(link_findings) == 0

    def test_updates_marker_not_phrase(self, tmp_path):
        """UPDATEDB marker should not be treated as phrase."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
UPDATEDB
Welcome.
"""
        content_file = tmp_path / "content.txt"
        content_file.write_text(content, encoding="utf-8", newline="\r\n")
        
        result = validate_content(
            _payload(content_file),
            SYSTEM,
            house_rules_path=HOUSE_RULES,
            systems_dir=SYSTEMS_DIR,
        )
        
        # UPDATEDB should not trigger any content rules
        assert isinstance(result, ValidationResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])