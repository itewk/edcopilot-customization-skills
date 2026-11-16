"""Content file handling functions for EDCoPilot custom speech extensions.

Everything needed to append validated content to
``EDCoPilot.SpeechExtensions.Custom.txt``: the block splitter, the provenance
marker, the per-block labelling and the git commit. The scripts never pause
for a gate; they do refuse impossible or invalid operations.
"""

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from edcg.common.layout import (
    CUSTOM_FILE_NAME,
    PROVENANCE_RE,
    resolve_custom_file,
)
from edcg.repo.gitrepo import GitRepo

COMMIT_PREFIX = "edcg"

__all__ = ["CUSTOM_FILE_NAME", "PROVENANCE_RE", "WriteResult", "write_content"]

#: Provenance triple's first field: the generator version.
VERSION = "1.0.0-alpha.3"


@dataclass(frozen=True)
class WriteResult:
    """Result of a write_content operation.

    Mirrors the old handler's payload with the gate/pause states removed: a
    write can no longer pause, so there is nothing to ask and no workflow table.
    """

    file_path: Path
    commit_hash: Optional[str]


def _split_content_blocks(content_block: str) -> list[str]:
    """Split authored text into tag blocks, each starting at an @ tag line."""
    blocks: list[str] = []
    current: list[str] = []
    for line in content_block.splitlines():
        if line.strip().startswith("@") and current:
            blocks.append("\n".join(current).strip("\n"))
            current = [line]
            continue
        current.append(line)
    if current:
        block = "\n".join(current).strip("\n")
        if block:
            blocks.append(block)
    return [block for block in blocks if block.strip()]


def _collapse_provenance(text: str) -> str:
    """Drop every provenance marker but the first, so a file validates as one block."""
    seen = False
    kept: list[str] = []
    for line in text.splitlines():
        if PROVENANCE_RE.match(line):
            if seen:
                continue
            seen = True
        kept.append(line)
    return "\n".join(kept)


def _append_co_author_trailer(message: str, co_author: Optional[str]) -> str:
    """Append a Co-authored-by trailer naming the harness and model(s)."""
    if not co_author:
        return message
    trailer = co_author.strip()
    if not trailer:
        return message
    return f"{message}\n\nCo-authored-by: {trailer}"


def write_content(
    system_name: str,
    content_block: str = "",
    model: Optional[str] = None,
    commit_co_author: Optional[str] = None,
) -> WriteResult:
    """Append a validated provenance block to EDCoPilot.SpeechExtensions.Custom.txt with git commit.

    This function writes generated speech extension content to the EDCoPilot custom file,
    prepending a provenance comment with version, model, and timestamp information.
    If the EDCoPilot root is a git repository, it creates a commit with a standardized message.
    Omit the block to commit edits already staged in the runtime repo.

    Args:
        system_name: Name of the system the content is for (used in commit message).
        content_block: The content block to append (should contain @tag lines and
            phrases). Omit or pass an empty string to commit edits already staged
            in the runtime repo, for example by rewrite_tag.
        model: Optional model name that generated the content (included in provenance).
        commit_co_author: Optional trailer value naming the harness and model(s)
            that produced the content, e.g.
            "🤖 OpenCode (DeepSeek V4.1 Flash Free) <noreply@opencode.ai>".
            The function prefixes it with "Co-authored-by: ".

    Returns:
        WriteResult with file_path (Path to the custom file) and commit_hash (short hash or None).

    The provenance comment format:
    <!-- provenance: edcopilot_customization_generator {version} — {model} — {timestamp} -->

    Commit message format:
    edcg: content {system}
    """
    custom_file, config = resolve_custom_file()

    block = (content_block or "").strip()
    if not block and not custom_file.exists():
        return WriteResult(file_path=custom_file, commit_hash=None)

    if block:
        # Ensure the file exists
        custom_file.parent.mkdir(parents=True, exist_ok=True)
        if not custom_file.exists():
            custom_file.write_text("", encoding="utf-8", newline="\r\n")

        # Build provenance comment
        version = VERSION
        model_name = model or "unknown"
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        provenance = f"<!-- provenance: edcopilot_customization_generator {version} — {model_name} — {timestamp} -->"

        # Prepare the content to append: a provenance marker before each tag block,
        # so the file reads as labelled blocks rather than one marker over many.
        if not content_block.endswith("\n"):
            content_block = content_block + "\n"

        blocks = _split_content_blocks(content_block)
        if blocks:
            content_block = "\n\n".join(f"{provenance}\n{chunk}" for chunk in blocks) + "\n"
        else:
            content_block = f"{provenance}\n{content_block}"

        # Read existing content
        existing_content = custom_file.read_text(encoding="utf-8")

        # Append new content with provenance
        # Add a blank line before provenance if file doesn't end with one
        if existing_content and not existing_content.endswith("\n"):
            existing_content += "\n"
        if existing_content and not existing_content.endswith("\n\n"):
            existing_content += "\n"

        new_content = existing_content + content_block

        # Write with CRLF line endings
        custom_file.write_text(new_content, encoding="utf-8", newline="\r\n")

    # Git commit if auto_commit and it's a repo
    commit_hash = None
    if config.auto_commit and GitRepo.is_repo(custom_file.parent):
        with GitRepo(custom_file.parent) as repo:
            repo.add_all()
            commit_message = f"{COMMIT_PREFIX}: content {system_name}"
            commit_message = _append_co_author_trailer(commit_message, commit_co_author)
            commit_hash = repo.commit(commit_message)

    return WriteResult(
        file_path=custom_file,
        commit_hash=commit_hash,
    )
