# Script / Skill Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Python layer self-contained (rule data becomes package data under `scripts/edcg/rules/data/`), make `assets/` purely agent-facing, and turn `init` into a skeleton command whose house-rules example is copied and reviewed by the agent.

**Architecture:** Three rule TOMLs move by `git mv` from `skills/edcopilot-system-content/assets/` to `skills/edcopilot-system-content/scripts/edcg/rules/data/`; the two loaders switch from `parents[3] / "assets"` to module-relative `Path(__file__).parent / "data"`; `init` loses its example copy (config-file-only skeleton commit); SKILL.md Setup gains the agent-mediated house-rules copy-and-review step (D4/D7–D10 of the spec).

**Tech Stack:** Python 3.12+, stdlib `tomllib`, pytest; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-11-script-skill-separation-design.md` (this repo). Executors read both.

## Global Constraints

- The three rule TOMLs' **content is unchanged byte-for-byte** (`git mv`; the validators' expectations and live-fixture assertions depend on it). The example (`all.rules.toml.example`) is a prose starter and MAY be edited (D7: correct its stale header to point at `scripts/edcg/rules/data/base.toml`).
- After this change, **no `.py` file under `skills/edcopilot-system-content/scripts/` contains the string `assets`** (spec D6 guard test pins this).
- `assets/` ends containing exactly `dossier-template.md` and `all.rules.toml.example`.
- Product identity, hermetic default tests, adjacent trailers (`Models:` then `Co-authored-by:` in one final paragraph), conventional commit subjects — all per the founding spec and prior plans.
- Suite baseline: 714 passed, 10 deselected. Every task ends with the full hermetic suite green.

## Review Focus

Failure modes this plan implies that no single task's tests may cover; each is pinned by the named test in the named task.

1. **Loader breaks when the skill folder is relocated** — module-relative loading must not depend on the skill root's position. Test: `test_rules_layer/test_data_loading.py::test_loader_is_module_relative` (Task 1).
2. **A script regains a reference to `assets/`** — the anti-coupling invariant must be enforced forever. Test: `test_skill/test_assets.py::test_no_script_references_assets` (Task 1).
3. **`init` on an existing repo sweeps unrelated files** — skeleton commit must stage only the config file. Test: `test_cli/test_init.py::test_init_stages_only_config` (Task 3).
4. **Old `all.rules.toml.example` in a legacy repo is preserved, not clobbered** — the agent step promotes the in-repo copy (D10). Test: `test_skill_md` setup-text assertions + live-fixture coverage of a promoted example (Task 4).
5. **The house-rules review step is skippable without the user seeing the rules** — SKILL.md must gate: the copy is confirmed with the user and the review happens before any content work. Test: `test_skill_md.py` setup-content assertions (Task 4).

---

### Task 1: Rule data becomes package data

**Files:**
- Move: `skills/edcopilot-system-content/assets/{base,build_types,raven}.toml` → `skills/edcopilot-system-content/scripts/edcg/rules/data/` (new dir with `__init__.py`? No — plain data dir, no `__init__.py`; loaded by path, not import)
- Modify: `skills/edcopilot-system-content/scripts/edcg/rules/engine.py` (loader), `skills/edcopilot-system-content/scripts/edcg/rules/validation.py` (loader)
- Test: `tests/test_rules_layer/test_data_loading.py` (new), `tests/test_skill/test_assets.py` (guard)

**Interfaces:**
- Consumes: nothing new.
- Produces: module-relative loader behavior — `engine.py` and `validation.py` resolve `base.toml`/`build_types.toml`/`raven.toml` from `Path(__file__).resolve().parent / "data"`. `validation.py` keeps `load_base_config(rules_dir: Path)` signature (callers pass the dir explicitly); its internal default (`RULES_DIR`) becomes the new data dir. No public signatures change.

- [ ] **Step 1: Write the failing guard/loading tests**

```python
# tests/test_rules_layer/test_data_loading.py
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "edcopilot-system-content" / "scripts"

def test_rule_data_lives_in_package():
    data = SCRIPTS / "edcg" / "rules" / "data"
    for name in ("base.toml", "build_types.toml", "raven.toml"):
        assert (data / name).is_file(), name

def test_no_script_references_assets():
    for py in SCRIPTS.rglob("*.py"):
        assert "assets" not in py.read_text(encoding="utf-8"), py

def test_assets_is_agent_facing_only():
    assets = SCRIPTS.parent.parent / "assets"
    assert sorted(p.name for p in assets.iterdir()) == [
        "all.rules.toml.example", "dossier-template.md"]

def test_loader_is_module_relative():
    # relocate-proof: no loader line may contain "parents[3]" or "assets"
    for name in ("engine.py", "validation.py"):
        text = (SCRIPTS / "edcg" / "rules" / name).read_text(encoding="utf-8")
        assert "assets" not in text, name
        assert 'parents[3]' not in text, name
