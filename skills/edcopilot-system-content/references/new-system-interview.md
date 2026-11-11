# New system interview

Use this when the system has no definition yet. Related references:
[`writing-brief.md`](writing-brief.md), [`rules.md`](rules.md),
[`workflow-details.md`](workflow-details.md).

Work through the phases **one phase at a time**. Ask the questions in order,
then wait for the answers before writing a file or moving on. The human answers
the interview; the agent proposes, writes and validates. The agent **must not invent facts** to fill a gap: if a source is unavailable, record that and let
the human decide whether the remaining evidence is enough.

Before Phase 1, ask once whether to do the work on a feature branch. This offer
is optional; if the user accepts, run `edcg.py branch start <description>`
before producing artifacts. If they decline, stay where you are and say so.
Never create a branch without being asked.

## FACTUAL BASELINE (from live data)

Gather facts first when the system has a Raven entry: run
`edcg.py gather-facts --system <name>` and show the result. When the system has
no Raven entry, skip gathering and start the interview from the human's
description instead, saying that no live baseline exists.

The baseline is grouped by what it means for the design:

- **LANDABLE STATIONS** — have landing pads, so each one needs
  `StationGreeting`, `StationChatter` and `StationFact` content.
- **NON-LANDABLE SITES** — hubs and installations: **no station content**; their
  material goes into system-level content and the dossier's site table.
- **BODIES WITH STATIONS** — what a Commander sees from the station: type,
  atmosphere, temperature, pressure, gravity, radius, volcanism, orbit and
  terraforming state. At most 20 are shown; the rest are counted.
- **JOURNAL-ONLY STATIONS** — docked by the player but absent from Raven:
  investigate.
- **CONFLICTS BETWEEN SOURCES** — resolve every one during design, not by
  picking the convenient value.

The authority order is the same everywhere: Raven is authoritative for the plan,
the journal outranks Raven for ground truth, Inara and Spansh are advisory. A
station missing from the journal is unknown, not disproved.

## LORE NOTES: STATIONS AND BODIES

Once the system name is known, review the station and body overview with the
user and ask:

> Tell me anything special lore-wise about any of these stations or bodies —
> origins, local legends, notable residents, unusual conditions, conflicts,
> rumours, or anything the APIs get wrong or leave out. If a station or body
> should stay deliberately plain, say so.

**Output for this question:** A bullet list of lore notes keyed to the station
or body name, or "none" if nothing special.

Do not write Phase 2 until this answer exists.

## PHASE 1: HIGH-LEVEL CONCEPT

Establish the core identity of this system. Answer:

1. **System name** — exact casing as it appears in-game.
2. **Architect** — the colonisation architect name (for example, a player
   group or squadron).
3. **Colonising group** — who settled here? Corporation, faction, independent.
4. **Theme summary** — one paragraph: what is this system *about*? Corporate
   exploitation, scientific frontier, military outpost, religious pilgrimage.
   The theme drives all voice, tone and content decisions.

**Output for this phase:** A completed §1 Identity and Canon section for the
dossier.

## PHASE 2: STATION & CHARACTER DESIGN

Design the personality of each landable station and the voices that inhabit it.
Reference the factual baseline — only landable stations get station content.

For EACH landable station:

1. **Station personality** — corporate sterile, gritty frontier, scientific
   curiosity, military discipline, hedonistic pleasure port?
2. **Key characters and voices** — who speaks here? Name 2-4 voices, each with
   a voice tag, role or archetype, personality quirks, and the filters it uses
   (allbusiness, vegan, and so on).
   Voice names are ONE token, with no spaces: write `[<PortAuthority>]`, never
   `[<Garrett Control>]`.
3. **Station-specific lore hooks** — rumours, ongoing events, local conflicts.

For the SYSTEM overall:

4. **System-wide voices** — voices heard across stations.
5. **Broadcast style** — the `@SystemBroadcast` mixes announcements, monologues
   and multi-character conversations. Describe the mix.
6. **Conversation families** — two families per the dossier template: one
   formal and official (uses `<Commander> <cmdrname>`), one familiar and
   personal (uses `<cmdrname>` or `<Commander>`).

**Output for this phase:** Completed §2 Lore and Theme, §3 Tone Rules, and §8
Writing Rules, especially the Voices Used and Addressing the Player subsections.

## PHASE 3: PLOT THREADS

Define ongoing narrative threads that content can reference. These become the
Open Threads in dossier §9 and seeds for station chatter.

For each thread define:

1. **Title** — short and evocative.
2. **Description** — what is happening, who is involved, what is at stake.
3. **Stations involved** — whose chatter and facts reference this.
4. **Timeline** — imminent, ongoing, long-term or dormant.
5. **Resolution hooks** — how players might discover or influence it.

Aim for 3-6 threads spanning different tones: corporate intrigue, scientific
mystery, social conflict, environmental survival, personal drama.

