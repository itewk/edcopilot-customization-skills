---
name: edcopilot-system-content
description: Author and update EDCoPilot speech extensions for colonisation systems in Elite Dangerous. Use this for a new system or station, and for refreshing existing greeting, chatter, broadcast and StationFact content - interview the user, write the dossier and rules, author the speech content, validate it, and stage it for EDCoPilot's database update.
license: GPL-3.0
compatibility: Requires Windows (EDCoPilot), Python 3.14+, the httpx and GitPython packages, and git
metadata:
  version: "1.0.0-alpha.3"
---

# EDCoPilot System Content

This skill writes and maintains the speech content for one colonisation system
at a time. It interviews the human, records the design as a dossier and a rules
file, writes the speech extensions, validates them, and walks the marker cycle
that makes EDCoPilot pick the new lines up. It is for **authoring** a new system
and for **updating** an existing one after play.

The prose lives here and in `references/`; the scripts supply facts, computed
values, validation and file writes. The scripts never pause for a gate; they do
refuse impossible or invalid operations (a bad definition, a rewrite that would
introduce errors, an existing repository on `init`). The gates below are
advisory, and the agent's discipline carries them.

## Setup

### Read this when

Load a reference for the job in front of you; each is the single home for its
subject.

| Read this | When |
|---|---|
| [`references/workflow-details.md`](references/workflow-details.md) | Setup: environment variables and root resolution; then the marker cycle, branch mechanics, git and commit rules |
| [`references/new-system-interview.md`](references/new-system-interview.md) | A system with no definition yet: the six-phase interview |
| [`references/update-interview.md`](references/update-interview.md) | A system that already has a definition: the seven-phase update |
| [`references/writing-brief.md`](references/writing-brief.md) | Before writing content: exact tag lines, section sizes, voices, tokens and filters |
| [`references/rules.md`](references/rules.md) | Rule layers, precedence and bound semantics — before changing a rule, and when authoring a system's rules file |

1. **Check the environment.** Run `python <skill-dir>/scripts/edcg.py doctor`.
   It prints one `OK` or `FAIL` line per check (Python version, `httpx`,
   GitPython, the `git` binary, git identity, content root, EDCoPilot root).
   Relay every `FAIL` with the `fix:` hint it prints. On a fresh machine the
   EDCoPilot-root check — and the logs check that depends on it — fails with
   `not configured (expected on first run)`; that is expected, and no other
   failed check may be bypassed.
