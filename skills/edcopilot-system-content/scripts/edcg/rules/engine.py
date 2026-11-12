"""Build-type catalogue lookups for the EDCoPilot system content skill.

Reads the offline copy of the Raven Colonial facility catalogue so a site can be
classified as landable (has pads) or not, and by whether it sits on a surface or
in orbit, without a network call.
"""

import tomllib
from pathlib import Path
from typing import Any

# Rule data ships beside the engine as package data.
RULE_DATA_DIR = Path(__file__).resolve().parent / "data"

# Lazy-loaded cached resources
_base_rules: dict[str, Any] | None = None
_build_types: dict[str, Any] | None = None


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


def _get_all_build_types() -> dict[str, dict[str, str]]:
    """Get a flat dict of all build types with their class and name."""
    build_types = get_build_types()
    classes = build_types.get("classes", {})
    flat = {}
    for class_name, class_dict in classes.items():
        for bt_name, bt_facility_name in class_dict.items():
            flat[bt_name] = {"class": class_name, "name": bt_facility_name}
    return flat


# Used only when base.toml does not declare the list. The data is the source of
# truth; this fallback exists so a malformed rules file degrades rather than
# silently calling hubs landable.
_DEFAULT_NOT_LANDABLE_CLASSES = ("hub", "installation")


def not_landable_classes() -> tuple[str, ...]:
    """Facility classes that cannot take landing pads, from base.toml."""
    cfg = (
        get_base_rules()
        .get("rules", {})
        .get("content", {})
        .get("station_landable", {})
    )
    return tuple(
        str(cls).lower()
        for cls in cfg.get("not_landable_classes", _DEFAULT_NOT_LANDABLE_CLASSES)
    )


def get_landable_build_types() -> list[str]:
    """Get list of build types that are landable (not hub/installation)."""
    return [bt for bt in _get_all_build_types() if is_landable_build_type(bt)]


def is_landable_build_type(build_type: str) -> bool:
    """Check if a build type is landable (has landing pads)."""
    bt_info = _get_all_build_types().get(build_type)
    if bt_info is None:
        return False
    return str(bt_info.get("class", "")).lower() not in not_landable_classes()


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


__all__ = [
    "get_build_types",
    "get_landable_build_types",
    "is_landable_build_type",
    "get_facility_class",
    "get_facility_name",
    "get_placement",
    "not_landable_classes",
]
