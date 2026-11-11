"""Tests for base rules loading from package data."""

import pytest
from pathlib import Path
from edcg.rules import engine

class TestBaseRulesLoading:
    """Tests for loading base rules from package data."""

    def test_get_base_rules_returns_dict(self):
        """Test that get_base_rules returns a dictionary."""
        rules = engine.get_base_rules()
        assert isinstance(rules, dict)
        assert len(rules) > 0

    def test_base_rules_has_version(self):
        """Test that base rules have a version field."""
        rules = engine.get_base_rules()
        assert "version" in rules
        assert isinstance(rules["version"], int)

    def test_base_rules_has_content_section(self):
        """Test that base rules have content configuration."""
        rules = engine.get_base_rules()
        assert "content" in rules
        content = rules["content"]
        assert "file" in content
        assert content["file"] == "EDCoPilot.SpeechExtensions.Custom.txt"
        assert "line_ending" in content
        assert content["line_ending"] == "crlf"

    def test_base_rules_has_provenance_section(self):
        """Test that base rules have provenance pattern."""
        rules = engine.get_base_rules()
        assert "provenance" in rules
        assert "pattern" in rules["provenance"]

    def test_base_rules_has_vocab_section(self):
        """Test that base rules have vocabulary definitions."""
        rules = engine.get_base_rules()
        assert "vocab" in rules
        vocab = rules["vocab"]
        assert "undocumented" in vocab
        assert "documented" in vocab
        assert isinstance(vocab["undocumented"], list)
        assert isinstance(vocab["documented"], dict)
        # Check some known tokens
        assert "Commander" in vocab["documented"]
        assert "cmdrname" in vocab["documented"]
        assert "myshipname" in vocab["documented"]

    def test_base_rules_has_kinds_section(self):
        """Test that base rules have tag kinds definitions."""
        rules = engine.get_base_rules()
        assert "kinds" in rules
        kinds = rules["kinds"]
        # Check all expected kinds exist
        expected_kinds = [
            "SystemGreeting",
            "SystemBroadcast",
            "StationGreeting",
            "StationChatter",
            "StationFact",
            "ConfirmedCommander",
            "CoPilotStarting",
            "RandomShipName",
        ]
        for kind in expected_kinds:
            assert kind in kinds, f"Missing kind: {kind}"
            assert "parts" in kinds[kind]
            assert isinstance(kinds[kind]["parts"], list)

    def test_base_rules_has_rules_section(self):
        """Test that base rules have rule definitions."""
        rules = engine.get_base_rules()
        assert "rules" in rules
        rule_sections = rules["rules"]
        # Check major rule categories exist
        assert "syntax" in rule_sections
        assert "filters" in rule_sections
        assert "content" in rule_sections
        assert "db" in rule_sections
        assert "dossier" in rule_sections

    def test_syntax_rules_exist(self):
        """Test that syntax rules are defined."""
        rules = engine.get_base_rules()
        syntax = rules["rules"]["syntax"]
        expected_syntax_rules = [
            "filter_known",
            "filter_leads",
            "token_known",
            "token_case",
            "encoding",
            "no_example_wrapper",
        ]
        for rule in expected_syntax_rules:
            assert rule in syntax, f"Missing syntax rule: {rule}"
            assert "impl" in syntax[rule]
            assert "severity" in syntax[rule]
            assert "why" in syntax[rule]

    def test_format_rules_exist(self):
        """Test that format rules are defined."""
        rules = engine.get_base_rules()
        fmt = rules["rules"]["format"]
        assert "tag_shape" in fmt
        assert fmt["tag_shape"]["impl"] == "rule_format_tag_shape"
        assert fmt["tag_shape"]["severity"] == "error"
        assert "why" in fmt["tag_shape"]

    def test_filter_known_has_filters(self):
        """Test that filter_known rule has filter definitions."""
        rules = engine.get_base_rules()
        filters = rules["rules"]["syntax"]["filter_known"]["filters"]
        assert isinstance(filters, dict)
        expected_filters = [
            "allbusiness",
            "vegan",
            "profanity",
            "flirt",
            "innuendo",
            "alcohol",
            "toughlove",
            "dislikesmining",
            "notranslate",
            "homesystem",
            "nothomesystem",
            "CMDRisMale",
            "CMDRisFemale",
            "AIisMale",
            "AIisFemale",
            "crime_neutral",
            "crime_dislike",
            "crime_like",
            "XenoStance_Anti",
            "XenoStance_Peace",
            "XenoStance_Pro",
        ]
        for f in expected_filters:
            assert f in filters, f"Missing filter: {f}"
            assert isinstance(filters[f], str)
            assert len(filters[f]) > 0

    def test_filters_required_rules_exist(self):
        """Test that required filter policy rules exist."""
        rules = engine.get_base_rules()
        filter_rules = rules["rules"]["filters"]
        expected_required = [
            "vegan",
            "alcohol",
            "profanity",
            "flirt",
            "innuendo",
        ]
        for req in expected_required:
            assert req in filter_rules, f"Missing required filter rule: {req}"
            assert "required" in filter_rules[req], f"Missing 'required' sub-rule for {req}"
            required = filter_rules[req]["required"]
            assert required["impl"] == "policy"
            assert "why" in required

    def test_allbusiness_rule_exists(self):
        """Test that allbusiness mechanical rule exists."""
        rules = engine.get_base_rules()
        allbusiness = rules["rules"]["filters"]["allbusiness"]
        assert allbusiness["impl"] == "rule_filters_allbusiness"
        assert allbusiness["severity"] == "error"
        assert "warn_below" in allbusiness
        assert "applies_to" in allbusiness
        assert set(allbusiness["applies_to"]) == {
            "SystemGreeting",
            "SystemBroadcast",
            "StationGreeting",
            "StationChatter",
        }

    def test_fallback_rule_exists(self):
        """Test that fallback rule exists."""
        rules = engine.get_base_rules()
        fallback = rules["rules"]["filters"]["fallback"]
        assert fallback["impl"] == "rule_filters_fallback"
        assert fallback["severity"] == "error"
        assert fallback["require_allbusiness_clean"] is True

    def test_content_rules_exist(self):
        """Test that content rules exist."""
        rules = engine.get_base_rules()
        content_rules = rules["rules"]["content"]
        expected_content_rules = [
            "fact_image",
            "no_links",
            "fact_no_filters",
            "station_landable",
            "commander_token",
        ]
        for rule in expected_content_rules:
            assert rule in content_rules, f"Missing content rule: {rule}"
            assert "impl" in content_rules[rule]
            assert "severity" in content_rules[rule]
            assert "why" in content_rules[rule]

    def test_station_landable_has_not_landable_classes(self):
        """Test that station_landable rule has not_landable_classes."""
        rules = engine.get_base_rules()
        station_landable = rules["rules"]["content"]["station_landable"]
        assert "not_landable_classes" in station_landable
        assert station_landable["not_landable_classes"] == ["hub", "installation"]

    def test_dossier_spine_rule_exists(self):
        """Test that dossier spine rule exists with expected sections."""
        rules = engine.get_base_rules()
        spine = rules["rules"]["dossier"]["spine"]
        assert spine["impl"] == "rule_dossier_spine"
        assert spine["severity"] == "error"
        assert "title_severity" in spine
        assert "sections" in spine
        assert isinstance(spine["sections"], list)
        assert len(spine["sections"]) == 9
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
        assert spine["sections"] == expected_sections


