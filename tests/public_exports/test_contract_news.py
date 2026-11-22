from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from scripts.official_contract_semantics.http_client import FetchResult
from scripts.public_exports import contract_news as news
from scripts.public_exports import market_radar as radar
from scripts.public_exports.contract_news_context import EvidenceResponse

NOW = dt.datetime(2026, 11, 19, 16, 0, tzinfo=dt.UTC)
ID = "11222333000181-2-000123/2026"
SECOND_ID = "11222333000181-2-000124/2026"


def payload(**changes):
    result = {
        "numeroControlePNCP": ID,
        "tipoContrato": {"id": 1, "nome": "Contrato (termo inicial)"},
        "receita": False,
        "tipoPessoa": "PJ",
        "niFornecedor": "04252011000110",
        "orgaoEntidade": {"cnpj": "11222333000181", "razaoSocial": "Município de Exemplo"},
        "nomeRazaoSocialFornecedor": "Construtora Exemplo Ltda",
        "objetoContrato": "Contratação de empresa para construção de escola municipal e instalações prediais.",
        "valorGlobal": "3250000.1234",
        "valorInicial": "3000000.0000",
        "dataPublicacaoPncp": "2026-11-18T17:41:00-03:00",
        "dataAtualizacao": "2026-11-19T11:30:00-03:00",
        "dataAssinatura": "2026-11-17",
        "dataVigenciaInicio": "2026-12-01",
        "dataVigenciaFim": "2027-12-01",
        "unidadeOrgao": {"municipioNome": "Exemplo", "ufSigla": "SC"},
    }
    result.update(changes)
    return result


def normalized(raw=None, **kwargs):
    return news.normalize_official(
        raw or payload(), contract_id=ID, checked_at=NOW, source_sha256="a" * 64, **kwargs,
    )


def fetched(raw, *, identity=ID):
    body = json.dumps(raw, ensure_ascii=False)
    return FetchResult(
        url=news.source_urls(identity)[1], ok=True, status=200, body=body,
        sha256=hashlib.sha256(body.encode()).hexdigest(), unavailability=None,
    )


def meta():
    return {
        "source_as_of": "2026-11-19T15:59:00Z",
        "ingestion_latest_at": "2026-11-19T14:00:00Z",
        "window_start": "2026-11-13",
        "window_end": "2026-11-19",
    }


def snapshot(ids, fetch, rechecks=()):
    return news.build_snapshot(
        ids, recheck_ids=rechecks, requested_rechecks=rechecks,
        metadata=meta(), fetch=fetch, clock=lambda: NOW,
        context_fetch=lambda url, limit, timeout: EvidenceResponse(url, 200, b"[]"),
    )


def test_full_official_object_typed_value_and_exact_sources():
    long_object = "Construção de escola pública com instalações elétricas, hidráulicas e sanitárias. " * 20
    record = normalized(payload(objetoContrato=long_object))
    assert len(record["object"]) > 500
    assert record["object"] == long_object.strip()
    assert record["value"] == {"amount": "3250000.1234", "kind": "valorGlobal", "currency": "BRL"}
    assert record["source_url"] == "https://pncp.gov.br/app/contratos/11222333000181/2026/123"
    assert record["source_api_url"] == "https://pncp.gov.br/api/pncp/v1/orgaos/11222333000181/contratos/2026/123"
    assert record["source_published_at"] == "2026-11-18T20:41:00Z"
    assert record["administrative_location"] == {"city": "Exemplo", "state": "SC"}
    assert record["supplier_type"] == "PJ"
    assert "niFornecedor" not in record
    assert "04252011000110" not in json.dumps(record)


