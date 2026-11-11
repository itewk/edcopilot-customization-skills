---
name: edcopilot-system-content
description: Author and update EDCoPilot speech extensions for colonisation systems in Elite Dangerous. Use this for a new system or station, and for refreshing existing greeting, chatter, broadcast and StationFact content - interview the user, write the dossier and rules, author the speech content, validate it, and stage it for EDCoPilot's database update.
license: GPL-3.0
compatibility: Requires Windows (EDCoPilot), Python 3.12+, the httpx and GitPython packages, and git
metadata:
  version: "1.0.0"
---

# EDCoPilot System Content

This skill writes and maintains the speech content for one colonisation system
at a time. It interviews the human, records the design as a dossier and a rules
file, writes the speech extensions, validates them, and walks the marker cycle
that makes EDCoPilot pick the new lines up. It is for **authoring** a new system
and for **updating** an existing one after play.

The prose lives here and in `references/`; the scripts supply facts, computed
values, validation and file writes. The scripts never refuse a step: the gates
below are advisory, and the agent's discipline carries them.

## Setup

1. Run `python <skill-dir>/scripts/edcg.py doctor` before anything else. It
   prints one `OK` or `FAIL` line per check (Python version, `httpx`, GitPython,
   git identity, content root, EDCoPilot root). Relay every `FAIL` together with
   the `fix:` hint it prints. Do not start the workflow past a failed check.
2. The content root is the current working directory. Set
   `EDCG_CONTENT_DEFINITIONS_ROOT` to use another directory. The dossier, the
   rules file and the git history all live there; nothing else stores workflow
   state.
3. If `doctor` reports the content root as `blank`, do not invent a layout.
   Confirm with the user first: "this directory isn't a content repository yet —
   set one up here?" On a yes, run `edcg.py init`. It writes the config file, a
   `systems/` directory, the rules example and, unless `--no-git` is passed, an
   initial commit. Offer `--no-git` when the user does not want a repository.
4. EDCoPilot's "User custom files" folder is resolved from
   `EDCG_EDCOPILOT_ROOT`, then from the config file in the content repository,
   then by asking the user. Store the answer in the config file when it is
   stable; never guess a path into a game installation.
5. EDCoPilot must be closed whenever a step writes the custom file or changes
   markers. Ask the user to close it, and to restart it when the marker cycle
   calls for a restart.

## Commands

Run every command from the content root as
`python <skill-dir>/scripts/edcg.py <subcommand>`. Data commands print JSON on
stdout and take their payload as JSON on stdin where noted. Exit codes: `0`
success, `1` a check failed, `2` usage error.

| Command | Purpose |
|---|---|
| `edcg.py doctor` | Check Python, packages, git identity and both roots |
| `edcg.py init` | Scaffold a blank content repository (`--no-git` to skip git) |
| `edcg.py gather-facts` | One system's facts as JSON (`--system <name>`) |
| `edcg.py get-template` | Print the dossier template validation enforces |
| `edcg.py validate-definition` | Validate a dossier and rules pair (JSON stdin) |
| `edcg.py save-definition` | Save a validated pair and commit (JSON stdin) |
| `edcg.py writing-brief-data` | Exact tag lines, bounds and voices (`--system <name>`) |
| `edcg.py validate-content` | Validate a content block (JSON stdin) |
| `edcg.py write-content` | Append a content block and commit (JSON stdin) |
| `edcg.py get-content` | Authored tags, lines, counts and bounds (`--system <name>`) |
| `edcg.py update-scan` | Scan every system for fact changes as JSON |
| `edcg.py rewrite-tag` | Remove, replace or add lines in one tag (JSON stdin) |
| `edcg.py markdb add` | Add `UPDATEDB` to the given tags and commit once |
| `edcg.py markdb remove` | Remove `UPDATEDB` from the given tags and commit once |
| `edcg.py check-logs` | Read EDCoPilot's log after a restart (`--since`, `--system`) |
| `edcg.py audit` | Compare a system across the four fact sources (`--system`) |
| `edcg.py branch start` | Start a feature branch in both repositories |
| `edcg.py branch status` | Show the active branch and uncommitted changes |
| `edcg.py branch review` | Print the branch diff for review |
| `edcg.py branch finalize` | Merge the feature branch (`--merge`, `--push`) |
| `edcg.py branch abort` | Discard the feature branch (`--confirm` to act) |
| `edcg.py version` | Print the skill version string |

## Resume rule

For any system-touching request, run `edcg.py audit --system <name>` (or
`edcg.py update-scan` when several systems may have moved) **before** writing
anything and read where things stand. The content repository is the state:
`systems/` shows what is defined, the custom file shows what is written,
provenance markers show who wrote it, `UPDATEDB` lines show an open marker
cycle, and the git log shows what has landed. Nothing is stored in a running
process, so a new session resumes from the repository alone.

## New system

Start with `edcg.py gather-facts --system <name>`. When Raven has no entry yet,
start without a name and let the interview create the identity from the user's
description. Then run the six-phase interview one phase at a time, waiting for
answers: high-level concept, station and character design, plot threads,
artifacts (dossier and rules TOML), the validation loop, and save. Ask once,
before the artifacts, how many examples each section should keep, then write
`[content.bounds]` from the answer. Full text:
[`references/new-system-interview.md`](references/new-system-interview.md).

## Update an existing system

Refresh the facts, then invalidate what is no longer true, then offer variety,
then make room for new lines, and only then update the artifacts, validate and
save. The seven-phase order is fixed; phase 2B (reconcile existing content) runs
between the lore update and the station update. Use `edcg.py get-content` to
read the exact lines before editing, and `edcg.py rewrite-tag` for every
removal, replacement or addition. Full text:
[`references/update-interview.md`](references/update-interview.md).

`edcg.py update-scan` is the refresh command, for one system or many: it
reports every system's deltas, so run it whenever facts may have moved. Process
the changed systems one at a time and never batch validation or save across
them.

## Advisory gates

Nothing refuses. Ask, and treat the answer as the instruction:

- **Preview** — after the definition is saved, offer a small representative
  sample (about 8-10 lines) before the full generation. If the user declines,
  write the full block. If they accept, show the sample, take at most one round
  of changes, then continue.
- **Review choice** — ask whether to mark the content for database update as
  soon as it is written, or to pause for a static or live review first. For a
  static review the user reads the file or diff; for a live review they restart
  EDCoPilot and listen. Live review is reliable for new tags; an updated
  existing tag may not refresh until `UPDATEDB` is added, so offer static review
  as the reliable path.
- **Restart** — after `markdb add`, ask the user to restart EDCoPilot. Confirm
  the restart before running `edcg.py check-logs`.
- **Log check** — show the per-tag report. A failed tag is the user's call: fix
  the content and repeat the marker cycle, or accept the failure and continue.
  Do not remove markers behind their back and do not hide a failure.

Derive the state before each gate rather than assuming it: `edcg.py branch
status` for the active branch, `edcg.py get-content` for authored tags and their
counts, the custom file for `UPDATEDB` markers, and `systems/` for the dossier
and rules files. Read them together so the user can see where the cycle is.
Details: [`references/workflow-details.md`](references/workflow-details.md).

## Commit conventions

The scripts commit for you, with the co-author trailer you pass as
`commit_co_author` (`🤖 <harness> (<models>) <email>`). Subjects:

- `edcg: scaffold <system> - <summary>` — a new dossier and rules pair;
- `edcg: update <system> - <summary>` — a changed dossier and rules pair;
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
