"""Representative live #241 pagination proof against official PNCP."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from scripts.crawl.pncp_entity_pagination import (
    expected_pages,
    proof_report,
    prove_scope,
    record_page,
)

PNCP_CONTRATOS = "https://pncp.gov.br/api/consulta/v1/contratos"
USER_AGENT = "extra-cli-entity-pagination/1.0"
PAGE_SIZE = 50


def _fetch(url: str, timeout: int = 45) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 — HTTPS official PNCP
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read() if exc.fp else b""


def parse_contratos_page(body: bytes) -> tuple[list[dict[str, Any]], int | None]:
    if not body:
        return [], None
    payload = json.loads(body.decode("utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)], len(payload)
    if not isinstance(payload, dict):
        return [], None
    records = payload.get("data") or payload.get("items") or []
    total = payload.get("totalRegistros")
    return list(records) if isinstance(records, list) else [], int(total) if total is not None else None


def prove_entity_window(
    *,
    ente_cnpj: str,
    data_inicial: str,
    data_final: str,
    max_pages: int = 3,
) -> dict[str, Any]:
    pages = []
    found = 0
    total = None
    query_complete = True
    pages_expected = 1
    for page_no in range(1, max_pages + 1):
        params = urllib.parse.urlencode(
            {
                "dataInicial": data_inicial.replace("-", ""),
                "dataFinal": data_final.replace("-", ""),
                "cnpjOrgao": ente_cnpj,
                "pagina": str(page_no),
                "tamanhoPagina": str(PAGE_SIZE),
            }
        )
        url = f"{PNCP_CONTRATOS}?{params}"
        status, body = _fetch(url)
        try:
            records, page_total = parse_contratos_page(body)
        except json.JSONDecodeError:
            records, page_total = [], None
            query_complete = False
        if page_total is not None:
            total = page_total
        found += len(records)
        pages.append(
            record_page(
                url=url,
                status=status,
                body=body,
                page=page_no,
                records=len(records) if isinstance(records, list) else 0,
            )
        )
        if status != 200:
            query_complete = False
            break
        if isinstance(records, list) and len(records) < PAGE_SIZE:
            break
    if total is not None:
        pages_expected = expected_pages(total, PAGE_SIZE)
    else:
        pages_expected = len(pages) if pages else 1
    if pages_expected > max_pages:
        query_complete = False
        pages_expected = max_pages
    proof = prove_scope(
        ente_id=ente_cnpj,
        window=f"{data_inicial}_{data_final}",
        modalidade=None,
        pages_expected=pages_expected,
        pages=pages,
        found_count=found,
        query_complete=query_complete,
    )
    return proof_report([proof])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m scripts.crawl.pncp_entity_scope_live")
    parser.add_argument("--ente", required=True, help="Publishing-org CNPJ")
    parser.add_argument("--data-inicial", required=True)
    parser.add_argument("--data-final", required=True)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    report = prove_entity_window(
        ente_cnpj=args.ente,
        data_inicial=args.data_inicial,
        data_final=args.data_final,
        max_pages=args.max_pages,
    )
    path = args.out
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    sys.stdout.write(json.dumps({"ok": True, "path": path, "verdict": report["scopes"][0]["verdict"]}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
