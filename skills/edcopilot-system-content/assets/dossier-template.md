# <system name> — system dossier

Context for the EDCoPilot custom content written for the colonisation system
**<system name>**.

Read this before editing that system's greetings, broadcasts or station content.
Each bridge system built to reach it has its own dossier under `systems/`
(named `<bridge systems dossier>` here).

Last reviewed: <review date>. Sources: Raven Colonial rev <raven revision>, cross-checked against
the in-game journal.

---

## 1. Identity and canon

| Fact | Value |
|---|---|
| System name (exact casing) | `<system name>` |
| Architect | `<architect>` |
| Colonising group | <colonising group> |
| Raven Colonial revision | <raven revision> |
| Site census | Section 4 is the census: its site tables name every site, its build type and its body. Raven also carries unresolved placeholder entries with no body and a `?` build type; they are not part of the plan (section 6). |

### Body map

| Body | Type | Role in the theme |
|---|---|---|
<!-- Fill in one row per body: | <body> | <type> | <role in the theme> | -->

> **<body_map_notes_title>**
>
<!-- Replace with the notes worth keeping: tidal locks, ruins, unusual orbits. -->

### The bridge systems

Bridge systems are the nearby systems colonised to extend the colonial reach far
enough to claim this one. Replace this example with what each one holds and who
is posted there.

| System | Distance from here | Contents | Attachment |
|---|---|---|---|
<!-- Fill in one row per bridge system: | <system> | <distance> | <contents> | <attachment> | -->

They are also <bridge_distance_between> from each other, which the crews on both sides enjoy
bringing up.

---

## 2. Lore and theme

<lore_theme>

---

## 3. Tone rules (hard constraints)

<!-- Replace with the hard tone constraints: register, banned jokes, subjects off limits. -->

---

## 4. Canon site table

Statuses: `complete` = finished · `build` = under construction · `plan` = planned.

**Definite vs tentative:** a `plan` site with a real name is committed; a
two-NATO-word name is a placeholder rather than a plan, so it belongs in the
tentative table and is excluded from the coverage list in section 7.

**Names rechecked at rev <raven revision>.** Renames and the pending journal updates
are logged in section 5 and section 9 — the current rule is simply that a station
name must match the game exactly.

**Orbital or on the ground?** Get this right in the chatter — a crew living in
a space station must not talk about sitting on rocks.

| Station | Where it is | Evidence |
|---|---|---|
<!-- Fill in one row per station: | <station> | <body or orbit> | <build type, journal, Raven> | -->

**`prometheus` outposts are space based**, here and at both bridge systems.
Placement is a property of the build type, or of the construction-site prefix
while a site is still building; the journal's `StationType` is not evidence for
it, and a Raven re-pull never changes it.

**Can it be landed at?** This is decided by the **build type alone**, never by
the in-game name: landable stations are named "Hub" and "Installation" as well.
A **starport**, an **outpost** or a **settlement** has landing pads. A **hub**
or an **installation** has none, so EDCoPilot plays no station greeting, chatter
or fact for it, and content written for one can never be heard by anybody. The
rule `content.station_landable` enforces this from the build types in this
section, against the facility catalogue shipped with the skill's scripts
(`scripts/edcg/rules/data/build_types.toml`).

The sites here with no pads have their material outside station content:

| Site with no pads | Build type | Where its material is instead |
|---|---|---|
<!-- Fill in one row per no-pad site: | <site> | <build type> | <which system-level tag carries it> | -->

### Complete (<complete_count>)

| Site | Build type | Body |
|---|---|---|
<!-- Fill in one row per complete site: | <site> | `<build type>` | <body> | -->

### Under construction (<building_count>)

| Site | Build type | Body |
|---|---|---|
<!-- Fill in one row per site under construction: | <site> | `<build type>` | <body> | -->

### Definitely planned (<planned_count>)

| Site | Build type | Body |
|---|---|---|
<!-- Fill in one row per committed plan: | <site> | `<build type>` | <body> | -->

