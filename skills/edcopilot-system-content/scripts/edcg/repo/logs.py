"""Read EDCoPilot's GUI log to verify that a restart processed the markers."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

FAILURE_RE = re.compile(
    r"skipping UPDATEDB for tag (?P<tag>.+?) as (?P<reason>.+)", re.IGNORECASE
)
NO_CHANGE_RE = re.compile(
    r"Skipping updates or deletes of custom colonisation data, "
    r"as .* has not changed since last update",
    re.IGNORECASE,
)
LOG_NAME_RE = re.compile(r"EDCoPilotGUI\.log\.(\d{8})\.(\d{6})\.txt$")

NO_SINCE_SUMMARY = "Add the markers before checking the restart."
NO_LOG_SUMMARY = "Restart EDCoPilot, then retry."
CLEAN_SUMMARY = "No UPDATEDB failures in the log written after the restart."
NO_CHANGE_SUMMARY = (
    "EDCoPilot did not process a change: the custom file was unchanged "
    "since the last update."
)


def resolve_logs_dir(edcopilot_root: Path, configured: Path | None) -> Path:
    if configured is not None:
        return configured
    candidate = edcopilot_root.parent / "logs"
    if candidate.is_dir():
        return candidate
    return edcopilot_root / "logs"


def log_launch_time(path: Path) -> datetime | None:
    """When EDCoPilot launched, from the log's name; None if it does not parse."""
    match = LOG_NAME_RE.search(path.name)
    if not match:
        return None
    stamp = datetime.strptime(
        f"{match.group(1)}.{match.group(2)}", "%Y%m%d.%H%M%S"
    )
    return stamp.astimezone()


def newest_log_after(logs_dir: Path, since: datetime) -> Path | None:
    best: tuple[datetime, Path] | None = None
    if not logs_dir.is_dir():
        return None
    for path in logs_dir.glob("EDCoPilotGUI.log.*.txt"):
        moment = log_launch_time(path)
        if moment is None or moment <= since:
            continue
        if best is None or moment > best[0]:
            best = (moment, path)
    return best[1] if best else None


def parse_log(path: Path) -> tuple[list[dict], bool]:
    """Failure entries and the no-change flag, with repeated copies collapsed."""
    failures: dict[tuple[str, str], dict] = {}
    skipped_update = False
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = FAILURE_RE.search(raw)
        if match:
            tag = match.group("tag").strip()
            reason = match.group("reason").strip()
            key = (tag, reason)
            if key not in failures:
                failures[key] = {"tag": tag, "reason": reason, "line": raw.strip()}
            continue
        if NO_CHANGE_RE.search(raw):
            skipped_update = True
    return list(failures.values()), skipped_update


def check_logs(
    edcopilot_root: Path,
    since: datetime | None,
    configured: Path | None = None,
) -> dict:
    """Find a log created after ``since`` and report what it says."""
    base = {
        "checked": False,
        "log_path": None,
        "since": None,
        "failures": [],
        "skipped_update": False,
        "ok": False,
    }
    if since is None:
        return {**base, "summary": NO_SINCE_SUMMARY}

    logs_dir = resolve_logs_dir(edcopilot_root, configured)
    path = newest_log_after(logs_dir, since)
    if path is None:
        return {**base, "summary": NO_LOG_SUMMARY}

    failures, skipped_update = parse_log(path)
    report = {
        "checked": True,
        "log_path": str(path),
        "since": since.astimezone(timezone.utc).isoformat(),
        "failures": failures,
        "skipped_update": skipped_update,
        "ok": not failures and not skipped_update,
    }
    if failures:
        report["summary"] = f"{len(failures)} UPDATEDB failure(s) in the new log."
    elif skipped_update:
        report["summary"] = NO_CHANGE_SUMMARY
    else:
        report["summary"] = CLEAN_SUMMARY
    return report


def _failure_text(failure: dict) -> str:
    return f"{failure.get('tag', '')} {failure.get('line', '')}"


def scope_failures(
    failures: list[dict], system_name: str, systems: list[str]
) -> list[dict]:
    """Keep this system's failures and failures that name no open system."""
    scoped: list[dict] = []
    for failure in failures:
        text = _failure_text(failure)
        owners = [name for name in systems if name and name in text]
        if not owners or system_name in owners:
            scoped.append(failure)
    return scoped


# ``check_cycle_logs`` is not ported: it reads and records content-cycle state
# (core.workflow), and spec D2 removes the gate/cycle surface. The pure
# log-reading functions above are the whole remaining behaviour.
