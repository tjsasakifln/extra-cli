"""Adversarial tests for stratified recall fail-closed gate.

Drives the real evaluate_sample / validate_sample_schema / denominator_hash /
try_match_against_system entry points — no reimplementation of gate logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.coverage.recall_benchmark import (
    CRITICAL_STRATA,
    GLOBAL_TARGET_PCT,
    MIN_PER_STRATUM,
    MIN_UNIQUE_ITEMS,
    REQUIRED_STRATA,
    STRATUM_FLOOR_PCT,
    assert_denominator_unchanged,
    denominator_hash,
    evaluate_sample,
    freeze_sample_lock,
    main,
    try_match_against_system,
    validate_sample_schema,
)


def _item(
    sid: str,
    strata: list[str],
    *,
    captured: bool | None = True,
    evidence: str | None = "id=1",
    miss_reason: str | None = None,
    url: str = "https://pncp.gov.br/app/editais/x",
    external_id: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "sample_id": sid,
        "strata": strata,
        "portal_url": url,
        "external_id": external_id or sid,
        "source_platform": "pncp",
        "captured_by_system": captured,
        "capture_evidence": evidence if captured else None,
    }
    if captured is False:
        row["miss_reason"] = miss_reason
        row["capture_evidence"] = None
    return row


def _full_strata_cycle() -> list[list[str]]:
    """Produce distinct stratum sets so each required stratum appears often."""
    # Each item carries a small genuine subset; we need many items for min counts.
    base_platforms = [
        ["platform_pncp", "source_api"],
        ["platform_sc_compras", "source_js"],
        ["platform_ciga", "source_pdf", "source_html"],
    ]
    natures = [
        ["municipio_grande", "admin_direta"],
        ["municipio_medio", "admin_direta"],
        ["municipio_pequeno", "admin_direta"],
        ["admin_indireta", "autarquia"],
        ["admin_indireta", "fundacao"],
        ["camara", "admin_direta"],
        ["consorcio", "admin_indireta"],
    ]
    combos: list[list[str]] = []
    for i in range(max(MIN_UNIQUE_ITEMS + 5, 60)):
        combos.append(sorted(set(base_platforms[i % 3] + natures[i % len(natures)])))
    return combos


def _ready_sample(
    *,
    n: int | None = None,
    capture_rate: float = 1.0,
    evidence: bool = True,
    miss_reason: str = "source_gap",
) -> dict[str, Any]:
    n = n or max(MIN_UNIQUE_ITEMS, 60)
    combos = _full_strata_cycle()
    items = []
    for i in range(n):
        captured = i < int(n * capture_rate)
        items.append(
            _item(
                f"REAL-{i:03d}",
                combos[i % len(combos)],
                captured=captured,
                evidence=f"opp.id={i}" if (captured and evidence) else (None if captured else None),
                miss_reason=None if captured else miss_reason,
            )
        )
    return {
        "schema_version": 2,
        "window": {"start": "2026-07-01", "end": "2026-07-22"},
        "methodology": {
            "required_strata": REQUIRED_STRATA,
            "selected_before_match": True,
            "forbidden": "Do not use COUNT(*) from database as recall proxy",
        },
        "independence": {"selected_before_match": True, "denies_operational_table_denominator": True},
        "portal_items": items,
        "forbidden_proxy_used": False,
        "denominator_source": "independent_official_portals",
    }


def test_scaffold_example_is_not_ready() -> None:
    result = evaluate_sample(
        {
            "portal_items": [
                {
                    "sample_id": "EXAMPLE-001",
                    "strata": REQUIRED_STRATA,
                    "captured_by_system": True,
                    "capture_evidence": "x",
                }
            ]
        }
    )
    assert result["status"] == "NOT_READY"
    assert result["gate_exit"] != 0
    assert result["pct"] is None


def test_unlabeled_items_do_not_disappear_from_denominator() -> None:
    sample = _ready_sample(capture_rate=1.0)
    sample["portal_items"][0]["captured_by_system"] = None
    sample["portal_items"][0]["capture_evidence"] = None
    result = evaluate_sample(sample)
    assert result["status"] == "PARTIAL"
    assert result["published_in_sample"] == len(sample["portal_items"])
    assert result["pct"] is None
    assert result["gate_exit"] != 0


def test_capture_requires_evidence() -> None:
    sample = _ready_sample()
    sample["portal_items"][0]["capture_evidence"] = None
    result = evaluate_sample(sample)
    assert result["status"] == "PARTIAL"
    assert "captured_without_evidence" in result["notes"]
    assert result["gate_exit"] != 0


def test_miss_requires_classified_reason() -> None:
    sample = _ready_sample(capture_rate=0.9)
    # force one miss without reason
    for it in sample["portal_items"]:
        if it.get("captured_by_system") is False:
            it.pop("miss_reason", None)
            break
    result = evaluate_sample(sample)
    assert result["status"] == "PARTIAL"
    assert "misses_without_reason" in result["notes"]
    assert result["gate_exit"] != 0


def test_single_row_multi_stratum_cannot_satisfy_min_per_stratum() -> None:
    """One artificial line tagged with all strata still fails min-5 coverage."""
    sample = {
        "window": {"start": "2026-07-01", "end": "2026-07-02"},
        "portal_items": [
            _item("REAL-ALL", list(REQUIRED_STRATA), captured=True, evidence="x"),
        ]
        + [
            _item(f"REAL-FILL-{i}", ["platform_pncp", "source_api", "municipio_medio", "admin_direta"])
            for i in range(MIN_UNIQUE_ITEMS)
        ],
        "forbidden_proxy_used": False,
        "methodology": {"selected_before_match": True},
        "independence": {"selected_before_match": True},
    }
    result = evaluate_sample(sample)
    assert result["status"] in {"PARTIAL", "NOT_READY"}
    assert result["gate_exit"] != 0
    assert any("thin_strata" in result["notes"] or "missing_strata" in result["notes"] for _ in [1])


def test_insufficient_sample_size_fails_closed() -> None:
    combos = _full_strata_cycle()
    items = [
        _item(f"REAL-{i}", combos[i], captured=True, evidence=f"e{i}") for i in range(10)
    ]
    result = evaluate_sample(
        {
            "window": {"start": "2026-07-01", "end": "2026-07-02"},
            "portal_items": items,
            "methodology": {"selected_before_match": True},
            "independence": {"selected_before_match": True},
        }
    )
    assert result["status"] == "PARTIAL"
    assert result["published_in_sample"] == 10
    assert result["gate_exit"] != 0


def test_global_recall_below_95_is_fail_not_partial() -> None:
    # 90% capture on ready sample → FAIL (structural ok, metric miss)
    sample = _ready_sample(capture_rate=0.90)
    result = evaluate_sample(sample)
    # Ensure structural readiness first
    assert result["validation"]["unlabeled"] == 0
    assert result["validation"]["missing_strata"] == []
    assert result["status"] == "FAIL"
    assert result["pct"] is not None
    assert result["pct"] < GLOBAL_TARGET_PCT
    assert result["gate_exit"] == 1


def test_stratum_floor_blocks_pass_even_if_global_high() -> None:
    sample = _ready_sample(capture_rate=1.0)
    # Poison one critical stratum: mark all items that carry camara as miss
    for it in sample["portal_items"]:
        if "camara" in (it.get("strata") or []):
            it["captured_by_system"] = False
            it["capture_evidence"] = None
            it["miss_reason"] = "source_gap"
    result = evaluate_sample(sample)
    # Global may still be high; camara floor should fail
    assert result["status"] == "FAIL"
    assert result["gate_exit"] != 0
    assert result["floors_failed"]


def test_denominator_hash_stable_after_miss_label_change() -> None:
    sample = _ready_sample(capture_rate=1.0)
    h1 = denominator_hash(sample)
    lock = freeze_sample_lock(sample)
    # Simulate miss labeling — must not change denominator identity
    sample["portal_items"][0]["captured_by_system"] = False
    sample["portal_items"][0]["capture_evidence"] = None
    sample["portal_items"][0]["miss_reason"] = "match_gap"
    h2 = denominator_hash(sample)
    assert h1 == h2
    assert_denominator_unchanged(sample, lock)


def test_denominator_shrink_after_miss_is_detected() -> None:
    sample = _ready_sample()
    lock = freeze_sample_lock(sample)
    # Illegal: remove a miss from denominator
    sample["portal_items"] = sample["portal_items"][1:]
    with pytest.raises(RuntimeError, match="denominator hash drift"):
        assert_denominator_unchanged(sample, lock)


def test_db_count_proxy_flag_rejected() -> None:
    sample = _ready_sample()
    sample["forbidden_proxy_used"] = True
    result = evaluate_sample(sample)
    assert result["status"] in {"PARTIAL", "FAIL", "NOT_READY"}
    assert result["gate_exit"] != 0


def test_operational_denominator_source_rejected_by_schema() -> None:
    sample = _ready_sample()
    sample["denominator_source"] = "COUNT(*) FROM opportunity_intel"
    val = validate_sample_schema(sample)
    assert val["ok"] is False
    assert any("denominator_source" in e for e in val["errors"])


def test_pass_path_requires_full_floors() -> None:
    sample = _ready_sample(capture_rate=1.0)
    result = evaluate_sample(sample)
    assert result["status"] == "PASS"
    assert result["pct"] == 100.0
    assert result["gate_exit"] == 0
    assert result["forbidden_proxy_used"] is False
    for s in CRITICAL_STRATA:
        assert result["stratum_pct"].get(s) is not None
        assert result["stratum_pct"][s] >= STRATUM_FLOOR_PCT


def test_cli_evaluate_exits_nonzero_on_partial(tmp_path: Path) -> None:
    sample = {
        "portal_items": [
            {
                "sample_id": "EXAMPLE-001",
                "strata": ["platform_pncp"],
                "portal_url": "https://example.invalid/1",
            }
        ]
    }
    sample_path = tmp_path / "sample.json"
    out_path = tmp_path / "out.json"
    sample_path.write_text(json.dumps(sample), encoding="utf-8")
    rc = main(["evaluate", "--sample", str(sample_path), "-o", str(out_path)])
    assert rc != 0
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["status"] == "NOT_READY"


def test_cli_gate_exits_nonzero_on_fail(tmp_path: Path) -> None:
    sample = _ready_sample(capture_rate=0.5)
    sample_path = tmp_path / "sample.json"
    out_path = tmp_path / "out.json"
    sample_path.write_text(json.dumps(sample), encoding="utf-8")
    rc = main(["gate", "--sample", str(sample_path), "-o", str(out_path)])
    assert rc != 0
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["status"] in {"FAIL", "PARTIAL"}


def test_auto_match_fail_closed_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = _ready_sample(n=MIN_UNIQUE_ITEMS)
    for it in sample["portal_items"]:
        it["captured_by_system"] = None
        it["capture_evidence"] = None
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("RECALL_ISOLATED_DSN", raising=False)
    with pytest.raises(RuntimeError, match="DSN required"):
        try_match_against_system(sample, dsn=None, fail_closed=True)


def test_auto_match_fail_closed_on_connection_error() -> None:
    from unittest.mock import patch

    sample = {
        "portal_items": [
            {
                "sample_id": "REAL-1",
                "strata": ["platform_pncp"],
                "portal_url": "https://pncp.gov.br/app/editais/x",
                "external_id": "x",
                "captured_by_system": None,
            }
        ]
    }
    # Force connect failure (conftest autouse mocks psycopg2.connect otherwise).
    with patch("psycopg2.connect", side_effect=OSError("connection refused")):
        with pytest.raises(RuntimeError, match="fail-closed"):
            try_match_against_system(
                sample,
                dsn="postgresql://test:test@127.0.0.1:59999/does_not_exist",
                fail_closed=True,
            )


def test_duplicate_sample_ids_rejected() -> None:
    sample = _ready_sample()
    sample["portal_items"][1]["sample_id"] = sample["portal_items"][0]["sample_id"]
    val = validate_sample_schema(sample)
    assert val["ok"] is False
    assert any("duplicate_sample_id" in e for e in val["errors"])


def test_min_per_stratum_constant_is_at_least_5() -> None:
    assert MIN_PER_STRATUM >= 5
    assert MIN_UNIQUE_ITEMS >= 50
    assert GLOBAL_TARGET_PCT >= 95.0
    assert STRATUM_FLOOR_PCT >= 90.0
