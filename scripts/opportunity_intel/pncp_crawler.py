"""PNCP crawler for open bidding opportunities.

Uses the PNCP API v1 endpoint /contratacoes/proposta
to fetch contracts with open proposal periods.

API reference:
    https://pncp.gov.br/api/consulta/swagger-ui/index.html
    GET /v1/contratacoes/proposta — open proposal periods

Reuses patterns from:
    scripts/crawl/pncp_crawler_adapter.py
    scripts/crawl/pncp_contract.py
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from scripts.crawl.pncp_contract import DEFAULT_MODALIDADES, format_pncp_date
from scripts.opportunity_intel.crawler_base import BaseOpportunityCrawler, CrawlRequest

_logger = logging.getLogger(__name__)

# Constants
PNCP_CONSULTA_BASE = "https://pncp.gov.br/api/consulta/v1"
PNCP_PAGE_SIZE = min(50, max(10, int(os.getenv("PNCP_PAGE_SIZE", "50"))))
PNCP_MAX_PAGES = int(os.getenv("PNCP_MAX_PAGES", "200"))
PNCP_REQUEST_DELAY = float(os.getenv("PNCP_REQUEST_DELAY", "0.5"))


class PncpOpportunityCrawler(BaseOpportunityCrawler):
    """Crawler for PNCP open bidding opportunities.

    Fetches from /v1/contratacoes/proposta — returns contracts
    currently accepting proposals (open status).
    """

    def __init__(
        self,
        dsn: str | None = None,
        *,
        timeout: int | None = None,
        max_retries: int | None = None,
        request_delay: float | None = None,
        max_pages: int | None = None,
    ):
        kwargs: dict[str, Any] = {}
        if timeout is not None:
            kwargs["timeout"] = timeout
        if max_retries is not None:
            kwargs["max_retries"] = max_retries
        super().__init__(
            source_name="pncp",
            dsn=dsn,
            page_size=PNCP_PAGE_SIZE,
            max_pages=max_pages if max_pages is not None else PNCP_MAX_PAGES,
            request_delay=(request_delay if request_delay is not None else PNCP_REQUEST_DELAY),
            **kwargs,
        )

    def build_url(self, request: CrawlRequest, page: int) -> str:
        """Build URL for PNCP API contratacoes/proposta endpoint.

        This endpoint returns only contracts with open proposal periods.
        Optional filters: uf, codigoModalidadeContratacao, pagina, tamanhoPagina.
        """
        if not request.target or not request.target.startswith("modalidade:"):
            raise ValueError("PNCP open-proposals crawl requires target='modalidade:<1-19>'")
        modalidade = int(request.target.split(":", 1)[1])
        if modalidade not in DEFAULT_MODALIDADES:
            raise ValueError(f"Unsupported PNCP modalidade: {modalidade}")
        params: dict[str, str] = {
            "dataFinal": format_pncp_date(request.date_to or date.today()),
            "codigoModalidadeContratacao": str(modalidade),
            "pagina": str(page),
            "tamanhoPagina": str(self.page_size),
            "uf": "SC",
        }
        qs = urlencode(params)
        return f"{PNCP_CONSULTA_BASE}/contratacoes/proposta?{qs}"

    def parse_response(self, raw_data: Any) -> list[dict[str, Any]]:
        """Extract contratacao records from PNCP API response.

        PNCP returns: [{...contratacao fields...}, ...]
        or wrapped: {data: [...], totalRegistros: N, totalPaginas: M}
        """
        if isinstance(raw_data, dict):
            # Wrapped response
            if "data" in raw_data:
                data = raw_data["data"]
                return data if isinstance(data, list) else []
            # Single record?
            if "numeroControlePNCP" in raw_data:
                return [raw_data]
            return []

        if isinstance(raw_data, list):
            return raw_data

        return []


class PncpPublicationCrawler(BaseOpportunityCrawler):
    """Crawler for PNCP contracts by publication date.

    Uses /v1/contratacoes/publicacao — broader than /proposta,
    includes all contracts published in a date range regardless
    of proposal status. Post-filtering needed for open status.
    """

    def __init__(self, dsn: str | None = None):
        super().__init__(
            source_name="pncp_publication",
            dsn=dsn,
            page_size=PNCP_PAGE_SIZE,
            max_pages=PNCP_MAX_PAGES,
            request_delay=PNCP_REQUEST_DELAY,
        )

    def build_url(self, request: CrawlRequest, page: int) -> str:
        """Build URL for contratacoes/publicacao with date range."""
        date_from = request.date_from or date.today() - timedelta(days=30)
        date_to = request.date_to or date.today()

        params: dict[str, str] = {
            "dataInicial": date_from.isoformat(),
            "dataFinal": date_to.isoformat(),
            "pagina": str(page),
            "tamanhoPagina": str(self.page_size),
            "uf": "SC",
        }

        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{PNCP_CONSULTA_BASE}/contratacoes/publicacao?{qs}"

    def parse_response(self, raw_data: Any) -> list[dict[str, Any]]:
        """Same response format as PncpOpportunityCrawler."""
        if isinstance(raw_data, dict):
            if "data" in raw_data:
                return raw_data["data"] if isinstance(raw_data["data"], list) else []
            if "numeroControlePNCP" in raw_data:
                return [raw_data]
            return []
        if isinstance(raw_data, list):
            return raw_data
        return []
