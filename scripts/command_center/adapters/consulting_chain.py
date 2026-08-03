"""Allowlisted adapters for consulting chain: edital, budget, acervo, bid readiness.

No domain logic here — only argv construction + artifact discovery against
canonical python -m modules.
"""

from __future__ import annotations

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


def _generic_interpret(
    *,
    proc: SubprocessResult,
    preflight: PreflightResult,
    out_dir: Path,
    params: dict[str, Any],
) -> AdapterResult:
    arts = discover_artifacts(out_dir)
    # Also scan case_dir / out param when provided
    for key in ("case_dir", "out", "output_dir", "data"):
        p = params.get(key)
        if p:
            path = Path(str(p))
            if path.exists():
                arts.extend(discover_artifacts(path))
    status = (
        "SUCCEEDED"
        if proc.exit_code == 0
        else ("PARTIAL" if proc.exit_code == 2 else "FAILED")
    )
    limitations = list(preflight.limitations)
    if proc.exit_code != 0:
        limitations.append(f"exit_code={proc.exit_code} (PARTIAL/FAILED — UI must not paint as success)")
    # Never elevate PARTIAL/FAILED to success cosmetics
    if status in {"PARTIAL", "FAILED", "BLOCKED_DATA"}:
        terminal = status
    else:
        terminal = "SUCCEEDED"
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
        params_public={k: v for k, v in params.items() if "secret" not in k.lower() and "token" not in k.lower()},
        preflight=preflight.to_dict(),
        limitations=limitations,
        terminal_claim=terminal,
        stdout_tail=(proc.stdout or "")[-4000:],
        stderr_tail=(proc.stderr or "")[-4000:],
        message=f"status={status}",
        pipeline_status=status,
    )


class EditalCaseAdapter:
    workflow_id = "workflow.edital_case"
    capability_id = "consulting.edital_case.run"
    canonical_module = "scripts.edital_case"

    def preflight(self, params: dict[str, Any], *, out_dir: Path) -> PreflightResult:
        checks = [
            check_module_importable(self.canonical_module),
            check_dir_writable(out_dir, name="dir:out"),
        ]
        limitations = [
            "Case pack imutável de triagem técnica — não é parecer jurídico.",
            "Sem rede obrigatória no modo fixture/local; verify fail-closed.",
            "PARTIAL/REVIEW/BLOCKED nunca devem aparecer como sucesso na UI.",
        ]
        return finalize_preflight(checks, capability_id=self.capability_id, limitations=limitations)

    def build_argv(self, params: dict[str, Any], *, out_dir: Path) -> list[str]:
        action = str(params.get("action") or "run")
        allowed = {"create", "ingest", "analyze", "report", "verify", "run", "gate"}
        if action not in allowed:
            raise ValueError(f"edital_case action não permitida: {action}")
        argv = python_module_argv(self.canonical_module, action)
        case_id = str(params.get("case_id") or "cc-edital-case")
        output = str(params.get("output") or params.get("case_dir") or out_dir / "edital_case")
        if action == "run":
            source = str(
                params.get("source")
                or params.get("source_dir")
                or "tests/edital_case/fixtures/sample_edital.pdf"
            )
            argv.extend(["--case-id", case_id, "--source", source, "--output", output])
        elif action in {"analyze", "report", "verify", "gate", "ingest"}:
            # subcommands accept case path via --output or case-id depending on version
            argv.extend(["--case-id", case_id])
            if params.get("source"):
                argv.extend(["--source", str(params["source"])])
            argv.extend(["--output", output])
        else:
            argv.extend(["--case-id", case_id, "--output", output])
        return argv

    def interpret(self, params, *, out_dir, proc, preflight) -> AdapterResult:
        return _generic_interpret(proc=proc, preflight=preflight, out_dir=out_dir, params=params)


class BudgetAuditAdapter:
    workflow_id = "workflow.budget_audit"
    capability_id = "consulting.budget_audit.run"
    canonical_module = "scripts.budget_audit"

    def preflight(self, params: dict[str, Any], *, out_dir: Path) -> PreflightResult:
        checks = [
            check_module_importable(self.canonical_module),
            check_dir_writable(out_dir, name="dir:out"),
        ]
        limitations = [
            "Auditoria de planilha/composições/BDI com locators — não fecha comparação oficial sozinha.",
            "Comparação SINAPI/SICRO real exige dataset oficial (claim REAL_CASE_PROVEN).",
            "UI não deve converter findings em GO comercial.",
        ]
        return finalize_preflight(checks, capability_id=self.capability_id, limitations=limitations)

    def build_argv(self, params: dict[str, Any], *, out_dir: Path) -> list[str]:
        action = str(params.get("action") or "run")
        allowed = {
            "create",
            "ingest",
            "map",
            "audit",
            "compare",
            "references",
            "report",
            "verify",
            "run",
        }
        if action not in allowed:
            raise ValueError(f"budget_audit action não permitida: {action}")
        argv = python_module_argv(self.canonical_module, action)
        case_id = str(params.get("case_id") or "cc-budget-audit")
        output = str(params.get("output") or params.get("case_dir") or out_dir / "budget_audit")
        if action == "run":
            source = str(params.get("source") or "tests/fixtures/budget_audit_sample.xlsx")
            argv.extend(["--case-id", case_id, "--source", source, "--output", output])
        else:
            argv.extend(["--case-id", case_id, "--output", output])
            if params.get("source"):
                argv.extend(["--source", str(params["source"])])
        return argv

    def interpret(self, params, *, out_dir, proc, preflight) -> AdapterResult:
        return _generic_interpret(proc=proc, preflight=preflight, out_dir=out_dir, params=params)


