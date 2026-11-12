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

from edcg.common.config import ConfigError, get_config, resolve_edcopilot_root
from edcg.repo.gitrepo import GitRepo


# ---------------------------------------------------------------------------
# Branch state mirrors the repositories
# ---------------------------------------------------------------------------
# The repositories are the state: the active branch is whichever branch the
# content repo is checked out on (when it is not the default branch) and the
# runtime repo agrees with. ``_active_branch`` remains only as a compatibility
# mirror for callers that read the module attribute; it is never consulted to
# decide status, finalize, abort or review.
_active_branch: str | None = None
_branch_systems: set[str] = set()


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

    When ``config`` is supplied it is authoritative: its ``edcopilot_root``
    (which the CLI builds from ``EDCG_EDCOPILOT_ROOT``) is trusted without
    consulting the ambient environment, so tests that inject a config are
    hermetic. Only a caller that passes no config at all falls back to reading
    ``env``/``os.environ``.
    """
    if config is None:
        env_map = os.environ if env is None else env
        config = get_config(env_map)
    else:
        env_map = {}

    content_root = getattr(config, "content_definitions_root", None)
    injected = getattr(config, "edcopilot_root", None)

    # A config's own root wins outright when it is usable; this is also the
    # environment value on the CLI path, since load_config takes it from there.
    if injected is not None and Path(injected).is_dir():
        return Path(injected)

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

    if injected is not None:
        raise ConfigError(
            "EDCoPilot root is unusable: EDCG_EDCOPILOT_ROOT is set to "
            f"'{injected}' but it is not an existing directory; set a valid "
            "path or store [roots] edcopilot in the config file"
        )

    raise ConfigError(
        "Cannot proceed without a configured EDCoPilot root: set "
        "EDCG_EDCOPILOT_ROOT or store roots.edcopilot in the config file"
    )


def _is_repo(root) -> bool:
    """True when ``root`` is configured and is a git repository."""
    return root is not None and GitRepo.is_repo(root)


def _default_branch_for(repo: GitRepo) -> str:
    """Best-effort default branch detection that prefers branches that exist."""
    try:
        branches = repo.list_branches()
    except Exception:
        branches = []
    if "main" in branches:
        return "main"
    if "master" in branches:
        return "master"
    try:
        db = repo.default_branch()
    except Exception:
        db = "main"
    if db in branches:
        return db
    if branches:
        return branches[0]
    return db or "main"


def _branch_state(
    config, runtime_root: Optional[Path] = None
) -> tuple[Optional[str], str, str]:
    """Derive the active branch from the two repositories.

    The active branch is the content repository's current branch when it is a
    workflow branch (``gen/...``), not that repository's default branch, and
    (when the runtime root is a git repository) the runtime repository is on
    the same branch. A foreign non-default checkout is reported through
    ``content_current_branch`` but is never treated as the active workflow
    branch. Returns
    ``(active_branch, content_current_branch, runtime_current_branch)``.
    """
    content_root = config.content_definitions_root
    if runtime_root is None:
        runtime_root = resolve_runtime_root(config)

    content_branch = ""
    content_default = ""
    if _is_repo(content_root):
        repo = GitRepo(content_root)
        try:
            content_branch = repo.current_branch()
            content_default = _default_branch_for(repo)
        finally:
            repo.close()

    runtime_branch = ""
    runtime_is_git = _is_repo(runtime_root)
    if runtime_is_git:
        repo = GitRepo(runtime_root)
        try:
            runtime_branch = repo.current_branch()
        finally:
            repo.close()

    active: Optional[str] = None
    if (
        is_managed_branch(content_branch)
        and content_branch != content_default
        and (not runtime_is_git or runtime_branch == content_branch)
    ):
        active = content_branch
    return active, content_branch, runtime_branch


def _foreign_checkout(content_branch: str, content_default: str) -> bool:
    """True when the content repo sits on a non-default branch we did not make."""
    return (
        isinstance(content_branch, str)
        and bool(content_branch)
        and content_branch != content_default
        and not is_managed_branch(content_branch)
    )


def _default_branch_of(root) -> str:
    """The default branch of ``root``, or ``""`` when it is not a repository."""
    if not _is_repo(root):
        return ""
    repo = GitRepo(root)
    try:
        return _default_branch_for(repo)
    finally:
        repo.close()


@dataclass
class BranchResult:
    branch_name: str
    repos_branched: list[str] = field(default_factory=list)
    backup_path: Optional[Path] = None
    # Convenience booleans / aliases for compatibility
    branch: Optional[str] = None
    name: Optional[str] = None
    repos: Optional[list[str]] = None
    backup: Optional[Path] = None
    content_branched: bool = False
    runtime_branched: bool = False
    warnings: list[str] = field(default_factory=list)
    message: Optional[str] = None

    def __post_init__(self):
        if self.branch is None:
            self.branch = self.branch_name
        if self.name is None:
            self.name = self.branch_name
        if self.repos is None:
            self.repos = list(self.repos_branched)
        if self.backup is None:
            self.backup = self.backup_path
        if "content" in self.repos_branched or "content_definitions" in self.repos_branched:
            self.content_branched = True
        if "runtime" in self.repos_branched or "edcopilot" in self.repos_branched:
            self.runtime_branched = True


@dataclass
class BranchStatus:
    active_branch: Optional[str] = None
    content_current_branch: str = ""
    runtime_current_branch: str = ""
    # aliases
    active_branch_name: Optional[str] = None
    content_branch: str = ""
    runtime_branch: str = ""
    content_branch_name: str = ""
    runtime_branch_name: str = ""
    content_status: dict = field(default_factory=dict)
    runtime_status: dict = field(default_factory=dict)
    uncommitted_changes: dict = field(default_factory=dict)
    uncommitted: dict = field(default_factory=dict)
    content_uncommitted: bool = False
    runtime_uncommitted: bool = False
    has_uncommitted_changes: bool = False
    # True when the content repo is on a non-default branch the workflow did
    # not generate (for example a human's ``release`` checkout).
    foreign_checkout: bool = False
    systems_affected: list[str] = field(default_factory=list)
    affected_systems: list[str] = field(default_factory=list)
    systems: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.active_branch_name is None:
            self.active_branch_name = self.active_branch
        self.content_branch = self.content_current_branch
        self.runtime_branch = self.runtime_current_branch
        self.content_branch_name = self.content_current_branch
        self.runtime_branch_name = self.runtime_current_branch
        self.uncommitted = dict(self.uncommitted_changes)
        self.affected_systems = list(self.systems_affected)
        self.systems = list(self.systems_affected)


@dataclass
class FinalizeResult:
    merged: bool = False
    merge_commits: list[str] = field(default_factory=list)
    content_merge_commit: Optional[str] = None
    runtime_merge_commit: Optional[str] = None
    merge_errors: list[str] = field(default_factory=list)
    failed_repos: list[str] = field(default_factory=list)
    pushed: bool = False
    push_status: str = "not_pushed"
    message: Optional[str] = None
    # aliases
    commits: Optional[list[str]] = None
    content_commit: Optional[str] = None
    runtime_commit: Optional[str] = None

    def __post_init__(self):
        if self.commits is None:
            self.commits = list(self.merge_commits)
        if self.content_commit is None:
            self.content_commit = self.content_merge_commit
        if self.runtime_commit is None:
            self.runtime_commit = self.runtime_merge_commit


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
    # aliases
    branch: Optional[str] = None
    discarded_items: Optional[list] = None

    def __post_init__(self):
        if self.branch is None:
            self.branch = self.discarded_branch
        if self.discarded_items is None:
            self.discarded_items = list(self.would_discard) if not self.confirmed else list(self.discarded)


def start_branch(description: Optional[str] = None) -> BranchResult:
    """Start a feature branch across the content repo and (if git) runtime root.

    Creates and checks out a matching branch in each repository. That checkout
    is the state: status, finalize and abort read it back from git, so the
    workflow survives across separate command invocations. When the runtime
    root is not a git repository, a timestamped backup copy of the custom file
    is created instead.
    """
    global _active_branch, _branch_systems

    config = get_config()
    from edcg.repo.gitrepo import slugify_branch_name

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
            r = GitRepo(root)
            try:
                existing_branches.update(r.list_branches())
            finally:
                r.close()
    if branch_name in existing_branches:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        branch_name = f"{branch_name}-{ts}"

    # Content repo (always expected to be a repo)
    if _is_repo(content_root):
        repo = GitRepo(content_root)
        try:
            default = _default_branch_for(repo)
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
        finally:
            repo.close()
    else:
        warnings.warn(
            f"Content definitions root is not a git repository: {content_root}",
            UserWarning,
        )
        warnings_list.append("content root is not a git repository")

    # Runtime root
    if _is_repo(runtime_root):
        repo = GitRepo(runtime_root)
        try:
            default = _default_branch_for(repo)
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
        finally:
            repo.close()
    else:
        warnings.warn(
            f"EDCoPilot root is not a git repository; creating backup copy: {runtime_root}",
            UserWarning,
        )
        warnings_list.append("runtime root is not a git repository")
        custom_file = runtime_root / "EDCoPilot.SpeechExtensions.Custom.txt"
        if not custom_file.exists():
            try:
                custom_file.parent.mkdir(parents=True, exist_ok=True)
                custom_file.write_text("", encoding="utf-8")
            except Exception:
                pass
        if custom_file.exists():
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = runtime_root / f"EDCoPilot.SpeechExtensions.Custom.txt.{ts}.bak"
            try:
                shutil.copy2(custom_file, backup)
                backup_path = backup
            except Exception as exc:  # pragma: no cover - defensive
                warnings_list.append(f"backup failed: {exc}")

    # Compatibility mirror only: the checkout above is the real state.
    _active_branch = branch_name
    _branch_systems = set()

    return BranchResult(
        branch_name=branch_name,
        repos_branched=repos_branched,
        backup_path=backup_path,
        warnings=warnings_list,
    )


def branch_status() -> BranchStatus:
    """Return the current branch orchestration status."""
    global _active_branch, _branch_systems

    config = get_config()

    content_root = config.content_definitions_root
    runtime_root = resolve_runtime_root(config)

    active_branch, content_branch, runtime_branch = _branch_state(
        config, runtime_root
    )
    content_status: dict = {"staged": [], "unstaged": [], "untracked": [], "clean": True}
    runtime_status: dict = {"staged": [], "unstaged": [], "untracked": [], "clean": True}

    if _is_repo(content_root):
        repo = GitRepo(content_root)
        try:
            content_status = repo.status()
        finally:
            repo.close()

    if _is_repo(runtime_root):
        repo = GitRepo(runtime_root)
        try:
            runtime_status = repo.status()
        finally:
            repo.close()

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
        foreign_checkout=_foreign_checkout(
            content_branch, _default_branch_of(content_root)
        ),
        systems_affected=sorted(_branch_systems),
    )


def finalize_branch(merge: bool = True, push: bool = False) -> FinalizeResult:
    """Finalize the active feature branch.

    With merge=True (default), merges the feature branch into the default
    branch of each repository and optionally pushes. With merge=False, the
    session stays on the feature branch for further editing.
    """
    global _active_branch, _branch_systems

    config = get_config()
    runtime_root = resolve_runtime_root(config)
    # The repositories are the state; the process mirror is never consulted.
    branch = _branch_state(config, runtime_root)[0]

    if not merge:
        # Stay on the feature branch; ensure checked out where possible
        if branch:
            for root in (config.content_definitions_root, runtime_root):
                if _is_repo(root):
                    repo = GitRepo(root)
                    try:
                        if branch in repo.list_branches():
                            repo.checkout(branch)
                    finally:
                        repo.close()
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

    for root, flag_name in ((config.content_definitions_root, "content"), (runtime_root, "runtime")):
        if not _is_repo(root) or not branch:
            continue

        repo = GitRepo(root)
        try:
            default = _default_branch_for(repo)
            if default and default in repo.list_branches():
                # land on the default branch, then merge the feature into it
                if branch in repo.list_branches():
                    if default != branch:
                        repo.checkout(default)

                # merge into default branch
                try:
                    if not repo.status().get("clean", True):
                        warnings.warn(f"Uncommitted changes in {root} before merge", UserWarning)
                    if default != branch:
                        repo._repo.git.merge(branch)
                        merged = True
                        commit_hash = repo._repo.head.commit.hexsha[:8]
                        if flag_name == "content":
                            content_commit = commit_hash
                        else:
                            runtime_commit = commit_hash
                except Exception as exc:
                    try:
                        repo._repo.git.merge("--abort")
                    except Exception:
                        pass
                    merge_errors.append(f"{flag_name}: {exc}")
                    failed_repos.append(flag_name)

                # push the default branch (if requested), reporting the truth
                if push_requested:
                    push_attempted.append(flag_name)
                    if repo.push("origin"):
                        push_succeeded.append(flag_name)
        finally:
            repo.close()

    _active_branch = None
    _branch_systems = set()

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
        message="merged feature branch" if merged else "no active branch or no merge performed",
    )


def abort_branch(confirm: bool = False) -> AbortResult:
    """Discard the active feature branch in both repositories.

    With confirm=False (default), returns what would be discarded without
    making changes. With confirm=True, deletes the branch in both repos and
    returns to the default branch.
    """
    global _active_branch, _branch_systems

    config = get_config()
    runtime_root = resolve_runtime_root(config)
    # The repositories are the state; the process mirror is never consulted.
    branch = _branch_state(config, runtime_root)[0]

    # Determine what would be discarded (commits on branch not on default)
    would_discard: list = []
    if branch:
        for root in (config.content_definitions_root, runtime_root):
            if not _is_repo(root):
                continue
            repo = GitRepo(root)
            try:
                default = _default_branch_for(repo)
                if branch in repo.list_branches():
                    rrepo = getattr(repo, "_repo", None)
                    if rrepo is not None and hasattr(rrepo, "iter_commits"):
                        try:
                            commits = list(rrepo.iter_commits(f"{default}..{branch}"))
                            for c in commits:
                                would_discard.append(getattr(c, "summary", str(c)))
                        except Exception:
                            pass
            finally:
                repo.close()

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
    for root, flag_name in ((config.content_definitions_root, "content"), (runtime_root, "runtime")):
        if not _is_repo(root) or not branch:
            continue
        repo = GitRepo(root)
        try:
            default = _default_branch_for(repo)
            if branch in repo.list_branches():
                # checkout default if currently on feature branch
                if repo.current_branch() == branch:
                    if default in repo.list_branches():
                        repo.checkout(default)
                    else:
                        # fallback: create? just try checkout
                        pass
                # delete branch
                try:
                    rrepo = getattr(repo, "_repo", None)
                    if rrepo is not None and hasattr(rrepo, "git"):
                        rrepo.git.branch("-D", branch)
                        if flag_name == "content":
                            content_discarded = True
                        else:
                            runtime_discarded = True
                except Exception:
                    pass
        finally:
            repo.close()

    _active_branch = None
    _branch_systems = set()

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


def review_branch() -> str:
    """Return a summary of the changes in the active branch."""

    config = get_config()

    content_root = config.content_definitions_root
    runtime_root = resolve_runtime_root(config)

    branch_name = _branch_state(config, runtime_root)[0]

    # Content repo diff
    content_files: list[str] = []
    content_ins = 0
    content_del = 0
    if _is_repo(content_root):
        repo = GitRepo(content_root)
        try:
            if branch_name is None:
                branch_name = repo.current_branch()
            st = repo.status()
            content_files = sorted(set(st.get("staged", []) + st.get("unstaged", []) + st.get("untracked", [])))
            for staged in (False, True):
                d = repo.diff(staged=staged)
                for line in d.splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        content_ins += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        content_del += 1
            # Committed changes since divergence from default branch
            try:
                default = _default_branch_for(repo)
                committed_names = repo._repo.git.diff(f"{default}...HEAD", "--name-only").splitlines()
                content_files = sorted(set(content_files + [n for n in committed_names if n]))
                committed_diff = repo._repo.git.diff(f"{default}...HEAD")
                for line in committed_diff.splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        content_ins += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        content_del += 1
            except Exception:
                pass
        finally:
            repo.close()

    # Runtime root diff
    runtime_files: list[str] = []
    runtime_ins = 0
    runtime_del = 0
    runtime_is_git = _is_repo(runtime_root)
    if runtime_is_git:
        repo = GitRepo(runtime_root)
        try:
            st = repo.status()
            runtime_files = sorted(set(st.get("staged", []) + st.get("unstaged", []) + st.get("untracked", [])))
            for staged in (False, True):
                d = repo.diff(staged=staged)
                for line in d.splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        runtime_ins += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        runtime_del += 1
            try:
                default = _default_branch_for(repo)
                committed_names = repo._repo.git.diff(f"{default}...HEAD", "--name-only").splitlines()
                runtime_files = sorted(set(runtime_files + [n for n in committed_names if n]))
                committed_diff = repo._repo.git.diff(f"{default}...HEAD")
                for line in committed_diff.splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        runtime_ins += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        runtime_del += 1
            except Exception:
                pass
        finally:
            repo.close()

    systems = sorted(_branch_systems)

    lines = []
    lines.append("# Branch Review Summary")
    lines.append("")
    lines.append(f"**Branch:** {branch_name or '(none)'}")
    lines.append("")
    lines.append("## Content Repo")
    lines.append(f"- Files changed: {len(content_files)}")
    lines.append(f"- Insertions: {content_ins}")
    lines.append(f"- Deletions: {content_del}")
    if content_files:
        for f in content_files:
            lines.append(f"  - {f}")
    lines.append("")
    lines.append("## Runtime Root")
    if runtime_is_git:
        lines.append(f"- Files changed: {len(runtime_files)}")
        lines.append(f"- Insertions: {runtime_ins}")
        lines.append(f"- Deletions: {runtime_del}")
        if runtime_files:
            for f in runtime_files:
                lines.append(f"  - {f}")
    else:
        lines.append("- (non-git runtime root; diff skipped)")
    lines.append("")
    lines.append("## Systems Affected")
    if systems:
        for s in systems:
            lines.append(f"- {s}")
    else:
        lines.append("(none)")
    lines.append("")

    return "\n".join(lines)