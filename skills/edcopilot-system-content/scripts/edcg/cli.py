"""CLI entry point for the EDCoPilot system-content skill.

Every subcommand is a thin, scriptable wrapper around one function in the
``edcg`` package. Data subcommands print JSON on stdout; ``version`` prints its
value directly. Exit codes: 0 success, 1 check failure, 2 usage error; a usage
error's message goes to stderr, so stdout stays parseable. The scripts never
pause for a gate; they do refuse impossible or invalid operations.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from edcg import __version__
from edcg.common import layout
from edcg.common.config import (
    CONFIG_FILENAME,
    ConfigError,
    ContentRootError,
    get_config,
    resolve_content_root,
    resolve_edcopilot_root,
)
from edcg.common.layout import CUSTOM_FILE_NAME
from edcg.content.custom_file import write_content, _append_co_author_trailer
from edcg.content.markdb import custom_file_exists, markdb_add, markdb_remove
from edcg.content.rewrite import get_system_content, rewrite_tag
from edcg.facts.facts import gather_facts
from edcg.facts.journal import find_journal_dir
from edcg.repo import branches
from edcg.repo.audit import build_audit_report
from edcg.repo.brief import build_update_scan, system_names, writing_brief_data
from edcg.repo.dossier import save_definition
from edcg.repo.gitrepo import GitRepo
from edcg.repo.logs import check_logs, scope_failures
from edcg.rules.validation import validate_content, validate_definition

_MAX_STATION_BODIES = 20

CONFIG_TEMPLATE = """\
# edcg content repository configuration.
#
# EDCoPilot's "User custom files" folder is resolved from EDCG_EDCOPILOT_ROOT,
# then from the roots.edcopilot key below, then by asking the caller.
[roots]
# edcopilot = "C:/Users/you/Saved Games/Frontier Developments/Elite Dangerous"
"""


class UsageError(Exception):
    """A command was called with a missing or malformed payload."""


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def _emit(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default))


def _fail(message: str) -> int:
    _emit({"error": message})
    return 1


def _payload() -> dict:
    """Read one JSON object from stdin."""
    text = sys.stdin.read()
    if not text.strip():
        raise UsageError("expected a JSON payload on stdin\nfix: pipe a JSON object via stdin (e.g., cat payload.json | edcg ...)")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UsageError(f"invalid JSON payload: {exc}\nfix: ensure your JSON is valid and well-formed") from exc
    if not isinstance(data, dict):
        raise UsageError("JSON payload must be an object\nfix: the payload should be a JSON dictionary (object)")
    return data


def _require_fields(data: dict, spec: dict[str, type | tuple[type, bool]]) -> None:
    errors: list[str] = []
    for key, requirement in spec.items():
        if isinstance(requirement, tuple):
            expected_type, required = requirement
        else:
            expected_type, required = requirement, True

        if key not in data or data[key] is None:
            if required:
                errors.append(f"error: payload is missing required field {key!r}\nfix: include {key!r} — see this command's --help example")
        elif not isinstance(data[key], expected_type):
            actual_type = type(data[key]).__name__
            errors.append(f"error: payload field {key!r} must be a {expected_type.__name__}, got {actual_type}\nfix: pass {key!r} as a {expected_type.__name__}")
    if errors:
        raise UsageError("\n".join(errors))


def _required(data: dict, key: str) -> Any:
    if key not in data or data[key] is None:
        raise UsageError(f"payload is missing required field {key!r}")
    return data[key]


def _validation_payload(result) -> dict:
    """``asdict`` the validation result into the CLI's JSON payload."""
    return asdict(result)


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def _python_version() -> tuple[int, int]:
    return (sys.version_info.major, sys.version_info.minor)


def _check_import(module: str) -> tuple[bool, str]:
    try:
        importlib.import_module(module)
    except Exception as exc:  # ImportError and anything the module raises
        return False, str(exc)
    return True, "importable"


