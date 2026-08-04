"""Markdown reports, CSV/JSON, dossiers, run manifest."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.commercial.reajuste_14133 import MODULE_VERSION, STATUS_HOT_VERIFIED


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _safe_filename(cnpj: str, contrato_id: str) -> str:
    c = re.sub(r"\D", "", cnpj or "semcnpj")[:14]
    cid = re.sub(r"[^\w.-]+", "_", contrato_id or "semcontrato")[:80]
    return f"{c}_{cid}"


def lead_flat_row(lead: dict[str, Any]) -> dict[str, Any]:
    """Flatten lead for CSV/Excel commercial use."""
    decomp = lead.get("score_decomposition") or {}
    decomp_s = "; ".join(f"{k}={v}" for k, v in decomp.items())
    pen = lead.get("score_penalties") or {}
    pen_s = "; ".join(f"{k}={v}" for k, v in pen.items())
    cont = lead.get("canais_contato") or {}
    return {
        "ranking": lead.get("ranking"),
        "classificacao": lead.get("classificacao"),
        "score_total": lead.get("score_total"),
        "score_decomposition": decomp_s,
        "score_penalties": pen_s,
        "cnpj": lead.get("cnpj"),
        "razao_social": lead.get("razao_social"),
        "nome_fantasia": lead.get("nome_fantasia"),
        "municipio_empresa": lead.get("municipio_empresa"),
        "uf": lead.get("uf"),
        "orgao_contratante": lead.get("orgao_contratante"),
        "orgao_cnpj": lead.get("orgao_cnpj"),
        "contrato_id": lead.get("contrato_id"),
        "objeto": (lead.get("objeto") or "")[:500],
        "classificacao_obra": lead.get("classificacao_obra"),
        "valor_original": lead.get("valor_original"),
        "valor_atualizado": lead.get("valor_atualizado"),
        "saldo_conhecido": lead.get("saldo_conhecido"),
        "regime_legal": lead.get("regime_legal"),
        "regime_proven": lead.get("regime_proven"),
        "data_base": lead.get("data_base"),
        "data_base_status": lead.get("data_base_status"),
        "data_base_source": lead.get("data_base_source"),
        "indice": lead.get("indice"),
        "data_proximo_reajuste": lead.get("data_proximo_reajuste"),
        "dias_atraso_potencial": lead.get("dias_atraso_potencial"),
        "vigencia_final": lead.get("vigencia_final"),
        "percentual_reajuste": lead.get("percentual_reajuste"),
        "base_potencialmente_reajustavel": lead.get("base_potencialmente_reajustavel"),
        "base_label": lead.get("base_label"),
        "valor_potencial": lead.get("valor_potencial"),
        "teto_teorico": lead.get("teto_teorico"),
        "teto_label": lead.get("teto_label"),
        "status_reajustes_anteriores": lead.get("status_reajustes_anteriores"),
        "evidencias_favoraveis": " | ".join(lead.get("evidencias_favoraveis") or []),
        "lacunas": " | ".join(lead.get("lacunas") or []),
        "riscos": " | ".join(lead.get("riscos") or []),
        "proxima_acao_investigativa": lead.get("proxima_acao_investigativa"),
        "argumento_comercial": lead.get("argumento_comercial"),
        "email_comercial": cont.get("email"),
        "telefone_empresarial": cont.get("telefone"),
        "site_oficial": cont.get("site"),
        "urls_oficiais": " | ".join(lead.get("urls_oficiais") or []),
        "hot_gates_passed": lead.get("hot_gates_passed"),
        "timestamp_analise": lead.get("timestamp_analise"),
    }


FIELD_DICTIONARY: list[tuple[str, str]] = [
    ("ranking", "Posição no ranking comercial (maior score primeiro; desempate determinístico)"),
    ("classificacao", "Status do funil: HOT_VERIFIED, STRONG_CANDIDATE, REVIEW_REQUIRED, etc."),
    ("score_total", "Score 0–100 decomponível (não é probabilidade de conversão)"),
    ("data_base", "Data-base efetiva usada na análise (pode ser proxy de prospecção)"),
    ("data_base_status", "CONFIRMED | PROXY_PROSPECTION_ONLY | MISSING"),
    ("valor_potencial", "Valor potencialmente reclamável só com índice+série+base reajustável"),
    ("teto_teorico", "Teto teórico (UPPER_BOUND_NOT_CLAIM_VALUE) — não é valor devido"),
    ("regime_proven", "True apenas com campo estruturado ou documento oficial"),
    ("indice", "Índice contratual localizado no instrumento — nunca inventado"),
]


def write_csv_json(out_dir: Path, run: dict[str, Any]) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    leads = run.get("top_leads") or run.get("leads") or []
    flat = [lead_flat_row(lead) for lead in leads]

    p_csv = out_dir / "leads_reajuste_14133.csv"
    if flat:
        fields = list(flat[0].keys())
    else:
        fields = ["ranking", "classificacao", "cnpj", "contrato_id"]
    with p_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in flat:
            w.writerow(row)
    paths["csv"] = str(p_csv)

    p_json = out_dir / "leads_reajuste_14133.json"
    _write_json(p_json, {
        "run_id": run.get("run_id"),
        "as_of": run.get("as_of"),
        "module_version": MODULE_VERSION,
        "leads": leads,
        "funnel": run.get("funnel"),
        "metrics": run.get("metrics"),
        "language_policy": run.get("language_policy"),
    })
    paths["json"] = str(p_json)

    p_ex = out_dir / "excluded_reasons.csv"
    excl = run.get("excluded") or []
    with p_ex.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["contrato_id", "cnpj", "reason", "detail"])
        w.writeheader()
        for e in excl:
            w.writerow({
                "contrato_id": e.get("contrato_id"),
                "cnpj": e.get("cnpj"),
                "reason": e.get("reason"),
                "detail": json.dumps(e.get("detail"), ensure_ascii=False, default=str) if e.get("detail") else "",
            })
    paths["excluded_csv"] = str(p_ex)

    p_man = out_dir / "run_manifest.json"
    manifest = {
        k: run.get(k)
        for k in (
            "run_id", "as_of", "module_version", "campaign", "git_sha",
            "source_mode", "source_dsn_masked", "started_at", "finished_at",
            "params", "funnel", "metrics", "language_policy",
        )
    }
    # secret scan hard fail later
    _write_json(p_man, manifest)
    paths["manifest"] = str(p_man)
    return paths


def write_methodology(out_dir: Path) -> Path:
    text = f"""# Metodologia — Reajuste em sentido estrito (Lei nº 14.133/2021)

