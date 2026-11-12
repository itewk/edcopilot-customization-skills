"""Content tests for the five reference files.

These are ports of the old prompt-content assertions. In the old package the
interview, brief and gates lived in Python prompt builders and were asserted
against the returned prompt string. Here the same prose lives in markdown, so
every surviving assertion names the file the text moved to. Nothing is dropped:
phase names and counts, the refresh/invalidate/variety/room update steps, the
bounds interview, and the marker mechanics all keep their original assertions.
"""

import re
from pathlib import Path

import pytest

SKILL_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "edcopilot-system-content"
)
REFERENCES = SKILL_DIR / "references"

NEW_INTERVIEW = "new-system-interview.md"
UPDATE_INTERVIEW = "update-interview.md"
WRITING_BRIEF = "writing-brief.md"
RULES = "rules.md"
WORKFLOW = "workflow-details.md"


def _read(name: str) -> str:
    path = REFERENCES / name
    assert path.is_file(), f"missing reference file: {path}"
    return path.read_text(encoding="utf-8")


def _lower(name: str) -> str:
    return _read(name).lower()


def _phases(text: str) -> dict[str, str]:
    """Split a reference at its ``## PHASE ...`` headings."""
    parts = re.split(r"(?m)^## (PHASE [^\n]+)\n", text)
    return {
        parts[index].strip(): parts[index + 1]
        for index in range(1, len(parts), 2)
    }


