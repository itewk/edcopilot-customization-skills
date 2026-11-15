# Live-run UX fixes — design

**Date:** 2026-11-15
**Status:** awaiting human approval
**Evidence:** OpenCode session `ses_e200927cfffeiIMaDStr9VAEmU` (the OB-K b1-8
experiment run), full-thread analysis; findings F1–F10 as catalogued in that
analysis. The content repository
(`edcopilot-customization-skyrunner42`) has been reverted to `219b17f` and the
experiment residue removed; the human will rerun the experiment in a fresh
session **after** these fixes land.

## Intent and why

The first real use of the skill by an agent (gemma 4 26B via LM Studio) failed
at dossier authoring — not because the agent misunderstood the lore (the
interview was good), but because the payload contract and the definition
checklist lived in two places the agent never opened, the CLI answered wrong
payload *types* with raw tracebacks, and the interface forced the agent to
hand-assemble a giant JSON string. The failure chain: skip reference → invent
schema → four turns of error-driven schema archaeology → retry loop → human
stops the session. All of it stung: wasted time, guesswork, and the fear it
recurs on the next system.

Success: a fresh-session rerun of the same experiment reaches
`validate-definition` → `passed: true` → `save-definition` without the agent
ever having to guess a payload shape, and a single wrong payload produces one
complete diagnosis.

## Goals

1. **G1 — Contract at point of use.** The spine's step-4 shorthand names every
   payload field (including `system_name`); each stateful command's `--help`
   stays the worked-example home (existing convention).
2. **G2 — The rules example.** A complete, minimal, worked per-system
   `rules.toml` exists in agent-facing prose, parallel to
   `assets/dossier-template.md` for the dossier.
3. **G3 — Errors that teach.** `validate-definition` / `save-definition` (and
   the shared payload reader) validate payload *types* and emit doctor-style
   fix hints; wrong-type and unparsable-JSON payloads never surface as Python
   tracebacks.
4. **G4 — No giant JSON strings.** `validate-definition` and
   `save-definition` accept `--dossier-file` / `--rules-file` so an agent can
   pass file paths instead of embedding full documents as JSON strings.
   JSON stdin remains the canonical wire format.
5. **G5 — Recurrence record.** The live-run findings are recorded where the
   release gates read them, and the fresh rerun replaces the salvage as the
   pre-tag live-run gate (it should also exercise `init --co-author`).

## Non-goals

- No MCP server, no state file, no build step (founding spec unchanged).
- No change to the provenance block format or the byte-pinned wire-protocol
  strings.
- No new interview phases; the six-phase reference content itself is already
  sound — the failure was that it was never read.
- No salvage of the OB-K b1-8 definition; the content repo stays reverted.

## Anti-goals (what would make this a failure)

- Fixing only the spine wording while the type-error traceback and the
  missing rules example remain — the loop would find another path.
- Fattening the spine back into a duplicate of the references (undoes SQ3).
- Making the validator stricter or noisier — findings quality was already
  excellent once fed the right shape; the problem is upstream.

## Constraints

- Hermetic tests only; no network, no real EDCoPilot folders.
- Python 3.14; stdlib `tomllib`; no new dependencies.
- Advisory gates philosophy: the scripts refuse invalid operations but never
  pause; agent discipline carries the process. Fix G3 sharpens the
  *refusals*; it does not add gates.
- Help-as-interface-doc: command tables stay out of SKILL.md; the spine
  carries pointers, the references carry content.

## Decisions made (with the human)

- **D1 — No salvage in this session.** The experiment reruns fresh after the
  fixes; the fresh rerun is the live-run gate (human decision).
- **D2 — Content repo reverted** to `219b17f`, temp files and empty
  `systems/` removed (done).
- **D3 — JSON stdin stays canonical;** file flags are additive sugar
  (controller call, standing unless vetoed).
- **D4 — Payload faults keep the usage-error contract** (stderr, exit 2) so
  "rejected payload" stays distinguishable from "failed definition"
  (controller call from the builder check; the design's earlier "exit 1"
  wording was wrong and is corrected in B3).
- **D5 — One aggregated diagnosis per invocation** — the payload reader
  collects all missing/wrong-typed fields before emitting (controller call;
  per-field rejection would reintroduce the N-round-trip archaeology loop).
- **D6 — `--all-rules-file` joins the flag set** on validate-definition
  (controller call; leaving `all_rules` as an embedded string reproduces the
  failure mode G4 kills).
- **D7 — Step 5 enumerates its own field names in the spine** rather than
  aliasing step-4 names on save-definition (controller call; aliases add
  API-surface debt for no gain).
- **D8 — The definition commit narrows to definition files + house-rules
  ride-along** instead of `add_all()` (controller call from the builder
  check — **flagged for the human to veto while reading**: this changes what
  lands in the definition commit in their content repository, though it is
  the hygiene fix that stops staging junk being committed silently).

## What's left to the builder

