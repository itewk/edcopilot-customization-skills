# <system name> - system dossier

Context for the EDCoPilot custom content written for the colonisation system
**<system name>**.

Read this before editing that system's greetings, broadcasts or station content.
<bridge systems> The bridge systems built to reach it have their own dossier at
`systems/<bridge systems dossier>`.<bridge systems>

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
<for body in bodies>
| `<body.name>` | <body.type> | <body.role> |
<endfor>

<if body_map_notes>
> **<body_map_notes_title>**
>
<for note in body_map_notes>
> <note>
<endfor>
<if body_map_notes>

<if bridge_systems>
### The bridge systems

Two nearby systems were colonised for one reason only: to extend the colonial
reach far enough to claim this one. Each holds a single outpost, and the crews
posted there are the ones who did not get the interesting assignment.

| System | Distance from here | Contents | Attachment |
|---|---|---|---|
<for bridge in bridge_systems>
| `<bridge.name>` | <bridge.distance> | <bridge.contents> | <bridge.attachment> |
<endfor>

They are also <bridge_distance_between> from each other, which the crews on both sides enjoy
bringing up.
<if bridge_systems>

---

## 2. Lore and theme

<lore_theme>

---

## 3. Tone rules (hard constraints)

<for rule in tone_rules>
- <rule>
<endfor>

---

## 4. Canon site table

Statuses: `complete` = finished � `build` = under construction � `plan` = planned.

**Definite vs tentative:** a `plan` site with a real name is committed; a
two-NATO-word name is a placeholder (`names.placeholder`, deferred; see
`tools/rules/INVENTORY.md`).

**Names rechecked at rev <raven revision>.** Renames and the pending journal updates
are logged in section 5 and section 9 - the current rule is simply that a station
name must match the game exactly.

**Orbital or on the ground?** Get this right in the chatter - a crew living in
a space station must not talk about sitting on rocks.

| Station | Where it is | Evidence |
|---|---|---|
<for station in stations>
| `<station.name>` | **<station.placement>**, <station.location> | <station.evidence> |
<endfor>

**`prometheus` outposts are space based**, here and at both bridge systems. The
placement tests - the build type, or the construction-site prefix while a site is
still building - are set out in `systems/DECISIONS.md`. The journal's
`StationType` is not one of them.

**Can it be landed at?** This is decided by the **build type alone**, never by
the in-game name: landable stations are named "Hub" and "Installation" as well.
A **starport**, an **outpost** or a **settlement** has landing pads. A **hub**
or an **installation** has none, so EDCoPilot plays no station greeting, chatter
or fact for it, and content written for one can never be heard by anybody. The
rule `content.station_landable` enforces this from the build types in this
section, against the facility catalogue in `tools/rules/build_types.toml`.

The sites here with no pads have their material outside station content:

| Site with no pads | Build type | Where its material is instead |
|---|---|---|
<for no_pad in no_pad_sites>
| `<no_pad.name>` | `<no_pad.build_type>` | <no_pad.material_location> |
<endfor>

### Complete (<complete_count>)

| Site | Build type | Body |
|---|---|---|
<for site in complete_sites>
| <site.name> | `<site.build_type>` | `<site.body>` |
<endfor>

### Under construction (<building_count>)

| Site | Build type | Body |
|---|---|---|
<for site in building_sites>
| <site.name> | `<site.build_type>` | `<site.body>` |
<endfor>

### Definitely planned (<planned_count>)

| Site | Build type | Body |
|---|---|---|
<for site in planned_sites>
| <site.name> | `<site.build_type>` | `<site.body>` |
<endfor>

### Tentatively planned (<tentative_count>)

Two NATO words = placeholder name.

| Site | Build type | Body |
|---|---|---|
<for site in tentative_sites>
| <site.name> | `<site.build_type>` | `<site.body>` |
<endfor>

<if security_balance>
### Security balance, mapped

<for line in security_balance>
- <line>
<endfor>
<if security_balance>

---

## 5. Corrections log (do not reintroduce these)

