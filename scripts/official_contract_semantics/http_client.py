"""Bounded official HTTP: timeout, limited retry, rate limit, cache, identifiable UA."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scripts.official_contract_semantics.constants import (
    DEFAULT_HTTP_RETRIES,
    DEFAULT_HTTP_TIMEOUT_S,
    DEFAULT_RATE_LIMIT_S,
    USER_AGENT,
)
from scripts.official_contract_semantics.identity import raw_record_hash_for
from scripts.official_contract_semantics.models import SourceUnavailability
from scripts.official_contract_semantics.serialize import sha256_text


@dataclass(frozen=True)
class FetchResult:
    url: str
    ok: bool
    status: int | None
    body: str | None
    sha256: str | None
    unavailability: SourceUnavailability | None
    from_cache: bool = False


def _sleep(seconds: float, sleeper: Callable[[float], None] | None = None) -> None:
    (sleeper or time.sleep)(seconds)


def cache_path(cache_dir: Path, url: str) -> Path:
    return cache_dir / f"{sha256_text(url)}.json"


def _load_cache(cache_dir: Path | None, url: str) -> FetchResult | None:
    if cache_dir is None:
        return None
    target = cache_path(cache_dir, url)
    if not target.exists():
        return None
    payload = json.loads(target.read_text(encoding="utf-8"))
    unavailable = payload.get("unavailability")
    return FetchResult(
        url=url,
        ok=bool(payload.get("ok")),
        status=payload.get("status"),
        body=payload.get("body"),
        sha256=payload.get("sha256"),
        unavailability=SourceUnavailability(**unavailable) if unavailable else None,
        from_cache=True,
    )


def _store_cache(cache_dir: Path | None, result: FetchResult) -> None:
    if cache_dir is None:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "url": result.url,
        "ok": result.ok,
        "status": result.status,
        "body": result.body,
        "sha256": result.sha256,
        "unavailability": result.unavailability.as_dict() if result.unavailability else None,
    }
    cache_path(cache_dir, result.url).write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def fetch_official(
    url: str,
    *,
    timeout_s: float = DEFAULT_HTTP_TIMEOUT_S,
    retries: int = DEFAULT_HTTP_RETRIES,
    rate_limit_s: float = DEFAULT_RATE_LIMIT_S,
    cache_dir: Path | None = None,
    opener: Callable[..., object] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> FetchResult:
    cached = _load_cache(cache_dir, url)
    if cached is not None:
        return cached
    scheme = url.split(":", 1)[0].lower()
    if scheme not in {"http", "https"}:
        return FetchResult(
            url=url,
            ok=False,
            status=None,
            body=None,
            sha256=None,
            unavailability=SourceUnavailability(
                official_url=url,
                error_kind="scheme_not_allowed",
                message=f"only_http_https_permitted:{scheme}",
            ),
        )
    last_error: SourceUnavailability | None = None
    open_url = opener or urllib.request.urlopen
    for attempt in range(retries + 1):
        if attempt:
            _sleep(rate_limit_s * (attempt + 1), sleeper)
        request = urllib.request.Request(  # noqa: S310 — scheme already restricted to http/https
            url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json"}
        )
        try:
            with open_url(request, timeout=timeout_s) as response:  # type: ignore[arg-type]
                status = int(getattr(response, "status", 200) or 200)
                raw = response.read()
            if status >= 400:
                last_error = SourceUnavailability(
                    official_url=url,
                    error_kind="http_status",
                    http_status=status,
                    message=f"http_{status}",
                )
                continue
            body = raw.decode("utf-8", errors="replace")
            result = FetchResult(
                url=url,
                ok=True,
                status=status,
                body=body,
                sha256=raw_record_hash_for(raw),
                unavailability=None,
            )
            _store_cache(cache_dir, result)
            _sleep(rate_limit_s, sleeper)
            return result
        except urllib.error.HTTPError as exc:
            last_error = SourceUnavailability(
                official_url=url,
                error_kind="http_status",
                http_status=int(exc.code),
                message=str(exc.reason),
            )
            if int(exc.code) < 500:
                break
        except urllib.error.URLError as exc:
            last_error = SourceUnavailability(
                official_url=url,
                error_kind="network",
                message=str(exc.reason if getattr(exc, "reason", None) else exc),
            )
        except TimeoutError as exc:
            last_error = SourceUnavailability(official_url=url, error_kind="timeout", message=str(exc))
        except OSError as exc:
            last_error = SourceUnavailability(official_url=url, error_kind="os_error", message=str(exc))
    failure = FetchResult(
        url=url,
        ok=False,
        status=last_error.http_status if last_error else None,
        body=None,
        sha256=None,
        unavailability=last_error,
    )
    _store_cache(cache_dir, failure)
    return failure