class TestNewSystemInterview:
    """The six-phase design interview."""

    def test_has_exactly_six_phases_in_order(self):
        text = _read(NEW_INTERVIEW)
        headings = re.findall(r"(?m)^## PHASE [^\n]+", text)
        assert len(headings) == 6, headings
        expected = [
            "PHASE 1: HIGH-LEVEL CONCEPT",
            "PHASE 2: STATION & CHARACTER DESIGN",
            "PHASE 3: PLOT THREADS",
            "PHASE 4: PRODUCE ARTIFACTS",
            "PHASE 5: VALIDATION LOOP",
            "PHASE 6: SAVE",
        ]
        positions = [text.index(f"## {name}") for name in expected]
        assert positions == sorted(positions)

    def test_phase_1_asks_the_concept_questions_only(self):
        phase = _phases(_read(NEW_INTERVIEW))["PHASE 1: HIGH-LEVEL CONCEPT"].lower()
        assert "system name" in phase
        assert "architect" in phase
        assert "colonising group" in phase
        assert "theme" in phase or "concept" in phase
        assert "station name suffix" not in phase
        assert "headquarters" not in phase
        assert "body map" not in phase

    def test_phase_2_asks_for_station_personalities_and_voices(self):
        phase = _phases(_read(NEW_INTERVIEW))["PHASE 2: STATION & CHARACTER DESIGN"]
        lowered = phase.lower()
        assert "personality" in lowered
        assert "2-4 voices" in lowered
        assert "filter" in lowered
        assert "broadcast" in lowered
        assert "conversation famil" in lowered
        assert "system-wide voices" in lowered
        assert "[<PortAuthority>]" in phase

    def test_phase_3_asks_for_threads_with_hooks(self):
        phase = _phases(_read(NEW_INTERVIEW))["PHASE 3: PLOT THREADS"].lower()
        assert "title" in phase
        assert "description" in phase
        assert "stations involved" in phase
        assert "timeline" in phase
        assert "resolution hooks" in phase
        assert "3-6 threads" in phase

    def test_phase_4_produces_dossier_and_rules_artifacts(self):
        phase = _phases(_read(NEW_INTERVIEW))["PHASE 4: PRODUCE ARTIFACTS"]
        lowered = phase.lower()
        assert "dossier" in lowered
        assert "rules" in lowered and ".toml" in lowered
        assert "[content.bounds]" in phase
        assert "3-6" in phase
        assert "any stations that should carry more or less" in lowered
        assert "nine-section" in lowered or "9-section" in lowered
        assert "identity and canon" in lowered
        assert "open threads" in lowered

    def test_phase_4_asks_the_bounds_interview(self):
        phase = _phases(_read(NEW_INTERVIEW))["PHASE 4: PRODUCE ARTIFACTS"].lower()
        assert "section size" in phase
        assert "system greeting" in phase
        assert "station chatter" in phase
        assert "system broadcast" in phase
        assert "station facts" in phase
        assert "include the filter-mandated lines" in phase.replace("includes", "include")

    def test_phase_5_is_an_iterative_validation_loop(self):
        phase = _phases(_read(NEW_INTERVIEW))["PHASE 5: VALIDATION LOOP"]
        lowered = phase.lower()
        assert "edcg.py validate-definition" in phase
        assert "iterative" in lowered
        assert "passed" in lowered
        assert "fix" in lowered
        assert "all 9 dossier sections present and in order" in lowered
        assert "voices in rules.toml match voices in dossier" in lowered

    def test_phase_6_saves_and_names_the_three_runtime_commits(self):
        phase = _phases(_read(NEW_INTERVIEW))["PHASE 6: SAVE"]
        lowered = phase.lower()
        assert "edcg.py save-definition" in phase
        assert "commit_co_author" in phase
        assert "Co-authored-by: 🤖 <harness> (<models>) <email>" in phase
        assert "commit" in lowered
        assert "edcg: scaffold" in lowered
        assert "exactly three runtime commits" in lowered
        assert "after the user confirms" in lowered
        assert "markdb remove" in lowered

    def test_validation_precedes_save(self):
        text = _read(NEW_INTERVIEW)
        phase_5 = text.index("## PHASE 5: VALIDATION LOOP")
        phase_6 = text.index("## PHASE 6: SAVE")
        assert phase_5 < phase_6
        assert "do not proceed to phase 6 until validation passes" in text.lower()

    def test_factual_baseline_section_covers_every_source_category(self):
        text = _read(NEW_INTERVIEW)
        for heading in (
            "FACTUAL BASELINE",
            "LANDABLE STATIONS",
            "NON-LANDABLE SITES",
            "BODIES WITH STATIONS",
            "JOURNAL-ONLY STATIONS",
            "CONFLICTS BETWEEN SOURCES",
        ):
            assert heading in text, f"missing baseline category: {heading}"
        assert "no station content" in text.lower()
        assert "gather-facts" in text

    def test_lore_notes_question_is_carried_over(self):
        text = _read(NEW_INTERVIEW)
        lowered = text.lower()
        assert "LORE NOTES: STATIONS AND BODIES" in text
        assert "anything special lore-wise" in lowered
        assert "bullet list of lore notes" in lowered
        assert '"none"' in lowered
        assert "the apis get wrong" in lowered

    def test_voice_names_are_one_token(self):
        text = _read(NEW_INTERVIEW)
        assert "Voice names are ONE token" in text
        assert "[<PortAuthority>]" in text
        assert "[<Garrett Control>]" in text  # the negative example only
        assert "[<Port Authority>]" not in text

    def test_offer_of_a_feature_branch_is_optional(self):
        lowered = _lower(NEW_INTERVIEW)
        assert "branch start" in lowered
        assert "optional" in lowered
        assert "never create a branch without being asked" in lowered

    def test_interview_runs_one_phase_at_a_time(self):
        lowered = _lower(NEW_INTERVIEW)
        assert "one phase at a time" in lowered
        assert "wait for" in lowered
        assert "do not invent" in lowered or "must not invent" in lowered


