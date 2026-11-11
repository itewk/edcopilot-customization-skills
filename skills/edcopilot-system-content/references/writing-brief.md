# Writing brief

Run `edcg.py writing-brief-data --system <name>` before writing. It returns the
computed values the old prompt used to inline; this file is the prose that goes
with them. Related references: [`rules.md`](rules.md),
[`workflow-details.md`](workflow-details.md).

The payload has `tag_lines` (system and per-station, with the exact text), and
`landable_stations` (name, build type, body, status). It also carries `bounds`
(the per-kind default plus per-station overrides), `voices` (dossier, rules,
declarations and the declarations missing on either side), `raven_revision`,
`dossier_path` and `rules_path`, and `site_count`.

Write the content, then validate it with `edcg.py validate-content` before
`edcg.py write-content`. The rules themselves are explained in
[`rules.md`](rules.md); this file is how to write to them.

## THE TAG UNIVERSE

Copy tag lines from `tag_lines` verbatim: no spaces around `<~>`, and the
system and station segments are case-sensitive, matching the exact in-game
names.

- System-level, one each: `@SystemGreeting<~><system>` and
  `@SystemBroadcast<~><system>`.
- Per-station, three each: `@StationGreeting<~><system><~><station>`,
  `@StationChatter<~><system><~><station>` and
  `@StationFact<~><system><~><station>`.

The general shape is `@TagKind<~>system<~>station`; the station segment is
omitted for system tags. Every landable, non-tentative station in §7 coverage
gets all three station tags; non-landable sites get none.

## FORMAT REMINDERS

1. **One line per candidate phrase** — EDCoPilot picks one line at random from a
   tag.
2. **Whole conversation on one line** — use `[<Voice1>]text[<Voice2>]text` for
   multi-character exchanges. A voice name is one token: `[<GarrettControl>]`,
   never `[<Garrett Control>]`.
3. **NO `[example]` wrapper** — that belongs to chatter files only.
4. **Tag line format** — `@TagKind<~>system<~>station`.
5. **Filter markers** go after the voice tag: `[<Voice>](filter)text`, not
   `(filter)[<Voice>]text`.
6. **Station Fact format** — tag line, then `img_url=...`, then the title, then
   the paragraphs.
7. **Station tag naming** — case-sensitive, exact in-game name.
8. **Provenance marker** — a provenance comment marks the start of authored
   content; the writer inserts one per tag block.
9. **Line endings** — CRLF, no BOM.
10. **Database marker** — `UPDATEDB` is added on the line after a tag by
    `edcg.py markdb add`, after content is written and validated.

## TOKEN VOCABULARY

Use tokens, never a literal player name.

- `<Commander>` — a control addressing the player (greeting, hail, notice).
- `<cmdrname>` — a speaker who knows them by name, or talking about them.
- `<Commander> <cmdrname>` — the formal pair (garrisons, official).
- `<myshipname>` — the ship, for lines about the ship.

**Never write 'Commander' literally** in authored prose; use the token. Do not
write a real player name either. The vocabulary is `[vocab]` in this skill's
`assets/base.toml`: `[vocab.documented]` lists `<Commander>`, `<cmdrname>`,
`<myshipname>`, `<fuelLevels>`, `<starsystem>`, `<stationname>` and the rest,
with what EDCoPilot substitutes for each. `[vocab.undocumented]` lists tokens
EDCoPilot's own content uses without documenting them (`<systemname>`,
`<bodyName>`, `<ship1>`, `<greeting>` and so on). Prefer the documented tokens;
use an undocumented one only to match the game's own phrasing.

## FILTER REQUIREMENTS

### (allbusiness) — All Business Mode

Applies to `@SystemGreeting`, `@SystemBroadcast`, `@StationGreeting` and
`@StationChatter`.

- Every tag in that list MUST have **at least 1 line with `(allbusiness)`**.
- Every tag MUST also have **at least 1 line with NO filters** (plays for
  everyone).
