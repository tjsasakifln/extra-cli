"""Licitações-e surface map (#265) — official redirect/deprecation evidence."""

from __future__ import annotations

from typing import Any

from scripts.complementary.contract import RunResult, sha256_json

SOURCE = "licitacoes_e"
CANONICAL_HINTS = (
    "https://www.licitacoes-e.com.br/",
    "https://www.licitacoes-e.com.br/aop/index.jsp",
)


def classify_surface(probe: dict[str, Any]) -> RunResult:
    """Classify a public probe of Licitações-e.

    Restricted / login-only → BLOCKED.
    Official deprecation/redirect → NOT_APPLICABLE with evidence.
    Active public search → success + fixture contract.
    """
    status = probe.get("status")
    final_url = str(probe.get("final_url") or probe.get("url") or "")
    body = str(probe.get("body") or "")
    redirected = bool(probe.get("redirected") or (probe.get("url") and final_url and probe.get("url") != final_url))
    lower = body.lower()

    evidence = {
        "url": probe.get("url"),
        "final_url": final_url,
        "status": status,
        "redirected": redirected,
        "hash": sha256_json({"url": final_url, "status": status, "body": body[:500]}),
    }

    if probe.get("restricted") or status in {401, 403} or "captcha" in lower:
        return RunResult(SOURCE, "BLOCKED", 0, 0, 0, 0, reason="restricted_or_captcha", job=evidence)
    if probe.get("deprecated") or "descontinuad" in lower or "migrad" in lower:
        return RunResult(SOURCE, "NOT_APPLICABLE", 0, 0, 0, 0, reason="official_deprecation", job=evidence)
    if redirected and "bb.com.br" in final_url.lower():
        return RunResult(SOURCE, "NOT_APPLICABLE", 0, 0, 0, 0, reason="redirected_off_platform", job=evidence)
    if probe.get("active") or "pesquisar" in lower or "licita" in lower:
        records = list(probe.get("processes") or [])
        terminal = "success" if records else "ZERO_CONFIRMED"
        if records and not probe.get("pagination_complete"):
            terminal = "partial"
        return RunResult(
            SOURCE,
            terminal,  # type: ignore[arg-type]
            fetched=len(records),
            persisted=len(records),
            deduplicated=0,
            failed=0,
            records=records,
            job=evidence,
        )
    return RunResult(SOURCE, "FAILED", 0, 0, 0, 0, reason="surface_unclassified", job=evidence)