def test_authoritative_editorial_scope_rejects_it_before_collecting_documents(tmp_path):
    scope_file = tmp_path / "scope.json"
    scope_file.write_text(json.dumps({"schema": news.EDITORIAL_SCOPE_SCHEMA, "lookback_days": 14,
                                      "exclude": r"\bmainframe\b", "include": [r"\bconstrucao\b"]}))
    lookback, scope = news.load_editorial_scope(scope_file)
    objects = {
        ID: payload(objetoContrato="Contratação de infraestrutura virtualizada com processamento em mainframe."),
        SECOND_ID: payload(numeroControlePNCP=SECOND_ID, dataPublicacaoPncp="2026-11-08T12:00:00Z"),
    }
    accessed = []

    def evidence(url, limit, timeout):
        accessed.append(url)
        return EvidenceResponse(url, 200, b"[]")

    result = news.build_snapshot(
        list(objects), recheck_ids=[], requested_rechecks=[], metadata=meta(),
        fetch=lambda identity: fetched(objects[identity], identity=identity), context_fetch=evidence,
        clock=lambda: NOW, editorial_scope=scope, lookback_days=lookback,
    )
    assert [row["id"] for row in result["records"]] == [SECOND_ID]
    assert result["selection"]["excluded"] == {"outside_editorial_scope": 1}
    assert len(accessed) == 1 and "/contratos/2026/124/arquivos" in accessed[0]
    scope_file.write_text('{"schema":"wrong"}')
    with pytest.raises(news.ExportError, match="invalid_editorial_scope"):
        news.load_editorial_scope(scope_file)


@pytest.mark.parametrize("global_value", [None, 0, "0.0000"])
def test_initial_fallback_names_its_actual_source_field(global_value):
    record = normalized(payload(valorGlobal=global_value))
    assert record["value"]["kind"] == "valorInicial"
    assert record["value"]["amount"] == "3000000.0000"


@pytest.mark.parametrize("changes,reason", [
    ({"valorGlobal": None, "valorInicial": None, "valorTotalEstimado": 1e9}, "no_positive"),
    ({"valorGlobal": "NaN"}, "invalid_value"),
    ({"valorGlobal": "Infinity"}, "invalid_value"),
    ({"valorGlobal": True}, "invalid_value"),
    ({"valorGlobal": -1}, "invalid_value"),
    ({"valorGlobal": "1000000000000000"}, "invalid_value"),
    ({"valorGlobal": "125.12345"}, "value_precision"),
    ({"tipoContrato": {"id": 7, "nome": "Empenho"}}, "not_initial_contract"),
    ({"tipoContrato": {"id": True, "nome": "Contrato"}}, "not_initial_contract"),
    ({"tipoContrato": {"id": 8, "nome": "Outros"}}, "not_initial_contract"),
    ({"tipoContrato": None}, "not_initial_contract"),
    ({"receita": True}, "not_expense_contract"),
    ({"receita": None}, "not_expense_contract"),
    ({"tipoPessoa": "PF"}, "supplier_not_legal_entity"),
    ({"tipoPessoa": "PE"}, "supplier_not_legal_entity"),
    ({"niFornecedor": "111.111.111-11"}, "invalid_supplier_identity"),
    ({"niFornecedor": "00000000000000"}, "invalid_supplier_identity"),
    ({"orgaoEntidade": {"cnpj": "04252011000110", "razaoSocial": "Outro órgão"}}, "buyer_identity_mismatch"),
    ({"numeroControlePNCP": SECOND_ID}, "official_identity_mismatch"),
    ({"objetoContrato": "Compra de medicamentos para construção de estoque de emergência municipal."}, "object_not_engineering"),
    ({"objetoContrato": "Locação de veículos para a secretaria de obras públicas do município."}, "object_not_engineering"),
    ({"objetoContrato": "Serviço de cobrança administrativa de impostos e taxas municipais."}, "object_not_engineering"),
    ({"objetoContrato": "Construção " + "x" * 5200}, "source_text_out_of_bounds"),
    ({"objetoContrato": "Obra"}, "source_text_out_of_bounds"),
    ({"dataPublicacaoPncp": None}, "invalid_source_publication"),
    ({"dataPublicacaoPncp": "2026-11-20T16:00:00Z"}, "invalid_source_publication"),
    ({"dataPublicacaoPncp": "2026-11-12T12:00:00Z"}, "outside_publication_window"),
    ({"dataPublicacaoPncp": "2025-06-01T12:00:00Z"}, "outside_publication_window"),
    ({"dataAssinatura": "2026-11-21"}, "future_signature"),
    ({"dataAssinatura": "2026-02-30"}, "invalid_source_date"),
    ({"dataVigenciaInicio": "2028-01-01"}, "inverted_validity"),
    ({"dataAtualizacao": "invalid"}, "invalid_source_update"),
    ({"dataAtualizacao": "2026-11-21T12:00:00Z"}, "invalid_source_update"),
])
def test_rejects_false_or_unfit_news_facts(changes, reason):
    with pytest.raises(news.ExportError, match=reason):
        normalized(payload(**changes))


