# Workflow details

Markers, log checks, branches and the git rules that hold a cycle together.
Related references: [`new-system-interview.md`](new-system-interview.md),
[`update-interview.md`](update-interview.md),
[`writing-brief.md`](writing-brief.md), [`rules.md`](rules.md).

## Two roots

Two root directories, never confused:

- **The content root** holds the dossiers, rules, config and its git history.
  `edcg.py save-definition` and `edcg.py init` write here.
- **The EDCoPilot root** is the game's "User custom files" folder. It holds
  `EDCoPilot.SpeechExtensions.Custom.txt`. `edcg.py write-content`,
  `edcg.py rewrite-tag` and the marker commands write here, and nothing else
  does.

The skill writes only the custom file and marker lines in the runtime folder. It
never edits game configuration, keybinds or other EDCoPilot files.

## Environment variables

Every `EDCG_*` setting is read from the environment; none is required. A variable
that is unset or empty falls back to the default in the table.

| Variable | Effect |
|---|---|
| `EDCG_EDCOPILOT_ROOT` | The runtime root (EDCoPilot's "User custom files" folder). Resolution order: this variable when it names an existing directory, then `roots.edcopilot` in the content repository's config file (a relative value resolves against the content root), then ask the user. |
| `EDCG_CONTENT_DEFINITIONS_ROOT` | Content root override. Defaults to the current working directory; it must name an existing writable directory. |
| `EDCG_EDCOPILOT_LOGS_DIR` | Logs directory override. Defaults to the `logs/` sibling of the EDCoPilot root, falling back to `logs/` inside it. |
| `EDCG_JOURNAL_DIR` | Elite Dangerous journal directory override. When set, this path is checked first for Journal.*.log files. If found, it's used; otherwise falls through to the platform-specific candidates. |
| `EDCG_AUTO_COMMIT` | Gates the runtime writes only: `write-content`, `markdb add` and `markdb remove` commit when it is true (the default). `save-definition` always commits, and `init` commits unless `--no-git` was passed. |
| `EDCG_INARA_API_KEY` | Inara API key. When unset, Inara checks are skipped and `audit` reports "Inara API key is not configured." — the answer to "why is Inara unavailable". |
| `EDCG_SPANSH_ENABLED` | Whether Spansh is queried. Defaults to true. |
| `EDCG_RAVEN_API_URL` | Raven Colonial base URL. Defaults to the hosted Raven Colonial service. |
| `EDCG_LOG_LEVEL` | Accepted but currently unused (reserved). |
| `EDCG_DEEPL_API_KEY` | Reserved; accepted and ignored. Nothing uses it yet. |

## The marker cycle

Content is invisible to EDCoPilot's database until a tag carries an `UPDATEDB`
line. The marker goes on the line **after** its tag line.

1. Write and validate the content; close EDCoPilot first.
2. Run `edcg.py write-content`. It appends each block below a provenance
   comment and makes one commit.
3. Run `edcg.py markdb add` with every tag in the block (repeat `--tag` or send
   a JSON payload with `tags`). Every marker lands in one write and one commit.
   The command prints a warning for any requested tag that matched no authored
   content: compare `modified_tags` to the tags you passed, and stop and
   reconcile the station or tag name before proceeding.
4. Ask the user to restart EDCoPilot, then confirm they did.
5. Run `edcg.py check-logs` and show the report.
6. Ask the user to test the content in game and upload the database from inside
   EDCoPilot, then run `edcg.py markdb remove` with the same tags. Every marker
   clears in one write and one commit. A missing tag in `modified_tags` matched
   no authored content: stop and reconcile the station or tag name before
   proceeding.

Do not add `UPDATEDB` by hand before `edcg.py markdb add`: the script owns the
marker and the commit. If a tag disappears from the file, stop and find out why
before adding it back. Each marker is preserved by a rewrite, so editing lines
never silently drops the update.

A tag rewritten by `edcg.py rewrite-tag` stays uncommitted until the next
`edcg.py write-content`, which owns the content commit. That is deliberate: one
predictable content commit covers an append and any staged rewrites.

## What check-logs reports

`edcg.py check-logs` reads
`<EDCoPilot root>/../logs/EDCoPilotGUI.log.<timestamp>.txt`, or
`EDCG_EDCOPILOT_LOGS_DIR` when the logs live elsewhere. It reports:

- `checked`, `log_path` and `since` — `--since` takes an ISO 8601 timestamp and
  defaults to the custom file's modification time;
- `failures` — one entry per failing tag with its reason and the raw log line;
- `skipped_update` — true when EDCoPilot did not process a change because the
  custom file was unchanged since the last update;
- `ok` — clean only when there are no failures and no skipped update;
- `summary` — a one-line explanation, and with `--system`, the failures are
  scoped to that system's tags.

Show the result per-tag. When a tag failed, the **user decides**: fix the
content and repeat the marker cycle, or accept the failure and continue. Do not
hide a failure, and do not remove markers to make a report look clean.

An `ok: false` with `checked: false` means no cycle can be checked yet: no log
was found after the marker add, or no custom file exists to date the cycle. The
summary names which, so say which one it is rather than calling it a pass.

## Advisory gates

None of these gates refuses; the agent asks and then obeys the answer.

- **Preview** — after the definition is saved, ask whether the user wants a
  small representative sample before the full generation. Show the
  `@SystemGreeting` block, one `@SystemBroadcast` line and one representative
  station's greeting, chatter and fact: **8-10 lines** at most. Take one round
  of changes, then continue.
- **Review choice** — ask whether to mark the content immediately or pause for a
  static or live review first. Static means the user reads the file or the diff;
  live means they restart EDCoPilot and listen. Live review is reliable for new
  tags; an updated existing tag may not refresh until `UPDATEDB` is added, so
  offer static review as the reliable path.
- **Restart** — after markers are added, ask the user to restart EDCoPilot and
  confirm before the log check.
- **Log check** — present the per-tag report before removing markers.
- **In-game test and upload** — after the log check, ask the user to test the
  content in game and upload the database from inside EDCoPilot. Only after they
  confirm, remove the markers.

Show a **progress table** at every gate, derived from the repository rather than
stored: `edcg.py branch status` for the active branch,
`edcg.py get-content --system <name>` for authored tags and their counts, the
custom file for open `UPDATEDB` markers, and `systems/` for the dossier and
rules files. Read them together; the content repository is the state.

## Audit

`edcg.py audit --system <name>` answers "do the sources disagree?", not "what
has been written?" — derive that from the repository as the progress table
does. Audit compares Raven, the journal, Inara and Spansh without writing
anything. It reports the sources reached with record counts,
discrepancies by category and severity, totals, `passed` (false only for an
error-severity landability conflict between Raven and Spansh), the Raven
revision and the last journal visit.

An empty report with no evidence is not a pass. If a source was unavailable,
say so and let the user decide whether the remaining evidence is enough. A
missing journal station is expected until the player docks there.

## Branches

Branch state is read back from git, not remembered in a process. That is what
makes a cycle survive across separate command invocations.

```
edcg.py branch start <description>
edcg.py branch status
edcg.py branch review
edcg.py branch finalize          # --merge (default), --push
edcg.py branch abort            # --confirm to actually discard
```

`edcg.py branch start` creates and checks out a matching branch in both
repositories and records the systems it affects. When the runtime root is not a
git repository, it makes a timestamped **backup** of the custom file instead.
`edcg.py branch status` reports the active branch, each repository's current
branch and its uncommitted changes. `edcg.py branch review` prints the diff.
`edcg.py branch finalize` merges into the default branch and reports the merge
commits; `edcg.py branch abort --confirm` discards the branch and its commits.

Offer a branch before the work starts, never after artifacts exist. Never create
a branch the user did not ask for.

## Git rules

- A design or update cycle leaves exactly **three commits** in the runtime
  repository: content, marker add, marker remove. The content repository gets
  one commit per saved definition.
- Subjects: `edcg: scaffold <system> — <summary>` and
  `edcg: update <system> — <summary>` for definitions, `edcg: content <system>`
  for content, `edcg: markdb add <n> tag(s)` and `edcg: markdb remove <n> tag(s)`
  for markers (the tag list goes in the commit body).
- Every commit names its producer through a `Co-authored-by:` trailer. Pass the
  harness and model(s) actually in use as `commit_co_author`; the script adds
  the trailer. If you create a commit yourself, append the same trailer.
- `EDCG_AUTO_COMMIT` gates the runtime writes: `write-content`, `markdb add` and
  `markdb remove` commit only when it is true. `save-definition` always commits
  the content repository, and `init` commits the initial scaffold unless
  `--no-git` was passed. Turn the setting off only when the user explicitly
  wants to inspect runtime changes before committing.
- A **dirty** tree is a stop condition: each script stages all changes in its
  repository, so unrelated edits would be swept into the tool's commit. Ask the
  user to commit or stash first.
- A provenance comment marks the start of authored content, one marker per tag block. Validation reads from the last provenance marker, and the rewrite path
  collapses intermediate markers before validating so an edit is still checked
  against every authored block. The provenance comment uses the historical
  package identifier and version `0.1.0` deliberately, to keep byte-compatibility
  with previously written content; it is not the skill version.

## Stop and ask the human

- Either root is not a git repository, or its identity is missing, so a
  "successful" write would leave no commit.
- The working tree is dirty before a writing or committing step.
- A validation error means the rule and the content disagree about intent:
  change the rule deliberately, with its reason, rather than deleting content to
  silence it.
- A fact source is unavailable and the remaining evidence cannot settle a
  factual question.
- A tag is already present with different content, or an old tag would be
  duplicated.
- An update reports a conflict that neither the journal nor Raven clearly
  resolves.