```

- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests\test_rules_layer\test_data_loading.py -q` — Expected: FAIL (files not moved; `assets` strings present).
- [ ] **Step 3: `git mv` the three TOMLs into `scripts/edcg/rules/data/`.** In `engine.py`: replace the `_ASSETS_DIR` constant and its comment with `RULE_DATA_DIR = Path(__file__).resolve().parent / "data"` and update `_load_toml` to use it. In `validation.py`: `RULES_DIR = Path(__file__).resolve().parent / "data"` (rename to `RULE_DATA_DIR` for consistency with engine; update the two internal uses at ~:1289 and ~:1542; keep `load_base_config(rules_dir)`'s parameter semantics — callers passing explicit dirs are unaffected).
- [ ] **Step 4: Run** the full suite `.\.venv\Scripts\python.exe -m pytest tests\ -q -m "not integration"` — Expected: PASS except tasks 3–5's tests, which are updated in their own tasks; `test_assets.py`'s whole-skill identity guard auto-covers the moved files (rglob). Fix any test that read `assets/base.toml` by re-pointing to the new data dir (`tests/test_rules_layer/*`, `tests/test_content_*.py`, `tests/test_integration/test_live_fixtures.py` — search for `assets`).
- [ ] **Step 5: Commit** `refactor: rule data becomes package data` + adjacent trailers.

### Task 2: `init` becomes skeleton-only

**Files:**
- Modify: `skills/edcopilot-system-content/scripts/edcg/cli.py` (init handler ~:300-335), `skills/edcopilot-system-content/scripts/edcg/repo/dossier.py` if it touches the example
- Test: `tests/test_cli/test_init.py`

**Interfaces:**
- Consumes: Task 1's data dir (nothing to copy anymore).
- Produces: `init` creates the config file, `systems/`, git skeleton; skeleton commit stages **only the config file** (D8); JSON `created` lists the config file and `systems/` (filesystem creations); the house-rules example is NOT created by init.

- [ ] **Step 1: Update `tests/test_cli/test_init.py`:** the example-creation assertions become assertions that init does NOT create `all.rules.toml.example` (and that `assets/all.rules.toml.example` still exists after init); the commit-staging test gains `test_init_stages_only_config`: an existing repo with an unrelated untracked file → after init, the commit contains only the config file and the unrelated file stays untracked (Review Focus 3).
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement:** remove the example copy (~:329-335); stage only the config file for the skeleton commit (replace any `add_all()`-style staging in init with an explicit path add per D8 — note `add_all()` parity applies to content/definition commits, NOT init); adjust the JSON `created` list.
- [ ] **Step 4: Run** full suite — Expected: PASS.
- [ ] **Step 5: Commit** `refactor: init becomes a skeleton command` + adjacent trailers.

### Task 3: Agent-mediated house-rules copy and review (docs + tests)

**Files:**
- Modify: `skills/edcopilot-system-content/SKILL.md` (Setup step), `skills/edcopilot-system-content/references/rules.md` (base rules path), `references/writing-brief.md` (rule-whys path), `docs/live-run-checklist.md` (house-rules step), `docs/backlog.md` (item 23 resolved; item 7 already resolved), `assets/all.rules.toml.example` (header per D7)
- Test: `tests/test_skill/test_skill_md.py`, `tests/test_skill/test_references.py`

**Interfaces:**
- Consumes: Task 1's data dir location (docs point at it).
- Produces: SKILL.md Setup gains the house-rules step (D4 wording, D9 ride-along note, D10 promote-legacy rule); docs name `scripts/edcg/rules/data/base.toml`.

- [ ] **Step 1: Update the SKILL.md tests:** assert Setup contains a house-rules step mentioning `assets/all.rules.toml.example`, the copy to `systems/all.rules.toml`, the review with the user (modify/add/remove), the ride-along-into-first-definition-commit note, and the promote-legacy rule (D10). Keep the existing four setup labels; the new step slots after the content-root step.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Write the docs:** SKILL.md Setup step 3 (renumber 3→4, 4→5); exact content per spec D4/D7/D9/D10: copy `assets/all.rules.toml.example` → `systems/all.rules.toml` when absent; if a legacy `systems/all.rules.toml.example` exists, promote it instead and delete the redundant copy; review each section with the user (logo, banned filters, conversation floors) — modify/add/remove; the file rides into the first definition commit the workflow makes (`edcg: scaffold` or `edcg: update`). Correct `all.rules.toml.example`'s header comment (D7). Update `rules.md`/`writing-brief.md` paths to `scripts/edcg/rules/data/base.toml`. Update `docs/live-run-checklist.md` (house-rules step between init and the interview). Update `docs/backlog.md`: item 23 → resolved; re-point `assets/base.toml` mentions to the data dir.
- [ ] **Step 4: Run** full suite — Expected: PASS.
- [ ] **Step 5: Commit** `docs: agent-mediated house rules setup` + adjacent trailers.

### Task 4: Final verification and review

**Files:** none new.

- [ ] **Step 1:** Full hermetic suite (expect 714±, 0 failed, 10 deselected) + `skills-ref validate skills/edcopilot-system-content` + the Review Focus items re-checked.
- [ ] **Step 2:** Reviewer dispatch (task-scoped), then final whole-change review per SDD.
- [ ] **Step 3:** Backlog: confirm items 7/23 closed; no new deferred items unrecorded.

---

## Execution notes for the dispatcher

- Task order is strict: 1 → 2 → 3 → 4 (each builds on the previous).
- Delegation policy: local Qwen first for coding tasks (3 attempts), pivot to a paid Go model after; review on paid Go models. The local model's inherited cwd now equals the repo root — still instruct absolute paths.
- The worktree scratch-copy hazard is resolved (session moved); if a subagent's report claims a commit, verify with `git -C F:\Users\Ian\Development\EDCoPilot-customization\edcopilot-customization-skills log`.
