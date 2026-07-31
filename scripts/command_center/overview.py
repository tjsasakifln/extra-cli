"""Aggregate overview / attention data without inventing business metrics."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from scripts.command_center.capabilities.registry import CapabilityRegistry
from scripts.command_center.config import Settings, git_sha
from scripts.command_center.redaction import env_presence
from scripts.command_center.store import Store


def build_overview(settings: Settings, store: Store, registry: CapabilityRegistry) -> dict[str, Any]:
    caps = registry.public_list()
    available = [c for c in caps if c["availability"] == "available"]
    unavailable = [c for c in caps if c["availability"] != "available"]
    jobs = store.list_jobs(limit=20)
    active = store.active_jobs()
    decisions = store.list_decisions(limit=10)
    attention: list[dict[str, Any]] = []

    for j in active:
        attention.append(
            {
                "kind": "job_running",
                "priority": 10,
                "title": f"Job em andamento: {j.action}",
                "detail": j.human_message,
                "href": f"/jobs/{j.job_id}",
            }
        )
    for j in jobs:
        if j.status in {"FAILED", "TIMED_OUT", "BLOCKED_EXTERNAL", "BLOCKED_HUMAN", "PARTIAL"}:
            attention.append(
                {
                    "kind": "job_attention",
                    "priority": 20 if j.status.startswith("BLOCKED") else 30,
                    "title": f"{j.action}: {j.status}",
                    "detail": j.human_message,
                    "href": f"/jobs/{j.job_id}",
                }
            )
    for c in unavailable[:8]:
        attention.append(
            {
                "kind": "capability_missing",
                "priority": 50,
                "title": f"Indisponível: {c['name']}",
                "detail": c.get("unavailable_reason") or "Ainda não disponível nesta versão",
                "href": "/capabilities",
            }
        )

    # Profile presence (no secret content)
    profile_path = Path("config/client_profiles/extra.yaml")
    profile_state = "presente" if (settings and (Path(__file__).resolve().parents[2] / profile_path).exists()) else "ausente"
    if profile_state == "ausente":
        attention.append(
            {
                "kind": "profile",
                "priority": 15,
                "title": "Perfil Extra incompleto ou ausente",
                "detail": "Valide o perfil antes do ciclo semanal.",
                "href": "/extra",
            }
        )

    attention.sort(key=lambda x: x["priority"])
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
        "human_decisions_recent": decisions,
        "quick_actions": [
            {"id": "extra.profile.validate", "label": "Validar perfil Extra", "href": "/extra"},
            {"id": "extra.weekly.run", "label": "Ciclo semanal", "href": "/extra"},
            {"id": "confenge.suppliers.cycle.run", "label": "Ciclo comercial fornecedores", "href": "/confenge/suppliers"},
            {"id": "confenge.public_agencies.cycle.run", "label": "Órgãos públicos", "href": "/confenge/agencies"},
            {"id": "process_documents.coverage", "label": "Cobertura documental", "href": "/documents"},
            {"id": "dod.status", "label": "Status DOD", "href": "/dod"},
            {"id": "cc.fixture.echo", "label": "Teste seguro (fixture)", "href": "/jobs"},
        ],
        "areas": [
            {"id": "extra", "label": "Operações da Extra", "href": "/extra"},
            {"id": "suppliers", "label": "CONFENGE — Fornecedores", "href": "/confenge/suppliers"},
            {"id": "agencies", "label": "CONFENGE — Órgãos Públicos", "href": "/confenge/agencies"},
            {"id": "documents", "label": "Documentos de Processos", "href": "/documents"},
            {"id": "ops", "label": "Operação e Infraestrutura", "href": "/ops"},
            {"id": "dod", "label": "DOD e Evidências", "href": "/dod"},
        ],
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
                    "href": f"/capabilities/{c['id']}",
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
    for root_name in ("output", "artifacts", "docs"):
        root = Path(__file__).resolve().parents[2] / root_name
        if not root.exists():
            continue
        try:
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                if q in p.name.lower() or q in str(p).lower():
                    results.append(
                        {
                            "type": "artifact",
                            "id": str(p),
                            "label": p.name,
                            "detail": str(p),
                            "href": f"/artifacts?path={p}",
                        }
                    )
                    if len(results) >= 40:
                        break
        except OSError:
            continue
        if len(results) >= 40:
            break
    return {"query": query, "results": results[:40]}
