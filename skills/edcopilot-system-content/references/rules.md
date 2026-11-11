# Rules

Every validation finding comes from a rule. A rule is TOML, declared in one of
three layers, and carries its own reason so nobody has to guess why it exists.
Related references: [`writing-brief.md`](writing-brief.md),
[`workflow-details.md`](workflow-details.md).

```toml
[rules.content.station_landable]
severity = "error"
impl = "rule_station_landable"
why = "Only a station with landing pads can greet a Commander."
```

## The three layers

| Layer | File | Holds |
|---|---|---|
| base | the skill's `assets/base.toml` | Tool-wide defaults and the dossier spine. Not copied into the content repository. |
| house | `systems/all.rules.toml` | Project policy for every system: image style, banned filters, extra rules. |
| system | `systems/<slug>.rules.toml` | What one system overrides or adds. |

Override **precedence** is base, then house, then system: the most specific
layer wins for every key it declares, and the other keys keep their inherited
value. House rules can declare new rules, so project policy does not need a
base change. A system normally overrides only bounds and voices.

Two field values change how a rule behaves:

- `severity = "off"` retires the rule for that layer and below; the validator
  skips it.
- `impl = "policy"` marks a rule a human checks, not the validator. It appears
  in the validation table as a manual row, and the user confirms it by hand.

## The why field

`why` is the rule's reason, in the words the user should read. It is what makes
a finding actionable: "only landable stations get station content" is a
decision, not a preference. Read the why before changing a rule, and never ship
a rule without one.

## The catalogue

- `syntax.filter_known` — every `(filter)` marker is on the known list, which is
  also printed in the brief.
- `syntax.filter_leads` — a filter marker leads the line, after the voice tag.
- `syntax.voice_name` — a voice name is one token, no spaces.
- `syntax.token_known` — every `<token>` exists in the vocabulary.
- `syntax.token_case` — a token keeps its documented spelling.
- `syntax.encoding` — CRLF line endings and no BOM.
- `syntax.no_example_wrapper` — no `[example]`/`[\example]` wrapper.
- `format.tag_shape` — a tag line is `@TagKind<~>system<~>station`.
- `filters.vegan.required`, `filters.alcohol.required`,
  `filters.profanity.required`, `filters.flirt.required`,
  `filters.innuendo.required` — the content triggers the marker.
- `filters.allbusiness` — the All Business floor and its fallback lines.
- `filters.fallback` — every tag keeps a line that plays for everyone.
- `filters.banned` — a house rule listing markers that must never appear.
- `content.commander_token` — the player is addressed with `<Commander>`.
- `content.station_landable` — only landable stations get station content.
- `content.fact_image` — a Station Fact's `img_url` matches the house image.
- `content.fact_no_filters` — Station Facts carry no filters.
- `content.no_links` — no URLs in spoken prose beyond the fact image.
- `db.placement` — `UPDATEDB` sits on the line after its tag.
- `dossier.spine` — every dossier has the nine sections, in order.

## Bounds

Bounds live beside the rules, under `[content.bounds]`, because a rule table
would flatten a nested kind into a patch path. The check itself is still a rule,
`[rules.content.bounds]`.

Bounds are **per-tag**, not per system: every `@SystemGreeting` and every
station-specific tag sits between its own minimum and maximum. Counts are
inclusive of the **filter-mandated lines**, so a minimum of 3 leaves one
creative line.

`StationFact` is bounded by paragraphs inside one block, not by tag count. The
title is not a paragraph.

A station may carry its own bound:

```toml
[content.bounds.stations."Primary Station (AB-1)"]
StationChatter = [12, 24]
```

Resolution is **most-specific-first**: station override, then the system's kind
bound, then the base default. An override naming an **unknown station** — one
that is not in the content — produces a **warning**, so a rename or typo cannot
silently do nothing.

Below the minimum is an **error**: the section is incomplete. Above the maximum
is a **warning**: volume is a taste question, and blocking a writer mid-draft
would be hostile. Both findings name the tag, the count and the bound.

## Reading a validation result

`edcg.py validate-definition` and `edcg.py validate-content` print
`{passed, findings, rule_summary}`. Each finding names the `rule`, `severity`,
`line` and `message`. Fix every `error`, understand every `warn`, and show the
policy rows to the user.

## Changing a rule

Do not weaken a rule just to make a run pass. If a rule and the content
disagree about intent, change the house rule deliberately, with its why, rather
than deleting content to silence it. A rule that keeps firing is either a
content mistake or a policy that has genuinely changed; decide which, in the
open, and record the decision in the rule's `why`.
