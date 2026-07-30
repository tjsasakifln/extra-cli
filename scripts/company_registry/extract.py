"""Stream extract RFB ZIP (CSV semicolon latin-1) without loading all into RAM."""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from scripts.company_registry.normalization import (
    compose_cnpj14,
    normalize_cnae,
    normalize_situacao,
    parse_money_br,
)


def _open_zip_text(zf: zipfile.ZipFile, member: str) -> io.TextIOWrapper:
    raw = zf.open(member, "r")
    return io.TextIOWrapper(raw, encoding="latin-1", errors="replace", newline="")


def iter_zip_csv_rows(
    zip_path: Path | str,
    *,
    delimiter: str = ";",
) -> Iterator[tuple[str, list[str]]]:
    """Yield (member_name, fields) for every CSV row in the zip."""
    path = Path(zip_path)
    with zipfile.ZipFile(path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            # RFB members often have no extension
            with _open_zip_text(zf, info.filename) as fh:
                reader = csv.reader(fh, delimiter=delimiter)
                for row in reader:
                    if not row or all(not (c or "").strip() for c in row):
                        continue
                    yield info.filename, row


def parse_estabelecimento(fields: list[str]) -> dict[str, Any] | None:
    """Parse RFB Estabelecimentos layout (fixed column order)."""
    if len(fields) < 20:
        return None
    cnpj14 = compose_cnpj14(fields[0], fields[1], fields[2])
    if not cnpj14:
        return None
    secs_raw = fields[12] if len(fields) > 12 else ""
    secondary = []
    if secs_raw:
        for part in secs_raw.split(","):
            c = normalize_cnae(part)
            if c:
                secondary.append(c)
    phone = None
    ddd1 = fields[21] if len(fields) > 21 else None
    tel1 = fields[22] if len(fields) > 22 else None
    if ddd1 or tel1:
        phone = f"{(ddd1 or '').strip()}{(tel1 or '').strip()}".strip() or None
    email = (fields[27] if len(fields) > 27 else None) or None
    if email:
        email = email.strip() or None
    return {
        "cnpj14": cnpj14,
        "cnpj_basico": str(fields[0]).zfill(8)[-8:],
        "cnpj_ordem": str(fields[1]).zfill(4)[-4:],
        "cnpj_dv": str(fields[2]).zfill(2)[-2:],
        "matriz_filial": fields[3] if len(fields) > 3 else None,
        "nome_fantasia": (fields[4] or None) if len(fields) > 4 else None,
        "situacao_cadastral": normalize_situacao(fields[5]) if len(fields) > 5 else None,
        "data_situacao": _date(fields[6]) if len(fields) > 6 else None,
        "motivo_situacao": fields[7] if len(fields) > 7 else None,
        "data_inicio": _date(fields[10]) if len(fields) > 10 else None,
        "cnae_principal": normalize_cnae(fields[11]) if len(fields) > 11 else None,
        "cnaes_secundarios": secondary,
        "tipo_logradouro": fields[13] if len(fields) > 13 else None,
        "logradouro": fields[14] if len(fields) > 14 else None,
        "numero": fields[15] if len(fields) > 15 else None,
        "complemento": fields[16] if len(fields) > 16 else None,
        "bairro": fields[17] if len(fields) > 17 else None,
        "cep": fields[18] if len(fields) > 18 else None,
        "uf": fields[19] if len(fields) > 19 else None,
        "municipio_code": fields[20] if len(fields) > 20 else None,
        "municipio": None,
        "ddd1": ddd1,
        "telefone1": phone,
        "email": email,
    }


def parse_empresa(fields: list[str]) -> dict[str, Any] | None:
    if len(fields) < 2:
        return None
    basico = str(fields[0]).zfill(8)[-8:]
    return {
        "cnpj_basico": basico,
        "razao_social": fields[1] or None,
        "natureza_juridica": fields[2] if len(fields) > 2 else None,
        "qualificacao_responsavel": fields[3] if len(fields) > 3 else None,
        "capital_social": parse_money_br(fields[4]) if len(fields) > 4 else None,
        "porte": fields[5] if len(fields) > 5 else None,
        "ente_federativo": fields[6] if len(fields) > 6 else None,
    }


def parse_simples(fields: list[str]) -> dict[str, Any] | None:
    if len(fields) < 2:
        return None
    basico = str(fields[0]).zfill(8)[-8:]
    return {
        "cnpj_basico": basico,
        "opcao_simples": fields[1] if len(fields) > 1 else None,
        "data_opcao_simples": _date(fields[2]) if len(fields) > 2 else None,
        "data_exclusao_simples": _date(fields[3]) if len(fields) > 3 else None,
        "opcao_mei": fields[4] if len(fields) > 4 else None,
        "data_opcao_mei": _date(fields[5]) if len(fields) > 5 else None,
        "data_exclusao_mei": _date(fields[6]) if len(fields) > 6 else None,
    }


def parse_domain_pair(fields: list[str]) -> dict[str, str] | None:
    if len(fields) < 2:
        return None
    return {"code": str(fields[0]).strip(), "description": str(fields[1]).strip()}


def _date(raw: str | None) -> str | None:
    if not raw:
        return None
    s = str(raw).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    if s in {"0", "00000000"}:
        return None
    return s or None


def detect_kind_from_name(name: str) -> str:
    n = name.lower()
    if "estabelecimento" in n:
        return "estabelecimentos"
    if "empresa" in n:
        return "empresas"
    if "socio" in n or "sócio" in n:
        return "socios"
    if "simples" in n:
        return "simples"
    if "cnae" in n:
        return "cnaes"
    if "municip" in n:
        return "municipios"
    if "natureza" in n:
        return "naturezas"
    if "motivo" in n:
        return "motivos"
    if "pais" in n or "paise" in n:
        return "paises"
    if "qualific" in n:
        return "qualificacoes"
    return "unknown"
