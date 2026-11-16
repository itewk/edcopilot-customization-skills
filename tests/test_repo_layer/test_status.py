"""Tests for the derived workflow checklist behind ``edcg status``.

Every state is a real temporary repository: the report may only describe what
the repository and files hold (D4), so each fixture is a state a live run
actually leaves behind. The content rule is strict (D8) and is asserted against
the looser runtime reader it deliberately does not reuse.
"""

from __future__ import annotations

import pytest

from edcg.common.config import CONFIG_FILENAME, Config
from edcg.common.layout import CUSTOM_FILE_NAME
from edcg.content.rewrite import get_system_content
from edcg.repo.status import HEADING, build_status
from support import commit_all, run_git

NAME = "Test System"
SLUG = "test-system"

RULES = """[system]
names = ["Test System"]
dossier = "systems/test-system.md"
voices = ["PortAuthority"]
"""

DOSSIER = "# Test System — system dossier\n"


@pytest.fixture(autouse=True)
def _no_ambient_edcopilot_root(monkeypatch):
    """Content is only seen through the root a test sets up itself."""
    monkeypatch.delenv("EDCG_EDCOPILOT_ROOT", raising=False)


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    """EDCoPilot's "User custom files" folder, resolved from the environment."""
    directory = tmp_path / "edcopilot-runtime"
    directory.mkdir()
    monkeypatch.setenv("EDCG_EDCOPILOT_ROOT", str(directory))
    return directory


def _status(root, system=None):
    return build_status(Config(content_definitions_root=root), system)


def _lines(root, system=None):
    return _status(root, system).splitlines()


def _write_definition(root):
    systems = root / "systems"
    systems.mkdir(parents=True, exist_ok=True)
    (systems / f"{SLUG}.md").write_text(DOSSIER, encoding="utf-8")
    (systems / f"{SLUG}.rules.toml").write_text(RULES, encoding="utf-8")


def _write_custom(runtime, text):
    path = runtime / CUSTOM_FILE_NAME
    path.write_text(text, encoding="utf-8")
    return path


class TestRepositoryLines:
    """The lines that are the same for every system."""

    def test_blank_repository_reports_every_step_unchecked(self, git_repo):
        root = git_repo(files={"README.md": "# empty\n"})

        lines = _lines(root)

        assert lines[0] == HEADING
        assert f"[x] repository: {root}" in lines
        assert (
            f"[ ] config: no {CONFIG_FILENAME} - run edcg.py init to scaffold "
            "the repository (SKILL.md Setup step 2)"
        ) in lines
        assert (
            "[ ] house rules: no systems/all.rules.toml - create it from the "
            "skill's rules example and review each section with the user "
            "(SKILL.md Setup step 3)"
        ) in lines
        assert (
            "systems (the box is the saved definition; each line names what runs next):"
        ) in lines
        assert (
            "  (none yet - read references/new-system-interview.md and run the interview)"
        ) in lines
        assert not any(line.startswith("[x] definition") for line in lines)

    def test_house_rules_only_checks_the_repository_wide_steps(self, git_repo):
        root = git_repo(
            files={
                "README.md": "# empty\n",
                CONFIG_FILENAME: "[roots]\n",
                "systems/all.rules.toml": "[rules]\n",
            }
        )

        lines = _lines(root)

        assert f"[x] config: {CONFIG_FILENAME}" in lines
        assert f"[x] house rules: {root / 'systems' / 'all.rules.toml'}" in lines
        assert (
            "  (none yet - read references/new-system-interview.md and run the interview)"
        ) in lines


