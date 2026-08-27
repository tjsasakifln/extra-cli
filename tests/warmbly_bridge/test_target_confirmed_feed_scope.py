"""The published feed carries the TARGET_CONFIRMED population, one lead per root.

The full decision universe stays extra-cli's authoritative record and is still
accounted for in the manifest; only the outreach population is shipped.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.warmbly_bridge import export as export_module
from scripts.warmbly_bridge.export import (
    CONSUMER_MAX_CHUNKS,
    CONSUMER_MAX_LEADS,
    ExportConfig,
    _assert_consumer_ceilings,
    export_outreach,
)
from scripts.warmbly_bridge.io_jsonl import InputError

NOW = "2026-08-12T12:00:00Z"
BUYER = "88999000000191"


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _universe_row(cnpj: str, *, watermark: str = NOW, supplier: bool = True) -> dict[str, Any]:
    row: dict[str, Any] = {
        "cnpj14": cnpj,
        "cnpj_root": cnpj[:8],
        "razao_social": f"CONSTRUTORA {cnpj}",
        "municipio": "Florianopolis",
        "uf": "SC",
        "commercial_state": "NEW",
        "outreach_eligibility": "ELIGIBLE",
        "priority_score": 50,
        "portfolio": {"contract_count_total": 1, "value_total_brl": 100000, "ufs_atuacao": ["SC"]},
    }
    if supplier:
        row["contracts"] = [
            {
                "id": f"contract-{cnpj}",
                "supplier_cnpj14": cnpj,
                "buyer_cnpj14": BUYER,
                "supplier_role": "CONTRATADA",
                "buyer_role": "CONTRATANTE",
            }
        ]
    return row


def _decision(cnpj: str, target_class: str, *, watermark: str = NOW) -> dict[str, Any]:
    return {
        "cnpj14": cnpj,
        "target_fit_class": target_class,
        "target_fit_confidence": 0.9,
        "target_fit_version": "confenge-target-fit-v2",
        "target_fit_computed_at": watermark,
        "target_fit_source_watermark": watermark,
        "target_fit_operational_status": "ok",
        "target_fit_evidence": [{"id": f"contract-{cnpj}", "type": "CONTRACT_EXECUTION"}],
        "target_fit_reason_codes": [target_class.lower()],
    }


def _export(
    root: Path,
    decisions: list[tuple[str, str]],
    *,
    suffix: str,
    reorder: bool = False,
    supplier_cnpjs: set[str] | None = None,
    previous_feed_dir: Path | None = None,
    deactivations: list[dict[str, Any]] | None = None,
    max_leads_per_chunk: int = 50,
    watermarks: dict[str, str] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Export one feed from an explicit (cnpj, target_fit_class) decision list."""
    source = root / suffix
    source.mkdir(parents=True)
    stamps = watermarks or {}
    universe = [
        _universe_row(
            cnpj,
            watermark=stamps.get(cnpj, NOW),
            supplier=(supplier_cnpjs is None or cnpj in supplier_cnpjs),
        )
        for cnpj, _cls in decisions
    ]
    target_fit = [_decision(cnpj, target_class, watermark=stamps.get(cnpj, NOW)) for cnpj, target_class in decisions]
    contacts = [{"cnpj14": cnpj, "contacts": []} for cnpj, _cls in decisions]
    intel: list[dict[str, Any]] = []
    if reorder:
        # Deterministic non-natural permutation: reversed, odd rows first.
        for rows in (universe, target_fit, contacts):
            reordered = [*rows[1::2], *rows[0::2]][::-1]
            rows[:] = reordered
    out = source / "feed"
    result = export_outreach(
        ExportConfig(
            universe=_write_jsonl(source / "universe.jsonl", universe),
            account_intelligence=_write_jsonl(source / "intelligence.jsonl", intel),
            contacts=_write_jsonl(source / "contacts.jsonl", contacts),
            target_fit_snapshot=_write_jsonl(source / "target-fit.jsonl", target_fit),
            expected_universe_count=len(decisions),
            out_dir=out,
            generated_at=NOW,
            datalake_watermark=NOW,
            repo_sha="feed-scope-test",
            max_leads_per_chunk=max_leads_per_chunk,
            previous_feed_dir=previous_feed_dir,
            deactivations=deactivations,
        )
    )
    return out, result