**Módulo:** `{MODULE_VERSION}`
**Campanha:** reajuste periódico por índice contratual
**NÃO cobre:** reequilíbrio econômico-financeiro, repactuação de mão de obra, atualização monetária por atraso de pagamento, aditivo quantitativo.

## Fundamento jurídico mínimo

- Lei nº 14.133/2021, art. 6º, LVIII (reajustamento)
- art. 25, § 7º (índice e data-base do orçamento estimado)
- art. 92, V e § 3º (cláusulas necessárias)
- art. 123 e art. 136, I (apostila)
- Lei nº 10.192/2001 (periodicidade mínima anual)
- Orientação TCU sobre reajuste em sentido estrito

## Premissas operacionais

1. Data-base vinculada à data do **orçamento estimado**.
2. Primeiro reajuste somente após interregno anual.
3. Assinatura, publicação, OS e início de execução **não** são data-base automática.
4. Índice deve constar do edital/contrato — nunca inventado (IPCA/INCC/SINAPI por “plausibilidade” é proibido).
5. Reajuste ordinário pode ser registrado por **apostila**.
6. Ausência de apostila no PNCP **não prova** que o reajuste não foi concedido.
7. Ausência de cláusula é inconsistência documental — o sistema **não inventa** índice/data-base.
8. Ferramenta **qualifica oportunidades**; não emite conclusão jurídica definitiva.

## Funil de classificação

