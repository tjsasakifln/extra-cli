"""Static fail-closed contracts for the production off-site backup script."""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "backup-database.sh"


def test_backup_failure_preserves_nonzero_exit_code() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'if do_backup "$BACKUP_BASE"; then' in source
    assert "backup_exit=$?" in source
    assert 'if ! do_backup "$BACKUP_BASE"; then' not in source


def test_offsite_backup_is_published_atomically() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    staging = 'remote_staging="${dump_path}.partial.$$"'
    copy = 'cp -f "$staging_path" "$remote_staging"'
    publish = 'mv -f "$remote_staging" "$dump_path"'
    assert staging in source
    assert copy in source
    assert publish in source
    assert source.index(staging) < source.index(copy) < source.index(publish)
    assert 'cp -f "$staging_path" "$dump_path"' not in source
