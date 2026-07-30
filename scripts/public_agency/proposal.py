"""Scope-based proposal generator with mandatory legal disclaimer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.public_agency.fiscal_support import check_commercial_text
from scripts.public_agency.fragmentation import price_from_scope

LEGAL_DISCLAIMER = (
    "A definição do fundamento e do procedimento de contratação compete exclusivamente "
    "ao órgão ou entidade contratante, conforme sua regulamentação, análise jurídica e "
    "controles internos. A CONFENGE não afirma direito à contratação direta nem garante "
    "enquadramento em dispensa de licitação."
)


def generate_proposal(
    *,
    agency_name: str,
    problem: str,
    object_text: str,
    service: dict[str, Any],
    deliverables: list[str],
    effort_hours: float,
    hourly_rate: float = 250.0,
    visits: int = 0,
    travel_cost: float = 0.0,
    complexity_factor: float = 1.0,
    margin: float = 0.15,
    taxes: float = 0.0,
    object_classification: dict[str, Any] | None = None,
    eligibility: dict[str, Any] | None = None,
    validity_days: int = 30,
) -> dict[str, Any]:
    pricing = price_from_scope(
        effort_hours=effort_hours,
        hourly_rate=hourly_rate,
        travel_cost=travel_cost,
        inspections=visits,
        inspection_cost=500.0 if visits else 0.0,
        complexity_factor=complexity_factor,
        margin=margin,
        taxes=taxes,
        ceiling=(eligibility or {}).get("threshold_amount"),
    )

    body_md = f"""# Proposta técnica e comercial — CONFENGE

**Órgão:** {agency_name}  
**Objeto:** {object_text}  
**Oferta:** {service.get('nome') or service.get('service_id')}  
**Validade:** {validity_days} dias  

## 1. Problema

{problem}

## 2. Escopo

{service.get('escopo') or ''}

## 3. Entregáveis

{chr(10).join(f'- {d}' for d in deliverables)}

## 4. Exclusões

{chr(10).join(f'- {e}' for e in (service.get('exclusoes') or []))}

## 5. Premissas

- Documentos técnicos são minutas para validação e aprovação da Administração.
- Apoio à fiscalização, quando aplicável, assiste e subsidia o fiscal/gestor (art. 117) sem substituição de competências exclusivas.
- Preço formado por escopo/esforço/responsabilidade técnica — não por teto de dispensa.

## 6. Formação de preço

| Item | Valor |
|------|-------|
| Horas estimadas | {effort_hours} |
| Taxa horária (R$) | {hourly_rate} |
| Visitas/inspeções | {visits} |
| Deslocamentos (R$) | {travel_cost} |
| Fator de complexidade | {complexity_factor} |
| Margem | {margin} |
| **Preço proposto (R$)** | **{pricing['proposed_price']}** |

Método: `{pricing['pricing_method']}`  
Âncora no teto legal: `{pricing['ceiling_used_as_price_anchor']}`

## 7. Classificação jurídica preliminar

- Classe: {(object_classification or {}).get('suggested_class')}
- Confiança: {(object_classification or {}).get('confidence')}
- Elegibilidade potencial: {(eligibility or {}).get('eligibility_state')}

## 8. Cronograma

Conforme duração estimada do catálogo: {service.get('duracao_estimada') or 'a combinar'}.

## 9. Matriz de responsabilidades

| Parte | Responsabilidade |
|-------|------------------|
| CONFENGE | Entregas técnicas contratadas; ART quando cabível |
| Órgão | Validação, decisão administrativa, fiscalização formal, pagamentos |

## 10. Ressalva legal

{LEGAL_DISCLAIMER}

---
*CONFENGE — capacidade técnica, redução de risco e qualidade documental.*
"""

    lang = check_commercial_text(body_md)
    if not lang.allowed:
        raise ValueError(f"proposal blocked by fiscal language gate: {lang.blocked_phrases}")

    return {
        "agency_name": agency_name,
        "service_id": service.get("service_id"),
        "pricing": pricing,
        "deliverables": deliverables,
        "disclaimer": LEGAL_DISCLAIMER,
        "markdown": body_md,
        "object_classification": object_classification,
        "eligibility": eligibility,
        "fiscal_language_ok": True,
    }


def write_proposal(out_dir: Path, proposal: dict[str, Any], stem: str) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    md = out_dir / f"proposal-{stem}.md"
    md.write_text(proposal["markdown"], encoding="utf-8")
    paths["markdown"] = str(md)
    js = out_dir / f"proposal-{stem}.json"
    payload = {k: v for k, v in proposal.items() if k != "markdown"}
    payload["markdown_path"] = str(md)
    js.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    paths["json"] = str(js)
    # simple price sheet csv
    csv_path = out_dir / f"proposal-{stem}-pricing.csv"
    p = proposal["pricing"]
    csv_path.write_text(
        "field,value\n"
        + "\n".join(f"{k},{v}" for k, v in p.items())
        + "\n",
        encoding="utf-8",
    )
    paths["pricing_csv"] = str(csv_path)
    return paths
