"""Self-contained pSEO public export pipeline (durable untracked module)."""
from __future__ import annotations

import re

import argparse
import json
import os
import sys
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable

from scripts.pseo.aggregate import (
    attach_problem_evidence,
    build_agencies,
    build_competition,
    build_markets,
    build_problem_service_bridges,
)
from scripts.pseo.archetypes import (
    ARCHETYPE_DEFS,
    ClassifiedContract,
    build_public_archetypes,
    load_icp_signature_from_top20_artifact,
)
from scripts.pseo.classifiers import classify_objeto
from scripts.pseo.comparison import build_comparable_prices
from scripts.pseo.normalization import cnpj8, cnpj14, iso_date, money_float
from scripts.pseo.opportunities import filter_open_bids, radar_freshness
from scripts.pseo.provenance import (
    EXPORT_VERSION,
    build_manifest,
    compute_dataset_hash,
    sha256_text,
)
from scripts.pseo.sanitize import assert_public, deep_strip_forbidden
from scripts.pseo.schemas import PUBLIC_SCHEMA

# Canonical entry (plan / docs); cli_export is a durable alias with the same main().
EXPORT_ENTRYPOINT = "python -m scripts.pseo.export_web_cfg"
DEFAULT_TOP20 = (
    "artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/"
    "post-merge/evidence-slim/top20-slim.json"
)
TABLES = ["pncp_supplier_contracts", "pncp_raw_bids", "sc_public_entities"]
QUERY_VERSIONS = {
    "pncp_supplier_contracts": "v2_public_fields_valor_gt_0",
    "pncp_raw_bids": "v2_with_encerramento_and_status",
    "sc_public_entities": "v1_count_only",
}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def classify_rows(rows: Iterable[dict[str, Any]]) -> list[ClassifiedContract]:
    out: list[ClassifiedContract] = []
    for r in rows:
        obj = r.get("objeto_contrato") or r.get("objeto") or ""
        clf = classify_objeto(obj)
        if clf.label != "aec_confirmed" or not clf.archetypes:
            continue
        valor = money_float(r.get("valor_total") if r.get("valor_total") is not None else r.get("valor"))
        if not valor or valor <= 0:
            continue
        out.append(
            ClassifiedContract(
                contrato_id=r.get("contrato_id"),
                orgao_cnpj=cnpj8(r.get("orgao_cnpj")),
                orgao_nome=r.get("orgao_nome"),
                fornecedor_cnpj=cnpj14(r.get("fornecedor_cnpj")),
                fornecedor_nome=r.get("fornecedor_nome"),
                objeto=str(obj),
                valor=float(valor),
                data_inicio=iso_date(r.get("data_inicio")),
                data_fim=iso_date(r.get("data_fim")),
                data_publicacao=iso_date(r.get("data_publicacao")),
                uf=(r.get("uf") or None),
                municipio=r.get("municipio"),
                source=str(r.get("source") or "pncp"),
                archetypes=list(clf.archetypes),
            )
        )
    return out


