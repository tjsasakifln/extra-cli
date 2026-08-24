# Story #469: Descoberta de contato em escala no feed autoritativo CONFENGE

## Status

**Ready for Review**

## Executor Assignment

executor: "@dev"
quality_gate: "@architect"
quality_gate_tools: ["pytest", "ruff", "dod_controller", "coderabbit"]

## Story

**Como** fundador da CONFENGE responsável pela aprovação humana do outbound,
**quero** que a descoberta pública de contato processe em escala o universo de engenharia e construção e que os contatos defensáveis sejam incorporados ao `confenge.outreach.v1` autoritativo,
**para que** Comercial → Rascunhos receba volume real para revisão sem afrouxar target-fit, autorizar envio ou depender do arquivo isolado de 72 leads.

## Contexto e vínculo normativo

- Origem priorizada: [extra-cli #469](https://github.com/tjsasakifln/extra-cli/issues/469), P0, irmã de #468 (frescor).
- Fatos de produção medidos em 2026-08-24 são o baseline imutável fornecido pelo fundador e não devem ser re-derivados: 402.012 contas, 8.245 `TARGET_CONFIRMED`, 7.890 sem contato, 177 com contato utilizável, 110 prontas hoje; feed do universo com 401.923 leads e zero contatos; `email_send_ready_feed.json` com 72 leads. Esse baseline ancora o before/after, mas não congela nem limita o denominador live: o run processa a população canônica corrente inteira e registra sua própria contagem/hash/`as_of`/modo/SHAs de classificação.
- Itens finais do DOD cobertos por esta story: executar busca contextual bounded para contas A1/A2 com terminal honesto; e fazer a projeção consumer-agnostic chegar ao Warmbly sem segunda verdade ou autorização de envio. [Fonte: `DOD.md`, seção “Contact resolution público e defensável”]
- #468 é dependência operacional para frescor e cadência, mas não pertence ao raio de implementação desta story. Um contato incorporado não pode vencer o gate de target-fit stale. [Fonte: `docs/architecture/adr/ADR-035-confenge-authoritative-target-fit-feed.md#decision`]

## Acceptance Criteria

1. Existe um comando CLI reproduzível que seleciona do PostgreSQL canônico todas as empresas `TARGET_CONFIRMED`, com CNPJ de estabelecimento observado e sem hard cap comercial, registra a classe setorial sem usá-la para truncar a verdade de reachability e as enfileira na infraestrutura durável de `CONFENGE_CONTACT_DISCOVERY`. `CONSTRUCTION_CONFIRMED`/`CONSTRUCTION_PROBABLE` continua sendo gate independente do feed/send-ready, e o enriquecimento setorial contínuo mais amplo permanece independente de target-fit.
2. A seleção/enqueue registra denominador, classes setoriais e target-fit, versão de input/política, backend, budget e hash/versão reproduzível. Reexecução idêntica é idempotente e resume trabalho; `--limit` permanece somente smoke/diagnóstico e não pode produzir claim full-scale.
3. A execução reutiliza `contact_discovery_jobs` e o worker com lease, heartbeat, `FOR UPDATE SKIP LOCKED`, retry/backoff, circuit breaker, limites por backend/domínio e kill switch existentes. Nenhuma nova fila concorrente é criada.
4. Cada conta da população `TARGET_CONFIRMED` canônica corrente, sem hard cap, é efetivamente executada pelo waterfall e termina explicitamente em `EMAIL_ROUTE_READY`, `NO_PUBLIC_EMAIL_FOUND` ou `BLOCKED_WITH_REASON`; “sem contato porque nunca executou” não é terminal. O relatório também reconcilia o baseline de 8.245, classificando nominalmente eventual conta que deixou a população corrente, sem omitir novas contas. Para `EMAIL_ROUTE_READY`, o job persiste projeção consumer-agnostic apta a compor `contacts[]`, mantendo pessoa, cargo/departamento, rota, derivação, verificação, suitability, freshness e provenance separados.
5. O pipeline autoritativo compõe contatos duráveis já descobertos com os contatos resolvidos no hot set atual, por CNPJ canônico e política/input vigentes, e escreve essa união em `05_bridge_inputs/contacts.jsonl` antes de gerar os chunks do universo. O mesmo contato não gera duplicidade; resultado mais novo não pode substituir silenciosamente evidência de política incompatível.
6. Os chunks `confenge.outreach.v1` do universo passam a carregar `contacts[]` para todas as contas com contato defensável disponível; contas sem resultado continuam explicitamente com lista vazia. O arquivo isolado de send-ready não é usado como fonte de verdade do feed do universo.
7. `email_send_ready` continua fail-closed e só pode ser verdadeiro quando todos os gates atuais passam, inclusive `construction_universe_member=true`, target-fit `TARGET_CONFIRMED` fresco, DNC/supressão, associação pública mailbox↔empresa, provenance e política de contato. A ausência de pessoa/cargo nominal não bloqueia `ROLE_OR_DEPARTMENT`, `GENERIC_COMPANY` ou `PUBLIC_COMPANY_FREEMAIL` publicamente associados à empresa; essas rotas não são promovidas a `EMAIL_VALIDATED` de pessoa. `PROBABILISTIC_OR_RISKY` permanece fora do piloto default.
8. Manifesto/relatório do ciclo expõe, no denominador correto, pelo menos: `population_count`, `population_hash`, `population_as_of`, modo e SHAs dos classificadores, jobs por estado, equação população = jobs = contas terminais, contas tentadas, contas com algum contato, contas com e-mail, contas com contato utilizável, contas incorporadas ao feed, pendentes, bloqueadas/DLQ e distribuição de reason codes. Fixture valida lógica, não prova escala live.
9. Testes adversariais cobrem seleção integral sem truncamento, prioridade A1/A2, idempotência, projeção de job para contato, merge entre snapshot durável e hot set, conflito de política/input, deduplicação, ausência de contato, stale target-fit e DNC. As suítes focadas e a regressão canônica passam sem `skip`/`xfail` ou mocks irreais.
10. Evidência live da story fecha 100% da população `TARGET_CONFIRMED` corrente versionada nas três condições terminais e reconcilia separadamente 8.245/8.245 contas do baseline, sem usar o número antigo para truncar o run nem omitir candidatos novos. Registra o yield legitimamente obtido sem impor porcentagem arbitrária e publica hashes, timestamps, parâmetros, distribuição por route class/provenance/reason code e amostra auditável protegida fora do Git. Amostra de 30/100/1.000 valida a onda; não fecha este AC.
11. Segurança operacional é preservada e reconfirmada: `CONFENGE_AUTO_SEND_ENABLED=false`, kill switch de envio pausado, `confenge_dispatch_control.paused=true`, zero envios e zero aprovações automáticas. Esta story não altera `min_wait_time=600s`, `confenge.composer.v6`, o fluxo Comercial → Rascunhos nem o Warmbly.
12. Runbook, ADR/handoff e DOD recebem os deltas/evidências cabíveis. O item só pode virar `ACCEPTED` no `main`, com CI verde e o teste específico passando; somente então qualquer checkbox correspondente do `DOD.md` pode ser marcado.
13. O waterfall determinístico/incremental reutiliza, nesta ordem aproximada conforme yield medido: contatos canônicos/históricos já existentes; dados públicos cadastrais ligados por CNPJ; website/domínio oficial; documentos e fontes B2G já coletados; busca pública adicional bounded. Não contorna login/CAPTCHA/paywall/robots, não depende de provider pago e não promove mailbox inferida por padrão a fato.
14. Por account, uma única `preferred email route` é selecionada na ordem default `DIRECT_PERSON` → `ROLE_OR_DEPARTMENT` → `GENERIC_COMPANY` → `PUBLIC_COMPANY_FREEMAIL`; alternativas permanecem armazenadas/rankeadas e não são usadas simultaneamente no primeiro toque. Bounce definitivo pode liberar a próxima rota somente pela policy do Warmbly.

## 🤖 CodeRabbit Integration

### Story Type Analysis

**Primary Type:** Integration
**Secondary Type(s):** Database, Deployment
**Complexity:** High — compõe seleção PostgreSQL, fila durável, projeção de dados, export autoritativo e operação live em escala.

### Specialized Agent Assignment

**Primary Agents:**

- @dev (implementação e pre-commit)
- @data-engineer (revisão das consultas/índices, se houver delta de schema)

**Supporting Agents:**

- @qa (veredito independente e evidência live)
- @devops (systemd/deploy, PR e operação remota)

### Quality Gate Tasks

- [ ] Pre-Commit (@dev): `~/.local/bin/coderabbit --prompt-only -t uncommitted` antes de concluir a story.
- [ ] Pre-PR (@devops): policies de artefatos/reviewability e review sobre o diff exato.
- [ ] Pre-Deployment (@devops): CI verde no HEAD, configuração, rollback e postura de envio pausado.

### Self-Healing Configuration

**Expected Self-Healing:**

- Primary Agent: @dev (light mode)
- Max Iterations: 2
- Timeout: 15 minutes
- Severity Filter: CRITICAL only

**Predicted Behavior:**

- CRITICAL: corrigir até duas iterações e interromper se persistir.
- HIGH: documentar para revisão; não ocultar nem reduzir gate.

### CodeRabbit Focus Areas

**Primary Focus:**

- Compatibilidade do contrato `confenge.outreach.v1`, deduplicação e provenance fail-closed.
- Concorrência/idempotência das consultas e composição de snapshots sem segunda verdade.

**Secondary Focus:**

- Nenhum segredo ou PII em Git; artefatos pesados permanecem fora do repositório.
- Nenhum caminho de auto-send/aprovação e nenhuma regressão de target-fit stale/DNC.

## Tasks / Subtasks

- [x] Task 1 — Materializar a seleção canônica e o enqueue full-scale (AC: 1, 2, 3)
  - [x] Reusar `load_construction_jobs_from_dsn` e a identidade de estabelecimento observada; não sintetizar CNPJ.
  - [x] Adicionar ao CLI batch uma origem DSN explícita que preserve prioridade e metadados setorial/target-fit.
  - [x] Garantir denominador/checksum/idempotência e separar `--limit` smoke do modo full-scale.
  - [x] Escrever testes unitários e real-DB para cardinalidade, prioridade, reexecução e ausência de CNPJ observado.
- [x] Task 2 — Executar o waterfall e projetar resultados duráveis (AC: 4, 13, 14)
  - [x] Reconciliar primeiro contatos já existentes por CNPJ e preservar source version/freshness/provenance.
  - [x] Reusar os adapters atuais para fontes cadastrais, website, documentos B2G e busca pública bounded; adicionar apenas lacunas provadas.
  - [x] Produzir projeção `contacts[]` a partir do resultado real de `run_account`, usando as classificações existentes.
  - [x] Persistir hash, política/input, provenance e reason codes sem promover inferência.
  - [x] Fechar cada conta em `EMAIL_ROUTE_READY`, `NO_PUBLIC_EMAIL_FOUND` ou `BLOCKED_WITH_REASON`, cobrindo retryable/DLQ e conflito de versão.
- [x] Task 3 — Compor os contatos no feed do universo (AC: 5, 6, 7)
  - [x] Ler somente projeções válidas/vigentes e uni-las aos contatos do hot set por CNPJ canônico.
  - [x] Definir precedência/deduplicação determinística e falhar fechado em incompatibilidade.
  - [x] Alimentar `ExportConfig.contacts` com a união e provar contato dentro dos chunks autoritativos.
  - [x] Preservar todos os gates atuais de `email_send_ready`, target-fit freshness, DNC e membership setorial.
- [ ] Task 4 — Fechar métricas, operação e regressões (AC: 8, 9, 11)
  - [ ] Publicar funil/estados/reason codes no manifesto leve e no relatório operacional.
  - [ ] Atualizar o runbook de batch e unidade systemd somente no raio necessário.
  - [ ] Executar testes focados, Ruff, source contracts, full suite e golden path conforme aplicável.
  - [ ] Reconfirmar zero sends/approvals e controles pausados; não tocar composer/cohort/min_wait_time.
- [ ] Task 5 — Produzir prova live e handoff (AC: 10, 12)
  - [ ] Executar a seleção/enqueue/worker no host autorizado com budget explícito e fechar o denominador corrente versionado (`population_count`/hash/`as_of`/modo/SHAs), reconciliando também o baseline de 8.245.
  - [ ] Publicar feed novo apenas se os gates autoritativos passarem; armazenar PII/evidência pesada fora do Git.
  - [ ] Demonstrar milhares de contatos utilizáveis no denominador corrente e no recorte do baseline, ou registrar blocker live honesto.
  - [ ] Atualizar ADR/handoff/DOD e submeter aceitação independente no harness.

## Dev Notes

### Architecture and contracts

- O artefato wire é snapshot completo de decisões, não seleção send-ready; inteligência/contato caro pode ser bounded, mas a decisão target-fit não. [Source: `docs/architecture/adr/ADR-035-confenge-authoritative-target-fit-feed.md#decision`]
- A dimensão setorial define `CONSTRUCTION_UNIVERSE`; target-fit e contato controlam prioridade/envio. Enriquecimento contínuo não pode ser limitado por Top-N, hot set ou reserva piloto. [Source: `docs/architecture/adr/ADR-036-confenge-universe-and-pilot-go-separation.md#decision`]
- extra-cli é a verdade de identidade/reachability; Warmbly é activation/outcome. Não existe `AUTO_SEND`. [Source: `docs/architecture/adr-decision-unit-intelligence.md#consequences`]
- O modelo mantém identidade, papel, domínio, derivação, verificação, suitability, freshness e provenance separados; busca/crawl têm budget e SSRF/robots/rate limits fail-closed. [Source: `docs/commercial-intelligence/contact-resolution.md#epistemic-and-route-model` e `#public-web-discovery`]
- O caminho de produção atual resolve contato apenas para `sample_rows`/hot set e passa `bridge_contacts_path` ao export do universo; esse é o ponto de composição a corrigir, sem reescrever o composer. [Source: `scripts/confenge_outreach_pipeline/pipeline.py`, stages 2–5]
- A infraestrutura durável já existe em `db/migrations/093_contact_discovery_batch.sql`, `scripts/decision_unit_intelligence/batch_queue.py`, `batch_worker.py`, `batch_outcomes.py` e `batch_snapshot.py`; deve ser estendida/combinada, não duplicada. [Source: `docs/ops/contact-discovery-batch.md`]
- A projeção atual `project_warmbly_outreach` e `feed_contact_from_classified` já preserva classificação de rota e `auto_send=false`; reutilizar essas regras. [Source: `scripts/decision_unit_intelligence/projection.py` e `controlled_email.py`]

### Prior work and constraints

- A story anterior de evidência humana encerrou `NO_GO_CONTACT_EVIDENCE`: 303 contas examinadas, 192 e-mails encontrados, apenas 1 cadeia humana completa. Este resultado prova que repetir o canário nominal estrito não produz escala e não autoriza relaxar provenance. [Source: `docs/handoffs/confenge-human-recipient-evidence-20260813.md#decision` e `#before-and-after`]
- `--limit-downstream` é smoke/batch-only; em produção o feed continua integral, embora inteligência/contato síncronos usem hot set. [Source: `docs/ops/confenge-outreach-pipeline.md#flags`]
- Raw chunks, PII e matrizes live ficam fora do Git; o PR leva código, testes, hashes e documentação leve. [Source: `docs/architecture/adr/ADR-035-confenge-authoritative-target-fit-feed.md#consequences`]

### Relevant source tree

- CLI/fila/worker: `scripts/decision_unit_intelligence/{cli,batch_queue,batch_worker,batch_outcomes,batch_snapshot,projection}.py`
- Seleção canônica: `scripts/confenge_contact_resolution/continuous_from_target_fit.py`
- Composição/feed: `scripts/confenge_outreach_pipeline/{cli,pipeline}.py`, `scripts/warmbly_bridge/{export,mapping}.py`
- Schema/serviço: `db/migrations/093_contact_discovery_batch.sql`, `deploy/systemd/extra-contact-discovery-worker@.service`
- Testes: `tests/test_contact_discovery_batch.py`, `tests/confenge_contact_resolution/`, `tests/confenge_outreach_pipeline/`, `tests/warmbly_bridge/`

### Project structure notes

- Os arquivos genéricos `docs/framework/{coding-standards,tech-stack,source-tree}.md` configurados no AIOX não existem neste checkout, assim como os fallbacks `docs/pt/framework/`. Esta story usa os documentos canônicos/ADRs/runbooks acima e `docs/DEVELOPMENT.md` como fonte de padrões.
- ClickUp não está conectado nesta sessão; a issue GitHub #469 e a prioridade explícita do fundador são a rastreabilidade de backlog.

## Testing

- Teste específico obrigatório: suíte nova/focada para seleção + projeção + merge do contato durável no feed.
- Regressões existentes mínimas: `tests/test_contact_discovery_batch.py`, `tests/confenge_contact_resolution/`, `tests/confenge_outreach_pipeline/`, `tests/warmbly_bridge/`.
- Gates canônicos: `python3 -m pytest tests/ -q --tb=no -x`, `ruff check .`, `python3 -m scripts.ops.source_contract_tests --json`, golden path com DSN explícito e policies de reviewability.
- Testes `real_db` seguem `REQUIRE_REAL_DB=1` e DSN explícito; ausência de banco não pode ser apresentada como sucesso. [Source: `docs/DEVELOPMENT.md#2-comandos-canônicos-setup--validação--golden-path--weekly`]
- Prova live exige timestamp/origem/identificadores/hashes/parâmetros e o denominador correto. Fixture nunca fecha o AC 10. [Source: `.specify/memory/constitution.md#v-evidence-honesty`]

## Change Log

| Date | Version | Description | Author |
|---|---|---|---|
| 2026-08-24 | 0.1.0 | Draft inicial derivado da issue #469, fatos medidos e contratos vigentes | River (@sm) |
| 2026-08-24 | 0.1.1 | Validated GO (9/10) — Status: Draft → Ready; executor/quality gate alinhados ao Projeto Bob | Pax (@po) |
| 2026-08-24 | 0.2.0 | Refinado pelo novo DoD: 8.245/8.245 terminais, route classes não nominais válidas, waterfall e anti-shotgun | River (@sm) |
| 2026-08-24 | 0.2.1 | Validated GO (10/10) — Status: Draft → Ready após refinamento executivo | Pax (@po) |
| 2026-08-24 | 0.3.0 | Implementação local: seleção canônica, terminais, projeção hash-verificada e merge no feed amplo | Dex (@dev) |

## Dev Agent Record

### Agent Model Used

GPT-5 Codex (Dex / @dev)

### Debug Log References

- 2026-08-24: 74 testes focados passaram após a primeira onda (projeção terminal + contrato auditável).
- 2026-08-24: regressão do raio de contato/feed/Warmbly `304 passed`; Ruff global e 17/17 source contracts verdes.
- 2026-08-24: mypy isolado nos seis módulos alterados passou; a execução transitiva expõe dívida legada fora do raio.
- 2026-08-24: seleção canônica validada com teste unitário e PostgreSQL real local.
- 2026-08-24: projeção durável → feed amplo validada, inclusive conta fora do hot set.
- 2026-08-24: suíte canônica `5806 passed, 235 skipped, 11 deselected`; Ruff e 17/17 source contracts verdes.
- 2026-08-24: suíte canônica final da implementação `5838 passed, 240 skipped, 11 deselected` em 510,50s; sem alteração dos gates congelados.
- 2026-08-24: CodeRabbit CLI não encontrado no host (`/home/tjsasakifln/.local/bin/coderabbit` ausente); revisão automática permanece gate de PR/CI, sem falso-verde local.

### Completion Notes List

- Implementação local cobre seleção integral, terminais honestos, projeção hash-verificada e composição no feed.
- Artefatos históricos de contatos agora entram como inputs explícitos, SHA-256-bound e verificados no primeiro degrau do worker; alteração/missing vira blocker nominal.
- O cadastro oficial local é consultado por CNPJ exato; e-mail cadastral preserva release/autoridade, não inventa pessoa e registra indisponibilidade como blocker factual de waterfall. Freemail público continua regido pela associação defensável da policy ativa.
- Evidência live do denominador corrente versionado, reconciliação 8.245/8.245 do baseline, deploy e aceitação continuam abertos; fixture não foi tratada como prova operacional.

### File List

- `docs/ops/confenge-outreach-pipeline.md`
- `docs/ops/contact-discovery-batch.md`
- `docs/stories/story-469-contact-discovery-at-scale.md`
- `scripts/confenge_contact_resolution/continuous_from_target_fit.py`
- `scripts/confenge_outreach_pipeline/cli.py`
- `scripts/confenge_outreach_pipeline/pipeline.py`
- `scripts/decision_unit_intelligence/batch_outcomes.py`
- `scripts/decision_unit_intelligence/batch_contact_metadata.py`
- `scripts/decision_unit_intelligence/batch_population.py`
- `scripts/decision_unit_intelligence/batch_projection.py`
- `scripts/decision_unit_intelligence/batch_queue.py`
- `scripts/decision_unit_intelligence/batch_worker.py`
- `scripts/decision_unit_intelligence/cli.py`
- `scripts/decision_unit_intelligence/providers/existing_contacts.py`
- `scripts/decision_unit_intelligence/providers/official_company_registry.py`
- `tests/confenge_outreach_pipeline/test_pipeline.py`
- `tests/test_contact_discovery_batch.py`
- `tests/test_contact_discovery_outcomes.py`
- `tests/test_contact_discovery_population.py`
- `tests/test_existing_contact_seed.py`

## QA Results

_A preencher por @qa; o implementador não é autoridade única de aceitação._
