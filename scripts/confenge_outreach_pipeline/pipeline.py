"""End-to-end CONFENGE outreach pipeline (no manual JSON between stages)."""

from __future__ import annotations

import json
import resource
import subprocess
import time
import traceback
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from datetime import time as datetime_time
from pathlib import Path
from typing import Any

from scripts.confenge_account_intelligence.pipeline import process_batch
from scripts.confenge_activation.checkpoint import (
    load_checkpoint,
    new_checkpoint,
    save_checkpoint,
)
from scripts.confenge_activation.commercial_authority_v2 import POLICY_VERSION as COMMERCIAL_POLICY_V2
from scripts.confenge_activation.commercial_authority_v2 import RootQualification
from scripts.confenge_activation.funnel import (
    DOWNSTREAM_EXPORTED,
    DOWNSTREAM_NO_CONTACT,
    load_commercial_memory_jsonl,
    mark_downstream,
)
from scripts.confenge_activation.metrics import (
    build_run_manifest,
    build_universe_summary,
)
from scripts.confenge_activation.planner import run_activation_cycle
from scripts.confenge_activation.policy import load_policy
from scripts.confenge_activation.rebuild_commercial_qualification import iter_qualifications, write_corpus
from scripts.confenge_activation.store import (
    load_projections_jsonl,
    write_hot_set_jsonl,
    write_projections_jsonl,
)
from scripts.confenge_contact_resolution.cache import ResolutionCache
from scripts.confenge_contact_resolution.export import write_resolution_artifacts
from scripts.confenge_contact_resolution.models import ServiceContext
from scripts.confenge_contact_resolution.resolver import (
    ContactResolver,
    ResolverConfig,
    default_adapters,
)
from scripts.confenge_outreach_pipeline import MODULE_VERSION, PIPELINE_ID
from scripts.confenge_outreach_pipeline.adapt import (
    contact_resolution_to_bridge_row,
    intelligence_dossier_to_bridge_row,
    universe_row_for_bridge,
    universe_row_to_intelligence_input,
)
from scripts.confenge_outreach_pipeline.sample import sample_profile_counts, select_diverse_sample
from scripts.confenge_target_fit.company_key import canonical_cnpj14
from scripts.confenge_target_fit.published import load_published_index
from scripts.confenge_target_fit.store import get_control, queue_counts
from scripts.confenge_universe import (
    DEFAULT_EXCLUSIONS_JSONL_NAME,
    DEFAULT_JSONL_NAME,
    DEFAULT_MANIFEST_NAME,
)
from scripts.confenge_universe.pipeline import run_universe_build
from scripts.crawl.run_evidence import runtime_release_sha
from scripts.decision_unit_intelligence import POLICY_VERSION as CONTACT_DISCOVERY_POLICY_VERSION
from scripts.decision_unit_intelligence.controlled_email import dedupe_feed_contacts_by_mailbox
from scripts.warmbly_bridge.export import ExportConfig, export_outreach


def _digits_cnpj(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:14]


