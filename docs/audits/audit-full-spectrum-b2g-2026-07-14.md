# Auditoria Full-Spectrum B2G — Extra Consultoria

**Data:** 2026-07-14
**Commit:** fe7fed3 (HEAD)
**Branch:** main
**Método:** 5 auditores paralelos read-only + convergência do coordenador
**Escopo:** AEC (engenharia/construção/obras), Santa Catarina, 200km Florianópolis, Extra Construtora

---

## 1. Matriz de Readiness

| Capacidade | Estado | Evidência |
|-----------|--------|-----------|
| Órgãos compradores | NOT_READY | Sem ranking, perfil ou scoring de órgãos. Apenas listagem em panorama.py |
| Contratos históricos | NOT_READY | Crawler implementado, 0 contratos ingeridos. PNCP API live (6735 registros/dia) |
| Contratos vincendos | NOT_READY | 0 contratos com data_fim_vigencia no raio 200km. Views criadas, sem dados |
| Concorrentes históricos | PARTIAL | View v_supplier_winners com HHI. 0 dados em SQLite. Manifesto PG mostra 63.679 fornecedores |
| Preços e valores | PARTIAL | Semântica documentada. Falso deságio por média de órgão. Sem preço-unitário comparável |
| Editais abertos | READY | PNCP funcional. Briefing sem filtro AEC/200km. Ranking/scoring determinístico |
| Diagnóstico B2G | PARTIAL | Geradores PDF/Excel existem. Pipeline end-to-end não implementado. Zero outputs |
| Monitoramento mensal | PARTIAL | Cobertura semanal (64.4%). Sem comparação temporal. Métricas comerciais NOT_READY |
| Análise de edital | NOT_READY | Zero implementação. Apenas descrição comercial no PRD |
| Apoio à proposta | NOT_READY | build-proposta-data.py existe (esqueleto). Sem checklist, matriz ou tracking |
| Acompanhamento contratual | NOT_READY | Zero implementação. Sem ledger da Extra. PRD declara "fora de escopo" |
| Win rate da Extra | NOT_READY | Win/loss tracker vazio. Sem registro de propostas ou resultados |

---

## 2. Baseline de Dados

### PostgreSQL (b2g-fresh-db, porta 54398)

| Métrica | Valor |
|---------|-------|
| Banco ativo | pndb (vazio, sem schema) |
| Tabelas de aplicação | 0 |

### SQLite (data/contract_intel.db)

| Métrica | Valor |
|---------|-------|
| target_universe | 1093 entidades |
| pncp_supplier_contracts | 0 contratos |

### PNCP API (live)

| Métrica | Valor |
|---------|-------|
| Contratos em 2026-07-14 | 6735 (Brasil todo) |
| Backfill 3 anos | ~1800 chamadas API estimadas |

---

## 3. Golden Paths

### Golden Path A — Editais e Oportunidades: READY (parcial)

- PNCP crawling funcional
- Ranking determinístico GO/REVIEW/NO_GO
- Scoring dual-axis (data_confidence + client_fit)
- Briefing sem filtro AEC/200km ⚠️
- Sem geração de dossiê por edital ⚠️

### Golden Path B — Contratos Históricos: NOT_READY

- Crawler implementado com checkpoint/resume
- PNCP API endpoints reais verificados
- 0 contratos ingeridos
- Column name mismatch crawler↔SQLite
- Migration 026 views com nomes de colunas antigos

### Golden Path C — Verdade da Extra: NOT_READY

- Sem ledger de contratos próprios
- Sem registro de propostas
- Win/loss tracker vazio
- Victory profile sem dados de treino

---

## 4. Estado AIOX (pós-correção)

| Story | Estado State | Estado MD | QA | PO | Consistente? |
|-------|-------------|-----------|-----|-----|-------------|
| B2G-FIX-01 | Done | Done | PASS | Closed | ✅ |
| B2G-FIX-02 | Done | ready ⚠️ | PASS | Closed | MD frontmatter desatualizado |
| B2G-FIX-03 | Done | Done | PASS | Closed | ✅ |
| B2G-FIX-04 | Done | Done | PASS | Closed | ✅ |
| QW-01 | Done | InReview ⚠️ | CONCERNS | Closed | MD desatualizado |
| 1.1 | Done | Done | CONCERNS | Closed | ✅ (corrigido) |
| 1.2 | Done | Done | CONCERNS | Closed | ✅ (corrigido) |
| 1.3 | Done | Done | CONCERNS | Closed | ✅ (corrigido) |
| 1.4 | Done | Done | CONCERNS | Closed | ✅ (corrigido) |
| 1.5 | Done | Done | PASS | Closed | ✅ |
| MAX-W1-01 | InReview | NÃO EXISTE ⚠️ | PASS | Aberto | Sem story MD |
| b2g-audit | Done | NÃO EXISTE | WAIVED | Closed | Sem story MD |

---

## 5. Governança Corrigida

| Ação | Status |
|------|--------|
| State files 1.1-1.4 status → Done | ✅ Corrigido |
| EPIC W2-W5 gates desmarcados | ✅ Corrigido |
| MAX-W1-01 sem story MD | ⚠️ Pendente |
| B2G-FIX-02 MD frontmatter → Done | ⚠️ Pendente |
| QW-01 MD QA Results → populado | ⚠️ Pendente |
| Snapshot evidence files ausentes | ⚠️ Pendente |

---

## 6. Principais Gaps por Dimensão

### Órgãos Compradores
- Sem ranking de atratividade
- Sem perfil por órgão (prazo, pagamento, risco)
- Sem buyer-level HHI
- Listagem básica em panorama.py

### Contratos Históricos
- Backfill NUNCA executado
- Schema PostgreSQL não aplicado
- Column name mismatch crawler↔SQLite
- Migration 026 bug (header vs SQL column names)

### Concorrentes
- v_supplier_winners com HHI (estrutura pronta)
- Sem dados para treinar victory profile
- Sem all-bidders (apenas vencedores)
- Sem perfil detalhado por concorrente

### Valores
- Semântica documentada corretamente
- Falso deságio: média por órgão, não item-a-item
- Sem preço unitário comparável
- Sem taxonomia AEC granular

### Cinco Frentes
1. Diagnóstico: geradores existem, pipeline ausente
2. Monitoramento: semanal (64.4%), sem mensal comparativo
3. Análise de edital: ZERO implementação
4. Apoio à proposta: esqueleto apenas
5. Acompanhamento: ZERO implementação

---

## 7. Próximos Passos (Ordem de Execução)

1. Aplicar schema PostgreSQL → setup_db.sh
2. Executar backfill de contratos PNCP (Golden Path B)
3. Implementar ranking de órgãos (Wave 2)
4. Implementar perfil de concorrentes (Wave 2)
5. Corrigir falso deságio (Wave 2)
6. Criar ledger da Extra (Golden Path C)
7. Implementar 5 frentes da consultoria (Wave 3)
8. Multi-source (Wave 4)
9. Reliability (Wave 5)
10. QA sistêmico + PO close + PR (Wave 6)

---

*Auditoria consolidada por 5 agentes paralelos + convergência.*
*Próxima etapa: aplicação de schema + backfill de contratos.*
