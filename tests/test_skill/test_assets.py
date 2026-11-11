"""Guards for the assets the skill ships to every new user.

``init`` creates only the skeleton (the config file and ``systems/``); the agent
copies ``all.rules.toml.example`` into the content repository during setup, and
the dossier template is what the agent starts from, so both must be neutral. An
author's own name, domain or first-person voice baked into either file becomes
every user's default.
"""

import re
from pathlib import Path

SKILL_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "edcopilot-system-content"
)

IDENTITY_RE = re.compile(r"ii-?42|skyrunner42|skyrunner", re.IGNORECASE)
FIRST_PERSON_RE = re.compile(r"\bI\b|\bmy\b|\bI'm\b")


def _text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


def test_no_author_identity_strings_ship_in_the_skill():
    """The author's identity must not ship in any skill file, assets included."""
    hits = [
        str(path.relative_to(SKILL_DIR))
        for path, text in _text_files(SKILL_DIR)
        if IDENTITY_RE.search(text)
    ]
    assert hits == [], f"author identity leaked into: {hits}"


def test_house_rules_example_is_not_first_person():
    """The example ships as the user's starting point, not the author's diary."""
    text = (SKILL_DIR / "assets" / "all.rules.toml.example").read_text(
        encoding="utf-8"
    )
    assert FIRST_PERSON_RE.findall(text) == []
