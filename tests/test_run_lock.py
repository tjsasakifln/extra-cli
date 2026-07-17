"""Tests for file-based crawl run lock."""

from __future__ import annotations

from pathlib import Path

from scripts.crawl.run_lock import RunLock


def test_acquire_and_release(tmp_path: Path):
    lock_path = tmp_path / "crawl.lock"
    lock = RunLock(path=lock_path, run_id="run-a")
    assert lock.acquire() is True
    assert lock_path.is_file()
    lock2 = RunLock(path=lock_path, run_id="run-b")
    assert lock2.acquire() is False
    lock.release()
    assert lock2.acquire() is True
    lock2.release()
