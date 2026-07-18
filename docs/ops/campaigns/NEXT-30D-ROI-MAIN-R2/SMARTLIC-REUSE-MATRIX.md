# SMARTLIC REUSE MATRIX — NEXT-30D-ROI-MAIN-R2

**UTC:** 2026-07-18T22:13:10Z  
**Policy revision:** 2.0.0 — **dataset SmartLic = DEFERRED_STALE_SOURCE**

## Policy (non-negotiable)

O dataset operacional do SmartLic está **stale** (meses sem crawls).  
Portanto **não** pode acelerar:

- cobertura operacional
- freshness
- editais abertos
- contratos atuais
- métricas operacionais
- gates da campanha / LOCAL_READY

| Atributo | Valor |
|----------|-------|
| Class | `DEFERRED_STALE_SOURCE` |
| Bloqueante | **Não** |
| Caminho crítico | **Fora** |
| Ranking Extra-ROI | **Removido** |
| Export DB SmartLic | **Não solicitar / não aguardar** |
| Novos ciclos de integração de dados | **Proibidos** |

### Código existente

| Artefato | Política |
|----------|----------|
| `scripts/integrations/smartlic_snapshot_import.py` | **Manter** — ativo opcional já testado; **sem expansão** |
| `tests/fixtures/smartlic/*` + unit tests | **OK** — só transformação/idempotência/schema |
| Import de snapshot real / DSN SmartLic | **Não no caminho crítico** |

### Ainda permitido (sem freshness)

- Corpus rotulado offline (classificador)
- Padrões de resiliência / paginação (PATTERN_ONLY)
- Estruturas de relatório (sem dados SmartLic)

### Proibido atrasar

Coleta própria Extra, incremental próprio, validação live Extra.

## Classificação de ativos

| ID | Asset | Class | Action |
|----|-------|-------|--------|
| SL-A01 | contracts_crawler | EXTRA_VERSION_SUPERIOR | Do not port |
| SL-A02 | checkpoint | PATTERN_ONLY | Optional pattern |
| SL-A03 | snapshot tables / dataset | **DEFERRED_STALE_SOURCE** | **Defer — no import** |
| SL-A04 | PNCP fixtures | PORT_FIXTURE | Fixture-only tests |
| SL-A05 | classification corpus | PORT_FIXTURE | Offline corpus optional |
| SL-A06 | frontend/billing | REJECT_COMPLEXITY | Reject |
| SL-A07 | Redis/ARQ/SaaS | INCOMPATIBLE | Reject |
| SL-A08 | high-volume pagination | PATTERN_ONLY | Optional |
| SL-A09 | report helpers | PATTERN_ONLY | Extra superior |
| SL-A10 | schema origin | ALREADY_PRESENT | None |

## Extra-ROI ranking (pós-deferral)

1. **N06c** — expansão real coleta/cobertura por entidade (só Extra)
2. **N01** — golden path live sem timeout
3. **N09** — amostra estratificada + recall real
4. **N07/N18** — histórico de contratos próprio
5. **N14** — revalidação residual DoD
6. **N15** — auditoria cética + encerramento
7. Outputs operacionais só com dados atuais defensáveis