def contact_job_meta(sample_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Pass razão/fantasia/website into discovery so domain probe is not name-blind."""
    meta: dict[str, dict[str, Any]] = {}
    for row in sample_rows:
        cnpj = _digits_cnpj(row.get("cnpj14") or row.get("cnpj"))
        if len(cnpj) != 14:
            continue
        meta[cnpj] = {
            "razao_social": row.get("razao_social") or row.get("legal_name"),
            "company_name": row.get("razao_social") or row.get("legal_name"),
            "nome_fantasia": row.get("nome_fantasia") or row.get("trade_name"),
            "website": row.get("website") or row.get("site"),
        }
    return meta


def build_pipeline_contact_resolver(
    cfg: PipelineConfig,
    *,
    sample_rows: list[dict[str, Any]],
    cache: ResolutionCache | None,
    service_context: str,
) -> ContactResolver:
    """Wire the shipped DiscoveryCascade on live network runs. No SMTP."""
    enable_web = bool(cfg.enable_web_search) or bool(cfg.allow_network)
    fixtures = cfg.contact_fixtures_dir or cfg.fixtures_dir
    web_provider = None
    discovery_cascade = None
    if cfg.allow_network and not fixtures:
        from scripts.confenge_contact_resolution.discovery import (
            DiscoveryBudget,
            DiscoveryCascade,
            build_web_search_provider,
        )

        web_provider = build_web_search_provider()
        discovery_cascade = DiscoveryCascade(
            budget=DiscoveryBudget.from_env_or_defaults(),
            web_provider=web_provider,
            dsn=cfg.dsn,
            allow_network=True,
        )
    adapters = default_adapters(
        web_search_enabled=enable_web,
        web_search_provider=web_provider,
        registry_prefer_network=bool(cfg.allow_network),
    )
    return ContactResolver(
        ResolverConfig(
            service_context=service_context,
            adapters=adapters,
            cache=cache,
            allow_network=cfg.allow_network,
            fixtures_dir=fixtures,
            max_workers=cfg.max_workers,
            discovery_cascade=discovery_cascade,
            job_meta=contact_job_meta(sample_rows),
        )
    )


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    import shutil

    if release_sha := runtime_release_sha():
        return release_sha
    git_bin = shutil.which("git")
    if not git_bin:
        return "unknown"
    try:
        out = subprocess.check_output(  # noqa: S603 — absolute git path, fixed argv
            [git_bin, "-C", str(Path(__file__).resolve().parents[2]), "rev-parse", "--short=12", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip() or "unknown"
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return "unknown"


def _peak_rss_mb() -> float | None:
    try:
        # ru_maxrss is KB on Linux, bytes on macOS — treat Linux (this CI) as KB.
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return round(usage.ru_maxrss / 1024.0, 2)
    except Exception:  # noqa: BLE001
        return None


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return {"path": str(path), "lines": len(rows)}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        rows.append(json.loads(text))
    return rows


def _dedupe_decision_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Return one deterministic authoritative decision row per canonical CNPJ."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicate_count = 0
    for row in rows:
        cnpj = canonical_cnpj14(row.get("cnpj14") or row.get("cnpj"))
        if not cnpj:
            continue
        if cnpj in seen:
            duplicate_count += 1
            continue
        seen.add(cnpj)
        out.append({**row, "cnpj14": cnpj})
    return out, duplicate_count


def _load_target_confirmed_identity_rows(dsn: str) -> list[dict[str, Any]]:
    """Load the canonical establishment selected for every confirmed root.

    Target fit and the continuous contact waterfall are root-scoped, while the
    broad contract universe is establishment-scoped. The waterfall already
    resolves that boundary through ``representative_cnpj14``. Reuse the same
    identity here so a route discovered for the representative establishment
    cannot be stranded on a different branch in the feed.
    """
    from scripts.confenge_contact_resolution.continuous_from_target_fit import (
        load_construction_jobs_from_dsn,
    )

    jobs = load_construction_jobs_from_dsn(dsn, target_confirmed_only=True)
    rows: list[dict[str, Any]] = []
    invalid_identity_count = 0
    for job in jobs:
        cnpj = canonical_cnpj14(job.cnpj14)
        if not cnpj:
            invalid_identity_count += 1
            continue
        meta = job.meta if isinstance(job.meta, dict) else {}
        root = str(meta.get("cnpj_raiz") or cnpj[:8]).strip()
        rows.append(
            {
                "cnpj14": cnpj,
                "cnpj_root": root,
                "cnpj_raiz": root,
                "company_key": meta.get("company_key") or f"cnpj_root:{root}",
                "razao_social": job.razao_social or meta.get("razao_social"),
                "nome_fantasia": meta.get("nome_fantasia"),
                "target_fit_class": "TARGET_CONFIRMED",
                "target_fit_confidence": meta.get("target_fit_confidence"),
                "target_fit_version": meta.get("target_fit_version"),
                "target_fit_computed_at": meta.get("target_fit_computed_at"),
                "target_fit_source_watermark": meta.get("target_fit_source_watermark"),
                "source_lead_id": f"target-fit:{root}:{cnpj}",
                "target_fit_identity_source": "confenge_company_sector_current.representative_cnpj14",
            }
        )
    if invalid_identity_count:
        raise ValueError(
            f"TARGET_CONFIRMED account is missing an observed representative CNPJ14; count={invalid_identity_count}"
        )
    return rows


def _rebuild_durable_commercial_authority(
    dsn: str,
    *,
    as_of: date,
    out_dir: Path,
) -> tuple[list[RootQualification], dict[str, Any], Path]:
    """Rebuild authority from the canonical datalake view, never target-fit."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    now = datetime.combine(as_of, datetime_time.min, tzinfo=UTC)
    authority_dir = out_dir / "00_commercial_authority"
    authority_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = authority_dir / "commercial-qualification.jsonl"
    summary_path = authority_dir / "commercial-qualification-summary.json"
    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    conn.set_session(readonly=True, autocommit=True)
    try:
        roots = list(iter_qualifications(conn, now=now))
        with corpus_path.open("w", encoding="utf-8") as handle:
            summary = write_corpus(conn, handle, now=now, qualifications=roots)
    finally:
        conn.close()
    if not roots:
        raise ValueError("COMMERCIAL_AUTHORITY/2.0 produced no qualified roots; refusing publication")
    if [root.as_dict() for root in roots] != _read_jsonl(corpus_path):
        raise ValueError("commercial qualification corpus is not deterministic across identical datalake reads")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return roots, summary, corpus_path


def _commercial_authority_snapshot(
    decision_rows: list[dict[str, Any]],
    qualifications: list[RootQualification],
    *,
    observed_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Project durable qualifications onto the legacy target-fit wire shape."""
    identities: list[dict[str, Any]] = []
    by_root: dict[str, RootQualification] = {}
    for q in qualifications:
        if q.cnpj_root8 in by_root:
            raise ValueError(f"commercial authority repeats root {q.cnpj_root8}")
        if len(q.supplier_cnpj14) != 14 or q.supplier_cnpj14[:8] != q.cnpj_root8:
            raise ValueError(f"commercial authority lacks an exact supplier CNPJ14 for root {q.cnpj_root8}")
        by_root[q.cnpj_root8] = q
        identities.append(
            {
                "cnpj14": q.supplier_cnpj14,
                "cnpj_root": q.cnpj_root8,
                "cnpj_raiz": q.cnpj_root8,
                "company_key": f"cnpj_root:{q.cnpj_root8}",
                "target_fit_class": "TARGET_CONFIRMED",
                "target_fit_version": COMMERCIAL_POLICY_V2,
                "target_fit_computed_at": observed_at,
                "target_fit_source_watermark": observed_at,
                "source_lead_id": f"commercial-authority:{q.cnpj_root8}:{q.supplier_cnpj14}",
                "commercial_qualification": q.as_dict(),
            }
        )
    reconciled, metrics = _reconcile_target_confirmed_decision_rows(decision_rows, identities)
    snapshots = [
        {
            **identity,
            "target_fit_confidence": 1.0,
            "target_fit_evidence": [{"id": by_root[identity["cnpj_root"]].qualifying_contract_id}],
            "target_fit_reason_codes": ["COMMERCIAL_QUALIFIED", "DATALAKE_DURABLE_AUTHORITY"],
            "computed_at": observed_at,
            "source_watermark": observed_at,
            "operational_status": "ok",
        }
        for identity in identities
    ]
    return reconciled, snapshots, metrics


def _reconcile_target_confirmed_decision_rows(
    decision_rows: list[dict[str, Any]],
    target_identity_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Emit exactly one feed account per confirmed company root.

    A root can occur under multiple establishments in the contract universe,
    and the contact waterfall may select a representative establishment that
    is absent from that universe. Keep the richest same-root universe row for
    commercial context, replace its identity with the waterfall's canonical
    representative, collapse branch duplicates, and append roots not present
    in the contract universe. No target-fit class is inferred here: callers
    supply identities selected from the authoritative TARGET_CONFIRMED store.
    """

    target_by_root: dict[str, dict[str, Any]] = {}
    for raw in target_identity_rows:
        cnpj = canonical_cnpj14(raw.get("cnpj14") or raw.get("cnpj"))
        root = str(raw.get("cnpj_root") or raw.get("cnpj_raiz") or (cnpj or "")[:8]).strip()
        if not cnpj or len(root) != 8 or not root.isdigit() or cnpj[:8] != root:
            raise ValueError("TARGET_CONFIRMED identity reconciliation received an invalid canonical identity")
        prior = target_by_root.get(root)
        if prior is not None and prior["cnpj14"] != cnpj:
            raise ValueError("TARGET_CONFIRMED identity reconciliation found multiple representatives for one root")
        target_by_root[root] = {**raw, "cnpj14": cnpj, "cnpj_root": root, "cnpj_raiz": root}

    base_target_rows: dict[str, list[dict[str, Any]]] = {root: [] for root in target_by_root}
    non_target_rows: list[dict[str, Any]] = []
    for row in decision_rows:
        cnpj = canonical_cnpj14(row.get("cnpj14") or row.get("cnpj"))
        if cnpj and cnpj[:8] in target_by_root:
            base_target_rows[cnpj[:8]].append(row)
        else:
            non_target_rows.append(row)

    def _context_rank(row: dict[str, Any], representative: str) -> tuple[int, int, float, int, str]:
        portfolio = row.get("portfolio") if isinstance(row.get("portfolio"), dict) else {}
        try:
            priority = float(row.get("priority_score") or 0.0)
        except (TypeError, ValueError):
            priority = 0.0
        contract_count = int(portfolio.get("contract_count_total") or len(portfolio.get("recent_contracts") or []))
        cnpj = canonical_cnpj14(row.get("cnpj14") or row.get("cnpj")) or ""
        has_name = int(bool(str(row.get("razao_social") or row.get("legal_name") or "").strip()))
        return has_name, contract_count, priority, int(cnpj == representative), cnpj

    reconciled_targets: list[dict[str, Any]] = []
    roots_present_in_base = 0
    canonical_replacements = 0
    for root in sorted(target_by_root):
        identity = target_by_root[root]
        representative = str(identity["cnpj14"])
        candidates = base_target_rows[root]
        context = max(candidates, key=lambda row: _context_rank(row, representative)) if candidates else {}
        if candidates:
            roots_present_in_base += 1
            if not any(canonical_cnpj14(row.get("cnpj14") or row.get("cnpj")) == representative for row in candidates):
                canonical_replacements += 1

        merged = {**context}
        for key, value in identity.items():
            if value is not None and value != "":
                merged[key] = value
        merged["cnpj14"] = representative
        merged["cnpj_root"] = root
        merged["cnpj_raiz"] = root
        merged["source_lead_id"] = identity.get("source_lead_id") or f"target-fit:{root}:{representative}"
        merged["target_fit_class"] = "TARGET_CONFIRMED"
        reconciled_targets.append(merged)

    reconciled = [*non_target_rows, *reconciled_targets]
    output_target_roots = {
        cnpj[:8]
        for row in reconciled
        for cnpj in (canonical_cnpj14(row.get("cnpj14") or row.get("cnpj")),)
        if cnpj and cnpj[:8] in target_by_root
    }
    if output_target_roots != set(target_by_root):
        raise ValueError("TARGET_CONFIRMED identity reconciliation omitted an authoritative root")

    base_target_count = sum(len(rows) for rows in base_target_rows.values())
    return reconciled, {
        "authoritative_target_roots": len(target_by_root),
        "base_target_establishments": base_target_count,
        "base_target_roots": roots_present_in_base,
        "target_roots_added": len(target_by_root) - roots_present_in_base,
        "branch_duplicates_collapsed": base_target_count - roots_present_in_base,
        "canonical_establishments_replaced": canonical_replacements,
        "target_roots_emitted": len(output_target_roots),
        "target_rows_missing_legal_name": sum(
            not bool(str(row.get("razao_social") or row.get("legal_name") or "").strip()) for row in reconciled_targets
        ),
        "output_decision_rows": len(reconciled),
    }


def _select_intelligence_rows(
    *,
    decision_rows: list[dict[str, Any]],
    downstream_rows: list[dict[str, Any]],
    target_fit_snapshot_rows: list[dict[str, Any]],
    include_all_target_confirmed: bool,
) -> tuple[list[dict[str, Any]], dict[str, int | str]]:
    """Select account-intelligence scope without using activation as a hard gate.

    The activation hot set continues to bound contact/network work and preserve
    its canary role. Account intelligence is local and deterministic, so a
    production activation run also covers every account in the authoritative
    ``TARGET_CONFIRMED`` snapshot.
    """
    target_cnpjs = {
        cnpj
        for row in target_fit_snapshot_rows
        if str(row.get("target_fit_class") or "").upper() == "TARGET_CONFIRMED"
        for cnpj in (canonical_cnpj14(row.get("cnpj14") or row.get("cnpj")),)
        if cnpj
    }
    selected: list[dict[str, Any]] = []
    selected_cnpjs: set[str] = set()

    def _append(row: dict[str, Any]) -> None:
        cnpj = canonical_cnpj14(row.get("cnpj14") or row.get("cnpj"))
        if not cnpj or cnpj in selected_cnpjs:
            return
        selected.append(row)
        selected_cnpjs.add(cnpj)

    for row in downstream_rows:
        _append(row)
    if include_all_target_confirmed:
        for row in decision_rows:
            cnpj = canonical_cnpj14(row.get("cnpj14") or row.get("cnpj"))
            if cnpj in target_cnpjs:
                _append(row)

    downstream_cnpjs = {
        cnpj for row in downstream_rows for cnpj in (canonical_cnpj14(row.get("cnpj14") or row.get("cnpj")),) if cnpj
    }
    covered_targets = len(target_cnpjs & selected_cnpjs)
    return selected, {
        "scope": (
            "target_confirmed_plus_activation_hot_set" if include_all_target_confirmed else "downstream_sample_only"
        ),
        "target_confirmed_total": len(target_cnpjs),
        "target_confirmed_processed": covered_targets,
        "target_confirmed_missing": len(target_cnpjs) - covered_targets,
        "activation_or_sample_count": len(downstream_cnpjs),
        "selected_count": len(selected),
    }


def merge_contact_rows(
    durable_rows: list[dict[str, Any]],
    current_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Merge durable waterfall contacts with this run's hot-set corroboration."""
    durable_policies = {
        str(row.get("contact_discovery_policy_version"))
        for row in durable_rows
        if row.get("contact_discovery_policy_version")
    }
    durable_inputs = {
        str(row.get("contact_discovery_input_evidence_version"))
        for row in durable_rows
        if row.get("contact_discovery_input_evidence_version")
    }
    if len(durable_policies) > 1 or len(durable_inputs) > 1:
        raise ValueError(
            "durable contact projection mixes discovery policy/input versions; "
            f"policies={sorted(durable_policies)} inputs={sorted(durable_inputs)}"
        )
    if durable_policies and durable_policies != {CONTACT_DISCOVERY_POLICY_VERSION}:
        raise ValueError(
            "durable contact projection policy differs from runtime; "
            f"expected={CONTACT_DISCOVERY_POLICY_VERSION} observed={sorted(durable_policies)}"
        )
    by_cnpj: dict[str, dict[str, Any]] = {}
    durable_accounts: set[str] = set()
    current_accounts: set[str] = set()
    for source_name, rows in (("durable", durable_rows), ("current", current_rows)):
        for row in rows:
            cnpj = canonical_cnpj14(row.get("cnpj14") or row.get("cnpj"))
            if not cnpj:
                continue
            if source_name == "durable":
                durable_accounts.add(cnpj)
            else:
                current_accounts.add(cnpj)
            existing = by_cnpj.get(cnpj, {"cnpj14": cnpj, "contacts": []})
            # Durable discovery is the persistent base. Same-run resolution adds
            # corroboration and newly observed alternatives; ranking is redone at
            # the bridge boundary over the union.
            combined = [*(existing.get("contacts") or []), *(row.get("contacts") or [])]
            merged = {**row, **existing, "cnpj14": cnpj}
            merged["contacts"] = dedupe_feed_contacts_by_mailbox(combined)
            merged["contact_projection_sources"] = sorted(
                set(existing.get("contact_projection_sources") or []) | {source_name}
            )
            if not merged.get("official_domain") and row.get("official_domain"):
                merged["official_domain"] = row["official_domain"]
            by_cnpj[cnpj] = merged
    merged_rows = [by_cnpj[cnpj] for cnpj in sorted(by_cnpj)]
    return merged_rows, {
        "durable_accounts": len(durable_accounts),
        "current_accounts": len(current_accounts),
        "merged_accounts": len(merged_rows),
        "accounts_in_both": len(durable_accounts & current_accounts),
        "accounts_with_contacts": sum(bool(row.get("contacts")) for row in merged_rows),
    }


def _published_target_fit_snapshot(
    rows: list[dict[str, Any]],
    *,
    dsn: str | None,
    authoritative_source_freshness: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], str, str | None]:
    """Resolve production decisions from the mode-aware published store.

    Offline fixtures retain embedded decisions. With a production DSN, store
    misses stay omitted here so the exporter emits explicit missing tombstones.
    A published row without a source watermark is not an authoritative decision
    and is omitted the same way: the authoritative export fails closed on the
    first incomplete lead, so admitting one would abort the whole run instead of
    tombstoning one account.
    """
    if not dsn:
        return list(rows), "universe_embedded_snapshot", None

    from scripts.confenge_target_fit.db import connect

    raw_cnpjs = [str(row.get("cnpj14") or row.get("cnpj") or "") for row in rows]
    lookup_cnpjs = sorted({cnpj for raw in raw_cnpjs for cnpj in (raw, canonical_cnpj14(raw)) if cnpj})
    source_observed_at = str((authoritative_source_freshness or {}).get("source_observed_at") or "").strip()
    if authoritative_source_freshness is not None:
        if authoritative_source_freshness.get("status") != "FRESH":
            raise ValueError("target-fit observation requires a FRESH authoritative PNCP source")
        if not source_observed_at:
            raise ValueError("FRESH authoritative PNCP source is missing source_observed_at")
        try:
            observed_dt = datetime.fromisoformat(source_observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("authoritative PNCP source_observed_at is invalid") from exc
        if observed_dt.tzinfo is None:
            raise ValueError("authoritative PNCP source_observed_at must be timezone-aware")

    conn = connect(dsn, readonly=True)
    try:
        published = load_published_index(conn, cnpj14s=lookup_cnpjs)
        control = get_control(conn, "cdc_watermark")
        datalake_watermark = str(control.get("watermark") or "").strip() or None
        if source_observed_at:
            coverage = get_control(conn, "target_fit_coverage")
            last_full = str(coverage.get("last_full_reconcile_completed_at") or "").strip()
            try:
                last_full_dt = datetime.fromisoformat(last_full.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("target-fit full-reconcile observation is missing or invalid") from exc
            if last_full_dt.tzinfo is None or last_full_dt < observed_dt:
                raise ValueError("target-fit full reconcile must complete after the authoritative PNCP observation")
            if (
                float(coverage.get("coverage_ratio") or 0.0) < 1.0
                or int(coverage.get("last_full_reconcile_unexplained_missing") or 0) != 0
                or not bool(coverage.get("pagination_exhausted_normally"))
            ):
                raise ValueError("target-fit national coverage is incomplete for source re-observation")
            queue = queue_counts(conn)
            unresolved = sum(int(queue.get(status) or 0) for status in ("pending", "processing", "retry", "dead"))
            if unresolved:
                raise ValueError(f"target-fit source re-observation has {unresolved} unresolved queue items")
            # This is the observation watermark for the fully reconciled target-fit
            # snapshot.  The evidence-change watermark remains on each decision.
            datalake_watermark = source_observed_at
    finally:
        conn.close()

    snapshot: list[dict[str, Any]] = []
    for raw in raw_cnpjs:
        canonical = canonical_cnpj14(raw)
        if not canonical:
            continue
        decision = published.get(canonical[:8]) or published.get(raw[:8])
        if not decision:
            continue
        if not str(decision.get("source_watermark") or decision.get("target_fit_source_watermark") or "").strip():
            continue
        projected = dict(decision)
        if source_observed_at:
            projected["target_fit_evidence_watermark"] = str(
                decision.get("source_watermark") or decision.get("target_fit_source_watermark") or ""
            )
            projected["source_watermark"] = source_observed_at
            projected["target_fit_observation_run_id"] = str((authoritative_source_freshness or {}).get("run_id") or "")
        snapshot.append(
            {
                **projected,
                "cnpj14": canonical,
                "cnpj_raiz": canonical[:8],
                "company_key": f"cnpj_root:{canonical[:8]}",
            }
        )
    return snapshot, "published_target_fit_store", datalake_watermark


def _service_context_from_primary(service_id: str | None) -> str:
    sid = (service_id or "").lower()
    if "reajuste" in sid or "reequilibrio" in sid or "pleito" in sid:
        return ServiceContext.CLAIMS_REAJUSTE.value
    if "licit" in sid or "proposta" in sid:
        return ServiceContext.LICITACOES.value
    if "medicao" in sid or "glosa" in sid or "orcamento" in sid or "bdi" in sid:
        return ServiceContext.ORCAMENTO_MEDICOES.value
    return ServiceContext.GENERIC.value


@dataclass
class PipelineConfig:
    out_dir: Path
    dsn: str | None = None
    csv_path: str | None = None
    as_of: date | None = None
    limit_downstream: int = 200
    max_workers: int = 4
    max_rows: int | None = None  # universe sampling (diagnostic only)
    dnc_path: str | None = None
    skip_universe: bool = False
    skip_contacts: bool = False
    allow_network: bool = False
    enable_web_search: bool = False
    fixtures_dir: Path | None = None
    contact_fixtures_dir: Path | None = None
    durable_contacts_path: Path | None = None
    # Previously published feed release (``<publish_dir>/current``). Used to
    # derive deactivations for accounts that left the TARGET_CONFIRMED feed.
    published_feed_dir: Path | None = None
    include_dnc_in_sample: bool = True
    feed_limit: int | None = None
    # Activation planner (production default when True)
    use_activation_planner: bool = True
    activation_policy_path: str | None = None
    activation_capacity: int | None = None
    prior_activation_path: str | None = None
    # Smoke/diagnostic only: force diverse sample shortlist (not commercial strategy)
    force_sample_mode: bool = False
    # Durable commercial memory overlay (outcomes / DNC / NOT_NOW)
    commercial_memory_path: str | None = None
    # Resume from pipeline-checkpoint.json under out_dir
    resume: bool = True
    # Progress logging to stdout
    progress: bool = True
    authoritative_source_freshness: dict[str, Any] | None = None


@dataclass
class PipelineResult:
    ok: bool
    out_dir: str
    stages: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    manifest_path: str | None = None


def _progress(enabled: bool, msg: str) -> None:
    if enabled:
        print(msg, flush=True)


def run_pipeline(cfg: PipelineConfig) -> PipelineResult:
    """Execute UNIVERSE → ACTIVATION|SAMPLE → INTEL → CONTACTS → FEED."""
    started = time.monotonic()
    as_of = cfg.as_of or date.today()
    out = Path(cfg.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    use_activation = bool(cfg.use_activation_planner) and not bool(cfg.force_sample_mode)
    if cfg.feed_limit is not None:
        raise ValueError(
            "feed_limit is incompatible with the authoritative CONFENGE decision feed; "
            "limit expensive enrichment with limit_downstream instead"
        )

    dirs = {
        "universe": out / "01_universe",
        "sample": out / "02_downstream_sample",
        "activation": out / "02_activation",
        "intel": out / "03_account_intelligence",
        "contacts": out / "04_contact_resolution",
        "bridge_inputs": out / "05_bridge_inputs",
        "feed": out / "06_warmbly_feed",
        "reports": out / "reports",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    result = PipelineResult(ok=True, out_dir=str(out))
    repo_sha = _git_sha()
    started_at = _utcnow()
    stages: dict[str, Any] = {
        "pipeline_id": PIPELINE_ID,
        "module_version": MODULE_VERSION,
        "repo_sha": repo_sha,
        "as_of": as_of.isoformat(),
        "started_at": started_at,
        "limit_downstream": cfg.limit_downstream,
        "max_workers": cfg.max_workers,
        "max_rows_universe": cfg.max_rows,
        "sampling": bool(cfg.max_rows is not None),
        "use_activation_planner": use_activation,
        "force_sample_mode": bool(cfg.force_sample_mode),
        "source_operational_health": cfg.authoritative_source_freshness,
    }

    commercial_qualifications: list[RootQualification] = []
    commercial_qualification_corpus: Path | None = None
    commercial_qualification_summary: dict[str, Any] | None = None
    if cfg.dsn:
        (
            commercial_qualifications,
            commercial_qualification_summary,
            commercial_qualification_corpus,
        ) = _rebuild_durable_commercial_authority(cfg.dsn, as_of=as_of, out_dir=out)
        stages["commercial_authority_v2"] = {
            **commercial_qualification_summary,
            "corpus": str(commercial_qualification_corpus),
        }

    # Durable checkpoint for resume != restart from zero
    ckpt = None
    if cfg.resume:
        ckpt = load_checkpoint(out)
    if ckpt is None:
        ckpt = new_checkpoint(run_id=f"pipe-{repo_sha}-{as_of.isoformat()}", as_of=as_of.isoformat())
    commercial_memory: dict[str, dict[str, Any]] = {}
    if cfg.commercial_memory_path:
        commercial_memory = load_commercial_memory_jsonl(cfg.commercial_memory_path)

    try:
        # ── 1. Universe ──────────────────────────────────────────────────
        universe_jsonl = dirs["universe"] / DEFAULT_JSONL_NAME
        exclusions_jsonl = dirs["universe"] / DEFAULT_EXCLUSIONS_JSONL_NAME
        universe_manifest = dirs["universe"] / DEFAULT_MANIFEST_NAME
        skip_uni = bool(cfg.skip_universe and universe_jsonl.is_file() and exclusions_jsonl.is_file())
        if (
            not skip_uni
            and ckpt.stage_completed("universe")
            and universe_jsonl.is_file()
            and exclusions_jsonl.is_file()
        ):
            skip_uni = True
            _progress(cfg.progress, "[universe] resume: reusing completed checkpoint artifacts")

        ckpt.mark_running("universe")
        save_checkpoint(out, ckpt)

        if skip_uni:
            uni_meta: dict[str, Any] = {
                "ok": True,
                "skipped": True,
                "jsonl_path": str(universe_jsonl),
                "manifest_path": str(universe_manifest) if universe_manifest.is_file() else None,
            }
            if universe_manifest.is_file():
                try:
                    man = json.loads(universe_manifest.read_text(encoding="utf-8"))
                    uni_meta["counts"] = man.get("counts") or {}
                    uni_meta["reconciliation_ok"] = (man.get("counts") or {}).get("reconciliation", {}).get(
                        "ok"
                    ) or man.get("extra", {}).get("reconciliation_bucket_ok")
                    uni_meta["source"] = man.get("source") or {}
                except (json.JSONDecodeError, OSError):
                    pass
        else:
            _progress(cfg.progress, "[universe] scanning contracts (full datalake when max_rows=None)…")
            uni_meta = run_universe_build(
                as_of=as_of,
                dsn=cfg.dsn,
                csv_path=cfg.csv_path,
                out_dir=dirs["universe"],
                max_rows=cfg.max_rows,
                dnc_path=cfg.dnc_path,
            )
            universe_jsonl = Path(uni_meta.get("jsonl_path") or universe_jsonl)
            exclusions_jsonl = Path(uni_meta.get("exclusions_jsonl_path") or exclusions_jsonl)
            universe_manifest = Path(uni_meta.get("manifest_path") or universe_manifest)
        stages["universe"] = {
            k: uni_meta.get(k)
            for k in (
                "status",
                "as_of",
                "repo_sha",
                "jsonl_path",
                "manifest_path",
                "counts",
                "reconciliation_ok",
                "ok",
                "skipped",
                "source",
            )
            if k in uni_meta
        }

        universe_rows = _read_jsonl(universe_jsonl)
        exclusion_rows = _read_jsonl(exclusions_jsonl)
        base_decision_rows, duplicate_decision_rows = _dedupe_decision_rows([*universe_rows, *exclusion_rows])
        if cfg.dsn:
            qualification_observed_at = (
                datetime.combine(as_of, datetime_time.min, tzinfo=UTC).isoformat().replace("+00:00", "Z")
            )
            (
                decision_rows,
                target_fit_snapshot_rows,
                target_identity_reconciliation,
            ) = _commercial_authority_snapshot(
                base_decision_rows,
                commercial_qualifications,
                observed_at=qualification_observed_at,
            )
            target_fit_authority = "commercial_authority_v2_datalake"
            target_fit_datalake_watermark = qualification_observed_at
        else:
            decision_rows = base_decision_rows
            target_identity_reconciliation = {
                "authoritative_target_roots": 0,
                "base_target_establishments": 0,
                "base_target_roots": 0,
                "target_roots_added": 0,
                "branch_duplicates_collapsed": 0,
                "canonical_establishments_replaced": 0,
                "target_roots_emitted": 0,
                "target_rows_missing_legal_name": 0,
                "output_decision_rows": len(decision_rows),
            }
            (
                target_fit_snapshot_rows,
                target_fit_authority,
                target_fit_datalake_watermark,
            ) = _published_target_fit_snapshot(decision_rows, dsn=None)
        stages["universe_row_count"] = len(universe_rows)
        stages["reservoir_count"] = len(universe_rows)
        stages["target_fit_base_decision_universe_count"] = len(base_decision_rows)
        stages["target_fit_decision_universe_count"] = len(decision_rows)
        stages["target_fit_duplicate_cnpj_collapsed"] = duplicate_decision_rows
        stages["target_fit_identity_reconciliation"] = target_identity_reconciliation
        stages["target_fit_unaddressable_exclusion_count"] = len(exclusion_rows) - (
            len(base_decision_rows) - len(universe_rows)
        )
        stages["target_fit_snapshot_count"] = len(target_fit_snapshot_rows)
        stages["target_fit_authority"] = target_fit_authority
        uni_counts = stages.get("universe", {}).get("counts") or uni_meta.get("counts") or {}
        ckpt.universe_total = len(universe_rows)
        ckpt.full_datalake_scanned = bool(
            uni_counts.get("full_scale")
            if "full_scale" in uni_counts
            else (cfg.max_rows is None and bool(cfg.dsn) and not cfg.csv_path)
        )
        ckpt.mark_completed(
            "universe",
            counts={
                "rows": len(universe_rows),
                "contracts": uni_counts.get("input_contract_rows"),
                "full_scale": ckpt.full_datalake_scanned,
            },
            artifact_paths={"jsonl": str(universe_jsonl)},
        )
        save_checkpoint(out, ckpt)
        _progress(
            cfg.progress,
            f"[universe] {uni_counts.get('input_contract_rows') or '?'} contracts → "
            f"{len(universe_rows)} construction companies "
            f"(full_scale={ckpt.full_datalake_scanned})",
        )

        # ── 2. Activation planner (production) OR diverse sample (smoke) ─
        activation_by_cnpj: dict[str, dict[str, Any]] = {}
        deactivations: list[dict[str, Any]] = []
        sample_rows: list[dict[str, Any]] = []
        cycle_projections: list[Any] = []
        service_dist: dict[str, int] = {}

        ckpt.mark_running("activation")
        save_checkpoint(out, ckpt)

        if use_activation:
            policy = load_policy(cfg.activation_policy_path)
            prior_path = cfg.prior_activation_path
            if not prior_path:
                candidate = dirs["activation"] / "activation-projections.jsonl"
                if candidate.is_file():
                    prior_path = str(candidate)
            prior = load_projections_jsonl(prior_path) if prior_path else {}
            # Hot-set size: --activation-capacity override, else policy.planned_capacity().
            # NEVER pass limit_downstream as capacity_override — that is smoke/batch-only
            # and must not become the production commercial shortlist.
            capacity = cfg.activation_capacity  # None → planner uses policy.planned_capacity()
            cycle = run_activation_cycle(
                universe_rows,
                policy=policy,
                as_of=as_of,
                prior_projections=prior,
                capacity_override=capacity,
                commercial_memory=commercial_memory or None,
                include_watch_fill=True,
            )
            cycle_projections = list(cycle.projections)
            write_projections_jsonl(dirs["activation"] / "activation-projections.jsonl", cycle.projections)
            write_hot_set_jsonl(dirs["activation"] / "hot-set.jsonl", cycle.hot_set)
            (dirs["activation"] / "deactivations.json").write_text(
                json.dumps(cycle.deactivations, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (dirs["activation"] / "activation-summary.json").write_text(
                json.dumps(cycle.summary(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            deactivations = list(cycle.deactivations)
            activation_by_cnpj = {p.cnpj14: p.as_dict() for p in cycle.projections}
            # Map hot set back to universe rows (preserve order of hot set)
            by_cnpj = {"".join(ch for ch in str(r.get("cnpj14") or "") if ch.isdigit()): r for r in universe_rows}
            sample_rows = [by_cnpj[c] for c in (p.cnpj14 for p in cycle.hot_set) if c in by_cnpj]
            # Preserve the activation canary for network contact work. Deterministic
            # account intelligence expands to authoritative TARGET_CONFIRMED below.
            sample_path = dirs["sample"] / "downstream-hot-set.jsonl"
            _write_jsonl(sample_path, sample_rows)
            planned_cap = int(capacity) if capacity is not None else policy.capacity.planned_capacity()
            stages["activation"] = {
                **cycle.summary(),
                "projections_path": str(dirs["activation"] / "activation-projections.jsonl"),
                "hot_set_path": str(dirs["activation"] / "hot-set.jsonl"),
                "capacity_this_round": planned_cap,
                "capacity_source": (
                    "activation_capacity_override" if cfg.activation_capacity is not None else "policy.planned_capacity"
                ),
                "note": (
                    "Hot set is capacity-aware activation planning, not arbitrary Top-N. "
                    "Full reservoir remains monitored; only hot set enters network contact discovery. "
                    "Deterministic intelligence also covers authoritative TARGET_CONFIRMED. "
                    "--limit-downstream is smoke/batch-only and does NOT set commercial capacity."
                ),
            }
            stages["sample"] = {
                "path": str(sample_path),
                "count": len(sample_rows),
                "mode": "activation_hot_set",
                "profile_counts": sample_profile_counts(sample_rows),
                "note": (
                    "Network-contact rows selected by activation planner hot set. "
                    f"capacity={planned_cap}; reservoir={len(universe_rows)}."
                ),
            }
            stages["activation_counts"] = cycle.activation_counts
            stages["hot_set_count"] = cycle.hot_set_count
            stages["policy_version"] = cycle.policy_version
            stages["source_watermark"] = cycle.source_watermark
            ckpt.add_processed(
                [p.cnpj14 for p in cycle.hot_set],
                cursor=cycle.hot_set[-1].cnpj14 if cycle.hot_set else None,
            )
            _progress(
                cfg.progress,
                f"[activation] reservoir={cycle.reservoir_count} "
                f"hot_set={cycle.hot_set_count}/{planned_cap} "
                f"states={cycle.activation_counts}",
            )
        else:
            sample_rows = select_diverse_sample(
                universe_rows,
                limit=cfg.limit_downstream,
                include_dnc=cfg.include_dnc_in_sample,
            )
            sample_path = dirs["sample"] / "downstream-sample.jsonl"
            _write_jsonl(sample_path, sample_rows)
            profile_counts = sample_profile_counts(sample_rows)
            stages["sample"] = {
                "path": str(sample_path),
                "count": len(sample_rows),
                "mode": "diverse_sample",
                "profile_counts": profile_counts,
                "note": (
                    "SMOKE/DIAGNOSTIC only. limit_downstream bounds expensive stages; "
                    "not a production commercial shortlist strategy. "
                    "Use --use-activation-planner for production."
                ),
            }
            stages["activation_counts"] = {}
            stages["hot_set_count"] = len(sample_rows)
            stages["policy_version"] = None
            stages["source_watermark"] = None

        ckpt.mark_completed(
            "activation",
            counts={
                "hot_set": len(sample_rows),
                "reservoir": len(universe_rows),
            },
        )
        save_checkpoint(out, ckpt)

        # ── 3. Account intelligence ──────────────────────────────────────
        ckpt.mark_running("intelligence")
        save_checkpoint(out, ckpt)
        intelligence_rows, intelligence_scope = _select_intelligence_rows(
            decision_rows=decision_rows,
            downstream_rows=sample_rows,
            target_fit_snapshot_rows=target_fit_snapshot_rows,
            include_all_target_confirmed=use_activation,
        )
        if use_activation and intelligence_scope["target_confirmed_missing"]:
            raise ValueError(
                "authoritative TARGET_CONFIRMED account missing from account-intelligence scope: "
                f"missing={intelligence_scope['target_confirmed_missing']} "
                f"total={intelligence_scope['target_confirmed_total']}"
            )
        intel_inputs = [universe_row_to_intelligence_input(r, as_of=as_of.isoformat()) for r in intelligence_rows]
        intel_input_path = dirs["intel"] / "intelligence-inputs.jsonl"
        _write_jsonl(intel_input_path, intel_inputs)

        dossiers = process_batch(
            intel_inputs,
            max_workers=cfg.max_workers,
            as_of=as_of.isoformat(),
        )
        # Stash normalized contracts so the bridge can emit real contracts[]
        # (dossier schema keeps portfolio_summary only).
        for d, inp in zip(dossiers, intel_inputs, strict=False):
            if isinstance(d, dict) and isinstance(inp, dict):
                d["_pipeline_contracts"] = list(inp.get("contracts") or [])
        intel_raw_path = dirs["intel"] / "confenge-account-intelligence-v1.jsonl"
        _write_jsonl(intel_raw_path, dossiers)

        bridge_intel = [intelligence_dossier_to_bridge_row(d) for d in dossiers]
        bridge_intel_path = dirs["bridge_inputs"] / "account_intelligence.jsonl"
        _write_jsonl(bridge_intel_path, bridge_intel)

        for d in dossiers:
            ps = d.get("primary_service") if isinstance(d.get("primary_service"), dict) else {}
            sid = str(ps.get("service_id") or "unknown")
            service_dist[sid] = service_dist.get(sid, 0) + 1
        stages["account_intelligence"] = {
            "input_path": str(intel_input_path),
            "raw_path": str(intel_raw_path),
            "bridge_path": str(bridge_intel_path),
            "count": len(dossiers),
            **intelligence_scope,
            "service_distribution": dict(sorted(service_dist.items(), key=lambda x: (-x[1], x[0]))),
        }
        ckpt.mark_completed("intelligence", counts={"dossiers": len(dossiers)})
        save_checkpoint(out, ckpt)
        _progress(
            cfg.progress,
            f"[intelligence] {len(dossiers)} processed; "
            f"TARGET_CONFIRMED={intelligence_scope['target_confirmed_processed']}/"
            f"{intelligence_scope['target_confirmed_total']}",
        )

        # ── 4. Contact resolution ────────────────────────────────────────
        ckpt.mark_running("contacts")
        save_checkpoint(out, ckpt)
        if cfg.skip_contacts:
            bridge_contacts: list[dict[str, Any]] = [
                {"cnpj14": r.get("cnpj14") or r.get("cnpj"), "contacts": []} for r in sample_rows
            ]
            contact_meta: dict[str, Any] = {"skipped": True, "count": len(bridge_contacts)}
        else:
            # Prefer service context from primary service when uniform-ish; else generic.
            majority_svc = max(service_dist, key=service_dist.get) if service_dist else None  # type: ignore[arg-type]
            svc_ctx = _service_context_from_primary(majority_svc)
            cache = ResolutionCache(dirs["contacts"] / ".cache", ttl_seconds=86400)
            resolver = build_pipeline_contact_resolver(
                cfg,
                sample_rows=sample_rows,
                cache=cache,
                service_context=svc_ctx,
            )
            cnpjs = [_digits_cnpj(r.get("cnpj14") or r.get("cnpj")) for r in sample_rows]
            cnpjs = [c for c in cnpjs if len(c) == 14]
            resolutions = resolver.resolve_batch(cnpjs, max_workers=cfg.max_workers)
            contact_meta = write_resolution_artifacts(
                resolutions,
                dirs["contacts"],
                mode="pipeline",
                service_context=svc_ctx,
            )
            bridge_contacts = [contact_resolution_to_bridge_row(r.as_dict()) for r in resolutions]

            # Contact metrics
            metrics = _contact_metrics(resolutions)
            contact_meta["metrics"] = metrics

        durable_contacts: list[dict[str, Any]] = []
        if cfg.durable_contacts_path is not None:
            durable_path = Path(cfg.durable_contacts_path)
            if not durable_path.is_file():
                raise ValueError(f"durable contact projection not found: {durable_path}")
            durable_contacts = _read_jsonl(durable_path)
        bridge_contacts, merge_metrics = merge_contact_rows(durable_contacts, bridge_contacts)
        contact_meta["durable_projection"] = {
            **merge_metrics,
            "path": str(cfg.durable_contacts_path) if cfg.durable_contacts_path else None,
        }

        bridge_contacts_path = dirs["bridge_inputs"] / "contacts.jsonl"
        _write_jsonl(bridge_contacts_path, bridge_contacts)
        stages["contacts"] = {
            **contact_meta,
            "bridge_path": str(bridge_contacts_path),
        }
        cm = (contact_meta or {}).get("metrics") or {}
        ckpt.mark_completed(
            "contacts",
            counts={
                "resolved": cm.get("empresas_com_email_verificavel") or cm.get("empresas_total"),
                "no_contact": cm.get("empresas_sem_contato"),
            },
        )
        save_checkpoint(out, ckpt)
        _progress(
            cfg.progress,
            f"[contacts] resolved={cm.get('empresas_com_email_verificavel', '?')} "
            f"no_contact={cm.get('empresas_sem_contato', '?')} "
            f"pending=0",
        )

        # ── 5. Bridge universe inputs + export ───────────────────────────
        ckpt.mark_running("feed")
        save_checkpoint(out, ckpt)
        # The feed ships the current TARGET_CONFIRMED population. Accounts that
        # were shipped in the previously published release and are no longer
        # members must leave as explicit deactivations, never by vanishing.
        published_feed_dir = Path(cfg.published_feed_dir) if cfg.published_feed_dir else None
        if published_feed_dir is not None and not published_feed_dir.is_dir():
            published_feed_dir = None
        stages["published_feed_dir"] = str(published_feed_dir) if published_feed_dir else None
        bridge_universe = [universe_row_for_bridge(r, rank=i + 1) for i, r in enumerate(decision_rows)]
        # Attach activation projection onto bridge universe rows when available
        if activation_by_cnpj:
            for br in bridge_universe:
                c = "".join(ch for ch in str(br.get("cnpj14") or "") if ch.isdigit())
                act = activation_by_cnpj.get(c)
                if act:
                    br["activation"] = {
                        "state": act.get("activation_state"),
                        "score": act.get("activation_score"),
                        "reason_codes": act.get("reason_codes") or [],
                        "policy_version": act.get("policy_version"),
                        "evaluated_at": act.get("evaluated_at"),
                        "next_best_action_at": act.get("next_best_action_at"),
                        "expires_at": act.get("expires_at"),
                        "source_hash": act.get("source_hash"),
                        "score_components": act.get("score_components") or {},
                    }
        bridge_universe_path = dirs["bridge_inputs"] / "universe.jsonl"
        _write_jsonl(bridge_universe_path, bridge_universe)
        target_fit_snapshot_path = dirs["bridge_inputs"] / "target-fit-snapshot.jsonl"
        _write_jsonl(target_fit_snapshot_path, target_fit_snapshot_rows)

        # Empty hot set is a valid ops state (all capacity consumed / no eligibles)
        # — write empty feed artifacts instead of failing closed on empty join.
        if not bridge_universe:
            empty_manifest = {
                "schema_version": "confenge.outreach.manifest.v1",
                "module_version": MODULE_VERSION,
                "generated_at": _utcnow(),
                "lead_count": 0,
                "chunk_count": 0,
                "chunks": [],
                "note": "No leads in this round's hot set (capacity/cursor/memory).",
                "reservoir_count": len(universe_rows),
            }
            (dirs["feed"] / "manifest.json").write_text(
                json.dumps(empty_manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            export_result = {
                "ok": True,
                "out_dir": str(dirs["feed"].resolve()),
                "run_id": "run-empty-hot-set",
                "lead_count": 0,
                "chunk_count": 0,
                "manifest": str((dirs["feed"] / "manifest.json").resolve()),
                "chunks": [],
            }
        else:
            export_cfg = ExportConfig(
                universe=bridge_universe_path,
                account_intelligence=bridge_intel_path,
                contacts=bridge_contacts_path,
                target_fit_snapshot=target_fit_snapshot_path,
                contact_projection_report=(
                    Path(cfg.durable_contacts_path).with_name("contact-projection-report.json")
                    if cfg.durable_contacts_path is not None
                    and (
                        cfg.dsn is not None
                        or Path(cfg.durable_contacts_path).with_name("contact-projection-report.json").is_file()
                    )
                    else None
                ),
                expected_universe_count=len(bridge_universe),
                out_dir=dirs["feed"],
                datalake_watermark=target_fit_datalake_watermark,
                require_authoritative_target_fit_metadata=bool(cfg.dsn),
                require_authoritative_contact_projection_metadata=bool(
                    cfg.dsn and cfg.durable_contacts_path is not None
                ),
                repo_sha=repo_sha,
                authoritative_source_freshness=cfg.authoritative_source_freshness,
                require_authoritative_source_freshness=False,
                commercial_qualification_corpus=commercial_qualification_corpus,
                require_commercial_authority_v2=bool(cfg.dsn),
                deactivations=deactivations,
                previous_feed_dir=published_feed_dir,
            )
            export_result = export_outreach(export_cfg)
        stages["feed"] = export_result
        stages["feed_count"] = (export_result or {}).get("lead_count")
        stages["expensive_enrichment_count"] = len(intelligence_rows)

        # Persist funnel progress: mark exported / no-contact on projections
        if use_activation and cycle_projections:
            contact_by = {"".join(ch for ch in str(c.get("cnpj14") or "") if ch.isdigit()): c for c in bridge_contacts}
            updated = []
            for p in cycle_projections:
                d = p.as_dict() if hasattr(p, "as_dict") else dict(p)
                cnpj = d.get("cnpj14")
                if cnpj and any(
                    "".join(ch for ch in str(r.get("cnpj14") or "") if ch.isdigit()) == cnpj for r in sample_rows
                ):
                    crow = contact_by.get(cnpj) or {}
                    contacts = crow.get("contacts") or []
                    d["account_intelligence_status"] = "DONE"
                    d["last_processed_at"] = d.get("last_downstream_at") or _utcnow()
                    if contacts:
                        d = mark_downstream(d, status=DOWNSTREAM_EXPORTED)
                        d["contact_resolution_status"] = "FOUND"
                        d["feed_export_status"] = "EXPORTED"
                    else:
                        d = mark_downstream(d, status=DOWNSTREAM_NO_CONTACT)
                        d["contact_resolution_status"] = "NO_CONTACT"
                        d["feed_export_status"] = "EXPORTED" if not cfg.skip_contacts else "PENDING"
                    d["outreach_state"] = d.get("commercial_state") or "NEW"
                updated.append(d)
            # rewrite projections with funnel status
            proj_path = dirs["activation"] / "activation-projections.jsonl"
            with proj_path.open("w", encoding="utf-8") as f:
                for d in sorted(updated, key=lambda x: x.get("cnpj14") or ""):
                    f.write(json.dumps(d, ensure_ascii=False, sort_keys=True) + "\n")
            activation_by_cnpj = {d["cnpj14"]: d for d in updated if d.get("cnpj14")}

        ckpt.mark_completed(
            "feed",
            counts={"lead_count": stages.get("feed_count") or 0},
            artifact_paths={"manifest": str(dirs["feed"] / "manifest.json")},
        )
        save_checkpoint(out, ckpt)

        # ── 6. Stage reports + auditable full-run package ────────────────
        stages["finished_at"] = _utcnow()
        stages["elapsed_seconds"] = round(time.monotonic() - started, 3)
        stages["peak_rss_mb"] = _peak_rss_mb()
        uni_counts = (stages.get("universe") or {}).get("counts") or {}
        stages["full_scale_universe"] = bool(
            uni_counts.get("full_scale")
            if "full_scale" in uni_counts
            else (not cfg.max_rows and bool(cfg.dsn) and not cfg.csv_path)
        )
        elapsed = max(0.001, float(stages["elapsed_seconds"]))
        contracts_n = int(uni_counts.get("input_contract_rows") or 0)
        stages["throughput"] = {
            "contracts_per_sec": round(contracts_n / elapsed, 2) if contracts_n else None,
            "companies_per_min": round(len(universe_rows) / (elapsed / 60.0), 2),
            "contacts_per_min": round(
                float((stages.get("contacts") or {}).get("metrics", {}).get("empresas_total") or 0) / (elapsed / 60.0),
                2,
            ),
            "elapsed_seconds": stages["elapsed_seconds"],
            "peak_rss_mb": stages["peak_rss_mb"],
        }
        # Explicit production-facing summary (real cycle numbers, never hard-coded)
        stages["manifest_summary"] = {
            "reservoir_count": stages.get("reservoir_count") or len(universe_rows),
            "universe_total": stages.get("reservoir_count") or len(universe_rows),
            "activation_counts": stages.get("activation_counts") or {},
            "hot_set_count": stages.get("hot_set_count") or 0,
            "expensive_enrichment_count": stages.get("expensive_enrichment_count") or 0,
            "feed_count": stages.get("feed_count") or 0,
            "policy_version": stages.get("policy_version"),
            "source_watermark": stages.get("source_watermark"),
            "full_scale_universe": stages.get("full_scale_universe"),
            "use_activation_planner": use_activation,
            "limit_downstream_is_batch_only": True,
            "checkpoint_path": str(out / "pipeline-checkpoint.json"),
        }

        # Universe summary + run manifest (auditable arithmetic)
        uni_source = (stages.get("universe") or {}).get("source") or uni_meta.get("source") or {}
        universe_summary = build_universe_summary(
            source=uni_source if isinstance(uni_source, dict) else {},
            counts=uni_counts if isinstance(uni_counts, dict) else {},
            universe_rows=universe_rows,
            started_at=started_at,
            finished_at=stages["finished_at"],
        )
        state_dist: dict[str, int] = {}
        if activation_by_cnpj:
            for d in activation_by_cnpj.values():
                st = str(d.get("activation_state") or "UNKNOWN")
                state_dist[st] = state_dist.get(st, 0) + 1
        contact_summary = (stages.get("contacts") or {}).get("metrics") or {}
        run_manifest = build_run_manifest(
            run_id=ckpt.run_id,
            stages=stages,
            universe_summary=universe_summary,
            service_distribution=service_dist,
            state_distribution=state_dist,
            contact_summary=contact_summary,
            feed_summary={
                "lead_count": stages.get("feed_count") or 0,
                "chunk_count": (export_result or {}).get("chunk_count"),
                "run_id": (export_result or {}).get("run_id"),
                "out_dir": (export_result or {}).get("out_dir"),
            },
            throughput=stages["throughput"],
        )
        (dirs["reports"] / "universe_summary.json").write_text(
            json.dumps(universe_summary, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        (dirs["reports"] / "service_distribution.json").write_text(
            json.dumps(service_dist, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (dirs["reports"] / "state_distribution.json").write_text(
            json.dumps(state_dist, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (dirs["reports"] / "contact_resolution_summary.json").write_text(
            json.dumps(contact_summary, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        (dirs["reports"] / "full-run-manifest.json").write_text(
            json.dumps(run_manifest, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        stages["full_run_manifest"] = {
            "path": str(dirs["reports"] / "full-run-manifest.json"),
            "acceptance": run_manifest.get("acceptance"),
            "result": run_manifest.get("result"),
        }

        report_path = dirs["reports"] / "pipeline-manifest.json"
        report_path.write_text(
            json.dumps(stages, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        ckpt.mark_completed("done", counts={"ok": True})
        save_checkpoint(out, ckpt)
        _progress(
            cfg.progress,
            f"[feed] leads={stages.get('feed_count')} "
            f"elapsed={stages['elapsed_seconds']}s "
            f"rss_mb={stages['peak_rss_mb']}",
        )
        result.stages = stages
        result.manifest_path = str(report_path)
        result.ok = True
        return result

    except Exception as exc:  # noqa: BLE001
        result.ok = False
        result.errors.append(f"{type(exc).__name__}: {exc}")
        stages["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        stages["finished_at"] = _utcnow()
        stages["elapsed_seconds"] = round(time.monotonic() - started, 3)
        stages["peak_rss_mb"] = _peak_rss_mb()
        report_path = dirs["reports"] / "pipeline-manifest.json"
        report_path.write_text(
            json.dumps(stages, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        result.stages = stages
        result.manifest_path = str(report_path)
        return result


def _contact_metrics(resolutions: list[Any]) -> dict[str, Any]:
    nominal = 0
    generic_only = 0
    verifiable_email = 0
    phone_valid = 0
    phone_mobile = 0
    phone_landline = 0
    no_contact = 0
    dnc = 0
    for r in resolutions:
        cands = getattr(r, "candidates", None) or []
        if not cands:
            no_contact += 1
            continue
        has_nominal = False
        has_generic = False
        has_verifiable = False
        has_phone = False
        has_mobile = False
        has_landline = False
        is_dnc = False
        for c in cands:
            if getattr(c, "dnc", False):
                is_dnc = True
            name = (getattr(c, "name", None) or "").strip()
            email = (getattr(c, "email", None) or "").strip()
            vs = str(getattr(c, "verification_status", "") or "").upper()
            layers = getattr(c, "email_layers", None)
            pattern = bool(getattr(layers, "pattern_guessed", False)) if layers else False
            if name and " " in name:
                has_nominal = True
            if email and not name:
                has_generic = True
            if email and not pattern and vs not in {"CANDIDATE_UNVERIFIED", "SYNTAX_INVALID", "NOT_AVAILABLE"}:
                has_verifiable = True
            phone = getattr(c, "phone_e164", None) or getattr(c, "phone_raw", None)
            if phone:
                has_phone = True
                ptype = str(getattr(c, "phone_type", "") or "").lower()
                if ptype == "mobile":
                    has_mobile = True
                elif ptype == "landline":
                    has_landline = True
        if is_dnc:
            dnc += 1
        if has_nominal:
            nominal += 1
        elif has_generic:
            generic_only += 1
        if has_verifiable:
            verifiable_email += 1
        if has_phone:
            phone_valid += 1
        if has_mobile:
            phone_mobile += 1
        if has_landline:
            phone_landline += 1

    n = max(1, len(resolutions))
    return {
        "empresas_total": len(resolutions),
        "empresas_com_contato_nominal": nominal,
        "empresas_apenas_email_funcional_generico": generic_only,
        "empresas_com_email_verificavel": verifiable_email,
        "empresas_com_telefone_valido": phone_valid,
        "empresas_com_telefone_movel": phone_mobile,
        "empresas_com_telefone_fixo": phone_landline,
        "empresas_sem_contato": no_contact,
        "empresas_dnc": dnc,
        "nominal_contact_rate": round(nominal / n, 4),
        "verified_email_rate": round(verifiable_email / n, 4),
        "generic_email_rate": round(generic_only / n, 4),
        "phone_rate": round(phone_valid / n, 4),
        "no_contact_rate": round(no_contact / n, 4),
        "note": (
            "Email fabricado por padrão de nome (pattern_guessed) NÃO conta como verificável. "
            "Telefone público NÃO implica opt-in WhatsApp."
        ),
    }
