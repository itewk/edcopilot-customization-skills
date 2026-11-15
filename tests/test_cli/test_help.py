"""Tests that ``--help`` is the interface documentation.

SKILL.md no longer carries a command table, so argparse is the only place an
agent learns a command's flags and payload shape. These tests keep that surface
honest: every argument has help text, the exit-code contract is printed, the
worked examples in the epilogs are real invocations the parser accepts, the
JSON blocks in them are not reflowed into one paragraph, and every documented
payload is type-valid against the command that reads it.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex

import pytest
from edcg import cli
from edcg.cli import build_parser

# Commands whose payload cannot be guessed from the flag names alone.
EXAMPLED_COMMANDS = [
    ["validate-definition"],
    ["save-definition"],
    ["write-content"],
    ["rewrite-tag"],
    ["markdb", "add"],
    ["markdb", "remove"],
    ["branch", "finalize"],
    ["branch", "abort"],
]

# What each command's worked example shows the caller. Pinned so that dropping
# or misspelling a documented key cannot slip through: `_require_fields` only
# walks the spec, so an absent optional key is invisible to it.
DOCUMENTED_KEYS = {
    "validate-definition": {"system_name", "dossier", "rules", "all_rules"},
    "save-definition": {
        "system_name",
        "dossier_md",
        "rules_toml",
        "commit_co_author",
    },
    "validate-content": {"system_name", "content"},
    "write-content": {"content_block", "system_name", "commit_co_author"},
    "rewrite-tag": {"system_name", "tag", "replace"},
}

STDIN_REDIRECT_RE = re.compile(r"\s<\s+\S+$")


def _all_parsers() -> list[argparse.ArgumentParser]:
    """The root parser and every nested subparser."""

    def walk(parser):
        yield parser
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for subparser in action.choices.values():
                    yield from walk(subparser)

    return list(walk(build_parser()))


def _parsers_with_epilog() -> list[argparse.ArgumentParser]:
    return [parser for parser in _all_parsers() if parser.epilog]


def _example_argvs() -> list[list[str]]:
    """Every ``python edcg.py ...`` line in an epilog, split into argv."""
    found: list[list[str]] = []
    for parser in _parsers_with_epilog():
        for line in parser.epilog.splitlines():
            line = line.strip()
            if not line.startswith("python edcg.py "):
                continue
            invocation = line[len("python edcg.py ") :]
            # Examples may show stdin redirection; only the arguments parse.
            invocation = STDIN_REDIRECT_RE.sub("", invocation)
            found.append(shlex.split(invocation))
    return found


def _json_example(parser: argparse.ArgumentParser) -> dict | None:
    """The first ``{ ... }`` block in *parser*'s epilog, parsed."""
    lines = parser.epilog.splitlines()
    for start, line in enumerate(lines):
        if line.strip() != "{":
            continue
        for end in range(start + 1, len(lines)):
            if lines[end].rstrip() == "}":
                block = "\n".join(lines[start : end + 1])
                return json.loads(block)
    return None


def _command_of(parser: argparse.ArgumentParser) -> str:
    """``edcg markdb add`` -> ``markdb add``."""
    return " ".join(parser.prog.split()[1:])


def test_every_argument_and_subcommand_has_help_text():
    for parser in _all_parsers():
        for action in parser._actions:
            assert action.help, f"{parser.prog}: {action.dest} has no help text"


def test_top_level_help_documents_the_exit_codes():
    help_text = build_parser().format_help()
    assert "Exit codes: 0 success, 1 check failure, 2 usage error." in help_text


def test_the_worked_examples_are_found():
    """A canary: an extractor regression must not make the checks vacuous."""
    assert len(_example_argvs()) >= len(EXAMPLED_COMMANDS)


@pytest.mark.parametrize("argv", _example_argvs(), ids=lambda argv: " ".join(argv))
def test_every_epilog_example_parses(argv):
    args = build_parser().parse_args(argv)
    assert args.command, f"example names no command: {' '.join(argv)}"


def test_the_stateful_commands_document_a_worked_example():
    argvs = _example_argvs()
    for head in EXAMPLED_COMMANDS:
        assert any(argv[: len(head)] == head for argv in argvs), (
            f"no worked example for {' '.join(head)}"
        )


def test_the_definition_commands_document_the_file_flags():
    seen = []
    for parser in _parsers_with_epilog():
        command = _command_of(parser)
        if command not in {"validate-definition", "save-definition"}:
            continue
        seen.append(command)
        help_text = parser.format_help()
        assert "--dossier-file" in help_text, f"{command} hides --dossier-file"
        assert "--rules-file" in help_text, f"{command} hides --rules-file"
        # Both invocation forms are shown: stdin-only and file flags.
        assert "< definition.json" in parser.epilog
        assert "< system_name.json" in parser.epilog
    # A vanished epilog must not turn this into a vacuous pass.
    assert sorted(seen) == ["save-definition", "validate-definition"]


def test_every_documented_payload_is_type_valid_for_its_command():
    """A drifted epilog example is a documented contract the CLI rejects."""
    # Every command with a payload spec must have a documented-key decision.
    assert set(DOCUMENTED_KEYS) == set(cli.PAYLOAD_SPECS)

    seen = []
    for parser in _parsers_with_epilog():
        command = _command_of(parser)
        if command not in cli.PAYLOAD_SPECS:
            continue
        seen.append(command)
        payload = _json_example(parser)
        assert payload is not None, f"{command} documents no JSON payload"
        spec = cli.PAYLOAD_SPECS[command]
        # Types of the keys it does show, plus required keys that must be there.
        cli._require_fields(payload, spec)
        # An unknown or misspelled key the command would silently ignore.
        assert set(payload) <= set(spec), (
            f"{command} documents keys the payload reader does not accept: "
            f"{sorted(set(payload) - set(spec))}"
        )
        # And a dropped optional key, which the type check above cannot see.
        assert set(payload) == DOCUMENTED_KEYS[command], (
            f"{command} no longer documents the payload it should: "
            f"missing {sorted(DOCUMENTED_KEYS[command] - set(payload))}, "
            f"unexpected {sorted(set(payload) - DOCUMENTED_KEYS[command])}"
        )
    assert sorted(seen) == sorted(DOCUMENTED_KEYS)


def test_json_epilog_blocks_are_not_reflowed():
    """Subparsers need RawDescriptionHelpFormatter or the block collapses."""
    parsers = [
        parser for parser in _parsers_with_epilog() if "{\n" in parser.epilog
    ]
    assert parsers, "no parser documents a JSON payload"
    for parser in parsers:
        assert "{\n" in parser.format_help(), f"{parser.prog} reflowed its JSON block"
