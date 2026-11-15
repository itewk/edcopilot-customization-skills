# Live Run Checklist

The acceptance run for the EDCoPilot system content skill: one new system from a
blank directory, then one update of an existing system, through to a marker
cycle that EDCoPilot has actually picked up.

Run it against a real content repository and a real EDCoPilot installation.
Every step is a command you can watch and a result you can see; tick a box only
when you have seen the result described beside it.

Commands are shown as `edcg.py <subcommand>`, run from the content root as
`python <skill-dir>/scripts/edcg.py <subcommand>`.

The fresh-session rerun of this checklist is the pre-tag live-run gate. Section
F records the 2026-11-15 run that replaced the salvage.

---

## A. Bootstrap from a blank directory

- [ ] Create an empty directory and make it the working directory. It holds
      nothing: no `systems/`, no config file, no git repository.
- [ ] Run `edcg.py doctor`.
      - [ ] Every check prints `OK` or `FAIL`; no traceback, no silence.
      - [ ] A `FAIL` carries its `fix:` hint, and you relay every one of them.
      - [ ] The content root is reported `blank`.
- [ ] Run `edcg.py init`.
      - [ ] It writes the config file and `systems/` — nothing else; it does not
            copy the house-rules example.
      - [ ] It makes an initial commit unless `--no-git` was passed.
      - [ ] `git log` at the content root shows that commit, and `git status` is
            clean.
      - [ ] This run passes `--co-author "🤖 <harness> (<models>) <email>"`, and
            that initial commit carries the trailer (`git log -1 --format=full`).
            Without the flag the commit is unchanged, so a missing trailer is a
            failed check, not a default.
      - [ ] With `--no-git` the content root is not a git repository, so no step
            in this checklist commits. Say so before starting, and skip the
            commit checks below.
- [ ] Adopt the house rules before any content work.
      - [ ] If `systems/all.rules.toml` does not exist: if a legacy
            `systems/all.rules.toml.example` exists, promote it — copy it to
            `systems/all.rules.toml` and delete the redundant example;
            otherwise copy `assets/all.rules.toml.example` →
            `systems/all.rules.toml`.
      - [ ] The rules are reviewed with the user — each section the example
            contains (logo, banned filters, conversation floors); they may
            modify, add or remove a rule.
      - [ ] The reviewed file rides into the first definition commit the
            workflow makes (`edcg: scaffold` or `edcg: update`).
- [ ] Run `edcg.py doctor` again.
      - [ ] The content root is no longer `blank`.
      - [ ] The `EDCoPilot root` check is `OK`, and the line names the source the
            path came from.
- [ ] If the `EDCoPilot root` check failed, point the skill at EDCoPilot.
      `edcg.py doctor` does not prompt: an unresolvable root is a `FAIL` with a
      `fix:` hint, not a question. Either set `EDCG_EDCOPILOT_ROOT` in the
      environment, or add the path to the content repository's
      `edcopilot-customization-generator.toml`:

      ```toml
      [roots]
      edcopilot = "C:/EDCoPilot/User custom files"
      ```

      - [ ] `edcg.py doctor` is re-run, and the `EDCoPilot root` check is `OK`.
- [ ] Run `edcg.py version` and note the version in this checklist.

## B. New system: the six-phase interview

Ask one phase at a time and wait for the answers. Do not merge phases.

- [ ] Run `edcg.py gather-facts --system <name>`, or start without a name when
      the source has no entry yet.
- [ ] **Phase 1 — high-level concept.** The system's identity and theme are
      stated, and the theme is something the crew would talk about.
- [ ] **Phase 2 — station and character design.** Every station has a voice
      cast; the voices read as people rather than labels.
- [ ] **Phase 3 — plot threads.** The open threads are recorded, including the
      ones deliberately left unexplained.
- [ ] **Phase 4 — produce artifacts.** Ask how many examples each section
      should keep, then write `[content.bounds]` from the answer.
      - [ ] The dossier follows the nine-section spine, in order.
      - [ ] The rules TOML declares `system.names`, `system.dossier` and
            `system.voices`.
- [ ] **Phase 5 — validation loop.** Run `edcg.py validate-definition` with the
      pair on stdin, or keep the dossier and rules in files and pass
      `--dossier-file` / `--rules-file` (the payload then carries only
      `system_name`, and `all_rules` or `--all-rules-file` when present).
      - [ ] Findings are read back to the user and fixed in the artifact, not
            argued away in the rules.
      - [ ] One deliberately wrong payload (a field of the wrong type) produces
            one aggregated `error:`/`fix:` diagnosis on stderr, exit 2, empty
            stdout, and no traceback.
