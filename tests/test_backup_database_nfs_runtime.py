"""Runtime contracts for byte-balanced backup retention on laggy NFS statfs."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "backup-database.sh"

pytestmark = pytest.mark.skipif(
    os.name != "posix" or shutil.which("bash") is None,
    reason="requires GNU/Linux shell utilities",
)


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def _run_retention(
    tmp_path: Path,
    *,
    available_blocks: int,
    fail_candidate_rm: bool = False,
    fail_directory_sync: bool = False,
    filesystem_type: str = "nfs",
    fail_df: bool = False,
    malformed_df: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    backup_base = tmp_path / "backup"
    daily = backup_base / "daily"
    weekly = backup_base / "weekly"
    daily.mkdir(parents=True)
    weekly.mkdir()
    candidates = []
    for index in range(3):
        candidate = daily / f"pncp_datalake-2026-09-{10 + index}.dump.gz"
        candidate.write_bytes(bytes([index + 1]) * 4096)
        os.utime(candidate, (1_700_000_000 + index, 1_700_000_000 + index))
        candidates.append(candidate)

    incoming = tmp_path / "incoming.dump.gz"
    incoming.write_bytes(b"x" * 4096)
    log_path = tmp_path / "backup.log"
    lock_path = tmp_path / "backup.lock"
    script_copy = tmp_path / "backup-database.sh"
    source = SCRIPT.read_text(encoding="utf-8").replace(
        'LOCK_FILE="/tmp/backup-database.lock"', f'LOCK_FILE="{lock_path}"'
    )
    script_copy.write_text(source, encoding="utf-8", newline="\n")
    script_copy.chmod(0o755)

    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    real_stat = shutil.which("stat")
    real_rm = shutil.which("rm")
    assert real_stat and real_rm
    _write_executable(
        shim_dir / "stat",
        "#!/bin/sh\n"
        f'if [ "${{1:-}}" = "--file-system" ]; then echo {filesystem_type}; exit 0; fi\n'
        f'exec "{real_stat}" "$@"\n',
    )
    if fail_df:
        df_body = "#!/bin/sh\nexit 1\n"
    else:
        available = "not-a-number" if malformed_df else str(available_blocks)
        df_body = (
            "#!/bin/sh\n"
            "echo 'Filesystem 1024-blocks Used Available Capacity Mounted on'\n"
            f"echo 'laggy-nfs 1000000 100 {available} 1% /fake'\n"
        )
    _write_executable(shim_dir / "df", df_body)
    if fail_candidate_rm:
        _write_executable(
            shim_dir / "rm",
            "#!/bin/sh\n"
            "case \"$*\" in *'/daily/'*) exit 1 ;; esac\n"
            f'exec "{real_rm}" "$@"\n',
        )
    if fail_directory_sync:
        real_sync = shutil.which("sync")
        assert real_sync
        _write_executable(
            shim_dir / "sync",
            "#!/bin/sh\n"
            "case \"$*\" in *'-f '*'/daily') exit 1 ;; esac\n"
            f'exec "{real_sync}" "$@"\n',
        )
    for command in ("pg_dump", "gzip", "getent"):
        _write_executable(shim_dir / command, "#!/bin/sh\nexit 0\n")

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{shim_dir}{os.pathsep}{env['PATH']}",
            "LOCAL_DATALAKE_DSN": "postgresql://unused",
            "BACKUP_REMOTE_DIR": str(backup_base),
            "BACKUP_STORAGE_BOX_SSH": "",
            "BACKUP_NFS_EXPORT": "",
            "BACKUP_BYTE_BALANCED_RETENTION": "1",
            "BACKUP_BYTE_BALANCED_MINIMUM": "2",
            "BACKUP_BYTE_BALANCED_INCOMING_PATH": str(incoming),
            "BACKUP_RETENTION_DAILY": "7",
            "BACKUP_RETENTION_WEEKLY": "4",
            "BACKUP_LOG_FILE": str(log_path),
        }
    )
    result = subprocess.run(
        ["bash", str(script_copy), "--retention-only"],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    return result, candidates[0], log_path


def test_nfs_df_lag_is_accepted_with_verified_unlink_and_full_headroom(tmp_path: Path) -> None:
    result, oldest, log_path = _run_retention(tmp_path, available_blocks=900_000)
    log = log_path.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert not oldest.exists()
    assert "Byte retention aceitou contabilização NFS atrasada" in log
    assert "Byte retention satisfeita antes da cópia" in log


def test_nfs_df_lag_still_fails_when_absolute_headroom_is_too_small(tmp_path: Path) -> None:
    result, _oldest, log_path = _run_retention(tmp_path, available_blocks=1)
    log = log_path.read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "Byte retention não comprovou capacidade" in log
    assert "Byte retention satisfeita antes da cópia" not in log


def test_failed_unlink_is_not_counted_as_reclaimed_capacity(tmp_path: Path) -> None:
    result, oldest, log_path = _run_retention(
        tmp_path, available_blocks=900_000, fail_candidate_rm=True
    )
    log = log_path.read_text(encoding="utf-8")
    assert result.returncode != 0
    assert oldest.exists()
    assert "Byte retention falhou ao remover candidato" in log
    assert "Byte retention satisfeita antes da cópia" not in log


@pytest.mark.parametrize("filesystem_type", ["nfs", "nfs4"])
def test_nfs_does_not_require_unsupported_directory_fsync(
    tmp_path: Path, filesystem_type: str
) -> None:
    result, oldest, log_path = _run_retention(
        tmp_path,
        available_blocks=900_000,
        fail_directory_sync=True,
        filesystem_type=filesystem_type,
    )
    log = log_path.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert not oldest.exists()
    assert "não exige fsync de diretório incompatível com NFS" in log
    assert "Byte retention satisfeita antes da cópia" in log


@pytest.mark.parametrize("filesystem_type", ["ext2/ext3", "xfs", "unknown"])
def test_local_filesystem_directory_fsync_failure_remains_fail_closed(
    tmp_path: Path, filesystem_type: str
) -> None:
    result, _oldest, log_path = _run_retention(
        tmp_path,
        available_blocks=900_000,
        fail_directory_sync=True,
        filesystem_type=filesystem_type,
    )
    log = log_path.read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "não conseguiu sincronizar o filesystem" in log
    assert "Byte retention satisfeita antes da cópia" not in log


@pytest.mark.parametrize(
    ("fail_df", "malformed_df"),
    [(True, False), (False, True)],
)
def test_df_failure_before_unlink_preserves_oldest_candidate(
    tmp_path: Path, fail_df: bool, malformed_df: bool
) -> None:
    result, oldest, log_path = _run_retention(
        tmp_path,
        available_blocks=900_000,
        fail_df=fail_df,
        malformed_df=malformed_df,
    )
    log = log_path.read_text(encoding="utf-8")
    assert result.returncode != 0
    assert oldest.exists()
    assert "capacidade" in log
    assert "Byte retention removeu" not in log
