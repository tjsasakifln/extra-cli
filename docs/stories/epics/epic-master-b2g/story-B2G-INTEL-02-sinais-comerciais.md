---
story_id: B2G-INTEL-02
title: "Pipeline de sinais comerciais — detectar oportunidades para CONFENGE"
status: ready
priority: P0
risk_level: STANDARD
effort: L
agent: "@dev"
epic: EPIC-MASTER-B2G-READINESS
phase: 5
depends_on: [B2G-INTEL-01, B2G-BACKFILL-01]
blocks: [B2G-INTEL-03, B2G-INTEL-04]
---

# Story B2G-INTEL-02: Pipeline de Sinais Comerciais

## Problema

O PRD v2.0 reconhece que todas as métricas comerciais estão NOT_READY (contract_total_value, deságio, win_rate, relicitacao_probability). As APIs públicas não expõem os dados necessários para as métricas originais (preço praticado, deságio por item).

**Mudança estratégica:** O objetivo não é mais "analytics para Extra Construtora" e sim "sinais comerciais para CONFENGE". Os sinais relevantes são diferentes e mais acionáveis:

- Empresa vencedora de contrato relevante (valor alto, órgão grande)
- Deságio elevado (risco de execução)
- Entrada em novo estado ou órgão
- Contrato muito maior que o histórico da empresa
- Sucessão de aditivos, suspensão, rescisão, relicitação
- Baixa concorrência, histórico de inabilitação
- Prazo curto, visita técnica, documentos complexos

## Escopo

**IN:** Implementar 12+ sinais comerciais determinísticos no QW-01 Radar, unificar com competitive_intel_validation.py, expor via CLI `opportunity_intel signals`, gerar fila pequena e priorizada (não milhares de registros).

**OUT:** Preço praticado (B2G-2 original — dados não disponíveis nas APIs), win rate (B2G-3 original — requer tracking manual), dashboard TUI, alertas Telegram.

## Acceptance Criteria

1. **AC1:** 12+ sinais comerciais implementados — cada sinal tem: nome, descrição, gatilho, confidence, evidência
2. **AC2:** Sinais detectados para ≥5 oportunidades/dia (após backfill)
3. **AC3:** Cada sinal vinculado a: CNPJ da empresa, edital/contrato fonte, URL de evidência
4. **AC4:** CLI: `python scripts/opportunity_intel/cli.py signals --limit 20` funcional
5. **AC5:** Sinais ranqueados por prioridade (não por data)
6. **AC6:** Zero falsos positivos nos top-10 sinais (validado manualmente)

## Sinais a Implementar

| Sinal | Gatilho | Prioridade |
|-------|---------|-----------|
| Vencedor com contrato > R$1M | valor_global > 1M | Alta |
| Deságio > 30% | (estimado - contratado) / estimado > 0.3 | Alta |
| Empresa em novo órgão | CNPJ nunca visto naquele órgão | Alta |
| Contrato 3x maior que média | valor > 3 * ticket_médio(CNPJ) | Alta |
| Sucessão de aditivos | ≥3 aditivos no mesmo contrato | Média |
| Baixa concorrência | ≤2 participantes na licitação | Média |
| Prazo curto | <15 dias até abertura | Média |
| Visita técnica obrigatória | keyword no edital | Média |
| Histórico de inabilitação | CNPJ com inabilitação prévia | Média |
| Suspensão ou revogação | evento de suspensão/republicação | Alta |
| Edital com muitos anexos | >10 documentos | Baixa |
| Empresa com crescimento rápido | contratos/ano dobrando | Média |

## Tasks

- [ ] Task 1: Implementar detectores de sinais em `opportunity_intel/` (módulo `signals.py`)
- [ ] Task 2: Integrar com QW-01 Radar pipeline
- [ ] Task 3: Implementar CLI `signals` e `explain`
- [ ] Task 4: Validar manualmente top-20 sinais
- [ ] Task 5: Ajustar thresholds com base na validação

## Definition of Done

- [ ] 12+ sinais implementados e testados
- [ ] CLI signals funcional
- [ ] Top-10 sinais validados manualmente (zero falsos positivos)
- [ ] Documentação de cada sinal com evidência e confidence

## Arquivos Afetados

- `scripts/opportunity_intel/signals.py` (novo)
- `scripts/opportunity_intel/cli.py`
- `scripts/opportunity_intel/radar.py`
- `scripts/opportunity_intel/ranking.py`
- `scripts/opportunity_intel/competitive_intel_validation.py`
