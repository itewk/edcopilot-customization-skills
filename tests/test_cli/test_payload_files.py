"""File-path payload flags on the two definition commands.

A live dossier and its rules are too large to paste into a shell heredoc, so
``validate-definition`` and ``save-definition`` also accept ``--dossier-file``,
``--rules-file`` and (validate only) ``--all-rules-file``. The flags feed the
same JSON payload contract: relative paths resolve from the content root,
absolute paths are taken as given, files must be UTF-8, and a field may arrive
from stdin or from a file but never from both.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from edcg import cli
from support import run_git

DOSSIER = "# Test System\n\nDossier body.\n"
RULES = '[system]\nnames = ["Test System"]\n'
ALL_RULES = '[rules.content.station_landable]\nseverity = "error"\n'


def _run(argv, stdin=""):
    class _Stdin:
        def read(self):
            return stdin

    original = sys.stdin
    sys.stdin = _Stdin()
    try:
        return cli.main(argv)
    finally:
        sys.stdin = original


def _write(path: Path, text: str) -> Path:
    """Write exact bytes: Path.write_text would translate newlines on Windows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def _content_root(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "content"
    root.mkdir()
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(root))
    return root


def test_validate_definition_from_files_matches_the_stdin_payload(
    monkeypatch, tmp_path, capsys
):
    root = _content_root(monkeypatch, tmp_path)
    dossier = _write(root / "dossier.md", DOSSIER)
    rules = _write(root / "rules.toml", RULES)
    all_rules = _write(root / "all_rules.toml", ALL_RULES)
    system_name = {"system_name": "Test System"}

    flags_code = _run(
        [
            "validate-definition",
            "--dossier-file",
            str(dossier),
            "--rules-file",
            str(rules),
            "--all-rules-file",
            str(all_rules),
        ],
        stdin=json.dumps(system_name),
    )
    from_flags = json.loads(capsys.readouterr().out)

    stdin_code = _run(
        ["validate-definition"],
        stdin=json.dumps(
            {
                **system_name,
                "dossier": DOSSIER,
                "rules": RULES,
                "all_rules": ALL_RULES,
            }
        ),
    )
    from_stdin = json.loads(capsys.readouterr().out)

    assert (flags_code, from_flags) == (stdin_code, from_stdin)
    assert from_flags["passed"] is False
    assert from_flags["findings"]


def test_relative_path_resolves_from_content_root(monkeypatch, tmp_path, capsys):
    root = _content_root(monkeypatch, tmp_path)
    _write(root / "dossier.md", DOSSIER)
    _write(root / "rules.toml", RULES)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    code = _run(
        [
            "validate-definition",
            "--dossier-file",
            "dossier.md",
            "--rules-file",
            "rules.toml",
        ],
        stdin=json.dumps({"system_name": "Test System"}),
    )
    captured = capsys.readouterr()

    # Both files exist only under the content root, so a cwd-relative
    # resolution would have failed as a missing-file usage error.
    assert code != 2
    assert "could not read" not in captured.err
    assert json.loads(captured.out)["findings"]


def test_absolute_path_is_accepted_from_any_cwd(monkeypatch, tmp_path, capsys):
    _content_root(monkeypatch, tmp_path)
    outside = tmp_path / "outside"
    dossier = _write(outside / "dossier.md", DOSSIER)
    rules = _write(outside / "rules.toml", RULES)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    code = _run(
        [
            "validate-definition",
            "--dossier-file",
            str(dossier),
            "--rules-file",
            str(rules),
        ],
        stdin=json.dumps({"system_name": "Test System"}),
    )
    captured = capsys.readouterr()

    assert code != 2
    assert "could not read" not in captured.err
    assert json.loads(captured.out)["findings"]


@pytest.mark.parametrize(
    "command, option, field",
    [
        ("validate-definition", "--dossier-file", "dossier"),
        ("validate-definition", "--rules-file", "rules"),
        ("validate-definition", "--all-rules-file", "all_rules"),
        ("save-definition", "--dossier-file", "dossier_md"),
        ("save-definition", "--rules-file", "rules_toml"),
    ],
)
def test_flag_and_json_field_conflict_is_usage_error(
    monkeypatch, tmp_path, capsys, command, option, field
):
    _content_root(monkeypatch, tmp_path)
    payload = {"system_name": "Test System", field: "from stdin"}

    # The path does not exist: the conflict must be reported before any read.
    code = _run(
        [command, option, str(tmp_path / "never-read.txt")],
        stdin=json.dumps(payload),
    )
    captured = capsys.readouterr()

    assert code == 2
    assert f"'{field}'" in captured.err
    assert "given twice" in captured.err
    assert option in captured.err
    assert "could not read" not in captured.err
    assert "fix:" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_missing_files_are_one_aggregated_usage_error(
    monkeypatch, tmp_path, capsys
):
    _content_root(monkeypatch, tmp_path)

    code = _run(
        [
            "validate-definition",
            "--dossier-file",
            str(tmp_path / "no-dossier.md"),
            "--rules-file",
            str(tmp_path / "no-rules.toml"),
        ],
        stdin=json.dumps({"system_name": "Test System"}),
    )
    captured = capsys.readouterr()

    assert code == 2
    assert captured.err.count("error:") == 2  # both faults, one message
    assert "no-dossier.md" in captured.err
    assert "no-rules.toml" in captured.err
    assert "fix:" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_undecodable_file_is_usage_error(monkeypatch, tmp_path, capsys):
    root = _content_root(monkeypatch, tmp_path)
    bad = root / "dossier.md"
    bad.write_bytes(b"# Test System\n\xff\xfe broken\n")
    _write(root / "rules.toml", RULES)

    code = _run(
        ["validate-definition", "--dossier-file", str(bad), "--rules-file", "rules.toml"],
        stdin=json.dumps({"system_name": "Test System"}),
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "dossier" in captured.err
    assert "UTF-8" in captured.err
    assert "fix:" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_save_definition_maps_flags_to_md_toml_keys(
    monkeypatch, tmp_path, capsys, git_repo
):
    root = git_repo(files={"README.md": "# content\n"})
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(root))
    monkeypatch.setenv("EDCG_AUTO_COMMIT", "true")
    dossier = _write(tmp_path / "dossier.md", DOSSIER)
    rules = _write(tmp_path / "rules.toml", RULES)

    code = _run(
        [
            "save-definition",
            "--dossier-file",
            str(dossier),
            "--rules-file",
            str(rules),
        ],
        stdin=json.dumps(
            {
                "system_name": "Test System",
                "commit_co_author": "Test <test@example.com>",
            }
        ),
    )
    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert code == 0
    assert captured.err == ""
    assert len(result["commit_hash"]) == 8
    assert result["files_changed"] == [
        str(Path("systems") / "test-system.md"),
        str(Path("systems") / "test-system.rules.toml"),
    ]
    # The file contents are the flag payloads, not the stdin fields.
    assert (root / "systems" / "test-system.md").read_text(
        encoding="utf-8"
    ).replace("\r\n", "\n") == DOSSIER
    assert (root / "systems" / "test-system.rules.toml").read_text(
        encoding="utf-8"
    ).replace("\r\n", "\n") == RULES
    message = run_git(root, "log", "-1", "--format=%B")
    assert message.startswith("edcg: scaffold Test System")
    assert "Co-authored-by: Test <test@example.com>" in message
