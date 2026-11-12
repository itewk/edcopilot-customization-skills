# Maintainability and Simplification Proposals — `edcg` and its test suite

**Date:** 2026-11-12
**Status:** PROPOSAL — awaiting human accept/reject decisions; not authorized work
**Review method:** Independent maintainability review with fresh context. Read every module under `skills/edcopilot-system-content/scripts/edcg/` (`common/`, `facts/`, `rules/`, `content/`, `repo/`, `cli.py`) and the whole `tests/` tree; measured duplication and dead code by cross-referencing imports and call sites with `Select-String`, ran `python -m ruff check` for lint-level evidence, and ran the suite at HEAD for a baseline: **759 passed, 10 deselected, 4 warnings in 148s**. **Model used:** DeepSeek V4.1 Flash (OpenCode Go). No code was modified; this document is the only change.
**Scope:** duplication, over-complexity, inconsistent patterns, test-suite simplification, coupling that hurts change. No new features and no standards conformance (a separate reviewer covers those). The accepted decisions in `docs/backlog.md:113-129` are treated as fixed constraints, not as proposals.

## Global Constraints

Every accepted proposal is implemented under these constraints:

- **Behaviour is unchanged.** Same CLI JSON payload keys and casing, same exit codes (0/2 for usage), same commit message subjects and trailers, same provenance bytes (including the pinned `0.1.0` identifier), same file line endings, same validation findings, same root-resolution precedence (env → config file → ask).
- **The suite stays green.** `python -m pytest -q -m "not integration"` must be 759 passed / 10 deselected before and after each item; an item whose test rewrite changes the count says so in its own section.
- **One item per commit,** conventional-commit subject, with the `Models:` and `Co-authored-by:` trailers this repo requires.
- **No new runtime dependency, no build step, no second-skill shared library.** `common/` stays stdlib-only; `httpx`/`gitpython` remain the only third-party runtime imports.
- **Accepted decisions are not re-opened:** advisory gates, no state file, no MCP server, `add_all()` parity in content and definition commits, byte-pinned provenance, rule TOMLs as package data, branch state derived from git, `assets/` agent-facing only.
- **Deleted code takes its tests with it.** No proposal leaves an orphan test asserting a function that no longer exists, and no proposal deletes a test that still guards a behaviour.
- **Help text, epilogs and worked examples are untouched.** `tests/test_cli/test_help.py` is the guard; it must stay green.

**Effort legend:** **S** = well under a day, one or two files, mechanical; **M** = a day or two, several files, test rewriting included; **L** = more than two days. No proposal here is L.

## How the ranking works

Ranked by *maintainability payoff per unit of effort*: how much future work stops being surprising, divided by how much it costs now. The top of the list is where a change today is cheap and the cost of not doing it compounds.

| # | Proposal | Effort | Payoff |
|---|---|---|---|
| 1 | One content root on `Config`; delete dead config surface | S | High |
| 2 | One module for content-repository layout and constants | S/M | High |
| 3 | Delete the branch layer's compatibility aliases and process mirrors | S | High |
| 4 | One HTTP transport for the three API clients | M | High |
| 5 | Extract dossier document parsing out of `rules/validation.py` | M | High |
| 6 | Delete production API whose only consumer is the test suite | M | High |
| 7 | `GitRepo`: context manager, one default-branch answer | S | High |
| 8 | `review_branch`: one diff-stats helper, no `_repo` poking | S | Medium-high |
| 9 | One JSON emission path; one `WriteResult` | S | Medium |
| 10 | Landability and vocabulary declared once | S | Medium |
| 11 | Facts layer: one site record, one comparison helper | S/M | Medium |
| 12 | `markdb`: one pass, no vestigial parameters | S | Medium |
| 13 | `cli.py`: one dispatch mechanism | S | Medium |
| 14 | `_extract_stations_from_section_7`: one parser, no dead branch | S | Medium |
| 15 | Tests: shared fixtures in `conftest.py` | M | Medium |
| 16 | Tests: delete what asserts nothing, stop writing into the repo | S | Medium |

---

### 1. One content root on `Config`; delete dead config surface

**Problem — evidence.** `Config` carries the same directory twice: `content_definitions_root` and `content_root` (`common/config.py:53-54`), assigned from one local at `:189-190`. Callers then pick either: `content_root` at `content/custom_file.py:90`, `content/markdb.py:25`, `content/rewrite.py:99`, `:170`, `cli.py:601`; `content_definitions_root` at `repo/brief.py:39`, `:48`, `:60`, `:253`, `repo/dossier.py:54`, `content/rewrite.py:51`, `rules/validation.py:1337`, `repo/branches.py:135`, `:324`, `:421`, `:684`, `cli.py:642`. `tests/test_common/test_config.py:308-309` asserts the two fields are equal, which pins the duplication in place.

Dead surface in the same file: `deepl_api_key` (`:61`, `:195`) and `log_level` (`:18`, `:63`, `:197` plus `DEFAULT_LOG_LEVEL`) have no reader anywhere; `read_stored_root` (`:301-304`) has no caller; `write_stored_root` (`:312-362`) plus its helpers `_toml_string`, `_ROOTS_HEADER`, `_EDCOPILOT_KEY` (`:20-23`, `:307-309`) have no caller; and there are two `get_config` functions with different behaviour (`common/config.py:201-207` versus `repo/dossier.py:16-18`).

