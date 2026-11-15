# Live-run UX fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the skill's definition workflow un-guessable: one wrong payload yields one complete diagnosis, file-path flags remove giant JSON strings, the rules example exists, and the spine points at all of it.

**Architecture:** A shared payload-spec validator in `cli.py` aggregates all missing/wrong-typed fields into one usage error (stderr, exit 2 — the pinned usage contract). File flags on validate-definition/save-definition read UTF-8 files relative to the content root. `save_definition` narrows its commit from `add_all()` to exactly the definition files plus the house-rules ride-along. Spine and reference edits make the contract discoverable at point of use.

**Tech Stack:** Python 3.14, stdlib `argparse`/`json`/`tomllib`, pytest (hermetic).

**Spec:** `docs/superpowers/specs/2026-11-15-live-run-ux-fixes-design.md`

## Global Constraints

- Hermetic tests only: no network, no real EDCoPilot folders, `tmp_path` fixtures.
- Python 3.14 exactly (CI pins 3.14; `Path.read_text(newline=)` allowed).
- No new dependencies; stdlib `tomllib` for TOML.
- Provenance block format and byte-pinned wire-protocol strings untouched.
- Exit codes: 0 success, 1 check failure (validation produced findings), 2 usage error (stderr text, empty stdout). Payload faults are usage errors (D4).
- Advisory gates: scripts refuse invalid operations, never pause.
- Help-as-interface-doc: worked examples live in subcommand `--help` epilogs; SKILL.md carries pointers, not duplication.
- Commits: conventional subjects + single trailer `Co-authored-by: 🤖 OpenCode (<model(s)>) <noreply@opencode.ai>` naming the model actually used; no `Models:` line.
- Suite baseline at `ddaaecd`: 795 passed / 1 skipped / 9 deselected. Never weaken an assertion.

## Review Focus

1. **Dossier passed as a JSON object** (the live-run trap) → one aggregated usage error naming every fault with fix hints; never a traceback. Test: Task 1.
2. **JSON field and file flag both given** for the same value → usage error ("given twice"), not a silent override. Test: Task 2.
3. **File flag path relative to content root / absolute / with spaces** → reads exactly that file; missing or undecodable file → usage error with fix hint. Tests: Task 2.
4. **Stray staging file in the content root at save time** → NOT in the definition commit; house-rules ride-along still lands on first save. Tests: Task 3.
5. **Rules example drift** — the worked TOML in rules.md must satisfy the validator's rules-side checks verbatim. Test: Task 5.

---

### Task 1: Aggregated, type-validating payload reader

**Files:**
- Modify: `skills/edcopilot-system-content/scripts/edcg/cli.py` (`_payload` area, lines ~88–105; `command_validate_definition` ~486; `command_save_definition` ~495; `command_validate_content`; `command_write_content`; `command_rewrite_tag`)
- Test: `tests/test_cli/test_payload_validation.py` (create)

**Interfaces:**
- Produces: `_require_fields(data: dict, spec: dict[str, type]) -> None` in `cli.py` — raises `UsageError` whose message aggregates every fault, one `error: ...` + `fix: ...` pair per fault, newline-separated. `spec` maps field name → expected type (`str` only for now; every payload field in the five commands is a string or absent). Later tasks consume it.
- Unchanged: `_payload()` reading behaviour; existing messages `expected a JSON payload on stdin`, `invalid JSON payload: ...`, `JSON payload must be an object` keep their meaning (wording may gain a `fix:` line).

- [ ] **Step 1: Write the failing tests**

```python
def test_dossier_as_object_aggregates_faults(capsys):
    # The live-run trap: {"system_name": {...}} and nested dossier object.
    payload = {"system_name": {"a": 1}, "dossier": {"x": 1}, "rules": "x"}
    assert _run(["validate-definition"], stdin=json.dumps(payload)) == 2
    err = capsys.readouterr().err
    assert "system_name" in err and "dossier" in err   # both faults, one message
    assert "fix:" in err
    assert capsys.readouterr().out == ""

def test_missing_and_wrong_type_in_one_message(capsys):
    payload = {"rules": 5}
    assert _run(["save-definition"], stdin=json.dumps(payload)) == 2
    err = capsys.readouterr().err
    assert "system_name" in err and "dossier_md" in err and "rules_toml" in err

def test_valid_payload_still_reaches_validation(capsys):
    # A well-formed but invalid definition exits 1 with findings, NOT 2.
    # (minimal dossier markdown, no sections)
    payload = {"system_name": "X", "dossier": "# X\n", "rules": "[system]\n"}
    assert _run(["validate-definition"], stdin=json.dumps(payload)) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_cli\test_payload_validation.py -v`
