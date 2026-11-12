"""Save a system dossier and its rules to the content definitions repo."""

from __future__ import annotations

from typing import Optional

from edcg.common.config import get_config
from edcg.common.layout import dossier_path, rules_path, systems_dir
from edcg.content.custom_file import COMMIT_PREFIX, _append_co_author_trailer
from edcg.repo.gitrepo import GitRepo
from edcg.rules.validation import SaveResult


def save_definition(
    system_name: str,
    dossier_md: str,
    rules_toml: str,
    commit_co_author: Optional[str] = None,
) -> SaveResult:
    """Persist a validated system dossier and rules to the content definitions repo.

    This writes the dossier and rules files to the edcopilot-content-definitions
    repository and creates a git commit with a standardized message.

    Args:
        system_name: The exact system name (must match rules.system.names).
        dossier_md: The complete dossier markdown content.
        rules_toml: The system rules TOML content.
        commit_co_author: Optional trailer value naming the harness and model(s)
            that produced the dossier, e.g.
            "🤖 OpenCode (DeepSeek V4.1 Flash Free) <noreply@opencode.ai>".
            The function prefixes it with "Co-authored-by: ".

    Returns:
        SaveResult with commit_hash (short, 8 chars) and files_changed list.

    Files written:
    - systems/<slug>.md (dossier)
    - systems/<slug>.rules.toml (rules)

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
    repo = GitRepo(repo_root)
    try:
        repo.add_all()
        commit_hash = repo.commit(commit_message)
    finally:
        repo.close()

    # Determine files changed
    files_changed = [
        str(dossier_file.relative_to(repo_root)),
        str(rules_file.relative_to(repo_root)),
    ]

    return SaveResult(commit_hash=commit_hash, files_changed=files_changed)