**Proposed change.** Keep `content_definitions_root` (it already has ~20 production call sites) and delete `content_root`; update the five production sites, `tests/test_common/test_config.py:308-309`, and the `Config(...)` construction at `tests/test_repo_layer/test_save_definition.py:112-116`. Delete `deepl_api_key`, `log_level` and `DEFAULT_LOG_LEVEL`. Delete `read_stored_root`. Delete `write_stored_root` and its three helpers — *unless* a planned command will store `roots.edcopilot`, in which case keep it and add the test that calls it; dead code that nothing exercises is not an asset. Delete `repo/dossier.py:16-18` and import `get_config` from `common.config`; replace the eleven direct `load_config(os.environ)` calls with `get_config()` (identical behaviour, one name). This keeps `tests/test_repo_layer/test_save_definition.py`'s `patch("edcg.repo.dossier.get_config")` working, because the patched name remains a module attribute.

**Why it matters for maintainability.** Two names for one directory means every new module guesses, and the next person to "fix" root handling fixes half of it. Dead fields are worse than missing ones: a reader implements against `config.log_level` and only finds out at runtime that nothing honours it. The test at `test_config.py:309` turns a bug (the fields must agree) into a requirement.

**Done when:** `Select-String content_root` finds only `content_root_state` and `resolve_content_root`; suite green.

- [x] Accept
- [ ] Reject

---

### 2. One module for content-repository layout and constants

**Problem — evidence.** The same three questions are answered in several places:

- **"Where is EDCoPilot's custom file?"** four times, with two different failure behaviours: `content/custom_file.py:82-96` (`_custom_file_path`, raises `FileNotFoundError`), `content/markdb.py:22-31` (`_resolve_custom_file`, byte-identical body), `content/rewrite.py:98-105` (raises) and `content/rewrite.py:169-174` (returns `{"tags": []}` when the root is unresolvable — the same condition, a different answer).
- **"Where is the systems directory?"** built by hand at `cli.py:336`, `common/config.py:226`, `repo/brief.py:60`, `:253`, `repo/dossier.py:55`, `rules/validation.py:1337`; and two path helpers already duplicate each other: `repo/brief.py:36-51` versus `content/rewrite.py:48-54`.
- **`slugify`** lives in `content/rewrite.py:29-45` (a rewrite module) and is imported by `repo/brief.py:17` and `repo/dossier.py:11`.
- **Constants:** the custom-file name literal is respelled at `repo/branches.py:387` and `:396` instead of using `CUSTOM_FILE_NAME`; `PROVENANCE_RE` is defined twice, identically (`content/custom_file.py:27`, `rules/validation.py:34`).

**Proposed change.** Add `edcg/common/layout.py` (stdlib only) owning file locations *within* a root — root resolution stays in `config.py`:

- `CUSTOM_FILE_NAME`, `PROVENANCE_RE`
- `slugify(name) -> str` (moved unchanged)
- `systems_dir(config) -> Path`
- `dossier_path(config, system_name) -> Path`, `rules_path(config, system_name) -> Path`
- `resolve_custom_file(env=None) -> tuple[Path, Config]`, raising one exception (`FileNotFoundError`) with the message `custom_file.py:92-95` already uses

Then delete `_custom_file_path`, `_resolve_custom_file`, both inline copies in `rewrite.py`, `brief.system_rules_path`/`brief.dossier_path`, `rewrite._system_rules_path`, the six hand-built `"systems"` paths, and both duplicate `PROVENANCE_RE` definitions (import from `common.layout`). `get_system_content` keeps its empty-payload answer by catching the one exception — the policy stays at the call site, the resolution becomes single. Watch for an import cycle: `layout` imports `config`, nothing imports `validation`, so `validation` may import `layout` at module level and the local `from edcg.common.config import load_config` at `validation.py:1335` disappears.

**Why it matters for maintainability.** The missing-root case is already answered three different ways, so the next content command will invent a fourth. Every consumer currently re-derives the repository's shape, which is why "change where systems live" is a six-file edit and why a `slugify` change risks a mismatch between the file `save_definition` writes and the file `writing_brief_data` reads.

**Done when:** `grep -c '"/ "systems"'` returns one non-test site; `get-content` and `rewrite-tag` behaviour on a missing root is unchanged (existing tests in `test_rewrite_content.py`, `test_content_rewrite.py`).

- [x] Accept
- [ ] Reject

---

### 3. Delete the branch layer's compatibility aliases and process mirrors

**Problem — evidence.** `repo/branches.py` keeps process state that its own comment says is never consulted: `_active_branch` and `_branch_systems` (`:31-32`) are set at `:404-405`, `:556-557`, `:664-665` and read for no decision; `branch_status` even declares `global` without assigning (`:417`, flagged by ruff as `PLW0602`). `_branch_systems` is only ever assigned `set()`, so `systems_affected` (`:464`) and its aliases are structurally always empty, and the CLI emits three empty arrays per `branch status` call (`cli.py:705-710`).

On top of that, 19 dataclass fields are aliases of other fields in the same object (four of them derived booleans), populated in `__post_init__`: `BranchResult` 6 of 11 (`:194-198`, `:204-216`), `BranchStatus` 8 of 19 (`:224-242`, `:244-253`), `FinalizeResult` 3 of 12 (`:267-270`, `:272-278`), `AbortResult` 2 of 10 (`:291-293`, `:295-299`). One payload therefore reports the active branch as `active_branch`, `active_branch_name`, `content_current_branch`, `content_branch` and `content_branch_name`.