| Wrong | Right | Note |
|---|---|---|
<for correction in corrections>
| <correction.wrong> | <correction.right> | <correction.note> |
<endfor>

---

## 6. Site list maintenance

Raven Colonial is authoritative for this system; Spansh and EDSM lag and still
show superseded names.

How to pull the data - base URL, endpoints, `bodyNum` assignment, the
placeholder-name rule and the build-type decode - is in `tools/rules/raven.toml`.
Re-pulling the list invalidates the tables in section 4 and the station list in
section 7, and can add or remove stations from the content.

Raven also carries entries with a `-1` body number and an unresolved build
type (`outpost?`, `installation?`), whose names use square brackets rather than
parentheses: <for unresolved in unresolved_sites><unresolved><if not loop.last>, <endif><endfor>.
They look like hand-entered duplicates and are not part of the plan. They are
deliberately absent from the tables above and from the build-type catalogue, and
no content uses those names; `content.station_landable` warns if a site that has
content ever carries a build type the catalogue does not recognise.

---

## 7. Coverage

All content lives in **`EDCoPilot.SpeechExtensions.Custom.txt`**. <bridge dossier> The bridge-system tags are inventoried in `<bridge dossier>`.<bridge dossier>

This system has one `@SystemGreeting` and one `@SystemBroadcast` tag. The greeting
carries no character voice; the broadcast does, and it mixes announcements,
monologues and multi-character conversations: <for desc in broadcast_description><desc><if not loop.last>; <endif><endfor>.

Each **landable** station then gets a `@StationGreeting` set, a `@StationChatter`
set and a `@StationFact` page - a title line, three paragraphs, and the shared
ii42 tile on the `img_url=` line. A hub or an installation gets none of that,
because EDCoPilot plays no station content for a facility with no landing pads.

### Stations covered

Built, in progress and definitively planned, **and landable**. Tentatively
planned sites are deliberately excluded, and so are the sites with no pads:

<for station in covered_stations><station><if not loop.last> � <endif><endfor>

### Where the remaining themes are heard

<for theme_site in theme_sites><theme_site> have no landing pads, so their material is carried by tags that do work:
<endfor>

<for theme_location in theme_locations>
- **<theme_location.name>** - <theme_location.description>
<endfor>

Both sets are written as <conversation_types> conversation types with several variations each, so
the system keeps some variety in what a Commander hears.

**Station tag naming rule:** the station segment is **case sensitive** and must
match the name the game reports **exactly**. Where the in-game name carries a
parenthetical part, keep it in round brackets - square brackets are EDCoPilot
token syntax and a bracketed station name broke the entire tag. The
parenthetical part appears only in the tag line; the spoken phrases use the
plain name. Tags use the **final** station name. The <for in_progress in in_progress_stations><in_progress><if not loop.last>, <endif><endfor> currently report an
`Orbital Construction Site: ` prefix in game; that prefix disappears on
completion, and it is deliberately **not** used in the tags (EDCoPilot also has
its own built-in construction-site handling). Consequence: the station content
for those <if in_progress_stations|length == 1>one<else><in_progress_stations|length></if> goes live when each site completes.

---

## 8. Writing rules

### Voices used

<for category, voices in voices_by_category.items()>
- **<category>:** <for voice in voices>[<voice>]<if not loop.last>, <endif><endfor>
<endfor>

<voices_description>

<security_experiment_description>

<farm_restaurant_theme>

### Addressing the player

The player is addressed by token everywhere (`content.commander_token`), and
this system uses all of it deliberately: <token_usage_description>.

Two conversation families exist to make that deliberate rather than incidental:

<for family in conversation_families>
- **<family.name>.** <family.description>
<endfor>

### Format reminder

The speech format rules - one line per candidate phrase, a whole conversation on
one line, no `[example]` wrapper - live in `tools/README.md` and are not repeated
here.

---

## 9. Open threads (TODO)

<for thread in open_threads>
- **<thread.title>** - <thread.description>
<endfor>