"""Acceptance tests — EXTRA technical acervo knowledge base (OBJECTIVE 1–15)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.technical_acervo.format import format_item_hit
from scripts.technical_acervo.guards import assert_response_has_provenance, scan_store_for_pii
from scripts.technical_acervo.match import match_natural, match_requirement
from scripts.technical_acervo.search import (
    build_search_chunks,
    max_quantity_for_service,
    search_experiences,
    search_items,
)
from scripts.technical_acervo.store import DEFAULT_ACERVO_PATH, load_store
from scripts.technical_acervo.synonyms import synonym_map_from_store

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def store():
    assert DEFAULT_ACERVO_PATH.is_file(), f"missing canonical store: {DEFAULT_ACERVO_PATH}"
    return load_store()


# --- 1–4 counts and dedup ---------------------------------------------------


def test_seven_canonical_cats(store):
    assert store.count_cats() == 7
    certs = {d["certificate_number"] for d in store.cats()}
    assert len(certs) == 7
    assert "252025174528" in certs


def test_one_canonical_cao(store):
    assert store.count_caos() == 1
    cao = store.caos()[0]
    assert cao["certificate_number"] == "7-250004663-6"
    assert cao["document_type"] == "CAO"


def test_eight_technical_experiences(store):
    assert store.count_experiences() == 8
    sao_jose = store.get_experience("exp-sao-jose-tombada-2024")
    assert sao_jose is not None
    assert sao_jose["individual_cat_not_provided"] is True


def test_arquivo5_and_arquivo8_not_duplicated(store):
    dedup = store.assert_dedup_integrity()
    assert dedup["ok"] is True
    assert dedup["arquivo5_arquivo8_same_document"] is True
    assert dedup["certificate"] == "252025174528"
    f5 = store.find_document(source_file="arquivo5.pdf")
    f8 = store.find_document(source_file="arquivo8.pdf")
    assert len(f5) == 1 and len(f8) == 1
    assert f5[0]["id"] == f8[0]["id"]
    # only one CAT with that number
    assert len(store.find_document(certificate="252025174528")) == 1


# --- 5–7 key quantities -----------------------------------------------------


def _items_for_cat(store, cert: str) -> list[dict]:
    docs = store.find_document(certificate=cert)
    assert docs, f"CAT {cert} not found"
    doc = docs[0]
    exps = store.experiences_for_document(doc["id"])
    items = []
    for e in exps:
        if e.get("primary_document_id") == doc["id"] or doc["id"] in (e.get("linked_documents") or []):
            # prefer primary
            pass
        items.extend(e.get("technical_items") or [])
    # filter items whose source_document is this cat when possible
    primary = [i for i in items if i.get("source_document") == doc["id"]]
    return primary or items


def test_cat_252025173593_compactacao_aterro(store):
    items = _items_for_cat(store, "252025173593")
    by_svc = {i["service"]: i for i in items}
    assert by_svc["compactacao de aterro e/ou de base"]["quantity"] == 718.5
    assert by_svc["compactacao de aterro e/ou de base"]["unit"] == "m2"
    assert by_svc["aterro"]["quantity"] == 718.5
    assert by_svc["aterro"]["unit"] == "m2"


def test_cat_252025173008_metal_fire_blocks(store):
    items = _items_for_cat(store, "252025173008")
    metal = [i for i in items if "estrutura metalica" in i["service"]]
    assert metal and metal[0]["quantity"] == 534.12
    cob = [i for i in items if i["service"] == "cobertura metalica"]
    assert cob and cob[0]["quantity"] == 550.0
    blocos = [i for i in items if "blocos de concreto" in i["service"]]
    assert blocos and blocos[0]["quantity"] == 1016.0
    fire = [i for i in items if "preventivo de incendio" in i["service"] or "incendio" in i["service"]]
    assert len(fire) >= 3


def test_cat_252024163553_cobasi_quantities(store):
    items = _items_for_cat(store, "252024163553")
    metal = [i for i in items if "estrutura metalica" in i["service"]]
    assert metal and metal[0]["quantity"] == 1321.08
    calc_c = [i for i in items if i["service"] == "calcada de concreto"]
    calc_l = [i for i in items if i["service"] == "calcada de lajotas"]
    assert calc_c and calc_c[0]["quantity"] == 150.0
    assert calc_l and calc_l[0]["quantity"] == 150.0


# --- 8–9 tombada + São José -------------------------------------------------


def test_search_edificacao_tombada_returns_fama_and_sao_jose(store):
    from scripts.technical_acervo.normalize import normalize_text

    hits = search_experiences(store, "edificação tombada")
    titles = normalize_text(" ".join(h.get("title") or "" for h in hits))
    cities_n = {normalize_text(h.get("city")) for h in hits}
    assert any("fama" in normalize_text(h.get("title")) for h in hits)
    assert any("sao jose" in normalize_text(h.get("city")) for h in hits)
    assert any("florianopolis" in c for c in cities_n)
    assert any("sao jose" in c for c in cities_n)
    assert "tombad" in titles or any(
        "tombad" in normalize_text(" ".join(h.get("capability_tags") or []).replace("_", " "))
        for h in hits
    )


def test_sao_jose_operational_certificate_only(store):
    exp = store.get_experience("exp-sao-jose-tombada-2024")
    assert exp["evidence_level"] == "operational_certificate_only"
    assert exp["individual_cat_not_provided"] is True
    assert exp["primary_document_id"] == "doc-cao-7-250004663-6"
    # no individual CAT among linked docs
    linked = [store.get_document(d) for d in exp["linked_documents"]]
    assert all((d or {}).get("document_type") == "CAO" for d in linked)


# --- 10–12 CAO status / restrictions / review flag --------------------------


def test_cao_expired_since_2025_05_24(store):
    cao = store.caos()[0]
    assert cao["current_status"] == "expired"
    assert cao["valid_until"] == "2025-05-24"
    assert cao["issued_at"] == "2025-04-24"


def test_cao_not_for_public_bidding_attestation(store):
    cao = store.caos()[0]
    blob = " ".join(cao.get("restrictions") or []).lower()
    assert "concorrências públicas" in blob or "concorrencias publicas" in blob.replace("ê", "e").replace("ç", "c")
    assert "atestado" in blob
    assert "não tem a finalidade" in blob or "nao tem a finalidade" in blob.replace("ã", "a")


def test_cao_filename_date_conflict_review_flag(store):
    cao = store.caos()[0]
    flags = cao.get("review_flags") or []
    flag_ids = [f.get("flag") if isinstance(f, dict) else f for f in flags]
    assert "source_filename_date_conflicts_with_document_content" in flag_ids
    # original filename preserved
    assert any("02-06-2026" in f for f in (cao.get("source_files") or []))


# --- 13 PII -----------------------------------------------------------------


def test_no_cpf_or_birth_date_in_store_or_chunks(store):
    scan = scan_store_for_pii(store)
    assert scan["ok"], scan["issues"]
    raw_text = DEFAULT_ACERVO_PATH.read_text(encoding="utf-8").lower()
    # No actual birth-date or CPF fields/values in the store
    assert "data_nascimento" not in raw_text
    assert re.search(r'"cpf"\s*:', raw_text) is None
    assert re.search(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", raw_text) is None
    for prof in store.professionals:
        assert "cpf" not in prof
        assert "birth_date" not in prof
        assert "data_nascimento" not in prof
    for ch in build_search_chunks(store):
        text = (ch.get("text") or "").lower()
        assert "cpf" not in text
        assert not re.search(r"nascido\s+em\s+\d{2}", text)


# --- 14 no auto-sum ---------------------------------------------------------


def test_metal_structure_500_does_not_auto_sum(store):
    result = match_requirement(
        store,
        service="estrutura metalica",
        quantity=500,
        unit="m2",
        allow_sum=False,
    )
    assert result["allow_sum"] is False
    assert result["sum_total"] is None
    assert result["summed_records"] == []
    # Cobasi 1321.08 alone should satisfy individually
    assert result["max_individual_quantity"] is not None
    assert float(result["max_individual_quantity"]) >= 500
    assert result["adherence_level"] == "full_individual"
    assert any("Somatório automático" in lim or "allow_sum=false" in lim for lim in result["limitations"])

    # even if qty requires sum, without allow_sum must not sum
    high = match_requirement(
        store,
        service="estrutura metalica",
        quantity=2000,
        unit="m2",
        allow_sum=False,
    )
    assert high["sum_total"] is None
    assert high["adherence_level"] in ("partial_individual", "no_match", "evidence_limited")
    assert high["adherence_level"] != "only_with_sum"


def test_allow_sum_explicit_lists_records(store):
    result = match_requirement(
        store,
        service="estrutura metalica",
        quantity=2000,
        unit="m2",
        allow_sum=True,
    )
    if result["adherence_level"] == "only_with_sum":
        assert result["sum_total"] is not None
        assert len(result["summed_records"]) >= 2
        assert any("Registros somados" in lim for lim in result["limitations"])


# --- 15 provenance fields ---------------------------------------------------


def test_responses_include_provenance_fields(store):
    hits = search_items(store, "compactacao", limit=5)
    assert hits
    for h in hits:
        fmt = format_item_hit(h)
        missing = assert_response_has_provenance(fmt)
        assert not missing, f"missing {missing} in {fmt}"


def test_synonyms_drywall_and_spcip(store):
    syn = synonym_map_from_store(store)
    from scripts.technical_acervo.normalize import normalize_text

    assert "drywall" in syn or normalize_text("drywall") in syn
    drywall_hits = search_items(store, "drywall", limit=5)
    assert drywall_hits
    assert any("gesso" in (h.get("service") or "") for h in drywall_hits)

    fire = search_items(store, "prevenção contra incêndio", limit=10)
    assert fire
    assert any("incendio" in (h.get("service") or "") or "emergencia" in (h.get("service") or "") for h in fire)


def test_organizations_and_professional(store):
    assert any("EXTRA EMPREITEIRA" in (o.get("legal_name") or "") for o in store.organizations)
    org = store.organizations[0]
    assert org.get("crea_sc") == "209827-7"
    assert org.get("cnpj_document") == "24.515.663/0001-49"
    assert org.get("cnpj_profile_conflict", {}).get("review_required") is True
    prof = store.professionals[0]
    assert prof["full_name"] == "Guilherme Pereira de Andrade"
    assert prof["crea_sc"] == "134481-6"
    assert prof.get("rnp") == "2514282160"


# --- CLI real entry points --------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.technical_acervo", *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_inventory_and_show_cat():
    inv = _run_cli("inventory")
    assert inv.returncode == 0, inv.stderr
    assert "CATs: 7" in inv.stdout
    assert "CAO: 1" in inv.stdout
    assert "Experiências: 8" in inv.stdout

    show = _run_cli("show", "--cat", "252025173593")
    assert show.returncode == 0, show.stderr
    assert "718,50" in show.stdout or "718.5" in show.stdout
    assert "compactacao" in show.stdout.lower() or "compactação" in show.stdout.lower()
    assert "arquivo3.pdf" in show.stdout


def test_cli_ask_dedup_and_cao_and_match():
    dedup = _run_cli("ask", "O arquivo5 e o arquivo8 são documentos diferentes?")
    assert dedup.returncode == 0, dedup.stderr
    assert "252025174528" in dedup.stdout
    assert re.search(r"n[aã]o|mesma cat|mesmo", dedup.stdout, re.I)

    cao = _run_cli("ask", "A CAO está válida?")
    assert cao.returncode == 0, cao.stderr
    assert "expired" in cao.stdout or "vencid" in cao.stdout.lower()
    assert "2025-05-24" in cao.stdout or "24/05/2025" in cao.stdout

    match = _run_cli(
        "match",
        "--service",
        "estrutura metalica",
        "--qty",
        "500",
        "--unit",
        "m2",
        "--json",
    )
    assert match.returncode == 0, match.stderr
    data = json.loads(match.stdout)
    assert data["allow_sum"] is False
    assert data["sum_total"] is None
    assert data["adherence_level"] == "full_individual"
    assert float(data["max_individual_quantity"]) >= 500


def test_cli_search_prevencao_and_tombada():
    from scripts.technical_acervo.normalize import normalize_text

    fire = _run_cli("search", "prevenção contra incêndio", "--experiences-too")
    assert fire.returncode == 0, fire.stderr
    assert "252025173008" in fire.stdout or "incendio" in fire.stdout.lower() or "emergencia" in fire.stdout.lower()

    tomb = _run_cli("search", "edificação tombada", "--experiences-too")
    assert tomb.returncode == 0, tomb.stderr
    out = normalize_text(tomb.stdout)
    assert "fama" in out
    assert "sao jose" in out or "centro historico" in out


def test_natural_match_helper(store):
    parsed = match_natural(store, "A Extra possui acervo de estrutura metálica acima de 500 m²?")
    assert parsed["allow_sum"] is False
    assert parsed["max_individual_quantity"] is not None
    assert float(parsed["max_individual_quantity"]) >= 500


def test_max_quantity_individual_only(store):
    mx = max_quantity_for_service(store, "estrutura metalica", unit="m2")
    assert mx["allow_sum"] is False
    assert float(mx["max_individual_quantity"]) == 1321.08


def test_cobertura_metalica_max_is_550_not_estrutura(store):
    """Tag pollution must not report Cobasi 1321.08 as cobertura metálica."""
    mx = max_quantity_for_service(store, "cobertura metalica", unit="m2")
    assert mx["max_individual_quantity"] is not None
    assert float(mx["max_individual_quantity"]) == 550.0
    best = mx["best"]
    assert best is not None
    assert "cobertura metalica" in (best.get("service") or "")
    assert best.get("certificate_number") == "252025173008"
    assert best.get("service_relevant") is True
    # No candidate should be an unrelated service with inflated qty
    for c in mx["candidates"]:
        assert "cobertura" in (c.get("service") or "")
        assert "estrutura metalica" != (c.get("service") or "")

    match = match_requirement(
        store, service="cobertura metalica", quantity=500, unit="m2"
    )
    assert float(match["max_individual_quantity"]) == 550.0
    assert "cobertura" in (match["best_individual"]["service"] or "")
    assert match["adherence_level"] == "full_individual"


def test_prevencao_incendio_not_blocos_or_contrapiso(store):
    """Fire search must not rank blocos de concreto / contrapiso as best qty."""
    hits = search_items(store, "prevenção contra incêndio", service_only=True, limit=20)
    assert hits
    for h in hits:
        svc = h.get("service") or ""
        assert "incendio" in svc or "emergencia" in svc or "extintor" in svc
        assert "blocos de concreto" not in svc
        assert "contrapiso" not in svc
        assert "alvenaria" not in svc
        assert h.get("service_relevant") is True

    mx = max_quantity_for_service(store, "prevenção contra incêndio", unit="m2")
    assert float(mx["max_individual_quantity"]) == 534.12
    best_svc = (mx["best"] or {}).get("service") or ""
    assert "preventivo" in best_svc or "incendio" in best_svc
    assert "blocos" not in best_svc

    match = match_requirement(
        store, service="prevenção contra incêndio", quantity=500, unit="m2"
    )
    assert float(match["max_individual_quantity"]) == 534.12
    bsvc = (match["best_individual"] or {}).get("service") or ""
    assert "preventivo" in bsvc or "incendio" in bsvc
    assert match["adherence_level"] == "full_individual"