def test_missing_optional_dates_and_location_stay_missing():
    record = normalized(payload(
        dataAssinatura=None, dataVigenciaInicio=None, dataVigenciaFim=None,
        dataAtualizacao=None, unidadeOrgao={"ufSigla": "XX"},
    ))
    assert record["signed_at"] is record["starts_at"] is record["ends_at"] is None
    assert record["administrative_location"] == {"city": None, "state": None}
    assert record["source_updated_at"] is None


def test_naive_pncp_clock_preserves_its_brazilian_calendar_day():
    record = normalized(payload(dataPublicacaoPncp="2026-11-13T00:05:00"))
    assert record["source_published_at"] == "2026-11-13T03:05:00Z"


def test_old_contract_only_allowed_for_explicit_correction():
    raw = payload(dataPublicacaoPncp="2025-07-01T12:00:00Z")
    with pytest.raises(news.ExportError, match="outside_publication_window"):
        normalized(raw)
    record = normalized(raw, correction=True)
    assert record["source_published_at"] == "2025-07-01T12:00:00Z"


def test_contact_and_personal_identifiers_are_sanitized():
    record = normalized(payload(objetoContrato=(
        "Construção de escola e instalações prediais. Contato ana@example.com "
        "(48) 99999-0000, CPF 123.456.789-00, documento 12345678900."
    )))
    text = json.dumps(record)
    for forbidden in ["ana@example.com", "99999", "123.456.789", "12345678900"]:
        assert forbidden not in text


def test_snapshot_ranks_confirmed_values_and_records_corrections():
    def fetch(identity):
        return fetched(payload(
            numeroControlePNCP=identity,
            valorGlobal="100.00" if identity == ID else "500.00",
            dataPublicacaoPncp="2025-01-01T12:00:00Z" if identity == ID else "2026-11-18T12:00:00Z",
        ), identity=identity)

    result = snapshot([SECOND_ID], fetch, rechecks=[ID])
    assert [item["id"] for item in result["records"]] == [SECOND_ID, ID]
    assert result["schema"] == news.SCHEMA
    assert result["selection"]["official_requests"] == 2
    assert result["recheck_results"] == [{"id": ID, "status": "verified", "reason": "official_payload_confirmed"}]


def test_unavailable_recheck_is_distinct_from_ineligible_source():
    failed = FetchResult("https://pncp.gov.br", False, 503, None, None, None)
    result = snapshot([SECOND_ID], lambda identity: failed if identity == ID else fetched(
        payload(numeroControlePNCP=SECOND_ID), identity=SECOND_ID,
    ), rechecks=[ID])
    assert result["recheck_results"][0]["status"] == "unavailable"
    result = snapshot([], lambda identity: fetched(payload(tipoPessoa="PF")), rechecks=[ID])
    assert result["recheck_results"][0]["status"] == "ineligible"
    assert not result["records"]


def test_total_official_outage_cannot_overwrite_a_previous_snapshot():
    failed = FetchResult("https://pncp.gov.br", False, 503, None, None, None)
    with pytest.raises(news.ExportError, match="all_official_requests_unavailable"):
        snapshot([ID], lambda identity: failed)


@pytest.mark.parametrize("body", ["{broken", "[]", "null"])
def test_malformed_official_payload_is_unavailable_not_semantic_withdrawal(body):
    failed = FetchResult(
        news.source_urls(ID)[1], True, 200, body, hashlib.sha256(body.encode()).hexdigest(), None,
    )
    result = snapshot([SECOND_ID], lambda identity: failed if identity == ID else fetched(
        payload(numeroControlePNCP=SECOND_ID), identity=SECOND_ID,
    ), rechecks=[ID])
    assert result["recheck_results"][0]["status"] == "unavailable"
    with pytest.raises(news.ExportError, match="all_official_requests_unavailable"):
        snapshot([], lambda identity: failed, rechecks=[ID])