**Proposed change.** Delete the two module globals and the `_branch_systems`-derived fields (`systems_affected`, `affected_systems`, `systems`). Delete the alias fields, keeping the one name per concept that the CLI and tests actually read (`active_branch`, `content_current_branch`, `runtime_current_branch`, `content_status`, `runtime_status`, `uncommitted_changes`, `content_uncommitted`, `runtime_uncommitted`, `has_uncommitted_changes`, `foreign_checkout`; `merge_commits`, `content_merge_commit`, `runtime_merge_commit`, `merge_errors`, `failed_repos`, `pushed`, `push_status`, `message`; `discarded_branch`, `would_discard`, `discarded`, `discarded_commits`, `content_discarded`, `runtime_discarded`, `confirmed`, `message`). No test and no CLI consumer reads an alias key — verified across `tests/`.

**Why it matters for maintainability.** An API that says the same thing six ways forces every consumer to pick a key and the next author to guess which one is canonical. Worse, the mirror is a lie: tests can set `_active_branch` and see nothing happen (see proposal 16), which teaches the reader a false model of how state works. Branch state comes from git; delete the pretence.

**Done when:** suite green; `branch status` payload contains exactly one key per concept; `tests/test_repo_layer/test_branches.py:20-28`, `:59-67`, `:88-99`, `:102-113`, `:116-130`, `:133-149` are deleted with the mirror they test (see 16).

- [x] Accept
- [ ] Reject

---

### 4. One HTTP transport for the three API clients

**Problem — evidence.** `RavenClient` (`facts/raven.py:155-256`), `SpanshClient` (`facts/spansh.py:60-167`) and `InaraClient` (`facts/inara.py:46-186`) each implement the same lifecycle: `__aenter__`, `__aexit__`, `_ensure_client`, `close`, `_rate_limit_wait`, `_request_with_retry` — roughly 85 duplicated lines each, including an identical exponential-backoff loop and an identical three-branch error message block. The differences are small and already expressible as parameters:

- redirects: `spansh.py:109` and `raven.py:198-200` follow, `inara.py:107-110` does not (deliberately — the API key is in the POST body);
- 429 retry: only `inara.py:170`;
- a `User-Agent` header only on `spansh.py:110`;
- request shape: `raven`/`spansh` pass `method` + `url`, `inara` POSTs JSON to `base_url` (`inara.py:150-158`).

**Proposed change.** Add `edcg/facts/_http.py` with an `ApiClient` base that owns `_client`, `_rate_lock`, `_last_request_time`, the context manager, `close()`, `_rate_limit_wait()` and `_request_with_retry()`; per-client configuration is a class attribute (`error_type`, `follow_redirects`, `retry_statuses`, `default_headers`, `user_agent`). Each client keeps only its URL building and response parsing. Keep the three exception classes (callers catch `RavenAPIError`/`SpanshAPIError`/`InaraAPIError` by name and tests import them) but derive them from one `ApiError` base so the transport can raise `self.error_type`.

**Why it matters for maintainability.** Retry, backoff and rate limiting are one policy, currently maintained in three places with three subtly different behaviours. The next fix — a timeout, a `Retry-After` header, a jittered backoff — must land three times or will silently apply to one source. The existing client tests (`test_raven.py`, `test_spansh.py`, `test_inara.py`, ~1000 lines) already pin the observable behaviour, so a mechanical consolidation is well protected.

**Done when:** `test_raven.py`, `test_spansh.py`, `test_inara.py` pass unchanged; no client module contains `asyncio.sleep`, `httpx.AsyncClient` or `raise_for_status`.

- [x] Accept
- [ ] Reject

---

### 5. Extract dossier document parsing out of `rules/validation.py`

**Problem — evidence.** `repo/brief.py:19-29` imports seven names from `rules/validation.py`, five of them private: `_parse_dossier_sections`, `_extract_site_table`, `_extract_stations_from_section_7`, `_extract_voices_from_section_8`, `_get_landable_build_types`, `_normalize_station_name`. Those functions are dossier-markdown parsing (`validation.py:1452-1698`, ~250 lines) and have nothing to do with validating speech content. `validation.py` is 1748 lines and mixes six jobs: rule-data loading (`:242-388`), content parsing (`:395-476`), eighteen rule implementations (`:525-962`), summary rendering (`:1105-1173`), two orchestration functions (`:1176-1445`, `:1751-1954`), and dossier parsing (`:1452-1698`).

**Proposed change.** Add `edcg/rules/dossier.py` holding `DOSSIER_SECTIONS`, `SECTION_RE`, `parse_sections`, `extract_site_table`, `extract_voices`, `extract_coverage_stations`, `normalize_station_name` and their private helpers — public names, because they now have consumers outside the module. `validation.py` and `repo/brief.py` import from it; nothing imports a leading underscore across a module boundary afterwards. Optional follow-on in the same series: move `validate_definition` (`:1751-1954`) to `rules/definition.py`, leaving `validation.py` as content rules only (still ~1250 lines, but with one subject).

