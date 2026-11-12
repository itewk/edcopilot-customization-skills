"""Marker database functions for EDCoPilot custom speech extensions.

``UPDATEDB`` markers sit immediately under a tag and tell EDCoPilot's database
builder that the block changed. Adding or removing markers is one pass, one
file write and one commit. The scripts never pause for a gate; they do refuse
impossible or invalid operations.
"""

from pathlib import Path
from typing import Optional

from edcg.common.layout import resolve_custom_file
from edcg.content.custom_file import (
    COMMIT_PREFIX,
    _append_co_author_trailer,
)
from edcg.repo.gitrepo import GitRepo


def custom_file_exists() -> bool:
    """Whether EDCoPilot's custom file exists; False before the first write."""
    custom_file, _ = resolve_custom_file()
    return custom_file.exists()


def _commit_marker_change(
    edcopilot_root: Path,
    action: str,
    tags: list[str],
    commit_co_author: Optional[str],
) -> Optional[str]:
    """Commit one marker pass for every changed tag."""
    if not GitRepo.is_repo(edcopilot_root):
        return None
    repo = GitRepo(edcopilot_root)
    try:
        repo.add_all()
        noun = "tag" if len(tags) == 1 else "tags"
        message = f"{COMMIT_PREFIX}: markdb {action} {len(tags)} {noun}"
        message = f"{message}\n\n" + "\n".join(tags)
        message = _append_co_author_trailer(message, commit_co_author)
        return repo.commit(message)
    finally:
        repo.close()


def _apply_markers(
    tags: list[str],
    *,
    add: bool,
    commit_co_author: Optional[str],
) -> dict:
    """Add or remove UPDATEDB markers in one pass, one write and one commit.

    The scan and the single write are shared; ``add`` chooses whether a matched
    tag gains a marker or loses the one under it. Returns ``modified_tags`` (tags
    found, in input order) and ``commit_hashes`` (one hash for the whole pass, or
    ``[]`` when nothing changed).
    """
    custom_file, config = resolve_custom_file()

    if not custom_file.exists():
        return {"modified_tags": [], "commit_hashes": []}

    # read_text normalises line endings, so splitlines(keepends=True) yields
    # LF-terminated lines; the file is written back with CRLF below.
    content = custom_file.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    modified_tags: list[str] = []
    changed_tags: list[str] = []
    seen: set[str] = set()

    for tag in tags:
        tag_stripped = tag.strip()
        if not tag_stripped or tag_stripped in seen:
            continue
        seen.add(tag_stripped)

        for i, line in enumerate(lines):
            if line.rstrip("\r\n").strip() != tag_stripped:
                continue
            modified_tags.append(tag_stripped)
            has_marker = i + 1 < len(lines) and lines[i + 1].strip() == "UPDATEDB"
            if add:
                if has_marker:
                    break
                # read_text normalises line endings, so only the final line can
                # lack one; terminate it first so the marker cannot fuse with
                # the tag.
                if not line.endswith("\n"):
                    lines[i] = line + "\n"
                lines.insert(i + 1, "UPDATEDB\n")
                changed_tags.append(tag_stripped)
            elif has_marker:
                lines.pop(i + 1)
                changed_tags.append(tag_stripped)
            break

    if not changed_tags:
        return {"modified_tags": modified_tags, "commit_hashes": []}

    custom_file.write_text("".join(lines), encoding="utf-8", newline="\r\n")

    commit_hash = None
    if config.auto_commit:
        commit_hash = _commit_marker_change(
            custom_file.parent,
            "add" if add else "remove",
            changed_tags,
            commit_co_author,
        )

    return {
        "modified_tags": modified_tags,
        "commit_hashes": [commit_hash],
    }


def markdb_add(
    tags: list[str],
    commit_co_author: Optional[str] = None,
) -> dict:
    """Add UPDATEDB marker lines after specified tags in the EDCoPilot custom file.

    This function adds a `UPDATEDB` marker line immediately after each specified tag
    in EDCoPilot.SpeechExtensions.Custom.txt. All markers are applied in one
    pass, the file is written once, and one commit covers every changed tag.

    Args:
        tags: List of tag lines to mark (e.g., ["@SystemGreeting<~>System Name",
            "@StationGreeting<~>System Name<~>Station Name"])
        commit_co_author: Optional trailer value naming the harness and model(s)
            that produced the content. The function prefixes it with "Co-authored-by: ".

    Returns:
        Dict with:
        - "modified_tags": tags found in the file, in input order
        - "commit_hashes": one hash for the whole pass (None when auto-commit
          is off or the root is not a repository), or [] when nothing changed
    """
    return _apply_markers(
        tags, add=True, commit_co_author=commit_co_author
    )


def markdb_remove(
    tags: list[str],
    commit_co_author: Optional[str] = None,
) -> dict:
    """Remove UPDATEDB marker lines after specified tags in the EDCoPilot custom file.

    This function removes a `UPDATEDB` marker line immediately after each specified tag
    in EDCoPilot.SpeechExtensions.Custom.txt. All markers are removed in one
    pass, the file is written once, and one commit covers every changed tag.

    Args:
        tags: List of tag lines to unmark (e.g., ["@SystemGreeting<~>System Name",
            "@StationGreeting<~>System Name<~>Station Name"])
        commit_co_author: Optional trailer value naming the harness and model(s)
            that produced the content. The function prefixes it with "Co-authored-by: ".

    Returns:
        Dict with:
        - "modified_tags": tags found in the file, in input order
        - "commit_hashes": one hash for the whole pass (None when auto-commit
          is off or the root is not a repository), or [] when nothing changed
    """
    return _apply_markers(
        tags, add=False, commit_co_author=commit_co_author
    )
