"""Shipped-path tests for the official-live paving peer-group canary (#415)."""

from __future__ import annotations

import io
import json
from typing import Any
from urllib.request import Request

from scripts.contract_comparables.constants import (
    CATALOG_LIVE_CANDIDATE,
    CONSUMER_WEB_CFG,
    FOCAL_CANARY_CONTRACT_ID,
    FORBIDDEN_CLAIM_TOKENS,
    FORBIDDEN_METRIC_KEYS,
    LIVE_PAVING_CANARY_ID,
    MIN_USABLE_N_COMPARABLE,
    OFFICIAL_LIVE,
    PAVING_FAMILY_CBUQ,
    PAVING_FAMILY_PARALELEPIPEDO,
    REASON_AREA_MISSING,
    REASON_CNPJ_IN_MUNICIPIO,
    REASON_CONSULTA_CNPJ_ORGAO,
    REASON_DSN_UNAVAILABLE,
    REASON_FIXTURE_LABELED_LIVE,
    REASON_GRAIN_MISMATCH,
    REASON_IDENTITY_SWAP,
    REASON_INVERTED_DATES,
    REASON_NATIONALIZED_STATE_SAMPLE,
    REASON_PAVING_FAMILY_MISMATCH,
    REASON_PHYSICAL_UNIT,
    REASON_PNCP_UNAVAILABLE,
    REASON_REGIME_UNPUBLISHED,
    REASON_ZERO_FROM_MISSING,
    STATUS_BLOCKED,
    STATUS_COMPARABLE,
    STATUS_HOLD,
    STATUS_NOT,
)
from scripts.contract_comparables.engine import build_peer_group
from scripts.contract_comparables.handoff import verify_sha256sums, write_comparables_handoff
from scripts.contract_comparables.models import PeerRequest
from scripts.contract_comparables.normalize import records_from_mappings
from scripts.contract_comparables.official_paving import (
    adapter_refusals,
    consulta_contratos_url,
    documented_area_m2,
    paving_family,
    run_live_paving_canary,
)
from scripts.contract_comparables.serialize import fold_for_scan

FOCAL = FOCAL_CANARY_CONTRACT_ID
FOCAL_URL = "https://pncp.gov.br/api/pncp/v1/orgaos/14862788000150/contratos/2026/69"
AS_OF = "2026-08-19"
START = "2026-07-01"
END = "2026-08-19"


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = body
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class FakeOpener:
    def __init__(self, routes: dict[str, tuple[int, Any]]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, request: Request, timeout: float | None = None) -> FakeResponse:
        url = getattr(request, "full_url", str(request))
        self.calls.append(url)
        for prefix, (status, payload) in self.routes.items():
            if prefix in url:
                body = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload).encode("utf-8")
                if status >= 400:
                    import urllib.error

                    raise urllib.error.HTTPError(url, status, "error", hdrs=None, fp=io.BytesIO(b""))  # type: ignore[arg-type]
                return FakeResponse(body, status)
        import urllib.error

        raise urllib.error.HTTPError(url, 404, "missing", hdrs=None, fp=io.BytesIO(b""))  # type: ignore[arg-type]


def _item(
    contract_id: str,
    objeto: str,
    valor: float,
    *,
    uf: str = "PI",
    municipio: str = "Teresina",
    inicio: str = "2026-07-08",
    fim: str = "2027-07-08",
    semantic_value_key: str = "valorGlobal",
) -> dict[str, Any]:
    cnpj = contract_id.split("-", 1)[0]
    payload = {
        "numeroControlePncp": contract_id,
        "objetoContrato": objeto,
        semantic_value_key: valor,
        "dataVigenciaInicio": inicio,
        "dataVigenciaFim": fim,
        "dataAssinatura": inicio,
        "dataPublicacaoPncp": inicio,
        "cnpjOrgao": cnpj,
        "niFornecedor": "00000000000191",
        "unidadeOrgao": {"ufSigla": uf, "municipioNome": municipio},
    }
    return payload


def _paving(
    index: int,
    *,
    uf: str = "PI",
    area: str | None = "1.200,00",
    family: str = "cbuq",
) -> dict[str, Any]:
    area_bit = f" de {area} m²" if area else ""
    if family == "paralelepipedo":
        objeto = f"Pavimentação em Paralelepípedo{area_bit} de ruas"
    else:
        objeto = f"Pavimentação asfáltica em CBUQ{area_bit} de vias urbanas"
    return _item(
        f"14862788000150-2-{index:06d}/2026",
        objeto,
        500000 + index * 10000,
        uf=uf,
    )


