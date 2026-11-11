from pathlib import Path

from edcg.rules.validation import validate_content

# The rule assets ship beside the skill's scripts/ directory.
BASE = Path(__file__).resolve().parents[2] / "skills" / "edcopilot-system-content" / "assets" / "base.toml"
SYSTEM = "Test System"

VALID = """<!-- provenance: tool=test model=test -->
@SystemGreeting<~>Test System
UPDATEDB
(allbusiness)Line one.
Unfiltered line two.
Line three.
"""


def _result(text: str, systems_dir: Path):
    return validate_content(text, SYSTEM, base_rules_path=BASE, systems_dir=systems_dir)


def test_rule_summary_has_a_pass_row_for_a_clean_rule(tmp_path):
    rows = {r["rule"]: r for r in _result(VALID, tmp_path).rule_summary}
    assert rows["syntax.voice_name"]["status"] == "pass"
    assert rows["syntax.voice_name"]["findings"] == 0


def test_rule_summary_marks_an_error_and_counts_findings(tmp_path):
    bad = VALID.replace("Line three.\n", "")
    rows = {r["rule"]: r for r in _result(bad, tmp_path).rule_summary}
    assert rows["content.bounds"]["status"] == "error"
    assert rows["content.bounds"]["findings"] == 1


def test_policy_rules_are_manual_not_pass(tmp_path):
    rows = {r["rule"]: r for r in _result(VALID, tmp_path).rule_summary}
    policies = [r for r in rows.values() if r["status"] == "manual"]
    assert policies
    assert all(r["rule"].startswith("filters.") for r in policies)


def test_rule_table_contains_symbols_and_both_tables(tmp_path):
    table = _result(VALID, tmp_path).rule_table
    assert "✅" in table
    assert "Policy rules (confirm manually)" in table
