"""Commercial kit materials for public-agency vertical — no invented credentials."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.public_agency.catalog import load_catalog, services_list
from scripts.public_agency.fiscal_support import FISCAL_SUPPORT_PREFERRED


def _status_unknown(doc_id: str) -> dict[str, str]:
    return {
        "document_id": doc_id,
        "status": "revisão necessária",
        "notes": "Estado não comprovado no repositório; operador deve atualizar.",
    }


def build_qualification_kit_states() -> list[dict[str, str]]:
    docs = [
        "cartao_cnpj",
        "contrato_social",
        "certidoes",
        "registro_profissional",
        "registro_empresa_conselho",
        "responsaveis_tecnicos",
        "acervo",
        "atestados",
        "curriculos",
        "portfolio",
        "declaracoes",
        "comprovantes_experiencia",
        "apolices",
        "dados_bancarios",
        "documentos_assinatura",
    ]
    return [_status_unknown(d) for d in docs]


def generate_commercial_kit(out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    catalog = load_catalog()
    services = services_list()

    # Institutional presentation
    p = out_dir / "apresentacao-institucional-orgaos.md"
    p.write_text(
        f"""# CONFENGE — apresentação institucional para órgãos públicos

## Quem somos

A CONFENGE presta **serviços técnicos especializados** a órgãos e entidades públicas
em planejamento de contratações de obras e serviços de engenharia, orçamentação,
revisão pré-publicação, {FISCAL_SUPPORT_PREFERRED} e diagnóstico de contratos críticos.

## O que fazemos

- Apoio técnico à fase preparatória (ETP, TR, quantidades, riscos, cronograma, orçamento)
- Orçamento e planejamento de obras
- Revisão técnica independente antes da publicação
- {FISCAL_SUPPORT_PREFERRED} (art. 117 — sem substituir o fiscal/gestor)
- Diagnóstico de obra/contrato crítico
- Capacitação aplicada (oferta secundária)

## O que não fazemos

- Não emitimos parecer jurídico vinculante
- Não substituímos fiscal, gestor ou autoridade pública
- Não prometemos dispensa de licitação ou contratação direta
- Não inventamos atestados, acervos ou qualificações

## Princípio comercial

Vendemos **capacidade técnica, redução de risco e qualidade documental** —
não "dispensa de licitação".
""",
        encoding="utf-8",
    )
    paths["apresentacao"] = str(p)

    # Capability statement
    p = out_dir / "capability-statement.md"
    p.write_text(
        """# Capability statement — CONFENGE (órgãos públicos)

Este documento lista capacidades declaradas. **Credenciais específicas**
(atestados, ART, registros) só devem ser afirmadas quando constarem do kit
de habilitação com status `disponível`/`válido` comprovado pelo operador.

| Capacidade | Status no repositório |
|------------|----------------------|
| Planejamento técnico da contratação | Oferta catalogada |
| Orçamento e planejamento de obras | Oferta catalogada |
| Revisão pré-publicação | Oferta catalogada |
| Apoio técnico à fiscalização | Oferta catalogada |
| Diagnóstico de contrato/obra crítica | Oferta catalogada |
| Capacitação aplicada | Oferta secundária |

Qualquer alegação de atestado/acervo/registro sem evidência no kit é **proibida**.
""",
        encoding="utf-8",
    )
    paths["capability"] = str(p)

    # Catalog export
    p = out_dir / "catalogo-servicos.md"
    lines = ["# Catálogo de serviços — órgãos públicos\n"]
    for s in services:
        lines.append(f"## {s.get('service_id')} — {s.get('nome')}\n")
        lines.append(f"**Problema:** {s.get('problema_resolvido')}\n")
        lines.append(f"**Classificação jurídica sugerida:** {s.get('classificacao_juridica_sugerida')}\n")
        lines.append("**Entregáveis:**\n")
        for e in s.get("entregaveis") or []:
            lines.append(f"- {e}")
        lines.append("\n**Exclusões:**\n")
        for e in s.get("exclusoes") or []:
            lines.append(f"- {e}")
        lines.append("\n")
    p.write_text("\n".join(lines), encoding="utf-8")
    paths["catalogo"] = str(p)

    # One-pagers
    for s in services:
        sid = s.get("service_id")
        op = out_dir / f"one-page-{sid}.md"
        op.write_text(
            f"""# {s.get('nome')}

**ID:** `{sid}`

## Problema
{s.get('problema_resolvido')}

## Escopo
{s.get('escopo')}

## Principais entregáveis
{chr(10).join('- ' + str(e) for e in (s.get('entregaveis') or [])[:8])}

## Exclusões
{chr(10).join('- ' + str(e) for e in (s.get('exclusoes') or [])[:6])}

## Faixa de preço (orientação por escopo)
{json.dumps(s.get('faixa_preco_por_escopo'), ensure_ascii=False, indent=2)}

