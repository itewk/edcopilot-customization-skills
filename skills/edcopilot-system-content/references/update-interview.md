# Update interview

Use this when the system already has a dossier and rules file. Related
references: [`writing-brief.md`](writing-brief.md), [`rules.md`](rules.md),
[`workflow-details.md`](workflow-details.md).

Refresh, then invalidate, then offer variety, then make room. The seven phases
are fixed: ask in order and wait for the answers. The agent **must not invent
facts** to fill a gap.

## PHASE 1: REVIEW FACTUAL CHANGES

Run `edcg.py update-scan` first and read this system's entry. The scan computes
the fact diff: `raven_revision` old and new; new, lost and renamed stations;
build-type and status changes; new and lost non-landable sites; journal-only
stations; fact availability and `has_changes`. For one system's raw facts
without the scan, run `edcg.py gather-facts --system <name>`.

`edcg.py audit --system <name>` answers a different question: whether the
sources disagree with each other. Use it for source availability, discrepancies
by category and severity, counts, the Raven revision and the last journal visit.

Review each item and decide how to incorporate it into the updated design.

**For each change, consider:**

1. Does this change the station's role, personality, or voice needs?
2. Does this affect the system's theme or lore?
3. Are there new stations that need StationGreeting, StationChatter and
   StationFact content?
4. Are there lost stations whose content should be archived or removed?
5. Do status changes (plan to build, build to complete) warrant new chatter
   about construction?

**Output for this phase:** A decision on each change — incorporate, defer, or investigate further.

The authority order settles disputes: Raven is authoritative for the plan, the
journal outranks Raven for ground truth, and Inara and Spansh are advisory. A
station missing from the journal is unknown, not disproved.

## PHASE 2: LORE & THEME UPDATES

1. **Theme evolution** — do new stations or status changes shift the theme? A
   new starport means trade-hub weight; a pirate outpost means a lawless fringe.
2. **Lore hooks for new stations** — who funded them, and why here?
3. **Updated timeline** — construction start dates and completion estimates.
4. **Faction dynamics** — do new stations introduce factions or shift power?
5. Update dossier **§2 Lore and Theme**, and adjust **§3 Tone Rules** if the
   theme shifted.

**Output for this phase:** Updated §2 and §3.

## PHASE 2B: RECONCILE EXISTING CONTENT

Existing dialog may no longer be true. Fix it before writing anything new. Read
the current content first:

```
edcg.py get-content --system <name>
```

It returns each authored tag, its lines, how many blocks contain it, its count
and the applicable minimum and maximum. Never guess at a line's exact text.

**1. Invalidate (do this without asking).** Remove every line that the new facts
or lore make untrue: a station that finished construction loses its
under-construction lines; a site that was renamed loses lines using the old
name; changed lore drops dialogue that now contradicts it. Run
`edcg.py rewrite-tag` per affected tag with a JSON payload such as
`{"system_name": "...", "tag": "@StationChatter<~>System<~>Station",
"remove": ["exact line"]}`. It validates before writing and leaves the edit
**uncommitted**: the next `edcg.py write-content` commits it, so a mistake is
recoverable with git.

**2. Variety (ask).** Offer to replace still-valid lines purely for freshness,
only on request: replace only what the user agrees to, using
`"replace": {"old line": "new line"}`.

**3. Room (ask when full).** Add lines for new lore with `"add": ["new line"]`
while the tag is under its maximum. At the maximum, ask which the user wants:
replace existing lines with the new material, or raise the maximum for that tag
(edit the system rules, then save the definition as usual).

Removals and replacements apply to every occurrence of a tag; additions go to
the latest occurrence only. After the edits the tag must still satisfy its
bounds. The rewrite refuses an edit that introduces a validation error, so
resolve it here rather than saving invalid content; errors that already existed
do not block it. `UPDATEDB` markers are preserved.

## PHASE 3: STATION & CHARACTER UPDATES

List the affected stations from Phase 1: **New stations needing content**,
**Stations removed (archive content)**, and **Stations with status changes**
(or say "(none)" for each).

For EACH new landable station:

1. **Station personality** — corporate, frontier, military, pirate, scientific?
2. **Key voices** — 2-4 voices with tags, roles, quirks and filter usage. A
   voice name is ONE token: `[<GarrettControl>]`, never `[<Garrett Control>]`.
3. **Station-specific lore hooks** — rumours, events, conflicts.

For status changes: **Construction chatter** (workers, engineers, progress) and
transition narratives (how the vibe shifts during the build). For lost
stations: **Archive or remove** — log the removal, drop it from coverage, delete
its tags.

For system-wide voices: do new stations add voices heard everywhere? Does the
`@SystemBroadcast` mix change? Are there still two conversation families
(formal and familiar)?

**Output for this phase:** Updated §8 Writing Rules — Voices Used, Addressing
the Player, Conversation Families.

## PHASE 4: PLOT THREAD EVOLUTION

