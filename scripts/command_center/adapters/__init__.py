"""Command Center adapters for canonical REAL pipelines."""

from __future__ import annotations

from scripts.command_center.adapters.base import (
    AdapterBlockedError,
    AdapterResult,
    DataMode,
    PreflightResult,
    resolve_data_mode,
    run_real_adapter,
)
from scripts.command_center.adapters.confenge_public_agencies import ConfengePublicAgenciesAdapter
from scripts.command_center.adapters.confenge_suppliers import ConfengeSuppliersAdapter
from scripts.command_center.adapters.consulting_chain import (
    BidReadinessAdapter,
    BudgetAuditAdapter,
    EditalCaseAdapter,
    TechnicalAcervoAdapter,
)
from scripts.command_center.adapters.extra_opportunities import ExtraOpportunitiesAdapter
from scripts.command_center.adapters.process_documents import ProcessDocumentsAdapter

_ADAPTERS = {
    ExtraOpportunitiesAdapter.workflow_id: ExtraOpportunitiesAdapter(),
    ConfengeSuppliersAdapter.workflow_id: ConfengeSuppliersAdapter(),
    ConfengePublicAgenciesAdapter.workflow_id: ConfengePublicAgenciesAdapter(),
    ProcessDocumentsAdapter.workflow_id: ProcessDocumentsAdapter(),
    EditalCaseAdapter.workflow_id: EditalCaseAdapter(),
    BudgetAuditAdapter.workflow_id: BudgetAuditAdapter(),
    TechnicalAcervoAdapter.workflow_id: TechnicalAcervoAdapter(),
    BidReadinessAdapter.workflow_id: BidReadinessAdapter(),
}


def get_adapter(workflow_id: str):
    return _ADAPTERS.get(workflow_id)


def list_adapter_workflow_ids() -> list[str]:
    return sorted(_ADAPTERS.keys())


def preflight_workflow(workflow_id: str, params: dict, *, out_dir) -> PreflightResult:
    adapter = get_adapter(workflow_id)
    if adapter is None:
        return PreflightResult(
            status="BLOCKED_CONFIG",
            checks=[],
            limitations=["Sem adapter REAL para este fluxo."],
            safe_to_run=False,
            capability_id=workflow_id,
            message=f"Adapter não registrado: {workflow_id}",
        )
    return adapter.preflight(params, out_dir=out_dir)


__all__ = [
    "AdapterBlockedError",
    "AdapterResult",
    "DataMode",
    "PreflightResult",
    "get_adapter",
    "list_adapter_workflow_ids",
    "preflight_workflow",
    "resolve_data_mode",
    "run_real_adapter",
]
