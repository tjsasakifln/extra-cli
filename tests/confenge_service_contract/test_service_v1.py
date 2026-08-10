"""confenge.service.v1 — no silent REAJUSTE fallback; all families map."""

from __future__ import annotations

import pytest

from scripts.confenge_service_contract.mapping import (
    SCHEMA_ID,
    UnknownServiceCodeError,
    export_contract_json,
    fallback_canonical,
    load_service_contract,
    map_to_canonical,
    map_to_warmbly,
    resolve_service,
)


def test_contract_loads() -> None:
    c = load_service_contract()
    assert c["schema_id"] == SCHEMA_ID
    assert len(c["services"]) >= 10


def test_all_extra_cli_ids_map() -> None:
    expected = [
        "estruturacao_pleito_reajuste",
        "reequilibrio_economico_financeiro",
        "aditivos_extracontratuais",
        "medicoes_glosas_memoria",
        "auditoria_orcamento_bdi",
        "gestao_monitoramento_contratual",
        "apoio_licitacoes_propostas",
        "inteligencia_pncp_mercado",
        "diagnostico_contratual_b2g",
        "reforco_temporario_backoffice",
    ]
    for sid in expected:
        can = map_to_canonical(sid)
        warm = map_to_warmbly(sid)
        assert can
        assert warm
        assert warm != ""  # mapped


def test_reajuste_14133_maps_to_reajuste_not_default_for_others() -> None:
    assert map_to_canonical("REAJUSTE_14133") == "REAJUSTE"
    assert map_to_warmbly("estruturacao_pleito_reajuste") == "REAJUSTE"
    assert map_to_canonical("auditoria_orcamento_bdi") == "ORCAMENTO_BDI"
    assert map_to_warmbly("auditoria_orcamento_bdi") == "PLANILHAS"
    assert map_to_canonical("diagnostico_contratual_b2g") == "DIAGNOSTICO"


def test_unknown_raises_never_reajuste() -> None:
    with pytest.raises(UnknownServiceCodeError):
        resolve_service("COMPLETELY_UNKNOWN_SERVICE_XYZ")
    with pytest.raises(UnknownServiceCodeError):
        map_to_canonical("")


def test_fallback_is_diagnostico_not_reajuste() -> None:
    assert fallback_canonical() == "DIAGNOSTICO"


def test_export_json_shape() -> None:
    data = export_contract_json()
    assert data["schema_id"] == SCHEMA_ID
    codes = {s["canonical_service_code"] for s in data["services"]}
    assert "REAJUSTE" in codes
    assert "DIAGNOSTICO" in codes
    assert "MEDICOES" in codes
    assert data["routing_rules"]["reajuste_is_never_default"] is True
    assert data["routing_rules"]["unknown_code_behavior"] == "FAIL_CLOSED"