1. **Review existing threads (§9)** — resolved, stalled or escalated?
2. **New threads** from new stations: espionage, labour disputes, smuggling.
3. **Status change threads** — milestones, accidents, delays, a grand opening.
4. **Cross-station threads** — do new stations connect existing storylines?
5. Each thread: title, description, stations involved, timeline, hooks.
6. Aim for 3-6 active threads spanning different tones.

**Output for this phase:** Updated §9 Open Threads.

## PHASE 5: PRODUCE UPDATED ARTIFACTS

Begin by opening the existing `systems/<slug>.md` and
`systems/<slug>.rules.toml`; their paths are `dossier_path` and `rules_path` in
the `writing-brief-data` output. Read both before editing. Update those files
**in place** rather than regenerating them, so the corrections log and the git
history survive. Then produce the TWO UPDATED artifacts from Phases 1-4. Read
the template first with [`../assets/dossier-template.md`](../assets/dossier-template.md).

### Artifact 1: UPDATED System Dossier (Markdown)

§1 Identity and Canon (revision and site-table reference); §2 Lore and Theme;
§3 Tone Rules; §4 Canon Site Table (new and changed stations moved between
Complete, Under Construction, Definitely Planned and Tentatively Planned, with
build type, body and status; remove lost stations); §5 Corrections Log (removed
or renamed material, with the reason); §6 Site List Maintenance (Raven revision);
§7 Coverage (ALL landable stations, built and planned, NOT tentative, with
case-sensitive exact names); §8 Writing Rules (voices, tokens, conversation
families); §9 Open Threads.

### Artifact 2: UPDATED System Rules (TOML)

```toml
[system]
names = ["Exact System Name", "Alternative Name"]
dossier = "systems/<slug>.md"
voices = ["Voice1", "Voice2", "Voice3"]  # MUST match dossier §8 exactly
```

`names` must include the exact in-game name and the dossier path is relative to
the content root; update the revision reference in §1 and §6.

**Output for this phase:** UPDATED dossier markdown and UPDATED rules TOML,
ready for validation.

## PHASE 6: VALIDATION LOOP

Validate the UPDATED artifacts before saving. This is an ITERATIVE loop:

1. Run `edcg.py validate-definition` with the updated dossier and rules:

   ```json
   {
     "system_name": "Your System",
     "dossier": "...updated dossier markdown...",
     "rules": "...updated rules TOML...",
     "all_rules": "...optional house rules..."
   }
   ```

2. Read the findings. `passed: true` goes to Phase 7; an `error` is fixed and
   re-validated; a `warn` is advisory but understood.
3. Common checks for updates: all 9 dossier sections present and in order; §4
   tables parse; §7 coverage lists exactly the landable stations from §4; voices
   in rules.toml match dossier §8 exactly; `img_url` matches the fact-image
   expectation; rules.toml has `system.names`, `system.dossier` and
   `system.voices`; the system name parameter matches rules.system.names; the
   corrections log (§5) documents removed content.
4. Repeat until `passed: true`.

**Do not proceed to Phase 7 until validation passes.**

## PHASE 7: SAVE

Once `validate-definition` returns `passed: true`:

1. Run `edcg.py save-definition`:

   ```json
   {
     "system_name": "Your System",
     "dossier_md": "...validated updated dossier...",
     "rules_toml": "...validated updated rules...",
     "commit_co_author": "🤖 <harness> (<models>) <email>"
   }
   ```

2. It overwrites both files, creates `edcg: update <system> — <summary>`, adds
   the trailer `Co-authored-by: 🤖 <harness> (<models>) <email>` from
   `commit_co_author`, and returns the commit hash and files changed.
3. Verify with `git -C <content root> log -1 --oneline`.
4. A cycle leaves **exactly three runtime commits**: content, marker add, marker
   remove. Only **after the user confirms** the in-game test and the database
   upload, run `edcg.py markdb remove`. Pass the same `commit_co_author` to all
   three.

## Select only the content that changed

Run `edcg.py writing-brief-data --system <name>`. Its tag list is the whole system's tag universe, not a diff. Use the Phase 1 diff and the custom file to keep only tags that are new, renamed (only if the game still reports the old name), factually changed (status, build type, body or role), or newly covered.

Leave every unchanged tag alone. Write, validate and `edcg.py write-content`
only that selection, then run
`edcg.py markdb add --tag <tag> --tag <tag>` (or send a JSON payload with
`tags`) for that selection only. Confirm that every old tag still occurs exactly once, every new tag occurs once, and the latest provenance block holds only the
new or changed tags. If the diff is ambiguous, ask rather than guess.

## Batch update

When facts may have moved, run `edcg.py update-scan` — for one system or many.
It returns one entry per system with the Raven revision delta,
new/lost/renamed/status changes, fact availability and `has_changes`. Process
the changed systems one at a time: Phases 1-4, then validate, then save, before
the next system. Do not batch validation or save calls across systems; systems
without changes need no content work.

A system with an `error` (unparsable rules; rules declare no system name; failed fact gathering) is reported
rather than dropped; a system without a rules file is `skipped`. Both are things
to investigate, not passes.
