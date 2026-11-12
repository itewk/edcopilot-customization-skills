"""Tests for the content-root writability probe."""

from pathlib import Path

import pytest

from edcg.common.config import ContentRootError, resolve_content_root


def _contents(directory: Path) -> set[str]:
    """Names in ``directory``, used to prove the probe leaves no trace."""
    return {entry.name for entry in directory.iterdir()}


class TestContentRootWriteProbe:
    """The probe must test writability without disturbing existing content."""

    def test_writable_directory_is_accepted_and_left_unchanged(self, tmp_path):
        """A successful probe reports the root and cleans up after itself."""
        before = _contents(tmp_path)

        assert resolve_content_root(tmp_path, {}) == tmp_path

        assert _contents(tmp_path) == before

    def test_write_failure_is_reported_as_not_writable(self, tmp_path, monkeypatch):
        """A directory that refuses a write is reported as not writable."""

        def refusing_write_text(self, *args, **kwargs):
            raise OSError(13, "Permission denied")

        monkeypatch.setattr(Path, "write_text", refusing_write_text)

        with pytest.raises(ContentRootError, match="not writable"):
            resolve_content_root(tmp_path, {})

    def test_failed_write_leaves_no_probe_behind(self, tmp_path, monkeypatch):
        """Cleanup runs even when the write fails, so no probe file survives."""

        def refusing_write_text(self, *args, **kwargs):
            raise OSError(13, "Permission denied")

        monkeypatch.setattr(Path, "write_text", refusing_write_text)
        before = _contents(tmp_path)

        with pytest.raises(ContentRootError):
            resolve_content_root(tmp_path, {})

        assert _contents(tmp_path) == before

    def test_preexisting_probe_named_file_survives(self, tmp_path):
        """A real file whose name matches the old probe name is never touched."""
        sentinel = tmp_path / ".write_probe"
        sentinel.write_text("user data", encoding="utf-8")

        assert resolve_content_root(tmp_path, {}) == tmp_path

        assert sentinel.is_file()
        assert sentinel.read_text(encoding="utf-8") == "user data"

    def test_preexisting_probe_named_directory_survives(self, tmp_path):
        """A real directory whose name matches the old probe name is not an error."""
        occupied = tmp_path / ".write_probe"
        occupied.mkdir()
        (occupied / "keep.txt").write_text("user data", encoding="utf-8")

        assert resolve_content_root(tmp_path, {}) == tmp_path

        assert (occupied / "keep.txt").read_text(encoding="utf-8") == "user data"

    def test_cleanup_failure_is_not_reported_as_unwritable(
        self, tmp_path, monkeypatch
    ):
        """A probe locked during cleanup must not fake an unwritable root."""

        def locked_unlink(self, *args, **kwargs):
            raise PermissionError(13, "The process cannot access the file")

        monkeypatch.setattr(Path, "unlink", locked_unlink)

        assert resolve_content_root(tmp_path, {}) == tmp_path
