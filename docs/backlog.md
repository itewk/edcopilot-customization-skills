# Backlog

Open work for this repository, split by release. Each item is a **seed for the
superpowers process**: when picked up, it starts with brainstorming (unless the
diagnosis is already complete and the fix is a small change), then a plan under
`docs/superpowers/plans/`, then subagent-driven execution.

Items marked **(gate)** must pass before tagging `v1.0.0` but are execution
gates, not code changes.

---

## Before 1.0 — bugs and issues to resolve

These are defects or misleading behaviour in the shipped product. One plan
covers them (see `docs/superpowers/plans/` — "pre-1.0 fixes").

1. **Journal directory discovery is hard-coded and silent when it misses.**
   `edcg/facts/journal.py:find_journal_dir()` checks per-platform candidates
   (`%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`, its
   OneDrive variant; the Steam/Proton and native Linux paths; the macOS
   Application Support path) and returns `None` when none contains
   `Journal.*.log` — so relocated Saved Games, second Steam libraries, or
   redirected OneDrive silently drop the player journal, the workflow's
   ground-truth source (`facts.py:380-392` proceeds with empty journal
   stations). Fix sketch: `EDCG_JOURNAL_DIR` override resolved first and
   validated for `Journal.*.log`; a `doctor` check reporting the resolved
   journal path as `OK`/`WARN`; a row in the environment-variable reference;
   tests for override-wins and missing-journal-warns.
2. **Bounds keys that name no tag kind are silently inert.** Live content
   showed 2 of 3 `*.rules.toml` files declaring `[content.bounds]` with
   snake_case keys (`system_greeting`, `station_chatter`, …) that never match
   `tag.kind` (`resolve_bounds` / `rule_content_bounds`). Station-level
   overrides warn; kind-level ones do not. Fix sketch: a warning finding for
   any bounds key that matches no known kind, at both kind and station
   sub-key level, with tests. Then correct the author's live rules files
   (requires human OK — they are content).
3. **`markdb` on a missing custom file has no dedicated message.** The
   unmatched-tag warning is suppressed when the file is absent, leaving only
   empty `modified_tags`/`commit_hashes`. Fix sketch: a clear error naming the
   missing path and the resolved EDCoPilot root.
4. **Exit-code semantics at the edges.** `check-logs` exits 0 when the
   EDCoPilot root is unresolvable (`ok:false` only in JSON); `branch finalize
   --push` exits 0 when the push is refused; `push_status` reads `"failed"`
   when `--push` had nothing to attempt. Decision (recorded): refused or
   unresolved actions exit 1, aligned with "1 = check failure"; `push_status`
   gains a distinct `nothing_to_push` value. Apply uniformly with tests.
5. **`Config.edcopilot_root` is a second authority with different semantics.**
   `load_config` copies the raw env value while consumers are supposed to use
   `resolve_edcopilot_root`. Fix sketch: remove the raw field if no caller
   remains, or make it the resolved value; migrate callers.
6. **`os.access(W_OK)` on Windows is unreliable** for the content-root
   writability check. Fix sketch: a probe write, or a documented best-effort
   with the failure mode named.
7. **Docs accuracy sweep (release-blocking polish).** CONTRIBUTING hardcodes
   suite counts that rot (currently `668`/`682` against 730 — remove the
   numbers); `references/update-interview.md` self-duplicating clause at the
   end of the skip/error paragraph and its error taxonomy listing two of three
   causes (missing declared system name is absent). The reference-internal
   bare-sibling link form is an accepted deviation (links resolve; covered by
   a resolution test) — do not churn it.
8. **Pin `skills-ref` in CI** to a commit or tag (currently the
   default-branch tip) — release reproducibility.

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
