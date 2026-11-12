# Backlog

Open work for this repository, split by release. Each item is a **seed for the
superpowers process**: when picked up, it starts with brainstorming (unless the
diagnosis is already complete and the fix is a small change), then a plan under
`docs/superpowers/plans/`, then subagent-driven execution.

Items marked **(gate)** must pass before tagging `v1.0.0` but are execution
gates, not code changes.

---

## Before 1.0 — bugs and issues to resolve

All eight items below were resolved by the pre-1.0 fixes batch (commits
`aa02995`…`8d8bdbc`, 2026-11-11; see `docs/superpowers/plans/2026-11-11-pre-1-fixes.md`
and the SDD ledger for the full record). They are kept here as the resolution
record until the `v1.0.0` tag.

1. ~~Journal directory discovery~~ — **resolved** (`aa02995`): `EDCG_JOURNAL_DIR`
   override validated for `Journal.*.log`; doctor reports the resolved journal
   path as `OK`/`WARN` (a WARN never fails doctor); env-var documented and
   guard-tested; the `gather_facts` wiring is pinned end-to-end.
2. ~~Bounds keys matching no tag kind~~ — **resolved** (`2bb83a8`): warning
   findings at kind and station level, base-level pass included; the live
   content's inert keys are asserted by the integration test. The affected
   live rules files will NOT be corrected: the old content repository is being
   archived and the v1 live run uses a freshly bootstrapped repository, so the
   inert keys never reach the new workflow (human decision, 2026-11-12).
3. ~~markdb missing custom file~~ — **resolved** (`35d7580`): exit 1 naming the
   expected file and the resolved root, before any mutation; docs updated.
4. ~~Exit-code semantics at the edges~~ — **resolved** (`fa3fd57`): refused or
   unresolved actions exit 1; `push_status` gains `nothing_to_push`; the
   predicate keys off `push_status`. `--no-merge --push` is rejected at the
   parser (exit 2, `8d8bdbc`). Merge-failure-without-`--push` exits 0 by policy.
5. ~~`Config.edcopilot_root` second authority~~ — **resolved** (`222d538`): field
   removed; a surviving production reader and an env-blanking bug in
   `resolve_runtime_root` were found and fixed; test fixtures migrated.
6. ~~`os.access(W_OK)` unreliability~~ — **resolved** (`015dc15`, `8d8bdbc`):
   real write probe with a unique `mkstemp` name, `finally` cleanup separated
   from the write-failure verdict, deterministic tests including the
   `mkstemp` PermissionError path.
7. ~~Docs accuracy sweep~~ — **resolved** (`0e088ac`): CONTRIBUTING counts
   removed (guarded), update-interview duplication fixed (guarded) and
   taxonomy completed.
8. ~~`skills-ref` pin~~ — **resolved** (`bc5e90d`): CI pins the install to
   commit `83021e2be457a9b6679148719c1f6074f0ad975e`, validated locally.

## After 1.0 — features and improvements

9. **`--dry-run` flags** for the stateful commands (`write-content`,
   `save-definition`, `init`) so an agent can preview state changes (from the
   using-scripts guide).
10. **Output-size policy for data commands:** `get-content` on a large system
    is unbounded; default to a summary with a flag to request more
    (`gather-facts` already caps at 20 bodies).
11. **Boolean parsing parity decision:** `_str_to_bool` rejects `t/y/f/n`
    (accepted by the old pydantic settings) and treats `""` as unset → default
    `True`. Decide whether old spellings must be accepted; test the answer.
12. **`update-scan` coverage:** optionally add Inara/Spansh discrepancy,
    conflict and revision-delta counts the old summary carried.
13. **Test and hermeticity debt:** assertion-free or tautological tests
    (`test_extra_env_vars_ignored`, `test_env_var_prefix_is_edcg`,
    `test_smoke`'s folder-name assertion, `test_existing_root_not_rescaffolded`);
    environment leaks (`os.environ` written without `monkeypatch`); the
    under-asserting non-repo warning test; `GitRepo.push`'s `True/False/None`
    returns never asserted directly; the weak branch-e2e review assertion;
    `markdb`'s `[None]` no-commit path; "matches the code" tests that hardcode
    strings instead of deriving them; live-fixture breadth (all.rules-missing
    skip, rules-less dossier, provenance-before-skip, station sub-keys,
    byte-exactness vs the production writer); `_section`'s weak `ValueError`;
    test-docstring overclaims.
14. **Help-surface blind spots:** the argument-help walker cannot see
    per-subcommand `help=` (a future `add_parser` without help passes
    silently); the guarded-flag count bound is `>= 7` against an inventory of
    12; epilog examples spell `python edcg.py …` while SKILL.md documents
    `python <skill-dir>/scripts/edcg.py …` from the content root; the root
    epilog's command-group block omits `version`; `validate-definition` /
    `validate-content` carry no worked example.
15. **Help example encoding:** epilog examples are ASCII because a literal
    🤖 crashes redirected cp1252 stdout — revisit if the console-encoding
    story changes.
16. **Docs polish:** `references/update-interview.md` is ~2.1K tokens
    (decide whether a sixth reference is worth it); test-docstring overclaims
    in the asset/dossier tests.
17. **CI hardening:** `timeout-minutes`, `concurrency`, pip cache; run `ruff`
    and `mypy` (installed but never run); strip trailing whitespace in
    `ci.yml`.
18. **Distribution decision:** whether zip/directory installs are supported
    (untracked `__pycache__` would travel; a clean script or packaging step if
    so). Git-based installs are clean.

## Future capability

19. **Additional skills.** Chit-chat, the wider speech-extension surface, and
    space chatter are planned as further skills under `skills/`. When the
    second skill arrives, make the script-sharing decision (shared library,
    promoted service, or stamping build). The founding spec's "Adding a
    second skill" section is the starting point.
20. **Promote the facts layer to a standalone capability** only if a second
    consumer appears. Do not build it speculatively.

## Release gates

1. **(gate) First GitHub Actions run** — never executed on real Actions.
2. **(gate) Live human-gated run** — `docs/live-run-checklist.md` end-to-end
   on the real machine (blank-dir bootstrap, new system, update of an
   existing system, listening checks, in-game test + database upload).
3. **(gate) Publish** — decide GitHub owner/visibility, replace the
   `<your-github-owner>` placeholder, verify `npx skills add` and
   `npx skills update` in a real client. Then tag `v1.0.0`.

## Accepted decisions — do not re-open without new evidence

- Advisory gates; no state file; no MCP server; no build step (founding spec).
- Content root = CWD with env override; blank-directory bootstrap requires
  user confirmation; EDCoPilot root precedence env → config file → ask.
- Provenance format (including the historical package identifier and version
  `0.1.0`) is byte-parity-pinned; em dashes in commit subjects.
- Wire-protocol strings and the config filename are data, exempt from product
  identity rules.
- `add_all()` in content/definition commits is old-behavior parity; `init`
  alone stages selectively.
- Inara redirects are not followed (deliberate security deviation).
- Reference-internal bare-sibling links are an accepted deviation (they
  resolve; a resolution test guards them).
- Scripts are self-contained: rule data is package data; `assets/` is
  agent-facing only; `init` is a skeleton command; the agent copies and
  reviews the house rules (script/skill separation, 2026-11-11).