class TestDefinitionState:
    """A definition is the dossier AND rules pair, and it lives in git."""

    def test_a_saved_definition_needs_both_files_and_a_commit(self, git_repo):
        root = git_repo(files={"README.md": "# empty\n"})
        _write_definition(root)
        commit_all(root, "edcg: scaffold Test System — system definition")

        lines = _lines(root, NAME)

        assert (
            f"[x] definition: systems/{SLUG}.md and systems/{SLUG}.rules.toml "
            "are committed"
        ) in lines

    def test_definition_files_without_a_commit_are_not_a_saved_definition(
        self, git_repo
    ):
        root = git_repo(files={"README.md": "# empty\n"})
        _write_definition(root)

        lines = _lines(root, NAME)

        assert (
            f"[ ] definition: files exist at systems/{SLUG}.md and "
            f"systems/{SLUG}.rules.toml but no commit touches systems/{SLUG} - "
            "run edcg.py save-definition so the pair lands in git "
            "(references/new-system-interview.md Phase 6)"
        ) in lines
        assert not any(line.startswith("[x] definition") for line in lines)

    def test_a_dossier_without_its_rules_file_is_an_incomplete_definition(
        self, git_repo
    ):
        """Half a pair is a new system, the same rule ``is_new`` applies."""
        root = git_repo(files={"README.md": "# empty\n"})
        (root / "systems").mkdir()
        (root / "systems" / f"{SLUG}.md").write_text(DOSSIER, encoding="utf-8")
        commit_all(root, "dossier only")

        lines = _lines(root, NAME)

        assert (
            f"[ ] definition: incomplete - systems/{SLUG}.md exists without "
            f"systems/{SLUG}.rules.toml; the dossier and rules pair is the "
            "definition (is_new semantics) - run edcg.py save-definition with "
            "both files (references/new-system-interview.md Phase 5, then Phase 6)"
        ) in lines
        assert not any(line.startswith("[x] definition") for line in lines)

    def test_the_missing_definition_line_says_the_interview_is_invisible(
        self, git_repo
    ):
        """A conversation-only step must never read as a forgotten one."""
        root = git_repo(files={"README.md": "# empty\n"})

        lines = _lines(root, NAME)

        assert (
            "[ ] definition: none - the interview is conversation - status cannot "
            "see it; a missing definition here means the definition steps have "
            "not run yet; read references/new-system-interview.md (Phase 5 "
            "validation, Phase 6 save)"
        ) in lines

    def test_a_sibling_slugs_commit_is_not_this_systems_commit(self, git_repo):
        """``systems/sol`` must never match ``systems/sol-prime.md``."""
        root = git_repo(files={"README.md": "# empty\n"})
        _write_definition(root)
        sibling = f"systems/{SLUG}-2.md"
        (root / sibling).write_text(
            "# Test System 2 — system dossier\n", encoding="utf-8"
        )
        # Only the sibling lands in history; the pair stays uncommitted.
        run_git(root, "add", sibling)
        run_git(root, "commit", "-m", "the sibling's commit only")

        lines = _lines(root, NAME)

        assert (
            f"[ ] definition: files exist at systems/{SLUG}.md and "
            f"systems/{SLUG}.rules.toml but no commit touches systems/{SLUG} - "
            "run edcg.py save-definition so the pair lands in git "
            "(references/new-system-interview.md Phase 6)"
        ) in lines

    def test_a_non_git_directory_reports_an_uncommitted_definition(self, tmp_path):
        """No repository is a state with no history, not a warning or a crash."""
        _write_definition(tmp_path)

        lines = _lines(tmp_path, NAME)

        assert (
            f"[ ] definition: files exist at systems/{SLUG}.md and "
            f"systems/{SLUG}.rules.toml but no commit touches systems/{SLUG} - "
            "run edcg.py save-definition so the pair lands in git "
            "(references/new-system-interview.md Phase 6)"
        ) in lines


class TestContentState:
    """Authored content is counted with the strict system rule (D8)."""

    def test_content_is_counted_strictly_by_system(
        self, git_repo, runtime, monkeypatch
    ):
        root = git_repo(files={"README.md": "# empty\n"})
        # get_system_content resolves the content root from the environment; the
        # sibling content-layer tests set it the same way rather than relying on
        # the process cwd.
        monkeypatch.setenv("EDCG_CONTENT_DEFINITIONS_ROOT", str(root))
        _write_definition(root)
        commit_all(root, "edcg: scaffold Test System — system definition")
        _write_custom(
            runtime,
            "@SystemGreeting<~>Test System\nHello.\n"
            "@StationGreeting<~>Other System<~>Elsewhere\nHi.\n",
        )

        # The looser runtime reader keeps the station-declared tag...
        assert len(get_system_content(NAME)["tags"]) == 2
        # ...and the checklist deliberately does not: an approximate line here
        # would be a checklist that lies.
        lines = _lines(root, NAME)
        assert (
            f"[x] content: 1 authored tag for {NAME} - review with edcg.py "
            "get-content; edit in place with edcg.py rewrite-tag"
        ) in lines

    def test_no_authored_content_names_the_writing_reference(self, git_repo, runtime):
        root = git_repo(files={"README.md": "# empty\n"})
        _write_definition(root)
        commit_all(root, "edcg: scaffold Test System — system definition")

        lines = _lines(root, NAME)

        assert (
            f"[ ] content: no authored tag for {NAME} - run edcg.py "
            "writing-brief-data, validate-content and write-content "
            "(references/writing-brief.md)"
        ) in lines
        assert (
            "[ ] markers: nothing is authored yet, so there is no marker to set"
        ) in lines


