"""Branch orchestration across the content repository and EDCoPilot root."""

from __future__ import annotations

import os
import re
import shutil
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

from edcg.common.config import (
    ConfigError,
    environ_edcopilot_root,
    get_config,
    resolve_edcopilot_root,
)
from edcg.common.layout import CUSTOM_FILE_NAME
from edcg.repo.gitrepo import GitRepo, slugify_branch_name


# Only branches this workflow creates are workflow branches. ``slugify_branch_name``
# emits ``gen/<slug>`` and appends ``-YYYYMMDDTHHMMSSZ`` on a collision. Any other
# non-default checkout (a human's ``release`` branch, for example) is foreign.
_MANAGED_BRANCH_RE = re.compile(
    r"^gen/[a-z0-9]+(?:-[a-z0-9]+)*(?:-[0-9]{8}T[0-9]{6}Z)?$"
)


def is_managed_branch(name: Optional[str]) -> bool:
    """True only for branch names the workflow itself generates (``gen/...``)."""
    return isinstance(name, str) and bool(_MANAGED_BRANCH_RE.match(name))


def resolve_runtime_root(
    config=None, env: Optional[Mapping[str, str]] = None
) -> Path:
    """Resolve EDCoPilot's root for a branch operation.

    Branch commands touch the runtime repository, so they follow the same D5
    precedence as every other runtime-touching command: the environment
    variable, then ``roots.edcopilot`` in the content repository's config file,
    then asking the caller. A stale stored path fails loudly and by name; an
    unconfigured root fails with a clear message instead of silently omitting
    the runtime repository.

    ``config`` only supplies the content root used to read ``roots.edcopilot``;
    it carries no EDCoPilot root of its own. The environment is therefore
    consulted on every call, and ``env`` exists so a caller (or a test) can
    supply a hermetic mapping instead of ``os.environ``.
    """
    env_map = os.environ if env is None else env
    if config is None:
        config = get_config(env_map)

    content_root = getattr(config, "content_definitions_root", None)

    if content_root is not None:
        resolved = resolve_edcopilot_root(content_root, env_map)
        if resolved.path is not None:
            return resolved.path
        if resolved.stale is not None:
            raise ConfigError(
                "EDCoPilot root is unusable: configured path no longer exists: "
                f"{resolved.stale}. Update roots.edcopilot in the config file or "
                "set EDCG_EDCOPILOT_ROOT."
            )

    environment_root = environ_edcopilot_root(env_map)
    if environment_root is not None:
        raise ConfigError(
            "EDCoPilot root is unusable: EDCG_EDCOPILOT_ROOT is set to "
            f"'{environment_root}' but it is not an existing directory; set a valid "
            "path or store [roots] edcopilot in the config file"
        )

    raise ConfigError(
        "Cannot proceed without a configured EDCoPilot root: set "
        "EDCG_EDCOPILOT_ROOT or store roots.edcopilot in the config file"
    )


def _is_repo(root) -> bool:
    """True when ``root`` is configured and is a git repository."""
    return root is not None and GitRepo.is_repo(root)


def _branch_state(
    config, runtime_root: Optional[Path] = None
) -> tuple[Optional[str], str, str, str]:
    """Derive the active branch from the two repositories.

    The repositories are the state: the active branch is the content
    repository's current branch when it is a workflow branch (``gen/...``), not
    that repository's default branch, and (when the runtime root is a git
    repository) the runtime repository is on the same branch. A foreign
    non-default checkout is reported through ``content_current_branch`` but is
    never treated as the active workflow branch. Returns ``(active_branch,
    content_current_branch, runtime_current_branch, content_default_branch)``.
    """
    content_root = config.content_definitions_root
    if runtime_root is None:
        runtime_root = resolve_runtime_root(config)

    content_branch = ""
    content_default = ""
    if _is_repo(content_root):
        with GitRepo(content_root) as repo:
            content_branch = repo.current_branch()
            content_default = repo.default_branch()

    runtime_branch = ""
    runtime_is_git = _is_repo(runtime_root)
    if runtime_is_git:
        with GitRepo(runtime_root) as repo:
            runtime_branch = repo.current_branch()

    active: Optional[str] = None
    if (
        is_managed_branch(content_branch)
        and content_branch != content_default
        and (not runtime_is_git or runtime_branch == content_branch)
    ):
        active = content_branch
    return active, content_branch, runtime_branch, content_default


def _foreign_checkout(content_branch: str, content_default: str) -> bool:
    """True when the content repo sits on a non-default branch we did not make."""
    return (
        isinstance(content_branch, str)
        and bool(content_branch)
        and content_branch != content_default
        and not is_managed_branch(content_branch)
    )


