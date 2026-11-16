"""The release version is one string, not three that drift apart."""

from pathlib import Path

SKILL_MD = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "edcopilot-system-content"
    / "SKILL.md"
)


def _metadata_version() -> str:
    """Read ``metadata.version`` out of SKILL.md's YAML frontmatter."""
    lines = SKILL_MD.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---", "SKILL.md does not open with frontmatter"
    in_metadata = False
    for line in lines[1:]:
        if line == "---":
            break
        if line.rstrip() == "metadata:":
            in_metadata = True
            continue
        if in_metadata and line.startswith("  "):
            key, _, value = line.strip().partition(":")
            if key == "version":
                return value.strip().strip('"').strip("'")
        elif in_metadata and line and not line.startswith(" "):
            in_metadata = False
    raise AssertionError("SKILL.md frontmatter has no metadata.version")


def test_the_three_version_strings_are_aligned():
    from edcg import __version__
    from edcg.content.custom_file import VERSION

    metadata_version = _metadata_version()
    assert metadata_version == __version__ == VERSION == "1.0.0-alpha.3"