def test_budget_and_duplicate_identity_fail_before_network():
    fetch = MagicMock()
    with pytest.raises(news.ExportError, match="request_budget_exceeded"):
        snapshot([ID] * 21, fetch)
    with pytest.raises(news.ExportError, match="duplicate_candidate_identity"):
        snapshot([ID, ID], fetch)
    with pytest.raises(news.ExportError, match="duplicate_candidate_identity"):
        snapshot([ID], fetch, rechecks=[ID])
    fetch.assert_not_called()


def test_exact_request_limit_is_respected():
    identities = [f"11222333000181-2-{index:06d}/2026" for index in range(1, 21)]
    called = []

    def fetch(identity):
        called.append(identity)
        return fetched(payload(numeroControlePNCP=identity), identity=identity)

    result = snapshot(identities, fetch)
    assert len(called) == 20
    assert result["selection"]["official_requests"] == 20


def test_published_ids_contract_and_request_membership(tmp_path):
    path = tmp_path / "published.json"
    path.write_text(json.dumps({"published_ids": [ID, SECOND_ID], "recheck_ids": [ID]}))
    assert news.load_published_ids(path) == ([ID, SECOND_ID], [ID])
    for bad in [
        [ID], {"published_ids": [ID], "recheck_ids": [SECOND_ID]},
        {"published_ids": [ID, ID], "recheck_ids": []},
        {"published_ids": [ID], "recheck_ids": [], "sql": "DROP TABLE"},
        {"published_ids": ["https://localhost"], "recheck_ids": []},
    ]:
        path.write_text(json.dumps(bad))
        with pytest.raises(news.ExportError):
            news.load_published_ids(path)


def test_candidate_query_uses_persisted_dates_explicit_ids_and_bounded_limit():
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (NOW, NOW - dt.timedelta(hours=1))
    cursor.fetchall.side_effect = [[(ID,)], [(SECOND_ID, Decimal("10000.00"))]]
    fresh, rechecks, metadata = news.select_candidates(
        conn, now=NOW, published_ids=[ID], recheck_ids=[ID],
    )
    assert fresh == [SECOND_ID]
    assert rechecks == [ID]
    assert metadata["window_start"] == "2026-11-13"
    selection = cursor.execute.call_args_list[-1]
    assert selection.args[0] == news.SOURCE_SQL
    assert selection.args[1][-1] == 19
    assert selection.args[1][-2] == [ID]
    assert "data_publicacao_fonte BETWEEN" in selection.args[0]
    assert "valorGlobal" not in selection.args[0]


def test_stale_lake_refused_before_any_candidate_appears():
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (NOW, NOW - dt.timedelta(days=3))
    with pytest.raises(news.ExportError, match="stale_lake_ingestion"):
        news.select_candidates(conn, now=NOW, published_ids=[], recheck_ids=[])
    assert cursor.execute.call_count == 1


def test_snapshot_write_is_atomic_private_and_refuses_oversize(tmp_path):
    output = tmp_path / "facts.json"
    result = snapshot([ID], lambda identity: fetched(payload()))
    digest = news.write_snapshot(output, result)
    before = output.read_bytes()
    assert hashlib.sha256(before).hexdigest() == digest
    assert json.loads(before)["records"][0]["id"] == ID
    assert os.stat(output).st_mode & 0o777 == 0o440
    with pytest.raises(news.ExportError, match="snapshot_too_large"):
        news.write_snapshot(output, {"oversize": "x" * news.MAX_SNAPSHOT_BYTES})
    assert output.read_bytes() == before
    assert not list(tmp_path.glob(".facts.json.*"))


def test_output_lock_rejects_concurrency_and_symlink(tmp_path):
    path = tmp_path / "facts.json"
    with news._output_lock(path):
        with pytest.raises(news.ExportError, match="export_already_running"):
            with news._output_lock(path):
                pytest.fail("lock admitted a concurrent writer")
    target = tmp_path / "target"
    target.write_text("keep")
    path.symlink_to(target)
    with pytest.raises(news.ExportError, match="output_boundary_not_provisioned"):
        with news._output_lock(path):
            pytest.fail("symlink admitted")


