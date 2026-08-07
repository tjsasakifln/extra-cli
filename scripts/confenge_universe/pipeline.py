"""Orchestrate stream → aggregate → classify → eligibility → score → export."""

from __future__ import annotations

import subprocess
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.commercial_leads.contract_relevance import classify_contract_relevance
from scripts.confenge_universe import (
    DNC,
    ELIGIBLE,
    MODULE_VERSION,
    NOT_CONSTRUCTION,
    RULE_VERSION,
    SCHEMA_VERSION,
)
from scripts.confenge_universe.aggregate import (
    EntityBucket,
    UniverseAggregator,
    bucket_to_portfolio_dict,
)
from scripts.confenge_universe.construction import assess_construction
from scripts.confenge_universe.eligibility import (
    decide_eligibility,
    is_dnc_cnpj,
    load_dnc_set,
)
from scripts.confenge_universe.export import (
    build_manifest,
    default_output_paths,
    write_jsonl_stream,
    write_manifest,
)
from scripts.confenge_universe.identity import Identity
from scripts.confenge_universe.scoring import compute_priority_score
from scripts.confenge_universe.source import (
    SourceConfig,
    iter_contract_rows,
    iter_contracts_keyset,
    mask_dsn,
    resolve_source,
    source_fingerprint,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_sha(root: Path | None = None) -> str:
    r = root or _PROJECT_ROOT
    try:
        out = subprocess.check_output(  # noqa: S603
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=str(r),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip()
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return "unknown"


def _representative_identity(bucket: EntityBucket) -> Identity | None:
    if not bucket.identities:
        return None
    # Prefer matriz
    for c14, ident in sorted(bucket.identities.items()):
        if len(c14) == 14 and c14[8:12] == "0001":
            return ident
    return bucket.identities[sorted(bucket.identities.keys())[0]]


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def finalize_bucket(
    bucket: EntityBucket,
    *,
    as_of: date,
    dnc_set: set[str],
    registry: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return (universe_record_or_None, exclusion_or_meta)."""
    identity = _representative_identity(bucket)
    if identity is None:
        excl = {
            "entity_key": bucket.entity_key.key,
            "cnpj_root": bucket.cnpj_root,
            "outreach_eligibility": "UNKNOWN_IDENTITY",
            "reason": "no_identity",
        }
        return None, excl

    reg = None
    if registry and identity.cnpj14:
        reg = registry.get(identity.cnpj14)

    cnae = (reg or {}).get("cnae_principal") if reg else None
    nome_fantasia = (reg or {}).get("nome_fantasia") if reg else None
    situacao = (reg or {}).get("situacao_cadastral") if reg else None
    mun = (reg or {}).get("municipio") if reg else None
    uf_reg = (reg or {}).get("uf") if reg else None

    construction = assess_construction(
        razao_social=identity.razao_social,
        nome_fantasia=nome_fantasia,
        contracts=list(bucket.contracts_for_classify),
        cnae_principal=cnae,
    )

    dnc = is_dnc_cnpj(identity.cnpj14, identity.cnpj_root, dnc_set)
    elig = decide_eligibility(
        identity=identity,
        construction=construction,
        dnc=dnc,
    )

    portfolio = bucket_to_portfolio_dict(bucket)
    portfolio["object_categories"] = list(construction.object_categories)

    last_d = _parse_date(portfolio.get("last_contract_date"))
    score = compute_priority_score(
        construction=construction,
        contract_count=bucket.contract_count,
        contract_count_recent=bucket.contract_count_recent,
        value_total=bucket.value_total,
        value_recent=bucket.value_recent,
        n_ufs=len(bucket.ufs),
        n_orgaos=len(bucket.orgaos),
        last_contract_date=last_d,
        as_of=as_of,
        active_count=bucket.active_count,
    )

    if not elig.in_universe:
        excl = {
            "entity_key": bucket.entity_key.key,
            "cnpj_root": bucket.cnpj_root,
            "cnpj14": identity.cnpj14,
            "razao_social": identity.razao_social,
            "outreach_eligibility": elig.outreach_eligibility,
            "reason": elig.reason,
            "sector_fit": construction.sector_fit,
            "construction_evidence": construction.as_dict(),
        }
        return None, excl

    uf = uf_reg or (sorted(bucket.ufs)[0] if bucket.ufs else None)
    municipio = mun or (sorted(bucket.municipios)[0] if bucket.municipios else None)

    record = {
        "schema_version": SCHEMA_VERSION,
        "entity_key": bucket.entity_key.key,
        "cnpj14": portfolio.get("representative_cnpj14") or identity.cnpj14,
        "cnpj_root": bucket.cnpj_root,
        "razao_social": identity.razao_social,
        "nome_fantasia": nome_fantasia,
        "uf": uf,
        "municipio": municipio,
        "situacao_cadastral": situacao,
        "activity_classes": [construction.activity_class],
        "construction_evidence": construction.as_dict(),
        "portfolio": portfolio,
        "temporal_signals": {
            "first_contract_date": portfolio.get("first_contract_date"),
            "last_contract_date": portfolio.get("last_contract_date"),
            "active_contract_count": portfolio.get("active_contract_count"),
            "contract_count_recent": portfolio.get("contract_count_recent"),
            "note": (
                "Temporal signals are observational context for approach timing; "
                "they are not claims of contractual pain, atraso, reajuste, or Lei 14.133."
            ),
        },
        "priority_score": score.score,
        "priority_reason": score.reason,
        "priority_components": score.components,
        "outreach_eligibility": elig.outreach_eligibility,
        "eligibility_reason": elig.reason,
        "independent_brand": bucket.independent_brand,
        "epistemic": {
            "priority_score_class": score.epistemic_class,
            "construction_class": construction.epistemic_class,
            "provenance": [
                {"field": "priority_score", "class": "INFERENCE", "source": score.provenance},
                {
                    "field": "construction_evidence",
                    "class": construction.epistemic_class,
                    "source": "commercial_leads.sector_fit+contract_relevance",
                },
            ],
        },
        "rule_version": RULE_VERSION,
        "module_version": MODULE_VERSION,
    }
    # Free classify buffer after finalize to bound memory
    bucket.contracts_for_classify.clear()
    return record, {
        "entity_key": bucket.entity_key.key,
        "outreach_eligibility": elig.outreach_eligibility,
        "in_universe": True,
    }


def _identity_root_exclusions(agg: UniverseAggregator) -> dict[str, dict[str, Any]]:
    """Collapse row-level identity failures into root-level exclusion keys when possible."""
    by_key: dict[str, dict[str, Any]] = {}
    for sample in agg.identity_excluded_rows:
        raw = sample.get("tax_id") or sample.get("name") or "unknown"
        key = f"identity:{raw}"
        code = sample.get("code") or "INVALID_IDENTITY"
        by_key[key] = {
            "entity_key": key,
            "cnpj_root": None,
            "outreach_eligibility": code,
            "reason": sample.get("detail") or code,
        }
    return by_key


def run_universe_build(
    *,
    as_of: date | None = None,
    dsn: str | None = None,
    csv_path: str | None = None,
    row_iter: Iterator[dict[str, Any]] | None = None,
    out_dir: str | Path,
    batch_size: int = 2000,
    max_rows: int | None = None,
    min_contract_value: float = 0.0,
    uf: str | None = None,
    dnc_path: str | None = None,
    dnc_set: set[str] | None = None,
    enable_independent_brand: bool = True,
    registry: dict[str, dict[str, Any]] | None = None,
    source_meta_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build national construction universe from streamable contract source.

    Production: pass dsn (or env) without max_rows for full scale.
    Tests/fixtures: pass csv_path or row_iter.
    """
    as_of_d = as_of or date.today()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    jsonl_path, manifest_path = default_output_paths(out)

    dnc = set(dnc_set or set())
    dnc |= load_dnc_set(dnc_path)

    cfg: SourceConfig | None = None
    source_meta: dict[str, Any]

    if row_iter is not None:
        batches: Iterator[list[dict[str, Any]]] = iter_contract_rows(
            row_iter, batch_size=batch_size
        )
        source_meta = {
            "mode": "iterator",
            "as_of": as_of_d.isoformat(),
            "note": "in-memory/fixture iterator",
        }
    else:
        cfg = resolve_source(dsn, csv_path=csv_path)
        batches = iter_contracts_keyset(
            cfg,
            min_contract_value=min_contract_value,
            uf=uf,
            batch_size=batch_size,
            max_rows=max_rows,
        )
        source_meta = source_fingerprint(cfg, as_of=as_of_d)
        if max_rows is not None:
            source_meta["sampling"] = {
                "max_rows": max_rows,
                "note": "Diagnostic sample — NOT full-scale population proof",
            }

    if source_meta_extra:
        source_meta = {**source_meta, **source_meta_extra}

    agg = UniverseAggregator(
        as_of=as_of_d, enable_independent_brand=enable_independent_brand
    )

    peak_batch = 0
    for batch in batches:
        peak_batch = max(peak_batch, len(batch))
        agg.ingest_batch(batch, relevance_fn=classify_contract_relevance)

    records: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    elig_breakdown: Counter[str] = Counter()
    excl_breakdown: Counter[str] = Counter()

    # Roots/entities that entered aggregation (valid identity)
    input_entity_keys = set(agg.buckets.keys())

    for bucket in agg.all_buckets():
        rec, meta = finalize_bucket(
            bucket, as_of=as_of_d, dnc_set=dnc, registry=registry
        )
        if rec is not None:
            records.append(rec)
            elig_breakdown[str(rec["outreach_eligibility"])] += 1
        else:
            exclusions.append(meta)
            excl_breakdown[str(meta.get("outreach_eligibility") or "UNKNOWN")] += 1

    # Identity failures that never formed buckets: count as exclusion units
    # Use unique samples as approximate exclusion entities for reconciliation.
    # For strict root recon we count: len(buckets) + identity_exclusion_entities.
    identity_excl = _identity_root_exclusions(agg)
    for key, meta in identity_excl.items():
        if key not in input_entity_keys:
            exclusions.append(meta)
            excl_breakdown[str(meta.get("outreach_eligibility") or "INVALID_IDENTITY")] += 1

    # Reconciliation on operational entity keys with valid identity:
    # every finalized bucket is either eligible (in universe) or justified exclusion.
    n_input_entities = len(input_entity_keys)
    n_eligibles = len(records)
    # Prefer exact: eligibles + exclusions that came from buckets
    bucket_excl = [
        e for e in exclusions if not str(e.get("entity_key", "")).startswith("identity:")
    ]
    n_excl_from_buckets = len(bucket_excl)
    recon_ok = n_input_entities == n_eligibles + n_excl_from_buckets

    jsonl_meta = write_jsonl_stream(records, jsonl_path)
    counts = {
        "input_contract_rows": agg.stats["input_contract_rows"],
        "input_supplier_roots": n_input_entities,
        "eligibles": n_eligibles,
        "exclusions": n_excl_from_buckets,
        "identity_row_exclusions": agg.stats["identity_exclusions"],
        "identity_exclusion_breakdown": dict(agg.stats["identity_exclusion_breakdown"]),
        "eligibility_breakdown": dict(elig_breakdown),
        "exclusion_breakdown": dict(excl_breakdown),
        "dnc_in_universe": elig_breakdown.get(DNC, 0),
        "eligible_for_outreach": elig_breakdown.get(ELIGIBLE, 0),
        "not_construction": excl_breakdown.get(NOT_CONSTRUCTION, 0),
        "peak_batch_size": peak_batch,
        "batch_size_config": batch_size,
        "max_rows": max_rows,
        "full_scale": max_rows is None and row_iter is None,
    }
    sha = git_sha()
    manifest = build_manifest(
        as_of=as_of_d,
        repo_sha=sha,
        source_meta=source_meta,
        counts=counts,
        jsonl_meta=jsonl_meta,
        extra={
            "built_at": utc_now(),
            "dsn_masked": mask_dsn(cfg.dsn) if cfg and cfg.dsn else None,
            "reconciliation_bucket_ok": recon_ok,
            "full_scale_command": (
                "python3 -m scripts.confenge_universe build "
                "--out output/confenge_universe "
                "--dsn \"$LOCAL_DATALAKE_DSN\" "
                "# omit --max-rows for full national scan"
            ),
        },
    )
    # Force recon fields from bucket invariant
    manifest["counts"]["reconciliation"] = {
        "formula": "input_supplier_roots = eligibles + exclusions",
        "input_supplier_roots": n_input_entities,
        "eligibles": n_eligibles,
        "exclusions": n_excl_from_buckets,
        "ok": recon_ok,
    }
    write_manifest(manifest, manifest_path)

    return {
        "status": "PASS" if recon_ok else "FAIL_RECONCILIATION",
        "as_of": as_of_d.isoformat(),
        "repo_sha": sha,
        "jsonl_path": str(jsonl_path),
        "manifest_path": str(manifest_path),
        "counts": counts,
        "records": records,
        "exclusions": exclusions,
        "manifest": manifest,
        "reconciliation_ok": recon_ok,
    }
