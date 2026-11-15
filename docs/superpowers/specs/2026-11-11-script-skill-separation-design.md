# Script / Skill Separation — Design

**Date:** 2026-11-11
**Status:** Approved direction (human decisions recorded); spec for planning
**Supersedes:** nothing; it refines the founding spec's layering
(`docs/superpowers/specs/2026-11-10-repo-design.md`).

---

## Intent and why

Today the Python layer reaches into the skill's agent-facing directories:
`_ASSETS_DIR = Path(__file__).parents[3] / "assets"` counts parents to the
skill root, and `init` reads `all.rules.toml.example` from `assets/` to copy
into the user's repository. Two problems:

1. **Fragile coupling.** The code's layout is welded to the skill folder's
   layout by parent-counting; moving a directory breaks the scripts silently.
2. **Mixed concerns.** `assets/` holds both *executable rule data* the Python
   interprets (`base.toml`, `build_types.toml`, `raven.toml`) and *prose the
   agent reads* (`dossier-template.md`, `all.rules.toml.example`). The
   boundary that matters inside a skill folder is *what the code needs to
   run* vs *what the agent needs to read*.

This change draws that boundary. After it, the scripts are self-contained
(they depend only on their own package), `assets/` is purely agent-facing,
and the house-rules example becomes agent-mediated — the agent copies and
reviews it with the user, rather than `init` placing it mechanically.

## Goals

1. Rule data (`base.toml`, `build_types.toml`, `raven.toml`) lives in package
   data under `scripts/edcg/rules/data/`, loaded module-relative. No script
   contains a path that reaches the skill root by parent-counting.
2. `assets/` contains only agent-facing files: `dossier-template.md` and
   `all.rules.toml.example`.
3. `init` creates only the skeleton: git (unless `--no-git`), the config
   file, `systems/`. It no longer copies the house-rules example.
4. The setup flow gains a house-rules step: the agent copies
   `assets/all.rules.toml.example` → `systems/all.rules.toml` (when absent)
   and reviews the rules with the user — modify, add, remove — before any
   content work. This is an initial-setup step; afterwards, rule changes are
   deliberate edits with their reasons.
5. Everything else is unchanged: validation behavior, commit conventions,
   doctor, roots resolution, the Process section's step order (the new
   house-rules step slots into Setup; doctor's full-green gate before any
   content work stands).

## Non-goals

- No change to validator semantics, rule content, or the bounds/rule-patch
  machinery — only where the TOMLs live and how they load.
- No change to `dossier-template.md`'s content or its role (agent reads it
  directly; validation enforces the spine via `base.toml`).
- No new commands, flags, or env vars.
- The facts/content/repo layers are untouched (they never referenced
  `assets/`).

## Anti-goals (failure conditions)

- Any script still referencing the skill's `assets/` or `references/`
  directories after this change.
- A house-rules copy that happens without the user seeing the rules (the
  review step is the point, not paperwork).
- Silent breakage of the live-fixture tests (`tests/test_integration/`)
  through loader-path changes.

## Constraints

- Python ≥3.14; stdlib loading (`tomllib`); no new dependencies.
- The rule TOMLs' content is unchanged byte-for-byte (git mv semantics; the
  validators' expectations and the live-fixture assertions depend on it).
- `skills-ref validate` and the full hermetic suite stay green.
- Product identity: no new MCP/old-repo references anywhere.

## Decisions

### D1. Rule data home: `scripts/edcg/rules/data/` (human decision)

`base.toml`, `build_types.toml`, `raven.toml` move from `assets/` to
`scripts/edcg/rules/data/` (git mv — content unchanged). Loading becomes
module-relative: `Path(__file__).parent / "data" / <file>` in
`rules/engine.py` and `rules/validation.py`. The `_ASSETS_DIR` /
`RULES_DIR` constants are removed (no script reads `assets/` afterwards);
whatever tests referenced them read the new locations.

### D2. `assets/` is agent-facing only (design principle)

Contains exactly: `dossier-template.md`, `all.rules.toml.example`. Both are
read by the agent (via links from SKILL.md / references), never by scripts.

### D3. `init` is a skeleton command (human decision)

`init` creates: the config file (`edcopilot-customization-generator.toml`),
`systems/`, and git (unless `--no-git`) with the skeleton commit. It no
longer copies the house-rules example and no longer reads `assets/`. Its
JSON output drops the example-file entry.

