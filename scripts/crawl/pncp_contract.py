from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import IntEnum


class ModalidadePNCP(IntEnum):
    LEILAO_ELETRONICO = 1
    DIALOGO_COMPETITIVO = 2
    CONCURSO = 3
    CONCORRENCIA_ELETRONICA = 4
    CONCORRENCIA_PRESENCIAL = 5
    PREGAO_ELETRONICO = 6
    PREGAO_PRESENCIAL = 7
    DISPENSA = 8
    INEXIGIBILIDADE = 9
    MANIFESTACAO_INTERESSE = 10
    PRE_QUALIFICACAO = 11
    CREDENCIAMENTO = 12
    LEILAO_PRESENCIAL = 13
    INAPLICABILIDADE_LICITACAO = 14
    CHAMADA_PUBLICA = 15
    CONCORRENCIA_ELETRONICA_INTERNACIONAL = 16
    CONCORRENCIA_PRESENCIAL_INTERNACIONAL = 17
    PREGAO_ELETRONICO_INTERNACIONAL = 18
    PREGAO_PRESENCIAL_INTERNACIONAL = 19


PNCP_CONSULTA_BASE = os.getenv("PNCP_CONSULTA_BASE", "https://pncp.gov.br/api/consulta/v1")
PNCP_API_BASE = os.getenv("PNCP_API_BASE", "https://pncp.gov.br/api/pncp/v1")
PNCP_DATE_FORMAT = "%Y%m%d"
PNCP_TAMANHO_PAGINA_MIN = 10
PNCP_TAMANHO_PAGINA_MAX = 50
PNCP_SAFE_WINDOW_DAYS = int(os.getenv("PNCP_SAFE_WINDOW_DAYS", "7"))

DEFAULT_MODALIDADES = tuple(mod.value for mod in ModalidadePNCP)


class PNCPTargetError(ValueError):
    pass


@dataclass(frozen=True)
class PNCPTarget:
    kind: str
    value: str | None = None


def parse_target(value: str | None) -> PNCPTarget:
    if value is None or not value.strip():
        return PNCPTarget("sc")

    target = value.strip()
    lower = target.lower()

    if lower in {"sc", "within_200km", "engineering"}:
        return PNCPTarget(lower)

    if lower.startswith("municipio:"):
        code = digits_only(target.split(":", 1)[1])
        if len(code) != 7:
            raise PNCPTargetError("municipio:<codigo_ibge> exige codigo IBGE com 7 digitos")
        return PNCPTarget("municipio", code)

    if lower.startswith("municipio_nome:"):
        name = target.split(":", 1)[1].strip()
        if not name:
            raise PNCPTargetError("municipio_nome:<nome> exige um nome de municipio")
        return PNCPTarget("municipio_nome", name)

    if lower.startswith("cnpj:"):
        cnpj = digits_only(target.split(":", 1)[1])
        if len(cnpj) != 14:
            raise PNCPTargetError("cnpj:<cnpj> exige CNPJ com 14 digitos")
        return PNCPTarget("cnpj", cnpj)

    raise PNCPTargetError(
        "target invalido. Use um de: sc, within_200km, municipio:<ibge>, "
        "municipio_nome:<nome>, cnpj:<cnpj>, engineering"
    )


def digits_only(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\D", "", value)


def format_pncp_date(day: date) -> str:
    return day.strftime(PNCP_DATE_FORMAT)


def parse_modalidades_from_env(raw: str | None = None) -> tuple[int, ...]:
    if raw is None:
        raw = os.getenv("INGESTION_MODALIDADES")
    if not raw:
        return DEFAULT_MODALIDADES

    parsed: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        code = int(part)
        ModalidadePNCP(code)
        parsed.append(code)
    return tuple(dict.fromkeys(parsed))


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    ascii_only = ascii_only.lower()
    ascii_only = re.sub(r"[^a-z0-9]+", " ", ascii_only)
    return re.sub(r"\s+", " ", ascii_only).strip()


def build_pncp_public_link(
    *,
    orgao_cnpj: str | None,
    ano_compra: int | str | None,
    sequencial_compra: int | str | None,
) -> str | None:
    cnpj = digits_only(orgao_cnpj)
    if len(cnpj) != 14 or ano_compra in (None, "") or sequencial_compra in (None, ""):
        return None
    return f"https://pncp.gov.br/app/editais/{cnpj}/{int(ano_compra)}/{int(sequencial_compra)}"


def explain_modalidades(modalidades: Iterable[int]) -> list[str]:
    return [f"{code}:{ModalidadePNCP(code).name}" for code in modalidades]