**Output for this phase:** Completed §9 Open Threads with structured entries.

## PHASE 4: PRODUCE ARTIFACTS

Produce the two required artifacts from Phases 1-3. Read the template first with
[`../assets/dossier-template.md`](../assets/dossier-template.md); it is the structure validation enforces.

### Section size (minimum and maximum examples)

Before writing the rules file, ask how many examples each section should keep,
offering these defaults: system greeting 3-6 lines, station greeting 4-8,
station chatter 6-12, system broadcast 8-16, station facts 1-3 paragraphs. The
counts are total lines per tag and **includes the filter-mandated lines**, so a
minimum of 3 leaves one creative line. Then ask once:
"any stations that should carry more or less?" and record only the stations the
user names. Put the answers in the rules file as `[content.bounds]`, and
`[content.bounds.stations."<station>"]` for the exceptions. The full semantics
are in [`rules.md`](rules.md).

### Artifact 1: System Dossier (Markdown)

Create a complete nine-section dossier:

1. **Identity and Canon** — from Phase 1, including the body map: use the
   factual baseline when one exists, otherwise the bodies described in the
   interview.
2. **Lore and Theme** — from Phases 1 and 2.
3. **Tone Rules (hard constraints)** — from Phase 2.
4. **Canon Site Table** — from the baseline and the lore notes, with tables for
   Complete, Under Construction, Definitely Planned and Tentatively Planned,
   plus the non-landable sites table.
5. **Corrections Log** — empty for a new system.
6. **Site List Maintenance** — the Raven reference and placeholder rules.
7. **Coverage** — list ALL landable stations (built and planned, NOT tentative),
   with the case-sensitive exact in-game station names, and say where
   non-landable material goes.
8. **Writing Rules** — from Phase 2: Voices Used (matching the rules file
   exactly), Addressing the Player (tokens), Conversation families.
9. **Open Threads** — from Phase 3.

### Artifact 2: System Rules (TOML)

Create `<slug>.rules.toml` with:

```toml
[system]
names = ["Exact System Name", "Alternative Name"]
dossier = "systems/<slug>.md"
voices = ["Voice1", "Voice2", "Voice3"]
```

Critical rules:

- `voices` MUST match the voices declared in dossier §8 exactly.
- `names` must include the exact in-game system name.
- `dossier` is relative to the content root.
- Add `[content.bounds]` from the section-size answer; no rule overrides are
  needed for a new system.

**Output for this phase:** Two strings — dossier markdown and rules TOML —
ready for validation.

## PHASE 5: VALIDATION LOOP

Validate before saving. This is an ITERATIVE loop:

1. Run `edcg.py validate-definition` with a JSON payload on stdin:

   ```json
   {
     "system_name": "Your System",
     "dossier": "...dossier markdown...",
     "rules": "...rules TOML...",
     "all_rules": "...optional house rules..."
   }
   ```

2. Read the findings: `passed: true` goes to Phase 6, an `error` is fixed and
   re-validated, a `warn` is advisory but understood.
3. Common checks to fix first:
   - all 9 dossier sections present and in order;
   - §4 site tables parse (markdown tables with a `Build type` column);
   - §7 coverage lists exactly the landable stations from §4;
   - voices in rules.toml match voices in dossier §8 exactly;
   - the `img_url` in §7 matches the `all.rules.toml` fact-image expectation;
   - rules.toml has `system.names`, `system.dossier` and `system.voices`.
4. Repeat until `passed: true`.

**Do not proceed to Phase 6 until validation passes.**

## PHASE 6: SAVE

Once `validate-definition` returns `passed: true`, persist the artifacts:

1. Run `edcg.py save-definition` with:

   ```json
   {
     "system_name": "Your System",
     "dossier_md": "...validated dossier...",
     "rules_toml": "...validated rules...",
     "commit_co_author": "🤖 <harness> (<models>) <email>"
   }
   ```

2. What it does: writes `systems/<slug>.md` and `systems/<slug>.rules.toml`,
   creates the commit `edcg: scaffold <system> — <summary>`, adds the
   `Co-authored-by:` trailer supplied in `commit_co_author`, and returns the
   commit hash and files changed.
3. Verify the commit in the content repository with
   `git -C <content root> log -1 --oneline`.
4. Next: write the content. Read [`writing-brief.md`](writing-brief.md) for the
   brief, run `edcg.py validate-content` on the block, then run
   `edcg.py write-content`. A design cycle leaves **exactly three runtime commits**: content, marker add, marker remove. Only **after the user confirms** the in-game test and the database upload, run
   `edcg.py markdb remove`. Pass the same `commit_co_author` to all three.

Use the `Co-authored-by: 🤖 <harness> (<models>) <email>` trailer form: name
the harness and the model(s) actually in use, never the example. Do not commit
from `edcg.py rewrite-tag`; it stages the edit for `edcg.py write-content`,
which owns the content commit.
