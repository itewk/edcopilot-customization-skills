"""Tests for documentation accuracy."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"
UPDATE_INTERVIEW = (
    REPO_ROOT
    / "skills"
    / "edcopilot-system-content"
    / "references"
    / "update-interview.md"
)

# A count of three or more digits sitting within a short distance of "passed"
# is a hardcoded suite total that rots the moment a test is added.
HARDCODED_COUNT = r"\b\d[\d,]{2,}\b[^\n]{0,20}\bpassed\b"


def test_contributing_has_no_hardcoded_suite_counts():
    """Verify CONTRIBUTING.md doesn't contain hardcoded suite counts that rot."""
    content = CONTRIBUTING.read_text(encoding="utf-8")

    matches = re.findall(HARDCODED_COUNT, content)
    assert not matches, f"Found hardcoded suite counts in CONTRIBUTING.md: {matches}"


def test_update_interview_has_correct_error_taxonomy():
    """Verify update-interview.md has the complete error taxonomy."""
    content = UPDATE_INTERVIEW.read_text(encoding="utf-8")

    # Should contain all three error causes
    assert "unparsable rules; rules declare no system name; failed fact gathering" in content
