# Max Coverage Consolidated — 2026-07-15

**Orquestrador:** AIOX Master (Orion)
**Branch:** `epic-coverage-max-200km`
**HEAD:** `7616950`
**Fontes:** 8 agentes paralelos (A-H) + validação direta no banco

---

## Resumo Executivo

O sistema tem **recall real de 6.1%** (67/1093 entes com dados de oportunidades no banco),
muito abaixo do target declarado de 95%. A única fonte produzindo dados operacionais é o
PNCP. Das 10 fontes não-PNCP, 2 estão quebradas (Transparência), 1 está stale (DOE-SC
Selenium), e as demais carecem de evidência de execução recente.

**O sistema entrega valor hoje?** Sim — 298 oportunidades identificadas, 201 abertas,
com ranking e CLI funcional. Mas o recall é insuficiente para uso consultivo confiável.

**Prontidão para VPS:** `NO_GO`. Infraestrutura documentada é sólida (systemd, backup,
provisionamento), mas não foi validada em VPS real, o banco Docker local tem apenas 16
migrations de 42 aplicadas, e não há smoke test reproduzível.

---

## 1. Estado Atual — Métricas Decisivas

| Métrica | Valor | Fonte |
|---------|-------|-------|
| Entes no raio 200km | **1.093** | Agente B + validação haversine |
| Municípios únicos no raio | **95** | Agente B |
| Entes COM dados de oportunidade | **67** (6.1%) | DB direto (CNPJ match) |
| Entes SEM dados | **1.026** (93.9%) | DB direto |
| Oportunidades no banco | **298** (201 abertas) | DB direto |
| Fontes com dados operacionais | **1** (PNCP) | DB direto |
| Fontes implementadas | **10** (3 ativas, 2 quebradas) | Agente D |
| Contratos no banco | **0** | DB direto |
| entity_coverage populada | **Não** (tabela vazia) | DB direto |
| Migrations aplicadas | **16/42** (parcial) | DB direto |

### Recall por tipo de entidade

| Tipo | Total | Com dados | Recall |
|------|-------|-----------|--------|
| Município (prefeitura) | 95 | 35 | **36.8%** |
| Órgão Executivo Estadual | 99 | 6 | 6.1% |
| Órgão Executivo Federal | 44 | 3 | 6.8% |
| Autarquia Federal | 57 | 3 | 5.3% |
| Órgão Legislativo Municipal | 98 | 2 | 2.0% |
| Fundo Público Estadual | 61 | 2 | 3.3% |
| Órgão Executivo Municipal | 179 | 0 | **0.0%** |
| Judiciário Estadual | 78 | 0 | **0.0%** |
| Autarquia Municipal | 61 | 0 | **0.0%** |
| Consórcio Público | 37 | 0 | **0.0%** |

### Status das fontes

| Fonte | Status | Método | Dados no banco? | Cobertura declarada |
|-------|--------|--------|-----------------|-------------------|
| PNCP | ACTIVE | API REST | Sim (298 ops) | 100% nominal |
| DOM-SC | ACTIVE | API REST (auth) | Não confirmado | ~280 municípios |
| PCP | ACTIVE | API REST | Não confirmado | ~100+ municípios |
| ComprasGov | ACTIVE | API REST v3 | Não confirmado | Órgãos federais SC |
| TCE-SC | ACTIVE | API JSON | Não confirmado | Apenas TCE-SC |
| SC Compras | ACTIVE | API REST | Não confirmado | Estado SC |
| DOE-SC API | ACTIVE | API REST (auth) | Não confirmado | 513 entes estaduais |
| DOE-SC Selenium | STALE | Selenium | Não | Fallback |
| Transparência | BROKEN | HTML+Selenium | Não | 64/295 municípios |
| CIGA CKAN | ACTIVE | CKAN API | Não | Dataset até Dez/2025 |

---

## 2. QA Adversarial — Casos Críticos

4 dos 16 casos adversariais testados são **ALTO risco** (Agente H):

