"""Structural tests for the skill's SKILL.md.

The old package served its instructions from Python prompt builders. The skill
serves the same instructions from markdown, so these tests assert the structure
the agent needs at discovery time: valid frontmatter, a body short enough to
load whole, the eight spine sections, working reference links, and a command
list that cannot drift from the CLI's registered subcommands.
"""

import argparse
import re
from pathlib import Path

import pytest

SKILL_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "edcopilot-system-content"
)
SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES = SKILL_DIR / "references"

EXPECTED_REFERENCES = [
    "new-system-interview.md",
    "update-interview.md",
    "writing-brief.md",
    "rules.md",
    "workflow-details.md",
]

# The eight spine sections, in order.
EXPECTED_SECTIONS = [
    "Setup",
    "Commands",
    "Resume rule",
    "New system",
    "Update an existing system",
    "Advisory gates",
    "Commit conventions",
    "Human gates",
]

# Built from fragments so the repository's own identity grep stays clean.
BANNED_STRINGS = [
    "mcp",
    "edcp" + "_cg_",
    "edcopilot" + "_customization" + "_generator",
]

COMMAND_RE = re.compile(
    r"`edcg\.py ([a-z][a-z-]*)"
    r"(?: (add|remove|start|status|review|finalize|abort))?`"
)
REFERENCE_LINK_RE = re.compile(r"\]\((references/[a-z-]+\.md)\)")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _frontmatter(text: str) -> tuple[dict, list[str]]:
    """Parse the simple YAML subset the frontmatter uses."""
    lines = text.splitlines()
    assert lines[0] == "---", "SKILL.md must open with a YAML frontmatter fence"
    end = lines.index("---", 1)
    data: dict = {}
    current = None
    for line in lines[1:end]:
        if not line.strip():
            continue
        if line.startswith((" ", "\t")):
            key, _, value = line.strip().partition(":")
            data.setdefault(current, {})[key.strip()] = _unquote(value)
            continue
        key, _, value = line.partition(":")
        current = key.strip()
        data[current] = _unquote(value) if value.strip() else {}
    return data, lines[end + 1 :]


def _body() -> tuple[dict, list[str]]:
    return _frontmatter(SKILL_MD.read_text(encoding="utf-8"))


def _registered_commands() -> set[str]:
    """Every command string the parser actually registers."""
    from edcg.cli import build_parser

    parser = build_parser()
    top = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ][0].choices

    commands = {name for name in top if name not in ("branch", "markdb")}
    for group in ("branch", "markdb"):
        nested = [
            action
            for action in top[group]._actions
            if isinstance(action, argparse._SubParsersAction)
        ][-1].choices
        commands |= {f"{group} {sub}" for sub in nested}
    return commands


def _documented_commands(body: str) -> set[str]:
    found = set()
    for match in COMMAND_RE.finditer(body):
        command = match.group(1)
        if match.group(2):
            command = f"{command} {match.group(2)}"
        found.add(command)
    return found


class TestFrontmatter:
    """The discovery surface: only the frontmatter is read before activation."""

    def test_frontmatter_has_the_pinned_fields(self):
        data, _ = _body()
        for field in ("name", "description", "license", "compatibility", "metadata"):
            assert field in data, f"missing frontmatter field: {field}"

    def test_name_matches_the_skill_folder(self):
        data, _ = _body()
        assert data["name"] == "edcopilot-system-content"
        assert data["name"] == SKILL_DIR.name

    def test_description_covers_both_workflows_and_activation_keywords(self):
        description = _body()[0]["description"].lower()
        assert "author" in description or "writing" in description
        assert "updat" in description
        for keyword in (
            "colonisation",
            "system",
            "station",
            "greeting",
            "chatter",
            "broadcast",
            "edcopilot",
            "elite dangerous",
            "speech extensions",
        ):
            assert keyword in description, f"description never mentions {keyword!r}"

    def test_license_is_gpl_3(self):
        assert _body()[0]["license"] == "GPL-3.0"

    def test_compatibility_names_the_runtime_requirements(self):
        compatibility = _body()[0]["compatibility"]
        assert compatibility == (
            "Requires Windows (EDCoPilot), Python 3.12+, the httpx and "
            "GitPython packages, and git"
        )
        assert len(compatibility) <= 500

    def test_metadata_carries_the_version(self):
        data, _ = _body()
        assert data["metadata"]["version"] == "1.0.0"


