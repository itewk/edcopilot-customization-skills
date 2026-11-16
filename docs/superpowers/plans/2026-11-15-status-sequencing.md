# Workflow status and sequencing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agents see where the workflow stands (`edcg status`), cannot do content work without a definition without an explicit human-acknowledged skip, and all three version strings align at `1.0.0-alpha.3`.

**Architecture:** `status` derives its checklist from the repo and files only (house-rules file, `systems/<slug>` definition files + definition commits in git, authored content in the custom file, markers). The definition-prerequisite family (`writing-brief-data`, `validate-content`, `write-content`, `rewrite-tag`, `markdb`) refuses with a three-part message and an explicit `--allow-no-definition` override that emits a consequence-restating warning on stderr. No state file; no pausing.

**Tech Stack:** Python 3.14, stdlib argparse/json/tomllib, pytest hermetic.

**Spec:** `docs/superpowers/specs/2026-11-15-status-sequencing-design.md`

**Worktree note:** implementation happens in the alpha.3 worktree; run tests with the main repo's venv interpreter (`F:\Users\Ian\Development\EDCoPilot-customization\edcopilot-customization-skills\.venv\Scripts\python.exe`) from the worktree cwd; `skills-ref` likewise by absolute path.

## Global Constraints

- Hermetic tests only; no network, no real EDCoPilot folders; `clean_env`/`tmp_path` fixtures.
- Python 3.14; no new dependencies.
- Advisory-gates philosophy: refusal of an invalid operation is allowed; pausing is not.
- `status` exits 0 always (usage errors exit 2 as usual); refusals are check failures → exit 1 via the existing `_fail` convention.
- No state file; state derives from git + files only.
- Help-as-interface-doc: worked examples for new command/flags.
- Commits: conventional subjects + single `Co-authored-by: 🤖 OpenCode (<model(s)>) <noreply@opencode.ai>` trailer naming the model actually used.
- Suite baseline at `ba38373` (v1.0.0-alpha.2): 859 passed / 1 skipped / 9 deselected. Never weaken an assertion.

## Review Focus

1. **Content work with no definition** (the live-run failure class) → refused, three-part message, exit 1, no partial writes. Test: Task 3 (each of the five commands).
2. **Human-approved skip** → `--allow-no-definition` proceeds, warning block restates consequences on stderr, transcript records it. Test: Task 3.
3. **Systemless tags** (kinds with `parts = []`, e.g. ConfirmedCommander) → markdb never refuses on them; markers for them cannot be stranded. Test: Task 3 (D6).
4. **A checklist that lies** — status derives strictly (`tag.system == system_name` for content; definition = dossier AND rules files, matching `is_new` semantics). Tests: Task 2 per state fixture.
5. **Version drift** — the three version strings must be equal; a consistency test pins it. Test: Task 1.

---

### Task 1: Version alignment — everything to 1.0.0-alpha.3

**Files:**
- Modify: `skills/edcopilot-system-content/scripts/edcg/content/custom_file.py:26` (`VERSION = "0.1.0"` → `"1.0.0-alpha.3"`)
- Modify: `skills/edcopilot-system-content/scripts/edcg/__init__.py` (`__version__` → `"1.0.0-alpha.3"`)
- Modify: `skills/edcopilot-system-content/SKILL.md` (metadata `version` → `"1.0.0-alpha.3"`)
- Modify: `docs/backlog.md` (superseded-decision note)
- Test: the version-pinning tests (grep `0.1.0` and `alpha.2` in `tests/` — `test_dispatch.py` pins provenance `VERSION`; `test_skill_md.py` pins metadata/`__version__`)

**Interfaces:**
- Produces: the provenance triple written to the runtime custom file now carries `1.0.0-alpha.3`. `PROVENANCE_RE` is untouched (matches format, not version).

- [ ] **Step 1: Write the failing consistency test** (new file `tests/test_version_alignment.py`):

```python
def test_the_three_version_strings_are_aligned():
    from edcg import __version__
    from edcg.content.custom_file import VERSION
    assert __version__ == VERSION == "1.0.0-alpha.3"
```
(plus update the existing pins: provenance expectations in `test_dispatch.py` from `0.1.0` → `1.0.0-alpha.3`; metadata pins in `test_skill_md.py`.)

- [ ] **Step 2: Run to verify fail** — `python -m pytest tests\test_version_alignment.py tests\test_cli\test_dispatch.py -q` → the alignment test fails, provenance pins fail.
- [ ] **Step 3: Implement** — the three strings + backlog note: "Superseded decision (2026-11-15): the provenance version byte-pin to the old implementation's `0.1.0` — the human ruled all version strings align on semver pre-releases; provenance blocks from this version onward carry the release version (`1.0.0-alpha.3`). `PROVENANCE_RE` format unchanged."
- [ ] **Step 4: Run to verify pass + full suite** (venv interpreter from the worktree) — 0 failed.
- [ ] **Step 5: Commit** — `chore: align all version strings on 1.0.0-alpha.3`

