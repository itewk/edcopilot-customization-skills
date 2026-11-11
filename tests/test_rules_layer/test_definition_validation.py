"""Tests for definition validation - dossier + rules cross-references.

These tests follow TDD: RED (fail) -> GREEN (pass).
Tests validate_definition(dossier: str, rules: str, system_name: str) -> ValidationResult
"""

import pytest
from edcg.rules.validation import (
    ValidationResult,
    Finding,
    _normalize_station_name,
    validate_definition,
)


# ============================================================
# Test fixtures - valid dossier and rules
# ============================================================

VALID_DOSSIER = """# Test System — system dossier

## 1. Identity and canon

| Fact | Value |
|---|---|
| System name | `Test System` |

## 2. Lore and theme

Test lore.

## 3. Tone rules (hard constraints)

Test tone.

## 4. Canon site table

### Complete (3)

| Site | Build type | Body |
|---|---|---|
| Primary Improbable Discoveries (ii-42) | `prometheus` Scientific Outpost | `4 d` |
| Infinite Redshirts (ii-42) | `nemesis` Military Outpost | star |
| Cold Probabilities (ii-42) | `nona` Civilian Surface Outpost | `3 a` |
| Refined Industrial Probabilities (ii-42) | `quad_truss` Coriolis Starport | `3 a` |
| Plundered Probabilities (ii-42) | `dysnomia` Pirate Outpost | `5 d` |
| Probably Redshirts (ii-42) | `nemesis` Military Outpost | `4 a` |

## 5. Corrections log (do not reintroduce these)

## 6. Site list maintenance

## 7. Coverage

Primary Improbable Discoveries (ii-42) · Infinite Redshirts (ii-42) · Cold Probabilities (ii-42) ·
Refined Industrial Probabilities (ii-42) · Plundered Probabilities (ii-42) · Probably Redshirts (ii-42)

## 8. Writing rules

### Voices used

- **Crew:** `[<Foreman>]`, `[<Welder>]`, `[<Researcher>]`, `[<LabTech>]`
- **Garrison:** `[<GuardSarge>]`, `[<GuardTrooper>]`

## 9. Open threads (TODO)

- Test thread
"""

VALID_RULES = """[system]
names = ["Test System"]
dossier = "test.md"
voices = ["Foreman", "Welder", "Researcher", "LabTech", "GuardSarge", "GuardTrooper"]
"""

VALID_ALL_RULES = """[rules.filters.banned]
impl = "rule_filters_banned"
severity = "error"
tokens = ["profanity", "flirt", "innuendo", "alcohol"]
why = "Test house rule"

[rules.content.fact_image]
expected = "https://elite-dangerous.skyrunner42.xyz/ii42-logo.jpg"

[rules.filters.allbusiness]
warn_below = 2
warn_below_by_kind = { StationGreeting = 1 }
"""


def test_station_name_normalization_preserves_parenthetical():
    """A parenthetical part is part of the station name, not removable decoration."""
    assert _normalize_station_name("Station (Old)") == "Station (Old)"
    assert _normalize_station_name("Station (Old)") != _normalize_station_name("Station (New)")


# ============================================================
# Test cases
# ============================================================