def test_bounded_http_transport_refuses_oversized_body_and_redirect():
    response = MagicMock()
    response.status = 200
    response.read.return_value = b"x" * (news.MAX_BODY_BYTES + 1)
    with news._BoundedResponse(response) as bounded:
        with pytest.raises(OSError, match="too_large"):
            bounded.read()
    response.close.assert_called_once()
    request = MagicMock(full_url=news.source_urls(ID)[1])
    with pytest.raises(news.urllib.error.HTTPError):
        news._NoRedirect().redirect_request(request, None, 302, "redirect", {}, "http://localhost/")


def test_transport_has_one_request_and_no_shared_cache(monkeypatch):
    call = MagicMock(return_value=fetched(payload()))
    monkeypatch.setattr(news, "fetch_official", call)
    news.fetch_contract(ID)
    assert call.call_count == 1
    assert call.call_args.args == (news.source_urls(ID)[1],)
    assert call.call_args.kwargs["retries"] == 0
    assert call.call_args.kwargs["timeout_s"] == 15
    assert "cache_dir" not in call.call_args.kwargs


def test_cli_dependency_error_does_not_print_credentials(monkeypatch, capsys, tmp_path):
    def fail(**_kwargs):
        raise RuntimeError("postgresql://private:secret@host/db")

    monkeypatch.setattr(news, "export_from_postgres", fail)
    assert news.main(["--output", str(tmp_path / "facts.json")]) == 1
    output = capsys.readouterr().out
    assert "secret" not in output and "postgresql" not in output
    assert json.loads(output)["reason"] == "export_dependency_failed"


def radar_snapshot(tmp_path):
    rows = []
    for identity, value, published in [(ID, "100000000", "2025-11-18"), (SECOND_ID, "1000000", "2026-11-18")]:
        rows.append({
            "contrato_id": identity, "orgao_cnpj": identity[:14], "orgao_nome": "Órgão Exemplo",
            "fornecedor_cnpj": "04252011000110", "fornecedor_nome": "Construtora Exemplo Ltda",
            "objeto_contrato": "Construção de escola e instalações prediais para atendimento da rede municipal.",
            "valor_total": Decimal(value), "data_publicacao_fonte": dt.date.fromisoformat(published),
            "data_inicio": None, "data_fim": None, "source_updated_at": NOW,
            "supplier_id_type": "CNPJ", "quality_state": "VALID", "status_normalized": "ACTIVE_PROVEN",
            "uf": "SC", "municipio": "Exemplo",
        })
    radar.build_snapshot(
        rows, output_dir=tmp_path, today=NOW.date(), generated_at=NOW,
        source_meta={
            "source_as_of": NOW, "ingestion_latest_at": NOW - dt.timedelta(hours=1),
            "window_start": dt.date(2024, 11, 19), "window_end": NOW.date(),
            "candidate_rows": 2, "qualified_rows": 2,
        },
    )
    return tmp_path / "current.json"


def rewrite_pointer(path, mutate):
    pointer = json.loads(path.read_text())
    mutate(pointer)
    path.chmod(0o600)
    path.write_text(json.dumps(pointer))
    path.chmod(0o440)


def test_real_sqlite_radar_selection_excludes_published_and_rechecks_old(tmp_path):
    pointer = radar_snapshot(tmp_path)
    fresh, due, metadata = news.select_from_radar(pointer, now=NOW, published_ids=[ID], recheck_ids=[ID])
    assert fresh == [SECOND_ID]
    assert due == [ID]
    assert metadata["radar_contract"] == radar.SNAPSHOT_SCHEMA
    assert metadata["source_as_of"] == "2026-11-19T16:00:00Z"
    assert metadata["window_start"] == "2026-11-13"
    fresh, due, _ = news.select_from_radar(pointer, now=NOW, published_ids=[ID, SECOND_ID], recheck_ids=[])
    assert fresh == due == []


