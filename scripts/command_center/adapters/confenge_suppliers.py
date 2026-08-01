"""Adapter: CONFENGE supplier commercial cycle via target_router."""

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


class ConfengeSuppliersAdapter:
    workflow_id = "workflow.confenge.suppliers"
    capability_id = "confenge.suppliers.cycle.run"
    canonical_module = "scripts.ops.confenge_commercial_target_router"

    def preflight(self, params: dict[str, Any], *, out_dir: Path) -> PreflightResult:
        checks: list[PreflightCheck] = [
            check_module_importable(self.canonical_module),
            check_module_importable("scripts.ops.confenge_commercial_cycle"),
            check_module_importable("scripts.company_registry"),
            check_env_present("LOCAL_DATALAKE_DSN", required=True),
            check_postgres_optional("LOCAL_DATALAKE_DSN"),
            check_dir_writable(out_dir, name="dir:out"),
        ]
        limitations = [
            "Router canônico: confenge_commercial_target_router --target suppliers.",
            "Cadastro oficial fail-closed quando CONFENGE_REQUIRE_OFFICIAL_REGISTRY=1.",
            "Sem envio de e-mail/WhatsApp; sem auto-outreach.",
            "run_mode default DRY_RUN no workbench até confirmação explícita de RC/LIVE.",
        ]
        return finalize_preflight(checks, capability_id=self.capability_id, limitations=limitations)

    def build_argv(self, params: dict[str, Any], *, out_dir: Path) -> list[str]:
        run_mode = str(params.get("run_mode") or "DRY_RUN")
        if run_mode not in {"RC", "LIVE", "DRY_RUN", "EXPERIMENTAL_SAMPLE"}:
            raise ValueError(f"run_mode inválido: {run_mode}")
        population_mode = str(params.get("population_mode") or "BOUNDED_SAMPLE")
        if population_mode not in {"BOUNDED_SAMPLE", "FULL_POPULATION"}:
            raise ValueError(f"population_mode inválido: {population_mode}")
        argv = python_module_argv(
            self.canonical_module,
            "--target",
            "suppliers",
            "--run-mode",
            run_mode,
            "--population-mode",
            population_mode,
            "--out",
            str(out_dir / "commercial"),
        )
        if params.get("uf"):
            argv.extend(["--uf", str(params["uf"])])
        if params.get("max_contracts") is not None:
            argv.extend(["--max-contracts", str(int(params["max_contracts"]))])
        elif params.get("max_companies") is not None:
            argv.extend(["--max-contracts", str(int(params["max_companies"]))])
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
        rows = _extract_companies(arts)
        if rows:
            src = out_dir / "suppliers.json"
            if not src.is_file():
                payload = {
                    "coverage": {
                        "top_n": len(rows),
                        "population_mode": params.get("population_mode") or "BOUNDED_SAMPLE",
                        "uf": params.get("uf") or "",
                    },
                    "companies": rows,
                }
                src.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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
            coverage={
                "top_n": len(rows),
                "population_mode": params.get("population_mode") or "BOUNDED_SAMPLE",
                "uf": params.get("uf"),
            },
            source_snapshots=[{"type": "pipeline", "module": self.canonical_module, "target": "suppliers"}],
            stdout_tail=proc.stdout[-4000:],
            stderr_tail=proc.stderr[-4000:],
            message=f"CONFENGE suppliers REAL exit={proc.exit_code}; {len(arts)} artefatos.",
            rows=rows,
            pipeline_status=status,
        )


def _extract_companies(arts: list[Path]) -> list[dict[str, Any]]:
    for art in arts:
        if art.suffix.lower() != ".json":
            continue
        try:
            data = json.loads(art.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            for key in ("companies", "leads", "items", "rows", "suppliers"):
                val = data.get(key)
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    return val
        if isinstance(data, list) and data and isinstance(data[0], dict):
            if any("cnpj" in r or "razao" in str(r).lower() for r in data[:3]):
                return data
    return []
