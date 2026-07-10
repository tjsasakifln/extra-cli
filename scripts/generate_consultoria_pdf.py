#!/usr/bin/env python3
"""
Gerador de PDF de Proposta de Consultoria Estratégica B2G.

Gera PDF formal com opções de escopo de consultoria, valores de referência
e condições comerciais. Foco nos 5 eixos de serviço:
  - Diagnóstico B2G
  - Monitoramento Mensal
  - Análise de Editais
  - Elaboração de Propostas
  - Acompanhamento de Contratos

Design: Big Four / Management Consulting aesthetic (idêntico ao intel-report.py).
  Paleta: charcoal navy + warm bronze. Tipografia: Times-Roman serif.
  Tabelas: three-rule sem cor, sem zebra.

Usage:
    python scripts/generate-consultoria-pdf.py --input data.json --output proposta.pdf
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Ensure scripts/ is on sys.path for lib imports
_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.pdfgen import canvas as pdfgen_canvas
    from reportlab.platypus import (
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
except ImportError:
    print("ERROR: reportlab not installed. Run: pip install reportlab")
    sys.exit(1)

# ============================================================
# DESIGN TOKENS, Big Four Aesthetic (matches intel-report.py)
# ============================================================

INK = colors.HexColor("#1B2A3D")
ACCENT = colors.HexColor("#8B7355")
SIGNAL_RED = colors.HexColor("#B5342A")
SIGNAL_GREEN = colors.HexColor("#1B7A3D")
SIGNAL_AMBER = colors.HexColor("#B8860B")

TEXT_COLOR = colors.HexColor("#2D3748")
TEXT_SECONDARY = colors.HexColor("#5A6577")
TEXT_MUTED = colors.HexColor("#8896A6")
RULE_COLOR = colors.HexColor("#C8CDD3")
RULE_HEAVY = colors.HexColor("#4A5568")
BG_SUBTLE = colors.HexColor("#F5F6F8")

FOOTER_LINE1 = "Tiago Sasaki — Consultor de Inteligência em Licitações"
FOOTER_LINE2 = "Proposta confidencial preparada exclusivamente para o destinatário"

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 2.2 * cm

ILLEGAL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# ============================================================
# ACCENT RESTORATION
# ============================================================

_ACCENT_MAP = [
    (r"\bconstrucao\b", "construção"),
    (r"\bConstrucao\b", "Construção"),
    (r"\blicitacao\b", "licitação"),
    (r"\bLicitacao\b", "Licitação"),
    (r"\blicitacoes\b", "licitações"),
    (r"\bLicitacoes\b", "Licitações"),
    (r"\bcontratacao\b", "contratação"),
    (r"\bContratacao\b", "Contratação"),
    (r"\bcontratacoes\b", "contratações"),
    (r"\bContratacoes\b", "Contratações"),
    (r"\bconcorrencia\b", "concorrência"),
    (r"\bConcorrencia\b", "Concorrência"),
    (r"\bparticipacao\b", "participação"),
    (r"\bParticipacao\b", "Participação"),
    (r"\binformacao\b", "informação"),
    (r"\binformacoes\b", "informações"),
    (r"\bavaliacao\b", "avaliação"),
    (r"\brecomendacao\b", "recomendação"),
    (r"\bpregao\b", "pregão"),
    (r"\bPregao\b", "Pregão"),
    (r"\borgao\b", "órgão"),
    (r"\bOrgao\b", "Órgão"),
    (r"\borgaos\b", "órgãos"),
    (r"\bOrgaos\b", "Órgãos"),
    (r"\binteligencia\b", "inteligência"),
    (r"\bInteligencia\b", "Inteligência"),
    (r"\bexperiencia\b", "experiência"),
    (r"\bExperiencia\b", "Experiência"),
    (r"\bexigencias\b", "exigências"),
    (r"\bExigencias\b", "Exigências"),
    (r"\bcompativel\b", "compatível"),
    (r"\bCompativel\b", "Compatível"),
    (r"\btecnica\b", "técnica"),
    (r"\bTecnica\b", "Técnica"),
    (r"\btecnico\b", "técnico"),
    (r"\bTecnico\b", "Técnico"),
    (r"\bjuridica\b", "jurídica"),
    (r"\bJuridica\b", "Jurídica"),
    (r"\beletronico\b", "eletrônico"),
    (r"\bEletronico\b", "Eletrônico"),
    (r"\beletronica\b", "eletrônica"),
    (r"\bEletronica\b", "Eletrônica"),
    (r"\bpreco\b", "preço"),
    (r"\bPreco\b", "Preço"),
    (r"\bprecos\b", "preços"),
    (r"\bPrecos\b", "Preços"),
    (r"\bservico\b", "serviço"),
    (r"\bservicos\b", "serviços"),
    (r"\bServicos\b", "Serviços"),
    (r"\bmunicipio\b", "município"),
    (r"\bMunicipio\b", "Município"),
    (r"\bmunicipios\b", "municípios"),
    (r"\bMunicipios\b", "Municípios"),
    (r"\bhabilitacao\b", "habilitação"),
    (r"\bHabilitacao\b", "Habilitação"),
    (r"\binabilitacao\b", "inabilitação"),
    (r"\binabilitacoes\b", "inabilitações"),
    (r"\bsancoes\b", "sanções"),
    (r"\bSancoes\b", "Sanções"),
    (r"\bgestao\b", "gestão"),
    (r"\bGestao\b", "Gestão"),
    (r"\bsaude\b", "saúde"),
    (r"\bSaude\b", "Saúde"),
    (r"\bqualificacao\b", "qualificação"),
    (r"\bQualificacao\b", "Qualificação"),
    (r"\bclassificacao\b", "classificação"),
    (r"\bClassificacao\b", "Classificação"),
    (r"\bmanutencao\b", "manutenção"),
    (r"\bManutencao\b", "Manutenção"),
    (r"\bseguranca\b", "segurança"),
    (r"\bSeguranca\b", "Segurança"),
    (r"\bnao\b", "não"),
    (r"\bNao\b", "Não"),
    (r"\bSao\b", "São"),
    (r"\bSAO\b", "São"),
    (r"\bJOSE\b", "José"),
    (r"\bindice\b", "índice"),
    (r"\bindices\b", "índices"),
    (r"\bcontabil\b", "contábil"),
    (r"\bcontabeis\b", "contábeis"),
    (r"\bregiao\b", "região"),
    (r"\bRegiao\b", "Região"),
    (r"\butil\b", "útil"),
    (r"\buteis\b", "úteis"),
    (r"\bultimos\b", "últimos"),
    (r"\bUltimos\b", "Últimos"),
    (r"\bacompanhamento\b", "acompanhamento"),
    (r"\bAcompanhamento\b", "Acompanhamento"),
    (r"\belaboracao\b", "elaboração"),
    (r"\bElaboracao\b", "Elaboração"),
    (r"\bexpansao\b", "expansão"),
    (r"\bExpansao\b", "Expansão"),
    (r"\bdiagnostico\b", "diagnóstico"),
    (r"\bDiagnostico\b", "Diagnóstico"),
    (r"\bmonitoramento\b", "monitoramento"),
    (r"\banalise\b", "análise"),
    (r"\bAnalise\b", "Análise"),
    (r"\bprecificacao\b", "precificação"),
    (r"\bPrecificacao\b", "Precificação"),
    (r"\bcondicoes\b", "condições"),
    (r"\bCondicoes\b", "Condições"),
    (r"\bproposta\b", "proposta"),
    (r"\bProposta\b", "Proposta"),
    (r"\bpropostas\b", "propostas"),
    (r"\bPropostas\b", "Propostas"),
    (r"\bconsultoria\b", "consultoria"),
    (r"\bConsultoria\b", "Consultoria"),
    (r"\bestrategia\b", "estratégia"),
    (r"\bEstrategia\b", "Estratégia"),
    (r"\bestrategico\b", "estratégico"),
    (r"\bEstrategico\b", "Estratégico"),
    (r"\bestrategica\b", "estratégica"),
    (r"\bEstrategica\b", "Estratégica"),
    (r"\beditais\b", "editais"),
    (r"\bEditais\b", "Editais"),
    (r"\bedital\b", "edital"),
    (r"\bEdital\b", "Edital"),
    (r"\bcontratos\b", "contratos"),
    (r"\bContratos\b", "Contratos"),
    (r"\bpraticos\b", "práticos"),
    (r"\bPraticos\b", "Práticos"),
    (r"\bproximo\b", "próximo"),
    (r"\bProximo\b", "Próximo"),
    (r"\bproximos\b", "próximos"),
    (r"\bProximos\b", "Próximos"),
    (r"\bmetricas\b", "métricas"),
    (r"\bMetricas\b", "Métricas"),
    (r"\bcenario\b", "cenário"),
    (r"\bCenario\b", "Cenário"),
    (r"\bcenarios\b", "cenários"),
    (r"\bpublica\b", "pública"),
    (r"\bPublica\b", "Pública"),
    (r"\bpublicas\b", "públicas"),
    (r"\bPublicas\b", "Públicas"),
    (r"\bpublico\b", "público"),
    (r"\bPublico\b", "Público"),
    (r"\bpublicos\b", "públicos"),
    (r"\bPublicos\b", "Públicos"),
    (r"\bcomercial\b", "comercial"),
    (r"\bComercial\b", "Comercial"),
    (r"\bcomerciais\b", "comerciais"),
    (r"\bComerciais\b", "Comerciais"),
    (r"\brelatorio\b", "relatório"),
    (r"\bRelatorio\b", "Relatório"),
    (r"\brelatorios\b", "relatórios"),
    (r"\bRelatorios\b", "Relatórios"),
    (r"\bgovernanca\b", "governança"),
    (r"\bGovernanca\b", "Governança"),
    (r"\bdossie\b", "dossiê"),
    (r"\bDossie\b", "Dossiê"),
    (r"\bvincendos\b", "vincendos"),
    (r"\bVincendos\b", "Vincendos"),
    (r"\bprioritario\b", "prioritário"),
    (r"\bPrioritario\b", "Prioritário"),
    (r"\bprioritarios\b", "prioritários"),
    (r"\bPrioritarios\b", "Prioritários"),
    (r"\bambito\b", "âmbito"),
    (r"\bAmbito\b", "Âmbito"),
    (r"\bperiodo\b", "período"),
    (r"\bPeriodo\b", "Período"),
    (r"\bnegocio\b", "negócio"),
    (r"\bNegocio\b", "Negócio"),
    (r"\bnegocios\b", "negócios"),
    (r"\bcredito\b", "crédito"),
    (r"\bpsicola\b", "psicológico"),
    (r"\bconformidade\b", "conformidade"),
    (r"\bConformidade\b", "Conformidade"),
]
_ACCENT_PATTERNS = [(re.compile(pat), repl) for pat, repl in _ACCENT_MAP]


def restore_accents(text: str) -> str:
    """Restore Portuguese accents that are lost in ASCII-only contexts."""
    if not text or not isinstance(text, str):
        return text or ""
    text = ILLEGAL_CHARS_RE.sub(" ", text)
    for pat, repl in _ACCENT_PATTERNS:
        text = pat.sub(repl, text)
    return text


# ============================================================
# FORMAT HELPERS
# ============================================================

def _fmt_brl(value: float | None) -> str:
    if value is None:
        return "Não informado"
    try:
        v = float(value)
    except (ValueError, TypeError):
        return "Não informado"
    if v == 0:
        return "R$ 0,00"
    return "R$ {:,.2f}".format(v).replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_brl_short(value: float | None) -> str:
    if value is None:
        return "Não informado"
    try:
        v = float(value)
    except (ValueError, TypeError):
        return "Não informado"
    if v >= 1_000_000:
        return "R$ {:,.1f}M".format(v / 1_000_000).replace(",", "X").replace(".", ",").replace("X", ".")
    if v >= 1_000:
        return "R$ {:,.0f}K".format(v / 1_000).replace(",", "X").replace(".", ",").replace("X", ".")
    return _fmt_brl(v)


def _fmt_date(date_str: str | None) -> str:
    if not date_str:
        return "Não informado"
    text = str(date_str).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10], fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return "Não informado"


def _s(text: str) -> str:
    """Short alias for restore_accents."""
    return restore_accents(str(text))


def _detect_gender(name: str) -> str:
    if not name:
        return "Sr."
    first = name.strip().split()[0].lower()
    female_names = {
        "angela", "ana", "maria", "mariana", "juliana", "fernanda", "amanda",
        "patricia", "luciana", "adriana", "cristiane", "rosane", "eliane",
        "simone", "viviane", "aline", "caroline", "michele", "vanessa",
        "larissa", "beatriz", "roberta", "denise", "raquel", "claudia",
        "silvia", "sandra", "carla", "paula", "lucia", "renata", "camila",
        "leticia", "gabriela", "daniela", "rafaela", "isabela", "priscila",
        "tatiana", "fabiana", "luana", "bruna", "natalia",
    }
    male_names = {
        "andre", "alexandre", "felipe", "henrique", "jose", "dante",
        "jorge", "duarte", "vicente", "jaime", "juliano", "rogerio",
    }
    if first in male_names:
        return "Sr."
    if first in female_names:
        return "Sra."
    if first.endswith("a") or first.endswith("e"):
        return "Sra."
    return "Sr."

# ============================================================
# EMBEDDED CONTENT, Proposta de Consultoria (from dossiê)
# NÃO contém menções a contratos específicos.
# Foco: escopo + valores + condições.
# ============================================================

SERVICES = [
    {
        "id": "diagnostico",
        "title": "Diagnóstico B2G de Mercado",
        "objective": (
            "Fornecer ao decisor um panorama estruturado do mercado de licitações "
            "compatível com o perfil da empresa, mapeando órgãos compradores, "
            "concorrentes ativos, preços praticados e oportunidades de curto prazo."
        ),
        "scope_items": [
            ("Região de análise", "Definida pelo cliente (municípios, região metropolitana ou estado)"),
            ("Órgãos-alvo", "Prefeituras, autarquias estaduais, fundações e empresas públicas com perfil de compra relevante"),
            ("Tipos de contratação", "Obras, serviços de engenharia ou fornecimentos do setor de atuação"),
            ("Faixa de valor", "Definida conforme o porte da empresa e seu histórico de contratações"),
            ("Período analisado", "3 anos de dados históricos"),
        ],
        "deliverables": [
            "Mapa de órgãos compradores, ranking com perfil detalhado de cada órgão (volume, frequência, modalidades, fornecedores habituais)",
            "Mapeamento de concorrentes, top 15 com contratos vencidos, ticket médio, deságio e órgãos de atuação",
            "Painel de preços praticados, mediana, P25, P75 e evolução temporal por tipo de contratação",
            "Oportunidades de curto prazo, contratos vincendos em 90–180 dias com probabilidade de relicitação",
            "Editais ativos analisados, triagem com score de prioridade e recomendação",
            "Recomendações estratégicas, 5 a 10 ações comerciais priorizadas com base nos achados",
        ],
    },
    {
        "id": "monitoramento",
        "title": "Monitoramento Mensal de Oportunidades e Concorrentes",
        "objective": (
            "Manter fluxo contínuo de inteligência comercial: editais do setor, "
            "movimentação de concorrentes, atualização de preços de referência e "
            "alertas de contratos vincendos. Substitui a busca manual em portais "
            "por inteligência estruturada e análise qualificada."
        ),
        "scope_items": [
            ("Frequência", "Relatórios semanais + 1 relatório mensal consolidado"),
            ("Cobertura geográfica", "UF sede + UFs limítrofes (expansível)"),
            ("Fontes monitoradas", "Publicações oficiais de contratações públicas conforme Lei 14.133/2021"),
            ("Análise de concorrência", "Atualização mensal do painel competitivo"),
        ],
        "deliverables": [
            "Relatórios semanais com editais classificados por aderência ao perfil",
            "Alertas de editais prioritários com prazo crítico (< 7 dias)",
            "Relatório mensal consolidado com métricas de mercado e tendências",
            "Painel de concorrência atualizado (novos entrantes, contratos recentes)",
            "Mapeamento de contratos vincendos com alerta de relicitação",
            "1 reunião mensal de alinhamento estratégico (online, 1h)",
        ],
    },
    {
        "id": "analise_editais",
        "title": "Análise Técnica de Editais e Orçamentos",
        "objective": (
            "Para cada edital prioritário, realizar análise detalhada de viabilidade, "
            "riscos documentais, exigências de habilitação e compatibilidade "
            "orçamentária, com recomendação fundamentada de GO/NO-GO."
        ),
        "scope_items": [
            ("Modalidades cobertas", "Pregão, Concorrência, Concurso, Diálogo Competitivo, Dispensa"),
            ("Profundidade", "Análise completa de edital + anexos + planilha orçamentária"),
            ("Prazo de entrega", "2 a 15 dias úteis conforme complexidade"),
        ],
        "deliverables": [
            "Checklist de 15–20 pontos críticos do edital (prazos, exigências, inconsistências)",
            "Análise de planilha orçamentária: composições, BDI, quantitativos",
            "Verificação de exigências de habilitação: atestados, índices contábeis, capital mínimo",
            "Comparação com preços de mercado para o mesmo tipo de contratação na região",
            "Identificação de cláusulas restritivas e red flags",
            "Parecer final com recomendação PARTICIPAR / NÃO PARTICIPAR fundamentado",
        ],
    },
    {
        "id": "elaboracao_propostas",
        "title": "Apoio Estratégico à Elaboração de Propostas",
        "objective": (
            "Aumentar a qualidade e competitividade de propostas específicas, "
            "com precificação baseada em dados de mercado, posicionamento "
            "competitivo e checklist de conformidade documental."
        ),
        "scope_items": [
            ("Escopo", "Preparação completa ou revisão de proposta existente"),
            ("Prazo", "Conforme cronograma do edital"),
        ],
        "deliverables": [
            "Análise de posicionamento competitivo: concorrentes prováveis e faixa de preço esperada",
            "Precificação baseada em dados reais de mercado (P25/P50/P75)",
            "Checklist de documentação de habilitação",
            "Revisão de conformidade da proposta comercial",
            "Estratégia de lance para pregões eletrônicos (quando aplicável)",
        ],
    },
    {
        "id": "acompanhamento",
        "title": "Acompanhamento de Contratos Públicos",
        "objective": (
            "Supervisionar contratos públicos em execução para maximizar "
            "rentabilidade, antecipar renovações e evitar perda de prazos "
            "contratuais, aditivos e reequilíbrios."
        ),
        "scope_items": [
            ("Periodicidade", "Mensal (relatórios) + alertas em tempo real para prazos críticos"),
            ("Escopo", "Monitoramento de publicações oficiais relacionadas aos contratos ativos"),
        ],
        "deliverables": [
            "Alertas de prazos: aditivos, renovações, reequilíbrios, vigência",
            "Monitoramento de publicações do contratante (portarias, notificações)",
            "Relatório mensal de status da carteira de contratos",
            "Identificação de oportunidades de aditivo ou reequilíbrio econômico-financeiro",
            "Preparação para relicitação com antecedência de 90 dias",
        ],
    },
]

PRICING_TABLES = {
    "diagnosticos": {
        "title": "Ofertas Pontuais, Diagnósticos B2G",
        "headers": ["Oferta", "Para Que Serve", "Prazo", "Valor"],
        "rows": [
            [
                "Diagnóstico Essencial",
                "Visão inicial de mercado em uma região e tipo de contratação. "
                "Mapa de órgãos, top 10 concorrentes, preços de referência, editais recentes.",
                "5–7 dias úteis",
                "R$ 6.000",
            ],
            [
                "Diagnóstico de Expansão\n(RECOMENDADO)",
                "Mapa completo de oportunidades. Perfil detalhado de órgãos, 15 concorrentes, "
                "painel de preços, contratos vincendos, editais ativos, recomendações estratégicas.",
                "10–15 dias úteis",
                "R$ 8.000",
            ],
            [
                "Dossiê Estratégico Completo",
                "Decisão estruturante: expansão regional, diversificação, entrada em novo estado. "
                "Análise completa de mercado + concorrência + precificação + risco + projeções.",
                "20–30 dias úteis",
                "R$ 17.000",
            ],
        ],
    },
    "monitoramento": {
        "title": "Ofertas Recorrentes, Monitoramento Mensal",
        "headers": ["Oferta", "Entregáveis Principais", "Periodicidade", "Valor"],
        "rows": [
            [
                "Monitoramento\nMensal Básico",
                "Relatórios semanais de oportunidades, alertas de editais prioritários, "
                "1 relatório mensal consolidado.",
                "Mensal (mín. 3 meses)",
                "R$ 3.250/mês",
            ],
            [
                "Monitoramento\nMensal Estratégico",
                "Tudo do Básico + análise de concorrência atualizada + mapeamento de "
                "contratos vincendos + painel de preços + 1 reunião mensal.",
                "Mensal (mín. 3 meses)",
                "R$ 6.250/mês",
            ],
        ],
    },
    "analise_editais": {
        "title": "Ofertas por Edital, Análise e Apoio a Propostas",
        "headers": ["Oferta", "Para Que Serve", "Prazo", "Valor"],
        "rows": [
            [
                "Triagem de Edital",
                "Primeira análise de um edital específico: checklist de 15–20 pontos críticos.",
                "2–3 dias úteis",
                "R$ 1.450",
            ],
            [
                "Análise Técnica de Edital",
                "Edital complexo ou de alto valor: análise detalhada de edital + planilha "
                "orçamentária + composições + BDI + comparação com preços de mercado.",
                "5–10 dias úteis",
                "R$ 3.750",
            ],
            [
                "Análise Crítica Completa",
                "Decisão GO/NO-GO com parecer: análise técnica + concorrência esperada + "
                "projeção de margem + recomendação final fundamentada.",
                "10–15 dias úteis",
                "R$ 5.500",
            ],
            [
                "Apoio à Proposta",
                "Preparação de proposta específica: posicionamento competitivo, precificação "
                "baseada em dados, checklist de documentação, revisão de conformidade.",
                "Conforme edital",
                "R$ 5.250",
            ],
        ],
    },
    "acompanhamento": {
        "title": "Oferta de Acompanhamento de Contratos",
        "headers": ["Oferta", "Para Que Serve", "Entregáveis", "Valor"],
        "rows": [
            [
                "Acompanhamento de Contratos",
                "Supervisionar contratos públicos em execução, antecipar renovações, "
                "evitar perda de prazos e identificar oportunidades de reequilíbrio.",
                "Alertas de prazos e aditivos, monitoramento de publicações oficiais, "
                "relatório mensal de status, preparação para relicitação.",
                "R$ 4.750/mês",
            ],
        ],
    },
}

EXPANSION_STAGES = [
    {
        "stage": 1,
        "title": "Diagnóstico Pontual",
        "objective": "Mapear o mercado relevante e identificar oportunidades imediatas.",
        "deliverables": "Mapa de órgãos, concorrentes, preços, oportunidades de curto prazo, recomendações.",
        "when": "Imediatamente, é o primeiro passo.",
        "price": "R$ 7.000",
    },
    {
        "stage": 2,
        "title": "Monitoramento Mensal",
        "objective": "Manter fluxo contínuo de inteligência: editais, concorrentes, preços, contratos vincendos.",
        "deliverables": "Relatórios semanais, alertas, painel de concorrência atualizado, reunião mensal.",
        "when": "Após o diagnóstico, quando a empresa decide institucionalizar a inteligência comercial.",
        "price": "R$ 5.250/mês",
    },
    {
        "stage": 3,
        "title": "Análise de Editais Prioritários",
        "objective": "Para cada edital de alto valor ou risco, obter análise técnica e estratégica antes de decidir.",
        "deliverables": "Relatório técnico, análise de planilha, BDI, riscos, recomendação GO/NO-GO.",
        "when": "Quando surgem editais acima de R$ 500 mil ou com complexidade técnica elevada.",
        "price": "R$ 4.200 por edital",
    },
    {
        "stage": 4,
        "title": "Apoio à Preparação de Propostas",
        "objective": "Aumentar a qualidade e competitividade de propostas específicas.",
        "deliverables": "Posicionamento competitivo, precificação com dados de mercado, checklist documental.",
        "when": "Em editais prioritários onde a empresa decide participar.",
        "price": "R$ 5.250 por proposta",
    },
    {
        "stage": 5,
        "title": "Acompanhamento de Contratos",
        "objective": "Maximizar rentabilidade dos contratos conquistados e antecipar renovações.",
        "deliverables": "Monitoramento de prazos e aditivos, alertas, relatórios de status.",
        "when": "Quando a empresa tem 3+ contratos públicos ativos.",
        "price": "R$ 4.750/mês",
    },
]

ROI_EXAMPLES = [
    {
        "situation": "Diagnóstico (R$ 8.000) identifica contrato não monitorado.",
        "value_at_stake": "Receita potencial de R$ 400 mil.",
        "ratio": "53:1",
    },
    {
        "situation": "Análise crítica (R$ 5.000) evita licitação de órgão com histórico de inadimplência.",
        "value_at_stake": "Prevenção de perda de R$ 100–300 mil em capital de giro.",
        "ratio": "20:1 a 60:1",
    },
    {
        "situation": "Monitoramento mensal (R$ 5.500/mês) encontra 3 editais/mês não detectados pela empresa.",
        "value_at_stake": "+ R$ 500 mil/ano em receita adicional.",
        "ratio": "7,5:1",
    },
    {
        "situation": "Acompanhamento de contratos (R$ 3.000/mês) identifica reequilíbrio de R$ 45 mil.",
        "value_at_stake": "+ R$ 45 mil em aditivo.",
        "ratio": "1,25:1 (só o aditivo paga o ano)",
    },
]

PRICE_REFERENCE = [
    ("Diagnóstico pontual essencial", "R$ 6.000"),
    ("Diagnóstico de expansão (recomendado)", "R$ 8.000"),
    ("Dossiê estratégico completo", "R$ 17.000"),
    ("Monitoramento mensal básico", "R$ 3.250/mês"),
    ("Monitoramento mensal estratégico", "R$ 6.250/mês"),
    ("Triagem de edital", "R$ 1.450"),
    ("Análise técnica de edital", "R$ 3.750"),
    ("Análise crítica completa de edital", "R$ 5.500"),
    ("Apoio estratégico à proposta", "R$ 5.250"),
    ("Acompanhamento de contratos", "R$ 4.750/mês"),
]

CREDENTIALS_INTRO = (
    "Tiago Sasaki é engenheiro civil formado pela Universidade de São Paulo, EESC/USP. "
    "Sua trajetória combina atuação em engenharia civil, infraestrutura, manutenção "
    "industrial e inteligência de dados aplicada ao setor público."
)

CREDENTIALS_BODY = [
    "Atua no setor público desde 2019, com experiência direta em fiscalização de "
    "contratos, convênios, obras públicas, documentação técnica, análise administrativa "
    "e processos relacionados à contratação pública.",

    "No setor privado, possui experiência anterior em engenharia civil e manutenção "
    "industrial, incluindo atuação na Gerdau e na Engecorps.",

    "É fundador e engenheiro de produto da GoVision.AI, desenvolvendo sistemas de IA "
    "aplicada, automação, RAG, fluxos documentais e produtos GovTech, entre eles o "
    "SmartLic, plataforma de inteligência sobre dados públicos de licitações e contratos.",
]

CREDENTIALS_WHY = (
    "O valor desta consultoria não está apenas em buscar editais, isso qualquer portal "
    "faz. Está em interpretar o mercado público com um olhar que integra três perspectivas: "
    "(1) engenharia e obras, entender contratos, orçamentos, aditivos, fiscalização, "
    "execução, BDI e composições de custo; (2) setor público por dentro, conhecer como "
    "órgãos públicos publicam, organizam e processam suas informações; e (3) dados e "
    "inteligência analítica, transformar registros dispersos em inteligência comercial "
    "útil. É a interseção dessas três competências que sustenta a qualidade da entrega."
)

GOVERNANCE_ITEMS = [
    "A consultoria não oferece influência institucional, intermediação indevida, "
    "favorecimento ou acesso privilegiado a agentes públicos ou processos decisórios.",

    "A análise se baseia exclusivamente em dados públicos, informações fornecidas "
    "pelo cliente e metodologia própria de inteligência comercial.",

    "Não há promessa de vitória em licitações ou de interferência em decisões públicas.",

    "O trabalho respeita integralmente a legislação, a impessoalidade, a moralidade "
    "administrativa e as regras de integridade aplicáveis.",

    "Quando houver potencial conflito de interesse, real ou aparente, o caso será "
    "recusado ou limitado exclusivamente a análise genérica de dados públicos.",

    "A atuação pública do responsável é credencial técnica, não canal de influência.",
]

ENTREGA_CONSULTORIA = [
    "Informação estruturada para decisão, dados consolidados, análises cruzadas e "
    "recomendações fundamentadas.",

    "Redução de assimetria informacional, a empresa passa a enxergar o mercado público "
    "com clareza comparável ou superior à de concorrentes maiores.",

    "Priorização objetiva de oportunidades, critérios baseados em dados substituem feeling.",

    "Identificação de padrões e riscos, comportamentos de órgãos e concorrentes que são "
    "invisíveis sem dados históricos.",

    "Economia de tempo, a equipe para de garimpar portais e passa a analisar oportunidades "
    "pré-qualificadas.",
]

NAO_PROMETE = [
    "Vitória garantida em licitações, nenhuma análise elimina a natureza competitiva do "
    "processo licitatório.",

    "Eliminação total de risco, a inteligência reduz, não elimina, a probabilidade de "
    "decisões ruins.",

    "Substituição de análise jurídica, contábil ou técnica, a consultoria complementa, "
    "não substitui, advogados, contadores e engenheiros orçamentistas.",

    "Acesso a informações não públicas, todos os dados vêm de fontes oficiais de "
    "transparência.",

    "Previsões infalíveis, projeções baseadas em dados históricos podem ser afetadas "
    "por mudanças regulatórias, crises fiscais e decisões políticas.",
]

# ============================================================
# STYLES
# ============================================================

def _build_styles():
    """Build ParagraphStyle map, Big Four aesthetic (serif, left-aligned)."""
    base = getSampleStyleSheet()
    styles = {}

    styles["cover_title"] = ParagraphStyle(
        "cover_title", parent=base["Title"],
        fontName="Times-Bold", fontSize=26, leading=32,
        textColor=INK, alignment=TA_LEFT, spaceAfter=5 * mm,
    )
    styles["cover_subtitle"] = ParagraphStyle(
        "cover_subtitle", parent=base["Normal"],
        fontName="Times-Roman", fontSize=14, leading=18,
        textColor=TEXT_SECONDARY, alignment=TA_LEFT, spaceAfter=4 * mm,
    )
    styles["h1"] = ParagraphStyle(
        "h1", parent=base["Heading1"],
        fontName="Times-Bold", fontSize=14, leading=18,
        textColor=INK, spaceBefore=8 * mm, spaceAfter=4 * mm,
        keepWithNext=1,
    )
    styles["h2"] = ParagraphStyle(
        "h2", parent=base["Heading2"],
        fontName="Times-Bold", fontSize=11, leading=14,
        textColor=INK, spaceBefore=5 * mm, spaceAfter=3 * mm,
        keepWithNext=1,
    )
    styles["h3"] = ParagraphStyle(
        "h3", parent=base["Heading3"],
        fontName="Times-Bold", fontSize=10, leading=13,
        textColor=TEXT_COLOR, spaceBefore=3 * mm, spaceAfter=2 * mm,
        keepWithNext=1,
    )
    styles["body"] = ParagraphStyle(
        "body", parent=base["Normal"],
        fontName="Times-Roman", fontSize=10, leading=14,
        textColor=TEXT_COLOR, alignment=TA_JUSTIFY, spaceAfter=2 * mm,
    )
    styles["body_bold"] = ParagraphStyle(
        "body_bold", parent=base["Normal"],
        fontName="Times-Bold", fontSize=10, leading=14,
        textColor=TEXT_COLOR, spaceAfter=2 * mm,
    )
    styles["body_small"] = ParagraphStyle(
        "body_small", parent=base["Normal"],
        fontName="Times-Roman", fontSize=9, leading=12,
        textColor=TEXT_SECONDARY, spaceAfter=1.5 * mm,
    )
    styles["quote"] = ParagraphStyle(
        "quote", parent=base["Normal"],
        fontName="Times-Italic", fontSize=10, leading=14,
        textColor=TEXT_SECONDARY, leftIndent=8 * mm, rightIndent=8 * mm,
        spaceAfter=3 * mm, spaceBefore=2 * mm,
    )
    styles["caption"] = ParagraphStyle(
        "caption", parent=base["Normal"],
        fontName="Helvetica", fontSize=7, leading=9,
        textColor=TEXT_MUTED,
    )
    styles["cell_header"] = ParagraphStyle(
        "cell_header", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=8, leading=10,
        textColor=INK,
    )
    styles["cell_white"] = ParagraphStyle(
        "cell_white", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=9, leading=12,
        textColor=colors.white,
    )
    styles["cell_white_sub"] = ParagraphStyle(
        "cell_white_sub", parent=base["Normal"],
        fontName="Helvetica", fontSize=8.5, leading=11,
        textColor=colors.white, alignment=TA_CENTER,
    )
    styles["cell"] = ParagraphStyle(
        "cell", parent=base["Normal"],
        fontName="Helvetica", fontSize=8, leading=10,
        textColor=TEXT_COLOR,
    )
    styles["cell_bold"] = ParagraphStyle(
        "cell_bold", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=8, leading=10,
        textColor=TEXT_COLOR,
    )
    styles["cell_right"] = ParagraphStyle(
        "cell_right", parent=base["Normal"],
        fontName="Helvetica", fontSize=8, leading=10,
        textColor=TEXT_COLOR, alignment=TA_RIGHT,
    )
    styles["cell_center"] = ParagraphStyle(
        "cell_center", parent=base["Normal"],
        fontName="Helvetica", fontSize=8, leading=10,
        textColor=TEXT_COLOR, alignment=TA_CENTER,
    )
    return styles

S = None  # global styles, set in generate_consultoria_pdf()


def P(text, style="body"):
    """Shortcut: Paragraph with accent restoration."""
    return Paragraph(restore_accents(str(text)), S[style])


# ============================================================
# LAYOUT HELPERS
# ============================================================

class _NumberedCanvas(pdfgen_canvas.Canvas):
    """Canvas that numbers pages correctly with SimpleDocTemplate."""
    def __init__(self, *args, **kwargs):
        pdfgen_canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            pdfgen_canvas.Canvas.showPage(self)
        pdfgen_canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        if self._pageNumber > 1:  # skip cover
            self.setFont("Helvetica", 7)
            self.setFillColor(TEXT_MUTED)
            self.drawRightString(PAGE_WIDTH - MARGIN, 10 * mm, f"Página {self._pageNumber - 1}")
            self.drawCentredString(PAGE_WIDTH / 2, 10 * mm, FOOTER_LINE1)
            self.setStrokeColor(RULE_COLOR)
            self.setLineWidth(0.4)
            self.line(MARGIN, PAGE_HEIGHT - 14 * mm, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 14 * mm)


def _draw_footer(canvas, doc):
    """Footer callback for pages 2+."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(TEXT_MUTED)
    canvas.drawRightString(PAGE_WIDTH - MARGIN, 10 * mm, f"Página {doc.page}")
    canvas.drawCentredString(PAGE_WIDTH / 2, 10 * mm, FOOTER_LINE1)
    canvas.setStrokeColor(RULE_COLOR)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN, PAGE_HEIGHT - 14 * mm, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 14 * mm)
    canvas.restoreState()


