"""Official-live consumer handoff: freshness, analysis_mode, gates, rendezvous."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.historical_contract_authority.analysis import resolve_analysis_mode, resolve_comparability
from scripts.historical_contract_authority.consumer import (
    assemble_consumer_dossier,
    claim_is_located,
    validate_consumer_dossier,
)
from scripts.historical_contract_authority.freshness import dossier_freshness, strip_temporal_for_hash
from scripts.historical_contract_authority.official_live import (
    build_rendezvous_files,
    same_consumer_shape,
    write_atomic_rendezvous,
)
from scripts.historical_contract_authority.schema import content_hash, is_sha256

DIGEST = "a" * 64


def _claim(text: str = "Objeto oficial de pavimentacao asfaltica em Brusque.") -> dict:
    return {
        "claim_id": "fact-1",
        "class": "FACT",
        "text": text,
        "evidence_id": "doc-1",
        "url": "https://pncp.gov.br/app/contratos/x",
        "sha256": DIGEST,
        "locator": {"json_path": "$.objetoContrato"},
        "source_refs": ["doc-1"],
    }


def _artifact() -> dict:
    return {
        "evidence_id": "doc-1",
        "url": "https://pncp.gov.br/app/contratos/x",
        "sha256": DIGEST,
        "locator": {"json_path": "$.objetoContrato"},
        "retrieved_at": "2026-08-17T12:00:00Z",
        "verified_at": "2026-08-17T12:00:00Z",
    }


def _identity() -> dict:
    return {
        "contract_id": "1536471100010442024001",
        "orgao_cnpj": "82940433000194",
        "fornecedor_cnpj": "07894512000133",
        "objeto": "Pavimentacao asfaltica com aditivo de prazo",
        "uf": "SC",
        "municipio": "Brusque",
        "source_system": "pncp",
        "official_urls": ["https://pncp.gov.br/app/contratos/x"],
    }


def _assemble(**overrides):
    kwargs = {
        "analysis_id": "analysis-demo-01",
        "identity": _identity(),
        "artifacts": [_artifact()],
        "claims": [_claim()],
        "calculations": [],
        "inferences": [],
        "unknowns": [
            {
                "claim_id": "unk-unit",
                "class": "UNKNOWN",
                "text": "Unidade física não demonstrada na fonte oficial desta execução.",
                "evidence_id": "doc-1",
                "url": "https://pncp.gov.br/app/contratos/x",
                "sha256": DIGEST,
                "locator": {"json_path": "$.unidade"},
            }
        ],
        "insight": (
            "A cadeia documental oficial descreve pavimentação com aditivo de prazo; "
            "o insight é a sequência documental, não um ranking de pares."
        ),
        "limitations": [
            "Sem comparação de pares: unidade, regime, escopo e período compatíveis não foram demonstrados.",
            "atípico nunca significa irregular.",
        ],
        "method": "official-live-document-chain/1.1",
        "producer_repo": "tjsasakifln/extra-cli",
        "producer_commit": "abc123",
        "replay_command": "python3 -m scripts.historical_contract_authority --mode official-live --limit 2",
        "query_window": {"start": "2026-08-03", "end": "2026-08-17", "uf": "SC"},
        "retrieved_at": "2026-08-17T12:00:00Z",
        "verified_at": "2026-08-17T12:00:00Z",
        "source_as_of": None,
        "event_effective_at": "2024-03-01",
        "source_published_at": "2024-03-02",
        "as_of": "2026-08-17T12:00:00Z",
        "bytes_obtained": True,
        "requested_mode": "DOCUMENT_CHAIN",
    }
    kwargs.update(overrides)
    return assemble_consumer_dossier(**kwargs)


def test_old_event_current_verify_not_stale_and_not_recent() -> None:
    block = dossier_freshness(
        as_of="2026-08-17T12:00:00Z",
        event_effective_at="2024-03-01",
        source_published_at="2024-03-02",
        retrieved_at="2026-08-17T12:00:00Z",
        verified_at="2026-08-17T12:00:00Z",
        source_as_of=None,
        bytes_obtained=True,
    )
    assert block["stale"] is False
    assert block["event_is_recent"] is False
    assert block["event_effective_at"] == "2024-03-01"


def test_generic_value_and_term_is_not_singular_insight() -> None:
    from scripts.historical_contract_authority.official_live import _insight_for
    from scripts.official_contract_semantics.models import observation_from_mapping

    raw = {
        "schema_version": "official-contract-observation/1.1",
        "observation_id": "obs-generic",
        "source_system": "pncp",
        "source_kind": "contract",
        "official_url": "https://pncp.gov.br/app/contratos/x",
        "source_document_id": "x",
        "source_document_sha256": DIGEST,
        "contract_identifier": "x",
        "object_text": "Aquisição de botijão de gás por registro de preços.",
        "value_amount": "1289.00",
        "value_semantic": "valor_global",
        "period_start": "2026-07-31",
        "period_end": "2026-12-31",
        "raw_record_hash": DIGEST,
        "status": "observed",
        "confidence_class": "explicit_structured_field",
        "locator": {"json_path": "$.objetoContrato"},
        "extractor_version": "official-contract-semantics-extract/1.1",
    }
    obs = observation_from_mapping(raw)
    assert _insight_for([obs], []) == ""


def test_document_chain_without_comparative_language_accepts_not_applicable() -> None:
    dossier = _assemble()
    assert dossier["analysis"]["analysis_mode"] == "DOCUMENT_CHAIN"
    assert dossier["analysis"]["comparability_status"] == "NOT_APPLICABLE"
    assert dossier["handoff_status"] == "HANDOFF_READY"
    assert dossier["gates"]["publication_authorization"] is False
    assert dossier["gates"]["index_authorization"] is False
    assert dossier["gates"]["commercial_relationship_claim"] is False
    assert dossier["gates"]["official_live"] is True


def test_comparative_phrase_reactivates_peer_gate() -> None:
    mode, hits = resolve_analysis_mode(
        requested="DOCUMENT_CHAIN",
        claims=("Valor acima da mediana dos peers de pavimentação.",),
        insight="Contrato outlier frente aos pares.",
        limitations=("sem comparação",),
        comparative_engine_used=False,
    )
    assert mode == "COMPARATIVE"
    assert hits
    result = resolve_comparability(
        analysis_mode=mode,
        comparative_hits=hits,
        singular_insight="Contrato outlier frente aos pares.",
        limitations_declare_no_comparison=True,
        engine_status="NOT_COMPARABLE",
        engine_reason_codes=("incompatible_unit",),
        unit_compatible=False,
        regime_compatible=False,
        scope_compatible=False,
        period_compatible=False,
    )
    assert result["status"] == "NOT_COMPARABLE"
    dossier = _assemble(insight="Este contrato é outlier frente aos pares de pavimentação.")
    assert dossier["analysis"]["analysis_mode"] == "COMPARATIVE"
    assert dossier["analysis"]["comparability_status"] == "NOT_COMPARABLE"
    assert dossier["handoff_status"] != "HANDOFF_READY"


def test_comparative_without_compatible_peers_cannot_be_ready() -> None:
    dossier = _assemble(requested_mode="COMPARATIVE", insight="Comparação de valor integral nominal.")
    assert dossier["analysis"]["analysis_mode"] == "COMPARATIVE"
    assert dossier["handoff_status"] != "HANDOFF_READY"


def test_missing_locator_blocks_handoff_ready() -> None:
    bare = {"claim_id": "fact-bare", "class": "FACT", "text": "Valor publicado.", "evidence_id": "doc-1"}
    assert claim_is_located(bare) is False
    dossier = _assemble(claims=[bare])
    assert dossier["handoff_status"] != "HANDOFF_READY"
    assert "missing_locator_blocks_handoff_ready" in dossier["reason_codes"]


def test_official_live_false_without_verification_clock() -> None:
    dossier = _assemble(retrieved_at=None, verified_at=None, bytes_obtained=False)
    assert dossier["gates"]["official_live"] is False
    assert dossier["handoff_status"] != "HANDOFF_READY"


def test_dsn_and_api_paths_share_consumer_shape() -> None:
    api = _assemble(analysis_id="from-api")
    dsn = _assemble(analysis_id="from-dsn")
    assert same_consumer_shape(api, dsn)
    for payload in (api, dsn):
        assert payload["schema"] == "official-live-authority-dossier/1.1"
        assert payload["gates"]["publication_authorization"] is False
        assert payload["provenance"]["replay_command"]


def test_schema_1_0_consumer_payload_still_validates() -> None:
    payload = {
        "schema": "official-live-authority-dossier/1.0",
        "analysis_id": "legacy",
        "identity": _identity(),
        "gates": {
            "official_live": False,
            "handoff_status": "DATA_HOLD",
            "publication_authorization": False,
            "index_authorization": False,
            "commercial_relationship_claim": False,
        },
    }
    ok, reasons = validate_consumer_dossier(payload)
    assert ok is True
    assert reasons == ()


def test_hashes_are_deterministic_excluding_clocks() -> None:
    first = _assemble(retrieved_at="2026-08-17T12:00:00Z", verified_at="2026-08-17T12:00:00Z")
    second = _assemble(retrieved_at="2026-08-17T18:00:00Z", verified_at="2026-08-17T18:00:00Z")
    assert first["content_hash"] == second["content_hash"]
    assert first["content_hash"] == content_hash(
        strip_temporal_for_hash({k: v for k, v in first.items() if k != "content_hash"})
    )
    assert is_sha256(first["content_hash"])


def test_publication_index_authorization_stay_false() -> None:
    dossier = _assemble()
    ok, reasons = validate_consumer_dossier(
        {
            **dossier,
            "gates": {**dossier["gates"], "publication_authorization": True, "index_authorization": True},
        }
    )
    assert ok is False
    assert "publication_authorization_must_be_false" in reasons
    assert "index_authorization_must_be_false" in reasons


def test_atomic_rendezvous_ready_xor_blocked(tmp_path: Path) -> None:
    ready = _assemble()
    dest = tmp_path / "official-live-01"
    files = build_rendezvous_files(
        [ready],
        producer={"repo": "tjsasakifln/extra-cli", "branch": "goal/x", "commit": "abc"},
        generated_at="2026-08-17T12:00:00Z",
        replay_command="python3 -m scripts.historical_contract_authority --mode official-live --limit 2",
        query_window={"start": "2026-08-03", "end": "2026-08-17"},
        live_meta={"sources": ["pncp_consulta_api"], "production_write": False, "backfill": False},
        candidate_log=[{"contract_id": "x", "disposition": "entered", "reason": "adjacency"}],
        tests=["tests/historical_contract_authority/test_official_live_handoff.py"],
    )
    write_atomic_rendezvous(dest, files)
    assert (dest / "READY.json").is_file()
    assert not (dest / "BLOCKED.json").exists()
    ready_doc = json.loads((dest / "READY.json").read_text(encoding="utf-8"))
    assert ready_doc["status"] == "READY"
    assert ready_doc["dossier_count"] == 1
    hold = _assemble(insight="", claims=[_claim()], bytes_obtained=False, retrieved_at=None, verified_at=None)
    blocked_dest = tmp_path / "blocked"
    blocked_files = build_rendezvous_files(
        [hold],
        producer={"repo": "tjsasakifln/extra-cli", "branch": "goal/x", "commit": "abc"},
        generated_at="2026-08-17T12:00:00Z",
        replay_command="replay",
        query_window={"start": "2026-08-03", "end": "2026-08-17"},
        live_meta={"sources": ["pncp_consulta_api"], "reason_codes": ["no_handoff_ready_dossier"]},
        candidate_log=[],
        tests=[],
    )
    write_atomic_rendezvous(blocked_dest, blocked_files)
    assert (blocked_dest / "BLOCKED.json").is_file()
    assert not (blocked_dest / "READY.json").exists()
    assert json.loads((blocked_dest / "BLOCKED.json").read_text(encoding="utf-8"))["status"] == "BLOCKED"


def test_no_production_write_and_no_backfill_flags() -> None:
    dossier = _assemble()
    files = build_rendezvous_files(
        [dossier],
        producer={"repo": "tjsasakifln/extra-cli", "branch": "goal/x", "commit": "abc"},
        generated_at="2026-08-17T12:00:00Z",
        replay_command="replay",
        query_window={"start": "2026-08-03", "end": "2026-08-17"},
        live_meta={"production_write": False, "backfill": False, "sources": ["pncp_consulta_api"]},
        candidate_log=[],
        tests=[],
    )
    manifest = json.loads(files["manifest.json"])
    assert manifest["production_write"] is False
    assert manifest["backfill"] is False
    assert manifest["publication_authorization"] is False
    assert manifest["index_authorization"] is False
