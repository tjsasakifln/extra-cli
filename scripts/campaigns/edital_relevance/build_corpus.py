#!/usr/bin/env python3
"""Build pilot / development / locked_holdout gold corpora for §8.4.

Selection is from public inventories only (PNCP API live, SC Compras public
API snapshot, CIGA DOM official zip). Never uses classifier output, DB counts,
scores, success_zero, or operational queues.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.campaigns.edital_relevance.dual_label import dual_label_record  # noqa: E402

# Approx population buckets for SC + Brazil municipalities in sample
GRANDE = {
    "JOINVILLE", "FLORIANOPOLIS", "BLUMENAU", "SAO JOSE", "CHAPECO", "CRICIUMA",
    "ITAJAI", "LAGES", "JARAGUA DO SUL", "PALHOCA", "BRUSQUE", "TUBARAO",
    "BALNEARIO CAMBORIU", "SAO PAULO", "RIO DE JANEIRO", "BELO HORIZONTE",
    "CURITIBA", "PORTO ALEGRE", "BRASILIA", "SALVADOR", "FORTALEZA", "RECIFE",
    "MANAUS", "BELEM", "GOIANIA", "GUARULHOS", "CAMPINAS",
}
MEDIO = {
    "CACADOR", "CONCORDIA", "NAVEGANTES", "SAO BENTO DO SUL", "MAFRA",
    "RIO DO SUL", "INDAIAL", "GASPAR", "BIGUACU", "ARARANGUA", "VIDEIRA",
    "CANOINHAS", "XANXERE", "BRUSQUE", "TIMBO", "PENHA", "IMBITUBA",
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
        return "medio"  # state-level organs treated as medium stratum
    if n in GRANDE or any(g in n for g in GRANDE):
        return "grande"
    if n in MEDIO or any(m in n for m in MEDIO):
        return "medio"
    return "pequeno"


def natureza_from_orgao(orgao: str | None, source: str) -> str:
    o = (orgao or "").upper()
    if any(x in o for x in ("CONSORCIO", "CONSÓRCIO", "CISAMURES", "AMURES")):
        return "admin_indireta"
    if any(x in o for x in ("AUTARQUIA", "FUNDACAO", "FUNDAÇÃO", "INSTITUTO", "AGENCIA", "AGÊNCIA")):
        return "admin_indireta"
    if any(x in o for x in ("CAMARA", "CÂMARA")):
        return "admin_indireta"
    if any(x in o for x in ("PREFEITURA", "MUNICIPIO", "MUNICÍPIO", "SECRETARIA", "ESTADO")):
        return "admin_direta"
    # default by source
    return "admin_direta" if source in {"pncp", "sc_compras", "ciga"} else "admin_direta"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else "")
    path.write_text(body, encoding="utf-8")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def enrich(rec: dict[str, Any]) -> dict[str, Any]:
    out = dict(rec)
    out.setdefault("titulo", None)
    out["municipio_bucket"] = municipio_bucket(out.get("municipio"))
    out["natureza_juridica"] = natureza_from_orgao(out.get("orgao"), str(out.get("source")))
    out["selection_method"] = "public_inventory_stratified_content_sample"
    out.setdefault(
        "selection_provenance",
        f"public_inventory:{out.get('source')}",
    )
    # Explicit anti-proxy flags
    out["selected_by_classifier"] = False
    out["selected_by_db_presence"] = False
    out["selected_by_success_zero"] = False
    out["synthetic"] = False
    return dual_label_record(out)


def rough_eng(obj: str) -> bool:
    o = (obj or "").lower()
    keys = (
        "paviment", "drenagem", "terrapl", "saneamento", "asfalt", "galeria pluvial",
        "reforma de escola", "ampliação de", "ampliacao de", "construção de escola",
        "construcao de escola", "obra de engenharia", "manutenção predial",
        "manutencao predial", "empreitada", "muro de arrimo", "esgoto", "adutora",
        "edificação", "edificacao", "passeio", "calçada", "calcada",
    )
    return any(k in o for k in keys)


def rough_non(obj: str) -> bool:
    o = (obj or "").lower()
    keys = (
        "medicamento", "computador", "combustivel", "combustível", "uniforme",
        "merenda", "software", "fisioterapia", "exame", "alimento", "gasolina",
        "diesel", "notebook", "vacina", "lençol", "lencol", "telefonia", "voip",
        "jardinagem", "frota", "capacitação", "capacitacao", "karate",
    )
    return any(k in o for k in keys)


def sample_balanced(
    rows: list[dict[str, Any]],
    n: int,
    *,
    rng: random.Random,
    prefer_eng_ratio: float = 0.5,
) -> list[dict[str, Any]]:
    eng = [r for r in rows if rough_eng(r.get("objeto") or "")]
    non = [r for r in rows if rough_non(r.get("objeto") or "") and r not in eng]
    other = [r for r in rows if r not in eng and r not in non]
    n_eng = int(round(n * prefer_eng_ratio))
    n_non = n - n_eng
    rng.shuffle(eng)
    rng.shuffle(non)
    rng.shuffle(other)
    picked: list[dict[str, Any]] = []
    picked.extend(eng[:n_eng])
    picked.extend(non[:n_non])
    # fill
    pool = eng[n_eng:] + non[n_non:] + other
    for r in pool:
        if len(picked) >= n:
            break
        if r not in picked:
            picked.append(r)
    return picked[:n]


def build_pilot(
    pncp: list[dict[str, Any]],
    sc: list[dict[str, Any]],
    ciga: list[dict[str, Any]],
    *,
    seed: int = 42,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    parts = [
        sample_balanced(pncp, 12, rng=rng),
        sample_balanced(sc, 12, rng=rng),
        sample_balanced(ciga, 12, rng=rng),
    ]
    out = []
    seen = set()
    for part in parts:
        for r in part:
            e = enrich(r)
            if e["official_id"] in seen:
                continue
            seen.add(e["official_id"])
            e["split"] = "pilot"
            out.append(e)
    return out[:36]


def expand_sets(
    pncp: list[dict[str, Any]],
    sc: list[dict[str, Any]],
    ciga: list[dict[str, Any]],
    pilot_ids: set[str],
    *,
    seed: int = 20260726,
    holdout_relevant_target: int = 110,
    holdout_irrelevant_target: int = 110,
    dev_target: int = 120,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build development + locked_holdout with stratification."""
    rng = random.Random(seed)
    all_rows: list[dict[str, Any]] = []
    for src_rows in (pncp, sc, ciga):
        for r in src_rows:
            if r["official_id"] in pilot_ids:
                continue
            all_rows.append(enrich(r))

    # Drop UNDECIDABLE from final sets when possible (keep some in dev for coverage)
    relevant = [r for r in all_rows if r["label_final"] == "RELEVANT"]
    irrelevant = [r for r in all_rows if r["label_final"] == "IRRELEVANT"]
    undec = [r for r in all_rows if r["label_final"] == "UNDECIDABLE"]
    rng.shuffle(relevant)
    rng.shuffle(irrelevant)
    rng.shuffle(undec)

    def take_stratified(
        pool: list[dict[str, Any]], n: int, used: set[str]
    ) -> list[dict[str, Any]]:
        """Prefer diversity of source, municipio_bucket, natureza."""
        buckets: dict[str, list[dict[str, Any]]] = {}
        for r in pool:
            if r["official_id"] in used:
                continue
            key = f"{r.get('source')}|{r.get('municipio_bucket')}|{r.get('natureza_juridica')}"
            buckets.setdefault(key, []).append(r)
        keys = list(buckets.keys())
        rng.shuffle(keys)
        picked: list[dict[str, Any]] = []
        # round-robin
        while len(picked) < n and keys:
            progress = False
            for k in list(keys):
                if not buckets[k]:
                    keys.remove(k)
                    continue
                r = buckets[k].pop()
                if r["official_id"] in used:
                    continue
                used.add(r["official_id"])
                picked.append(r)
                progress = True
                if len(picked) >= n:
                    break
            if not progress:
                break
        return picked

    used: set[str] = set()
    holdout: list[dict[str, Any]] = []
    holdout.extend(take_stratified(relevant, holdout_relevant_target, used))
    holdout.extend(take_stratified(irrelevant, holdout_irrelevant_target, used))
    # ensure min strata presence by top-up
    for r in relevant + irrelevant:
        if len(holdout) >= holdout_relevant_target + holdout_irrelevant_target + 30:
            break
        if r["official_id"] in used:
            continue
        # fill missing source quotas
        holdout.append(r)
        used.add(r["official_id"])

    for r in holdout:
        r["split"] = "locked_holdout"

    # development from remainder
    rem_rel = [r for r in relevant if r["official_id"] not in used]
    rem_irr = [r for r in irrelevant if r["official_id"] not in used]
    rem_und = [r for r in undec if r["official_id"] not in used]
    dev: list[dict[str, Any]] = []
    dev.extend(take_stratified(rem_rel, dev_target // 2, used))
    dev.extend(take_stratified(rem_irr, dev_target // 2, used))
    dev.extend(take_stratified(rem_und, min(15, len(rem_und)), used))
    for r in dev:
        r["split"] = "development"

    return dev, holdout


def write_manifest(
    path: Path,
    *,
    role: str,
    corpus_path: Path,
    corpus_sha256: str,
    records: list[dict[str, Any]],
    stratum_blockers: dict[str, str] | None = None,
) -> None:
    relevant = sum(1 for r in records if r.get("label_final") == "RELEVANT")
    irrelevant = sum(1 for r in records if r.get("label_final") == "IRRELEVANT")
    undec = sum(1 for r in records if r.get("label_final") == "UNDECIDABLE")
    agreed = sum(1 for r in records if r.get("labels_agreed"))
    sources = {}
    for r in records:
        sources[r.get("source")] = sources.get(r.get("source"), 0) + 1
    man = {
        "schema_version": "edital-relevance-corpus/1.0.0",
        "role": role,
        "campaign": "EDITAL-RELEVANCE-RECALL-95-01",
        "frozen_at": utc_now(),
        "sealed_before_classifier_edits": role == "locked_holdout",
        "corpus_path": str(corpus_path.as_posix()),
        "corpus_sha256": corpus_sha256,
        "n_records": len(records),
        "n_relevant": relevant,
        "n_irrelevant": irrelevant,
        "n_undecidable": undec,
        "dual_label_agreement_rate": (agreed / len(records)) if records else 0.0,
        "sources": sources,
        "selection_rule": (
            "public_inventory_only; stratified content sample; "
            "NOT system_class/db_count/score/success_zero/operational_queue"
        ),
        "stratum_blockers": stratum_blockers or {},
        "reviewers": [
            "criteria_A_inclusion_first",
            "criteria_B_exclusion_first",
        ],
        "adjudication": "conflicts adjudicated; UNDECIDABLE never silent→IRRELEVANT",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pncp", required=True)
    ap.add_argument("--sc", required=True)
    ap.add_argument("--ciga", required=True)
    ap.add_argument("--out-dir", default=str(PROJECT_ROOT / "evals/edital_relevance"))
    args = ap.parse_args()

    pncp = load_jsonl(Path(args.pncp))
    sc = load_jsonl(Path(args.sc))
    ciga = load_jsonl(Path(args.ciga))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pilot = build_pilot(pncp, sc, ciga)
    # if pilot short, pad carefully
    if len(pilot) < 36:
        print(f"WARN pilot size {len(pilot)} < 36", file=sys.stderr)

    pilot_path = out_dir / "pilot_36.jsonl"
    h = write_jsonl(pilot_path, pilot)
    write_manifest(
        out_dir / "pilot_36-manifest.json",
        role="pilot",
        corpus_path=pilot_path,
        corpus_sha256=h,
        records=pilot,
    )

    pilot_ids = {r["official_id"] for r in pilot}
    dev, holdout = expand_sets(pncp, sc, ciga, pilot_ids)

    # stratum blockers if needed
    from collections import Counter

    def stratum_check(rows: list[dict[str, Any]]) -> dict[str, int]:
        c: Counter[str] = Counter()
        for r in rows:
            c[f"source:{r.get('source')}"] += 1
            c[f"municipio_bucket:{r.get('municipio_bucket')}"] += 1
            c[f"natureza:{r.get('natureza_juridica')}"] += 1
        return dict(c)

    scounts = stratum_check(holdout)
    blockers = {}
    for key, floor in [
        ("source:pncp", 10),
        ("source:sc_compras", 10),
        ("source:ciga", 10),
        ("municipio_bucket:grande", 10),
        ("municipio_bucket:medio", 10),
        ("municipio_bucket:pequeno", 10),
        ("natureza:admin_direta", 10),
        ("natureza:admin_indireta", 10),
    ]:
        if scounts.get(key, 0) < floor:
            blockers[key] = (
                f"population in sampled public inventory window yielded "
                f"{scounts.get(key, 0)} after dual-label adjudication; "
                f"floor {floor} not reachable without inventing rows"
            )

    dev_path = out_dir / "development.jsonl"
    hold_path = out_dir / "locked_holdout.jsonl"
    hd = write_jsonl(dev_path, dev)
    hh = write_jsonl(hold_path, holdout)
    write_manifest(
        out_dir / "development-manifest.json",
        role="development",
        corpus_path=dev_path,
        corpus_sha256=hd,
        records=dev,
    )
    write_manifest(
        out_dir / "locked_holdout-manifest.json",
        role="locked_holdout",
        corpus_path=hold_path,
        corpus_sha256=hh,
        records=holdout,
        stratum_blockers=blockers,
    )

    # sampling plan doc data
    plan = {
        "window": "PNCP live ~30d to 2026-07-26; SC Compras full 2026 snapshot live_fetch; CIGA DOM Jul/2026 public zips",
        "selection": "stratified content sample from public inventories; ~half eng-ish keywords for balance pre-label only",
        "not_used": [
            "classifier_output",
            "db_count",
            "score",
            "success_zero",
            "operational_queue",
            "presence_in_db",
        ],
        "pilot_n": len(pilot),
        "development_n": len(dev),
        "holdout_n": len(holdout),
        "holdout_relevant": sum(1 for r in holdout if r["label_final"] == "RELEVANT"),
        "holdout_stratum_counts": scounts,
        "stratum_blockers": blockers,
        "dual_label_agreement_pilot": (
            sum(1 for r in pilot if r.get("labels_agreed")) / len(pilot) if pilot else 0
        ),
        "dual_label_agreement_holdout": (
            sum(1 for r in holdout if r.get("labels_agreed")) / len(holdout) if holdout else 0
        ),
    }
    (out_dir / "sampling_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
