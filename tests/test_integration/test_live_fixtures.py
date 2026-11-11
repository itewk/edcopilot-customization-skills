"""Integration tests against the author's live content repositories.

These tests are the live regression fixture: they point the skill's own
machinery at real authored files and prove it parses them without losing a
byte. They never assert that the human's content is perfect - a finding is
reported, not failed - because the invariant under test is the *reader*, not
the text.

Two environment variables, both read-only:

``EDCP_TEST_LIVE_ROOT``
    The live content repository (``systems/*.md`` + ``*.rules.toml``).
    Unset means every test here skips.

``EDCP_TEST_EDCOPILOT_ROOT``
    EDCoPilot's install directory, holding
    ``EDCoPilot.SpeechExtensions.Custom.txt``. Unset means the custom-file
    tests skip: there is nothing to read, so nothing is round-tripped.

The files are opened for reading only; nothing under either root is written.
"""

import os
from pathlib import Path

import pytest

from edcg.content.custom_file import CUSTOM_FILE_NAME
from edcg.rules import engine
from edcg.rules.validation import (
    PROVENANCE_RE,
    RULES_DIR,
    Finding,
    ValidationResult,
    _extract_site_table,
    _parse_dossier_sections,
    load_all_system_rules,
    load_base_config,
    load_house_rules,
    load_kinds,
    load_system_rules,
    merge_rules,
    parse_content,
    rewrite_tag_lines,
    validate_content,
    validate_definition,
)

pytestmark = pytest.mark.integration

LIVE_ROOT_ENV = "EDCP_TEST_LIVE_ROOT"
EDCOPILOT_ROOT_ENV = "EDCP_TEST_EDCOPILOT_ROOT"
TEMPLATE_DIR_NAME = "edcopilot-colonisation-template"


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _report(title: str, rows: list[str]) -> None:
    """Print a summary so a live run shows what it actually found.

    Run the live path with ``-s`` to see it; on a failure pytest shows it too.
    """
    print(f"\n{title}")
    for row in rows:
        print(f"  {row}")


def _live_systems_dir() -> Path:
    """The live content repo's ``systems/`` directory, or a skip."""
    raw = os.environ.get(LIVE_ROOT_ENV)
    if not raw:
        pytest.skip(f"{LIVE_ROOT_ENV} is not set: no live content repository to check")
    root = Path(raw).expanduser()
    if not root.is_dir():
        pytest.skip(f"{LIVE_ROOT_ENV} points at {root}, which is not a directory")
    systems = root / "systems"
    if not systems.is_dir():
        pytest.skip(f"{root} has no systems/ directory")
    return systems


@pytest.fixture
def live_systems_dir() -> Path:
    return _live_systems_dir()


@pytest.fixture
def live_house_rules(live_systems_dir: Path) -> Path:
    path = live_systems_dir / "all.rules.toml"
    if not path.is_file():
        pytest.skip(f"{live_systems_dir} has no all.rules.toml: no house rules to merge")
    return path


@pytest.fixture
def live_custom_file() -> Path:
    """EDCoPilot's custom file, or a skip explaining why it is unavailable."""
    raw = os.environ.get(EDCOPILOT_ROOT_ENV)
    if not raw:
        pytest.skip(
            f"{EDCOPILOT_ROOT_ENV} is not set: EDCoPilot's install directory is "
            f"unknown, so {CUSTOM_FILE_NAME} cannot be read or round-tripped"
        )
    root = Path(raw).expanduser()
    path = root / CUSTOM_FILE_NAME
    if not path.is_file():
        pytest.skip(f"{CUSTOM_FILE_NAME} is not present under {root}")
    return path


def _system_rules_files(systems_dir: Path) -> list[Path]:
    """Every per-system rules file, i.e. every *.rules.toml but all.rules.toml."""
    return [
        path
        for path in sorted(systems_dir.glob("*.rules.toml"))
        if path.name != "all.rules.toml"
    ]


def _declared_names(rules: dict) -> list[str]:
    system = rules.get("system") or {}
    names = system.get("names") or []
    return [name for name in names if isinstance(name, str)]