| Status | Significado |
|--------|-------------|
| HOT_VERIFIED | 10 gates documentais atendidos |
| STRONG_CANDIDATE | Forte probabilidade; falta confirmação pontual |
| REVIEW_REQUIRED | Indício relevante com lacunas |
| RESEARCH_REQUIRED | Dados insuficientes para abordagem responsável |
| ALREADY_ADJUSTED | Evidência de reajuste do período |
| NOT_ELIGIBLE | Fora das regras materiais/temporais |
| LEGAL_REGIME_UNKNOWN | Regime 14.133 não comprovado |
| CLOSED_OR_FINANCIALLY_EXHAUSTED | Encerrado / sem saldo |

**Regra dura:** nenhum `HOT_VERIFIED` pode depender apenas de datas de `pncp_supplier_contracts`.

## Scoring comercial

- 25% confiança jurídica/documental
- 20% atratividade financeira
- 15% urgência temporal
- 15% saldo reajustável provável
- 10% aderência ICP CONFENGE
- 10% contatabilidade empresarial
- 5% qualidade das fontes

Penalidades: regime não confirmado, data-base ausente, índice ausente, encerramento próximo sem docs, execução concluída, reajuste já publicado, contradições, fornecedor gigante, micro vs ticket, contato apenas pessoal.

## Finanças

- `valor_potencial`: só com índice contratual + série oficial + base reajustável conhecida.
- `teto_teorico` / `UPPER_BOUND_NOT_CLAIM_VALUE`: envelope sobre valor total **sem** pretensão de valor devido.

## Limitações honestas

