#!/usr/bin/env python3
"""Public-inventory candidate selection helpers for edital relevance foundation.

Selection uses public fields only. Never uses classifier output, DB counts,
scores, success_zero, or operational queues.

This module supports independent candidate acquisition for future human labeling.
It does NOT produce gold labels or sealed holdouts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

GRANDE = {
    "JOINVILLE",
    "FLORIANOPOLIS",
    "BLUMENAU",
    "SAO JOSE",
    "CHAPECO",
    "CRICIUMA",
    "ITAJAI",
    "LAGES",
    "JARAGUA DO SUL",
    "PALHOCA",
    "BRUSQUE",
    "TUBARAO",
    "BALNEARIO CAMBORIU",
    "SAO PAULO",
    "RIO DE JANEIRO",
    "BELO HORIZONTE",
    "CURITIBA",
    "PORTO ALEGRE",
    "BRASILIA",
    "SALVADOR",
    "FORTALEZA",
    "RECIFE",
    "MANAUS",
    "BELEM",
    "GOIANIA",
    "GUARULHOS",
    "CAMPINAS",
}
MEDIO = {
    "CACADOR",
    "CONCORDIA",
    "NAVEGANTES",
    "SAO BENTO DO SUL",
    "MAFRA",
    "RIO DO SUL",
    "INDAIAL",
    "GASPAR",
    "BIGUACU",
    "ARARANGUA",
    "VIDEIRA",
    "CANOINHAS",
    "XANXERE",
    "TIMBO",
    "PENHA",
    "IMBITUBA",
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm_muni(name: str | None) -> str:
    if not name:
        return ""
    t = unicodedata.normalize("NFKD", str(name))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.upper()).strip()


def municipio_bucket(name: str | None) -> str:
    n = _norm_muni(name)
    if not n or "ESTADUAL" in n or n == "SC":
        return "medio"
    if n in GRANDE or any(g in n for g in GRANDE):
        return "grande"
    if n in MEDIO or any(m in n for m in MEDIO):
        return "medio"
    return "pequeno"


def natureza_from_orgao(orgao: str | None, source: str) -> str:
    text = (orgao or "").lower()
    if any(
        k in text
        for k in (
            "autarquia",
            "fundacao",
            "empresa publica",
            "sociedade de economia",
            "saaе",
            "saae",
            "companhia",
        )
    ):
        return "admin_indireta"
    if source == "ciga":
        return "admin_direta"
    return "admin_direta"


def content_hash(rec: dict[str, Any]) -> str:
    blob = "|".join(
        [
            str(rec.get("official_id") or ""),
            str(rec.get("source") or ""),
            str(rec.get("url") or ""),
            str(rec.get("objeto") or ""),
            str(rec.get("titulo") or ""),
        ]
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def enrich_public_candidate(rec: dict[str, Any]) -> dict[str, Any]:
    """Normalize a public inventory record into candidate schema (no labels)."""
    out = dict(rec)
    out["municipio_bucket"] = out.get("municipio_bucket") or municipio_bucket(out.get("municipio"))
    out["natureza_juridica"] = out.get("natureza_juridica") or natureza_from_orgao(
        out.get("orgao"), str(out.get("source") or "")
    )
    out["content_hash"] = out.get("content_hash") or content_hash(out)
    out["observed_at"] = out.get("observed_at") or utc_now()
    out["selection_method"] = out.get("selection_method") or "public_inventory_stratified_content_sample"
    out["selection_provenance"] = out.get("selection_provenance") or (f"public_inventory:{out.get('source')}")
    out["selected_by_classifier"] = False
    out["selected_by_db_presence"] = False
    out["selected_by_success_zero"] = False
    out["synthetic"] = False
    return out


def validate_candidate_selection(records: list[dict[str, Any]]) -> list[str]:
    """Return errors if selection proxies are present."""
    errors: list[str] = []
    for i, rec in enumerate(records):
        oid = rec.get("official_id") or f"row[{i}]"
        if rec.get("selected_by_classifier") is True:
            errors.append(f"{oid}: selected_by_classifier")
        if rec.get("selected_by_db_presence") is True:
            errors.append(f"{oid}: selected_by_db_presence")
        if rec.get("selected_by_success_zero") is True:
            errors.append(f"{oid}: selected_by_success_zero")
        if rec.get("synthetic") is True:
            errors.append(f"{oid}: synthetic not allowed for public candidate pool")
        sel = str(rec.get("selection_method") or "").lower()
        for bad in ("system_class", "classifier_output", "db_count", "success_zero", "operational_queue"):
            if bad in sel:
                errors.append(f"{oid}: forbidden selection_method token {bad}")
    return errors


def cmd_enrich(args: argparse.Namespace) -> int:
    path = Path(args.input)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(enrich_public_candidate(json.loads(line)))
    errors = validate_candidate_selection(rows)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "n": len(rows),
                "output": str(out),
                "errors": errors,
                "ok": not errors,
                "note": "Candidates only — not gold, not human labels, not sealed holdout",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Public candidate enrichment for relevance foundation")
    sub = p.add_subparsers(dest="command", required=True)
    e = sub.add_parser("enrich", help="Enrich public inventory JSONL with strata metadata")
    e.add_argument("--input", required=True)
    e.add_argument("--output", required=True)
    e.set_defaults(func=cmd_enrich)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
