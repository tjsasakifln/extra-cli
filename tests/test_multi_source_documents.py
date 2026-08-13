"""Inventário documental e análise mínima da shortlist."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from scripts.ops.multi_source_open_pack.analysis import analyze_edital_minimo, apply_minimum_analysis
from scripts.ops.multi_source_open_pack.consolidate import consolidate_observations
from scripts.ops.multi_source_open_pack.decide import apply_decisions
from scripts.ops.multi_source_open_pack.documents import (
    FetchResult,
    inventariar_processo,
    inventariar_shortlist,
    is_specific_official_url,
)
from scripts.ops.multi_source_open_pack.models import SourceObservation
from scripts.ops.multi_source_open_pack.textutil import BR_TZ


def _obs(**kw) -> SourceObservation:
    base = dict(
        observation_id="d1",
        fonte="pncp",
        fonte_papel="required",
        id_externo="82951351000142-1-000441/2026",
        orgao="SECRETARIA DE ESTADO DA ADMINISTRACAO",
        orgao_cnpj="82951351000142",
        municipio="FLORIANOPOLIS",
        uf="SC",
        objeto="Contratação de serviços de engenharia para reforma das quadras poliesportivas da escola",
        modalidade="Pregão",
        valor_estimado=800000.0,
        data_publicacao="2026-07-01",
        data_abertura="",
        data_encerramento="2026-09-30T17:00:00-03:00",
        url="https://pncp.gov.br/app/editais/82951351000142/2026/441",
        status_fonte="open",
        categoria_ato="edital_aberto",
        in_universe=True,
        match_universo="cnpj8",
        distance_km=0.1,
        distance_method="universe_seed_geodesic_from_florianopolis",
        entity_key="82951351",
        event_type="edital",
        is_active_dispute=True,
        exclusion_reason="",
    )
    base.update(kw)
    return SourceObservation(**base)


def test_is_specific_official_url():
    assert is_specific_official_url("https://pncp.gov.br/app/editais/82951351000142/2026/441")
    assert not is_specific_official_url("https://pncp.gov.br/app/editais")
    assert not is_specific_official_url("https://www.google.com/search?q=edital")


def test_inventario_marks_blocked_without_specific_url():
    o = _obs(url="https://pncp.gov.br/app/editais")
    procs, _ = consolidate_observations([o], now=datetime(2026, 7, 31, 12, 0, tzinfo=BR_TZ))
    apply_decisions(procs, profile={})
    p = procs[0]
    p.url_oficial = "https://pncp.gov.br/app/editais"
    p.official_page_validated = False
    ev = inventariar_processo(p, download_arquivos=False)
    assert ev["page_validated"] is False
    assert "sem_pagina_oficial" in ev["blocked_reason"] or "especifica" in ev["blocked_reason"]
    assert p.docs_inventory_status.startswith("blocked")


def test_inventario_page_only_is_not_complete(tmp_path: Path):
    """HTML page hash alone must NOT qualify as shortlist-complete."""
    o = _obs()
    procs, _ = consolidate_observations([o], now=datetime(2026, 7, 31, 12, 0, tzinfo=BR_TZ))
    apply_decisions(procs, profile={})
    p = procs[0]
    fake = FetchResult(
        ok=True,
        url_original=p.url_oficial,
        url_final=p.url_oficial,
        http_status=200,
        content_type="text/html",
        sha256="abc123",
        size=100,
        body=b"<html><body>Edital reforma predial garantia da proposta 1% habilitacao juridica</body></html>",
        fetched_at="2026-08-01T00:00:00Z",
    )
    with patch(
        "scripts.ops.multi_source_open_pack.documents.fetch_url",
        return_value=fake,
    ), patch(
        "scripts.ops.multi_source_open_pack.documents.list_pncp_arquivos",
        return_value=[],
    ):
        ev = inventariar_processo(p, cache_dir=tmp_path, download_arquivos=True)
    assert ev["page_validated"] is True
    assert p.docs_inventory_status == "partial_page_only"
    assert ev.get("docs_complete") is False


def test_inventario_complete_with_parsed_edital_pdf(tmp_path: Path):
    o = _obs()
    procs, _ = consolidate_observations([o], now=datetime(2026, 7, 31, 12, 0, tzinfo=BR_TZ))
    apply_decisions(procs, profile={})
    p = procs[0]
    page = FetchResult(
        ok=True,
        url_original=p.url_oficial,
        url_final=p.url_oficial,
        http_status=200,
        content_type="text/html",
        sha256="pagehash",
        size=50,
        body=b"<html><body>portal</body></html>",
        fetched_at="2026-08-01T00:00:00Z",
    )
    # minimal valid-ish PDF header + text via mock extract
    pdf_body = b"%PDF-1.4 fake content for test " + b"x" * 200
    pdf = FetchResult(
        ok=True,
        url_original="https://pncp.gov.br/arquivo/edital.pdf",
        url_final="https://pncp.gov.br/arquivo/edital.pdf",
        http_status=200,
        content_type="application/pdf",
        sha256="pdfhash",
        size=len(pdf_body),
        body=pdf_body,
        fetched_at="2026-08-01T00:00:01Z",
    )

    def _fetch(url, **kwargs):
        if "edital" in url or "arquivo" in url:
            return pdf
        return page

    from scripts.ops.multi_source_open_pack.pdf_parse import PdfExtract

    with patch(
        "scripts.ops.multi_source_open_pack.documents.fetch_url",
        side_effect=_fetch,
    ), patch(
        "scripts.ops.multi_source_open_pack.documents.list_pncp_arquivos",
        return_value=[
            {
                "title": "Edital 0461-2026 assinado.pdf",
                "url": "https://pncp.gov.br/arquivo/edital.pdf",
                "tipo": "edital",
            }
        ],
    ), patch(
        "scripts.ops.multi_source_open_pack.documents.extract_pdf_text",
        return_value=PdfExtract(
            ok=True,
            text=(
                "EDITAL DE CONCORRENCIA. Objeto: reforma predial. "
                "Habilitacao juridica. Garantia da proposta 1%. "
                "Prazo de execucao 180 dias. Criterio de julgamento menor preco. "
                "Regime de execucao empreitada por preco global. "
                "Capacidade tecnica com atestado CAT."
            ),
            pages_read=2,
            pages_total=10,
            confidence=0.85,
        ),
    ):
        ev = inventariar_processo(p, cache_dir=tmp_path, download_arquivos=True)
    assert ev.get("docs_complete") is True
    assert p.docs_inventory_status.startswith("complete")
    assert any(d.parse_status == "text_extracted" for d in p.documents)
    analysis = analyze_edital_minimo(p, page_text=ev.get("combined_text") or ev.get("page_text_sample", ""))
    assert "Objeto:" in analysis["summary"]
    assert analysis["confidence"] > 0.4
    assert analysis.get("found_critical")


def test_shortlist_inventory_disabled_marks_review_blocked():
    o = _obs()
    procs, _ = consolidate_observations([o], now=datetime(2026, 7, 31, 12, 0, tzinfo=BR_TZ))
    apply_decisions(procs, profile={})
    summary = inventariar_shortlist(procs, enabled=False)
    assert summary["enabled"] is False
    assert "inventario" in procs[0].docs_inventory_status or "bloqueado" in procs[0].docs_inventory_status


def test_minimum_org_competitor_evidence_based_no_invention():
    o = _obs()
    procs, _ = consolidate_observations([o], now=datetime(2026, 7, 31, 12, 0, tzinfo=BR_TZ))
    apply_decisions(procs, profile={})
    # Offline: pack-based only (no live contracts API)
    apply_minimum_analysis(procs, all_processes=procs, fetch_contracts=False)
    p = procs[0]
    assert "No pack multi-fonte" in p.buyer_analysis or "processo(s)" in p.buyer_analysis
    # Must not invent generic constructor lists
    assert "lista genérica" not in p.competitors_probable.lower() or "Não inventar" in p.competitors_probable
    assert p.buyer_analysis
    # With fetch disabled, competitors may be empty but message is honest
    assert "concorrente" in p.competitors_probable.lower() or "histórico" in p.competitors_probable.lower()
