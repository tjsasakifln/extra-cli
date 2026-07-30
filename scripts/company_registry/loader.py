"""Load RFB extracts into staging SQLite with streaming + optional CNPJ filter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.company_registry.extract import (
    detect_kind_from_name,
    iter_zip_csv_rows,
    parse_domain_pair,
    parse_empresa,
    parse_estabelecimento,
    parse_simples,
)
from scripts.company_registry.integrity import validate_downloaded_file
from scripts.company_registry.normalization import is_valid_cnpj14
from scripts.company_registry.store import (
    connect_db,
    count_table,
    set_meta,
    upsert_companies,
    upsert_establishments,
    upsert_simples,
)


def load_zip_into_db(
    zip_path: Path | str,
    db_path: Path | str,
    *,
    kind_hint: str | None = None,
    interest_cnpjs: set[str] | None = None,
    interest_roots: set[str] | None = None,
    batch_size: int = 2000,
) -> dict[str, Any]:
    """Stream one ZIP into the SQLite DB. Optionally filter by interest set."""
    zip_path = Path(zip_path)
    db_path = Path(db_path)
    validation = validate_downloaded_file(zip_path, expect_zip=True)
    if not validation["ok"]:
        return {
            "ok": False,
            "zip": str(zip_path),
            "errors": validation["errors"],
            "row_counts": {},
            "reject_counts": {},
        }

    kind = kind_hint or detect_kind_from_name(zip_path.name)
    conn = connect_db(db_path)
    row_counts = {"parsed": 0, "upserted": 0}
    reject_counts: dict[str, int] = {}
    batch: list[dict[str, Any]] = []

    def flush_est() -> None:
        nonlocal batch
        if batch:
            row_counts["upserted"] += upsert_establishments(conn, batch)
            conn.commit()
            batch = []

    def flush_emp() -> None:
        nonlocal batch
        if batch:
            row_counts["upserted"] += upsert_companies(conn, batch)
            conn.commit()
            batch = []

    def flush_sim() -> None:
        nonlocal batch
        if batch:
            row_counts["upserted"] += upsert_simples(conn, batch)
            conn.commit()
            batch = []

    try:
        for _member, fields in iter_zip_csv_rows(zip_path):
            row_counts["parsed"] += 1
            if kind == "estabelecimentos" or (
                kind == "unknown" and len(fields) >= 20
            ):
                rec = parse_estabelecimento(fields)
                if not rec:
                    reject_counts["bad_estabelecimento"] = reject_counts.get("bad_estabelecimento", 0) + 1
                    continue
                if interest_cnpjs is not None and rec["cnpj14"] not in interest_cnpjs:
                    if interest_roots is None or rec["cnpj_basico"] not in interest_roots:
                        continue
                if not is_valid_cnpj14(rec["cnpj14"]):
                    reject_counts["invalid_cnpj"] = reject_counts.get("invalid_cnpj", 0) + 1
                    # still store if structurally 14? campaign says reject structurally invalid DV
                    continue
                batch.append(rec)
                if len(batch) >= batch_size:
                    flush_est()
            elif kind == "empresas" or (kind == "unknown" and len(fields) <= 10 and len(fields) >= 2):
                rec = parse_empresa(fields)
                if not rec:
                    reject_counts["bad_empresa"] = reject_counts.get("bad_empresa", 0) + 1
                    continue
                if interest_roots is not None and rec["cnpj_basico"] not in interest_roots:
                    # also allow if any interest cnpj shares root
                    if interest_cnpjs is not None:
                        if not any(c.startswith(rec["cnpj_basico"]) for c in interest_cnpjs):
                            continue
                    else:
                        continue
                batch.append(rec)
                if len(batch) >= batch_size:
                    flush_emp()
            elif kind == "simples":
                rec = parse_simples(fields)
                if not rec:
                    reject_counts["bad_simples"] = reject_counts.get("bad_simples", 0) + 1
                    continue
                if interest_roots is not None and rec["cnpj_basico"] not in interest_roots:
                    continue
                batch.append(rec)
                if len(batch) >= batch_size:
                    flush_sim()
            elif kind in {"municipios", "cnaes", "naturezas", "motivos", "paises", "qualificacoes"}:
                pair = parse_domain_pair(fields)
                if not pair:
                    continue
                table = {
                    "municipios": "domain_municipio",
                    "cnaes": "domain_cnae",
                    "naturezas": "domain_natureza",
                    "motivos": "domain_motivo",
                }.get(kind)
                if table:
                    conn.execute(
                        f"INSERT OR REPLACE INTO {table}(code, {'name' if table=='domain_municipio' else 'description'}) VALUES(?,?)",  # noqa: S608
                        (pair["code"], pair["description"]),
                    )
            # socios skipped for commercial v1 unless needed
        if kind in {"estabelecimentos", "unknown"}:
            flush_est()
        if kind in {"empresas", "unknown"}:
            flush_emp()
        if kind == "simples":
            flush_sim()
        conn.commit()
        # resolve municipio names if domain loaded
        try:
            conn.execute(
                """
                UPDATE establishments
                SET municipio = (
                    SELECT name FROM domain_municipio m
                    WHERE m.code = establishments.municipio_code
                )
                WHERE municipio IS NULL AND municipio_code IS NOT NULL
                """
            )
            conn.commit()
        except Exception:
            pass
        set_meta(conn, f"loaded:{zip_path.name}", {"kind": kind, "ok": True})
        conn.commit()
        return {
            "ok": True,
            "zip": str(zip_path),
            "kind": kind,
            "row_counts": row_counts,
            "reject_counts": reject_counts,
            "db_counts": {
                "establishments": count_table(conn, "establishments"),
                "companies": count_table(conn, "companies"),
                "simples": count_table(conn, "simples"),
            },
        }
    finally:
        conn.close()


def load_jsonl_selective(
    jsonl_path: Path | str,
    db_path: Path | str,
    *,
    source_label: str = "rfb_public_cadastral",
) -> dict[str, Any]:
    """Load pre-normalized JSONL (operator extract / selective redistributor) into DB."""
    path = Path(jsonl_path)
    conn = connect_db(db_path)
    n_est = 0
    n_emp = 0
    rejects = 0
    batch_est: list[dict[str, Any]] = []
    batch_emp: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                rejects += 1
                continue
            cnpj = row.get("cnpj14") or row.get("cnpj")
            from scripts.company_registry.normalization import normalize_cnpj14

            cnpj14 = normalize_cnpj14(cnpj)
            if not cnpj14 or not is_valid_cnpj14(cnpj14):
                rejects += 1
                continue
            basico = cnpj14[:8]
            batch_est.append(
                {
                    "cnpj14": cnpj14,
                    "cnpj_basico": basico,
                    "cnpj_ordem": cnpj14[8:12],
                    "cnpj_dv": cnpj14[12:14],
                    "matriz_filial": row.get("matriz_filial") or row.get("headquarters_or_branch"),
                    "nome_fantasia": row.get("nome_fantasia") or row.get("trade_name"),
                    "situacao_cadastral": row.get("situacao_cadastral")
                    or row.get("registration_status"),
                    "data_situacao": row.get("data_situacao")
                    or row.get("registration_status_date"),
                    "motivo_situacao": row.get("motivo_situacao"),
                    "data_inicio": row.get("data_inicio"),
                    "cnae_principal": row.get("cnae_principal") or row.get("primary_cnae"),
                    "cnaes_secundarios": row.get("cnaes_secundarios")
                    or row.get("secondary_cnaes")
                    or [],
                    "tipo_logradouro": None,
                    "logradouro": row.get("logradouro") or row.get("address"),
                    "numero": row.get("numero"),
                    "complemento": row.get("complemento"),
                    "bairro": row.get("bairro"),
                    "cep": row.get("cep"),
                    "uf": row.get("uf") or row.get("state"),
                    "municipio_code": row.get("municipio_code"),
                    "municipio": row.get("municipio") or row.get("city"),
                    "ddd1": None,
                    "telefone1": row.get("telefone") or row.get("phone"),
                    "email": row.get("email"),
                }
            )
            batch_emp.append(
                {
                    "cnpj_basico": basico,
                    "razao_social": row.get("razao_social") or row.get("legal_name"),
                    "natureza_juridica": row.get("natureza_juridica") or row.get("legal_nature"),
                    "qualificacao_responsavel": None,
                    "capital_social": row.get("capital_social") or row.get("capital"),
                    "porte": row.get("porte") or row.get("company_size"),
                    "ente_federativo": None,
                }
            )
            if row.get("opcao_simples") is not None or row.get("simples") is not None:
                sim = "S" if row.get("simples") is True or str(row.get("opcao_simples")).upper() in {
                    "S",
                    "SIM",
                    "TRUE",
                    "1",
                } else str(row.get("opcao_simples") or "")
                mei = "S" if row.get("mei") is True or str(row.get("opcao_mei")).upper() in {
                    "S",
                    "SIM",
                    "TRUE",
                    "1",
                } else str(row.get("opcao_mei") or "")
                upsert_simples(
                    conn,
                    [
                        {
                            "cnpj_basico": basico,
                            "opcao_simples": sim or None,
                            "data_opcao_simples": None,
                            "data_exclusao_simples": None,
                            "opcao_mei": mei or None,
                            "data_opcao_mei": None,
                            "data_exclusao_mei": None,
                        }
                    ],
                )
            if len(batch_est) >= 500:
                n_est += upsert_establishments(conn, batch_est)
                n_emp += upsert_companies(conn, batch_emp)
                conn.commit()
                batch_est, batch_emp = [], []
    if batch_est:
        n_est += upsert_establishments(conn, batch_est)
        n_emp += upsert_companies(conn, batch_emp)
        conn.commit()
    set_meta(conn, "source_label", source_label)
    set_meta(conn, "load_mode", "jsonl_selective")
    conn.commit()
    out = {
        "ok": True,
        "path": str(path),
        "establishments_upserted": n_est,
        "companies_upserted": n_emp,
        "rejects": rejects,
        "db_counts": {
            "establishments": count_table(conn, "establishments"),
            "companies": count_table(conn, "companies"),
        },
        "source_label": source_label,
    }
    conn.close()
    return out