class TestUpdateInterview:
    """The seven-phase update interview plus its reconciliation phase."""

    def test_has_seven_numbered_phases_in_order(self):
        text = _read(UPDATE_INTERVIEW)
        numbered = re.findall(r"(?m)^## PHASE [1-7]: [^\n]+", text)
        assert len(numbered) == 7, numbered
        expected = [
            "PHASE 1: REVIEW FACTUAL CHANGES",
            "PHASE 2: LORE & THEME UPDATES",
            "PHASE 3: STATION & CHARACTER UPDATES",
            "PHASE 4: PLOT THREAD EVOLUTION",
            "PHASE 5: PRODUCE UPDATED ARTIFACTS",
            "PHASE 6: VALIDATION LOOP",
            "PHASE 7: SAVE",
        ]
        positions = [text.index(f"## {name}") for name in expected]
        assert positions == sorted(positions)

    def test_phase_1_reviews_the_factual_diff_before_prose(self):
        phase = _phases(_read(UPDATE_INTERVIEW))["PHASE 1: REVIEW FACTUAL CHANGES"]
        lowered = phase.lower()
        assert "review each item" in lowered
        assert "role, personality" in lowered
        assert "theme or lore" in lowered
        assert "new stations" in lowered
        assert "lost stations" in lowered
        assert "status changes" in lowered
        assert "incorporate, defer, or investigate" in lowered
        assert "raven is authoritative for the plan" in lowered
        assert "journal outranks raven for ground truth" in lowered
        assert "inara and spansh are advisory" in lowered

    def test_phase_2_updates_lore_and_theme(self):
        lowered = _phases(_read(UPDATE_INTERVIEW))[
            "PHASE 2: LORE & THEME UPDATES"
        ].lower()
        assert "theme evolution" in lowered
        assert "lore hooks" in lowered
        assert "timeline" in lowered
        assert "faction dynamics" in lowered

    def test_phase_3_handles_new_lost_and_changed_stations(self):
        phase = _phases(_read(UPDATE_INTERVIEW))[
            "PHASE 3: STATION & CHARACTER UPDATES"
        ]
        lowered = phase.lower()
        assert "new stations needing content" in lowered
        assert "stations removed" in lowered
        assert "status changes" in lowered
        assert "construction chatter" in lowered
        assert "archive or remove" in lowered
        assert "[<Garrett Control>]" in phase

    def test_phase_4_evolves_plot_threads(self):
        lowered = _phases(_read(UPDATE_INTERVIEW))[
            "PHASE 4: PLOT THREAD EVOLUTION"
        ].lower()
        assert "existing threads" in lowered
        assert "new threads" in lowered
        assert "cross-station threads" in lowered
        assert "3-6" in lowered

    def test_phase_5_produces_updated_artifacts(self):
        phase = _phases(_read(UPDATE_INTERVIEW))[
            "PHASE 5: PRODUCE UPDATED ARTIFACTS"
        ]
        lowered = phase.lower()
        assert "updated system dossier" in lowered
        assert "updated system rules" in lowered
        assert "dossier" in lowered and "rules" in lowered
        assert "corrections log" in lowered

    def test_phase_6_validates_the_update(self):
        phase = _phases(_read(UPDATE_INTERVIEW))["PHASE 6: VALIDATION LOOP"]
        lowered = phase.lower()
        assert "edcg.py validate-definition" in phase
        assert "system name parameter matches rules.system.names" in lowered
        assert "corrections log" in lowered
        assert "do not proceed to phase 7 until validation passes" in lowered

    def test_phase_7_saves_with_an_update_commit(self):
        phase = _phases(_read(UPDATE_INTERVIEW))["PHASE 7: SAVE"]
        lowered = phase.lower()
        assert "edcg.py save-definition" in phase
        assert "commit_co_author" in phase
        assert "Co-authored-by: 🤖 <harness> (<models>) <email>" in phase
        assert "edcg: update" in lowered
        assert "exactly three runtime commits" in lowered
        assert "after the user confirms" in lowered
        assert "markdb remove" in lowered

    def test_reconciliation_phase_reads_before_editing(self):
        phase = _phases(_read(UPDATE_INTERVIEW))[
            "PHASE 2B: RECONCILE EXISTING CONTENT"
        ]
        lowered = phase.lower()
        assert "invalidate" in lowered
        assert "edcg.py get-content --system" in phase
        assert "edcg.py rewrite-tag" in phase
        assert "never guess" in lowered

    def test_invalidation_is_automatic_and_reversible(self):
        phase = _phases(_read(UPDATE_INTERVIEW))[
            "PHASE 2B: RECONCILE EXISTING CONTENT"
        ]
        lowered = phase.lower()
        assert "do this without asking" in lowered
        assert "under construction" in lowered or "under-construction" in lowered
        assert "renamed" in lowered
        assert "uncommitted" in lowered
        assert "git" in lowered

    def test_variety_is_offered_only_on_request(self):
        phase = _phases(_read(UPDATE_INTERVIEW))[
            "PHASE 2B: RECONCILE EXISTING CONTENT"
        ]
        lowered = phase.lower()
        assert "variety" in lowered
        assert "only on request" in lowered or "only replace what the user agrees" in lowered
        assert "replace" in lowered
        assert "fresh" in lowered

    def test_room_is_asked_when_a_tag_is_full(self):
        phase = _phases(_read(UPDATE_INTERVIEW))[
            "PHASE 2B: RECONCILE EXISTING CONTENT"
        ]
        lowered = phase.lower()
        assert "room" in lowered
        assert "under its maximum" in lowered
        assert "raise the maximum" in lowered
        assert "add" in lowered
        assert "validate" in lowered

    def test_phase_1_uses_the_scan_for_the_diff(self):
        phase = _phases(_read(UPDATE_INTERVIEW))["PHASE 1: REVIEW FACTUAL CHANGES"]
        lowered = phase.lower()
        assert "edcg.py update-scan" in phase
        assert "raven_revision" in phase
        assert "fact availability" in lowered
        assert "edcg.py gather-facts --system" in phase
        assert "edcg.py audit --system" in phase
        assert "sources disagree" in lowered
        assert "discrepancies" in lowered

    def test_phase_5_reads_the_existing_files_before_editing(self):
        phase = _phases(_read(UPDATE_INTERVIEW))[
            "PHASE 5: PRODUCE UPDATED ARTIFACTS"
        ]
        lowered = phase.lower()
        assert "systems/<slug>.md" in phase
        assert "systems/<slug>.rules.toml" in phase
        assert "dossier_path" in phase
        assert "rules_path" in phase
        assert "in place" in lowered
        assert "corrections log" in lowered
        assert "history" in lowered

    def test_content_selection_uses_the_diff_not_the_tag_universe(self):
        text = _read(UPDATE_INTERVIEW)
        lowered = text.lower()
        assert "whole system's tag universe, not a diff" in lowered
        assert "leave every unchanged tag alone" in lowered
        assert "write-content" in lowered
        assert "edcg.py markdb add --tag <tag> --tag <tag>" in text
        assert "json payload with" in lowered and "`tags`" in text
        assert "exactly once" in lowered
        assert "markdb add only those tags" not in lowered

    def test_batch_update_scans_then_processes_one_system_at_a_time(self):
        lowered = _lower(UPDATE_INTERVIEW)
        assert "update-scan" in lowered
        assert "one system or many" in lowered
        assert "one at a time" in lowered
        assert "do not batch" in lowered
        assert "skipped" in lowered
        assert "unparsable rules or failed fact gathering" in lowered
        assert "treat a skip as something to investigate, not a pass" in lowered


