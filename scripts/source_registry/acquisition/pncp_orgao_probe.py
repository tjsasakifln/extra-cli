"""PNCP órgão probe — recover entities via publication history / órgão API.

Strategy:
    1. Index full CNPJs from local PNCP session artifacts (prefix match on cnpj8).
    2. For each target entity, attempt to resolve a full 14-digit CNPJ.
    3. Optionally call PNCP ``GET /api/pncp/v1/orgaos/{cnpj}`` (network).
    4. Always write structured attempt evidence — never silent success.

CLI::

    python -m scripts.source_registry.cli acquire --strategy pncp_orgao_probe --limit 100
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.source_registry.builder import persist_registry
from scripts.source_registry.models import EntitySourceRecord

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PNCP_ORGAO_URL = "https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}"
DEFAULT_ARTIFACT_GLOBS = (
    "output/pncp_sc/**/*.jsonl",
    "output/**/contratacoes.jsonl",
    "data/raw/pncp*/**/*.jsonl",
)
PROBE_TIMEOUT_S = 8


def _digits(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\D", "", str(value))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def index_local_pncp_cnpjs(
    project_root: Path | None = None,
    *,
    max_files: int = 20,
    max_lines_per_file: int = 50_000,
) -> dict[str, dict[str, Any]]:
    """Build cnpj8 → {cnpj14, razao_social, sample_count} from local artifacts."""
    root = project_root or PROJECT_ROOT
    index: dict[str, dict[str, Any]] = {}
    files: list[Path] = []
    for pattern in DEFAULT_ARTIFACT_GLOBS:
        files.extend(sorted(root.glob(pattern)))
    # Prefer most recent files
    files = sorted({f.resolve() for f in files if f.is_file()}, key=lambda p: p.stat().st_mtime, reverse=True)
    files = files[:max_files]

    for path in files:
        try:
            with path.open(encoding="utf-8") as fh:
                for i, line in enumerate(fh):
                    if i >= max_lines_per_file:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    orgao = row.get("orgaoEntidade") or {}
                    if not isinstance(orgao, dict):
                        orgao = {}
                    cnpj14 = _digits(orgao.get("cnpj") or row.get("orgao_cnpj") or row.get("cnpj"))
                    if len(cnpj14) < 8:
                        continue
                    cnpj8 = cnpj14[:8]
                    razao = (
                        orgao.get("razaoSocial") or row.get("orgao_razao_social") or row.get("orgaoRazaoSocial") or ""
                    )
                    entry = index.get(cnpj8)
                    if entry is None:
                        index[cnpj8] = {
                            "cnpj14": cnpj14,
                            "razao_social": razao,
                            "sample_count": 1,
                            "sources": [str(path.relative_to(root))],
                        }
                    else:
                        entry["sample_count"] += 1
                        if len(cnpj14) == 14:
                            entry["cnpj14"] = cnpj14
                        if razao and not entry.get("razao_social"):
                            entry["razao_social"] = razao
        except OSError as exc:
            logger.warning("Skip artifact %s: %s", path, exc)
    logger.info("Indexed %s CNPJ8 prefixes from %s local PNCP files", len(index), len(files))
    return index


def probe_pncp_orgao_api(cnpj14: str, *, timeout: float = PROBE_TIMEOUT_S) -> dict[str, Any]:
    """Call PNCP órgão endpoint. Returns structured result (never raises)."""
    cnpj14 = _digits(cnpj14)
    result: dict[str, Any] = {
        "cnpj": cnpj14,
        "url": PNCP_ORGAO_URL.format(cnpj=cnpj14),
        "ok": False,
        "status_code": None,
        "error": None,
        "body_keys": None,
        "razao_social": None,
        "probed_at": _now_iso(),
    }
    if len(cnpj14) != 14:
        result["error"] = f"cnpj_not_14_digits:{len(cnpj14)}"
        return result
    try:
        req = Request(  # noqa: S310 — public PNCP API
            result["url"],
            headers={
                "User-Agent": "extra-consultoria-pncp-orgao-probe/1.0",
                "Accept": "application/json",
            },
        )
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — public PNCP API
            result["status_code"] = getattr(resp, "status", None) or resp.getcode()
            raw = resp.read(200_000)
            try:
                payload = json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                result["error"] = "invalid_json"
                return result
            result["ok"] = 200 <= int(result["status_code"]) < 300
            if isinstance(payload, dict):
                result["body_keys"] = sorted(payload.keys())[:30]
                result["razao_social"] = (
                    payload.get("razaoSocial")
                    or payload.get("nome")
                    or (payload.get("orgaoEntidade") or {}).get("razaoSocial")
                )
            return result
    except HTTPError as exc:
        result["status_code"] = exc.code
        result["error"] = f"http_{exc.code}"
        return result
    except (URLError, TimeoutError, OSError) as exc:
        result["error"] = str(exc)
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"unexpected:{exc!s}"
        return result


def _select_targets(
    records: list[EntitySourceRecord],
    *,
    limit: int,
    only_uncovered: bool = True,
    local_index: dict[str, dict[str, Any]] | None = None,
) -> list[EntitySourceRecord]:
    pool = records
    if only_uncovered:
        pool = [
            r for r in records if r.access_status in {"unknown", "source_not_identified", "mapped", "failed", "blocked"}
        ]
        # Prefer: local PNCP hit available → unknown → source_not_identified → rest
        rank = {
            "unknown": 0,
            "source_not_identified": 1,
            "failed": 2,
            "blocked": 3,
            "mapped": 4,
        }
        idx = local_index or {}

        def _sort_key(r: EntitySourceRecord) -> tuple:
            cnpj8 = (r.cnpj or "")[:8]
            has_local = 0 if cnpj8 and cnpj8 in idx else 1
            return (
                has_local,
                rank.get(r.access_status, 9),
                r.priority,
                r.razao_social or "",
            )

        pool = sorted(pool, key=_sort_key)
    else:
        pool = sorted(records, key=lambda r: (r.priority, r.razao_social or ""))
    return pool[: max(0, limit)]


def probe_pncp_orgaos(
    records: list[EntitySourceRecord],
    *,
    limit: int = 100,
    dry_run: bool = True,
    use_network: bool | None = None,
    persist: bool = True,
    local_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Probe PNCP for entities and update registry records in-place.

    Args:
        records: Full registry list (mutated in place for matched entities).
        limit: Max entities to attempt.
        dry_run: When True, do not call network API (local artifact match only).
        use_network: Override; default is ``not dry_run``.
        persist: Rewrite registry JSONL after updates.
        local_index: Prebuilt cnpj8 index (tests inject this).

    Returns:
        Summary of attempts/hits/failures.
    """
    if use_network is None:
        use_network = not dry_run

    index = local_index if local_index is not None else index_local_pncp_cnpjs()
    targets = _select_targets(records, limit=limit, local_index=index)
    by_id = {r.canonical_id: r for r in records}

    attempts: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "strategy": "pncp_orgao_probe",
        "attempted": 0,
        "local_hits": 0,
        "api_hits": 0,
        "api_misses": 0,
        "api_errors": 0,
        "no_cnpj": 0,
        "updated": 0,
        "dry_run": dry_run,
        "use_network": use_network,
        "local_index_size": len(index),
        "attempts": attempts,
    }

    for rec in targets:
        stats["attempted"] += 1
        attempt: dict[str, Any] = {
            "canonical_id": rec.canonical_id,
            "cnpj8": rec.cnpj[:8] if rec.cnpj else None,
            "attempted_at": _now_iso(),
            "local_match": None,
            "api": None,
            "outcome": "no_match",
        }

        cnpj8 = (rec.cnpj or "")[:8]
        if not cnpj8:
            stats["no_cnpj"] += 1
            attempt["outcome"] = "no_cnpj"
            evidence = {
                "type": "pncp_orgao_probe",
                "outcome": "no_cnpj",
                "attempted_at": attempt["attempted_at"],
            }
            rec.evidences = list(rec.evidences or []) + [evidence]
            rec.last_attempt_at = attempt["attempted_at"]
            attempts.append(attempt)
            continue

        local = index.get(cnpj8)
        cnpj14 = None
        if local:
            stats["local_hits"] += 1
            cnpj14 = local.get("cnpj14")
            attempt["local_match"] = {
                "cnpj14": cnpj14,
                "razao_social": local.get("razao_social"),
                "sample_count": local.get("sample_count"),
                "sources": local.get("sources"),
            }
            # Local evidence of PNCP presence → at least mapped/accessible
            rec.external_ids = dict(rec.external_ids or {})
            if cnpj14:
                rec.external_ids["cnpj14"] = cnpj14
            rec.external_ids["pncp_local_sample_count"] = local.get("sample_count")
            if "pncp" not in rec.plataformas:
                rec.plataformas = list(rec.plataformas) + ["pncp"]
            rec.integration_type = "api_json"
            rec.access_status = "accessible" if (local.get("sample_count") or 0) >= 1 else "mapped"
            rec.collection_strategy = "pncp_monitor_by_cnpj"
            rec.current_blocker = "none"
            rec.next_action = "schedule_pncp_incremental_for_orgao"
            rec.mapping_confidence = min(1.0, max(rec.mapping_confidence, 0.75))
            rec.last_success_at = attempt["attempted_at"]
            attempt["outcome"] = "local_hit"

        api_result = None
        if use_network and cnpj14 and len(_digits(cnpj14)) == 14:
            api_result = probe_pncp_orgao_api(cnpj14)
            attempt["api"] = {
                "ok": api_result.get("ok"),
                "status_code": api_result.get("status_code"),
                "error": api_result.get("error"),
                "razao_social": api_result.get("razao_social"),
            }
            if api_result.get("ok"):
                stats["api_hits"] += 1
                rec.access_status = "accessible"
                rec.last_success_at = attempt["attempted_at"]
                rec.mapping_confidence = min(1.0, max(rec.mapping_confidence, 0.9))
                if api_result.get("razao_social") and not rec.nome_fantasia:
                    rec.nome_fantasia = api_result["razao_social"]
                attempt["outcome"] = "api_hit"
            else:
                if api_result.get("error") and "http" not in str(api_result.get("error")):
                    stats["api_errors"] += 1
                else:
                    stats["api_misses"] += 1
                # Keep local_hit status if we had one; else mark failed attempt
                if attempt["outcome"] != "local_hit":
                    attempt["outcome"] = "api_miss"
                    rec.access_status = rec.access_status if rec.access_status != "unknown" else "failed"
                    rec.current_blocker = rec.current_blocker or "no_api"
                    rec.next_action = "retry_pncp_orgao_probe_with_full_cnpj"
        elif use_network and not cnpj14:
            # No full CNPJ — cannot call API; record structured miss
            attempt["api"] = {
                "ok": False,
                "error": "full_cnpj_unavailable_cannot_call_api",
                "skipped": True,
            }
            stats["api_misses"] += 1
            if attempt["outcome"] == "no_match":
                attempt["outcome"] = "no_full_cnpj"
                rec.next_action = "resolve_full_cnpj_then_pncp_probe"
                rec.current_blocker = rec.current_blocker or "fragmented"

        evidence = {
            "type": "pncp_orgao_probe",
            "outcome": attempt["outcome"],
            "attempted_at": attempt["attempted_at"],
            "local_match": attempt.get("local_match"),
            "api": attempt.get("api"),
            "dry_run": dry_run,
            "use_network": use_network,
        }
        rec.evidences = list(rec.evidences or []) + [evidence]
        rec.last_attempt_at = attempt["attempted_at"]
        if attempt["outcome"] in {"local_hit", "api_hit"}:
            stats["updated"] += 1
            # ensure by_id points to same object (already does — in-place)
            _ = by_id.get(rec.canonical_id)
        attempts.append(attempt)

    summary = {k: v for k, v in stats.items() if k != "attempts"}
    summary["sample_attempts"] = attempts[:10]
    summary["total_attempts_logged"] = len(attempts)

    if persist:
        persist_registry(records)
        summary["persisted"] = True
    else:
        summary["persisted"] = False

    return summary