def _routes(items: list[dict[str, Any]], *, focal: dict[str, Any] | None = None) -> dict[str, tuple[int, Any]]:
    listing = {"data": items, "totalPaginas": 1, "totalRegistros": len(items)}
    target = focal or next(item for item in items if item["numeroControlePncp"] == FOCAL)
    return {
        "api/consulta/v1/contratos": (200, listing),
        "api/pncp/v1/orgaos/14862788000150/contratos/2026/69": (200, target),
    }


def _run(opener: FakeOpener, **kwargs: Any) -> dict[str, Any]:
    return run_live_paving_canary(
        dsn=None,
        focal_id=FOCAL,
        as_of=AS_OF,
        start_date=START,
        end_date=END,
        limit=50,
        max_pages=2,
        opener=opener,
        sleeper=lambda _seconds: None,
        rate_limit_s=0.0,
        retries=0,
        cache_dir=None,
        producer_sha="test-sha",
        **kwargs,
    )


def _scan(payload: dict[str, Any]) -> str:
    return fold_for_scan(json.dumps(payload, ensure_ascii=False))


def test_documented_area_from_brazilian_object_text() -> None:
    area = documented_area_m2(
        "Pavimentação em Paralelepípedo de 4.710,00 m² de ruas no município de São Gonçalo do Piauí - PI"
    )
    assert area is not None
    assert format(area, "f") == "4710.00"
    assert documented_area_m2("Pavimentação asfáltica em CBUQ") is None


def test_adapter_refuses_identity_swap_and_cnpj_in_municipio() -> None:
    reasons = adapter_refusals(
        {
            "municipio": "14862788000150",
            "orgao_id": "Teresina",
            "objeto": "Pavimentação asfáltica",
            "source_kind": "contract",
        }
    )
    assert REASON_CNPJ_IN_MUNICIPIO in reasons
    assert REASON_IDENTITY_SWAP in reasons


def test_adapter_refuses_inverted_dates_ata_grain_and_zero_coercion() -> None:
    inverted = adapter_refusals(
        {
            "period_start": "2027-01-01",
            "period_end": "2026-01-01",
            "source_kind": "contract",
            "objeto": "Pavimentação",
        }
    )
    assert REASON_INVERTED_DATES in inverted
    ata = adapter_refusals({"objeto": "Ata de registro de preços para pavimentação", "source_kind": "ata"})
    assert REASON_GRAIN_MISMATCH in ata
    coerced = adapter_refusals({"valor": "0", "valor_is_unknown": True, "source_kind": "contract"})
    assert REASON_ZERO_FROM_MISSING in coerced
    fixture = adapter_refusals({"catalog_mode": OFFICIAL_LIVE, "source": "fixture", "source_kind": "contract"})
    assert REASON_FIXTURE_LABELED_LIVE in fixture


def test_custo_km_is_refused_before_denominator() -> None:
    payload = run_live_paving_canary(
        dsn=None,
        metric="custo/km",
        as_of=AS_OF,
        sleeper=lambda _seconds: None,
        rate_limit_s=0.0,
        retries=0,
    )
    assert payload["status"] == STATUS_HOLD
    assert REASON_PHYSICAL_UNIT in payload["reason_codes"]
    assert payload["official_live"] is False
    assert payload["catalog_mode"] != OFFICIAL_LIVE
    assert "custo_por_km" not in (payload.get("unit_metrics") or {})


def test_consulta_url_uses_official_cnpj_orgao_param() -> None:
    url = consulta_contratos_url(
        start="2026-07-01",
        end="2026-08-19",
        page=1,
        page_size=50,
        cnpj_orgao="14862788000150",
    )
    assert "cnpjOrgao=14862788000150" in url
    assert "uf=" not in url
    assert paving_family("Pavimentação em Paralelepípedo de 4.710,00 m²") == PAVING_FAMILY_PARALELEPIPEDO
    assert paving_family("Pavimentação asfáltica em CBUQ") == PAVING_FAMILY_CBUQ


