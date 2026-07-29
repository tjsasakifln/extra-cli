"""Tests for scripts.ops.extra_recurring_delivery — recurring weekly deltas."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from scripts.ops.extra_recurring_delivery import (
    ALLOWED_EVENT_TYPES,
    EXIT_BLOCKED,
    EventDelta,
    detect_all_deltas,
    load_weekly_input,
    main,
    run_delivery,
)
from scripts.ops.strategic_monthly_monitor import compute_variation as smm_variation

AS_OF = date(2026, 7, 29)


# ---------------------------------------------------------------------------
# Fixture builders (unit-test only — not evidence paths)
# ---------------------------------------------------------------------------


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    """Write CSV with valid header. Empty rows → header-only (SUCCESS_ZERO shape).

    Never write zero-byte files: post-D3 validate_weekly_pack rejects them.
    """
    if rows:
        fields = fieldnames or list(rows[0].keys())
    else:
        fields = fieldnames or ["row_count"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        if not rows and fields == ["row_count"]:
            w.writerow({"row_count": 0})
            return
        for r in rows:
            w.writerow(r)


def make_weekly_pack(
    root: Path,
    *,
    cycle_id: str = "weekly-test-001",
    collection_id: str = "col-test-001",
    exit_code: int = 0,
    opportunities: list[dict] | None = None,
    contracts: list[dict] | None = None,
    competitors: list[dict] | None = None,
    source_health: list[dict] | None = None,
    orgaos: list[dict] | None = None,
) -> Path:
    """Minimal valid weekly pack (manifest + checksums + product CSVs)."""
    root.mkdir(parents=True, exist_ok=True)
    opps = opportunities if opportunities is not None else [
        {
            "id": "1",
            "source": "pncp",
            "numero_controle_pncp": "11111111000111-1-000001/2026",
            "source_id": "11111111000111-1-000001/2026",
            "orgao_nome": "Pref. Alpha",
            "objeto": "Reforma de escola municipal",
            "status_canonico": "open",
            "data_encerramento": "2026-08-15",
            "link_edital": "https://pncp.gov.br/app/editais/11111111000111/2026/1",
            "valor_estimado": "100000",
        }
    ]
    contracts = contracts if contracts is not None else [
        {
            "contrato_id": "CT-001",
            "orgao_nome": "Pref. Alpha",
            "fornecedor_cnpj": "22222222000122",
            "fornecedor_nome": "Construtora A",
            "data_fim": "2026-12-01",  # ~125d from AS_OF → in 180d window
            "valor_total": "50000",
        }
    ]
    competitors = competitors if competitors is not None else [
        {
            "fornecedor_cnpj": "22222222000122",
            "fornecedor_nome": "Construtora A",
            "n_contratos": "10",
            "soma_valor_contratado": "1000000",
        },
        {
            "fornecedor_cnpj": "33333333000133",
            "fornecedor_nome": "Construtora B",
            "n_contratos": "5",
            "soma_valor_contratado": "500000",
        },
    ]
    source_health = source_health if source_health is not None else [
        {
            "source": "pncp_opportunities",
            "level": "fresh",
            "sla_hours": "24",
            "age_hours": "1.0",
            "last_status": "completed",
        },
        {
            "source": "pncp_contracts",
            "level": "fresh",
            "sla_hours": "168",
            "age_hours": "2.0",
            "last_status": "completed",
        },
    ]
    orgaos = orgaos if orgaos is not None else [
        {"orgao_cnpj": "111", "orgao_nome": "Pref. Alpha", "n_opp": "1"},
    ]

    # D3/schema: validate_weekly_pack requires critical columns (incl. source).
    for row in opps:
        row.setdefault("source", "pncp")
    _write_csv(root / "opportunities.csv", opps)
    _write_csv(root / "contracts.csv", contracts)
    _write_csv(root / "competitors.csv", competitors)
    _write_csv(root / "source_health.csv", source_health)
    _write_csv(root / "orgaos.csv", orgaos)
    _write_csv(root / "gaps.csv", [{"gap": "none", "detail": "fixture"}])
    _write_csv(root / "claims_provenance.csv", [{"claim_id": "c1", "kind": "test"}])
    (root / "executive_summary.md").write_text("# fixture weekly\n", encoding="utf-8")
    # minimal xlsx substitute (checksum still works on bytes)
    (root / "extra_weekly_pack.xlsx").write_bytes(b"PK\x03\x04fixture-xlsx")

    product_files = {
        "opportunities_csv": root / "opportunities.csv",
        "contracts_csv": root / "contracts.csv",
        "competitors_csv": root / "competitors.csv",
        "orgaos_csv": root / "orgaos.csv",
        "source_health_csv": root / "source_health.csv",
        "gaps_csv": root / "gaps.csv",
        "claims_csv": root / "claims_provenance.csv",
        "executive_md": root / "executive_summary.md",
        "excel": root / "extra_weekly_pack.xlsx",
    }
    artifacts = {}
    for key, pth in product_files.items():
        artifacts[key] = {
            "path": pth.name,
            "sha256": _sha(pth),
            "bytes": pth.stat().st_size,
        }

    checksums = {
        "schema": "extra-weekly-checksums/1.0",
        "cycle_id": cycle_id,
        "collection_id": collection_id,
        "artifacts": artifacts,
    }
    (root / "checksums.json").write_text(
        json.dumps(checksums, indent=2) + "\n", encoding="utf-8"
    )
    manifest = {
        "cycle_id": cycle_id,
        "collection_id": collection_id,
        "exit_code": exit_code,
        "started_at": "2026-07-29T02:00:00Z",
        "finished_at": "2026-07-29T03:00:00Z",
        "freshness": source_health,
        "source_health": source_health,
        "limitations": [],
        "stages": [{"name": "delivery", "status": "ok"}],
        "claims_allowed": ["fixture"],
        "claims_forbidden": [],
        "gaps": [],
        "runs": [],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return root


REQUIRED_OUTPUTS = [
    "weekly-report.md",
    "weekly-report.xlsx",
    "weekly-delta.json",
    "weekly-delta.csv",
    "tender-events.csv",
    "expiring-contracts.csv",
    "orgaos-winners-delta.csv",
    "urgent-alerts.json",
    "urgent-alerts.csv",
    "monthly-report.md",
    "monthly-comparison.json",
    "meeting-support.md",
    "source-health.json",
    "manifest.json",
    "checksums.json",
]


def _event_types(delivery: Path) -> set[str]:
    data = json.loads((delivery / "weekly-delta.json").read_text(encoding="utf-8"))
    return {e["event_type"] for e in data["events"]}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_current_without_previous_first_run(tmp_path: Path) -> None:
    cur = make_weekly_pack(tmp_path / "cur", cycle_id="w-cur")
    out = tmp_path / "out"
    result = run_delivery(
        current_run=cur, delivery_out=out, previous_run=None, as_of=AS_OF
    )
    assert result["ok"] is True
    assert result["first_run"] is True
    assert result["status"] == "FIRST_RUN"
    data = json.loads((out / "weekly-delta.json").read_text(encoding="utf-8"))
    assert data["status"] == "FIRST_RUN"
    # no NEW_TENDER spam on first run
    assert "NEW_TENDER" not in _event_types(out)
    for name in REQUIRED_OUTPUTS:
        assert (out / name).is_file(), name
    assert "FIRST_RUN" in (out / "weekly-report.md").read_text(encoding="utf-8")


def test_identical_runs_success_zero(tmp_path: Path) -> None:
    base = make_weekly_pack(tmp_path / "a", cycle_id="w-a")
    prev = tmp_path / "b"
    shutil.copytree(base, prev)
    # rewrite cycle ids but same content-ish
    for p, cid in ((base, "w-cur"), (prev, "w-prev")):
        make_weekly_pack(p, cycle_id=cid)  # identical opps/contracts
    out = tmp_path / "out"
    result = run_delivery(
        current_run=base, delivery_out=out, previous_run=prev, as_of=AS_OF
    )
    assert result["status"] == "SUCCESS_ZERO"
    assert result["total_events"] == 0
    data = json.loads((out / "weekly-delta.json").read_text(encoding="utf-8"))
    assert data["total_events"] == 0
    # reports still present
    assert (out / "weekly-report.md").is_file()
    assert (out / "monthly-report.md").is_file()
    assert "SUCCESS_ZERO" in (out / "weekly-report.md").read_text(encoding="utf-8")


def test_new_tender(tmp_path: Path) -> None:
    prev = make_weekly_pack(tmp_path / "prev", cycle_id="w-prev")
    opps = [
        {
            "id": "1",
            "numero_controle_pncp": "11111111000111-1-000001/2026",
            "source_id": "11111111000111-1-000001/2026",
            "orgao_nome": "Pref. Alpha",
            "objeto": "Reforma",
            "status_canonico": "open",
            "data_encerramento": "2026-08-15",
            "link_edital": "https://pncp.gov.br/app/editais/11111111000111/2026/1",
        },
        {
            "id": "2",
            "numero_controle_pncp": "11111111000111-1-000099/2026",
            "source_id": "11111111000111-1-000099/2026",
            "orgao_nome": "Pref. Beta",
            "objeto": "Pavimentação nova",
            "status_canonico": "open",
            "data_encerramento": "2026-09-01",
            "link_edital": "https://pncp.gov.br/app/editais/11111111000111/2026/99",
        },
    ]
    cur = make_weekly_pack(tmp_path / "cur", cycle_id="w-cur", opportunities=opps)
    out = tmp_path / "out"
    run_delivery(current_run=cur, delivery_out=out, previous_run=prev, as_of=AS_OF)
    types = _event_types(out)
    assert "NEW_TENDER" in types
    data = json.loads((out / "weekly-delta.json").read_text(encoding="utf-8"))
    new = [e for e in data["events"] if e["event_type"] == "NEW_TENDER"]
    assert any("000099" in e["entity_id"] for e in new)


def test_deadline_changed(tmp_path: Path) -> None:
    prev = make_weekly_pack(tmp_path / "prev", cycle_id="w-prev")
    opps = [
        {
            "id": "1",
            "numero_controle_pncp": "11111111000111-1-000001/2026",
            "source_id": "11111111000111-1-000001/2026",
            "orgao_nome": "Pref. Alpha",
            "objeto": "Reforma",
            "status_canonico": "open",
            "data_encerramento": "2026-08-01",  # changed from 08-15
            "link_edital": "https://pncp.gov.br/app/editais/11111111000111/2026/1",
        }
    ]
    cur = make_weekly_pack(tmp_path / "cur", cycle_id="w-cur", opportunities=opps)
    out = tmp_path / "out"
    run_delivery(current_run=cur, delivery_out=out, previous_run=prev, as_of=AS_OF)
    assert "DEADLINE_CHANGED" in _event_types(out)


@pytest.mark.parametrize(
    "new_status,expected",
    [
        ("suspended", "SUSPENDED"),
        ("revogada", "REVOKED"),
        ("retificado", "RECTIFIED"),
    ],
)
def test_status_special_events(tmp_path: Path, new_status: str, expected: str) -> None:
    prev = make_weekly_pack(tmp_path / "prev", cycle_id="w-prev")
    opps = [
        {
            "id": "1",
            "numero_controle_pncp": "11111111000111-1-000001/2026",
            "source_id": "11111111000111-1-000001/2026",
            "orgao_nome": "Pref. Alpha",
            "objeto": "Reforma",
            "status_canonico": new_status,
            "data_encerramento": "2026-08-15",
            "link_edital": "https://pncp.gov.br/app/editais/11111111000111/2026/1",
        }
    ]
    cur = make_weekly_pack(tmp_path / "cur", cycle_id="w-cur", opportunities=opps)
    out = tmp_path / "out"
    run_delivery(current_run=cur, delivery_out=out, previous_run=prev, as_of=AS_OF)
    assert expected in _event_types(out)


def test_reopened(tmp_path: Path) -> None:
    prev_opps = [
        {
            "id": "1",
            "numero_controle_pncp": "11111111000111-1-000001/2026",
            "source_id": "11111111000111-1-000001/2026",
            "orgao_nome": "Pref. Alpha",
            "objeto": "Reforma",
            "status_canonico": "suspensa",
            "data_encerramento": "2026-08-15",
            "link_edital": "https://pncp.gov.br/app/editais/11111111000111/2026/1",
        }
    ]
    prev = make_weekly_pack(tmp_path / "prev", cycle_id="w-prev", opportunities=prev_opps)
    cur_opps = [
        {
            **prev_opps[0],
            "status_canonico": "open",
        }
    ]
    cur = make_weekly_pack(tmp_path / "cur", cycle_id="w-cur", opportunities=cur_opps)
    out = tmp_path / "out"
    run_delivery(current_run=cur, delivery_out=out, previous_run=prev, as_of=AS_OF)
    assert "REOPENED" in _event_types(out)


def test_contract_entering_window(tmp_path: Path) -> None:
    # Previous: contract far out of window; current: same id now ends within 180d
    prev_contracts = [
        {
            "contrato_id": "CT-NEW",
            "orgao_nome": "Pref. Z",
            "fornecedor_cnpj": "99999999000199",
            "fornecedor_nome": "Nova",
            "data_fim": "2028-01-01",  # outside 180d
            "valor_total": "1",
        }
    ]
    cur_contracts = [
        {
            "contrato_id": "CT-NEW",
            "orgao_nome": "Pref. Z",
            "fornecedor_cnpj": "99999999000199",
            "fornecedor_nome": "Nova",
            "data_fim": "2026-10-01",  # ~64d — inside window
            "valor_total": "1",
        }
    ]
    prev = make_weekly_pack(
        tmp_path / "prev", cycle_id="w-prev", contracts=prev_contracts
    )
    cur = make_weekly_pack(
        tmp_path / "cur", cycle_id="w-cur", contracts=cur_contracts
    )
    out = tmp_path / "out"
    run_delivery(
        current_run=cur,
        delivery_out=out,
        previous_run=prev,
        as_of=AS_OF,
        expiry_window_days=180,
    )
    assert "CONTRACT_ENTERED_EXPIRY_WINDOW" in _event_types(out)
    exp = (out / "expiring-contracts.csv").read_text(encoding="utf-8")
    assert "CT-NEW" in exp


def test_winner_change(tmp_path: Path) -> None:
    prev = make_weekly_pack(tmp_path / "prev", cycle_id="w-prev")
    competitors = [
        {
            "fornecedor_cnpj": "22222222000122",
            "fornecedor_nome": "Construtora A",
            "n_contratos": "10",
        },
        {
            "fornecedor_cnpj": "33333333000133",
            "fornecedor_nome": "Construtora B",
            "n_contratos": "5",
        },
        {
            "fornecedor_cnpj": "44444444000144",
            "fornecedor_nome": "Construtora Nova",
            "n_contratos": "3",
        },
    ]
    cur = make_weekly_pack(
        tmp_path / "cur", cycle_id="w-cur", competitors=competitors
    )
    out = tmp_path / "out"
    run_delivery(current_run=cur, delivery_out=out, previous_run=prev, as_of=AS_OF)
    assert "NEW_WINNER" in _event_types(out)


def test_winner_concentration_changed(tmp_path: Path) -> None:
    prev_comp = [
        {"fornecedor_cnpj": "A", "fornecedor_nome": "A", "n_contratos": "50"},
        {"fornecedor_cnpj": "B", "fornecedor_nome": "B", "n_contratos": "50"},
    ]
    cur_comp = [
        {"fornecedor_cnpj": "A", "fornecedor_nome": "A", "n_contratos": "90"},
        {"fornecedor_cnpj": "B", "fornecedor_nome": "B", "n_contratos": "10"},
    ]
    prev = make_weekly_pack(
        tmp_path / "prev", cycle_id="w-prev", competitors=prev_comp
    )
    cur = make_weekly_pack(tmp_path / "cur", cycle_id="w-cur", competitors=cur_comp)
    out = tmp_path / "out"
    run_delivery(current_run=cur, delivery_out=out, previous_run=prev, as_of=AS_OF)
    assert "WINNER_CONCENTRATION_CHANGED" in _event_types(out)


def test_current_nonzero_exit_blocks_package(tmp_path: Path) -> None:
    """Weekly exit!=0 must not produce SUCCESS_ZERO/OK consultive pack."""
    cur = make_weekly_pack(tmp_path / "cur", cycle_id="w-cur", exit_code=2)
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as exc:
        run_delivery(current_run=cur, delivery_out=out, as_of=AS_OF)
    assert int(exc.value.code) == EXIT_BLOCKED
    assert not (out / "manifest.json").is_file() or (
        json.loads((out / "manifest.json").read_text(encoding="utf-8")).get("status")
        != "SUCCESS_ZERO"
        if (out / "manifest.json").is_file()
        else True
    )


def test_previous_nonzero_exit_blocks_delta(tmp_path: Path) -> None:
    prev = make_weekly_pack(tmp_path / "prev", cycle_id="w-prev", exit_code=3)
    cur = make_weekly_pack(tmp_path / "cur", cycle_id="w-cur", exit_code=0)
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as exc:
        run_delivery(current_run=cur, delivery_out=out, previous_run=prev, as_of=AS_OF)
    assert int(exc.value.code) == EXIT_BLOCKED


def test_source_degraded_and_freshness_breach(tmp_path: Path) -> None:
    prev = make_weekly_pack(tmp_path / "prev", cycle_id="w-prev")
    health = [
        {
            "source": "pncp_opportunities",
            "level": "stale",
            "sla_hours": "24",
            "age_hours": "48",
            "last_status": "completed",
        },
        {
            "source": "pncp_contracts",
            "level": "fresh",
            "sla_hours": "168",
            "age_hours": "2",
            "last_status": "completed",
        },
    ]
    cur = make_weekly_pack(
        tmp_path / "cur", cycle_id="w-cur", source_health=health
    )
    out = tmp_path / "out"
    run_delivery(current_run=cur, delivery_out=out, previous_run=prev, as_of=AS_OF)
    types = _event_types(out)
    assert "FRESHNESS_BREACH" in types
    assert "SOURCE_DEGRADED" in types
    sh = json.loads((out / "source-health.json").read_text(encoding="utf-8"))
    assert sh["freshness_breaches"]


def test_weekly_and_monthly_reports(tmp_path: Path) -> None:
    prev = make_weekly_pack(tmp_path / "prev", cycle_id="w-prev")
    cur = make_weekly_pack(tmp_path / "cur", cycle_id="w-cur")
    out = tmp_path / "out"
    run_delivery(current_run=cur, delivery_out=out, previous_run=prev, as_of=AS_OF)
    weekly = (out / "weekly-report.md").read_text(encoding="utf-8")
    monthly = (out / "monthly-report.md").read_text(encoding="utf-8")
    assert "Relatório semanal" in weekly
    assert "Relatório mensal" in monthly
    mc = json.loads((out / "monthly-comparison.json").read_text(encoding="utf-8"))
    assert "variation" in mc
    assert (out / "meeting-support.md").is_file()


def test_denom_zero_variation_safe() -> None:
    # strategic_monthly_monitor.compute_variation — denom zero → delta_pct None
    v = smm_variation({"a": 5, "b": 0}, {"a": 0, "b": 0})
    assert v["fields"]["a"]["delta_pct"] is None
    assert v["fields"]["a"]["delta"] == 5
    assert v["fields"]["b"]["delta"] == 0
    v2 = smm_variation({"x": 1}, {"x": 0})
    assert v2["fields"]["x"]["delta_pct"] is None


def test_urgent_alert_separate(tmp_path: Path) -> None:
    prev = make_weekly_pack(tmp_path / "prev", cycle_id="w-prev")
    opps = [
        {
            "id": "1",
            "numero_controle_pncp": "11111111000111-1-000001/2026",
            "source_id": "11111111000111-1-000001/2026",
            "orgao_nome": "Pref. Alpha",
            "objeto": "Reforma",
            "status_canonico": "revogada",
            "data_encerramento": "2026-08-15",
            "link_edital": "https://pncp.gov.br/app/editais/11111111000111/2026/1",
        }
    ]
    cur = make_weekly_pack(tmp_path / "cur", cycle_id="w-cur", opportunities=opps)
    out = tmp_path / "out"
    run_delivery(current_run=cur, delivery_out=out, previous_run=prev, as_of=AS_OF)
    urgent = json.loads((out / "urgent-alerts.json").read_text(encoding="utf-8"))
    assert urgent["count"] >= 1
    assert any(a["event_type"] == "REVOKED" for a in urgent["alerts"])
    # consolidated report still exists and is distinct file
    assert (out / "weekly-report.md").is_file()
    assert (out / "weekly-report.md").stat().st_size > 0


def test_report_without_alerts(tmp_path: Path) -> None:
    base = make_weekly_pack(tmp_path / "a", cycle_id="w-a")
    prev = tmp_path / "b"
    make_weekly_pack(prev, cycle_id="w-b")  # identical content
    out = tmp_path / "out"
    run_delivery(current_run=base, delivery_out=out, previous_run=prev, as_of=AS_OF)
    urgent = json.loads((out / "urgent-alerts.json").read_text(encoding="utf-8"))
    assert urgent["count"] == 0
    assert (out / "weekly-report.md").is_file()
    assert (out / "monthly-report.md").is_file()
    assert (out / "meeting-support.md").is_file()


def test_alert_does_not_remove_report(tmp_path: Path) -> None:
    prev = make_weekly_pack(tmp_path / "prev", cycle_id="w-prev")
    health = [
        {
            "source": "pncp_opportunities",
            "level": "stale",
            "sla_hours": "24",
            "age_hours": "99",
        }
    ]
    cur = make_weekly_pack(
        tmp_path / "cur", cycle_id="w-cur", source_health=health
    )
    out = tmp_path / "out"
    run_delivery(current_run=cur, delivery_out=out, previous_run=prev, as_of=AS_OF)
    assert json.loads((out / "urgent-alerts.json").read_text())["count"] >= 1
    for name in ("weekly-report.md", "monthly-report.md", "meeting-support.md"):
        assert (out / name).is_file()
        assert len((out / name).read_text(encoding="utf-8")) > 50


def test_idempotency(tmp_path: Path) -> None:
    prev = make_weekly_pack(tmp_path / "prev", cycle_id="w-prev")
    opps = [
        {
            "id": "1",
            "numero_controle_pncp": "11111111000111-1-000001/2026",
            "source_id": "11111111000111-1-000001/2026",
            "orgao_nome": "Pref. Alpha",
            "objeto": "Reforma",
            "status_canonico": "open",
            "data_encerramento": "2026-08-20",
            "link_edital": "https://pncp.gov.br/app/editais/11111111000111/2026/1",
        },
        {
            "id": "2",
            "numero_controle_pncp": "11111111000111-1-000002/2026",
            "source_id": "11111111000111-1-000002/2026",
            "orgao_nome": "Pref. Beta",
            "objeto": "Novo",
            "status_canonico": "open",
            "data_encerramento": "2026-09-01",
            "link_edital": "",
        },
    ]
    cur = make_weekly_pack(tmp_path / "cur", cycle_id="w-cur", opportunities=opps)
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    run_delivery(current_run=cur, delivery_out=out1, previous_run=prev, as_of=AS_OF)
    run_delivery(current_run=cur, delivery_out=out2, previous_run=prev, as_of=AS_OF)
    # product content hashes (exclude manifest generated_at)
    for name in (
        "weekly-delta.json",
        "weekly-delta.csv",
        "urgent-alerts.json",
        "monthly-comparison.json",
        "source-health.json",
        "weekly-report.md",
        "monthly-report.md",
        "meeting-support.md",
    ):
        assert _sha(out1 / name) == _sha(out2 / name), name
    ck1 = json.loads((out1 / "checksums.json").read_text())["artifacts"]
    ck2 = json.loads((out2 / "checksums.json").read_text())["artifacts"]
    # openpyxl .xlsx is not byte-stable (ZIP entry timestamps / workbook props).
    # Textual products above already prove content idempotency.
    skip_checksum = {"manifest.json", "weekly-report.xlsx"}
    for k in ck1:
        if k in skip_checksum:
            continue
        assert ck1[k]["sha256"] == ck2[k]["sha256"], k


def test_checksums_present(tmp_path: Path) -> None:
    cur = make_weekly_pack(tmp_path / "cur", cycle_id="w-cur")
    out = tmp_path / "out"
    run_delivery(current_run=cur, delivery_out=out, as_of=AS_OF)
    ck = json.loads((out / "checksums.json").read_text(encoding="utf-8"))
    assert "artifacts" in ck
    assert "weekly-report.md" in ck["artifacts"]
    assert len(ck["artifacts"]["weekly-report.md"]["sha256"]) == 64
    # verify matches disk
    actual = _sha(out / "weekly-report.md")
    assert ck["artifacts"]["weekly-report.md"]["sha256"] == actual


def test_fail_closed_missing_current(tmp_path: Path) -> None:
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as ei:
        run_delivery(
            current_run=tmp_path / "does-not-exist",
            delivery_out=out,
            as_of=AS_OF,
        )
    assert ei.value.code == 2


def test_fail_closed_invalid_structure(tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "readme.txt").write_text("not a pack", encoding="utf-8")
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as ei:
        run_delivery(current_run=bad, delivery_out=out, as_of=AS_OF)
    assert ei.value.code == 2


def test_fail_closed_cli_missing(tmp_path: Path) -> None:
    code = main(
        [
            "run",
            "--current-run",
            str(tmp_path / "missing"),
            "--delivery-out",
            str(tmp_path / "out"),
            "--as-of",
            "2026-07-29",
        ]
    )
    assert code == 2


def test_event_delta_rejects_unknown_type() -> None:
    with pytest.raises(ValueError):
        EventDelta(
            entity_type="tender",
            entity_id="x",
            event_type="NOT_ALLOWED",
            previous_value=None,
            current_value=None,
            detected_at="2026-07-29T12:00:00Z",
            source_run_id=None,
            previous_run_id=None,
            official_url=None,
            severity="low",
            action_required="n/a",
        )


def test_allowed_event_types_frozen() -> None:
    expected = {
        "NEW_TENDER",
        "DEADLINE_CHANGED",
        "STATUS_CHANGED",
        "SUSPENDED",
        "REVOKED",
        "REOPENED",
        "RECTIFIED",
        "CONTRACT_ENTERED_EXPIRY_WINDOW",
        "NEW_WINNER",
        "WINNER_CONCENTRATION_CHANGED",
        "SOURCE_DEGRADED",
        "FRESHNESS_BREACH",
    }
    assert ALLOWED_EVENT_TYPES == expected


def test_detect_all_deltas_unit(tmp_path: Path) -> None:
    prev = load_weekly_input(
        make_weekly_pack(tmp_path / "prev", cycle_id="p"), require_ok=True
    )
    opps = [
        {
            "id": "1",
            "numero_controle_pncp": "11111111000111-1-000001/2026",
            "source_id": "11111111000111-1-000001/2026",
            "orgao_nome": "Pref. Alpha",
            "objeto": "Reforma",
            "status_canonico": "open",
            "data_encerramento": "2026-08-15",
            "link_edital": "https://x",
        },
        {
            "id": "9",
            "numero_controle_pncp": "99999999000199-1-000009/2026",
            "source_id": "99999999000199-1-000009/2026",
            "orgao_nome": "Pref. New",
            "objeto": "Novo edital",
            "status_canonico": "open",
            "data_encerramento": "2026-09-01",
            "link_edital": "https://y",
        },
    ]
    cur = load_weekly_input(
        make_weekly_pack(tmp_path / "cur", cycle_id="c", opportunities=opps),
        require_ok=True,
    )
    delta = detect_all_deltas(cur, prev, as_of=AS_OF, expiry_window_days=180)
    assert delta["status"] == "OK"
    assert any(e.event_type == "NEW_TENDER" for e in delta["events"])


def test_cli_run_success(tmp_path: Path) -> None:
    cur = make_weekly_pack(tmp_path / "cur", cycle_id="w-cli")
    out = tmp_path / "out"
    code = main(
        [
            "run",
            "--current-run",
            str(cur),
            "--delivery-out",
            str(out),
            "--as-of",
            "2026-07-29",
            "--expiry-window-days",
            "180",
        ]
    )
    assert code == 0
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert man["schema"].startswith("extra-recurring-delivery")
    assert man["first_run"] is True
