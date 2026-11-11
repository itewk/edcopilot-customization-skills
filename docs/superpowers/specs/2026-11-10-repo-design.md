# EDCoPilot Customization Skills — Repository Design

**Date:** 2026-11-10 (founding spec, v1.0.0)
**Status:** Approved

This document is the repository's founding design: how the skills here are
structured, how they resolve their environment, and which invariants protect
the workflow they implement. It expresses decisions as architecture. Future
changes to the skills are specced and planned under `docs/superpowers/`.

## What this repository is

A collection of distributable Agent Skills (agentskills.io) for authoring and
updating EDCoPilot custom speech content. Each skill is a self-contained
folder under `skills/`, installable with `npx skills add <owner>/<repo>` and
updatable with `npx skills update` (whole-folder replace; `metadata.version`
in each SKILL.md tracks releases; git tags mark them).

Every skill folder carries everything it needs: `SKILL.md`, `references/`,
`assets/`, `scripts/`. Scripts are not shared between skills. The Python is
internally layered so that a future refactor — a shared library, a promoted
service, or per-skill stamping — is a mechanical extraction:

- `common/` — configuration and roots resolution
- `facts/` — Raven Colonial, player journal, Spansh, Inara clients
- `rules/` — rule engine, validation
- `content/` — custom-file reading/writing, tag blocks, provenance, markers
- `repo/` — git operations, dossier IO, audit, log checks, branch orchestration
- `edcg.py` — thin CLI over the layers

Release 1 ships one skill, `edcopilot-system-content`, covering the entire
system-content workflow: the six-phase design interview and the seven-phase
update interview, dossier and content validation, fact gathering, the writing
brief, custom-file writing with provenance, per-tag rewrite, `UPDATEDB`
markers, restart log checking, audit, and branch management. The skill
instructions live in `SKILL.md` (the spine) and `references/` (the detail),
loaded progressively.

## The two roots

- **Content definitions root:** the agent's current working directory;
  `EDCG_CONTENT_DEFINITIONS_ROOT` overrides when set. A blank directory is a
  valid starting point: `edcg.py init` scaffolds it (`git init` unless
  `--no-git`, the config file, `systems/`, the house-rules example) after the
  user confirms. A directory containing `systems/` or the config file is never
  re-scaffolded.
- **EDCoPilot root, in precedence order:** `EDCG_EDCOPILOT_ROOT` if set and
  existing; then the path persisted in the content repo's
  `edcopilot-customization-generator.toml` (`[roots] edcopilot`), committed
  deliberately — a clone on a second machine carries a stale path, and
  staleness is detected and re-asked rather than silently overwritten; then
  unresolved, and the skill asks the user, verifies, and stores the answer.
  `EDCG_EDCOPILOT_LOGS_DIR` optionally relocates the logs directory
  (default: sibling `logs/` of the EDCoPilot root).

`edcg.py doctor` verifies the environment on first contact: Python ≥3.12,
`httpx` and GitPython importable, git identity, both roots — one OK/FAIL line
per check, with fix hints, exiting 1 on any failure.

## The content repository is the state

No workflow state file exists anywhere. The content repository is the memory:
dossiers and rules under `systems/`, provenance-commented blocks in the
runtime custom file, `UPDATEDB` markers, git history. For any system-touching
request the skill first runs the audit / update-scan and reads where things
stand.

All human gates are **advisory**: the skill asks (preview before full
generation, review choice before marking, restart confirmation before the log
check and marker removal, listening after restart), and the scripts never
refuse. The agent's discipline carries the gates; if trust proves misplaced,
script-side checks are a deliberate later addition, not an accident of
omission.

## Invariants

1. **The workflow is the product.** Scripts supply facts, rules, validators
   and writers; they do not decide what a system is about. The LLM conducts
   the interview and writes the prose; the human answers, approves and listens.
2. **Never invent facts.** If a source is unavailable, record it and let the
   human decide whether the remaining evidence is enough.
3. **Format parity.** Tag syntax, provenance comment format, commit subjects
   (`edcg: scaffold|update <system> — <summary>`, `edcg: content <system>`,
   `edcg: markdb add|remove <n> tag(s)`) and `Co-authored-by` trailers are
   part of the contract; changing them silently is a bug.
4. **Two-roots separation.** Tooling and dossiers stay out of the runtime
   folder; the runtime folder receives only the custom file and marker
   operations.
5. **Hermetic default tests.** No network, no real EDCoPilot folders; live
   content is exercised only by integration-marked tests that are read-only.
6. **Product identity.** These skills stand alone. References to other tools,
   servers or prior architectures do not belong in user-facing files, commit
   messages or code comments. Wire-protocol strings (API payloads, User-Agent
   values, provenance text) are data, not prose, and are exempt.
7. **Faithful ports.** Wherever code is replaced or rewritten, the existing
   test suites are the spec; a rewrite that changes behaviour beyond a
   recorded, approved decision is a defect.

## Constraints

- Python ≥3.12; runtime dependencies: `httpx`, `GitPython` only.
- Windows-first (EDCoPilot is a Windows application); paths must not be
  hard-coded to specific drive layouts.
- `SKILL.md` bodies stay under 500 lines; detailed material lives in
  `references/` loaded on demand.
- Skill names: lowercase `a-z0-9-`, no consecutive hyphens, matching the
  folder name; `skills-ref validate` must pass for every folder under
  `skills/` — CI validates them all automatically so adding a skill requires
  no CI changes.
- GPLv3.

## Adding a second skill

Add a folder under `skills/` with the same shape. Decide its script needs
against the existing skill's layers; if the same code is needed in both,
that is the moment to make the sharing decision (shared library, promoted
service, or stamping build) — the layering above is designed to make that
decision mechanical. Repo-level docs describe the collection; CI and the
`skills/` glob pick the new folder up without changes.