def classify_bids(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        obj = r.get("objeto_compra") or r.get("objeto") or ""
        clf = classify_objeto(obj)
        if clf.label != "aec_confirmed" or not clf.archetypes:
            continue
        item = dict(r)
        item["objeto"] = obj
        item["archetypes"] = list(clf.archetypes)
        item["classification_label"] = clf.label
        item["classification_confidence"] = clf.confidence
        item["data_encerramento"] = iso_date(
            r.get("data_encerramento")
            or r.get("data_encerramento_proposta")
            or r.get("data_fim_proposta")
        )
        if item.get("valor_total_estimado") is not None and item.get("valor_estimado") is None:
            item["valor_estimado"] = money_float(item["valor_total_estimado"])
        out.append(item)
    return out


def classify_all_rows_stats(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        obj = r.get("objeto_contrato") or r.get("objeto") or ""
        label = classify_objeto(obj).label
        counts[label] = counts.get(label, 0) + 1
    return counts


def _uf_label(uf: str) -> str:
    names = {
        "AC": "Acre", "AL": "Alagoas", "AP": "Amapa", "AM": "Amazonas",
        "BA": "Bahia", "CE": "Ceara", "DF": "Distrito Federal", "ES": "Espirito Santo",
        "GO": "Goias", "MA": "Maranhao", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
        "MG": "Minas Gerais", "PA": "Para", "PB": "Paraiba", "PR": "Parana",
        "PE": "Pernambuco", "PI": "Piaui", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
        "RS": "Rio Grande do Sul", "RO": "Rondonia", "RR": "Roraima", "SC": "Santa Catarina",
        "SP": "Sao Paulo", "SE": "Sergipe", "TO": "Tocantins",
    }
    return names.get(uf, uf)


def build_opportunities_v2(
    open_bids: list[dict[str, Any]],
    markets: list[dict[str, Any]],
    min_open: int = 3,
    *,
    as_of: str | None = None,
    closed_bids: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    as_of_d = date.fromisoformat(as_of) if as_of else date.today()
    as_of_s = as_of_d.isoformat()
    truly_open, not_open, _ = filter_open_bids(open_bids, as_of=as_of_d)
    if closed_bids:
        _, more_closed, _ = filter_open_bids(closed_bids, as_of=as_of_d)
        not_open = not_open + more_closed

    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for b in truly_open:
        uf = b.get("uf")
        if not uf:
            continue
        for a in b.get("archetypes") or []:
            buckets[(a, uf)].append(b)

    hist_buckets: dict[tuple[str, str], int] = defaultdict(int)
    closed_recent: dict[tuple[str, str], int] = defaultdict(int)
    suspended: dict[tuple[str, str], int] = defaultdict(int)
    for b in not_open:
        uf = b.get("uf")
        if not uf:
            continue
        decision = b.get("open_decision") or {}
        for a in b.get("archetypes") or []:
            hist_buckets[(a, uf)] += 1
            bucket = decision.get("status_bucket") or ""
            if bucket == "suspensa":
                suspended[(a, uf)] += 1
            elif bucket in {"encerrada", "historico"}:
                closed_recent[(a, uf)] += 1

    market_slugs = {m["slug"] for m in markets}
    out: list[dict[str, Any]] = []
    # Wall-clock now — never pass as_of as now (would force age_hours=0)
    fresh = radar_freshness(as_of_s, now=date.today())
    for (arch, uf), items in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        if len(items) < min_open:
            continue
        label = ARCHETYPE_DEFS.get(arch, {}).get("label", arch)
        slug = f"{arch}-{uf.lower()}"
        related = slug if slug in market_slugs else None
        pub_items = []
        for b in items[:25]:
            decision = b.get("open_decision") or {}
            link = b.get("link_pncp") or b.get("link_oficial")
            if link and not str(link).startswith("http"):
                link = None
            # Prefer real portal deep-link when present; else PNCP contract deep-link from ID
            if not link:
                link = pncp_consulta_url(b.get("pncp_id") or b.get("contrato_id"), b.get("source"))
            pub_items.append(
                {
                    "pncp_id": b.get("pncp_id"),
                    "objeto": (b.get("objeto") or "")[:220],
                    "valor_estimado": b.get("valor_estimado"),
                    "modalidade": b.get("modalidade") or b.get("modalidade_nome"),
                    "uf": b.get("uf"),
                    "municipio": b.get("municipio"),
                    "orgao_nome": b.get("orgao_nome"),
                    "data_encerramento": decision.get("data_encerramento") or b.get("data_encerramento"),
                    "link_pncp": link,
                    "link_oficial": link,
                    "source": b.get("source") or "pncp",
                    "status_bucket": decision.get("status_bucket") or "aberta",
                    "status_raw": decision.get("status_raw"),
                    "uncertainty": bool(decision.get("uncertainty")),
                    "verified_at": as_of_s,
                }
            )
        out.append(
            {
                "id": f"radar-{slug}",
                "slug": slug,
                "segment": label,
                "region": uf,
                "region_label": _uf_label(uf),
                "as_of": as_of_s,
                "verified_at": as_of_s,
                "timezone": "America/Sao_Paulo",
                "open_count": len(items),
                "closed_recent_count": closed_recent.get((arch, uf), 0),
                "suspended_count": suspended.get((arch, uf), 0),
                "items": pub_items,
                "historical_count": hist_buckets.get((arch, uf), 0),
                "status_breakdown": {
                    "abertas": len(items),
                    "encerradas_recentes": closed_recent.get((arch, uf), 0),
                    "suspensas": suspended.get((arch, uf), 0),
                    "historico": hist_buckets.get((arch, uf), 0),
                },
                "freshness": fresh,
                "sources": sorted({b.get("source") or "pncp" for b in items}),
                "limitations": [
                    "Somente oportunidades com data_encerramento >= as_of e status compativel.",
                    "Nao e monitoramento em tempo real; verifique no portal oficial.",
                    "Pagina evergreen: nao indexa um edital por URL.",
                    "historical_count NAO entra em open_count.",
                ],
                "related_market_slug": related,
            }
        )
    return out



def pncp_consulta_url(contrato_id: str | None, source: str | None = None) -> str | None:
    """Build a specific public PNCP contract deep-link when ID shape is known.

    Preferred format (PNCP app):
      https://pncp.gov.br/app/contratos/{cnpj14}/{ano}/{sequencial}

    Returns None when the ID is empty/opaque — never invent URLs.
    """
    if not contrato_id:
        return None
    cid = str(contrato_id).strip()
    if cid.startswith("http://") or cid.startswith("https://"):
        return cid
    # e.g. 88830609000139-2-002361/2026
    m = re.match(r"^(\d{14})-(\d+)-(\d+)/(\d{4})$", cid)
    if m:
        cnpj, _tipo, seq, ano = m.group(1), m.group(2), m.group(3), m.group(4)
        seq_int = str(int(seq)) if seq.isdigit() else (seq.lstrip("0") or "0")
        return f"https://pncp.gov.br/app/contratos/{cnpj}/{ano}/{seq_int}"
    return None


def load_from_db(dsn: str):
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as e:
        raise SystemExit(f"psycopg2 required for DB export: {e}") from e
    conn = psycopg2.connect(dsn, connect_timeout=15)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    counts: dict[str, int] = {}
    cur.execute(
        """
        SELECT contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
               objeto_contrato, valor_total, data_inicio, data_fim, data_publicacao,
               uf, municipio, source
        FROM pncp_supplier_contracts
        WHERE valor_total IS NOT NULL AND valor_total > 0
        """
    )
    contracts = [dict(r) for r in cur.fetchall()]
    counts["pncp_supplier_contracts"] = len(contracts)
    cur.execute(
        """
        SELECT pncp_id, objeto_compra, valor_total_estimado, modalidade_nome, uf, municipio,
               orgao_razao_social AS orgao_nome, orgao_cnpj,
               data_publicacao, data_abertura, data_encerramento, link_pncp, source, is_active
        FROM pncp_raw_bids
        WHERE is_active IS DISTINCT FROM false
        """
    )
    bids = [dict(r) for r in cur.fetchall()]
    counts["pncp_raw_bids"] = len(bids)
    cur.execute("SELECT COUNT(*) AS n FROM sc_public_entities")
    counts["sc_public_entities"] = int(cur.fetchone()["n"])
    conn.close()
    return contracts, bids, counts


def load_from_fixture(path: Path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    contracts = raw.get("contracts") or []
    bids = raw.get("bids") or []
    counts = {
        "pncp_supplier_contracts": len(contracts),
        "pncp_raw_bids": len(bids),
        "sc_public_entities": int(raw.get("entity_count") or 0),
        "fixture": 1,
    }
    return contracts, bids, counts


def build_export(
    contracts: list[dict[str, Any]],
    bids: list[dict[str, Any]],
    counts: dict[str, int],
    *,
    top20_path: str | None,
    source_run_id: str | None = None,
    as_of: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    as_of_s = as_of or date.today().isoformat()
    as_of_d = date.fromisoformat(as_of_s)

    classification_counts = classify_all_rows_stats(contracts)
    classified = classify_rows(contracts)
    aec_bids = classify_bids(bids)
    open_bids, closed_bids, opp_status_counts = filter_open_bids(aec_bids, as_of=as_of_d)

    markets = build_markets(classified, open_bids)
    agencies = build_agencies(classified, open_bids)
    prices_raw = build_comparable_prices(classified, min_obs=12)
    for pr in prices_raw:
        uf = pr.get("region")
        if uf and len(str(uf)) == 2:
            pr["region_label"] = _uf_label(str(uf))
        arch = pr.get("object_pattern")
        if arch and uf and len(str(uf)) == 2:
            pr.setdefault("mesh_slug", f"{arch}-{str(uf).lower()}")
        # Attach specific official links to examples when possible (never invent)
        for ex in pr.get("public_examples") or []:
            if not ex.get("link_oficial"):
                link = pncp_consulta_url(ex.get("contrato_id"), ex.get("source"))
                if link:
                    ex["link_oficial"] = link
                    ex.setdefault("portal_origem", "pncp")
    competition = build_competition(classified)
    opportunities = build_opportunities_v2(
        open_bids, markets, as_of=as_of_s, closed_bids=closed_bids
    )
    problems = attach_problem_evidence(build_problem_service_bridges(), markets, prices_raw)
    archetypes = build_public_archetypes(classified)

    payload = {
        "archetypes": archetypes,
        "markets": markets,
        "agencies": agencies,
        "prices": prices_raw,
        "competition": competition,
        "opportunities": opportunities,
        "problem_service": problems,
    }
    payload = deep_strip_forbidden(payload)
    assert_public(payload, "export_payload")

    icp = load_icp_signature_from_top20_artifact(top20_path)
    icp = {
        "available": icp.get("available"),
        "n_accounts_internal": icp.get("n_accounts_internal"),
        "activity_class_histogram": icp.get("activity_class_histogram"),
        "sector_fit_histogram": icp.get("sector_fit_histogram"),
        "public_signal_frequency": icp.get("public_signal_frequency"),
        "note": icp.get("note"),
    }

    files_body = {
        "archetypes": payload["archetypes"],
        "markets": payload["markets"],
        "agencies": payload["agencies"],
        "prices": payload["prices"],
        "competition": payload["competition"],
        "opportunities": payload["opportunities"],
        "problem_service": payload["problem_service"],
        "icp_methodology": {
            "schema_version": "1.1.0",
            "methodology": (
                "Top 20 comercial so calibra classes de atividade. "
                "Classificador multi-camada: so aec_confirmed alimenta indicadores indexaveis."
            ),
            "internal_signature_aggregates": icp,
            "classifier": {
                "labels": [
                    "aec_confirmed",
                    "aec_probable",
                    "non_aec",
                    "ambiguous",
                    "insufficient_context",
                ],
                "indexable_class": "aec_confirmed",
            },
        },
    }
    assert_public(files_body, "files_body")
    dataset_hash = compute_dataset_hash(files_body)
    generated_at = _now()
    run_id = source_run_id or f"pseo-{generated_at.replace(':','').replace('-','')}-{uuid.uuid4().hex[:8]}"

    dates = [c.data_publicacao for c in classified if c.data_publicacao]
    bid_dates = []
    for b in aec_bids:
        for k in ("data_publicacao", "data_encerramento", "data_abertura"):
            if b.get(k):
                bid_dates.append(str(b[k])[:10])
    all_dates = [str(d)[:10] for d in dates + bid_dates if d]
    max_data = max(all_dates) if all_dates else None
    min_data = min(all_dates) if all_dates else None
    contract_dates = [str(d)[:10] for d in dates if d]

    counts_full = {
        **counts,
        "classified_aec_contracts": len(classified),
        "classified_aec_bids": len(aec_bids),
        "open_bids": len(open_bids),
        "closed_bids": len(closed_bids),
        "markets": len(payload["markets"]),
        "agencies": len(payload["agencies"]),
        "prices": len(payload["prices"]),
        "competition": len(payload["competition"]),
        "opportunities": len(payload["opportunities"]),
        "archetypes": len(payload["archetypes"]),
        "problem_service": len(payload["problem_service"]),
        "raw_contracts": counts.get("pncp_supplier_contracts", 0),
        "after_classification_aec_confirmed": len(classified),
        "after_open_filter": len(open_bids),
    }

    manifest = build_manifest(
        files_body=files_body,
        counts=counts_full,
        classification_counts={
            **classification_counts,
            **{f"bid_status_{k}": v for k, v in opp_status_counts.items()},
        },
        freshness={
            "data_period_start": min_data,
            "data_period_end": max_data,
            "data_as_of": as_of_s,
            "max_age_days_policy": 180,
            "generated_at": generated_at,
            "by_dataset": {
                "contracts": {
                    "min_date": min(contract_dates) if contract_dates else None,
                    "max_date": max(contract_dates) if contract_dates else None,
                    "n": len(classified),
                    "policy_warning_days": 30,
                    "policy_fail_days": 90,
                },
                "bids_radar": {
                    "n_open": len(open_bids),
                    "n_classified": len(aec_bids),
                    "policy_warning_hours": 24,
                    "policy_fail_hours": 72,
                    "as_of": as_of_s,
                },
            },
            "note": "Record ages from data_publicacao/data_encerramento, not only generated_at.",
        },
        sources=[{"table": t, "role": "read_only_aggregate"} for t in TABLES],
        denominators={
            "contracts_total_loaded": counts.get("pncp_supplier_contracts", 0),
            "bids_total_loaded": counts.get("pncp_raw_bids", 0),
            "aec_confirmed_contracts": len(classified),
            "aec_confirmed_bids": len(aec_bids),
            "open_bids_after_status_filter": len(open_bids),
            "classified_share_note": "Only multi-layer aec_confirmed objects enter public aggregates.",
        },
        limitations=[
            "Export is aggregated and sanitized; no commercial pipeline fields.",
            "Datalake coverage is incomplete relative to the national universe.",
            "Do not interpret medians as unit prices.",
            "Only aec_confirmed records feed market/price/competition aggregates.",
            "Open opportunities require data_encerramento >= data_as_of and compatible status.",
            "Freshness uses record dates, not only generated_at.",
        ],
        generated_at=generated_at,
        data_as_of=as_of_s,
        source_run_id=run_id,
        repo_root=repo_root,
        query_versions=QUERY_VERSIONS,
        horizon={"period_start": min_data, "period_end": max_data},
    )
    manifest["export_entrypoint"] = EXPORT_ENTRYPOINT
    manifest["exporter_entrypoint"] = EXPORT_ENTRYPOINT
    manifest["schema_version"] = "1.1.0"
    manifest["dataset_hash"] = dataset_hash
    return {"manifest": manifest, "files": files_body, "dataset_hash": dataset_hash}


def write_export(out_dir: Path, bundle: dict[str, Any]) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = bundle["files"]
    checksums: dict[str, str] = {}
    written: dict[str, str] = {}
    mapping = {
        "archetypes.json": files["archetypes"],
        "markets.json": files["markets"],
        "agencies.json": files["agencies"],
        "prices.json": files["prices"],
        "competition.json": files["competition"],
        "opportunities.json": files["opportunities"],
        "problem_service.json": files["problem_service"],
        "icp_methodology.json": files["icp_methodology"],
    }
    for name, data in mapping.items():
        text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
        path = out_dir / name
        path.write_text(text, encoding="utf-8")
        checksums[name] = sha256_text(text)
        written[name] = str(path)
    schema = dict(PUBLIC_SCHEMA)
    schema["schema_version"] = "1.1.0"
    schema["export_entrypoint"] = EXPORT_ENTRYPOINT
    schema_text = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (out_dir / "schema.json").write_text(schema_text, encoding="utf-8")
    checksums["schema.json"] = sha256_text(schema_text)
    written["schema.json"] = str(out_dir / "schema.json")
    manifest = dict(bundle["manifest"])
    manifest["checksums"] = checksums
    m_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    (out_dir / "manifest.json").write_text(m_text, encoding="utf-8")
    written["manifest.json"] = str(out_dir / "manifest.json")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export sanitized pSEO data for web-cfg")
    parser.add_argument("--out", type=Path, default=Path("artifacts/pseo/web_cfg_export"))
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--top20", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[2]
    top20 = args.top20
    if top20 is None:
        candidate = root / DEFAULT_TOP20
        top20 = str(candidate) if candidate.exists() else None

    if args.fixture:
        contracts, bids, counts = load_from_fixture(args.fixture)
    else:
        dsn = args.dsn or os.environ.get("DATABASE_URL") or os.environ.get("LOCAL_DATALAKE_DSN")
        if not dsn:
            print("ERROR: no DSN and no --fixture", file=sys.stderr)
            return 2
        contracts, bids, counts = load_from_db(dsn)

    bundle = build_export(
        contracts,
        bids,
        counts,
        top20_path=top20,
        source_run_id=args.run_id,
        as_of=args.as_of,
        repo_root=root,
    )
    paths = write_export(args.out, bundle)
    result: dict[str, Any] = {
        "ok": True,
        "out": str(args.out),
        "dataset_hash": bundle["dataset_hash"],
        "export_entrypoint": EXPORT_ENTRYPOINT,
        "export_version": EXPORT_VERSION,
        "files": list(paths.keys()),
        "counts": bundle["manifest"]["counts"],
        "classification_counts": bundle["manifest"].get("classification_counts"),
        "source_commit_sha": bundle["manifest"].get("source_commit_sha"),
        "data_as_of": bundle["manifest"].get("data_as_of"),
    }
    if args.validate:
        from scripts.pseo.validation import validate_export_dir

        vr = validate_export_dir(args.out, repo_root=root, require_commit_entrypoint=False)
        if not (root / "scripts/pseo/export_web_cfg.py").exists():
            vr.setdefault("errors", []).append("export_web_cfg.py missing")
        if not (root / "scripts/pseo/cli_export.py").exists():
            vr.setdefault("errors", []).append("cli_export.py alias missing")
            vr["ok"] = False
        result["validation"] = vr
        if not vr["ok"]:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