Expected: FAIL (type errors currently reach `parse_sections`/`tomllib` as `AttributeError`/`TypeError` tracebacks, exit 1).

- [ ] **Step 3: Implement `_require_fields` in `cli.py`**

Collect faults for every key in `spec`: missing/None → `error: payload is missing required field '<key>'` / `fix: include '<key>' — see this command's --help example`; present but `not isinstance(value, spec[key])` → `error: payload field '<key>' must be a <type name>, got <actual type name>` / `fix: pass '<key>' as a string ...`. Raise one `UsageError("\n".join(lines))` if any fault. Then replace the sequential `_required(...)` calls in the five commands (`validate-definition`, `save-definition`, `validate-content`, `write-content`, `rewrite-tag`) with one `_require_fields(data, {...spec...})` followed by direct `data[...]` access. Existing `test_dispatch.py` usage tests must still pass (message substrings `"required field"`, `"JSON payload"`, `"invalid JSON"` survive; add a `fix:` line to `_payload`'s three existing errors).

- [ ] **Step 4: Run the full test file + pinned usage tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_cli\test_payload_validation.py tests\test_cli\test_dispatch.py -v`
Expected: PASS (old tests unchanged in meaning).

- [ ] **Step 5: Commit**

```bash
git add skills/edcopilot-system-content/scripts/edcg/cli.py tests/test_cli/test_payload_validation.py
git commit -m "fix: aggregate payload type faults into one usage diagnosis"
```

### Task 2: File-path flags on the definition commands

**Files:**
- Modify: `skills/edcopilot-system-content/scripts/edcg/cli.py` (`definition_parser` ~797, `save_parser` ~801, `command_validate_definition`, `command_save_definition`)
- Test: `tests/test_cli/test_payload_files.py` (create)

**Interfaces:**
- Consumes: `_require_fields` from Task 1.
- Produces: `--dossier-file PATH`, `--rules-file PATH`, `--all-rules-file PATH` on `validate-definition`; `--dossier-file PATH`, `--rules-file PATH` on `save-definition` (no `all_rules` field there, so no third flag). Relative paths resolve against the content root (`get_config().content_definitions_root`); absolute paths accepted. Files read as UTF-8.
- Precedence (D3): if a file flag AND its JSON payload field are both supplied → `UsageError` naming the field ("given twice"), exit 2.
- `command_validate_definition(args)` gains: after `_payload()`, for each `(flag_attr, json_key, expected_desc)` in `[("dossier_file", "dossier", ...), ("rules_file", "rules", ...), ("all_rules_file", "all_rules", ...)]`: if `getattr(args, flag_attr)` and `json_key in data` → conflict error; if flag present → `data[json_key] = _read_utf8(resolved_path, json_key)`. `command_save_definition` same for its two flags mapping to `dossier_md`/`rules_toml`.

- [ ] **Step 1: Write the failing tests**

```python
def test_validate_definition_from_files(tmp_path, ...):   # round-trip
    # write minimal dossier.md + rules.toml files, run with flags,
    # expect the SAME findings JSON as the equivalent stdin payload
def test_flag_and_json_field_conflict_is_usage_error(capsys): ...
def test_missing_file_is_usage_error_with_fix_hint(capsys): ...
def test_relative_path_resolves_from_content_root(...): ...
def test_undecodable_file_is_usage_error(...):            # invalid UTF-8 bytes
def test_save_definition_maps_flags_to_md_toml_keys(...): # commit created
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_cli\test_payload_files.py -v`
Expected: FAIL (`argparse: unrecognized arguments`).

- [ ] **Step 3: Implement the flags, resolution, conflict check, `_read_utf8(path, field) -> str`**

`_read_utf8` decodes with `path.read_bytes().decode("utf-8")`, converting `UnicodeDecodeError`/`FileNotFoundError`/`OSError` into `UsageError` with the field name and a fix hint. Extend the `validate-definition` epilog with a worked example showing BOTH forms (stdin JSON with all four fields, and the three file flags); extend the `save-definition` epilog's example with the file form.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_cli\test_payload_files.py tests\test_cli\test_payload_validation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/edcopilot-system-content/scripts/edcg/cli.py tests/test_cli/test_payload_files.py
git commit -m "feat: definition commands accept file-path flags for large payloads"
```

### Task 3: Definition-commit hygiene (no `add_all`)

**Files:**
- Modify: `skills/edcopilot-system-content/scripts/edcg/repo/dossier.py:78-88` (the `with GitRepo(repo_root) as repo: repo.add_all()` block)
- Test: `tests/test_repo_layer/test_dossier.py` (extend; locate the existing save-definition tests and add alongside)

**Interfaces:**
- Consumes: `GitRepo.add(path)` (exists — used by `command_init`), `layout.systems_dir`, `config.content_definitions_root`.
- Produces: the definition commit contains exactly: `systems/<slug>.md`, `systems/<slug>.rules.toml`, plus `systems/all.rules.toml` ONLY when that file exists untracked at save time (the spine's house-rules ride-along, preserved). `SaveResult.files_changed` lists every committed file relative to the repo root (so it gains the house-rules entry when the ride-along happens).

- [ ] **Step 1: Write the failing tests**

```python
def test_stray_staging_file_not_committed(...):
    # save a definition with an unrelated untracked final_payload.json in the
    # root -> git status afterwards shows it still untracked; commit contains
    # exactly the two definition files
def test_house_rules_ride_along_on_first_save(...):
    # untracked systems/all.rules.toml present -> it IS in the commit and in
    # files_changed
def test_house_rules_not_readded_when_tracked(...):
    # all.rules.toml already tracked -> files_changed has exactly the two files
```

- [ ] **Step 2: Run to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_repo_layer\test_dossier.py -v`
Expected: FAIL (add_all sweeps the stray file).

- [ ] **Step 3: Implement**

Replace `repo.add_all()` with explicit `repo.add(...)` of the dossier file, rules file, and conditionally the house-rules file (`systems_dir / "all.rules.toml"` when it exists and is untracked — check via `git status --porcelain` semantics or `repo.is_untracked(path)` if GitRepo exposes one; otherwise add it unconditionally when `is_new` and it exists — `repo.add` on a tracked file is a no-op, which keeps the third test's behaviour naturally). Extend `files_changed` accordingly.

- [ ] **Step 4: Run to verify they pass + full suite**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_repo_layer\test_dossier.py -v` then `.\.venv\Scripts\python.exe -m pytest tests\ -q -m "not integration"`
Expected: PASS; suite count >= 800, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add skills/edcopilot-system-content/scripts/edcg/repo/dossier.py tests/test_repo_layer/test_dossier.py
git commit -m "fix: definition commit takes exactly its files plus the house-rules ride-along"
```

### Task 4: Spine wording — contract at point of use

**Files:**
- Modify: `skills/edcopilot-system-content/SKILL.md` (Process steps 3, 4, 5; lines ~100–102; the line-93 sentence stays as-is)

**Interfaces:**
- Consumes: the flag names from Task 2 and the field names from Task 1's specs (exact strings below).

- [ ] **Step 1: Edit SKILL.md**

Step 4 becomes: "`edcg.py validate-definition` (JSON stdin: `system_name`, `dossier`, `rules`, and `all_rules` when present; or pass `--dossier-file` / `--rules-file` / `--all-rules-file` instead of embedding the documents — see the command's `--help` example). Fix every `error` and repeat until `passed` is true. Warnings are understood, not ignored."

Step 5 becomes: "`edcg.py save-definition` (JSON stdin: `system_name`, `dossier_md`, `rules_toml`, `commit_co_author`; or `--dossier-file` / `--rules-file` — note the field names differ from validate-definition's). Verify the returned commit hash with `git log -1 --oneline`."

Step 3 gains one sentence at the end: "Read the interview reference before asking the first interview question; its phases and its validation checklist are the workflow."

- [ ] **Step 2: Check the skill tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_skill\ -v`
Expected: PASS (update any pinned step text the tests assert on, preserving each test's assertion intent).

- [ ] **Step 3: Validate the skill**

Run: `.\.venv\Scripts\skills-ref.exe validate skills\edcopilot-system-content`
Expected: `Valid skill`.

- [ ] **Step 4: Commit**

```bash
git add skills/edcopilot-system-content/SKILL.md
git commit -m "docs: spine names the definition payload fields and the file flags"
```

### Task 5: Worked per-system rules.toml example

**Files:**
- Modify: `skills/edcopilot-system-content/references/rules.md` (new section after "The catalogue", before "Bounds")
- Modify: `skills/edcopilot-system-content/SKILL.md` (read-this-when table row for rules.md, line ~37)
- Test: `tests/test_skill/test_rules_reference_example.py` (create)

**Interfaces:**
- Produces: a complete minimal worked `rules.toml` covering exactly what `validate_definition`'s rules-side checks require (read `validation.py` ~1320–1400 first and derive the required keys from the checks themselves, not from memory): `[system]` with `names` (array containing the system name), `dossier` (string), `voices` (array matching the dossier's section-8 voices), plus one station bound override demonstrating the `[content.bounds.stations."..."]` shape from the existing "Bounds" section.

- [ ] **Step 1: Write the failing test**

```python
def test_worked_example_parses_and_satisfies_required_keys():
    # extract the first ```toml block from the new "Authoring a system rules
    # file" section of references/rules.md; tomllib.loads it; assert
    # system.names is a non-empty list of str, system.dossier is a non-empty
    # str, system.voices is a non-empty list of str

def test_example_voices_match_the_example_prose():
    # if the section names example voices in prose, they match the TOML
```

- [ ] **Step 2: Run to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_skill\test_rules_reference_example.py -v`
Expected: FAIL (section does not exist).

- [ ] **Step 3: Write the section**

Section title: "Authoring a system rules file". Content: the minimal worked example TOML, one short paragraph on where it goes (`systems/<slug>.rules.toml`), the requirement that `voices` match dossier section 8 exactly, and a pointer to the validator's rules findings for anything else. Update the SKILL.md table row to: "Rule layers, precedence and bound semantics — before changing a rule, and when authoring a system's rules file".

- [ ] **Step 4: Run tests + validate**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_skill\ -v` then `.\.venv\Scripts\skills-ref.exe validate skills\edcopilot-system-content`
Expected: PASS; `Valid skill`.

- [ ] **Step 5: Commit**

```bash
git add skills/edcopilot-system-content/references/rules.md skills/edcopilot-system-content/SKILL.md tests/test_skill/test_rules_reference_example.py
git commit -m "docs: worked per-system rules.toml example in the rules reference"
```

### Task 6: Evidence record — live-run findings and the fresh-rerun gate

**Files:**
- Modify: `docs/live-run-checklist.md` (new findings section or linked note)
- Modify: `docs/backlog.md` (Before-1.0 record)

- [ ] **Step 1: Write the findings record**

One home: either a section in `docs/live-run-checklist.md` or a linked findings note — builder's choice, linked from the checklist. Content: the failure chain (skipped reference → invented schema → error-driven archaeology → retry loop), the fixes that now exist (aggregated diagnosis, file flags, rules example, spine pointers, commit hygiene), and that the fresh-session rerun replaces the salvage as the pre-tag live-run gate — exercising `init --co-author`, the new flags and error messages end to end.

- [ ] **Step 2: Update the backlog**

Under the 1.0 record: the five fixes shipped; the fresh rerun is the remaining gate before tagging.

- [ ] **Step 3: Commit**

```bash
git add docs/live-run-checklist.md docs/backlog.md
git commit -m "docs: record the live-run findings and the fresh-rerun release gate"
```

## Final verification (controller)

- `.\.venv\Scripts\python.exe -m pytest tests\ -q -m "not integration"` — full raw output; expect ≥ 810 passed, 0 failed, 9 deselected.
- `.\.venv\Scripts\skills-ref.exe validate skills\edcopilot-system-content` — clean.
- `git log --oneline <baseline>..HEAD` — six conventional commits, single co-author trailers, no `Models:` lines.
- Whole-branch review on a paid model before reporting completion.