class TestMarkerState:
    """Markers are read from the parsed tags, never inferred."""

    def _defined_repo(self, git_repo):
        root = git_repo(files={"README.md": "# empty\n"})
        _write_definition(root)
        commit_all(root, "edcg: scaffold Test System — system definition")
        return root

    def test_every_authored_tag_marked_is_a_checked_line(self, git_repo, runtime):
        root = self._defined_repo(git_repo)
        _write_custom(
            runtime,
            "@SystemGreeting<~>Test System\nUPDATEDB\nHello.\n"
            "@SystemBroadcast<~>Test System\nUPDATEDB\nHi.\n",
        )

        lines = _lines(root, NAME)

        assert (
            f"[x] markers: every authored tag for {NAME} is marked for update - "
            "restart EDCoPilot, run edcg.py check-logs, then edcg.py markdb "
            "remove after the in-game upload (SKILL.md Process steps 13-16)"
        ) in lines

    def test_a_partial_marker_pass_is_still_open(self, git_repo, runtime):
        root = self._defined_repo(git_repo)
        _write_custom(
            runtime,
            "@SystemGreeting<~>Test System\nUPDATEDB\nHello.\n"
            "@SystemBroadcast<~>Test System\nHi.\n",
        )

        lines = _lines(root, NAME)

        assert (
            "[ ] markers: 1 authored tag not marked for update - run edcg.py "
            "markdb add for the rest (SKILL.md Process step 12)"
        ) in lines

    def test_no_marker_yet_names_the_marking_step(self, git_repo, runtime):
        root = self._defined_repo(git_repo)
        _write_custom(runtime, "@SystemGreeting<~>Test System\nHello.\n")

        lines = _lines(root, NAME)

        assert (
            "[ ] markers: no authored tag is marked for update - after the "
            "review gate run edcg.py markdb add (SKILL.md Process step 12)"
        ) in lines


class TestUnreadableCustomFile:
    """A probe that cannot run is reported, never guessed at."""

    def test_an_unconfigured_edcopilot_root_is_named(self, git_repo):
        root = git_repo(files={"README.md": "# empty\n"})

        lines = _lines(root, NAME)

        assert (
            "[ ] content: EDCoPilot's root is not configured - run edcg.py "
            "doctor (SKILL.md Setup step 4)"
        ) in lines
        assert (
            "[ ] markers: unknown - the custom file cannot be read, so no marker "
            "is claimed"
        ) in lines

    def test_a_stale_configured_root_is_named_with_its_path(self, git_repo):
        """A configured-but-gone root is not the same state as "unconfigured"."""
        root = git_repo(files={"README.md": "# empty\n"})
        gone = root / "moved-away"
        (root / CONFIG_FILENAME).write_text(
            f'[roots]\nedcopilot = "{gone.as_posix()}"\n', encoding="utf-8"
        )

        lines = _lines(root, NAME)

        assert (
            f"[ ] content: EDCoPilot's root is configured but no longer exists "
            f"({gone}) - run edcg.py doctor (SKILL.md Setup step 4)"
        ) in lines

    def test_a_non_utf8_custom_file_is_reported_not_crashed(
        self, git_repo, runtime
    ):
        """UnicodeDecodeError is a ValueError: unguarded it turns into exit 1."""
        root = git_repo(files={"README.md": "# empty\n"})
        (runtime / CUSTOM_FILE_NAME).write_bytes(
            "@SystemGreeting<~>Test System\nHello.\n".encode("utf-16")
        )

        lines = _lines(root, NAME)

        assert (
            "[ ] content: the custom file cannot be read (not valid UTF-8) - "
            "run edcg.py doctor (SKILL.md Setup step 4)"
        ) in lines
        assert not any(
            line.startswith("[x] content") or line.startswith("[x] markers")
            for line in lines
        )

    def test_a_locked_custom_file_is_reported_not_crashed(
        self, git_repo, runtime, monkeypatch
    ):
        """A file EDCoPilot holds open is a probe that failed, not exit 1."""
        root = git_repo(files={"README.md": "# empty\n"})
        _write_custom(runtime, "@SystemGreeting<~>Test System\nHello.\n")

        def locked(*args, **kwargs):
            raise OSError(13, "Permission denied")

        monkeypatch.setattr("edcg.repo.status.parse_content", locked)

        lines = _lines(root, NAME)

        assert (
            "[ ] content: the custom file cannot be read (Permission denied) - "
            "run edcg.py doctor (SKILL.md Setup step 4)"
        ) in lines
        assert not any(
            line.startswith("[x] content") or line.startswith("[x] markers")
            for line in lines
        )


