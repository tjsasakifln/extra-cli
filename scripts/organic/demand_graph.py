"""Demand graph: persona → problem → question → intent → Confenge service.

Not a keyword list. Semantic needs map to one opportunity node even when
queries vary textually.
"""

from __future__ import annotations

from typing import Any

# Canonical demand nodes grounded in CONFENGE service inventory
DEMAND_NODES: list[dict[str, Any]] = [
    {
        "id": "need-reequilibrio-pleito",
        "persona": "diretor-construtora",
        "problem": "Contrato de obra pública virou prejuízo ou a equação original se rompeu",
        "question": "Quando cabe reequilíbrio e como estruturar um pleito defensável?",
        "intent": "bofu",
        "jtbd": "Proteger margem e decidir se vale montar pleito de reequilíbrio agora",
        "cluster": "reequilibrio",
        "service_slug": "reequilibrio-obras-publicas",
        "service_path": "/reequilibrio-obras-publicas/",
        "related_queries": [
            "reequilíbrio econômico financeiro obra pública",
            "pedido de reequilíbrio contrato público",
            "reajuste ou reequilíbrio obra pública",
        ],
        "cta": "Analisar viabilidade de reequilíbrio",
        "funnel": "bofu",
        "existing_url": "/reequilibrio-obras-publicas/",
    },
    {
        "id": "need-aditivo-limite",
        "persona": "engenheiro-contratos",
        "problem": "Acréscimos/supressões se aproximam dos limites legais",
        "question": "Como contar o limite de 25%/50% e o que documentar no aditivo?",
        "intent": "mofu",
        "jtbd": "Calcular saldo de aditivo e evitar pedido sem base",
        "cluster": "aditivos",
        "service_slug": "aditivos-obras-publicas",
        "service_path": "/aditivos-obras-publicas/",
        "related_queries": [
            "aditivos obra pública",
            "limite aditivo 25 50 obra pública",
            "acréscimo e supressão contrato público",
        ],
        "cta": "Revisar estratégia de aditivo",
        "funnel": "mofu",
        "tool_path": "/ferramentas/limite-acrescimos-supressoes/",
        "existing_url": "/aditivos-obras-publicas/",
    },
    {
        "id": "need-medicao-glosa",
        "persona": "engenheiro-obra",
        "problem": "Medição glosada, critério inventado ou parcela retida",
        "question": "Como contestar glosa e proteger o fluxo de caixa?",
        "intent": "bofu",
        "jtbd": "Recuperar medição e documentar nexo com o contrato",
        "cluster": "medicoes-pagamentos",
        "service_slug": "medicoes-glosas-obras-publicas",
        "service_path": "/medicoes-glosas-obras-publicas/",
        "related_queries": [
            "glosa de medição obra pública",
            "medição de obra pública rejeitada",
            "parcela incontroversa medição",
        ],
        "cta": "Revisar medição e glosa",
        "funnel": "bofu",
        "existing_url": "/medicoes-glosas-obras-publicas/",
    },
    {
        "id": "need-sinapi-desonerado",
        "persona": "orcamentista",
        "problem": "Dúvida sobre base SINAPI desonerada vs não desonerada no edital",
        "question": "Qual base usar e como alinhar BDI e encargos?",
        "intent": "mofu",
        "jtbd": "Evitar erro de base que destrói margem na proposta",
        "cluster": "orcamento-bdi",
        "service_slug": "auditoria-orcamento-licitacao",
        "service_path": "/auditoria-orcamento-licitacao/",
        "related_queries": [
            "desonerado e não desonerado",
            "sinapi desonerado ou não desonerado",
            "desonerado ou não desonerado",
        ],
        "cta": "Auditar orçamento e BDI do edital",
        "funnel": "mofu",
        "existing_url": "/conteudos/sinapi-desonerado-nao-desonerado/",
    },
    {
        "id": "need-atraso-prorrogacao",
        "persona": "gerente-contratos",
        "problem": "Atraso imputável à Administração ou risco de notificação",
        "question": "Como documentar prorrogação e responder notificação?",
        "intent": "mofu",
        "jtbd": "Proteger prazo e evitar sanção indevida",
        "cluster": "atrasos-prorrogacao",
        "service_slug": "atrasos-prorrogacao-obras-publicas",
        "service_path": "/atrasos-prorrogacao-obras-publicas/",
        "related_queries": [
            "prorrogação prazo obra pública",
            "notificação atraso obra pública",
            "atraso imputável administração",
        ],
        "cta": "Montar defesa de prazo",
        "funnel": "mofu",
        "tool_path": "/ferramentas/matriz-atraso-obra/",
        "existing_url": "/atrasos-prorrogacao-obras-publicas/",
    },
    {
        "id": "need-edital-orcamento",
        "persona": "licitacoes",
        "problem": "Edital com orçamento inconsistente ou referência duvidosa",
        "question": "Participar, impugnar ou auditar a planilha antes da proposta?",
        "intent": "bofu",
        "jtbd": "Decidir se a licitação é economicamente segura",
        "cluster": "edital-proposta",
        "service_slug": "auditoria-orcamento-licitacao",
        "service_path": "/auditoria-orcamento-licitacao/",
        "related_queries": [
            "orçamento incompleto edital obra pública",
            "auditoria orçamento licitação",
            "sinapi ou sicro obra pública",
        ],
        "cta": "Auditar edital e orçamento",
        "funnel": "bofu",
        "existing_url": "/auditoria-orcamento-licitacao/",
    },
    {
        "id": "need-benchmark-mercado",
        "persona": "diretor-construtora",
        "problem": "Não sabe se valor/duração/alterações do contrato são 'normais'",
        "question": "Isso é normal no mercado público de obras?",
        "intent": "tofu",
        "jtbd": "Comparar o próprio caso com evidência agregada do mercado",
        "cluster": "inteligencia-mercado",
        "service_slug": "metodologia-inteligencia",
        "service_path": "/metodologia-inteligencia/",
        "related_queries": [
            "benchmark contratos obras públicas",
            "mediana valor contrato obra pública",
        ],
        "cta": "Entender como a inteligência de mercado apoia decisões",
        "funnel": "tofu",
        "requires_data_moat": True,
    },
    {
        "id": "need-gestao-contratual",
        "persona": "proprietario-construtora",
        "problem": "Contratos públicos sem rotina de gestão geram prejuízo silencioso",
        "question": "Quando vale consultoria de acompanhamento contratual vs equipe própria?",
        "intent": "bofu",
        "jtbd": "Decidir se contrata apoio externo para gestão B2G",
        "cluster": "gestao-contratual",
        "service_slug": "acompanhamento-contratos-obras",
        "service_path": "/acompanhamento-contratos-obras/",
        "related_queries": [
            "consultoria B2G engenharia construtora",
            "gestão de contratos de obras públicas",
        ],
        "cta": "Diagnosticar gestão contratual B2G",
        "funnel": "bofu",
        "existing_url": "/acompanhamento-contratos-obras/",
    },
]


