"""Payload type validation: every fault is aggregated into one usage diagnosis.

Each of the five stdin commands reads a JSON object and hands it to
``_require_fields`` before touching the domain layer. Missing required fields
and wrong-typed fields are usage errors: exit 2, one ``error:``/``fix:`` pair
per fault on stderr, nothing on stdout, and no traceback.
"""

import io
import json
from unittest.mock import patch

from edcg import cli


def test_dossier_as_object_aggregates_faults(capsys):
    # The live-run trap: {"system_name": {...}} and a nested dossier object.
    payload = {"system_name": {"a": 1}, "dossier": {"x": 1}, "rules": "x"}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["validate-definition"])
    assert code == 2
    captured = capsys.readouterr()
    assert "system_name" in captured.err and "dossier" in captured.err
    assert captured.err.count("error:") == 2  # both faults, one message
    assert "fix:" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_save_definition_reports_every_missing_field(capsys):
    # `rules` is not a save-definition field: it is ignored, and the three
    # required fields are reported in one message.
    payload = {"rules": 5}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["save-definition"])
    assert code == 2
    captured = capsys.readouterr()
    assert "system_name" in captured.err
    assert "dossier_md" in captured.err
    assert "rules_toml" in captured.err
    assert captured.err.count("error:") == 3
    assert captured.out == ""


def test_valid_payload_still_reaches_validation(capsys):
    # A well-formed but invalid definition exits 1 with findings, NOT 2.
    payload = {"system_name": "X", "dossier": "# X\n", "rules": "[system]\n"}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["validate-definition"])
    captured = capsys.readouterr()
    assert code == 1
    assert json.loads(captured.out)["passed"] is False
    assert captured.err == ""


def test_save_definition_wrong_type(capsys):
    payload = {"system_name": "X", "dossier_md": {}, "rules_toml": None}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["save-definition"])
    assert code == 2
    captured = capsys.readouterr()
    assert "dossier_md" in captured.err and "rules_toml" in captured.err
    assert captured.err.count("error:") == 2
    assert captured.out == ""


def test_validate_content_wrong_type(capsys):
    payload = {"system_name": "X", "content": 3}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["validate-content"])
    assert code == 2
    captured = capsys.readouterr()
    assert "content" in captured.err
    assert captured.err.count("error:") == 1
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_write_content_wrong_type(capsys):
    # content_block reaches custom_file.write_content, which calls .strip():
    # a nested object there was an AttributeError traceback before the guard.
    payload = {"system_name": "S", "content_block": {"a": 1}}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["write-content"])
    assert code == 2
    captured = capsys.readouterr()
    assert "content_block" in captured.err
    assert "must be a str" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_write_content_optional_model_must_be_a_string(capsys):
    # `model` is optional, but its type is checked when present.
    payload = {"system_name": "S", "content_block": "", "model": 5}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["write-content"])
    assert code == 2
    captured = capsys.readouterr()
    assert "model" in captured.err
    assert "must be a str" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_write_content_content_block_may_be_absent(
    monkeypatch, tmp_path, capsys
):
    # Omitting content_block is the documented flow for committing edits that
    # are already staged in the runtime repo; only a wrong type is a fault
    # (see test_write_content_wrong_type above).
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(runtime))
    monkeypatch.setenv("EDCG_AUTO_COMMIT", "false")
    # The definition gate is satisfied, so this test keeps judging the payload
    # rule it was written for rather than the prerequisite.
    systems = tmp_path / "systems"
    systems.mkdir()
    (systems / "s.md").write_text("# S\n", encoding="utf-8")
    (systems / "s.rules.toml").write_text(
        '[system]\nnames = ["S"]\ndossier = "s.md"\n', encoding="utf-8"
    )
    payload = {"system_name": "S"}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["write-content"])
    captured = capsys.readouterr()
    assert code == 0
    assert "required field" not in captured.err
    assert "Traceback" not in captured.err
    assert json.loads(captured.out)["commit_hash"] is None


def test_save_definition_optional_commit_co_author_must_be_a_string(capsys):
    # commit_co_author is optional, but a non-string would reach git as a
    # trailer value, so its type is checked when present.
    payload = {
        "system_name": "X",
        "dossier_md": "# X\n",
        "rules_toml": "[system]\n",
        "commit_co_author": ["harness", "model"],
    }
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["save-definition"])
    assert code == 2
    captured = capsys.readouterr()
    assert "commit_co_author" in captured.err
    assert "must be a str" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_rewrite_tag_wrong_type(capsys):
    payload = {"system_name": "X", "tag": ["a"]}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["rewrite-tag"])
    assert code == 2
    captured = capsys.readouterr()
    assert "tag" in captured.err
    assert captured.err.count("error:") == 1
    assert captured.out == ""


def test_rewrite_tag_optional_remove_must_be_a_list(capsys):
    # `remove` is optional, but its type is checked when present.
    payload = {"system_name": "X", "tag": "@T", "remove": "not-a-list"}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["rewrite-tag"])
    assert code == 2
    captured = capsys.readouterr()
    assert "remove" in captured.err
    assert "must be a list" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_rewrite_tag_optional_fields_may_be_absent(capsys, clean_env):
    # Absence of remove/replace/add is not a usage fault: the call gets past
    # the payload reader to repository resolution.
    payload = {"system_name": "X", "tag": "@SystemGreeting<~>X"}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["rewrite-tag"])
    captured = capsys.readouterr()
    assert "required field" not in captured.err
    assert "Traceback" not in captured.err
    assert code != 2


def test_validate_definition_wrong_type(capsys):
    payload = {"system_name": 1}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["validate-definition"])
    assert code == 2
    captured = capsys.readouterr()
    assert "system_name" in captured.err
    assert captured.err.count("error:") == 3  # the other two required fields too


def test_validate_definition_all_rules_must_be_a_string(capsys):
    # all_rules is TOML text, not a list: a list reached tomllib.loads and
    # raised TypeError once section 7 made the all-rules check run.
    payload = {
        "system_name": "X",
        "dossier": "# X\n",
        "rules": "[system]\n",
        "all_rules": ["rule1", "rule2"],
    }
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["validate-definition"])
    assert code == 2
    captured = capsys.readouterr()
    assert "all_rules" in captured.err
    assert "must be a str" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""