@dataclass
class BranchResult:
    branch_name: str
    repos_branched: list[str] = field(default_factory=list)
    backup_path: Optional[Path] = None
    warnings: list[str] = field(default_factory=list)
    message: Optional[str] = None


@dataclass
class BranchStatus:
    active_branch: Optional[str] = None
    content_current_branch: str = ""
    runtime_current_branch: str = ""
    content_status: dict = field(default_factory=dict)
    runtime_status: dict = field(default_factory=dict)
    uncommitted_changes: dict = field(default_factory=dict)
    content_uncommitted: bool = False
    runtime_uncommitted: bool = False
    has_uncommitted_changes: bool = False
    # True when the content repo is on a non-default branch the workflow did
    # not generate (for example a human's ``release`` checkout).
    foreign_checkout: bool = False


@dataclass
class FinalizeResult:
    merged: bool = False
    merge_commits: list[Optional[str]] = field(default_factory=list)
    content_merge_commit: Optional[str] = None
    runtime_merge_commit: Optional[str] = None
    merge_errors: list[str] = field(default_factory=list)
    failed_repos: list[str] = field(default_factory=list)
    pushed: bool = False
    push_status: str = "not_pushed"
    message: Optional[str] = None


@dataclass
class AbortResult:
    discarded_branch: Optional[str] = None
    would_discard: list = field(default_factory=list)
    discarded: list = field(default_factory=list)
    discarded_commits: list[str] = field(default_factory=list)
    content_discarded: bool = False
    runtime_discarded: bool = False
    confirmed: bool = False
    message: Optional[str] = None


def start_branch(description: Optional[str] = None) -> BranchResult:
    """Start a feature branch across the content repo and (if git) runtime root.

    Creates and checks out a matching branch in each repository. That checkout
    is the state: status, finalize and abort read it back from git, so the
    workflow survives across separate command invocations. When the runtime
    root is not a git repository, a timestamped backup copy of the custom file
    is created instead.
    """
    config = get_config()

    branch_name = slugify_branch_name(description)

    repos_branched: list[str] = []
    backup_path: Optional[Path] = None
    warnings_list: list[str] = []

    # Collision handling: check existing branches across repos
    existing_branches: set[str] = set()
    content_root = config.content_definitions_root
    runtime_root = resolve_runtime_root(config)
    for root in (content_root, runtime_root):
        if _is_repo(root):
            with GitRepo(root) as repo:
                existing_branches.update(repo.list_branches())
    if branch_name in existing_branches:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        branch_name = f"{branch_name}-{ts}"

    # Content repo (always expected to be a repo)
    if _is_repo(content_root):
        with GitRepo(content_root) as repo:
            default = repo.default_branch()
            if default and default in repo.list_branches():
                repo.checkout(default)
            # warn if dirty
            try:
                st = repo.status()
                if not st.get("clean", True):
                    warnings_list.append("content root has uncommitted changes")
            except Exception:
                pass
            created = repo.create_branch(branch_name)
            if created is not None:
                repos_branched.append("content")
    else:
        warnings.warn(
            f"Content definitions root is not a git repository: {content_root}",
            UserWarning,
        )
        warnings_list.append("content root is not a git repository")

    # Runtime root
    if _is_repo(runtime_root):
        with GitRepo(runtime_root) as repo:
            default = repo.default_branch()
            if default and default in repo.list_branches():
                repo.checkout(default)
            try:
                st = repo.status()
                if not st.get("clean", True):
                    warnings_list.append("runtime root has uncommitted changes")
            except Exception:
                pass
            created = repo.create_branch(branch_name)
            if created is not None:
                repos_branched.append("runtime")
    else:
        warnings.warn(
            f"EDCoPilot root is not a git repository; creating backup copy: {runtime_root}",
            UserWarning,
        )
        warnings_list.append("runtime root is not a git repository")
        custom_file = runtime_root / CUSTOM_FILE_NAME
        if not custom_file.exists():
            try:
                custom_file.parent.mkdir(parents=True, exist_ok=True)
                custom_file.write_text("", encoding="utf-8")
            except Exception:
                pass
        if custom_file.exists():
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = runtime_root / f"{CUSTOM_FILE_NAME}.{ts}.bak"
            try:
                shutil.copy2(custom_file, backup)
                backup_path = backup
            except Exception as exc:  # pragma: no cover - defensive
                warnings_list.append(f"backup failed: {exc}")

    return BranchResult(
        branch_name=branch_name,
        repos_branched=repos_branched,
        backup_path=backup_path,
        warnings=warnings_list,
    )


