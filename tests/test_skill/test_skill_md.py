"""Structural tests for the skill's SKILL.md.

The old package served its instructions from Python prompt builders. The skill
serves the same instructions from markdown, so these tests assert the structure
the agent needs at discovery time: valid frontmatter, a body short enough to
load whole, the eight spine sections, working reference links, and the commands
the Process steps name inline that cannot drift from the CLI's registered
subcommands (`--help` is the interface documentation, so there is no table).
"""

import argparse
import functools
import re
from pathlib import Path

import pytest

SKILL_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "edcopilot-system-content"
)
SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES = SKILL_DIR / "references"

EXPECTED_REFERENCES = [
    "new-system-interview.md",
    "update-interview.md",
    "writing-brief.md",
    "rules.md",
    "workflow-details.md",
]

# The eight spine sections, in order.
EXPECTED_SECTIONS = [
    "Setup",
    "Process",
    "Resume rule",
    "New system",
    "Update an existing system",
    "Advisory gates",
    "Commit conventions",
    "Human gates",
]

# Built from fragments so the repository's own identity grep stays clean.
BANNED_STRINGS = [
    "mcp",
    "edcp" + "_cg_",
    "edcopilot" + "_customization" + "_generator",
]

COMMAND_TOKEN_RE = re.compile(r"edcg\.py\s+([a-z][a-z-]*)(?:\s+([a-z][a-z-]*))?")
# Nested groups whose second token is a subcommand, not a flag argument.
SUBCOMMAND_GROUPS = {"branch", "markdb"}
STEP_RE = re.compile(r"^\d+\.\s+")
SECTION_RE = re.compile(r"^#{1,6} ")
BACKTICK_SPAN_RE = re.compile(r"`([^`\n]*)`")
REFERENCE_LINK_RE = re.compile(r"\]\((references/[a-z-]+\.md)\)")
FLAG_RE = re.compile(r"--[a-z][a-z-]*")
# Commands the skill deliberately leaves to `--help`: they belong to no
# workflow step, so no prose document has a reason to spell them out.
HELP_ONLY_COMMANDS = {"version"}


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _frontmatter(text: str) -> tuple[dict, list[str]]:
    """Parse the simple YAML subset the frontmatter uses."""
    lines = text.splitlines()
    assert lines[0] == "---", "SKILL.md must open with a YAML frontmatter fence"
    end = lines.index("---", 1)
    data: dict = {}
    current = None
    for line in lines[1:end]:
        if not line.strip():
            continue
        if line.startswith((" ", "\t")):
            key, _, value = line.strip().partition(":")
            data.setdefault(current, {})[key.strip()] = _unquote(value)
            continue
        key, _, value = line.partition(":")
        current = key.strip()
        data[current] = _unquote(value) if value.strip() else {}
    return data, lines[end + 1 :]


def _body() -> tuple[dict, list[str]]:
    return _frontmatter(SKILL_MD.read_text(encoding="utf-8"))


def _registered_commands() -> set[str]:
    """Every command string the parser actually registers."""
    from edcg.cli import build_parser

    parser = build_parser()
    top = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ][0].choices

    commands = {name for name in top if name not in ("branch", "markdb")}
    for group in ("branch", "markdb"):
        nested = [
            action
            for action in top[group]._actions
            if isinstance(action, argparse._SubParsersAction)
        ][-1].choices
        commands |= {f"{group} {sub}" for sub in nested}
    return commands


def _normalised(text: str) -> str:
    """Prose wraps command forms across lines; match on single spaces."""
    return " ".join(text.split())


def _process_steps(body: list[str]) -> list[str]:
    """The numbered step blocks of ``## Process``, continuation lines included.

    A step starts at a line matching ``^\\d+\\. ``; the wrapped prose that
    follows it (such as step 2's second command) belongs to that step. The
    preamble before step 1 is not a step and is skipped.
    """
    text = "\n".join(body)
    start = text.find("## Process")
    assert start != -1, "SKILL.md has no ## Process section"
    end = text.find("\n## Resume rule", start)
    assert end != -1, "## Process is not followed by ## Resume rule"
    steps: list[list[str]] = []
    for line in text[start:end].splitlines():
        if STEP_RE.match(line):
            steps.append([line])
        elif steps and line.strip():
            steps[-1].append(line)
    assert steps, "## Process has no numbered steps"
    return [_normalised("\n".join(block)) for block in steps]


