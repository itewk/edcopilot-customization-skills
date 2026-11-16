"""The definition prerequisite and the human override (G2, G3, D6).

Five commands are gated: ``writing-brief-data``, ``validate-content``,
``write-content``, ``rewrite-tag`` and ``markdb`` (add and remove). Without a
saved definition each refuses with exit 1 and the three-part message, before it
writes anything. ``--allow-no-definition`` lifts the gate, and the skip is made
audible by a ``warning:`` block on stderr: the transcript is the record.

``markdb`` has no system field, so its systems come from the tag lines: the
field the kind's ``parts`` declares as the system (index 0 for every shipped
kind today; a test drives a reordered kind). A systemless tag is exempt: a
marker must never be stranded.
"""

from __future__ import annotations

import argparse
import json
import sys

import pytest

from edcg import cli
from edcg.common.layout import CUSTOM_FILE_NAME
from edcg.repo.sequencing import (
    CONSEQUENCES,
    SKIP_FLAG,
    refusal_message,
    tag_systems,
)
from edcg.rules.validation import Kind

NAME = "Test System"

REFUSAL_PARTS = (
    f"no definition saved for {NAME} - run the interview, then "
    "validate-definition and save-definition",
    "without a definition there are no bounds, voices or tag lines - content "
    "will be written blind, validation will be weak, and EDCoPilot coverage "
    "cannot be verified",
    "if the human chooses to skip this prerequisite, re-run with "
    "--allow-no-definition",
)


def _run(argv, stdin=None):
    """Run the CLI in-process, optionally with *stdin* text."""
    if stdin is None:
        return cli.main(argv)

    class _Stdin:
        def read(self):
            return stdin

    original = sys.stdin
    sys.stdin = _Stdin()
    try:
        return cli.main(argv)
    finally:
        sys.stdin = original


def _payload(data: dict) -> str:
    return json.dumps(data)


def _define(root, name: str = NAME) -> None:
    """Write the dossier and rules pair that makes *name* defined."""
    slug = name.lower().replace(" ", "-")
    systems = root / "systems"
    systems.mkdir(parents=True, exist_ok=True)
    (systems / f"{slug}.md").write_text(
        f"# {name} — system dossier\n", encoding="utf-8"
    )
    (systems / f"{slug}.rules.toml").write_text(
        f'[system]\nnames = ["{name}"]\ndossier = "{slug}.md"\n'
        'voices = ["PortAuthority"]\n',
        encoding="utf-8",
    )


def _environment(monkeypatch, tmp_path, custom_text: str | None = None):
    """A content root, an EDCoPilot runtime root, and no automatic commits."""
    runtime = tmp_path / "runtime"
    runtime.mkdir(exist_ok=True)
    if custom_text is not None:
        (runtime / CUSTOM_FILE_NAME).write_text(custom_text, encoding="utf-8")
    monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(tmp_path))
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(runtime))
    monkeypatch.setenv("EDCG_AUTO_COMMIT", "false")
    return runtime