def _three_rule_table(headers, rows, col_widths):
    """Table with three-rule style: top heavy, hairline inner, bottom medium. No color, no zebra."""
    hdr = [P(h, "cell_header") for h in headers]
    data = [hdr] + [[P(c, "cell") if not isinstance(c, Paragraph) else c for c in row] for row in rows]
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, RULE_HEAVY),
        ("LINEBELOW", (0, -1), (-1, -1), 0.8, RULE_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(1, len(data)):
        style_cmds.append(("LINEBELOW", (0, i), (-1, i), 0.3, RULE_COLOR))
    t.setStyle(TableStyle(style_cmds))
    return t


def _key_value_table(rows, key_width=52 * mm):
    """Key-value table with three-rule style."""
    vw = PAGE_WIDTH - 2 * MARGIN - key_width
    data = [[P(k, "cell_bold"), P(v, "cell")] for k, v in rows]
    t = Table(data, colWidths=[key_width, vw])
    style_cmds = [
        ("LINEBELOW", (0, -1), (-1, -1), 0.8, RULE_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(1, len(data)):
        style_cmds.append(("LINEBELOW", (0, i), (-1, i), 0.3, RULE_COLOR))
    t.setStyle(TableStyle(style_cmds))
    return t


def _section_heading(text):
    """Section heading with accent rule above title."""
    from reportlab.platypus import HRFlowable
    return [
        HRFlowable(width=PAGE_WIDTH - 2 * MARGIN, thickness=0.5, color=ACCENT, spaceAfter=2 * mm, spaceBefore=4 * mm),
        Paragraph(restore_accents(text), S["h1"]),
    ]


def _bullet(text, style="body"):
    return Paragraph("•  " + restore_accents(text), S[style])


def _spacer(mm_val=3):
    return Spacer(1, mm_val * mm)



# ============================================================
# SECTION BUILDERS (v2 — executive + catalog structure)
# ============================================================

def _build_cover(empresa, today, validity_date):
    nome = restore_accents((empresa.get("nome_fantasia") or "").strip() or empresa.get("razao_social", "Empresa"))
    cnpj = empresa["cnpj"]
    today_fmt = today.strftime("%d/%m/%Y")
    validity_fmt = validity_date.strftime("%d/%m/%Y")
    cnae_principal = restore_accents(empresa.get("cnae_principal", ""))
    cidade = restore_accents(empresa.get("cidade_sede", ""))
    uf = empresa.get("uf_sede", "")

    from reportlab.platypus import HRFlowable

    elements = []
    elements.append(_spacer(35))
    elements.append(Paragraph("Proposta de Consultoria", S["cover_title"]))
    elements.append(Paragraph("Estratégica em Licitações Públicas", S["cover_title"]))
    elements.append(_spacer(6))
    elements.append(HRFlowable(width=40 * mm, thickness=0.8, color=ACCENT, spaceAfter=6 * mm, spaceBefore=3 * mm))
    elements.append(Paragraph("Preparada exclusivamente para", S["cover_subtitle"]))
    elements.append(Paragraph(f"<b>{nome}</b>", S["cover_subtitle"]))
    elements.append(_spacer(4))
    elements.append(Paragraph(f"CNPJ: {cnpj}  |  {cidade}/{uf}", S["cover_subtitle"]))
    elements.append(Paragraph(f"{cnae_principal}", S["cover_subtitle"]))
    elements.append(_spacer(12))

    cov_data = [
        ["Data", today_fmt],
        ["Validade", f"15 dias (até {validity_fmt})"],
        ["Consultor", "Tiago Sasaki"],
        ["Contato", "(48) 9 8834-4559"],
    ]
    ct = Table(
        [[P(a, "cell_bold"), P(b, "cell_center")] for a, b in cov_data],
        colWidths=[35 * mm, 55 * mm],
    )
    ct.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(ct)
    elements.append(PageBreak())
    return elements


def _build_carta_decisor(empresa, setor, honorific, decisor_full):
    nome = restore_accents((empresa.get("nome_fantasia") or "").strip() or empresa.get("razao_social", "Empresa"))
    cidade = restore_accents(empresa.get("cidade_sede", ""))
    uf = empresa.get("uf_sede", "")
    setor = restore_accents(setor)
    greeting = f"{honorific} {decisor_full}"

    carta_title = f"Carta à Decisora" if honorific == "Sra." else "Carta ao Decisor"
    elements = []
    elements.extend(_section_heading(carta_title))
    elements.append(Paragraph(restore_accents(greeting), S["body_bold"]))
    elements.append(_spacer(2))

    # Specific thesis based on sector + location
    if "engenharia" in setor.lower() or "obra" in setor.lower() or "constru" in setor.lower():
        thesis = (
            f"Para uma construtora de {cidade}/{uf}, a oportunidade está em mapear "
            f"órgãos públicos que contratam obras e serviços de engenharia de forma "
            f"recorrente na região, identificar contratos de manutenção predial e reforma "
            f"com vencimento próximo, conhecer os concorrentes habituais que disputam "
            f"essas licitações e selecionar editais compatíveis com a capacidade "
            f"operacional da empresa. Não se trata de garimpar portais, mas de transformar "
            f"dados públicos dispersos em um roteiro comercial objetivo."
        )
    else:
        thesis = (
            f"Para uma empresa de {cidade}/{uf} atuando no setor de {setor.lower()}, "
            f"a oportunidade está em mapear órgãos públicos que contratam de forma "
            f"recorrente na região, identificar contratos com vencimento próximo, "
            f"conhecer os concorrentes que disputam essas licitações e selecionar "
            f"editais compatíveis com o perfil técnico e financeiro da empresa."
        )

    elements.append(Paragraph(thesis, S["body"]))
    elements.append(_spacer(3))

    elements.append(Paragraph(
        f"Esta proposta apresenta o caminho mais direto para começar: um diagnóstico "
        f"pontual de mercado, com escopo definido, valor fixo, prazo claro e uma "
        f"reunião de apresentação dos resultados. As demais possibilidades de "
        f"consultoria estão no catálogo de serviços ao final do documento, como "
        f"referência para expansão futura.",
        S["body"]
    ))
    elements.append(PageBreak())
    return elements


def _build_credenciais_compact():
    """Compact credentials, moved early to sustain pricing authority."""
    elements = []
    elements.extend(_section_heading("Quem Conduz a Análise"))

    elements.append(Paragraph(
        "Tiago Sasaki, engenheiro civil formado pela EESC/USP. Atua no setor público "
        "desde 2019, com experiência direta em fiscalização de contratos, convênios, "
        "obras públicas, documentação técnica e processos de contratação pública. "
        "No setor privado, atuou em engenharia civil e manutenção industrial (Gerdau, "
        "Engecorps). É fundador da GoVision.AI, onde desenvolve sistemas de inteligência "
        "artificial aplicada a licitações e dados públicos, incluindo a plataforma SmartLic.",
        S["body"]
    ))
    elements.append(_spacer(2))

    elements.append(Paragraph("O que isso significa para o cliente:", S["body_bold"]))
    elements.append(Paragraph(
        "Esta consultoria não é apenas um serviço de captação de editais. Ela combina "
        "três competências que raramente estão juntas: (1) engenharia e obras, "
        "entendendo contratos, orçamentos, aditivos, BDI e fiscalização; (2) setor "
        "público por dentro, conhecendo como órgãos publicam, organizam e processam "
        "informações; e (3) inteligência de dados, transformando registros dispersos "
        "em decisão comercial. É essa interseção que sustenta a qualidade da entrega.",
        S["body"]
    ))
    elements.append(_spacer(3))

    # Compact governance
    elements.append(Paragraph("Governança e Ética", S["h2"]))
    elements.append(Paragraph(
        "Atuação baseada exclusivamente em dados públicos, metodologia própria e "
        "informações fornecidas pelo cliente. Sem intermediação, influência, promessa "
        "de vitória ou acesso privilegiado a processos decisórios. A atuação pública "
        "do responsável é credencial técnica, não canal de influência. Condições "
        "adicionais de governança podem ser formalizadas em contrato, se necessário.",
        S["body"]
    ))
    elements.append(PageBreak())
    return elements


def _build_diagnostico_entrada():
    """The ONE recommended service: Diagnóstico de Expansão. Concrete, specific, actionable."""
    elements = []
    elements.extend(_section_heading("Diagnóstico de Expansão B2G"))
    elements.append(Paragraph(
        "Recomendação de entrada: um diagnóstico pontual que mapeia o mercado "
        "relevante e entrega um roteiro comercial acionável em até 15 dias úteis.",
        S["body"]
    ))
    elements.append(_spacer(2))

    # Concrete examples of what the client receives
    elements.append(Paragraph("O Que Você Recebe", S["h2"]))
    entregaveis = [
        "Ranking dos órgãos públicos da região que mais contratam obras e serviços "
        "de engenharia no perfil da empresa, com valor médio, frequência e modalidade "
        "de cada um. Exemplo ilustrativo do tipo de análise entregue: 'Prefeitura X "
        "contratou 12 obras de reforma predial nos últimos 3 anos, ticket médio de "
        "R$ 480 mil, 80% via Tomada de Preços.'",

        "Mapeamento dos 15 concorrentes que mais venceram editais do mesmo tipo na "
        "região, com ticket médio, deságio habitual, órgãos onde atuam e contratos "
        "ativos. Exemplo ilustrativo do tipo de análise entregue: 'Concorrente A "
        "venceu 8 editais em 2025, ticket médio de R$ 620 mil, atua principalmente "
        "em Florianópolis e São José, atualmente com 4 contratos ativos somando "
        "R$ 2,8 milhões (provavelmente sem capacidade para novas disputas de maior porte).'",

        "Lista de contratos de reforma, manutenção predial e construção de edifícios "
        "públicos com vencimento em 90 a 180 dias nos órgãos da região, com "
        "probabilidade de relicitação. Exemplo ilustrativo do tipo de análise "
        "entregue: 'Contrato de manutenção predial do Órgão Y vence em 45 dias; "
        "histórico indica que o órgão relicita em 85% dos casos; ticket médio "
        "histórico de R$ 350 mil.'",

        "Painel de preços reais praticados para cada tipo de obra na região: mediana, "
        "P25, P75 e evolução temporal. Referência concreta para precificar propostas, "
        "não planilha de custos teórica.",

        "Editais abertos na semana de conclusão do diagnóstico, triados e ranqueados "
        "por aderência ao perfil da empresa, com recomendação individual de PARTICIPAR "
        "ou NÃO PARTICIPAR fundamentada.",
    ]
    for i, e in enumerate(entregaveis, 1):
        elements.append(Paragraph(f"<b>{i}.</b> {restore_accents(e)}", S["body"]))
    elements.append(_spacer(3))

    # Scope
    elements.append(Paragraph("Escopo e Condições", S["h2"]))
    elements.append(_key_value_table([
        ("Serviço", "Diagnóstico B2G de Expansão, Concorrência e Oportunidades"),
        ("Região", "Grande Florianópolis e municípios do entorno (ajustável na reunião de alinhamento)"),
        ("Tipos de contratação", "Obras de reforma predial, manutenção, construção de edifícios públicos (ajustável conforme perfil)"),
        ("Período analisado", "3 anos de dados históricos de contratações públicas"),
        ("Prazo de entrega", "10 a 15 dias úteis após alinhamento de escopo"),
        ("Formato", "PDF executivo (30 a 50 páginas) + planilhas de dados (Excel)"),
        ("Reuniões incluídas", "1 reunião de alinhamento inicial (45 min, online) + 1 reunião de apresentação dos resultados (1h30, online)"),
    ]))
    elements.append(_spacer(2))

    # Single clear price
    elements.append(Paragraph("Investimento", S["h2"]))
    elements.append(Paragraph(
        "<b>Investimento: R$ 8.000.</b> O valor é confirmado na reunião de "
        "alinhamento de escopo, sem surpresas.",
        S["body"]
    ))
    elements.append(Paragraph(
        "Parte do valor pode ser abatida na contratação de monitoramento mensal "
        "em até 60 dias após a entrega do diagnóstico (até 25% de abatimento).",
        S["body_small"]
    ))

    elements.append(_spacer(3))

    # ROI — sober, not pitch math
    elements.append(Paragraph("Raciocínio Econômico", S["h2"]))
    elements.append(Paragraph(
        "Em contratações públicas de obras e serviços de engenharia, o valor de um "
        "único contrato de R$ 400 mil supera em mais de 50 vezes o custo do "
        "diagnóstico. Na direção oposta, evitar uma licitação de órgão com histórico "
        "de inadimplência ou rescisões também gera economia real de tempo, equipe "
        "técnica e capital de giro. O diagnóstico não garante contrato, mas "
        "substitui a decisão por feeling por uma decisão baseada em evidências. "
        "Para uma construtora que já venceu licitações, isso significa escolher "
        "melhor onde competir, não competir mais.",
        S["body"]
    ))
    elements.append(PageBreak())
    return elements


def _build_condicoes_comerciais(today, validity_date):
    """Compact: price summary + combo discounts + CTA + next steps. All in one section."""
    today_fmt = today.strftime("%d/%m/%Y")
    validity_fmt = validity_date.strftime("%d/%m/%Y")

    elements = []
    elements.extend(_section_heading("Condições Comerciais e Próximos Passos"))

    # Price summary
    elements.append(Paragraph("Resumo da Oferta de Entrada", S["h2"]))
    elements.append(_key_value_table([
        ("Serviço recomendado", "Diagnóstico B2G de Expansão"),
        ("Valor", "R$ 8.000"),
        ("Prazo de entrega", "10 a 15 dias úteis"),
        ("Forma de pagamento", "Boleto, PIX ou Cartão de Crédito"),
        ("Validade desta proposta", validity_fmt),
        ("Data-base", today_fmt),
    ]))

    elements.append(_spacer(3))

    # Combo discounts for future expansion
    elements.append(Paragraph("Expansão Futura: Descontos para Contratação Combinada", S["h2"]))
    elements.append(Paragraph(
        "Se após o diagnóstico a empresa decidir expandir para outros serviços, "
        "os descontos abaixo se aplicam sobre o valor total do pacote contratado "
        "simultaneamente:",
        S["body"]
    ))
    elements.append(_spacer(1))
    combo_headers = ["Serviços", "Desconto", "Exemplo de Combinação", "Valor com Desconto"]
    combo_rows = [
        ["Diagnóstico + 1 serviço", "10%", "Diagnóstico + Monitoramento Mensal Estratégico",
         "R$ 8.000 + R$ 6.250/mês = R$ 14.250 → R$ 12.825"],
        ["Diagnóstico + 2 serviços", "15%", "Diagnóstico + Monitoramento + Acompanhamento",
         "R$ 8.000 + R$ 6.250 + R$ 4.750 = R$ 19.000 → R$ 16.150"],
        ["Pacote completo (5 eixos)", "25%", "Todos os 5 eixos da consultoria",
         "R$ 29.750 → R$ 22.313 (economia de R$ 7.438)"],
    ]
    cw_combo = [34 * mm, 20 * mm, 56 * mm, 54 * mm]
    elements.append(_three_rule_table(combo_headers, combo_rows, cw_combo))
    elements.append(_spacer(1))
    elements.append(Paragraph(
        "O abatimento de 25% do diagnóstico em monitoramento futuro (em até 60 dias) "
        "é cumulativo com os descontos de pacote acima.",
        S["body_small"]
    ))

    elements.append(_spacer(3))

    # What IS / IS NOT included — crystal clear
    elements.append(Paragraph("O Que Está Incluído e o Que Não Está", S["h2"]))
    incl_nincl_headers = ["Está Incluído", "Não Está Incluído"]
    incl_nincl_rows = [
        [
            "Análise estratégica, precificação de referência, checklist de habilitação "
            "e revisão crítica de conformidade para apoiar a tomada de decisão sobre "
            "participar ou não de uma licitação.",
            "Montagem final dos documentos de habilitação, assinatura, protocolo e "
            "responsabilidade técnica/jurídica sobre a proposta entregue. Essas "
            "atividades permanecem com a empresa.",
        ],
        [
            "Identificação de editais, mapeamento de concorrentes, painel de preços "
            "e alertas de contratos vincendos.",
            "Representação presencial em sessões de licitação, serviços jurídicos "
            "(impugnações, recursos), execução do objeto contratado, garantias financeiras.",
        ],
    ]
    cw_in = [(PAGE_WIDTH - 2 * MARGIN) / 2] * 2
    elements.append(_three_rule_table(incl_nincl_headers, incl_nincl_rows, cw_in))

    elements.append(_spacer(4))

    # Next steps — concrete action, not anxiety
    elements.append(Paragraph("Próximos Passos", S["h2"]))
    elements.append(Paragraph(
        "A reunião de alinhamento define o recorte inicial: região, tipos de obra, "
        "faixa de valor, concorrentes relevantes e órgãos prioritários. Com isso "
        "fechado, o diagnóstico pode ser entregue em 10 a 15 dias úteis.",
        S["body"]
    ))
    elements.append(_spacer(2))

    # CTA — KeepTogether prevents navy box from splitting across pages
    from reportlab.platypus import HRFlowable
    cta_box = Table(
        [
            [Paragraph("Para agendar a reunião de alinhamento:", S["cell_white"])],
            [Paragraph("WhatsApp: (48) 9 8834-4559  |  Email: tiago.sasaki@confenge.com.br", S["cell_white_sub"])],
        ],
        colWidths=[PAGE_WIDTH - 2 * MARGIN],
    )
    cta_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), INK),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    cta_elements = [cta_box, _spacer(3)]
    elements.append(KeepTogether(cta_elements))
    elements.append(_spacer(2))

    # Contact
    contact_elements = [
        HRFlowable(width=(PAGE_WIDTH - 2 * MARGIN) * 0.4, thickness=1, color=INK, spaceAfter=4 * mm, spaceBefore=2 * mm),
        Paragraph("<b>Tiago Sasaki</b>", S["body"]),
        Paragraph("Engenheiro Civil, EESC/USP | Consultor de Inteligência em Licitações", S["body"]),
        Paragraph("WhatsApp: (48) 9 8834-4559 | tiago.sasaki@confenge.com.br", S["body"]),
    ]
    elements.extend(contact_elements)
    elements.append(_spacer(5))

    # Disclaimer
    elements.append(Paragraph(
        f"Proposta preparada em {today_fmt}. Projeções baseadas em dados históricos "
        "de contratações públicas. Este documento não substitui assessoria jurídica, "
        "contábil ou técnica especializada. Anexo: Catálogo de Serviços.",
        S["caption"]
    ))
    elements.append(PageBreak())
    return elements


def _build_catalogo_servicos():
    """Annex: full services catalog. For future reference, not for first-conversation decision."""
    elements = []
    elements.extend(_section_heading("Anexo: Catálogo de Serviços"))
    elements.append(Paragraph(
        "Este anexo apresenta o portfólio completo de serviços de consultoria em "
        "inteligência para licitações públicas. Ele serve como referência para "
        "expansão futura, após a conclusão do diagnóstico inicial. Os valores são "
        "de referência e podem ser ajustados conforme escopo, abrangência geográfica "
        "e complexidade.",
        S["body_small"]
    ))
    elements.append(_spacer(2))

    # Service catalog table
    cat_headers = ["Serviço", "Para Que Serve", "Entregáveis Principais", "Prazo", "Valor de Ref."]
    cat_rows = [
        [
            "Diagnóstico B2G Essencial",
            "Visão inicial de mercado em uma região e tipo de contratação",
            "Mapa de órgãos, top 10 concorrentes, preços de referência, editais recentes",
            "5 a 7 dias úteis",
            "R$ 6.000",
        ],
        [
            "Diagnóstico B2G de Expansão",
            "Mapa completo de oportunidades a partir do perfil da empresa",
            "Mapa de órgãos, 15 concorrentes, painel de preços, contratos vincendos, "
            "editais ativos analisados, recomendações estratégicas",
            "10 a 15 dias úteis",
            "R$ 8.000",
        ],
        [
            "Dossiê Estratégico Completo",
            "Decisão estruturante: expansão regional, diversificação, novo estado",
            "Análise completa de mercado + concorrência + precificação + risco + projeções + plano de ação",
            "20, 30 dias úteis",
            "R$ 17.000",
        ],
        [
            "Monitoramento Mensal Básico",
            "Substituir busca manual de editais por fluxo contínuo de inteligência",
            "Relatórios semanais de oportunidades, alertas de editais prioritários, "
            "1 relatório mensal consolidado",
            "Mensal (mín. 3 meses)",
            "R$ 3.250/mês",
        ],
        [
            "Monitoramento Mensal Estratégico",
            "Operação comercial orientada a dados com inteligência competitiva",
            "Tudo do Básico + análise de concorrência atualizada + mapeamento de "
            "contratos vincendos + painel de preços + 1 reunião mensal",
            "Mensal (mín. 3 meses)",
            "R$ 6.250/mês",
        ],
        [
            "Triagem de Edital",
            "Primeira análise de um edital específico antes de decidir participar",
            "Checklist de 15 a 20 pontos críticos (prazos, exigências, inconsistências, preço de referência)",
            "2 a 3 dias úteis",
            "R$ 1.450",
        ],
        [
            "Análise Técnica de Edital",
            "Edital complexo ou de alto valor: análise completa antes da proposta",
            "Análise detalhada de edital + planilha orçamentária + composições + BDI "
            "+ comparação com preços de mercado",
            "5, 10 dias úteis",
            "R$ 3.750",
        ],
        [
            "Análise Crítica Completa",
            "Decisão GO/NO-GO com parecer fundamentado para editais estratégicos",
            "Análise técnica + concorrência esperada + projeção de margem + recomendação final",
            "10 a 15 dias úteis",
            "R$ 5.500",
        ],
        [
            "Apoio à Elaboração de Proposta",
            "Suporte estratégico para preparação de proposta específica",
            "Posicionamento competitivo, precificação com dados de mercado, checklist "
            "de documentação, revisão de conformidade",
            "Conforme edital",
            "R$ 5.250",
        ],
        [
            "Acompanhamento de Contratos",
            "Supervisionar contratos públicos em execução e antecipar renovações",
            "Alertas de prazos e aditivos, monitoramento de publicações, relatório "
            "mensal de status, preparação para relicitação",
            "Mensal",
            "R$ 4.750/mês",
        ],
    ]
    cw_cat = [32 * mm, 38 * mm, 52 * mm, 22 * mm, 24 * mm]
    elements.append(_three_rule_table(cat_headers, cat_rows, cw_cat))
    elements.append(_spacer(3))

    # Discounts
    elements.append(Paragraph("Descontos para Contratação Combinada", S["h2"]))
    elements.append(_three_rule_table(
        ["Serviços Contratados", "Desconto"],
        [
            ["Diagnóstico + 1 serviço adicional", "10% sobre o total"],
            ["Diagnóstico + 2 serviços adicionais", "15% sobre o total"],
            ["Pacote completo (5 eixos)", "25% sobre o total"],
        ],
        [60 * mm, 60 * mm],
    ))
    elements.append(_spacer(1))
    elements.append(Paragraph(
        "Acumulativo com abatimento de 25% do diagnóstico em monitoramento futuro "
        "contratado em até 60 dias após a entrega. Pagamento anual (monitoramento): "
        "pague 10 meses, leve 12.",
        S["body_small"]
    ))

    elements.append(_spacer(3))
    elements.append(Paragraph("Expansão Progressiva", S["h2"]))
    elements.append(Paragraph(
        "A consultoria é desenhada como esteira de inteligência comercial B2G. "
        "O diagnóstico pontual é a porta de entrada. O monitoramento mensal "
        "transforma inteligência em rotina. A análise de editais reduz risco nas "
        "decisões de participar ou não. O apoio a propostas melhora a competitividade. "
        "O acompanhamento de contratos protege e maximiza o retorno do que já foi "
        "conquistado. Cada etapa financia a seguinte.",
        S["body"]
    ))

    return elements


# ============================================================
# MAIN GENERATOR (v2 — executive + catalog flow)
# ============================================================

def generate_consultoria_pdf(data, output_path):
    global S
    S = _build_styles()

    empresa = data.get("empresa", {})

    decisor_full = empresa["qsa"][0]["nome"] if empresa.get("qsa") else "Prezado(a) Diretor(a)"
    decisor_full = restore_accents(decisor_full)
    honorific = _detect_gender(decisor_full)

    today = datetime.now(timezone.utc).date()
    validity_date = today + timedelta(days=15)

    elements = []

    # 1. Cover (1 page)
    elements.extend(_build_cover(empresa, today, validity_date))

    # 2. Carta ao Decisor with specific thesis (1 page)
    elements.extend(_build_carta_decisor(empresa, data.get("setor", "construção civil"), honorific, decisor_full))

    # 3. Credenciais compactas + governança (1 page)
    elements.extend(_build_credenciais_compact())

    # 4. Diagnóstico de Entrada, concreto (2 pages)
    elements.extend(_build_diagnostico_entrada())

    # 5. Condições Comerciais + Próximos Passos (1 page)
    elements.extend(_build_condicoes_comerciais(today, validity_date))

    # 6. Anexo: Catálogo de Serviços (remaining pages)
    elements.extend(_build_catalogo_servicos())

    # Build PDF
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Proposta de Consultoria Estratégica B2G",
        author="Tiago Sasaki",
    )
    doc.build(elements, onLaterPages=_draw_footer)
    return output_path


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Gera PDF de Proposta de Consultoria Estratégica B2G (estética Big Four)"
    )
    parser.add_argument("--input", "-i", required=True,
                        help="Caminho para JSON de dados (output do build-proposta-data.py)")
    parser.add_argument("--output", "-o",
                        help="Caminho para PDF de saída (default: docs/consultoria-b2g/proposta-{cnpj}.pdf)")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    empresa = data.get("empresa", {})
    cnpj_clean = re.sub(r"\D", "", empresa.get("cnpj", ""))

    output_path = args.output or f"docs/consultoria-b2g/proposta-{cnpj_clean}-consultoria.pdf"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    result = generate_consultoria_pdf(data, output_path)
    print(f"PDF gerado: {result}")


if __name__ == "__main__":
    main()
