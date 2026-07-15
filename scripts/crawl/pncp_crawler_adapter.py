from __future__ import annotations

import json
import logging
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

from scripts.crawl.common import safe_date, safe_float
from scripts.crawl.ingestion._base.crawler import CrawlRequest, FetchResult
from scripts.crawl.pncp_contract import (
    DEFAULT_MODALIDADES,
    PNCP_CONSULTA_BASE,
    PNCP_SAFE_WINDOW_DAYS,
    PNCP_TAMANHO_PAGINA_MAX,
    PNCP_TAMANHO_PAGINA_MAX_CONTRATOS,
    PNCP_TAMANHO_PAGINA_MIN,
    build_pncp_public_link,
    digits_only,
    format_pncp_date,
    parse_modalidades_from_env,
    parse_target,
)
from scripts.crawl.security import USER_AGENT

_logger = logging.getLogger(__name__)

PNCP_PAGE_SIZE = max(
    PNCP_TAMANHO_PAGINA_MIN,
    min(PNCP_TAMANHO_PAGINA_MAX, int(os.getenv("PNCP_PAGE_SIZE", str(PNCP_TAMANHO_PAGINA_MAX)))),
)
PNCP_CONTRATOS_PAGE_SIZE = max(
    PNCP_TAMANHO_PAGINA_MIN,
    min(
        PNCP_TAMANHO_PAGINA_MAX_CONTRATOS,
        int(os.getenv("PNCP_CONTRATOS_PAGE_SIZE", str(PNCP_TAMANHO_PAGINA_MAX_CONTRATOS))),
    ),
)
PNCP_MAX_PAGES = int(os.getenv("PNCP_MAX_PAGES", "200"))
PNCP_READ_TIMEOUT = int(os.getenv("PNCP_READ_TIMEOUT", "120"))
PNCP_MAX_RETRIES = int(os.getenv("PNCP_MAX_RETRIES", "3"))
PNCP_REQUEST_DELAY = float(os.getenv("PNCP_REQUEST_DELAY", "0.5"))
INGESTION_INCREMENTAL_DAYS = int(os.getenv("INGESTION_INCREMENTAL_DAYS", "1"))
INGESTION_DATE_RANGE_DAYS = int(os.getenv("INGESTION_DATE_RANGE_DAYS", "30"))
INGESTION_MODALIDADES = parse_modalidades_from_env()
UPSERT_FUNCTION = "upsert_pncp_raw_bids"


def _windowed_dates(date_from: date, date_to: date) -> list[tuple[date, date]]:
    windows: list[tuple[date, date]] = []
    cursor = date_from
    while cursor <= date_to:
        window_end = min(cursor + timedelta(days=PNCP_SAFE_WINDOW_DAYS - 1), date_to)
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def _request_params(request: CrawlRequest, modalidade: int, page: int) -> dict[str, str]:
    target = parse_target(request.target)
    if request.date_from and request.date_to and request.date_from > request.date_to:
        raise ValueError("date_from deve ser menor ou igual a date_to")

    params = {
        "dataInicial": format_pncp_date(request.date_from or date.today()),
        "dataFinal": format_pncp_date(request.date_to or request.date_from or date.today()),
        "codigoModalidadeContratacao": str(modalidade),
        "pagina": str(page),
        "tamanhoPagina": str(PNCP_PAGE_SIZE),
    }

    if target.kind in {"sc", "within_200km", "engineering", "municipio_nome"}:
        params["uf"] = "SC"
    elif target.kind == "municipio":
        params["codigoMunicipioIbge"] = target.value or ""
    elif target.kind == "cnpj":
        params["cnpj"] = target.value or ""

    return params


