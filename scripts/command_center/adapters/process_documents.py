"""Adapter: process documents public corpus (show / coverage)."""

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
    check_module_importable,
    discover_artifacts,
    finalize_preflight,
    python_module_argv,
)
from scripts.command_center.config import git_sha


class ProcessDocumentsAdapter:
    workflow_id = "workflow.process_documents"
    capability_id = "process_documents.show"
    canonical_module = "scripts.process_documents"

    def preflight(self, params: dict[str, Any], *, out_dir: Path) -> PreflightResult:
        checks: list[PreflightCheck] = [
            check_module_importable(self.canonical_module),
            check_dir_writable(out_dir, name="dir:out"),
        ]
        query = str(params.get("query") or "").strip()
        checks.append(
            PreflightCheck(
                name="param:query",
                ok=bool(query),
                detail="query informada" if query else "query vazia",
                required=True,
            )
        )
        # DSN optional for show (may use local corpus); warn but don't require for READ show
        limitations = [
            "Comando canônico: python -m scripts.process_documents show <query>.",
            "Leitura/indexação de acervo; sem envio de mensagens.",
            "Coleta live (collect/harvest) exige confirmação e DSN — use Avançado se necessário.",
        ]
        return finalize_preflight(checks, capability_id=self.capability_id, limitations=limitations)

    def build_argv(self, params: dict[str, Any], *, out_dir: Path) -> list[str]:
        action = str(params.get("action") or "show")
        allowed = {"show", "coverage", "discover", "build-corpus"}
        if action not in allowed:
            raise ValueError(f"action process_documents não permitida: {action}")
        if action == "show":
            query = str(params.get("query") or "").strip()
            if not query:
                raise ValueError("query obrigatória para process_documents show")
            # Reject shell metacharacters in query (argv-separated, but belt-and-suspenders)
            if any(c in query for c in [";", "|", "&", "`", "$", "\n", "\r"]):
                raise ValueError("query contém caracteres não permitidos")
            return python_module_argv(self.canonical_module, "show", query)
        if action == "coverage":
            return python_module_argv(self.canonical_module, "coverage")
        if action == "discover":
            return python_module_argv(self.canonical_module, "discover")
        return python_module_argv(self.canonical_module, "build-corpus")

    def interpret(
        self,
        params: dict[str, Any],
        *,
        out_dir: Path,
        proc: SubprocessResult,
        preflight: PreflightResult,
    ) -> AdapterResult:
        # Persist structured stdout when JSON
        rows: list[dict[str, Any]] = []
        index_path = out_dir / "documents-index.json"
        payload: Any
        try:
            payload = json.loads(proc.stdout) if proc.stdout.strip().startswith(("{", "[")) else None
        except json.JSONDecodeError:
            payload = None
        if payload is not None:
            index_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            if isinstance(payload, list):
                rows = [r for r in payload if isinstance(r, dict)]
            elif isinstance(payload, dict):
                for key in ("documents", "items", "rows", "results"):
                    if isinstance(payload.get(key), list):
                        rows = [r for r in payload[key] if isinstance(r, dict)]
                        break
                if not rows:
                    rows = [payload]
        else:
            # Save human-readable show output
            summary = out_dir / "documents-show.txt"
            summary.write_text(proc.stdout or proc.stderr or "(sem saída)", encoding="utf-8")
            index_path.write_text(
                json.dumps(
                    {
                        "query": params.get("query"),
                        "exit_code": proc.exit_code,
                        "stdout_excerpt": (proc.stdout or "")[:8000],
                        "documents": [],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
        arts = discover_artifacts(out_dir)
        # Known process_documents output root
        default_out = Path("output/process_documents")
        if default_out.is_dir():
            arts.extend(discover_artifacts(default_out)[:50])
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
            coverage={"query": params.get("query"), "documents": len(rows)},
            source_snapshots=[{"type": "pipeline", "module": self.canonical_module}],
            stdout_tail=proc.stdout[-4000:],
            stderr_tail=proc.stderr[-4000:],
            message=f"Process documents REAL exit={proc.exit_code}; {len(arts)} artefatos.",
            rows=rows,
            pipeline_status=status,
        )