def _manifest(out: Path) -> dict[str, Any]:
    return json.loads((out / "manifest.json").read_text(encoding="utf-8"))


def _shipped(out: Path) -> list[str]:
    shipped: list[str] = []
    for path in sorted(out.glob("chunk_*.json")):
        shipped.extend(lead["company"]["cnpj14"] for lead in json.loads(path.read_text(encoding="utf-8"))["leads"])
    return shipped


def _feed_identity(manifest: dict[str, Any]) -> str:
    """Consumer-visible manifest identity.

    Excludes only the operational per-chunk ``status`` (written/unchanged), which
    describes this run's disk writes rather than the feed itself.
    """
    payload = {
        **manifest,
        "chunks": [{key: value for key, value in chunk.items() if key != "status"} for chunk in manifest["chunks"]],
    }
    payload.pop("manifest_content_hash", None)
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _declared_hash(cnpj14s: list[str]) -> str:
    roots = sorted({cnpj[:8] for cnpj in cnpj14s})
    return hashlib.sha256("".join(f"{root}\n" for root in roots).encode("utf-8")).hexdigest()


def test_zero_confirmed_members_ship_no_leads(tmp_path: Path) -> None:
    out, result = _export(
        tmp_path,
        [("11222333000181", "TARGET_OUT_OF_SCOPE"), ("22333444000172", "TARGET_INSUFFICIENT_EVIDENCE")],
        suffix="empty-population",
    )

    manifest = _manifest(out)
    assert result["lead_count"] == 0
    assert _shipped(out) == []
    # The decision universe is still fully reported.
    assert result["decision_count"] == 2
    assert manifest["authoritative_target_fit"]["full_decision_count"] == 2
    assert manifest["authoritative_target_membership"]["population_count"] == 0
    assert manifest["authoritative_feed_scope"]["withheld_decision_count"] == 2


def test_single_member_feed_reproduces_the_declared_membership_hash(tmp_path: Path) -> None:
    cnpj = "11222333000181"
    out, result = _export(tmp_path, [(cnpj, "TARGET_CONFIRMED")], suffix="single")

    manifest = _manifest(out)
    membership = manifest["authoritative_target_membership"]
    shipped = _shipped(out)

    assert shipped == [cnpj]
    assert manifest["lead_count"] == 1 == membership["population_count"]
    assert membership["membership_hash"] == _declared_hash(shipped)
    assert manifest["authoritative_feed_scope"]["membership_hash_reproduced_from_feed"] is True
    assert manifest["authoritative_feed_scope"]["unique_root_count"] == 1
    assert result["authoritative_feed_scope"]["membership_hash"] == membership["membership_hash"]


def test_lead_count_equals_population_and_unique_root_count(tmp_path: Path) -> None:
    confirmed = ["11222333000181", "22333444000172", "33444555000166"]
    decisions = [(cnpj, "TARGET_CONFIRMED") for cnpj in confirmed]
    decisions += [("44555666000177", "TARGET_OUT_OF_SCOPE"), ("55666777000188", "TARGET_INSUFFICIENT_EVIDENCE")]

    out, _result = _export(tmp_path, decisions, suffix="closure", max_leads_per_chunk=2)

    manifest = _manifest(out)
    shipped = _shipped(out)
    roots = {cnpj[:8] for cnpj in shipped}

    assert sorted(shipped) == sorted(confirmed)
    assert manifest["lead_count"] == len(shipped) == len(roots)
    assert manifest["authoritative_target_membership"]["population_count"] == len(shipped)
    assert manifest["authoritative_target_membership"]["source_member_count"] == len(shipped)
    assert manifest["authoritative_target_membership"]["duplicate_member_count"] == 0
    assert manifest["authoritative_target_membership"]["membership_hash"] == _declared_hash(shipped)
    assert sum(chunk["lead_count"] for chunk in manifest["chunks"]) == manifest["lead_count"]
    assert manifest["chunk_count"] == len(manifest["chunks"])


