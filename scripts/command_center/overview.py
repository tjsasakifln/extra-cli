"""Aggregate overview / attention data without inventing business metrics."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from scripts.command_center.capabilities.registry import CapabilityRegistry
from scripts.command_center.config import Settings, git_sha
from scripts.command_center.redaction import env_presence
from scripts.command_center.search_index import get_search_index
from scripts.command_center.store import Store

# Home hierarchy priorities (lower = more urgent):
# 1 human decision / BLOCKED_HUMAN
# 2 BLOCKED_TECHNICAL / BLOCKED_EXTERNAL
# 3 FAILED / TIMED_OUT
# 4 PARTIAL
# 5 running
# 6 non-urgent warnings
# 7 advanced capabilities unavailable


def _status_priority(status: str) -> int:
    if status in {"BLOCKED_HUMAN", "BLOCKED_INSUFFICIENT_HUMAN_LABELS", "READY_FOR_HUMAN_ACCEPTANCE"}:
        return 1
    if status in {"BLOCKED_TECHNICAL", "BLOCKED_EXTERNAL"}:
        return 2
    if status in {"FAILED", "TIMED_OUT"}:
        return 3
    if status in {"PARTIAL", "SUCCEEDED_WITH_WARNINGS"}:
        return 4
    if status in {"RUNNING", "QUEUED", "VALIDATING", "CANCELLING"}:
        return 5
    return 6


def _status_kind(status: str) -> str:
    if status in {"BLOCKED_HUMAN", "BLOCKED_INSUFFICIENT_HUMAN_LABELS", "READY_FOR_HUMAN_ACCEPTANCE"}:
        return "awaiting_human"
    if status == "BLOCKED_EXTERNAL":
        return "blocked_external"
    if status in {"FAILED", "TIMED_OUT", "BLOCKED_TECHNICAL"}:
        return "blocked_technical"
    if status == "PARTIAL":
        return "partial"
    if status in {"RUNNING", "QUEUED", "VALIDATING", "CANCELLING"}:
        return "running"
    return "attention"


def build_overview(settings: Settings, store: Store, registry: CapabilityRegistry) -> dict[str, Any]:
    caps = registry.public_list()
    available = [c for c in caps if c["availability"] == "available"]
    unavailable = [c for c in caps if c["availability"] != "available"]
    jobs = store.list_jobs(limit=50)
    active = store.active_jobs()
    decisions = store.list_decisions(limit=10)
    attention: list[dict[str, Any]] = []

    # Pending human reviews first
    reviews_pending = store.count_reviews(status="pending")
    if reviews_pending > 0:
        attention.append(
            {
                "kind": "awaiting_human",
                "priority": 1,
                "title": f"{reviews_pending} revisão(ões) aguardando sua decisão",
                "detail": "Itens na fila humana — nada é aceito automaticamente.",
                "href": "/review",
                "next_action": "Abrir a fila e decidir com evidência",
                "count": reviews_pending,
            }
        )

    # Group running jobs by action (avoid 6 identical lines)
    running_groups: dict[str, list[Any]] = {}
    for j in active:
        key = j.action or j.capability_id
        running_groups.setdefault(key, []).append(j)
    for action, group in running_groups.items():
        first = group[0]
        n = len(group)
        attention.append(
            {
                "kind": "running",
                "priority": 5,
                "title": (
                    f"{action} — {n} execuções em andamento"
                    if n > 1
                    else f"Em andamento: {action}"
                ),
                "detail": first.human_message,
                "href": f"/jobs/{first.job_id}" if n == 1 else "/jobs",
                "next_action": "Acompanhar logs ou abrir a lista de atividades",
                "count": n if n > 1 else None,
            }
        )

    active_ids = {j.job_id for group in running_groups.values() for j in group}
    for j in jobs:
        if j.job_id in active_ids:
            continue
        if j.status not in {
            "FAILED",
            "TIMED_OUT",
            "BLOCKED_EXTERNAL",
            "BLOCKED_HUMAN",
            "BLOCKED_TECHNICAL",
            "PARTIAL",
            "BLOCKED_INSUFFICIENT_HUMAN_LABELS",
            "READY_FOR_HUMAN_ACCEPTANCE",
        }:
            continue
        attention.append(
            {
                "kind": _status_kind(j.status),
                "priority": _status_priority(j.status),
                "title": f"{j.action}: {j.status}",
                "detail": j.human_message,
                "href": f"/jobs/{j.job_id}",
                "next_action": j.next_action or "Abrir a execução e decidir a próxima ação",
            }
        )

    # Profile presence (no secret content)
    profile_path = Path("config/client_profiles/extra.yaml")
    profile_state = (
        "presente" if (settings and (Path(__file__).resolve().parents[2] / profile_path).exists()) else "ausente"
    )
    if profile_state == "ausente":
        attention.append(
            {
                "kind": "attention",
                "priority": 6,
                "title": "Perfil Extra incompleto ou ausente",
                "detail": "Valide o perfil antes do ciclo semanal.",
                "href": "/extra",
                "next_action": "Completar onboarding / perfil Extra",
            }
        )

    # Advanced capabilities last — not day-to-day commercial work
    for c in unavailable[:5]:
        attention.append(
            {
                "kind": "no_data",
                "priority": 7,
                "title": f"Capability avançada indisponível: {c['name']}",
                "detail": c.get("unavailable_reason") or "Ainda não disponível nesta versão",
                "href": "/actions",
                "next_action": "Não é trabalho comercial do dia",
            }
        )

    attention.sort(key=lambda x: (x["priority"], x.get("title", "")))

    # What-changed candidates: latest succeeded workflow jobs with manifests
    what_changed: list[dict[str, Any]] = []
    seen_wf: set[str] = set()
    for j in jobs:
        if not str(j.capability_id or "").startswith("workflow."):
            continue
        if j.status not in {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS", "PARTIAL"}:
            continue
        if j.capability_id in seen_wf:
            continue
        if not (j.manifests or j.artifacts):
            continue
        seen_wf.add(j.capability_id)
        man = (j.manifests or [None])[0]
        what_changed.append(
            {
                "workflow_id": j.capability_id,
                "label": j.action,
                "job_id": j.job_id,
                "finished_at": j.finished_at,
                "manifest_path": man,
                "href": f"/compare?workflow={j.capability_id}&current={man or ''}",
            }
        )
        if len(what_changed) >= 5:
            break

    deliverables_recent = []
    for j in jobs[:15]:
        for p in j.artifacts or []:
            if str(p).lower().endswith((".pdf", ".xlsx")):
                deliverables_recent.append(
                    {
                        "path": p,
                        "job_id": j.job_id,
                        "action": j.action,
                        "href": f"/results?path={p}",
                    }
                )
        if len(deliverables_recent) >= 8:
            break

    return {
        "headline": "O que precisa da minha atenção agora?",
        "attention": attention[:15],
        "health": {
            "sha": git_sha(),
            "env": {
                "LOCAL_DATALAKE_DSN": env_presence("LOCAL_DATALAKE_DSN"),
                "OPENAI_API_KEY": env_presence("OPENAI_API_KEY"),
                "DATABASE_URL": env_presence("DATABASE_URL"),
            },
            "profile": profile_state,
            "python": os.sys.version.split()[0],
        },
        "capabilities": {
            "total": len(caps),
            "available": len(available),
            "unavailable": len(unavailable),
            "by_category": registry.categories_summary(),
        },
        "jobs": {
            "active": [j.to_public() for j in active],
            "recent": [j.to_public() for j in jobs[:10]],
            "counts": store.job_counts(),
        },
        "reviews_pending_count": reviews_pending,
        "what_changed": what_changed,
        "deliverables_recent": deliverables_recent,
        "human_decisions_recent": decisions,
        "quick_actions": [
            {
                "id": "workflow.extra.opportunities",
                "label": "Encontrar oportunidades para a Extra",
                "href": "/work/start/workflow.extra.opportunities",
                "blurb": "Fluxo guiado → shortlist + PDF + planilha, sem terminal.",
            },
            {
                "id": "workflow.confenge.suppliers",
                "label": "Encontrar empresas com potencial comercial",
                "href": "/work/start/workflow.confenge.suppliers",
                "blurb": "Fornecedores CONFENGE com cobertura de cadastro e entregáveis.",
            },
            {
                "id": "workflow.confenge.public_agencies",
                "label": "Encontrar órgãos para serviços técnicos",
                "href": "/work/start/workflow.confenge.public_agencies",
                "blurb": "Órgãos públicos — classificações preliminares revisáveis.",
            },
            {
                "id": "workflow.process_documents",
                "label": "Analisar documentos de processos",
                "href": "/work/start/workflow.process_documents",
                "blurb": "Cobertura documental, PDFs no navegador e índice XLSX.",
            },
            {
                "id": "review.pending",
                "label": "Revisar trabalho pendente",
                "href": "/review",
                "blurb": "Fila humana com evidências e decisões auditáveis.",
            },
            {
                "id": "process_documents.coverage",
                "label": "Ver cobertura de documentos (avançado)",
                "href": "/actions/process_documents.coverage",
                "blurb": "O que já temos e o que falta nos processos.",
            },
            {
                "id": "results",
                "label": "Abrir resultados e planilhas",
                "href": "/results",
                "blurb": "Tabelas e relatórios gerados recentemente.",
            },
        ],
        "areas": [
            {
                "id": "extra",
                "label": "Oportunidades Extra",
                "href": "/extra",
                "blurb": "Ciclo semanal, shortlist e decisões da consultoria.",
            },
            {
                "id": "suppliers",
                "label": "Fornecedores CONFENGE",
                "href": "/confenge/suppliers",
                "blurb": "Cadastro oficial, ranking e lista comercial.",
            },
            {
                "id": "agencies",
                "label": "Órgãos públicos",
                "href": "/confenge/agencies",
                "blurb": "Prospecção institucional com linguagem cautelosa.",
            },
            {
                "id": "documents",
                "label": "Documentos de processos",
                "href": "/documents",
                "blurb": "Editais, anexos e cobertura documental.",
            },
            {"id": "review", "label": "Revisões humanas", "href": "/review", "blurb": "Fila do que só você pode decidir."},
            {"id": "results", "label": "Resultados", "href": "/results", "blurb": "Tudo que foi gerado, em tabela."},
        ],
        "persona": {
            "audience": "engenheiro_civil_consultor",
            "tone": "operacional_negocio",
            "hide_dev_chrome_by_default": True,
        },
    }


def build_search(query: str, store: Store, registry: CapabilityRegistry, settings: Settings) -> dict[str, Any]:
    q = (query or "").strip().lower()
    if not q or len(q) < 2:
        return {"query": query, "results": []}
    results: list[dict[str, Any]] = []
    for c in registry.public_list():
        blob = f"{c['id']} {c['name']} {c['description']} {c['category']}".lower()
        if q in blob:
            results.append(
                {
                    "type": "capability",
                    "id": c["id"],
                    "label": c["name"],
                    "detail": c["description"],
                    "href": f"/actions/{c['id']}",
                }
            )
    for j in store.list_jobs(limit=100):
        blob = f"{j.job_id} {j.capability_id} {j.action} {j.status}".lower()
        if q in blob:
            results.append(
                {
                    "type": "job",
                    "id": j.job_id,
                    "label": j.action,
                    "detail": j.status,
                    "href": f"/jobs/{j.job_id}",
                }
            )
    # Artifact catalog via TTL index — never full recursive scan on the hot path
    remaining = max(0, 40 - len(results))
    if remaining:
        index = get_search_index(Path(__file__).resolve().parents[2])
        results.extend(index.search(q, limit=remaining))
    return {"query": query, "results": results[:40]}
