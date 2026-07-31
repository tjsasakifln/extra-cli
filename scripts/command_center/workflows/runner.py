"""Execute guided workflows: fixture-backed deliverables + run-manifest.

CLI remains the engine for live cycles; fixtures power offline proof without forging
live evidence claims. Output paths are always assigned by the Command Center.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.command_center.deliverables.excel_render import write_workbook
from scripts.command_center.deliverables.pdf_render import write_executive_pdf
from scripts.command_center.fixtures import sample_data
from scripts.command_center.run_manifest import (
    ArtifactRole,
    ProgressEvent,
    RunManifest,
    declare_file,
    sha256_file,
)
from scripts.command_center.workflows.catalog import WorkflowDef, get_workflow


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


ProgressCb = Callable[[dict[str, Any]], None]


def load_source_rows(path: Path, *, list_keys: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Load rows from a prior/corrected source JSON (list or dict envelope)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        keys = list_keys or ("companies", "opportunities", "items", "rows", "leads", "documents")
        for key in keys:
            if isinstance(raw.get(key), list):
                return [r for r in raw[key] if isinstance(r, dict)]
        raise ValueError(f"Fonte {path.name} sem lista de registros reconhecível")
    raise ValueError(f"Fonte {path.name} inválida")


def run_workflow(
    workflow_id: str,
    params: dict[str, Any],
    *,
    out_dir: Path,
    code_sha: str | None = None,
    job_id: str | None = None,
    on_progress: ProgressCb | None = None,
    source_override: Path | None = None,
) -> dict[str, Any]:
    wf = get_workflow(workflow_id)
    if wf is None:
        raise ValueError(f"Workflow desconhecido: {workflow_id}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    override = Path(source_override) if source_override else None
    if override is not None and not override.is_file():
        raise ValueError(f"source_override inexistente: {override}")

    def emit(stage_id: str, label: str, state: str, message: str | None = None, **extra: Any) -> None:
        ev = ProgressEvent(
            stage_id=stage_id,
            stage_label=label,
            state=state,
            message=message,
            **{k: v for k, v in extra.items() if k in ProgressEvent.__dataclass_fields__},
        )
        if on_progress:
            on_progress(ev.to_dict())

    emit("preparing", "Preparando", "running", "Criando pasta segura de resultados")
    mf = RunManifest(
        job_id=job_id,
        capability_id=workflow_id,
        workflow_id=workflow_id,
        client_id=wf.client_id,
        parameters=dict(params),
        code_sha=code_sha,
        data_as_of=_utcnow()[:10],
        output_profile=str(params.get("output_profile") or "CLIENT_READY"),
        limitations=list(wf.limitations),
        started_at=_utcnow(),
    )
    # Guided workflows use representative fixtures only. Live commercial/Extra
    # cycles remain in Avançado (allowlisted CLI capabilities) — do not pretend.
    use_fixture = params.get("use_fixture", True)
    if isinstance(use_fixture, str):
        use_fixture = use_fixture.lower() in {"1", "true", "yes", "sim"}
    if use_fixture is False and override is None:
        raise ValueError(
            "Este fluxo guiado opera com dados de demonstração (fixture). "
            "Para execução live/canônica use a área Avançada (capabilities CLI: "
            "extra.weekly.run, confenge.suppliers.cycle.run, confenge.public_agencies.cycle.run, "
            "process_documents.*). Não há orquestração live disfarçada de fixture."
        )
    params = {**params, "use_fixture": True}
    mf.parameters = dict(params)
    if override is not None:
        mf.warnings.append("Execução a partir de fonte corrigida/regenerada (não sample_data fresco).")
        mf.limitations.append(
            "Fonte: JSON de execução anterior com correções humanas aplicadas — ainda fixture/local, não live prod."
        )
        mf.source_snapshots.append(
            {"type": "corrected_source", "path": str(override), "note": "human correction or parent run"}
        )
    else:
        mf.warnings.append("Execução com dados de demonstração (fixture representativa).")
        mf.limitations.append(
            "Fonte: fixture representativa do Command Center — não reivindica evidência live de produção."
        )
        mf.source_snapshots.append({"type": "fixture", "id": workflow_id, "note": "offline representative"})
    emit("preparing", "Preparando", "succeeded")

    if workflow_id == "workflow.extra.opportunities":
        result = _run_extra(wf, params, out_dir, mf, emit, source_override=override)
    elif workflow_id == "workflow.confenge.suppliers":
        result = _run_suppliers(wf, params, out_dir, mf, emit, source_override=override)
    elif workflow_id == "workflow.confenge.public_agencies":
        result = _run_agencies(wf, params, out_dir, mf, emit, source_override=override)
    elif workflow_id == "workflow.process_documents":
        result = _run_documents(wf, params, out_dir, mf, emit, source_override=override)
    elif workflow_id == "workflow.review.pending":
        result = {
            "status": "SUCCEEDED",
            "message": "Abra a fila de revisões no menu Revisões.",
            "redirect": "/review",
        }
        mf.status = "SUCCEEDED"
        mf.finished_at = _utcnow()
        path = mf.write(out_dir)
        result["manifest_path"] = str(path)
        result["run_id"] = mf.run_id
        result["out_dir"] = str(out_dir)
        return result
    else:
        raise ValueError(f"Runner não implementado: {workflow_id}")

    emit("validating", "Validando", "running")
    mf.finished_at = _utcnow()
    mf.status = result.get("status") or "SUCCEEDED"
    manifest_path = mf.write(out_dir)
    # re-add manifest entry cleanly
    mf.artifacts = [a for a in mf.artifacts if a.get("logical_name") != "run-manifest.json"]
    mf.add_artifact(declare_file(manifest_path, role=ArtifactRole.MANIFEST.value, title="Run manifest"))
    manifest_path = mf.write(out_dir)
    emit("validating", "Validando", "succeeded")
    emit("completed", "Concluído", "succeeded", "Entregáveis prontos para revisão no navegador")

    result["manifest_path"] = str(manifest_path)
    result["run_id"] = mf.run_id
    result["out_dir"] = str(out_dir)
    result["manifest"] = mf.to_dict()
    result["artifacts"] = [a["path"] for a in mf.artifacts]
    return result


def _prov(mf: RunManifest, wf: WorkflowDef) -> dict[str, Any]:
    return {
        "run_id": mf.run_id,
        "workflow_id": wf.id,
        "code_sha": mf.code_sha or "unknown",
        "client": wf.client_label,
        "no_auto_outreach": "true",
    }


def _run_extra(
    wf: WorkflowDef,
    params: dict[str, Any],
    out_dir: Path,
    mf: RunManifest,
    emit: ProgressCb,
    source_override: Path | None = None,
) -> dict[str, Any]:
    emit("collecting", "Coletando", "running", "Carregando oportunidades (fixture ou pacote local)")
    max_sl = int(params.get("max_shortlist") or 15)
    if source_override is not None:
        rows = load_source_rows(source_override, list_keys=("opportunities", "items", "rows"))
        rows = rows[: max(1, min(max_sl, len(rows)))] if rows else rows
    else:
        rows = sample_data.extra_opportunities(max_shortlist=max_sl)
    source_path = out_dir / "opportunities.json"
    source_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mf.add_artifact(
        declare_file(
            source_path,
            role=ArtifactRole.SOURCE_DATA.value,
            title="Shortlist de oportunidades",
            review_required=True,
        )
    )
    emit("collecting", "Coletando", "succeeded")
    emit("processing", "Processando", "running", f"{len(rows)} oportunidades na shortlist")
    mf.coverage = {
        "shortlist_count": len(rows),
        "period_days": params.get("period_days") or 7,
        "source": "fixture" if params.get("use_fixture", True) else "local",
    }
    emit("processing", "Processando", "succeeded")
    emit("generating_report", "Gerando relatório", "running")

    headers = [
        "ID",
        "Órgão",
        "Objeto",
        "UF",
        "Valor estimado",
        "Prazo (dias)",
        "Aderência",
        "Risco",
        "Modalidade",
    ]
    data_rows = [
        [
            r["id"],
            r["orgao"],
            r["objeto"],
            r["uf"],
            r["valor_estimado"],
            r["prazo_dias"],
            r["aderencia_perfil"],
            r["risco"],
            r["modalidade"],
        ]
        for r in rows
    ]
    pdf_path = out_dir / "relatorio-executivo-extra.pdf"
    write_executive_pdf(
        pdf_path,
        title="Relatório executivo de oportunidades — Extra Construtora",
        client_label=wf.client_label,
        data_as_of=mf.data_as_of,
        executive_summary=(
            f"Foram organizadas {len(rows)} oportunidades para revisão humana, com aderência ao perfil, "
            "prazo, valor e evidências resumidas. Nenhuma decisão é automática."
        ),
        conclusions=[
            f"Shortlist com {len(rows)} itens para decisão ACCEPT/REJECT/DEFER.",
            "Itens de maior aderência devem ser priorizados na fila de revisão.",
            "Riscos altos exigem checagem de atestados e prazos antes de qualquer ação comercial.",
        ],
        indicators=[
            ("Itens na shortlist", str(len(rows))),
            ("Período (dias)", str(params.get("period_days") or 7)),
            ("Fonte", "fixture representativa" if params.get("use_fixture", True) else "local"),
        ],
        table_headers=headers,
        table_rows=data_rows,
        methodology=[
            "Ordenação por aderência ao perfil operacional da Extra.",
            "Parâmetros de período e tamanho definidos no preflight do Command Center.",
            "Geração de PDF/XLSX desacoplada das regras de negócio do CLI.",
        ],
        sources=["Fixture Command Center / ou weekly pack local quando disponível"],
        limitations=list(wf.limitations) + list(mf.limitations),
        version_id=mf.run_id,
        provenance=_prov(mf, wf),
        brand="EXTRA",
    )
    xlsx_path = out_dir / "workbook-oportunidades-extra.xlsx"
    write_workbook(
        xlsx_path,
        title="Oportunidades Extra Construtora",
        summary_rows=[
            ("Cliente", wf.client_label),
            ("Itens", len(rows)),
            ("Período (dias)", params.get("period_days") or 7),
            ("Run", mf.run_id),
        ],
        data_headers=headers + ["Evidência"],
        data_rows=[row + [r["evidencia"]] for row, r in zip(data_rows, rows, strict=False)],
        methodology=[
            "Shortlist gerada para apoio à decisão interna.",
            "Valores monetários em BRL nominais da fonte.",
        ],
        sources=["Command Center fixture/local pack"],
        limitations=list(wf.limitations),
        provenance=_prov(mf, wf),
        sheet_data_name="Oportunidades",
    )
    evidence_dir = out_dir / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    (evidence_dir / "README.md").write_text(
        "# Evidências\n\nPacote de apoio à shortlist. Ver opportunities.json e manifest.\n",
        encoding="utf-8",
    )
    shutil.copy(source_path, evidence_dir / "opportunities.json")

    mf.add_artifact(
        declare_file(
            pdf_path,
            role=ArtifactRole.EXECUTIVE_REPORT.value,
            title="Relatório executivo PDF",
            primary=True,
            description="PDF profissional da shortlist Extra",
        )
    )
    mf.add_artifact(
        declare_file(
            xlsx_path,
            role=ArtifactRole.WORKBOOK.value,
            title="Workbook de oportunidades",
            primary=True,
        )
    )
    mf.add_artifact(
        declare_file(
            evidence_dir / "README.md",
            role=ArtifactRole.EVIDENCE.value,
            title="Pacote de evidências",
        )
    )
    # reviews for each opportunity
    for r in rows:
        mf.reviews_required.append(
            {
                "item_key": r["id"],
                "title": f"{r['orgao']} — {r['objeto'][:60]}",
                "question": "Aceitar esta oportunidade para acompanhamento ativo?",
                "evidence": r["evidencia"],
                "limitations": "Classificação de aderência e risco é preliminar.",
                "risks": f"Risco declarado: {r['risco']}.",
                "content_hash": sha256_file(source_path),
            }
        )
    emit("generating_report", "Gerando relatório", "succeeded")
    emit("awaiting_review", "Aguardando revisão", "waiting_review", f"{len(rows)} itens na fila")
    return {
        "status": "SUCCEEDED",
        "message": f"Shortlist com {len(rows)} oportunidades. PDF e XLSX prontos.",
        "reviews": mf.reviews_required,
        "empty": len(rows) == 0,
    }


def _run_suppliers(
    wf: WorkflowDef,
    params: dict[str, Any],
    out_dir: Path,
    mf: RunManifest,
    emit: ProgressCb,
    source_override: Path | None = None,
) -> dict[str, Any]:
    emit("collecting", "Coletando", "running", "Recorte de empresas e cadastro oficial (fixture)")
    uf = str(params.get("uf") or "SC")
    n = int(params.get("max_companies") or 10)
    if source_override is not None:
        rows = load_source_rows(source_override, list_keys=("companies", "items", "rows"))
        rows = rows[: max(1, min(n, len(rows)))] if rows else rows
    else:
        rows = sample_data.confenge_suppliers(uf=uf, max_companies=n)
    population_mode = str(params.get("population_mode") or "BOUNDED_SAMPLE")
    mf.coverage = {
        "top_n": len(rows),
        "population_mode": population_mode,
        "official_registry_top_n_resolved": sum(1 for r in rows if r.get("cadastro_oficial") == "RESOLVED"),
        "official_registry_top_n_total": len(rows),
        "population_integral_coverage": None,
        "population_integral_note": (
            "Cobertura da população integral não medida nesta execução de amostra (BOUNDED_SAMPLE)."
            if population_mode == "BOUNDED_SAMPLE"
            else "FULL_POPULATION exige evidência de varredura integral no ciclo live."
        ),
        "uf": uf,
    }
    source_path = out_dir / "suppliers.json"
    source_path.write_text(json.dumps({"coverage": mf.coverage, "companies": rows}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mf.add_artifact(declare_file(source_path, role=ArtifactRole.SOURCE_DATA.value, title="Empresas", review_required=True))
    emit("collecting", "Coletando", "succeeded")
    emit("processing", "Processando", "succeeded", f"{len(rows)} empresas no Top N")
    emit("generating_report", "Gerando relatório", "running")

    headers = ["CNPJ", "Razão social", "UF", "Município", "Score", "Contratos 36m", "Valor", "Cadastro oficial"]
    data_rows = [
        [
            r["cnpj"],
            r["razao_social"],
            r["uf"],
            r["municipio"],
            r["score"],
            r["contratos_36m"],
            r["valor_contratos"],
            r["cadastro_oficial"],
        ]
        for r in rows
    ]
    pdf_path = out_dir / "relatorio-executivo-fornecedores.pdf"
    write_executive_pdf(
        pdf_path,
        title="Relatório executivo — prospecção de fornecedores CONFENGE",
        client_label=wf.client_label,
        data_as_of=mf.data_as_of,
        executive_summary=(
            f"Recorte {uf} com Top {len(rows)} empresas. "
            f"Cadastro oficial resolvido em {mf.coverage['official_registry_top_n_resolved']}/{len(rows)} do Top N. "
            "Cobertura do Top N não equivale à população integral."
        ),
        conclusions=[
            "Priorize empresas com cadastro RESOLVED para revisão comercial.",
            "Score é prioridade de revisão — não propensão ou intenção de compra.",
            "Abordagem permanece manual; a UI não envia mensagens.",
        ],
        indicators=[
            ("Top N", str(len(rows))),
            ("UF", uf),
            ("Cadastro oficial (Top N)", f"{mf.coverage['official_registry_top_n_resolved']}/{len(rows)}"),
            ("Modo população", population_mode),
        ],
        table_headers=headers,
        table_rows=data_rows,
        methodology=[
            "Router canônico confenge_commercial_target_router (live) ou fixture alinhada ao contrato.",
            "Distinção explícita Top N vs população integral.",
        ],
        sources=["Fixture / ciclo comercial CONFENGE"],
        limitations=list(wf.limitations),
        version_id=mf.run_id,
        provenance=_prov(mf, wf),
    )
    xlsx_path = out_dir / "planilha-comercial-fornecedores.xlsx"
    write_workbook(
        xlsx_path,
        title="Planilha comercial — fornecedores CONFENGE",
        summary_rows=[
            ("UF", uf),
            ("Top N", len(rows)),
            ("Population mode", population_mode),
            ("Run", mf.run_id),
        ],
        data_headers=headers + ["Sinais", "Limitações"],
        data_rows=[
            row + [r["sinais"], r["limitacoes"]] for row, r in zip(data_rows, rows, strict=False)
        ],
        methodology=["Uso interno comercial; sem auto-outreach."],
        sources=["Command Center / CONFENGE cycle"],
        limitations=list(wf.limitations),
        provenance=_prov(mf, wf),
        sheet_data_name="Empresas",
    )
    mf.add_artifact(
        declare_file(pdf_path, role=ArtifactRole.EXECUTIVE_REPORT.value, title="Relatório executivo PDF", primary=True)
    )
    mf.add_artifact(
        declare_file(xlsx_path, role=ArtifactRole.WORKBOOK.value, title="Planilha comercial XLSX", primary=True)
    )
    for r in rows:
        mf.reviews_required.append(
            {
                "item_key": r["cnpj"],
                "title": r["razao_social"],
                "question": "Incluir esta empresa na fila comercial manual?",
                "evidence": f"Score {r['score']}; cadastro {r['cadastro_oficial']}; sinais: {r['sinais']}",
                "limitations": r["limitacoes"],
                "risks": "Contato sem validação cadastral pode gerar abordagem indevida.",
                "content_hash": sha256_file(source_path),
            }
        )
    emit("generating_report", "Gerando relatório", "succeeded")
    emit("awaiting_review", "Aguardando revisão", "waiting_review")
    return {"status": "SUCCEEDED", "message": f"{len(rows)} empresas. PDF e XLSX prontos.", "reviews": mf.reviews_required}


def _run_agencies(
    wf: WorkflowDef,
    params: dict[str, Any],
    out_dir: Path,
    mf: RunManifest,
    emit: ProgressCb,
    source_override: Path | None = None,
) -> dict[str, Any]:
    emit("collecting", "Coletando", "running")
    uf = str(params.get("uf") or "SC")
    n = int(params.get("max_leads") or 10)
    mode = str(params.get("mode") or "REACTIVE_OPPORTUNITY")
    if source_override is not None:
        rows = load_source_rows(source_override, list_keys=("items", "rows", "leads", "agencies"))
        rows = rows[: max(1, min(n, len(rows)))] if rows else rows
    else:
        rows = sample_data.confenge_agencies(uf=uf, max_leads=n)
    if mode:
        # keep all but annotate preferred mode
        for r in rows:
            r["modo_solicitado"] = mode
    source_path = out_dir / "public_agencies.json"
    source_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mf.add_artifact(declare_file(source_path, role=ArtifactRole.SOURCE_DATA.value, title="Órgãos", review_required=True))
    mf.coverage = {"count": len(rows), "uf": uf, "mode": mode}
    mf.limitations.append("Nenhuma conclusão de contratação direta garantida é emitida.")
    emit("collecting", "Coletando", "succeeded")
    emit("processing", "Processando", "succeeded")
    emit("generating_report", "Gerando relatório", "running")

    headers = [
        "Órgão",
        "UF",
        "Tipo",
        "Classificação jurídica (preliminar)",
        "Risco fracionamento",
        "Conflito interesse",
    ]
    data_rows = [
        [
            r["orgao"],
            r["uf"],
            r["tipo"],
            r["classificacao_juridica_preliminar"],
            r["risco_fracionamento"],
            r["conflito_interesse"],
        ]
        for r in rows
    ]
    pdf_path = out_dir / "relatorio-orgaos-publicos.pdf"
    write_executive_pdf(
        pdf_path,
        title="Órgãos públicos — serviços técnicos CONFENGE",
        client_label=wf.client_label,
        data_as_of=mf.data_as_of,
        executive_summary=(
            f"Lista de {len(rows)} órgãos em {uf}. Classificações jurídicas são preliminares e revisáveis. "
            "Não há garantia de contratação direta."
        ),
        conclusions=[
            "Separe oportunidades reativas de prospects institucionais proativos.",
            "Itens com risco de fracionamento alto exigem análise humana antes de qualquer proposta.",
            "Conflitos de interesse devem ser revalidados fora da fixture.",
        ],
        indicators=[("Órgãos", str(len(rows))), ("UF", uf), ("Modalidade pedida", mode)],
        table_headers=headers,
        table_rows=data_rows,
        methodology=["Vertical public-agency; router canônico em modo live."],
        sources=["Fixture / ciclo public-agency"],
        limitations=list(wf.limitations),
        legal_disclaimers=[
            "Classificação jurídica preliminar ≠ parecer jurídico.",
            "É proibido apresentar contratação direta como garantida.",
        ],
        version_id=mf.run_id,
        provenance=_prov(mf, wf),
    )
    xlsx_path = out_dir / "workbook-orgaos-publicos.xlsx"
    write_workbook(
        xlsx_path,
        title="Órgãos públicos CONFENGE",
        summary_rows=[("UF", uf), ("Quantidade", len(rows)), ("Run", mf.run_id)],
        data_headers=headers + ["Objeto recente", "Limitações"],
        data_rows=[row + [r["objeto_recente"], r["limitacoes"]] for row, r in zip(data_rows, rows, strict=False)],
        methodology=["Revisão humana obrigatória para classificação."],
        sources=["Command Center"],
        limitations=list(wf.limitations),
        provenance=_prov(mf, wf),
        sheet_data_name="Orgaos",
    )
    review_pkg = out_dir / "pacote-revisao-orgaos.json"
    review_pkg.write_text(
        json.dumps({"items": rows, "legal": "PRELIMINAR"}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    mf.add_artifact(
        declare_file(pdf_path, role=ArtifactRole.EXECUTIVE_REPORT.value, title="Relatório PDF", primary=True)
    )
    mf.add_artifact(declare_file(xlsx_path, role=ArtifactRole.WORKBOOK.value, title="Workbook XLSX", primary=True))
    mf.add_artifact(
        declare_file(review_pkg, role=ArtifactRole.REVIEW_PACKAGE.value, title="Pacote de revisão", review_required=True)
    )
    for r in rows:
        mf.reviews_required.append(
            {
                "item_key": r["orgao"],
                "title": r["orgao"],
                "question": "A classificação jurídica preliminar está aceitável para seguir?",
                "evidence": r["classificacao_juridica_preliminar"] + " | " + r["objeto_recente"],
                "limitations": r["limitacoes"],
                "risks": f"Fracionamento: {r['risco_fracionamento']}; conflito: {r['conflito_interesse']}",
                "content_hash": sha256_file(source_path),
                "correctable_fields": ["classificacao_juridica_preliminar", "limitacoes"],
            }
        )
    emit("generating_report", "Gerando relatório", "succeeded")
    emit("awaiting_review", "Aguardando revisão", "waiting_review")
    return {"status": "SUCCEEDED", "message": f"{len(rows)} órgãos. Entregáveis prontos.", "reviews": mf.reviews_required}


def _run_documents(
    wf: WorkflowDef,
    params: dict[str, Any],
    out_dir: Path,
    mf: RunManifest,
    emit: ProgressCb,
    source_override: Path | None = None,
) -> dict[str, Any]:
    emit("collecting", "Coletando", "running", "Montando acervo documental")
    query = str(params.get("query") or "demo-processo-001")
    _ = source_override  # documents index regen uses fixture pack; override reserved for future
    pack = sample_data.process_documents(query=query)
    source_path = out_dir / "documents-index.json"
    source_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mf.coverage = pack["coverage"]
    mf.limitations.extend(pack["limitations"])
    docs_dir = out_dir / "documents"
    docs_dir.mkdir(exist_ok=True)
    # minimal valid-ish PDF stubs via reportlab for in-browser open
    from reportlab.pdfgen import canvas as pdf_canvas

    present_files: list[Path] = []
    for doc in pack["documents"]:
        if not doc["presente"]:
            continue
        p = docs_dir / doc["nome"]
        c = pdf_canvas.Canvas(str(p))
        c.setTitle(doc["nome"])
        c.drawString(72, 800, f"Documento fixture: {doc['nome']}")
        c.drawString(72, 780, f"Processo: {pack['processo_id']}")
        c.drawString(72, 760, f"Categoria: {doc['categoria']}")
        c.drawString(72, 740, f"Query: {query}")
        c.showPage()
        c.save()
        present_files.append(p)
        mf.add_artifact(
            declare_file(
                p,
                role=ArtifactRole.ATTACHMENT.value,
                title=doc["nome"],
                description=f"Categoria {doc['categoria']}",
            )
        )
    emit("collecting", "Coletando", "succeeded")
    emit("processing", "Processando", "running", "Calculando cobertura por categoria")
    emit("processing", "Processando", "succeeded")
    emit("generating_report", "Gerando relatório", "running")

    headers = ["Categoria", "Arquivo", "Presente", "Páginas"]
    data_rows = [
        [d["categoria"], d["nome"], "sim" if d["presente"] else "NÃO", d["paginas"]] for d in pack["documents"]
    ]
    pdf_path = out_dir / "relatorio-cobertura-documental.pdf"
    write_executive_pdf(
        pdf_path,
        title="Relatório de cobertura documental",
        client_label=wf.client_label,
        data_as_of=mf.data_as_of,
        executive_summary=(
            f"Consulta «{query}»: cobertura por categoria com ausências explícitas. "
            "Proposta vencedora ausente é reportada sem fabricação."
        ),
        conclusions=[
            f"Documentos presentes: {sum(1 for d in pack['documents'] if d['presente'])}.",
            "Categorias ausentes bloqueiam afirmações de completude.",
        ],
        indicators=[
            (k, f"{v['found']} encontrados · status={v['status']}") for k, v in pack["coverage"].items()
        ],
        table_headers=headers,
        table_rows=data_rows,
        methodology=[
            "Categorias separadas: edital/anexos, sessão/julgamento/homologação, proposta vencedora, habilitação.",
        ],
        sources=["Fixture process_documents / acervo local"],
        limitations=pack["limitations"],
        version_id=mf.run_id,
        provenance=_prov(mf, wf),
        brand="EXTRA",
    )
    xlsx_path = out_dir / "indice-documentos.xlsx"
    write_workbook(
        xlsx_path,
        title=f"Índice documental — {query}",
        summary_rows=[("Query", query), ("Processo", pack["processo_id"]), ("Run", mf.run_id)],
        data_headers=headers,
        data_rows=data_rows,
        methodology=["Índice gerado pelo Command Center."],
        sources=["Fixture/local"],
        limitations=pack["limitations"],
        provenance=_prov(mf, wf),
        sheet_data_name="Indice",
    )
    zip_path = out_dir / "documentos-selecionados.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in present_files:
            # safe names only — no path traversal
            zf.write(p, arcname=p.name)
    mf.add_artifact(
        declare_file(pdf_path, role=ArtifactRole.EXECUTIVE_REPORT.value, title="Cobertura PDF", primary=True)
    )
    mf.add_artifact(declare_file(xlsx_path, role=ArtifactRole.WORKBOOK.value, title="Índice XLSX", primary=True))
    mf.add_artifact(declare_file(zip_path, role=ArtifactRole.ATTACHMENT.value, title="ZIP documentos"))
    mf.add_artifact(declare_file(source_path, role=ArtifactRole.SOURCE_DATA.value, title="Índice JSON"))
    emit("generating_report", "Gerando relatório", "succeeded")
    return {
        "status": "SUCCEEDED",
        "message": "Cobertura e índice gerados; PDFs abrem no navegador.",
        "coverage": pack["coverage"],
    }