### D4. The agent owns the house-rules copy and review (human decision)

SKILL.md Setup gains a step (after the content-root step, before the
first interview): if `systems/all.rules.toml` does not exist, copy
[`assets/all.rules.toml.example`](assets/all.rules.toml.example) →
`systems/all.rules.toml`, then review the rules with the user — walk each
section the example contains (logo, banned filters, conversation floors) and
let them modify, add, or remove before any content work. For an existing content
repository the step is a no-op except as a reminder that house-rule changes
are deliberate edits with their reasons. `docs/live-run-checklist.md` gains
the same step. `references/rules.md` keeps explaining the layers and points
at the new locations.

### D5. Documentation follows the files (builder execution)

Every doc that names the old locations is updated: `references/rules.md`
(base rules path), `references/writing-brief.md` (rule whys location), the
env-var reference if it names paths, README (init description and any
`assets/` mentions), and the founding spec's layer list if it names
`assets/` contents (it should be updated to the new boundary, since it is
the repo's own architecture statement).

### D6. Tests follow (builder execution)

`tests/test_rules_layer/test_rules_loading.py`,
`tests/test_assets/test_dossier_template.py` (identity/first-person guards
now scan the moved files at their new home), `tests/test_cli/test_init.py`
(skeleton-only init: the example is NOT created by init; a new test asserts
the agent-facing example remains in `assets/` after init),
`tests/test_integration/test_live_fixtures.py` (base-rules loading path).
A new guard test: no `.py` file under `scripts/` contains the string
`assets` (the anti-coupling invariant, enforced so it cannot creep back).

## What's left to the builder

- Exact loader spelling (module-relative constant vs importlib.resources —
  module-relative `Path(__file__).parent / "data"` is the lean).
- Whether `_MANAGED`-style constants or docstrings need wording updates
  beyond D5's list (sweep for `assets` across `scripts/` — the guard test
  from D6 will find them).
- The SKILL.md Setup step's exact wording and placement (after the
  content-root step is the lean).
- Whether `docs/backlog.md` items referencing `assets/base.toml` paths need
  re-pointing (they do; do it in the same change).

### D7. The example's stale header is corrected in this change (builder-check ruling)

`assets/all.rules.toml.example`'s header comment still says the base rule set
is `rules/base.toml in the installed package` (backlog item 23). Since the new
review step walks the user through this exact file, its header is corrected
now to point at `scripts/edcg/rules/data/base.toml`. The byte-for-byte
constraint covers only the three rule TOMLs — the example is a prose starter
and may be edited.

### D8. The init skeleton commit contains the config file only (builder-check ruling)

`systems/` is created on disk but git cannot track an empty directory; no
`.gitkeep` placeholder is added (the house-rules file arrives immediately in
setup and makes the directory tracked). The skeleton commit stages only the
config file — never `repo.add("systems")` with a no-match pathspec. The JSON
`created` list reports filesystem creations (config, `systems/`); the commit
holds the config file.

### D9. The reviewed house rules ride in the first definition commit (builder-check ruling)

No new command and no new commit subject: after the agent copies and reviews
`systems/all.rules.toml`, the file rides into the first definition commit the
workflow makes — `edcg: scaffold <system>` or `edcg: update <system>`, written
by `save-definition`, which stages every change in the content repository.
SKILL.md's setup step says so explicitly, so the setup state does not silently
disappear into an unexpected commit.

Erratum (2026-11-11): the original D9 said "first content commit";
`save-definition` runs before `write-content` and stages everything, so the
destination is the first definition commit. The old implementation had the same
ordering.

### D10. Promote an in-repo example before copying from assets (builder-check ruling)

A repository bootstrapped by the current `init` can hold
`systems/all.rules.toml.example` with no `systems/all.rules.toml`. The agent
step becomes: if `all.rules.toml` is missing and an in-repo
`all.rules.toml.example` exists, promote it (copy it — it may hold user
edits) and delete the now-redundant `.example`; only when neither exists copy
from `assets/all.rules.toml.example`. The review step follows in both cases.

## Builder-check resolutions (2026-11-11)

- Rule-data home: scripts/edcg/rules/data/ - confirmed by the human.
- House-rules copy owner: the agent, with a review step - confirmed by the human.
- Route: full spec/plan - confirmed by the human.
- D7-D10: builder-check rulings recorded above; no open questions remain for the human.