@functools.lru_cache(maxsize=None)
def _group_subcommands(group: str) -> frozenset[str]:
    """The subcommand names the parser registers under ``group``."""
    from edcg.cli import build_parser

    top = [
        action
        for action in build_parser()._actions
        if isinstance(action, argparse._SubParsersAction)
    ][0].choices
    nested = [
        action
        for action in top[group]._actions
        if isinstance(action, argparse._SubParsersAction)
    ][-1].choices
    return frozenset(nested)


def _command_tokens(base: str, second: str | None) -> list[str]:
    """``["markdb", "add"]`` for a registered subcommand, else ``["markdb"]``.

    Bounding the second token to the registered set keeps prose words out:
    ``edcg.py branch start`` is a command, ``edcg.py branch and ...`` is not.
    """
    if base in SUBCOMMAND_GROUPS and second in _group_subcommands(base):
        return [base, second]
    return [base]


def _command_name(base: str, second: str | None) -> str:
    """``branch start`` for a registered subcommand, else ``audit``."""
    return " ".join(_command_tokens(base, second))


def _documented_commands(body: list[str]) -> set[str]:
    """The commands the Process steps name inline, e.g. ``markdb add``."""
    found = set()
    for step in _process_steps(body):
        for base, second in COMMAND_TOKEN_RE.findall(step):
            found.add(_command_name(base, second))
    return found


def _mention_from_span(content: str) -> list[str] | None:
    """Command tokens when an inline span names one, else None.

    Handles both ``edcg.py markdb add`` and a bare backticked ``init``. Spans
    quoting another tool (``git log -1 --oneline``) and ordinary prose
    (``systems/``, ``UPDATEDB``) return None.
    """
    text = content.strip()
    match = COMMAND_TOKEN_RE.fullmatch(text)
    if match:
        return _command_tokens(match.group(1), match.group(2))
    words = text.split()
    if not 1 <= len(words) <= 2:
        return None
    if not all(re.fullmatch(r"[a-z][a-z-]*", word) for word in words):
        return None
    tokens = _command_tokens(words[0], words[1] if len(words) == 2 else None)
    return tokens if " ".join(tokens) in _registered_commands() else None


def _find_span(spans: list[re.Match], position: int) -> int | None:
    for index, span in enumerate(spans):
        if span.start() <= position < span.end():
            return index
    return None


def _line_events(
    line: str,
) -> tuple[list[tuple[int, str, object, int | None]], list[re.Match]]:
    """Mentions and flags on one line, in reading order.

    Each event is ``(position, kind, payload, span index)``; ``kind`` is
    ``"mention"`` (command tokens) or ``"flag"`` (the flag string).
    """
    spans = list(BACKTICK_SPAN_RE.finditer(line))
    events: list[tuple[int, str, object, int | None]] = []
    seen_spans: set[int] = set()

    for match in COMMAND_TOKEN_RE.finditer(line):
        tokens = _command_tokens(match.group(1), match.group(2))
        index = _find_span(spans, match.start())
        if index is None:
            events.append((match.start(), "mention", tokens, None))
        elif index not in seen_spans:
            seen_spans.add(index)
            events.append((spans[index].start(), "mention", tokens, index))

    for index, span in enumerate(spans):
        if index in seen_spans:
            continue
        tokens = _mention_from_span(span.group(1))
        if tokens is not None:
            events.append((span.start(), "mention", tokens, index))

    for match in FLAG_RE.finditer(line):
        events.append(
            (match.start(), "flag", match.group(0), _find_span(spans, match.start()))
        )

    events.sort(key=lambda event: event[0])
    return events, spans