def branch_status() -> BranchStatus:
    """Return the current branch orchestration status."""
    config = get_config()

    content_root = config.content_definitions_root
    runtime_root = resolve_runtime_root(config)

    active_branch, content_branch, runtime_branch, content_default = _branch_state(
        config, runtime_root
    )
    content_status: dict = {"staged": [], "unstaged": [], "untracked": [], "clean": True}
    runtime_status: dict = {"staged": [], "unstaged": [], "untracked": [], "clean": True}

    if _is_repo(content_root):
        with GitRepo(content_root) as repo:
            content_status = repo.status()

    if _is_repo(runtime_root):
        with GitRepo(runtime_root) as repo:
            runtime_status = repo.status()

    content_uncommitted = not bool(content_status.get("clean", True))
    runtime_uncommitted = not bool(runtime_status.get("clean", True))
    has_uncommitted = content_uncommitted or runtime_uncommitted

    return BranchStatus(
        active_branch=active_branch,
        content_current_branch=content_branch,
        runtime_current_branch=runtime_branch,
        content_status=content_status,
        runtime_status=runtime_status,
        uncommitted_changes={
            "content": content_status,
            "runtime": runtime_status,
        },
        content_uncommitted=content_uncommitted,
        runtime_uncommitted=runtime_uncommitted,
        has_uncommitted_changes=has_uncommitted,
        foreign_checkout=_foreign_checkout(content_branch, content_default),
    )


def finalize_branch(merge: bool = True, push: bool = False) -> FinalizeResult:
    """Finalize the active feature branch.

    With merge=True (default), merges the feature branch into the default
    branch of each repository and optionally pushes. With merge=False, the
    session stays on the feature branch for further editing.
    """
    config = get_config()
    runtime_root = resolve_runtime_root(config)
    # The repositories are the state; there is no process mirror to consult.
    branch = _branch_state(config, runtime_root)[0]

    if not merge:
        # Stay on the feature branch; ensure checked out where possible
        if branch:
            for root in (config.content_definitions_root, runtime_root):
                if _is_repo(root):
                    with GitRepo(root) as repo:
                        if branch in repo.list_branches():
                            repo.checkout(branch)
        return FinalizeResult(
            merged=False,
            merge_commits=[],
            content_merge_commit=None,
            runtime_merge_commit=None,
            pushed=False,
            push_status="not_pushed",
            message="stayed on feature branch" if branch else "no active branch",
        )

    content_commit: Optional[str] = None
    runtime_commit: Optional[str] = None
    merge_errors: list[str] = []
    failed_repos: list[str] = []

    # Merge the feature branch into the default branch for each repo
    merged = False
    pushed = False
    push_requested = bool(push)
    push_attempted: list[str] = []
    push_succeeded: list[str] = []

    for root, flag_name in (
        (config.content_definitions_root, "content"),
        (runtime_root, "runtime"),
    ):
        if not _is_repo(root) or not branch:
            continue

        with GitRepo(root) as repo:
            default = repo.default_branch()
            if default and default in repo.list_branches():
                # land on the default branch, then merge the feature into it
                if branch in repo.list_branches() and default != branch:
                    repo.checkout(default)

                # merge into default branch
                try:
                    if not repo.status().get("clean", True):
                        warnings.warn(
                            f"Uncommitted changes in {root} before merge", UserWarning
                        )
                    if default != branch:
                        merge_commit = repo.merge(branch)
                        if merge_commit is None:
                            repo.abort_merge()
                            merge_errors.append(
                                f"{flag_name}: merge of {branch} into {default} failed"
                            )
                            failed_repos.append(flag_name)
                        else:
                            merged = True
                            if flag_name == "content":
                                content_commit = merge_commit
                            else:
                                runtime_commit = merge_commit
                except Exception as exc:
                    repo.abort_merge()
                    merge_errors.append(f"{flag_name}: {exc}")
                    failed_repos.append(flag_name)

                # push the default branch (if requested), reporting the truth
                if push_requested:
                    push_attempted.append(flag_name)
                    if repo.push("origin"):
                        push_succeeded.append(flag_name)

    if not push_requested:
        push_status = "not_pushed"
    elif push_requested and not push_attempted:
        # --push was asked for, but no repository offered a branch to push.
        # That is not a refusal by a remote; report the distinct label.
        push_status = "nothing_to_push"
    elif len(push_succeeded) == len(push_attempted):
        push_status = "pushed"
        pushed = True
    elif push_succeeded:
        push_status = "partial"
    else:
        push_status = "failed"

    return FinalizeResult(
        merged=merged,
        merge_commits=[content_commit, runtime_commit],
        content_merge_commit=content_commit,
        runtime_merge_commit=runtime_commit,
        merge_errors=merge_errors,
        failed_repos=failed_repos,
        pushed=pushed,
        push_status=push_status,
        message="merged feature branch"
        if merged
        else "no active branch or no merge performed",
    )


