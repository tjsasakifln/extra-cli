#!/usr/bin/env python3
"""Load session-normalized DOE/DOM/Compras SC records into official_acts (052).

Idempotent batch loader for smoke/session artifacts. Not a crawler.

Usage:
  PYTHONPATH=. python3 -m scripts.ingestion.load_official_acts_session \\
    --sources ciga_dom,dados_abertos_sc,sc_compras --limit 0
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# scripts/ingestion may resolve to scripts/crawl/ingestion (compat path).
_HERE = Path(__file__).resolve().parent
for _candidate in (_HERE.parents[i] for i in range(1, 6)):
    if (_candidate / "db" / "migrations").is_dir() and (_candidate / "scripts").is_dir():
        _PROJECT_ROOT = _candidate
        break
else:
    _PROJECT_ROOT = _HERE.parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl.run_evidence import build_run_evidence, new_run_id  # noqa: E402
from scripts.schema.official_acts import OfficialActsStore, compute_record_hash  # noqa: E402

_logger = logging.getLogger(__name__)
BATCH = 200


def _load_dotenv() -> None:
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def _iter_jsonl(path: Path, limit: int = 0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                rows.append(rec)
            if limit and len(rows) >= limit:
                break
    return rows


def _conf_label(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        f = float(val)
        if f >= 0.8:
            return "high"
        if f >= 0.5:
            return "medium"
        return "low"
    s = str(val).lower()
    if s in {"high", "medium", "low"}:
        return s
    return str(val)[:32]


def map_ciga(rec: dict[str, Any], run_id: str) -> dict[str, Any]:
    external_id = str(rec.get("codigo") or rec.get("external_id") or "") or None
    title = rec.get("titulo") or rec.get("title") or ""
    text = rec.get("texto") or rec.get("raw_text") or ""
    pub = rec.get("data") or rec.get("publication_date")
    source = "ciga_dom"
    rh = rec.get("record_hash") or compute_record_hash(
        source, external_id=external_id, title=title, raw_text=text, publication_date=pub
    )
    return {
        "source": source,
        "external_id": external_id,
        "record_hash": rh,
        "title": title[:2000] if title else None,
        "raw_text": (text or "")[:50000] or None,
        "raw_json": rec,
        "orgao_nome": rec.get("orgao") or rec.get("entidade"),
        "municipio": rec.get("municipio"),
        "uf": "SC",
        "ente_federativo": "municipal",
        "publication_date": pub,
        "edition_date": pub,
        "event_date": pub,
        "date_semantics": "publication_from_source_data",
        "edition_number": rec.get("edicao"),
        "category": rec.get("act_category") or rec.get("category"),
        "category_source": "classifier",
        "category_confidence": _conf_label(rec.get("act_confidence") or rec.get("confidence")),
        "classification_evidence": str(rec.get("act_evidence") or rec.get("reason") or "")[:2000]
        or None,
        "process_number": rec.get("processo") or rec.get("process_number"),
        "source_url": rec.get("url") or rec.get("link"),
        "run_id": run_id,
        "status": "active",
        "proveniencia": {
            "portal": "dados.ciga.sc.gov.br",
            "resource_id": rec.get("resource_id"),
            "package_id": rec.get("package_id"),
            "source_file": rec.get("source_file"),
        },
        "metadata": {
            "entidade": rec.get("entidade"),
            "data_raw": rec.get("data_raw"),
        },
    }


def map_doe(rec: dict[str, Any], run_id: str) -> dict[str, Any]:
    external_id = str(rec.get("external_id") or rec.get("numero_publicacao") or "") or None
    title = rec.get("title") or rec.get("titulo") or ""
    text = rec.get("texto_ou_extrato") or title
    pub = rec.get("publication_date") or rec.get("data_publicacao") or rec.get("data_edicao")
    source = str(rec.get("source") or "dados_abertos_sc")
    rh = rec.get("record_hash") or compute_record_hash(
        source, external_id=external_id, title=title, raw_text=text, publication_date=pub
    )
    return {
        "source": source,
        "external_id": external_id,
        "record_hash": rh,
        "title": title[:2000] if title else None,
        "raw_text": (text or "")[:50000] or None,
        "raw_json": rec,
        "orgao_nome": rec.get("orgao_nome") or rec.get("orgao"),
        "municipio": None,
        "uf": "SC",
        "ente_federativo": "estadual",
        "publication_date": pub,
        "edition_date": rec.get("data_edicao"),
        "event_date": pub,
        "date_semantics": "edition_and_publication_from_csv",
        "edition_number": str(rec.get("edition_number") or rec.get("numero_edicao") or "") or None,
        "category": rec.get("act_category") or rec.get("source_category") or rec.get("categoria"),
        "category_source": "classifier",
        "category_confidence": _conf_label(rec.get("act_confidence")),
        "classification_evidence": str(rec.get("act_evidence") or "")[:2000] or None,
        "section": rec.get("categoria"),
        "source_url": rec.get("source_url") or rec.get("link_extrato") or rec.get("link_edicao"),
        "run_id": run_id,
        "status": "active",
        "proveniencia": {
            "portal": rec.get("portal") or "dados.sc.gov.br",
            "resource_id": rec.get("resource_id"),
            "resource_name": rec.get("resource_name"),
            "resource_url": rec.get("resource_url"),
            "record_hash": rec.get("record_hash"),
        },
        "metadata": {
            "unidade": rec.get("unidade"),
            "tipo_ato": rec.get("tipo_ato"),
            "assunto": rec.get("assunto"),
            "categoria_fonte": rec.get("categoria"),
        },
    }


def map_sc_compras(rec: dict[str, Any], run_id: str) -> dict[str, Any]:
    external_id = str(rec.get("id") or rec.get("pncp_id") or rec.get("codigo") or "") or None
    title = rec.get("objeto_compra") or rec.get("objeto") or rec.get("titulo") or ""
    pub = (
        rec.get("data_publicacao")
        or rec.get("dataPublicacao")
        or rec.get("data_abertura")
        or rec.get("dataAbertura")
    )
    source = "sc_compras"
    rh = rec.get("record_hash") or compute_record_hash(
        source, external_id=external_id, title=title, publication_date=pub
    )
    # status constraint expects active-like values; map portal situacao into metadata
    situacao = rec.get("situacao") or rec.get("status")
    return {
        "source": source,
        "external_id": external_id,
        "record_hash": rh,
        "title": (title or "")[:2000] or None,
        "raw_text": (title or "")[:50000] or None,
        "raw_json": rec,
        "orgao_nome": rec.get("orgao") or rec.get("orgao_nome") or rec.get("nomeOrgao"),
        "municipio": rec.get("municipio"),
        "uf": "SC",
        "ente_federativo": rec.get("esfera") or "estadual",
        "publication_date": pub,
        "event_date": pub,
        "date_semantics": "publication_from_portal_api",
        "category": "aviso_licitacao",
        "category_source": "source_native",
        "category_confidence": "medium",
        "process_number": rec.get("numero_processo") or rec.get("processo"),
        "edital_number": str(rec.get("numero") or rec.get("numero_edital") or "") or None,
        "source_url": rec.get("url_detalhe") or rec.get("url"),
        "status": "active",
        "run_id": run_id,
        "proveniencia": {"portal": "compras.sc.gov.br"},
        "metadata": {
            "situacao": situacao,
            "modalidade": rec.get("modalidade") or rec.get("modalidade_nome"),
            "valor_estimado": rec.get("valor_estimado"),
            "pncp_id": rec.get("pncp_id"),
        },
    }


def _latest_path(glob_pat: str) -> Path | None:
    """Prefer largest non-empty artifact, then newest mtime (avoids empty incremental)."""
    paths = [p for p in _PROJECT_ROOT.glob(glob_pat) if p.is_file()]
    if not paths:
        return None
    non_empty = [p for p in paths if p.stat().st_size > 0]
    pool = non_empty or paths
    pool.sort(key=lambda p: (p.stat().st_size, p.stat().st_mtime), reverse=True)
    return pool[0]


def load_source(
    store: OfficialActsStore,
    source: str,
    run_id: str,
    limit: int = 0,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source": source,
        "inserted": 0,
        "updated": 0,
        "errors": 0,
        "path": None,
        "records_read": 0,
    }
    records: list[dict[str, Any]] = []
    mapper = None

    if source == "ciga_dom":
        path = _latest_path("output/ciga_dom/*/publications.jsonl")
        mapper = map_ciga
    elif source == "dados_abertos_sc":
        path = _latest_path("data/normalized/dados_abertos_sc/**/*.jsonl")
        if path is None:
            # fallback: sample_records from smoke artifact
            art = _latest_path("output/dados_abertos_sc/smoke-*.json")
            if art:
                payload = json.loads(art.read_text(encoding="utf-8"))
                records = list(payload.get("sample_records") or [])
                result["path"] = str(art)
                mapper = map_doe
                path = art
            else:
                result["error"] = "no normalized DOE path"
                return result
        else:
            mapper = map_doe
    elif source == "doe_sc_public_ckan":
        path = _latest_path("output/doe_sc/*/publications.jsonl")
        mapper = map_doe
    elif source == "sc_compras":
        path = _latest_path("output/sc_compras/sc_compras-*/licitacoes.jsonl")
        mapper = map_sc_compras
    else:
        result["error"] = f"unknown source {source}"
        return result

    if path is None:
        result["error"] = "artifact not found"
        return result

    result["path"] = str(path)
    if path.suffix == ".jsonl":
        records = _iter_jsonl(path, limit=limit)
    elif not records:
        result["error"] = "no records"
        return result
    elif limit:
        records = records[:limit]

    result["records_read"] = len(records)
    if mapper is None:
        result["error"] = "mapper missing"
        return result
    mapped = [mapper(r, run_id) for r in records]

    # Register a synthetic resource row for provenance
    try:
        store.upsert_resource(
            source=source,
            resource_id=f"session-load:{run_id}:{source}",
            package_name=f"session-{source}",
            title=f"Session load {source}",
            resource_url=result["path"],
            format="JSONL",
            run_id=run_id,
            fetch_status="parsed",
            metadata={"records": len(mapped), "loader": "load_official_acts_session"},
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning("resource upsert failed for %s: %s", source, exc)

    for i in range(0, len(mapped), BATCH):
        chunk = mapped[i : i + BATCH]
        try:
            outcomes = store.upsert_acts(chunk)
            for o in outcomes:
                if o.get("action") == "inserted":
                    result["inserted"] += 1
                else:
                    result["updated"] += 1
        except Exception as exc:  # noqa: BLE001
            _logger.exception("batch upsert failed %s@%s: %s", source, i, exc)
            result["errors"] += len(chunk)
    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _load_dotenv()
    p = argparse.ArgumentParser(description="Load session acts into official_acts")
    p.add_argument(
        "--sources",
        default="ciga_dom,dados_abertos_sc,sc_compras",
        help="comma-separated sources",
    )
    p.add_argument("--limit", type=int, default=0, help="0 = all records per source")
    p.add_argument(
        "--output",
        default="output/session-evidence/official-acts-load.json",
        help="terminal evidence path",
    )
    args = p.parse_args(argv)

    run_id = new_run_id("official-acts-load")
    started = datetime.now(UTC)
    store = OfficialActsStore()
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    per_source: list[dict[str, Any]] = []
    for src in sources:
        _logger.info("Loading source=%s limit=%s", src, args.limit or "all")
        per_source.append(load_source(store, src, run_id, limit=args.limit))

    # Validation queries
    validation: dict[str, Any] = {}
    try:
        with store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT source, COUNT(*) AS n,
                           COUNT(DISTINCT municipio) FILTER (WHERE municipio IS NOT NULL) AS municipios,
                           COUNT(DISTINCT orgao_nome) FILTER (WHERE orgao_nome IS NOT NULL) AS orgaos
                    FROM public.official_acts
                    GROUP BY source
                    ORDER BY source
                    """
                )
                validation["by_source"] = [
                    {
                        "source": r[0],
                        "count": r[1],
                        "municipios": r[2],
                        "orgaos": r[3],
                    }
                    for r in cur.fetchall()
                ]
                cur.execute("SELECT COUNT(*) FROM public.official_acts")
                validation["total_acts"] = int(cur.fetchone()[0])
                cur.execute(
                    """
                    SELECT COUNT(*) FROM (
                        SELECT source, record_hash, COUNT(*) c
                        FROM public.official_acts
                        GROUP BY source, record_hash
                        HAVING COUNT(*) > 1
                    ) d
                    """
                )
                validation["duplicate_source_hash_groups"] = int(cur.fetchone()[0])
    except Exception as exc:  # noqa: BLE001
        validation["error"] = f"{type(exc).__name__}: {exc}"

    completed = datetime.now(UTC)
    status = (
        "ok"
        if per_source and not any(s.get("errors") or s.get("error") for s in per_source)
        else "partial"
    )
    counts_after = {
        "sources": {s["source"]: s.get("inserted", 0) + s.get("updated", 0) for s in per_source},
        "validation": validation,
    }
    evidence = build_run_evidence(
        run_id=run_id,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        command="python3 -m scripts.ingestion.load_official_acts_session",
        status=status,
        counts_after=counts_after,
        claims_allowed=[
            "session artifacts loaded into official_acts with idempotent upsert",
        ],
        claims_forbidden=[
            "full historical DOE/DOM coverage",
            "LOCAL_READY",
            "PROJECT_DONE",
        ],
    )
    artifact = {
        "run_id": run_id,
        "attestation": False,
        "live_fetch": False,
        "loader": "load_official_acts_session",
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "sources": per_source,
        "validation": validation,
        "status": status,
        "evidence": evidence,
    }
    out_path = _PROJECT_ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "output": str(out_path), "status": status, **validation}, ensure_ascii=False, indent=2, default=str))
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