- [ ] **Phase 6 — save.** Run `edcg.py save-definition` with the pair on stdin,
      or with `--dossier-file` / `--rules-file`.
      - [ ] The save accepts the file flags in place of `dossier_md` and
            `rules_toml`, and rejects a field supplied both ways.
      - [ ] The commit lands in the **content repository**, the root holding
            `systems/`. It is made only when `EDCG_AUTO_COMMIT` is true (the
            default) and that root is a git repository; a `--no-git` bootstrap
            means no commit here.
      - [ ] One commit, subject `edcg: scaffold <system> — <summary>` (em dash).
      - [ ] In the content repository: `systems/all.rules.toml` is tracked and
            present at HEAD (it landed with the definition commit).
      - [ ] `git status` in the content repository is clean afterwards.

## C. Write and stage the content

EDCoPilot must be closed before anything writes the custom file or changes
markers. Commits in this section land in the **runtime repository** — EDCoPilot's
root, the directory holding `EDCoPilot.SpeechExtensions.Custom.txt` — and only
when `EDCG_AUTO_COMMIT` is true (the default) and that root is a git repository.
A `--no-git` bootstrap or a non-repository EDCoPilot root means no commits: the
files are still written, so run the `git log` checks below at the runtime root
only when it is a repository.

- [ ] Ask the user to close EDCoPilot, and confirm it is closed.
      - [ ] EDCoPilot is closed; nothing writes the custom file while it runs.
- [ ] Offer the preview gate: a representative sample of about 8-10 lines.
      - [ ] If the user declines, the full block is written.
      - [ ] If the user accepts, the sample is shown, at most one round of
            changes is taken, and then the full block is written.
- [ ] Run `edcg.py writing-brief-data --system <name>`.
      - [ ] The exact tag lines, bounds and voices are in hand before writing.
- [ ] Run `edcg.py validate-content` on each block before writing it.
      - [ ] Findings are reported with their rule id and line.
      - [ ] No rule is weakened to make a block pass.
- [ ] Run `edcg.py write-content` with the approved block.
      - [ ] One commit in the runtime repository, subject
            `edcg: content <system>`.
      - [ ] The block carries its provenance marker, and the file uses CRLF.
- [ ] Run `edcg.py markdb add` with the tags to stage.
      - [ ] One commit in the runtime repository, subject
            `edcg: markdb add <n> tag(s)`.
      - [ ] Every named tag now carries `UPDATEDB`.
- [ ] Ask the user to start EDCoPilot again, and confirm the restart before
      reading logs.
      - [ ] EDCoPilot was restarted with the markers in place.
- [ ] Run `edcg.py check-logs`.
      - [ ] The per-tag report is shown to the user, pass and fail alike.
      - [ ] A failed tag is the user's call: fix and repeat, or accept.
- [ ] Listen in game.
      - [ ] Greetings, broadcasts, chatter and station facts are heard in the
            voices the dossier declared.
      - [ ] No filter marker is read aloud as a phrase.
- [ ] Ask the user to close EDCoPilot again before the markers are removed.
      - [ ] EDCoPilot is closed; removing markers is also a write to the custom
            file.
- [ ] Run `edcg.py markdb remove` with the tags that were staged.
      - [ ] One commit in the runtime repository, subject
            `edcg: markdb remove <n> tag(s)`.
      - [ ] The custom file carries no `UPDATEDB` for those tags.
      - [ ] `git log` at the runtime root shows exactly three commits for this
            cycle: content, marker add, marker remove.

## D. Update an existing system end-to-end

- [ ] Run `edcg.py update-scan` (or `audit --system <name>` for one system).
      - [ ] The deltas are reported per system; process one system at a time.
- [ ] **Phase 1 — review factual changes.** Changes are put to the user, not
      applied silently.
- [ ] **Phase 2 — lore and theme updates.** New lore is consistent with the
      existing tone rules.
- [ ] **Phase 2B — reconcile existing content.** Close EDCoPilot first: every
      rewrite writes the custom file. Read the exact lines with
      `edcg.py get-content --system <name>`, then invalidate what is no longer
      true with `edcg.py rewrite-tag`.
      - [ ] EDCoPilot was closed before the rewrite.
      - [ ] The rewrite staged nothing and committed nothing: the next
            `write-content` owns that commit.
- [ ] **Phase 3 — station and character updates.** Changed stations and voices
      are reflected in both the dossier and the rules file.