def _http_get_json(url: str) -> FetchResult:
    metadata = {"url": url, "retries": 0}

    for attempt in range(PNCP_MAX_RETRIES + 1):
        metadata["retries"] = attempt
        try:
            req = urllib.request.Request(  # noqa: S310 — hardcoded HTTPS PNCP API endpoint (callers use https://pncp.gov.br)
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=PNCP_READ_TIMEOUT) as response:  # noqa: S310 — hardcoded HTTPS PNCP API endpoint
                status = response.status
                raw_body = response.read()

            if status == 204:
                return FetchResult(
                    records=[],
                    request_completed=True,
                    http_status=204,
                    empty_confirmed=True,
                    metadata=metadata,
                )

            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError as exc:
                return FetchResult(
                    records=[],
                    request_completed=True,
                    http_status=status,
                    empty_confirmed=False,
                    errors=[f"JSON invalido: {exc}"],
                    metadata=metadata,
                )

            if status == 200:
                records = payload.get("data", []) if isinstance(payload, dict) else []
                is_empty = bool(isinstance(payload, dict) and payload.get("empty")) or not records
                metadata["pagination"] = {
                    "totalRegistros": payload.get("totalRegistros") if isinstance(payload, dict) else None,
                    "totalPaginas": payload.get("totalPaginas") if isinstance(payload, dict) else None,
                    "numeroPagina": payload.get("numeroPagina") if isinstance(payload, dict) else None,
                    "paginasRestantes": payload.get("paginasRestantes") if isinstance(payload, dict) else None,
                    "empty": payload.get("empty") if isinstance(payload, dict) else None,
                }
                return FetchResult(
                    records=records if isinstance(records, list) else [],
                    request_completed=True,
                    http_status=200,
                    empty_confirmed=is_empty,
                    metadata=metadata,
                )

            return FetchResult(
                records=[],
                request_completed=True,
                http_status=status,
                empty_confirmed=False,
                errors=[f"HTTP {status} inesperado"],
                metadata=metadata,
            )
        except urllib.error.HTTPError as exc:
            status = exc.code
            if status == 429 and attempt < PNCP_MAX_RETRIES:
                retry_after = exc.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else min(30.0, 2**attempt)
                time.sleep(wait)
                continue

            label = "falha externa"
            if status in {400, 404, 422}:
                label = "erro de requisicao"
            elif status >= 500:
                label = "falha externa"
            return FetchResult(
                records=[],
                request_completed=True,
                http_status=status,
                empty_confirmed=False,
                errors=[f"{label}: HTTP {status}"],
                metadata=metadata,
            )
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, socket.gaierror):
                error = f"falha de conectividade: DNS {reason}"
            elif isinstance(reason, TimeoutError):
                error = "falha de conectividade: timeout"
            else:
                error = f"falha de conectividade: {reason}"
            if attempt < PNCP_MAX_RETRIES:
                time.sleep(min(10.0, 1 + attempt))
                continue
            return FetchResult(
                records=[],
                request_completed=False,
                http_status=None,
                empty_confirmed=False,
                errors=[error],
                metadata=metadata,
            )
        except TimeoutError:
            if attempt < PNCP_MAX_RETRIES:
                time.sleep(min(10.0, 1 + attempt))
                continue
            return FetchResult(
                records=[],
                request_completed=False,
                http_status=None,
                empty_confirmed=False,
                errors=["falha de conectividade: timeout"],
                metadata=metadata,
            )

    return FetchResult(
        records=[],
        request_completed=False,
        http_status=None,
        empty_confirmed=False,
        errors=["falha externa: retries esgotados"],
        metadata=metadata,
    )


def _http_get_payload(url: str) -> tuple[Any | None, FetchResult]:
    metadata = {"url": url, "retries": 0}

    for attempt in range(PNCP_MAX_RETRIES + 1):
        metadata["retries"] = attempt
        try:
            req = urllib.request.Request(  # noqa: S310 — hardcoded HTTPS PNCP API endpoint (callers use https://pncp.gov.br)
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=PNCP_READ_TIMEOUT) as response:  # noqa: S310 — hardcoded HTTPS PNCP API endpoint
                payload = json.loads(response.read().decode("utf-8"))
            return payload, FetchResult(
                records=[payload] if isinstance(payload, dict) else (payload if isinstance(payload, list) else []),
                request_completed=True,
                http_status=200,
                empty_confirmed=(not payload),
                metadata=metadata,
            )
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < PNCP_MAX_RETRIES:
                wait = min(30.0, 2 ** (attempt + 1))
                time.sleep(wait)
                continue
            return None, FetchResult(
                records=[],
                request_completed=True,
                http_status=exc.code,
                empty_confirmed=False,
                errors=[f"HTTP {exc.code}"],
                metadata=metadata,
            )
        except urllib.error.URLError as exc:
            if attempt < PNCP_MAX_RETRIES:
                time.sleep(min(10.0, 1 + attempt))
                continue
            return None, FetchResult(
                records=[],
                request_completed=False,
                http_status=None,
                empty_confirmed=False,
                errors=[f"falha de conectividade: {exc.reason}"],
                metadata=metadata,
            )
        except json.JSONDecodeError as exc:
            return None, FetchResult(
                records=[],
                request_completed=True,
                http_status=200,
                empty_confirmed=False,
                errors=[f"JSON invalido: {exc}"],
                metadata=metadata,
            )

    return None, FetchResult(
        records=[],
        request_completed=False,
        http_status=None,
        empty_confirmed=False,
        errors=["falha externa: retries esgotados"],
        metadata=metadata,
    )


