"""Selective CNPJ fetch for interest universe when bulk RFB zip is unavailable.

Uses OpenCNPJ redistributor of RFB public cadastral data only as selective filler.
Labels source as rfb_public_cadastral_via_opencnpj (official marker, not bare opencnpj).
Does NOT claim bulk RFB completeness.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.company_registry.normalization import is_valid_cnpj14, normalize_cnae, normalize_cnpj14, normalize_situacao

API = "https://api.opencnpj.org"
UA = "extra-cli-company-registry/1.0 (+selective-rfb-public-via-opencnpj)"
SOURCE_LABEL = "rfb_public_cadastral_via_opencnpj"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fetch_one(cnpj14: str, *, timeout: float = 20.0) -> tuple[str, dict[str, Any] | None]:
    url = f"{API}/{cnpj14}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "NOT_FOUND", None
        if exc.code in {429, 500, 502, 503, 504}:
            return "TRANSIENT", None
        return "TRANSIENT", None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return "TRANSIENT", None
    if not isinstance(raw, dict):
        return "CORRUPT", None

    cnae = raw.get("cnae_principal") or raw.get("cnae_fiscal") or raw.get("cnae")
    if isinstance(cnae, dict):
        cnae = cnae.get("codigo") or cnae.get("code")
    secs: list[str] = []
    for s in raw.get("cnaes_secundarios") or raw.get("cnaes_secundarias") or []:
        if isinstance(s, dict):
            code = s.get("codigo") or s.get("code")
            if code is not None:
                c = normalize_cnae(code)
                if c:
                    secs.append(c)
        elif s:
            c = normalize_cnae(s)
            if c:
                secs.append(c)

    row = {
        "cnpj14": cnpj14,
        "cnpj": cnpj14,
        "razao_social": raw.get("razao_social") or raw.get("nome_empresarial"),
        "legal_name": raw.get("razao_social") or raw.get("nome_empresarial"),
        "nome_fantasia": raw.get("nome_fantasia"),
        "trade_name": raw.get("nome_fantasia"),
        "situacao_cadastral": normalize_situacao(
            raw.get("situacao_cadastral") or raw.get("descricao_situacao_cadastral")
        ),
        "registration_status": normalize_situacao(
            raw.get("situacao_cadastral") or raw.get("descricao_situacao_cadastral")
        ),
        "data_situacao": raw.get("data_situacao_cadastral") or raw.get("data_situacao"),
        "cnae_principal": normalize_cnae(cnae),
        "primary_cnae": normalize_cnae(cnae),
        "cnaes_secundarios": secs,
        "secondary_cnaes": secs,
        "natureza_juridica": raw.get("natureza_juridica")
        or (raw.get("natureza_juridica") if not isinstance(raw.get("natureza_juridica"), dict) else None),
        "porte": raw.get("porte") or raw.get("descricao_porte"),
        "company_size": raw.get("porte") or raw.get("descricao_porte"),
        "capital_social": raw.get("capital_social"),
        "capital": raw.get("capital_social"),
        "municipio": raw.get("municipio") or raw.get("cidade"),
        "city": raw.get("municipio") or raw.get("cidade"),
        "uf": raw.get("uf"),
        "state": raw.get("uf"),
        "logradouro": raw.get("logradouro"),
        "address": raw.get("logradouro"),
        "telefone": raw.get("ddd_telefone_1") or raw.get("telefone"),
        "phone": raw.get("ddd_telefone_1") or raw.get("telefone"),
        "email": raw.get("email"),
        "matriz_filial": raw.get("descricao_identificador_matriz_filial")
        or raw.get("matriz_filial")
        or raw.get("identificador_matriz_filial"),
        "opcao_simples": raw.get("opcao_pelo_simples") or raw.get("simples"),
        "opcao_mei": raw.get("opcao_pelo_mei") or raw.get("mei"),
        "source_distributor": "opencnpj.org",
        "source_authority": "RECEITA_FEDERAL",
        "source_label": SOURCE_LABEL,
    }
    return "OK", row


def fetch_interest_jsonl(
    cnpjs: list[str],
    out_path: Path | str,
    *,
    max_workers: int = 4,
    max_retries: int = 5,
    sleep_between: float = 0.0,
    limit: int | None = None,
    append: bool = False,
    failed_out: Path | str | None = None,
) -> dict[str, Any]:
    """Fetch selective universe and write JSONL for load_jsonl_selective."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in cnpjs:
        c = normalize_cnpj14(raw)
        if not c or not is_valid_cnpj14(c):
            continue
        if c not in seen:
            seen.add(c)
            cleaned.append(c)
    if limit is not None:
        cleaned = cleaned[:limit]

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    stats = {"ok": 0, "not_found": 0, "transient": 0, "corrupt": 0, "invalid_input": 0}
    rows_written = 0
    failed: list[str] = []

    def work(cnpj: str) -> tuple[str, dict[str, Any] | None]:
        last: tuple[str, dict[str, Any] | None] = ("TRANSIENT", None)
        for attempt in range(max_retries):
            status, row = _fetch_one(cnpj, timeout=30.0)
            if status != "TRANSIENT":
                return status, row
            last = status, row
            time.sleep(min(8.0, 0.5 * (2 ** attempt)))
        return last

    mode = "a" if append and out.is_file() else "w"
    with out.open(mode, encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(work, c): c for c in cleaned}
        for fut in as_completed(futs):
            cnpj = futs[fut]
            status, row = fut.result()
            if status == "OK" and row:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                rows_written += 1
                stats["ok"] += 1
            elif status == "NOT_FOUND":
                stats["not_found"] += 1
            elif status == "CORRUPT":
                stats["corrupt"] += 1
                failed.append(cnpj)
            else:
                stats["transient"] += 1
                failed.append(cnpj)
            if sleep_between:
                time.sleep(sleep_between)

    if failed_out is not None:
        Path(failed_out).write_text("\n".join(failed) + ("\n" if failed else ""), encoding="utf-8")

    manifest = {
        "ok": rows_written > 0 or stats["not_found"] > 0,
        "path": str(out),
        "requested": len(cleaned),
        "rows_written": rows_written,
        "stats": stats,
        "failed_n": len(failed),
        "failed_out": str(failed_out) if failed_out else None,
        "source_label": SOURCE_LABEL,
        "source_authority": "RECEITA_FEDERAL",
        "source_distributor": "opencnpj.org",
        "mode": "selective_interest",
        "bulk_completeness_claimed": False,
        "generated_at": utc_now(),
        "reference_date": date.today().isoformat(),
        "note": (
            "Selective redistributor path for commercial interest CNPJs when direct "
            "RFB bulk listing is unreachable. Not a claim of full RFB bulk mirror."
        ),
    }
    side = out.with_suffix(out.suffix + ".manifest.json")
    side.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest
