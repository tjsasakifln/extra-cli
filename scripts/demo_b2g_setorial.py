#!/usr/bin/env python3
"""
Geração de Dossiê Demo B2G Setorial — v0.1

Recebe setor + UF + período e gera relatório executivo de inteligência
de mercado a partir de contratos públicos homologados (pncp_supplier_contracts).

Outputs:
  - Markdown executivo (demo-{setor}-{uf}.md)
  - JSON consolidado (demo-{setor}-{uf}.json)
  - CSV com órgãos/fornecedores/segmentos (demo-{setor}-{uf}.csv)

Usage:
    python scripts/demo_b2g_setorial.py --setor engenharia --uf SC
    python scripts/demo_b2g_setorial.py --setor manutencao_predial --uf SP --periodo-meses 24
    python scripts/demo_b2g_setorial.py --setor engenharia --uf SC --formato md
    python scripts/demo_b2g_setorial.py --setor engenharia --uf SC --valor-min 50000 --max-contratos 3000

Requer:
    - DATALAKE_QUERY_ENABLED=true (env var)
    - DATALAKE_BACKEND=local (env var, para uso local)
    - LOCAL_DATALAKE_DSN (env var, DSN do PostgreSQL local)
    - datalake_helper.py no mesmo diretório

Fontes:
    - pncp_supplier_contracts (DataLake Supabase)
    - backend/intel_sectors_config.yaml (keywords setoriais)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Path setup ──────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
if str(_PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "backend"))

# ── Imports ─────────────────────────────────────────────────
try:
    from datalake_helper import DatalakeClient
except ImportError:
    print("ERRO: datalake_helper.py não encontrado em scripts/")
    sys.exit(1)

try:
    from scripts.intel_sector_loader import load_intel_sectors_config
except ImportError:
    # Try direct import
    try:
        from intel_sector_loader import load_intel_sectors_config
    except ImportError:
        print("AVISO: intel_sector_loader.py não encontrado. Usando fallback de keywords.")
        load_intel_sectors_config = None  # type: ignore[assignment]

# ── Constants ────────────────────────────────────────────────
VERSION = "0.1.0"
DEFAULT_PERIODO_MESES = 12
DEFAULT_MAX_CONTRATOS = 5000
DEFAULT_VALOR_MIN = 50000.0
DEFAULT_OUTPUT_DIR = "docs/demo"
MIN_CONTRATOS_THRESHOLD = 30
MIN_ORGAOS_THRESHOLD = 5
MIN_FORNECEDORES_THRESHOLD = 5

# Keywords de engenharia/construção para busca no DataLake
# Mapeamento setor → keywords de busca (fallback se intel_sectors_config não disponível)
FALLBACK_KEYWORDS: dict[str, list[str]] = {
    "engenharia": ["reforma", "pavimentação", "construção", "engenharia"],
    "manutencao_predial": ["manutenção predial", "manutencao predial", "reforma predial", "instalação elétrica", "instalação hidráulica", "ar condicionado", "climatização", "pintura predial"],
    "vestuario": ["uniforme", "fardamento", "vestuário", "vestuario", "camiseta", "jaleco"],
    "alimentos": ["merenda", "alimentação escolar", "alimentacao escolar", "gênero alimentício", "genero alimenticio", "refeição", "refeicao"],
    "informatica": ["computador", "notebook", "impressora", "equipamento de informática", "equipamento de informatica"],
    "software": ["software", "sistema de gestão", "licença de software", "desenvolvimento de sistema"],
    "mobiliario": ["mobiliário", "mobiliario", "cadeira", "mesa", "armário", "armario"],
    "facilities": ["limpeza predial", "conservação", "conservacao", "jardinagem", "zeladoria", "portaria"],
    "vigilancia": ["vigilância", "vigilancia", "segurança patrimonial", "seguranca patrimonial", "monitoramento", "cftv"],
    "saude": ["medicamento", "material hospitalar", "equipamento médico", "equipamento medico"],
    "transporte": ["veículo", "veiculo", "ônibus", "onibus", "combustível", "combustivel", "transporte escolar"],
    "materiais_eletricos": ["material elétrico", "material eletrico", "cabo elétrico", "lâmpada", "luminária"],
    "materiais_hidraulicos": ["material hidráulico", "material hidraulico", "tubo", "tubulação", "conexão"],
    "papelaria": ["material de escritório", "material de escritorio", "papelaria", "papel a4", "toner"],
}

# Palavras-chave para classificação de segmentos dentro de engenharia
SEGMENT_KEYWORDS: dict[str, list[str]] = {
    "Pavimentação": ["pavimentação", "pavimentacao", "asfáltica", "asfaltica", "recapeamento", "asfalto", "cbuq", "intertravada", "paver", "bloquete"],
    "Drenagem e Pluvial": ["drenagem", "pluvial", "galeria", "bueiro", "sarjeta", "canalização", "microdrenagem", "macrodrenagem"],
    "Reforma Predial": ["reforma", "predial", "pintura", "telhado", "cobertura", "impermeabilização", "impermeabilizacao", "fachada"],
    "Construção Civil": ["construção", "construcao", "edificação", "edificacao", "ampliação", "ampliacao", "prédio", "predio"],
    "Infraestrutura Viária": ["rodovia", "estrada", "sinalização", "sinalizacao", "ciclovia", "calçada", "calcada", "passeio", "meio-fio", "acostamento"],
    "Saneamento": ["saneamento", "esgoto", "água", "agua", "adutora", "estação de tratamento", "fossa"],
    "Escolas e Creches": ["escola", "creche", "educação infantil", "educacao infantil", "fnde"],
    "Saúde": ["ubs", "posto de saúde", "posto de saude", "hospital", "unidade de saúde", "unidade de saude", "unidade sanitária", "unidade sanitaria", "policlínica", "policlinica"],
    "Esporte e Lazer": ["quadra", "ginásio", "ginasio", "praça", "praca", "parque", "campo", "centro esportivo", "complexo esportivo"],
    "Infraestrutura Urbana": ["muro", "contenção", "contencao", "ponte", "viaduto", "terminal", "abrigo", "urbanização", "urbanizacao"],
}

# ── Helpers ─────────────────────────────────────────────────

def _fmt_brl(value: float) -> str:
    """Formata valor como Real brasileiro: R$ 1.500.000,00"""
    if abs(value) >= 1_000_000:
        return f"R$ {value/1_000_000:,.1f}M".replace(",", "X").replace(".", ",").replace("X", ".")
    if abs(value) >= 1_000:
        return f"R$ {value/1_000:,.0f}K".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def _fmt_num(value: float) -> str:
    """Formata número com separador de milhar brasileiro."""
    return f"{value:,.0f}".replace(",", ".")

def _pct(data: list[float], p: float) -> float:
    """Percentil sobre lista ordenada."""
    n = len(data)
    if n == 0:
        return 0.0
    k = (n - 1) * p
    f = int(k)
    c = min(f + 1, n - 1)
    if f == c:
        return data[f]
    return data[f] + (data[c] - data[f]) * (k - f)

def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def _get_sector_keywords(setor: str) -> list[str]:
    """Obtém keywords de busca para o setor, tentando intel_sectors_config primeiro."""
    if load_intel_sectors_config is not None:
        try:
            config = load_intel_sectors_config()
            if config and "sectors" in config and setor in config["sectors"]:
                sec = config["sectors"][setor]
                # Prioridade: competition_keywords, senão sector_hints
                kw = sec.get("competition_keywords") or sec.get("sector_hints") or []
                if kw:
                    return kw[:8]  # Limitar a 8 para evitar queries muito restritivas
        except Exception:
            pass  # Fallback abaixo

    # Fallback para keywords hardcoded
    if setor in FALLBACK_KEYWORDS:
        return FALLBACK_KEYWORDS[setor]

    # Último recurso: usar o nome do setor como keyword
    return [setor.replace("_", " ")]


def _classify_segments(contratos: list[dict]) -> dict[str, dict]:
    """Classifica contratos em segmentos usando SEGMENT_KEYWORDS."""
    seg_data: dict[str, dict] = {}
    for seg, kws in SEGMENT_KEYWORDS.items():
        n = 0
        v = 0.0
        for c in contratos:
            obj = (c.get("objeto_contrato") or "").lower()
            if any(k in obj for k in kws):
                n += 1
                try:
                    v += float(c.get("valor_global") or 0)
                except (ValueError, TypeError):
                    pass
        seg_data[seg] = {"n": n, "valor_total": v}
    return seg_data


# ── Post-filter: False Positive Removal ─────────────────────

# Patterns that indicate a contract is NOT engenharia/construção,
# even though it matched a keyword like "obra" (→ "mão de obra")
NEGATIVE_PATTERNS_ENGENHARIA: list[str] = [
    # Segurança e vigilância (capturados via "mão de obra")
    "vigilância", "vigilancia", "segurança privada", "seguranca privada",
    "segurança patrimonial", "seguranca patrimonial", "porteiro", "portaria",
    "monitoramento eletrônico", "monitoramento eletronico",
    "alarme", "cftv", "circuito fechado",
    # Limpeza e facilities (capturados via "mão de obra")
    "limpeza predial", "limpeza hospitalar", "limpeza urbana",
    "serviços de limpeza", "servicos de limpeza",
    "higienização", "higienizacao", "asseio e conservação", "asseio e conservacao",
    "coleta de resíduos", "coleta de residuos", "coleta de lixo",
    "jardinagem", "paisagismo", "dedetização", "dedetizacao",
    "zeladoria", "copeiragem",
    # Alimentação (capturados via "mão de obra")
    "merenda escolar", "alimentação escolar", "alimentacao escolar",
    "gênero alimentício", "genero alimenticio",
    "fornecimento de refeição", "fornecimento de refeicao",
    "quentinha", "marmitex", "catering", "buffet",
    "restaurante", "lanchonete",
    # Manutenção de frota/veículos (capturados via "obra" em manutenção veicular)
    "manutenção de frota", "manutencao de frota",
    "manutenção de veículos", "manutencao de veiculos",
    "gerenciamento de frota", "manutenção preditiva.*frota",
    "manutenção preventiva.*frota",
    # Serviços administrativos não-engenharia
    "serviço de copeiragem", "servico de copeiragem",
    "locação de mão de obra", "locacao de mao de obra",
    "fornecimento de mão de obra", "fornecimento de mao de obra",
]

# Patterns that RESCUE a contract from false-positive filter
# (i.e., if the object ALSO contains obvious engineering terms, keep it)
RESCUE_PATTERNS_ENGENHARIA: list[str] = [
    # Termos técnicos de engenharia — alta confiança
    "pavimentação", "pavimentacao", "asf[áa]ltic[ao]", "asfalto",
    "drenagem", "terraplenagem", "edificação", "edificacao",
    "estrutura met[áa]lica", "concreto armado",
    "fundação", "fundacao", "alvenaria", "concretagem",
    "recapeamento", "cbua", "cbuq",
    # Ações de engenharia civil (sem preposição fixa — casa com de/da/do/das/dos)
    "obras? de engenharia", "obras? civis?",
    "construção", "construcao", "ampliação", "ampliacao",
    "reforma", "pavimentação", "pavimentacao",
    "execução de obra", "execucao de obra",
    # Tipos de edificação tipicamente construídos/reformados
    "gin[áa]sio", "quadra (poliesportiva|coberta|esportiva)",
    "escola", "creche", "ubs\\b", "posto de sa[úu]de",
    "unidade (b[áa]sica )?de sa[úu]de", "hospital",
    "terminal (urbano|rodovi[áa]rio|de transporte)",
    "centro (comunit[áa]rio|esportivo)", "praça", "praca",
    "ponte", "viaduto", "passarela",
    # Projetos e serviços técnicos de engenharia
    "projeto (executivo|b[áa]sico|arquitet[ôo]nico)",
    "fiscalização de obra", "fiscalizacao de obra",
    "supervisão de obra", "supervisao de obra",
]


def _filter_false_positives(contracts: list[dict], setor: str) -> list[dict]:
    """Remove contratos que são claramente de outro setor.

    Heurística: se o objeto contém NEGATIVE pattern E NÃO contém RESCUE pattern,
    o contrato é removido. Específico para o setor 'engenharia'.
    """
    if setor not in ("engenharia",):
        return contracts  # Outros setores não têm filtro configurado ainda

    import re

    negative_re = re.compile("|".join(NEGATIVE_PATTERNS_ENGENHARIA), re.IGNORECASE)
    rescue_re = re.compile("|".join(RESCUE_PATTERNS_ENGENHARIA), re.IGNORECASE)

    filtered: list[dict] = []
    removed_examples: list[str] = []

    for c in contracts:
        obj = (c.get("objeto_contrato") or "").lower()
        nome = (c.get("nome_fornecedor") or "").lower()

        neg_match = negative_re.search(obj) or negative_re.search(nome)
        rescue_match = rescue_re.search(obj)

        if neg_match and not rescue_match:
            if len(removed_examples) < 5:
                removed_examples.append(
                    f"  [{c.get('nome_fornecedor', '?')[:40]}] {obj[:100]}"
                )
            continue

        filtered.append(c)

    if removed_examples:
        print("  Exemplos removidos:")
        for ex in removed_examples:
            print(ex)

    return filtered


# ── Core: Coleta ────────────────────────────────────────────

def collect_setorial(
    setor: str,
    uf: str,
    periodo_meses: int = DEFAULT_PERIODO_MESES,
    max_contratos: int = DEFAULT_MAX_CONTRATOS,
    valor_min: float = DEFAULT_VALOR_MIN,
) -> dict[str, Any]:
    """Coleta e agrega dados setoriais do DataLake.

    Returns:
        Dict com meta, orgaos, fornecedores, segmentos, distribuicao, sazonalidade, recorrencia.
        Levanta ValueError se dados insuficientes.
    """
    dl = DatalakeClient()
    if not dl.is_enabled:
        raise RuntimeError(
            "DataLake não disponível. Configure DATALAKE_QUERY_ENABLED=true, "
            "DATALAKE_BACKEND=local e LOCAL_DATALAKE_DSN no ambiente."
        )

    keywords_raw = _get_sector_keywords(setor)
    # Remove accented duplicates (pavimentação ≈ pavimentacao)
    # ILIKE handles both, running both is wasteful and causes timeouts
    seen_kw_norm: set[str] = set()
    keywords: list[str] = []
    for kw in keywords_raw:
        norm = kw.lower()
        # Keep first occurrence of each normalized form
        if norm not in seen_kw_norm:
            seen_kw_norm.add(norm)
            keywords.append(kw)
    # If keywords list is too long, keep only top 5 (prevent timeout chain)
    if len(keywords) > 5:
        keywords = keywords[:5]
    print(f"Setor: {setor} | UF: {uf} | Período: {periodo_meses}m | Keywords: {keywords}")

    # Coleta por keyword individual, com dedup
    all_contracts: list[dict] = []
    seen_ids: set[str] = set()
    per_kw_limit = min(max_contratos // len(keywords), 500) if keywords else 500

    for kw in keywords:
        rows, meta = dl.supplier_contracts(
            ufs=[uf],
            keywords=[kw],
            meses=periodo_meses,
            limit=per_kw_limit,
        )
        if rows:
            added = 0
            for r in rows:
                cid = r.get("numero_controle_pncp") or ""
                if cid and cid in seen_ids:
                    continue
                if cid:
                    seen_ids.add(cid)
                try:
                    v = float(r.get("valor_global") or 0)
                except (ValueError, TypeError):
                    v = 0.0
                if valor_min > 0 and v < valor_min:
                    continue
                all_contracts.append(r)
                added += 1
            print(f"  {kw}: {len(rows)} raw → {added} novos (valor >= R$ {valor_min:,.0f})")
        else:
            print(f"  {kw}: 0 contratos (erro: {meta.get('datalake_error', 'N/A')})")

    # ── Pós-filtro: remover falsos positivos setoriais ──────
    # Contratos capturados por keywords genéricas ("obra" → "mão de obra"
    # em segurança/limpeza/alimentação) são removidos aqui.
    n_before_filter = len(all_contracts)
    all_contracts = _filter_false_positives(all_contracts, setor)
    n_fp_removed = n_before_filter - len(all_contracts)
    if n_fp_removed > 0:
        print(f"Falsos positivos removidos: {n_fp_removed}")

    n_total = len(all_contracts)
    print(f"\nTotal contratos após filtro: {n_total}")

    if n_total < MIN_CONTRATOS_THRESHOLD:
        raise ValueError(
            f"Apenas {n_total} contratos encontrados (mínimo: {MIN_CONTRATOS_THRESHOLD}). "
            f"Tente aumentar o período, reduzir valor_min ou escolher outro setor/UF."
        )

    # ── Valores ──────────────────────────────────────────
    valores = sorted(
        [float(r["valor_global"]) for r in all_contracts
         if r.get("valor_global") and float(r["valor_global"]) > 0]
    )
    valor_total = sum(valores)

    # ── Órgãos ───────────────────────────────────────────
    orgaos_d: dict[str, dict] = {}
    for r in all_contracts:
        cnpj = r.get("orgao_cnpj") or "?"
        nome = r.get("orgao_nome") or "Órgão Desconhecido"
        key = f"{cnpj}|{nome}"
        if key not in orgaos_d:
            orgaos_d[key] = {"nome": nome, "cnpj": cnpj, "n": 0, "valor": 0.0, "uf": r.get("uf", ""), "objetos": []}
        o = orgaos_d[key]
        o["n"] += 1
        try:
            o["valor"] += float(r.get("valor_global") or 0)
        except (ValueError, TypeError):
            pass
        if len(o["objetos"]) < 3:
            o["objetos"].append((r.get("objeto_contrato") or "")[:150])

    ranked_org = sorted(orgaos_d.values(), key=lambda x: x["n"], reverse=True)[:20]
    if len(ranked_org) < MIN_ORGAOS_THRESHOLD:
        raise ValueError(f"Apenas {len(ranked_org)} órgãos encontrados (mínimo: {MIN_ORGAOS_THRESHOLD}).")

    # ── Fornecedores ─────────────────────────────────────
    forn_d: dict[str, dict] = {}
    for r in all_contracts:
        cnpj = r.get("ni_fornecedor") or "?"
        nome = (r.get("nome_fornecedor") or "Desconhecido").upper()
        if cnpj not in forn_d:
            forn_d[cnpj] = {"nome": nome, "cnpj": cnpj, "n": 0, "valor": 0.0, "orgaos": set(), "objetos": []}
        f = forn_d[cnpj]
        f["n"] += 1
        try:
            f["valor"] += float(r.get("valor_global") or 0)
        except (ValueError, TypeError):
            pass
        f["orgaos"].add((r.get("orgao_nome") or "")[:50])
        if len(f["objetos"]) < 2:
            f["objetos"].append((r.get("objeto_contrato") or "")[:120])

    ranked_forn = sorted(forn_d.values(), key=lambda x: x["valor"], reverse=True)[:20]
    if len(ranked_forn) < MIN_FORNECEDORES_THRESHOLD:
        raise ValueError(f"Apenas {len(ranked_forn)} fornecedores encontrados (mínimo: {MIN_FORNECEDORES_THRESHOLD}).")

    # ── Segmentos ────────────────────────────────────────
    segmentos = _classify_segments(all_contracts)
    ranked_seg = sorted(segmentos.items(), key=lambda x: x[1]["valor_total"], reverse=True)

    # ── Sazonalidade ─────────────────────────────────────
    monthly: dict[str, dict] = defaultdict(lambda: {"n": 0, "valor": 0.0})
    for r in all_contracts:
        d = (r.get("data_assinatura") or "")[:7]
        if d:
            monthly[d]["n"] += 1
            try:
                monthly[d]["valor"] += float(r.get("valor_global") or 0)
            except (ValueError, TypeError):
                pass

    # ── Recorrência ──────────────────────────────────────
    recorrencia: list[dict] = []
    for o in ranked_org:
        if o["n"] >= 5:
            objs = " ".join(o["objetos"]).lower()
            segs = [seg for seg, kws in SEGMENT_KEYWORDS.items() if any(k in objs for k in kws)]
            if segs:
                recorrencia.append({
                    "orgao": o["nome"],
                    "n_contratos": o["n"],
                    "segmentos": segs[:3],
                    "valor_total": round(o["valor"], 2),
                })

    return {
        "meta": {
            "titulo": f"Dossiê Demo Extra Consultoria Intelligence — {setor.replace('_', ' ').title()} em {uf}",
            "setor": setor,
            "uf": uf,
            "periodo": f"{periodo_meses} meses",
            "data_geracao": _today_str(),
            "versao_script": VERSION,
            "total_contratos": n_total,
            "valor_total": round(valor_total, 2),
            "orgaos_distintos": len(orgaos_d),
            "fornecedores_ativos": len(forn_d),
            "valor_min_filtro": valor_min,
            "fontes": ["pncp_supplier_contracts via DataLake Supabase"],
            "keywords_utilizadas": keywords,
        },
        "orgaos": [
            {
                "nome": o["nome"], "cnpj": o["cnpj"], "n_contratos": o["n"],
                "valor_total": round(o["valor"], 2),
                "ticket_medio": round(o["valor"] / o["n"], 2) if o["n"] else 0,
                "objetos_tipicos": o["objetos"][:3],
            }
            for o in ranked_org
        ],
        "fornecedores": [
            {
                "nome": f["nome"], "cnpj": f["cnpj"], "n_contratos": f["n"],
                "valor_total": round(f["valor"], 2),
                "ticket_medio": round(f["valor"] / f["n"], 2) if f["n"] else 0,
                "n_orgaos": len(f["orgaos"]),
                "objetos": f["objetos"][:2],
            }
            for f in ranked_forn
        ],
        "segmentos": [
            {"segmento": seg, "n": d["n"], "valor_total": round(d["valor_total"], 2)}
            for seg, d in ranked_seg if d["n"] > 0
        ],
        "distribuicao_valores": {
            "n": len(valores),
            "p10": round(_pct(valores, 0.10), 2),
            "p25": round(_pct(valores, 0.25), 2),
            "p50": round(_pct(valores, 0.50), 2),
            "p75": round(_pct(valores, 0.75), 2),
            "p90": round(_pct(valores, 0.90), 2),
            "media": round(sum(valores) / len(valores), 2) if valores else 0,
            "total": round(sum(valores), 2),
        },
        "sazonalidade": {
            m: {"n": d["n"], "valor_total": round(d["valor"], 2)}
            for m, d in sorted(monthly.items())
        },
        "recorrencia": recorrencia[:15],
    }


# ── Output: Markdown ────────────────────────────────────────

def _md_safe(s: str) -> str:
    """Escapa pipes e newlines para células de tabela Markdown."""
    return (s or "").replace("|", "\\|").replace("\n", " ").replace("\r", "")

def generate_markdown(data: dict, setor: str, uf: str) -> str:
    """Gera relatório Markdown executivo a partir dos dados consolidados."""
    m = data["meta"]
    dv = data["distribuicao_valores"]
    orgs = data["orgaos"]
    forns = data["fornecedores"]
    segs = data["segmentos"]
    rec = data["recorrencia"]
    saz = data["sazonalidade"]

    setor_nome = setor.replace("_", " ").title()

    lines: list[str] = []
    a = lines.append

    a(f"# Dossiê Demo Extra Consultoria Intelligence")
    a(f"")
    a(f"## Inteligência B2G para {setor_nome} em {uf}")
    a(f"")
    a(f"**Data de geração:** {m['data_geracao']}  ")
    a(f"**Classificação:** DEMONSTRAÇÃO — Dados Reais de Contratos Públicos  ")
    a(f"**Versão do script:** {VERSION}  ")
    a(f"**Preparado por:** Extra Consultoria Intelligence")
    a(f"")
    a(f"---")
    a(f"")
    a(f"## 1. Sumário Executivo")
    a(f"")

    # Sumário comercial automático
    top_f = forns[0] if forns else {"nome": "N/D", "valor_total": 0}
    top_o = orgs[0] if orgs else {"nome": "N/D", "n_contratos": 0}
    top_seg = segs[0] if segs else {"segmento": "N/D", "valor_total": 0}

    a(f"**O mercado de {setor_nome.lower()} em {uf} movimentou {_fmt_brl(m['valor_total'])} em contratos públicos nos últimos {m['periodo']}**, "
      f"distribuídos em {_fmt_num(m['total_contratos'])} contratações de {m['orgaos_distintos']} órgãos públicos diferentes.")
    a(f"")
    a(f"**Por que isso importa para uma empresa que vende ao governo:**")
    a(f"")
    a(f"- **{_fmt_brl(m['valor_total'])}** em contratos assinados — o mercado existe e é mensurável.")
    if segs:
        a(f"- **{top_seg['segmento']} domina com {_fmt_brl(top_seg['valor_total'])}** — é o segmento de maior demanda em {uf}.")
    a(f"- **{m['fornecedores_ativos']} fornecedores ativos** — mercado fragmentado, sem monopólio evidente.")
    a(f"- **{m['orgaos_distintos']} órgãos compradores distintos** — base pulverizada, múltiplos pontos de entrada.")
    a(f"- **Mediana de {_fmt_brl(dv['p50'])} por contrato** — acessível a empresas de pequeno e médio porte.")
    a(f"")

    # Achados principais (top 5 automáticos)
    a(f"## 2. Principais Métricas")
    a(f"")
    a(f"| Métrica | Valor |")
    a(f"|---------|-------|")
    a(f"| Contratos analisados | {_fmt_num(m['total_contratos'])} |")
    a(f"| Valor total | {_fmt_brl(m['valor_total'])} |")
    a(f"| Órgãos distintos | {m['orgaos_distintos']} |")
    a(f"| Fornecedores ativos | {m['fornecedores_ativos']} |")
    a(f"| Mediana (P50) | {_fmt_brl(dv['p50'])} |")
    a(f"| P75 | {_fmt_brl(dv['p75'])} |")
    a(f"| Média | {_fmt_brl(dv['media'])} |")
    a(f"| Segmento dominante | {top_seg['segmento']} ({_fmt_brl(top_seg['valor_total'])}) |")
    a(f"| Top órgão | {top_o['nome'][:60]} ({top_o['n_contratos']} contratos) |")
    a(f"| Top fornecedor | {top_f['nome'][:60]} ({_fmt_brl(top_f['valor_total'])}) |")
    a(f"")
    a(f"## 3. Recorte Analisado")
    a(f"")
    a(f"| Dimensão | Valor |")
    a(f"|----------|-------|")
    a(f"| Setor analisado | {setor_nome} |")
    a(f"| UF | {uf} |")
    a(f"| Período | {m['periodo']} |")
    a(f"| Fonte primária | PNCP — Contratos homologados (pncp_supplier_contracts) |")
    a(f"| Contratos analisados | {_fmt_num(m['total_contratos'])} (após deduplicação e filtro valor >= {_fmt_brl(m['valor_min_filtro'])}) |")
    a(f"| Valor total analisado | {_fmt_brl(m['valor_total'])} |")
    a(f"| Órgãos identificados | {m['orgaos_distintos']} órgãos distintos |")
    a(f"| Fornecedores ativos | {m['fornecedores_ativos']} CNPJs distintos |")
    a(f"| Metodologia | Busca por palavras-chave setoriais com deduplicação por número de controle PNCP |")
    a(f"| Keywords utilizadas | {', '.join(m.get('keywords_utilizadas', ['N/D']))} |")
    a(f"")
    a(f"## 4. Principais Achados")
    a(f"")

    # Gerar achados automaticamente
    achados = []

    if segs:
        achados.append({
            "titulo": f"{top_seg['segmento']} é o segmento dominante",
            "evidencia": f"{top_seg['segmento']} representa {top_seg['valor_total']/m['valor_total']*100:.0f}% do valor total contratado ({_fmt_brl(top_seg['valor_total'])}) em {top_seg['n']} contratos.",
            "estrategia": f"Empresas com capacidade neste segmento têm demanda comprovada. Empresas sem este perfil devem focar em segmentos secundários.",
        })

    if dv["p50"] > 0 and dv["p75"] > dv["p50"] * 3:
        achados.append({
            "titulo": "Alta dispersão de valores — oportunidades para todos os portes",
            "evidencia": f"A mediana é {_fmt_brl(dv['p50'])} mas o P75 é {_fmt_brl(dv['p75'])} — {dv['p75']/dv['p50']:.0f}x maior. Os 10% maiores contratos ultrapassam {_fmt_brl(dv['p90'])}.",
            "estrategia": "Empresas de pequeno/médio porte devem mirar o P50. Empresas maiores têm menos concorrência no P90+.",
        })

    if saz:
        meses_ord = sorted(saz.keys())
        if len(meses_ord) >= 3:
            pico_mes = max(saz.keys(), key=lambda m: saz[m]["valor_total"])
            vale_mes = min(saz.keys(), key=lambda m: saz[m]["valor_total"])
            achados.append({
                "titulo": f"Sazonalidade marcante — pico em {pico_mes}",
                "evidencia": f"{pico_mes} concentrou {_fmt_brl(saz[pico_mes]['valor_total'])} em {saz[pico_mes]['n']} contratos, versus {_fmt_brl(saz[vale_mes]['valor_total'])} em {vale_mes}.",
                "estrategia": f"Preparação de propostas deve começar 60-90 dias antes do pico sazonal. Abordagem comercial deve anteceder o ciclo de contratação.",
            })

    if m["orgaos_distintos"] > 50:
        achados.append({
            "titulo": "Mercado pulverizado — base de órgãos compradores extensa",
            "evidencia": f"{m['orgaos_distintos']} órgãos distintos contrataram no período. Nenhum órgão concentra mais de {orgs[0]['valor_total']/m['valor_total']*100:.0f}% do valor total.",
            "estrategia": "A estratégia de vendas deve ser capilar. Priorize os top 20 órgãos (que concentram a maior parte do valor) e expanda gradualmente.",
        })

    if len(forns) >= 10:
        top3_share = sum(f["valor_total"] for f in forns[:3]) / m["valor_total"] * 100
        achados.append({
            "titulo": f"Top 3 fornecedores detêm apenas {top3_share:.0f}% do mercado — sem monopólio",
            "evidencia": f"Os 3 maiores fornecedores somam {_fmt_brl(sum(f['valor_total'] for f in forns[:3]))} de {_fmt_brl(m['valor_total'])}.",
            "estrategia": "Há espaço para novos entrantes. A barreira não é tamanho do concorrente, mas capacidade de identificar e se posicionar para oportunidades.",
        })

    for i, ac in enumerate(achados[:8]):
        a(f"### Achado {i+1} — {ac['titulo']}")
        a(f"")
        a(f"**Evidência:** {ac['evidencia']}")
        a(f"")
        a(f"**Implicação comercial:** {ac['estrategia']}")
        a(f"")

    # ── Órgãos ───────────────────────────────────────────
    a(f"## 5. Órgãos Compradores Prioritários")
    a(f"")
    a(f"| # | Órgão | Contratos | Valor Total | Ticket Médio | Objetos Típicos |")
    a(f"|---|-------|-----------|-------------|--------------|-----------------|")
    for i, o in enumerate(orgs[:20]):
        ticket = o["valor_total"] / o["n_contratos"] if o["n_contratos"] else 0
        obj = _md_safe(o["objetos_tipicos"][0][:80]) if o["objetos_tipicos"] else "-"
        a(f"| {i+1} | {_md_safe(o['nome'][:55])} | {o['n_contratos']} | {_fmt_brl(o['valor_total'])} | {_fmt_brl(ticket)} | {obj} |")
    a(f"")

    # ── Fornecedores ─────────────────────────────────────
    a(f"## 6. Fornecedores/Concorrentes Recorrentes")
    a(f"")
    a(f"| # | Fornecedor | CNPJ | Contratos | Valor Total | Órgãos | Ticket Médio |")
    a(f"|---|-----------|------|-----------|-------------|--------|--------------|")
    for i, f in enumerate(forns[:20]):
        ticket = f["valor_total"] / f["n_contratos"] if f["n_contratos"] else 0
        a(f"| {i+1} | {_md_safe(f['nome'][:50])} | {f['cnpj'][:14]} | {f['n_contratos']} | {_fmt_brl(f['valor_total'])} | {f['n_orgaos']} | {_fmt_brl(ticket)} |")
    a(f"")

    # ── Faixas de valor ──────────────────────────────────
    a(f"## 7. Faixas de Valor e Padrões de Contratação")
    a(f"")
    a(f"| Indicador | Valor |")
    a(f"|-----------|-------|")
    a(f"| Total | {_fmt_brl(dv['total'])} |")
    a(f"| Média | {_fmt_brl(dv['media'])} |")
    a(f"| P10 | {_fmt_brl(dv['p10'])} |")
    a(f"| P25 | {_fmt_brl(dv['p25'])} |")
    a(f"| P50 (mediana) | {_fmt_brl(dv['p50'])} |")
    a(f"| P75 | {_fmt_brl(dv['p75'])} |")
    a(f"| P90 | {_fmt_brl(dv['p90'])} |")
    a(f"")
    a(f"**Leitura:** 50% dos contratos estão entre {_fmt_brl(dv['p25'])} e {_fmt_brl(dv['p75'])}. "
      f"Contratos acima de {_fmt_brl(dv['p90'])} representam os 10% maiores e tendem a ter concorrência mais qualificada.")
    a(f"")

    # ── Segmentos ────────────────────────────────────────
    if segs:
        a(f"## 8. Segmentos ou Subcategorias Relevantes")
        a(f"")
        a(f"| Segmento | Contratos | Valor Total | % do Total |")
        a(f"|----------|-----------|-------------|------------|")
        for seg in segs[:12]:
            pct = seg["valor_total"] / m["valor_total"] * 100 if m["valor_total"] else 0
            a(f"| {seg['segmento']} | {seg['n']} | {_fmt_brl(seg['valor_total'])} | {pct:.0f}% |")
        a(f"")
        a(f"**Nota:** Um mesmo contrato pode pertencer a múltiplos segmentos. Percentuais não somam 100%.")
        a(f"")

    # ── Sazonalidade ─────────────────────────────────────
    if len(saz) >= 3:
        a(f"## 9. Sazonalidade")
        a(f"")
        a(f"| Mês | Contratos | Valor Total |")
        a(f"|-----|-----------|-------------|")
        for m_key in sorted(saz.keys()):
            d = saz[m_key]
            a(f"| {m_key} | {d['n']} | {_fmt_brl(d['valor_total'])} |")
        a(f"")

    # ── Recorrência ──────────────────────────────────────
    if rec:
        a(f"## 10. Indícios de Recorrência")
        a(f"")
        a(f"**Atenção:** São padrões históricos observáveis, não previsão garantida de contratação futura.")
        a(f"")
        a(f"| Órgão | Contratos | Segmentos Principais |")
        a(f"|-------|-----------|---------------------|")
        for r in rec[:10]:
            a(f"| {_md_safe(r['orgao'][:50])} | {r['n_contratos']} | {', '.join(r['segmentos'])} |")
        a(f"")

    # ── Oportunidades ────────────────────────────────────
    a(f"## 11. Oportunidades Comerciais Priorizadas")
    a(f"")
    a(f"| # | Órgão-Alvo | Racional | Confiança | Esforço |")
    a(f"|---|-----------|----------|-----------|---------|")
    for i, o in enumerate(orgs[:10]):
        ticket = o["valor_total"] / o["n_contratos"] if o["n_contratos"] else 0
        if ticket > 1_000_000:
            confianca = "Alta"
            esforco = "Médio/Alto"
            racional = f"Ticket alto ({_fmt_brl(ticket)}), {o['n_contratos']} contratos. Comprador recorrente."
        elif ticket > 200_000:
            confianca = "Média"
            esforco = "Médio"
            racional = f"Ticket moderado ({_fmt_brl(ticket)}), {o['n_contratos']} contratos. Bom ponto de entrada."
        else:
            confianca = "Baixa"
            esforco = "Baixo"
            racional = f"Ticket baixo ({_fmt_brl(ticket)}). Pode ser porta de entrada para relacionamento."
        a(f"| {i+1} | {_md_safe(o['nome'][:45])} | {racional} | {confianca} | {esforco} |")
    a(f"")

    # ── Riscos ──────────────────────────────────────────
    a(f"## 12. Riscos e Limitações")
    a(f"")
    a(f"**Limitações metodológicas deste dossiê:**")
    a(f"")
    a(f"1. **Fonte única:** Dados provenientes exclusivamente do PNCP. Contratos não publicados ou publicados apenas em diários oficiais podem não estar cobertos.")
    a(f"2. **Ruído em objetos contratuais:** Descrições genéricas ou imprecisas podem causar falsos positivos (ex: materiais de construção classificados como obra).")
    a(f"3. **Busca por palavras-chave:** Contratos com objetos mal descritos podem não ser capturados.")
    a(f"4. **Cobertura do DataLake:** O período analisado está limitado à retenção do DataLake. Contratos muito antigos podem não estar disponíveis.")
    a(f"5. **Sem verificação de aditivos:** Os valores são os originais do contrato. Aditivos posteriores não estão refletidos.")
    a(f"6. **Não é recomendação de investimento:** Este documento é uma demonstração de inteligência de mercado. Não substitui due diligence jurídica, técnica ou comercial.")
    a(f"7. **Demonstração:** Esta é uma versão demo gerada automaticamente. A versão premium incluiria análise documental de editais, perfil financeiro de concorrentes e monitoramento contínuo.")
    a(f"")

    # ── Plano 30 dias ───────────────────────────────────
    a(f"## 13. Plano de Ataque Comercial de 30 Dias")
    a(f"")
    a(f"### Semana 1 — Seleção e Inteligência")
    a(f"- Selecionar 10 órgãos prioritários da Seção 5")
    a(f"- Levantar CNPJ, telefone e email do setor de licitações de cada órgão")
    a(f"- Verificar editais abertos destes órgãos no PNCP (últimos 30 dias)")
    a(f"")
    a(f"### Semana 2 — Abordagem Consultiva")
    a(f"- Contato com 5 prefeituras de médio/alto valor")
    a(f"- Contato com 5 prefeituras de menor porte (porta de entrada)")
    a(f"- Follow-up dos contatos não respondidos")
    a(f"")
    a(f"### Semana 3 — Preparação Técnica")
    a(f"- Para órgãos que responderam: solicitar editais e projetos básicos")
    a(f"- Preparar documentação de habilitação (certidões atualizadas)")
    a(f"- Elaborar planilha de preços para editais-alvo")
    a(f"")
    a(f"### Semana 4 — Follow-up e Refinamento")
    a(f"- Follow-up de todos os contatos sem retorno")
    a(f"- Novos contatos: prefeituras de pequeno porte")
    a(f"- Planejamento do mês seguinte com base nos resultados")
    a(f"")

    # ── ROI ─────────────────────────────────────────────
    a(f"## 14. Como Este Relatório se Paga")
    a(f"")
    a(f"1. **Economia de tempo:** Levantar manualmente estes dados consumiria 40-80 horas de um diretor comercial. A R$ 150/hora, isso equivale a R$ 6.000-12.000.")
    a(f"2. **Priorização:** Focar nos 20 órgãos que mais contratam aumenta a taxa de conversão versus prospecção aleatória.")
    a(f"3. **Precificação:** Saber a mediana de {_fmt_brl(dv['p50'])} e o P90 de {_fmt_brl(dv['p90'])} permite calibrar o porte de edital adequado ao seu negócio.")
    a(f"4. **Antecipação:** Conhecer o ciclo de contratação permite preparar documentação antes do edital sair.")
    a(f"")

    # ── Próximos passos ─────────────────────────────────
    a(f"## 15. Próximos Passos")
    a(f"")
    a(f"1. **Validar os órgãos prioritários** contra sua própria experiência e região de atuação.")
    a(f"2. **Solicitar versão personalizada** com seu CNPJ — inclui acervo compatível, concorrentes específicos e oportunidades abertas.")
    a(f"3. **Contratar monitoramento mensal** para não perder novos editais nos órgãos prioritários.")
    a(f"4. **War room para edital específico** — dossiê completo com documentos, preços de referência e checklist de habilitação.")
    a(f"")
    a(f"---")
    a(f"")
    a(f"*Dossiê gerado por Extra Consultoria Intelligence em {m['data_geracao']}.*  ")
    a(f"*Dados: PNCP via DataLake Supabase. Metodologia: extração por palavras-chave setoriais com deduplicação.*  ")
    a(f"*Este documento é uma demonstração de capacidade analítica. Não constitui recomendação de investimento ou garantia de resultado.*  ")
    a(f"")

    return "\n".join(lines)


# ── Output: CSV ────────────────────────────────────────────

def generate_csv(data: dict, filepath: Path) -> None:
    """Gera CSV com órgãos, fornecedores e segmentos."""
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)

        w.writerow(["TIPO", "NOME", "CNPJ", "N_CONTRATOS", "VALOR_TOTAL", "TICKET_MEDIO", "DETALHES"])
        for o in data["orgaos"]:
            ticket = o["valor_total"] / o["n_contratos"] if o["n_contratos"] else 0
            w.writerow(["ÓRGÃO", o["nome"], o["cnpj"], o["n_contratos"], o["valor_total"], round(ticket, 2),
                        " | ".join([obj[:100] for obj in o.get("objetos_tipicos", [])[:2]])])
        w.writerow([])

        for f in data["fornecedores"]:
            ticket = f["valor_total"] / f["n_contratos"] if f["n_contratos"] else 0
            w.writerow(["FORNECEDOR", f["nome"], f["cnpj"], f["n_contratos"], f["valor_total"], round(ticket, 2),
                        f"{f['n_orgaos']} órgãos | {' | '.join(f.get('objetos', [])[:1])}"])
        w.writerow([])

        for seg in data["segmentos"]:
            pct = seg["valor_total"] / data["meta"]["valor_total"] * 100 if data["meta"]["valor_total"] else 0
            w.writerow(["SEGMENTO", seg["segmento"], "", seg["n"], seg["valor_total"], round(pct, 1), ""])
        w.writerow([])

        dv = data["distribuicao_valores"]
        w.writerow(["DISTRIBUIÇÃO", "P10", "P25", "P50", "P75", "P90", "MÉDIA", "TOTAL"])
        w.writerow(["VALORES", dv["p10"], dv["p25"], dv["p50"], dv["p75"], dv["p90"], dv["media"], dv["total"]])


# ── Main ────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Geração de Dossiê Demo B2G Setorial — v0.1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python scripts/demo_b2g_setorial.py --setor engenharia --uf SC
  python scripts/demo_b2g_setorial.py --setor manutencao_predial --uf SP --periodo-meses 24
  python scripts/demo_b2g_setorial.py --setor engenharia --uf SC --formato md --valor-min 50000
        """,
    )
    parser.add_argument("--setor", required=True, help="Setor econômico (ex: engenharia, manutencao_predial, vestuario)")
    parser.add_argument("--uf", required=True, help="UF (ex: SC, SP, MG)")
    parser.add_argument("--periodo-meses", type=int, default=DEFAULT_PERIODO_MESES, help=f"Meses de análise (default: {DEFAULT_PERIODO_MESES})")
    parser.add_argument("--max-contratos", type=int, default=DEFAULT_MAX_CONTRATOS, help=f"Máximo de contratos (default: {DEFAULT_MAX_CONTRATOS})")
    parser.add_argument("--valor-min", type=float, default=DEFAULT_VALOR_MIN, help=f"Valor mínimo por contrato (default: {DEFAULT_VALOR_MIN})")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help=f"Diretório de saída (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--formato", choices=["md", "json", "csv", "todos"], default="todos", help="Formato(s) de saída (default: todos)")
    args = parser.parse_args()

    setor = args.setor
    uf = args.uf.upper()
    periodo = args.periodo_meses
    max_contratos = args.max_contratos
    valor_min = args.valor_min
    output_dir = Path(args.output_dir)
    formato = args.formato

    # Validar setor
    keywords = _get_sector_keywords(setor)
    if not keywords:
        print(f"ERRO: Setor '{setor}' não encontrado. Setores disponíveis:")
        print(f"  Fallback keywords: {list(FALLBACK_KEYWORDS.keys())}")
        sys.exit(1)

    print(f"=== Dossiê Demo B2G Setorial v{VERSION} ===")
    print(f"Setor: {setor} | UF: {uf} | Período: {periodo}m | Valor mín: R$ {valor_min:,.0f}")
    print()

    # Coletar
    try:
        data = collect_setorial(
            setor=setor,
            uf=uf,
            periodo_meses=periodo,
            max_contratos=max_contratos,
            valor_min=valor_min,
        )
    except ValueError as e:
        print(f"\nERRO: {e}")
        sys.exit(2)
    except RuntimeError as e:
        print(f"\nERRO FATAL: {e}")
        sys.exit(3)

    # Criar diretório
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"demo-v0-{setor}-{uf}"

    # Gerar outputs
    generated: list[str] = []

    if formato in ("json", "todos"):
        json_path = output_dir / f"{prefix}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        generated.append(f"JSON: {json_path} ({json_path.stat().st_size} bytes)")

    if formato in ("csv", "todos"):
        csv_path = output_dir / f"{prefix}.csv"
        generate_csv(data, csv_path)
        generated.append(f"CSV: {csv_path} ({csv_path.stat().st_size} bytes)")

    if formato in ("md", "todos"):
        md_content = generate_markdown(data, setor, uf)
        md_path = output_dir / f"{prefix}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        generated.append(f"MD: {md_path} ({md_path.stat().st_size} bytes)")

    print()
    for g in generated:
        print(g)

    m = data["meta"]
    print(f"\n=== RESUMO ===")
    print(f"Contratos: {_fmt_num(m['total_contratos'])}")
    print(f"Valor total: {_fmt_brl(m['valor_total'])}")
    print(f"Órgãos distintos: {m['orgaos_distintos']}")
    print(f"Fornecedores ativos: {m['fornecedores_ativos']}")
    dv = data["distribuicao_valores"]
    print(f"Mediana: {_fmt_brl(dv['p50'])} | P75: {_fmt_brl(dv['p75'])} | Média: {_fmt_brl(dv['media'])}")
    print(f"\n✅ Dossiê gerado com sucesso em {output_dir}/")


if __name__ == "__main__":
    main()