class TechnicalAcervoAdapter:
    workflow_id = "workflow.technical_acervo"
    capability_id = "consulting.technical_acervo.match"
    canonical_module = "scripts.technical_acervo"

    def preflight(self, params: dict[str, Any], *, out_dir: Path) -> PreflightResult:
        checks = [
            check_module_importable(self.canonical_module),
            check_dir_writable(out_dir, name="dir:out"),
            PreflightCheck(
                name="data:canonical_acervo",
                ok=Path("data/extra_technical_acervo.json").is_file(),
                detail="data/extra_technical_acervo.json",
                required=True,
            ),
        ]
        limitations = [
            "Fonte canônica única: data/extra_technical_acervo.json.",
            "Match não habilita nem autoriza submissão.",
            "Somatório desligado por padrão.",
        ]
        return finalize_preflight(checks, capability_id=self.capability_id, limitations=limitations)

    def build_argv(self, params: dict[str, Any], *, out_dir: Path) -> list[str]:
        action = str(params.get("action") or "match")
        allowed = {
            "inventory",
            "list",
            "show",
            "search",
            "experiences",
            "match",
            "ask",
            "matrix",
            "chunks",
        }
        if action not in allowed:
            raise ValueError(f"technical_acervo action não permitida: {action}")
        argv = python_module_argv(self.canonical_module, action)
        if action == "match":
            service = str(params.get("service") or params.get("query") or "pavimentacao").strip()
            argv.extend(["--service", service])
            qty = params.get("quantity") if params.get("quantity") is not None else params.get("qty")
            if qty is not None:
                argv.extend(["--qty", str(qty)])
            if params.get("unit"):
                argv.extend(["--unit", str(params["unit"])])
            if params.get("allow_sum"):
                argv.append("--allow-sum")
        elif action == "search":
            q = str(params.get("query") or params.get("service") or "").strip()
            if not q:
                raise ValueError("query/service obrigatório para search")
            argv.append(q)
        elif action == "show":
            key = str(params.get("id") or params.get("query") or "").strip()
            if not key:
                raise ValueError("id obrigatório para show")
            argv.append(key)
        argv.append("--json")
        return argv

    def interpret(self, params, *, out_dir, proc, preflight) -> AdapterResult:
        # Persist stdout JSON for workbench
        out_json = out_dir / "technical_acervo_result.json"
        if proc.stdout and proc.stdout.strip():
            out_json.write_text(proc.stdout, encoding="utf-8")
        return _generic_interpret(proc=proc, preflight=preflight, out_dir=out_dir, params=params)


class BidReadinessAdapter:
    workflow_id = "workflow.bid_readiness"
    capability_id = "consulting.bid_readiness.run"
    canonical_module = "scripts.bid_readiness"

    def preflight(self, params: dict[str, Any], *, out_dir: Path) -> PreflightResult:
        checks = [
            check_module_importable(self.canonical_module),
            check_module_importable("scripts.technical_acervo"),
            check_dir_writable(out_dir, name="dir:out"),
        ]
        limitations = [
            "Package nunca emite READY_TO_SUBMIT / HABILITADA.",
            "Technical matching via technical_acervo canônico.",
            "Somente READY_FOR_HUMAN_REVIEW ou BLOCKED_*.",
            "Sem envio/submissão automática.",
        ]
        return finalize_preflight(checks, capability_id=self.capability_id, limitations=limitations)

    def build_argv(self, params: dict[str, Any], *, out_dir: Path) -> list[str]:
        action = str(params.get("action") or "run")
        allowed = {
            "create",
            "run",
            "verify",
            "inventory",
            "match",
            "report",
            "validate",
            "declarations",
            "assemble",
            "ingest",
        }
        if action not in allowed:
            raise ValueError(f"bid_readiness action não permitida: {action}")
        argv = python_module_argv(self.canonical_module, action)
        if action == "run":
            case_id = str(params.get("case_id") or "cc-bid-readiness")
            reqs = str(
                params.get("requirements")
                or "scripts/bid_readiness/fixtures/golden/requirements.json"
            )
            docs = str(
                params.get("documents")
                or params.get("documents_dir")
                or "scripts/bid_readiness/fixtures/golden/documents"
            )
            ref = str(params.get("reference_date") or "2026-08-01")
            output = str(params.get("output") or out_dir / "bid_readiness")
            argv.extend(
                [
                    "--case-id",
                    case_id,
                    "--requirements",
                    reqs,
                    "--documents",
                    docs,
                    "--reference-date",
                    ref,
                    "--output",
                    output,
                ]
            )
        else:
            if params.get("case_id"):
                argv.extend(["--case-id", str(params["case_id"])])
            if params.get("output"):
                argv.extend(["--output", str(params["output"])])
        return argv

    def interpret(self, params, *, out_dir, proc, preflight) -> AdapterResult:
        result = _generic_interpret(proc=proc, preflight=preflight, out_dir=out_dir, params=params)
        # Hard non-claim: scan artifacts for forbidden status labels as UI success
        for art in result.artifacts:
            try:
                text = Path(art).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            # package_status equality only — not the forbidden list in schema docs
            if '"package_status": "READY_TO_SUBMIT"' in text or '"package_status":"READY_TO_SUBMIT"' in text:
                result.status = "FAILED"
                result.limitations.append("FORBIDDEN package_status READY_TO_SUBMIT detected")
                result.terminal_claim = "FAILED"
        result.limitations.append("human_review_required — never auto-submit")
        return result