def demand_map() -> dict[str, Any]:
    """Export demand graph as versioned artifact structure."""
    by_cluster: dict[str, list[str]] = {}
    by_intent: dict[str, list[str]] = {}
    for n in DEMAND_NODES:
        by_cluster.setdefault(n["cluster"], []).append(n["id"])
        by_intent.setdefault(n["intent"], []).append(n["id"])
    return {
        "schema_version": "organic-demand-v1",
        "model": "persona → problem → question → intent → service",
        "nodes": DEMAND_NODES,
        "by_cluster": by_cluster,
        "by_intent": by_intent,
        "principle": (
            "Agrupar variantes textuais da mesma necessidade em um único nó. "
            "Não criar uma página por keyword."
        ),
    }


def match_queries_to_nodes(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach GSC query rows to demand nodes by substring overlap."""
    matches: list[dict[str, Any]] = []
    for qrow in queries:
        q = str(qrow.get("query") or qrow.get("Top consultas") or "").lower()
        if not q:
            continue
        best = None
        best_hits = 0
        for node in DEMAND_NODES:
            hits = 0
            for rq in node.get("related_queries") or []:
                tokens = [t for t in rq.lower().split() if len(t) > 3]
                if sum(1 for t in tokens if t in q) >= max(2, len(tokens) // 2):
                    hits += 1
                if rq.lower() in q or q in rq.lower():
                    hits += 2
            # cluster token hits
            for tok in node["cluster"].replace("-", " ").split():
                if len(tok) > 3 and tok in q:
                    hits += 1
            if hits > best_hits:
                best_hits = hits
                best = node
        if best and best_hits > 0:
            matches.append(
                {
                    "query": q,
                    "node_id": best["id"],
                    "hits": best_hits,
                    "impressions": float(qrow.get("impressions") or qrow.get("Impressões") or 0),
                    "clicks": float(qrow.get("clicks") or qrow.get("Cliques") or 0),
                    "position": float(qrow.get("position") or qrow.get("Posição") or 0),
                    "ctr": float(qrow.get("ctr") or 0),
                }
            )
    return matches
