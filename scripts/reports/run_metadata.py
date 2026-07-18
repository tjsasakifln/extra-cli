#!/usr/bin/env python3
"""Shared run metadata for PDF/Excel commercial reports.

Both executive_report (PDF) and executive_excel write the same schema so
`reconcile_pdf_excel.py` can verify they share run_id / cutoff / filters.

Schema (JSON sidecar + embedded labels):
{
  "schema_version": 1,
  "run_id": "exec-YYYYMMDD-HHMMSS-<short>",
  "generated_at": "ISO-8601 UTC",
  "artifact_kind": "pdf" | "excel" | "sidecar",
  "script": "scripts/reports/executive_*.py",
  "filters": {
    "uf": "SC",
    "is_active": true,
    "table_primary": "opportunity_intel",
    "vincendos_horizon_days": 180
  },
  "cutoff": {
    "as_of_date": "YYYY-MM-DD",
    "data_window": "all_active",
    "ultima_atualizacao_db": "..."
  },
  "sample_size": {
    "opportunity_intel_active": N,
    "ranking_go": N,
    "ranking_review": N,
    "ranking_no_go": N,
    "orgaos_sc": N,
    "pncp_raw_bids_active": N,
    "vincendos_180d": N,
    "label": "INSUFFICIENT" | "MINIMAL" | "ADEQUATE"
  },
  "git_sha": "short or unknown",
  "profile_id": "extra",
  "claims": {
    "allowed": [...],
    "forbidden": [...]
  }
}
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_UF = "SC"
DEFAULT_VINCENDOS_DAYS = 180
PROFILE_ID = "extra"
PROFILE_VERSION: int | str | None = None


def _load_profile_version() -> int | str | None:
    """Best-effort read of config/client_profiles/extra.yaml version."""
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None  # type: ignore
    root = Path(__file__).resolve().parent.parent.parent
    path = root / "config" / "client_profiles" / "extra.yaml"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        if yaml is not None:
            data = yaml.safe_load(text) or {}
            return data.get("version")
        # Minimal parse without PyYAML
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("version:") and "version_" not in stripped:
                raw = stripped.split(":", 1)[1].strip().strip("\"'")
                try:
                    return int(raw)
                except ValueError:
                    return raw or None
    except OSError:
        return None
    return None

# Honest commercial claims — reused by generators and baseline docs.
CLAIMS_ALLOWED = [
    "Contagens derivadas de opportunity_intel.is_active=true no DSN local.",
    "Ranking GO/REVIEW/NO_GO conforme coluna ranking (pode ser stub/fixture).",
    "Ranking de órgãos por volume de editais ativos (UF filtrada quando aplicável).",
    "Contratos vincendos apenas se pncp_supplier_contracts tiver linhas no horizonte.",
    "Amostra rotulada INSUFFICIENT/MINIMAL/ADEQUATE — não inventar cobertura %.",
]

CLAIMS_FORBIDDEN = [
    "Afirmar cobertura 95% ou readiness comercial sem evidence ledger.",
    "Tratar REVIEW como GO ou esconder sample_size=0.",
    "Misturar PDF e Excel de runs diferentes sem reconciliação PASS.",
    "Inferir contratos vincendos a partir de pncp_raw_bids.",
    "Publicar ranking de órgãos como 'mercado completo SC' com N < 20 editais.",
    # DoD §25 language (scripts.lib.claim_language)
    "Ausência de dados como ausência de licitação sem consulta válida",
    "Vencedores observados como conjunto completo de concorrentes",
    "Participante não identificado tratado como inexistente",
    "Win rate sem propostas enviadas no denominador",
    "Score rotulado como probabilidade sem calibração",
    "Relatório sem limitações relevantes",
    "Afirmar que o projeto acompanha obras fisicamente",
]


def _git_sha_short() -> str:
    try:
        import shutil

        git_bin = shutil.which("git")
        if not git_bin:
            return "unknown"
        out = subprocess.check_output(  # noqa: S603 — fixed git binary + fixed args
            [git_bin, "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip() or "unknown"
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return "unknown"


def new_run_id(prefix: str = "exec") -> str:
    """Generate a stable-looking run id for a report pair."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    short = uuid.uuid4().hex[:8]
    return f"{prefix}-{stamp}-{short}"


