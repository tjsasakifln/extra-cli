# Roadmap: Consolidação dos Módulos de Alta Confiança

> Identificador: `001-modulos-alta-confianca`
> Data: 2026-07-14
> Requirements: `_reversa_forward/001-modulos-alta-confianca/requirements.md`
> Confidência: 🟢 CONFIRMADO, 🟡 INFERIDO, 🔴 LACUNA

## 1. Resumo da abordagem

A feature consolida três módulos em uma única intervenção coordenada, seguindo a ordem de dependência natural: **(1) deploy** (orquestração local future-proof) → **(2) tests** (coverage gate fail-closed) → **(3) opportunity_intel** (snapshot reconciliation + URL enforcement + competitive intel schema validation).

A abordagem é **delta-driven**: cada módulo recebe adições mínimas e cirúrgicas, sem reescrever o que as stories 1.1→1.5 já entregaram. O `docker-compose.yml` existente (hoje só test-db) é expandido com serviço de aplicação, reutilizando a mesma imagem e rede para compatibilidade futura com VPS. O Makefile orquestra o ciclo completo com variável `ENV ?= local` para switch entre ambientes. O coverage gate é implementado como script autônomo (`coverage_gate.py`) que o CI chama após pytest. A snapshot reconciliation é injetada no pipeline QW-01 Radar como etapa pós-export, com guarda de execução parcial.

## 2. Princípios aplicados

| Princípio | Como a feature se relaciona | Status |
|-----------|------------------------------|--------|
| CLI First (AIOX Art. I) | Makefile é CLI-first: `make run-pipeline`, `make test`, `make lint` — sem GUI, sem dependência de IDE | respeita |
| Fail-Closed (ADR-014) | Coverage gate exit 2 se < 80%; snapshot reconciliation só em execução completa; CI gate unificado fail-closed | respeita |
| Evidence-Based (ADR-013) | Toda reconciliação registra evento em `coverage_evidence`; coverage gate emite JSON auditável por módulo | respeita |
| Conservative Denominator (Domain Rule) | População de módulos críticos para coverage é explícita e fixa (7 módulos), sem inferência automática | respeita |
| No Invention (AIOX Art. IV) | Toda decisão técnica ancora em artefato existente do `_reversa_sdd/` ou do plano mestre | respeita |
| KISS | Makefile usa shell commands simples, não Makefile DSL complexo; docker-compose expande o existente, não reescreve | respeita |

## 3. Decisões técnicas

| ID | Decisão | Justificativa | Alternativas descartadas | Confidência |
|----|---------|----------------|--------------------------|-------------|
| D-01 | Expandir `docker-compose.yml` existente (hoje só `test-db`) com serviço `app` usando Python 3.12, mesma rede, volumes para `output/` e `config/`. Renomear para `docker-compose.local.yml`. | Reutiliza imagem postgis já em uso; evita duplicação de definição de banco; facilita transição VPS (só muda `--env-file`) | (a) docker-compose separado para cada ambiente — duplicação; (b) Dockerfile customizado — over-engineering para fase atual | 🟢 |
| D-02 | Makefile com variável `ENV ?= local` para alternar entre ambientes. Targets: `run-pipeline`, `run-crawl`, `run-report`, `test`, `lint`, `clean`. | Padrão Makefile é universal em Python; `ENV` variável permite `make run-pipeline ENV=vps` sem modificar código | (a) Taskfile (Go) — dependência extra; (b) Just — não padrão Python; (c) Scripts shell soltos — já é o estado atual, caótico | 🟢 |
| D-03 | `bootstrap_local.sh` como script bash idempotente (não Makefile target). Steps: create DB → migrations → seed → verify fingerprint. Cada step verifica estado antes de aplicar. | Scripts de bootstrap são mais legíveis e depuráveis que targets Makefile complexos; idempotência por step com guardas | (a) Python script — mais pesado, depende de psycopg2; (b) Makefile target — difícil debugging de falha parcial | 🟢 |
| D-04 | `coverage_gate.py` lê `.coveragerc` com `[coverage_gate]` section listando 7 módulos e threshold 80%. Emite JSON `{module: {pct, pass}}` + exit code agregado. | Separação de concerns: pytest gera coverage, gate verifica thresholds. `.coveragerc` é padrão pytest, só adiciona seção customizada | (a) pytest `--cov-fail-under` global (não por módulo); (b) pytest plugin customizado — complexo, frágil com upgrades | 🟢 |
| D-05 | Snapshot reconciliation como função `reconcile_snapshot(conn, run_id, current_bid_ids)` chamada APÓS export no pipeline QW-01, com guarda `is_complete and errors == 0`. | Injeta reconciliação no ponto correto do pipeline (pós-export, pré-manifest); guarda impede falso-positivo em execução parcial | (a) Trigger no PostgreSQL — esconde lógica, difícil testar; (b) Comando CLI separado — usuário esqueceria de rodar | 🟢 |
| D-06 | `validate_competitive_intel_schema(conn)` como validação pura (read-only), sem corrigir colunas. Reporta erros, não altera schema. | Escopo decidido no `/reversa-clarify`: validação apenas. P0-09 completo é feature separada. | (a) Auto-fix de colunas — fora do escopo; (b) Mock validation — não detecta problemas reais | 🟢 |
| D-07 | `ci_gate.sh` como script bash sequencial: ruff → pyright → bandit → pytest+coverage_gate. Cada etapa emite JSON parcial. Exit code fail-closed (2) se qualquer etapa falha. | Bash é universal em CI; sequencial permite caching entre etapas; JSON por etapa facilita debugging | (a) Makefile target `ci` — ok mas bash é mais portável entre CI providers; (b) GitHub Actions — prematuro, sem deploy VPS ainda | 🟢 |