class TestBuildTypesLoading:
    """Tests for loading build types catalogue."""

    def test_get_build_types_returns_dict(self):
        """Test that get_build_types returns a dictionary."""
        build_types = engine.get_build_types()
        assert isinstance(build_types, dict)
        assert len(build_types) > 0

    def test_build_types_has_version(self):
        """Test that build types have a version field."""
        build_types = engine.get_build_types()
        assert "version" in build_types
        assert isinstance(build_types["version"], int)

    def test_build_types_has_classes(self):
        """Test that build types have class sections."""
        build_types = engine.get_build_types()
        assert "classes" in build_types
        classes = build_types["classes"]
        expected_classes = ["starport", "outpost", "settlement", "hub", "installation"]
        for cls in expected_classes:
            assert cls in classes, f"Missing class: {cls}"
            assert isinstance(classes[cls], dict)
            assert len(classes[cls]) > 0

    def test_starport_build_types(self):
        """Test starport build types are defined."""
        build_types = engine.get_build_types()
        starports = build_types["classes"]["starport"]
        expected = [
            "aphrodite", "hera", "poseidon", "zeus",
            "apollo", "artemis",
            "asteroid",
            "dodec", "quint_truss", "dec_truss",
            "no_truss", "dual_truss", "quad_truss",
            "ocellus",
        ]
        for bt in expected:
            assert bt in starports, f"Missing starport build type: {bt}"

    def test_outpost_build_types(self):
        """Test outpost build types are defined."""
        build_types = engine.get_build_types()
        outposts = build_types["classes"]["outpost"]
        expected = [
            "ananke", "antevorta", "fauna", "necessitas", "porrima", "providentia",
            "atropos", "clotho", "decima", "hestia", "lachesis", "nona",
            "bia", "hephaestus", "mefitis", "opis", "ponos", "tethys",
            "dysnomia",
            "nemesis",
            "plutus",
            "prometheus",
            "vesta",
            "vulcan",
        ]
        for bt in expected:
            assert bt in outposts, f"Missing outpost build type: {bt}"

    def test_settlement_build_types(self):
        """Test settlement build types are defined."""
        build_types = engine.get_build_types()
        settlements = build_types["classes"]["settlement"]
        expected = [
            "aerecura", "erebus", "mantus", "orcus", "ourea",
            "annona", "picumnus", "ceres", "fornax", "consus",
            "chronos", "asteria", "caerus", "pheobe",
            "comus", "gelos", "fufluns", "aergia",
            "gaea", "meteope", "minthe", "palici", "fontus",
            "minerva", "bellona", "enyo", "polemos", "ioke",
        ]
        for bt in expected:
            assert bt in settlements, f"Missing settlement build type: {bt}"

    def test_hub_build_types(self):
        """Test hub build types are defined."""
        build_types = engine.get_build_types()
        hubs = build_types["classes"]["hub"]
        expected = [
            "aegle", "alala", "ares", "athena", "caelus",
            "eunostus", "molae", "tellus_i", "io", "janus",
            "silenus", "tartarus", "tellus_e",
        ]
        for bt in expected:
            assert bt in hubs, f"Missing hub build type: {bt}"

    def test_installation_build_types(self):
        """Test installation build types are defined."""
        build_types = engine.get_build_types()
        installations = build_types["classes"]["installation"]
        expected = [
            "alastor", "vacuna",
            "aletheia", "pistis", "soter",
            "angelia", "eirene", "hermes",
            "apate", "laverna",
            "asclepius", "eupraxia",
            "astraeus", "coeus", "dione", "dodona",
            "bacchus", "dionysus",
            "demeter",
            "dicaeosyne", "eunomia", "nomos", "poena",
            "enodia", "ichnaea",
            "euthenia", "phorcys",
            "harmonia",
            "hedone", "opora", "pasithea",
        ]
        for bt in expected:
            assert bt in installations, f"Missing installation build type: {bt}"