def _fetch_publication_page(request: CrawlRequest, modalidade: int, page: int) -> FetchResult:
    params = _request_params(request, modalidade, page)
    url = f"{PNCP_CONSULTA_BASE}/contratacoes/publicacao?{urllib.parse.urlencode(params)}"
    result = _http_get_json(url)
    result.metadata["params"] = params
    return result


def _derive_request(mode: str | CrawlRequest) -> CrawlRequest:
    if isinstance(mode, CrawlRequest):
        request = mode
    else:
        if mode == "incremental":
            start = date.today() - timedelta(days=INGESTION_INCREMENTAL_DAYS - 1)
            request = CrawlRequest(mode=mode, date_from=start, date_to=date.today())
        else:
            start = date.today() - timedelta(days=INGESTION_DATE_RANGE_DAYS - 1)
            request = CrawlRequest(mode=mode, date_from=start, date_to=date.today())

    if request.date_from is None and request.date_to is None:
        end = date.today()
        days = INGESTION_INCREMENTAL_DAYS if request.mode == "incremental" else INGESTION_DATE_RANGE_DAYS
        request = CrawlRequest(
            mode=request.mode,
            date_from=end - timedelta(days=days - 1),
            date_to=end,
            target=request.target,
            limit=request.limit,
        )
    elif request.date_from is not None and request.date_to is None:
        request = CrawlRequest(
            mode=request.mode,
            date_from=request.date_from,
            date_to=request.date_from,
            target=request.target,
            limit=request.limit,
        )

    parse_target(request.target)
    return request


def _synthetic_pncp_id(raw: dict[str, Any]) -> tuple[str, bool, str]:
    base = "|".join(
        [
            digits_only(((raw.get("orgaoEntidade") or {}).get("cnpj")) or raw.get("orgao_cnpj")),
            str(raw.get("anoCompra") or ""),
            str(raw.get("sequencialCompra") or ""),
            str(raw.get("dataPublicacaoPncp") or ""),
            str(raw.get("objetoCompra") or ""),
        ]
    )
    import hashlib

    return hashlib.sha256(base.encode("utf-8")).hexdigest(), True, "numeroControlePNCP ausente"


def crawl(mode: str | CrawlRequest = "full") -> FetchResult:
    request = _derive_request(mode)
    if request.date_from is None or request.date_to is None:
        raise ValueError("CrawlRequest precisa de date_from e date_to resolvidos")

    all_records: list[dict[str, Any]] = []
    errors: list[str] = []
    metadata: dict[str, Any] = {
        "endpoint": f"{PNCP_CONSULTA_BASE}/contratacoes/publicacao",
        "modalidades": list(INGESTION_MODALIDADES or DEFAULT_MODALIDADES),
        "target": asdict(parse_target(request.target)),
        "windows": [],
        "pages_fetched": 0,
    }
    completed_any = False
    empty_confirmed = True

    for window_start, window_end in _windowed_dates(request.date_from, request.date_to):
        metadata["windows"].append({"date_from": window_start.isoformat(), "date_to": window_end.isoformat()})
        for modalidade in INGESTION_MODALIDADES or DEFAULT_MODALIDADES:
            page = 1
            while page <= PNCP_MAX_PAGES:
                page_request = CrawlRequest(
                    mode=request.mode,
                    date_from=window_start,
                    date_to=window_end,
                    target=request.target,
                    limit=request.limit,
                )
                result = _fetch_publication_page(page_request, modalidade, page)
                metadata["pages_fetched"] += 1

                if result.request_completed:
                    completed_any = True
                if result.errors:
                    errors.extend(result.errors)
                    empty_confirmed = False
                    break

                if result.records:
                    all_records.extend(result.records)
                    empty_confirmed = False
                elif not result.empty_confirmed:
                    empty_confirmed = False

                pagination = result.metadata.get("pagination") or {}
                remaining = pagination.get("paginasRestantes")
                if request.limit and len(all_records) >= request.limit:
                    all_records = all_records[: request.limit]
                    return FetchResult(
                        records=all_records,
                        request_completed=completed_any,
                        http_status=result.http_status,
                        empty_confirmed=False,
                        errors=errors,
                        metadata=metadata,
                    )
                if result.empty_confirmed and not result.records:
                    break
                if not isinstance(remaining, int) or remaining <= 0:
                    break
                page += 1
                time.sleep(PNCP_REQUEST_DELAY)
            time.sleep(PNCP_REQUEST_DELAY)

    http_status = 200 if completed_any else None
    return FetchResult(
        records=all_records,
        request_completed=completed_any,
        http_status=http_status,
        empty_confirmed=empty_confirmed and not all_records and not errors,
        errors=errors,
        metadata=metadata,
    )


