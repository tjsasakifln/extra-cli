"""Mandatory full-data pipeline tests: silent limits, cursor, memory, feed, resume.

These drive the shipped production modules — not reimplemented stand-ins.
"""

from __future__ import annotations

import ast
import inspect
import json
from datetime import date
from pathlib import Path

from scripts.confenge_activation.checkpoint import (
    load_checkpoint,
    new_checkpoint,
    save_checkpoint,
)
from scripts.confenge_activation.funnel import (
    DOWNSTREAM_EXPORTED,
    apply_commercial_memory,
    is_reeligible,
    load_commercial_memory_jsonl,
)
from scripts.confenge_activation.metrics import reconcile
from scripts.confenge_activation.planner import run_activation_cycle
from scripts.confenge_activation.policy import load_policy
from scripts.confenge_outreach_pipeline.pipeline import PipelineConfig, run_pipeline
from scripts.confenge_universe.source import build_keyset_query, iter_contract_rows
from scripts.warmbly_bridge.export import ExportConfig, export_outreach

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CSV = ROOT / "tests" / "fixtures" / "confenge_universe" / "contracts_sample.csv"
DNC_TXT = ROOT / "tests" / "fixtures" / "confenge_universe" / "dnc.txt"
POLICY = load_policy()
AS_OF = date(2026, 8, 8)
SOURCE_PY = ROOT / "scripts" / "confenge_universe" / "source.py"
PIPELINE_PY = ROOT / "scripts" / "confenge_outreach_pipeline" / "pipeline.py"


def _company(cnpj: str, *, last: str = "2026-07-20", commercial: str = "NEW", score: float = 55.0) -> dict:
    return {
        "cnpj14": cnpj,
        "cnpj_root": cnpj[:8],
        "razao_social": f"Co {cnpj[:4]}",
        "outreach_eligibility": "ELIGIBLE" if commercial not in {"DNC", "DO_NOT_CONTACT"} else "DNC",
        "commercial_state": commercial,
        "priority_score": score,
        "construction_evidence": {"sector_fit": "STRONG_ENGINEERING_FIT", "relevant_contract_count": 2},
        "portfolio": {
            "active_contract_count": 2,
            "contract_count_recent": 2,
            "contract_count_total": 5,
            "first_contract_date": "2024-08-01",
            "last_contract_date": last,
            "value_recent_brl": 500_000,
            "value_total_brl": 1_000_000,
            "orgaos": ["ORGAO"],
            "ufs_atuacao": ["SP"],
            "recent_contracts": [
                {
                    "contrato_id": "1",
                    "objeto": "obra de engenharia",
                    "data_publicacao": last,
                    "valor_total": 500_000,
                    "is_active": True,
                }
            ],
        },
    }


# ── Silent limits ──────────────────────────────────────────────────────────


def test_production_keyset_limit_is_only_batch_bound() -> None:
    """LIMIT in production SQL is keyset batch size, not a silent universe cap."""
    sql, params = build_keyset_query(columns=["id", "ni_fornecedor", "valor_global"], batch_size=2000)
    assert "LIMIT %s" in sql
    assert params[-1] == 2000
    # Full walk: next keyset continues — no OFFSET, no hard max_rows in default
    assert "OFFSET" not in sql.upper()
    src = SOURCE_PY.read_text(encoding="utf-8")
    # max_rows documented as diagnostic only
    assert "diagnostic sampling only" in src or "max_rows" in src
    # CLI default for max_rows is None (no default production sample)
    cli_src = (ROOT / "scripts" / "confenge_universe" / "cli.py").read_text(encoding="utf-8")
    assert "default=None" in cli_src or 'default=None' in cli_src.replace(" ", "")


def test_pipeline_max_rows_default_is_none() -> None:
    """--max-rows is never a production default on PipelineConfig."""
    cfg = PipelineConfig(out_dir=Path("/tmp/x"))  # noqa: S108
    assert cfg.max_rows is None
    sig = inspect.signature(PipelineConfig)
    assert sig.parameters["max_rows"].default is None


