"""Static fail-closed contracts for the production off-site backup script."""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "backup-database.sh"


def test_backup_failure_preserves_nonzero_exit_code() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'if do_backup "$BACKUP_BASE"; then' in source
    assert "backup_exit=$?" in source
    assert 'if ! do_backup "$BACKUP_BASE"; then' not in source


def test_notification_command_is_direct_and_fail_closed() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'eval "$NOTIFY_CMD"' not in source
    assert '[[ "$NOTIFY_CMD" == /* ]]' in source
    assert '[[ ! "$NOTIFY_CMD" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]*$ ]]' in source
    assert '"$NOTIFY_CMD" "$subject" "$body"' in source
    assert "BACKUP_NOTIFY_CMD inválido; notificação desabilitada" in source


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
    assert 'if ! sync "$remote_staging"; then' in source
    assert source.index(copy) < source.index('if ! sync "$remote_staging"; then')
    assert source.index('if ! sync "$remote_staging"; then') < source.index(publish)
    assert 'CURRENT_REMOTE_STAGING="$remote_staging"' in source
    assert 'remove_remote_staging "$CURRENT_REMOTE_STAGING"' in source


def test_offsite_directories_are_observable_without_exposing_dump_contents() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'OBSERVER_GROUP="${BACKUP_OBSERVER_GROUP:-extra-consultoria}"' in source
    assert 'chgrp "$OBSERVER_GROUP" "$base/daily" "$base/weekly"' in source
    assert 'chmod 0750 "$base/daily" "$base/weekly"' in source
    assert "chmod -R" not in source


def test_nfs_statfs_lag_requires_verified_unlink_and_copy_headroom() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    unlink = 'rm -f -- "$candidate"'
    absent = 'if [ -e "$candidate" ] || [ -L "$candidate" ]; then'
    headroom = 'if [ "$free_after" -lt "$copy_headroom_bytes" ]; then'
    lag = 'Byte retention aceitou contabilização NFS atrasada'
    assert unlink in source
    assert 'if ! rm -f -- "$candidate"; then' in source
    assert absent in source
    assert headroom in source
    assert lag in source
    assert "nfs|nfs4)" in source
    assert source.index(unlink) < source.index(absent) < source.index(headroom) < source.index(lag)


def test_nfs_directory_fsync_exception_preserves_file_fsync_publication_gate() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    nfs_exception = 'não exige fsync de diretório incompatível com NFS'
    retention_call = "if ! do_byte_balanced_retention"
    file_sync = 'if ! sync "$remote_staging"; then'
    publish = 'mv -f "$remote_staging" "$dump_path"'
    assert nfs_exception in source
    assert retention_call in source
    assert file_sync in source
    assert source.index(retention_call) < source.index(file_sync) < source.index(publish)


def test_df_is_synchronized_and_validated_before_any_unlink() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    helper = 'df_output="$(df --sync -Pk "$target")"'
    read_before = 'free_before="$(filesystem_free_bytes "$daily_dir")"'
    unlink = 'rm -f -- "$candidate"'
    read_after = 'free_after="$(filesystem_free_bytes "$daily_dir")"'
    assert helper in source
    assert read_before in source
    assert read_after in source
    assert source.index(read_before) < source.index(unlink) < source.index(read_after)
    assert "capacidade inválida do filesystem" in source


def test_weekly_promotion_is_byte_balanced_synced_and_atomic() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    admission = '"$weekly_dir" "$weekly_path" "$weekly_growth" "$weekly_incoming"'
    staging = 'weekly_staging="${weekly_path}.partial.$$"'
    copy = 'cp "$latest_daily" "$weekly_staging"'
    sync = 'sync "$weekly_staging"'
    compare = 'cmp -s "$latest_daily" "$weekly_staging"'
    size = 'weekly_remote_size="$(stat --printf=\'%s\' "$weekly_staging"'
    publish = 'mv -f "$weekly_staging" "$weekly_path"'
    for contract in (admission, staging, copy, sync, compare, size, publish):
        assert contract in source
    assert source.index(admission) < source.index(staging)
    assert source.index(staging) < source.index(copy) < source.index(sync)
    assert source.index(sync) < source.index(compare) < source.index(size)
    assert source.index(size) < source.index(publish)
    assert "weekly_source_identity_after" in source


def test_remote_partial_cleanup_is_verified_before_global_is_cleared() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    helper_start = source.index("remove_remote_staging()")
    helper_end = source.index("\n}\n", helper_start)
    helper = source[helper_start:helper_end]
    assert 'if ! rm -f -- "$staging_path"; then' in helper
    assert 'if [ -e "$staging_path" ] || [ -L "$staging_path" ]; then' in helper
    assert helper.index('rm -f -- "$staging_path"') < helper.index(
        'CURRENT_REMOTE_STAGING=""'
    )


def test_df_shortfall_remains_fail_closed_outside_nfs() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert (
        'Byte retention não comprovou liberação no filesystem: type=$filesystem_type'
        in source
    )
    assert 'return 2\n        ;;\n    esac' in source