def _snapshot(root):
    """Every file under *root* with its bytes, for a no-partial-write check."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _error(capsys) -> dict:
    """The failure payload, pinned to the error object alone."""
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"error"}
    return payload


def _custom(runtime) -> str:
    return (runtime / CUSTOM_FILE_NAME).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _isolated(clean_env):
    """Run every test from an empty cwd with no inherited roots."""
    return clean_env


# ---------------------------------------------------------------------------
# The message, single-homed
# ---------------------------------------------------------------------------


def test_refusal_message_pins_the_three_parts():
    """One string, three parts: prerequisite and fix, consequences, override."""
    assert refusal_message(NAME) == "\n".join(REFUSAL_PARTS)


def test_consequences_are_the_spec_wording():
    assert CONSEQUENCES == REFUSAL_PARTS[1]


def test_the_override_flag_name_is_the_documented_one():
    assert SKIP_FLAG == "--allow-no-definition"


# ---------------------------------------------------------------------------
# writing-brief-data
# ---------------------------------------------------------------------------


def test_writing_brief_data_refuses_without_a_definition(monkeypatch, tmp_path, capsys):
    _environment(monkeypatch, tmp_path)
    before = _snapshot(tmp_path)

    assert cli.main(["writing-brief-data", "--system", NAME]) == 1

    error = _error(capsys)["error"]
    for part in REFUSAL_PARTS:
        assert part in error
    assert _snapshot(tmp_path) == before


def test_writing_brief_data_proceeds_when_the_human_allows_the_skip(
    monkeypatch, tmp_path, capsys
):
    """The gate is lifted; the command's own requirement still applies."""
    _environment(monkeypatch, tmp_path)

    assert cli.main(
        ["writing-brief-data", "--system", NAME, "--allow-no-definition"]
    ) == 1

    captured = capsys.readouterr()
    error = json.loads(captured.out)["error"]
    assert "no definition saved for" not in error
    assert "not found" in error
    assert "warning:" in captured.err
    assert CONSEQUENCES in captured.err
    assert NAME in captured.err


@pytest.mark.parametrize("present", ["dossier", "rules"])
def test_writing_brief_data_refuses_on_half_a_definition(
    present, monkeypatch, tmp_path, capsys
):
    """A definition is the pair: either file alone must not open the gate."""
    _environment(monkeypatch, tmp_path)
    systems = tmp_path / "systems"
    systems.mkdir()
    if present == "dossier":
        (systems / "test-system.md").write_text("# Test System\n", encoding="utf-8")
    else:
        (systems / "test-system.rules.toml").write_text(
            '[system]\nnames = ["Test System"]\n', encoding="utf-8"
        )

    assert cli.main(["writing-brief-data", "--system", NAME]) == 1

    error = _error(capsys)["error"]
    for part in REFUSAL_PARTS:
        assert part in error


# ---------------------------------------------------------------------------
# validate-content
# ---------------------------------------------------------------------------


def test_validate_content_refuses_without_a_definition(monkeypatch, tmp_path, capsys):
    _environment(monkeypatch, tmp_path)
    before = _snapshot(tmp_path)

    code = _run(
        ["validate-content"],
        stdin=_payload({"system_name": NAME, "content": f"@SystemGreeting<~>{NAME}\nHi.\n"}),
    )

    assert code == 1
    error = _error(capsys)["error"]
    for part in REFUSAL_PARTS:
        assert part in error
    assert _snapshot(tmp_path) == before


def test_validate_content_proceeds_when_the_human_allows_the_skip(
    monkeypatch, tmp_path, capsys
):
    _environment(monkeypatch, tmp_path)

    code = _run(
        ["validate-content", "--allow-no-definition"],
        stdin=_payload({"system_name": NAME, "content": f"@SystemGreeting<~>{NAME}\nHi.\n"}),
    )

    captured = capsys.readouterr()
    assert code in (0, 1)  # a validation verdict, not a sequencing refusal
    assert set(json.loads(captured.out)) == {"passed", "findings", "rule_summary"}
    assert "warning:" in captured.err
    assert CONSEQUENCES in captured.err


# ---------------------------------------------------------------------------
# write-content
# ---------------------------------------------------------------------------


def test_write_content_refuses_without_a_definition(monkeypatch, tmp_path, capsys):
    runtime = _environment(monkeypatch, tmp_path)

    code = _run(
        ["write-content"],
        stdin=_payload(
            {"system_name": NAME, "content_block": f"@SystemGreeting<~>{NAME}\nHi.\n"}
        ),
    )

    assert code == 1
    error = _error(capsys)["error"]
    assert error == refusal_message(NAME)
    assert not (runtime / CUSTOM_FILE_NAME).exists()


