"""Computed data for the writing brief and the batch update scan.

The old prompt builders mixed prose with facts: exact tag lines, section
bounds, voice declarations and per-system fact diffs. The prose now lives in the
skill's reference files, so this module extracts only the computed values and
returns them as JSON-serialisable dictionaries.
"""

from __future__ import annotations

import re
import tomllib
from typing import Awaitable, Callable

from edcg.common.config import Config
from edcg.common.layout import dossier_path, rules_path, slugify, systems_dir
from edcg.facts.facts import SystemFacts, compute_facts_diff
from edcg.rules.dossier import (
    extract_coverage_stations,
    extract_site_table,
    extract_voices,
    known_token_names,
    normalize_station_name,
    parse_sections,
)
from edcg.rules.engine import get_landable_build_types
from edcg.rules.validation import (
    RULE_DATA_DIR,
    load_base_config,
    resolve_bounds,
)

RAVEN_REVISION_RE = re.compile(r"revision\s*\|\s*[`\"]?(\d+)", re.IGNORECASE)

FactsGatherer = Callable[[str, Config], Awaitable[SystemFacts]]


def system_names(config: Config) -> list[str]:
    """Canonical names of every system that has a rules file, sorted.

    A rules file with no ``system.names`` is skipped rather than guessed at;
    the scan reports only systems it can name.
    """
    directory = systems_dir(config)
    if not directory.is_dir():
        return []
    names: list[str] = []
    for path in sorted(directory.glob("*.rules.toml")):
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        declared = data.get("system", {}).get("names", [])
        if isinstance(declared, list) and declared and isinstance(declared[0], str):
            names.append(declared[0])
    return names


def parse_dossier_for_diff(dossier: str) -> dict:
    """Parse dossier markdown into the dict ``compute_facts_diff`` expects.

    Port of the old helper: classify section-4 sites by build type and read the
    Raven revision from section 1.
    """
    sections, _ = parse_sections(dossier)
    sites = extract_site_table(sections.get(4, ("", []))[1])

    landable_build_types = set(get_landable_build_types())
    landable_stations: list[dict] = []
    non_landable_sites: list[dict] = []
    for site in sites:
        site_data = {
            "name": site["name"],
            "build_type": site["build_type"],
            "body": site["body"],
            "status": site.get("status", "unknown"),
        }
        if site["build_type"] in landable_build_types:
            landable_stations.append(site_data)
        else:
            non_landable_sites.append(site_data)

    raven_revision = 0
    if 1 in sections:
        section_1_text = "\n".join(sections[1][1])
        rev_match = RAVEN_REVISION_RE.search(section_1_text)
        if rev_match:
            raven_revision = int(rev_match.group(1))

    return {
        "raven_revision": raven_revision,
        "stations": landable_stations,
        "non_landable_sites": non_landable_sites,
    }


def _landable_stations_from_dossier(sections: dict) -> list[dict]:
    """Landable, non-tentative sites that also appear in section 7 coverage."""
    landable_build_types = set(get_landable_build_types())
    sites = extract_site_table(sections.get(4, ("", []))[1])
    candidates = [
        site
        for site in sites
        if site["build_type"] in landable_build_types
        and site.get("status") != "tentative"
    ]

    coverage = extract_coverage_stations(sections.get(7, ("", []))[1])
    by_name = {normalize_station_name(site["name"]): site for site in candidates}
    return [by_name[name] for name in sorted(coverage) if name in by_name]


def build_tag_lines(system_name: str, landable_stations: list[dict]) -> dict:
    """The exact tag lines the content must carry.

    Two system tags plus three tags for every landable station: the same shape
    as the old prompt builder, returned as data instead of a markdown section.
    """
    system_tags = [
        f"@SystemGreeting<~>{system_name}",
        f"@SystemBroadcast<~>{system_name}",
    ]
    station_tags = [
        f"{prefix}<~>{system_name}<~>{station['name']}"
        for station in landable_stations
        for prefix in ("@StationGreeting", "@StationChatter", "@StationFact")
    ]
    return {
        "system": system_tags,
        "station": station_tags,
        "all": system_tags + station_tags,
        "total": len(system_tags) + len(station_tags),
        "station_tag_count_per_station": 3,
    }


def build_voice_data(
    dossier_voices: set[str], system_voices: list[str]
) -> dict:
    """Voice declarations from the dossier and the system rules, as data."""
    dossier_only = sorted(set(dossier_voices) - set(system_voices))
    rules_only = sorted(set(system_voices) - set(dossier_voices))
    declared = sorted(set(dossier_voices) | set(system_voices))
    return {
        "dossier": sorted(dossier_voices),
        "rules": sorted(system_voices),
        "declarations": [f"[<{voice}>]" for voice in declared],
        "declared_in_both": sorted(set(dossier_voices) & set(system_voices)),
        "dossier_only": dossier_only,
        "rules_only": rules_only,
    }