### Tentatively planned (<tentative_count>)

Two NATO words = placeholder name.

| Site | Build type | Body |
|---|---|---|
<!-- Fill in one row per placeholder site: | <site> | `<build type>` | <body> | -->

### Security balance, mapped

<!-- Replace with one line per body: its security level and what it means for the content. -->

---

## 5. Corrections log (do not reintroduce these)

| Wrong | Right | Note |
|---|---|---|
<!-- Fill in one row per correction: | <wrong name or claim> | <right value> | <where the evidence is> | -->

---

## 6. Site list maintenance

Raven Colonial is authoritative for this system; Spansh and EDSM lag and still
show superseded names.

How to pull the data — base URL, endpoints, `bodyNum` assignment, the
placeholder-name rule and the placement rule — is in the Raven configuration
shipped with the skill's rule data
(`scripts/edcg/rules/data/raven.toml`); the build-type decode is in the
facility catalogue beside it (`build_types.toml`).
Re-pulling the list invalidates the tables in section 4 and the station list in
section 7, and can add or remove stations from the content.

Raven also carries entries with a `-1` body number and an unresolved build type
(`outpost?`, `installation?`), whose names are wrapped in square brackets
instead of parentheses. They look like hand-entered duplicates and are not part of the plan.
They are deliberately absent from the tables above and from the build-type
catalogue, and no content uses those names; `content.station_landable` warns if
a site that has content ever carries a build type the catalogue does not
recognise.

---

## 7. Coverage

All content lives in **`EDCoPilot.SpeechExtensions.Custom.txt`**. The bridge-system tags are inventoried in the bridge systems' dossiers (`systems/<bridge dossier>`).

This system has one `@SystemGreeting` and one `@SystemBroadcast` tag. The greeting
carries no character voice; the broadcast does, and it mixes announcements,
monologues and multi-character conversations.

Each **landable** station then gets a `@StationGreeting` set, a `@StationChatter`
set and a `@StationFact` page — a title line, three paragraphs, and the shared
station tile on the `img_url=` line. A hub or an installation gets none of that,
because EDCoPilot plays no station content for a facility with no landing pads.

### Stations covered

Built, in progress and definitively planned, **and landable**. Tentatively
planned sites are deliberately excluded, and so are the sites with no pads:

<!-- Fill in the covered stations, comma separated. -->

### Where the remaining themes are heard

<!-- Replace with the system-level tags that carry the remaining themes, and which site each theme belongs to. -->

Both sets are written as <conversation_types> conversation types with several variations each, so
the system keeps some variety in what a Commander hears.

**Station tag naming rule:** the station segment is **case sensitive** and must
match the name the game reports **exactly**. Where the in-game name carries a
parenthetical part, keep it in round brackets — square brackets are EDCoPilot
token syntax and a bracketed station name broke the entire tag. The
parenthetical part appears only in the tag line; the spoken phrases use the
plain name. Tags use the **final** station name. A station still under
construction currently reports an `Orbital Construction Site: ` prefix in game;
that prefix disappears on completion, and it is deliberately **not** used in the
tags (EDCoPilot also has its own built-in construction-site handling).
Consequence: the station content for a site under construction goes live when it
completes.

---

## 8. Writing rules

### Voices used

<!-- Fill in one row per voice: - **<category>:** `[<Voice>]`, `[<Voice>]` -->

<voices_description>

<security_experiment_description>

<!-- Replace with the theme note this system's voices refer to. -->

### Addressing the player

The player is addressed by token everywhere (`content.commander_token`), and
this system uses all of it deliberately: <token_usage_description>.

Two conversation families exist to make that deliberate rather than incidental:

<!-- Replace with the two conversation families and what each one is for. -->

### Format reminder

The speech format rules are short: one candidate phrase per line, a whole
conversation on one line, never an `[example]` wrapper. `validate-content`
enforces them, and the skill's writing-brief reference explains why.

---

## 9. Open threads (TODO)

<!-- Fill in one bullet per open thread: what is unresolved, and what would settle it. -->
