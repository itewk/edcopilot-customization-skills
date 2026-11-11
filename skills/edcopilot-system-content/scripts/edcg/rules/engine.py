"""Build-type catalogue lookups for the EDCoPilot system content skill.

Reads the offline copy of the Raven Colonial facility catalogue so a site can be
classified as landable (has pads) or not, and by whether it sits on a surface or
in orbit, without a network call.
"""

import tomllib
from pathlib import Path
from typing import Any, cast

# Rule data ships beside the engine as package data.
RULE_DATA_DIR = Path(__file__).resolve().parent / "data"

# Lazy-loaded cached resources
_base_rules: dict[str, Any] | None = None
_build_types: dict[str, Any] | None = None
_raven_config: dict[str, Any] | None = None


def _load_toml_data(filename: str) -> dict[str, Any]:
    """Load a TOML file from the rule data directory."""
    with (RULE_DATA_DIR / filename).open("rb") as f:
        return tomllib.load(f)


def get_base_rules() -> dict[str, Any]:
    """Get base rules (base.toml) - cached after first load."""
    global _base_rules
    if _base_rules is None:
        _base_rules = _load_toml_data("base.toml")
    return _base_rules


def get_build_types() -> dict[str, Any]:
    """Get build types catalogue (build_types.toml) - cached after first load."""
    global _build_types
    if _build_types is None:
        _build_types = _load_toml_data("build_types.toml")
    return _build_types


def get_raven_config() -> dict[str, Any]:
    """Get Raven Colonial API config (raven.toml) - cached after first load."""
    global _raven_config
    if _raven_config is None:
        _raven_config = _load_toml_data("raven.toml")
    return _raven_config


def get_vocab() -> dict[str, Any]:
    """Get vocabulary from base rules."""
    return cast(dict[str, Any], get_base_rules().get("vocab", {}))


def get_kinds() -> dict[str, Any]:
    """Get tag kinds from base rules."""
    return cast(dict[str, Any], get_base_rules().get("kinds", {}))


def get_filters() -> dict[str, Any]:
    """Get filter definitions from base rules."""
    return cast(
        dict[str, Any],
        get_base_rules().get("rules", {}).get("syntax", {}).get("filter_known", {}).get("filters", {}),
    )


def _get_all_build_types() -> dict[str, dict[str, str]]:
    """Get a flat dict of all build types with their class and name."""
    build_types = get_build_types()
    classes = build_types.get("classes", {})
    flat = {}
    for class_name, class_dict in classes.items():
        for bt_name, bt_facility_name in class_dict.items():
            flat[bt_name] = {"class": class_name, "name": bt_facility_name}
    return flat


def get_landable_build_types() -> list[str]:
    """Get list of build types that are landable (not hub/installation)."""
    # From base.toml: not_landable_classes = ["hub", "installation"]
    all_bts = _get_all_build_types()
    landable = []
    for bt_name, bt_info in all_bts.items():
        bt_class = bt_info.get("class", "").lower()
        if bt_class not in ("hub", "installation"):
            landable.append(bt_name)
    return landable


def is_landable_build_type(build_type: str) -> bool:
    """Check if a build type is landable (has landing pads)."""
    all_bts = _get_all_build_types()
    bt_info = all_bts.get(build_type)
    if bt_info is None:
        return False
    bt_class = bt_info.get("class", "").lower()
    return bt_class not in ("hub", "installation")


def get_facility_class(build_type: str) -> str:
    """Get the facility class for a build type (e.g., 'starport', 'outpost', 'hub')."""
    all_bts = _get_all_build_types()
    return all_bts.get(build_type, {}).get("class", "unknown")


def get_facility_name(build_type: str) -> str:
    """Get the human-readable facility name for a build type."""
    all_bts = _get_all_build_types()
    return all_bts.get(build_type, {}).get("name", build_type)


def get_placement(build_type: str) -> str:
    """Get whether a build type sits on a body surface or in orbit.

    Placement is a property of the build type, not of the facility class:
    outposts and starports exist in both variants. A Scientific Outpost
    ("prometheus") has class "outpost" but orbits, while a Scientific Surface
    Outpost ("ananke") is on the ground.

    Args:
        build_type: The build type code (e.g. "prometheus").

    Returns:
        "surface", "orbital", or "unknown" when the type is not catalogued.
    """
    placement = get_build_types().get("placement", {})
    if build_type in placement.get("surface", []):
        return "surface"
    if build_type in placement.get("orbital", []):
        return "orbital"
    return "unknown"


def load_system_rules(rules_path: Path) -> dict[str, Any]:
    """Load a system-specific rules TOML file."""
    with rules_path.open("rb") as f:
        return tomllib.load(f)


def load_house_rules(rules_path: Path) -> dict[str, Any]:
    """Load house rules (all.rules.toml) from definitions root."""
    with rules_path.open("rb") as f:
        return tomllib.load(f)


def merge_rules(base: dict[str, Any], house: dict[str, Any], system: dict[str, Any]) -> dict[str, Any]:
    """Merge base, house, and system rules following the precedence order.

    Precedence: base.toml → house (all.rules.toml) → system (system.rules.toml)
    House rules can only override, not declare new impl.
    System rules can only override, not declare new impl.
    """
    import copy
    merged = copy.deepcopy(base)

    def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                _deep_merge(target[key], value)
            else:
                target[key] = value

    if "rules" in house:
        _deep_merge(merged.setdefault("rules", {}), house["rules"])
    if "rules" in system:
        _deep_merge(merged.setdefault("rules", {}), system["rules"])

    return merged


__all__ = [
    "get_base_rules",
    "get_build_types",
    "get_raven_config",
    "get_vocab",
    "get_kinds",
    "get_filters",
    "get_landable_build_types",
    "is_landable_build_type",
    "get_facility_class",
    "get_facility_name",
    "get_placement",
    "load_system_rules",
    "load_house_rules",
    "merge_rules",
]
