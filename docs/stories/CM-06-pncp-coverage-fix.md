# CM-06 — Auditoria e Correção de Cobertura PNCP

**Epic:** EPIC-COVERAGE-MAX-200KM | **Onda:** 2 — Correções de Alto Retorno
**Risk:** HIGH-RISK | **Status:** Ready
**Asymmetric Score:** 95 | **Recall gain estimado:** +29% (6% → 35%)

---

## Problema Econômico

PNCP é a única fonte com dados operacionais (298 oportunidades), mas:
- **entity_coverage está vazia** (0 rows) — sistema não sabe quem está coberto
- **Contratos zerados** (pncp_supplier_contracts = 0) — análise de concorrência impossível
- **ARP/PCA com max_pages=10** — coleta apenas ~3.3% das atas publicadas
- **Circuit breaker é stub** (is_degraded=False fixo) — sem proteção contra API lenta
- **Checkpoints por data, não por página** — crawl que falha recomeça da página 1

O recall real é 6.1% (67/1093). A correção do pipeline PNCP + backfill de contratos
pode elevar para ~35% — o maior ganho marginal disponível.

## Hipótese

Corrigir o pipeline de entity_coverage, popular contratos com backfill de 3 anos,
aumentar max_pages de ARP/PCA e implementar circuit breaker real resolve as maiores
perdas verificáveis na fonte de maior retorno.

---

## Escopo (IN)

1. Popular `entity_coverage` executando o pipeline contra o banco atual
2. Crawler de contratos com backfill de 36 meses para SC
3. Aumentar `INGESTION_ARP_MAX_PAGES` de 10 para 100
4. Aumentar `INGESTION_PCA_MAX_PAGES` de 10 para 100
5. Implementar circuit breaker real (substituir stub)
6. Adicionar page-level checkpoint nos crawlers ARP e PCA
7. Adicionar coluna `last_crawl_at` e `last_error_at` em entity_coverage

## Fora de Escopo (OUT)

- Adicionar novas fontes além do PNCP (CM-07 a CM-12)
- Correção de matching de CNPJ (CM-13)
- Anexos e retificações (CM-12)

---

## Arquivos Prováveis

| Arquivo | Ação |
|---------|------|
| `scripts/coverage/manifest.py` | Corrigir pipeline de entity_coverage |
| `scripts/crawl/contracts_crawler.py` | Habilitar backfill 36 meses |
| `scripts/crawl/pncp_arp_crawler.py` | Aumentar max_pages, page checkpoint |
| `scripts/crawl/pncp_pca_crawler.py` | Aumentar max_pages, page checkpoint |
| `scripts/crawl/ingestion/config.py` | Atualizar constantes |
| `scripts/crawl/circuit_breaker.py` | Implementar real (substituir stub) |
| `scripts/crawl/clients/pncp/circuit_breaker.py` | Remover stub ou delegar ao real |
| `db/migrations/044_entity_coverage_health.sql` | NOVO — last_crawl_at, last_error_at |

## Dependências

- CM-03 (reconciliação golden dataset)
- CM-05 (detecção de zero anômalo)
- PostgreSQL acessível
- API PNCP acessível

---

## Critérios de Aceite

### AC-1: entity_coverage populada
**Given** banco com 298 oportunidades e 2.085 entes
**When** executo `python scripts/coverage/manifest.py`
**Then** entity_coverage tem > 0 rows e is_covered=true para entes com dados

### AC-2: Contratos com backfill
**Given** crawler de contratos configurado para SC, 36 meses
**When** executo `python scripts/crawl/monitor.py --source contracts --mode backfill`
**Then** pncp_supplier_contracts tem > 10.000 registros para SC

### AC-3: ARP sem truncamento
**Given** INGESTION_ARP_MAX_PAGES=100
**When** executo crawl de ARP para SC, 90 dias
**Then** sistema coleta até 5.000 registros (100 páginas × 50 itens) sem truncar

### AC-4: Circuit breaker funcional
**Given** API PNCP retornando 500 por 30 segundos
**When** crawler tenta fazer requests
**Then** circuit breaker abre após 5 falhas consecutivas e registra evento

### AC-5: Page-level checkpoint
**Given** crawl de ARP interrompido na página 47
**When** reexecuto o crawl
**Then** retoma da página 47 (não da página 1)

### AC-6: Métricas de cobertura atualizadas
**Given** entity_coverage populada
**When** executo `python scripts/opportunity_intel/cli.py coverage`
**Then** dashboard mostra recall por ente e fonte com dados reais

---

## Testes

1. **Unit:** Circuit breaker — abre após N falhas, half-open, fecha
2. **Unit:** Page checkpoint — salva e restaura página
3. **Integration:** entity_coverage pipeline com dados reais
4. **Integration:** crawl de contratos (1 mês, não 36) — verifica inserts
5. **Smoke:** Contrato de backfill em modo limitado (1 dia, 1 página)

## Evidências Obrigatórias

- [ ] `SELECT count(*) FROM entity_coverage WHERE is_covered = true` > 60
- [ ] `SELECT count(*) FROM pncp_supplier_contracts` > 10.000
- [ ] Circuit breaker registra evento de abertura em log
- [ ] Page checkpoint persiste e restaura entre execuções
- [ ] Nenhum truncamento silencioso detectado (log confirma páginas coletadas = páginas disponíveis)

---

## Rollback

```bash
# Reverter max_pages
git revert <commit>
# Limpar contratos e re-coletar
TRUNCATE pncp_supplier_contracts;
# Restaurar entity_coverage anterior
SELECT * FROM entity_coverage_backup;
```

## Comando de Validação

```bash
# Popular coverage
python scripts/coverage/manifest.py
python scripts/opportunity_intel/cli.py coverage  # deve mostrar recall > 6%

# Backfill contratos (SC, 1 mês para teste)
python scripts/crawl/monitor.py --source contracts --mode backfill --months 1 --uf SC
python scripts/local_datalake.py stats  # verificar contratos

# ARP sem truncamento
python scripts/crawl/monitor.py --source pncp_arp --mode incremental
# Verificar log: "Collected X/Y pages (100%)"
```

---

## Definition of Done

- [ ] entity_coverage populada (>60 entes covered)
- [ ] Contratos backfill SC (>10.000 registros)
- [ ] ARP/PCA max_pages=100, sem truncamento
- [ ] Circuit breaker real implementado e testado
- [ ] Page-level checkpoint funcional
- [ ] Testes passando
- [ ] Lint e type check OK
- [ ] State file AIOX atualizado

---

## Asymmetric Score Detalhado

```
Recall Gain:          29% (6% → 35%, +483% relativo)
Entity Importance:    8/10 (PNCP é fonte dominante, cobre todos os entes)
Opportunity Value:    7/10 (contratos + atas = alta inteligência competitiva)
Failure Probability:  9/10 (stubs, tabelas vazias, max_pages=10 — falha CERTA)
Reuse Factor:         10/10 (correções beneficiam TODAS as fontes PNCP)
Effort:               5/10 (correções cirúrgicas, sem reescrever crawlers)
Operational Risk:     3/10 (mudanças em crawlers existentes, mas isoladas)
                    ------
Asymmetric Score:    ~95
```

---

*CM-06 — AIOX Master Orion, 2026-07-15*
