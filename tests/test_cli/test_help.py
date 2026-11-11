"""Tests that ``--help`` is the interface documentation.

SKILL.md no longer carries a command table, so argparse is the only place an
agent learns a command's flags and payload shape. These tests keep that surface
honest: every argument has help text, the exit-code contract is printed, the
worked examples in the epilogs are real invocations the parser accepts, and the
JSON blocks in them are not reflowed into one paragraph.
"""

from __future__ import annotations

import argparse
import re
import shlex

import pytest
from edcg.cli import build_parser

# Commands whose payload cannot be guessed from the flag names alone.
EXAMPLED_COMMANDS = [
    ["save-definition"],
    ["write-content"],
    ["rewrite-tag"],
    ["markdb", "add"],
    ["markdb", "remove"],
    ["branch", "finalize"],
    ["branch", "abort"],
]

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


def test_json_epilog_blocks_are_not_reflowed():
    """Subparsers need RawDescriptionHelpFormatter or the block collapses."""
    parsers = [
        parser for parser in _parsers_with_epilog() if "{\n" in parser.epilog
    ]
    assert parsers, "no parser documents a JSON payload"
    for parser in parsers:
        assert "{\n" in parser.format_help(), f"{parser.prog} reflowed its JSON block"
