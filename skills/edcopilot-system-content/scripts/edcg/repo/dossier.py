"""Save a system dossier and its rules to the content definitions repo."""

from __future__ import annotations

from typing import Optional

from edcg.common.config import get_config
from edcg.common.layout import dossier_path, rules_path, systems_dir
from edcg.content.custom_file import COMMIT_PREFIX, _append_co_author_trailer
from edcg.repo.gitrepo import GitRepo
from edcg.rules.validation import ALL_RULES, SaveResult


def save_definition(
    system_name: str,
    dossier_md: str,
    rules_toml: str,
    commit_co_author: Optional[str] = None,
) -> SaveResult:
    """Persist a validated system dossier and rules to the content definitions repo.

    This writes the dossier and rules files to the edcopilot-content-definitions
    repository and creates a git commit with a standardized message. The commit
    is made whenever the content root is a git repository; it is not gated by
    ``EDCG_AUTO_COMMIT``, which governs the runtime writes instead.

    Args:
        system_name: The exact system name (must match rules.system.names).
        dossier_md: The complete dossier markdown content.
        rules_toml: The system rules TOML content.
        commit_co_author: Optional trailer value naming the harness and model(s)
            that produced the dossier, e.g.
            "🤖 OpenCode (DeepSeek V4.1 Flash Free) <noreply@opencode.ai>".
            The function prefixes it with "Co-authored-by: ".

    Returns:
        SaveResult with commit_hash (short, 8 chars) and files_changed: the
        posix-separated paths the commit actually recorded (so an add that git
        refused cannot be over-reported), or an empty list when there was
        nothing to commit.

    Files written:
    - systems/<slug>.md (dossier)
    - systems/<slug>.rules.toml (rules)

    Commit contents:
    - the two files above, always;
    - systems/all.rules.toml on the first save, when it exists and is still
      untracked — the reviewed house rules ride along with the definition that
      first needs them;
    - nothing else. A stray or staging file left in the content root stays
      untracked. A tracked ``systems/all.rules.toml`` is deliberately NOT
      committed by this save even when it is modified: house-rule edits are
      deliberate commits of their own.

    Commit message format:
    - New system: "edcg: scaffold {system} — {summary}"
    - Update: "edcg: update {system} — {summary}"
    - With commit_co_author: the message ends with a Co-authored-by trailer.
    """
    config = get_config()
    repo_root = config.content_definitions_root
    directory = systems_dir(config)
    directory.mkdir(parents=True, exist_ok=True)

    dossier_file = dossier_path(config, system_name)
    rules_file = rules_path(config, system_name)

    # Check if this is a new system or update
    is_new = not (dossier_file.exists() and rules_file.exists())

    # Write files
    dossier_file.write_text(dossier_md, encoding="utf-8", newline="\r\n")
    rules_file.write_text(rules_toml, encoding="utf-8", newline="\r\n")

    # Create commit message
    action = "scaffold" if is_new else "update"
    # Extract a brief summary from the dossier (first line of section 2 or first 50 chars of lore)
    summary = "system definition"
    lines = dossier_md.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("## 2."):
            # Look for content after section 2 header
            for j in range(i + 1, min(i + 5, len(lines))):
                if lines[j].strip() and not lines[j].startswith("#"):
                    summary = lines[j].strip()[:60]
                    break
            break

    commit_message = f"{COMMIT_PREFIX}: {action} {system_name} — {summary}"
    commit_message = _append_co_author_trailer(commit_message, commit_co_author)

    # Git operations: always commit when the content root is a repository.
    with GitRepo(repo_root) as repo:
        # One staging list, and one source for the report below: what git
        # accepted is what the commit holds, which is what files_changed says.
        to_stage = [
            str(dossier_file.relative_to(repo_root)),
            str(rules_file.relative_to(repo_root)),
        ]
        all_rules_file = directory / ALL_RULES
        if all_rules_file.exists() and repo.is_untracked(all_rules_file):
            # First save: the reviewed house rules have never been committed,
            # so the definition that first needs them carries them.
            to_stage.append(str(all_rules_file.relative_to(repo_root)))

        repo.add(*to_stage)
        commit_hash = repo.commit(commit_message)

        # Derived from the commit itself, not from the staging intent: git is
        # the only authority on what landed, and its paths are posix on every
        # platform. Nothing to commit means nothing changed to report.
        files_changed = repo.commit_files(commit_hash) if commit_hash else []

    return SaveResult(commit_hash=commit_hash, files_changed=files_changed)