class TestWritingBrief:
    """The writing instructions the brief data feeds."""

    def test_brief_names_the_data_it_supplies(self):
        text = _read(WRITING_BRIEF)
        assert "edcg.py writing-brief-data --system" in text
        for field in (
            "tag_lines",
            "landable_stations",
            "bounds",
            "voices",
            "raven_revision",
            "dossier_path",
            "rules_path",
        ):
            assert field in text, f"brief never names field {field!r}"

    def test_exact_tag_lines_carry_no_spaces(self):
        text = _read(WRITING_BRIEF)
        assert "@SystemGreeting<~>" in text
        assert "@SystemBroadcast<~>" in text
        assert "@StationGreeting<~>" in text
        assert "@StationChatter<~>" in text
        assert "@StationFact<~>" in text
        assert "@TagKind<~>system<~>station" in text
        assert "no spaces around `<~>`" in text
        assert "@SystemGreeting <~>" not in text
        assert "@StationFact <~>" not in text
        assert "case-sensitive" in text

    def test_format_reminders_are_carried_over(self):
        text = _read(WRITING_BRIEF)
        lowered = text.lower()
        assert "one line per candidate phrase" in lowered
        assert "whole conversation on one line" in lowered
        assert "NO `[example]` wrapper" in text
        assert "filter markers" in lowered
        assert "after the voice tag" in lowered
        assert "station fact" in lowered and "img_url" in lowered
        assert "crlf, no bom" in lowered
        assert "provenance" in lowered
        assert "UPDATEDB" in text
        assert "after content is written and validated" in lowered
        assert "one token" in lowered

    def test_token_vocabulary_is_carried_over(self):
        text = _read(WRITING_BRIEF)
        lowered = text.lower()
        for token in ("<Commander>", "<cmdrname>", "<myshipname>"):
            assert token in text, f"missing token {token}"
        assert "<Commander> <cmdrname>" in text
        assert "never write 'commander' literally" in lowered
        assert "control addressing the player" in lowered
        assert "speaker who knows them by name" in lowered
        assert "the ship" in lowered

    def test_token_classification_matches_the_base_vocabulary(self):
        text = _read(WRITING_BRIEF)
        assert "[vocab.documented]" in text
        assert "[vocab.undocumented]" in text
        for documented in ("<fuelLevels>", "<starsystem>", "<stationname>"):
            assert documented in text, f"missing documented token {documented}"
        assert "<systemname>" in text
        assert "<bodyName>" in text
        assert "undocumented tokens such as `<fuelLevels>`" not in text

    def test_rule_sources_are_locatable(self):
        text = _read(WRITING_BRIEF)
        lowered = text.lower()
        assert "systems/all.rules.toml" in text
        assert "scripts/edcg/rules/data/base.toml" in text
        assert "[rules.syntax.filter_known]" in text
        assert "systems/<slug>.rules.toml" in text
        assert "writing-brief-data" in text
        assert "where the rules live" in lowered

    def test_filter_requirements_are_carried_over(self):
        text = _read(WRITING_BRIEF)
        lowered = text.lower()
        for marker in ("(allbusiness)", "(vegan)", "(alcohol)", "(profanity)", "(flirt)", "(innuendo)"):
            assert marker in text, f"missing filter {marker}"
        assert "all business" in lowered
        assert "at least 1 line with no filters" in lowered
        assert "only `(allbusiness)`" in lowered
        assert "station facts take no filters" in lowered
        assert "banned filters" in lowered
        assert "warn_below" in lowered

    def test_section_bounds_are_carried_over(self):
        text = _read(WRITING_BRIEF)
        assert "SECTION SIZE" in text
        for row in (
            "| SystemGreeting | 3 | 6 |",
            "| StationGreeting | 4 | 8 |",
            "| StationChatter | 6 | 12 |",
            "| SystemBroadcast | 8 | 16 |",
            "| StationFact | 1 | 3 |",
        ):
            assert row in text, f"section-bound row drifted: {row}"
        assert "INCLUDE the filter-mandated lines" in text
        assert "paragraphs after the title" in text
        assert "the title is not a paragraph" in text
        assert "minimum" in text.lower() and "error" in text.lower()
        assert "maximum" in text.lower() and "warning" in text.lower()
        assert "[content.bounds.stations" in text
        assert "most-specific-first" in text

    def test_rule_ids_appear_in_the_brief(self):
        text = _read(WRITING_BRIEF)
        for rule_id in (
            "content.commander_token",
            "content.station_landable",
            "content.fact_image",
            "syntax.filter_known",
            "syntax.filter_leads",
            "syntax.token_known",
            "syntax.token_case",
            "filters.allbusiness",
            "filters.fallback",
            "filters.banned",
        ):
            assert rule_id in text, f"brief never names rule {rule_id}"

    def test_writing_discipline_points_at_the_rules_file(self):
        lowered = _lower(WRITING_BRIEF)
        assert "rules.md" in lowered
        assert "validate-content" in lowered