def _flag_pairs_in(text: str) -> list[tuple[list[str], str]]:
    """Every (command tokens, flag) pair one markdown document documents.

    A flag belongs to the nearest command before it. Inside backticks it only
    counts when it shares the span with that command, so a separate
    ``git log -1 --oneline`` is never read as an edcg flag; a flag quoted on
    its own (``--since``) belongs to the command the surrounding section names.
    """
    pairs: list[tuple[list[str], str]] = []
    current: list[str] | None = None

    for line in text.splitlines():
        if SECTION_RE.match(line):
            current = None
            continue
        events, spans = _line_events(line)
        span_mentions: dict[int, list[str]] = {}

        for _, kind, payload, index in events:
            if kind == "mention":
                current = list(payload)  # type: ignore[arg-type]
                if index is not None:
                    span_mentions[index] = list(payload)  # type: ignore[arg-type]
                continue

            flag = str(payload)
            if index is None:
                owner = current
            elif index in span_mentions:
                owner = span_mentions[index]
            elif FLAG_RE.sub("", spans[index].group(1)).strip():
                # Another tool's span, e.g. `git log -1 --oneline`.
                owner = None
            else:
                owner = current
            if owner is not None:
                pairs.append((list(owner), flag))

    return pairs


def _documented_flags() -> list[tuple[list[str], str]]:
    """Every documented flag with the command that must accept it.

    Scans SKILL.md and the references, so the flags the deleted table used to
    own (``--no-git``, ``--since``, ``--merge``, ``--push``, ``--confirm``)
    stay checked.
    """
    texts = [SKILL_MD.read_text(encoding="utf-8")]
    texts += [
        path.read_text(encoding="utf-8") for path in sorted(REFERENCES.glob("*.md"))
    ]
    pairs: list[tuple[list[str], str]] = []
    seen: set[tuple[tuple[str, ...], str]] = set()
    for text in texts:
        for tokens, flag in _flag_pairs_in(text):
            key = (tuple(tokens), flag)
            if key not in seen:
                seen.add(key)
                pairs.append((tokens, flag))
    return pairs


def _documented_anywhere() -> set[str]:
    """Every command named in SKILL.md or a reference document.

    The deleted Commands table was the only place that listed the whole
    surface. Now the Process steps, Setup and the references together name it,
    so coverage is checked across the skill's prose rather than one section.
    """
    texts = [SKILL_MD.read_text(encoding="utf-8")]
    texts += [
        path.read_text(encoding="utf-8") for path in sorted(REFERENCES.glob("*.md"))
    ]
    found: set[str] = set()
    for text in texts:
        for base, second in COMMAND_TOKEN_RE.findall(_normalised(text)):
            found.add(_command_name(base, second))
    return found


def _command_parser(tokens: list[str]) -> argparse.ArgumentParser:
    """The parser that owns ``tokens``, e.g. the ``markdb add`` subparser."""
    from edcg.cli import build_parser

    current = build_parser()
    for token in tokens:
        subparsers = [
            action
            for action in current._actions
            if isinstance(action, argparse._SubParsersAction)
        ]
        assert subparsers, f"{' '.join(tokens)} has no subcommand {token!r}"
        choices = subparsers[0].choices
        assert token in choices, f"unknown command token {token!r}"
        current = choices[token]
    return current


class TestFrontmatter:
    """The discovery surface: only the frontmatter is read before activation."""

    def test_frontmatter_has_the_pinned_fields(self):
        data, _ = _body()
        for field in ("name", "description", "license", "compatibility", "metadata"):
            assert field in data, f"missing frontmatter field: {field}"

    def test_name_matches_the_skill_folder(self):
        data, _ = _body()
        assert data["name"] == "edcopilot-system-content"
        assert data["name"] == SKILL_DIR.name

    def test_description_covers_both_workflows_and_activation_keywords(self):
        description = _body()[0]["description"].lower()
        assert "author" in description or "writing" in description
        assert "updat" in description
        for keyword in (
            "colonisation",
            "system",
            "station",
            "greeting",
            "chatter",
            "broadcast",
            "edcopilot",
            "elite dangerous",
            "speech extensions",
        ):
            assert keyword in description, f"description never mentions {keyword!r}"

    def test_license_is_gpl_3(self):
        assert _body()[0]["license"] == "GPL-3.0"

    def test_compatibility_names_the_runtime_requirements(self):
        compatibility = _body()[0]["compatibility"]
        assert compatibility == (
            "Requires Windows (EDCoPilot), Python 3.12+, the httpx and "
            "GitPython packages, and git"
        )
        assert len(compatibility) <= 500

    def test_metadata_carries_the_release_version(self):
        from edcg import __version__

        data, _ = _body()
        assert data["metadata"]["version"] == "1.0.0"
        assert data["metadata"]["version"] == __version__