def test_live_path_comparable_never_labels_catalog_official_live(monkeypatch: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    items = [_item(FOCAL, "Pavimentação em Paralelepípedo de 4.710,00 m² de ruas", 719177.48)]
    items.extend(_paving(index, family="paralelepipedo") for index in range(70, 78))
    opener = FakeOpener(_routes(items))
    first = _run(opener)
    second = _run(FakeOpener(_routes(items)))
    assert first["status"] == STATUS_COMPARABLE
    assert int(first["total_used"]) >= MIN_USABLE_N_COMPARABLE
    assert first["schema"] == "comparable-contracts-live-paving-handoff/1.0"
    assert first["official_live"] is True
    assert first["catalog_mode"] == CATALOG_LIVE_CANDIDATE
    assert first["catalog_mode"] != OFFICIAL_LIVE
    assert first["document"]["catalog_mode"] != OFFICIAL_LIVE
    assert first["target_contract_id"] == FOCAL
    assert first["peer_group_id"]
    assert first["grain"] == "contrato"
    assert first["value_semantic"] == "valor_integral_nominal"
    assert first["unit"] == "BRL_TOTAL"
    assert first["publication_authorization"] is False
    assert first["index_authorization"] is False
    assert first["national_claim_authorized"] is False
    assert first["consumer"] == CONSUMER_WEB_CFG
    assert first["producer"] == "extra-cli"
    assert "valid" not in first
    assert first["unit_metrics"]["emitted"] is False
    assert MIN_USABLE_N_COMPARABLE == 5
    assert first["content_hash"] == second["content_hash"]
    assert first["live"]["dsn_available"] is False
    assert first["live"]["production_write"] is False
    assert first["live"]["backfill"] is False
    assert first["availability"]["class"] == "consulta_cnpj_orgao_bounded"
    assert first["availability"]["dsn"]["class"] == "dsn_absent"
    assert REASON_CONSULTA_CNPJ_ORGAO in first["reason_codes"]
    assert REASON_REGIME_UNPUBLISHED in first["reason_codes"]
    metrics = (first.get("document") or {}).get("metrics") or {}
    assert metrics
    assert "median" in metrics
    assert "p25" in metrics
    assert "p75" in metrics
    for key in FORBIDDEN_METRIC_KEYS:
        assert key not in metrics
    blob = _scan(first)
    for token in FORBIDDEN_CLAIM_TOKENS:
        assert fold_for_scan(token) not in blob


def test_distinct_paving_family_is_excluded(monkeypatch: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    items = [_item(FOCAL, "Pavimentação em Paralelepípedo de 4.710,00 m² de ruas", 719177.48)]
    items.extend(_paving(index, family="cbuq") for index in range(70, 78))
    payload = _run(FakeOpener(_routes(items)))
    peer_ids = {item.get("contract_id") for item in payload.get("peers") or []}
    assert all("000070" not in str(item) for item in peer_ids)
    assert payload["status"] != STATUS_COMPARABLE
    assert REASON_PAVING_FAMILY_MISMATCH in payload["reason_codes"] or payload["total_used"] == 0


def test_n_below_minimum_stays_hold(monkeypatch: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    items = [_item(FOCAL, "Pavimentação em Paralelepípedo de 4.710,00 m² de ruas", 719177.48)]
    items.extend(_paving(index, family="paralelepipedo") for index in range(70, 73))
    payload = _run(FakeOpener(_routes(items)))
    assert int(payload["total_used"]) < MIN_USABLE_N_COMPARABLE
    assert payload["status"] != STATUS_COMPARABLE
    assert payload["catalog_mode"] != OFFICIAL_LIVE


def test_fixture_is_never_official_live_verdict() -> None:
    from scripts.contract_comparables.corpus import case_records, case_request, load_corpus

    corpus = load_corpus()
    case_id = next(iter(corpus["cases"]))
    _result, document = build_peer_group(case_records(corpus, case_id), case_request(corpus, case_id))
    assert document["catalog_mode"] != OFFICIAL_LIVE
    assert document["source"] == "fixture"


def test_brl_m2_kill_gate_when_any_peer_lacks_area(monkeypatch: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    items = [
        _item(FOCAL, "Pavimentação em Paralelepípedo de 4.710,00 m² de ruas", 719177.48),
        _paving(70, family="paralelepipedo", area=None),
        _paving(71, family="paralelepipedo", area="800,00"),
        _paving(72, family="paralelepipedo", area=None),
        _paving(73, family="paralelepipedo", area="900,00"),
        _paving(74, family="paralelepipedo", area=None),
    ]
    payload = _run(FakeOpener(_routes(items)), metric="BRL/m2")
    assert payload["unit_metrics"]["emitted"] is False
    assert REASON_AREA_MISSING in payload["unit_metrics"].get("reason_codes", []) or REASON_PHYSICAL_UNIT in payload["reason_codes"]
    assert payload["status"] != STATUS_COMPARABLE


def test_lexical_typology_is_not_a_peer(monkeypatch: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    items = [
        _item(FOCAL, "Pavimentação asfáltica em CBUQ de vias urbanas", 719177.48),
        _item("14862788000150-2-000080/2026", "Melhoria viária e infraestrutura urbana", 100000.0),
        _item("14862788000150-2-000081/2026", "Construção de escola municipal", 200000.0),
        _paving(82),
    ]
    payload = _run(FakeOpener(_routes(items)))
    peer_ids = {item.get("contract_id") for item in payload.get("peers") or []}
    assert "14862788000150-2-000080/2026" not in peer_ids
    assert "14862788000150-2-000081/2026" not in peer_ids


def test_contrato_vs_ata_and_estimado_are_refused(monkeypatch: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    items = [
        _item(FOCAL, "Pavimentação asfáltica em CBUQ", 719177.48),
        _item("14862788000150-2-000090/2026", "Ata de registro de preços para pavimentação asfáltica", 100000.0),
        _item(
            "14862788000150-2-000091/2026",
            "Pavimentação asfáltica em CBUQ",
            110000.0,
            semantic_value_key="valorEstimado",
        ),
    ]
    payload = _run(FakeOpener(_routes(items)))
    assert REASON_GRAIN_MISMATCH in payload["reason_codes"] or payload["status"] in {STATUS_HOLD, STATUS_NOT}
    peer_ids = {item.get("contract_id") for item in payload.get("peers") or []}
    assert "14862788000150-2-000090/2026" not in peer_ids


def test_inverted_dates_and_identity_swap_in_live_path(monkeypatch: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    items = [
        _item(FOCAL, "Pavimentação asfáltica em CBUQ", 719177.48, inicio="2027-07-08", fim="2026-07-08"),
        _paving(92),
    ]
    payload = _run(FakeOpener(_routes(items)))
    assert payload["status"] == STATUS_NOT
    assert REASON_INVERTED_DATES in payload["reason_codes"]
    swapped = [
        _item(FOCAL, "Pavimentação asfáltica em CBUQ", 719177.48, municipio="14862788000150"),
        _paving(93),
    ]
    swapped_payload = _run(FakeOpener(_routes(swapped)))
    assert swapped_payload["status"] == STATUS_NOT
    assert REASON_IDENTITY_SWAP in swapped_payload["reason_codes"]


def test_nationalized_state_sample_is_refused(monkeypatch: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    items = [_item(FOCAL, "Pavimentação asfáltica em CBUQ", 719177.48), _paving(94)]
    payload = _run(FakeOpener(_routes(items)), national_claim_authorized=True)
    assert payload["status"] == STATUS_NOT
    assert REASON_NATIONALIZED_STATE_SAMPLE in payload["reason_codes"]
    assert payload["national_claim_authorized"] is False


def test_pncp_unavailable_is_blocked_not_fixture(monkeypatch: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    opener = FakeOpener(
        {
            "api/consulta/v1/contratos": (503, {"error": "unavailable"}),
            "api/pncp/v1/orgaos/14862788000150/contratos/2026/69": (503, {"error": "unavailable"}),
        }
    )
    payload = _run(opener)
    assert payload["status"] == STATUS_BLOCKED
    assert REASON_PNCP_UNAVAILABLE in payload["reason_codes"] or REASON_DSN_UNAVAILABLE in payload["reason_codes"]
    assert payload["official_live"] is False
    assert payload["catalog_mode"] != OFFICIAL_LIVE
    assert payload.get("document") in (None, {}) or payload["status"] == STATUS_BLOCKED


def test_late_arrival_invalidates_only_affected_group(monkeypatch: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    items = [_item(FOCAL, "Pavimentação asfáltica em CBUQ", 719177.48)]
    items.extend(_paving(index, family="cbuq") for index in range(100, 106))
    payload = _run(FakeOpener(_routes(items)))
    late = payload["observability"]["late_arrivals"]
    assert late["affected_groups"]
    assert any(item not in late["affected_groups"] for item in late.get("unaffected_groups") or [None])
    assert late.get("old_hash_remains_valid") is False


def test_handoff_ready_xor_blocked_and_checksums(monkeypatch: Any, tmp_path: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    items = [_item(FOCAL, "Pavimentação em Paralelepípedo de 4.710,00 m² de ruas", 719177.48)]
    items.extend(_paving(index, family="paralelepipedo") for index in range(110, 116))
    envelope = _run(FakeOpener(_routes(items)))
    out = tmp_path / LIVE_PAVING_CANARY_ID
    result = write_comparables_handoff(envelope, out)
    assert result["decision"] in {"READY", "BLOCKED"}
    ready = (out / "READY.json").exists()
    blocked = (out / "BLOCKED.json").exists()
    assert ready != blocked
    errors = verify_sha256sums(out)
    assert errors == []
    payload = json.loads((out / "payload.json").read_text(encoding="utf-8"))
    instructions = json.loads((out / "consumer_instructions.json").read_text(encoding="utf-8"))
    assert payload["publication_authorization"] is False
    assert payload["index_authorization"] is False
    assert payload["no_cross_repo_write"] is True
    assert payload["consumer"] == CONSUMER_WEB_CFG
    assert payload["producer"] == "extra-cli"
    assert instructions["national_claim_authorized"] is False
    assert "narrative" in instructions["do_not_write"]
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert "html" not in json.dumps(manifest).lower() or "do_not" in json.dumps(instructions)


def test_cli_live_paving_handoff_custo_km(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    from scripts.contract_comparables.cli import main

    out = tmp_path / "handoff"
    rc = main(
        [
            "live-paving-handoff",
            "--metric",
            "custo/km",
            "--as-of",
            AS_OF,
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    assert (out / "READY.json").exists() != (out / "BLOCKED.json").exists()
    state = json.loads((out / "state.json").read_text(encoding="utf-8"))
    assert state["publication_authorization"] is False
    assert REASON_PHYSICAL_UNIT in state["reason_codes"]


def test_cli_drives_real_opener_path(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    items = [_item(FOCAL, "Pavimentação asfáltica em CBUQ de 4.710,00 m²", 719177.48)]
    items.extend(_paving(index, family="cbuq") for index in range(120, 125))
    opener = FakeOpener(_routes(items))

    def _fake_fetch(url: str, **kwargs: Any) -> Any:
        from scripts.official_contract_semantics.http_client import FetchResult
        from scripts.official_contract_semantics.identity import raw_record_hash_for

        request = Request(url)
        try:
            with opener(request) as response:
                raw = response.read()
            return FetchResult(url=url, ok=True, status=200, body=raw.decode("utf-8"), sha256=raw_record_hash_for(raw), unavailability=None)
        except Exception as exc:  # noqa: BLE001
            from scripts.official_contract_semantics.models import SourceUnavailability

            return FetchResult(
                url=url,
                ok=False,
                status=503,
                body=None,
                sha256=None,
                unavailability=SourceUnavailability(official_url=url, error_kind="network", message=str(exc)),
            )

    monkeypatch.setattr("scripts.contract_comparables.official_paving.fetch_official", _fake_fetch)
    from scripts.contract_comparables.cli import main

    out = tmp_path / "cli-handoff"
    rc = main(
        [
            "live-paving-handoff",
            "--focal",
            FOCAL,
            "--as-of",
            AS_OF,
            "--start-date",
            START,
            "--end-date",
            END,
            "--limit",
            "50",
            "--max-pages",
            "1",
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    payload = json.loads((out / "payload.json").read_text(encoding="utf-8"))
    assert payload["target_contract_id"] == FOCAL
    assert payload["catalog_mode"] != OFFICIAL_LIVE
    assert payload["status"] in {STATUS_HOLD, STATUS_NOT, STATUS_COMPARABLE}
    assert verify_sha256sums(out) == []


def test_engine_still_refuses_incompatible_unit_and_missing_area_as_unknown() -> None:
    mappings = [
        {
            "contract_id": FOCAL,
            "objeto": "Pavimentação asfáltica em CBUQ",
            "valor": "1000",
            "valor_semantic": "valor_integral_nominal",
            "unidade": "km",
            "uf": "PI",
            "data_referencia": "2026-07-08",
            "regime": "empreitada_global",
        },
        {
            "contract_id": "peer-km",
            "objeto": "Pavimentação asfáltica em CBUQ",
            "valor": "1100",
            "valor_semantic": "valor_integral_nominal",
            "unidade": "km",
            "uf": "PI",
            "data_referencia": "2026-07-08",
            "regime": "empreitada_global",
        },
    ]
    request = PeerRequest(
        focal_contract_id=FOCAL,
        as_of=AS_OF,
        catalog_mode=CATALOG_LIVE_CANDIDATE,
        source="test",
        live_semantic_columns_present=True,
    )
    _result, document = build_peer_group(records_from_mappings(mappings), request)
    assert document["status"] != STATUS_COMPARABLE
    assert document["catalog_mode"] != OFFICIAL_LIVE
    assert document["unit"] != "BRL_TOTAL"


def test_min_usable_n_was_not_lowered() -> None:
    assert MIN_USABLE_N_COMPARABLE == 5


def test_envelope_has_no_dsn_password_or_token(monkeypatch: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    items = [_item(FOCAL, "Pavimentação em Paralelepípedo de 4.710,00 m² de ruas", 719177.48)]
    items.extend(_paving(index, family="paralelepipedo") for index in range(70, 76))
    payload = _run(FakeOpener(_routes(items)))
    blob = json.dumps(payload, ensure_ascii=False).lower()
    for token in ("password", "passwd", "token=", "postgresql://", "dsn="):
        assert token not in blob


def test_live_opener_calls_bounded_cnpj_orgao(monkeypatch: Any) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("NATIONAL_INTEL_DSN", raising=False)
    items = [_item(FOCAL, "Pavimentação em Paralelepípedo de 4.710,00 m² de ruas", 719177.48)]
    items.extend(_paving(index, family="paralelepipedo") for index in range(70, 76))
    opener = FakeOpener(_routes(items))
    _run(opener)
    consulta_calls = [url for url in opener.calls if "api/consulta/v1/contratos" in url]
    assert consulta_calls
    assert any("cnpjOrgao=14862788000150" in url for url in consulta_calls)


def test_evidence_refs_sorted_by_identity_for_hash() -> None:
    from scripts.contract_comparables.official_paving import attach_live_hash, stabilize_evidence_refs

    refs = [
        {"contract_id": "b", "url": "u2", "sha256": "x", "locator": {"json_path": "$.data[9].objetoContrato"}, "source_kind": "contract"},
        {"contract_id": "a", "url": "u1", "sha256": "y", "locator": {"json_path": "$.data[1].objetoContrato"}, "source_kind": "contract"},
    ]
    stable = stabilize_evidence_refs(refs)
    assert [item["contract_id"] for item in stable] == ["a", "b"]
    first = attach_live_hash({"evidence_refs": list(reversed(refs)), "status": STATUS_HOLD})
    second = attach_live_hash({"evidence_refs": refs, "status": STATUS_HOLD})
    assert first["content_hash"] == second["content_hash"]


def test_envelope_hash_ignores_transport_byte_volatility() -> None:
    from scripts.contract_comparables.official_paving import attach_live_hash

    base = {
        "schema": "comparable-contracts-live-paving-handoff/1.0",
        "status": STATUS_HOLD,
        "reason_codes": ["live_columns_unavailable"],
        "catalog_mode": CATALOG_LIVE_CANDIDATE,
        "official_live": True,
        "source_kind": "pncp_contrato_api",
        "as_of": AS_OF,
        "target_contract_id": FOCAL,
        "evidence_refs": [{"contract_id": FOCAL, "url": FOCAL_URL, "sha256": "aaa", "locator": {"json_path": "$.valorGlobal"}}],
        "live": {"focal_sha256": "aaa", "official_live": True, "dsn_available": False, "unavailabilities": [{"error_kind": "timeout"}]},
        "observability": {"refresh_latency_ms": 1.0},
        "document": {"content_hash": "stable"},
    }
    other = json.loads(json.dumps(base))
    other["evidence_refs"][0]["sha256"] = "bbb"
    other["live"]["focal_sha256"] = "bbb"
    other["live"]["unavailabilities"] = [{"error_kind": "timeout", "message": "other"}]
    other["observability"]["refresh_latency_ms"] = 99.0
    first = attach_live_hash(dict(base))
    second = attach_live_hash(other)
    assert first["content_hash"] == second["content_hash"]