- **B1 — Spine wording (G1).** SKILL.md Process step 4: enumerate the payload
  fields (`system_name`, `dossier`, `rules`; `all_rules` when present) and
  point at the subcommand `--help` example. Step 5: likewise enumerate its
  own fields (`system_name`, `dossier_md`, `rules_toml`,
  `commit_co_author`) — the field names differ between the two commands and
  the rename trap must not just move one step later. Step 3: one enforcing
  sentence — read the interview reference *before asking the first interview
  question*. Keep it to that; do not re-duplicate reference content.
- **B2 — Rules example (G2).** Add an "authoring a system rules file" section
  to `references/rules.md` with a complete minimal worked `rules.toml`
  (covering the validator-required `system.names`, `system.dossier`,
  `system.voices` and one bound override); update the SKILL.md
  read-this-when row for rules.md to cover authoring as well as changing.
  Single-homed: the example lives in rules.md, not duplicated as an asset —
  unless the builder finds the interview references need to inline it, in
  which case reference rules.md rather than copy.
- **B3 — Error UX (G3).** In the shared payload reader (`_payload` /
  `_required` in `scripts/edcg/cli.py`): validate types, not just presence,
  and emit **one aggregated diagnosis per invocation** — collect every
  missing and wrong-typed field first, then emit a single message naming
  each fault with its fix hint (doctor style, `error: ... fix: ...` lines on
  **stderr**, exit **2**). Payload faults are usage errors: they keep the
  pinned contract (stderr text, empty stdout, exit 2, "2 usage error" in the
  top-level help and SKILL.md:93), which also keeps exit 1 meaning "the
  validation ran and produced findings" — a rejected payload and a failed
  definition stay distinguishable by exit code. Wrong-type cases are new
  behaviour; the existing clean messages (empty stdin, invalid JSON, must
  be an object) keep their channel and exit code and gain fix hints; their
  wording may evolve as the pinned tests are updated with the aggregation.
  Hermetic tests for each case, each of which would fail on the old
  traceback behaviour.
- **B4 — File-path flags (G4).** `validate-definition --dossier-file
  <path> --rules-file <path> --all-rules-file <path>` and the same flags on
  `save-definition` (`--dossier-file` maps to `dossier_md`, `--rules-file`
  to `rules_toml`; `save-definition` has no house-rules field, so no
  `--all-rules-file` there). Three strings, three file flags: the
  house-rules document is ~3 KB of TOML the agent would otherwise still
  embed as a JSON string on every step-4 call — the exact failure mode G4
  exists to prevent, and omitting it silently loses the `fact_image` check.
  Precedence: explicit JSON payload fields win over file flags when both
  are given — decide and document the actual rule (simplest defensible:
  file flags error if the corresponding JSON field is also present? or file
  flags win? pick one, document in `--help`, test it). Paths resolve relative
  to the content root like other commands' path arguments; absolute paths
  are accepted. Missing file → aggregated fix-hint error, not traceback.
  stdin remains the default when no flags are passed. **Add the missing
  worked example to `validate-definition --help`** (JSON form plus file
  form) — G1 points agents at that example, and it does not exist today
  (only save-definition, write-content, rewrite-tag, markdb, check-logs and
  branch have one).
- **B5 — Evidence record (G5).** Record the live-run failure chain and its
  fixes in `docs/live-run-checklist.md` (or a findings note it links to) and
  note in `docs/backlog.md` that the fresh rerun replaces the salvage as the
  pre-tag gate, exercising `init --co-author`. Where exactly the findings
  text lives is the builder's call; one home, linked from the checklist.
- **B6 — Definition-commit hygiene.** `save_definition` commits with
  `repo.add_all()`, so a staging file the agent leaves in the content root
  (exactly what the live run did with `final_payload.json`) is swept into
  the definition commit silently. Narrow the definition commit to exactly
  the files it writes (dossier markdown, rules TOML) plus the house-rules
  ride-along when `systems/all.rules.toml` is untracked at first-save time
  (preserving spine step 3's recorded behaviour); anything else untracked
  stays untracked. `files_changed` in the JSON output already reports what
  was committed — keep it accurate. Test: a stray staging file in the
  content root is NOT in the definition commit.

## Known accepted deviations (verify, don't re-litigate)

- The founding spec's invariants (advisory gates, no state file, no MCP,
  byte-pinned provenance, hermetic tests).
- The single-trailer commit convention (`Co-authored-by: 🤖 OpenCode
  (<model(s)>) <noreply@opencode.ai>`, no separate `Models:` line).
- Wire-protocol strings are exempt from product-identity rules.
- The observed agent failures (Code Mode misuse ×2, invented `scaffold`
  command, skipped references) are partly model behaviour; these fixes make
  the interface resilient to them but do not attempt to make any model
  follow instructions better.

## Verification bar

- Full hermetic suite green (baseline 795 passed / 1 skipped / 9 deselected
  at `ddaaecd`), `skills-ref validate` clean, conventional commit with the
  single co-author trailer.
- The G3 cases each have a test that would fail on the old traceback
  behaviour.
- The G4 flags have round-trip tests (file in → same validation result as
  the equivalent JSON payload), including the `--all-rules-file` path.
- The B6 hygiene test: a stray file in the content root is not swept into
  the definition commit, and the house-rules ride-along still works.