| Caso | Risco | Descrição |
|------|-------|-----------|
| (b) Mudança de data de abertura | ALTO | Duas implementações de hash conflitantes — transformer NÃO inclui datas |
| (d) Formatação de número de edital | ALTO | "001/2024" ≠ "1/2024" — sem normalização |
| (h) Fontes bloqueadas (SOURCE_BLOCKERS) | ALTO | 6 crawlers bloqueados por Selenium/CAPTCHA/credenciais |
| (l) Paginação prematuramente interrompida | ALTO | Confia em `paginasRestantes` sem validação cruzada |

Outros 9 casos são MÉDIO risco e 2 BAIXO. Ver `docs/audits/adversarial-coverage-qa-2026-07.md` para análise completa.

---

## 3. Dez Maiores Causas de Perda de Oportunidades

| # | Causa | Entes afetados | Impacto | Evidência |
|---|-------|---------------|---------|-----------|
| 1 | **Secretarias publicam no CNPJ da prefeitura** | 179 executivos municipais | 0% recall — matching falha porque CNPJ da secretaria ≠ CNPJ que publica | DB: 0/179 secretarias com dados |
| 2 | **Transparência quebrado** (78% sem detecção) | 231 municípios | Portais municipais não coletados | Agente D: apenas 64/295 portais detectados |
| 3 | **Sem crawler para Judiciário Estadual** | 78 entes | 0% recall — publicam no DJE/SC, não no PNCP | DB: 0/78 com dados |
| 4 | **ARP/PCA com paginação truncada** | Todos SC | Max 500 registros de ~15k/ano | Agente C: max_pages=10 |
| 5 | **entity_coverage não populada** | Todos 1093 | Sistema não sabe quem está coberto | DB: entity_coverage = 0 rows |
| 6 | **Contratos zerados** | Todos 1093 | Análise de concorrência e preços impossível | DB: pncp_supplier_contracts = 0 rows |
| 7 | **TCE-SC cobre apenas TCE-SC** | ~100 municípios | crawl_by_municipio() existe mas nunca testada | Agente D: p285 fixo |
| 8 | **Sem matching cross-source** | Todos | Mesmo edital no PNCP + portal = 2 registros | Agente G: sem dedup cross-source |
| 9 | **DOE-SC sem execução comprovada** | 513 entes estaduais | API requer auth (login+senha), sem evidência de coleta | Agente D |
| 10 | **604 entes sem coordenadas** | Fora do raio | Potencialmente excluídos incorretamente | Agente B: 604 "N/D" |

---

## 3. Violações de Protocolo AIOX

| Violação | Story | Severidade | Correção necessária |
|----------|-------|-----------|-------------------|
| `publication_authorized=true` com `reviewed_commit=null` | qw-01 | **CRITICAL** | Setar reviewed_commit ou reverter pub_auth |
| Story Done com gates PENDING | story-1.4 | HIGH | Executar lint+tests ou rebaixar status |
| MD status InReview ≠ State Done | qw-01 | HIGH | Sincronizar |
| Stories Done com lint FAIL | 1.1, 1.2, 1.3 | MEDIUM | Corrigir lint ou documentar waiver |
| 3 stories sem markdown | GP-01, MAX-W1-01, FULL-SPECTRUM-W0 | MEDIUM | Criar story MD ou consolidar |

---

## 4. Matriz de Prontidão VPS

**Classificação: `NO_GO`**

| Área | Veredito | Evidência |
|------|----------|-----------|
| Docker Compose | PASS | docker-compose.yml funcional |
| PostgreSQL persistente | PASS | Volume pgdata, healthcheck |
| Migrations fresh-install | **FAIL** | Apenas 16/42 migrations aplicadas |
| Seeds idempotentes | PASS | db/seed/001_sc_entities.py |
| Systemd services | PASS | 21 services, 20 timers |
| Systemd timers | PASS | UTC com RandomizedDelaySec |
| Browser headless | CONCERNS | Selenium + Playwright coexistem, sem smoke test |
| Backup | PASS | pg_dump → sshfs → Storage Box |
| Restore | **UNKNOWN** | Nunca testado |
| Health checks | PASS | extra-health-check.timer (30min) |
| Alertas | PASS | extra-check-alerts.timer (15min) |
| CI gates | PASS | 6 jobs fail-closed |
| Segurança (secrets) | PASS | .env.example, sem hardcoded secrets |
| Firewall | PASS | UFW configurado no provision |
| Usuário não-root | PASS | extra-consultoria user |
| Timezone | PASS | UTC explícito |
| Rollback | **FAIL** | Apenas 1/42 migrations com rollback |
| CD | **UNKNOWN** | Deploy manual via SSH |
| Smoke test | **FAIL** | Nunca executado |

