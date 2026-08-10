"""Public source classification for CONFENGE contact ladder (auth vs no-auth).

Used by national pack to prove which cascade steps are PUBLIC_NO_AUTH vs
require session/CAPTCHA before EXTERNAL_BLOCKER is allowed.
"""

from __future__ import annotations

from typing import Any

# Cascade from goal objective mapped to technical reality of this codebase.
SOURCE_CLASSIFICATION: list[dict[str, Any]] = [
    {
        "step": 1,
        "name": "datalake_existing",
        "ladder_id": "public_docs_datalake",
        "class": "PUBLIC_NO_AUTH",
        "integrated": True,
        "adapter": "registry / public_docs",
    },
    {
        "step": 2,
        "name": "pncp_structured",
        "ladder_id": "pncp_annexes",
        "class": "PUBLIC_NO_AUTH",
        "integrated": True,
        "adapter": "pncp_supplier_harvest",
    },
    {
        "step": 3,
        "name": "pncp_attachments",
        "ladder_id": "pncp_annexes",
        "class": "PUBLIC_NO_AUTH",
        "integrated": True,
        "adapter": "process_resolve + text_extract",
    },
    {
        "step": 4,
        "name": "public_admin_process",
        "ladder_id": "process_administrative_docs",
        "class": "PUBLIC_NO_AUTH",
        "integrated": True,
        "adapter": "national_confirmed process harvest",
    },
    {
        "step": 5,
        "name": "orgao_official_portal",
        "ladder_id": "transparency_compras",
        "class": "PUBLIC_NO_AUTH",
        "integrated": True,
        "adapter": "municipal_portal (process enrichment)",
        "note": "HTTP GET only; not yet wired into contact enrich-batch adapters list",
    },
    {
        "step": 6,
        "name": "company_official_site",
        "ladder_id": "official_site",
        "class": "PUBLIC_NO_AUTH",
        "integrated": True,
        "adapter": "site / site_crawl",
    },
    {
        "step": 7,
        "name": "company_contact_pages",
        "ladder_id": "company_public_pages",
        "class": "PUBLIC_NO_AUTH",
        "integrated": True,
        "adapter": "contact_page + web_search",
    },
    {
        "step": 8,
        "name": "company_public_pdfs",
        "ladder_id": "company_public_pages",
        "class": "PUBLIC_NO_AUTH",
        "integrated": True,
        "adapter": "site crawl PDF links",
    },
    {
        "step": 9,
        "name": "public_compras_transparency",
        "ladder_id": "transparency_compras",
        "class": "PUBLIC_NO_AUTH",
        "integrated": "PARTIAL",
        "adapter": "municipal_portal.py",
        "note": "Public GET; national contact graph must call it for FULL public exhaustion",
    },
    {
        "step": 10,
        "name": "sei_authenticated",
        "ladder_id": "sei",
        "class": "HUMAN_SESSION_REQUIRED",
        "integrated": True,
        "adapter": "sei_human_session",
        "note": "Requires human session / CAPTCHA — valid EXTERNAL after PUBLIC_NO_AUTH exhausted",
    },
]


def classification_report(*, yield_by_source: dict[str, Any] | None = None) -> dict[str, Any]:
    y = yield_by_source or {}
    rows = []
    for s in SOURCE_CLASSIFICATION:
        lid = s["ladder_id"]
        attempted = 0
        if isinstance(y.get(lid), dict):
            attempted = int(y[lid].get("companies_attempted") or 0)
        elif isinstance(y.get(lid), int):
            attempted = int(y[lid])
        rows.append({**s, "companies_attempted": attempted})
    public_no_auth = [r for r in rows if r["class"] == "PUBLIC_NO_AUTH"]
    unattempted_public = [
        r for r in public_no_auth if r["companies_attempted"] == 0 and r.get("integrated") is not False
    ]
    return {
        "schema": "confenge.source_ladder_classification.v1",
        "sources": rows,
        "public_no_auth_unattempted": [
            {"name": r["name"], "ladder_id": r["ladder_id"], "note": r.get("note")}
            for r in unattempted_public
        ],
        "all_public_no_auth_attempted": len(unattempted_public) == 0,
    }
