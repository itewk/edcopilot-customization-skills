"""Dossier parsing utilities for EDCoPilot customization content.

Contains functions for parsing and validating system dossiers, including:
- Section parsing
- Site table extraction 
- Voice coverage analysis
- Station list parsing
"""

import re
from typing import List, Dict, Set, Tuple, Optional

# Regular expressions used in dossier parsing
SECTION_RE = re.compile(r"^##\s+(\d+)\.\s*(.*?)\s*$")
VOICE_TAG_RE = re.compile(r"\[<([^>]+)>\]")


def _parse_dossier_sections(dossier: str) -> Tuple[Dict[int, Tuple[str, List[str]]], List[int]]:
    """Parse dossier into sections: {section_num: (title, lines)}, and section_order list."""
    sections: Dict[int, Tuple[str, List[str]]] = {}
    section_order: List[int] = []
    lines = dossier.splitlines()
    current_num = None
    current_title = None
    current_lines: List[str] = []
    
    for line in lines:
        m = SECTION_RE.match(line)
        if m:
            if current_num is not None:
                sections[current_num] = (current_title, current_lines)
            current_num = int(m.group(1))
            current_title = m.group(2).strip()
            current_lines = []
            section_order.append(current_num)
        else:
            current_lines.append(line)
    
    if current_num is not None:
        sections[current_num] = (current_title, current_lines)
    
    return sections, section_order


def _extract_site_table(lines: List[str]) -> List[Dict]:
    """Extract site table rows from section 4 lines.
    
    Returns list of {name, build_type, body, status} dicts.
    Looks for tables with "Build type" column and a site name column.
    Handles variations like "Site | Build type | Body" or "System | Site | Build type | Orbits".
    Status is one of: complete, build, plan, tentative.
    """
    sites = []
    i = 0
    current_status = "unknown"
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Track subsection status
        if line.startswith("###"):
            if "complete" in line.lower():
                current_status = "complete"
            elif "build" in line.lower() or "construction" in line.lower():
                current_status = "build"
            elif "plan" in line.lower():
                current_status = "plan"
            elif "tentative" in line.lower():
                current_status = "tentative"
        
        # Look for table rows with site names
        if "|" in line and not line.startswith("#") and line.strip() != "":
            # Skip header lines 
            if any(header in line.lower() for header in ["site", "build type", "system", "body"]):
                i += 1
                continue
                
            # Parse table row (assumes format like: | Site Name | Build Type | Body | Status |)
            parts = [p.strip() for p in line.split('|') if p.strip()]
            
            if len(parts) >= 2:
                # Extract site name and build type from the first two columns
                site_name = parts[0].strip()
                build_type = parts[1].strip()
                
                # Try to extract body and status from remaining columns
                body = ""
                status = current_status
                
                if len(parts) >= 4:
                    # Body is usually in column 3, status in column 4
                    body = parts[2].strip()
                    status = parts[3].strip().lower() or current_status
                    
                # Only add if we have a valid site name
                if site_name and not site_name.startswith('Site') and not site_name.startswith('---'):
                    sites.append({
                        'name': site_name,
                        'build_type': build_type,
                        'body': body,
                        'status': status
                    })
        i += 1
    
    return sites


def _get_landable_build_types() -> Set[str]:
    """Return set of landable build types (those with landing pads)."""
    # This is a simplified version - in reality, this would come from the build types catalog
    return {
        "starport", "outpost", "settlement", "scientific_outpost",
        "research_station", "orbital_station", "space_station"
    }


def _extract_voices_from_section_8(lines: List[str]) -> Set[str]:
    """Extract voice names from dossier section 8 (Writing rules)."""
    voices: Set[str] = set()
    in_voices_used = False
    known_tokens = {
        "commander", "myshipname", "cmdrname", "system", "station", 
        "shipname", "shipclass", "shipmodel", "shipvariant"
    }
    
    for line in lines:
        stripped = line.strip()
        
        # Look for the section that lists voices used
        if "Voices used" in stripped and "###" in stripped:
            in_voices_used = True
            continue
        
        # Stop at next subsection header
        if in_voices_used and stripped.startswith("###"):
            break
        
        if in_voices_used:
            for match in VOICE_TAG_RE.finditer(line):
                voice = match.group(1)
                # Exclude known tokens (case-insensitive)
                if voice.lower() not in known_tokens:
                    voices.add(voice)
    
    return voices


def _normalize_station_name(name: str) -> str:
    """Normalize station name for comparison: strip markdown formatting."""
    # Remove backticks and asterisks
    name = name.strip("`").strip("*").strip()
    return name


_DESCRIPTIVE_PREFIXES = (
    "Built", "Tentative", "and ", "so ", "the ", "a ", "an ",
)


def _is_descriptive(line: str) -> bool:
    """True when a coverage line is prose rather than a station name."""
    stripped = line.strip()
    return (
        stripped.startswith(_DESCRIPTIVE_PREFIXES)
        or "deliberately excluded" in stripped
        or "sites with no pads" in stripped
    )


def _parse_station_list(text: str) -> Set[str]:
    """Split one coverage line on its separators and keep station-like names."""
    stations: Set[str] = set()
    for part in re.split(r"[·•,\n]", text):
        part = part.strip().strip("`").strip("*").strip()
        if part and len(part) > 2 and not part.lower().startswith(
            ("the ", "a ", "an ")
        ):
            stations.add(_normalize_station_name(part))
    return stations


def _starts_simple_station_list(stripped: str) -> bool:
    """True when a line without the header looks like the simple list format."""
    return (
        ("·" in stripped or "•" in stripped)
        and not stripped.startswith(("Built", "Tentative"))
        and "deliberately" not in stripped
    )


def _extract_stations_from_section_7(lines: List[str]) -> Set[str]:
    """Station names from section 7: a ``### Stations covered`` list or a simple one."""
    stations: Set[str] = set()
    in_station_list = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("###") and "Stations covered" in stripped:
            in_station_list = True
            continue
        if in_station_list and stripped.startswith("###"):
            break
        if in_station_list:
            if stripped and not _is_descriptive(stripped):
                stations |= _parse_station_list(stripped)
            continue
        if stripped and _starts_simple_station_list(stripped):
            in_station_list = True
            if not _is_descriptive(stripped):
                stations |= _parse_station_list(stripped)
    return stations


__all__ = [
    "_parse_dossier_sections",
    "_extract_site_table", 
    "_get_landable_build_types",
    "_extract_voices_from_section_8",
    "_normalize_station_name",
    "_is_descriptive",
    "_parse_station_list",
    "_starts_simple_station_list",
    "_extract_stations_from_section_7",
]