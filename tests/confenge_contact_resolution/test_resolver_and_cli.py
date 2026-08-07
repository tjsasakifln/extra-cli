"""Integration tests: resolver with synthetic fixtures + real CLI entry points."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.confenge_contact_resolution.adapters.base import AdapterContext
from scripts.confenge_contact_resolution.adapters.contact_pages import ContactPageAdapter
from scripts.confenge_contact_resolution.adapters.public_docs import PublicDocsAdapter
from scripts.confenge_contact_resolution.adapters.registry import RegistryAdapter
from scripts.confenge_contact_resolution.adapters.site import SiteAdapter
from scripts.confenge_contact_resolution.adapters.web_search import NoOpWebSearchProvider, WebSearchAdapter
from scripts.confenge_contact_resolution.cache import ResolutionCache
from scripts.confenge_contact_resolution.export import (
    CANDIDATES_FILENAME,
    MANIFEST_FILENAME,
    write_resolution_artifacts,
)
from scripts.confenge_contact_resolution.models import ServiceContext, VerificationStatus
from scripts.confenge_contact_resolution.resolver import ContactResolver, ResolverConfig

CNPJ_A = "11222333000181"
CNPJ_B = "44555666000172"
CNPJ_ABSENT = "99888777000166"


def _adapters_offline():
    return [
        RegistryAdapter(prefer_network=False),
        SiteAdapter(),
        PublicDocsAdapter(),
        ContactPageAdapter(),
        WebSearchAdapter(provider=NoOpWebSearchProvider(), enabled=False),
    ]


def _ctx_builder(base: dict[str, AdapterContext]):
    def build(cnpj14: str) -> AdapterContext:
        return base.get(
            cnpj14,
            AdapterContext(cnpj14=cnpj14, allow_network=False),
        )

    return build


@pytest.fixture
def synthetic_contexts() -> dict[str, AdapterContext]:
    """Synthetic multi-case fixtures — no network, no real PII of third parties."""
    return {
        CNPJ_A: AdapterContext(
            cnpj14=CNPJ_A,
            allow_network=False,
            registry_record={
                "email": "contato@acme-engenharia.example",
                "phone": "4832221000",
                "legal_name": "ACME Engenharia LTDA",
                "company_size": "EPP",
                "source_date": "2026-01-15",
                "official_match_status": "MATCHED",
            },
            site_pages=[
                {
                    "url": "https://acme-engenharia.example/contato",
                    "source_date": "2026-05-01",
                    "contacts": [
                        {
                            "name": "Carla Diretora",
                            "cargo": "Diretora Técnica",
                            "email": "carla.diretora@acme-engenharia.example",
                            "phone": "48999991234",
                        },
                        {
                            "name": "Guessed Person",
                            "cargo": "Diretor",
                            "email": "joao.silva@acme-engenharia.example",
                            "pattern_guessed_email": True,
                        },
                    ],
                }
            ],
            public_docs=[
                {
                    "document_id": "contrato-pncp-1",
                    "source_date": "2019-03-01",
                    "name": "Rep Antigo",
                    "cargo": "Representante",
                    "email": "antigo@acme-engenharia.example",
                    "phone": "4833330000",
                    "url": "https://pncp.example/doc/1",
                }
            ],
            contact_pages=[
                {
                    "url": "https://acme-engenharia.example/equipe",
                    "source_date": "2026-04-01",
                    "people": [
                        {
                            "name": "Pedro Licitações",
                            "cargo": "Coordenador de Licitações",
                            "email": "licitacoes@acme-engenharia.example",
                            "phone": "48988887777",
                        }
                    ],
                }
            ],
            human_outcomes=[],
        ),
        CNPJ_B: AdapterContext(
            cnpj14=CNPJ_B,
            allow_network=False,
            registry_record={
                "email": "financeiro@beta.example",
                "phone": "11999998888",
                "legal_name": "Beta Construtora SA",
                "company_size": "DEMAIS",
                "source_date": "2026-02-01",
                "official_match_status": "MATCHED",
            },
            human_outcomes=[
                {
                    "cnpj14": CNPJ_B,
                    "email": "financeiro@beta.example",
                    "dnc": True,
                    "dnc_reason": "DO_NOT_CONTACT",
                    "state": "DO_NOT_CONTACT",
                    "source_date": "2026-07-01",
                }
            ],
            contact_pages=[
                {
                    "url": "https://beta.example/contato",
                    "source_date": "2026-06-01",
                    "people": [
                        {
                            "name": "Outro Canal",
                            "cargo": "Comercial",
                            "email": "vendas@beta.example",
                            "phone": "11977776666",
                        }
                    ],
                }
            ],
        ),
        CNPJ_ABSENT: AdapterContext(
            cnpj14=CNPJ_ABSENT,
            allow_network=False,
            registry_record={"official_match_status": "MATCHED", "legal_name": "Vazia LTDA"},
        ),
    }


def test_resolver_generic_email_nominal_dnc_absence(synthetic_contexts, tmp_path: Path) -> None:
    cache = ResolutionCache(tmp_path / "cache", ttl_seconds=3600)
    cfg = ResolverConfig(
        service_context=ServiceContext.LICITACOES.value,
        adapters=_adapters_offline(),
        cache=cache,
        allow_network=False,
        context_builder=_ctx_builder(synthetic_contexts),
        max_workers=2,
    )
    resolver = ContactResolver(cfg)

    r_a = resolver.resolve_one(CNPJ_A)
    assert r_a.candidates
    assert r_a.schema_id == "confenge-contact-candidates-v1"
    emails = {c.email for c in r_a.candidates if c.email}
    assert "contato@acme-engenharia.example" in emails  # functional/generic from registry
    # nominal decision-maker
    assert any(c.name == "Carla Diretora" for c in r_a.candidates)
    # pattern guessed
    guessed = [c for c in r_a.candidates if c.verification_status == VerificationStatus.CANDIDATE_UNVERIFIED.value]
    assert guessed
    assert all(not c.recommended for c in guessed)
    assert all(not c.enrollable for c in guessed)
    # recommended exists for licitacoes → prefer licitacoes role
    assert r_a.recommended_candidate_id
    rec = next(c for c in r_a.candidates if c.recommended)
    assert rec.role_class == "licitações"
    # landline from registry phone
    assert any(c.phone_type == "landline" for c in r_a.candidates if c.phone_e164)
    # mobile
    assert any(c.phone_type == "mobile" for c in r_a.candidates if c.phone_e164)
    # whatsapp default not OPTED_IN
    for c in r_a.candidates:
        if c.phone_e164:
            assert c.whatsapp.consent_status in {"UNKNOWN", "NO_OPT_IN"}

    # stale has lower freshness
    stale = next(c for c in r_a.candidates if c.email == "antigo@acme-engenharia.example")
    freshish = next(c for c in r_a.candidates if c.email == "licitacoes@acme-engenharia.example")
    assert stale.freshness < freshish.freshness

    r_b = resolver.resolve_one(CNPJ_B)
    dnc = [c for c in r_b.candidates if c.dnc]
    assert dnc
    assert all(not c.recommended for c in dnc)
    assert r_b.recommended_candidate_id
    assert not next(c for c in r_b.candidates if c.recommended).dnc

    r_abs = resolver.resolve_one(CNPJ_ABSENT)
    assert r_abs.candidates == []
    assert r_abs.absence_reason == "no_public_business_contact_found"
    assert r_abs.recommended_candidate_id is None


def test_invalid_phone_not_e164(synthetic_contexts) -> None:
    ctx = AdapterContext(
        cnpj14=CNPJ_A,
        allow_network=False,
        contact_pages=[
            {
                "url": "https://x.example",
                "people": [{"name": "X", "email": "x@y.example", "phone": "not-a-phone"}],
            }
        ],
    )
    cfg = ResolverConfig(
        adapters=_adapters_offline(),
        allow_network=False,
        context_builder=lambda _c: ctx,
    )
    r = ContactResolver(cfg).resolve_one(CNPJ_A)
    bad = next(c for c in r.candidates if c.email == "x@y.example")
    assert bad.phone_raw == "not-a-phone"
    assert bad.phone_e164 is None


def test_idempotent_cache_and_export(synthetic_contexts, tmp_path: Path) -> None:
    cache = ResolutionCache(tmp_path / "cache", ttl_seconds=3600)
    cfg = ResolverConfig(
        service_context=ServiceContext.GENERIC.value,
        adapters=_adapters_offline(),
        cache=cache,
        allow_network=False,
        context_builder=_ctx_builder(synthetic_contexts),
    )
    resolver = ContactResolver(cfg)
    r1 = resolver.resolve_one(CNPJ_A)
    r2 = resolver.resolve_one(CNPJ_A)
    assert r2.cache_hit is True
    assert len(r1.candidates) == len(r2.candidates)
    names1 = sorted((c.name or "", c.email or "") for c in r1.candidates)
    names2 = sorted((c.name or "", c.email or "") for c in r2.candidates)
    assert names1 == names2

    out = tmp_path / "out1"
    s1 = write_resolution_artifacts([r1], out, mode="single", service_context="generic", run_id="run-a")
    s2 = write_resolution_artifacts([r2], out, mode="single", service_context="generic", run_id="run-a")
    assert (out / CANDIDATES_FILENAME).is_file()
    assert (out / MANIFEST_FILENAME).is_file()
    # second write does not invent people
    lines = (out / CANDIDATES_FILENAME).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["schema_id"] == "confenge-contact-candidates-v1"
    assert rec["schema_version"]
    assert "candidates" in rec
    assert s1["checksum_sha256"]  # may differ if resolved_at changes; presence is enough
    assert s2["ok"] is True


def test_batch_resolve(synthetic_contexts, tmp_path: Path) -> None:
    cfg = ResolverConfig(
        adapters=_adapters_offline(),
        allow_network=False,
        context_builder=_ctx_builder(synthetic_contexts),
        max_workers=2,
    )
    results = ContactResolver(cfg).resolve_batch([CNPJ_A, CNPJ_B, CNPJ_ABSENT])
    assert len(results) == 3
    assert results[2].absence_reason


def test_cli_single_and_batch_idempotent(synthetic_contexts, tmp_path: Path) -> None:
    """Drive real CLI module; fixtures via fixtures-dir files."""
    fix = tmp_path / "fixtures"
    fix.mkdir()
    # Write fixture files consumed by adapters
    (fix / f"{CNPJ_A}_site.json").write_text(
        json.dumps(
            {
                "url": "https://acme.example/contato",
                "source_date": "2026-05-01",
                "contacts": [
                    {
                        "name": "Carla",
                        "cargo": "Diretora",
                        "email": "carla@acme.example",
                        "phone": "48999990000",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (fix / f"{CNPJ_A}_contact_page.json").write_text(
        json.dumps(
            {
                "url": "https://acme.example/equipe",
                "source_date": "2026-04-01",
                "people": [
                    {
                        "email": "contato@acme.example",
                        "phone": "4832221000",
                        "cargo": "Atendimento",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    out1 = tmp_path / "cli-single-1"
    out2 = tmp_path / "cli-single-2"
    cmd_base = [
        sys.executable,
        "-m",
        "scripts.confenge_contact_resolution",
        "resolve",
        "--cnpj",
        CNPJ_A,
        "--fixtures-dir",
        str(fix),
        "--no-cache",
    ]
    r1 = subprocess.run(
        [*cmd_base, "-o", str(out1)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    r2 = subprocess.run(
        [*cmd_base, "-o", str(out2)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    assert r1.returncode == 0, r1.stderr + r1.stdout
    assert r2.returncode == 0, r2.stderr + r2.stdout
    for out in (out1, out2):
        jp = out / CANDIDATES_FILENAME
        assert jp.is_file()
        row = json.loads(jp.read_text(encoding="utf-8").strip().splitlines()[0])
        assert row["schema_id"] == "confenge-contact-candidates-v1"
        assert row["cnpj14"] == CNPJ_A
        assert (out / MANIFEST_FILENAME).is_file()

    # batch
    inp = tmp_path / "cnpjs.txt"
    inp.write_text(f"{CNPJ_A}\n{CNPJ_ABSENT}\n", encoding="utf-8")
    outb1 = tmp_path / "cli-batch-1"
    outb2 = tmp_path / "cli-batch-2"
    for outb in (outb1, outb2):
        rb = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.confenge_contact_resolution",
                "batch",
                "-i",
                str(inp),
                "-o",
                str(outb),
                "--fixtures-dir",
                str(fix),
                "--no-cache",
                "--max-workers",
                "2",
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        assert rb.returncode == 0, rb.stderr + rb.stdout
        lines = (outb / CANDIDATES_FILENAME).read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        # absence not fabricated
        rows = [json.loads(x) for x in lines]
        absent = next(r for r in rows if r["cnpj14"] == CNPJ_ABSENT)
        assert absent["candidates"] == []
        assert absent.get("absence_reason")


def test_web_search_disabled_by_default() -> None:
    adapter = WebSearchAdapter(enabled=False)
    assert adapter.collect(AdapterContext(cnpj14=CNPJ_A)) == []


def test_small_firm_boosts_owner() -> None:
    from scripts.confenge_contact_resolution.merge import observations_to_candidates
    from scripts.confenge_contact_resolution.models import RawObservation, SourceProvenance
    from scripts.confenge_contact_resolution.ranking import select_recommended

    obs = [
        RawObservation(
            adapter="site",
            cnpj14=CNPJ_A,
            name="Dono",
            cargo="Proprietário",
            email="dono@me.example",
            phone_raw="48999991111",
            source=SourceProvenance(source_type="site", source_date="2026-06-01"),
        ),
        RawObservation(
            adapter="site",
            cnpj14=CNPJ_A,
            name="Func",
            cargo="Assistente",
            email="contato@me.example",
            phone_raw="48999992222",
            source=SourceProvenance(source_type="site", source_date="2026-06-01"),
        ),
    ]
    cands = observations_to_candidates(obs, cnpj14=CNPJ_A)
    ranked, _ = select_recommended(cands, service_context="generic", small_firm=True)
    assert next(c for c in ranked if c.recommended).role_class == "owner"


def test_resolver_account_dnc_blocks_all(tmp_path: Path) -> None:
    """End-to-end: account-level human DO_NOT_CONTACT blocks any recommendation."""
    ctx = AdapterContext(
        cnpj14=CNPJ_A,
        allow_network=False,
        site_pages=[
            {
                "url": "https://x.example",
                "source_date": "2026-06-01",
                "contacts": [
                    {"name": "Vendas", "cargo": "Comercial", "email": "vendas@x.example", "phone": "48999991111"},
                ],
            }
        ],
        human_outcomes=[
            {
                "cnpj14": CNPJ_A,
                "dnc": True,
                "dnc_reason": "DO_NOT_CONTACT",
                "state": "DO_NOT_CONTACT",
                "source_date": "2026-07-01",
            }
        ],
    )
    cfg = ResolverConfig(
        adapters=_adapters_offline(),
        allow_network=False,
        context_builder=lambda _c: ctx,
        cache=ResolutionCache(tmp_path / "c", ttl_seconds=60),
    )
    r = ContactResolver(cfg).resolve_one(CNPJ_A)
    assert r.candidates
    assert r.recommended_candidate_id is None
    assert all(not c.recommended for c in r.candidates)
    assert any("account_block" in lim for lim in r.limitations)
