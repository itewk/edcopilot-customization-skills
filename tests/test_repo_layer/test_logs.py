from datetime import datetime, timezone
from pathlib import Path

from edcg.repo.logs import (
    check_logs, log_launch_time, newest_log_after, parse_log, resolve_logs_dir,
    scope_failures,
)

FAILURE = (
    "#*:00:07:46   INFO - skipping UPDATEDB for tag "
    "StationGreetingBleia Eohn SX-F c12Primary Improbable Discoveries (ii-42) "
    "as station cannot be validated. Check spelling and case and retry."
)
NO_CHANGE = (
    "#*:22:48:38   INFO - Skipping updates or deletes of custom colonisation data, "
    "as EDCoPilot.SpeechExtensions.Custom.txt has not changed since last update."
)


def _log(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text + "\n", encoding="utf-8")
    return path


def test_parse_log_finds_and_dedupes_a_failure(tmp_path):
    path = _log(tmp_path, "EDCoPilotGUI.log.20261031.100000.txt", "\n".join([FAILURE, FAILURE]))
    failures, skipped = parse_log(path)
    assert len(failures) == 1
    assert failures[0]["tag"].startswith("StationGreeting")
    assert "station cannot be validated" in failures[0]["reason"]
    assert skipped is False


def test_parse_log_detects_no_change(tmp_path):
    path = _log(tmp_path, "EDCoPilotGUI.log.20261031.100000.txt", NO_CHANGE)
    failures, skipped = parse_log(path)
    assert failures == []
    assert skipped is True


def test_log_launch_time_comes_from_the_name(tmp_path):
    path = _log(tmp_path, "EDCoPilotGUI.log.20261031.100000.txt", "")
    moment = log_launch_time(path)
    assert moment.year == 2026 and moment.hour == 10


def test_unparsable_log_names_are_ignored(tmp_path):
    path = _log(tmp_path, "EDCoPilotGUI.log.current.txt", "")
    assert log_launch_time(path) is None
    since = datetime(2026, 10, 31, 9, 0, tzinfo=timezone.utc)
    assert newest_log_after(tmp_path, since) is None


def test_newest_log_after_ignores_an_older_running_log(tmp_path):
    old = _log(tmp_path, "EDCoPilotGUI.log.20261031.090000.txt", "")
    new = _log(tmp_path, "EDCoPilotGUI.log.20261031.100000.txt", "")
    # mtime makes the old file look recent, as a running session would.
    import os
    os.utime(old, None)
    since = datetime(2026, 10, 31, 9, 30, tzinfo=timezone.utc)
    assert newest_log_after(tmp_path, since) == new


def test_check_logs_without_a_log_reports_not_checked(tmp_path):
    report = check_logs(tmp_path, datetime(2026, 10, 31, 10, 0, tzinfo=timezone.utc), tmp_path)
    assert report["checked"] is False
    assert report["ok"] is False


def test_check_logs_clean_is_ok(tmp_path):
    _log(tmp_path, "EDCoPilotGUI.log.20261031.100000.txt", "nothing to see")
    report = check_logs(tmp_path, datetime(2026, 10, 31, 9, 0, tzinfo=timezone.utc), tmp_path)
    assert report["checked"] is True
    assert report["ok"] is True


def test_resolve_logs_dir_prefers_the_configured_path(tmp_path):
    assert resolve_logs_dir(tmp_path / "custom", tmp_path / "logs") == tmp_path / "logs"


def test_scope_failures_keeps_this_system_and_unowned_failures():
    """A failure belongs to a system only when its tag names that system."""
    alpha = {
        "tag": "StationGreetingAlpha Station",
        "reason": "cannot be validated",
        "line": "skipping UPDATEDB for tag StationGreetingAlpha Station ...",
    }
    beta = {
        "tag": "StationChatterBeta Station",
        "reason": "cannot be validated",
        "line": "skipping UPDATEDB for tag StationChatterBeta Station ...",
    }
    unowned = {
        "tag": "SystemGreeting",
        "reason": "unknown tag",
        "line": "skipping UPDATEDB for tag SystemGreeting ...",
    }

    assert scope_failures([alpha, beta, unowned], "Alpha", ["Alpha", "Beta"]) == [
        alpha,
        unowned,
    ]
    assert scope_failures([alpha, beta, unowned], "Beta", ["Alpha", "Beta"]) == [
        beta,
        unowned,
    ]


def test_scope_failures_keeps_a_failure_naming_no_open_system():
    unowned = {"tag": "SystemGreeting", "reason": "unknown", "line": "..."}
    assert scope_failures([unowned], "Gamma", ["Alpha", "Beta"]) == [unowned]


def test_scope_failures_owns_a_line_that_names_two_systems():
    shared = {
        "tag": "StationGreetingAlpha Station",
        "reason": "Beta Station also named",
        "line": "Alpha Station and Beta Station",
    }
    assert scope_failures([shared], "Alpha", ["Alpha", "Beta"]) == [shared]
    assert scope_failures([shared], "Gamma", ["Alpha", "Beta"]) == []