### Task 2: `edcg status` — the derived checklist

**Files:**
- Modify: `skills/edcopilot-system-content/scripts/edcg/cli.py` (new `command_status`, parser registration near the other read-only commands)
- Modify: `skills/edcopilot-system-content/scripts/edcg/repo/status.py` (CREATE — the state derivation, so the CLI stays thin; mirrors `repo/audit.py` placement)
- Test: `tests/test_repo_layer/test_status.py` (derivation) + `tests/test_cli/test_status.py` (command surface)

**Interfaces:**
- Consumes: `layout.dossier_path/rules_path/systems_dir`, `common.config.get_config`, `GitRepo` (definition commits via `git log -- systems/<slug>` — add a minimal `GitRepo.log_paths(prefix)` helper if none exists), `content.custom_file`/`get_system_content`-equivalent reading with the STRICT filter `tag.system == system_name` (D8 — do NOT reuse `get_system_content`'s station-decl fallback; comment the divergence), marker state via the existing markdb reading helpers.
- Produces: `build_status(config, system_name: str | None) -> str` — the prose checklist block; `command_status(args)` prints it, exit 0 always (D9).

- [ ] **Step 1: Write the failing tests** — derivation states per fixture: blank repo; house-rules only; definition saved (both files + definition commit); content written; markers set. Each asserted line uses `[x]`/`[ ]`; the interview-invisible wording per spec ("the interview is conversation — status cannot see it; a missing definition here means the definition steps have not run yet").
- [ ] **Step 2: Verify fail.** Step 3: **Implement** `repo/status.py` + thin `command_status` + parser (`status [ --system <name> ]` per D7; without the flag: repo-wide lines + one line per system; with: the full checklist). `--help` epilog with a worked example (B6). Step 4: verify pass + full suite. Step 5: **Commit** — `feat: edcg status derives the workflow checklist from the repository`

### Task 3: Definition-prerequisite refusals + override

**Files:**
- Modify: `skills/edcopilot-system-content/scripts/edcg/cli.py` (the five commands + parser flags)
- Modify: `skills/edcopilot-system-content/scripts/edcg/repo/sequencing.py` (CREATE — the shared check + message builder, so the wording is single-homed)
- Test: `tests/test_cli/test_sequencing.py`

**Interfaces:**
- Consumes: `layout.dossier_path/rules_path` (definition = BOTH files, matching `is_new`), markdb tag→system derivation (tag line split on `<~>`; field 1 after `@Kind`; kinds with `parts = []` exempt — D6; read `rules/data/base.toml` `[kinds]` via the existing loading helpers).
- Produces: `require_definition(config, system_name: str) -> None` raising the standard refusal; `refusal_message(system_name)` (three parts, exact text pinned in tests): prerequisite + fix; downstream consequences ("no bounds/voices/tag lines - content will be written blind, validation will be weak, EDCoPilot coverage cannot be verified"); the override flag name. `warn_skip(system_name)` printing the `warning:` block on stderr.

- [ ] **Step 1: Write the failing tests** — for each of the five commands: no definition → exit 1, three-part message, no partial writes; `--allow-no-definition` → proceeds, warning on stderr; systemless-tag markdb call → never refuses; markdb mixed call (one defined, one undefined system) → refuses naming the undefined system.
- [ ] **Step 2: Verify fail.** Step 3: **Implement** — each command checks `require_definition` after payload validation but BEFORE any filesystem write; markdb derives per-tag systems (refuse naming the offending system; exempt `parts = []` kinds); the flag skips the check and emits `warn_skip`. Add `--allow-no-definition` to the five parsers with a one-line help text (when a human chooses to skip the prerequisite). Step 4: verify pass + full suite. Step 5: **Commit** — `feat: content commands refuse without a definition unless the human allows the skip`

### Task 4: Docs — the workflow's new mechanics in the references

**Files:**
- Modify: `docs/live-run-checklist.md` (§B gains: run `edcg status` after init and after each gate; the refusal + override behaviour with the human-skip rule)
- Modify: `docs/backlog.md` (shipped note)

- [ ] **Step 1:** update the checklist §B with a status checkpoint and the refusal/override explanation (three sentences max). **Step 2:** backlog shipped line. **Step 3:** full suite + commit — `docs: status and sequencing in the live-run checklist`

## Final verification (controller)

- Full hermetic suite green (expect ≥ 865 passed); `skills-ref validate` clean; `git log` conventional commits with single trailers.
- Whole-branch review (paid) over the alpha.3 range before merge back to hello-galaxy.
