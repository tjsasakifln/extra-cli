"""Markdown rendering of a ``confenge-dossier/1.0`` document.

Byte-stable for a given document: no wall-clock reads, no dict iteration order
dependence. The rendered file is the human deliverable; the JSON is the contract.
"""

from __future__ import annotations

from typing import Any

from scripts.dossier.constants import (
    DATA_READY,
    SECTION_BUYER_MAP,
    SECTION_COMPETITORS,
    SECTION_EXPIRING,
    SECTION_IDENTITY,
    SECTION_OPPORTUNITIES,
    SECTION_PRICE_PANEL,
    UNKNOWN,
)

STATE_LABEL = {
    "DATA_READY": "pronto",
    "DATA_HOLD": "retido por falta de evidência",
    "DATA_REJECT": "recusado",
}

POSITION_LABEL = {
    "BELOW_P25": "abaixo do p25 do painel",
    "P25_P50": "entre p25 e p50 do painel",
    "P50_P75": "entre p50 e p75 do painel",
    "ABOVE_P75": "acima do p75 do painel",
    "OUT_OF_PANEL_RANGE": "fora da faixa do painel — sem posição percentílica",
    UNKNOWN: UNKNOWN,
}


def _brl(value: Any) -> str:
    if value in (None, "", UNKNOWN):
        return UNKNOWN
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    inteiro, _, centavos = f"{number:,.2f}".partition(".")
    return "R$ " + inteiro.replace(",", ".") + "," + centavos


def _section(document: dict[str, Any], section_id: str) -> dict[str, Any]:
    section = document.get("sections", {}).get(section_id, {})
    return section if isinstance(section, dict) else {}


def _payload(document: dict[str, Any], section_id: str) -> dict[str, Any]:
    return _section(document, section_id).get("payload", {}) or {}


def _state_line(document: dict[str, Any], section_id: str) -> str:
    section = _section(document, section_id)
    state = section.get("state", UNKNOWN)
    label = STATE_LABEL.get(state, state)
    reasons = section.get("reason_codes") or []
    suffix = f" — códigos: {', '.join(reasons)}" if reasons else ""
    return f"*Estado da seção: {label} (`{state}`), {section.get('row_count', 0)} registros{suffix}.*"


