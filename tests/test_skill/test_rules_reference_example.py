"""Tests for the worked rules.toml example in ``references/rules.md``.

The example is the only worked per-system rules file the skill ships, so it has
to be valid on its own terms: it must parse, declare everything
``validate_definition`` requires of a rules payload (``system.names`` containing
the system name, a ``system.dossier`` string, ``system.voices`` matching the
dossier's section 8), and its prose must not drift from it. An example that
drifts sends an agent back into the error-driven loop the live run hit.
"""

import re
import tomllib
from pathlib import Path

import pytest

from edcg.rules.dossier import DOSSIER_SECTIONS
from edcg.rules.validation import validate_definition

SKILL_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "edcopilot-system-content"
)
RULES_MD = SKILL_DIR / "references" / "rules.md"
SECTION_TITLE = "## Authoring a system rules file"
BLOCK_RE = re.compile(r"```toml\n(.*?)```", re.DOTALL)
PROSE_VOICE_RE = re.compile(r"`([A-Z][A-Za-z]*)`")


def _section_text() -> str:
    """The "Authoring a system rules file" section, up to the next heading."""
    text = RULES_MD.read_text(encoding="utf-8")
    start = text.index(SECTION_TITLE)
    end = text.find("\n## ", start + len(SECTION_TITLE))
    assert end != -1, f"{SECTION_TITLE!r} is the last section; Bounds must follow"
    return text[start:end]


def _toml_text() -> str:
    block = BLOCK_RE.search(_section_text())
    assert block is not None, f"no ```toml block in {SECTION_TITLE!r}"
    return block.group(1)


def _example() -> dict:
    return tomllib.loads(_toml_text())


def _dossier_for(system: dict) -> str:
    """A dossier whose section 8 declares exactly the example's voices.

    The rules-side checks cross-reference section 8, so the example can only be
    proven against a dossier that names the same speakers. The spine, one
    landable site and its coverage entry make the rest of the pair valid, so a
    passing result proves the example itself rather than the fixture.
    """
    voices = " ".join(f"`[<{voice}>]`" for voice in system["voices"])
    lines = [f"# {system['names'][0]} — system dossier", ""]
    for number, title in enumerate(DOSSIER_SECTIONS, start=1):
        lines += [f"## {number}. {title}", ""]
        if number == 4:
            lines += [
                "### Complete (2)",
                "",
                "| Site | Build type | Body |",
                "|---|---|---|",
                "| Primary Station (AB-1) | `nona` Civilian Surface Outpost | `3 a` |",
                "| Secondary Station (AB-2) | `nona` Civilian Surface Outpost | `4 b` |",
                "",
            ]
        elif number == 7:
            lines += ["Primary Station (AB-1) · Secondary Station (AB-2)", ""]
        elif number == 8:
            lines += ["### Voices used", "", f"- **Crew:** {voices}", ""]
    return "\n".join(lines)


def _prose() -> str:
    """The section's prose: the TOML block removed, so voices are read twice."""
    return _section_text().replace(_toml_text(), "")


def test_worked_example_parses_and_satisfies_required_keys():
    system = _example()["system"]

    names = system.get("names")
    assert isinstance(names, list) and names, "system.names must be a non-empty list"
    assert all(isinstance(name, str) and name for name in names)

    dossier = system.get("dossier")
    assert isinstance(dossier, str) and dossier, "system.dossier must be a non-empty string"

    voices = system.get("voices")
    assert isinstance(voices, list) and voices, "system.voices must be a non-empty list"
    assert all(isinstance(voice, str) and voice for voice in voices)


def test_worked_example_passes_definition_validation():
    """The example is what the validator is run against, so it must pass it."""
    example = _example()
    system = example["system"]

    result = validate_definition(
        dossier=_dossier_for(system),
        rules=_toml_text(),
        system_name=system["names"][0],
    )

    assert result.passed, [f.message for f in result.findings]
    assert not [f for f in result.findings if f.severity == "error"]


def test_a_wrong_system_name_is_what_the_example_avoids():
    """The example only passes because ``names`` carries its system name."""
    example = _example()
    system = example["system"]

    result = validate_definition(
        dossier=_dossier_for(system),
        rules=_toml_text(),
        system_name="Some Other System",
    )

    assert not result.passed
    assert any(f.rule == "rules.system_names" for f in result.findings)


def test_example_voices_match_the_example_prose():
    """The prose names the voices in backticks; they must be the TOML's."""
    system = _example()["system"]
    voices = set(system["voices"])

    mentioned = set(PROSE_VOICE_RE.findall(_prose()))

    assert mentioned == voices, (
        f"prose names {sorted(mentioned)}, the TOML declares {sorted(voices)}"
    )


@pytest.mark.parametrize("voice", ["Foreman", "Quartermaster"])
def test_example_voice_names_are_one_token(voice):
    """``syntax.voice_name`` allows no spaces, so the example cannot show one."""
    system = _example()["system"]
    assert voice in system["voices"]
    assert " " not in voice


def test_the_section_carries_exactly_one_worked_example():
    """One example, so a second (drifting) block cannot hide behind the first."""
    assert len(BLOCK_RE.findall(_section_text())) == 1


def test_example_shows_a_station_bound_override():
    """The bound shape the Bounds section documents is demonstrated, not just named."""
    stations = _example().get("content", {}).get("bounds", {}).get("stations")
    assert isinstance(stations, dict) and stations, (
        'the example must show [content.bounds.stations."<station>"]'
    )
    for station, kinds in stations.items():
        assert station, "a station override needs a station name"
        assert kinds, f"station {station!r} overrides no tag kind"
        for kind, pair in kinds.items():
            assert isinstance(pair, list) and len(pair) == 2, (
                f"{station}/{kind} must be a [min, max] pair"
            )
            low, high = pair
            assert isinstance(low, int) and isinstance(high, int) and low <= high


def test_example_dossier_path_is_relative_to_the_content_root():
    dossier = _example()["system"]["dossier"]
    assert dossier.startswith("systems/")
    assert dossier.endswith(".md")
    assert "<" not in dossier and ">" not in dossier