class TestRepositoryWideListing:
    """Without ``--system``: one line per system, naming what runs next."""

    def test_one_line_per_system_names_the_next_action(self, git_repo, runtime):
        root = git_repo(files={"README.md": "# empty\n"})
        _write_definition(root)
        (root / "systems" / "half-done.md").write_text(
            "# Half Done — system dossier\n", encoding="utf-8"
        )
        commit_all(root, "edcg: scaffold Test System — system definition")
        _write_custom(
            runtime, "@SystemGreeting<~>Test System\nUPDATEDB\nHello.\n"
        )

        lines = _lines(root)

        assert (
            f"  [x] {NAME} - definition committed, 1 authored tag, all marked for "
            "update; next: restart EDCoPilot, check-logs, then markdb remove "
            "after the in-game upload"
        ) in lines
        assert (
            "  [ ] half-done - no readable rules file names this system; next: "
            "save the dossier and rules pair (references/new-system-interview.md "
            "Phase 5)"
        ) in lines

    def test_content_written_without_a_definition_still_appears(
        self, git_repo, runtime
    ):
        """The custom file is derived state too (D4): silence would hide a skip."""
        root = git_repo(files={"README.md": "# empty\n"})
        _write_custom(
            runtime, "@SystemGreeting<~>Ghost System\nUPDATEDB\nHello.\n"
        )

        lines = _lines(root)

        assert (
            "  [ ] Ghost System - no definition; next: the new-system interview "
            "(references/new-system-interview.md)"
        ) in lines

    def test_a_defined_system_without_content_names_the_writing_step(
        self, git_repo, runtime
    ):
        root = git_repo(files={"README.md": "# empty\n"})
        _write_definition(root)
        commit_all(root, "edcg: scaffold Test System — system definition")

        lines = _lines(root)

        assert (
            f"  [x] {NAME} - definition committed, no content; next: edcg.py "
            "writing-brief-data, then validate-content and write-content "
            "(references/writing-brief.md)"
        ) in lines

    def test_an_uncommitted_definition_names_the_save_step(self, git_repo):
        root = git_repo(files={"README.md": "# empty\n"})
        _write_definition(root)

        lines = _lines(root)

        assert (
            f"  [ ] {NAME} - definition files are uncommitted; next: run edcg.py "
            "save-definition so the pair lands in git"
        ) in lines

    def test_a_non_table_system_key_is_unnamed_not_a_crash(self, git_repo):
        """`system = 5` is valid TOML and names no system."""
        root = git_repo(files={"README.md": "# empty\n"})
        (root / "systems").mkdir()
        (root / "systems" / "odd.md").write_text(DOSSIER, encoding="utf-8")
        (root / "systems" / "odd.rules.toml").write_text(
            "system = 5\n", encoding="utf-8"
        )
        commit_all(root, "odd rules")

        lines = _lines(root)

        assert (
            "  [ ] odd - no readable rules file names this system; next: save "
            "the dossier and rules pair (references/new-system-interview.md "
            "Phase 5)"
        ) in lines

    def test_a_non_utf8_rules_file_is_unnamed_not_a_crash(self, git_repo):
        """The same D9 rule as the custom file, one file over."""
        root = git_repo(files={"README.md": "# empty\n"})
        (root / "systems").mkdir()
        (root / "systems" / "odd.md").write_text(DOSSIER, encoding="utf-8")
        (root / "systems" / "odd.rules.toml").write_bytes(
            RULES.encode("utf-16")
        )
        commit_all(root, "odd rules")

        lines = _lines(root)

        assert (
            "  [ ] odd - no readable rules file names this system; next: save "
            "the dossier and rules pair (references/new-system-interview.md "
            "Phase 5)"
        ) in lines