def _dossier_pairs(systems_dir: Path) -> tuple[list[tuple[Path, Path]], list[Path]]:
    """(dossier, rules) pairs, resolved the way the validators resolve them.

    ``system.dossier`` is declared relative to the repo root, but older
    repositories declare it relative to ``systems/``; both are tried. A dossier
    with no rules file is reported rather than failed: the rules-less dossier is
    content in progress, not a broken reader.
    """
    by_dossier: dict[Path, Path] = {}
    for rules_path in _system_rules_files(systems_dir):
        declared = (engine.load_system_rules(rules_path).get("system") or {}).get("dossier")
        if not declared:
            continue
        for candidate in (systems_dir / declared, systems_dir.parent / declared):
            if candidate.is_file():
                by_dossier.setdefault(candidate.resolve(), rules_path)
                break

    pairs: list[tuple[Path, Path]] = []
    unpaired: list[Path] = []
    for dossier in sorted(systems_dir.glob("*.md")):
        rules_path = by_dossier.get(dossier.resolve())
        if rules_path is None:
            sibling = dossier.with_suffix(".rules.toml")
            rules_path = sibling if sibling.is_file() else None
        if rules_path is None:
            unpaired.append(dossier)
        else:
            pairs.append((dossier, rules_path))
    return pairs, unpaired


def _assert_findings_well_formed(result: ValidationResult, label: str) -> None:
    """The result is the dataclass the rest of the skill consumes."""
    assert isinstance(result, ValidationResult), label
    assert isinstance(result.passed, bool), label
    assert isinstance(result.findings, list), label
    for finding in result.findings:
        assert isinstance(finding, Finding), f"{label}: {finding!r} is not a Finding"
        assert isinstance(finding.rule, str) and finding.rule, f"{label}: empty rule id"
        assert finding.severity in ("error", "warn", "info"), f"{label}: {finding.severity}"
        assert finding.line is None or isinstance(finding.line, int), f"{label}: {finding.line}"
        assert isinstance(finding.message, str) and finding.message, f"{label}: empty message"


def _finding_summary(result: ValidationResult) -> str:
    errors = sum(1 for f in result.findings if f.severity == "error")
    warns = sum(1 for f in result.findings if f.severity == "warn")
    infos = sum(1 for f in result.findings if f.severity == "info")
    detail = "; ".join(
        f"{f.severity} {f.rule}: {f.message}" for f in result.findings[:5]
    )
    suffix = f" [{detail}]" if detail else ""
    return (
        f"{'passed' if result.passed else 'failed'} - "
        f"{errors} error(s), {warns} warn(s), {infos} info{suffix}"
    )


def _render_bytes(lines: list[str], line_ending: str, bom: bool, raw: bytes) -> bytes:
    """Rebuild a file from parsed lines, restoring the encoding it arrived in.

    This is the reverse of ``parse_content``: it is what proves the parser kept
    every line, in order, with nothing trimmed or rewritten.
    """
    text = "\n".join(lines)
    if raw.endswith(b"\n"):
        text += "\n"
    if line_ending == "crlf":
        text = text.replace("\n", "\r\n")
    if bom:
        text = "\ufeff" + text
    return text.encode("utf-8")


# ---------------------------------------------------------------------------
# Live content repository
# ---------------------------------------------------------------------------