def _git_config(key: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "config", "--get", key],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _git_binary() -> Optional[str]:
    """The ``git --version`` line, or None when git is not on PATH.

    This is deliberately separate from the identity probe: without a binary the
    identity question is meaningless, and the ``git config`` hint would send the
    user to a command they cannot run.
    """
    try:
        result = subprocess.run(
            ["git", "--version"], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _git_identity() -> tuple[Optional[str], Optional[str]]:
    return _git_config("user.name"), _git_config("user.email")


def _report_line(
    label: str, ok: bool, detail: str, hint: Optional[str] = None
) -> bool:
    print(f"{'OK  ' if ok else 'FAIL'} {label}: {detail}")
    if not ok and hint:
        print(f"     fix: {hint}")
    return ok


def _looks_like_edcopilot_root(path: Path) -> bool:
    """True when ``path`` holds at least one ``EDCoPilot*`` file.

    The check is deliberately a warning, not a failure: EDCoPilot's layout is
    the user's business, but a folder with no EDCoPilot file at all is worth
    confirming before the workflow writes a custom file into it.
    """
    try:
        return any(
            child.is_file() and child.name.lower().startswith("edcopilot")
            for child in path.iterdir()
        )
    except OSError:
        return False


def command_doctor(args: argparse.Namespace) -> int:
    """One OK/FAIL line per check; exit 1 when anything fails."""
    passed = True

    major, minor = _python_version()
    passed &= _report_line(
        "python",
        (major, minor) >= (3, 12),
        f"Python {platform.python_version()} (3.14 or newer required)",
        "install Python 3.14 or newer and run the script with it",
    )

    for module, label, hint in (
        ("httpx", "httpx", "pip install httpx gitpython"),
        ("git", "gitpython", "pip install httpx gitpython"),
    ):
        ok, detail = _check_import(module)
        passed &= _report_line(label, ok, detail, hint)

    git_version = _git_binary()
    git_available = git_version is not None
    if git_available:
        passed &= _report_line("git", True, git_version)
    else:
        passed &= _report_line(
            "git",
            False,
            "git not found on PATH",
            "install git and put it on PATH",
        )

    if git_available:
        name, email = _git_identity()
        if name and email:
            passed &= _report_line(
                "git identity", True, f"{name} <{email}>"
            )
        else:
            missing = ", ".join(
                label for label, value in (("user.name", name), ("user.email", email))
                if not value
            )
            passed &= _report_line(
                "git identity",
                False,
                f"missing {missing}",
                'git config --global user.name "Your Name" && '
                'git config --global user.email "you@example.com"',
            )

    content_root: Optional[Path] = None
    try:
        content_root = resolve_content_root(Path.cwd(), os.environ)
    except ContentRootError as exc:
        passed &= _report_line(
            "content root",
            False,
            str(exc),
            "set EDCG_CONTENT_DEFINITIONS_ROOT to an existing writable directory",
        )
    else:
        passed &= _report_line(
            "content root",
            True,
            f"{content_root} ({layout.content_root_state(content_root)})",
        )

    if content_root is None:
        passed &= _report_line(
            "EDCoPilot root", False, "content root unavailable",
            "fix the content root first",
        )
    else:
        resolved = resolve_edcopilot_root(content_root, os.environ)
        if resolved.path is not None:
            passed &= _report_line(
                "EDCoPilot root", True, f"{resolved.path} (source: {resolved.source})"
            )
            if not _looks_like_edcopilot_root(resolved.path):
                print(
                    f"WARN EDCoPilot root: {resolved.path} does not look like "
                    "EDCoPilot's User custom files folder — confirm with the user"
                )
        elif resolved.stale is not None:
            passed &= _report_line(
                "EDCoPilot root",
                False,
                f"configured path no longer exists: {resolved.stale}",
                "update roots.edcopilot in the config file or set EDCG_EDCOPILOT_ROOT",
            )
        else:
            passed &= _report_line(
                "EDCoPilot root",
                False,
                "not configured (expected on first run)",
                "first run: set EDCG_EDCOPILOT_ROOT or store roots.edcopilot "
                "in the config file",
            )

    # Check for journal directory
    journal_dir = find_journal_dir(os.environ)
    if journal_dir:
        passed &= _report_line(
            "journal", True, f"{journal_dir}"
        )
    else:
        # WARN instead of FAIL - journal visibility is informational, not a failure
        print("WARN journal: not found - set EDCG_JOURNAL_DIR or check Saved Games")
        # Don't update 'passed' to maintain doctor exit status

    return 0 if passed else 1


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def command_init(args: argparse.Namespace) -> int:
    root = resolve_content_root(Path.cwd(), os.environ)
    if layout.content_root_state(root) == "existing":
        return _fail(
            f"{root} is already a content repository: it has a systems/ directory "
            f"or {CONFIG_FILENAME}"
        )

    created: list[str] = []

    config_file = root / CONFIG_FILENAME
    if not config_file.exists():
        config_file.write_text(CONFIG_TEMPLATE, encoding="utf-8", newline="\n")
        created.append(CONFIG_FILENAME)

    systems_dir = layout.systems_dir(root)
    if not systems_dir.is_dir():
        systems_dir.mkdir(parents=True)
        created.append("systems/")

    git_info: dict[str, Any] = {"initialized": False, "commit": None}
    if not args.no_git:
        with GitRepo.init(root) as repo:
            # Stage only what init created. An existing repository may hold
            # unrelated untracked files; they must stay untracked.
            repo.add(CONFIG_FILENAME)
            commit_message = "edcg: scaffold content repository"
            commit_message = _append_co_author_trailer(commit_message, args.co_author)
            commit = repo.commit(commit_message)
        git_info = {"initialized": True, "commit": commit}
        if commit is None:
            return _fail(
                "git init succeeded but the scaffolding commit failed: "
                "configure user.name and user.email (run `edcg doctor`)"
            )

    _emit(
        {
            "content_root": str(root),
            "state": "blank",
            "created": created,
            "git": git_info,
        }
    )
    return 0


# ---------------------------------------------------------------------------
# facts, writing brief and update scan
# ---------------------------------------------------------------------------


def _facts_dict(facts) -> dict:
    """The gather-facts payload, with datetimes rendered as ISO 8601.

    This is a *projection*, not a generic renderer: it deliberately omits
    ``raven_sites``/``journal_data``/``inara_stations``/``spansh_stations`` and
    caps ``station_bodies`` at ``_MAX_STATION_BODIES``, which ``asdict`` cannot
    express.
    """
    return {
        "system_name": facts.system_name,
        "raven_system": {
            "architect": facts.raven_system.architect,
            "revision": facts.raven_system.revision,
            "bodies": facts.raven_system.bodies,
        }
        if facts.raven_system
        else None,
        "raven_sites_loaded": facts.raven_sites_loaded,
        "landable_stations": [
            {
                "name": station.name,
                "build_type": station.build_type,
                "facility_class": station.facility_class,
                "facility_name": station.facility_name,
                "body": station.body,
                "status": station.status,
                "source": station.source,
                "placement": station.placement,
            }
            for station in facts.landable_stations
        ],
        "non_landable_sites": [
            {
                "name": site.name,
                "build_type": site.build_type,
                "facility_class": site.facility_class,
                "facility_name": site.facility_name,
                "body": site.body,
                "status": site.status,
                "source": site.source,
                "placement": site.placement,
            }
            for site in facts.non_landable_sites
        ],
        "journal_only_stations": [
            {
                "name": station.name,
                "system": station.system,
                "timestamp": station.timestamp.isoformat(),
                "market_id": station.market_id,
            }
            for station in facts.journal_only_stations
        ],
        "station_bodies": [
            {
                "name": body.name,
                "sub_type": body.sub_type,
                "atmosphere": body.atmosphere,
                "temperature_k": body.temperature_k,
                "pressure_atm": body.pressure_atm,
                "gravity_g": body.gravity_g,
                "radius_km": body.radius_km,
                "volcanism": body.volcanism,
                "orbital_period_days": body.orbital_period_days,
                "landable": body.landable,
                "terraforming_state": body.terraforming_state,
            }
            for body in facts.station_bodies[:_MAX_STATION_BODIES]
        ],
        "station_bodies_omitted": max(
            0, len(facts.station_bodies) - _MAX_STATION_BODIES
        ),
        "conflicts": [
            {
                "field": conflict.field,
                "value": conflict.value,
                "sources": conflict.sources,
                "conflict": conflict.conflict,
                "details": conflict.details,
            }
            for conflict in facts.conflicts
        ],
    }


def command_gather_facts(args: argparse.Namespace) -> int:
    config = get_config()
    facts = asyncio.run(gather_facts(args.system, config))
    _emit(_facts_dict(facts))
    return 0


def command_writing_brief_data(args: argparse.Namespace) -> int:
    config = get_config()
    _emit(writing_brief_data(config, args.system))
    return 0


def command_update_scan(args: argparse.Namespace) -> int:
    config = get_config()
    _emit(asyncio.run(build_update_scan(config, gather_facts)))
    return 0


def command_audit(args: argparse.Namespace) -> int:
    config = get_config()
    facts = asyncio.run(gather_facts(args.system, config))
    report = build_audit_report(facts, config)
    _emit(asdict(report))
    return 0 if report.passed else 1


# ---------------------------------------------------------------------------
# definitions and content
# ---------------------------------------------------------------------------





def command_validate_definition(args: argparse.Namespace) -> int:
    data = _payload()
    _require_fields(
        data,
        {
            "dossier": str,
            "rules": str,
            "system_name": str,
            "all_rules": (str, False),
        },
    )
    result = validate_definition(
        dossier=data["dossier"],
        rules=data["rules"],
        system_name=data["system_name"],
        all_rules=data.get("all_rules"),
    )
    _emit(_validation_payload(result))
    return 0 if result.passed else 1


def command_save_definition(args: argparse.Namespace) -> int:
    data = _payload()
    _require_fields(data, {"system_name": str, "dossier_md": str, "rules_toml": str})
    result = save_definition(
        system_name=data["system_name"],
        dossier_md=data["dossier_md"],
        rules_toml=data["rules_toml"],
        commit_co_author=data.get("commit_co_author"),
    )
    _emit(
        {
            "commit_hash": result.commit_hash,
            "files_changed": result.files_changed,
        }
    )
    return 0


def command_validate_content(args: argparse.Namespace) -> int:
    data = _payload()
    _require_fields(data, {"content": str, "system_name": str})
    result = validate_content(
        content=data["content"],
        system_name=data["system_name"],
    )
    _emit(_validation_payload(result))
    return 0 if result.passed else 1


def command_write_content(args: argparse.Namespace) -> int:
    data = _payload()
    _require_fields(
        data,
        {
            "system_name": str,
            "content_block": str,
            "model": (str, False),
            "commit_co_author": (str, False),
        },
    )
    result = write_content(
        system_name=data["system_name"],
        content_block=data["content_block"],
        model=data.get("model"),
        commit_co_author=data.get("commit_co_author"),
    )
    _emit(asdict(result))
    return 0


def command_get_content(args: argparse.Namespace) -> int:
    _emit(get_system_content(args.system))
    return 0


def command_rewrite_tag(args: argparse.Namespace) -> int:
    data = _payload()
    _require_fields(
        data,
        {
            "system_name": str,
            "tag": str,
            "remove": (list, False),
            "replace": (dict, False),
            "add": (list, False),
        },
    )
    result = rewrite_tag(
        system_name=data["system_name"],
        tag=data["tag"],
        remove=data.get("remove"),
        replace=data.get("replace"),
        add=data.get("add"),
    )
    _emit(result)
    return 0


def _warn_unmatched_tags(requested: list[str], modified: list[str]) -> None:
    """Make a marker no-op observable without turning it into a failure.

    A mistyped tag matches no authored content and the call stays a no-op, which
    is the old tool's parity behaviour. The warning names the tags so the caller
    can reconcile the station or tag name instead of assuming the marker landed.
    """
    matched = set(modified)
    seen: set[str] = set()
    missing: list[str] = []
    for tag in requested:
        stripped = tag.strip()
        if stripped and stripped not in seen and stripped not in matched:
            seen.add(stripped)
            missing.append(stripped)
    if not missing:
        return
    print(
        "warning: requested tag(s) matched no authored content: "
        + ", ".join(missing)
        + " — compare modified_tags to the tags you passed, then reconcile "
        "the station/tag name before proceeding",
        file=sys.stderr,
    )


def command_markdb(args: argparse.Namespace) -> int:
    data: dict = {}
    if not args.tag:
        data = _payload()
    tags = args.tag or _required(data, "tags")
    co_author = data.get("commit_co_author")

    if not custom_file_exists():
        config = get_config()
        resolved = resolve_edcopilot_root(config.content_definitions_root, os.environ)
        return _fail(
            f"custom file not found: {resolved.path / CUSTOM_FILE_NAME} "
            f"(EDCoPilot root: {resolved.path})"
        )

    if args.markdb_command == "add":
        result = markdb_add(tags, commit_co_author=co_author)
    else:
        result = markdb_remove(tags, commit_co_author=co_author)
    _warn_unmatched_tags(tags, result["modified_tags"])
    _emit(result)
    return 0


# ---------------------------------------------------------------------------
# check-logs
# ---------------------------------------------------------------------------


def _parse_since(raw: str) -> datetime:
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UsageError(
            f"--since must be an ISO 8601 timestamp: {raw!r}"
        ) from exc
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment


def _custom_file_mtime(root: Path) -> Optional[datetime]:
    custom_file = root / CUSTOM_FILE_NAME
    if not custom_file.is_file():
        return None
    return datetime.fromtimestamp(custom_file.stat().st_mtime).astimezone()


def command_check_logs(args: argparse.Namespace) -> int:
    config = get_config()
    resolved = resolve_edcopilot_root(config.content_definitions_root, os.environ)
    if resolved.path is None:
        _emit(
            {
                "checked": False,
                "log_path": None,
                "since": None,
                "failures": [],
                "skipped_update": False,
                "ok": False,
                "summary": (
                    "Could not resolve EDCoPilot's root"
                    + (f": configured path no longer exists: {resolved.stale}"
                       if resolved.stale is not None else "")
                ),
            }
        )
        return 1

    since = _parse_since(args.since) if args.since else _custom_file_mtime(
        resolved.path
    )
    report = check_logs(
        resolved.path, since, configured=config.edcopilot_logs_dir
    )

    if args.system:
        report["system"] = args.system
        if report["checked"]:
            systems = system_names(config)
            failures = scope_failures(report["failures"], args.system, systems)
            report["failures"] = failures
            report["ok"] = not failures and not report["skipped_update"]
            if failures:
                report["summary"] = (
                    f"{len(failures)} UPDATEDB failure(s) in the new log."
                )
            elif report["skipped_update"]:
                report["summary"] = (
                    "EDCoPilot did not process a change: the custom file was "
                    "unchanged since the last update."
                )
            else:
                report["summary"] = (
                    "No UPDATEDB failures in the log written after the restart."
                )

    _emit(report)
    if report["checked"] and not report["ok"]:
        return 1
    return 0


# ---------------------------------------------------------------------------
# branch orchestration
# ---------------------------------------------------------------------------


def command_branch_start(args: argparse.Namespace) -> int:
    _emit(asdict(branches.start_branch(args.description)))
    return 0


def command_branch_status(args: argparse.Namespace) -> int:
    _emit(asdict(branches.branch_status()))
    return 0


def command_branch_review(args: argparse.Namespace) -> int:
    print(branches.review_branch())
    return 0


def command_branch_finalize(args: argparse.Namespace) -> int:
    result = branches.finalize_branch(merge=args.merge, push=args.push)
    _emit(asdict(result))

    # Exit policy keys off what the push actually did, never off `merged`: a
    # successful push is success even when no merge happened, and a partial or
    # refused push is not success even when the merge did happen.
    if result.push_status in {"failed", "nothing_to_push", "partial"}:
        return 1
    return 0


def command_branch_abort(args: argparse.Namespace) -> int:
    _emit(asdict(branches.abort_branch(confirm=args.confirm)))
    return 0


def command_version(args: argparse.Namespace) -> int:
    print(__version__)
    return 0


# ---------------------------------------------------------------------------
# Parser and dispatch
# ---------------------------------------------------------------------------


class _FinalizeFlag(argparse.Action):
    """Store a ``branch finalize`` flag, rejecting ``--no-merge`` with ``--push``.

    The pair has no meaning: a push carries the default branch, which the merge
    produces, so there is nothing to push before a merge. Accepting the pair
    would silently drop the request, so it fails as a usage error instead.
    """

    def __init__(self, option_strings, dest, const, **kwargs):
        super().__init__(option_strings, dest, nargs=0, const=const, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, self.const)
        merge = namespace.merge
        push = namespace.push
        if push and not merge:
            parser.error(
                "--no-merge cannot be combined with --push: without a merge "
                "there is nothing to push"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edcg",
        description="EDCoPilot system-content authoring commands",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Exit codes: 0 success, 1 check failure, 2 usage error.

Major command groups:
setup: doctor/init
authoring: gather-facts/validate-definition/save-definition/writing-brief-data/validate-content/write-content/get-content/update-scan/rewrite-tag
markers: markdb/check-logs
review: audit/branch
""",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        metavar="<command>",
        help="Available commands; each one's --help documents its flags and examples",
    )

    doctor_parser = subparsers.add_parser(
        "doctor", help="Check Python, packages, git and roots"
    )
    doctor_parser.set_defaults(func=command_doctor)

    init_parser = subparsers.add_parser(
        "init", help="Scaffold a blank content repository"
    )
    init_parser.add_argument(
        "--no-git", action="store_true", help="Do not run git init"
    )
    init_parser.add_argument(
        "--co-author",
        help="Co-author trailer value for the scaffolding commit (formatted as '🤖 <harness> (<models>) <email>')",
        default=None,
    )
    init_parser.set_defaults(func=command_init)

    gather_parser = subparsers.add_parser(
        "gather-facts", help="Gather a system's facts as JSON"
    )
    gather_parser.add_argument("--system", required=True, help="System name")
    gather_parser.set_defaults(func=command_gather_facts)

    definition_parser = subparsers.add_parser("validate-definition",
        help="Validate a dossier and rules pair (JSON on stdin)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:
  python edcg.py validate-definition < definition.json

Where definition.json is:
{
  "system_name": "Test System",
  "dossier": "# Test System - system dossier\\n...",
  "rules": "[system]\\nnames = [\\"Test System\\"]\\n",
  "all_rules": "[rules.content.station_landable]\\nseverity = \\"error\\"\\n"
}""",
    )
    definition_parser.set_defaults(func=command_validate_definition)
    save_parser = subparsers.add_parser(
        "save-definition",
        help="Save a dossier and rules pair (JSON on stdin)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:
  python edcg.py save-definition < definition.json

Where definition.json is:
{
  "system_name": "Test System",
  "dossier_md": "# Test System - system dossier\\n...",
  "rules_toml": "[system]\\nnames = [\\"Test System\\"]\\n",
  "commit_co_author": "<harness> (<models>) <email>"
}""",
    )
    save_parser.set_defaults(func=command_save_definition)

    brief_parser = subparsers.add_parser(
        "writing-brief-data", help="Computed writing-brief data as JSON"
    )
    brief_parser.add_argument("--system", required=True, help="System name")
    brief_parser.set_defaults(func=command_writing_brief_data)

    content_validate_parser = subparsers.add_parser(
        "validate-content", help="Validate a content block (JSON on stdin)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:
  python edcg.py validate-content < content.json

Where content.json is:
{
  "system_name": "Test System",
  "content": "Hello world."
}""",
    )
    content_validate_parser.set_defaults(func=command_validate_content)
    write_parser = subparsers.add_parser(
        "write-content", help="Append a content block (JSON on stdin)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:
  python edcg.py write-content < content.json

Where content.json is:
{
  "content_block": "@SystemGreeting<~>Test System\\nHello world.\\n",
  "system_name": "Test System",
  "commit_co_author": "<harness> (<models>) <email>"
}""",
    )
    write_parser.set_defaults(func=command_write_content)

    content_parser = subparsers.add_parser(
        "get-content", help="Authored content for a system as JSON"
    )
    content_parser.add_argument("--system", required=True, help="System name")
    content_parser.set_defaults(func=command_get_content)

    scan_parser = subparsers.add_parser(
        "update-scan", help="Scan every system for fact changes as JSON"
    )
    scan_parser.set_defaults(func=command_update_scan)
    rewrite_parser = subparsers.add_parser(
        "rewrite-tag", help="Rewrite one tag's dialog (JSON on stdin)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:
  python edcg.py rewrite-tag < payload.json

Where payload.json is:
{
  "system_name": "Test System",
  "tag": "@SystemGreeting<~>Test System",
  "replace": {
    "Hello world.": "Hi there!"
  }
}""",
    )
    rewrite_parser.set_defaults(func=command_rewrite_tag)

    markdb_parser = subparsers.add_parser(
        "markdb", help="Add or remove UPDATEDB markers"
    )
    markdb_subparsers = markdb_parser.add_subparsers(
        dest="markdb_command", metavar="add|remove", help="Marker action"
    )
    markdb_subparsers.required = True
    markdb_examples = {
        "add": """Example:
  python edcg.py markdb add --tag "@SystemGreeting<~>Test System" --tag "@SystemBroadcast<~>Test System"

Or pass the tags as JSON on stdin:
{
  "tags": ["@SystemGreeting<~>Test System"],
  "commit_co_author": "<harness> (<models>) <email>"
}""",
        "remove": """Example:
  python edcg.py markdb remove --tag "@SystemGreeting<~>Test System" --tag "@SystemBroadcast<~>Test System"

Or pass the tags as JSON on stdin:
{
  "tags": ["@SystemGreeting<~>Test System"],
  "commit_co_author": "<harness> (<models>) <email>"
}""",
    }
    for action in ("add", "remove"):
        action_parser = markdb_subparsers.add_parser(
            action,
            help=f"{action.capitalize()} UPDATEDB markers for the given tags",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=markdb_examples[action],
        )
        action_parser.add_argument(
            "--tag",
            action="append",
            default=[],
            help="Exact tag line (repeatable; otherwise JSON on stdin)",
        )
        action_parser.set_defaults(func=command_markdb)

    logs_parser = subparsers.add_parser(
        "check-logs", help="Check EDCoPilot's log after a restart",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:
  python edcg.py check-logs --system "Test System" --since "2026-01-01T00:00:00Z"

If --since is not provided, it defaults to the mtime of the custom file.
""",
    )
    logs_parser.add_argument(
        "--since", help="ISO 8601 timestamp (default: custom-file mtime)"
    )
    logs_parser.add_argument("--system", help="Scope failures to this system")
    logs_parser.set_defaults(func=command_check_logs)

    audit_parser = subparsers.add_parser(
        "audit", help="Audit a system across the four sources"
    )
    audit_parser.add_argument("--system", required=True, help="System name")
    audit_parser.set_defaults(func=command_audit)

    branch_parser = subparsers.add_parser(
        "branch", help="Two-repository branch orchestration"
    )
    branch_subparsers = branch_parser.add_subparsers(
        dest="branch_command",
        metavar="start|status|review|finalize|abort",
        help="Branch action",
    )
    branch_subparsers.required = True
    start_parser = branch_subparsers.add_parser(
        "start", help="Start a feature branch in both repositories"
    )
    start_parser.add_argument("description", nargs="?", help="Branch description")
    start_parser.set_defaults(func=command_branch_start)
    status_parser = branch_subparsers.add_parser("status", help="Show branch status")
    status_parser.set_defaults(func=command_branch_status)
    review_parser = branch_subparsers.add_parser("review", help="Review branch changes")
    review_parser.set_defaults(func=command_branch_review)
    finalize_parser = branch_subparsers.add_parser(
        "finalize", help="Merge the feature branch into the default branch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:
  python edcg.py branch finalize --merge --push

--merge is the default; --no-merge leaves the work on the feature branch.
--no-merge cannot be combined with --push: nothing exists to push before a merge.
""",
    )
    finalize_parser.add_argument(
        "--merge", dest="merge", action=_FinalizeFlag, const=True,
        help="Merge (default)",
    )
    finalize_parser.add_argument(
        "--no-merge", dest="merge", action=_FinalizeFlag, const=False,
        help="Do not merge",
    )
    finalize_parser.add_argument(
        "--push", action=_FinalizeFlag, const=True,
        help="Push the default branch",
    )
    finalize_parser.set_defaults(merge=True, push=False, func=command_branch_finalize)
    abort_parser = branch_subparsers.add_parser(
        "abort", help="Discard the feature branch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:
  python edcg.py branch abort --confirm

Without --confirm it only reports what would be discarded.
""",
    )
    abort_parser.add_argument(
        "--confirm", action="store_true", help="Actually delete the branch"
    )
    abort_parser.set_defaults(func=command_branch_abort)

    version_parser = subparsers.add_parser("version", help="Print the version string")
    version_parser.set_defaults(func=command_version)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except UsageError as exc:
        # A usage error is not a data answer: the message goes to stderr so a
        # caller parsing stdout never mistakes it for a payload.
        print(str(exc), file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError, ConfigError, OSError) as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