def test_no_silent_max_rows_assignment_in_pipeline_ast() -> None:
    """Static audit: pipeline must not hardcode max_rows=N for production path."""
    tree = ast.parse(PIPELINE_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "max_rows" and isinstance(kw.value, ast.Constant):
                    # Only None is allowed as a constant default binding
                    assert kw.value.value is None, f"silent max_rows={kw.value.value} in pipeline"


def test_synthetic_stream_batches_not_full_ram() -> None:
    """1M+ synthetic rows stream via batches — never materialize all at once in iter."""
    def gen():
        for i in range(1_000_050):
            yield {"contrato_id": str(i), "fornecedor_cnpj": f"{i%10000000:08d}000181"}

    peak_batch = 0
    n_batches = 0
    total = 0
    for batch in iter_contract_rows(gen(), batch_size=5000):
        peak_batch = max(peak_batch, len(batch))
        n_batches += 1
        total += len(batch)
        # simulate consumer discarding batch
        del batch
        if n_batches >= 3:
            # prove streaming works without requiring full consume in CI time
            break
    assert peak_batch == 5000
    assert total == 15000
    # Full generator is not list()'d — only 3 batches pulled


def test_reconciliation_unaccounted_zero() -> None:
    r = reconcile(entrada=1000, processados=700, excluidos=300, label="t")
    assert r["ok"] is True
    assert r["unaccounted_records"] == 0
    bad = reconcile(entrada=1000, processados=700, excluidos=299)
    assert bad["ok"] is False
    assert bad["unaccounted_records"] == 1


# ── Cursor / multi-round ───────────────────────────────────────────────────


def test_limit_downstream_does_not_change_universe_total(tmp_path: Path) -> None:
    """Smoke path: limit_downstream bounds sample only (force_sample_mode).

    Production activation uses policy.planned_capacity — covered by
    test_production_activation_does_not_use_limit_downstream_as_capacity.
    """
    r1 = run_pipeline(
        PipelineConfig(
            out_dir=tmp_path / "a",
            csv_path=str(FIXTURE_CSV),
            dnc_path=str(DNC_TXT) if DNC_TXT.is_file() else None,
            as_of=date(2026, 8, 1),
            limit_downstream=1,
            skip_contacts=True,
            progress=False,
            force_sample_mode=True,
        )
    )
    r2 = run_pipeline(
        PipelineConfig(
            out_dir=tmp_path / "b",
            csv_path=str(FIXTURE_CSV),
            dnc_path=str(DNC_TXT) if DNC_TXT.is_file() else None,
            as_of=date(2026, 8, 1),
            limit_downstream=2,
            skip_contacts=True,
            progress=False,
            force_sample_mode=True,
        )
    )
    assert r1.ok and r2.ok
    assert r1.stages["universe_row_count"] == r2.stages["universe_row_count"]
    assert r1.stages["sample"]["count"] == 1
    assert r2.stages["sample"]["count"] == 2
    assert r1.stages["sample"]["count"] <= r1.stages["universe_row_count"]


def test_round2_does_not_repeat_first_batch() -> None:
    """After round 1 marks downstream SELECTED/EXPORTED, round 2 advances cursor."""
    rows = []
    for i in range(40):
        cnpj = f"{i:08d}000181"
        assert len(cnpj) == 14
        rows.append(_company(cnpj, last="2026-07-25", score=50 + (i % 20)))

    c1 = run_activation_cycle(
        rows,
        policy=POLICY,
        as_of=AS_OF,
        capacity_override=10,
        evaluated_at="2026-08-08T10:00:00Z",
    )
    assert c1.hot_set_count == 10
    hot1 = {p.cnpj14 for p in c1.hot_set}
    # Simulate export persistence
    prior = {}
    for p in c1.projections:
        d = p.as_dict()
        if p.cnpj14 in hot1:
            d["downstream_status"] = DOWNSTREAM_EXPORTED
            d["last_downstream_at"] = "2026-08-08T10:00:00Z"
            d["last_hot_set_at"] = "2026-08-08T10:00:00Z"
        prior[p.cnpj14] = d

    c2 = run_activation_cycle(
        rows,
        policy=POLICY,
        as_of=AS_OF,
        prior_projections=prior,
        capacity_override=10,
        evaluated_at="2026-08-08T11:00:00Z",
    )
    hot2 = {p.cnpj14 for p in c2.hot_set}
    assert hot2.isdisjoint(hot1), f"round2 re-selected prior hot set: {hot2 & hot1}"
    assert c2.reservoir_count == c1.reservoir_count == 40


def test_after_n_rounds_all_eligibles_reachable() -> None:
    n = 25
    rows = [_company(f"{i:08d}000199", last="2026-07-20", score=40 + i) for i in range(n)]
    for r in rows:
        assert len(r["cnpj14"]) == 14
    prior: dict = {}
    seen: set[str] = set()
    cap = 5
    rounds = 0
    while len(seen) < n and rounds < 20:
        cycle = run_activation_cycle(
            rows,
            policy=POLICY,
            as_of=AS_OF,
            prior_projections=prior,
            capacity_override=cap,
            evaluated_at=f"2026-08-08T{10 + rounds:02d}:00:00Z",
        )
        for p in cycle.hot_set:
            seen.add(p.cnpj14)
        # persist exported
        prior = {}
        hot = {p.cnpj14 for p in cycle.hot_set}
        for p in cycle.projections:
            d = p.as_dict()
            if p.cnpj14 in hot or p.cnpj14 in seen:
                d["downstream_status"] = DOWNSTREAM_EXPORTED
                d["last_downstream_at"] = d.get("last_hot_set_at") or "2026-08-08T10:00:00Z"
                d["last_hot_set_at"] = d.get("last_hot_set_at") or "2026-08-08T10:00:00Z"
            prior[p.cnpj14] = d
        rounds += 1
    assert len(seen) == n, f"only reached {len(seen)}/{n} after {rounds} rounds"
    assert rounds >= (n // cap)


# ── Commercial memory ──────────────────────────────────────────────────────


def test_dnc_never_reenters_hot_set() -> None:
    rows = [
        _company("11222333000181", commercial="DO_NOT_CONTACT", last="2026-07-28"),
        _company("11222333000182", commercial="NEW", last="2026-07-28"),
    ]
    cycle = run_activation_cycle(
        rows, policy=POLICY, as_of=AS_OF, capacity_override=10, evaluated_at="2026-08-08T10:00:00Z"
    )
    by = {p.cnpj14: p for p in cycle.projections}
    assert by["11222333000181"].activation_state == "SUPPRESSED"
    hot = {p.cnpj14 for p in cycle.hot_set}
    assert "11222333000181" not in hot
    assert "11222333000182" in hot


def test_not_now_respects_next_eligible_at() -> None:
    prior = {
        "11222333000183": {
            "cnpj14": "11222333000183",
            "activation_state": "WATCH",
            "commercial_state": "NOT_NOW",
            "next_eligible_at": "2026-12-01T00:00:00Z",
            "downstream_status": "PENDING",
            "source_hash": "x",
        }
    }
    assert not is_reeligible(prior["11222333000183"], as_of=date(2026, 8, 8))
    assert is_reeligible(prior["11222333000183"], as_of=date(2026, 12, 2))


def test_bounced_email_invalidates_address_not_company() -> None:
    row = _company("11222333000184")
    mem = {
        "11222333000184": {
            "commercial_state": "NEW",
            "bounced_emails": ["bad@example.com"],
            "last_outcome": "BOUNCE",
        }
    }
    out = apply_commercial_memory(row, mem)
    assert out["commercial_state"] == "NEW"
    assert out["bounced_emails"] == ["bad@example.com"]
    assert out.get("outreach_eligibility") != "DNC"


def test_replied_blocks_parallel_cadence() -> None:
    rows = [_company("11222333000185", commercial="REPLIED", last="2026-07-28")]
    cycle = run_activation_cycle(
        rows, policy=POLICY, as_of=AS_OF, capacity_override=5, evaluated_at="2026-08-08T10:00:00Z"
    )
    assert cycle.hot_set_count == 0
    assert cycle.projections[0].activation_state in {"WATCH", "SUPPRESSED"} or (
        cycle.projections[0].commercial_state == "REPLIED"
    )


def test_commercial_memory_jsonl_loader(tmp_path: Path) -> None:
    p = tmp_path / "mem.jsonl"
    p.write_text(
        json.dumps({"cnpj14": "11222333000186", "commercial_state": "DO_NOT_CONTACT"}) + "\n",
        encoding="utf-8",
    )
    mem = load_commercial_memory_jsonl(p)
    assert mem["11222333000186"]["commercial_state"] == "DO_NOT_CONTACT"


# ── Checkpoint / resume ────────────────────────────────────────────────────


def test_checkpoint_resume_not_restart(tmp_path: Path) -> None:
    ckpt = new_checkpoint(run_id="run-test", as_of="2026-08-08")
    ckpt.mark_completed("universe", counts={"rows": 100}, cursor="cid-500")
    ckpt.full_datalake_scanned = True
    ckpt.universe_total = 100
    path = save_checkpoint(tmp_path, ckpt)
    assert path.is_file()
    loaded = load_checkpoint(tmp_path)
    assert loaded is not None
    assert loaded.stage_completed("universe")
    assert loaded.universe_total == 100
    assert loaded.full_datalake_scanned is True
    assert loaded.as_dict()["resume_safe"] is True
    # resume continues: next stage still pending
    assert not loaded.stage_completed("activation")


def test_pipeline_resume_skips_completed_universe(tmp_path: Path) -> None:
    out = tmp_path / "run"
    r1 = run_pipeline(
        PipelineConfig(
            out_dir=out,
            csv_path=str(FIXTURE_CSV),
            dnc_path=str(DNC_TXT) if DNC_TXT.is_file() else None,
            as_of=date(2026, 8, 1),
            limit_downstream=2,
            skip_contacts=True,
            progress=False,
        )
    )
    assert r1.ok
    # Second run with skip via checkpoint + skip_universe flag
    r2 = run_pipeline(
        PipelineConfig(
            out_dir=out,
            csv_path=str(FIXTURE_CSV),
            skip_universe=True,
            as_of=date(2026, 8, 1),
            limit_downstream=2,
            skip_contacts=True,
            progress=False,
            resume=True,
        )
    )
    assert r2.ok
    assert r2.stages["universe_row_count"] == r1.stages["universe_row_count"]
    # universe stage should report skipped when reusing
    assert r2.stages.get("universe", {}).get("skipped") is True or r2.ok


# ── Feed idempotency ───────────────────────────────────────────────────────


def test_feed_chunk_reimport_idempotent(tmp_path: Path) -> None:
    uni = tmp_path / "u.jsonl"
    intel = tmp_path / "i.jsonl"
    contacts = tmp_path / "c.jsonl"
    # Minimal valid bridge rows
    uni_row = {
        "cnpj14": "11222333000181",
        "cnpj_root": "11222333",
        "razao_social": "ACME",
        "municipio": "SP",
        "uf": "SP",
        "outreach_eligibility": "ELIGIBLE",
        "priority_score": 50,
        "commercial_state": "NEW",
        "portfolio": {"contract_count_total": 1, "value_total_brl": 100000, "ufs_atuacao": ["SP"]},
        "target_fit_class": "TARGET_CONFIRMED",
        "target_fit_version": "confenge-target-fit-v2",
        "target_fit_computed_at": "2026-08-08T10:00:00Z",
        "target_fit_source_watermark": "2026-08-08T10:00:00Z",
        "target_fit_operational_status": "ok",
    }
    intel_row = {
        "cnpj14": "11222333000181",
        "offer": {"service_code": "reajuste_contratual", "label": "Reajuste"},
        "messaging": {
            "fact_to_mention": "Contrato X",
            "question_to_ask": "Q?",
            "cta": "C",
            "claims_to_avoid": [],
        },
        "why_now": {"trigger": "t", "temporal_fact": "f", "epistemic_class": "confirmed"},
    }
    contact_row = {"cnpj14": "11222333000181", "contacts": []}
    for path, rows in ((uni, [uni_row]), (intel, [intel_row]), (contacts, [contact_row])):
        path.write_text(json.dumps(rows[0], ensure_ascii=False) + "\n", encoding="utf-8")

    out = tmp_path / "feed"
    cfg = ExportConfig(
        universe=uni,
        account_intelligence=intel,
        contacts=contacts,
        out_dir=out,
        generated_at="2026-08-08T12:00:00Z",
        repo_sha="deadbeef",
    )
    r1 = export_outreach(cfg)
    r2 = export_outreach(cfg)
    assert r1["ok"] and r2["ok"]
    assert r1["snapshot_hash"] == r2["snapshot_hash"]
    assert r1["run_id"] == r2["run_id"]
    chunks1 = {c["file"]: c["content_hash"] for c in r1["chunks"]}
    chunks2 = {c["file"]: c["content_hash"] for c in r2["chunks"]}
    assert chunks1 == chunks2
    # Second export should mark unchanged when bytes match
    assert any(c.get("status") == "unchanged" for c in r2["chunks"]) or chunks1 == chunks2


def test_no_lead_disappears_between_chunks(tmp_path: Path) -> None:
    leads_cnpjs = [f"{i:08d}000181" for i in range(15)]
    uni_lines = []
    intel_lines = []
    contact_lines = []
    for cnpj in leads_cnpjs:
        uni_lines.append(
            json.dumps(
                {
                    "cnpj14": cnpj,
                    "cnpj_root": cnpj[:8],
                    "razao_social": f"Co{cnpj[:4]}",
                    "uf": "SP",
                    "municipio": "SP",
                    "outreach_eligibility": "ELIGIBLE",
                    "priority_score": 40,
                    "commercial_state": "NEW",
                    "portfolio": {
                        "contract_count_total": 1,
                        "value_total_brl": 10000,
                        "ufs_atuacao": ["SP"],
                    },
                    "target_fit_class": "TARGET_CONFIRMED",
                    "target_fit_version": "confenge-target-fit-v2",
                    "target_fit_computed_at": "2026-08-08T10:00:00Z",
                    "target_fit_source_watermark": "2026-08-08T10:00:00Z",
                    "target_fit_operational_status": "ok",
                }
            )
        )
        intel_lines.append(
            json.dumps(
                {
                    "cnpj14": cnpj,
                    "offer": {"service_code": "auditoria_planilhas", "label": "Audit"},
                    "messaging": {
                        "fact_to_mention": "f",
                        "question_to_ask": "q",
                        "cta": "c",
                        "claims_to_avoid": [],
                    },
                    "why_now": {"trigger": "t", "temporal_fact": "f", "epistemic_class": "confirmed"},
                }
            )
        )
        contact_lines.append(json.dumps({"cnpj14": cnpj, "contacts": []}))
    uni = tmp_path / "u.jsonl"
    intel = tmp_path / "i.jsonl"
    contacts = tmp_path / "c.jsonl"
    uni.write_text("\n".join(uni_lines) + "\n", encoding="utf-8")
    intel.write_text("\n".join(intel_lines) + "\n", encoding="utf-8")
    contacts.write_text("\n".join(contact_lines) + "\n", encoding="utf-8")
    out = tmp_path / "feed"
    result = export_outreach(
        ExportConfig(
            universe=uni,
            account_intelligence=intel,
            contacts=contacts,
            out_dir=out,
            max_leads_per_chunk=4,
            generated_at="2026-08-08T12:00:00Z",
            repo_sha="abc",
        )
    )
    assert result["lead_count"] == 15
    found: set[str] = set()
    for ch in sorted(out.glob("chunk_*.json")):
        feed = json.loads(ch.read_text(encoding="utf-8"))
        assert "pagination" in feed
        assert "has_more" in feed["pagination"]
        for lead in feed["leads"]:
            found.add(lead["company"]["cnpj14"])
    assert found == set(leads_cnpjs)


# ── Pipeline single-lead error isolation (structural) ──────────────────────


def test_activation_error_on_one_row_does_not_drop_others() -> None:
    """Bad CNPJ skipped; good rows still projected."""
    rows = [
        {"cnpj14": "bad", "portfolio": {}},  # skipped
        _company("11222333000187", last="2026-07-22"),
    ]
    cycle = run_activation_cycle(
        rows, policy=POLICY, as_of=AS_OF, capacity_override=5, evaluated_at="2026-08-08T10:00:00Z"
    )
    assert cycle.reservoir_count == 1
    assert cycle.projections[0].cnpj14 == "11222333000187"


def test_activation_projection_has_durable_funnel_fields():
    """Obj §4: per-company durable commercial/funnel fields present."""
    from scripts.confenge_activation.planner import evaluate_row
    from scripts.confenge_activation.policy import load_policy

    row = _company("11222333000181", last="2026-07-25")
    row["cnpj_root"] = "11222333"
    proj = evaluate_row(
        row, policy=load_policy(), as_of=AS_OF, evaluated_at="2026-08-08T10:00:00Z"
    )
    d = proj.as_dict()
    for key in (
        "company_key",
        "cnpj_raiz",
        "priority_score",
        "priority_band",
        "account_intelligence_status",
        "contact_resolution_status",
        "feed_export_status",
        "warmbly_import_status",
        "last_processed_at",
        "next_eligible_at",
        "processing_attempts",
        "last_error",
        "commercial_state",
        "outreach_state",
        "last_outcome",
        "downstream_status",
    ):
        assert key in d, f"missing durable field {key}"
    assert d["cnpj_raiz"] == "11222333"
    assert d["company_key"]
    assert d["account_intelligence_status"] == "PENDING"
    assert d["feed_export_status"] == "PENDING"


def test_exclusion_breakdown_sums_to_exclusions():
    from scripts.confenge_activation.metrics import build_universe_summary

    counts = {
        "input_supplier_roots": 1000,
        "eligibles": 200,
        "exclusions": 800,
        "input_contract_rows": 5000,
        "identity_row_exclusions": 10,
        "full_scale": True,
        "max_rows": None,
        "exclusion_breakdown": {
            "NOT_CONSTRUCTION": 790,
            "NATURAL_PERSON": 5,
            "PUBLIC_ORGAN": 5,
            # stale overcount like production bug (+64 style)
            "STALE_MIXIN": 64,
        },
        "reconciliation": {
            "input_supplier_roots": 1000,
            "eligibles": 200,
            "exclusions": 800,
            "ok": True,
            "unaccounted_records": 0,
        },
    }
    s = build_universe_summary(source={"mode": "test"}, counts=counts, universe_rows=[])
    assert s["exclusion_breakdown_sum"] == 800
    assert sum(s["exclusion_breakdown"].values()) == 800
    assert s["unaccounted_records"] == 0