- Every tag MUST have at least 1 line with **ONLY `(allbusiness)`**, which plays
  in All Business and any other mode.

The warning threshold is `warn_below`; the floor is an error when zero.

### (vegan) — Vegan Mode

Any phrase referencing meat or animal products must carry `(vegan)`. A station's
own name (for example a name containing "Bacon") is a NAME, not a reference, so
it needs no filter. **Station Facts take no filters**: wording must be safe
without them.

### Other required filters

`(alcohol)`, `(profanity)`, `(flirt)` and `(innuendo)` are required wherever the
subject matter triggers them. The house rules also define **BANNED FILTERS**;
those markers are forbidden in authored content regardless of the wording.

### All known filters

`[rules.syntax.filter_known]` in `assets/base.toml` lists the known filter
markers with their meanings. Use only markers from that list, and only where the
content needs them.

## WHERE THE RULES LIVE

- House rules for this content repository: `systems/all.rules.toml`. That is
  where the banned-filter list, the image style and any project policy live.
- Tool-wide rules, `[rules.syntax.filter_known]` and the `[vocab]`
  documented/undocumented lists: this skill's `assets/base.toml`.
- One system's overrides: `systems/<slug>.rules.toml`.
- The per-kind bounds: in the `writing-brief-data` output, resolved from the
  system rules and `assets/base.toml`.

## RULE POINTERS

These rule ids are the ones a writing pass trips over most often:

- `content.commander_token` — the player is addressed with `<Commander>`.
- `content.station_landable` — only landable stations get station content.
- `content.fact_image` — a Station Fact's `img_url` matches the expected image.
- `syntax.filter_known` — every filter marker is a known one.
- `syntax.filter_leads` — a filter marker leads the line, after the voice.
- `syntax.token_known` — every `<token>` is known.
- `syntax.token_case` — token spelling keeps its documented case.
- `filters.allbusiness` — the All Business floor and fallback lines.
- `filters.fallback` — every tag keeps a line that plays for everyone.
- `filters.banned` — banned markers never appear.

Read the full rule, with its reason, in [`rules.md`](rules.md) before changing
any of them.

## SECTION SIZE (minimum and maximum examples)

Counts are total lines per tag and **INCLUDE the filter-mandated lines**, so a
minimum of 3 leaves one creative line. Station facts count **paragraphs after the title**; the title is not a paragraph.

| Kind | Minimum | Maximum |
|---|---|---|
| SystemGreeting: 3-6 | 3 | 6 |
| StationGreeting: 4-8 | 4 | 8 |
| StationChatter: 6-12 | 6 | 12 |
| SystemBroadcast: 8-16 | 8 | 16 |
| StationFact: 1-3 paragraphs | 1 | 3 |

Meet the minimum for every tag; below the minimum is an error. Exceeding the
maximum is a warning: volume is a taste question, not a correctness one.

A system overrides only the kinds it cares about in its own rules file, under
`[content.bounds]`. A station may carry its own bound when it differs from the
rest of the system:

```toml
[content.bounds.stations."Takenouchi Settlement (ii-42)"]
StationChatter = [12, 24]
```

Resolution is **most-specific-first**: station override, then the system's kind
bound, then the base default. An override for a station that is not in the
content is a warning, so a rename cannot silently do nothing.

## WRITE, VALIDATE, COMMIT

Write one phrase per line, a whole conversation on one line, no `[example]`
wrapper, tokens rather than a literal player name, and the filter markers the
house rules require. Then validate the block with
`edcg.py validate-content` (JSON payload with `system_name` and `content`), fix
every error, and repeat until `passed` is true. Print the validation rule table:
one pass, warn, error or manual row per rule, including the policy rules the
user confirms by hand.

Only then run `edcg.py write-content` with `system_name`, `content_block`,
`model` and `commit_co_author`. It appends the block below a provenance comment;
it never replaces or reorders existing content, and it commits any rewrites
already staged by `edcg.py rewrite-tag`.
