"""Representative offline fixtures for consulting workbench flows.

These are synthetic but realistic structures — never presented as live evidence.
"""

from __future__ import annotations

from typing import Any


def extra_opportunities(*, max_shortlist: int = 15) -> list[dict[str, Any]]:
    rows = [
        {
            "id": "opp-001",
            "orgao": "Prefeitura Municipal de Joinville",
            "objeto": "Reforma de escola municipal — engenharia civil",
            "uf": "SC",
            "valor_estimado": 1850000.0,
            "prazo_dias": 18,
            "aderencia_perfil": 0.86,
            "risco": "médio",
            "modalidade": "pregão eletrônico",
            "evidencia": "Objeto alinhado a obras prediais; CNAE e histórico compatíveis.",
        },
        {
            "id": "opp-002",
            "orgao": "DER-SC",
            "objeto": "Recuperação de pavimento em rodovia estadual",
            "uf": "SC",
            "valor_estimado": 4200000.0,
            "prazo_dias": 12,
            "aderencia_perfil": 0.72,
            "risco": "alto",
            "modalidade": "concorrência",
            "evidencia": "Exige atestados de rodovia; verificar capacidade técnica.",
        },
        {
            "id": "opp-003",
            "orgao": "Câmara Municipal de Blumenau",
            "objeto": "Adequação de acessibilidade em edifício público",
            "uf": "SC",
            "valor_estimado": 640000.0,
            "prazo_dias": 25,
            "aderencia_perfil": 0.91,
            "risco": "baixo",
            "modalidade": "pregão eletrônico",
            "evidencia": "Escopo predial com projetos complementares.",
        },
        {
            "id": "opp-004",
            "orgao": "Universidade do Estado de SC",
            "objeto": "Manutenção predial multi-campi",
            "uf": "SC",
            "valor_estimado": 980000.0,
            "prazo_dias": 9,
            "aderencia_perfil": 0.64,
            "risco": "médio",
            "modalidade": "pregão eletrônico",
            "evidencia": "Prazo curto; revisar certidões e equipe.",
        },
        {
            "id": "opp-005",
            "orgao": "Hospital Regional de São José",
            "objeto": "Obra de ampliação de ala ambulatorial",
            "uf": "SC",
            "valor_estimado": 7600000.0,
            "prazo_dias": 30,
            "aderencia_perfil": 0.55,
            "risco": "alto",
            "modalidade": "concorrência",
            "evidencia": "Hospitalar exige ART específica; aderência parcial.",
        },
    ]
    return rows[: max(1, min(max_shortlist, len(rows)))]


def confenge_suppliers(*, uf: str = "SC", max_companies: int = 10) -> list[dict[str, Any]]:
    base = [
        {
            "cnpj": "12.345.678/0001-90",
            "razao_social": "Alpha Suprimentos Técnicos Ltda",
            "uf": uf,
            "municipio": "Joinville",
            "score": 82,
            "contratos_36m": 14,
            "valor_contratos": 12500000.0,
            "cadastro_oficial": "RESOLVED",
            "sinais": "fornecimento recorrente; mesmo órgão 3x",
            "limitacoes": "Score é prioridade de revisão, não propensão de compra.",
        },
        {
            "cnpj": "98.765.432/0001-10",
            "razao_social": "Beta Engenharia e Materiais S.A.",
            "uf": uf,
            "municipio": "Blumenau",
            "score": 76,
            "contratos_36m": 9,
            "valor_contratos": 8300000.0,
            "cadastro_oficial": "RESOLVED",
            "sinais": "alta concentração em obras",
            "limitacoes": "Cobertura Top N; não generalizar para população integral.",
        },
        {
            "cnpj": "11.222.333/0001-44",
            "razao_social": "Gama Serviços Industriais ME",
            "uf": uf,
            "municipio": "Itajaí",
            "score": 71,
            "contratos_36m": 6,
            "valor_contratos": 2100000.0,
            "cadastro_oficial": "RESOLVED",
            "sinais": "crescimento recente de volume",
            "limitacoes": "Dados de fixture; validar no cadastro oficial antes de abordagem.",
        },
        {
            "cnpj": "55.666.777/0001-88",
            "razao_social": "Delta Componentes EIRELI",
            "uf": uf,
            "municipio": "Chapecó",
            "score": 68,
            "contratos_36m": 5,
            "valor_contratos": 1750000.0,
            "cadastro_oficial": "PENDING",
            "sinais": "cadastro oficial pendente",
            "limitacoes": "Não contatar com base apenas em PENDING.",
        },
        {
            "cnpj": "22.333.444/0001-55",
            "razao_social": "Épsilon Construções Ltda",
            "uf": uf,
            "municipio": "Criciúma",
            "score": 64,
            "contratos_36m": 4,
            "valor_contratos": 960000.0,
            "cadastro_oficial": "RESOLVED",
            "sinais": "contratos menores frequentes",
            "limitacoes": "Fixture representativa.",
        },
    ]
    return base[: max(1, min(max_companies, len(base)))]


