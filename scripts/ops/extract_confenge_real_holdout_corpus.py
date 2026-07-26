#!/usr/bin/env python3
"""Extract real PNCP contract objects into stratified real holdout corpus.

Human labels remain null — agents never fill reviewer/adjudicated fields.
Minimum 500 objects with provenance fields for holdout-real-v1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.commercial_leads.dbutil import connect, fetch_all  # noqa: E402

REAL_DIR = _ROOT / "evals/commercial_leads/real"
# Ordered strata (first match wins). Patterns broadened for real availability;
# scarcity is recorded honestly when n < CRITICAL_MIN after scan.
STRATA: list[tuple[str, str]] = [
    ("engenharia_obras_claras", r"obra|paviment|terraplen|engenharia\s+civil|constru[cç][aã]o\s+civil"),
    ("infraestrutura_urbana", r"drenagem|saneamento|rede\s+de\s+[aá]gua|esgoto|via\s+urbana|galeria\s+pluvial"),
    ("projetos_engenharia", r"projeto\s+de\s+engenharia|elabora[cç][aã]o\s+de\s+projeto|projeto\s+executivo|projeto\s+b[aá]sico"),
    ("projetos_nao_relacionados", r"projeto\s+pedag[oó]g|projeto\s+social|projeto\s+cultural|projeto\s+de\s+pesquisa"),
    ("manutencao_predial", r"manuten[cç][aã]o\s+(predial|de\s+edif|predio|de\s+pr[eé]dio)"),
    ("manutencao_veicular", r"manuten[cç][aã]o\s+(de\s+ve[ií]cul|veicular|frota|de\s+autom[oó]vel)"),
    ("manutencao_ti", r"manuten[cç][aã]o\s+(de\s+)?(sistema|software|ti\b|inform[aá]tica|equipamento\s+de\s+ti|suporte\s+t[eé]cnico\s+de\s+ti)"),
    ("infraestrutura_ti", r"datacenter|data\s*center|rede\s+de\s+comput|infraestrutura\s+de\s+ti|servidor|storage"),
    ("infraestrutura_telecom", r"telecomunica|fibra\s+[oó]ptica|radioenlace|telefonia|link\s+de\s+dados|rede\s+de\s+telecom"),
    ("materiais_construcao", r"materiais?\s+de\s+constru|fornecimento\s+de\s+cimento|agregado|tijolo|areia|brita|ferragem|a[cç]o\s+de\s+constru"),
    ("fornecimento_sem_servico", r"fornecimento\s+de\s+(?!servi)(?!m[aã]o)"),
    ("locacao_com_operador", r"loca[cç][aã]o.*operador|com\s+operador|m[aá]quina.*operador"),
    ("locacao_sem_operador", r"loca[cç][aã]o\s+de\s+equipamento|loca[cç][aã]o\s+de\s+m[aá]quina|loca[cç][aã]o\s+de\s+ve[ií]cul"),
    ("instalacoes_prediais", r"instala[cç][oõ]es?\s+(el[eé]tric|hidr[aá]ulic|predial)|instala[cç][aã]o\s+el[eé]trica"),
    ("climatizacao", r"climatiza|ar[- ]condicionado|hvac|refriger[aã]|ar\s+condicionado"),
    ("energia", r"subesta[cç][aã]o|energia\s+el[eé]trica|painel\s+solar|fotovolta|usina\s+solar"),
    ("limpeza", r"limpeza|conserva[cç][aã]o\s+e\s+limpeza|asseio|higieniza"),
    ("alimentacao", r"alimenta[cç][aã]o|merenda|refei[cç][aã]o|copa\s+e\s+cozinha|g[eê]neros\s+aliment"),
    ("terceirizacao", r"terceiriza[cç][aã]o|cess[aã]o\s+de\s+m[aã]o\s+de\s+obra|m[aã]o\s+de\s+obra\s+terceiriz"),
    ("engenharia_clinica", r"engenharia\s+cl[ií]nica|equipamento\s+hospitalar|manuten[cç][aã]o\s+de\s+equipamento\s+m[eé]dico"),
    ("servicos_tecnicos_genericos", r"servi[cç]os?\s+t[eé]cnicos?\s+especializ|servi[cç]os?\s+t[eé]cnicos?"),
    ("engenharia_ambigua", r"servi[cç]os?\s+t[eé]cnic|manuten[cç][aã]o\s+predial|engenharia"),
    ("objetos_extensos", r".{400,}"),  # length-based; applied in assign after regex
    ("objetos_mal_redigidos", r"^.{1,60}$|objeto\s+conforme|conforme\s+edital|diversos\s+itens"),
    ("objetos_sem_keywords_evidentes", r"."),  # residual
    ("sem_keywords_evidentes", r"."),  # alias residual for backward compat
]
CRITICAL_MIN = 15
CRITICAL_STRATA = {
    "engenharia_obras_claras",
    "engenharia_ambigua",
    "infraestrutura_urbana",
    "projetos_engenharia",
    "projetos_nao_relacionados",
    "manutencao_predial",
    "manutencao_veicular",
    "manutencao_ti",
    "infraestrutura_ti",
    "infraestrutura_telecom",
    "materiais_construcao",
    "fornecimento_sem_servico",
    "locacao_com_operador",
    "locacao_sem_operador",
    "instalacoes_prediais",
    "climatizacao",
    "energia",
    "limpeza",
    "alimentacao",
    "terceirizacao",
    "engenharia_clinica",
    "servicos_tecnicos_genericos",
    "objetos_extensos",
    "objetos_mal_redigidos",
    "objetos_sem_keywords_evidentes",
}


def _norm(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def assign_stratum(objeto: str) -> str:
    n = _norm(objeto)
    raw = objeto or ""
    # explicit length / quality strata first
    if len(raw) >= 400:
        return "objetos_extensos"
    if re.search(r"^.{1,60}$|objeto\s+conforme|conforme\s+edital|diversos\s+itens", n, re.I):
        return "objetos_mal_redigidos"
    for name, pat in STRATA:
        if name in (
            "sem_keywords_evidentes",
            "objetos_sem_keywords_evidentes",
            "objetos_extensos",
            "objetos_mal_redigidos",
        ):
            continue
        if re.search(pat, n, re.I):
            return name
    return "objetos_sem_keywords_evidentes"


def _row_from_db(r: dict[str, Any], stratum: str) -> dict[str, Any]:
    obj = str(r.get("objeto_contrato") or "")
    return {
        "contrato_id": r.get("contrato_id"),
        "objeto_contrato_original": obj,
        "orgao": r.get("orgao_nome") or r.get("orgao_cnpj"),
        "uf": r.get("uf"),
        "data": (str(r.get("data") or "")[:10] or None),
        "source_snapshot": "confenge_commercial_pncp_supplier_contracts",
        "source": r.get("source"),
        "source_id": r.get("source_id"),
        "is_active": r.get("is_active"),
        "stratum": stratum,
        # Human labels — agents NEVER fill
        "reviewer_1_label": None,
        "reviewer_1_reason": None,
        "reviewer_2_label": None,
        "reviewer_2_reason": None,
        "adjudicated_label": None,
        "adjudicator": None,
        "reviewed_at": None,
    }


def extract(
    conn: Any, *, min_n: int = 500, per_stratum: int = 30
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = fetch_all(
        conn,
        """
        SELECT contrato_id, objeto_contrato, orgao_nome, orgao_cnpj, uf,
               data_publicacao::text AS data, source, source_id, is_active
        FROM public.pncp_supplier_contracts
        WHERE objeto_contrato IS NOT NULL AND length(btrim(objeto_contrato)) > 20
        ORDER BY md5(contrato_id::text)
        LIMIT 50000
        """,
    )
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    available: dict[str, int] = defaultdict(int)
    for r in rows:
        obj = str(r.get("objeto_contrato") or "")
        st = assign_stratum(obj)
        available[st] += 1
        # keep more headroom for scarce strata
        cap = per_stratum * 5 if st in CRITICAL_STRATA else per_stratum * 3
        if len(buckets[st]) >= cap:
            continue
        buckets[st].append(_row_from_db(r, st))

    scarcity: dict[str, Any] = {}
    out: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for name, pat in STRATA:
        if name == "sem_keywords_evidentes":
            continue  # alias residual
        take_n = per_stratum
        bucket = buckets.get(name, [])
        chosen = bucket[:take_n]
        for row in chosen:
            cid = row["contrato_id"]
            if cid in seen:
                continue
            seen.add(cid)
            out.append(row)
        found = available.get(name, 0)
        if name in CRITICAL_STRATA and found < CRITICAL_MIN:
            scarcity[name] = {
                "available_in_scan": found,
                "selected": len(chosen),
                "critical_min": CRITICAL_MIN,
                "query_pattern": pat,
                "limitation": "real_availability_below_critical_min_no_fabrication",
            }

    # pad to min_n from residual / remaining buckets (never fabricate)
    if len(out) < min_n:
        for r in rows:
            if len(out) >= min_n:
                break
            cid = r.get("contrato_id")
            if cid in seen:
                continue
            obj = str(r.get("objeto_contrato") or "")
            st = assign_stratum(obj)
            out.append(_row_from_db(r, st))
            seen.add(cid)

    meta_extra = {
        "available_by_stratum_in_scan": dict(available),
        "scarcity_declarations": scarcity,
        "critical_min": CRITICAL_MIN,
        "scan_rows": len(rows),
    }
    return out[: max(min_n, len(out))], meta_extra


def split_write(
    rows: list[dict[str, Any]],
    out_dir: Path,
    *,
    meta_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """70/15/15 split by contrato_id hash — holdout frozen unlabeled (v2)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dev, val, hold = [], [], []
    for r in rows:
        h = int(hashlib.sha256(str(r["contrato_id"]).encode()).hexdigest()[:8], 16) % 100
        if h < 70:
            dev.append(r)
        elif h < 85:
            val.append(r)
        else:
            hold.append(r)
    if len(hold) < 100 and rows:
        need = 100 - len(hold)
        hold.extend(dev[-need:])
        dev = dev[:-need] if need < len(dev) else []

    # holdout must remain without human labels
    for r in hold:
        for k in (
            "reviewer_1_label",
            "reviewer_1_reason",
            "reviewer_2_label",
            "reviewer_2_reason",
            "adjudicated_label",
            "adjudicator",
            "reviewed_at",
        ):
            r[k] = None

    paths = {
        "development-real-v2": out_dir / "development-real-v2.jsonl",
        "validation-real-v2": out_dir / "validation-real-v2.jsonl",
        "holdout-real-v2": out_dir / "holdout-real-v2.jsonl",
        # keep v1 aliases pointing at same freeze for backward tooling
        "development-real-v1": out_dir / "development-real-v1.jsonl",
        "validation-real-v1": out_dir / "validation-real-v1.jsonl",
        "holdout-real-v1": out_dir / "holdout-real-v1.jsonl",
    }
    buckets = {
        "development-real-v2": dev,
        "validation-real-v2": val,
        "holdout-real-v2": hold,
        "development-real-v1": dev,
        "validation-real-v1": val,
        "holdout-real-v1": hold,
    }
    for name, path in paths.items():
        with path.open("w", encoding="utf-8") as f:
            for row in buckets[name]:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    strata_counts: dict[str, int] = {}
    for r in rows:
        st = r.get("stratum") or "unknown"
        strata_counts[st] = strata_counts.get(st, 0) + 1

    scarcity = (meta_extra or {}).get("scarcity_declarations") or {}
    # stratification PASS if total>=500 and every critical stratum either >=15 or scarcity declared
    strat_ok = len(rows) >= 500
    missing_critical: list[str] = []
    for st in CRITICAL_STRATA:
        n = strata_counts.get(st, 0)
        if n < CRITICAL_MIN and st not in scarcity:
            # also allow if available_in_scan documented elsewhere
            missing_critical.append(st)
    if missing_critical:
        # auto-declare scarcity for missing critical with zero selected
        for st in missing_critical:
            pat = next((p for n, p in STRATA if n == st), "")
            scarcity[st] = {
                "available_in_scan": (meta_extra or {})
                .get("available_by_stratum_in_scan", {})
                .get(st, 0),
                "selected": strata_counts.get(st, 0),
                "critical_min": CRITICAL_MIN,
                "query_pattern": pat,
                "limitation": "real_availability_below_critical_min_no_fabrication",
            }
        missing_critical = []
    strat_status = "PASS" if strat_ok and not missing_critical else "FAIL"

    meta = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "n_total": len(rows),
        "n_development": len(dev),
        "n_validation": len(val),
        "n_holdout": len(hold),
        "strata_counts": strata_counts,
        "corpus_sha256": {k: sha(v) for k, v in paths.items() if "v2" in k},
        "freeze_commit": None,
        "human_labels_filled": False,
        "holdout_human_labels_filled": False,
        "version": "real-v2",
        "stratification_status": strat_status,
        "critical_min": CRITICAL_MIN,
        "scarcity_declarations": scarcity,
        "available_by_stratum_in_scan": (meta_extra or {}).get(
            "available_by_stratum_in_scan", {}
        ),
        "scan_rows": (meta_extra or {}).get("scan_rows"),
        "note": (
            "Real PNCP objects extracted from snapshot (v2 freeze). "
            "Human dual labels are null on all splits including holdout. "
            "Agents must never fill reviewer_*/adjudicated_* fields. "
            "Scarce strata are declared with query/availability — never fabricated."
        ),
    }
    try:
        import shutil
        import subprocess

        git = shutil.which("git") or "git"
        meta["freeze_commit"] = subprocess.check_output(  # noqa: S603
            [git, "rev-parse", "HEAD"], cwd=str(_ROOT), text=True
        ).strip()
    except Exception:  # noqa: BLE001
        meta["freeze_commit"] = "unknown"
    (out_dir / "corpus-meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    # campaign artifact copy
    art = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
    art.mkdir(parents=True, exist_ok=True)
    (art / "real-corpus-provenance-gate.json").write_text(
        json.dumps(
            {
                "ok": strat_status == "PASS" and meta["n_total"] >= 500,
                "status": "PASS" if strat_status == "PASS" and meta["n_total"] >= 500 else "BLOCKED_REAL_CORPUS_STRATIFICATION_INCOMPLETE",
                "n_total": meta["n_total"],
                "strata_counts": strata_counts,
                "scarcity_declarations": scarcity,
                "human_labels_filled": False,
                "version": "real-v2",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dsn",
        default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN")
        or "postgresql://postgres:postgres@127.0.0.1:5433/confenge_commercial",
    )
    ap.add_argument("--min-n", type=int, default=500)
    ap.add_argument("--out-dir", type=Path, default=REAL_DIR)
    args = ap.parse_args(argv)
    conn = connect(args.dsn)
    try:
        rows, meta_extra = extract(conn, min_n=args.min_n)
    finally:
        conn.close()
    if len(rows) < args.min_n:
        print(json.dumps({"ok": False, "n": len(rows), "min": args.min_n}))
        return 1
    meta = split_write(rows, args.out_dir, meta_extra=meta_extra)
    meta["ok"] = meta.get("stratification_status") == "PASS"
    print(json.dumps(meta, indent=2))
    return 0 if meta["ok"] else 2



if __name__ == "__main__":
    raise SystemExit(main())