def transform(raw_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    transformed: list[dict[str, Any]] = []
    for raw in raw_records:
        orgao = raw.get("orgaoEntidade") or {}
        unidade = raw.get("unidadeOrgao") or {}

        numero_controle = raw.get("numeroControlePNCP")
        synthetic_id = False
        synthetic_reason = None
        pncp_id = numero_controle
        if not pncp_id:
            pncp_id, synthetic_id, synthetic_reason = _synthetic_pncp_id(raw)

        orgao_cnpj = digits_only(orgao.get("cnpj"))
        ano_compra = raw.get("anoCompra")
        sequencial_compra = raw.get("sequencialCompra")
        link_pncp = build_pncp_public_link(
            orgao_cnpj=orgao_cnpj,
            ano_compra=ano_compra,
            sequencial_compra=sequencial_compra,
        )

        import hashlib

        content_hash_source = "|".join(
            [
                str(numero_controle or ""),
                orgao_cnpj,
                str(ano_compra or ""),
                str(sequencial_compra or ""),
                str(safe_date(raw.get("dataPublicacaoPncp")) or ""),
                str(raw.get("objetoCompra") or ""),
            ]
        )
        content_hash = hashlib.sha256(content_hash_source.encode("utf-8")).hexdigest()

        transformed.append(
            {
                "pncp_id": pncp_id,
                "numero_controle_pncp": numero_controle,
                "synthetic_id": synthetic_id,
                "synthetic_id_reason": synthetic_reason,
                "objeto_compra": raw.get("objetoCompra"),
                "informacao_complementar": raw.get("informacaoComplementar"),
                "valor_total_estimado": safe_float(raw.get("valorTotalEstimado")),
                "modalidade_id": raw.get("modalidadeId"),
                "modalidade_nome": raw.get("modalidadeNome"),
                "situacao_compra": raw.get("situacaoCompraNome"),
                "esfera_id": orgao.get("esferaId"),
                "uf": unidade.get("ufSigla"),
                "municipio": unidade.get("municipioNome"),
                "codigo_municipio_ibge": digits_only(unidade.get("codigoIbge")),
                "orgao_razao_social": orgao.get("razaoSocial"),
                "orgao_cnpj": orgao_cnpj,
                "unidade_nome": unidade.get("nomeUnidade"),
                "data_publicacao": raw.get("dataPublicacaoPncp"),
                "data_abertura": raw.get("dataAberturaProposta"),
                "data_encerramento": raw.get("dataEncerramentoProposta"),
                "link_sistema_origem": raw.get("linkSistemaOrigem"),
                "link_pncp": link_pncp,
                "content_hash": content_hash,
                "source": "pncp",
                "source_id": numero_controle or pncp_id,
                "ano_compra": ano_compra,
                "sequencial_compra": sequencial_compra,
            }
        )
    return transformed


# ---------------------------------------------------------------------------
# Contratos (historical contracts) — /api/consulta/v1/contratos
# ---------------------------------------------------------------------------
# API docs: dataInicial (required), dataFinal (required), pagina (required).
# Optional: tamanhoPagina, uf, cnpj, codigoMunicipioIbge.
# WARNING: UF filter is broken server-side (returns same totalRegistros for
# any UF). Post-filtering is applied in transform_contracts() when target
# specifies a UF.
# ---------------------------------------------------------------------------


def _fetch_contracts_page(request: CrawlRequest, page: int) -> FetchResult:
    """Fetch one page of contratos from the PNCP consulta API."""
    params: dict[str, str] = {
        "dataInicial": format_pncp_date(request.date_from or date.today()),
        "dataFinal": format_pncp_date(request.date_to or request.date_from or date.today()),
        "pagina": str(page),
        "tamanhoPagina": str(PNCP_CONTRATOS_PAGE_SIZE),
    }
    # UF filter passed to API even though it's broken server-side —
    # reduces response size slightly in some cases. Post-filter in transform.
    target = parse_target(request.target)
    if target.kind in {"sc", "within_200km", "engineering"}:
        params["uf"] = "SC"
    elif target.kind == "municipio":
        params["codigoMunicipioIbge"] = target.value or ""
    elif target.kind == "cnpj":
        params["cnpj"] = target.value or ""

    url = f"{PNCP_CONSULTA_BASE}/contratos?{urllib.parse.urlencode(params)}"
    result = _http_get_json(url)
    result.metadata["params"] = params
    return result


def crawl_contracts(mode: str | CrawlRequest = "full") -> FetchResult:
    """Crawl PNCP contratos endpoint with windowed date pagination."""
    request = _derive_request(mode)
    if request.date_from is None or request.date_to is None:
        raise ValueError("CrawlRequest precisa de date_from e date_to resolvidos")

    all_records: list[dict[str, Any]] = []
    errors: list[str] = []
    metadata: dict[str, Any] = {
        "endpoint": f"{PNCP_CONSULTA_BASE}/contratos",
        "target": asdict(parse_target(request.target)),
        "windows": [],
        "pages_fetched": 0,
    }
    completed_any = False
    empty_confirmed = True

    for window_start, window_end in _windowed_dates(request.date_from, request.date_to):
        metadata["windows"].append({"date_from": window_start.isoformat(), "date_to": window_end.isoformat()})
        page = 1
        while page <= PNCP_MAX_PAGES:
            page_request = CrawlRequest(
                mode=request.mode,
                date_from=window_start,
                date_to=window_end,
                target=request.target,
                limit=request.limit,
            )
            result = _fetch_contracts_page(page_request, page)
            metadata["pages_fetched"] += 1

            if result.request_completed:
                completed_any = True
            if result.errors:
                errors.extend(result.errors)
                empty_confirmed = False
                break

            if result.records:
                all_records.extend(result.records)
                empty_confirmed = False
            elif not result.empty_confirmed:
                empty_confirmed = False

            pagination = result.metadata.get("pagination") or {}
            remaining = pagination.get("paginasRestantes")
            if request.limit and len(all_records) >= request.limit:
                all_records = all_records[: request.limit]
                return FetchResult(
                    records=all_records,
                    request_completed=completed_any,
                    http_status=result.http_status,
                    empty_confirmed=False,
                    errors=errors,
                    metadata=metadata,
                )
            if result.empty_confirmed and not result.records:
                break
            if not isinstance(remaining, int) or remaining <= 0:
                break
            page += 1
            time.sleep(PNCP_REQUEST_DELAY)
        time.sleep(PNCP_REQUEST_DELAY)

    http_status = 200 if completed_any else None
    return FetchResult(
        records=all_records,
        request_completed=completed_any,
        http_status=http_status,
        empty_confirmed=empty_confirmed and not all_records and not errors,
        errors=errors,
        metadata=metadata,
    )


def transform_contracts(raw_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform raw PNCP contratos records into the canonical supplier_contracts schema."""
    transformed: list[dict[str, Any]] = []
    for raw in raw_records:
        orgao = raw.get("orgaoEntidade") or {}
        unidade = raw.get("unidadeOrgao") or {}
        unidade_sub = raw.get("unidadeSubRogada") or {}

        numero_controle = raw.get("numeroControlePncpCompra")
        orgao_cnpj = digits_only(orgao.get("cnpj"))
        fornecedor_cnpj = digits_only(raw.get("niFornecedor"))
        ano_contrato = raw.get("anoContrato")
        sequencial_contrato = raw.get("sequencialContrato")

        contrato_id_parts = [
            orgao_cnpj,
            str(ano_contrato or ""),
            str(sequencial_contrato or ""),
        ]
        contrato_id = "|".join(contrato_id_parts) if all(contrato_id_parts) else None

        import hashlib

        content_hash_source = "|".join(
            [
                str(numero_controle or ""),
                orgao_cnpj,
                fornecedor_cnpj,
                str(ano_contrato or ""),
                str(sequencial_contrato or ""),
                str(raw.get("dataPublicacaoPncp") or ""),
            ]
        )
        content_hash = hashlib.sha256(content_hash_source.encode("utf-8")).hexdigest()

        transformed.append(
            {
                "contrato_id": contrato_id,
                "numero_controle_pncp_compra": numero_controle,
                "numero_controle_pncp_ata": raw.get("numeroControlePncpAta"),
                "orgao_cnpj": orgao_cnpj,
                "orgao_razao_social": orgao.get("razaoSocial"),
                "orgao_esfera_id": orgao.get("esferaId"),
                "unidade_nome": unidade.get("nomeUnidade"),
                "unidade_uf": unidade.get("ufSigla"),
                "unidade_municipio": unidade.get("municipioNome"),
                "unidade_codigo_ibge": digits_only(unidade.get("codigoIbge")),
                "unidade_sub_rogada_nome": unidade_sub.get("nomeUnidadeSubRogada"),
                "fornecedor_cnpj": fornecedor_cnpj,
                "fornecedor_tipo_pessoa": raw.get("tipoPessoa"),
                "fornecedor_pais_codigo": raw.get("codigoPaisFornecedor"),
                "ano_contrato": ano_contrato,
                "sequencial_contrato": sequencial_contrato,
                "tipo_contrato": raw.get("tipoContrato"),
                "numero_contrato_empenho": raw.get("numeroContratoEmpenho"),
                "categoria_processo": raw.get("categoriaProcesso"),
                "processo": raw.get("processo"),
                "informacao_complementar": raw.get("informacaoComplementar"),
                "data_assinatura": raw.get("dataAssinatura"),
                "data_vigencia_inicio": raw.get("dataVigenciaInicio"),
                "data_vigencia_fim": raw.get("dataVigenciaFim"),
                "data_publicacao_pncp": raw.get("dataPublicacaoPncp"),
                "data_atualizacao": raw.get("dataAtualizacao"),
                "valor_inicial": safe_float(raw.get("valorInicial")),
                "valor_global": safe_float(raw.get("valorGlobal")),
                "valor_parcela": safe_float(raw.get("valorParcela")),
                "valor_acumulado": safe_float(raw.get("valorAcumulado")),
                "content_hash": content_hash,
                "source": "pncp",
                "source_id": numero_controle or contrato_id,
            }
        )
    return transformed


def crawl_contracts_and_transform(mode: str | CrawlRequest = "full") -> tuple[list[dict[str, Any]], FetchResult]:
    """Crawl + transform contratos in one call. Returns (transformed_records, raw_result)."""
    raw = crawl_contracts(mode)
    records = transform_contracts(raw.records) if raw.records else []
    return records, raw


def fetch_compra_detail(cnpj: str, ano: int, sequencial: int) -> FetchResult:
    url = f"{PNCP_CONSULTA_BASE}/orgaos/{digits_only(cnpj)}/compras/{int(ano)}/{int(sequencial)}"
    payload, result = _http_get_payload(url)
    if isinstance(payload, dict):
        result.records = [payload]
        result.empty_confirmed = False
    return result


def _fetch_list_endpoint(url: str) -> FetchResult:
    payload, result = _http_get_payload(url)
    if isinstance(payload, list):
        result.records = payload
        result.empty_confirmed = not result.records
    return result


def fetch_compra_items(cnpj: str, ano: int, sequencial: int) -> FetchResult:
    url = f"https://pncp.gov.br/api/pncp/v1/orgaos/{digits_only(cnpj)}/compras/{int(ano)}/{int(sequencial)}/itens"
    return _fetch_list_endpoint(url)


def fetch_compra_documents(cnpj: str, ano: int, sequencial: int) -> FetchResult:
    url = f"https://pncp.gov.br/api/pncp/v1/orgaos/{digits_only(cnpj)}/compras/{int(ano)}/{int(sequencial)}/arquivos"
    return _fetch_list_endpoint(url)
