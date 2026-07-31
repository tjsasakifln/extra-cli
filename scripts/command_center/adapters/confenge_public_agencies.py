"""Adapter: CONFENGE public-agency vertical via target_router."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.command_center.adapters.base import (
    AdapterResult,
    DataMode,
    PreflightCheck,
    PreflightResult,
    SubprocessResult,
    check_dir_writable,
    check_env_present,
    check_module_importable,
    check_postgres_optional,
    discover_artifacts,
    finalize_preflight,
    python_module_argv,
)
from scripts.command_center.config import git_sha


class ConfengePublicAgenciesAdapter:
    workflow_id = "workflow.confenge.public_agencies"
    capability_id = "confenge.public_agencies.cycle.run"
    canonical_module = "scripts.ops.confenge_commercial_target_router"

    def preflight(self, params: dict[str, Any], *, out_dir: Path) -> PreflightResult:
        checks: list[PreflightCheck] = [
            check_module_importable(self.canonical_module),
            check_module_importable("scripts.public_agency"),
            check_env_present("LOCAL_DATALAKE_DSN", required=True),
            check_postgres_optional("LOCAL_DATALAKE_DSN"),
            check_dir_writable(out_dir, name="dir:out"),
        ]
        limitations = [
            "Router canônico: confenge_commercial_target_router --target public-agencies.",
            "Classificação jurídica é preliminar e exige revisão humana.",
            "Sem auto-outreach; sem autoaceite DOD.",
            "run_mode default DRY_RUN no workbench.",
        ]
        return finalize_preflight(checks, capability_id=self.capability_id, limitations=limitations)

    def build_argv(self, params: dict[str, Any], *, out_dir: Path) -> list[str]:
        run_mode = str(params.get("run_mode") or "DRY_RUN")
        if run_mode not in {"RC", "LIVE", "DRY_RUN", "EXPERIMENTAL_SAMPLE"}:
            raise ValueError(f"run_mode inválido: {run_mode}")
        mode = str(params.get("mode") or params.get("public_agency_mode") or "REACTIVE_OPPORTUNITY")
        if mode not in {"REACTIVE_OPPORTUNITY", "PROACTIVE_INSTITUTIONAL_PROSPECT"}:
            raise ValueError(f"public_agency_mode inválido: {mode}")
        argv = python_module_argv(
            self.canonical_module,
            "--target",
            "public-agencies",
            "--run-mode",
            run_mode,
            "--public-agency-mode",
            mode,
            "--public-agency-out",
            str(out_dir / "public-agencies"),
        )
        if params.get("uf"):
            argv.extend(["--uf", str(params["uf"])])
        max_leads = params.get("max_public_agency_leads") or params.get("max_leads") or params.get("max_items")
        if max_leads is not None:
            argv.extend(["--max-public-agency-leads", str(int(max_leads))])
        if params.get("skip_migrations"):
            argv.append("--skip-migrations")
        if params.get("skip_persist"):
            argv.append("--skip-persist")
        if params.get("as_of"):
            argv.extend(["--as-of", str(params["as_of"])])
        return argv

    def interpret(
        self,
        params: dict[str, Any],
        *,
        out_dir: Path,
        proc: SubprocessResult,
        preflight: PreflightResult,
    ) -> AdapterResult:
        arts = discover_artifacts(out_dir)
        rows = _extract_agencies(arts)
        if rows:
            src = out_dir / "public_agencies.json"
            if not src.is_file():
                src.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                arts.append(src)
        status = "SUCCEEDED" if proc.exit_code == 0 else (
            "BLOCKED_DATA" if proc.exit_code == 2 else "FAILED"
        )
        limitations = list(preflight.limitations)
        if proc.exit_code != 0:
            limitations.append(f"Pipeline exit_code={proc.exit_code}")
        return AdapterResult(
            status=status,
            exit_code=proc.exit_code,
            data_mode=DataMode.REAL.value,
            argv=list(proc.argv),
            artifacts=arts,
            out_dir=out_dir,
            started_at=proc.started_at,
            finished_at=proc.finished_at,
            duration_ms=proc.duration_ms,
            code_sha=git_sha(),
            params_public={},
            preflight=preflight.to_dict(),
            limitations=limitations,
            coverage={"leads": len(rows), "uf": params.get("uf"), "mode": params.get("mode")},
            source_snapshots=[
                {"type": "pipeline", "module": self.canonical_module, "target": "public-agencies"}
            ],
            stdout_tail=proc.stdout[-4000:],
            stderr_tail=proc.stderr[-4000:],
            message=f"CONFENGE public agencies REAL exit={proc.exit_code}; {len(arts)} artefatos.",
            rows=rows,
            pipeline_status=status,
        )


def _extract_agencies(arts: list[Path]) -> list[dict[str, Any]]:
    for art in arts:
        if art.suffix.lower() != ".json":
            continue
        try:
            data = json.loads(art.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data
        if isinstance(data, dict):
            for key in ("leads", "agencies", "items", "rows", "orgaos"):
                val = data.get(key)
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    return val
    return []