@pytest.mark.parametrize("mutate,reason", [
    (lambda p: p.update(schema="wrong"), "invalid_radar_pointer"),
    (lambda p: p.update(file="../../outside.sqlite"), "invalid_radar_filename"),
    (lambda p: p.update(bytes=True), "invalid_radar_size"),
    (lambda p: p["meta"].update(state="STALE"), "invalid_radar_metadata"),
    (lambda p: p["meta"].update(producer="different"), "invalid_radar_metadata"),
    (lambda p: p["meta"].update(value_aggregation=True), "invalid_radar_metadata"),
    (lambda p: p["meta"].update(ingestion_latest_at="2026-11-01T12:00:00Z"), "stale_or_invalid_radar_clock"),
    (lambda p: p["meta"].update(source_as_of="2026-11-18T13:59:00Z"), "stale_or_invalid_radar_clock"),
    (lambda p: p["meta"].update(record_count=999), "radar_metadata_mismatch"),
])
def test_radar_pointer_tampering_and_staleness_refused(tmp_path, mutate, reason):
    pointer = radar_snapshot(tmp_path)
    rewrite_pointer(pointer, mutate)
    with pytest.raises(news.ExportError, match=reason):
        news.select_from_radar(pointer, now=NOW, published_ids=[], recheck_ids=[])


def test_radar_sqlite_byte_tampering_and_writable_files_refused(tmp_path):
    pointer = radar_snapshot(tmp_path)
    data = json.loads(pointer.read_text())
    database = tmp_path / data["file"]
    database.chmod(0o640)
    with pytest.raises(news.ExportError, match="invalid_radar_file_boundary"):
        news.select_from_radar(pointer, now=NOW, published_ids=[], recheck_ids=[])
    with database.open("r+b") as handle:
        handle.seek(-1, 2)
        handle.write(b"\xff")
    database.chmod(0o440)
    with pytest.raises(news.ExportError, match="radar_digest_mismatch"):
        news.select_from_radar(pointer, now=NOW, published_ids=[], recheck_ids=[])


def test_radar_reader_cannot_modify_sqlite_source(tmp_path):
    pointer = radar_snapshot(tmp_path)
    before_pointer = pointer.read_bytes()
    database = tmp_path / json.loads(before_pointer)["file"]
    before_db = database.read_bytes()
    news.select_from_radar(pointer, now=NOW, published_ids=[], recheck_ids=[])
    assert before_pointer == pointer.read_bytes()
    assert before_db == database.read_bytes()
    assert not list(tmp_path.glob("*.sqlite-wal"))
    assert not list(tmp_path.glob("*.sqlite-journal"))


def test_radar_pointer_symlink_is_refused(tmp_path):
    pointer = radar_snapshot(tmp_path)
    alias = tmp_path / "alias.json"
    alias.symlink_to(pointer)
    with pytest.raises(OSError):
        news.select_from_radar(alias, now=NOW, published_ids=[], recheck_ids=[])


def test_radar_export_closes_reader_before_http_and_emits_sha(monkeypatch, tmp_path):
    producer = tmp_path / "producer"
    producer.mkdir()
    pointer = radar_snapshot(producer)
    output = tmp_path / "facts.json"
    expected = snapshot([SECOND_ID], lambda identity: fetched(payload(numeroControlePNCP=identity), identity=identity))

    def build(ids, **kwargs):
        assert ids == [SECOND_ID]
        assert kwargs["metadata"]["producer_commit"] == "b" * 40
        assert kwargs["metadata"]["radar_contract"] == radar.SNAPSHOT_SCHEMA
        return expected

    # Source clock is fixture-controlled; source freshness is separately tested.
    real_select = news.select_from_radar
    monkeypatch.setattr(news, "select_from_radar", lambda path, **kwargs: real_select(
        path, now=NOW, published_ids=kwargs["published_ids"], recheck_ids=kwargs["recheck_ids"],
    ))
    monkeypatch.setattr(news, "build_snapshot", build)
    result = news.export_from_radar(pointer_path=pointer, output=output, producer_commit="b" * 40)
    assert result["ok"] is True
    assert result["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


@pytest.mark.parametrize("url", [
    "http://pncp.gov.br/app/contratos/11222333000181/2026/123",
    "https://pncp.gov.br.evil.test/app/contratos/11222333000181/2026/123",
    "https://pncp.gov.br/app/contratos/11222333000181/2026/123?next=http://localhost",
    "https://pncp.gov.br/app/contratos/11222333000181/2026/0123",
    "https://pncp.gov.br/app/contratos/11222333000181/2026/0",
])
def test_radar_only_reconstructs_exact_canonical_portal_identity(url):
    with pytest.raises(news.ExportError, match="invalid_radar_source_url"):
        news._identity_from_radar_url(url)
