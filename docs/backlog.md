# Backlog

Open work for this repository, in priority order. Each item is a **seed for
the superpowers process**, not a spec: when an item is picked up, it starts
with brainstorming, then a spec under `docs/superpowers/specs/`, then a plan
under `docs/superpowers/plans/`, then subagent-driven execution. Do not start
from this file directly.

Items marked **(gate)** must pass before tagging `v1.0.0`.

---

## Release gates

1. **(gate) First GitHub Actions run.** CI has only ever run locally; the
   workflow has never executed on Actions. Push to GitHub and confirm the
   pipeline is green (it is also the first proof of the `skills-ref` install
   step and the Windows runner assumptions).
2. **(gate) Live human-gated run.** Execute `docs/live-run-checklist.md`
   end-to-end on the real machine: blank-directory bootstrap, a new system,
   and an update of an existing system, including the listening checks and the
   in-game test + database upload step before markers are cleared.
3. **(gate) Publish.** Decide the GitHub owner/visibility, replace the
   `<your-github-owner>` placeholder in README, push, and verify
   `npx skills add <owner>/edcopilot-customization-skills` followed by
   `npx skills update` in at least one real client. Only then tag `v1.0.0`.

## Next small changes (approved, no spec/plan needed)

- ~~Help as the interface doc~~ — **done** (commit `refactor: make --help the
  interface documentation`): command table removed, Process carries commands
  inline, `--help` upgraded (flag help, worked examples with parse-locked
  tests, exit codes documented), flag-ownership guard extended to references.
- **Candidates from the using-scripts guide (awaiting go-ahead):** `--dry-run`
  flags for the stateful commands (`write-content`, `save-definition`, `init`)
  so an agent can preview state changes; an output-size policy for data
  commands (`get-content` on a large system is unbounded; `gather-facts` caps
  at 20 bodies) — default to a summary with a flag to request more.

## Product correctness

4. **Journal directory discovery is hard-coded and silent when it misses.**
   `edcg/facts/journal.py:find_journal_dir()` checks per-platform candidates
   (`%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous` and its
   OneDrive variant; the Steam/Proton and native Linux paths; the macOS
   Application Support path) and returns `None` when none contains
   `Journal.*.log`. There is no override and no diagnostics, so a relocated
   Saved Games folder, a second Steam library, or redirected OneDrive silently
   drops the player journal — the workflow's ground-truth source
   (`facts.py:380-392` proceeds with empty journal stations).
   Sketch: an `EDCG_JOURNAL_DIR` override resolved first and validated for
   `Journal.*.log`; a `doctor` check that reports the resolved journal path as
   `OK` or `WARN`; one row in the environment-variable reference; both tests
   (override wins, missing journal warns without failing).
5. **Bounds keys that name no tag kind are silently inert.** Live content
   showed 2 of 3 `*.rules.toml` files declaring `[content.bounds]` with
   snake_case keys (`system_greeting`, `station_chatter`, …) that never match
   `tag.kind` (`rules/validation.py` `resolve_bounds` / `rule_content_bounds`).
   The station-level analogue warns; the kind-level one does not. Sketch: a
   warning finding for any bounds key that matches no known kind (kind and
   station sub-key levels), with tests; then correct the live rules files.
6. **`markdb` on a missing custom file has no dedicated message.** The
   unmatched-tag warning is suppressed when the file is absent, leaving only
   empty `modified_tags`/`commit_hashes` in JSON. Sketch: a clear error or
   warning naming the missing path (and the resolved EDCoPilot root).
7. **`get_template` containment guard — RESOLVED.** `get_template` and the
   `get-template` command were removed (commit `refactor: drop the get-template
   pass-through command`); the agent reads
   `assets/dossier-template.md` directly, so the guard is moot.
8. **Exit-code semantics at the edges.** `check-logs` exits 0 when the
   EDCoPilot root is unresolvable (`ok:false` only in JSON); `branch finalize
   --push` exits 0 when the push is refused; `push_status` reads `"failed"` when
   `--push` had nothing to attempt. Decide one policy (exit non-zero on any
   refused action, or document JSON-only signalling) and apply it uniformly.
9. **`Config.edcopilot_root` is a second authority with different semantics.**
   `load_config` copies the raw env value while every consumer is supposed to
   use `resolve_edcopilot_root`. Sketch: remove the raw field or make it the
   resolved value, with callers migrated.
10. **Boolean parsing is narrower than the old implementation.** `_str_to_bool`
    rejects `t/y/f/n` (accepted by the old pydantic settings) and treats `""`
    as unset → default `True`. Decide whether parity matters here; test
    whichever answer is chosen.
11. **`os.access(W_OK)` on Windows is unreliable** for the content-root
    writability check. Sketch: a probe write or a documented best-effort.
12. **`update-scan` narrows the old change set** (no Inara/Spansh discrepancy,
    conflict or revision-delta counts). Optional enhancement, not parity debt:
    decide whether the update flow needs them.

## Test and hermeticity debt

13. Assertion-free or tautological tests: `test_extra_env_vars_ignored`,
    `test_env_var_prefix_is_edcg`, `test_smoke`'s folder-name assertion,
    `test_existing_root_not_rescaffolded` (asserts nothing about not writing).
14. Environment leaks: the stale-root test writes `os.environ` without
    `monkeypatch`; audit similar tests when touched.