class TestRavenConfigLoading:
    """Tests for loading Raven Colonial API configuration."""

    def test_get_raven_config_returns_dict(self):
        """Test that get_raven_config returns a dictionary."""
        config = engine.get_raven_config()
        assert isinstance(config, dict)
        assert len(config) > 0

    def test_raven_config_has_version(self):
        """Test that raven config has a version field."""
        config = engine.get_raven_config()
        assert "version" in config
        assert isinstance(config["version"], int)

    def test_raven_config_has_base_url(self):
        """Test that raven config has base_url."""
        config = engine.get_raven_config()
        assert "base_url" in config
        assert config["base_url"] == "https://ravencolonial100-awcbdvabgze4c5cq.canadacentral-01.azurewebsites.net"

    def test_raven_config_has_endpoints(self):
        """Test that raven config has endpoints."""
        config = engine.get_raven_config()
        assert "endpoints" in config
        endpoints = config["endpoints"]
        assert "system" in endpoints
        assert "sites" in endpoints
        assert "{system}" in endpoints["system"]
        assert "{system}" in endpoints["sites"]


class TestVocabAccess:
    """Tests for vocabulary access functions."""

    def test_get_vocab_returns_vocab(self):
        """Test that get_vocab returns the vocab section."""
        vocab = engine.get_vocab()
        assert isinstance(vocab, dict)
        assert "undocumented" in vocab
        assert "documented" in vocab

    def test_get_vocab_undocumented(self):
        """Test that undocumented tokens are accessible."""
        vocab = engine.get_vocab()
        undoc = vocab["undocumented"]
        assert isinstance(undoc, list)
        assert "systemname" in undoc
        assert "bodyName" in undoc
        assert "bodyType" in undoc
        assert "greeting" in undoc

    def test_get_vocab_documented(self):
        """Test that documented tokens are accessible."""
        vocab = engine.get_vocab()
        doc = vocab["documented"]
        assert isinstance(doc, dict)
        assert "Commander" in doc
        assert "cmdrname" in doc
        assert "myshipname" in doc
        assert "fuelLevels" in doc
        assert "starsystem" in doc
        assert "stationname" in doc