def test_write_content_proceeds_when_the_human_allows_the_skip(
    monkeypatch, tmp_path, capsys
):
    runtime = _environment(monkeypatch, tmp_path)

    code = _run(
        ["write-content", "--allow-no-definition"],
        stdin=_payload(
            {"system_name": NAME, "content_block": f"@SystemGreeting<~>{NAME}\nHi.\n"}
        ),
    )

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["commit_hash"] is None
    assert "warning:" in captured.err
    assert CONSEQUENCES in captured.err
    assert f"@SystemGreeting<~>{NAME}" in _custom(runtime)


# ---------------------------------------------------------------------------
# rewrite-tag
# ---------------------------------------------------------------------------


def test_rewrite_tag_refuses_without_a_definition(monkeypatch, tmp_path, capsys):
    tag = f"@SystemGreeting<~>{NAME}"
    runtime = _environment(monkeypatch, tmp_path, f"{tag}\nHello.\n")

    code = _run(
        ["rewrite-tag"],
        stdin=_payload({"system_name": NAME, "tag": tag, "replace": {"Hello.": "Hi."}}),
    )

    assert code == 1
    error = _error(capsys)["error"]
    for part in REFUSAL_PARTS:
        assert part in error
    assert "Hello." in _custom(runtime)
    assert "Hi." not in _custom(runtime)


def test_rewrite_tag_proceeds_when_the_human_allows_the_skip(
    monkeypatch, tmp_path, capsys
):
    tag = f"@SystemGreeting<~>{NAME}"
    runtime = _environment(monkeypatch, tmp_path, f"{tag}\nHello.\n")

    code = _run(
        ["rewrite-tag", "--allow-no-definition"],
        stdin=_payload({"system_name": NAME, "tag": tag, "replace": {"Hello.": "Hi."}}),
    )

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["tag"] == tag
    assert "warning:" in captured.err
    assert CONSEQUENCES in captured.err
    assert "Hi." in _custom(runtime)


# ---------------------------------------------------------------------------
# markdb
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["add", "remove"])
def test_markdb_refuses_without_a_definition(
    action, monkeypatch, tmp_path, capsys
):
    tag = f"@SystemGreeting<~>{NAME}"
    text = f"{tag}\nUPDATEDB\nHello.\n" if action == "remove" else f"{tag}\nHello.\n"
    runtime = _environment(monkeypatch, tmp_path, text)

    assert cli.main(["markdb", action, "--tag", tag]) == 1

    error = _error(capsys)["error"]
    for part in REFUSAL_PARTS:
        assert part in error
    assert _custom(runtime) == text


def test_markdb_proceeds_when_the_human_allows_the_skip(
    monkeypatch, tmp_path, capsys
):
    tag = f"@SystemGreeting<~>{NAME}"
    runtime = _environment(monkeypatch, tmp_path, f"{tag}\nHello.\n")

    assert cli.main(["markdb", "add", "--tag", tag, "--allow-no-definition"]) == 0

    captured = capsys.readouterr()
    assert "warning:" in captured.err
    assert CONSEQUENCES in captured.err
    assert _custom(runtime).splitlines()[:2] == [tag, "UPDATEDB"]


def test_markdb_gates_the_json_payload_path(monkeypatch, tmp_path, capsys):
    """The gate is not a flag-parsing side effect: stdin tags are gated too."""
    tag = f"@SystemGreeting<~>{NAME}"
    text = f"{tag}\nHello.\n"
    runtime = _environment(monkeypatch, tmp_path, text)

    assert _run(["markdb", "add"], stdin=_payload({"tags": [tag]})) == 1

    error = _error(capsys)["error"]
    assert f"no definition saved for {NAME}" in error
    assert _custom(runtime) == text


def test_markdb_with_a_defined_system_needs_no_override(
    monkeypatch, tmp_path, capsys
):
    tag = f"@SystemGreeting<~>{NAME}"
    runtime = _environment(monkeypatch, tmp_path, f"{tag}\nHello.\n")
    _define(tmp_path)

    assert cli.main(["markdb", "add", "--tag", tag]) == 0

    captured = capsys.readouterr()
    assert "warning:" not in captured.err
    assert _custom(runtime).splitlines()[:2] == [tag, "UPDATEDB"]