class TestRulesReference:
    """The rule catalogue explanation."""

    def test_explains_the_three_rule_layers_and_precedence(self):
        text = _read(RULES)
        lowered = text.lower()
        assert "base" in lowered
        assert "house" in lowered
        assert "system" in lowered
        assert "precedence" in lowered
        assert "base, then house, then system" in lowered
        assert "house rules can declare new rules" in lowered

    def test_explains_rule_fields(self):
        text = _read(RULES)
        lowered = text.lower()
        assert "severity" in lowered
        assert "impl" in lowered
        assert "why" in lowered
        assert "policy" in lowered
        assert "off" in lowered

    def test_explains_why_a_rule_exists(self):
        lowered = _lower(RULES)
        assert "reason" in lowered or "rationale" in lowered
        assert "before changing a rule" in lowered

    def test_bounds_semantics_are_explained(self):
        text = _read(RULES)
        lowered = text.lower()
        assert "per-tag" in lowered
        assert "filter-mandated" in lowered or "filter-mandated lines" in lowered
        assert "stationfact" in lowered
        assert "paragraph" in lowered
        assert "most-specific-first" in lowered
        assert "unknown station" in lowered
        assert "warning" in lowered

    def test_warns_against_weakening_a_rule(self):
        lowered = _lower(RULES)
        assert "do not weaken a rule just to make a run pass" in lowered
        assert "change the house rule deliberately" in lowered