**Why it matters for maintainability.** A cross-module private import is coupling the tooling cannot see: rename `_extract_site_table` and the failure is an `ImportError` at CLI start-up, not a test failure in the module that owns the name. It also means "where do I change how a dossier is read?" has a surprising answer today (`rules/validation.py`), which is exactly the kind of question a new contributor asks on day one.

**Done when:** `Select-String "from edcg.rules.validation import"` shows no leading-underscore name; suite green; live-fixture tests (`tests/test_integration/test_live_fixtures.py`) unchanged.

- [x] Accept
- [ ] Reject

---

### 6. Delete production API whose only consumer is the test suite

**Problem — evidence.** Four blocks of shipping code exist only to be tested:

1. **`rules/engine.py` parallel rule API.** Production imports exactly four names from this module (`facts.py:18`, `audit.py:54`): `is_landable_build_type`, `get_facility_class`, `get_facility_name`, `get_placement`. Everything else — `get_base_rules` (`:27`), `get_raven_config` (`:43`), `get_vocab` (`:51`), `get_kinds` (`:56`), `get_filters` (`:61`), `get_landable_build_types` (`:80`), `load_system_rules` (`:136`), `load_house_rules` (`:142`), `merge_rules` (`:148-170`) — is called only from `tests/test_rules_layer/test_rules_loading.py` and `test_data_loading.py`. `engine.merge_rules` has the same name as `validation.merge_rules` (`validation.py:358`) and different parameters and precedence rules. `get_raven_config` reads `raven.toml`, which says of itself: "Nothing reads this file yet" (`rules/data/raven.toml:6`).
2. **`RuleEngine` and `validate()`.** `validation.py:1176-1278` plus the wrapper at `:1285-1294` and its private `load_system_rules` at `:308-322`. No production caller — the CLI uses `validate_content`/`validate_definition`. It is a second orchestration of load → merge → parse → run → sort → summarise, already divergent from the used one (it merges per-system overrides through `merge_rules` rather than through `Context.rule`, and does not apply the block offset logic).
3. **`SpanshClient.search_systems` + `_parse_search_result`** (`spansh.py:284-345`). Only `test_spansh.py` calls it; `facts.py` uses `get_system` alone.
4. **`ValidationResult.rule_table` and `_render_rule_table`** (`validation.py:142`, `:1151-1173`, computed at `:1277` and `:1444`). The CLI omits it (`cli.py:107-120`) and `tests/test_cli/test_dispatch.py:197` asserts it is absent — so every validation run builds a Markdown table and throws it away.

**Proposed change.** Delete (1) except `get_build_types`/`_get_all_build_types` and the four used lookups (make the data loader private, keep `__all__` to four names). Delete (2), keeping the module-level `validate_content`/`validate_definition` as the only entry points. Delete (3) and its three tests. Delete (4). Rewrite the affected tests behaviourally: keep the assertions that pin **rule data** (kinds, vocab, filters, build types) by reading through `validation.load_base_config(RULE_DATA_DIR)` or `engine.get_build_types()`; drop the classes that exercise the loader/merge duplicates. `test_validation.py`'s five `RuleEngine` call sites (`:60-62`, `:386`, `:465-469`, `:1210`, `:1219`) become `validate_content`/`validate_definition` cases.

**Why it matters for maintainability.** This is the largest single source of "which of these two functions is the real one?" in the codebase, and it inflates the surface a reader must understand before changing anything in validation. The rule data tests that survive are the valuable half: they assert the TOMLs, which is where the product decisions live. Note the count change: this item removes tests, so the suite total will fall — the item's commit message should state the new baseline.

**Done when:** `engine.__all__ == ["get_build_types", "is_landable_build_type", "get_facility_class", "get_facility_name", "get_placement"]` (or the loaders made private); `grep -r "RuleEngine\|search_systems\|rule_table" skills/` returns nothing; remaining tests green.

- [x] Accept
- [ ] Reject

---

### 7. `GitRepo`: context manager, one default-branch answer

**Problem — evidence.** `repo/branches.py` repeats the same four-line dance fifteen times: `if _is_repo(root): repo = GitRepo(root); try: … finally: repo.close()` (`:141-147`, `:151-156`, `:182-186`, `:328-332`, `:339-355`, `:365-380`, `:431-435`, `:438-442`, `:487-492`, `:519-554`, `:606-619`, `:639-662`, `:694-721`, `:729-753`), because `GitRepo` (`repo/gitrepo.py:35-100`) has no context-manager protocol. "What is the default branch?" has three implementations: `GitRepo.default_branch` (`gitrepo.py:424-437`), `_default_branch_for(repo)` (`branches.py:101-119`) and `_default_branch_of(root)` (`branches.py:178-186`) — the latter two wrapping the first. The instance registry `GitRepo._instances` plus `__del__` and an `atexit` hook (`gitrepo.py:42-43`, `:55`, `:74-75`, `:77-85`, `:441`) exists solely because closing is manual, and grows unbounded when a caller forgets.

**Proposed change.** Add `__enter__`/`__exit__` returning `self`/`None` and keep `close()` idempotent. Replace the fifteen blocks with `with GitRepo(root) as repo:`. Fold `_default_branch_for`/`_default_branch_of` into `GitRepo.default_branch()`, which already implements the union (prefer an existing branch, fall back to `symbolic_ref`, then `main`), and drop the `try/except` around `list_branches` — `list_branches` already returns `[]` on failure (`gitrepo.py:413-422`) and emits no warning because `_require_repo` has already checked. Once no manual `close()` remains, delete `_instances`, `__del__`, `_cleanup_all` and the `atexit` registration.

