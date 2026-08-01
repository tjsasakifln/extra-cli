"""Adapter: Extra Construtora opportunities (profile → weekly → decision loop)."""

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


class ExtraOpportunitiesAdapter:
    workflow_id = "workflow.extra.opportunities"
    capability_id = "extra.decision.finalize"
    canonical_module = "scripts.ops.extra_decision_loop"
    weekly_module = "scripts.ops.weekly_cycle"

    def preflight(self, params: dict[str, Any], *, out_dir: Path) -> PreflightResult:
        checks: list[PreflightCheck] = [
            check_module_importable(self.weekly_module),
            check_module_importable(self.canonical_module),
            check_module_importable("scripts.ops.extra_profile"),
            check_env_present("LOCAL_DATALAKE_DSN", required=True),
            check_postgres_optional("LOCAL_DATALAKE_DSN"),
            check_dir_writable(out_dir, name="dir:out"),
        ]
        weekly_input = params.get("weekly_input") or params.get("weekly_dir")
        if weekly_input:
            p = Path(str(weekly_input))
            checks.append(
                PreflightCheck(
                    name="data:weekly_input",
                    ok=p.is_dir(),
                    detail=str(p) if p.is_dir() else f"não é diretório: {p}",
                    required=False,
                )
            )
        limitations = [
            "Escrita local em output allowlisted; sem outreach automático.",
            "Decision loop gera pacote de revisão humana — sem autoaceite DOD.",
            "offline=true no weekly é teste e não prova LIVE comercial.",
        ]
        return finalize_preflight(checks, capability_id=self.capability_id, limitations=limitations)

    def build_argv(self, params: dict[str, Any], *, out_dir: Path) -> list[str]:
        """Prefer existing weekly pack; otherwise run decision loop after ensuring weekly via chain marker.

        Canonical path when weekly_dir provided:
          python -m scripts.ops.extra_decision_loop run --weekly-dir … --out …

        When not provided, run weekly_cycle first (caller may chain); argv here is the
        primary decision step when weekly already exists, else weekly_cycle collect path.
        """
        weekly = params.get("weekly_input") or params.get("weekly_dir")
        decision_out = out_dir / "decision"
        if weekly:
            argv = python_module_argv(
                self.canonical_module,
                "run",
                "--weekly-dir",
                str(weekly),
                "--out",
                str(decision_out),
            )
            if params.get("max_shortlist") is not None:
                argv.extend(["--max-shortlist", str(int(params["max_shortlist"]))])
            if params.get("profile"):
                argv.extend(["--profile", str(params["profile"])])
            return argv

        # No weekly pack: run weekly_cycle into out_dir/weekly (bounded when limit set)
        argv = python_module_argv(self.weekly_module)
        if params.get("strict", True):
            argv.append("--strict")
        else:
            argv.append("--no-strict")
        if params.get("skip_collect"):
            argv.append("--skip-collect")
        if params.get("offline"):
            argv.append("--offline")
        if params.get("period_days") is not None:
            argv.extend(["--lookback-days", str(int(params["period_days"]))])
        if params.get("limit") is not None:
            argv.extend(["--limit", str(int(params["limit"]))])
        elif params.get("max_shortlist") is not None:
            argv.extend(["--limit", str(int(params["max_shortlist"]))])
        argv.extend(["--output-dir", str(out_dir / "weekly")])
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
        # Also pick known default weekly locations if referenced
        weekly = params.get("weekly_input") or params.get("weekly_dir")
        if weekly:
            arts.extend(discover_artifacts(Path(str(weekly))))
        status = "SUCCEEDED" if proc.exit_code == 0 else (
            "BLOCKED_DATA" if proc.exit_code == 2 else "FAILED"
        )
        rows = _load_rows_from_artifacts(arts)
        # Write normalized shortlist for workbench viewers when rows found
        if rows:
            shortlist = out_dir / "opportunities.json"
            if not shortlist.is_file():
                shortlist.write_text(
                    json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                arts.append(shortlist)
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
            warnings=["Modo REAL — sem fixture."] if proc.exit_code == 0 else [],
            coverage={"shortlist_count": len(rows), "period_days": params.get("period_days")},
            source_snapshots=[{"type": "pipeline", "module": self.canonical_module}],
            terminal_claim=None,
            stdout_tail=proc.stdout[-4000:],
            stderr_tail=proc.stderr[-4000:],
            message=(
                f"Extra opportunities REAL exit={proc.exit_code}; {len(arts)} artefatos."
            ),
            rows=rows,
            pipeline_status=status,
        )


def _load_rows_from_artifacts(arts: list[Path]) -> list[dict[str, Any]]:
    candidates = [
        "opportunities.json",
        "actionable.json",
        "shortlist.json",
        "decision_package.json",
        "items.json",
    ]
    for art in arts:
        if art.name not in candidates and "actionable" not in art.name and "decision" not in art.name:
            if art.suffix.lower() != ".json":
                continue
        if art.suffix.lower() != ".json":
            continue
        try:
            data = json.loads(art.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data
        if isinstance(data, dict):
            for key in ("opportunities", "items", "rows", "shortlist", "actionable"):
                val = data.get(key)
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    return val
    return []