- [ ] **Phase 4 — plot thread evolution.** Resolved threads are closed and new
      ones recorded.
- [ ] **Phase 5 — produce updated artifacts.** Dossier and rules are edited in
      place; the nine-section spine is intact.
- [ ] **Phase 6 — validation loop.** Run `edcg.py validate-definition` and fix
      the artifacts, not the rules.
- [ ] **Phase 7 — save.** Run `edcg.py save-definition`.
      - [ ] The commit lands in the **content repository**. It is made only when
            `EDCG_AUTO_COMMIT` is true (the default) and that root is a git
            repository; a `--no-git` bootstrap means no commit here.
      - [ ] One commit, subject `edcg: update <system> — <summary>` (em dash).
- [ ] Run `edcg.py writing-brief-data` and `edcg.py get-content` again, then
      revise with `edcg.py rewrite-tag` and `edcg.py write-content`.
      - [ ] EDCoPilot was closed before the first rewrite.
      - [ ] One commit in the **runtime repository**, subject
            `edcg: content <system>`; `rewrite-tag` itself never commits.
      - [ ] Untouched lines are carried forward byte-for-byte.
      - [ ] New lines land once, on the latest occurrence of the tag.
- [ ] Repeat the marker cycle: close EDCoPilot → `markdb add` → start EDCoPilot
      → `check-logs` → listen → close EDCoPilot → `markdb remove`.
      - [ ] The static or live review choice is put to the user, and the
            reliable path is offered for a tag that already existed.
      - [ ] An existing tag refreshes in game, or the user accepts that it did
            not and says so.
      - [ ] `git log` at the runtime root shows the content, marker-add and
            marker-remove commits for this update.

## E. Sign-off

- [ ] `edcg.py doctor` is still all `OK` at the end of the run.
- [ ] No commit in either repository was made by hand. When a repository is in
      use, both the **content repository** (scaffold and update commits) and the
      **runtime repository** (content and marker commits) are clean.
- [ ] No validation rule was changed to make a run pass.
- [ ] Every authored tag in the custom file traces to a provenance marker the
      skill wrote.
- [ ] Nothing was written to a repository that was not the one under test.

| Field | Value |
|---|---|
| Date | |
| Skill version (`edcg.py version`) | |
| System created | |
| System updated | |
| EDCoPilot build | |
| Run by | |

## F. Why this checklist exists — the 2026-11-15 live run

The first real agent-driven use of the skill failed at dossier authoring
(OpenCode session `ses_e200927cfffeiIMaDStr9VAEmU`, the OB-K b1-8 experiment).
The lore interview was good. The process was not:

1. **The reference was skipped.** The agent never opened
   `references/new-system-interview.md`, so the payload contract and the
   definition checklist were never read.
2. **The schema was invented.** It guessed the `validate-definition` /
   `save-definition` payload shapes, including a dossier passed as a JSON
   object.
3. **The errors became archaeology.** A wrong payload type reached the domain
   layer and came back as a Python traceback, so each turn was spent inferring
   a field name from a stack trace instead of reading it in a document.
4. **The retry loop ended the session.** Four turns of guess-and-crash and the
   human stopped the run. The content repository was reverted to `219b17f` and
   the partial definition was not salvaged.

What now exists to break that chain, one fix per link:

- **Aggregated diagnosis.** `validate-definition` and `save-definition`
  validate every payload field at once: one `error:` line plus its `fix:` hint
  per fault, on stderr, exit 2, empty stdout, never a traceback.
- **File flags.** `--dossier-file` / `--rules-file` (and `--all-rules-file`)
  let the command read the documents from disk, so no agent has to hand-build a
  JSON string around a whole dossier.
- **A worked rules example.** `references/rules.md` §"Authoring a system rules
  file" carries the minimal valid per-system file, and a test runs it through
  `validate_definition` so it cannot drift.
- **Spine pointers.** `SKILL.md` step 3 says to read the interview reference
  first; steps 4 and 5 name every payload field and every file flag, and the
  read-this-when row sends a rules author to the reference.
- **Commit hygiene.** `save-definition` stages exactly the dossier and rules
  files plus the first-save house-rules ride-along, so a stray file in the
  working tree cannot ride into the definition commit.

**The gate.** Nothing from the failed run was salvaged. The pre-tag live-run
gate is a fresh-session rerun of this checklist on a freshly bootstrapped
repository: it must exercise `init --co-author` (A), one deliberately wrong
payload and the file flags (B, phases 5 and 6), and reach `passed: true` →
`save-definition` without the agent ever guessing a payload shape.