**Why it matters for maintainability.** Every new git-touching feature must remember a four-line dance whose omission leaks a file handle on Windows — the platform this runs on. A `with` block is the shape every Python reader expects, and one default-branch function removes the "which one do I call?" question in a file that already has 20 functions.

**Done when:** suite green, including `tests/test_repo_layer/test_branches.py` and `test_gitrepo.py`; `grep -c "repo.close()"` in `branches.py` is zero.

- [x] Accept
- [ ] Reject

---

### 8. `review_branch`: one diff-stats helper, no `_repo` poking

**Problem — evidence.** `branches.py:689-721` and `:723-753` are the same thirty lines applied to the content repository and then to the runtime repository, including four copies of the `+/−` counting loop (`:700-706`, `:713-717`, `:733-739`, `:745-749`). The wrapper's internals are reached from the layer above: `repo._repo.git.merge` (`:533`, `:542`), `repo._repo.git.diff` (`:710`, `:712`, `:742`, `:744`), and `getattr(repo, "_repo", None)` twice (`:610`, `:652`). `GitRepo.merge` (`gitrepo.py:367-382`) exists and `finalize_branch` does not use it.

**Proposed change.** One `_diff_stats(repo, default) -> {"files", "insertions", "deletions"}` used for both repositories. Add `GitRepo.diff_stat(ref=None)` and `GitRepo.delete_branch(name)` (and use the existing `merge`) so `branches.py` stops speaking GitPython; the `getattr(repo, "_repo", None)` guards then delete themselves. `review_branch` becomes: gather two stat dicts, format one report.

**Why it matters for maintainability.** The wrapper exists so callers do not speak GitPython; today its biggest caller does, which means a GitPython upgrade breaks in `branches.py` while the wrapper looks like the right place to fix it. The duplication also means a bug in the counting loop is fixed once and missed once.

**Done when:** `grep "_repo" repo/branches.py` returns nothing; `branch review` output is byte-identical for the same working tree (capture before/after on a temp repo).

- [x] Accept
- [ ] Reject

---

### 9. One JSON emission path; one `WriteResult`

**Problem — evidence.** `cli.py` shapes output four ways: `_validation_dict` (`:107-120`), `_facts_dict` (`:374-450`), `asdict(result)` (`:701`, `:706`, `:717`, `:728`) and `report.to_dict()` (`repo/audit.py:92-122`), even though `_json_default` (`cli.py:68-75`) already handles `Path`, `set` and dataclasses. `command_write_content` (`:529-545`) emits `"paused": getattr(result, "paused", False)` and `"ask_user": getattr(result, "ask_user", None)` — keys that belong to the *other* `WriteResult`, the unused dataclass at `rules/validation.py:152-159`; the live one (`content/custom_file.py:30-39`) has two fields. So the CLI emits two keys that can never hold anything but `False`/`None`, guarded by `getattr` defaults that hide the mismatch.

**Proposed change.** Make `_json_default` render `datetime` as `isoformat()`; delete `AuditReport.to_dict` and emit `asdict(report)`; delete `_validation_dict` and emit `asdict(result)` with `rule_table` removed (or gone entirely, per proposal 6); delete `rules/validation.py::WriteResult` and the two `getattr` keys. Keep `_facts_dict` as-is and add one line of docstring saying it is a *projection*, not a renderer — it deliberately omits `raven_sites`/`journal_data`/`inara_stations`/`spansh_stations` and caps `station_bodies` at `_MAX_STATION_BODIES` (`cli.py:47`, `:435-439`), which `asdict` cannot express.

**Why it matters for maintainability.** One encoder means a new result type is emitted correctly by default; today an author who copies the wrong helper silently gets `str()` for every datetime. The dead `WriteResult` is a trap: it documents fields the function does not have, and the `getattr` defaults in the CLI keep the mismatch from ever failing.

**Done when:** `test_cli/test_dispatch.py` key-set assertions are unchanged and green (notably `:208`); one `WriteResult` exists; `grep getattr cli.py` returns nothing.

- [x] Accept
- [ ] Reject

---

### 10. Landability and vocabulary declared once

**Problem — evidence.** "Is this site landable?" has four answers: `engine.py:80-89` (landable = class not in `("hub", "installation")`), `engine.py:92-99` (the same check, duplicated per build type), `validation.py:1575-1584` (`_get_landable_build_types` = classes `starport`/`outpost`/`settlement`), and `validation.py:757-758` (reads `not_landable_classes` from the rule TOML, with a hardcoded default). `rules/data/base.toml` already declares `not_landable_classes = ["hub", "installation"]`, so the code constants shadow the data. Adding a sixth facility class would change one, two or none of these depending on how it is added.

The vocabulary has the same shape: `_extract_voices_from_section_8` hardcodes ~33 token names (`validation.py:1593-1601`) that already live in `base.toml` `[vocab]`, with `"fuellevels"` listed twice (ruff `B033`), while `Context.known_tokens()` (`validation.py:226-230`) reads the same list from the data.

**Proposed change.** One predicate reading the rule data: `is_landable_build_type(build_type)` = the build type's class is not in `base["rules"]["content"]["station_landable"]["not_landable_classes"]` (defaulting to `["hub", "installation"]` only if the key is absent). `_get_landable_build_types()` becomes `{bt for bt in build_types if is_landable(bt)}`. Voice extraction takes the known-token set as an argument, supplied from `ctx.base["vocab"]` / `Context.known_tokens()`.