def test_live_systems_md_validation(live_systems_dir: Path, live_house_rules: Path) -> None:
    """Every live dossier parses and cross-references through validate_definition.

    The dossier text and its rules TOML go through the same definition
    validator a save runs, with the repository's own all.rules.toml, so the
    house rules that the author added are in play.

    The invariant asserted here is the reader's, not the prose's: the nine-section
    spine and the section 4 site table must parse, and no ``dossier.*`` rule may
    report an error. Those rules are the reader talking about its own parse - a
    broken heading regex or table extractor shows up as ``dossier.spine`` or
    ``dossier.site_table`` - so a failure here is a regression in the skill. Any
    other finding (``rules.*``, ``content.*``) is the author's business and is
    printed for them rather than asserted away.
    """
    all_rules = live_house_rules.read_text(encoding="utf-8")
    pairs, unpaired = _dossier_pairs(live_systems_dir)

    assert pairs, f"no dossier/rules pair found under {live_systems_dir}"

    rows: list[str] = []
    for dossier_path, rules_path in pairs:
        dossier = dossier_path.read_text(encoding="utf-8")
        rules = rules_path.read_text(encoding="utf-8")
        names = _declared_names(engine.load_system_rules(rules_path))
        assert names, f"{rules_path.name} declares no system.names"
        system_name = names[0]

        result = validate_definition(dossier, rules, system_name, all_rules)

        _assert_findings_well_formed(result, f"{dossier_path.name} / {rules_path.name}")

        # The reader's own parse, via the helpers the validator itself uses.
        sections, order = _parse_dossier_sections(dossier)
        assert sorted(sections) == list(range(1, 10)), (
            f"{dossier_path.name}: the spine parsed to sections {sorted(sections)}, "
            "not 1..9"
        )
        assert order == list(range(1, 10)), (
            f"{dossier_path.name}: the spine parsed out of order: {order}"
        )
        assert _extract_site_table(sections[4][1]), (
            f"{dossier_path.name}: section 4 parsed to no site table rows"
        )

        reader_errors = [
            finding
            for finding in result.findings
            if finding.rule.startswith("dossier.") and finding.severity == "error"
        ]
        assert not reader_errors, (
            f"{dossier_path.name}: the reader reported {len(reader_errors)} "
            f"dossier error(s): {[(f.rule, f.message) for f in reader_errors]}"
        )

        rows.append(f"{dossier_path.name} as {system_name!r}: {_finding_summary(result)}")

    for dossier in unpaired:
        rows.append(f"{dossier.name}: no matching .rules.toml - not validated")

    _report("Live dossier validation", rows)


def test_live_systems_rules_toml_loading(
    live_systems_dir: Path, live_house_rules: Path
) -> None:
    """Every live *.rules.toml loads through the real rules engine and merges.

    Three layers, in the order the skill uses them: the raw TOML loader, the
    validation layer's override loader (which rejects a system rule that tries
    to declare a new rule), and the merged rule set that the validator runs.
    The whole directory is then loaded at once, which is the path
    ``validate_content`` takes and the only one that resolves every declared
    dossier. Each system's ``[content.bounds]`` keys are then checked against the
    tag kinds: a bound naming no kind can never match, so it is reported as an
    inert override.
    """
    base = load_base_config(RULES_DIR)
    base_rules = base["rules"]
    house_declared, house_patches = load_house_rules(live_house_rules, base_rules)

    rules_files = _system_rules_files(live_systems_dir)
    assert rules_files, f"no per-system *.rules.toml found under {live_systems_dir}"

    rows: list[str] = []
    for rules_path in rules_files:
        loaded = engine.load_system_rules(rules_path)
        assert isinstance(loaded, dict) and loaded, f"{rules_path.name} loaded nothing"
        names = _declared_names(loaded)
        assert names, f"{rules_path.name} declares no system.names"

        overrides = load_system_rules(rules_path, base_rules)
        assert isinstance(overrides, dict) and overrides, (
            f"{rules_path.name} produced no per-system config"
        )

        merged = merge_rules(base_rules, house_declared, house_patches, overrides)
        assert set(base_rules) <= set(merged), (
            f"{rules_path.name} lost base rules: {sorted(set(base_rules) - set(merged))}"
        )
        assert "filters.banned" in merged, "the house rule did not survive the merge"

        rows.append(
            f"{rules_path.name}: {len(names)} name(s), "
            f"{sum(len(cfg.get('overrides', {})) for cfg in overrides.values())} override(s), "
            f"{len(merged)} merged rule(s)"
        )

    per_system = load_all_system_rules(live_systems_dir, base_rules)
    assert isinstance(per_system, dict) and per_system, "no system rules loaded as a directory"
    merged_all = merge_rules(base_rules, house_declared, house_patches, per_system)
    known_kinds = set(load_kinds(base))
    for name, cfg in per_system.items():
        dossier = cfg.get("_dossier_path")
        assert dossier is not None, f"{name} has no resolved dossier"
        assert Path(dossier).is_file(), f"{name}'s dossier is missing: {dossier}"

        # A bound key naming no tag kind can never match, so the override is
        # silently inert. Report it rather than fail: the numbers are the
        # author's, and only they can say which spelling they meant.
        declared = set((cfg.get("content") or {}).get("bounds", {})) - {"stations"}
        inert = sorted(declared - known_kinds)
        if inert:
            rows.append(f"{name}: inert bound key(s) {inert} - no tag kind has these names")
        else:
            rows.append(f"{name}: {len(declared)} bound key(s), every one a tag kind")

    rows.append(
        f"directory load: {len(per_system)} system(s) -> {len(merged_all)} merged rule(s), "
        "every declared dossier resolved"
    )

    _report("Live rules loading", rows)


