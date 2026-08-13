"""End-to-end reproducibility helpers — same inputs → same complete outputs."""

from __future__ import annotations

import hashlib
import json

from scripts.commercial_leads.pipeline import compute_supplier_history_metrics
from scripts.commercial_leads.scoring import (
    diagnose_offer_distribution,
    score_supplier,
)
from scripts.commercial_leads.signals import SIGNAL_STATUS_FIRED, SignalResult


class _Prof:
    data = {
        "next_steps_by_priority": {"WATCH": "x", "LOW": "x", "MEDIUM": "x", "HIGH": "x", "CRITICAL": "x"},
        "offer_mappings": [],
        "queue": {"min_score": 0.0, "min_signals_fired": 0},
        "exclusions": {},
    }
    queue_limit = 20


def _sig(sid: str, offer: str, contrib: float) -> SignalResult:
    return SignalResult(
        signal_id=sid,
        status=SIGNAL_STATUS_FIRED,
        contribution=contrib,
        offer=offer,
        evidence=[{"kind": "test"}],
        limitations=[],
        raw_value=contrib,
        hypothesis="test",
    )


def test_history_metrics_deterministic() -> None:
    rows = [
        {
            "objeto_contrato": "execução de obras de engenharia",
            "is_active": True,
            "data_publicacao": "2024-01-01",
            "orgao_cnpj": "a",
        },
        {
            "objeto_contrato": "fornecimento de merenda",
            "is_active": False,
            "data_publicacao": "2024-06-01",
            "orgao_cnpj": "b",
        },
    ]
    a = compute_supplier_history_metrics(rows)
    b = compute_supplier_history_metrics(list(rows))
    assert a == b
    h1 = hashlib.sha256(json.dumps(a, sort_keys=True).encode()).hexdigest()
    h2 = hashlib.sha256(json.dumps(b, sort_keys=True).encode()).hexdigest()
    assert h1 == h2


def test_offer_and_rank_stable_under_identical_signals() -> None:
    from scripts.commercial_leads.signals import SignalResult

    def make(sid: str, contrib: float, offer: str) -> SignalResult:
        return SignalResult(
            signal_id=sid,
            status=SIGNAL_STATUS_FIRED,
            strength=1.0,
            weight=1.0,
            contribution=contrib,
            hypothesis="t",
            evidence=[],
            limitations=[],
            offer=offer,
        )

    sigs = [
        make("near_expiry", 2.0, "acompanhamento_admin"),
        make("ticket_above_history", 1.5, "diagnostico_b2g"),
    ]
    p = _Prof()
    l1 = score_supplier(
        cnpj14="00000000000191",
        razao_social="A",
        signal_results=sigs,
        profile=p,  # type: ignore[arg-type]
    )
    l2 = score_supplier(
        cnpj14="00000000000191",
        razao_social="A",
        signal_results=list(sigs),
        profile=p,  # type: ignore[arg-type]
    )
    assert l1.score_total == l2.score_total
    assert l1.selected_offer == l2.selected_offer
    assert l1.offer_scores == l2.offer_scores


def test_offer_discrimination_detects_uniform_mapping() -> None:
    leads = [
        {
            "selected_offer": "acompanhamento_contratual",
            "selected_offer_margin": 0.1,
        }
        for _ in range(20)
    ]
    d = diagnose_offer_distribution(leads)
    assert d["dominant_offer_rate"] == 1.0
    assert d["block"] == "BLOCKED_OFFER_MAPPING_NOT_DISCRIMINATIVE"


def test_offer_discrimination_accepts_varied_mapping() -> None:
    offers = [
        "diagnostico_b2g",
        "licitacoes_propostas",
        "auditoria_orcamento",
        "acompanhamento_contratual",
        "inteligencia_pncp",
    ]
    leads = [
        {"selected_offer": offers[i % len(offers)], "selected_offer_margin": 1.5}
        for i in range(20)
    ]
    d = diagnose_offer_distribution(leads)
    assert d["dominant_offer_rate"] <= 0.80
    assert d["block"] is None