**Why it matters for maintainability.** The TOMLs are the repo's source of truth for rule data and already have tests guarding their contents; every code constant that re-states them is drift the data tests cannot catch. The duplicate `"fuellevels"` is a small proof that this list is not maintained carefully in code.

**Done when:** `grep -c '"hub", "installation"'` in `skills/` returns one; `test_rules_loading.py`'s remaining landability assertions still pass; suite green.

- [x] Accept
- [ ] Reject

---

### 11. Facts layer: one site record, one comparison helper

**Problem — evidence.** `LandableStation` (`facts/facts.py:52-66`) and `NonLandableSite` (`:68-82`) have the same nine fields and differ only in the `is_landable` default; `gather_facts` branches into two near-identical constructions (`:465-490`), then repeats the pair of loops for journal matching (`:496-509`) and again for lost stations (`:730-743` versus `:796-808`). `_compare_inara` (`:827-848`) and `_compare_spansh` (`:850-871`) are the same loop over a different field list — and those two field lists duplicate the attribute names of `InaraSystem`/`SpanshSystem`.

Three renderings enumerate the same eleven diff fields by hand and must be edited together: `format_for_llm` (`:177-261`), `present_changes` (`:280-335`), `has_changes` (`:263-278`). Two of them have no production caller — `repo/brief.py:294-339` projects the diff into JSON itself, and only `has_changes` is used (`brief.py:337`); `format_for_llm`/`present_changes` are kept alive by `tests/test_facts_layer/test_facts.py:1438-1513`.

**Proposed change.** One `Site` dataclass with `is_landable: bool` (keep the two old names as thin, non-duplicating aliases only if a downstream type hint needs them) and one construction path. One `_compare_fields(existing: dict, new: object, fields: list[tuple[str, str]]) -> list[SourceAttribution]` shared by the Inara and Spansh comparisons. Delete `format_for_llm` and `present_changes` with their tests; keep `has_changes`.

**Why it matters for maintainability.** Adding a fifth source currently means editing three hand-maintained enumerations inside a dataclass plus a fourth comparison function — and the audit reads `SystemFacts` field names directly (`repo/audit.py:280-350`), so a rename already crosses modules.

**Done when:** `test_facts.py` and `test_audit.py` green with the renderer tests removed; the diff JSON from `update-scan` is unchanged (`test_dispatch.py:364`).

- [x] Accept
- [ ] Reject

---

### 12. `markdb`: one pass, no vestigial parameters

**Problem — evidence.** `markdb_add` (`markdb.py:61-133`) and `markdb_remove` (`:136-202`) are the same ~70 lines; the only functional difference is `lines.insert(i + 1, "UPDATEDB\n")` (`:115`) versus `lines.pop(i + 1)` (`:185`). Both accept `system_name: Optional[str] = None`, documented as "Unused; kept for call-site compatibility" (`:64-77`, `:139-152`); the CLI (`cli.py:607-610`) and every test omit it.

**Proposed change.** One `_apply_markers(tags, *, add: bool, commit_co_author) -> dict` containing the scan, the single file write and the single commit; `markdb_add`/`markdb_remove` become one-line wrappers so the CLI and tests keep their names. Delete the `system_name` parameter.

**Why it matters for maintainability.** Two copies of a line-scanning loop with file-write and commit side effects is precisely where a divergence bug lives (one fixes the marker-fusing edge case at `:111-115` and the other misses it). An unused parameter with a comment excusing it teaches the reader that the API is bigger than it is.

**Done when:** `tests/test_content_layer/test_markdb.py` passes unchanged; `grep system_name markdb.py` returns nothing.

- [x] Accept
- [ ] Reject

---

### 13. `cli.py`: one dispatch mechanism

**Problem — evidence.** Dispatch uses three mechanisms in one function (`cli.py:1003-1034`): the `_HANDLERS` map (`:975-992`), a `"branch": None` sentinel (`:990`) routed through a second dict (`:994-1000`), and a third special case for `markdb` (`:1017-1021`) that validates what the parser could have enforced. `--system` is `required=True` for most commands (`:820`, `:842`, `:918`) but hand-checked for gather-facts (`:796`, then `:453-455`). Usage errors are printed ad-hoc to stderr (`:1014-1015`, `:1019`, `:1025`) instead of going through `parser.error`, so they differ in shape from argparse's own.

**Proposed change.** Give every subparser a handler via `set_defaults(func=...)` and dispatch with `args.func(args)`; the two handler dicts and the sentinel disappear. Make `gather_parser.add_argument("--system", required=True)` and delete the manual check. Set `markdb_subparsers.required = True` (3.12 supports it) and delete the special case. Replace the ad-hoc stderr lines with `parser.error(...)`.

**Why it matters for maintainability.** Adding a command currently means editing three places, and a missed entry fails at runtime rather than at import. `test_cli/test_help.py` already enumerates subcommands and epilog examples, so the change is guarded.

**Done when:** `test_help.py` and `test_dispatch.py` green; exit code 2 preserved for every usage error (`test_dispatch.py:9-13` and friends).

- [x] Accept
- [ ] Reject

---

### 14. `_extract_stations_from_section_7`: one parser, no dead branch