class TestKindsAccess:
    """Tests for tag kinds access functions."""

    def test_get_kinds_returns_kinds(self):
        """Test that get_kinds returns the kinds section."""
        kinds = engine.get_kinds()
        assert isinstance(kinds, dict)
        expected = [
            "SystemGreeting", "SystemBroadcast", "StationGreeting",
            "StationChatter", "StationFact", "ConfirmedCommander",
            "CoPilotStarting", "RandomShipName",
        ]
        for k in expected:
            assert k in kinds
            assert "parts" in kinds[k]
            assert isinstance(kinds[k]["parts"], list)

    def test_kinds_spoken_flag(self):
        """Test that spoken kinds have spoken=true."""
        kinds = engine.get_kinds()
        spoken_kinds = ["SystemGreeting", "SystemBroadcast", "StationGreeting", "StationChatter"]
        for k in spoken_kinds:
            assert kinds[k].get("spoken") is True, f"{k} should be spoken"
        # StationFact and others should not have spoken or be False
        assert kinds["StationFact"].get("spoken") is not True
        assert kinds["ConfirmedCommander"].get("spoken") is not True


class TestFiltersAccess:
    """Tests for filter definitions access."""

    def test_get_filters_returns_filters(self):
        """Test that get_filters returns the filter definitions."""
        filters = engine.get_filters()
        assert isinstance(filters, dict)
        expected = [
            "allbusiness", "vegan", "profanity", "flirt", "innuendo",
            "alcohol", "toughlove", "dislikesmining", "notranslate",
            "homesystem", "nothomesystem", "CMDRisMale", "CMDRisFemale",
            "AIisMale", "AIisFemale", "crime_neutral", "crime_dislike",
            "crime_like", "XenoStance_Anti", "XenoStance_Peace", "XenoStance_Pro",
        ]
        for f in expected:
            assert f in filters
            assert isinstance(filters[f], str)
            assert len(filters[f]) > 0


