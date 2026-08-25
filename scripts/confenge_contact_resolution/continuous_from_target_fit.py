"""Continuous contact enrichment over the live construction universe.

Pulls company roots from published target-fit (SHADOW or current), excludes
companies already attempted (checkpoint), and feeds EnrichmentBatchRunner
without any EMAIL_SEND_READY / pilot hard cap.

``max_companies`` is smoke/batch-only. Omit for full reservoir advancement.
Priority: higher commercial value first when scores available, else CNPJ order.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_activation.operational_metrics import (
    PILOT_ACCEPTANCE_SAMPLE as MINIMUM_PILOT_ACCEPTANCE_SAMPLE,
)
from scripts.confenge_activation.operational_metrics import (
    assert_not_pilot_as_capacity,
)
from scripts.confenge_contact_resolution.contact_coverage import (
    measure_contact_coverage,
)
from scripts.confenge_contact_resolution.discovery_state import (
    classify_contact_terminal,
    measure_terminal_coverage,
)
from scripts.confenge_contact_resolution.enrichment_batch import (
    CompanyJob,
    EnrichmentBatchRunner,
)
from scripts.confenge_contact_resolution.resolver import ResolverConfig
from scripts.confenge_target_fit import MODE_SHADOW, TARGET_CONFIRMED
from scripts.confenge_target_fit.db import connect
from scripts.confenge_target_fit.store import get_control

logger = logging.getLogger(__name__)

DEFAULT_OUT = Path("artifacts/confenge/contact-enrichment/continuous-construction")
LEGACY_DEFAULT_OUT = Path("artifacts/confenge/contact-enrichment/continuous-confirmed")


@dataclass
class ContinuousEnrichmentConfig:
    output_dir: Path = DEFAULT_OUT
    # None = no commercial hard cap (advance full reservoir)
    max_companies: int | None = None
    allow_network: bool = False
    fixtures_dir: Path | None = None
    resume: bool = True
    # Deprecated compatibility flag. Sector membership, not target-fit, defines
    # the enrichment population; all construction classes are always included.
    include_probable: bool = True


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def load_construction_jobs_from_dsn(
    dsn: str,
    *,
    target_confirmed_only: bool = False,
) -> list[CompanyJob]:
    """Load the construction universe, or the full current TARGET_CONFIRMED set."""
    conn = connect(dsn, readonly=True)
    try:
        mode_ctrl = get_control(conn, "async_mode")
        mode = str(mode_ctrl.get("mode") or MODE_SHADOW).upper()
        with conn.cursor() as cur:
            if mode == MODE_SHADOW:
                cur.execute(
                    """
                    SELECT s.company_key, s.cnpj_raiz, s.representative_cnpj14,
                           s.sector_class,
                           s.sector_confidence,
                           s.sector_version,
                           s.sector_classifier_sha256,
                           s.input_fingerprint AS sector_input_fingerprint,
                           s.source_watermark AS sector_source_watermark,
                           s.computed_at AS sector_computed_at,
                           t.shadow_class AS target_fit_class,
                           t.shadow_confidence AS target_fit_confidence,
                           t.target_fit_version,
                           t.classifier_sha AS target_fit_classifier_sha,
                           t.input_fingerprint AS target_fit_input_fingerprint,
                           t.source_watermark AS target_fit_source_watermark,
                           t.computed_at AS target_fit_computed_at,
                           COALESCE(NULLIF(BTRIM(r.razao_social), ''), pc.razao_social)
                               AS registry_razao_social,
                           r.nome_fantasia AS registry_nome_fantasia,
                           CASE
                               WHEN NULLIF(BTRIM(r.razao_social), '') IS NOT NULL THEN r.source
                               WHEN pc.razao_social IS NOT NULL THEN 'pncp_supplier_contracts'
                           END AS registry_source,
                           CASE
                               WHEN NULLIF(BTRIM(r.razao_social), '') IS NOT NULL THEN r.source_version
                               WHEN pc.razao_social IS NOT NULL THEN 'pncp_supplier_contract_identity.v1'
                           END AS registry_source_version,
                           CASE
                               WHEN NULLIF(BTRIM(r.razao_social), '') IS NOT NULL THEN r.source_date
                               ELSE pc.source_date
                           END AS registry_source_date
                    FROM confenge_company_sector_current s
                    LEFT JOIN confenge_target_fit_shadow t USING (company_key)
                    LEFT JOIN supplier_registry r
                      ON r.cnpj14 = s.representative_cnpj14
                    LEFT JOIN LATERAL (
                        SELECT NULLIF(BTRIM(c.fornecedor_nome), '') AS razao_social,
                               c.data_publicacao AS source_date
                        FROM pncp_supplier_contracts c
                        WHERE c.fornecedor_cnpj_8 = s.cnpj_raiz
                          AND NULLIF(BTRIM(c.fornecedor_nome), '') IS NOT NULL
                        ORDER BY c.data_publicacao DESC NULLS LAST, c.id DESC
                        LIMIT 1
                    ) pc ON TRUE
                    WHERE (
                        (%s AND t.shadow_class = 'TARGET_CONFIRMED')
                        OR (
                            NOT %s
                            AND s.sector_class IN ('CONSTRUCTION_CONFIRMED', 'CONSTRUCTION_PROBABLE')
                        )
                    )
                    ORDER BY
                        CASE t.shadow_class
                            WHEN 'TARGET_CONFIRMED' THEN 0
                            WHEN 'TARGET_PROBABLE_RESEARCH' THEN 1
                            WHEN 'TARGET_INSUFFICIENT_EVIDENCE' THEN 2
                            ELSE 3
                        END,
                        s.sector_confidence DESC,
                        s.cnpj_raiz
                    """,
                    (target_confirmed_only, target_confirmed_only),
                )
            else:
                cur.execute(
                    """
                    SELECT s.company_key, s.cnpj_raiz, s.representative_cnpj14,
                           s.sector_class,
                           s.sector_confidence,
                           s.sector_version,
                           s.sector_classifier_sha256,
                           s.input_fingerprint AS sector_input_fingerprint,
                           s.source_watermark AS sector_source_watermark,
                           s.computed_at AS sector_computed_at,
                           t.target_fit_class,
                           t.target_fit_confidence,
                           t.target_fit_version,
                           t.classifier_sha AS target_fit_classifier_sha,
                           t.input_fingerprint AS target_fit_input_fingerprint,
                           t.source_watermark AS target_fit_source_watermark,
                           t.computed_at AS target_fit_computed_at,
                           COALESCE(NULLIF(BTRIM(r.razao_social), ''), pc.razao_social)
                               AS registry_razao_social,
                           r.nome_fantasia AS registry_nome_fantasia,
                           CASE
                               WHEN NULLIF(BTRIM(r.razao_social), '') IS NOT NULL THEN r.source
                               WHEN pc.razao_social IS NOT NULL THEN 'pncp_supplier_contracts'
                           END AS registry_source,
                           CASE
                               WHEN NULLIF(BTRIM(r.razao_social), '') IS NOT NULL THEN r.source_version
                               WHEN pc.razao_social IS NOT NULL THEN 'pncp_supplier_contract_identity.v1'
                           END AS registry_source_version,
                           CASE
                               WHEN NULLIF(BTRIM(r.razao_social), '') IS NOT NULL THEN r.source_date
                               ELSE pc.source_date
                           END AS registry_source_date
                    FROM confenge_company_sector_current s
                    LEFT JOIN confenge_company_target_fit_current t USING (company_key)
                    LEFT JOIN supplier_registry r
                      ON r.cnpj14 = s.representative_cnpj14
                    LEFT JOIN LATERAL (
                        SELECT NULLIF(BTRIM(c.fornecedor_nome), '') AS razao_social,
                               c.data_publicacao AS source_date
                        FROM pncp_supplier_contracts c
                        WHERE c.fornecedor_cnpj_8 = s.cnpj_raiz
                          AND NULLIF(BTRIM(c.fornecedor_nome), '') IS NOT NULL
                        ORDER BY c.data_publicacao DESC NULLS LAST, c.id DESC
                        LIMIT 1
                    ) pc ON TRUE
                    WHERE (
                        (%s AND t.target_fit_class = 'TARGET_CONFIRMED')
                        OR (
                            NOT %s
                            AND s.sector_class IN ('CONSTRUCTION_CONFIRMED', 'CONSTRUCTION_PROBABLE')
                        )
                    )
                    ORDER BY
                        CASE t.target_fit_class
                            WHEN 'TARGET_CONFIRMED' THEN 0
                            WHEN 'TARGET_PROBABLE_RESEARCH' THEN 1
                            WHEN 'TARGET_INSUFFICIENT_EVIDENCE' THEN 2
                            ELSE 3
                        END,
                        s.sector_confidence DESC,
                        s.cnpj_raiz
                    """,
                    (target_confirmed_only, target_confirmed_only),
                )
            rows = list(cur.fetchall() or [])

        jobs: list[CompanyJob] = []
        for r in rows:
            raiz = str(r.get("cnpj_raiz") or "").strip()
            if len(raiz) != 8 or not raiz.isdigit():
                continue
            # Never synthesize check digits. A missing observed establishment is
            # an explicit pending identity state; it must not erase the root.
            cnpj14 = str(r.get("representative_cnpj14") or "").strip() or raiz
            target_class = str(r.get("target_fit_class") or "")
            conf = float(r.get("target_fit_confidence") or 0.0)
            if target_class == TARGET_CONFIRMED and conf >= 0.8:
                tier, rank = "A1", int((1.0 - conf) * 1000)
            elif target_class == TARGET_CONFIRMED:
                tier, rank = "A2", int((1.0 - conf) * 1000)
            elif target_class == "TARGET_PROBABLE_RESEARCH":
                tier, rank = "strategic", int((1.0 - conf) * 1000)
            else:
                tier, rank = "universe", int((1.0 - conf) * 1000)
            jobs.append(
                CompanyJob(
                    cnpj14=cnpj14,
                    razao_social=r.get("registry_razao_social"),
                    priority_tier=tier,
                    priority_rank=rank,
                    meta={
                        "company_key": r.get("company_key"),
                        "cnpj_raiz": raiz,
                        "representative_cnpj14": cnpj14 if len(cnpj14) == 14 else None,
                        "representative_establishment_observed": len(cnpj14) == 14,
                        "sector_class": r.get("sector_class"),
                        "sector_confidence": r.get("sector_confidence"),
                        "sector_version": r.get("sector_version"),
                        "sector_classifier_sha256": r.get("sector_classifier_sha256"),
                        "sector_input_fingerprint": r.get("sector_input_fingerprint"),
                        "sector_source_watermark": r.get("sector_source_watermark"),
                        "sector_computed_at": (
                            r.get("sector_computed_at").isoformat()
                            if hasattr(r.get("sector_computed_at"), "isoformat")
                            else r.get("sector_computed_at")
                        ),
                        "target_fit_class": target_class,
                        "target_fit_confidence": conf,
                        "target_fit_version": r.get("target_fit_version"),
                        "target_fit_classifier_sha": r.get("target_fit_classifier_sha"),
                        "target_fit_mode": mode,
                        "target_fit_input_fingerprint": r.get("target_fit_input_fingerprint"),
                        "target_fit_source_watermark": r.get("target_fit_source_watermark"),
                        "target_fit_computed_at": (
                            r.get("target_fit_computed_at").isoformat()
                            if hasattr(r.get("target_fit_computed_at"), "isoformat")
                            else r.get("target_fit_computed_at")
                        ),
                        "razao_social": r.get("registry_razao_social"),
                        "nome_fantasia": r.get("registry_nome_fantasia"),
                        "registry_source": r.get("registry_source"),
                        "registry_source_version": r.get("registry_source_version"),
                        "registry_source_date": (
                            r.get("registry_source_date").isoformat()
                            if hasattr(r.get("registry_source_date"), "isoformat")
                            else r.get("registry_source_date")
                        ),
                        "source": "continuous_construction_universe",
                    },
                )
            )
        return jobs
    finally:
        conn.close()


def load_confirmed_jobs_from_dsn(
    dsn: str,
    *,
    include_probable: bool = True,
) -> list[CompanyJob]:
    """Compatibility alias; target-fit no longer limits enrichment scope."""
    _ = include_probable
    return load_construction_jobs_from_dsn(dsn)


def load_attempted_keys(checkpoint_path: Path) -> set[str]:
    if not checkpoint_path.is_file():
        return set()
    try:
        data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    done = set(data.get("completed_cnpjs") or [])
    # also map by root when stored
    for k in list(done):
        digits = "".join(c for c in str(k) if c.isdigit())
        if len(digits) >= 8:
            done.add(digits[:8])
    return {str(x) for x in done}


def migrate_legacy_checkpoint(output_dir: Path) -> bool:
    """Carry the old default resume ledger forward without overwriting state."""
    output_dir = Path(output_dir)
    destination = output_dir / "checkpoint.json"
    source = LEGACY_DEFAULT_OUT / "checkpoint.json"
    if output_dir != DEFAULT_OUT or destination.exists() or not source.is_file():
        return False
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def run_continuous_enrichment(
    dsn: str,
    *,
    cfg: ContinuousEnrichmentConfig | None = None,
    resolver_config: ResolverConfig | None = None,
) -> dict[str, Any]:
    """Advance contact enrichment over the full construction universe (resumable)."""
    cfg = cfg or ContinuousEnrichmentConfig()
    # Enforce before any I/O: 50 is PILOT_ACCEPTANCE_SAMPLE / MINIMUM_PILOT_ACCEPTANCE_SAMPLE only.
    if cfg.max_companies == MINIMUM_PILOT_ACCEPTANCE_SAMPLE:
        raise ValueError(
            f"Refuse max_companies={MINIMUM_PILOT_ACCEPTANCE_SAMPLE}: that value is "
            "MINIMUM_PILOT_ACCEPTANCE_SAMPLE / PILOT_ACCEPTANCE_SAMPLE only, not "
            "reservoir capacity. Omit max_companies for full continuous enrichment."
        )
    assert_not_pilot_as_capacity(cfg.max_companies, context="enrich-continuous")
    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if cfg.resume:
        migrate_legacy_checkpoint(out)

    jobs = load_construction_jobs_from_dsn(dsn)
    construction_keys = list(dict.fromkeys(str((j.meta or {}).get("cnpj_raiz") or j.cnpj14[:8]) for j in jobs))

    rcfg = resolver_config or ResolverConfig(
        allow_network=cfg.allow_network,
        fixtures_dir=cfg.fixtures_dir,
        apply_ownership=True,
    )
    runner = EnrichmentBatchRunner(
        output_dir=out,
        resolver_config=rcfg,
        run_id=f"continuous-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
    )
    runnable_jobs = [job for job in jobs if bool((job.meta or {}).get("representative_establishment_observed"))]
    summary = runner.run(
        runnable_jobs,
        resume=cfg.resume,
        max_companies=cfg.max_companies,
    )

    # Coverage closed sum from jobs + checkpoint
    ckpt = out / "checkpoint.json"
    attempted_raw = load_attempted_keys(ckpt)
    # normalize attempted to roots
    attempted_roots: set[str] = set()
    for a in attempted_raw:
        d = "".join(c for c in a if c.isdigit())
        if len(d) >= 8:
            attempted_roots.add(d[:8])
        else:
            attempted_roots.add(str(a))

    metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
    # Honest discovery: offline/no-network runs with zero web queries are NOT
    # contact discovery — they are structure/checkpoint passes only.
    web_queries = int(metrics.get("web_queries_total") or 0)
    pages = int(metrics.get("pages_fetched_total") or 0)
    network_discovery = bool(cfg.allow_network) and (web_queries > 0 or pages > 0)
    # Without network discovery, attempted_keys stay empty for coverage rates
    # (never_attempted = all CONFIRMED). Checkpoint still tracks resume state.
    discovery_attempted = list(attempted_roots) if network_discovery else []
    rejection_reasons = {
        "no_email_found": int(metrics.get("companies_without_contact") or 0) if network_discovery else 0,
        "identity_rejected": 0,
        "third_party_rejected": int(metrics.get("third_party_rejected") or 0),
        "mailbox_purpose_rejected": 0,
        "provenance_rejected": 0,
        "network_failure": int(metrics.get("timeouts") or 0) + int(metrics.get("http_429") or 0),
        "crawl_failure": 0,
        "no_official_domain": 0,
    }
    if isinstance(metrics.get("rejected_by_primary_reason"), dict):
        for k, v in metrics["rejected_by_primary_reason"].items():
            rejection_reasons[str(k).lower()] = int(v)
    # Do NOT invent per-key real/owned/ESR from count slices — those require
    # evaluate_email_send_ready on real contact rows (see rebuild_national_funnel).
    coverage = measure_contact_coverage(
        population_keys=construction_keys,
        attempted_keys=discovery_attempted,
        real_email_keys=[],
        company_owned_keys=[],
        identity_safe_keys=[],
        email_send_ready_keys=[],
        rejection_reasons=rejection_reasons,
        population_name="CONSTRUCTION_UNIVERSE",
    )
    coverage["network_discovery"] = network_discovery
    coverage["offline_structure_pass"] = not network_discovery
    coverage["checkpoint_completed_cnpjs"] = len(attempted_roots)
    coverage["note_honest"] = (
        "EMAIL_SEND_READY / identity-safe not inferred from batch counters. "
        "Use rebuild_national_funnel harvest+evaluate_email_send_ready for ESR."
    )

    # Per-root terminal discovery states only for companies actually attempted
    # under network discovery. Unattempted roots remain outside the partition
    # (never_attempted in measure_terminal_coverage).
    terminal_states = []
    # Do NOT stamp DEFAULT_SOURCE_LADDER without proof — only record adapters
    # actually used by the enrich batch (from summary / per-company files when present).
    for root in construction_keys:
        did_attempt = root in attempted_roots and network_discovery
        if not did_attempt:
            continue
        # Checkpoint completion alone ≠ full source ladder. Sources are unknown
        # here; mark retry until merge with process harvest + real adapters.
        st = classify_contact_terminal(
            cnpj_raiz=root,
            sources_attempted=["network_enrich_checkpoint"],
            network_discovery=True,
            ladder_complete=False,
            email_candidates=0,
            email_send_ready=0,
            meta={"from": "continuous_from_target_fit", "honest": "no_fake_full_ladder"},
        )
        terminal_states.append(st)
    terminal_cov = measure_terminal_coverage(
        terminal_states,
        population_total=len(construction_keys),
        population_name="CONSTRUCTION_UNIVERSE",
    )
    terminals_path = out / "contact-discovery-terminals.jsonl"
    with terminals_path.open("w", encoding="utf-8") as fh:
        for st in terminal_states:
            fh.write(json.dumps(st.as_dict(), ensure_ascii=False) + "\n")

    report = {
        "schema": "confenge.continuous_contact_enrichment.v1",
        "as_of": _utcnow(),
        "construction_universe_jobs": len(construction_keys),
        "representative_establishment_jobs": len(runnable_jobs),
        "representative_establishment_pending": len(jobs) - len(runnable_jobs),
        "max_companies_bound": cfg.max_companies,
        "summary": summary,
        "contact_coverage": coverage,
        "contact_terminal_coverage": terminal_cov,
        "terminals_path": str(terminals_path),
        "output_dir": str(out),
        "note": (
            "Continuous enrichment over CONSTRUCTION_UNIVERSE; target-fit controls priority/send, not inclusion. "
            f"PILOT_ACCEPTANCE_SAMPLE={MINIMUM_PILOT_ACCEPTANCE_SAMPLE} is quality-only."
        ),
    }
    (out / "continuous-coverage.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    (out / "contact-terminal-coverage.json").write_text(
        json.dumps(terminal_cov, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info(
        "continuous enrichment construction=%s attempted_rate=%s esr=%s",
        coverage.get("population_total"),
        coverage.get("contact_discovery_attempt_rate"),
        coverage.get("email_send_ready"),
    )
    return report