**Problem — evidence.** `validation.py:1635-1698` contains a branch that does nothing: `if not seen_stations_covered_header and in_stations_covered: pass` (`:1659-1662`). The "skip descriptive lines" predicate is written twice, verbatim (`:1666-1671`, `:1686-1691`); the station-splitting loop is written twice (`:1673-1678`, `:1692-1696`); and `seen_stations_covered_header` is only ever set inside the branch that also sets `in_stations_covered` (`:1650-1653`), so the "simple format" fallback it guards never runs in the shape it was written for.

**Proposed change.** Extract `_is_descriptive(line) -> bool` and `_parse_station_list(text) -> set[str]` (split on `·`/`•`/`,`, strip markdown, drop descriptive prefixes), and call one parser from both entry points. Delete the dead branch. Behaviour must be identical on the live fixtures — `test_integration/test_live_fixtures.py:208+` and `test_rules_layer/test_definition_validation.py` are the guard.

**Why it matters for maintainability.** This is the likeliest home of a future "coverage check missed a station" bug, and no reader can currently tell which of the two loops is authoritative. Verification is cheap because the live dossiers exercise it.

**Done when:** the function is under 25 lines; live-fixture tests unchanged and green.

- [x] Accept
- [ ] Reject

---

### 15. Tests: shared fixtures in `conftest.py`

**Problem — evidence.** `tests/conftest.py` is five lines (a `sys.path` insert) while 36 test files re-declare the same fixtures:

- `_git` (a subprocess runner) is defined **five times**: `test_cli/test_branch_e2e.py:9`, `test_cli/test_init.py:4`, `test_content_layer/test_markdb.py:10`, `test_content_layer/test_rewrite_content.py:6`, `test_repo_layer/test_branches.py:171`.
- `clean_env` twice (`test_cli/test_doctor.py:17`, `test_cli/test_init.py:5`); `_json` twice; `_lines` twice; `mock_config` twice with different meanings (`test_content_layer/test_markdb.py:6` versus `test_facts_layer/test_facts.py:31` — the latter is a bare `MagicMock`).
- `RULE_DATA_DIR` recomputed by hand three times with the same `parents[2]` expression: `test_rules_layer/test_validation.py:20`, `test_content_validation.py:30`, `test_content_bounds.py:11`.
- "A temporary git repo with one commit" is built four ways: `test_repo_layer/test_save_definition.py:80-107` (`tempfile.mkdtemp` + `subprocess` + `shutil.rmtree`, bypassing `tmp_path`), `test_repo_layer/test_branches.py:177-183` (`GitRepo.init` + `_git`), and each CLI file's own variant.
- Facts builders are re-declared per file: `test_repo_layer/test_audit.py:7-100` defines eight factories (`raven_system`, `raven_site`, `journal_station`, `journal_data`, `inara_system`, `inara_station`, `spansh_station`, `spansh_system`) that rebuild what `test_facts_layer/test_facts.py:40-84` already builds; the three AsyncMock client fixtures at `test_facts.py:40-64` have byte-identical bodies.

**Proposed change.** Move to `tests/conftest.py`: `rule_data_dir`, `git` (subprocess runner), `git_repo` (tmp_path-based factory returning a repo with a configured identity and one commit), `clean_env`, `api_clients` (the raven/inara/spansh AsyncMock trio). Move the facts builders to `tests/test_facts_layer/conftest.py`, where `test_facts.py`, `test_audit.py` and the client tests can share them. Delete the private copies. This is a mechanical move: no test changes what it asserts.

**Why it matters for maintainability.** 36 files each carrying their own idea of "a git repo" and "a clean environment" is why a suite-level change (stop shelling out to git, add an env var, use a different tmp root) is a 36-file edit today — and why the four repo builders already behave differently.

**Done when:** suite green, same pass count; `grep -c "def _git" tests/` returns one.

- [x] Accept
- [ ] Reject

---

### 16. Tests: delete what asserts nothing, stop writing into the repo

**Problem — evidence.** Five distinct patterns, each with a concrete site:

1. **Tests of the dead mirror** (proposal 3): `test_repo_layer/test_branches.py:20-28` resets module globals production never reads; `:59-67`, `:88-99`, `:102-113`, `:116-130` seed `_active_branch` to "simulate" state that cannot be observed; `:133-149` (`test_abort_tolerant_mocked_repo`) asserts only `r is not None`.
2. **White-box mock verification:** `test_repo_layer/test_save_definition.py:313-336` replaces `GitRepo` with a `MagicMock` and asserts `assert_called_once()` — it cannot fail if commits break. `:338-356` is named `test_save_definition_validates_dossier_and_rules` but asserts that invalid rules are saved anyway. `:359-360` is a `pytest.main()` block inside a collected module.
3. **A test that writes into the repository:** `test_rules_layer/test_validation.py:447-473` writes the shared fixture path `tests/fixtures/test.rules.toml` (`:455`, `:468`), leaving a checked-in file modified and making later runs order-dependent. The same test builds its real input under `tmp_path` already, so the write is pure accident.
4. **Dead fixtures:** `test_validation.py:47-51` defines `content_path` pointing at `tests/fixtures/test_content.txt`, which does not exist and which nothing uses; `:53-56` defines `dossier_path`, unused.
5. **Assertions that cannot fail for the right reason:** `test_validation.py:1168-1179` asserts `isinstance(result, ValidationResult)` and `hasattr(result, "findings")`; `test_facts_layer/test_facts.py:91-113` and neighbours assert that a dataclass returns its constructor arguments; `test_content_layer/test_write_content.py:112-113`, `:338`, `:372-373` assert `isinstance`/`is not None` immediately before the assertion that matters.