def abort_branch(confirm: bool = False) -> AbortResult:
    """Discard the active feature branch in both repositories.

    With confirm=False (default), returns what would be discarded without
    making changes. With confirm=True, deletes the branch in both repos and
    returns to the default branch.
    """
    config = get_config()
    runtime_root = resolve_runtime_root(config)
    # The repositories are the state; there is no process mirror to consult.
    branch = _branch_state(config, runtime_root)[0]

    # Determine what would be discarded (commits on branch not on default)
    would_discard: list = []
    if branch:
        for root in (config.content_definitions_root, runtime_root):
            if not _is_repo(root):
                continue
            with GitRepo(root) as repo:
                default = repo.default_branch()
                if branch in repo.list_branches():
                    would_discard.extend(repo.commits_between(default, branch))

    if not confirm:
        return AbortResult(
            discarded_branch=branch,
            would_discard=would_discard,
            discarded=[],
            discarded_commits=list(would_discard),
            content_discarded=False,
            runtime_discarded=False,
            confirmed=False,
            message="confirmation required" if branch else "no active branch",
        )

    # confirm=True: delete branch in both repos
    content_discarded = False
    runtime_discarded = False
    for root, flag_name in (
        (config.content_definitions_root, "content"),
        (runtime_root, "runtime"),
    ):
        if not _is_repo(root) or not branch:
            continue
        with GitRepo(root) as repo:
            default = repo.default_branch()
            if branch in repo.list_branches():
                # checkout default if currently on feature branch
                if repo.current_branch() == branch and default in repo.list_branches():
                    repo.checkout(default)
                if repo.delete_branch(branch):
                    if flag_name == "content":
                        content_discarded = True
                    else:
                        runtime_discarded = True

    return AbortResult(
        discarded_branch=branch,
        would_discard=would_discard,
        discarded=would_discard,
        discarded_commits=list(would_discard),
        content_discarded=content_discarded,
        runtime_discarded=runtime_discarded,
        confirmed=True,
        message="branch discarded" if branch else "no active branch; nothing to discard",
    )


def _diff_stats(repo: GitRepo, default: str) -> dict:
    """Files, insertions and deletions for one repository's current branch.

    Combines the working tree (staged, unstaged and untracked files) with the
    commits made since ``default`` diverged. One helper for both repositories
    keeps the counting rule in one place.
    """
    status = repo.status()
    files = (
        set(status.get("staged", []))
        | set(status.get("unstaged", []))
        | set(status.get("untracked", []))
    )

    working = repo.diff_stat()
    committed = repo.diff_stat(default)
    files |= set(working["files"]) | set(committed["files"])

    return {
        "files": sorted(files),
        "insertions": working["insertions"] + committed["insertions"],
        "deletions": working["deletions"] + committed["deletions"],
    }


def review_branch() -> str:
    """Return a summary of the changes in the active branch."""

    config = get_config()

    content_root = config.content_definitions_root
    runtime_root = resolve_runtime_root(config)

    branch_name = _branch_state(config, runtime_root)[0]

    content = {"files": [], "insertions": 0, "deletions": 0}
    if _is_repo(content_root):
        with GitRepo(content_root) as repo:
            if branch_name is None:
                branch_name = repo.current_branch()
            content = _diff_stats(repo, repo.default_branch())

    runtime_is_git = _is_repo(runtime_root)
    runtime = {"files": [], "insertions": 0, "deletions": 0}
    if runtime_is_git:
        with GitRepo(runtime_root) as repo:
            runtime = _diff_stats(repo, repo.default_branch())

    lines = []
    lines.append("# Branch Review Summary")
    lines.append("")
    lines.append(f"**Branch:** {branch_name or '(none)'}")
    lines.append("")
    lines.append("## Content Repo")
    lines.append(f"- Files changed: {len(content['files'])}")
    lines.append(f"- Insertions: {content['insertions']}")
    lines.append(f"- Deletions: {content['deletions']}")
    for name in content["files"]:
        lines.append(f"  - {name}")
    lines.append("")
    lines.append("## Runtime Root")
    if runtime_is_git:
        lines.append(f"- Files changed: {len(runtime['files'])}")
        lines.append(f"- Insertions: {runtime['insertions']}")
        lines.append(f"- Deletions: {runtime['deletions']}")
        for name in runtime["files"]:
            lines.append(f"  - {name}")
    else:
        lines.append("- (non-git runtime root; diff skipped)")
    lines.append("")

    return "\n".join(lines)