def writing_brief_data(config: Config, system_name: str) -> dict:
    """Compute the writing brief's data for one system.

    Raises:
        FileNotFoundError: When the dossier or rules file is missing (the system
            has not been defined yet).
    """
    dossier_file = dossier_path(config, system_name)
    rules_file = rules_path(config, system_name)
    if not dossier_file.is_file() or not rules_file.is_file():
        raise FileNotFoundError(
            f"System '{system_name}' not found in content definitions. "
            f"Expected files: {dossier_file}, {rules_file}"
        )

    dossier_text = dossier_file.read_text(encoding="utf-8")
    rules_text = rules_file.read_text(encoding="utf-8")
    system_rules = tomllib.loads(rules_text)

    sections, _ = parse_sections(dossier_text)
    sites = extract_site_table(sections.get(4, ("", []))[1])
    landable_stations = _landable_stations_from_dossier(sections)

    base = load_base_config(RULE_DATA_DIR)
    known_tokens = {
        name.lower() for name in known_token_names(base.get("vocab", {}))
    }
    dossier_voices = (
        extract_voices(sections[8][1], known_tokens) if 8 in sections else set()
    )
    rules_voices = system_rules.get("system", {}).get("voices", [])
    if not isinstance(rules_voices, list):
        rules_voices = []

    raven_revision = 0
    if 1 in sections:
        rev_match = RAVEN_REVISION_RE.search("\n".join(sections[1][1]))
        if rev_match:
            raven_revision = int(rev_match.group(1))

    bounds_kinds, bounds_stations = resolve_bounds(base, system_rules)
    return {
        "system_name": system_name,
        "slug": slugify(system_name),
        "dossier_path": str(dossier_file),
        "rules_path": str(rules_file),
        "raven_revision": raven_revision,
        "tag_lines": build_tag_lines(system_name, landable_stations),
        "landable_stations": landable_stations,
        "bounds": {
            "default": {
                kind: [pair[0], pair[1]] for kind, pair in bounds_kinds.items()
            },
            "stations": {
                station: {
                    kind: [pair[0], pair[1]] for kind, pair in kinds.items()
                }
                for station, kinds in bounds_stations.items()
            },
        },
        "voices": build_voice_data(dossier_voices, rules_voices),
        "site_count": len(sites),
    }


def _fact_availability(facts: SystemFacts) -> dict:
    return {
        "raven": facts.raven_system is not None,
        "journal": facts.journal_data is not None,
        "inara": facts.inara_system is not None,
        "spansh": facts.spansh_system is not None,
    }


def _station_names(stations: list) -> list[str]:
    return sorted(station.name for station in stations)


async def build_update_scan(config: Config, gather: FactsGatherer) -> dict:
    """Scan every defined system and report its fact deltas as data.

    ``gather`` is injected so the CLI can be exercised without the network.
    Systems without a rules file, without a parseable canonical name, or whose
    facts cannot be gathered are reported with an ``error`` rather than dropped.
    """
    directory = systems_dir(config)
    results: list[dict] = []
    if not directory.is_dir():
        return {"systems": results, "systems_dir": str(directory)}

    for dossier_file in sorted(directory.glob("*.md")):
        slug = dossier_file.stem
        rules_file = directory / f"{slug}.rules.toml"
        entry: dict = {
            "slug": slug,
            "dossier_path": str(dossier_file),
            "rules_path": str(rules_file),
        }
        if not rules_file.is_file():
            entry.update({"system_name": None, "skipped": "no rules file"})
            results.append(entry)
            continue

        try:
            rules = tomllib.loads(rules_file.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            entry.update({"system_name": None, "error": f"cannot parse rules: {exc}"})
            results.append(entry)
            continue

        declared = rules.get("system", {}).get("names", [])
        if not isinstance(declared, list) or not declared:
            entry.update({"system_name": None, "error": "rules declare no system name"})
            results.append(entry)
            continue

        system_name = declared[0]
        entry["system_name"] = system_name
        try:
            existing = parse_dossier_for_diff(dossier_file.read_text(encoding="utf-8"))
            facts = await gather(system_name, config)
        except Exception as exc:
            entry["error"] = f"cannot gather facts: {exc}"
            results.append(entry)
            continue

        diff = compute_facts_diff(existing, facts)
        entry.update(
            {
                "dossier_coverage": sorted(
                    site["name"]
                    for site in existing["stations"] + existing["non_landable_sites"]
                ),
                "fact_availability": _fact_availability(facts),
                "raven_revision": {
                    "old": diff.old_revision,
                    "new": diff.new_revision,
                },
                "new_stations": _station_names(diff.new_landable_stations),
                "lost_stations": _station_names(diff.lost_landable_stations),
                "new_non_landable_sites": _station_names(
                    diff.new_non_landable_sites
                ),
                "lost_non_landable_sites": _station_names(
                    diff.lost_non_landable_sites
                ),
                "renamed_stations": [
                    {"old_name": item.old_name, "new_name": item.new_name}
                    for item in diff.renamed_stations
                ],
                "build_type_changes": [
                    {
                        "name": item.name,
                        "old_build_type": item.old_build_type,
                        "new_build_type": item.new_build_type,
                    }
                    for item in diff.build_type_changes
                ],
                "status_changes": [
                    {
                        "name": item.name,
                        "old_status": item.old_status,
                        "new_status": item.new_status,
                    }
                    for item in diff.status_changes
                ],
                "journal_only_stations": _station_names(
                    diff.journal_only_stations
                ),
                "has_changes": diff.has_changes(),
            }
        )
        results.append(entry)

    return {"systems": results, "systems_dir": str(directory)}
