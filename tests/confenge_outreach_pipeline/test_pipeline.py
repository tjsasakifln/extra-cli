"""Pipeline orchestrator: fixture path chains all stages without manual JSON."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.confenge_outreach_pipeline import pipeline as pipeline_module
from scripts.confenge_outreach_pipeline.adapt import (
    contact_resolution_to_bridge_row,
    intelligence_dossier_to_bridge_row,
    universe_row_to_intelligence_input,
)
from scripts.confenge_outreach_pipeline.cli import main as cli_main
from scripts.confenge_outreach_pipeline.pipeline import (
    PipelineConfig,
    _dedupe_decision_rows,
    _published_target_fit_snapshot,
    _reconcile_target_confirmed_decision_rows,
    _select_intelligence_rows,
    build_pipeline_contact_resolver,
    contact_job_meta,
    merge_contact_rows,
    run_pipeline,
)
from scripts.confenge_outreach_pipeline.sample import classify_profile, select_diverse_sample
from scripts.warmbly_bridge.mapping import build_leads

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_CSV = ROOT / "tests" / "fixtures" / "confenge_universe" / "contracts_sample.csv"
DNC_TXT = ROOT / "tests" / "fixtures" / "confenge_universe" / "dnc.txt"


def test_target_confirmed_reconciliation_emits_one_canonical_account_per_root() -> None:
    decision_rows = [
        {
            "cnpj14": "11222333000181",
            "razao_social": "Contexto menos rico",
            "portfolio": {"contract_count_total": 1},
            "priority_score": 20,
        },
        {
            "cnpj14": "11222333000262",
            "razao_social": "Contexto preservado",
            "portfolio": {"contract_count_total": 9},
            "priority_score": 80,
        },
        {"cnpj14": "33444555000129", "razao_social": "Não target"},
    ]
    target_identities = [
        {
            "cnpj14": "11222333000343",
            "cnpj_root": "11222333",
            "target_fit_class": "TARGET_CONFIRMED",
        },
        {
            "cnpj14": "22333444000155",
            "cnpj_root": "22333444",
            "razao_social": "Target fora do universo",
            "target_fit_class": "TARGET_CONFIRMED",
        },
    ]

    reconciled, metrics = _reconcile_target_confirmed_decision_rows(decision_rows, target_identities)

    target_rows = [row for row in reconciled if row.get("target_fit_class") == "TARGET_CONFIRMED"]
    assert {row["cnpj14"] for row in target_rows} == {"11222333000343", "22333444000155"}
    preserved = next(row for row in target_rows if row["cnpj_root"] == "11222333")
    assert preserved["razao_social"] == "Contexto preservado"
    assert preserved["portfolio"]["contract_count_total"] == 9
    assert any(row["cnpj14"] == "33444555000129" for row in reconciled)
    assert metrics == {
        "authoritative_target_roots": 2,
        "base_target_establishments": 2,
        "base_target_roots": 1,
        "target_roots_added": 1,
        "branch_duplicates_collapsed": 1,
        "canonical_establishments_replaced": 1,
        "target_roots_emitted": 2,
        "target_rows_missing_legal_name": 0,
        "output_decision_rows": 3,
    }


def test_account_intelligence_covers_target_confirmed_outside_hot_set() -> None:
    hot = {"cnpj14": "11222333000181", "razao_social": "Canary"}
    target_outside_hot = {"cnpj14": "22333444000155", "razao_social": "Target"}
    non_target = {"cnpj14": "33444555000129", "razao_social": "Other"}

    selected, metrics = _select_intelligence_rows(
        decision_rows=[hot, target_outside_hot, non_target],
        downstream_rows=[hot],
        target_fit_snapshot_rows=[
            {"cnpj14": hot["cnpj14"], "target_fit_class": "TARGET_CONFIRMED"},
            {"cnpj14": target_outside_hot["cnpj14"], "target_fit_class": "TARGET_CONFIRMED"},
            {"cnpj14": non_target["cnpj14"], "target_fit_class": "TARGET_OUT_OF_SCOPE"},
        ],
        include_all_target_confirmed=True,
    )

    assert [row["cnpj14"] for row in selected] == [hot["cnpj14"], target_outside_hot["cnpj14"]]
    assert metrics == {
        "scope": "target_confirmed_plus_activation_hot_set",
        "target_confirmed_total": 2,
        "target_confirmed_processed": 2,
        "target_confirmed_missing": 0,
        "activation_or_sample_count": 1,
        "selected_count": 2,
    }


def test_smoke_sample_does_not_expand_account_intelligence_scope() -> None:
    sample = {"cnpj14": "11222333000181"}
    target_outside_sample = {"cnpj14": "22333444000155"}

    selected, metrics = _select_intelligence_rows(
        decision_rows=[sample, target_outside_sample],
        downstream_rows=[sample],
        target_fit_snapshot_rows=[
            {"cnpj14": sample["cnpj14"], "target_fit_class": "TARGET_CONFIRMED"},
            {"cnpj14": target_outside_sample["cnpj14"], "target_fit_class": "TARGET_CONFIRMED"},
        ],
        include_all_target_confirmed=False,
    )

    assert selected == [sample]
    assert metrics["scope"] == "downstream_sample_only"
    assert metrics["target_confirmed_processed"] == 1
    assert metrics["target_confirmed_missing"] == 1


def test_limit_downstream_does_not_shrink_universe(tmp_path: Path) -> None:
    """Universe discovery runs fully; force-sample uses limit_downstream as batch only."""
    out = tmp_path / "run"
    result = run_pipeline(
        PipelineConfig(
            out_dir=out,
            csv_path=str(FIXTURE_CSV),
            dnc_path=str(DNC_TXT) if DNC_TXT.is_file() else None,
            as_of=__import__("datetime").date(2026, 8, 1),
            limit_downstream=1,
            max_workers=1,
            skip_contacts=True,
            progress=False,
            force_sample_mode=True,  # smoke path: limit_downstream bounds sample only
        )
    )
    assert result.ok, result.errors
    universe_total = result.stages["universe_row_count"]
    assert universe_total >= 1
    # Sample is capped by limit_downstream in force_sample_mode
    assert result.stages["sample"]["count"] == 1
    assert result.stages["sample"]["count"] <= universe_total
    # limit_downstream must NOT change universe_total
    assert result.stages["manifest_summary"]["universe_total"] == universe_total
    assert result.stages["manifest_summary"]["limit_downstream_is_batch_only"] is True
    # Intelligence only for sample
    assert result.stages["account_intelligence"]["count"] == 1
    # Feed is the complete decision universe; only expensive stages use the sample.
    feed = result.stages["feed"]
    assert feed.get("ok") is True
    assert feed.get("lead_count") == result.stages["target_fit_decision_universe_count"]
    assert feed.get("lead_count") > result.stages["sample"]["count"]
    feed_manifest = json.loads((out / "06_warmbly_feed" / "manifest.json").read_text(encoding="utf-8"))
    authority = feed_manifest["authoritative_target_fit"]
    assert authority["coverage_complete"] is True
    assert authority["omission_preserves_authorization"] is False
    assert authority["ordering"]["watermarks_monotonic"] is True
    # Manifest records sampling flags honestly
    assert result.stages.get("sampling") is False  # no max_rows on universe
    assert result.stages.get("full_scale_universe") is False  # csv path
    # Checkpoint written for resume
    assert (out / "pipeline-checkpoint.json").is_file()


def test_durable_projection_reaches_feed_accounts_outside_hot_set(tmp_path: Path) -> None:
    durable_path = tmp_path / "durable-contacts.jsonl"
    candidate_cnpjs = (
        "11222333000181",
        "44555666000181",
        "33445566000186",
        "77888999000181",
        "99887766000105",
        "12345678000195",
    )
    durable_rows = []
    for cnpj in candidate_cnpjs:
        host = f"empresa{cnpj[:8]}.com.br"
        durable_rows.append(
            {
                "cnpj14": cnpj,
                "enrichment_state": "EMAIL_ROUTE_READY",
                "contacts": [
                    {
                        "email": f"contato@{host}",
                        "source": "company_website",
                        "source_url": f"https://{host}/contato",
                        "observed_at": "2026-08-24T12:00:00Z",
                        "ownership_status": "COMPANY_OWNED",
                        "mailbox_company_evidence": "OBSERVED",
                        "channel_epistemic_class": "OBSERVED",
                        "route_freshness": "FRESH",
                        "route_suppression": "NONE",
                    }
                ],
            }
        )
    durable_path.write_text(
        "".join(json.dumps(row) + "\n" for row in durable_rows),
        encoding="utf-8",
    )
    out = tmp_path / "run-durable"
    result = run_pipeline(
        PipelineConfig(
            out_dir=out,
            csv_path=str(FIXTURE_CSV),
            as_of=__import__("datetime").date(2026, 8, 1),
            limit_downstream=1,
            max_workers=1,
            skip_contacts=True,
            durable_contacts_path=durable_path,
            progress=False,
            force_sample_mode=True,
        )
    )
    assert result.ok, result.errors
    sample_rows = [
        json.loads(line)
        for line in (out / "02_downstream_sample" / "downstream-sample.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    sample_cnpjs = {row["cnpj14"] for row in sample_rows}
    feed_leads = []
    for chunk in sorted((out / "06_warmbly_feed").glob("chunk_*.json")):
        feed_leads.extend(json.loads(chunk.read_text(encoding="utf-8"))["leads"])
    outside = [lead for lead in feed_leads if lead["company"]["cnpj14"] not in sample_cnpjs and lead.get("contacts")]
    assert outside, "durable contact projection must not be restricted to this run's hot set"
    contact = outside[0]["contacts"][0]
    assert contact["controlled_email_eligible"] is True
    assert contact["preferred_initial"] is True
    assert contact["route_class"] == "GENERIC_COMPANY"


def test_offline_snapshot_uses_embedded_decisions() -> None:
    rows = [{"cnpj14": "11222333000181", "target_fit_class": "TARGET_CONFIRMED"}]
    snapshot, authority, watermark = _published_target_fit_snapshot(rows, dsn=None)
    assert snapshot == rows
    assert authority == "universe_embedded_snapshot"
    assert watermark is None


def test_durable_contacts_extend_beyond_current_hot_set_and_rerank() -> None:
    durable = [
        {
            "cnpj14": "11222333000181",
            "enrichment_state": "EMAIL_ROUTE_READY",
            "contacts": [
                {
                    "email": "contato@acme.example.com",
                    "route_class": "GENERIC_COMPANY",
                    "source": "company_website",
                    "source_url": "https://acme.example.com/contato",
                    "observed_at": "2026-08-24T12:00:00Z",
                    "ownership_status": "COMPANY_OWNED",
                    "mailbox_company_evidence": "OBSERVED",
                    "channel_epistemic_class": "OBSERVED",
                    "route_freshness": "FRESH",
                    "route_suppression": "NONE",
                }
            ],
        },
        {
            "cnpj14": "44555666000181",
            "enrichment_state": "EMAIL_ROUTE_READY",
            "contacts": [
                {
                    "email": "licitacoes@mega.example.com",
                    "route_class": "ROLE_OR_DEPARTMENT",
                    "source": "company_website",
                    "source_url": "https://mega.example.com/licitacoes",
                    "observed_at": "2026-08-24T12:00:00Z",
                    "ownership_status": "COMPANY_OWNED",
                    "mailbox_company_evidence": "OBSERVED",
                    "mailbox_department_evidence": "OBSERVED",
                    "channel_epistemic_class": "OBSERVED",
                    "route_freshness": "FRESH",
                    "route_suppression": "NONE",
                }
            ],
        },
    ]
    current = [
        {
            "cnpj14": "11222333000181",
            "contacts": [
                {
                    "email": "comercial@acme.example.com",
                    "source": "company_website",
                    "source_url": "https://acme.example.com/comercial",
                    "ownership_status": "COMPANY_OWNED",
                    "mailbox_company_evidence": "OBSERVED",
                }
            ],
        }
    ]

    merged, metrics = merge_contact_rows(durable, current)

    assert metrics == {
        "durable_accounts": 2,
        "current_accounts": 1,
        "merged_accounts": 2,
        "accounts_in_both": 1,
        "accounts_with_contacts": 2,
    }
    by_cnpj = {row["cnpj14"]: row for row in merged}
    assert len(by_cnpj["11222333000181"]["contacts"]) == 2
    assert by_cnpj["44555666000181"]["contacts"][0]["email"] == "licitacoes@mega.example.com"


def test_durable_projection_rejects_mixed_input_versions() -> None:
    rows = [
        {
            "cnpj14": "11222333000181",
            "contact_discovery_policy_version": "dui.policy.v1",
            "contact_discovery_input_evidence_version": "target-fit.first",
            "contacts": [],
        },
        {
            "cnpj14": "44555666000181",
            "contact_discovery_policy_version": "dui.policy.v1",
            "contact_discovery_input_evidence_version": "target-fit.second",
            "contacts": [],
        },
    ]
    with __import__("pytest").raises(ValueError, match="mixes discovery policy/input versions"):
        merge_contact_rows(rows, [])


def test_authoritative_decision_universe_dedupes_canonical_cnpj() -> None:
    rows = [
        {"cnpj14": "11.222.333/0001-81", "entity_key": "brand:first"},
        {"cnpj14": "11222333000181", "entity_key": "brand:duplicate"},
        {"cnpj14": "22.333.444/0001-72", "entity_key": "brand:other"},
        {"cnpj14": "invalid", "entity_key": "unaddressable"},
    ]

    decisions, duplicates = _dedupe_decision_rows(rows)

    assert duplicates == 1
    assert [row["cnpj14"] for row in decisions] == ["11222333000181", "22333444000172"]
    assert decisions[0]["entity_key"] == "brand:first"


def test_production_snapshot_uses_published_store_and_canonicalizes_prevencao(
    monkeypatch,
) -> None:
    import scripts.confenge_outreach_pipeline.pipeline as pipeline
    import scripts.confenge_target_fit.db as target_fit_db

    class FakeConnection:
        closed = False

        def close(self) -> None:
            self.closed = True

    conn = FakeConnection()
    monkeypatch.setattr(target_fit_db, "connect", lambda dsn, readonly: conn)
    monkeypatch.setattr(
        pipeline,
        "load_published_index",
        lambda connection, cnpj14s: {
            "01489370": {
                "cnpj_raiz": "01489370",
                "company_key": "cnpj_root:01489370",
                "target_fit_class": "TARGET_OUT_OF_SCOPE",
                "source_watermark": "2026-08-12T07:00:00Z",
            }
        },
    )
    monkeypatch.setattr(
        pipeline,
        "get_control",
        lambda connection, key: {"watermark": "2026-08-12T08:00:00Z"},
    )

    snapshot, authority, watermark = _published_target_fit_snapshot(
        [{"cnpj14": "01489370000105"}],
        dsn="postgresql://unused",
    )

    assert conn.closed is True
    assert authority == "published_target_fit_store"
    assert watermark == "2026-08-12T08:00:00Z"
    assert snapshot == [
        {
            "cnpj14": "14893700000105",
            "cnpj_raiz": "14893700",
            "company_key": "cnpj_root:14893700",
            "target_fit_class": "TARGET_OUT_OF_SCOPE",
            "source_watermark": "2026-08-12T07:00:00Z",
        }
    ]


def test_published_decision_without_a_watermark_is_tombstoned_not_exported(monkeypatch) -> None:
    """One incomplete decision must cost one account, never the whole export."""
    import scripts.confenge_outreach_pipeline.pipeline as pipeline
    import scripts.confenge_target_fit.db as target_fit_db

    class FakeConnection:
        def close(self) -> None:
            return None

    monkeypatch.setattr(target_fit_db, "connect", lambda dsn, readonly: FakeConnection())
    monkeypatch.setattr(
        pipeline,
        "load_published_index",
        lambda connection, cnpj14s: {
            "14893700": {
                "cnpj_raiz": "14893700",
                "company_key": "cnpj_root:14893700",
                "target_fit_class": "TARGET_CONFIRMED",
                "source_watermark": "",
            },
            "11222333": {
                "cnpj_raiz": "11222333",
                "company_key": "cnpj_root:11222333",
                "target_fit_class": "TARGET_CONFIRMED",
                "source_watermark": "2026-08-12T07:00:00Z",
            },
        },
    )
    monkeypatch.setattr(pipeline, "get_control", lambda connection, key: {"watermark": "2026-08-12T08:00:00Z"})

    snapshot, _, _ = _published_target_fit_snapshot(
        [{"cnpj14": "14893700000105"}, {"cnpj14": "11222333000181"}],
        dsn="postgresql://unused",
    )

    assert [row["cnpj_raiz"] for row in snapshot] == ["11222333"]


def test_fresh_closed_source_reobserves_full_target_fit_without_erasing_evidence_watermark(
    monkeypatch,
) -> None:
    import scripts.confenge_outreach_pipeline.pipeline as pipeline
    import scripts.confenge_target_fit.db as target_fit_db

    class FakeConnection:
        closed = False

        def close(self) -> None:
            self.closed = True

    conn = FakeConnection()
    monkeypatch.setattr(target_fit_db, "connect", lambda dsn, readonly: conn)
    monkeypatch.setattr(
        pipeline,
        "load_published_index",
        lambda connection, cnpj14s: {
            "11222333": {
                "cnpj_raiz": "11222333",
                "company_key": "cnpj_root:11222333",
                "target_fit_class": "TARGET_CONFIRMED",
                "source_watermark": "2026-08-16T08:30:23Z",
            }
        },
    )

    def control(connection, key):
        if key == "cdc_watermark":
            return {"watermark": "2026-08-24T03:26:43Z"}
        assert key == "target_fit_coverage"
        return {
            "coverage_ratio": 1.0,
            "pagination_exhausted_normally": True,
            "last_full_reconcile_unexplained_missing": 0,
            "last_full_reconcile_completed_at": "2026-08-25T02:45:00Z",
        }

    monkeypatch.setattr(pipeline, "get_control", control)
    monkeypatch.setattr(pipeline, "queue_counts", lambda connection: {"done": 407_513})

    snapshot, authority, watermark = _published_target_fit_snapshot(
        [{"cnpj14": "11222333000181"}],
        dsn="postgresql://unused",
        authoritative_source_freshness={
            "status": "FRESH",
            "source_observed_at": "2026-08-25T02:42:00Z",
            "run_id": "contracts-live-1",
        },
    )

    assert conn.closed is True
    assert authority == "published_target_fit_store"
    assert watermark == "2026-08-25T02:42:00Z"
    assert snapshot[0]["source_watermark"] == "2026-08-25T02:42:00Z"
    assert snapshot[0]["target_fit_evidence_watermark"] == "2026-08-16T08:30:23Z"
    assert snapshot[0]["target_fit_observation_run_id"] == "contracts-live-1"


def test_target_fit_reobservation_fails_closed_until_full_reconcile_and_queue_drain(
    monkeypatch,
) -> None:
    import scripts.confenge_outreach_pipeline.pipeline as pipeline
    import scripts.confenge_target_fit.db as target_fit_db

    class FakeConnection:
        def close(self) -> None:
            return None

    monkeypatch.setattr(target_fit_db, "connect", lambda dsn, readonly: FakeConnection())
    monkeypatch.setattr(pipeline, "load_published_index", lambda connection, cnpj14s: {})
    monkeypatch.setattr(
        pipeline,
        "get_control",
        lambda connection, key: (
            {"watermark": "2026-08-24T03:26:43Z"}
            if key == "cdc_watermark"
            else {
                "coverage_ratio": 1.0,
                "pagination_exhausted_normally": True,
                "last_full_reconcile_unexplained_missing": 0,
                "last_full_reconcile_completed_at": "2026-08-25T02:40:00Z",
            }
        ),
    )
    monkeypatch.setattr(pipeline, "queue_counts", lambda connection: {"pending": 1})

    with __import__("pytest").raises(ValueError, match="full reconcile must complete after"):
        _published_target_fit_snapshot(
            [{"cnpj14": "11222333000181"}],
            dsn="postgresql://unused",
            authoritative_source_freshness={
                "status": "FRESH",
                "source_observed_at": "2026-08-25T02:42:00Z",
                "run_id": "contracts-live-1",
            },
        )

    monkeypatch.setattr(
        pipeline,
        "get_control",
        lambda connection, key: (
            {"watermark": "2026-08-24T03:26:43Z"}
            if key == "cdc_watermark"
            else {
                "coverage_ratio": 1.0,
                "pagination_exhausted_normally": True,
                "last_full_reconcile_unexplained_missing": 0,
                "last_full_reconcile_completed_at": "2026-08-25T02:45:00Z",
            }
        ),
    )
    with __import__("pytest").raises(ValueError, match="1 unresolved queue items"):
        _published_target_fit_snapshot(
            [{"cnpj14": "11222333000181"}],
            dsn="postgresql://unused",
            authoritative_source_freshness={
                "status": "FRESH",
                "source_observed_at": "2026-08-25T02:42:00Z",
                "run_id": "contracts-live-1",
            },
        )


def test_production_activation_does_not_use_limit_downstream_as_capacity(tmp_path: Path) -> None:
    """run_pipeline production path must use policy planned_capacity, not limit_downstream."""
    from scripts.confenge_activation.policy import load_policy

    out = tmp_path / "run_prod_cap"
    planned = load_policy().capacity.planned_capacity()
    assert planned > 5  # policy default is well above smoke sample size
    # Default limit_downstream is 200; production must NOT adopt that as commercial capacity.
    default_limit_downstream = 200
    result = run_pipeline(
        PipelineConfig(
            out_dir=out,
            csv_path=str(FIXTURE_CSV),
            dnc_path=str(DNC_TXT) if DNC_TXT.is_file() else None,
            as_of=__import__("datetime").date(2026, 8, 1),
            limit_downstream=5,  # must NOT become commercial hot-set capacity
            max_workers=1,
            skip_contacts=True,
            progress=False,
            use_activation_planner=True,
            force_sample_mode=False,
            activation_capacity=None,  # force policy path
        )
    )
    assert result.ok, result.errors
    act = result.stages.get("activation") or {}
    assert act.get("capacity_source") == "policy.planned_capacity"
    assert act.get("capacity_this_round") == planned
    assert act.get("capacity_this_round") != 5 or planned == 5
    assert act.get("capacity_this_round") != default_limit_downstream or planned == default_limit_downstream
    assert result.stages["sample"]["mode"] == "activation_hot_set"
    assert result.stages["universe_row_count"] >= result.stages["sample"]["count"]
    intelligence = result.stages["account_intelligence"]
    assert intelligence["scope"] == "target_confirmed_plus_activation_hot_set"
    assert intelligence["target_confirmed_processed"] == intelligence["target_confirmed_total"]
    assert intelligence["target_confirmed_missing"] == 0


def test_cli_run_fixture_end_to_end(tmp_path: Path, monkeypatch) -> None:
    # Full CI exposes a real datalake DSN. CSV fixture mode must remain offline
    # unless the operator explicitly combines it with --dsn.
    monkeypatch.setenv(
        "LOCAL_DATALAKE_DSN",
        "postgresql://ambient:ambient@127.0.0.1:1/must_not_be_used",
    )
    out = tmp_path / "cli_out"
    code = cli_main(
        [
            "run",
            "--csv",
            str(FIXTURE_CSV),
            "--out",
            str(out),
            "--as-of",
            "2026-08-01",
            "--limit-downstream",
            "5",
            "--max-workers",
            "2",
            "--skip-contacts",
        ]
    )
    assert code == 0
    manifest = out / "reports" / "pipeline-manifest.json"
    assert manifest.is_file()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["limit_downstream"] == 5
    assert data["account_intelligence"]["count"] >= 1
    assert "service_distribution" in data["account_intelligence"]
    # At least one feed chunk exists
    feed_dir = out / "06_warmbly_feed"
    chunks = list(feed_dir.glob("chunk_*.json"))
    assert chunks, "expected confenge.outreach.v1 chunk files"
    feed = json.loads(chunks[0].read_text(encoding="utf-8"))
    assert feed["schema_version"] == "confenge.outreach.v1"
    assert feed["leads"]
    lead = feed["leads"][0]
    assert lead["company"]["cnpj14"]
    assert "offer" in lead
    assert "messaging_context" in lead
    # Service chosen by intelligence, not blank for companies with contracts
    # (may be discovery for thin portfolios — still must be a string)
    assert isinstance(lead["offer"].get("service_code"), str)


def test_diverse_sample_not_pure_top_score() -> None:
    rows = []
    # High score mid-market
    for i in range(10):
        rows.append(
            {
                "cnpj14": f"11222333{i:04d}81"[:14].ljust(14, "0"),
                "priority_score": 90 - i,
                "outreach_eligibility": "ELIGIBLE",
                "portfolio": {
                    "contract_count_total": 5,
                    "value_total_brl": 1_000_000,
                    "ufs_atuacao": ["SC", "PR"],
                },
            }
        )
    # Low score regional lean — must still appear when limit allows diversity
    rows.append(
        {
            "cnpj14": "99888777000166",
            "priority_score": 5,
            "outreach_eligibility": "ELIGIBLE",
            "portfolio": {
                "contract_count_total": 2,
                "value_total_brl": 100_000,
                "ufs_atuacao": ["SC"],
            },
        }
    )
    # Few contracts
    rows.append(
        {
            "cnpj14": "55444333000122",
            "priority_score": 3,
            "outreach_eligibility": "ELIGIBLE",
            "portfolio": {
                "contract_count_total": 1,
                "value_total_brl": 50_000,
                "ufs_atuacao": ["RS"],
            },
        }
    )
    sample = select_diverse_sample(rows, limit=5)
    profiles = {r.get("_sample_profile") or classify_profile(r) for r in sample}
    assert "regional_lean" in profiles or "few_contracts" in profiles
    assert len(sample) == 5


def test_adapt_intelligence_and_contacts_join() -> None:
    universe = {
        "cnpj14": "11222333000181",
        "cnpj_root": "11222333",
        "razao_social": "ACME",
        "municipio": "Florianopolis",
        "uf": "SC",
        "outreach_eligibility": "ELIGIBLE",
        "priority_score": 70,
        "portfolio": {
            "contract_count_total": 2,
            "value_total_brl": 500_000,
            "ufs_atuacao": ["SC"],
            "recent_contracts": [
                {
                    "contrato_id": "C-1",
                    "objeto": "Pavimentacao",
                    "valor_total": 250_000,
                    "data_publicacao": "2024-03-01",
                    "data_fim": "2025-12-31",
                    "uf": "SC",
                    "orgao_nome": "Pref Joinville",
                    "supplier_cnpj14": "11222333000181",
                    "supplier_role": "CONTRATADA",
                    "buyer_cnpj14": "83169623000110",
                    "buyer_role": "ORGAO_CONTRATANTE",
                }
            ],
        },
    }
    intel_in = universe_row_to_intelligence_input(universe, as_of="2026-08-01")
    assert intel_in["contracts"]
    assert intel_in["cnpj14"] == "11222333000181"
    assert intel_in["contractor_role"]["status"] == "CONTRACTOR_ROLE_CONFIRMED"

    dossier = {
        "schema_id": "confenge-account-intelligence-v1",
        "account_snapshot": {
            "cnpj14": "11222333000181",
            "cnpj_root": "11222333",
            "razao_social": "ACME",
        },
        "primary_service": {
            "service_id": "gestao_monitoramento_contratual",
            "label": "Gestao contratual",
            "approach_mode": "diagnostico_focal",
        },
        "why_now": {
            "trigger": "portfolio_review",
            "temporal_fact": "Portfólio observável",
            "epistemic_class": "strong_inference",
        },
        "fact_to_mention": "Contrato de pavimentacao no PNCP",
        "question_to_ask": "Pergunta?",
        "cta": "CTA",
        "claims_to_avoid": ["garantia de economia"],
        "confirmed_facts": [
            {
                "id": "cf-1",
                "text": "Contrato C-1 publicado",
                "epistemic_class": "confirmed",
            }
        ],
        "strong_inferences": [],
        "weak_inferences": [],
        "service_fit_rationale": "Portfólio multi-contrato",
        "dominant_state": {"state": "NEW"},
        "generated_at": "2026-08-01T00:00:00Z",
        "as_of": "2026-08-01",
        "_pipeline_contracts": intel_in["contracts"],
    }
    bridge_intel = intelligence_dossier_to_bridge_row(dossier)
    assert bridge_intel["contractor_role"]["status"] == "CONTRACTOR_ROLE_CONFIRMED"
    # confenge.service.v1: warmbly service_code is canonical playbook code
    assert bridge_intel["offer"]["service_code"] == "MONITORAMENTO_CONTRATUAL"
    assert bridge_intel["offer"]["canonical_service_code"] == "MONITORAMENTO_CONTRATUAL"
    assert bridge_intel["offer"]["extra_cli_service_id"] == "gestao_monitoramento_contratual"
    assert bridge_intel["messaging"]["fact_to_mention"]

    resolution = {
        "cnpj14": "11222333000181",
        "candidates": [
            {
                "candidate_id": "ct-1",
                "name": "Ana Silva",
                "cargo": "Engenheira de contratos",
                "email": "ana@acme.example.com",
                "phone_e164": "",
                "verification_status": "OBSERVED",
                "confidence": 0.9,
                "recommended": True,
                "source": {
                    "source_type": "site",
                    "source_url": "https://acme.example.com/equipe",
                    "observed_at": "2026-08-01T00:00:00Z",
                },
                "ownership_status": "COMPANY_OWNED",
            }
        ],
        "recommended_candidate_id": "ct-1",
        "official_domain": "acme.example.com",
    }
    bridge_contacts = contact_resolution_to_bridge_row(resolution)
    assert bridge_contacts["contacts"][0]["role"] == "Engenheira de contratos"
    assert bridge_contacts["contacts"][0]["verification_status"] == "OFFICIAL_SOURCE"
    assert bridge_contacts["contacts"][0]["source_type"] == "site"
    assert bridge_contacts["contacts"][0]["ownership_status"] == "COMPANY_OWNED"
    assert bridge_contacts["official_domain"] == "acme.example.com"

    from scripts.confenge_outreach_pipeline.adapt import universe_row_for_bridge

    u = universe_row_for_bridge(universe, rank=1)
    leads = build_leads([u], [bridge_intel], [bridge_contacts])
    assert len(leads) == 1
    assert leads[0]["offer"]["service_code"] == "MONITORAMENTO_CONTRATUAL"
    assert leads[0]["offer"]["extra_cli_service_id"] == "gestao_monitoramento_contratual"
    assert leads[0]["contacts"][0]["email"] == "ana@acme.example.com"
    assert leads[0]["messaging_context"]["fact_to_mention"]


def test_pipeline_network_run_wires_discovery_cascade_and_job_meta(tmp_path: Path) -> None:
    rows = [
        {
            "cnpj14": "11222333000181",
            "razao_social": "ACME ENGENHARIA LTDA",
            "nome_fantasia": "Acme",
            "website": "https://acme.example.com",
        }
    ]
    meta = contact_job_meta(rows)
    assert meta["11222333000181"]["razao_social"] == "ACME ENGENHARIA LTDA"
    assert meta["11222333000181"]["nome_fantasia"] == "Acme"
    resolver = build_pipeline_contact_resolver(
        PipelineConfig(out_dir=tmp_path, allow_network=True, enable_web_search=True),
        sample_rows=rows,
        cache=None,
        service_context="generic",
    )
    assert resolver.config.discovery_cascade is not None
    assert resolver.config.allow_network is True
    assert resolver.config.job_meta["11222333000181"]["razao_social"] == "ACME ENGENHARIA LTDA"


def test_pipeline_offline_run_does_not_wire_discovery_cascade(tmp_path: Path) -> None:
    resolver = build_pipeline_contact_resolver(
        PipelineConfig(out_dir=tmp_path, allow_network=False),
        sample_rows=[{"cnpj14": "11222333000181", "razao_social": "ACME"}],
        cache=None,
        service_context="generic",
    )
    assert resolver.config.discovery_cascade is None


def test_contract_schema_matches_warmbly_constants() -> None:
    """Producer schema_version equals Warmbly consumer constant."""
    schema_path = ROOT / "scripts" / "warmbly_bridge" / "schemas" / "confenge.outreach.v1.json"
    assert schema_path.is_file()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    # schema file may use $id; constant in package is authoritative
    from scripts.warmbly_bridge import SCHEMA_OUTREACH

    assert SCHEMA_OUTREACH == "confenge.outreach.v1"
    # If JSON Schema, check required top-level
    if "properties" in schema:
        for key in ("schema_version", "source", "leads"):
            assert key in schema["properties"] or key in (schema.get("required") or [])


def test_git_sha_is_resolved_from_runtime_checkout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_check_output(command: list[str], **_kwargs: object) -> str:
        captured["command"] = command
        return "feedsha12345\n"

    monkeypatch.setattr(pipeline_module.subprocess, "check_output", fake_check_output)

    assert pipeline_module._git_sha() == "feedsha12345"
    runtime_root = Path(pipeline_module.__file__).resolve().parents[2]
    command = captured["command"]
    assert isinstance(command, list)
    assert command[1:3] == ["-C", str(runtime_root)]