def test_shared_root_collapses_to_one_deterministic_lead(tmp_path: Path) -> None:
    """Two establishments of one company never become two Warmbly accounts."""
    matriz = "11222333000181"
    filial = "11222333000262"
    other = "22333444000172"
    decisions = [(matriz, "TARGET_CONFIRMED"), (filial, "TARGET_CONFIRMED"), (other, "TARGET_CONFIRMED")]

    out, _result = _export(tmp_path, decisions, suffix="collapse")
    reversed_out, _reversed = _export(tmp_path, list(reversed(decisions)), suffix="collapse-reversed")

    shipped = _shipped(out)
    reversed_shipped = _shipped(reversed_out)
    manifest = _manifest(out)

    assert len(shipped) == 2
    assert len({cnpj[:8] for cnpj in shipped}) == 2
    assert shipped == reversed_shipped, "representative election must not depend on input order"
    assert manifest["lead_count"] == 2
    assert manifest["authoritative_target_membership"]["population_count"] == 2
    assert manifest["authoritative_target_membership"]["membership_hash"] == _declared_hash(shipped)
    scope = manifest["authoritative_feed_scope"]
    assert scope["branch_duplicates_collapsed"] == 1
    assert scope["target_confirmed_decision_count"] == 3
    collapsed = scope["collapsed_branch_cnpj14s"]
    assert len(collapsed) == 1
    assert collapsed[0] in {matriz, filial}
    assert collapsed[0] not in shipped


def test_supplier_confirmed_count_matches_the_shipped_leads(tmp_path: Path) -> None:
    supplier = "11222333000181"
    unknown_role = "22333444000172"
    out, _result = _export(
        tmp_path,
        [(supplier, "TARGET_CONFIRMED"), (unknown_role, "TARGET_CONFIRMED")],
        suffix="supplier-count",
        supplier_cnpjs={supplier},
    )

    manifest = _manifest(out)
    membership = manifest["authoritative_target_membership"]
    party_roles = manifest["authoritative_party_roles"]
    observed = [
        lead
        for path in sorted(out.glob("chunk_*.json"))
        for lead in json.loads(path.read_text(encoding="utf-8"))["leads"]
    ]
    shipped_suppliers = sum(1 for lead in observed if lead["contractor_role"]["target_party_role"] == "SUPPLIER")

    assert shipped_suppliers == 1
    assert membership["supplier_confirmed_count"] == 1
    assert party_roles["supplier_confirmed_count"] == 1
    assert party_roles["target_party_role_distribution"] == {"SUPPLIER": 1, "UNKNOWN": 1}
    assert membership["target_party_role_distribution"] == party_roles["target_party_role_distribution"]


def test_input_ordering_does_not_change_the_published_population(tmp_path: Path) -> None:
    """Same frozen snapshot, different input row order → same feed.

    ``snapshot_hash`` is deliberately the byte identity of the inputs, so the two
    runs carry different source identities. Everything the consumer imports —
    the lead sequence, the chunk partition, the cursors and the membership — must
    be identical.
    """
    decisions = [(f"{index:08d}000181", "TARGET_CONFIRMED") for index in range(11, 31)]
    watermarks = {cnpj: f"2026-08-12T{(index % 12) + 6:02d}:00:00Z" for index, (cnpj, _cls) in enumerate(decisions)}

    first_out, _first = _export(
        tmp_path, decisions, suffix="order-a", max_leads_per_chunk=3, watermarks=watermarks
    )
    second_out, _second = _export(
        tmp_path, decisions, suffix="order-b", reorder=True, max_leads_per_chunk=3, watermarks=watermarks
    )

    first = _manifest(first_out)
    second = _manifest(second_out)
    volatile = {"source", "inputs", "hashes", "manifest_content_hash", "chunks", "generated_at"}

    assert _shipped(first_out) == _shipped(second_out)
    assert [chunk["lead_count"] for chunk in first["chunks"]] == [chunk["lead_count"] for chunk in second["chunks"]]
    assert [chunk["cursor"] for chunk in first["chunks"]] == [chunk["cursor"] for chunk in second["chunks"]]
    assert {key: value for key, value in first.items() if key not in volatile} == {
        key: value for key, value in second.items() if key not in volatile
    }
    assert first["authoritative_target_membership"]["membership_hash"] == _declared_hash(_shipped(first_out))