2. **Establish the content root.** It is the current working directory; set
   `EDCG_CONTENT_DEFINITIONS_ROOT` to use another directory. The dossier, the
   rules file and the git history live there; nothing else stores workflow
   state. If `doctor` reports the root as `blank`, do not invent a layout:
   confirm with the user first ("this directory isn't a content repository yet
   — set one up here?"), then run `edcg.py init`. It writes the config file, a
   `systems/` directory and, unless `--no-git` is passed, an initial commit. Offer
   `--no-git` when the user does not want a repository. If your harness requires
   commit trailers, pass `--co-author "🤖 <harness> (<models>) <email>"` naming
   your own harness and model(s) so the scaffolding commit records attribution.
3. **Adopt the house rules.** If `systems/all.rules.toml` does not exist: if
   `systems/all.rules.toml.example` exists (a legacy scaffold), promote it —
   copy it to `systems/all.rules.toml` and delete the redundant example;
   otherwise copy
   [`assets/all.rules.toml.example`](assets/all.rules.toml.example) →
   `systems/all.rules.toml`. Then review the rules with the user — walk each
   section the example contains (logo, banned filters, conversation floors)
   and let them modify, add, or remove before any content work. The house-rules
   file rides into the first definition commit the workflow makes (`edcg:
   scaffold` or `edcg: update`). For an existing repository with house rules
   already in place, this step is a reminder that house-rule changes are
   deliberate edits with their reasons.
4. **Establish the EDCoPilot root.** EDCoPilot's "User custom files" folder is
   resolved from `EDCG_EDCOPILOT_ROOT`, then from `roots.edcopilot` in the
   content repository's config file, then by asking the user. Ask now if it is
   unresolved, and store the answer in the config file when it is stable; never
   guess a path into a game installation. If `doctor` warns that the folder does
   not look right, confirm the path with the user before proceeding.
5. **Re-run `doctor`.** Require every check to pass before any content work.
   The environment-variable reference is the "Environment variables" section of
   [`references/workflow-details.md`](references/workflow-details.md).

## Process

Run these in order. Every step applies to both modes; where the new-system and update paths differ, the step says so.

**Feature branch (optional, both modes).** Before the interview, offer once
whether to do the work on a feature branch. Run `edcg.py branch start
<description>` only if the user accepts; otherwise stay on the current branch
and say so. Never create a branch the user did not ask for. Branch mechanics,
and how the active branch is read back from git, are in
[`references/workflow-details.md`](references/workflow-details.md).

EDCoPilot must be closed whenever a step writes the custom file or changes
markers (steps 10, 12 and 16). Ask the user to close it, and to restart it when
a step calls for a restart.

Run every command from the content root as `python <skill-dir>/scripts/edcg.py <subcommand>`. The top-level `--help` lists every command and the exit codes (0 success, 1 check failure, 2 usage error); each stateful command's `--help` carries a worked example of its payload.

1. **Resume.** Run `edcg.py status` for the checklist derived from the repository, then `edcg.py audit --system <name>` (or `edcg.py update-scan` when facts may have moved). Read the repository state: `systems/`, the custom file, `UPDATEDB` markers, git log.
2. **Gather facts.** New: `edcg.py gather-facts --system <name>`. When Raven
   has no entry, skip gathering and start the interview from the user's
   description. Update: `edcg.py update-scan` and read this system's delta
   entry.
3. **Interview.** New: the six phases in [`references/new-system-interview.md`](references/new-system-interview.md). Update: the seven phases in [`references/update-interview.md`](references/update-interview.md). One phase at a time; wait for answers. Read the interview reference before asking the first interview question; its phases and its validation checklist are the workflow.
4. **Validate the definition.** `edcg.py validate-definition` (JSON stdin: `system_name`, `dossier`, `rules`, and `all_rules` when present; or pass `--dossier-file` / `--rules-file` / `--all-rules-file` instead of embedding the documents — see the command's `--help` example). Fix every `error` and repeat until `passed` is true. Warnings are understood, not ignored.
5. **Save the definition.** `edcg.py save-definition` (JSON stdin: `system_name`, `dossier_md`, `rules_toml`, `commit_co_author`; or `--dossier-file` / `--rules-file` — note the field names differ from validate-definition's). Verify the returned commit hash with `git log -1 --oneline`.
6. **Preview gate.** Offer a representative sample (about 8-10 lines) before the full generation; on acceptance show it, take at most one round of changes, then continue.
7. **Writing brief.** `edcg.py writing-brief-data --system <name>` supplies the exact tag lines, bounds and voices. Do not invent tag lines.
8. **Write the block.** Compose the content from the brief. Update mode: first `edcg.py get-content --system <name>` to read the exact existing lines, then `edcg.py rewrite-tag` for every removal, replacement or addition (staged, not committed).
9. **Validate the content.** `edcg.py validate-content` (JSON stdin). Fix every `error` and repeat until `passed` is true; present the returned rule table.
10. **Write the content.** `edcg.py write-content` (JSON stdin, including `commit_co_author`) appends the block with provenance and commits, including any rewrites staged in step 8.
11. **Review gate.** Ask the user whether to mark for update now or to review first (static: read the file or diff; live: restart EDCoPilot and listen). Record the choice in the conversation and follow it.
12. **Mark for update.** `edcg.py markdb add --tag <tag> ...` (or JSON `tags`). One commit. Compare `modified_tags` to the tags you passed — a missing tag matched no authored content; stop and reconcile the station/tag name before proceeding.
13. **Restart.** Ask the user to restart EDCoPilot and confirm when done.
14. **Check the logs.** `edcg.py check-logs --system <name>`. Show the per-tag report. A failed tag is the user's decision: fix and repeat the cycle, or accept.
15. **In-game test and upload.** Ask the user to test the content in game and upload the database from inside EDCoPilot. Only after they confirm, clear the markers.
16. **Clear the markers.** `edcg.py markdb remove --tag <tag> ...`. One commit. Compare `modified_tags` to the tags you passed — a missing tag matched no authored content; stop and reconcile the station/tag name before proceeding. The cycle is complete: exactly three runtime commits (content, marker add, marker remove).

## Resume rule

For any system-touching request, run `edcg.py audit --system <name>` (or
`edcg.py update-scan` when several systems may have moved) **before** writing
anything and read where things stand. The content repository is the state:
`systems/` shows what is defined, the custom file shows what is written,
provenance markers show who wrote it, `UPDATEDB` lines show an open marker
cycle, and the git log shows what has landed. Nothing is stored in a running
process, so a new session resumes from the repository alone.

## New system

The route is Process steps 1–10: resume, gather facts, the six-phase
interview, validate and save the definition, preview, the writing brief, then
write, validate and commit the content. When Raven has no entry yet, skip
gathering and start the interview from the user's description; the interview
creates the identity. Ask once, before the artifacts, how many examples each
section should keep, then write `[content.bounds]` from the answer.

Interview: [`references/new-system-interview.md`](references/new-system-interview.md).
The dossier structure is [`assets/dossier-template.md`](assets/dossier-template.md) — the structure validation enforces.

## Update an existing system

The route is Process steps 1–10: refresh the facts, invalidate what is no longer
true, offer variety, make room for new lines, then update the artifacts,
validate and save. The seven-phase order is fixed; phase 2B (reconcile existing
content) runs between the lore update and the station update.

Interview: [`references/update-interview.md`](references/update-interview.md).
`edcg.py update-scan` is the refresh command, for one system or many: it
reports every system's deltas, so run it whenever facts may have moved. Process
the changed systems one at a time and never batch validation or save across
them.

## Advisory gates

None of these gates refuses; ask, and treat the answer as the instruction. Each
gate is a Process step: **preview** (6), **review choice** (11), **restart**
(13), **log check** (14) and **in-game test and upload** (15). The step carries
what to offer; the operational detail — what a static review can and cannot
show, what a failed tag means, and how the progress table is built — is in
[`references/workflow-details.md`](references/workflow-details.md).

Derive the state before each gate rather than assuming it: `edcg.py branch
status` for the active branch, `edcg.py get-content --system <name>` for authored
tags and their counts, the custom file for `UPDATEDB` markers, and `systems/`
for the dossier and rules files. Read them together so the user can see where
the cycle is.

The definition prerequisite is a refusal, not a gate: when a content command
refuses, show the human all three parts — the missing step, the cost of
skipping, and the flag — and wait. Only the human may authorise the skip;
`edcg.py write-content` accepts `--allow-no-definition`, and the flag is per
command, so every gated call for a skipped system needs it again. It cannot help
`writing-brief-data`, whose brief is computed from the definition itself.

## Commit conventions

The scripts commit for you, with the co-author trailer you pass as
`commit_co_author` (`🤖 <harness> (<models>) <email>`). Subjects:

- `edcg: scaffold <system> — <summary>` — a new dossier and rules pair;
- `edcg: update <system> — <summary>` — a changed dossier and rules pair;
- `edcg: content <system>` — appended content and any staged rewrites;
- `edcg: markdb add <n> tag(s)` — the markers added in one commit, with the tag
  list in the body;
- `edcg: markdb remove <n> tag(s)` — the markers removed in one commit, with
  the tag list in the body.

One design or update cycle leaves exactly three commits in the runtime
repository: content, marker add, marker remove. Never commit by hand what a
script is about to commit, and stop before a writing step when the tree is
dirty: the scripts stage all changes in their repository.

## Human gates

The interview is the product, not paperwork in front of it.

- Never skip or merge interview phases; ask the questions in order and wait.
- Never write content the user has not approved, and never mark content the
  user has not chosen to mark.
- Never invent facts to fill a gap. If a source is unavailable, say so, record
  it, and let the user decide whether the remaining evidence is enough.
- Never weaken a rule to make a validation run pass. Change the rule
  deliberately, with its reason, or change the content.

Details for the writing rules: [`references/writing-brief.md`](references/writing-brief.md).
Details for rule layers and bounds: [`references/rules.md`](references/rules.md).