class TestWorkflowDetails:
    """Markers, log checks, branches and git rules."""

    def test_marker_cycle_is_documented(self):
        text = _read(WORKFLOW)
        lowered = text.lower()
        assert "UPDATEDB" in text
        assert "edcg.py markdb add" in text
        assert "edcg.py check-logs" in text
        assert "edcg.py markdb remove" in text
        assert "restart EDCoPilot" in text
        assert "do not add `updatedb` by hand" in lowered
        assert "marker is preserved" in lowered or "preserved markers" in lowered

    def test_check_logs_report_is_explained(self):
        text = _read(WORKFLOW)
        lowered = text.lower()
        assert "--since" in text
        assert "--system" in text
        assert "since" in lowered
        assert "skipped_update" in text
        assert "per-tag" in lowered
        assert "failure" in lowered
        assert "user decides" in lowered
        assert "custom file was unchanged" in lowered

    def test_advisory_gates_are_documented(self):
        text = _read(WORKFLOW)
        lowered = text.lower()
        assert "representative sample" in lowered
        assert "8-10 lines" in lowered
        assert "static or live review" in lowered
        assert "progress table" in lowered
        assert "none of these gates refuses" in lowered
        assert "in-game test and upload" in lowered
        assert "restart" in lowered

    def test_branch_management_is_documented(self):
        text = _read(WORKFLOW)
        for command in (
            "edcg.py branch start",
            "edcg.py branch status",
            "edcg.py branch review",
            "edcg.py branch finalize",
            "edcg.py branch abort",
        ):
            assert command in text, f"missing branch command {command}"
        lowered = text.lower()
        assert "git state" in lowered or "read back from git" in lowered
        assert "backup" in lowered
        assert "--confirm" in text

    def test_git_commit_rules_are_documented(self):
        text = _read(WORKFLOW)
        lowered = text.lower()
        assert "three commits" in lowered
        assert "edcg: content" in lowered
        assert "edcg: scaffold <system> — <summary>" in text
        assert "edcg: update <system> — <summary>" in text
        assert "edcg: markdb add <n> tag(s)" in text
        assert "edcg: markdb remove <n> tag(s)" in text
        assert "tag list goes in the commit body" in lowered
        assert "Co-authored-by:" in text
        assert "EDCG_AUTO_COMMIT" in text
        assert "dirty" in lowered
        assert "two roots" in lowered or "two root" in lowered

    def test_auto_commit_scope_is_scoped_to_the_runtime_writes(self):
        lowered = _lower(WORKFLOW)
        assert "gates the runtime writes" in lowered
        assert "`write-content`, `markdb add` and" in lowered
        assert "`save-definition` always commits" in lowered
        assert "`init` commits" in lowered

    def test_progress_state_is_derived_not_audit_attributed(self):
        lowered = _lower(WORKFLOW)
        assert "progress table" in lowered
        assert "edcg.py branch status" in lowered
        assert "edcg.py get-content" in lowered
        assert "updatedb" in lowered
        assert "audit-derived" not in lowered
        assert "from the audit state" not in lowered

    def test_provenance_markers_are_explained(self):
        lowered = _lower(WORKFLOW)
        assert "provenance" in lowered
        assert "one marker per tag block" in lowered
        assert "rewrite-tag" in lowered
        assert "does not commit" in lowered or "owns the content commit" in lowered
        assert "byte-compatibility" in lowered
        assert "not the skill version" in lowered


