"""Typed CNPJ lookup against the active (or specified) official release."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.company_registry.models import OfficialCompanyRecord, OfficialMatchStatus
from scripts.company_registry.normalization import is_valid_cnpj14, normalize_cnpj14
from scripts.company_registry.paths import active_pointer_path, db_path_for_release
from scripts.company_registry.store import connect_db, get_meta, lookup_row


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_active_pointer() -> dict[str, Any] | None:
    p = active_pointer_path()
    if not p.is_file():
        return None
    import json

    return json.loads(p.read_text(encoding="utf-8"))


def resolve_db_path(release_id: str | None = None) -> tuple[Path | None, str | None, str | None]:
    """Return (db_path, release_id, error_status)."""
    if release_id:
        path = db_path_for_release(release_id, staging=False)
        if path.is_file():
            return path, release_id, None
        # also try staging
        sp = db_path_for_release(release_id, staging=True)
        if sp.is_file():
            return sp, release_id, None
        return None, release_id, OfficialMatchStatus.OFFICIAL_REGISTRY_UNAVAILABLE.value
    ptr = read_active_pointer()
    if not ptr or ptr.get("status") != "ACTIVE":
        return None, None, OfficialMatchStatus.OFFICIAL_REGISTRY_UNAVAILABLE.value
    rid = ptr.get("release_id")
    path = Path(ptr["database_path"]) if ptr.get("database_path") else db_path_for_release(str(rid))
    if not path.is_file():
        return None, rid, OfficialMatchStatus.OFFICIAL_REGISTRY_UNAVAILABLE.value
    return path, str(rid), None


def lookup_cnpj(
    cnpj: str | None,
    *,
    release_id: str | None = None,
) -> OfficialCompanyRecord:
    if cnpj is None or str(cnpj).strip() == "":
        return OfficialCompanyRecord(
            cnpj="",
            official_match_status=OfficialMatchStatus.MISSING_CNPJ.value,
            official_authority=None,
            official_release_id=None,
            source_provenance={"reason": "missing_input"},
        )
    cnpj14 = normalize_cnpj14(cnpj)
    if not cnpj14:
        return OfficialCompanyRecord(
            cnpj=str(cnpj),
            official_match_status=OfficialMatchStatus.INVALID_CNPJ.value,
            official_authority=None,
            source_provenance={"reason": "structural_length"},
        )
    if not is_valid_cnpj14(cnpj14):
        return OfficialCompanyRecord(
            cnpj=cnpj14,
            official_match_status=OfficialMatchStatus.INVALID_CNPJ.value,
            official_authority=None,
            source_provenance={"reason": "invalid_check_digits"},
        )

    db_path, rid, err = resolve_db_path(release_id)
    if err or db_path is None:
        return OfficialCompanyRecord(
            cnpj=cnpj14,
            official_match_status=OfficialMatchStatus.OFFICIAL_REGISTRY_UNAVAILABLE.value,
            official_authority="RECEITA_FEDERAL",
            official_release_id=rid,
            source_provenance={"reason": "no_active_release"},
        )

    conn = connect_db(db_path, readonly=True)
    try:
        row = lookup_row(conn, cnpj14)
        source_label = get_meta(conn, "source_label", "rfb_public_cadastral")
        if not row:
            return OfficialCompanyRecord(
                cnpj=cnpj14,
                official_match_status=OfficialMatchStatus.NOT_FOUND_IN_OFFICIAL_RELEASE.value,
                official_authority="RECEITA_FEDERAL",
                official_release_id=rid,
                cnpj_root=cnpj14[:8],
                fetched_from_local_registry_at=utc_now(),
                source_provenance={
                    "release_id": rid,
                    "database_path": str(db_path),
                    "source_label": source_label,
                },
            )
        matriz = row.get("matriz_filial")
        hq = None
        if str(matriz) == "1":
            hq = "MATRIZ"
        elif str(matriz) == "2":
            hq = "FILIAL"
        elif matriz:
            hq = str(matriz)
        simples = row.get("opcao_simples")
        mei = row.get("opcao_mei")
        return OfficialCompanyRecord(
            cnpj=cnpj14,
            official_match_status=OfficialMatchStatus.MATCHED.value,
            official_authority="RECEITA_FEDERAL",
            official_release_id=rid,
            legal_name=row.get("razao_social"),
            trade_name=row.get("nome_fantasia"),
            registration_status=row.get("situacao_cadastral"),
            registration_status_date=row.get("data_situacao"),
            registration_status_reason=row.get("motivo_situacao"),
            primary_cnae=row.get("cnae_principal"),
            secondary_cnaes=list(row.get("cnaes_secundarios") or []),
            legal_nature=row.get("natureza_juridica"),
            company_size=row.get("porte"),
            capital=row.get("capital_social"),
            headquarters_or_branch=hq,
            city=row.get("municipio"),
            state=row.get("uf"),
            address=row.get("logradouro"),
            phone=row.get("telefone1"),
            email=row.get("email"),
            simples=_yn(simples),
            mei=_yn(mei),
            cnpj_root=cnpj14[:8],
            fetched_from_local_registry_at=utc_now(),
            source_provenance={
                "release_id": rid,
                "database_path": str(db_path),
                "source_label": source_label,
                "authority": "RECEITA_FEDERAL",
            },
        )
    finally:
        conn.close()


def _yn(v: Any) -> bool | None:
    if v is None or v == "":
        return None
    s = str(v).strip().upper()
    if s in {"S", "SIM", "TRUE", "1", "Y"}:
        return True
    if s in {"N", "NAO", "NÃO", "FALSE", "0"}:
        return False
    return None


def batch_lookup(
    cnpjs: list[str],
    *,
    release_id: str | None = None,
) -> dict[str, OfficialCompanyRecord]:
    out: dict[str, OfficialCompanyRecord] = {}
    for c in cnpjs:
        rec = lookup_cnpj(c, release_id=release_id)
        key = rec.cnpj or str(c)
        out[key] = rec
    return out