class TestBodyShape:
    """Progressive disclosure only works while the body stays small."""

    def test_body_is_under_500_lines(self):
        _, body = _body()
        assert len(body) < 500, f"SKILL.md body is {len(body)} lines"

    def test_body_has_the_eight_spine_sections_in_order(self):
        _, body = _body()
        headings = [
            line[3:].strip()
            for line in body
            if line.startswith("## ")
        ]
        assert headings == EXPECTED_SECTIONS

    def test_body_lists_the_five_reference_files(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        linked = REFERENCE_LINK_RE.findall(text)
        assert sorted(Path(path).name for path in linked) == sorted(EXPECTED_REFERENCES)

    def test_every_linked_reference_exists(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        for relative in REFERENCE_LINK_RE.findall(text):
            path = SKILL_DIR / relative
            assert path.is_file(), f"SKILL.md links to a missing file: {relative}"
            assert path.stat().st_size > 0

    def test_setup_mentions_doctor_before_init(self):
        _, body = _body()
        text = "\n".join(body)
        assert "edcg.py doctor" in text
        assert "edcg.py init" in text
        assert text.index("edcg.py doctor") < text.index("edcg.py init")
        assert "fix:" in text.lower()

    def test_setup_documents_the_content_root_and_blank_directory_flow(self):
        _, body = _body()
        text = "\n".join(body)
        assert "EDCG_CONTENT_DEFINITIONS_ROOT" in text
        assert "working directory" in text.lower()
        assert "isn't a content repository yet" in text.lower()
        assert "--no-git" in text

    def test_setup_names_the_edcopilot_root_override(self):
        _, body = _body()
        text = "\n".join(body)
        assert "EDCG_EDCOPILOT_ROOT" in text

    def test_resume_rule_audits_before_touching_content(self):
        _, body = _body()
        text = "\n".join(body)
        assert "edcg.py audit --system" in text
        assert "edcg.py update-scan" in text
        assert "the content repository is the state" in text.lower()

    def test_update_flow_names_update_scan_as_the_refresh_command(self):
        _, body = _body()
        text = "\n".join(body)
        assert "refresh command" in text.lower()
        assert "for one system or many" in text.lower()

    def test_commit_subjects_match_the_scripts(self):
        _, body = _body()
        text = "\n".join(body)
        assert "edcg: scaffold <system> - <summary>" in text
        assert "edcg: update <system> - <summary>" in text
        assert "edcg: markdb add <n> tag(s)" in text
        assert "edcg: markdb remove <n> tag(s)" in text

    def test_gate_state_is_derived_from_the_repository(self):
        _, body = _body()
        text = "\n".join(body)
        lowered = text.lower()
        assert "edcg.py branch status" in text
        assert "edcg.py get-content" in text
        assert "updatedb" in lowered
        assert "systems/" in text
        assert "audit-derived" not in lowered


class TestCommandList:
    """The documented command list and the parser must not drift apart."""

    def test_every_documented_command_is_registered(self):
        _, body = _body()
        documented = _documented_commands("\n".join(body))
        assert documented, "SKILL.md documents no edcg.py commands"
        assert documented == _registered_commands()

    def test_command_table_has_no_invented_commands(self):
        _, body = _body()
        documented = _documented_commands("\n".join(body))
        extra = documented - _registered_commands()
        assert not extra, f"SKILL.md invents commands: {sorted(extra)}"

    def test_every_registered_command_is_documented(self):
        _, body = _body()
        documented = _documented_commands("\n".join(body))
        missing = _registered_commands() - documented
        assert not missing, f"SKILL.md omits commands: {sorted(missing)}"


class TestProductIdentity:
    """The skill must read as a standalone product."""

    @pytest.mark.parametrize(
        "path",
        [pytest.param(SKILL_MD, id="SKILL.md")]
        + [pytest.param(REFERENCES / name, id=name) for name in EXPECTED_REFERENCES],
    )
    def test_no_prior_product_identity_strings(self, path: Path):
        assert path.is_file(), f"missing file: {path}"
        lowered = path.read_text(encoding="utf-8").lower()
        for banned in BANNED_STRINGS:
            assert banned not in lowered, f"{path.name} mentions {banned!r}"