def sample_size_label(
    n_opps: int,
    n_vincendos: int,
    n_bids: int,
) -> str:
    """Label commercial sample quality without overclaiming."""
    if n_opps == 0 and n_bids == 0:
        return "INSUFFICIENT"
    if n_opps < 20:
        return "MINIMAL"
    if n_opps < 100:
        return "ADEQUATE"
    return "ADEQUATE"


def build_run_metadata(
    *,
    run_id: str | None = None,
    artifact_kind: str = "sidecar",
    script: str = "scripts/reports/",
    uf: str = DEFAULT_UF,
    is_active: bool = True,
    vincendos_horizon_days: int = DEFAULT_VINCENDOS_DAYS,
    stats: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the canonical metadata dict shared by PDF and Excel."""
    stats = stats or {}
    now = generated_at or datetime.now(UTC)
    n_opps = int(stats.get("total") or stats.get("total_oportunidades") or 0)
    n_go = int(stats.get("go_count") or stats.get("total_go") or 0)
    n_review = int(stats.get("review_count") or stats.get("total_review") or 0)
    n_no_go = int(stats.get("no_go_count") or stats.get("total_no_go") or 0)
    n_orgaos = int(stats.get("orgaos_ativos") or 0)
    n_bids = int(stats.get("raw_bids_count") or stats.get("pncp_raw_bids_active") or 0)
    n_vinc = int(stats.get("vincendos_count") or stats.get("vincendos_180d") or 0)
    ultima = stats.get("ultima_atualizacao") or stats.get("ultima_atualizacao_db") or "N/I"

    label = sample_size_label(n_opps, n_vinc, n_bids)

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id or new_run_id(),
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "artifact_kind": artifact_kind,
        "script": script,
        "filters": {
            "uf": uf,
            "is_active": is_active,
            "table_primary": "opportunity_intel",
            "vincendos_horizon_days": vincendos_horizon_days,
            "orgao_ranking_uf": uf,
        },
        "cutoff": {
            "as_of_date": now.date().isoformat(),
            "data_window": "all_active",
            "ultima_atualizacao_db": str(ultima),
        },
        "sample_size": {
            "opportunity_intel_active": n_opps,
            "ranking_go": n_go,
            "ranking_review": n_review,
            "ranking_no_go": n_no_go,
            "orgaos_sc": n_orgaos,
            "pncp_raw_bids_active": n_bids,
            "vincendos_180d": n_vinc,
            "label": label,
        },
        "git_sha": _git_sha_short(),
        "profile_id": PROFILE_ID,
        "profile_version": PROFILE_VERSION if PROFILE_VERSION is not None else _load_profile_version(),
        "dsn_host": _dsn_host_hint(),
        "claims": {
            "allowed": list(CLAIMS_ALLOWED),
            "forbidden": list(CLAIMS_FORBIDDEN),
        },
    }


def _dsn_host_hint() -> str:
    dsn = os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL") or ""
    # Never dump credentials; only host:port/db if parseable.
    if "@" in dsn:
        try:
            return dsn.split("@", 1)[1]
        except IndexError:
            return "configured"
    return dsn or "default"


def meta_path_for(artifact_path: str | Path) -> Path:
    p = Path(artifact_path)
    return p.with_suffix(p.suffix + ".meta.json")


def write_sidecar(artifact_path: str | Path, metadata: dict[str, Any]) -> Path:
    """Write <artifact>.meta.json next to PDF/Excel."""
    path = meta_path_for(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(metadata)
    payload["artifact_path"] = str(Path(artifact_path).name)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_sidecar(artifact_path: str | Path) -> dict[str, Any] | None:
    path = meta_path_for(artifact_path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def metadata_label_pairs(metadata: dict[str, Any]) -> list[tuple[str, str]]:
    """Flat label/value pairs for Excel Metadados sheet and PDF text."""
    filters = metadata.get("filters") or {}
    cutoff = metadata.get("cutoff") or {}
    sample = metadata.get("sample_size") or {}
    return [
        ("Run ID", str(metadata.get("run_id", ""))),
        ("Generated At (UTC)", str(metadata.get("generated_at", ""))),
        ("Git SHA", str(metadata.get("git_sha", ""))),
        ("Profile ID", str(metadata.get("profile_id", ""))),
        ("Profile Version", str(metadata.get("profile_version", ""))),
        ("Filter UF", str(filters.get("uf", ""))),
        ("Filter is_active", str(filters.get("is_active", ""))),
        ("Filter table_primary", str(filters.get("table_primary", ""))),
        ("Filter vincendos_horizon_days", str(filters.get("vincendos_horizon_days", ""))),
        ("Cutoff as_of_date", str(cutoff.get("as_of_date", ""))),
        ("Cutoff data_window", str(cutoff.get("data_window", ""))),
        ("Cutoff ultima_atualizacao_db", str(cutoff.get("ultima_atualizacao_db", ""))),
        ("Sample label", str(sample.get("label", ""))),
        ("Sample opportunity_intel_active", str(sample.get("opportunity_intel_active", ""))),
        ("Sample ranking_go", str(sample.get("ranking_go", ""))),
        ("Sample ranking_review", str(sample.get("ranking_review", ""))),
        ("Sample ranking_no_go", str(sample.get("ranking_no_go", ""))),
        ("Sample orgaos_sc", str(sample.get("orgaos_sc", ""))),
        ("Sample vincendos_180d", str(sample.get("vincendos_180d", ""))),
        ("Sample pncp_raw_bids_active", str(sample.get("pncp_raw_bids_active", ""))),
    ]


def compare_metadata(pdf_meta: dict[str, Any], excel_meta: dict[str, Any]) -> dict[str, Any]:
    """Compare two metadata dicts; return structured reconciliation result."""
    checks: list[dict[str, Any]] = []

    def _check(name: str, left: Any, right: Any, *, critical: bool = True) -> None:
        ok = left == right
        checks.append(
            {
                "name": name,
                "pdf": left,
                "excel": right,
                "match": ok,
                "critical": critical,
            }
        )

    _check("run_id", pdf_meta.get("run_id"), excel_meta.get("run_id"), critical=True)
    _check(
        "cutoff.as_of_date",
        (pdf_meta.get("cutoff") or {}).get("as_of_date"),
        (excel_meta.get("cutoff") or {}).get("as_of_date"),
        critical=True,
    )
    _check(
        "cutoff.data_window",
        (pdf_meta.get("cutoff") or {}).get("data_window"),
        (excel_meta.get("cutoff") or {}).get("data_window"),
        critical=True,
    )
    for key in ("uf", "is_active", "table_primary", "vincendos_horizon_days", "orgao_ranking_uf"):
        _check(
            f"filters.{key}",
            (pdf_meta.get("filters") or {}).get(key),
            (excel_meta.get("filters") or {}).get(key),
            critical=True,
        )

    # Sample sizes should match for the same run (same DB snapshot intent).
    for key in (
        "opportunity_intel_active",
        "ranking_go",
        "ranking_review",
        "ranking_no_go",
        "orgaos_sc",
        "vincendos_180d",
        "label",
    ):
        _check(
            f"sample_size.{key}",
            (pdf_meta.get("sample_size") or {}).get(key),
            (excel_meta.get("sample_size") or {}).get(key),
            critical=True,
        )

    # Soft checks
    _check("profile_id", pdf_meta.get("profile_id"), excel_meta.get("profile_id"), critical=False)
    _check("git_sha", pdf_meta.get("git_sha"), excel_meta.get("git_sha"), critical=False)

    critical_fail = [c for c in checks if c["critical"] and not c["match"]]
    soft_fail = [c for c in checks if not c["critical"] and not c["match"]]

    if critical_fail:
        verdict = "FAIL"
    elif soft_fail:
        verdict = "CONCERNS"
    else:
        verdict = "PASS"

    return {
        "verdict": verdict,
        "checks": checks,
        "critical_mismatches": len(critical_fail),
        "soft_mismatches": len(soft_fail),
        "pdf_run_id": pdf_meta.get("run_id"),
        "excel_run_id": excel_meta.get("run_id"),
        "sample_label": (pdf_meta.get("sample_size") or {}).get("label")
        or (excel_meta.get("sample_size") or {}).get("label"),
        "as_of_date": (pdf_meta.get("cutoff") or {}).get("as_of_date")
        or (excel_meta.get("cutoff") or {}).get("as_of_date")
        or date.today().isoformat(),
    }