@pytest.mark.parametrize(
    "tag",
    [
        "@ConfirmedCommander",
        "@CoPilotStarting",
        "@RandomShipName",
        "@NotAKnownKind<~>Anywhere",
    ],
)
def test_markdb_systemless_tags_never_strand(
    tag, monkeypatch, tmp_path, capsys
):
    """A kind with no system part is exempt: the marker still lands."""
    runtime = _environment(monkeypatch, tmp_path, f"{tag}\nHello.\n")

    assert cli.main(["markdb", "add", "--tag", tag]) == 0

    captured = capsys.readouterr()
    assert "no definition saved for" not in captured.out
    assert "warning:" not in captured.err
    assert _custom(runtime).splitlines()[:2] == [tag, "UPDATEDB"]


def test_markdb_mixed_call_refuses_naming_the_undefined_system(
    monkeypatch, tmp_path, capsys
):
    """One defined system and one undefined: the undefined one is named."""
    defined = "@StationGreeting<~>Alpha<~>Alpha Station"
    undefined = "@SystemGreeting<~>Beta"
    text = f"{defined}\nHello.\n\n{undefined}\nHi.\n"
    runtime = _environment(monkeypatch, tmp_path, text)
    _define(tmp_path, "Alpha")

    assert cli.main(["markdb", "add", "--tag", defined, "--tag", undefined]) == 1

    error = _error(capsys)["error"]
    assert "no definition saved for Beta" in error
    assert "Alpha" not in error
    assert _custom(runtime) == text
    assert "UPDATEDB" not in _custom(runtime)


def test_tag_systems_derives_the_field_the_kind_declares():
    assert tag_systems(
        [
            "@SystemGreeting<~>Alpha",
            "@StationChatter<~>Beta<~>Beta Station",
            "@ConfirmedCommander",
            "@NotAKnownKind<~>Gamma",
            "not a tag",
        ]
    ) == ["Alpha", "Beta"]


def test_tag_systems_reads_the_index_the_kind_declares():
    """[kinds] owns the field order, so a reordered kind still derives right."""
    kinds = {"OddKind": Kind(parts=("station", "system"))}

    assert tag_systems(["@OddKind<~>Nowhere Station<~>Gamma"], kinds) == ["Gamma"]


# ---------------------------------------------------------------------------
# Help-as-interface-doc
# ---------------------------------------------------------------------------

GATED_ARGVS = [
    ["writing-brief-data"],
    ["validate-content"],
    ["write-content"],
    ["rewrite-tag"],
    ["markdb", "add"],
    ["markdb", "remove"],
]


@pytest.mark.parametrize("argv", GATED_ARGVS, ids=lambda argv: " ".join(argv))
def test_the_gated_commands_document_the_override_flag(argv):
    parser = _gated_parser(argv)

    help_text = " ".join(parser.format_help().split())
    assert "--allow-no-definition" in help_text
    assert "human has chosen to skip the definition prerequisite" in help_text
    # The examples still show the ordinary form: the flag is not the default.
    assert "--allow-no-definition" not in (parser.epilog or "")


@pytest.mark.parametrize("argv", [["gather-facts"], ["audit"]], ids=lambda a: a[0])
def test_probe_commands_gain_no_override(argv):
    """D3's scope: probes never refuse, so they have nothing to override."""
    help_text = _gated_parser(argv).format_help()
    assert "--allow-no-definition" not in help_text


def _gated_parser(argv):
    current = cli.build_parser()
    for token in argv:
        subparsers = [
            action
            for action in current._actions
            if isinstance(action, argparse._SubParsersAction)
        ]
        current = subparsers[0].choices[token]
    return current