class TestBuildTypeUtilities:
    """Tests for build type utility functions."""

    def test_get_landable_build_types_returns_list(self):
        """Test that get_landable_build_types returns a list."""
        landable = engine.get_landable_build_types()
        assert isinstance(landable, list)
        assert len(landable) > 0

    def test_landable_includes_starports_outposts_settlements(self):
        """Test that landable includes starports, outposts, settlements."""
        landable = engine.get_landable_build_types()
        # Should include starports
        assert any(bt.startswith(("aphrodite", "hera", "poseidon", "zeus", "apollo", "artemis", "asteroid", "dodec", "no_truss", "ocellus")) for bt in landable)
        # Should include outposts
        assert any(bt.startswith(("ananke", "atropos", "bia", "nemesis", "plutus", "prometheus", "vesta", "vulcan")) for bt in landable)
        # Should include settlements
        assert any(bt.startswith(("aerecura", "annona", "chronos", "comus", "gaea", "minerva")) for bt in landable)

    def test_landable_excludes_hubs_installations(self):
        """Test that landable excludes hubs and installations."""
        landable = engine.get_landable_build_types()
        hubs = ["aegle", "alala", "ares", "athena", "caelus", "eunostus", "molae", "tellus_i", "io", "janus", "silenus", "tartarus", "tellus_e"]
        installations = ["alastor", "vacuna", "aletheia", "pistis", "soter", "angelia", "eirene", "hermes", "apate", "laverna", "asclepius", "eupraxia", "astraeus", "coeus", "dione", "dodona", "bacchus", "dionysus", "demeter", "dicaeosyne", "eunomia", "nomos", "poena", "enodia", "ichnaea", "euthenia", "phorcys", "harmonia", "hedone", "opora", "pasithea"]
        for h in hubs:
            assert h not in landable, f"Hub {h} should not be landable"
        for i in installations:
            assert i not in landable, f"Installation {i} should not be landable"

    def test_is_landable_build_type(self):
        """Test is_landable_build_type function."""
        # Landable types
        assert engine.is_landable_build_type("aphrodite") is True  # starport
        assert engine.is_landable_build_type("ananke") is True  # outpost
        assert engine.is_landable_build_type("aerecura") is True  # settlement
        # Non-landable types
        assert engine.is_landable_build_type("aegle") is False  # hub
        assert engine.is_landable_build_type("alastor") is False  # installation
        # Unknown type
        assert engine.is_landable_build_type("unknown_type") is False

    def test_get_placement_outpost_variants(self):
        """Outposts exist in both orbital and surface variants."""
        # Scientific Outpost (medium pad, orbital) vs Scientific Surface Outpost
        assert engine.get_placement("prometheus") == "orbital"
        assert engine.get_placement("ananke") == "surface"
        # Civilian/Industrial Outpost orbit; their Surface variants do not
        assert engine.get_placement("vesta") == "orbital"
        assert engine.get_placement("atropos") == "surface"
        assert engine.get_placement("vulcan") == "orbital"
        assert engine.get_placement("bia") == "surface"

    def test_get_placement_starport_variants(self):
        """Large Planetary Ports sit on a surface; other starports orbit."""
        assert engine.get_placement("aphrodite") == "surface"
        assert engine.get_placement("hera") == "surface"
        assert engine.get_placement("poseidon") == "surface"
        assert engine.get_placement("zeus") == "surface"
        assert engine.get_placement("ocellus") == "orbital"
        assert engine.get_placement("dodec") == "orbital"
        assert engine.get_placement("asteroid") == "orbital"

    def test_get_placement_hubs_settlements_installations(self):
        """Hubs and settlements are surface builds; installations orbit."""
        assert engine.get_placement("aegle") == "surface"      # Civilian Hub
        assert engine.get_placement("tellus_e") == "surface"   # Exploration Hub
        assert engine.get_placement("aerecura") == "surface"   # Mining Settlement
        assert engine.get_placement("alastor") == "orbital"    # Military Installation
        assert engine.get_placement("bacchus") == "orbital"    # Space Bar Installation

    def test_get_placement_unknown_build_type(self):
        """An unknown build type has no placement."""
        assert engine.get_placement("unknown_type") == "unknown"

    def test_get_placement_is_an_exact_build_type_lookup(self):
        """Lookup is exact: no case folding, trimming or substring matching."""
        assert engine.get_placement("Prometheus") == "unknown"
        assert engine.get_placement(" prometheus") == "unknown"
        assert engine.get_placement("prometheus ") == "unknown"
        assert engine.get_placement("scientific outpost") == "unknown"
        assert engine.get_placement("") == "unknown"

    def test_get_placement_ignores_facility_name_wording(self):
        """The facility label never decides placement."""
        # The "Scientific Outpost" label is an orbital build type...
        assert engine.get_facility_name("prometheus") == "Scientific Outpost"
        assert engine.get_placement("prometheus") == "orbital"
        # ...while "Scientific Surface Outpost" is a surface build type.
        assert engine.get_facility_name("ananke") == "Scientific Surface Outpost"
        assert engine.get_placement("ananke") == "surface"

    def test_every_build_type_has_exactly_one_placement(self):
        """Placement data must cover the whole catalogue, and no type twice."""
        build_types = engine.get_build_types()
        placement = build_types["placement"]
        surface = set(placement["surface"])
        orbital = set(placement["orbital"])
        assert not surface & orbital, f"listed as both: {sorted(surface & orbital)}"

        catalogue = {
            code
            for entries in build_types["classes"].values()
            for code in entries
        }
        assert surface | orbital == catalogue, (
            f"missing: {sorted(catalogue - surface - orbital)}, "
            f"not in catalogue: {sorted((surface | orbital) - catalogue)}"
        )

    def test_get_facility_class(self):
        """Test get_facility_class function."""
        assert engine.get_facility_class("aphrodite") == "starport"
        assert engine.get_facility_class("ananke") == "outpost"
        assert engine.get_facility_class("aerecura") == "settlement"
        assert engine.get_facility_class("aegle") == "hub"
        assert engine.get_facility_class("alastor") == "installation"
        assert engine.get_facility_class("unknown") == "unknown"

    def test_get_facility_name(self):
        """Test get_facility_name function."""
        assert engine.get_facility_name("aphrodite") == "Large Planetary Port"
        assert engine.get_facility_name("ananke") == "Scientific Surface Outpost"
        assert engine.get_facility_name("aerecura") == "Mining Settlement"
        assert engine.get_facility_name("aegle") == "Civilian Hub"
        assert engine.get_facility_name("alastor") == "Military Installation"
        assert engine.get_facility_name("unknown") == "unknown"


