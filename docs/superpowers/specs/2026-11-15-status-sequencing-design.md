# Workflow status and sequencing design

**Date:** 2026-11-15
**Status:** awaiting human approval
**Version target:** 1.0.0-alpha.3 (this feature set). The alpha.2 batch (next-step
hints + version alignment) lands separately; the version-alignment ruling below
is recorded here because it supersedes a founding decision.

## Intent and why

Two live runs failed the same way: the agent skipped an early step (reference
reading, fact gathering) and downstream work proceeded anyway, producing blind
or invalid content. Fixes so far (next-step hints, spine wording) are
advisory; the human has ruled that ordering should be *enforced with an
override*: the scripts refuse out-of-order operations, the refusal names the
consequences, and the human may explicitly choose to skip.

Success: an agent (or the human, during the gate) can run `edcg status` and see
exactly where the workflow stands; an agent attempting content work without a
definition is refused with a message that both explains the refusal and costs
the skip honestly; and a human-directed skip is explicit, recorded in the
transcript, and never silent.

## Goals

1. **G1 — `edcg status`**: a derived checklist of the workflow's mechanical
   state, printed as prose on stdout. Derived from git + files only (no state
   file). Lines name the next action and, where one exists, the reference that
   governs it. Conversation-side steps (the interview itself) are worded so
   their absence is not mistaken for a forgotten step.
2. **G2 — Definition-prerequisite refusals**: `writing-brief-data`,
   `validate-content`, `write-content`, `rewrite-tag`, and `markdb` (add and
   remove) for a system with no saved definition refuse with exit 1 and a
   three-part message: (a) the missing prerequisite and the fix, (b) the
   downstream consequences of skipping it, (c) the override flag.
3. **G3 — The override**: `--allow-no-definition` on each refusing command.
   When passed, the command proceeds and prints a `warning:` block on stderr
   restating the consequences. The transcript is the record; nothing is
   stored.
4. **G4 — Scope is deliberately narrow**: only the definition-prerequisite
   family refuses. `gather-facts` is never refused (facts are not persisted;
   it is the probe). All other ordering stays advisory via `status` and the
   next-step hints.
5. **G5 — Version alignment (alpha.2, ruled by the human)**: every version
   string in the skill — SKILL.md metadata, `edcg.__version__`, AND the
   provenance `VERSION` in `content/custom_file.py` — becomes
   `1.0.0-alpha.2`. This **supersedes** the founding decision that pinned the
   provenance version to the old implementation's `0.1.0`: provenance blocks
   will no longer byte-match the old MCP server's output. Functionally safe
   (EDCoPilot treats the line as a comment; `PROVENANCE_RE` matches on
   format, not version); tests that pin `0.1.0` are updated; the superseded
   decision is recorded in `docs/backlog.md`.

## Non-goals

- No state file, no pausing, no MCP (founding invariants unchanged).
- No refusal of `gather-facts`, `doctor`, `init`, `audit`, `update-scan`,
  `get-content`, `check-logs` — these are probes and readers.
- No sequencing beyond the definition family in this increment.
- `status` does not track the interview conversation; it reports mechanical
  state only.

## Anti-goals (what would make this a failure)

- A skip that happens silently (override without the warning block).
- A refusal whose message does not name the consequences (the human cannot
  make an informed skip).
- A checklist that lies (deriving state from anything other than the repo and
  files, or claiming conversational steps it cannot see).

## Constraints

- Hermetic tests; Python 3.14; no new dependencies.
- Advisory-gates philosophy: refusal of an invalid operation is allowed;
  pausing is not.
- Prose on stdout for `status` (human/agent readable); refusals keep the
  established channel contract (refusals are check failures → exit 1, message
  per the existing `_fail` convention).
- Help-as-interface-doc: the new command and flag get worked examples.
- Commits: conventional subjects + single `Co-authored-by` trailer naming the
  model actually used.

## Decisions made (with the human)

- **D1 — Refuse + report + override**, not hard refusal: the human can say a
  step is skipped; the skill reports what may not work (this conversation).
- **D2 — Override is a per-command flag** (`--allow-no-definition`), not a
  session-wide acknowledgment (this conversation).
- **D3 — Refusal scope: the definition-prerequisite family only** (this
  conversation).
- **D4 — `status` derives from repo + files only** (this conversation).
- **D5 — Provenance version joins the alignment** (human instruction,
  superseding the byte-pin; recorded in the backlog).
- **D6 — markdb refusal rule** (builder check): a markdb call refuses when
  ANY tag's derivable system (field 1 of the tag, where the kind declares a
  system part) lacks a definition; tags whose kind declares no system part
  are exempt (systemless markers must never be stranded). The interface does
  NOT grow a system field — `PAYLOAD_SPECS`, `DOCUMENTED_KEYS` and the markdb
  epilogs stay untouched; the override covers the mixed/legacy edge.
- **D7 — status signature** (builder check): `edcg status [ --system <name> ]`.
  Without the flag: repo-wide lines (config, house rules) plus one one-line
  state per system. With it: the full checklist for that system.
- **D8 — status content line is precise** (builder check): content presence
  is derived with the strict rule (`tag.system == system_name` only), NOT via
  `get_system_content`'s station-decl fallback — an approximate line would
  violate the "checklist that lies" anti-goal. `get_system_content` itself is
  unchanged (runtime behaviour untouched; the divergence is commented in
  status's implementation).
- **D9 — status exits 0 always** (builder check): a status report is not a
  failed check; exit 1 would read as a stop signal on exactly the states the
  human wants pushed through with an override. Usage errors (exit 2) still
  apply.
- **D10 — Sequencing** (builder check): the alpha.3 plan assumes the alpha.2
  batch (next-step hints, version bump) has landed first; the provenance
  alignment from D5 lands on top of alpha.2 before this feature's tasks
  start.

## What's left to the builder

- **B1 — `status` output format**: exact checklist lines, order, and the
  wording for conversation-invisible steps; derive each line's state from
  existing sources (house-rules file, `systems/<slug>` definition files +
  definition commits in `git log`, content in the custom file via
  `get_system_content`, marker state). Keep it one prose block; no JSON.
- **B2 — Refusal wording**: exact three-part message text per command
  (pin in tests). The downstream-consequences text per skipped definition:
  no bounds/voices/tag lines — content will be written blind, validation
  will be weak, EDCoPilot coverage cannot be verified.
- **B3 — Override wiring**: flag on each refusing command; warning block on
  stderr naming the system and the same consequence text.
- **B4 — Version alignment**: the three version strings to
  `1.0.0-alpha.2` (unless the alpha.2 batch already landed two of them —
  check first; the provenance string is the one certainly remaining);
  update pinned tests; backlog note for the superseded byte-pin decision.
- **B5 — Version string for this feature**: `1.0.0-alpha.3` across the same
  three locations (SKILL.md metadata, `__init__.__version__`, provenance
  `VERSION`) — the alignment and the feature ship together, so the tree
  carries `1.0.0-alpha.3` when this work lands.
- **B6 — Help**: `status` gets a worked example; the refusing commands'
  `--help` documents `--allow-no-definition` with one line on when a human
  would choose it.

## Verification bar

- Full hermetic suite green at merge; `skills-ref validate` clean.
- Every refusal case, the override path, and each `status` state has a
  hermetic test that would fail on the old behaviour.
- Version consistency test: the three version strings are equal
  (`__version__` == SKILL.md metadata == provenance `VERSION`).
- `status`'s derived lines are tested against fixtures for each state
  (blank / house-rules-only / definition-saved / content-written).
