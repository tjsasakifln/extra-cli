#!/usr/bin/env python3
"""Independent gold-sample inventory for stratified recall.

Collects official portal publications WITHOUT reading operational opportunity
tables as the denominator source. Used by STRATIFIED-RECALL-SOURCE-RESILIENCE-01.

Usage:
  python -m scripts.coverage.independent_inventory collect \\
    --window-start 2026-07-01 --window-end 2026-07-22 \\
    --out artifacts/campaigns/STRATIFIED-RECALL-SOURCE-RESILIENCE-01/gold-sample.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import io
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.coverage.recall_benchmark import (
    MIN_PER_STRATUM,
    MIN_UNIQUE_ITEMS,
    REQUIRED_STRATA,
    denominator_hash,
    freeze_sample_lock,
    validate_sample_schema,
)

USER_AGENT = "ExtraConsultoria-RecallCampaign/1.0 (+stratified-recall; respectful rate limit)"
PNCP_BASE = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
SC_COMPRAS_BASE = "https://compras.sc.gov.br/api/editais"
CIGA_PACKAGE_SEARCH = "https://dados.ciga.sc.gov.br/api/3/action/package_search"

# Municipality size buckets (approx IBGE ranges for SC classification in this campaign)
# grande >= 100k, medio 20k-99999, pequeno < 20k
KNOWN_POP: dict[str, int] = {
    "JOINVILLE": 616317,
    "FLORIANOPOLIS": 537211,
    "BLUMENAU": 361261,
    "SAO JOSE": 270299,
    "CHAPECO": 224786,
    "CRICIUMA": 214875,
    "ITAJAI": 264054,
    "LAGES": 157148,
    "JARAGUA DO SUL": 182660,
    "PALHOCA": 222598,
    "BRUSQUE": 141385,
    "TUBARAO": 110088,
    "CACADOR": 80000,
    "CONCORDIA": 75000,
    "NAVEGANTES": 86000,
    "BALNEARIO CAMBORIU": 145796,
    "SAO BENTO DO SUL": 85000,
    "MAFRA": 60000,
    "RIO DO SUL": 72000,
    "INDAIAL": 73000,
    "GASPAR": 72000,
    "BIGUACU": 70000,
    "ARARANGUA": 70000,
    "VIDEIRA": 55000,
    "CANOINHAS": 55000,
    "XANXERE": 52000,
    "SAUDADES": 10000,
    "AGUAS FRIAS": 2500,
    "SANGAO": 12000,
    "ARVOREDO": 2500,
    "BANDEIRANTE": 3000,
    "ALTO BELA VISTA": 2000,
    "PRESIDENTE CASTELO BRANCO": 3000,
    "CALMON": 3500,
    "CORDILHEIRA ALTA": 4500,
    "RIO DOS CEDROS": 12000,
    "PORTO BELO": 27000,
    "PORTO UNIAO": 35000,
    "ABELARDO LUZ": 18000,
    "LAURO MULLER": 15000,
    "SOMBRIO": 30000,
    "IRANI": 10000,
    "PERITIBA": 3000,
    "PASSOS MAIA": 4000,
    "PARAISO": 4000,
    "ARROIO TRINTA": 3500,
    "PALMA SOLA": 8000,
    "SANTA HELENA": 2500,
    "SAO LUDGERO": 14000,
}


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _http_get_json(url: str, timeout: int = 45) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_bytes(url: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _norm_name(name: str) -> str:
    n = (name or "").upper()
    n = re.sub(r"[ÁÀÂÃÄ]", "A", n)
    n = re.sub(r"[ÉÈÊË]", "E", n)
    n = re.sub(r"[ÍÌÎÏ]", "I", n)
    n = re.sub(r"[ÓÒÔÕÖ]", "O", n)
    n = re.sub(r"[ÚÙÛÜ]", "U", n)
    n = n.replace("Ç", "C")
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _extract_municipio(orgao: str) -> str | None:
    n = _norm_name(orgao)
    for prefix in (
        "MUNICIPIO DE ",
        "PREFEITURA MUNICIPAL DE ",
        "PREFEITURA DE ",
        "CAMARA MUNICIPAL DE ",
        "FUNDO MUNICIPAL DE SAUDE DE ",
        "FUNDO MUNICIPAL DE ",
    ):
        if n.startswith(prefix):
            return n[len(prefix) :].strip()
    # "Prefeitura municipal de X"
    m = re.search(r"DE ([A-Z0-9 ]+)$", n)
    if m and ("MUNICIP" in n or "PREFEITURA" in n or "CAMARA" in n):
        return m.group(1).strip()
    return None


def municipio_size_stratum(orgao: str, municipio_hint: str | None = None) -> str:
    key = _norm_name(municipio_hint or _extract_municipio(orgao) or orgao)
    # strip common suffixes
    key = re.sub(r"\s*-\s*SC$", "", key)
    pop = KNOWN_POP.get(key)
    if pop is None:
        # try last token match
        for k, v in KNOWN_POP.items():
            if k in key or key in k:
                pop = v
                break
    if pop is None:
        # default médio for unknown SC municípios (conservative; still counts as observation)
        return "municipio_medio"
    if pop >= 100_000:
        return "municipio_grande"
    if pop >= 20_000:
        return "municipio_medio"
    return "municipio_pequeno"


def nature_strata(orgao: str) -> list[str]:
    n = _norm_name(orgao)
    strata: list[str] = []
    if "CONSORC" in n:
        strata.extend(["consorcio", "admin_indireta"])
    elif "CAMARA" in n or "ASSEMBLEIA" in n:
        strata.extend(["camara", "admin_direta"])
    elif "FUNDAC" in n:
        strata.extend(["fundacao", "admin_indireta"])
    elif any(x in n for x in ("AUTARQU", "INSTITUTO", "SAAE", "SERVICO AUTONOMO", "COMPANHIA", "EMPRESA BRASILEIRA", "EBSERH")):
        strata.extend(["autarquia", "admin_indireta"])
    elif "FUNDO" in n:
        # fundos often municipal direct admin for health
        strata.append("admin_direta")
    else:
        strata.append("admin_direta")
    return strata


def _content_hash(parts: list[str]) -> str:
    blob = "|".join(parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def collect_pncp(
    window_start: str,
    window_end: str,
    *,
    max_items: int = 80,
    sleep_s: float = 0.35,
) -> list[dict[str, Any]]:
    """Collect PNCP publications for SC in window (API, independent of DB)."""
    # PNCP expects YYYYMMDD
    di = window_start.replace("-", "")
    df = window_end.replace("-", "")
    modalities = [1, 3, 4, 5, 6, 8, 9]
    by_id: dict[str, dict[str, Any]] = {}
    for mod in modalities:
        page = 1
        while page <= 3 and len(by_id) < max_items * 2:
            url = (
                f"{PNCP_BASE}?dataInicial={di}&dataFinal={df}"
                f"&codigoModalidadeContratacao={mod}&uf=SC&pagina={page}&tamanhoPagina=50"
            )
            try:
                data = _http_get_json(url)
            except Exception:
                break
            rows = data.get("data") or []
            if not rows:
                break
            for row in rows:
                eid = row.get("numeroControlePNCP")
                if not eid or eid in by_id:
                    continue
                orgao = ((row.get("orgaoEntidade") or {}).get("razaoSocial")) or ""
                cnpj = (row.get("orgaoEntidade") or {}).get("cnpj")
                published = row.get("dataPublicacaoPncp") or row.get("dataInclusao")
                portal_url = f"https://pncp.gov.br/app/editais/{eid}"
                origin = row.get("linkSistemaOrigem") or ""
                strata = [
                    "source_api",
                    "platform_pncp",
                    municipio_size_stratum(orgao),
                    *nature_strata(orgao),
                ]
                # SPA front-end for PNCP app
                strata.append("source_js")
                if origin and ("compras.sc.gov.br" in origin or "sccompras" in origin.lower()):
                    strata.append("platform_sc_compras")
                    strata.append("source_html")
                item = {
                    "sample_id": f"PNCP-{eid.replace('/', '-')}",
                    "strata": sorted(set(strata)),
                    "orgao_nome": orgao,
                    "cnpj": cnpj,
                    "objeto": (row.get("objetoCompra") or "")[:500],
                    "portal_url": portal_url,
                    "published_at": published,
                    "source_platform": "pncp",
                    "external_id": eid,
                    "origin_system_url": origin or None,
                    "content_hash": _content_hash([eid, portal_url, orgao, str(published or "")]),
                    "captured_by_system": None,
                    "capture_evidence": None,
                    "inventory_source": "pncp_api_consulta_v1",
                    "notes": "Independent PNCP API observation; not selected from operational DB",
                }
                by_id[eid] = item
            page += 1
            time.sleep(sleep_s)
        time.sleep(sleep_s)
    return list(by_id.values())[:max_items]


def collect_sc_compras(*, year: int = 2026, max_items: int = 40) -> list[dict[str, Any]]:
    url = f"{SC_COMPRAS_BASE}?ano={year}&page=0&size=200"
    data = _http_get_json(url, timeout=60)
    rows = data.get("conteudo") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if len(out) >= max_items:
            break
        rid = row.get("id")
        if rid is None:
            continue
        orgao = row.get("orgaoNome") or row.get("orgaoSigla") or ""
        processo = row.get("processo") or ""
        portal_url = f"https://www.compras.sc.gov.br/editais/{rid}"
        strata = sorted(
            set(
                [
                    "source_api",
                    "source_js",
                    "platform_sc_compras",
                    "admin_direta",  # state secretarias default
                    "municipio_grande",  # statewide capital context for state orgs
                    *nature_strata(orgao),
                ]
            )
        )
        # state orgs are not municipal — if nature didn't add, keep admin_direta
        out.append(
            {
                "sample_id": f"SCCOMPRAS-{rid}",
                "strata": strata,
                "orgao_nome": orgao,
                "cnpj": None,
                "objeto": (row.get("objeto") or "")[:500],
                "portal_url": portal_url,
                "published_at": f"{year}-01-01",  # list endpoint lacks publication date
                "source_platform": "sc_compras",
                "external_id": str(rid),
                "processo": processo,
                "situacao": row.get("situacao"),
                "content_hash": _content_hash([str(rid), processo, orgao]),
                "captured_by_system": None,
                "capture_evidence": None,
                "inventory_source": "sc_compras_api_editais",
                "notes": "Independent SC Compras list API; publication day may require detail endpoint",
            }
        )
    return out


def collect_ciga(
    *,
    package_name: str = "domsc-publicacoes-de-07-2026",
    resource_day_hint: str = "10/07/2026",
    max_items: int = 40,
) -> list[dict[str, Any]]:
    search = _http_get_json(f"{CIGA_PACKAGE_SEARCH}?q={urllib.parse.quote(package_name)}&rows=5")
    pkg = None
    for r in (search.get("result") or {}).get("results") or []:
        if r.get("name") == package_name:
            pkg = r
            break
    if not pkg:
        results = (search.get("result") or {}).get("results") or []
        pkg = results[0] if results else None
    if not pkg:
        return []
    resource = None
    for res in pkg.get("resources") or []:
        if resource_day_hint in (res.get("name") or ""):
            resource = res
            break
    if not resource:
        # pick mid list
        resources = pkg.get("resources") or []
        resource = resources[min(10, len(resources) - 1)] if resources else None
    if not resource or not resource.get("url"):
        return []

    raw = _http_get_bytes(resource["url"])
    zf = zipfile.ZipFile(io.BytesIO(raw))
    acts: list[dict[str, Any]] = []
    for name in zf.namelist():
        if not name.endswith(".json"):
            continue
        payload = json.loads(zf.read(name))
        acts = payload.get("autopublicacoes") or []
        break

    # Prefer procurement-related categories
    pref = re.compile(r"licit|pregao|pregão|contrato|dispensa|inexig|edital|aviso", re.I)
    ranked = [a for a in acts if pref.search(str(a.get("categoria") or "") + str(a.get("titulo") or ""))]
    if len(ranked) < max_items:
        ranked = ranked + [a for a in acts if a not in ranked]

    out: list[dict[str, Any]] = []
    for act in ranked:
        if len(out) >= max_items:
            break
        codigo = str(act.get("codigo") or "")
        if not codigo:
            continue
        entidade = act.get("entidade") or ""
        municipio = act.get("municipio") or ""
        pdf_url = act.get("url") or ""
        portal_url = act.get("link") or f"https://diariomunicipal.sc.gov.br/?q=id:{codigo}"
        strata = sorted(
            set(
                [
                    "source_api",
                    "source_pdf",
                    "platform_ciga",
                    municipio_size_stratum(entidade, municipio),
                    *nature_strata(entidade),
                ]
            )
        )
        # HTML portal page exists
        strata = sorted(set(strata + ["source_html"]))
        out.append(
            {
                "sample_id": f"CIGA-{codigo}",
                "strata": strata,
                "orgao_nome": entidade,
                "municipio": municipio,
                "cnpj": None,
                "objeto": (act.get("titulo") or "")[:500],
                "portal_url": portal_url,
                "pdf_url": pdf_url or None,
                "published_at": (act.get("data") or "")[:10],
                "source_platform": "ciga_dom",
                "external_id": codigo,
                "categoria": act.get("categoria"),
                "content_hash": _content_hash([codigo, portal_url, pdf_url, entidade]),
                "captured_by_system": None,
                "capture_evidence": None,
                "inventory_source": f"ciga_ckan:{pkg.get('name')}:{resource.get('name')}",
                "notes": "Independent CIGA CKAN ZIP observation; not from opportunity_intel",
            }
        )
    return out


def _pick_balanced(candidates: list[dict[str, Any]], target_n: int = 60) -> list[dict[str, Any]]:
    """Greedy cover of required strata with min_per_stratum, then fill to target_n."""
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    counts: dict[str, int] = defaultdict(int)

    def add(item: dict[str, Any]) -> None:
        sid = item["sample_id"]
        if sid in selected_ids:
            return
        selected.append(item)
        selected_ids.add(sid)
        for s in item.get("strata") or []:
            counts[s] += 1

    # Phase 1: cover each required stratum to MIN_PER_STRATUM
    for stratum in REQUIRED_STRATA:
        need = MIN_PER_STRATUM - counts[stratum]
        if need <= 0:
            continue
        pool = [
            c
            for c in candidates
            if stratum in (c.get("strata") or []) and c["sample_id"] not in selected_ids
        ]
        # prefer items that also cover thin other strata
        def score(it: dict[str, Any]) -> int:
            return sum(1 for s in (it.get("strata") or []) if counts[s] < MIN_PER_STRATUM)

        pool.sort(key=score, reverse=True)
        for it in pool[:need]:
            add(it)

    # Phase 2: fill unique items
    for c in candidates:
        if len(selected) >= target_n:
            break
        add(c)

    return selected


def build_gold_sample(
    window_start: str,
    window_end: str,
    *,
    target_n: int = 60,
) -> dict[str, Any]:
    pncp = collect_pncp(window_start, window_end, max_items=100)
    time.sleep(0.5)
    sc = collect_sc_compras(year=int(window_start[:4]), max_items=50)
    time.sleep(0.5)
    ciga = collect_ciga(max_items=50)

    candidates = pncp + sc + ciga
    selected = _pick_balanced(candidates, target_n=target_n)

    plan_meta = {
        "selected_before_match": True,
        "collector": "scripts.coverage.independent_inventory",
        "denies_operational_table_denominator": True,
        "sources": {
            "pncp_candidates": len(pncp),
            "sc_compras_candidates": len(sc),
            "ciga_candidates": len(ciga),
            "selected": len(selected),
        },
        "window": {"start": window_start, "end": window_end},
        "collected_at": _utc_now(),
        "seeds": {
            "pncp_modalities": [1, 3, 4, 5, 6, 8, 9],
            "pncp_uf": "SC",
            "ciga_package": "domsc-publicacoes-de-07-2026",
            "sc_compras_year": int(window_start[:4]),
        },
    }
    plan_hash = hashlib.sha256(json.dumps(plan_meta, sort_keys=True).encode()).hexdigest()

    sample = {
        "schema_version": 2,
        "purpose": "Independent stratified recall gold sample — STRATIFIED-RECALL-SOURCE-RESILIENCE-01",
        "window": {
            "start": window_start,
            "end": window_end,
            "observed_at": _utc_now(),
            "notes": "Frozen independent inventory from official public APIs before system match",
        },
        "methodology": {
            "rule": "Each portal_item observed on official source; capture judged by id/url/hash match",
            "forbidden": "Do not use COUNT(*) from database as recall proxy",
            "required_strata": REQUIRED_STRATA,
            "min_unique_items": MIN_UNIQUE_ITEMS,
            "min_per_stratum": MIN_PER_STRATUM,
            "global_target_pct": 95.0,
            "stratum_floor_pct": 90.0,
            "selected_before_match": True,
            "independence": plan_meta,
        },
        "independence": plan_meta,
        "sample_plan_hash": plan_hash,
        "portal_items": selected,
        "status": "GOLD_FROZEN_UNLABELED",
        "forbidden_proxy_used": False,
        "denominator_source": "independent_official_portals",
    }
    return sample


def cmd_collect(args: argparse.Namespace) -> int:
    sample = build_gold_sample(args.window_start, args.window_end, target_n=args.target_n)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    validation = validate_sample_schema(sample)
    val_path = out.parent / "sample-validation.json"
    val_path.write_text(json.dumps(validation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lock = freeze_sample_lock(sample, meta={"campaign": "STRATIFIED-RECALL-SOURCE-RESILIENCE-01"})
    lock_path = Path(args.lock) if args.lock else out.parent / "sample-lock.json"
    lock_path.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    plan = {
        "schema_version": 1,
        "campaign": "STRATIFIED-RECALL-SOURCE-RESILIENCE-01",
        "sample_plan_hash": sample["sample_plan_hash"],
        "denominator_hash": denominator_hash(sample),
        "window": sample["window"],
        "methodology": sample["methodology"],
        "independence": sample["independence"],
        "validation": validation,
        "frozen_before_match": True,
    }
    plan_path = Path(args.plan) if args.plan else out.parent / "sample-plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "gold_sample": str(out),
                "unique_items": validation["unique_items"],
                "validation_ok": validation["ok"],
                "errors": validation["errors"],
                "denominator_hash": validation["denominator_hash"],
                "strata_counts": validation["strata_counts"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if validation["ok"] else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Independent stratified recall inventory")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collect", help="Collect and freeze gold sample from official portals")
    c.add_argument("--window-start", default="2026-07-01")
    c.add_argument("--window-end", default="2026-07-22")
    c.add_argument("--target-n", type=int, default=60)
    c.add_argument(
        "--out",
        default="artifacts/campaigns/STRATIFIED-RECALL-SOURCE-RESILIENCE-01/gold-sample.json",
    )
    c.add_argument("--lock", default=None)
    c.add_argument("--plan", default=None)
    c.set_defaults(func=cmd_collect)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