def test_replaying_the_same_snapshot_rewrites_nothing(tmp_path: Path) -> None:
    decisions = [(f"{index:08d}000181", "TARGET_CONFIRMED") for index in range(11, 21)]
    out, first = _export(tmp_path, decisions, suffix="replay", max_leads_per_chunk=3)
    before = {path.name: path.read_bytes() for path in sorted(out.glob("chunk_*.json"))}
    manifest_before = _feed_identity(_manifest(out))
    roster_before = (out / "membership.json").read_bytes()

    source = tmp_path / "replay"
    second = export_outreach(
        ExportConfig(
            universe=source / "universe.jsonl",
            account_intelligence=source / "intelligence.jsonl",
            contacts=source / "contacts.jsonl",
            target_fit_snapshot=source / "target-fit.jsonl",
            expected_universe_count=len(decisions),
            out_dir=out,
            generated_at=NOW,
            datalake_watermark=NOW,
            repo_sha="feed-scope-test",
            max_leads_per_chunk=3,
        )
    )

    assert second["snapshot_hash"] == first["snapshot_hash"]
    assert second["run_id"] == first["run_id"]
    assert all(chunk["status"] == "unchanged" for chunk in second["chunks"])
    assert {path.name: path.read_bytes() for path in sorted(out.glob("chunk_*.json"))} == before
    assert _feed_identity(_manifest(out)) == manifest_before
    assert (out / "membership.json").read_bytes() == roster_before


def test_member_leaving_target_confirmed_becomes_a_deactivation(tmp_path: Path) -> None:
    stays = "11222333000181"
    out_of_scope = "22333444000172"
    tombstoned = "33444555000166"
    first_out, _first = _export(
        tmp_path,
        [(stays, "TARGET_CONFIRMED"), (out_of_scope, "TARGET_CONFIRMED"), (tombstoned, "TARGET_CONFIRMED")],
        suffix="drop-before",
    )
    assert sorted(_shipped(first_out)) == sorted([stays, out_of_scope, tombstoned])

    second_out, _second = _export(
        tmp_path,
        [
            (stays, "TARGET_CONFIRMED"),
            (out_of_scope, "TARGET_OUT_OF_SCOPE"),
            (tombstoned, "TARGET_INSUFFICIENT_EVIDENCE"),
        ],
        suffix="drop-after",
        previous_feed_dir=first_out,
    )

    manifest = _manifest(second_out)
    deactivations = {row["cnpj14"]: row for row in manifest["deactivations"]}

    assert _shipped(second_out) == [stays]
    assert set(deactivations) == {out_of_scope, tombstoned}
    assert manifest["deactivation_count"] == 2
    assert deactivations[out_of_scope]["to_state"] == "SUPPRESSED"
    assert deactivations[tombstoned]["to_state"] == "RESEARCH_REQUIRED"
    assert all(row["to_state"] != "ACTIONABLE_NOW" for row in manifest["deactivations"])
    assert all("TARGET_CONFIRMED_MEMBERSHIP_DROPPED" in row["reason_codes"] for row in manifest["deactivations"])
    assert manifest["deactivation_projection"]["membership_drop_count"] == 2
    assert manifest["authoritative_feed_scope"]["previous_membership_source"] == "MEMBERSHIP_ROSTER"
    assert manifest["authoritative_feed_scope"]["previous_membership_count"] == 3


def test_still_published_account_is_never_also_deactivated(tmp_path: Path) -> None:
    cnpj = "11222333000181"
    out, _result = _export(
        tmp_path,
        [(cnpj, "TARGET_CONFIRMED")],
        suffix="contradiction",
        deactivations=[{"cnpj14": cnpj, "to_state": "WATCH", "from_state": "ACTIONABLE_NOW"}],
    )

    manifest = _manifest(out)
    assert _shipped(out) == [cnpj]
    assert manifest["deactivations"] == []
    assert manifest["deactivation_projection"]["suppressed_because_still_published"] == 1


