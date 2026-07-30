"""Resumable HTTP downloader for RFB open-data archives."""

from __future__ import annotations

import random
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from scripts.company_registry.integrity import sha256_file, validate_downloaded_file

UA = "extra-cli-company-registry/1.0 (+official-rfb-cnpj-mirror)"


class DownloadError(Exception):
    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


def _classify_http(code: int) -> tuple[bool, str]:
    if code == 404:
        return False, "not_found"
    if code == 403:
        return True, "forbidden"
    if code == 429:
        return True, "rate_limited"
    if 500 <= code <= 599:
        return True, "server_error"
    if code in {408, 425}:
        return True, "timeout_like"
    return False, f"http_{code}"


def download_file(
    url: str,
    dest: Path,
    *,
    expected_length: int | None = None,
    max_attempts: int = 5,
    timeout: float = 60.0,
    chunk_size: int = 1024 * 256,
    progress_cb: Callable[[int, int | None], None] | None = None,
) -> dict[str, Any]:
    """Download with resume (Range), temp file, atomic rename, integrity checks.

    Idempotent: if dest exists and validates, skip re-download.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    attempts: list[dict[str, Any]] = []
    started = time.monotonic()

    if dest.is_file():
        v = validate_downloaded_file(dest, expected_length=expected_length, expect_zip=True)
        if v["ok"]:
            return {
                "ok": True,
                "skipped": True,
                "path": str(dest),
                "sha256": v["sha256"],
                "size_bytes": v["size_bytes"],
                "attempts": 0,
                "latency_s": 0.0,
                "url": url,
            }

    for attempt in range(1, max_attempts + 1):
        attempt_meta: dict[str, Any] = {"attempt": attempt, "url": url}
        t0 = time.monotonic()
        try:
            existing = tmp.stat().st_size if tmp.is_file() else 0
            headers = {"User-Agent": UA, "Accept": "*/*"}
            if existing > 0:
                headers["Range"] = f"bytes={existing}-"
            req = urllib.request.Request(url, headers=headers)  # noqa: S310
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                status = getattr(resp, "status", 200) or 200
                content_type = resp.headers.get("Content-Type", "")
                cl_header = resp.headers.get("Content-Length")
                # If server ignored Range and sent 200, restart
                mode = "ab" if status == 206 and existing > 0 else "wb"
                if status == 200 and existing > 0:
                    existing = 0
                    mode = "wb"
                total: int | None = None
                if cl_header and cl_header.isdigit():
                    cl = int(cl_header)
                    total = cl + existing if status == 206 else cl
                if expected_length is not None:
                    total = expected_length
                written = existing
                with tmp.open(mode) as out:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        # Detect HTML early
                        if written == 0 and chunk.lstrip()[:15].lower().startswith(
                            (b"<!doctype", b"<html", b"<head")
                        ):
                            raise DownloadError(
                                "html_payload_instead_of_binary",
                                status=status,
                                retryable=False,
                            )
                        if "text/html" in content_type.lower() and written == 0:
                            raise DownloadError(
                                "unexpected_mime_html",
                                status=status,
                                retryable=False,
                            )
                        out.write(chunk)
                        written += len(chunk)
                        if progress_cb:
                            progress_cb(written, total)
            # Validate
            v = validate_downloaded_file(
                tmp, expected_length=expected_length, expect_zip=url.lower().endswith(".zip")
            )
            attempt_meta.update(
                {
                    "status": status,
                    "latency_s": round(time.monotonic() - t0, 3),
                    "size_bytes": written,
                    "validation": v,
                }
            )
            attempts.append(attempt_meta)
            if not v["ok"]:
                raise DownloadError(
                    "validation_failed:" + ",".join(v["errors"]),
                    status=status,
                    retryable="truncated" in v["errors"],
                )
            tmp.replace(dest)
            return {
                "ok": True,
                "skipped": False,
                "path": str(dest),
                "sha256": v["sha256"],
                "size_bytes": v["size_bytes"],
                "attempts": attempt,
                "attempt_log": attempts,
                "latency_s": round(time.monotonic() - started, 3),
                "url": url,
            }
        except DownloadError as exc:
            attempt_meta["error"] = str(exc)
            attempt_meta["retryable"] = exc.retryable
            attempt_meta["latency_s"] = round(time.monotonic() - t0, 3)
            attempts.append(attempt_meta)
            if not exc.retryable or attempt >= max_attempts:
                break
            time.sleep(_backoff(attempt))
        except urllib.error.HTTPError as exc:
            retryable, label = _classify_http(exc.code)
            attempt_meta.update(
                {
                    "error": f"HTTPError:{exc.code}:{label}",
                    "status": exc.code,
                    "retryable": retryable,
                    "latency_s": round(time.monotonic() - t0, 3),
                }
            )
            attempts.append(attempt_meta)
            if not retryable or attempt >= max_attempts:
                break
            time.sleep(_backoff(attempt))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            attempt_meta.update(
                {
                    "error": f"{type(exc).__name__}:{exc}",
                    "retryable": True,
                    "latency_s": round(time.monotonic() - t0, 3),
                }
            )
            attempts.append(attempt_meta)
            if attempt >= max_attempts:
                break
            time.sleep(_backoff(attempt))

    return {
        "ok": False,
        "skipped": False,
        "path": str(dest),
        "sha256": sha256_file(dest) if dest.is_file() else None,
        "size_bytes": dest.stat().st_size if dest.is_file() else 0,
        "attempts": len(attempts),
        "attempt_log": attempts,
        "latency_s": round(time.monotonic() - started, 3),
        "url": url,
        "errors": [a.get("error") for a in attempts if a.get("error")],
    }


def _backoff(attempt: int) -> float:
    return min(60.0, (2 ** (attempt - 1)) + random.uniform(0, 0.5))  # noqa: S311


def download_many(
    items: list[dict[str, Any]],
    *,
    max_workers: int = 2,
    max_attempts: int = 5,
    timeout: float = 60.0,
) -> list[dict[str, Any]]:
    """Download multiple files with limited concurrency.

    Each item: {url, dest, expected_length?}
    """
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        futs = {
            pool.submit(
                download_file,
                it["url"],
                Path(it["dest"]),
                expected_length=it.get("expected_length"),
                max_attempts=max_attempts,
                timeout=timeout,
            ): it
            for it in items
        }
        for fut in as_completed(futs):
            results.append(fut.result())
    return results