**Proposed change.** Delete (1) with proposal 3. Delete (2): the mocked-wrapper test and the misnamed one; keep a single behavioural test that the files land and the commit subject is right. Fix (3) by writing the rules file under `tmp_path` and pointing `systems_dir`/`system_rules_path` at it. Delete (4). For (5), either replace each `isinstance` block with one behavioural assertion (the file content, the finding, the counter) or delete the test if the behaviour is already covered.

**Why it matters for maintainability.** Tests are the specification a future maintainer reads. A test that passes when the feature is broken is worse than no test, and one that edits the repo working tree is a flake waiting for a parallel run or a dirty `git status` in CI.

**Done when:** suite green with a reduced count; `git status` is clean after a full run; no test writes outside `tmp_path`.

- [x] Accept
- [ ] Reject

---

## What is already good — do not change

Recording this so the accepted proposals do not spill into them:

- **Layer boundaries are real.** `common/` is stdlib-only, `facts/` isolates the three network clients, `content/` owns file writes, `repo/` owns git, `rules/` owns rule data. The violations above are exceptions, not the rule.
- **Rule data as package data with a loader-relative guard.** `rules/engine.py:13` and `rules/validation.py:16` resolve `RULE_DATA_DIR` from `__file__`, and `tests/test_rules_layer/test_data_loading.py` proves the loader follows a relocated module and that scripts never read `assets/`. That is the right protection for the packaging decision.
- **Docstrings carry the *why*, not the *what*.** `common/config.py:110-119` (why a write probe rather than `os.access`), `repo/logs.py:140-142` (what was deliberately not ported), `repo/audit.py:8-33` (the severity policy), `validation.py:886-901` (why an inert bounds key is reported). Keep these when refactoring; they are the cheapest institutional memory in the repo.
- **Exit-code policy is centralised and documented.** One `main()` maps exceptions to codes (`cli.py:1028-1034`), the epilog documents them (`:769`), and `test_help.py`/`test_dispatch.py` pin them.
- **Deterministic ordering.** Findings are sorted by severity/rule/line, directory listings are sorted, sets are rendered sorted. This is why the tests and JSON payloads are stable; preserve it in every refactor.
- **Hermetic by default.** The suite needs no network and no real EDCoPilot folder; live checks are a separately deselected marker (`tests/test_integration/`). Keep that split.
- **`_json_default` is the right shape.** One place that knows about `Path`, `set` and dataclasses (`cli.py:68-75`); proposal 9 extends it rather than replacing it.
- **Risk-weighted tests exist where they matter.** `test_branch_e2e.py` (branch workflow across processes), `test_content_rewrite.py:test_tag_roundtrip_byte_exact` (byte-exact rewrite), `test_common/test_write_probe.py` (the writability probe), `test_live_fixtures.py` (real dossiers). These are the tests that earn their maintenance cost.
- **No build step, no packaging magic, two runtime dependencies.** Nothing in this document adds either.

## Appendix — measurements behind the ranking

| Module | Lines | Note |
|---|---|---|
| `rules/validation.py` | 1748 | six responsibilities; 7 names imported privately by `repo/brief.py` |
| `repo/branches.py` | 693 | 19 alias fields; 15 manual `repo.close()` blocks |
| `facts/facts.py` | 747 | 2 near-identical site dataclasses; 2 near-identical comparators; 2 unused renderers |
| `cli.py` | 875 | 3 dispatch mechanisms; 4 output shapes; 2 unused payload keys |
| `repo/audit.py` | 493 | `to_dict` duplicates `asdict` + one encoder |
| `repo/brief.py` | 293 | imports 5 private names across a layer |
| `rules/engine.py` | 143 | 9 of 14 public functions have no production caller |
| `content/markdb.py` | 203 | add/remove are one function written twice |
| `facts/raven.py` + `spansh.py` + `inara.py` | 848 | ~85 lines of transport duplicated three times |

`python -m ruff check skills/edcopilot-system-content/scripts` at HEAD: **242 findings**, of which `UP045` (121) and `UP017` (11) are style-only. The maintainability-relevant subset: 24 `BLE001` blind excepts, 12 `S110` `try/except/pass`, 8 unused imports (`facts.py:10,13`; `inara.py:12`; `journal.py:10,12`; `brief.py:14`; `dossier.py:6`; `validation.py:13`), 2 `PLW0602` globals-without-assignment in `branches.py`, 1 `B033` duplicate set item (`validation.py:1594`), 1 `B018` useless expression (`gitrepo.py:138`), 1 `F541` placeholder-free f-string. None of these is proposed as its own item — they are symptoms the structural proposals remove, and `ruff --fix` on the imports is a free by-product of touching those files.

**Verdict:** the architecture is sound and the tests are real. What has accumulated is *second copies* — of rule loading, of transport, of root resolution, of branch results, of the same fixture in five files — each of which was reasonable when written and each of which now answers a question the codebase also answers elsewhere. The top six proposals remove most of that without changing behaviour; the rest is tidying that makes the next feature cheaper.