Preço final por esforço — teto legal não é âncora de preço.
""",
            encoding="utf-8",
        )
        paths[f"one_page_{sid}"] = str(op)

    # Art 117 declaration
    p = out_dir / "declaracao-apoio-fiscalizacao-art117.md"
    p.write_text(
        f"""# Declaração — {FISCAL_SUPPORT_PREFERRED}

A CONFENGE, quando contratada para apoio à fiscalização e gestão contratual:

## Pode
- Assistir e subsidiar fiscais e gestores
- Realizar inspeções técnicas e conferir medições
- Produzir relatórios, evidências e análises de cronograma
- Apontar não conformidades e avaliar tecnicamente pleitos/aditivos
- Subsidiar recebimentos e produzir notas técnicas

## Não pode / não se apresenta como
- Substituto do fiscal ou gestor público
- Autoridade para sanções, pagamentos, homologação, adjudicação
- Emissor de ordens administrativas em nome do órgão
- Responsável por recebimento definitivo reservado a agente/comissão
- Signatário de atos como autoridade pública

Base: Lei nº 14.133/2021, art. 117.
""",
        encoding="utf-8",
    )
    paths["art117"] = str(p)

    # Checklists
    p = out_dir / "checklist-contratacao-direta.md"
    p.write_text(
        """# Checklist de contratação direta (para o órgão — não é parecer)

- [ ] Natureza do objeto classificada
- [ ] Valor unitário e somatório anual da mesma natureza avaliados
- [ ] Ausência de fracionamento
- [ ] Instrução do art. 72
- [ ] Estimativa de preços (art. 23)
- [ ] Motivação e publicidade aplicáveis
- [ ] Análise jurídica do órgão
- [ ] Controles internos

A CONFENGE não decide o fundamento legal.
""",
        encoding="utf-8",
    )
    paths["checklist_cd"] = str(p)

    p = out_dir / "checklist-conflito-interesses.md"
    p.write_text(
        """# Checklist de conflito de interesses (operador)

- [ ] Órgão não está sob fiscalização/gestão/comissão do operador
- [ ] Sem uso de informação não pública
- [ ] Sem acesso privilegiado à oportunidade
- [ ] Contatos apenas institucionais públicos
- [ ] Clearance humano documentado (CONFLICT_CLEARED_BY_HUMAN_REVIEW)
- [ ] Sem envio de outreach antes da aprovação de Tiago
""",
        encoding="utf-8",
    )
    paths["checklist_coi"] = str(p)

    p = out_dir / "mensagens-abordagem.md"
    p.write_text(
        f"""# Mensagens de abordagem (minutas)

## Abertura institucional

Assunto: Apoio técnico em obras e contratações de engenharia — CONFENGE

Prezados(as),

A CONFENGE oferece {FISCAL_SUPPORT_PREFERRED}, planejamento técnico da contratação
e orçamentação para órgãos públicos. Não substituímos o fiscal público nem
prometemos contratação direta.

Caso haja interesse em conhecer nosso catálogo técnico, ficamos à disposição
para uma conversa institucional.

Atenciosamente,
CONFENGE

## Objeções

| Objeção | Resposta |
|---------|----------|
| "Isso é dispensa?" | Hipótese eventual do órgão; vendemos capacidade técnica. |
| "Vocês fiscalizam no nosso lugar?" | Não. Prestamos apoio técnico ao fiscal (art. 117). |
| "Precisamos de parecer jurídico" | Não emitimos; encaminhar à assessoria do órgão. |
""",
        encoding="utf-8",
    )
    paths["mensagens"] = str(p)

    p = out_dir / "roteiro-reuniao.md"
    p.write_text(
        """# Roteiro de reunião (órgão público)

1. Apresentação institucional e limites de atuação
2. Diagnóstico: fase preparatória, obras, fiscalização
3. Evidências públicas observadas (sem inferir o que não há)
4. Oferta aderente e entregáveis
5. Escopo, prazo, preço por esforço
6. Papéis: CONFENGE vs Administração
7. Documentos de habilitação
8. Próximos passos e aprovação interna do órgão
""",
        encoding="utf-8",
    )
    paths["roteiro"] = str(p)

    # Qualification kit states
    p = out_dir / "kit-habilitacao-status.json"
    kit = {
        "policy": "Não afirmar credencial sem status disponível/válido comprovado.",
        "documents": build_qualification_kit_states(),
    }
    p.write_text(json.dumps(kit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["habilitacao"] = str(p)

    # Modelo proposta pointer
    p = out_dir / "modelo-proposta.md"
    p.write_text(
        "Ver gerador `scripts.public_agency.proposal.generate_proposal` e "
        "saídas em `proposals/` de cada run.\n",
        encoding="utf-8",
    )
    paths["modelo_proposta"] = str(p)

    # Catalog raw yaml hash reference
    p = out_dir / "catalog-meta.json"
    p.write_text(
        json.dumps(
            {
                "catalog_id": catalog.get("catalog_id"),
                "version": catalog.get("version"),
                "service_count": len(services),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    paths["catalog_meta"] = str(p)

    return paths