def render_markdown(document: dict[str, Any]) -> str:
    identity = _payload(document, SECTION_IDENTITY)
    lines: list[str] = []
    nome = identity.get("razao_social") or UNKNOWN

    lines.append(f"# Diagnóstico B2G — {nome}")
    lines.append("")
    lines.append(f"- Documento: `{document.get('dossier_id')}`")
    lines.append(f"- Schema: `{document.get('schema')}` ({document.get('contract_version')})")
    lines.append(f"- Modo de catálogo: `{document.get('catalog_mode')}`")
    lines.append(
        f"- Estado dos dados: `{document.get('data_state')}` ({STATE_LABEL.get(str(document.get('data_state')), '')})"
    )
    lines.append(f"- Data de referência: `{document.get('as_of')}`")
    lines.append(f"- Observado em: `{document.get('observed_at') or UNKNOWN}`")
    lines.append(f"- Hash de conteúdo: `{document.get('content_hash')}`")
    lines.append(f"- Produtor: `{document.get('producer')}` @ `{document.get('producer_sha') or UNKNOWN}`")
    lines.append("")
    if document.get("data_state") != DATA_READY:
        lines.append(
            "> Este documento não está em estado pronto. As seções retidas indicam falta de "
            "evidência, não ausência do fato."
        )
        lines.append("")

    lines.append("## 1. Identificação")
    lines.append("")
    lines.append(_state_line(document, SECTION_IDENTITY))
    lines.append("")
    lines.append("| Campo | Valor |")
    lines.append("| --- | --- |")
    for label, key in (
        ("Razão social", "razao_social"),
        ("CNPJ", "cnpj14"),
        ("CNAE principal", "cnae_principal"),
        ("Situação cadastral", "situacao_cadastral"),
        ("Município", "municipio"),
        ("UF", "uf"),
        ("Fonte cadastral", "registry_source"),
        ("Data da fonte", "registry_source_date"),
    ):
        lines.append(f"| {label} | {identity.get(key, UNKNOWN)} |")
    lines.append("")

    buyer_map = _payload(document, SECTION_BUYER_MAP)
    lines.append("## 2. Mapa de compradores")
    lines.append("")
    lines.append(_state_line(document, SECTION_BUYER_MAP))
    lines.append("")
    lines.append(
        f"Compradores distintos: **{buyer_map.get('buyer_count', UNKNOWN)}** · "
        f"contratos: **{buyer_map.get('contract_count', UNKNOWN)}** · "
        f"valor conhecido: **{_brl(buyer_map.get('valor_sum_valued'))}** · "
        f"HHI: **{buyer_map.get('hhi', UNKNOWN)}**"
    )
    lines.append("")
    lines.append("| Comprador | UF | Contratos | Valor conhecido | Participação | Último fim |")
    lines.append("| --- | --- | ---: | ---: | ---: | --- |")
    for buyer in buyer_map.get("buyers", []):
        share = buyer.get("share_of_valued")
        share_text = UNKNOWN if share is None else f"{share * 100:.1f}%"
        lines.append(
            f"| {buyer.get('buyer_nome', UNKNOWN)} | {buyer.get('uf', UNKNOWN)} | "
            f"{buyer.get('contract_count', UNKNOWN)} | {_brl(buyer.get('valor_sum'))} | "
            f"{share_text} | {buyer.get('last_data_fim', UNKNOWN)} |"
        )
    lines.append("")

    competitors = _payload(document, SECTION_COMPETITORS)
    lines.append("## 3. Concorrentes na categoria principal")
    lines.append("")
    lines.append(_state_line(document, SECTION_COMPETITORS))
    lines.append("")
    lines.append(f"Categoria principal identificada: **{competitors.get('primary_category', UNKNOWN)}**.")
    lines.append("")
    lines.append(f"Regra de seleção: {competitors.get('selection_rule', UNKNOWN)}.")
    lines.append("")
    lines.append(
        "| Fornecedor | Contratos | Com valor publicado | Compradores em comum | Categorias | Valor conhecido |"
    )
    lines.append("| --- | ---: | ---: | ---: | --- | ---: |")
    for competitor in competitors.get("competitors", []):
        categorias = ", ".join(competitor.get("shared_categories") or []) or UNKNOWN
        lines.append(
            f"| {competitor.get('supplier_nome', UNKNOWN)} | {competitor.get('contract_count', UNKNOWN)} | "
            f"{competitor.get('valued_count', UNKNOWN)} | {competitor.get('shared_buyer_count', UNKNOWN)} | "
            f"{categorias} | {_brl(competitor.get('valor_sum'))} |"
        )
    lines.append("")

    price_panel = _payload(document, SECTION_PRICE_PANEL)
    lines.append("## 4. Painel de preços por categoria")
    lines.append("")
    lines.append(_state_line(document, SECTION_PRICE_PANEL))
    lines.append("")
    lines.append(
        f"Semântica de valor: `{price_panel.get('value_semantic', UNKNOWN)}` · "
        f"unidade: `{price_panel.get('unit', UNKNOWN)}`."
    )
    lines.append("")
    lines.append(f"Escopo solicitado: `{price_panel.get('requested_scope', UNKNOWN)}`.")
    lines.append("")
    lines.append("| Scope | Estado | Geografia | Amostra | Cobertura | As of | Fonte/versão | Hash |")
    lines.append("| --- | --- | --- | ---: | ---: | --- | --- | --- |")
    for panel in price_panel.get("panels", []):
        source = panel.get("source") or {}
        lines.append(
            f"| `{panel.get('scope_id', UNKNOWN)}` | `{panel.get('state', UNKNOWN)}` | "
            f"`{panel.get('geography', UNKNOWN)}` | {panel.get('sample_count', UNKNOWN)} | "
            f"{panel.get('coverage', UNKNOWN)} | {panel.get('as_of', UNKNOWN)} | "
            f"{source.get('id', UNKNOWN)}/{source.get('version', UNKNOWN)} | "
            f"`{panel.get('hash', UNKNOWN)}` |"
        )
        if panel.get("limitations"):
            lines.append("")
            lines.append(
                f"Limitações de `{panel.get('scope_id', UNKNOWN)}`: "
                + "; ".join(str(item) for item in panel["limitations"])
            )
    if price_panel.get("out_of_range_category_count"):
        lines.append("")
        lines.append(
            f"{price_panel['out_of_range_category_count']} categoria(s) ficaram fora da faixa do "
            f"painel por fator maior que {price_panel.get('out_of_range_factor')}x. Para essas, "
            "nenhuma posição percentílica é declarada: a categoria agrega objetos de porte "
            "incomparável."
        )
    lines.append("")
    lines.append(
        "| Categoria | Contratos da empresa | Mediana da empresa | p25 painel | p50 painel | p75 painel | Posição |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for category in price_panel.get("categories", []):
        lines.append(
            f"| {category.get('categoria', UNKNOWN)} | {category.get('focal_contract_count', UNKNOWN)} | "
            f"{_brl(category.get('focal_median'))} | {_brl(category.get('reference_p25'))} | "
            f"{_brl(category.get('reference_p50'))} | {_brl(category.get('reference_p75'))} | "
            f"{POSITION_LABEL.get(category.get('focal_position'), category.get('focal_position', UNKNOWN))} |"
        )
    lines.append("")

    expiring = _payload(document, SECTION_EXPIRING)
    lines.append(f"## 5. Contratos a vencer em até {expiring.get('window_days', UNKNOWN)} dias")
    lines.append("")
    lines.append(_state_line(document, SECTION_EXPIRING))
    lines.append("")
    lines.append("| Contrato | Órgão | Fim | Dias | Valor |")
    lines.append("| --- | --- | --- | ---: | ---: |")
    for contract in expiring.get("contracts", []):
        lines.append(
            f"| `{contract.get('contrato_id', UNKNOWN)}` | {contract.get('orgao_nome', UNKNOWN)} | "
            f"{contract.get('data_fim', UNKNOWN)} | {contract.get('dias_ate_fim', UNKNOWN)} | "
            f"{_brl(contract.get('valor'))} |"
        )
    lines.append("")

    opportunities = _payload(document, SECTION_OPPORTUNITIES)
    lines.append("## 6. Editais abertos de compradores já conhecidos")
    lines.append("")
    lines.append(_state_line(document, SECTION_OPPORTUNITIES))
    lines.append("")
    if opportunities.get("opportunities"):
        lines.append("| Edital | Órgão | Encerramento | Valor estimado |")
        lines.append("| --- | --- | --- | ---: |")
        for opportunity in opportunities.get("opportunities", []):
            lines.append(
                f"| `{opportunity.get('bid_id', UNKNOWN)}` | {opportunity.get('orgao_nome', UNKNOWN)} | "
                f"{opportunity.get('data_encerramento', UNKNOWN)} | {_brl(opportunity.get('valor_estimado'))} |"
            )
    else:
        lines.append(
            "Nenhum edital aberto foi observado para os compradores desta carteira na data de "
            "referência. Ausência de observação não é ausência de edital."
        )
    lines.append("")

    lines.append("## 7. Achados")
    lines.append("")
    lines.append(
        "Cada achado é um fato observado mais a pergunta que ele abre. Nenhum achado afirma "
        "direito, desequilíbrio econômico-financeiro, dano ou que um reajuste seja devido."
    )
    lines.append("")
    for finding in document.get("findings", []):
        lines.append(f"### `{finding.get('finding_id')}` — {finding.get('subject')}")
        lines.append("")
        lines.append(f"- Fato: {finding.get('fact')}")
        lines.append(f"- Pergunta: {finding.get('question')}")
        lines.append(f"- Evidência: {', '.join(finding.get('evidence_refs', [])) or UNKNOWN}")
        lines.append(f"- Severidade: `{finding.get('severity')}`")
        lines.append("")

    lines.append("## 8. Limitações declaradas")
    lines.append("")
    for limitation in document.get("limitations", []):
        lines.append(f"- {limitation}")
    lines.append("")
    if document.get("reason_codes"):
        lines.append(f"Códigos de razão: {', '.join(document['reason_codes'])}.")
        lines.append("")

    return "\n".join(lines)