15. Under-asserting ports: Task 3's non-repo warning test (no return-value or
    warning-category check), `GitRepo.push`'s new `True/False/None` returns
    (mocked at the caller, never asserted directly), the `branch e2e` review
    assertion (`"test" in output.lower()`), and `markdb`'s `[None]` no-commit
    return path.
16. "Matches the code" tests that hardcode strings instead of deriving them
    (commit subjects, token vocabulary) — they cannot catch drift. Sketch:
    read the code's constants or run the command and compare.
17. Fixture breadth: live-fixture tests skip both files when
    `systems/all.rules.toml` is absent (should run against base rules and
    report); a rules-less dossier is counted as "not validated" rather than
    parsed; provenance is asserted before the skip decision in the round-trip
    test; station-level bounds sub-keys are not covered by the inert-kind
    report; byte-exactness is proven against a test-local renderer rather than
    the production writer.
18. `_section` helper raises `ValueError` with a weak message instead of a
    clear assertion when an anchor drifts.
19. Test-docstring overclaims (e.g. "every zero-iteration table keeps its
    header" while checking headings only; placeholder inventory missing two
    scalars).
20. Help-surface blind spots (from the help-task review): the argument-help
    walker cannot see per-subcommand `help=` (a future `add_parser` without
    help passes silently); the guarded-flag count bound is `>= 7` against an
    inventory of 12 (wide margin); epilog examples spell `python edcg.py …`
    while SKILL.md documents `python <skill-dir>/scripts/edcg.py …` from the
    content root (not copy-paste runnable); the root epilog's command-group
    block omits `version`; `validate-definition`/`validate-content` (read-only,
    JSON stdin) carry no worked example.
21. Help example encoding: epilog examples are ASCII (`<harness> (<models>)`)
    because a literal 🤖 crashes redirected cp1252 stdout — deliberate; revisit
    if the console-encoding story changes.

## Documentation debt

20. **CONTRIBUTING hardcodes suite counts that rot** (currently `668`/`682`
    against a 713-test suite). Remove the numbers or derive them from a run.
21. `references/update-interview.md`: self-duplicating clause at the end of the
    skip/error paragraph; the error taxonomy lists two of three causes (missing
    declared system name is absent); Phase 7 "in place" vs `save-definition`
    "overwrites both files" needs one clarifying clause; one ~150-column line.
22. Docstrings that outlived their wording: `repo/dossier.py` subject-format
    docstring; `repo/logs.py` cycle vocabulary; audit any remaining
    "nothing refuses" absolutes in module docstrings (SKILL.md was corrected).
23. **Resolved.** `assets/all.rules.toml.example` said the base rule set lived
    at `rules/base.toml in the installed package`; it was `assets/base.toml` in
    the skill, and is now `scripts/edcg/rules/data/base.toml`.
24. Reference-internal links use bare sibling filenames (correct on disk) while
    the spec's recommendation is root-relative paths. Align or record the
    deviation.
25. `references/update-interview.md` is ~2.1K tokens, marginally over the
    split guidance; decide whether a sixth reference is worth it.

## CI, packaging and hygiene

26. Pin `skills-ref` to a commit or tag (currently the default-branch tip).
27. CI hardening: `timeout-minutes`, `concurrency`, pip cache; run `ruff` and
    `mypy` (already installed by `requirements-dev.txt` but never run); strip
    trailing whitespace in `ci.yml`.
28. Distribution hygiene for non-git installs: untracked `__pycache__`
    directories embed absolute paths and would travel in a zip copy. Decide
    whether zip/directory distribution is supported and add a packaging step or
    a clean script if so.

## Future capability

29. **Additional skills.** Chit-chat, the wider speech-extension surface, and
    space chatter are planned as further skills under `skills/`. When the
    second skill arrives, make the script-sharing decision (shared library,
    promoted service, or stamping build) — the layering was designed for it.
    The founding spec's "Adding a second skill" section is the starting point.
30. **Script / skill separation — planned, full spec/plan route (human
    decision).** Inside the skill folder, the boundary is *what the code needs
    to run* vs *what the agent needs to read*:
    - Move `base.toml`, `build_types.toml`, `raven.toml` from `assets/` into
      package data under `scripts/edcg/rules/`, loaded module-relative — no
      `parents[3]` counting, no skill-layout coupling. Scripts become
      self-contained.
    - `assets/` becomes agent-facing only (`dossier-template.md`,
      `all.rules.toml.example`).
    - `init` creates only the skeleton (git, config file, `systems/`). **The
      agent** copies `assets/all.rules.toml.example` → `systems/all.rules.toml`
      (human decision), and the setup flow gains a review step: walk the user
      through the house rules to modify/add/remove before any content work.
31. **Promote the facts layer to a standalone capability** only if a second
    consumer appears (e.g. another skill or project needs Raven/journal
    facts). Do not build it speculatively.

## Accepted decisions — do not re-open without new evidence

- Advisory gates; no state file; no MCP server; no build step (founding spec).
- Content root = CWD with env override; blank-directory bootstrap requires
  user confirmation; EDCoPilot root precedence env → config file → ask.
- Provenance format (including the historical package identifier and version
  `0.1.0`) is byte-parity-pinned; em dashes in commit subjects.
- Wire-protocol strings and the config filename are data, exempt from product
  identity rules.
- `add_all()` in content/definition commits is old-behavior parity (the
  legacy writer staged everything); `init` alone stages selectively.
- Inara redirects are not followed (deliberate security deviation).