class TestReferenceCrossLinks:
    """Every reference is reachable from SKILL.md and the interviews link onward."""

    @pytest.mark.parametrize("name", [NEW_INTERVIEW, UPDATE_INTERVIEW])
    def test_interviews_link_to_the_shared_references(self, name: str):
        text = _read(name)
        assert "writing-brief.md" in text
        assert "rules.md" in text
        assert "workflow-details.md" in text

    @pytest.mark.parametrize(
        "path",
        sorted(REFERENCES.glob("*.md")),
        ids=lambda path: path.name,
    )
    def test_every_relative_markdown_link_resolves(self, path: Path):
        """A link that does not resolve is a promise the reference cannot keep."""
        link_re = re.compile(r"\]\(([^)\s]+\.md)(?:#[^)]*)?\)")
        text = path.read_text(encoding="utf-8")
        targets = link_re.findall(text)
        assert targets, f"{path.name} links to no other reference"
        for target in targets:
            if "://" in target:
                continue
            resolved = (path.parent / target).resolve()
            assert resolved.is_file(), (
                f"{path.name} links to a missing file: {target}"
            )


class TestEnvironmentVariables:
    """Every EDCG_* variable the code reads is explained where setup points."""

    def test_code_reads_no_undocumented_environment_variable(self):
        sources = [
            SKILL_DIR / "scripts" / "edcg" / "common" / "config.py",
            SKILL_DIR / "scripts" / "edcg" / "facts" / "journal.py",
        ]
        names: set[str] = set()
        for source in sources:
            names |= set(
                re.findall(r"EDCG_[A-Z_]+", source.read_text(encoding="utf-8"))
            )
        assert names, "the scanned sources read no EDCG_* variables"
        assert "EDCG_JOURNAL_DIR" in names, "journal.py no longer declares its override"
        documented = _read(WORKFLOW)
        missing = sorted(name for name in names if name not in documented)
        assert not missing, (
            f"workflow-details.md does not document: {missing}"
        )

    def test_inara_unavailable_has_a_documented_reason(self):
        text = _read(WORKFLOW)
        assert "EDCG_INARA_API_KEY" in text
        assert "Inara API key is not configured" in text