class TestValidateDefinition:
    """Tests for validate_definition function."""

    def test_valid_dossier_and_rules_passes(self):
        """Valid dossier and rules should pass all checks."""
        result = validate_definition(VALID_DOSSIER, VALID_RULES, "Test System")
        
        assert isinstance(result, ValidationResult)
        assert result.passed
        errors = [f for f in result.findings if f.severity == "error"]
        assert len(errors) == 0

    def test_missing_section_1_is_error(self):
        """Missing section 1 should be error."""
        dossier = VALID_DOSSIER.replace("## 1. Identity and canon", "")
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "dossier.spine" and f.severity == "error"]
        assert len(errors) >= 1
        assert any("sections are" in f.message for f in errors)

    def test_missing_section_4_is_error(self):
        """Missing section 4 should be error."""
        dossier = VALID_DOSSIER.replace("## 4. Canon site table", "")
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "dossier.spine" and f.severity == "error"]
        assert len(errors) >= 1

    def test_wrong_section_order_is_error(self):
        """Wrong section order should be error."""
        dossier = VALID_DOSSIER.replace(
            "## 3. Tone rules (hard constraints)\n\nTest tone.\n\n## 4. Canon site table",
            "## 4. Canon site table\n\n### Complete (3)\n\n| Site | Build type | Body |\n|---|---|---|\n| Primary Improbable Discoveries (ii-42) | `prometheus` Scientific Outpost | `4 d` |\n\n## 3. Tone rules (hard constraints)\n\nTest tone."
        )
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "dossier.spine" and f.severity == "error"]
        assert len(errors) >= 1
        assert any("wrong order" in f.message.lower() for f in errors)

    def test_wrong_section_title_is_warn(self):
        """Wrong section title should be warning."""
        dossier = VALID_DOSSIER.replace("## 2. Lore and theme", "## 2. Wrong Title")
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        warnings = [f for f in result.findings if f.rule == "dossier.spine" and f.severity == "warn"]
        assert len(warnings) >= 1
        assert any("section 2 is" in f.message for f in warnings)

    def test_section_4_no_table_is_error(self):
        """Section 4 without a parseable table should be error."""
        dossier = VALID_DOSSIER.replace(
            "### Complete (3)\n\n| Site | Build type | Body |\n|---|---|---|\n| Primary Improbable Discoveries (ii-42) | `prometheus` Scientific Outpost | `4 d` |\n| Infinite Redshirts (ii-42) | `nemesis` Military Outpost | star |\n| Cold Probabilities (ii-42) | `nona` Civilian Surface Outpost | `3 a` |\n| Refined Industrial Probabilities (ii-42) | `quad_truss` Coriolis Starport | `3 a` |\n| Plundered Probabilities (ii-42) | `dysnomia` Pirate Outpost | `5 d` |\n| Probably Redshirts (ii-42) | `nemesis` Military Outpost | `4 a` |",
            "No table here."
        )
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "dossier.site_table" and f.severity == "error"]
        assert len(errors) >= 1
        assert any("site table" in f.message.lower() for f in errors)

    def test_section_4_malformed_table_is_error(self):
        """Section 4 with malformed table should be error."""
        dossier = VALID_DOSSIER.replace(
            "### Complete (3)\n\n| Site | Build type | Body |\n|---|---|---|\n| Primary Improbable Discoveries (ii-42) | `prometheus` Scientific Outpost | `4 d` |\n| Infinite Redshirts (ii-42) | `nemesis` Military Outpost | star |\n| Cold Probabilities (ii-42) | `nona` Civilian Surface Outpost | `3 a` |\n| Refined Industrial Probabilities (ii-42) | `quad_truss` Coriolis Starport | `3 a` |\n| Plundered Probabilities (ii-42) | `dysnomia` Pirate Outpost | `5 d` |\n| Probably Redshirts (ii-42) | `nemesis` Military Outpost | `4 a` |",
            "### Complete (3)\n\n| Site | Build type |\n|---|---|\n| Test Station | `nona` |"
        )
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "dossier.site_table" and f.severity == "error"]
        assert len(errors) >= 1

    def test_rules_toml_missing_system_names_is_error(self):
        """Rules TOML missing system.names should be error."""
        rules = """[system]
dossier = "test.md"
voices = ["Foreman"]
"""
        result = validate_definition(VALID_DOSSIER, rules, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "rules.system_names" and f.severity == "error"]
        assert len(errors) >= 1

    def test_rules_toml_missing_system_dossier_is_error(self):
        """Rules TOML missing system.dossier should be error."""
        rules = """[system]
names = ["Test System"]
voices = ["Foreman"]
"""
        result = validate_definition(VALID_DOSSIER, rules, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "rules.system_dossier" and f.severity == "error"]
        assert len(errors) >= 1

    def test_rules_toml_missing_voices_is_error(self):
        """Rules TOML missing voices should be error."""
        rules = """[system]
names = ["Test System"]
dossier = "test.md"
"""
        result = validate_definition(VALID_DOSSIER, rules, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "rules.voices" and f.severity == "error"]
        assert len(errors) >= 1

    def test_rules_toml_invalid_syntax_is_error(self):
        """Rules TOML with invalid syntax should be error."""
        rules = """[system
names = ["Test System"]
"""
        result = validate_definition(VALID_DOSSIER, rules, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "rules.toml_syntax" and f.severity == "error"]
        assert len(errors) >= 1

    def test_voice_in_rules_not_in_dossier_section_8_is_error(self):
        """Voice declared in rules but not used in dossier §8 should be error."""
        rules = """[system]
names = ["Test System"]
dossier = "test.md"
voices = ["Foreman", "Welder", "Researcher", "LabTech", "GuardSarge", "GuardTrooper", "UnknownVoice"]
"""
        result = validate_definition(VALID_DOSSIER, rules, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "dossier.voice_coverage" and f.severity == "error"]
        assert len(errors) >= 1
        assert any("UnknownVoice" in f.message for f in errors)

    def test_voice_in_dossier_section_8_not_in_rules_is_error(self):
        """Voice used in dossier §8 but not declared in rules should be error."""
        dossier = VALID_DOSSIER.replace(
            "- **Crew:** `[<Foreman>]`, `[<Welder>]`, `[<Researcher>]`, `[<LabTech>]`",
            "- **Crew:** `[<Foreman>]`, `[<Welder>]`, `[<Researcher>]`, `[<LabTech>]`, `[<NewVoice>]`"
        )
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "dossier.voice_coverage" and f.severity == "error"]
        assert len(errors) >= 1
        assert any("NewVoice" in f.message for f in errors)

    def test_station_in_coverage_not_landable_in_section_4_is_error(self):
        """Station listed in §7 coverage but not landable in §4 should be error."""
        dossier = VALID_DOSSIER.replace(
            "Primary Improbable Discoveries (ii-42) · Infinite Redshirts (ii-42) · Cold Probabilities (ii-42)",
            "Primary Improbable Discoveries (ii-42) · Infinite Redshirts (ii-42) · Cold Probabilities (ii-42) · NonLandable Station"
        )
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "dossier.coverage_match" and f.severity == "error"]
        assert len(errors) >= 1
        assert any("NonLandable Station" in f.message for f in errors)

    def test_landable_station_in_section_4_missing_from_coverage_is_error(self):
        """Landable station in §4 but missing from §7 coverage should be error."""
        dossier = VALID_DOSSIER.replace(
            "Primary Improbable Discoveries (ii-42) · Infinite Redshirts (ii-42) · Cold Probabilities (ii-42) ·\nRefined Industrial Probabilities (ii-42) · Plundered Probabilities (ii-42) · Probably Redshirts (ii-42)",
            "Primary Improbable Discoveries (ii-42) · Infinite Redshirts (ii-42) · Cold Probabilities (ii-42)"
        )
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "dossier.coverage_match" and f.severity == "error"]
        assert len(errors) >= 1

    def test_img_url_in_dossier_section_7_not_matching_all_rules_is_warn(self):
        """img_url mentioned in §7 not matching all.rules.toml fact_image should be warning."""
        # This test checks that if the dossier §7 mentions an img_url that doesn't match
        # the all.rules.toml expected value, it's a warning
        # The validation function needs all_rules content to check this
        pass  # This requires all_rules parameter - we'll add it later

    def test_section_4_hub_station_in_coverage_is_error(self):
        """Hub station in §4 listed in §7 coverage should be error (not landable)."""
        dossier = VALID_DOSSIER.replace(
            "| Primary Improbable Discoveries (ii-42) | `prometheus` Scientific Outpost | `4 d` |\n| Infinite Redshirts (ii-42) | `nemesis` Military Outpost | star |\n| Cold Probabilities (ii-42) | `nona` Civilian Surface Outpost | `3 a` |\n| Refined Industrial Probabilities (ii-42) | `quad_truss` Coriolis Starport | `3 a` |\n| Plundered Probabilities (ii-42) | `dysnomia` Pirate Outpost | `5 d` |\n| Probably Redshirts (ii-42) | `nemesis` Military Outpost | `4 a` |",
            "| Primary Improbable Discoveries (ii-42) | `prometheus` Scientific Outpost | `4 d` |\n| Infinite Redshirts (ii-42) | `nemesis` Military Outpost | star |\n| Cold Probabilities (ii-42) | `nona` Civilian Surface Outpost | `3 a` |\n| Refined Industrial Probabilities (ii-42) | `quad_truss` Coriolis Starport | `3 a` |\n| Plundered Probabilities (ii-42) | `dysnomia` Pirate Outpost | `5 d` |\n| Probably Redshirts (ii-42) | `nemesis` Military Outpost | `4 a` |\n| Test Hub Station (ii-42) | `silenus` Refinery Hub | `3 b` |"
        ).replace(
            "Primary Improbable Discoveries (ii-42) · Infinite Redshirts (ii-42) · Cold Probabilities (ii-42) ·\nRefined Industrial Probabilities (ii-42) · Plundered Probabilities (ii-42) · Probably Redshirts (ii-42)",
            "Primary Improbable Discoveries (ii-42) · Infinite Redshirts (ii-42) · Cold Probabilities (ii-42) ·\nRefined Industrial Probabilities (ii-42) · Plundered Probabilities (ii-42) · Probably Redshirts (ii-42) · Test Hub Station (ii-42)"
        )
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "dossier.coverage_match" and f.severity == "error"]
        assert len(errors) >= 1
        assert any("Test Hub Station" in f.message or "Refinery Hub" in f.message for f in errors)

    def test_section_4_installation_station_in_coverage_is_error(self):
        """Installation station in §4 listed in §7 coverage should be error (not landable)."""
        dossier = VALID_DOSSIER.replace(
            "| Primary Improbable Discoveries (ii-42) | `prometheus` Scientific Outpost | `4 d` |\n| Infinite Redshirts (ii-42) | `nemesis` Military Outpost | star |\n| Cold Probabilities (ii-42) | `nona` Civilian Surface Outpost | `3 a` |\n| Refined Industrial Probabilities (ii-42) | `quad_truss` Coriolis Starport | `3 a` |\n| Plundered Probabilities (ii-42) | `dysnomia` Pirate Outpost | `5 d` |\n| Probably Redshirts (ii-42) | `nemesis` Military Outpost | `4 a` |",
            "| Primary Improbable Discoveries (ii-42) | `prometheus` Scientific Outpost | `4 d` |\n| Infinite Redshirts (ii-42) | `nemesis` Military Outpost | star |\n| Cold Probabilities (ii-42) | `nona` Civilian Surface Outpost | `3 a` |\n| Refined Industrial Probabilities (ii-42) | `quad_truss` Coriolis Starport | `3 a` |\n| Plundered Probabilities (ii-42) | `dysnomia` Pirate Outpost | `5 d` |\n| Probably Redshirts (ii-42) | `nemesis` Military Outpost | `4 a` |\n| Test Installation Station (ii-42) | `dionysus` Space Bar Installation | `3 b` |"
        ).replace(
            "Primary Improbable Discoveries (ii-42) · Infinite Redshirts (ii-42) · Cold Probabilities (ii-42) ·\nRefined Industrial Probabilities (ii-42) · Plundered Probabilities (ii-42) · Probably Redshirts (ii-42)",
            "Primary Improbable Discoveries (ii-42) · Infinite Redshirts (ii-42) · Cold Probabilities (ii-42) ·\nRefined Industrial Probabilities (ii-42) · Plundered Probabilities (ii-42) · Probably Redshirts (ii-42) · Test Installation Station (ii-42)"
        )
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "dossier.coverage_match" and f.severity == "error"]
        assert len(errors) >= 1

    def test_multiple_sites_in_section_4_parsed_correctly(self):
        """Multiple sites in section 4 should all be parsed."""
        dossier = VALID_DOSSIER.replace(
            "| Primary Improbable Discoveries (ii-42) | `prometheus` Scientific Outpost | `4 d` |\n| Infinite Redshirts (ii-42) | `nemesis` Military Outpost | star |\n| Cold Probabilities (ii-42) | `nona` Civilian Surface Outpost | `3 a` |\n| Refined Industrial Probabilities (ii-42) | `quad_truss` Coriolis Starport | `3 a` |\n| Plundered Probabilities (ii-42) | `dysnomia` Pirate Outpost | `5 d` |\n| Probably Redshirts (ii-42) | `nemesis` Military Outpost | `4 a` |",
            "| Primary Improbable Discoveries (ii-42) | `prometheus` Scientific Outpost | `4 d` |\n| Infinite Redshirts (ii-42) | `nemesis` Military Outpost | star |\n| Cold Probabilities (ii-42) | `nona` Civilian Surface Outpost | `3 a` |\n| Refined Industrial Probabilities (ii-42) | `quad_truss` Coriolis Starport | `3 a` |\n| Plundered Probabilities (ii-42) | `dysnomia` Pirate Outpost | `5 d` |\n| Probably Redshirts (ii-42) | `nemesis` Military Outpost | `4 a` |\n| Another Station (ii-42) | `atropos` Civilian Surface Outpost | `3 b` |\n| Third Station (ii-42) | `prometheus` Scientific Outpost | `4 d` |"
        ).replace(
            "Primary Improbable Discoveries (ii-42) · Infinite Redshirts (ii-42) · Cold Probabilities (ii-42) ·\nRefined Industrial Probabilities (ii-42) · Plundered Probabilities (ii-42) · Probably Redshirts (ii-42)",
            "Primary Improbable Discoveries (ii-42) · Infinite Redshirts (ii-42) · Cold Probabilities (ii-42) ·\nRefined Industrial Probabilities (ii-42) · Plundered Probabilities (ii-42) · Probably Redshirts (ii-42) · Another Station · Third Station"
        )
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        # Should not have site_table errors
        errors = [f for f in result.findings if f.rule == "dossier.site_table" and f.severity == "error"]
        assert len(errors) == 0

    def test_section_4_with_multiple_status_sections(self):
        """Section 4 with Complete, Under construction, Planned subsections."""
        dossier = VALID_DOSSIER.replace(
            "### Complete (3)\n\n| Site | Build type | Body |\n|---|---|---|\n| Primary Improbable Discoveries (ii-42) | `prometheus` Scientific Outpost | `4 d` |\n| Infinite Redshirts (ii-42) | `nemesis` Military Outpost | star |\n| Cold Probabilities (ii-42) | `nona` Civilian Surface Outpost | `3 a` |\n| Refined Industrial Probabilities (ii-42) | `quad_truss` Coriolis Starport | `3 a` |\n| Plundered Probabilities (ii-42) | `dysnomia` Pirate Outpost | `5 d` |\n| Probably Redshirts (ii-42) | `nemesis` Military Outpost | `4 a` |",
            """### Complete (1)

| Site | Build type | Body |
|---|---|---|
| Test Station (ii-42) | `nona` Civilian Surface Outpost | `3 a` |

### Under construction (1)

| Site | Build type | Body |
|---|---|---|
| Building Station (ii-42) | `quad_truss` Coriolis Starport | `3 a` |

### Definitely planned (1)

| Site | Build type | Body |
|---|---|---|
| Planned Station (ii-42) | `dionysus` Space Bar Installation | `3` |"""
        )
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        # Should parse all tables
        errors = [f for f in result.findings if f.rule == "dossier.site_table" and f.severity == "error"]
        assert len(errors) == 0

    def test_system_name_in_rules_matches_parameter(self):
        """System name in rules should match the system_name parameter."""
        rules = """[system]
names = ["Wrong System"]
dossier = "test.md"
voices = ["Foreman"]
"""
        result = validate_definition(VALID_DOSSIER, rules, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "rules.system_names" and f.severity == "error"]
        assert len(errors) >= 1
        assert any("Test System" in f.message or "Wrong System" in f.message for f in errors)

    def test_dossier_section_7_empty_is_error_if_landable_stations_exist(self):
        """Empty §7 coverage when landable stations exist in §4 should be error."""
        dossier = VALID_DOSSIER.replace(
            "Primary Improbable Discoveries (ii-42) · Infinite Redshirts (ii-42) · Cold Probabilities (ii-42) ·\nRefined Industrial Probabilities (ii-42) · Plundered Probabilities (ii-42) · Probably Redshirts (ii-42)",
            ""
        )
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "dossier.coverage_match" and f.severity == "error"]
        assert len(errors) >= 1

    def test_dossier_section_8_empty_when_rules_have_voices_is_error(self):
        """Empty §8 voices when rules declare voices should be error."""
        dossier = VALID_DOSSIER.replace(
            "### Voices used\n\n- **Crew:** `[<Foreman>]`, `[<Welder>]`, `[<Researcher>]`, `[<LabTech>]`\n- **Garrison:** `[<GuardSarge>]`, `[<GuardTrooper>]`",
            ""
        )
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        assert not result.passed
        errors = [f for f in result.findings if f.rule == "dossier.voice_coverage" and f.severity == "error"]
        assert len(errors) >= 1

    def test_all_rules_toml_missing_fact_image_is_warn(self):
        """Missing fact_image in all.rules.toml should be warning when checking img_url."""
        # This requires the all_rules parameter
        pass

    def test_dossier_section_4_site_name_extraction(self):
        """Site names should be correctly extracted from table cells with backticks and markdown."""
        dossier = VALID_DOSSIER.replace(
            "| Primary Improbable Discoveries (ii-42) | `prometheus` Scientific Outpost | `4 d` |\n| Infinite Redshirts (ii-42) | `nemesis` Military Outpost | star |\n| Cold Probabilities (ii-42) | `nona` Civilian Surface Outpost | `3 a` |\n| Refined Industrial Probabilities (ii-42) | `quad_truss` Coriolis Starport | `3 a` |\n| Plundered Probabilities (ii-42) | `dysnomia` Pirate Outpost | `5 d` |\n| Probably Redshirts (ii-42) | `nemesis` Military Outpost | `4 a` |",
            "| `Primary Improbable Discoveries (ii-42)` | `prometheus` Scientific Outpost | `4 d` |\n| Infinite*Redshirts* (ii-42) | `nemesis` Military Outpost | star |\n| Cold Probabilities (ii-42) | `nona` Civilian Surface Outpost | `3 a` |\n| Refined Industrial Probabilities (ii-42) | `quad_truss` Coriolis Starport | `3 a` |\n| Plundered Probabilities (ii-42) | `dysnomia` Pirate Outpost | `5 d` |\n| Probably Redshirts (ii-42) | `nemesis` Military Outpost | `4 a` |"
        ).replace(
            "Primary Improbable Discoveries (ii-42) · Infinite Redshirts (ii-42) · Cold Probabilities (ii-42) ·\nRefined Industrial Probabilities (ii-42) · Plundered Probabilities (ii-42) · Probably Redshirts (ii-42)",
            "Primary Improbable Discoveries (ii-42) · Infinite*Redshirts* (ii-42) · Cold Probabilities (ii-42) ·\nRefined Industrial Probabilities (ii-42) · Plundered Probabilities (ii-42) · Probably Redshirts (ii-42)"
        )
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        # Should handle backticks and asterisks in cell content
        errors = [f for f in result.findings if f.rule == "dossier.site_table" and f.severity == "error"]
        assert len(errors) == 0
        errors = [f for f in result.findings if f.rule == "dossier.coverage_match" and f.severity == "error"]
        assert len(errors) == 0

    def test_section_4_build_type_extraction(self):
        """Build type should be correctly extracted from backtick-enclosed token."""
        dossier = VALID_DOSSIER.replace(
            "| Primary Improbable Discoveries (ii-42) | `prometheus` Scientific Outpost | `4 d` |\n| Infinite Redshirts (ii-42) | `nemesis` Military Outpost | star |\n| Cold Probabilities (ii-42) | `nona` Civilian Surface Outpost | `3 a` |\n| Refined Industrial Probabilities (ii-42) | `quad_truss` Coriolis Starport | `3 a` |\n| Plundered Probabilities (ii-42) | `dysnomia` Pirate Outpost | `5 d` |\n| Probably Redshirts (ii-42) | `nemesis` Military Outpost | `4 a` |",
            "| Primary Improbable Discoveries (ii-42) | `prometheus` Scientific Outpost | `4 d` |\n| Infinite Redshirts (ii-42) | `nemesis` Military Outpost | star |\n| Cold Probabilities (ii-42) | `nona` Civilian Surface Outpost | `3 a` |\n| Refined Industrial Probabilities (ii-42) | `quad_truss` Coriolis Starport | `3 a` |\n| Plundered Probabilities (ii-42) | `dysnomia` Pirate Outpost | `5 d` |\n| Probably Redshirts (ii-42) | `nemesis` Military Outpost | `4 a` |\n| Hub Station (ii-42) | `silenus` Refinery Hub | `3 b` |"
        ).replace(
            "Primary Improbable Discoveries (ii-42) · Infinite Redshirts (ii-42) · Cold Probabilities (ii-42) ·\nRefined Industrial Probabilities (ii-42) · Plundered Probabilities (ii-42) · Probably Redshirts (ii-42)",
            "Primary Improbable Discoveries (ii-42) · Infinite Redshirts (ii-42) · Cold Probabilities (ii-42) ·\nRefined Industrial Probabilities (ii-42) · Plundered Probabilities (ii-42) · Probably Redshirts (ii-42)"
        )
        result = validate_definition(dossier, VALID_RULES, "Test System")
        
        # Hub station in §4 but not in coverage - should pass (hub not landable, correctly excluded)
        errors = [f for f in result.findings if f.rule == "dossier.coverage_match" and f.severity == "error"]
        assert len(errors) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])