- Schema PNCP estruturado **não** traz data-base de orçamento, índice nem regime legal nativos.
- `process_documents` pode estar vazio no snapshot; fetches HTML/PDF são parciais.
- Classificação de obra é híbrida (regras + vocabulário negativo), sem LLM operacional em massa.
- Contatos apenas de fontes empresariais públicas (LGPD).
"""
    p = out_dir / "methodology.md"
    p.write_text(text, encoding="utf-8")
    return p


def write_data_quality(out_dir: Path, run: dict[str, Any]) -> Path:
    funnel = run.get("funnel") or {}
    metrics = run.get("metrics") or {}
    excl = run.get("excluded") or []
    reasons = Counter(str(e.get("reason") or "unknown") for e in excl)
    top_reasons = reasons.most_common(20)
    lines = [
        "# Data Quality Report — reajuste_14133",
        "",
        f"- run_id: `{run.get('run_id')}`",
        f"- as_of: `{run.get('as_of')}`",
        f"- source_mode: `{run.get('source_mode')}`",
        f"- source (masked): `{run.get('source_dsn_masked')}`",
        "",
        "## Funil",
        "",
    ]
    for k, v in funnel.items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## Métricas", ""]
    for k, v in metrics.items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## Principais exclusões", ""]
    for reason, n in top_reasons:
        lines.append(f"- `{reason}`: {n}")
    lines += [
        "",
        "## Gaps estruturais do datalake",
        "",
        "- Sem coluna nativa de data do orçamento estimado em `pncp_supplier_contracts`.",
        "- Sem coluna nativa de índice contratual ou regime legal estruturado.",
        "- Document harvest (`process_documents`) pode estar vazio → HOT_VERIFIED raro/zero é esperado (fail-closed).",
        "- Proxy de data-base (assinatura/início/publicação) só para prospecção.",
        "",
        "## Política de linguagem",
        "",
        json.dumps(run.get("language_policy") or {}, ensure_ascii=False, indent=2),
        "",
    ]
    p = out_dir / "data_quality_report.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def write_executive_brief(out_dir: Path, run: dict[str, Any], manual_review: list[dict[str, Any]] | None = None) -> Path:
    funnel = run.get("funnel") or {}
    metrics = run.get("metrics") or {}
    top = run.get("top_leads") or []
    lines = [
        "# Executive Brief — Fila comercial reajuste 14.133/2021 (CONFENGE)",
        "",
        f"**Data de referência (as-of):** {run.get('as_of')}  ",
        f"**Run:** `{run.get('run_id')}`  ",
        f"**Fonte (masked):** `{run.get('source_dsn_masked')}` ({run.get('source_mode')})",
        "",
        "## O que é esta fila",
        "",
        "Fila auditável de contratos públicos de **construção civil** com indícios de",
        "**reajuste periódico por índice** (sentido estrito), para oferta de:",
        "",
        "> Diagnóstico de elegibilidade, recuperação documental, memória de cálculo,",
        "> apuração de valores potencialmente devidos e estruturação técnica do pedido",
        "> administrativo de reajuste contratual.",
        "",
        "**Não é** parecer jurídico. **Não afirma** direito a valor sem prova documental.",
        "",
        "## Funil (contagens)",
        "",
        "| Etapa | N |",
        "|-------|---|",
        f"| Examinados (pré-filtro SQL) | {funnel.get('examined_raw', 0)} |",
        f"| Após dedupe | {funnel.get('after_dedupe', 0)} |",
        f"| Fornecedor privado | {funnel.get('private_supplier', 0)} |",
        f"| Objeto construção | {funnel.get('construction', 0)} |",
        f"| Regime 14.133 comprovado | {funnel.get('regime_14133_proven', 0)} |",
        f"| Temporalmente maduros | {funnel.get('temporally_mature', 0)} |",
        f"| Data-base confirmada | {funnel.get('data_base_confirmed', 0)} |",
        f"| Índice localizado | {funnel.get('index_located', 0)} |",
        f"| Já reajustados (evidência) | {funnel.get('already_adjusted', 0)} |",
        f"| HOT_VERIFIED | {funnel.get(STATUS_HOT_VERIFIED, 0)} |",
        f"| STRONG_CANDIDATE | {funnel.get('STRONG_CANDIDATE', 0)} |",
        f"| REVIEW_REQUIRED | {funnel.get('REVIEW_REQUIRED', 0)} |",
        f"| LEGAL_REGIME_UNKNOWN | {funnel.get('LEGAL_REGIME_UNKNOWN', 0)} |",
        "",
        f"- Valor potencial agregado (top): **R$ {metrics.get('valor_potencial_agregado_top', 0):,.2f}**",
        f"- Teto teórico agregado (top, não claim): **R$ {metrics.get('teto_teorico_agregado_top', 0):,.2f}**",
        "",
        "## Top 10 leads (sem PII pessoal)",
        "",
    ]
    for lead in top[:10]:
        lines.append(
            f"- **#{lead.get('ranking')}** {lead.get('classificacao')} score={lead.get('score_total')} "
            f"UF={lead.get('uf')} valor≈R$ {float(lead.get('valor_atualizado') or 0):,.0f} "
            f"CNPJ=`{str(lead.get('cnpj') or '')[:8]}****` "
            f"contrato=`{lead.get('contrato_id')}` "
            f"data_base_status={lead.get('data_base_status')}"
        )
    lines += ["", "## Human desk review top-30", ""]
    lines.append(
        "Fonte canônica: `human_desk_review_top30.md` / `.json` (notas humanas por lead). "
        "`automated_object_triage.json` é **máquina** e não conta como revisão humana."
    )
    lines.append("")
    if manual_review:
        for item in manual_review[:30]:
            lines.append(
                f"- `#{item.get('rank', '?')}` contrato `{item.get('contrato_id')}`: "
                f"**{item.get('decision')}** "
                f"(FP={item.get('false_positive')}; incerteza={item.get('uncertainty')}; "
                f"doc={item.get('document_consulted')})"
            )
        metrics = run.get("metrics") or {}
        if metrics.get("human_desk_review_keep_rate") is not None:
            lines.append("")
            lines.append(
                f"- Mantidos na fila: {metrics.get('human_desk_review_kept_in_queue')} / "
                f"{metrics.get('human_desk_review_count')} "
                f"(keep_rate={metrics.get('human_desk_review_keep_rate')}; "
                f"FP objeto={metrics.get('human_desk_review_false_positives')})"
            )
    else:
        lines.append(
            "_Sem `human_desk_review_top30.json` neste diretório — "
            "apenas triagem automática se `--manual-review` foi usado._"
        )
    lines += [
        "",
        "## Próximo passo CONFENGE",
        "",
        "1. Priorizar `STRONG_CANDIDATE` e `REVIEW_REQUIRED` com maior score no Sul/SC.",
        "2. Solicitar à construtora: contrato, planilha orçamentária (data-base), apostilas, medições.",
        "3. Só então montar memória de cálculo e minuta de pedido administrativo.",
        "",
    ]
    p = out_dir / "executive_brief.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def build_dossier_md(lead: dict[str, Any]) -> str:
    """13-section commercial dossier (non-claim language)."""
    cnpj = lead.get("cnpj")
    cid = lead.get("contrato_id")
    sections = []
    sections.append(f"# Dossier reajuste 14.133 — {lead.get('razao_social')}")
    sections.append("")
    sections.append(f"- CNPJ: `{cnpj}`")
    sections.append(f"- Contrato: `{cid}`")
    sections.append(f"- Classificação: **{lead.get('classificacao')}** | Score: **{lead.get('score_total')}**")
    sections.append(f"- Ranking: #{lead.get('ranking')} ({lead.get('ranking_bucket')})")
    sections.append("")
    sections.append("## 1. Resumo executivo")
    sections.append("")
    sections.append(
        f"Contrato com órgão **{lead.get('orgao_contratante')}** (UF {lead.get('uf')}), "
        f"objeto classificado como **{lead.get('classificacao_obra')}**, "
        f"valor observado ≈ R$ {float(lead.get('valor_atualizado') or 0):,.2f}. "
        f"Status de data-base: **{lead.get('data_base_status')}**. "
        "Identificamos indícios documentais de que o contrato pode possuir reajuste periódico "
        "ainda não localizado nas publicações consultadas. A confirmação depende da análise do "
        "contrato, das medições e das apostilas emitidas."
    )
    sections.append("")
    sections.append("## 2. Por que o contrato entrou no radar")
    sections.append("")
    for e in lead.get("evidencias_favoraveis") or []:
        sections.append(f"- {e}")
    sections.append("")
    sections.append("## 3. Linha do tempo")
    sections.append("")
    d = lead.get("dates") or {}
    for key in (
        "orcamento_estimado", "data_assinatura", "data_publicacao",
        "inicio_vigencia", "fim_vigencia", "ultimo_reajuste", "data_base_effective",
    ):
        field = d.get(key) or {}
        sections.append(
            f"- **{key}**: {field.get('value')} (fonte={field.get('source')}, conf={field.get('confidence')})"
        )
    sections.append(
        f"- Próximo aniversário: {lead.get('data_proximo_reajuste')} | "
        f"Dias desde aplicável: {lead.get('dias_atraso_potencial')}"
    )
    sections.append("")
    sections.append("## 4. Fundamento jurídico aplicável")
    sections.append("")
    sections.append(
        "Reajuste em sentido estrito (Lei 14.133/2021 arts. 6º LVIII, 25 §7º, 92 V e §3º, "
        "123, 136 I; Lei 10.192/2001 — anualidade). "
        f"Regime classificado: `{lead.get('regime_legal')}` "
        f"(comprovado={lead.get('regime_proven')}). {lead.get('regime_notes') or ''}"
    )
    sections.append("")
    sections.append("## 5. Cláusula e índice encontrados")
    sections.append("")
    sections.append(f"- Índice: `{lead.get('indice') or 'NÃO LOCALIZADO'}`")
    sections.append(f"- Data-base: `{lead.get('data_base')}` status=`{lead.get('data_base_status')}`")
    sections.append("- Sem invenção de cláusula: ausência ⇒ lacuna documental.")
    sections.append("")
    sections.append("## 6. Cálculo preliminar")
    sections.append("")
    fin = lead.get("finance") or {}
    sections.append(f"- Base: {lead.get('base_label')} = {lead.get('base_potencialmente_reajustavel')}")
    sections.append(f"- Percentual: {lead.get('percentual_reajuste')}")
    sections.append(f"- Valor potencial: {lead.get('valor_potencial')} (só se índice+série+base)")
    sections.append(f"- Teto teórico: {lead.get('teto_teorico')} ({lead.get('teto_label')})")
    sections.append(f"- Limitações: {', '.join(fin.get('limitations') or lead.get('riscos') or [])}")
    sections.append("")
    sections.append("## 7. Evidências oficiais")
    sections.append("")
    for u in lead.get("urls_oficiais") or []:
        sections.append(f"- {u}")
    doc = lead.get("doc_scan") or {}
    for e in (doc.get("evidences") or [])[:15]:
        sections.append(
            f"- [{e.get('doc_type')}] {e.get('field_found')}: {e.get('excerpt', '')[:200]} "
            f"(conf={e.get('confidence')}, método={e.get('extraction_method')})"
        )
    sections.append("")
    sections.append("## 8. Lacunas documentais")
    sections.append("")
    for g in lead.get("lacunas") or ["Nenhuma registrada"]:
        sections.append(f"- {g}")
    sections.append("")
    sections.append("## 9. Riscos e fatores que podem afastar o reajuste")
    sections.append("")
    for r in lead.get("riscos") or []:
        sections.append(f"- {r}")
    sections.append("- Reajuste já concedido por apostila não publicada no PNCP.")
    sections.append("- Contrato sem cláusula de reajuste (inconsistência a sanar, não a inventar).")
    sections.append("")
    sections.append("## 10. Documentos a solicitar à construtora")
    sections.append("")
    for dname in (
        "Edital e anexos (planilha orçamentária / data-base)",
        "Contrato integral e aditivos",
        "Apostilas de reajuste (se houver)",
        "Medições e cronograma físico-financeiro",
        "Ordem de serviço e prorrogações",
        "Comprovantes de pagamento / empenhos relevantes",
    ):
        sections.append(f"- {dname}")
    sections.append("")
    sections.append("## 11. Estratégia recomendada de abordagem")
    sections.append("")
    sections.append(
        "Contato empresarial com foco em **diagnóstico de elegibilidade** e organização documental. "
        "Não prometer valor. Oferecer trilha: diagnóstico → memória de cálculo → pedido administrativo."
    )
    sections.append("")
    sections.append("## 12. Frase personalizada de abertura comercial")
    sections.append("")
    sections.append(f"> {lead.get('argumento_comercial')}")
    sections.append("")
    sections.append("## 13. Próximo passo da CONFENGE")
    sections.append("")
    sections.append(lead.get("proxima_acao_investigativa") or "Revisão humana documental.")
    sections.append("")
    sections.append(f"_Gerado em {lead.get('timestamp_analise')} · módulo {lead.get('module_version')}_")
    return "\n".join(sections)


def write_dossiers(out_dir: Path, leads: list[dict[str, Any]], *, n: int = 30) -> list[str]:
    ddir = out_dir / "dossiers"
    ddir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for lead in leads[:n]:
        name = _safe_filename(str(lead.get("cnpj") or ""), str(lead.get("contrato_id") or ""))
        p = ddir / f"{name}.md"
        p.write_text(build_dossier_md(lead), encoding="utf-8")
        paths.append(str(p))
    return paths


def assert_no_secrets(out_dir: Path) -> list[str]:
    """Scan artifacts for credential-like strings (ignore already-masked DSNs)."""
    bad: list[str] = []
    # Real password in DSN (not *** mask)
    dsn_secret = re.compile(r"postgresql://[^:/@]+:(?!\*\*\*)[^@\s]+@")
    patterns = [
        dsn_secret,
        re.compile(r"password\s*=\s*(?!\*+)(\S+)", re.I),
        re.compile(r"-----BEGIN (RSA |OPENSSH )?PRIVATE KEY-----"),
    ]
    for p in out_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in {".xlsx", ".png", ".jpg", ".pdf"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in patterns:
            if pat.search(text):
                bad.append(str(p))
                break
    return bad