**Condições para GO:**
1. Fresh install completo (42 migrations) em ambiente limpo
2. Crawl mínimo (PNCP 7 dias) com sucesso
3. Briefing gerado com dados reais
4. Reconciliação contra planilha executada
5. Backup + restore testados
6. Browser headless validado (Selenium ou Playwright)
7. Health check após reboot

---

## 5. Arquitetura de Aquisição — Gaps Críticos

| Gap | Descrição | Impacto |
|-----|-----------|---------|
| GAP-1 | 3 paradigmas de crawler coexistem | Novo crawler sem caminho claro |
| GAP-2 | Sem raw zone para fontes não-PNCP | Dados brutos perdidos, sem re-processamento |
| GAP-3 | Sem dedup cross-source | Duplicação PNCP + portal |
| GAP-4 | Checkpoints por data, não por página | Crawl que falha recomeça da página 1 |
| GAP-5 | Stubs retornam default (não levantam erro) | Comportamento silenciosamente incorreto |
| GAP-6 | Circuit breaker é stub (is_degraded=False fixo) | Sem proteção contra API lenta/indisponível |
| GAP-7 | entity_coverage não populada | Sistema não sabe quem está coberto |

---

## 6. Plano de Ondas

### Onda 1 — Instrumentação (JÁ INICIADA)
- [x] Auditoria de cobertura (8 agentes)
- [x] Universo canônico confirmado (1093 entes)
- [x] Reconciliação golden dataset (recall 6.1%)
- [ ] Comando `coverage audit` unificado
- [ ] Métricas de recall automatizadas
- [ ] Detecção de zero anômalo
- [ ] Exit code ≠ 0 quando gate crítico falhar

### Onda 2 — Correções de Alto Retorno
- [ ] CM-06: Popular entity_coverage (corrigir pipeline)
- [ ] CM-02: Importador da planilha de alvos com reconciliação automática
- [ ] CM-13: Matching CNPJ secretaria → prefeitura (hierarquia de entes)
- [ ] CM-05: Detecção de zero anômalo e paginação truncada
- [ ] CM-06b: Crawler de contratos PNCP (backfill 3 anos)

### Onda 3 — Expansão de Fontes
- [ ] CM-09: Framework parametrizado para famílias de portais
- [ ] CM-10: Reparo do Transparência (78% → 90% detecção)
- [ ] CM-08: Expansão TCE-SC para municípios
- [ ] CM-07: Validação DOM-SC com execução real

### Onda 4 — Produção VPS
- [ ] CM-15: Fresh install idempotente
- [ ] CM-18: Backup + restore testados
- [ ] CM-20: Go-live gate e smoke test

---

## 7. Próximos Passos Imediatos

1. **Gerar epic e stories** (CM-01 a CM-20) com dependências e Asymmetric Score
2. **Corrigir violações de protocolo** (qw-01 reviewed_commit, story-1.4 gates)
3. **Popular entity_coverage** (roda pipeline de cobertura contra DB)
4. **Implementar crawling de contratos** (backfill SC)
5. **Corrigir matching de secretarias** (CNPJ raiz → CNPJ prefeitura)

---

## 8. Baseline de Arquivos

| Categoria | Contagem |
|-----------|----------|
| Scripts Python | 185 |
| Testes | 72 (em 61 arquivos) |
| Proporção testes/código | ~28% (cobertura 5.8% em linhas) |
| Migrations SQL | 42 |
| State files AIOX | 13 |
| Stories markdown | 10 ativas |
| ADRs | 3 |
| Docs markdown | ~199 |
| Fontes de dados implementadas | 10 (1 produzindo dados) |

---

*Relatório consolidado gerado por AIOX Master. Dados validados contra o banco PostgreSQL local em 2026-07-15.*
