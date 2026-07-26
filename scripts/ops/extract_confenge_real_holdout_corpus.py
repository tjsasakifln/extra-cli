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
STRATA: list[tuple[str, str]] = [
    ("engenharia_obras_claras", r"obra|paviment|terraplen|engenharia|constru[cç]"),
    ("engenharia_ambigua", r"servi[cç]os?\s+t[eé]cnic|manuten[cç][aã]o\s+predial"),
    ("manutencao_predial", r"manuten[cç][aã]o\s+(predial|de\s+edif|predio)"),
    ("manutencao_nao_predial", r"manuten[cç][aã]o\s+(de\s+ve[ií]cul|frota|equipamento)"),
    ("infraestrutura_urbana", r"drenagem|saneamento|rede\s+de\s+[aá]gua|esgoto|via\s+urbana"),
    ("infraestrutura_ti", r"datacenter|rede\s+de\s+comput|infraestrutura\s+de\s+ti|servidor"),
    ("projetos_engenharia", r"projeto\s+de\s+engenharia|elabora[cç][aã]o\s+de\s+projeto"),
    ("projetos_nao_relacionados", r"projeto\s+pedag[oó]g|projeto\s+social|projeto\s+cultural"),
    ("servicos_tecnicos_genericos", r"servi[cç]os?\s+t[eé]cnicos?\s+especializ"),
    ("materiais_construcao", r"materiais?\s+de\s+constru|fornecimento\s+de\s+cimento|agregados"),
    ("locacao_com_operador", r"loca[cç][aã]o.*operador|com\s+operador"),
    ("locacao_sem_operador", r"loca[cç][aã]o\s+de\s+equipamento|loca[cç][aã]o\s+de\s+m[aá]quina"),
    ("instalacoes_prediais", r"instala[cç][oõ]es?\s+(el[eé]tric|hidr[aá]ulic|predial)"),
    ("climatizacao", r"climatiza|ar[- ]condicionado|hvac|refriger[aã]"),
    ("energia", r"subesta[cç][aã]o|energia\s+el[eé]trica|painel\s+solar|fotovolta"),
    ("telecom", r"telecomunica|fibra\s+[oó]ptica|radioenlace|telefonia"),
    ("engenharia_clinica", r"engenharia\s+cl[ií]nica|equipamento\s+hospitalar\s+m[eé]dico"),
    ("limpeza", r"limpeza\s+(predial|hospitalar|de\s+vias)|conserva[cç][aã]o\s+e\s+limpeza"),
    ("terceirizacao", r"terceiriza[cç][aã]o|cess[aã]o\s+de\s+m[aã]o\s+de\s+obra"),
    ("alimentacao", r"alimenta[cç][aã]o|merenda|refei[cç][aã]o|copa\s+e\s+cozinha"),
    ("sem_keywords_evidentes", r"."),  # residual bucket
]


