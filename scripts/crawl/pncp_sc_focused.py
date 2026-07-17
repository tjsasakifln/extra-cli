#!/usr/bin/env python3
"""PNCP focused collector for Santa Catarina only (no national 90d crawl).

Uses public PNCP consultation API filtered by UF=SC and modality codes.
Collects recent publication windows in small day chunks with checkpointing.

Usage:
  python3 -m scripts.crawl.pncp_sc_focused --days 14
  python3 -m scripts.crawl.pncp_sc_focused --days 7 --mode incremental
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl.run_evidence import build_run_evidence, new_run_id, sha256_file  # noqa: E402
from scripts.crawl.security import USER_AGENT  # noqa: E402

_logger = logging.getLogger(__name__)

BASE = "https://pncp.gov.br/api/consulta"
# Modalidades that return 200 with uf=SC (empirically: 6 = pregão eletrônico works;
# others may 400 depending on API version — we probe and skip failures).
MODALIDADES = (1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13)
PAGE_SIZE = 50
HTTP_TIMEOUT = 45
REQUEST_DELAY = 0.35

RAW_DIR = _PROJECT_ROOT / "data" / "raw" / "pncp_sc"
CHECKPOINT_DIR = _PROJECT_ROOT / "data" / "pncp_sc_checkpoints"
OUTPUT_DIR = _PROJECT_ROOT / "output" / "pncp_sc"


def _get_json(url: str) -> tuple[dict[str, Any] | None, str | None]:
    req = urllib.request.Request(  # noqa: S310
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def fetch_page(
    *,
    data_inicial: date,
    data_final: date,
    modalidade: int,
    pagina: int,
) -> tuple[list[dict], dict[str, Any], str | None]:
    params = {
        "dataInicial": data_inicial.strftime("%Y%m%d"),
        "dataFinal": data_final.strftime("%Y%m%d"),
        "codigoModalidadeContratacao": str(modalidade),
        "uf": "SC",
        "pagina": str(pagina),
        "tamanhoPagina": str(PAGE_SIZE),
    }
    url = f"{BASE}/v1/contratacoes/publicacao?{urllib.parse.urlencode(params)}"
    data, err = _get_json(url)
    if err or not data:
        return [], {"url": url, "ok": False, "error": err}, err
    items = data.get("data") or []
    if not isinstance(items, list):
        items = []
    meta = {
        "url": url,
        "ok": True,
        "totalRegistros": data.get("totalRegistros"),
        "totalPaginas": data.get("totalPaginas"),
        "numeroPagina": data.get("numeroPagina"),
        "empty": data.get("empty"),
        "items": len(items),
    }
    return items, meta, None


def load_checkpoint() -> dict[str, Any]:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    path = CHECKPOINT_DIR / "checkpoint.json"
    if not path.exists():
        return {"completed_windows": {}, "seen_pncp_ids": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"completed_windows": {}, "seen_pncp_ids": []}


def save_checkpoint(cp: dict[str, Any]) -> Path:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    path = CHECKPOINT_DIR / "checkpoint.json"
    # Cap seen ids
    seen = list(dict.fromkeys(cp.get("seen_pncp_ids") or []))[-50000:]
    cp["seen_pncp_ids"] = seen
    cp["updated_at"] = datetime.now(UTC).isoformat()
    path.write_text(json.dumps(cp, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def run(
    *,
    days: int = 14,
    mode: str = "full",
    chunk_days: int = 3,
    modalidades: tuple[int, ...] = MODALIDADES,
    delay: float = REQUEST_DELAY,
) -> dict[str, Any]:
    mode = mode.lower().strip()
    run_id = new_run_id(prefix="pncp-sc")
    started = datetime.now(UTC)
    end = date.today()
    start = end - timedelta(days=max(1, days))

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run_out = OUTPUT_DIR / run_id
    run_out.mkdir(parents=True, exist_ok=True)
    jsonl_path = run_out / "contratacoes.jsonl"
    raw_dir = RAW_DIR / run_id
    raw_dir.mkdir(parents=True, exist_ok=True)

    cp = load_checkpoint()
    seen: set[str] = set(cp.get("seen_pncp_ids") or [])
    errors: list[str] = []
    stats = {
        "windows": 0,
        "pages": 0,
        "fetched": 0,
        "new": 0,
        "skipped_dup": 0,
        "http_errors": 0,
        "by_modalidade": {},
    }

    # Build date windows
    windows: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        w_end = min(cur + timedelta(days=chunk_days - 1), end)
        windows.append((cur, w_end))
        cur = w_end + timedelta(days=1)

    written = 0
    with jsonl_path.open("w", encoding="utf-8") as out_fh:
        for w_start, w_end in windows:
            for mod in modalidades:
                wkey = f"{w_start.isoformat()}_{w_end.isoformat()}_m{mod}"
                if mode == "incremental" and cp.get("completed_windows", {}).get(wkey) == "done":
                    continue
                stats["windows"] += 1
                page = 1
                total_pages = 1
                mod_count = 0
                while page <= total_pages:
                    items, meta, err = fetch_page(
                        data_inicial=w_start,
                        data_final=w_end,
                        modalidade=mod,
                        pagina=page,
                    )
                    stats["pages"] += 1
                    # persist raw page
                    raw_path = raw_dir / f"{wkey}_p{page:04d}.json"
                    raw_path.write_text(
                        json.dumps({"meta": meta, "items": items}, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    if err:
                        stats["http_errors"] += 1
                        if "HTTP 400" in err and page == 1:
                            # modality unsupported for this window — skip quietly
                            errors.append(f"{wkey}:{err}")
                            break
                        errors.append(f"{wkey}:p{page}:{err}")
                        break
                    if page == 1:
                        total_pages = int(meta.get("totalPaginas") or 1) or 1
                        # safety cap
                        total_pages = min(total_pages, 200)
                    for it in items:
                        stats["fetched"] += 1
                        pncp_id = it.get("numeroControlePNCP") or ""
                        if not pncp_id:
                            # synthesize stable id
                            orgao = (it.get("orgaoEntidade") or {}).get("cnpj") or "x"
                            pncp_id = f"synth-{orgao}-{it.get('anoCompra')}-{it.get('sequencialCompra')}"
                            it["_synthetic_id"] = pncp_id
                        if pncp_id in seen and mode == "incremental":
                            stats["skipped_dup"] += 1
                            continue
                        if pncp_id in seen:
                            stats["skipped_dup"] += 1
                            # still write in full mode only once
                            continue
                        seen.add(pncp_id)
                        it["_run_id"] = run_id
                        it["_window"] = [w_start.isoformat(), w_end.isoformat()]
                        it["_modalidade_query"] = mod
                        out_fh.write(json.dumps(it, ensure_ascii=False) + "\n")
                        written += 1
                        stats["new"] += 1
                        mod_count += 1
                    page += 1
                    time.sleep(delay)
                stats["by_modalidade"][str(mod)] = stats["by_modalidade"].get(str(mod), 0) + mod_count
                cp.setdefault("completed_windows", {})[wkey] = "done"
                cp["seen_pncp_ids"] = list(seen)
                save_checkpoint(cp)

    completed = datetime.now(UTC)
    cp_path = save_checkpoint(cp)
    evidence = build_run_evidence(
        run_id=run_id,
        command="scripts.crawl.pncp_sc_focused",
        args={"days": days, "mode": mode, "chunk_days": chunk_days},
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        status="ok" if written or stats["fetched"] >= 0 else "empty",
        checkpoint_path=str(cp_path),
        output_path=str(jsonl_path),
        counts_after={"records_written": written, **stats},
        errors=errors[:50],
        source="pncp_sc",
        live_fetch=True,
    )
    evidence_path = run_out / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    artifact = {
        "run_id": run_id,
        "source": "pncp_sc",
        "mode": mode,
        "status": "ok",
        "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "records_written": written,
        "stats": stats,
        "errors_sample": errors[:20],
        "jsonl_path": str(jsonl_path),
        "evidence_path": str(evidence_path),
        "output_sha256": sha256_file(jsonl_path) if jsonl_path.exists() else None,
        "claims_allowed": [
            "sc_uf_filter_live_fetch",
            "records_written_this_run",
            "checkpoint_window_resume",
        ],
        "claims_forbidden": [
            "national_90d_complete",
            "full_pncp_historical_sc",
        ],
    }
    art_path = run_out / "artifact.json"
    art_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    _logger.info("PNCP SC done run_id=%s written=%s", run_id, written)
    return artifact


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="PNCP SC focused collector")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--mode", choices=["full", "incremental"], default="full")
    p.add_argument("--chunk-days", type=int, default=3)
    p.add_argument("--delay", type=float, default=REQUEST_DELAY)
    p.add_argument("--modalidades", default="6", help="Comma-separated modality codes (default 6)")
    args = p.parse_args(argv)
    mods = tuple(int(x) for x in args.modalidades.split(",") if x.strip())
    result = run(
        days=args.days,
        mode=args.mode,
        chunk_days=args.chunk_days,
        modalidades=mods or (6,),
        delay=args.delay,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