def confenge_agencies(*, uf: str = "SC", max_leads: int = 10) -> list[dict[str, Any]]:
    base = [
        {
            "orgao": "Prefeitura de Joinville",
            "uf": uf,
            "tipo": "REACTIVE_OPPORTUNITY",
            "classificacao_juridica_preliminar": "possível dispensa/adesão a ata — PRELIMINAR",
            "risco_fracionamento": "médio",
            "conflito_interesse": "não identificado na fixture",
            "objeto_recente": "projetos de engenharia consultiva",
            "limitacoes": "Não constitui garantia de contratação direta.",
        },
        {
            "orgao": "Secretaria de Estado da Infraestrutura",
            "uf": uf,
            "tipo": "PROACTIVE_INSTITUTIONAL_PROSPECT",
            "classificacao_juridica_preliminar": "licitação típica esperada — PRELIMINAR",
            "risco_fracionamento": "baixo",
            "conflito_interesse": "verificar vínculos societários",
            "objeto_recente": "estudos e projetos rodoviários",
            "limitacoes": "Classificação revisável; não automatizar outreach.",
        },
        {
            "orgao": "Câmara Municipal de Florianópolis",
            "uf": uf,
            "tipo": "REACTIVE_OPPORTUNITY",
            "classificacao_juridica_preliminar": "pregão para serviços técnicos — PRELIMINAR",
            "risco_fracionamento": "alto",
            "conflito_interesse": "não identificado na fixture",
            "objeto_recente": "laudos e vistorias",
            "limitacoes": "Risco de fracionamento exige checagem humana.",
        },
        {
            "orgao": "Universidade Federal de SC (órgão de apoio)",
            "uf": uf,
            "tipo": "PROACTIVE_INSTITUTIONAL_PROSPECT",
            "classificacao_juridica_preliminar": "regime próprio / licitação — PRELIMINAR",
            "risco_fracionamento": "médio",
            "conflito_interesse": "checar parentes em comissão",
            "objeto_recente": "manutenção e projetos prediais",
            "limitacoes": "Fixture; validar competência do ente.",
        },
    ]
    return base[: max(1, min(max_leads, len(base)))]


def process_documents(*, query: str = "demo-processo-001") -> dict[str, Any]:
    docs = [
        {
            "categoria": "edital_anexos",
            "nome": "edital.pdf",
            "presente": True,
            "paginas": 42,
            "sha256_demo": "a" * 64,
        },
        {
            "categoria": "edital_anexos",
            "nome": "anexo-i-projeto.pdf",
            "presente": True,
            "paginas": 18,
            "sha256_demo": "b" * 64,
        },
        {
            "categoria": "sessao_julgamento_homologacao",
            "nome": "ata-sessao.pdf",
            "presente": True,
            "paginas": 5,
            "sha256_demo": "c" * 64,
        },
        {
            "categoria": "proposta_vencedora",
            "nome": "proposta-vencedora.pdf",
            "presente": False,
            "paginas": 0,
            "sha256_demo": None,
        },
        {
            "categoria": "habilitacao",
            "nome": "habilitacao-juridica.pdf",
            "presente": True,
            "paginas": 7,
            "sha256_demo": "d" * 64,
        },
    ]
    coverage = {
        "edital_anexos": {"found": 2, "expected_min": 1, "status": "ok"},
        "sessao_julgamento_homologacao": {"found": 1, "expected_min": 1, "status": "ok"},
        "proposta_vencedora": {"found": 0, "expected_min": 1, "status": "missing"},
        "habilitacao": {"found": 1, "expected_min": 1, "status": "ok"},
    }
    return {
        "query": query,
        "processo_id": "demo-processo-001",
        "documents": docs,
        "coverage": coverage,
        "limitations": [
            "Métricas por categoria são independentes.",
            "Documento ausente não é fabricado.",
            "Fixture de demonstração — não é acervo live.",
        ],
    }