def _norm(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def assign_stratum(objeto: str) -> str:
    n = _norm(objeto)
    for name, pat in STRATA:
        if name == "sem_keywords_evidentes":
            continue
        if re.search(pat, n, re.I):
            return name
    return "sem_keywords_evidentes"


def extract(conn: Any, *, min_n: int = 500, per_stratum: int = 30) -> list[dict[str, Any]]:
    rows = fetch_all(
        conn,
        """
        SELECT contrato_id, objeto_contrato, orgao_nome, orgao_cnpj, uf,
               data_publicacao::text AS data, source, source_id, is_active
        FROM public.pncp_supplier_contracts
        WHERE objeto_contrato IS NOT NULL AND length(btrim(objeto_contrato)) > 40
        ORDER BY md5(contrato_id::text)
        LIMIT 20000
        """,
    )
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        obj = str(r.get("objeto_contrato") or "")
        st = assign_stratum(obj)
        if len(buckets[st]) >= per_stratum * 3:
            continue
        buckets[st].append(
            {
                "contrato_id": r.get("contrato_id"),
                "objeto_contrato_original": obj,
                "orgao": r.get("orgao_nome") or r.get("orgao_cnpj"),
                "uf": r.get("uf"),
                "data": (str(r.get("data") or "")[:10] or None),
                "source_snapshot": "confenge_commercial_pncp_supplier_contracts",
                "source": r.get("source"),
                "source_id": r.get("source_id"),
                "is_active": r.get("is_active"),
                "stratum": st,
                # Human labels — agents NEVER fill
                "reviewer_1_label": None,
                "reviewer_1_reason": None,
                "reviewer_2_label": None,
                "reviewer_2_reason": None,
                "adjudicated_label": None,
                "adjudicator": None,
                "reviewed_at": None,
            }
        )

    # balanced take
    out: list[dict[str, Any]] = []
    for name, _ in STRATA:
        out.extend(buckets.get(name, [])[:per_stratum])
    # pad to min_n from residual
    if len(out) < min_n:
        used = {x["contrato_id"] for x in out}
        for r in rows:
            if len(out) >= min_n:
                break
            cid = r.get("contrato_id")
            if cid in used:
                continue
            obj = str(r.get("objeto_contrato") or "")
            out.append(
                {
                    "contrato_id": cid,
                    "objeto_contrato_original": obj,
                    "orgao": r.get("orgao_nome") or r.get("orgao_cnpj"),
                    "uf": r.get("uf"),
                    "data": (str(r.get("data") or "")[:10] or None),
                    "source_snapshot": "confenge_commercial_pncp_supplier_contracts",
                    "source": r.get("source"),
                    "source_id": r.get("source_id"),
                    "is_active": r.get("is_active"),
                    "stratum": assign_stratum(obj),
                    "reviewer_1_label": None,
                    "reviewer_1_reason": None,
                    "reviewer_2_label": None,
                    "reviewer_2_reason": None,
                    "adjudicated_label": None,
                    "adjudicator": None,
                    "reviewed_at": None,
                }
            )
            used.add(cid)
    return out[: max(min_n, len(out))]


def split_write(rows: list[dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    """70/15/15 split by contrato_id hash — holdout frozen separately."""
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
    # ensure holdout has enough for evaluation structure (>=150 of 500)
    if len(hold) < 100 and rows:
        # move tail of dev into hold
        need = 100 - len(hold)
        hold.extend(dev[-need:])
        dev = dev[:-need] if need < len(dev) else []

    paths = {
        "development-real-v1": out_dir / "development-real-v1.jsonl",
        "validation-real-v1": out_dir / "validation-real-v1.jsonl",
        "holdout-real-v1": out_dir / "holdout-real-v1.jsonl",
    }
    for name, path in [
        ("development-real-v1", paths["development-real-v1"]),
        ("validation-real-v1", paths["validation-real-v1"]),
        ("holdout-real-v1", paths["holdout-real-v1"]),
    ]:
        bucket = {"development-real-v1": dev, "validation-real-v1": val, "holdout-real-v1": hold}[
            name
        ]
        with path.open("w", encoding="utf-8") as f:
            for row in bucket:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    meta = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "n_total": len(rows),
        "n_development": len(dev),
        "n_validation": len(val),
        "n_holdout": len(hold),
        "strata_counts": {},
        "corpus_sha256": {
            k: sha(v) for k, v in paths.items()
        },
        "freeze_commit": None,
        "human_labels_filled": False,
        "note": (
            "Real PNCP objects extracted from snapshot. Human dual labels are null. "
            "Agents must never fill reviewer_*/adjudicated_* fields."
        ),
    }
    for r in rows:
        st = r.get("stratum") or "unknown"
        meta["strata_counts"][st] = meta["strata_counts"].get(st, 0) + 1
    try:
        import shutil
        import subprocess

        git = shutil.which("git") or "git"
        meta["freeze_commit"] = subprocess.check_output(  # noqa: S603
            [git, "rev-parse", "HEAD"], cwd=str(_ROOT), text=True
        ).strip()
    except Exception:  # noqa: BLE001 — freeze stamp is best-effort metadata only
        meta["freeze_commit"] = "unknown"
    (out_dir / "corpus-meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dsn",
        default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN")
        or "postgresql://confenge:confenge@127.0.0.1:5441/confenge_commercial",
    )
    ap.add_argument("--min-n", type=int, default=500)
    ap.add_argument("--out-dir", type=Path, default=REAL_DIR)
    args = ap.parse_args(argv)
    conn = connect(args.dsn)
    try:
        rows = extract(conn, min_n=args.min_n)
    finally:
        conn.close()
    if len(rows) < args.min_n:
        print(json.dumps({"ok": False, "n": len(rows), "min": args.min_n}))
        return 1
    meta = split_write(rows, args.out_dir)
    meta["ok"] = True
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
