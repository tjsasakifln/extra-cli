"""Supplier-centric PNCP contract/procurement document harvest.

Reuses process_documents PncpDocumentAdapter when available; does not fork
a second downloader stack.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import requests

from scripts.confenge_process_enrichment.doc_priority import rank_documents
from scripts.confenge_process_enrichment.identifiers import (
    digits_only,
    normalize_cnpj,
    parse_pncp_control_parts,
)
from scripts.confenge_process_enrichment.models import ContractNode, ProcessDocumentRef, ProvenanceEdge, _now_iso

PNCP_CONSULTA = "https://pncp.gov.br/api/consulta/v1"
PNCP_API = "https://pncp.gov.br/api/pncp/v1"
USER_AGENT = "extra-cli-confenge-process-enrichment/1.0"


@dataclass
class HarvestResult:
    contract_id: str
    documents: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    pages_attempted: int = 0
    used_adapter: str = "http"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "documents": self.documents,
            "blockers": self.blockers,
            "pages_attempted": self.pages_attempted,
            "used_adapter": self.used_adapter,
            "document_count": len(self.documents),
        }


class PncpSupplierHarvester:
    """Harvest PNCP arquivos for contracts belonging to a supplier."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (15.0, 90.0),
        request_delay: float = 0.25,
        download: bool = False,
        prefer_process_documents_adapter: bool = True,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers.setdefault("Accept", "application/json")
        self.timeout = timeout
        self.request_delay = request_delay
        self.download = download
        self.prefer_process_documents_adapter = prefer_process_documents_adapter
        self._adapter = None
        if prefer_process_documents_adapter:
            try:
                from scripts.process_documents.adapters.pncp import PncpDocumentAdapter

                self._adapter = PncpDocumentAdapter(session=self.session, timeout=timeout)
            except Exception:
                self._adapter = None

    def _sleep(self) -> None:
        if self.request_delay > 0:
            time.sleep(self.request_delay)

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> tuple[int | None, Any, str | None]:
        try:
            self._sleep()
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code != 200:
                return resp.status_code, None, f"HTTP {resp.status_code}"
            return resp.status_code, resp.json(), None
        except requests.Timeout:
            return None, None, "timeout"
        except requests.RequestException as exc:
            return None, None, str(exc)
        except ValueError as exc:
            return None, None, f"json:{exc}"

    def list_arquivos(
        self,
        orgao_cnpj: str,
        year: int,
        sequential: int,
        *,
        kind: str = "compras",
    ) -> HarvestResult:
        """List PNCP arquivos for compras or contratos resource path."""
        cnpj = normalize_cnpj(orgao_cnpj)
        kind = kind if kind in {"compras", "contratos"} else "compras"
        result = HarvestResult(contract_id=f"{cnpj}|{kind}|{year}|{sequential}")
        result.pages_attempted = 1

        # Reuse process_documents adapter only for compras path (its API surface).
        if kind == "compras" and self._adapter is not None:
            try:
                err, files, msg = self._adapter.list_arquivos(cnpj, int(year), int(sequential))
                result.used_adapter = "process_documents.PncpDocumentAdapter"
                if err is not None:
                    result.blockers.append(str(err.value if hasattr(err, "value") else err))
                    if msg:
                        result.blockers.append(msg)
                else:
                    for f in files or []:
                        result.documents.append(
                            self._normalize_arquivo(f, cnpj, year, sequential, kind=kind)
                        )
                    result.documents = rank_documents(result.documents)
                    return result
            except Exception as exc:  # noqa: BLE001
                result.blockers.append(f"adapter_fallback:{exc}")

        url = f"{PNCP_API}/orgaos/{cnpj}/{kind}/{int(year)}/{int(sequential)}/arquivos"
        code, payload, err = self._get_json(url)
        result.used_adapter = "http"
        if code is None:
            result.blockers.append(err or "connection_failed")
            return result
        if code in (401, 403):
            result.blockers.append("AUTH_REQUIRED")
            return result
        if code == 429:
            result.blockers.append("SOURCE_BLOCKED")
            return result
        if code == 404:
            return result  # empty OK
        if code != 200:
            result.blockers.append(f"HTTP_{code}")
            return result
        rows = payload if isinstance(payload, list) else (payload or {}).get("data") or []
        for f in rows:
            if isinstance(f, dict):
                result.documents.append(self._normalize_arquivo(f, cnpj, year, sequential, kind=kind))
        result.documents = rank_documents(result.documents)
        return result

    def list_compra_arquivos(self, orgao_cnpj: str, year: int, sequential: int) -> HarvestResult:
        return self.list_arquivos(orgao_cnpj, year, sequential, kind="compras")

    def _normalize_arquivo(
        self,
        f: dict[str, Any],
        orgao: str,
        year: int,
        seq: int,
        *,
        kind: str = "compras",
    ) -> dict[str, Any]:
        title = f.get("titulo") or f.get("uri") or f.get("nome") or f.get("title") or "arquivo"
        url = f.get("url") or f.get("uri") or f.get("download_url")
        if url and url.startswith("/"):
            url = urljoin("https://pncp.gov.br", url)
        if not url:
            seq_doc = f.get("sequencialDocumento") or f.get("sequencial")
            if seq_doc is not None:
                url = f"{PNCP_API}/orgaos/{orgao}/{kind}/{year}/{seq}/arquivos/{seq_doc}"
        return {
            "title": str(title),
            "url": url,
            "category": f.get("tipoDocumentoNome") or f.get("tipoDocumentoDescricao"),
            "document_id": str(
                f.get("sequencialDocumento") or f.get("id") or f"{orgao}-{kind}-{year}-{seq}-{title}"
            ),
            "source": f"pncp_{kind}",
            "orgao_cnpj": orgao,
            "year": year,
            "sequential": seq,
            "raw_type": f.get("tipoDocumentoId"),
            "size_bytes": f.get("tamanhoArquivo") or f.get("size"),
            "published_at": f.get("dataPublicacao") or f.get("dataPublicacaoPncp"),
            "pncp_resource": kind,
        }

    def harvest_contract(self, contract: ContractNode) -> HarvestResult:
        """Harvest procurement + contract docs for a single contract node.

        PNCP distinguishes:
        - numeroControlePncpCompra → /compras/{ano}/{seq}/arquivos (often richer)
        - contract orgao/ano/seq → /contratos/{ano}/{seq}/arquivos
        Compra control may reference a different organ CNPJ than the contract unit.
        """
        merged = HarvestResult(contract_id=contract.contract_id)
        seen_ids: set[str] = set()
        attempts: list[tuple[str, str, int, int]] = []  # kind, orgao, year, seq

        # 1) Compra control number (preferred for edital/anexo packs)
        compra_ctrl = contract.pncp_control_number or contract.raw_keys.get("numeroControlePncpCompra")
        parts = parse_pncp_control_parts(str(compra_ctrl) if compra_ctrl else None)
        if parts and parts.get("orgao_cnpj") and parts.get("year") is not None and parts.get("sequential") is not None:
            attempts.append(("compras", str(parts["orgao_cnpj"]), int(parts["year"]), int(parts["sequential"])))

        # 2) Contract keys on /contratos and /compras
        org = contract.contracting_authority_cnpj
        if org and contract.year is not None and contract.sequential is not None:
            attempts.append(("contratos", org, int(contract.year), int(contract.sequential)))
            attempts.append(("compras", org, int(contract.year), int(contract.sequential)))

        # de-dupe attempts
        seen_attempt: set[tuple[str, str, int, int]] = set()
        uniq_attempts: list[tuple[str, str, int, int]] = []
        for a in attempts:
            if a not in seen_attempt:
                seen_attempt.add(a)
                uniq_attempts.append(a)

        if not uniq_attempts:
            return HarvestResult(
                contract_id=contract.contract_id,
                blockers=["MISSING_PNCP_KEY: need parseable compra control or contract orgao/year/seq"],
            )

        for kind, orgao, year, seq in uniq_attempts:
            part = self.list_arquivos(orgao, year, seq, kind=kind)
            merged.pages_attempted += part.pages_attempted
            merged.blockers.extend(part.blockers)
            for d in part.documents:
                did = str(d.get("document_id") or d.get("url") or d.get("title"))
                if did in seen_ids:
                    continue
                seen_ids.add(did)
                merged.documents.append(d)

        merged.documents = rank_documents(merged.documents)
        merged.used_adapter = "pncp_multi_key"
        return merged

    def fetch_supplier_contracts_from_api(
        self,
        supplier_cnpj: str,
        *,
        data_inicial: str,
        data_final: str,
        max_pages: int = 3,
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        """Optional live pull of contratos for a supplier CNPJ via consulta API.

        Note: PNCP contratos filter is primarily date-based; client-side filter by niFornecedor.
        """
        cnpj = normalize_cnpj(supplier_cnpj)
        out: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            params = {
                "dataInicial": data_inicial.replace("-", ""),
                "dataFinal": data_final.replace("-", ""),
                "pagina": str(page),
                "tamanhoPagina": str(page_size),
            }
            code, payload, err = self._get_json(f"{PNCP_CONSULTA}/contratos", params=params)
            if code != 200 or not isinstance(payload, dict):
                break
            rows = payload.get("data") or []
            if not rows:
                break
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                ni = digits_only(raw.get("niFornecedor"))
                if ni != cnpj and not (len(cnpj) >= 8 and ni.startswith(cnpj[:8])):
                    continue
                out.append(raw)
            remaining = payload.get("paginasRestantes")
            if not remaining:
                break
        return out


def attach_docs_to_contract(contract: ContractNode, harvest: HarvestResult) -> ContractNode:
    """Mutate contract node with harvested document refs."""
    for d in harvest.documents:
        contract.documents.append(
            ProcessDocumentRef(
                document_id=str(d.get("document_id") or d.get("url") or d.get("title")),
                title=d.get("title"),
                url=d.get("url"),
                category=d.get("category") or d.get("priority_label"),
                yield_score=float(d.get("yield_score") or 0),
                company_authored_likely=bool(d.get("company_authored_likely")),
                size_bytes=d.get("size_bytes"),
                fetched=False,
                parsed=False,
                provenance=ProvenanceEdge(
                    source="pncp",
                    source_url=d.get("url"),
                    source_identifier=str(d.get("document_id")),
                    observed_at=_now_iso(),
                    confidence=0.9,
                    join_method="orgao_ano_sequencial",
                ),
            )
        )
    return contract
