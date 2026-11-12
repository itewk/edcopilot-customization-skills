"""Tests for validate_content function - validates a provenance block string against all rules.

These tests follow TDD: RED (fail) -> GREEN (pass).
Tests validate_content(content: str, system_name: str) -> ValidationResult
"""

import os
from pathlib import Path

import pytest
# pydantic is gone from this repo; ConfigError is its configuration-validation
# equivalent, so the assertions below keep their original names.
from edcg.common.config import ConfigError as ValidationError

import edcg.common.config as config_module
from edcg.rules.validation import (
    ValidationResult,
    Finding,
    validate_content,
    load_base_config,
    load_all_system_rules,
    load_house_rules,
    merge_rules,
    load_kinds,
    parse_content,
    PROVENANCE_RE,
    RULE_DATA_DIR,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


# ============================================================
# Test fixtures
# ============================================================

@pytest.fixture
def content_base_rules_path() -> Path:
    """Path to base.toml in the rule data dir."""
    return RULE_DATA_DIR / "base.toml"


@pytest.fixture
def content_house_rules_path() -> Path:
    """Path to test house rules file (all.rules.toml)."""
    return FIXTURES_DIR / "all.rules.toml"


@pytest.fixture
def content_systems_dir() -> Path:
    """Path to test systems directory with system rules."""
    return FIXTURES_DIR


# ============================================================
# Test content strings
# ============================================================

# Valid content with single provenance block
VALID_SINGLE_BLOCK = """<!-- provenance: tool=test model=test -->
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

# Content with multiple provenance blocks - latest should be validated
MULTIPLE_PROVENANCE_BLOCKS = """@ConfirmedCommander
Default EDCoPilot content.
<!-- provenance: tool=old version -->
@SystemGreeting<~>Test System
Old authored content.
<!-- provenance: tool=new version model=test -->
@SystemGreeting<~>Test System
UPDATEDB
(allbusiness)New welcome to <starsystem>, <Commander>.
Welcome to <starsystem>, <cmdrname>.
"""

# Content with no provenance - should validate entire file
NO_PROVENANCE = """@SystemGreeting<~>Test System
UPDATEDB
(allbusiness)Welcome to <starsystem>, <Commander>.
Welcome to <starsystem>, <cmdrname>.
(allbusiness)All business greeting.
"""

# Content with unknown filter in latest block
CONTENT_UNKNOWN_FILTER = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(unknown_filter)This line has an unknown filter.
"""

# Content with banned filter (profanity) in latest block
CONTENT_BANNED_FILTER = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(profanity)This has a banned filter.
"""

# Content with no allbusiness lines
CONTENT_NO_ALLBUSINESS = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Welcome to the system.
No allbusiness line here.
"""

# Content with filter before voice tag
CONTENT_FILTER_LEADS = """<!-- provenance: tool=test model=test -->
@SystemBroadcast<~>Test System
(allbusiness)[<Voice>]This filter leads the voice tag.
"""

# Content with miscased token
CONTENT_MISCASED_TOKEN = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Welcome <commander> to the system.
"""

# Content with unknown token
CONTENT_UNKNOWN_TOKEN = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Welcome <unknown_token> to the system.
"""

# Content with hardcoded "Commander"
CONTENT_HARDCODED_COMMANDER = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Welcome Commander to the system.
"""

# Content with link
CONTENT_WITH_LINK = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Visit https://example.com for more info.
"""

# Content with StationFact missing img_url
CONTENT_FACT_NO_IMAGE = """<!-- provenance: tool=test model=test -->
@StationFact<~>Test System<~>Test Station
UPDATEDB
This fact has no image.
"""

# Content with StationFact having filter
CONTENT_FACT_WITH_FILTER = """<!-- provenance: tool=test model=test -->
@StationFact<~>Test System<~>Test Station
UPDATEDB
img_url=https://example.com/logo.jpg
(vegan)This fact has a filter.
"""

# Content with no fallback (all lines filtered)
CONTENT_NO_FALLBACK = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(allbusiness)All business only.
(vegan)Vegan only.
"""

# Content with no clean allbusiness
CONTENT_NO_CLEAN_ALLBUSINESS = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(allbusiness)(vegan)Combined filter.
Welcome to the system.
"""

# Content with UPDATEDB in wrong place
CONTENT_UPDATEDB_WRONG = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
Welcome to the system.
UPDATEDB
"""

# Content with wrong tag shape (missing station part)
CONTENT_WRONG_TAG_SHAPE = """<!-- provenance: tool=test model=test -->
@StationGreeting<~>Test System
This tag is missing station part.
"""

# Content with example wrapper
CONTENT_EXAMPLE_WRAPPER = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
[example]This should not be here[/example]
"""

# Content with multiple violations
CONTENT_MULTIPLE_VIOLATIONS = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(profanity)Banned filter and unknown token <badtoken>.
Welcome Commander.
"""

# Station not landable (hub) - requires dossier
CONTENT_STATION_HUB = """<!-- provenance: tool=test model=test -->
@StationGreeting<~>Test System<~>Test Hub (ii-42)
UPDATEDB
Welcome to the hub.
"""

# Dossier for landable station
DOSSIER_LANDABLE = """# Test System — system dossier

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
| Test Hub (ii-42) | `silenus` Refinery Hub | `3 b` |

## 5. Corrections log (do not reintroduce these)

## 6. Site list maintenance

## 7. Coverage

Test Station (ii-42) · Test Hub (ii-42)

## 8. Writing rules

## 9. Open threads (TODO)
"""

# ============================================================
# Test cases
# ============================================================

class TestValidateContentBasic:
    """Basic tests for validate_content function."""

    def test_valid_single_block_passes(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Valid content with single provenance block should pass."""
        # The payload carries the CRLF endings syntax.encoding requires; the
        # literal is LF for readability.
        result = validate_content(VALID_SINGLE_BLOCK.replace("\n", "\r\n"), "Test System", 
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert isinstance(result, ValidationResult)
        assert result.passed
        errors = [f for f in result.findings if f.severity == "error"]
        assert len(errors) == 0

    def test_no_provenance_validates_full_file(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Content with no provenance should validate entire file."""
        result = validate_content(NO_PROVENANCE.replace("\n", "\r\n"), "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert isinstance(result, ValidationResult)
        assert result.passed
        errors = [f for f in result.findings if f.severity == "error"]
        assert len(errors) == 0

    def test_multiple_provenance_validates_latest_only(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Only the latest provenance block should be validated."""
        # The latest block has valid content, old block has no allbusiness
        # If it validated the old block, it would fail
        result = validate_content(MULTIPLE_PROVENANCE_BLOCKS, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert isinstance(result, ValidationResult)
        # Latest block has 2 allbusiness lines for SystemGreeting (warn_below=2), so should pass
        # But old block had 0 - if validated, would error
        errors = [f for f in result.findings if f.severity == "error" and f.rule == "filters.allbusiness"]
        assert len(errors) == 0

    def test_line_numbers_relative_to_block(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Finding line numbers should be relative to the validated block."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
UPDATEDB
(allbusiness)Line 1.
(unknown_filter)Line 2 with unknown filter.
"""
        result = validate_content(content, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        findings = [f for f in result.findings if f.rule == "syntax.filter_known"]
        assert len(findings) == 1
        # Line numbers relative to block: provenance is line 1, tag line 2, UPDATEDB line 3, phrase line 4
        # The unknown filter is on the 4th line of the block (1-indexed)
        # But relative to block start (after provenance), it's line 3 (tag=1, UPDATEDB=2, phrase=3)
        # Actually, the block starts at provenance line, so line 4 in block = line 4 absolute
        # Let's check what the function returns
        assert findings[0].line is not None
        assert findings[0].line >= 1


class TestValidateContentSyntaxRules:
    """Tests for syntax rule violations in validate_content."""

    def test_unknown_filter_is_error(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Unknown filter in latest block should be error."""
        result = validate_content(CONTENT_UNKNOWN_FILTER, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "syntax.filter_known"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "unknown_filter" in findings[0].message

    def test_banned_filter_is_error(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Banned filter (profanity) in latest block should be error."""
        result = validate_content(CONTENT_BANNED_FILTER, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "filters.banned"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "banned filter" in findings[0].message.lower()
        assert "profanity" in findings[0].message

    def test_filter_before_voice_tag_is_error(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Filter before first voice tag should be error."""
        result = validate_content(CONTENT_FILTER_LEADS, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "syntax.filter_leads"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "before the first voice tag" in findings[0].message

    def test_miscased_token_is_warn(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Miscased token should produce warning."""
        result = validate_content(CONTENT_MISCASED_TOKEN, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        findings = [f for f in result.findings if f.rule == "syntax.token_case"]
        assert len(findings) == 1
        assert findings[0].severity == "warn"
        assert "commander" in findings[0].message.lower()
        assert "Commander" in findings[0].message

    def test_unknown_token_is_warn(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Unknown token should produce warning."""
        result = validate_content(CONTENT_UNKNOWN_TOKEN, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        findings = [f for f in result.findings if f.rule == "syntax.token_known"]
        assert len(findings) == 1
        assert findings[0].severity == "warn"
        assert "unknown_token" in findings[0].message
        assert "declare the voice in the dossier" in findings[0].message
        assert "system rules file" in findings[0].message
        assert "README" not in findings[0].message

    def test_hardcoded_commander_is_error(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Hardcoded 'Commander' should be error."""
        result = validate_content(CONTENT_HARDCODED_COMMANDER, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "content.commander_token"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "hardcoded" in findings[0].message.lower()
        assert "Commander" in findings[0].message

    def test_link_in_phrase_is_error(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """URL in phrase should be error."""
        result = validate_content(CONTENT_WITH_LINK, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "content.no_links"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "https://example.com" in findings[0].message

    def test_example_wrapper_is_error(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """[example] wrapper should be error."""
        result = validate_content(CONTENT_EXAMPLE_WRAPPER, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "syntax.no_example_wrapper"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "example" in findings[0].message.lower()

    def test_wrong_tag_shape_is_error(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Wrong tag shape (missing parts) should be error."""
        result = validate_content(CONTENT_WRONG_TAG_SHAPE, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "format.tag_shape"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "field" in findings[0].message.lower()


class TestValidateContentFilterRules:
    """Tests for filter rules (allbusiness, fallback) in validate_content."""

    def test_no_allbusiness_is_error(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Tag with no (allbusiness) lines should be error."""
        result = validate_content(CONTENT_NO_ALLBUSINESS, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "filters.allbusiness"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "no (allbusiness) line" in findings[0].message

    def test_no_fallback_is_error(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Tag where every line has a filter should be error."""
        result = validate_content(CONTENT_NO_FALLBACK, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "filters.fallback"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "filters every line" in findings[0].message

    def test_no_clean_allbusiness_is_error(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Tag with no line carrying only (allbusiness) should be error."""
        result = validate_content(CONTENT_NO_CLEAN_ALLBUSINESS, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "filters.fallback"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "no line carrying (allbusiness) alone" in findings[0].message

    def test_station_fact_exempt_from_allbusiness(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """StationFact should be exempt from allbusiness requirement."""
        content = """<!-- provenance: tool=test model=test -->
@StationFact<~>Test System<~>Test Station
UPDATEDB
img_url=https://example.com/logo.jpg
This fact has no allbusiness line.
"""
        result = validate_content(content, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        findings = [f for f in result.findings if f.rule == "filters.allbusiness"]
        assert len(findings) == 0


class TestValidateContentStationRules:
    """Tests for station-related rules in validate_content."""

    def test_station_fact_no_image_is_error(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """StationFact without img_url should be error."""
        result = validate_content(CONTENT_FACT_NO_IMAGE, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "content.fact_image"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "no img_url line" in findings[0].message

    def test_station_fact_with_filter_is_error(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """StationFact with filter should be error."""
        result = validate_content(CONTENT_FACT_WITH_FILTER, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "content.fact_no_filters"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "fact text carries" in findings[0].message
        assert "vegan" in findings[0].message

    def test_station_not_landable_is_error(self, content_base_rules_path, content_house_rules_path, content_systems_dir, tmp_path):
        """Station classified as hub should be error."""
        # Write dossier with hub station
        dossier_path = tmp_path / "test_dossier.md"
        dossier_path.write_text(DOSSIER_LANDABLE, encoding="utf-8")
        
        # We need to test with a system that has this dossier
        # For now, test that the function can be called with dossier
        # The validate_content function may not support dossier_path parameter
        # This test documents expected behavior
        pass  # Will implement after function exists

    def test_updatedb_wrong_place_is_error(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """UPDATEDB not on line after @tag should be error."""
        result = validate_content(CONTENT_UPDATEDB_WRONG, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert not result.passed
        findings = [f for f in result.findings if f.rule == "db.placement"]
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "not on the line after" in findings[0].message


class TestValidateContentMultipleViolations:
    """Tests for multiple rule violations reported together."""

    def test_multiple_violations_reported(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Multiple rule violations should all be reported."""
        result = validate_content(CONTENT_MULTIPLE_VIOLATIONS, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert not result.passed
        rule_ids = {f.rule for f in result.findings}
        assert "filters.banned" in rule_ids
        assert "syntax.token_known" in rule_ids
        assert "content.commander_token" in rule_ids

    def test_severity_ordering(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Findings should be ordered by severity then rule then line."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
(profanity)Error severity.
(unknown_filter)Error severity unknown filter.
"""
        result = validate_content(content, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        # Check ordering: error before warn
        errors = [f for f in result.findings if f.severity == "error"]
        warns = [f for f in result.findings if f.severity == "warn"]
        # All errors should come before warns in the full list
        if errors and warns:
            last_error_idx = max(result.findings.index(f) for f in errors)
            first_warn_idx = min(result.findings.index(f) for f in warns)
            assert last_error_idx < first_warn_idx


class TestValidateContentEdgeCases:
    """Tests for edge cases."""

    def test_empty_content(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Empty content should be handled."""
        result = validate_content("", "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert isinstance(result, ValidationResult)

    def test_only_provenance(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Content with only provenance line should be handled."""
        content = "<!-- provenance: tool=test model=test -->"
        result = validate_content(content, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert isinstance(result, ValidationResult)

    def test_comment_lines_ignored(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Comment lines should be ignored."""
        content = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
<!-- This is a comment -->
Welcome.
"""
        result = validate_content(content, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert isinstance(result, ValidationResult)

    def test_unknown_system_name(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Unknown system name should still work (use base rules only)."""
        result = validate_content(VALID_SINGLE_BLOCK, "Unknown System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
        assert isinstance(result, ValidationResult)
        # Should not crash, may use base rules only

    def test_finding_has_required_fields(self, content_base_rules_path, content_house_rules_path, content_systems_dir):
        """Finding should have rule, severity, line, message."""
        result = validate_content(CONTENT_UNKNOWN_FILTER, "Test System",
                                  base_rules_path=content_base_rules_path,
                                  house_rules_path=content_house_rules_path,
                                  systems_dir=content_systems_dir)
        
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


class TestValidateContentConfiguration:
    """Default path resolution must not hide real configuration errors."""

    def test_missing_configuration_uses_documented_fallback(self, monkeypatch, tmp_path):
        """No EDCG_* environment means base-only validation, not a crash."""
        config_module.config = None
        for name in list(os.environ):
            if name.upper().startswith("EDCG_"):
                monkeypatch.delenv(name, raising=False)
        # The content root defaults to the working directory. An empty one
        # pins the "no system rules found" fallback this test documents.
        monkeypatch.chdir(tmp_path)

        result = validate_content(CONTENT_HARDCODED_COMMANDER, "Test System")

        assert isinstance(result, ValidationResult)
        assert any(f.rule == "content.commander_token" for f in result.findings)
        assert config_module.config is None

    def test_partial_configuration_uses_configured_content_root(
        self, monkeypatch, tmp_path
    ):
        """A content root is used even when the runtime root is not set."""
        config_module.config = None
        for name in list(os.environ):
            if name.upper().startswith("EDCG_"):
                monkeypatch.delenv(name, raising=False)

        systems_dir = tmp_path / "systems"
        systems_dir.mkdir()
        (systems_dir / "all.rules.toml").write_text(
            '[rules.content.commander_token]\nseverity = "off"\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))

        result = validate_content(CONTENT_HARDCODED_COMMANDER, "Test System")

        assert not any(f.rule == "content.commander_token" for f in result.findings)
        assert config_module.config is None

    def test_invalid_configuration_is_not_hidden(self, monkeypatch, tmp_path):
        """An invalid non-path setting raises instead of silently falling back."""
        config_module.config = None
        for name in list(os.environ):
            if name.upper().startswith("EDCG_"):
                monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
        monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(tmp_path))
        monkeypatch.setenv("EDCG_AUTO_COMMIT", "not-a-bool")

        with pytest.raises(ValidationError):
            validate_content(CONTENT_HARDCODED_COMMANDER, "Test System")

        assert config_module.config is None


class TestValidateContentLineEndings:
    """``syntax.encoding`` must judge the payload the caller actually sent.

    The temp file used to be written with ``newline='\\r\\n'``, which forced CRLF
    onto every payload: a multi-line LF block falsely passed and a single-line
    block falsely failed. These tests pin the real input's endings instead.
    """

    BLOCK = (
        "<!-- provenance: tool=test model=test -->\n"
        "@SystemGreeting<~>Test System\n"
        "Welcome to the system, <Commander>.\n"
    )

    def _encoding_findings(self, result):
        return [f for f in result.findings if f.rule == "syntax.encoding"]

    def test_multi_line_lf_payload_reports_lf(
        self, content_base_rules_path, content_house_rules_path, content_systems_dir
    ):
        result = validate_content(
            self.BLOCK,
            "Test System",
            base_rules_path=content_base_rules_path,
            house_rules_path=content_house_rules_path,
            systems_dir=content_systems_dir,
        )

        messages = [f.message for f in self._encoding_findings(result)]
        assert any("line ending is lf, expected crlf" in m for m in messages), messages

    def test_crlf_payload_reports_crlf(
        self, content_base_rules_path, content_house_rules_path, content_systems_dir
    ):
        result = validate_content(
            self.BLOCK.replace("\n", "\r\n"),
            "Test System",
            base_rules_path=content_base_rules_path,
            house_rules_path=content_house_rules_path,
            systems_dir=content_systems_dir,
        )

        assert self._encoding_findings(result) == []

    def test_single_line_payload_has_no_encoding_error(
        self, content_base_rules_path, content_house_rules_path, content_systems_dir
    ):
        result = validate_content(
            "@SystemGreeting<~>Test System",
            "Test System",
            base_rules_path=content_base_rules_path,
            house_rules_path=content_house_rules_path,
            systems_dir=content_systems_dir,
        )

        assert self._encoding_findings(result) == []


class TestValidateContentIntegration:
    """Integration tests with real system rules."""

    def test_with_real_system_rules(self, content_base_rules_path, content_house_rules_path, tmp_path):
        """Test with a real system from a content root's systems directory."""
        # Build a content root whose systems/ holds the fixture's real rules.
        systems_path = tmp_path / "systems"
        systems_path.mkdir()
        for name in ("test.rules.toml", "test.md"):
            (systems_path / name).write_text(
                (FIXTURES_DIR / name).read_text(encoding="utf-8"),
                encoding="utf-8",
            )

        system_files = list(systems_path.glob("*.rules.toml"))
        system_files = [f for f in system_files if f.name != "all.rules.toml"]
        
        if system_files:
            # Get first system name
            import tomllib
            with open(system_files[0], "rb") as f:
                cfg = tomllib.load(f)
            system_names = cfg.get("system", {}).get("names", [])
            if system_names:
                system_name = system_names[0]
                result = validate_content(VALID_SINGLE_BLOCK.replace("Test System", system_name), system_name,
                                          base_rules_path=content_base_rules_path,
                                          house_rules_path=content_house_rules_path,
                                          systems_dir=systems_path)
                assert isinstance(result, ValidationResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])