# ---------------------------------------------------------------------------
# Live EDCoPilot custom file
# ---------------------------------------------------------------------------

def test_live_custom_file_roundtrip(live_custom_file: Path) -> None:
    """The live custom file parses and survives a byte-exact round-trip.

    The bytes read are the bytes rebuilt: ``parse_content`` reports the line
    ending and BOM it stripped, so both are restored and compared against the
    file on disk. A no-op rewrite through ``rewrite_tag_lines`` then has to
    carry every line forward unchanged, which is the guarantee the save path
    depends on.
    """
    base = load_base_config(RULES_DIR)
    kinds = load_kinds(base)

    raw = live_custom_file.read_bytes()
    parsed = parse_content(live_custom_file, PROVENANCE_RE, kinds)

    assert parsed.lines, f"{live_custom_file.name} parsed to no lines"
    assert parsed.provenance, f"{live_custom_file.name} has no provenance marker"
    assert parsed.tags, f"{live_custom_file.name} has no authored tags"

    rebuilt = _render_bytes(parsed.lines, parsed.line_ending, parsed.bom, raw)
    assert rebuilt == raw, (
        f"{live_custom_file.name} does not round-trip: rebuilt {len(rebuilt)} bytes, "
        f"read {len(raw)}"
    )

    tag = next((candidate for candidate in parsed.authored_tags() if candidate.phrases), None)
    if tag is None:
        pytest.skip(
            f"{live_custom_file.name}'s authored tags carry no phrase lines: "
            "nothing for the rewrite primitive to carry forward"
        )

    tag_line = parsed.lines[tag.line - 1]
    phrase = tag.phrases[0].raw
    rewritten, counts = rewrite_tag_lines(
        list(parsed.lines), tag_line, replace={phrase: phrase}
    )

    assert counts["replaced"] >= 1
    assert rewritten == parsed.lines, "a self-replacement changed the file's lines"
    assert _render_bytes(rewritten, parsed.line_ending, parsed.bom, raw) == raw

    _report(
        "Live custom file round-trip",
        [
            f"{live_custom_file.name}: {len(parsed.lines)} line(s), "
            f"{len(parsed.provenance)} provenance marker(s), {len(parsed.tags)} tag(s), "
            f"{parsed.line_ending.upper() if parsed.line_ending is not None else 'no line ending'}"
            f"{' + BOM' if parsed.bom else ''} - byte-exact",
            f"self-replaced one phrase under {tag_line!r}: {counts}",
        ],
    )


