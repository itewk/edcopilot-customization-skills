import json
import pytest
import sys
import io
import contextlib
from unittest.mock import patch
from pathlib import Path
from edcg import cli

def _run(argv, stdin=None):
    if stdin is None:
        return cli.main(argv)

    class _Stdin:
        def read(self):
            return stdin
        def readline(self):
            return self.read() + "\n"
        def readlines(self):
            return [self.read()]

    original = sys.stdin
    sys.stdin = _Stdin()
    try:
        return cli.main(argv)
    finally:
        sys.stdin = original

def test_dossier_as_object_aggregates_faults(capsys):
    # The live-run trap: {"system_name": {...}} and nested dossier object.
    payload = {"system_name": {"a": 1}, "dossier": {"x": 1}, "rules": "x"}
    
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["validate-definition"])
            
    assert code == 2
    captured = capsys.readouterr()
    assert "system_name" in captured.err and "dossier" in captured.err   # both faults, one message
    assert "fix:" in captured.err
    assert captured.out == ""

def test_missing_and_wrong_type_in_one_message(capsys):
    # The test in brief expects 2 faults for save-definition
    payload = {"rules": 5}
    
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["save-definition"])
            
    assert code == 2
    captured = capsys.readouterr()
    assert "system_name" in captured.err and "dossier_md" in captured.err and "rules_toml" in captured.err
    assert captured.out == ""

def test_valid_payload_still_reaches_validation(capsys):
    payload = {"system_name": "X", "dossier": "# X\n", "rules": "[system]\n"}
    
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["validate-definition"])
            
    assert code in (0, 1)

def test_save_definition_wrong_type(capsys):
    payload = {"system_name": "X", "dossier_md": {}, "rules_toml": None}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["save-definition"])
    assert code == 2
    captured = capsys.readouterr()
    assert "dossier_md" in captured.err and "rules_toml" in captured.err

def test_validate_content_wrong_type(capsys):
    payload = {"system_name": "X", "content": 3}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["validate-content"])
    assert code == 2
    captured = capsys.readouterr()
    assert "content" in captured.err

def test_write_content_wrong_type(capsys):
    payload = {"system_name": None}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["write-content"])
    assert code == 2
    captured = capsys.readouterr()
    assert "system_name" in captured.err

def test_rewrite_tag_wrong_type(capsys):
    payload = {"system_name": "X", "tag": ["a"]}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["rewrite-tag"])
    assert code == 2
    captured = capsys.readouterr()
    assert "tag" in captured.err

def test_validate_definition_wrong_type(capsys):
    payload = {"system_name": 1}
    with patch("sys.stdin", io.StringIO(json.dumps(payload))):
        code = cli.main(["validate-definition"])
    assert code == 2
    captured = capsys.readouterr()
    assert "system_name" in captured.err