## 4. Premissas

> Nenhuma premissa. Todos os `[DÚVIDA]` foram resolvidos em `/reversa-clarify` 2026-07-14.

## 5. Delta arquitetural

| Componente | Arquivo de origem no legado | Tipo de mudança | Resumo |
|------------|------------------------------|-----------------|--------|
| Deploy (orquestração) | `_reversa_sdd/deploy/design.md#riscos-e-lacunas` | componente-novo | Makefile + docker-compose.local.yml + bootstrap_local.sh |
| Tests (coverage) | `_reversa_sdd/tests/requirements.md#requisitos-nao-funcionais` | componente-novo | coverage_gate.py com threshold 80% por módulo |
| CI Gates | `_reversa_sdd/architecture.md#ci-gates` | contrato-novo | ci_gate.sh unificado (ruff+pyright+bandit+pytest+coverage) |
| Opportunity Intel (reconciliação) | `_reversa_sdd/opportunity_intel/design.md#fluxo-principal` (step 12) | componente-novo | reconcile_snapshot() no pipeline QW-01 |
| Opportunity Intel (URL) | `_reversa_sdd/opportunity_intel/requirements.md#criterios-de-aceitacao` | regra-alterada | PRIORITARIA sem URL → downgrade REVISAR |
| Opportunity Intel (competitive intel) | `_reversa_sdd/opportunity_intel/requirements.md#lacuna-3` | componente-novo | validate_competitive_intel_schema() |

## 6. Delta no modelo de dados

- **Resumo:** Sem novas tabelas ou migrations DDL. `coverage_evidence` ganha novo `event_type` (`snapshot_reconciled`) com payload `{bids_inactivated, bids_kept}`. `opportunity_intel` table ganha constraint `official_url NOT NULL` para registros com `triage = 'PRIORITARIA'` (validado em Python, não em DDL).
- Detalhe completo em: `_reversa_forward/001-modulos-alta-confianca/data-delta.md`

## 7. Delta de contratos externos

| Contrato | Tipo | Arquivo de detalhe |
|----------|------|--------------------|
> Nenhum contrato externo novo ou alterado. Feature é inteiramente interna (orquestração, testes, pipeline).

## 8. Plano de migração

1. Criar `docker-compose.local.yml` expandindo o `docker-compose.yml` existente (serviço `app` adicional)
2. Criar `Makefile` com targets e variável `ENV`
3. Criar `scripts/bootstrap_local.sh` idempotente
4. Criar `scripts/coverage_gate.py` + seção `[coverage_gate]` em `.coveragerc`
5. Executar bootstrap → rodar pipeline completo → verificar saída
6. Rodar pytest com coverage gate → verificar relatório por módulo
7. Implementar `reconcile_snapshot()` → testar com execução PNCP completa
8. Implementar URL enforcement no ranking → verificar CSV de saída
9. Implementar `validate_competitive_intel_schema()` → verificar contra PostgreSQL real
10. Criar `scripts/ci_gate.sh` → executar sequência completa → verificar exit code

## 9. Riscos e mitigações

| Risco | Impacto | Probabilidade | Mitigação |
|-------|---------|---------------|-----------|
| `docker-compose.local.yml` conflitar com `docker-compose.yml` existente | médio | baixa | Nome distinto (`docker-compose.local.yml`); `docker-compose.yml` existente permanece inalterado para testes |
| Coverage gate 80% muito agressivo para módulos recém-criados (supplier_metrics, price_pipeline) | alto | média | Gate inicial com threshold documentado; se módulo nunca teve teste, baseline = 0% e gate falha corretamente |
| Snapshot reconciliation inativar registros incorretamente por bug no `current_bid_ids` | alto | baixa | Guarda `is_complete and errors == 0`; `--dry-run` flag que reporta sem inativar; `coverage_evidence` audit trail |
| Makefile conflitar com scripts shell existentes em `scripts/` | baixo | baixa | Makefile na raiz, scripts em `scripts/`; targets chamam scripts existentes, não reescrevem |
| Bootstrap idempotente falhar em estado parcial (migration pela metade) | médio | baixa | Cada step verifica estado antes de aplicar; migrations são transacionais (PostgreSQL DDL) |

## 10. Critério de pronto

- [ ] `make run-pipeline` executa do zero e produz PDF+Excel em `output/reports/`
- [ ] `docker compose -f docker-compose.local.yml up` sobe banco + app sem erro
- [ ] `scripts/bootstrap_local.sh` executado 2× — segunda execução é no-op
- [ ] `pytest --cov=scripts && python scripts/coverage_gate.py` → exit 0 (todos os 7 módulos ≥ 80%) ou exit 2 com relatório JSON
- [ ] `reconcile_snapshot()` executado após PNCP completo → `active_snapshot_integrity` = 100%
- [ ] Oportunidade PRIORITARIA sem `official_url` → downgrade REVISAR no CSV
- [ ] `validate_competitive_intel_schema(conn)` → `SchemaValidation` com 3 checks passando em PostgreSQL real
- [ ] `scripts/ci_gate.sh` → sequência ruff→pyright→bandit→pytest+coverage executada sem erro de script
- [ ] `cross-check.md` (se executado) sem CRITICAL nem HIGH
- [ ] `regression-watch.md` gerado
- [ ] Nenhum arquivo de protocolo AIOX ou Reversa modificado

## 11. Histórico de alterações

| Data | Alteração | Autor |
|------|-----------|-------|
| 2026-07-14 | Versão inicial gerada por `/reversa-plan` | reversa |