def test_previous_release_without_a_roster_is_recovered_from_its_chunks(tmp_path: Path) -> None:
    stays = "11222333000181"
    leaves = "22333444000172"
    first_out, _first = _export(
        tmp_path,
        [(stays, "TARGET_CONFIRMED"), (leaves, "TARGET_CONFIRMED")],
        suffix="legacy-before",
    )
    (first_out / "membership.json").unlink()

    second_out, _second = _export(
        tmp_path,
        [(stays, "TARGET_CONFIRMED"), (leaves, "TARGET_OUT_OF_SCOPE")],
        suffix="legacy-after",
        previous_feed_dir=first_out,
    )

    manifest = _manifest(second_out)
    assert manifest["authoritative_feed_scope"]["previous_membership_source"] == "PRIOR_RELEASE_CHUNKS"
    assert [row["cnpj14"] for row in manifest["deactivations"]] == [leaves]


def test_declared_previous_feed_without_a_feed_fails_closed(tmp_path: Path) -> None:
    empty = tmp_path / "empty-release"
    empty.mkdir()
    with pytest.raises(InputError, match="neither membership.json nor manifest.json"):
        _export(
            tmp_path,
            [("11222333000181", "TARGET_CONFIRMED")],
            suffix="missing-previous",
            previous_feed_dir=empty,
        )


def test_feed_above_the_consumer_chunk_ceiling_fails_closed(tmp_path: Path) -> None:
    """A feed the consumer cannot import aborts the run; it is never truncated."""
    decisions = [(f"{index:08d}000181", "TARGET_CONFIRMED") for index in range(CONSUMER_MAX_CHUNKS + 1)]
    with pytest.raises(InputError, match="exceeds the consumer chunk ceiling"):
        _export(tmp_path, decisions, suffix="over-chunks", max_leads_per_chunk=1)


def test_consumer_ceilings_never_truncate() -> None:
    _assert_consumer_ceilings(lead_count=CONSUMER_MAX_LEADS, chunk_count=CONSUMER_MAX_CHUNKS)
    with pytest.raises(InputError, match="exceeds the consumer lead ceiling"):
        _assert_consumer_ceilings(lead_count=CONSUMER_MAX_LEADS + 1, chunk_count=1)
    with pytest.raises(InputError, match="exceeds the consumer chunk ceiling"):
        _assert_consumer_ceilings(lead_count=1, chunk_count=CONSUMER_MAX_CHUNKS + 1)


def test_membership_hash_must_be_reproducible_from_the_shipped_leads(monkeypatch, tmp_path: Path) -> None:
    """A declared digest that the feed cannot reproduce aborts before any write."""
    real = export_module.canonical_target_membership

    def poisoned(cnpjs: list[Any]) -> dict[str, Any]:
        return {**real(cnpjs), "membership_hash": "0" * 64}

    monkeypatch.setattr(export_module, "canonical_target_membership", poisoned)
    with pytest.raises(InputError, match="not reproducible from the published leads"):
        _export(tmp_path, [("11222333000181", "TARGET_CONFIRMED")], suffix="poisoned")


def test_feed_path_never_reaches_transport_or_a_commercial_queue(tmp_path: Path) -> None:
    """The producer decides and publishes; it never sends or enqueues."""
    for transport in ("smtplib", "aiosmtplib", "smtpd"):
        sys.modules.pop(transport, None)
    out, _result = _export(tmp_path, [("11222333000181", "TARGET_CONFIRMED")], suffix="no-transport")

    # Producing the feed must not pull a mail transport into the process.
    assert not [name for name in sys.modules if name.split(".")[0] in {"smtplib", "aiosmtplib", "smtpd"}]
    blob = (out / "manifest.json").read_text(encoding="utf-8")
    for chunk in sorted(out.glob("chunk_*.json")):
        blob += chunk.read_text(encoding="utf-8")
    for forbidden in ("smtp", "dispatch_queue", "campaign_leads", "enrollment", "send_email"):
        assert forbidden not in blob.lower()
