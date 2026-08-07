"""End-to-end CONFENGE outreach pipeline (no manual JSON between stages)."""

from __future__ import annotations

import json
import resource
import subprocess
import time
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, UTC
from pathlib import Path
from typing import Any

from scripts.confenge_account_intelligence.pipeline import process_batch
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
from scripts.confenge_universe import DEFAULT_JSONL_NAME, DEFAULT_MANIFEST_NAME
from scripts.confenge_universe.pipeline import run_universe_build
from scripts.warmbly_bridge.export import ExportConfig, export_outreach


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"],
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
    include_dnc_in_sample: bool = True
    feed_limit: int | None = None


@dataclass
class PipelineResult:
    ok: bool
    out_dir: str
    stages: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    manifest_path: str | None = None


def run_pipeline(cfg: PipelineConfig) -> PipelineResult:
    """Execute UNIVERSE → SAMPLE → INTEL → CONTACTS → FEED."""
    started = time.monotonic()
    as_of = cfg.as_of or date.today()
    out = Path(cfg.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    dirs = {
        "universe": out / "01_universe",
        "sample": out / "02_downstream_sample",
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
    stages: dict[str, Any] = {
        "pipeline_id": PIPELINE_ID,
        "module_version": MODULE_VERSION,
        "repo_sha": repo_sha,
        "as_of": as_of.isoformat(),
        "started_at": _utcnow(),
        "limit_downstream": cfg.limit_downstream,
        "max_workers": cfg.max_workers,
        "max_rows_universe": cfg.max_rows,
        "sampling": bool(cfg.max_rows is not None),
    }

    try:
        # ── 1. Universe ──────────────────────────────────────────────────
        universe_jsonl = dirs["universe"] / DEFAULT_JSONL_NAME
        universe_manifest = dirs["universe"] / DEFAULT_MANIFEST_NAME
        if cfg.skip_universe and universe_jsonl.is_file():
            uni_meta: dict[str, Any] = {
                "ok": True,
                "skipped": True,
                "jsonl_path": str(universe_jsonl),
                "manifest_path": str(universe_manifest) if universe_manifest.is_file() else None,
            }
        else:
            uni_meta = run_universe_build(
                as_of=as_of,
                dsn=cfg.dsn,
                csv_path=cfg.csv_path,
                out_dir=dirs["universe"],
                max_rows=cfg.max_rows,
                dnc_path=cfg.dnc_path,
            )
            universe_jsonl = Path(uni_meta.get("jsonl_path") or universe_jsonl)
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
            )
            if k in uni_meta
        }

        universe_rows = _read_jsonl(universe_jsonl)
        stages["universe_row_count"] = len(universe_rows)

        # ── 2. Diverse downstream sample ─────────────────────────────────
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
            "profile_counts": profile_counts,
            "note": (
                "limit_downstream bounds only this sample and subsequent expensive stages; "
                "universe discovery is independent."
            ),
        }

        # ── 3. Account intelligence ──────────────────────────────────────
        intel_inputs = [
            universe_row_to_intelligence_input(r, as_of=as_of.isoformat()) for r in sample_rows
        ]
        intel_input_path = dirs["intel"] / "intelligence-inputs.jsonl"
        _write_jsonl(intel_input_path, intel_inputs)

        dossiers = process_batch(
            intel_inputs,
            max_workers=cfg.max_workers,
            as_of=as_of.isoformat(),
        )
        intel_raw_path = dirs["intel"] / "confenge-account-intelligence-v1.jsonl"
        _write_jsonl(intel_raw_path, dossiers)

        bridge_intel = [intelligence_dossier_to_bridge_row(d) for d in dossiers]
        bridge_intel_path = dirs["bridge_inputs"] / "account_intelligence.jsonl"
        _write_jsonl(bridge_intel_path, bridge_intel)

        service_dist: dict[str, int] = {}
        for d in dossiers:
            ps = d.get("primary_service") if isinstance(d.get("primary_service"), dict) else {}
            sid = str(ps.get("service_id") or "unknown")
            service_dist[sid] = service_dist.get(sid, 0) + 1
        stages["account_intelligence"] = {
            "input_path": str(intel_input_path),
            "raw_path": str(intel_raw_path),
            "bridge_path": str(bridge_intel_path),
            "count": len(dossiers),
            "service_distribution": dict(sorted(service_dist.items(), key=lambda x: (-x[1], x[0]))),
        }

        # ── 4. Contact resolution ────────────────────────────────────────
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
            adapters = default_adapters(
                web_search_enabled=bool(cfg.enable_web_search),
                registry_prefer_network=bool(cfg.allow_network),
            )
            resolver = ContactResolver(
                ResolverConfig(
                    service_context=svc_ctx,
                    adapters=adapters,
                    cache=cache,
                    allow_network=cfg.allow_network,
                    fixtures_dir=cfg.contact_fixtures_dir or cfg.fixtures_dir,
                    max_workers=cfg.max_workers,
                )
            )
            cnpjs = [
                "".join(ch for ch in str(r.get("cnpj14") or r.get("cnpj") or "") if ch.isdigit())
                for r in sample_rows
            ]
            cnpjs = [c for c in cnpjs if c]
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

        bridge_contacts_path = dirs["bridge_inputs"] / "contacts.jsonl"
        _write_jsonl(bridge_contacts_path, bridge_contacts)
        stages["contacts"] = {
            **contact_meta,
            "bridge_path": str(bridge_contacts_path),
        }

        # ── 5. Bridge universe inputs + export ───────────────────────────
        bridge_universe = [
            universe_row_for_bridge(r, rank=i + 1) for i, r in enumerate(sample_rows)
        ]
        bridge_universe_path = dirs["bridge_inputs"] / "universe.jsonl"
        _write_jsonl(bridge_universe_path, bridge_universe)

        export_cfg = ExportConfig(
            universe=bridge_universe_path,
            account_intelligence=bridge_intel_path,
            contacts=bridge_contacts_path,
            out_dir=dirs["feed"],
            limit=cfg.feed_limit,
            repo_sha=repo_sha,
        )
        export_result = export_outreach(export_cfg)
        stages["feed"] = export_result

        # ── 6. Stage reports ─────────────────────────────────────────────
        stages["finished_at"] = _utcnow()
        stages["elapsed_seconds"] = round(time.monotonic() - started, 3)
        stages["peak_rss_mb"] = _peak_rss_mb()
        uni_counts = (stages.get("universe") or {}).get("counts") or {}
        stages["full_scale_universe"] = bool(
            uni_counts.get("full_scale")
            if "full_scale" in uni_counts
            else (not cfg.max_rows and bool(cfg.dsn) and not cfg.csv_path)
        )

        report_path = dirs["reports"] / "pipeline-manifest.json"
        report_path.write_text(
            json.dumps(stages, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
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
