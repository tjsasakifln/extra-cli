"""AC1–AC6 e AC11 — o bundle contra o contrato VENDORIZADO.

O contrato lido aqui e ``docs/contracts/confenge-live-intelligence-v1.json``
(copia verbatim de ``tjsasakifln/web-cfg`` @ ``dea6457a…``). **Nunca** rede,
**nunca** ``.campaign/``: o teste tem de ser escrivel e reproduzivel offline, e o
``sha256`` registrado em ``docs/contracts/confenge-live-intelligence-v1.md`` e a
guarda contra re-vendorizacao silenciosa.

A fronteira de ``freshness`` e testada sobre a FUNCAO PURA
(``public_policy.build_freshness``), porque ``cutoff_at`` e escrito no persist e
um seed real nunca produziria 48h exatas. As asserções de concordancia (bloco
identico em todo payload, ``min`` dos watermarks, recomputacao das strings)
rodam sobre o bundle REAL.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.confenge_live_intelligence import export as li_export
from scripts.confenge_live_intelligence import public_policy as policy
from scripts.confenge_live_intelligence import schema as li_schema
from scripts.confenge_live_intelligence import verifier as li_verifier
from scripts.confenge_live_intelligence.producer import build_snapshot

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "docs" / "contracts" / "confenge-live-intelligence-v1.json"
CONTRACT_PROVENANCE = REPO_ROOT / "docs" / "contracts" / "confenge-live-intelligence-v1.md"

UTC_NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
AS_OF = date(2026, 9, 2)
CREATED_BY = "LI-TEST-export-contract"


@pytest.fixture(scope="module")
def contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


# --- proveniencia -----------------------------------------------------------


def test_contract_is_vendored_and_offline() -> None:
    assert CONTRACT_PATH.is_file(), "contrato vendorizado ausente — o teste nao pode depender de rede"
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    provenance = CONTRACT_PROVENANCE.read_text(encoding="utf-8")
    assert digest in provenance, (
        f"sha256 do contrato vendorizado ({digest}) nao consta em {CONTRACT_PROVENANCE.name} — "
        "re-vendorizacao silenciosa"
    )


def test_forbidden_lists_are_a_proven_copy_of_the_contract(contract: dict) -> None:
    """Sem isto, ``public_policy`` seria uma SEGUNDA fonte de verdade."""
    assert list(policy.FORBIDDEN_FIELDS) == contract["forbidden_conclusion_fields"]
    assert list(policy.FORBIDDEN_STRINGS) == contract["forbidden_public_language"]
    assert policy.DISCLAIMER_PT == contract["adherence_semantics"]["disclaimer_pt"]
    assert policy.FRESHNESS_MAX_AGE_HOURS == contract["freshness"]["max_age_hours"]
    assert sorted(policy.DATA_STATE_BY_SNAPSHOT_STATE.values()) == sorted(contract["data_state"]["enum"])
    assert list(policy.FORBIDDEN_ENUM_VALUES) == contract["data_state"]["forbidden"]


# --- fronteira de freshness (funcao pura, emenda do AC3) --------------------


def _freshness(delta: timedelta) -> dict:
    generated = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    return policy.build_freshness(generated, generated - delta)


def test_freshness_boundary_exactly_48h_is_fresh() -> None:
    """Comparacao ESTRITA: o contrato diz *exceeds*, e ``>=`` seria outra regra."""
    assert _freshness(timedelta(hours=48))["state"] == policy.FRESHNESS_FRESH


def test_freshness_boundary_48h_plus_one_second_is_stale() -> None:
    assert _freshness(timedelta(hours=48, seconds=1))["state"] == policy.FRESHNESS_STALE


def test_freshness_is_derived_from_the_serialized_strings() -> None:
    """Microssegundos nao podem mudar o rotulo: derivamos das strings emitidas."""
    generated = datetime(2026, 9, 3, 12, 0, 0, 999_999, tzinfo=UTC)
    source = generated - timedelta(hours=48)
    block = policy.build_freshness(generated, source)
    recomputed = datetime.fromisoformat(block["generated_at"]) - datetime.fromisoformat(block["source_as_of"])
    assert (recomputed > timedelta(hours=48)) == (block["state"] == policy.FRESHNESS_STALE)
    assert block["state"] == policy.FRESHNESS_FRESH
    assert block["generated_at"].endswith("+00:00") and "." not in block["generated_at"]


def test_stale_emits_the_internal_code_never_the_consumer_one() -> None:
    block = _freshness(timedelta(hours=72))
    codes = policy.freshness_reason_codes(block)
    assert policy.REASON_SOURCE_AS_OF_BEYOND_MAX_AGE in codes
    assert "freshness_stale" not in codes
    assert policy.freshness_limitations(block), "STALE sem linha em limitations"


def test_negative_delta_stays_fresh_and_declares_the_anomaly() -> None:
    """Rotular STALE aqui divergiria da formula do consumidor — proibido."""
    generated = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    block = policy.build_freshness(generated, generated + timedelta(hours=5))
    assert block["state"] == policy.FRESHNESS_FRESH
    assert policy.REASON_SOURCE_AS_OF_AFTER_GENERATED_AT in policy.freshness_reason_codes(block)


@pytest.mark.parametrize(
    ("generated", "source"),
    [
        (None, UTC_NOW),
        (UTC_NOW, None),
        (datetime(2026, 9, 3, 12, 0), UTC_NOW),
        (UTC_NOW, datetime(2026, 9, 3, 12, 0)),
    ],
    ids=["generated_none", "source_none", "generated_naive", "source_naive"],
)
def test_freshness_invariant_is_fail_closed(generated, source) -> None:
    with pytest.raises(policy.FreshnessInvariantError):
        policy.build_freshness(generated, source)


def test_internal_reason_codes_are_disjoint_from_the_contract_vocabulary(contract: dict) -> None:
    """Os 14 codigos do topo sao veredito do CONSUMIDOR; nenhum e emissivel por nos."""
    contract_codes = set(contract["reason_codes"])
    assert len(contract_codes) == 14
    assert contract_codes.isdisjoint(set(policy.INTERNAL_EXPORT_REASON_CODES))
    engine_codes = {
        value
        for name, value in vars(li_schema).items()
        if name.startswith(("REASON_", "BLOCKER_")) and isinstance(value, str)
    }
    assert contract_codes.isdisjoint(engine_codes), sorted(contract_codes & engine_codes)


# --- bundle real ------------------------------------------------------------


def _opportunity(**overrides) -> li_schema.LiveOpportunity:
    base = dict(
        opportunity_id="LI-TEST-EXP-1",
        source="pncp",
        source_as_of=UTC_NOW,
        objeto="Reforma de escola municipal com estrutura metalica",
        objeto_state=li_schema.OBSERVED,
        valor_estimado_brl=Decimal("250000.00"),
        valor_state=li_schema.OBSERVED,
        valor_band="100K_1M",
        modalidade="Pregao",
        modalidade_id="6",
        modalidade_state=li_schema.OBSERVED,
        uf="SC",
        municipio="Florianopolis",
        geo_state=li_schema.OBSERVED,
        orgao_cnpj="12345678000195",
        orgao_nome="Prefeitura Sintetica",
        orgao_state=li_schema.OBSERVED,
        data_publicacao=date(2026, 8, 1),
        data_encerramento=date(2026, 10, 1),
        deadline_state=li_schema.DEADLINE_OPEN,
    )
    base.update(overrides)
    return li_schema.LiveOpportunity(**base)


def _company(**overrides) -> li_schema.LiveCompany:
    base = dict(
        company_root8="11222333",
        source_as_of=UTC_NOW + timedelta(hours=3),
        date_resolver_version="ca-v2-precedence/1.0",
        razao_social="Construtora Sintetica",
        portfolio_contract_ids=("LI-TEST-C1",),
        observed_objects=("Reforma de escola municipal com estrutura metalica",),
        observed_value_bands=("100K_1M",),
        observed_ufs=("SC",),
        # '123456' tem != 14 digitos: exercita `buyers_unhashable` (AC6).
        observed_buyer_cnpjs=("12345678000195", "123456"),
        observed_establishment_cnpjs=("11222333000181", "11222333000262"),
        most_recent_contracting_date=date(2026, 5, 1),
        contracting_date_state=li_schema.OBSERVED,
    )
    base.update(overrides)
    return li_schema.LiveCompany(**base)


pytestmark = pytest.mark.real_db


@pytest.fixture
def ready_bundle(live_conn, tmp_path) -> tuple[str, Path, dict]:
    result = build_snapshot(
        live_conn,
        as_of=AS_OF,
        created_by=CREATED_BY,
        opportunities=[_opportunity()],
        companies=[_company()],
    )
    assert result.state == li_schema.SNAPSHOT_READY, result.state
    out = tmp_path / "bundle"
    # REQ-001 — a proveniencia `official_live` e uma REIVINDICACAO explicita do
    # invocador; o default do export e `fixture`. Este fixture exercita
    # deliberadamente o caminho reivindicado, que e o do AC1.
    manifest = li_export.export_bundle(
        live_conn,
        snapshot_id=result.snapshot_id,
        out_dir=out,
        catalog_mode="official_live",
    )
    return result.snapshot_id, out, manifest


def _files(out: Path) -> dict[str, dict]:
    return li_export.load_bundle(out)["files"]


# --- AC1 --------------------------------------------------------------------


def test_ready_snapshot_emits_data_ready_envelope(ready_bundle) -> None:
    _snapshot_id, _out, manifest = ready_bundle
    assert manifest["schema"] == "CONFENGE_LIVE_INTELLIGENCE/1.0"
    assert manifest["contract_version"] == "1.0"  # AC11 — nunca "v1.0.0"
    assert manifest["catalog_mode"] == "official_live"
    assert manifest["official_live"] is True
    assert manifest["producer_status"] == "official_live"
    assert manifest["data_state"] == "DATA_READY"


def test_export_without_an_explicit_claim_is_labeled_fixture(live_conn, tmp_path) -> None:
    """AC1/REQ-001 — omitir a reivindicacao NUNCA produz um bundle rotulado live.

    O contrato autoriza `official_live` *"only when producers are live official
    artifacts and claimed_live is true"*. O default do export e `fixture`, e o
    consumidor recusa esse bundle por `producer_status_not_official_live` — que e
    exatamente o efeito desejado para um export feito de um banco de teste/seed.
    """
    result = build_snapshot(
        live_conn,
        as_of=AS_OF,
        created_by=CREATED_BY,
        opportunities=[_opportunity()],
        companies=[_company()],
    )
    manifest = li_export.export_bundle(live_conn, snapshot_id=result.snapshot_id, out_dir=tmp_path / "unclaimed")
    assert manifest["catalog_mode"] == "fixture"
    assert manifest["official_live"] is False
    assert manifest["producer_status"] == "fixture"
    # A proveniencia nao rebaixa `data_state`: sao eixos independentes.
    assert manifest["data_state"] == "DATA_READY"


def test_invalid_catalog_mode_fails_closed(live_conn, tmp_path) -> None:
    """REQ-001 — vocabulario fechado; nenhum terceiro rotulo de proveniencia."""
    result = build_snapshot(
        live_conn,
        as_of=AS_OF,
        created_by=CREATED_BY,
        opportunities=[_opportunity()],
        companies=[_company()],
    )
    out = tmp_path / "invalid"
    with pytest.raises(li_export.LiveIntelligenceExportError):
        li_export.export_bundle(live_conn, snapshot_id=result.snapshot_id, out_dir=out, catalog_mode="live")
    assert not out.exists()


def test_manifest_never_emits_the_contract_key(ready_bundle) -> None:
    """AC1 — a chave de envelope e ``schema``. Alias e um segundo lugar para divergir."""
    _snapshot_id, out, manifest = ready_bundle
    assert "contract" not in manifest
    assert "contract" not in json.loads((out / li_export.MANIFEST_FILE).read_text(encoding="utf-8"))


def test_schema_is_present_at_all_three_levels(ready_bundle, contract: dict) -> None:
    _snapshot_id, out, manifest = ready_bundle
    files = _files(out)
    accepted = {
        "live-opportunity/1.0": contract["producer_contracts"]["live_opportunity"]["accepted_schemas"],
        "company-fit-profile/1.0": contract["producer_contracts"]["company_fit_profile"]["accepted_schemas"],
    }
    for payload in files.values():
        assert payload["schema"] in accepted
        assert payload["schema"] in accepted[payload["schema"]]
    for entry in (*manifest["index"]["opportunities"], *manifest["index"]["companies"]):
        assert entry["schema"] == files[entry["file"]]["schema"]


def test_index_is_exactly_the_set_of_emitted_files(ready_bundle) -> None:
    _snapshot_id, out, manifest = ready_bundle
    indexed = {e["file"] for e in manifest["index"]["opportunities"]} | {
        e["file"] for e in manifest["index"]["companies"]
    }
    on_disk = {
        f"{p.parent.name}/{p.name}"
        for sub in (li_export.OPPORTUNITIES_DIR, li_export.COMPANIES_DIR)
        for p in (out / sub).glob("*.json")
    }
    assert indexed == on_disk


def test_partial_snapshot_holds_and_declares_limitations(live_conn, tmp_path) -> None:
    """AC1 — ``DATA_HOLD`` + ``limitations`` nao vazio; linha excluida nao vira arquivo."""
    excluded = _opportunity(
        opportunity_id="LI-TEST-EXP-EXCLUDED",
        uf=None,
        municipio=None,
        geo_state=li_schema.UNKNOWN,
        reason_codes=(li_schema.REASON_GEO_MISSING,),
    )
    result = build_snapshot(
        live_conn,
        as_of=AS_OF,
        created_by=CREATED_BY,
        opportunities=[_opportunity(), excluded],
        companies=[_company()],
    )
    assert result.state == li_schema.SNAPSHOT_PARTIAL
    out = tmp_path / "partial"
    manifest = li_export.export_bundle(live_conn, snapshot_id=result.snapshot_id, out_dir=out)
    assert manifest["data_state"] == "DATA_HOLD"
    assert manifest["limitations"]
    assert manifest["coverage"]["opportunities_excluded"] == 1
    assert not (out / li_export.OPPORTUNITIES_DIR / "LI-TEST-EXP-EXCLUDED.json").exists()
    assert li_schema.REASON_ROW_EXCLUDED_REQUIRED_UNKNOWN in manifest["reason_codes"]


def test_blocked_snapshot_emits_only_the_manifest(live_conn, tmp_path) -> None:
    """AC1 — ``DATA_REJECT`` sem diretorio ``opportunities/`` nem ``companies/``."""
    from scripts.confenge_live_intelligence.producer import _blocked_result

    result = _blocked_result(
        live_conn,
        as_of=AS_OF,
        created_by=CREATED_BY,
        blockers=[li_schema.BLOCKER_WATERMARK_MISSING],
        persist=True,
    )
    out = tmp_path / "blocked"
    manifest = li_export.export_bundle(live_conn, snapshot_id=result.snapshot_id, out_dir=out)
    assert manifest["data_state"] == "DATA_REJECT"
    assert (out / li_export.MANIFEST_FILE).is_file()
    assert not (out / li_export.OPPORTUNITIES_DIR).exists()
    assert not (out / li_export.COMPANIES_DIR).exists()
    assert li_schema.BLOCKER_WATERMARK_MISSING in manifest["reason_codes"]


def test_sealed_snapshot_with_empty_universe_still_emits_a_bundle(live_conn, tmp_path) -> None:
    """AC1 — universo VAZIO nao e corrupcao: e um snapshot selado valido.

    `manifest.index` com zero arquivo satisfaz "nem mais, nem menos" (AC1), e o
    ramo de aborto da emenda do AC3 cobre apenas `generated_at`/`source_as_of`
    ausentes ou sem fuso — corrupcao de snapshot, nao catalogo vazio. Sem
    payload nao ha `min(source_as_of)`: o bloco reflete o corte do proprio
    snapshot e a substituicao e DECLARADA em `limitations`.

    Este e o caminho que um revisor exercita primeiro: `cli export` contra um
    `extra_test` sem datalake produz exatamente este snapshot.
    """
    result = build_snapshot(
        live_conn,
        as_of=AS_OF,
        created_by=CREATED_BY,
        opportunities=[],
        companies=[],
    )
    assert result.state == li_schema.SNAPSHOT_READY
    out = tmp_path / "empty"
    manifest = li_export.export_bundle(live_conn, snapshot_id=result.snapshot_id, out_dir=out)

    assert manifest["data_state"] == "DATA_READY"
    assert manifest["index"]["opportunities"] == []
    assert manifest["index"]["companies"] == []
    assert manifest["coverage"]["opportunities_observed"] == 0
    assert manifest["coverage"]["companies_observed"] == 0
    assert policy.LIMITATION_NO_PAYLOAD_EMITTED in manifest["limitations"]
    assert manifest["freshness"]["source_as_of"] == manifest["freshness"]["generated_at"]
    assert manifest["freshness"]["state"] == policy.FRESHNESS_FRESH
    # O verifier prova o bundle vazio como qualquer outro.
    assert li_verifier.verify_bundle(out).files_verified == 0


@pytest.mark.parametrize("state", [li_schema.SNAPSHOT_BUILDING, li_schema.SNAPSHOT_SUPERSEDED])
def test_non_exportable_state_writes_nothing(live_conn, tmp_path, ready_bundle, state: str) -> None:
    """AC1 — fail-closed: nem o manifest e escrito."""
    snapshot_id, _out, _manifest = ready_bundle
    with live_conn.cursor() as cur:
        # `chk_live_intel_superseded_has_timestamp` exige `superseded_at` junto
        # com o estado — a transicao e forjada so para provar o fail-closed do
        # export, nao para exercitar a emissao de SUPERSEDED (fora de escopo).
        cur.execute(
            "UPDATE public.confenge_live_intelligence_snapshots "
            "SET state = %s, superseded_at = CASE WHEN %s = 'SUPERSEDED' THEN cutoff_at ELSE NULL END "
            "WHERE snapshot_id = %s",
            (state, state, snapshot_id),
        )
    live_conn.commit()
    out = tmp_path / f"nonexportable-{state}"
    with pytest.raises(li_export.LiveIntelligenceExportError):
        li_export.export_bundle(live_conn, snapshot_id=snapshot_id, out_dir=out)
    assert not (out / li_export.MANIFEST_FILE).exists()


# --- AC2 --------------------------------------------------------------------


def test_export_never_reads_an_outbound_view(ready_bundle, live_conn, tmp_path) -> None:
    """AC2 — o export e funcao do snapshot selado, nunca da view outbound."""
    snapshot_id, _out, _manifest = ready_bundle
    executed: list[str] = []
    real_cursor = live_conn.cursor

    class _SpyCursor:
        def __init__(self, inner):
            self._inner = inner

        def execute(self, sql, params=None):
            executed.append(str(sql))
            return self._inner.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    class _SpyConn:
        def cursor(self, *a, **kw):
            inner = real_cursor(*a, **kw)

            class _Ctx:
                def __enter__(self):
                    return _SpyCursor(inner.__enter__())

                def __exit__(self, *exc):
                    return inner.__exit__(*exc)

            return _Ctx()

        def __getattr__(self, name):
            return getattr(live_conn, name)

    li_export.build_bundle(_SpyConn(), snapshot_id)
    assert executed, "nenhuma consulta observada — o espiao esta cego"
    joined = " ".join(executed).lower()
    for outbound in ("v_contracts_canonical_v2", "v_open_opportunities_canonical", "pncp_supplier_contracts"):
        assert outbound not in joined, f"export leu objeto outbound: {outbound}"
    assert "confenge_live_intelligence_" in joined


def test_export_source_has_no_wall_clock_call() -> None:
    """AC3 — ``export.py`` nunca chama ``datetime.now()``."""
    source = (REPO_ROOT / "scripts" / "confenge_live_intelligence" / "export.py").read_text(encoding="utf-8")
    stripped = re.sub(r'""".*?"""', "", source, flags=re.DOTALL)
    stripped = re.sub(r"#[^\n]*", "", stripped)
    for forbidden in ("datetime.now(", "date.today(", "time.time("):
        assert forbidden not in stripped, f"export.py usa relogio de parede: {forbidden}"


# --- AC3 (concordancia sobre o bundle real) --------------------------------


def test_freshness_block_is_identical_in_manifest_and_every_payload(ready_bundle) -> None:
    _snapshot_id, out, manifest = ready_bundle
    for rel, payload in _files(out).items():
        assert payload["freshness"] == manifest["freshness"], rel


def test_manifest_source_as_of_is_the_min_over_emitted_payloads(ready_bundle, live_conn) -> None:
    snapshot_id, _out, manifest = ready_bundle
    with live_conn.cursor() as cur:
        cur.execute(
            "SELECT source_as_of FROM public.confenge_live_intelligence_opportunities WHERE snapshot_id = %s "
            "UNION ALL SELECT source_as_of FROM public.confenge_live_intelligence_companies WHERE snapshot_id = %s",
            (snapshot_id, snapshot_id),
        )
        watermarks = [r["source_as_of"] for r in cur.fetchall()]
    assert len(watermarks) >= 2, "prova vacua: um unico watermark nao distingue min de max"
    expected = min(w.astimezone(UTC) for w in watermarks).isoformat(timespec="seconds")
    assert manifest["freshness"]["source_as_of"] == expected
    assert manifest["source_as_of"] == expected


def test_state_recomputed_from_serialized_strings_matches(ready_bundle) -> None:
    _snapshot_id, _out, manifest = ready_bundle
    block = manifest["freshness"]
    age = datetime.fromisoformat(block["generated_at"]) - datetime.fromisoformat(block["source_as_of"])
    expected = policy.FRESHNESS_STALE if age > timedelta(hours=48) else policy.FRESHNESS_FRESH
    assert block["state"] == expected


def test_generated_at_comes_from_cutoff_at(ready_bundle, live_conn) -> None:
    snapshot_id, _out, manifest = ready_bundle
    with live_conn.cursor() as cur:
        cur.execute(
            "SELECT cutoff_at, as_of_date FROM public.confenge_live_intelligence_snapshots WHERE snapshot_id = %s",
            (snapshot_id,),
        )
        row = cur.fetchone()
    assert manifest["generated_at"] == row["cutoff_at"].astimezone(UTC).isoformat(timespec="seconds")
    assert manifest["as_of"] == row["as_of_date"].isoformat()


def test_data_state_is_not_downgraded_by_stale(ready_bundle) -> None:
    """AC3 — ``DATA_READY`` + ``STALE`` sao dois eixos verdadeiros, nao contradicao."""
    _snapshot_id, _out, manifest = ready_bundle
    if manifest["freshness"]["state"] == policy.FRESHNESS_STALE:
        assert manifest["data_state"] == "DATA_READY"


# --- AC4 --------------------------------------------------------------------


def test_content_hash_is_stable_across_two_exports_without_repersist(ready_bundle, live_conn, tmp_path) -> None:
    """AC4 — ``sem re-persist intercalado``; ``manifest_hash`` NAO e asserido aqui."""
    snapshot_id, out, _manifest = ready_bundle
    first = {rel: p["content_hash"] for rel, p in _files(out).items()}
    second_dir = tmp_path / "second"
    li_export.export_bundle(live_conn, snapshot_id=snapshot_id, out_dir=second_dir)
    second = {rel: p["content_hash"] for rel, p in _files(second_dir).items()}
    assert first == second


def test_content_hash_is_recomputable(ready_bundle) -> None:
    _snapshot_id, out, _manifest = ready_bundle
    for rel, payload in _files(out).items():
        recomputed = li_schema.live_hash({k: v for k, v in payload.items() if k != "content_hash"})
        assert recomputed == payload["content_hash"], rel


# --- AC5 / AC6 --------------------------------------------------------------


def test_key_set_is_payload_fields_union_schema(ready_bundle, contract: dict) -> None:
    """`schema` e envelope ADITIVO, ausente das duas ``payload_fields`` do contrato."""
    _snapshot_id, out, _manifest = ready_bundle
    opportunity_fields = contract["producer_contracts"]["live_opportunity"]["payload_fields"]
    company_fields = contract["producer_contracts"]["company_fit_profile"]["payload_fields"]
    assert len(opportunity_fields) == 15
    assert len(company_fields) == 17
    assert "schema" not in opportunity_fields and "schema" not in company_fields

    for rel, payload in _files(out).items():
        expected = set(opportunity_fields if rel.startswith("opportunities/") else company_fields) | {"schema"}
        assert set(payload) == expected, rel


def test_verifier_proves_the_serialized_bundle(ready_bundle) -> None:
    _snapshot_id, out, _manifest = ready_bundle
    report = li_verifier.verify_bundle(out)
    assert report.files_verified >= 3
    assert "no_raw_cnpj_in_companies" in report.checks


def test_no_raw_or_masked_cnpj_in_company_files(ready_bundle) -> None:
    """AC6 — regex sobre o JSON SERIALIZADO, nem empresa, nem filial, nem terceiro."""
    _snapshot_id, out, _manifest = ready_bundle
    for path in (out / li_export.COMPANIES_DIR).glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        li_verifier.assert_no_raw_cnpj(payload, label=path.name)
        assert "company_root8" not in payload
        assert "company_ref" not in payload
        for buyer in payload["compradores"]:
            assert set(buyer) == {"buyer_digest"}
            assert re.fullmatch(r"^[0-9a-f]{16}$", buyer["buyer_digest"])
            assert buyer["buyer_digest"] != ""


def test_buyers_are_sorted_and_unhashable_ones_are_counted(ready_bundle) -> None:
    """AC6 — comprador != 14 digitos e OMITIDO, contado e declarado."""
    _snapshot_id, out, manifest = ready_bundle
    assert manifest["coverage"]["buyers_unhashable"] == 1
    for path in (out / li_export.COMPANIES_DIR).glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        digests = [b["buyer_digest"] for b in payload["compradores"]]
        assert digests == sorted(digests)
        assert len(digests) == 1
        assert policy.REASON_BUYER_CNPJ_NOT_HASHABLE in payload["reason_codes"]


def test_orgao_cnpj_stays_raw_in_opportunities(ready_bundle) -> None:
    """AC6 — a assimetria e DO CONTRATO: ``live_opportunity`` nao tem bloco ``identity``."""
    _snapshot_id, out, _manifest = ready_bundle
    payloads = [json.loads(p.read_text(encoding="utf-8")) for p in (out / li_export.OPPORTUNITIES_DIR).glob("*.json")]
    assert payloads
    assert any(p["orgao"]["cnpj"] == "12345678000195" for p in payloads)


def test_orgao_cnpj_suppression_flag_exists_and_is_off_by_default() -> None:
    assert policy.SUPPRESS_ORGAO_CNPJ is False


def test_one_file_per_establishment_digest(ready_bundle) -> None:
    """AC7 — N filiais → N arquivos, mesmo perfil, ``company_digest`` distinto."""
    _snapshot_id, out, manifest = ready_bundle
    from scripts.confenge_live_intelligence.identity import cnpj_digest

    expected = {cnpj_digest(c) for c in ("11222333000181", "11222333000262")}
    emitted = {e["company_digest"] for e in manifest["index"]["companies"]}
    assert emitted == expected
    assert manifest["coverage"]["establishment_digests"] == 2
    payloads = [json.loads(p.read_text(encoding="utf-8")) for p in (out / li_export.COMPANIES_DIR).glob("*.json")]
    perfis = {json.dumps(p["perfil"], sort_keys=True) for p in payloads}
    assert len(perfis) == 1, "os arquivos do mesmo root devem projetar o MESMO perfil"


def test_forbidden_language_and_conclusion_fields_are_absent(ready_bundle) -> None:
    """AC5 — sobre o SERIALIZADO, inclusive dentro de ``limitations`` e ``fonte``."""
    _snapshot_id, out, _manifest = ready_bundle
    for path in [out / li_export.MANIFEST_FILE, *(out).rglob("*/*.json")]:
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        li_verifier.assert_no_forbidden_content(text, payload, label=path.name)
        for forbidden in policy.FORBIDDEN_STRINGS:
            assert forbidden.lower() not in text.lower()


def test_index_enum_value_is_never_emitted(ready_bundle) -> None:
    """AC5 — ``INDEX`` como VALOR; ``manifest.index`` (o campo) e outra coisa."""
    _snapshot_id, out, manifest = ready_bundle
    assert "index" in manifest  # o campo continua obrigatorio
    for path in [out / li_export.MANIFEST_FILE, *(out).rglob("*/*.json")]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for value in li_verifier._walk_strings(payload):
            assert value not in policy.FORBIDDEN_ENUM_VALUES


def test_disclaimer_is_present_in_every_company_payload(ready_bundle, contract: dict) -> None:
    _snapshot_id, out, _manifest = ready_bundle
    for path in (out / li_export.COMPANIES_DIR).glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert contract["adherence_semantics"]["disclaimer_pt"] in payload["limitations"]


def test_suspensa_is_never_emitted_and_absence_is_declared(ready_bundle, contract: dict) -> None:
    _snapshot_id, out, manifest = ready_bundle
    assert "SUSPENSA" in contract["prazo_status_enum"]
    assert any("SUSPENSA" in line for line in manifest["limitations"])
    for path in (out / li_export.OPPORTUNITIES_DIR).glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["prazo"]["status"] in ("ABERTA", "ENCERRADA", "UNKNOWN")


def test_epistemic_classes_never_emit_inference(ready_bundle, contract: dict) -> None:
    _snapshot_id, out, _manifest = ready_bundle
    allowed = set(contract["epistemic_classes"])
    for rel, payload in _files(out).items():
        values = set(payload["epistemic_classes"].values())
        assert values <= allowed, rel
        assert "INFERENCE" not in values, rel


def test_emitted_reason_codes_are_disjoint_from_the_contract_vocabulary(ready_bundle, contract: dict) -> None:
    """Sobre o conjunto REALMENTE emitido, nao contra uma lista literal paralela."""
    _snapshot_id, out, manifest = ready_bundle
    emitted = set(manifest["reason_codes"])
    for payload in _files(out).values():
        emitted |= set(payload["reason_codes"])
    assert emitted, "prova vacua: nenhum reason code emitido"
    assert emitted.isdisjoint(set(contract["reason_codes"])), sorted(emitted & set(contract["reason_codes"]))


# --- P1 (goal CONFENGE-LIVE-INBOUND-FINAL-CUTOVER) — identidade -------------


def test_identity_projection_proves_two_branches_same_company_ref() -> None:
    """2 CNPJs de filial da mesma raiz -> digests distintos, MESMO company_ref."""
    company = _company()
    projection = li_export._build_identity_projection(
        snapshot_id="LI-TEST-IDENTITY",
        companies=[company],
        manifest_hash="deadbeef",
    )
    assert projection["schema"] == "CONFENGE_IDENTITY_PROJECTION/1.0"
    entries = projection["entries"]
    assert len(entries) == 2, entries
    digests = {e["establishment_digest"] for e in entries}
    refs = {e["company_ref"] for e in entries}
    assert len(digests) == 2, "filiais devem produzir establishment_digest distintos"
    assert len(refs) == 1, "filiais da mesma raiz devem resolver ao MESMO company_ref"
    assert next(iter(refs)) == company.company_ref()
    # sealed_hash e determinístico e recomputável a partir do proprio payload.
    resealed = dict(projection)
    del resealed["sealed_hash"]
    assert li_export.live_hash(resealed) == projection["sealed_hash"]


def test_identity_projection_is_absent_from_every_public_bundle_file(ready_bundle) -> None:
    """AC8: company_ref/cref1: nunca aparece em manifest.json nem em files/*.json."""
    _snapshot_id, out, manifest = ready_bundle
    assert "identity_projection" not in manifest
    serialized_manifest = li_export.canonical_json(manifest)
    assert "cref1:" not in serialized_manifest
    for rel, payload in _files(out).items():
        serialized = li_export.canonical_json(payload)
        assert "cref1:" not in serialized, rel
        assert "identity_projection" not in payload, rel