class TestRulesLoadingFromFiles:
    """Tests for loading rules from external files."""

    def test_load_system_rules(self, tmp_path):
        """Test loading a system rules file."""
        rules_file = tmp_path / "test.rules.toml"
        rules_file.write_text("""
[system]
names = ["Test System"]
dossier = "test.md"
voices = ["Voice1", "Voice2"]
""")
        loaded = engine.load_system_rules(rules_file)
        assert "system" in loaded
        assert loaded["system"]["names"] == ["Test System"]
        assert loaded["system"]["dossier"] == "test.md"
        assert loaded["system"]["voices"] == ["Voice1", "Voice2"]

    def test_load_house_rules(self, tmp_path):
        """Test loading house rules file."""
        rules_file = tmp_path / "all.rules.toml"
        rules_file.write_text("""
[rules.filters.banned]
impl = "rule_filters_banned"
severity = "error"
tokens = ["profanity"]
""")
        loaded = engine.load_house_rules(rules_file)
        assert "rules" in loaded
        assert "filters" in loaded["rules"]
        assert "banned" in loaded["rules"]["filters"]
        assert loaded["rules"]["filters"]["banned"]["impl"] == "rule_filters_banned"

class TestMergeRules:
    """Tests for merging base, house, and system rules."""

    def test_merge_rules_basic(self):
        """Test basic merge functionality."""
        base = {
            "rules": {
                "test_rule": {"impl": "rule_test", "severity": "error", "value": 1}
            }
        }
        house = {
            "rules": {
                "test_rule": {"value": 2}
            }
        }
        system = {
            "rules": {
                "test_rule": {"value": 3}
            }
        }
        merged = engine.merge_rules(base, house, system)
        assert merged["rules"]["test_rule"]["value"] == 3
        assert merged["rules"]["test_rule"]["impl"] == "rule_test"
        assert merged["rules"]["test_rule"]["severity"] == "error"

    def test_merge_rules_house_overrides_base(self):
        """Test that house rules override base rules."""
        base = {"rules": {"rule1": {"severity": "error", "threshold": 10}}}
        house = {"rules": {"rule1": {"threshold": 20}}}
        system = {}
        merged = engine.merge_rules(base, house, system)
        assert merged["rules"]["rule1"]["severity"] == "error"
        assert merged["rules"]["rule1"]["threshold"] == 20

    def test_merge_rules_system_overrides_house(self):
        """Test that system rules override house rules."""
        base = {"rules": {"rule1": {"threshold": 10}}}
        house = {"rules": {"rule1": {"threshold": 20}}}
        system = {"rules": {"rule1": {"threshold": 30}}}
        merged = engine.merge_rules(base, house, system)
        assert merged["rules"]["rule1"]["threshold"] == 30

    def test_merge_rules_deep_merge(self):
        """Test deep merge of nested dictionaries."""
        base = {"rules": {"category": {"rule1": {"a": 1, "b": 2}}}}
        house = {"rules": {"category": {"rule1": {"b": 20, "c": 30}}}}
        system = {}
        merged = engine.merge_rules(base, house, system)
        assert merged["rules"]["category"]["rule1"]["a"] == 1
        assert merged["rules"]["category"]["rule1"]["b"] == 20
        assert merged["rules"]["category"]["rule1"]["c"] == 30

    def test_merge_rules_empty_house_system(self):
        """Test merge with empty house and system rules."""
        base = {"rules": {"rule1": {"value": 1}}}
        house = {}
        system = {}
        merged = engine.merge_rules(base, house, system)
        assert merged["rules"]["rule1"]["value"] == 1

    def test_merge_rules_no_rules_in_house_system(self):
        """Test merge when house/system have no rules key."""
        base = {"rules": {"rule1": {"value": 1}}}
        house = {"other": "data"}
        system = {"other": "data2"}
        merged = engine.merge_rules(base, house, system)
        assert merged["rules"]["rule1"]["value"] == 1
        assert "other" not in merged  # Only rules are merged