def test_live_custom_file_validation(
    live_custom_file: Path, live_systems_dir: Path, live_house_rules: Path
) -> None:
    """The live custom file's latest provenance block validates for its systems.

    ``validate_content`` collapses to the last provenance marker before running
    the rules, so this is the same block the write path would have been checked
    against. The reader invariant is asserted first: that block must parse to
    tags, and those tags must name at least one system this repository defines -
    which is also what selects the systems validated here. A parse that returned
    no tags would make the validation vacuous, so it fails rather than passes.
    Findings are then reported for the human to read, not turned into a pass/fail
    on their prose.
    """
    content = live_custom_file.read_text(encoding="utf-8")
    base = load_base_config(RULES_DIR)
    per_system = load_all_system_rules(live_systems_dir, base["rules"])
    assert per_system, f"no system rules found under {live_systems_dir}"

    parsed = parse_content(live_custom_file, PROVENANCE_RE, load_kinds(base))
    assert parsed.provenance, f"{live_custom_file.name} has no provenance marker"

    block_start = parsed.provenance[-1][0]
    block_tags = [tag for tag in parsed.tags if tag.line >= block_start]
    assert block_tags, (
        f"{live_custom_file.name}: the last provenance block (line {block_start}) "
        "parsed to no tags"
    )

    named = {tag.system for tag in block_tags if tag.system}
    assert named, (
        f"{live_custom_file.name}: the block's {len(block_tags)} tag(s) name no "
        "system"
    )
    targets = sorted(name for name in per_system if name in named)
    assert targets, (
        f"{live_custom_file.name}: the block names {sorted(named)}, and none of "
        f"those systems is defined in {live_systems_dir} ({sorted(per_system)})"
    )

    rows: list[str] = [
        f"{live_custom_file.name}: block names {sorted(named)}, "
        f"{len(block_tags)} tag(s) parsed"
    ]
    for system_name in targets:
        result = validate_content(
            content,
            system_name,
            base_rules_path=RULES_DIR / "base.toml",
            house_rules_path=live_house_rules,
            systems_dir=live_systems_dir,
        )

        _assert_findings_well_formed(result, f"{live_custom_file.name} as {system_name!r}")
        rows.append(f"as {system_name!r}: {_finding_summary(result)}")

    _report("Live custom file validation (latest provenance block)", rows)


# ---------------------------------------------------------------------------
# Companion template repository
# ---------------------------------------------------------------------------

def test_companion_template_example_files(live_systems_dir: Path) -> None:
    """The companion template's example files load through the same validators.

    The template lives beside the live repository. It is an optional companion,
    so a missing directory is a skip with the path in the message: there is
    nothing to regress when it is not on this machine.
    """
    template_dir = live_systems_dir.parent.parent / TEMPLATE_DIR_NAME
    if not template_dir.is_dir():
        pytest.skip(f"companion template not found at {template_dir}")

    base = load_base_config(RULES_DIR)
    base_rules = base["rules"]
    house_paths = sorted(template_dir.rglob("all.rules.toml"))
    house_declared, house_patches = (
        load_house_rules(house_paths[0], base_rules) if house_paths else ({}, {})
    )
    house_text = house_paths[0].read_text(encoding="utf-8") if house_paths else None

    rows: list[str] = []
    rules_files = sorted(template_dir.rglob("*.rules.toml"))
    assert rules_files, f"companion template at {template_dir} has no rules files"

    for rules_path in rules_files:
        loaded = engine.load_house_rules(rules_path)
        assert isinstance(loaded, dict) and loaded, f"{rules_path} loaded nothing"

        declared = (loaded.get("system") or {}).get("dossier")
        if not declared:
            rows.append(f"{rules_path.relative_to(template_dir)}: house rules, loaded")
            continue

        dossier_path = None
        for candidate in (rules_path.parent / declared, template_dir / declared):
            if candidate.is_file():
                dossier_path = candidate
                break
        assert dossier_path is not None, f"{rules_path} declares a missing dossier: {declared}"

        names = _declared_names(loaded)
        assert names, f"{rules_path} declares no system.names"
        result = validate_definition(
            dossier_path.read_text(encoding="utf-8"),
            rules_path.read_text(encoding="utf-8"),
            names[0],
            house_text,
        )
        _assert_findings_well_formed(result, f"{rules_path.name} / {dossier_path.name}")
        rows.append(
            f"{rules_path.relative_to(template_dir)}: {_finding_summary(result)}"
        )

    merged = merge_rules(base_rules, house_declared, house_patches, {})
    assert set(base_rules) <= set(merged), "the template's house rules dropped base rules"
    rows.append(f"merged {len(merged)} rule(s) from the template's house rules")

    _report("Companion template example files", rows)
