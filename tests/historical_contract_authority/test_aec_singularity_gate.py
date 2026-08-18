"""Campaign-02 gates: AEC discard, SPA hash isolation, READY XOR BLOCKED, canary identity."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.historical_contract_authority.aec import (
    REASON_GENERIC_PURCHASE,
    REASON_INSUFFICIENT_AEC,
    REASON_LOCACAO_VEICULOS,
    aec_disposition,
    rank_aec_candidates,
)
from scripts.historical_contract_authority.consumer import validate_consumer_dossier
from scripts.historical_contract_authority.official_live import (
    _insight_for,
    build_rendezvous_files,
    dossier_from_group,
    extract_clause_excerpts,
    parse_pncp_contrato_id,
    pncp_contract_urls,
    select_candidates,
    termos_to_records,
    write_atomic_rendezvous,
)
from scripts.official_contract_semantics.extract import extract_payload
from scripts.official_contract_semantics.identity import raw_record_hash_for
from scripts.official_contract_semantics.models import observation_from_mapping
from tests.historical_contract_authority.test_official_live_handoff import (
    DIGEST,
    _assemble,
    _claim,
)


def _obs(*, contract_id: str, objeto: str, source_kind: str = "contract", **extra):
    raw = {
        "schema_version": "official-contract-observation/1.1",
        "observation_id": f"obs-{contract_id}-{source_kind}",
        "source_system": "pncp",
        "source_kind": source_kind,
        "official_url": extra.get("official_url") or "https://pncp.gov.br/api/consulta/v1/contratos?page=1",
        "source_document_id": contract_id,
        "source_document_sha256": extra.get("sha256") or DIGEST,
        "contract_identifier": contract_id,
        "object_text": objeto,
        "value_amount": extra.get("value_amount", None if source_kind == "process_document" else "100000.00"),
        "value_semantic": extra.get("value_semantic", None if source_kind == "process_document" else "valor_global"),
        "raw_record_hash": extra.get("sha256") or DIGEST,
        "status": "observed",
        "confidence_class": "explicit_structured_field",
        "locator": extra.get("locator") or {"json_path": "$.objetoContrato"},
        "extractor_version": "official-contract-semantics-extract/1.1",
        "amendment_type": extra.get("amendment_type"),
        "amendment_value_delta": extra.get("amendment_value_delta"),
        "currency": "BRL",
    }
    return observation_from_mapping(raw)


def test_locacao_veiculos_is_non_aec_discard() -> None:
    eligible, reason = aec_disposition("Locação de veículos automotores sem motorista para a frota municipal.")
    assert eligible is False
    assert reason == REASON_LOCACAO_VEICULOS
    grouped = {
        "15537199000169-2-000008/2026": [
            _obs(contract_id="15537199000169-2-000008/2026", objeto="Locacao de veiculos automotores sem motorista.")
        ]
    }
    chosen, log = select_candidates(grouped, limit=20)
    assert chosen == []
    assert any(item["reason"] == REASON_LOCACAO_VEICULOS for item in log)


def test_mao_de_obra_alone_is_not_aec() -> None:
    eligible, reason = aec_disposition(
        "CONTRATAÇÃO DE EMPRESA ESPECIALIZADA NA PRESTAÇÃO DE SERVIÇOS DE LIMPEZA, COM DEDICAÇÃO EXCLUSIVA DE MÃO DE OBRA"
    )
    assert eligible is False
    assert reason == REASON_INSUFFICIENT_AEC


def test_generic_purchase_and_identity_only_are_discarded() -> None:
    assert aec_disposition("Aquisição de material de expediente para a secretaria.") == (False, REASON_GENERIC_PURCHASE)
    assert aec_disposition("Fornecimento de botijão de gás por registro de preços.") == (False, REASON_INSUFFICIENT_AEC)
    rows = [
        {"contract_id": "a", "object_text": "Pavimentação asfáltica em CBUQ no município X"},
        {"contract_id": "b", "object_text": "Locação de veículos especiais"},
        {"contract_id": "c", "object_text": "Aquisição de gêneros alimentícios"},
    ]
    entered, log = rank_aec_candidates(rows, limit=20)
    assert [item["contract_id"] for item in entered] == ["a"]
    reasons = {item["contract_id"]: item["reason"] for item in log}
    assert reasons["b"] == REASON_LOCACAO_VEICULOS
    assert reasons["c"] == REASON_GENERIC_PURCHASE


def test_spa_portal_page_must_not_inherit_listing_sha256() -> None:
    listing = b'{"data":[{"objetoContrato":"obra"}]}'
    spa = b"<!doctype html><html><body>angular-shell</body></html>"
    listing_sha = raw_record_hash_for(listing)
    spa_sha = raw_record_hash_for(spa)
    assert listing_sha != spa_sha
    listing_obs = _obs(
        contract_id="82940433000194-1-000010/2026",
        objeto="Pavimentacao asfaltica com CBUQ",
        official_url="https://pncp.gov.br/api/consulta/v1/contratos?pagina=1",
        sha256=listing_sha,
    )
    page_obs = _obs(
        contract_id="82940433000194-1-000010/2026",
        objeto="Pavimentacao asfaltica com CBUQ",
        source_kind="official_page",
        official_url="https://pncp.gov.br/app/contratos/82940433000194-1-000010/2026",
        sha256=spa_sha,
    )
    dossier = dossier_from_group(
        "82940433000194-1-000010/2026",
        [listing_obs, page_obs],
        retrieved_at="2026-08-18T12:00:00Z",
        verified_at="2026-08-18T12:00:00Z",
        source_as_of=None,
        as_of="2026-08-18T12:00:00Z",
        producer={"repo": "tjsasakifln/extra-cli", "branch": "goal/x", "commit": "abc"},
        replay_command="replay",
        query_window={"start": "2026-07-19", "end": "2026-08-18", "uf": "SC"},
        bytes_obtained=True,
        disposition="entered",
        disposition_reason="aec_engineering_or_construction",
    )
    facts = [item for item in dossier["factual_matrix"]["claims"] if item.get("class") == "FACT"]
    assert facts
    for claim in facts:
        assert claim["url"] != page_obs.official_url
        assert claim["sha256"] != spa_sha
        assert claim["sha256"] == listing_sha


def test_ready_requires_located_facts_and_singular_insight() -> None:
    listing_only = _obs(contract_id="x-aec", objeto="Pavimentacao asfaltica em Brusque")
    assert _insight_for([listing_only], []) == ""
    hold = _assemble(insight="", claims=[_claim()])
    assert hold["handoff_status"] != "HANDOFF_READY"
    ready = _assemble()
    assert ready["handoff_status"] == "HANDOFF_READY"
    assert ready["analysis"]["singular_insight"]
    facts = [item for item in ready["factual_matrix"]["claims"] if item.get("class") == "FACT"]
    assert facts and all(item.get("url") and item.get("sha256") and item.get("locator") for item in facts)


def test_ready_and_blocked_are_mutually_exclusive(tmp_path: Path) -> None:
    ready = _assemble()
    files = build_rendezvous_files(
        [ready],
        producer={"repo": "tjsasakifln/extra-cli", "branch": "goal/x", "commit": "abc"},
        generated_at="2026-08-18T12:00:00Z",
        replay_command="replay",
        query_window={"start": "2026-07-19", "end": "2026-08-18"},
        live_meta={"production_write": False, "backfill": False},
        candidate_log=[{"contract_id": "x", "disposition": "entered", "reason": "aec_engineering_or_construction"}],
        tests=[],
    )
    dest = tmp_path / "ready"
    write_atomic_rendezvous(dest, files)
    assert (dest / "READY.json").is_file()
    assert not (dest / "BLOCKED.json").exists()
    hold = _assemble(insight="", bytes_obtained=False, retrieved_at=None, verified_at=None)
    blocked_files = build_rendezvous_files(
        [hold],
        producer={"repo": "tjsasakifln/extra-cli", "branch": "goal/x", "commit": "abc"},
        generated_at="2026-08-18T12:00:00Z",
        replay_command="replay",
        query_window={"start": "2026-07-19", "end": "2026-08-18"},
        live_meta={"production_write": False, "backfill": False, "dsn_present": False},
        candidate_log=[
            {"contract_id": "loc", "disposition": "exited", "reason": REASON_LOCACAO_VEICULOS},
            {"contract_id": "aec", "disposition": "entered", "reason": "aec_engineering_or_construction"},
        ],
        tests=[],
    )
    blocked_dest = tmp_path / "blocked"
    write_atomic_rendezvous(blocked_dest, blocked_files)
    assert (blocked_dest / "BLOCKED.json").is_file()
    assert not (blocked_dest / "READY.json").exists()
    blocked = json.loads((blocked_dest / "BLOCKED.json").read_text(encoding="utf-8"))
    assert blocked["status"] == "BLOCKED"
    assert blocked["ranking"]
    assert isinstance(blocked["smallest_next_verifiable_step"], str)
    assert blocked["smallest_next_verifiable_step"]
    assert blocked["smallest_next_verifiable_step"].count("http") <= 1 or "LOCAL_DATALAKE_DSN" in blocked[
        "smallest_next_verifiable_step"
    ]


def test_two_canaries_share_analysis_id_and_content_hash() -> None:
    first = _assemble(retrieved_at="2026-08-18T12:00:00Z", verified_at="2026-08-18T12:00:00Z")
    second = _assemble(retrieved_at="2026-08-18T18:00:00Z", verified_at="2026-08-18T18:00:00Z")
    assert first["analysis_id"] == second["analysis_id"]
    assert first["content_hash"] == second["content_hash"]
    assert first["identity"]["contract_id"] == second["identity"]["contract_id"]


def test_apostilamento_gestor_fiscal_is_not_singular_insight() -> None:
    contract_id = "88117700000101-2-000193/2026"
    body = json.dumps(
        [
            {
                "tipoTermoContratoNome": "Termo de Apostilamento",
                "objetoTermoContrato": "Alteração do gestor / fiscal: ",
                "valorAcrescido": 0.0,
                "qualificacaoAcrescimoSupressao": False,
                "qualificacaoVigencia": False,
                "qualificacaoReajuste": False,
                "prazoAditadoDias": 0,
            }
        ],
        ensure_ascii=False,
    )
    records = termos_to_records(
        contract_id=contract_id,
        termos_url="https://pncp.gov.br/api/pncp/v1/orgaos/88117700000101/contratos/2026/193/termos",
        body=body,
        sha256=raw_record_hash_for(body.encode("utf-8")),
        retrieved_at="2026-08-18T12:00:00Z",
        base=_obs(contract_id=contract_id, objeto="Pavimentacao asfaltica com CBUQ"),
    )
    assert records == []
    listing = _obs(contract_id=contract_id, objeto="Pavimentacao asfaltica com CBUQ", value_amount="443318.56")
    assert _insight_for([listing], []) == ""


def test_pdf_reajuste_page_is_material_insight() -> None:
    page = _obs(
        contract_id="88117700000101-2-000193/2026",
        objeto=(
            "6 DO REAJUSTE, REEQUILÍBRIO E REPACTUAÇÃO 6.3.1 Para Obras Rodoviárias os "
            "Índices de Reajustamento de Obras Rodoviárias divulgados pelo DNIT. 6.3.2 INCC."
        ),
        source_kind="process_document",
        official_url="https://pncp.gov.br/pncp-api/v1/orgaos/88117700000101/contratos/2026/193/arquivos/2",
        locator={"page": 4, "section": "contrato-oficial"},
    )
    listing = _obs(
        contract_id="88117700000101-2-000193/2026",
        objeto="reperfilagem asfáltica com CBUQ totalizando 528.00 metros lineares",
        value_amount="443318.56",
    )
    insight = _insight_for([listing, page], [])
    assert "reajuste" in insight.casefold()
    dossier = dossier_from_group(
        "88117700000101-2-000193/2026",
        [listing, page],
        retrieved_at="2026-08-18T12:00:00Z",
        verified_at="2026-08-18T12:00:00Z",
        source_as_of=None,
        as_of="2026-08-18T12:00:00Z",
        producer={"repo": "tjsasakifln/extra-cli", "branch": "goal/x", "commit": "abc"},
        replay_command="replay",
        query_window={"start": "2026-07-19", "end": "2026-08-18", "uf": "BR"},
        bytes_obtained=True,
        disposition="entered",
        disposition_reason="aec_engineering_or_construction",
    )
    assert dossier["handoff_status"] == "HANDOFF_READY"
    facts = [item for item in dossier["factual_matrix"]["claims"] if item.get("class") == "FACT"]
    pdf_facts = [item for item in facts if "arquivos/2" in str(item.get("url"))]
    assert pdf_facts
    assert all(item.get("locator", {}).get("page") == 4 for item in pdf_facts)
    assert dossier["factual_matrix"]["calculations"]
    from decimal import Decimal

    expected = (Decimal("443318.56") / Decimal("528.00")).quantize(Decimal("0.0001"))
    assert dossier["factual_matrix"]["calculations"][0]["result"] == format(expected, "f")
    assert dossier["factual_matrix"]["calculations"][0]["inputs"]["metros_lineares"] == "528.00"


def test_area_m2_ratio_uses_brazilian_thousands() -> None:
    listing = _obs(
        contract_id="14862788000150-2-000069/2026",
        objeto="Pavimentação em Paralelepípedo de 4.710,00 m² de ruas no município de São Gonçalo do Piauí",
        value_amount="719177.48",
    )
    page = _obs(
        contract_id="14862788000150-2-000069/2026",
        objeto="12.2 os preços contratados poderão sofrer reajuste após o interregno de um ano, INCC",
        source_kind="process_document",
        official_url="https://pncp.gov.br/pncp-api/v1/orgaos/14862788000150/contratos/2026/69/arquivos/1",
        locator={"page": 14, "section": "contrato-oficial"},
    )
    dossier = dossier_from_group(
        "14862788000150-2-000069/2026",
        [listing, page],
        retrieved_at="2026-08-18T12:00:00Z",
        verified_at="2026-08-18T12:00:00Z",
        source_as_of=None,
        as_of="2026-08-18T12:00:00Z",
        producer={"repo": "tjsasakifln/extra-cli", "branch": "goal/x", "commit": "abc"},
        replay_command="replay",
        query_window={"start": "2026-07-19", "end": "2026-08-18", "uf": "BR"},
        bytes_obtained=True,
        disposition="entered",
        disposition_reason="aec_engineering_or_construction",
    )
    from decimal import Decimal

    expected = (Decimal("719177.48") / Decimal("4710.00")).quantize(Decimal("0.0001"))
    calcs = dossier["factual_matrix"]["calculations"]
    assert calcs
    assert calcs[0]["inputs"]["area_m2"] == "4710.00"
    assert calcs[0]["result"] == format(expected, "f")


FGV_COLUNA_35_PAGE = (
    "12.2. Dentro do prazo de vigência do contrato e mediante solicitação da contratada, "
    "os preços contratados poderão sofrer reajuste após o interregno de um ano, contado a "
    "partir da data do orçamento a que a proposta se referir, conforme a seguinte fórmula: "
    "R = Valor do reajuste procurado; V = Valor contratual da obra/serviço a ser reajustado; "
    "Io = Índice inicial. 12.3. O índice de reajuste empregado na fórmula acima será o "
    "Índice Nacional da Construção Civil – Coluna 35, calculado e publicado pela Fundação "
    "Getúlio Vargas na revista Conjuntura Econômica, salvo de outro índice for indicado na "
    "Parte Específica deste Contrato. 12.4. Nos reajustes subsequentes ao primeiro, o "
    "interregno mínimo de um ano será contado a partir dos efeitos financeiros do último reajuste."
)


def test_fgv_coluna_35_page_does_not_invent_dnit_or_reequilibrio() -> None:
    """Drive shipped insight/FACT assembly with the retrieved FGV Coluna 35 clause.

    The live PDF names Fundação Getúlio Vargas / Coluna 35 and does not mention
    DNIT or reequilíbrio. A templated family string must fail this test.
    """
    assert "dnit" not in FGV_COLUNA_35_PAGE.casefold()
    assert "reequilibr" not in FGV_COLUNA_35_PAGE.casefold()
    excerpts = extract_clause_excerpts(FGV_COLUNA_35_PAGE)
    kinds = {kind for kind, _excerpt in excerpts}
    assert "indice" in kinds
    assert any("coluna 35" in excerpt.casefold() for _kind, excerpt in excerpts)
    listing = _obs(
        contract_id="14862788000150-2-000069/2026",
        objeto="Pavimentação em Paralelepípedo de 4.710,00 m² de ruas no município de São Gonçalo do Piauí",
        value_amount="719177.48",
    )
    page = _obs(
        contract_id="14862788000150-2-000069/2026",
        objeto=FGV_COLUNA_35_PAGE,
        source_kind="process_document",
        official_url="https://pncp.gov.br/pncp-api/v1/orgaos/14862788000150/contratos/2026/69/arquivos/1",
        locator={"page": 14, "section": "contrato-oficial"},
    )
    messy = _obs(
        contract_id="14862788000150-2-000069/2026",
        objeto=(
            "te do valor contratual será utilizado o Índice Nacional da Construção Civil – Coluna 35, "
            "calculado e publicado pela Fundação Getúlio Vargas, conforme já indicado na Parte Geral."
        ),
        source_kind="process_document",
        official_url="https://pncp.gov.br/pncp-api/v1/orgaos/14862788000150/contratos/2026/69/arquivos/1",
        locator={"page": 46, "section": "contrato-oficial"},
    )
    insight = _insight_for([listing, page, messy], [])
    blob = insight.casefold()
    assert "dnit" not in blob
    assert "reequilibr" not in blob
    assert "coluna 35" in blob
    assert "índice nacional da construção civil" in blob or "indice nacional da construcao civil" in blob
    assert "12.3" in insight
    assert not insight.casefold().startswith("te do valor")
    dossier = dossier_from_group(
        "14862788000150-2-000069/2026",
        [listing, page],
        retrieved_at="2026-08-18T12:00:00Z",
        verified_at="2026-08-18T12:00:00Z",
        source_as_of=None,
        as_of="2026-08-18T12:00:00Z",
        producer={"repo": "tjsasakifln/extra-cli", "branch": "goal/x", "commit": "abc"},
        replay_command="replay",
        query_window={"start": "2026-07-19", "end": "2026-08-18", "uf": "BR"},
        bytes_obtained=True,
        disposition="entered",
        disposition_reason="aec_engineering_or_construction",
    )
    assert dossier["handoff_status"] == "HANDOFF_READY"
    facts = [item for item in dossier["factual_matrix"]["claims"] if item.get("class") == "FACT"]
    pdf_facts = [item for item in facts if "arquivos/1" in str(item.get("url"))]
    assert pdf_facts
    assert all(not str(item.get("claim_id")).startswith("fact-object-") for item in pdf_facts)
    assert all(not str(item.get("text")).startswith("Objeto oficial:") for item in pdf_facts)
    joined = " ".join(str(item.get("text") or "") for item in pdf_facts).casefold()
    assert "dnit" not in joined
    assert "reequilibr" not in joined
    assert "coluna 35" in joined
    analysis_blob = " ".join(
        [
            str(dossier["analysis"].get("singular_insight") or ""),
            str(dossier["analysis"].get("what_documents_show") or ""),
        ]
    ).casefold()
    assert "dnit" not in analysis_blob
    assert "reequilibr" not in analysis_blob
    assert "coluna 35" in analysis_blob


def test_termos_bytes_drive_insight_and_ratio() -> None:
    contract_id = "82940433000194-1-000010/2026"
    termos = [
        {
            "tipoTermoContratoNome": "Termo Aditivo de valor",
            "objetoTermoContrato": "Acréscimo quantitativo da planilha de pavimentação",
            "valorAcrescimo": "15000.00",
            "dataAssinatura": "2026-08-01",
        }
    ]
    body = json.dumps(termos, ensure_ascii=False)
    digest = raw_record_hash_for(body.encode("utf-8"))
    records = termos_to_records(
        contract_id=contract_id,
        termos_url="https://pncp.gov.br/api/pncp/v1/orgaos/82940433000194/contratos/2026/10/termos",
        body=body,
        sha256=digest,
        retrieved_at="2026-08-18T12:00:00Z",
        base=_obs(contract_id=contract_id, objeto="Pavimentacao asfaltica"),
    )
    assert records
    extracted = extract_payload(records)
    assert extracted.observations
    listing = _obs(contract_id=contract_id, objeto="Pavimentacao asfaltica em Brusque", value_amount="100000.00")
    items = [listing, *extracted.observations]
    insight = _insight_for(items, [])
    assert insight
    dossier = dossier_from_group(
        contract_id,
        items,
        retrieved_at="2026-08-18T12:00:00Z",
        verified_at="2026-08-18T12:00:00Z",
        source_as_of=None,
        as_of="2026-08-18T12:00:00Z",
        producer={"repo": "tjsasakifln/extra-cli", "branch": "goal/x", "commit": "abc"},
        replay_command="replay",
        query_window={"start": "2026-07-19", "end": "2026-08-18", "uf": "SC"},
        bytes_obtained=True,
        disposition="entered",
        disposition_reason="aec_with_amendment_artifact",
    )
    assert dossier["analysis"]["singular_insight"]
    assert dossier["factual_matrix"]["calculations"]
    calc = dossier["factual_matrix"]["calculations"][0]
    assert calc["inputs"]["valor_base"] == "100000.00"
    assert calc["inputs"]["valor_termo_delta"] == "15000.00"
    assert calc["result"] == "0.1500"
    ok, reasons = validate_consumer_dossier({**dossier, "gates": {**dossier["gates"], "handoff_status": "HANDOFF_READY"}})
    assert ok is True, reasons
    assert dossier["handoff_status"] == "HANDOFF_READY"


def test_non_aec_sc_does_not_consume_aec_shortlist() -> None:
    """Generic SC listings must be logged and must not fill the 20-candidate AEC cap."""
    grouped = {}
    for i in range(20):
        cid = f"01613101000109-2-{i:06d}/2026"
        grouped[cid] = [_obs(contract_id=cid, objeto="UTENSÍLIOS DE COZINHA - LEI 14.133/2021")]
    aec_id = "82940433000194-1-000010/2026"
    grouped[aec_id] = [_obs(contract_id=aec_id, objeto="Pavimentação asfáltica com CBUQ em Brusque")]
    chosen, log = select_candidates(grouped, limit=20)
    assert chosen == [aec_id]
    assert sum(1 for item in log if item["disposition"] == "entered") == 1
    assert sum(1 for item in log if item["reason"] == REASON_INSUFFICIENT_AEC) == 20


def test_parse_pncp_contrato_id_and_termos_url() -> None:
    parsed = parse_pncp_contrato_id("15537199000169-2-000008/2026")
    assert parsed == ("15537199000169", 2026, 8)
    urls = pncp_contract_urls("15537199000169-2-000008/2026")
    assert urls is not None
    assert urls["termos"].endswith("/contratos/2026/8/termos")