class TestTemplateLoading:
    """Tests for loading template assets from the assets folder.

    The dossier template ships pre-rendered (static placeholders, no Jinja
    syntax), so these are assertions about that static text rather than
    about a Jinja2 environment rendering it.
    """

    def test_dossier_template_loads(self):
        """Test loading the dossier template asset."""
        # Read directly from assets instead of using get_template function
        assets_dir = Path(__file__).resolve().parents[2] / "skills" / "edcopilot-system-content" / "assets"
        template_path = assets_dir / "dossier-template.md"
        template = template_path.read_text(encoding="utf-8")
        assert isinstance(template, str)
        assert len(template) > 0
        assert "<system name>" in template
        assert "<architect>" in template
        assert "<review date>" in template

    def test_dossier_template_has_correct_spine(self):
        """Test that the dossier template keeps its section spine."""
        # Read directly from assets instead of using get_template function
        assets_dir = Path(__file__).resolve().parents[2] / "skills" / "edcopilot-system-content" / "assets"
        template_path = assets_dir / "dossier-template.md"
        template = template_path.read_text(encoding="utf-8")
        assert template.startswith("# <system name> \u2014 system dossier")
        expected_headings = (
            "## 1. Identity and canon",
            "## 2. Lore and theme",
            "## 3. Tone rules (hard constraints)",
            "## 4. Canon site table",
            "## 5. Corrections log (do not reintroduce these)",
            "## 6. Site list maintenance",
            "## 7. Coverage",
            "## 8. Writing rules",
            "## 9. Open threads (TODO)",
        )
        for heading in expected_headings:
            assert heading in template

    def test_dossier_template_has_no_jinja_syntax(self):
        """Test that the dossier template is a static render, not a template."""
        # Read directly from assets instead of using get_template function
        assets_dir = Path(__file__).resolve().parents[2] / "skills" / "edcopilot-system-content" / "assets"
        template_path = assets_dir / "dossier-template.md"
        template = template_path.read_text(encoding="utf-8")
        assert "{{" not in template
        assert "}}" not in template
        assert "{%" not in template
        assert "%}" not in template
        assert "<%" not in template