class TestBodyShape:
    """Progressive disclosure only works while the body stays small."""

    def test_body_is_under_500_lines(self):
        _, body = _body()
        assert len(body) < 500, f"SKILL.md body is {len(body)} lines"

    def test_body_has_the_eight_spine_sections_in_order(self):
        _, body = _body()
        headings = [
            line[3:].strip()
            for line in body
            if line.startswith("## ")
        ]
        assert headings == EXPECTED_SECTIONS

    def test_body_lists_the_five_reference_files(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        linked = REFERENCE_LINK_RE.findall(text)
        # A reference may be linked more than once (the Process section repeats
        # the two interview links), so compare the set of names, not the count.
        assert {Path(path).name for path in linked} == set(EXPECTED_REFERENCES)

    def test_every_linked_reference_exists(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        for relative in REFERENCE_LINK_RE.findall(text):
            path = SKILL_DIR / relative
            assert path.is_file(), f"SKILL.md links to a missing file: {relative}"
            assert path.stat().st_size > 0

    def test_setup_mentions_doctor_before_init(self):
        _, body = _body()
        text = "\n".join(body)
        assert "edcg.py doctor" in text
        assert "edcg.py init" in text
        assert text.index("edcg.py doctor") < text.index("edcg.py init")
        assert "fix:" in text.lower()

    def test_setup_resolves_the_fresh_setup_contradiction(self):
        """A missing root on first run is expected; everything else is not."""
        _, body = _body()
        text = "\n".join(body)
        lowered = text.lower()
        assert "expected on first run" in lowered
        flattened = " ".join(lowered.split())
        assert "no other failed check may be bypassed" in flattened
        assert "before any content work" in lowered
        assert "roots.edcopilot" in text
        assert "does not look right" in flattened

    def test_setup_documents_the_content_root_and_blank_directory_flow(self):
        _, body = _body()
        text = " ".join(" ".join(body).split())
        lowered = text.lower()
        assert "EDCG_CONTENT_DEFINITIONS_ROOT" in text
        assert "working directory" in lowered
        assert "isn't a content repository yet" in lowered
        assert "--no-git" in text
        # init is a skeleton command: it writes the config file and systems/,
        # and copies no rules example into the content repository.
        assert "it writes the config file" in lowered
        assert "`systems/` directory" in text
        assert "the rules example" not in lowered

    def test_skill_md_setup_adopts_house_rules(self):
        """The house-rules copy is agent-mediated and reviewed before content."""
        _, body = _body()
        setup = "\n".join(body)
        setup = setup[setup.index("## Setup") : setup.index("## Process")]
        text = " ".join(setup.split())
        lowered = text.lower()

        assert "**Adopt the house rules.**" in text
        # The step is Setup step 3: it follows init and precedes the root work.
        assert text.index("**Adopt the house rules.**") < text.index(
            "**Establish the EDCoPilot root.**"
        )

        # The step only acts when the house file is absent.
        assert "if `systems/all.rules.toml` does not exist" in lowered

        # A legacy in-repo example is promoted (it may hold user edits) and the
        # redundant copy is deleted.
        assert "promote it" in lowered
        assert "copy it to `systems/all.rules.toml`" in text
        assert "delete the redundant example" in lowered

        # Otherwise the agent-facing asset is the source, linked so it is read.
        assert (
            "copy [`assets/all.rules.toml.example`](assets/all.rules.toml.example)"
            in text
        )
        assert "→ `systems/all.rules.toml`" in text

        # The review is the point: every section the example contains is walked
        # with the user.
        assert "review the rules with the user" in lowered
        for section in ("logo", "banned filters", "conversation floors"):
            assert section in lowered, f"house-rules review omits {section!r}"
        # The starter asset has no bounds table; Setup must not claim one.
        assert "bounds" not in lowered
        assert "modify, add, or remove" in lowered
        assert "before any content work" in lowered

        # An existing repository is reminded that changes are deliberate.
        assert "for an existing repository" in lowered
        assert "deliberate edits with their reasons" in lowered

        # The reviewed file is not a stray: save-definition stages everything,
        # so it lands in the first definition commit (not the content commit).
        assert "rides into the first definition commit" in lowered
        assert "`edcg: scaffold` or `edcg: update`" in text
        assert "first content commit" not in lowered

    def test_setup_names_the_edcopilot_root_override(self):
        _, body = _body()
        text = "\n".join(body)
        assert "EDCG_EDCOPILOT_ROOT" in text

    def test_resume_rule_audits_before_touching_content(self):
        _, body = _body()
        text = "\n".join(body)
        assert "edcg.py audit --system" in text
        assert "edcg.py update-scan" in text
        assert "the content repository is the state" in text.lower()

    def test_update_flow_names_update_scan_as_the_refresh_command(self):
        _, body = _body()
        text = "\n".join(body)
        assert "refresh command" in text.lower()
        assert "for one system or many" in text.lower()

    def test_commit_subjects_match_the_scripts(self):
        _, body = _body()
        text = "\n".join(body)
        assert "edcg: scaffold <system> — <summary>" in text
        assert "edcg: update <system> — <summary>" in text
        assert "edcg: markdb add <n> tag(s)" in text
        assert "edcg: markdb remove <n> tag(s)" in text

    def test_gate_state_is_derived_from_the_repository(self):
        _, body = _body()
        # Prose wraps `edcg.py branch status` across a line break.
        text = " ".join(" ".join(body).split())
        lowered = text.lower()
        assert "edcg.py branch status" in text
        assert "edcg.py get-content" in text
        assert "updatedb" in lowered
        assert "systems/" in text
        assert "audit-derived" not in lowered

    def test_branch_offer_is_shared_and_early(self):
        """One branch decision, in the spine, before either workflow starts.

        The offer used to live only in the new-system interview, so an update
        could reach the interview without ever hearing about branches. It is one
        spine rule now, and it runs before the interview step in both modes.
        """
        _, body = _body()
        text = " ".join(" ".join(body).split())
        process = text[text.index("## Process") : text.index("## Resume rule")]
        assert "Feature branch (optional, both modes)." in process
        assert "edcg.py branch start" in process
        assert "only if the user accepts" in process
        assert "Never create a branch the user did not ask for" in process
        assert process.index("Feature branch (optional, both modes).") < process.index(
            "**Interview.**"
        )

    def test_scripts_pause_for_gates_but_refuse_invalid_operations(self):
        """No gate is enforced, but impossible operations still fail cleanly."""
        _, body = _body()
        text = " ".join(" ".join(body).split())
        assert "never pause for a gate" in text
        assert "refuse impossible or invalid operations" in text
        for example in (
            "a bad definition",
            "a rewrite that would introduce errors",
            "an existing repository on `init`",
        ):
            assert example in text, f"missing refusal example: {example}"


class TestCommandList:
    """The commands the Process steps name and the parser must not drift apart."""

    def test_every_documented_command_is_registered(self):
        _, body = _body()
        documented = _documented_commands(body)
        assert documented, "the ## Process steps name no edcg.py commands"
        invented = documented - _registered_commands()
        assert not invented, f"Process steps invent commands: {sorted(invented)}"

    def test_no_skill_document_invents_a_command(self):
        """The old table policed this; the prose across the skill now does."""
        invented = _documented_anywhere() - _registered_commands()
        assert not invented, f"skill documents invent commands: {sorted(invented)}"

    def test_every_registered_command_is_documented(self):
        """No registered command is invisible: prose names it, or --help does.

        The Process steps carry the workflow commands; Setup names `doctor`
        and `init`, and the references carry the branch lifecycle. Only
        `version` is left to `--help` (see HELP_ONLY_COMMANDS).
        """
        documented = _documented_anywhere()
        missing = _registered_commands() - documented - HELP_ONLY_COMMANDS
        assert not missing, f"no skill document names these commands: {sorted(missing)}"

    def test_documented_flags_are_accepted_by_their_command(self):
        """A documented flag that the parser rejects is argument-form drift."""
        from edcg.cli import build_parser

        top = build_parser()
        pairs = _documented_flags()

        # The inventory spans SKILL.md and the references, so the bound catches
        # an extractor that stops finding flags; it does not pin the vocabulary.
        assert len(pairs) >= 7, f"only {len(pairs)} documented flags found"

        for tokens, flag in pairs:
            # The flag may live on the subcommand's own parser or, for a
            # genuinely global flag, on the root parser.
            accepted = {
                option
                for parser in (top, _command_parser(tokens))
                for action in parser._actions
                for option in action.option_strings
            }
            assert flag in accepted, (
                f"{' '.join(tokens)} does not accept the documented flag {flag}"
            )

    @pytest.mark.parametrize(
        "argv",
        [
            ["gather-facts", "--system", "Test System"],
            ["writing-brief-data", "--system", "Test System"],
            ["get-content", "--system", "Test System"],
            ["audit", "--system", "Test System"],
            [
                "check-logs",
                "--since",
                "2026-01-01T00:00:00",
                "--system",
                "Test System",
            ],
            ["markdb", "add", "--tag", "@SystemGreeting<~>Test System"],
            ["markdb", "remove", "--tag", "@SystemGreeting<~>Test System"],
        ],
    )
    def test_representative_argument_forms_parse(self, argv):
        """Argument forms the prose and `--help` show must parse as written."""
        from edcg.cli import build_parser

        build_parser().parse_args(argv)

    def test_gather_facts_always_documents_the_required_system_argument(self):
        """Raven may have no entry, but the CLI still requires --system."""
        _, body = _body()
        rows = [line for line in body if "edcg.py gather-facts" in line]
        assert rows, "SKILL.md never documents gather-facts"
        for row in rows:
            assert "--system" in row, f"gather-facts row omits --system: {row}"


class TestProductIdentity:
    """The skill must read as a standalone product."""

    @pytest.mark.parametrize(
        "path",
        [pytest.param(SKILL_MD, id="SKILL.md")]
        + [pytest.param(REFERENCES / name, id=name) for name in EXPECTED_REFERENCES],
    )
    def test_no_prior_product_identity_strings(self, path: Path):
        assert path.is_file(), f"missing file: {path}"
        lowered = path.read_text(encoding="utf-8").lower()
        for banned in BANNED_STRINGS:
            assert banned not in lowered, f"{path.name} mentions {banned!r}"


def test_skill_md_has_numbered_process():
    """The Process section is the ordered spine of the whole workflow."""
    _, body = _body()
    text = "\n".join(body)
    lowered = text.lower()

    assert "## Process" in text, "SKILL.md has no ## Process section"
    assert lowered.index("## setup") < text.index("## Process"), (
        "## Process must follow ## Setup"
    )

    for label in (
        "Resume",
        "Gather facts",
        "Interview",
        "Validate the definition",
        "Save the definition",
        "Preview gate",
        "Writing brief",
        "Write the block",
        "Validate the content",
        "Write the content",
        "Review gate",
        "Mark for update",
        "Restart",
        "Check the logs",
        "In-game test and upload",
        "Clear the markers",
    ):
        assert f"**{label}.**" in text, f"Process is missing the step {label!r}"

    for number in range(1, 17):
        assert f"\n{number}. **" in text, f"Process is missing step number {number}"


def test_skill_md_setup_is_focused():
    content = SKILL_MD.read_text(encoding="utf-8")
    setup_start = content.index("## Setup")
    process_start = content.index("## Process")
    setup = content[setup_start:process_start]
    for label in ("**Check the environment.**", "**Establish the content root.**",
                  "**Adopt the house rules.**", "**Establish the EDCoPilot root.**",
                  "**Re-run `doctor`.**"):
        assert label in setup, label
    assert "must be closed whenever" not in setup
    assert "must be closed whenever" in content[process_start:]
    assert "Close EDCoPilot first." not in content
