# Story — CONFENGE Live Intelligence: fundação aditiva (schema + producer + verifier + gate P0)

- **ID:** `confenge-live-intelligence-01`
- **Mission:** CONFENGE-REVENUE-MULTI-ENGINE-W1
- **Risco:** HIGH-RISK (migration nova + segurança de superfície select-only + gate de equivalência outbound)
- **Base:** `review/universe-parafiscal-clean`
- **Status:** Done
- **Executor:** @dev (implementação) — **@data-engineer obrigatório** para a migration (LI-2, ver `agent-authority.md`)
- **Quality Gate:** @architect (arquitetura/aditividade) + @qa (independente)
- **Fontes normativas:**
  - `docs/architecture/confenge-live-intelligence-impact-analysis.md` — as 8 decisões fechadas (@architect). **Documento normativo desta story.**
  - `docs/architecture/confenge-live-intelligence-schema-draft.sql` — draft do @data-engineer. **NÃO é a especificação.** Ver §"Divergências do draft SQL" abaixo — é insumo de padrão de engenharia (state machine, RPCs, guarda de imutabilidade), não de contrato de dados.

---

## Story

**As a** engenharia de receita da Extra Consultoria,
**I want** um motor inbound aditivo (`CONFENGE_LIVE_INTELLIGENCE/1.0`) que observa oportunidades públicas abertas e as relaciona a empresas com execução pública observável, publicando um snapshot canônico versionado (schema + producer + verifier),
**so that** exista um handoff read-only, replayable e fail-closed para personalização de outbound em uma wave futura, **sem alterar em uma única linha o comportamento, o schema ou a saída do pipeline outbound existente**.

---

## Problema

O motor outbound (target-fit, sector, contracts) hoje decide *quem recebe contato*. Não existe hoje nenhum motor que observe *o que está aberto no mundo* (oportunidades PNCP) e o relacione, de forma explicável e sem score mágico, ao portfólio observado de uma empresa. A ausência desse motor bloqueia qualquer personalização de outbound baseada em oportunidade real. Construir isso **dentro** do motor outbound acopla dois sistemas com ciclos de mudança e donos diferentes — daí a decisão arquitetural de um motor novo, estritamente aditivo.

## Causa raiz

Não há causa raiz de bug — é ausência de capacidade. A causa raiz do *risco* de implementação é que o caminho óbvio (reusar `evidence_hash()`, escrever em `confenge_target_fit_dirty`, usar `v_open_opportunities_canonical`, usar score numérico de fit) quebraria isolamento com o outbound de 4 formas distintas, todas endereçadas pelas 8 decisões do `impact-analysis.md`.

## Valor

Entrega a fundação (schema + producer + verifier) de um handoff `READY_CANONICAL`/`PARTIAL`/`BLOCKED` consumível, com gate de equivalência byte-idêntica provando que o outbound continua intocado — pré-requisito para qualquer wave de personalização de outbound baseada em oportunidade.

---

## Escopo IN

Implementa os incrementos **LI-1 a LI-6** do `impact-analysis.md` (§5), mais o núcleo do verifier e o gate P0:

1. **LI-1 — Fundação de schema Python.** `scripts/confenge_live_intelligence/{__init__,schema}.py`. `ENGINE_ID`, `ENGINE_VERSION`, `SCHEMA_VERSION`, `live_hash()` (canonical-JSON + SHA256, Decisão 2), dataclasses frozen de OPPORTUNITY / COMPANY / COMPANY_OPPORTUNITY_FIT (Decisão 3), enums tri-estado (Decisão 4).
2. **LI-2 — Migration 104 aditiva + barreira de segurança.** `db/migrations/104_confenge_live_intelligence_v1.sql`. 6 tabelas novas + `live_open_opportunities_as_of(DATE)`, com a barreira select-only feita **exclusivamente por REVOKE explícito por objeto** — 14 REVOKEs cobrindo as 6 tabelas e a função as-of, para `PUBLIC` e `smartlic_public_reader` (Decisão 8, §8.2–§8.4). **A 104 não emite nenhum `ALTER DEFAULT PRIVILEGES`**: a §9 original foi removida pelo @data-engineer em 2026-09-02 após ser medida inerte no PG16 (TD-LI-2, ADR-040 Achado 2). **Owner: @data-engineer.**
3. **LI-3 — Leitores as-of read-only.** `scripts/confenge_live_intelligence/sources.py`, sobre `pncp_raw_bids` (Decisão 6), fixando `TimeZone` de sessão explicitamente (§8.4).
4. **LI-4 — Accessor único de data de contrato.** `scripts/confenge_live_intelligence/contract_date_resolver.py`, sobre `QUALIFYING_DATE_PRECEDENCE` (Decisão 7, §7.3), com `date_resolver_version = "ca-v2-precedence/1.0"`.
5. **LI-5 — FIT tri-estado.** `scripts/confenge_live_intelligence/fit.py`. 5 dimensões `MATCH/NO_MATCH/UNKNOWN` (Decisão 4), sem score numérico, ordenação lexicográfica.
6. **LI-6 — Producer e barreira de snapshot.** `scripts/confenge_live_intelligence/producer.py`. `BUILDING → READY_CANONICAL | PARTIAL | BLOCKED` (Decisão 7, critério de completude por linha).
7. **Verifier (núcleo).** `scripts/confenge_live_intelligence/verifier.py` — re-deriva hashes, falha fechado em qualquer divergência. `explain-fit`/`replay` completos ficam para a story 2 (ver OUT); o núcleo mínimo de verificação de hash **entra** aqui porque LI-9 depende dele.
8. **LI-9 — Gate P0 de não-interferência outbound** (escopo conforme AC2 reescopado, v1.6 — a equivalência byte-idêntica sob execução real migrou para o follow-up bloqueante). `tests/test_live_intelligence_outbound_equivalence.py` + teste estático da migration (nenhum `ALTER`/`DROP`/`CREATE OR REPLACE` sobre objetos outbound listados em §8.2).
9. **Teste de zero-PII/contato** no verifier: key-set do payload emitido é subconjunto do schema declarado (whitelist, não blacklist — ver divergência #5 abaixo).
10. **CLI mínimo:** `build` e `verify` apenas (não `replay`, não `explain-fit`).

## Escopo OUT (não faz parte desta story — fica para story 2)

- **LI-7 — Eventos idempotentes** (os 5 tipos: `NEW_OPPORTUNITY`, `OPPORTUNITY_CHANGED`, `DEADLINE_CHANGED`, `FIT_BECAME_RELEVANT`, `COMPANY_PORTFOLIO_CHANGED`), incluindo `confenge_live_intelligence_events` como tabela **populada** (a tabela pode nascer vazia na migration 104, mas nenhum código desta story escreve nela).
- **LI-8 completo** — CLI `replay` e `explain-fit`.
- Qualquer integração com `message_spine.py` ou personalização de outbound.
- Qualquer trigger/poll worker de produção (cron, systemd unit) para rodar o producer periodicamente — esta story entrega o motor invocável via CLI/teste, não a operacionalização contínua.
- Troca do `contract_date_resolver` para `contract_contracting_date_v1()` do PR #531 (fica documentada como ponto de troca de uma função; não é implementada porque #531 não está mergeado).
- Schema dedicado `live_intelligence_v1` (avaliado e rejeitado nesta wave, §8.4 do impact-analysis — fica em backlog).

## Dependências

- **Nenhuma dependência de PR aberto.** Esta story **NÃO PODE** depender de #531 (`103_contract_lifecycle_truth`) nem de #528 estarem mergeados para atingir Done. `date_resolver_version = "ca-v2-precedence/1.0"` resolve `dim_recency` de forma legítima sem #531; o snapshot resultante em dados reais será tipicamente `PARTIAL` — **isso é o resultado esperado e aceito desta story**, não um bloqueio (Decisão 7, §7.3).
- **Tarefa obrigatória no início da implementação:** re-executar `gh pr list --state open` e `gh pr diff <n> --name-only | grep db/migrations` para confirmar que `104` continua livre antes de criar o arquivo da migration (§8.1, regra de guarda). Se outro PR reivindicou `104` no intervalo, subir o número — nunca reutilizar.
- Primitivos reusados sem alteração: `public_contract_id()` (`scripts/confenge_contract_identity.py`), `QUALIFYING_DATE_PRECEDENCE`, `cnpj_root8()` (`scripts/confenge_activation/commercial_authority_v2.py`), `is_hollow_fact()`/`extract_contract_hook()` (`scripts/confenge_account_intelligence/message_spine.py`), `v_contracts_canonical_v2` (leitura), `idempotency_key()`/`sha256_payload()` pattern (`scripts/inference_runtime/jobs.py`).

---

## Riscos (herdados do impact-analysis, §4) cobertos por esta story

| # | Risco | Mitigação nesta story |
|---|---|---|
| R1 | Objetos novos nascem fora da barreira select-only de 090 | 14 REVOKEs explícitos por objeto na migration 104 (6 tabelas + função as-of, para `PUBLIC` e `smartlic_public_reader`) + teste estático por statement executável. **Sem `ALTER DEFAULT PRIVILEGES`** — mecanismo removido por ser inerte no PG16; a mitigação efetiva é o REVOKE explícito, agora provado e não apenas afirmado |
| R2 | Wrapper as-of sobre a view perde linhas excluídas no replay | `sources.py` lê `pncp_raw_bids` diretamente, não a view; teste de equivalência `as_of(CURRENT_DATE) == v_open_opportunities_canonical` |
| R3 | Escrita acidental em `confenge_target_fit_dirty` | Teste estático glob sobre `scripts/confenge_live_intelligence/**` proibindo DML sobre tabelas outbound (mantém-se válido quando `events.py` for adicionado na story 2) |
| R4 | Colisão de número de migration | Task explícita de re-verificação no início da implementação |
| R6 | Contagem de dimensões reintroduzida como score | Nenhum campo numérico no schema do FIT; ordenação por tupla lexicográfica |
| R7 | UNKNOWN colapsado em NO_MATCH | Tri-estado obrigatório testado explicitamente |
| R9 | Drift silencioso de schema | `schema_version` dentro do payload hasheado |
| R11 | Critério "qualquer UNKNOWN" torna READY inalcançável | Completude por linha + exclusão contada; teste prova READY alcançável com UNKNOWN só em dimensão OPCIONAL |
| R13 | Replay sob TimeZone de sessão diferente | `cutoff_timezone` fixo + `sources.py` fixa TZ explicitamente + teste cross-TZ |
| R14 | "PARTIAL com blockers" proibido só em prosa | CHECK estrutural cobrindo `READY_CANONICAL` e `PARTIAL` |

R5, R8, R10, R12, R15 e todo o grupo de eventos (R3 parcialmente) ficam plenamente endereçados na story 2, quando `events.py` existir.

---

## Divergências do draft SQL vs. documento normativo (registrar, não reabrir)

O `schema-draft.sql` do @data-engineer é **anterior** à reconciliação de decisões e contém pontos que contradizem decisões já fechadas no `impact-analysis.md`. @dev deve seguir o `impact-analysis.md` nestes pontos; usar o draft apenas como referência de *padrão de engenharia* (state machine com `BUILDING/BLOCKED/READY_CANONICAL/SUPERSEDED`, RPCs `begin_/put_watermark_/close_snapshot`, trigger de imutabilidade pós-fechamento — todos aplicáveis **sobre as tabelas novas apenas**, nunca sobre tabelas outbound):

| Draft SQL | Normativo (impact-analysis, adotar) |
|---|---|
| `fit_score DOUBLE PRECISION`, `fit_class IN ('FIT_STRONG','FIT_POSSIBLE','FIT_WEAK','NOT_RELEVANT','RELEVANCE_UNKNOWN')`, índice ordenado por `fit_score DESC` | Tri-estado por dimensão `MATCH/NO_MATCH/UNKNOWN`, `fit_state ∈ {OBSERVED_FIT, NO_OBSERVED_FIT, INSUFFICIENT_EVIDENCE}`, **zero campo numérico**, ordenação por tupla lexicográfica (Decisão 4 — fechada, não reabrir) |
| `CREATE SCHEMA confenge_live_v1` | Schema `public`, com REVOKE explícito por objeto (Decisão 8, §8.4 — schema dedicado avaliado e rejeitado nesta wave) |
| Nomes de tabela `confenge_live_*` | `confenge_live_intelligence_*` (Decisão 8, §8.2) |
| `confenge_live_company_snapshot` copia `target_fit_class`/`target_fit_confidence`/`sector_class` de `confenge_company_target_fit_current`/`confenge_company_sector_current` | **Proibido.** A COMPANY do motor inbound é projeção independente do portfólio observado; nenhum campo copiado de tabelas de fit/sector outbound (Decisão 3, §3.2) |
| Guarda de PII no `events` é blacklist regex sobre `payload::TEXT` (`!~* 'email\|telefone\|...'`) | Whitelist: verifier valida que o key-set do payload emitido é **subconjunto** do schema declarado. Blacklist deixa passar campos não previstos (ex.: `responsavel_nome`) que não batem no regex |
| Migration destino proposta `110_...` | `104_confenge_live_intelligence_v1.sql` (decisão de reconciliação da missão — não reabrir; ver §Dependências) |

---

## Baseline

- `db/migrations/`: mais recente mergeado é `102_national_coverage_nullable_expected_units.sql`. `103` reservado por PR #531 (não mergeado). `#528` não reserva nenhum número. **Próximo livre confirmado: `104`.**
- `scripts/confenge_live_intelligence/` **não existe** — todo o pacote é criado por esta story.
- Testes de referência para o **padrão estrutural** de equivalência/idempotência (existentes na árvore, confirmados — mas são testes de *ingestão*, não do pipeline outbound de feed; servem de modelo de construção de teste, não de fixture a reutilizar literalmente):
  - `tests/test_golden_path_idempotency.py` (reconciliação idempotente de `pncp_raw_bids`/seeds)
  - `tests/test_golden_path_snapshot.py` (`scripts.golden_path.run_snapshot_reconciliation`)
  - `tests/test_golden_path_canonical.py`
  - `tests/test_snapshot_reconciliation.py`
- **A saída outbound real a comparar não vem de `scripts/golden_path.py`** (esse script cobre ingestão/crawl/relatórios, não o pipeline comercial). A fonte de `feed rows` / `queue counts` / veredito `send_readiness` é:
  - `queue_counts()` em `scripts/confenge_target_fit/store.py`, usado por `run_pipeline()` em `scripts/confenge_outreach_pipeline/pipeline.py:630`;
  - o feed exportado por `scripts/warmbly_bridge/export.py` (leads/chunks);
  - o veredito de `scripts/confenge_contact_resolution/send_readiness.py` (EMAIL_SEND_READY).
- Antes de tocar o banco, capturar baseline: rodar `run_pipeline()` (ou o entrypoint CLI equivalente já usado por `scripts/confenge_outreach_pipeline/cli.py`) contra um dataset fixo e salvar `queue_counts()` + o payload do feed exportado + o veredito `send_readiness` como fixture "antes" para o teste de equivalência (AC2).

## Estado-alvo

- Migration 104 aplicada, aditiva, com barreira select-only por objeto.
- `scripts/confenge_live_intelligence/{__init__,schema,sources,contract_date_resolver,fit,producer,verifier,cli}.py` implementados conforme LI-1..LI-6 + núcleo do verifier.
- `python3 -m scripts.confenge_live_intelligence.cli build --effective-date <DATE>` produz um snapshot que resolve para `PARTIAL` (esperado, dado ausência de #531) ou `READY_CANONICAL`/`BLOCKED` conforme os dados observados — nunca falha silenciosamente.
- `python3 -m scripts.confenge_live_intelligence.cli verify --snapshot-id <id>` re-deriva todos os hashes e falha fechado em qualquer divergência.
- Gate P0 verde **conforme AC2 reescopado (v1.6)**: nenhum módulo outbound referencia o motor inbound, e nenhuma ACL de objeto outbound muda com a 104. A prova de saída byte-idêntica sob execução real de `run_pipeline()` **não é estado-alvo desta story** — migrou para o follow-up bloqueante [`story-confenge-live-intelligence-outbound-equivalence-gate.md`](story-confenge-live-intelligence-outbound-equivalence-gate.md).

---

## Exceção pontual e escopada a `forbidden_write_targets` (ruling do @po, v1.6)

O @dev reportou conflito entre `forbidden_write_targets` e a verificabilidade de AC4/AC5/AC8. **Ratifico a solução já implementada** — isto é ratificação de implementação existente (`tests/confenge_live_intelligence/conftest.py`), não autorização de trabalho futuro. @qa não deve re-litigar o ponto.

| Item | Ruling |
|---|---|
| Tabela | **`pncp_raw_bids` e mais nenhuma.** `sc_public_entities` e todos os demais alvos permanecem SELECT-only, sem exceção |
| Prefixo obrigatório | `LI-TEST-` em `pncp_id` (`SEED_PREFIX`, `conftest.py:20`) |
| Garantia de teardown | `DELETE ... WHERE pncp_id LIKE 'LI-TEST-%'` executado **no setup e no teardown** da fixture, sob `try/finally` (`conftest.py:56-66,83`). O DELETE de setup é o que garante sobrevivência a falha no meio do teste: uma execução anterior abortada é varrida na entrada da seguinte |
| Escopo | Somente-teste. Nenhum código de `scripts/confenge_live_intelligence/**` escreve em `pncp_raw_bids` — AC11 continua valendo integralmente |
| Estado final exigido | `pncp_raw_bids=0`, `sc_public_entities=0`, `confenge_target_fit_dirty=0`, `opportunity_intel=0` após a suíte — verificado pelo @dev |

**Natureza da exceção:** pontual e escopada, **não** reabertura de `forbidden_write_targets`. `pncp_raw_bids` **permanece** na lista; a exceção convive com a entrada, não a substitui. Justificativa: a lista foi herdada dos objetos protegidos do AC1, que restringe o **DDL da migration** — nunca teve a intenção de proibir seed transacional de teste. E a exceção é **mais conservadora que o padrão pré-existente do repo**: `tests/test_golden_path_coverage.py:27` faz `TRUNCATE pncp_raw_bids` e `tests/test_golden_path_editais_report.py:66` insere sem prefixo algum. Ratificar o padrão prefixado aqui não abençoa retroativamente esses; apenas não os torna mais estritos.

---

## Ruling do @po sobre TD-LI-6 — dívida aceitável, não bloqueador (RULING-LI-03, v1.8)

O @dev reverteu InReview → InProgress ao descobrir TD-LI-6: `test_blocked_when_watermark_is_missing` falha quando o banco de teste compartilhado (`postgresql://test:test@127.0.0.1:5433/extra_test`) contém 5 linhas residuais **sem** prefixo `LI-TEST-` em `pncp_raw_bids`, deixadas por suítes alheias (`golden_path_*`, `crawl_runtime_queue`, `entity_*`). **Veredito: dívida ACEITÁVEL. A story sobe para InReview.**

| Critério | Análise |
|---|---|
| **Identidade de causa raiz com RULING-LI-02** | Decisivo. O AC2 de dois braços foi reescopado precisamente porque desbloqueá-lo exige um **2º DSN descartável**, insumo de @devops. TD-LI-6 tem a **mesma** causa raiz e o **mesmo** owner. Tratá-lo como bloqueador contradiria o ruling anterior do @po na mesma story e estacionaria o trabalho aguardando um insumo que **nenhum agente do ciclo atual pode produzir** — deadlock de processo, não gate de qualidade |
| **O AC8 não fica descoberto** | O gatilho *watermark ausente* **está provado**: 95 passed com `pncp_raw_bids` livre de linhas alheias. O ramo `BLOCKED` do AC8 permanece coberto independentemente por `test_blocked_when_as_of_is_missing` e `test_blocked_snapshot_is_persisted_with_blockers`. O que falta é **reprodutibilidade sob banco poluído** — isto é um teste não-determinístico, **não** um AC não provado. Essa distinção é o que torna o item dívida e não lacuna |
| **O defeito não é do motor** | O motor está correto: falha fechado e explicitamente em vez de mascarar. O que varia é o estado de uma tabela compartilhada por suítes não relacionadas. Nenhuma linha de `scripts/confenge_live_intelligence/**` está em causa |
| **A direção de falha escolhida pelo @dev é a certa** | Apagar as 5 linhas exigiria `DELETE` **não escopado** ao prefixo `LI-TEST-` numa tabela de `forbidden_write_targets`. A exceção ratificada na v1.6 é escopada por prefixo e **não** se estende a isso. O @dev acertou em falhar em vez de apagar dado alheio — e em reportar em vez de reinterpretar a regra |
| **Herança** | TD-LI-6 é **herdado pela mesma story de follow-up bloqueante** [`story-confenge-live-intelligence-outbound-equivalence-gate.md`](story-confenge-live-intelligence-outbound-equivalence-gate.md), que já tem "2º DSN descartável" como pré-requisito. Nenhum insumo novo é criado; o item entra na story que já existe para provê-lo |

**O que InReview significa aqui — e o que não significa.** InReview é **handoff para veredito independente**, não aprovação e não afirmação de que a suíte completa está verde. O checkbox de suíte completa do DoD permanece `[ ]`, declarado. Julgar se TD-LI-6 comporta `PASS`, `CONCERNS` ou `FAIL` é autoridade exclusiva do @qa (§3 e §6 do `aiox-project-operating-protocol.md`) — o @po não a antecipa. O @po decide apenas que a story está **elegível para ser julgada**, e está.

**Instrução ao @qa (não re-litigar, verificar).** Reproduzir a evidência **nos dois sentidos**, que é o que caracteriza o item como não-determinismo de infraestrutura: (a) com `pncp_raw_bids` livre de linhas alheias → 95 passed; (b) após a suíte completa deixar as 5 linhas → 94 passed / 1 failed, sempre o mesmo teste. Auditar resíduo do motor **exclusivamente** por `WHERE pncp_id LIKE 'LI-TEST-%'` — a contagem crua de 5 linhas não é resíduo desta story.

---

## Ruling do @po sobre TD-LI-7 — CORRIGIR AGORA, dentro do escopo já autorizado (RULING-LI-04, v1.10)

O @dev pediu ao @po que rulasse TD-LI-7 "pelo mesmo mecanismo com que rulou TD-LI-6". **O mecanismo é o que decide — e ele decide no sentido oposto.** RULING-LI-02 e RULING-LI-03 não classificaram itens como dívida por serem chatos de corrigir: classificaram por **exigirem um insumo que nenhum agente do ciclo atual pode produzir** (2º DSN descartável, owner @devops). TD-LI-7 **não** tem essa propriedade. Logo **não** há identidade de causa raiz com o ruling anterior, e a analogia não se aplica.

**Veredito: TD-LI-7 é BLOQUEADOR DE CORREÇÃO IMEDIATA, não dívida aceitável. Opção (a) — o escopo autorizado do @dev cobre a correção.** A story permanece `InProgress`.

| Critério | Análise |
|---|---|
| **Não há identidade de causa raiz com RULING-LI-03** | Decisivo, e no sentido contrário. TD-LI-6 é insolúvel sem um insumo externo (banco isolado). TD-LI-7 se corrige com uma função no próprio `conftest.py` da story: nenhum insumo novo, nenhum DSN, nenhuma escrita em `forbidden_write_targets`, nenhuma autoridade que o @dev não tenha. Rulá-lo dívida seria **estender o precedente além da razão que o produziu** |
| **Não é ampliação de escopo** | `tests/confenge_live_intelligence/conftest.py` e `tests/confenge_live_intelligence/test_sources_as_of.py` **já constam de `scope_files`** no state file. O @po não está abrindo escopo novo; está autorizando explicitamente uma correção **dentro de arquivos que a story já possui**. O @qa não deve ler isto como scope creep |
| **`today_utc()` é carga da evidência de AR-1** | Argumento mais forte, e ausente do texto do @dev. `today_utc()` é chamada em `test_no_outbound_write_runtime.py:128` e `:183` — o arquivo que é a **única** evidência de AR-1, ação **BLOQUEANTE** do gate HIGH-RISK do @architect. Deixar uma janela de fuso de ~3h/dia sob a própria prova do gate é materialmente diferente de um teste de leitura flaky. Não é aceitável fechar o gate sobre um instrumento com janela de indeterminação conhecida |
| **A mitigação "AC4 não fica descoberta" está superestimada — correção do @po** | `test_as_of_current_date_equals_canonical_view` **também** chama `today_utc()` (`test_sources_as_of.py:52`), assim como `test_session_timezone_is_pinned_before_reading` (`:60`). Ela sobrevive à janela por **sorte da distribuição do seed** (`+30d` / `−10d` estão longe da fronteira), não por imunidade. A cobertura de AC4 **não é independente** do defeito. O texto do @dev afirmava independência; fica corrigido aqui para que o @qa não herde a afirmação |
| **É defeito latente generalizado, não um teste** | Quatro call sites em dois arquivos, um deles a prova de AR-1. Tratar como "um teste flaky" subdimensiona o item |
| **O motor está correto — e isso não muda o veredito** | Ratificado: `live_open_opportunities_as_of()` resolve a data civil em `America/Sao_Paulo` **de propósito** (AC5, `pin_session_timezone`). O defeito é do fixture. Mas "o defeito não é do motor" foi *reforço* em RULING-LI-03, nunca a razão decisiva — e não basta para sustentar dívida quando a correção é alcançável |

**Autorização de escopo (o que o @dev está autorizado a fazer, e apenas isto).** Corrigir a derivação de data civil no fixture de `tests/confenge_live_intelligence/`, de modo que todos os call sites atuais de `today_utc()` (`test_sources_as_of.py:22,52,60` e `test_no_outbound_write_runtime.py:128,183`) passem a operar sobre a mesma data civil que o motor resolve. Nenhum arquivo de `scripts/confenge_live_intelligence/**` deve ser tocado por esta correção — a função as-of está correta e alterá-la seria regressão.

**Propriedade de aceite (não "trocar uma linha").** A data civil do teste tem de **derivar da mesma fonte de fuso que o motor fixa** (`pin_session_timezone` / `America/Sao_Paulo`), e não de um segundo literal de `ZoneInfo` escrito à mão no fixture. Um segundo literal é uma **segunda fonte de verdade** — exatamente o modo de falha que AR-2 acabou de fechar para a allowlist de escrita, e ele reabriria a possibilidade de o teste e o motor divergirem de novo sem que nada quebre. Se a correção introduzir um literal de fuso, ele tem de ser importado por nome do módulo do motor, não redigitado.

**Obrigação de re-medição.** Depois da correção, o @dev deve reexecutar a suíte do motor sob `REQUIRE_REAL_DB=1` e **reportar a nova contagem** (esperado: a falha 2 desaparece; TD-LI-6 permanece, já rulado). A medição anterior (`2 failed / 119 passed`) fica superada. Sem re-medição, a correção é afirmação sem evidência.

**Nota de leitura ao @dev e ao @qa — texto superado, não reescrito.** O campo `snapshot_evidence.known_issue_td_li_7` do state file (autoria do @dev, v1.9) termina com "Correcao adequada (outra story)" e "MEDIUM". **As duas afirmações estão superadas por este ruling:** a disposição passa a ser *corrigir nesta story* e a severidade passa a **HIGH**. O @po não reescreveu o campo para não adulterar evidência de outro agente — mesmo procedimento da v1.8 com a linha estale `AC2 — BLOCKED-PENDING-AUTHORIZATION`. Não agir pela linha antiga.

**Limite deste ruling.** Isto é decisão de **escopo**, autoridade do @po. Não é veredito de qualidade: classificar TD-LI-7, a suíte completa e o gate como `PASS`/`CONCERNS`/`FAIL` continua sendo autoridade **exclusiva** do @qa (§3 e §6 do `aiox-project-operating-protocol.md`) e não é antecipada aqui. Também **não** toca `architect_gate.gate_satisfied`, que permanece `false` por indeterminação de AR-5 — julgar suficiência de AR-5 é do @architect.

---

## Acceptance Criteria

**AC1 — Aditividade estrutural (P0, bloqueante).**
`Given` o arquivo `db/migrations/104_confenge_live_intelligence_v1.sql` já escrito
`When` um teste estático lê o arquivo como texto
`Then` ele falha se o arquivo contiver `ALTER`, `DROP`, ou `CREATE OR REPLACE` referenciando qualquer um de: `opportunity_intel*`, `confenge_company_target_fit_current`, `confenge_company_target_fit_history`, `confenge_target_fit_dirty`, `confenge_target_fit_events`, `pncp_supplier_contracts`, `canonical_public_snapshots`, `canonical_snapshot_*`, `confenge_company_sector_current`, `confenge_company_sector_history`, `v_open_opportunities_canonical`, `v_contracts_canonical_v2`, `pncp_raw_bids`, `sc_public_entities`.

**AC2 — Não-interferência com o outbound, provada estaticamente e por diff de catálogo (P0, bloqueante).**

> **Reescopo do @po (2026-09-02, v1.6).** A formulação original — execução de dois braços de `run_pipeline()` com comparação byte-a-byte — exige três insumos que esta story não possui e não pode criar sem virar outra story: (i) um segundo DSN descartável, (ii) um dataset de seed que exercite as 5 etapas do pipeline outbound, (iii) autorização para que código de produção outbound escreva em `confenge_target_fit_dirty`, tabela em `forbidden_write_targets`. O @dev **não** contornou nem falsificou o AC — declarou-o bloqueado, o que está correto. O gate de dois braços **não é descartado**: é promovido a story bloqueante nomeada (ver §Follow-up bloqueante abaixo), e o AC2 desta story passa a ser o subconjunto que a evidência disponível prova de fato.

`Given` a migration 104 aplicada e o pacote `scripts/confenge_live_intelligence` presente no `sys.path`
`When` (1) um teste estático varre `scripts/confenge_target_fit/`, `scripts/confenge_outreach_pipeline/`, `scripts/warmbly_bridge/`, `scripts/confenge_contact_resolution/` e `scripts/opportunity_intel/` procurando qualquer import ou referência a `confenge_live_intelligence`; **e** (2) um teste captura o catálogo de ACLs de todos os objetos de `public` antes e depois da 104
`Then` (1) nenhuma referência existe — nenhum caminho de execução outbound alcança o motor inbound; **e** (2) nenhuma ACL de objeto outbound difere entre os dois catálogos.
Produzido por `test_no_outbound_module_imports_live_intelligence` e `test_rollback_removes_every_object_and_reapply_is_clean`, somados a AC1 (aditividade estrutural do DDL) e AC11 (ausência de DML outbound no código do motor).

**Limite explícito desta evidência (declarar, não maquiar):** ela prova *ausência de acoplamento de código e de mudança de superfície de grants*. Ela **não** prova igualdade byte-a-byte da saída do pipeline outbound sob execução real. Essa prova é a do follow-up bloqueante.

**§Follow-up bloqueante — [`story-confenge-live-intelligence-outbound-equivalence-gate.md`](story-confenge-live-intelligence-outbound-equivalence-gate.md).**
O protocolo de dois braços abaixo permanece normativo e **deve** ser executado antes de qualquer story que operacionalize o motor (cron/systemd, integração com `message_spine.py`, ou personalização de outbound). Owner: @sm (criação da story) + @po (validação) + @architect (protocolo) + @devops (2º DSN). Pré-requisitos a prover na story: segundo DSN descartável, dataset de seed que exercite as 5 etapas, e autorização escopada de escrita outbound naquele banco descartável. Substitui TD-LI-1 como item de dívida. Stub criado em resposta a AR-5 do gate sistêmico de arquitetura (ver `docs/architecture/adr/ADR-040-confenge-live-intelligence-foundation.md`); story existe de fato no backlog, status Draft.

> ⚠️ **TUDO ABAIXO ATÉ O FIM DA SEÇÃO AC2 É O PROTOCOLO PRESERVADO DO FOLLOW-UP — NÃO É REQUISITO DESTA STORY.** Nenhum item daqui em diante deve ser cobrado pelo @qa no fechamento de `confenge-live-intelligence-01`. Está reproduzido na íntegra apenas para não se perder na transcrição para a story de follow-up.

`Given` um dataset fixo de input para `run_pipeline()` (`scripts/confenge_outreach_pipeline/pipeline.py`)
`When` o pipeline outbound roda **{módulo `confenge_live_intelligence` ausente do `sys.path` E migration 104 NÃO aplicada}** e depois roda de novo sobre o mesmo dataset **{módulo presente E migration 104 aplicada, mas o módulo não é invocado por nenhum caminho outbound}**
`Then` `queue_counts()`, o payload do feed exportado por `scripts/warmbly_bridge/export.py` e o veredito de `scripts/confenge_contact_resolution/send_readiness.py` são byte-idênticos entre as duas execuções.

**Protocolo de isolamento de banco (obrigatório, senão o AC é inverificável).** As duas execuções **NÃO** podem compartilhar a mesma instância de banco em sequência: `run_pipeline()` tem efeitos colaterais de escrita, então uma diferença observada na 2ª execução seria atribuível à 1ª execução, não à migration 104. O teste deve usar **dois bancos partindo do mesmo baseline limpo**:
- **Braço A (controle):** banco limpo + `apply_migrations` até `102` (sem `104`), `scripts/confenge_live_intelligence` ausente do `sys.path`.
- **Braço B (tratamento):** banco limpo + `apply_migrations` até `104` (inclusive), módulo presente no `sys.path` mas não invocado por nenhum caminho outbound.
- Ambos os braços recebem **o mesmo dataset fixo de seed**, aplicado após as migrations e antes de `run_pipeline()`.
- A comparação byte-a-byte é entre a saída do braço A e a do braço B. Se a infraestrutura de teste só permitir um banco, o braço A deve rodar primeiro, com dump/restore do estado pré-pipeline antes do braço B — nunca reaproveitando o banco já mutado.

**A comparação inclui a migration aplicada/não aplicada** — testar só a ausência/presença do import em Python é insuficiente, porque o vetor de risco real é a superfície SQL nova (schema `public`, `ALTER DEFAULT PRIVILEGES`, role nova), não o import.

**AC3 — Barreira select-only por objeto novo, sem vazar para objetos futuros não relacionados.**
`Given` a migration 104 aplicada
`When` um teste consulta os grants de `smartlic_public_reader` e `PUBLIC` sobre cada objeto criado pela migration
`Then` nenhum grant além do REVOKE explícito existe.
**AC3, 2ª cláusula — reescrita pelo @po (2026-09-02, v1.8).** A formulação anterior era uma condicional de antecedente hoje falso ("*quando* a 104 adicionar `ALTER DEFAULT PRIVILEGES`, *então* escopar por role"), satisfeita vacuamente após a remoção da §9 pelo @data-engineer. Condicional vácua não é requisito: é reescrita como **proibição positiva**, que é estritamente mais forte e não-vacuamente provável.

`Given` que `db/migrations/089*.sql` e `090*.sql` foram inspecionados e **não usam `ALTER DEFAULT PRIVILEGES`** (confirmado por grep — o padrão do repo é REVOKE explícito por migration sobre objetos existentes no momento), e que a §9 da 104 foi removida por ser inerte no PG16
`When` um teste percorre os **statements executáveis** da 104 usando o parser real de `scripts/ops/apply_migrations.py` (`split_sql`/`is_executable`) — nunca por substring no texto bruto, que daria falso positivo porque o arquivo cita o termo 7 vezes em comentários explicando a remoção
`Then` (1) **nenhum** statement executável da 104 emite `ALTER DEFAULT PRIVILEGES` — a barreira é feita exclusivamente por REVOKE explícito por objeto; (2) existe `REVOKE` explícito para `PUBLIC` **e** para `smartlic_public_reader` sobre cada uma das 6 tabelas novas e sobre `live_open_opportunities_as_of(DATE)`; e (3) `pg_default_acl` permanece sem nenhuma entrada em `public` após a aplicação da 104.
Produzido por `test_104_barrier_is_explicit_revokes_without_default_privileges`.

`Given` que a proibição acima pode ser revertida por uma migration futura que reintroduza o mecanismo
`When` uma migration **subsequente simulada, sob role distinta**, cria uma tabela após a 104
`Then` essa tabela não recebe nenhum grant derivado de default privileges da 104. Produzido por `test_future_migration_under_a_different_role_is_not_affected`, **retido deliberadamente como guarda de regressão** — se a §9 voltar em qualquer forma, este teste e a asserção de `pg_default_acl` vazia são o que obriga a seção 3 do rollback a voltar a emitir o GRANT inverso.

**AC4 — Leitor as-of recupera linhas excluídas pela view.**
`Given` um edital com `data_encerramento` no passado (ex.: encerrado ontem em relação à data efetiva de replay)
`When` `live_open_opportunities_as_of(<data passada>)` é chamado
`Then` o edital aparece no resultado — provando que o leitor vai à tabela base `pncp_raw_bids`, não à view `v_open_opportunities_canonical`. E `live_open_opportunities_as_of(CURRENT_DATE)` retorna o mesmo conjunto que `v_open_opportunities_canonical`.

**AC5 — Replay determinístico cross-timezone.**
`Given` o mesmo `snapshot_id`
`When` o replay roda sob duas `TimeZone` de sessão distintas (UTC e `America/Sao_Paulo`)
`Then` o `universe_hash` resultante é idêntico nas duas execuções.

**AC6 — Tri-estado FIT sem score.**
`Given` o schema do FIT (`fit.py`)
`When` um teste estático inspeciona os campos declarados e os imports do módulo
`Then` nenhum campo numérico de score existe no output; nenhum import de `opportunity_intel.scoring`/`opportunity_intel.ranking`; as 5 dimensões resolvem sempre para exatamente um de `MATCH`/`NO_MATCH`/`UNKNOWN`; a ordenação segue a tupla lexicográfica declarada em `PRIORIDADE_DIMENSOES`.

**AC7 — UNKNOWN nunca colapsa em NO_MATCH.**
`Given` uma OPPORTUNITY com `objeto` hollow — isto é, `is_hollow_fact(objeto) is True` (verificado em `scripts/confenge_account_intelligence/message_spine.py:55-73`: a função retorna `True` quando o texto é vazio, meta-only, boilerplate ou < 24 chars)
`When` `dim_object` é calculado
`Then` o resultado é `UNKNOWN`, nunca `NO_MATCH`, e `reason_codes` documenta o motivo.

**AC8 — Critério de estado do snapshot é alcançável em ambas as direções.**
`Given` dados sintéticos com UNKNOWN apenas em dimensões OPCIONAIS (`dim_value_band`, `dim_comparable_buyer`)
`When` o producer fecha o snapshot
`Then` o snapshot resolve para `READY_CANONICAL`.
`Given` dados sintéticos com pelo menos 1 linha excluída por UNKNOWN em dimensão REQUERIDA (`dim_object`, `dim_geography`) ou `dim_recency` não resolvida
`When` o producer fecha o snapshot
`Then` ele resolve para `PARTIAL`, com `excluded_opportunity_count > 0` ou `excluded_company_count > 0`, `closed_at IS NOT NULL`, `content_hash IS NOT NULL`, `blockers = []`.
`Given` uma condição de bloqueio da lista fechada (§7.2 do impact-analysis — hash divergente, identidade contraditória, `public_contract_id()` vazio sem `allow_legacy_surrogate`, watermark ausente/`FAILED`/`BLOCKED`, `as_of_date` ausente, tentativa de escrita outbound detectada)
`When` o producer fecha o snapshot
`Then` ele resolve para `BLOCKED` com `blockers` não vazio.

**AC9 — Verifier fail-closed.**
`Given` um snapshot `READY_CANONICAL` ou `PARTIAL` gravado
`When` o `verifier.py` re-deriva todos os hashes (universo, política, schema, dados, fit) a partir do conteúdo persistido
`Then` qualquer divergência produz falha explícita (`BLOCKED`/exceção), nunca degradação silenciosa ou retorno de sucesso parcial não sinalizado.

**AC10 — Zero PII/contato (whitelist, não blacklist).**
`Given` o payload de qualquer objeto emitido pelo motor (OPPORTUNITY, COMPANY, FIT)
`When` o verifier compara o key-set do payload com o schema declarado em `schema.py`
`Then` o key-set do payload é subconjunto do schema declarado — nenhum campo extra pode existir, inclusive campos vazados por join lateral. Teste dedicado prova que um payload com uma chave não declarada (ex.: `responsavel_nome`) é rejeitado, mesmo que não bata em nenhum termo de blacklist regex.

**AC11 — Zero escrita cruzada com o outbound.**
`Given` todo o código em `scripts/confenge_live_intelligence/**`
`When` um teste estático varre o glob (não lista de arquivos fixa — deve continuar válido quando `events.py` for adicionado na story 2)
`Then` ele prova ausência de `INSERT`/`UPDATE`/`DELETE` referenciando qualquer tabela outbound listada em AC1, e especificamente ausência total de qualquer referência de escrita a `confenge_target_fit_dirty`.

**AC12 — Decisões abertas registradas explicitamente pelo @dev.**
`Given` esta story
`When` a implementação começa
`Then` o @dev registra, no ADR desta story (`docs/architecture/adr/ADR-0XX-confenge-live-intelligence-foundation.md`), a decisão explícita e justificada para **os quatro** itens abertos abaixo. Nenhum deles é ambiguidade sem dono: todos têm owner (@dev, com @data-engineer para (b)) e artefato (o ADR).

| # | Item aberto | O que deve ser decidido | Fonte |
|---|---|---|---|
| (a) | `reason_codes` como `TEXT[]` ou `JSONB` | Escolher um e justificar. Famílias de referência: 089/`schema-draft.sql` usam `TEXT[]`; 071/072 usam `JSONB`. Consistência interna do motor é o critério — não misturar os dois. | @sm/@data-engineer |
| (b) | Role de leitura: novo `confenge_live_intel_reader` vs. reuso de `smartlic_public_reader` | Adotado o role novo por recomendação do @data-engineer. Registrar a justificativa **e** a exclusão explícita dos objetos da 104 dos grants do reader existente. Registrar também o destino do role no rollback (ver §Plano de Rollback). | @data-engineer |
| (c) | Limitação de replay as-of sobre `pncp_raw_bids` mutável | Registrar como **risco residual aceito nesta wave**, não como bug. Declarar explicitamente qual é a superfície de detecção (o `universe_hash` + `verifier.py` fail-closed) e o que **não** é coberto (divergência causada por UPDATE em `pncp_raw_bids` posterior ao snapshot é detectada, não prevenida). | impact-analysis §6.3 (Risco residual), R5 |
| (d) | Ausência intencional de kill switch | Registrar a decisão de **não** reusar `truth_plane_kill_switch` do outbound e por quê (acoplaria os dois motores, violando o isolamento que é a razão de ser desta story). Declarar o mecanismo de pausa vigente: não invocar o CLI/producer. Registrar como follow-up de backlog, com owner, a necessidade de kill switch próprio quando o motor for operacionalizado (story futura com cron/systemd). | Dev Notes, Decisão 5 |

---

## 🤖 CodeRabbit Integration

`coderabbit_integration.enabled: true` em `.aiox-core/core-config.yaml` — seção completa aplicável.

**Story Type Analysis**
- **Primary Type**: Database (migration 104, schema, RLS-like select-only lock)
- **Secondary Type(s)**: Architecture (motor novo, isolamento de leitura), Security (superfície de grants nova)
- **Complexity**: High — nova migration, novo pacote Python, gate de equivalência byte-idêntica bloqueante

**Specialized Agent Assignment**
- **Primary Agents**: @dev (pre-commit), @data-engineer (schema/SQL, migration 104)
- **Supporting Agents**: @architect (revisão de aditividade contra as 8 decisões fechadas), @qa (gate independente)

**Quality Gate Tasks**
- [ ] Pre-Commit (@dev): `coderabbit --prompt-only -t uncommitted` antes de marcar a story completa
- [ ] Pre-PR (@devops): `coderabbit --prompt-only --base main` antes de criar o PR
- [ ] Pre-Deployment (@devops): não aplicável nesta story — motor não é operacionalizado (sem systemd/cron), sem deploy de produção

**Self-Healing Configuration**
- Primary Agent: @dev (light mode)
- Max Iterations: 2
- Timeout: 15 minutos
- Severity Filter: CRITICAL
- CRITICAL: auto_fix (até 2 iterações); HIGH: document_only

**CodeRabbit Focus Areas**
- **Primary**: grants/REVOKE por objeto (Database), ausência de DML sobre tabelas outbound (Security), aditividade estrutural — nenhum `ALTER`/`DROP`/`CREATE OR REPLACE` sobre objetos existentes (Architecture)
- **Secondary**: reversibilidade da migration (`db/rollback/104_..._rollback.sql`), consistência do `fit.py` com a Decisão 4 (zero score numérico)

---

## Testes requeridos

| Arquivo | Cobre |
|---|---|
| `tests/test_live_intelligence_outbound_equivalence.py` (novo) | AC2, AC1 (teste estático da migration como texto) |
| `tests/confenge_live_intelligence/test_schema.py` (novo) | AC6, AC10, `live_hash()` independente de ordem de campo |
| `tests/confenge_live_intelligence/test_sources_as_of.py` (novo) | AC4, AC5 (cross-timezone) |
| `tests/confenge_live_intelligence/test_fit.py` (novo) | AC6, AC7 |
| `tests/confenge_live_intelligence/test_producer_state_criteria.py` (novo) | AC8 |
| `tests/confenge_live_intelligence/test_verifier.py` (novo) | AC9, AC10 |
| `tests/confenge_live_intelligence/test_no_outbound_dml_static.py` (novo, glob-based) | AC11 |
| `tests/test_golden_path_idempotency.py`, `tests/test_golden_path_snapshot.py`, `tests/test_golden_path_canonical.py` (existentes — rodar como regressão, não modificar) | Regressão geral. **Não** são mais o baseline byte-idêntico do AC2 — esse papel migrou para o follow-up bloqueante (v1.6) |
| `tests/test_snapshot_reconciliation.py` (existente — modelo, não modificar) | Padrão de reconciliação para `verifier.py` |

Framework: `pytest`, seguindo o padrão já em uso no repo (`pytest tests/ -q --tb=no -x`). Testes de migration/grants exigem `LOCAL_DATALAKE_DSN` configurado conforme `docs/DEVELOPMENT.md`.

## Marcadores obrigatórios no resultado final

Cada marcador é produzido por um teste/verificação específica:

| Marcador | Produzido por |
|---|---|
| `OUTBOUND_DISABLED=NO` | **Herdado pelo follow-up bloqueante (AC2 reescopado, v1.6).** Exige execução real de `run_pipeline()`; não é produzível nesta story. Reportar como `NÃO VERIFICADO`, nunca como `NO` |
| `OUTBOUND_VOLUME_REDUCED=NO` | **Herdado pelo follow-up bloqueante (AC2 reescopado, v1.6).** Idem |
| `OUTBOUND_CADENCE_REDUCED=NO` | verificação de File List / `git diff --name-only` (não um teste pytest) — asserção de que nenhum arquivo `deploy/systemd/*` aparece no diff desta story; @qa confere manualmente no fechamento |
| `OUTBOUND_EXISTING_QUEUE_INVALIDATED=NO` | **Herdado pelo follow-up bloqueante (AC2 reescopado, v1.6).** Exige `queue_counts()` sobre banco com dados; não é produzível nesta story |
| `LIVE_INTELLIGENCE_HANDOFF_READY=<YES\|PARTIAL\|NO>` | `tests/confenge_live_intelligence/test_producer_state_criteria.py` reporta o estado do snapshot mais recente; `PARTIAL` é resultado **esperado e aceito** nesta wave (ver §Dependências) |

---

## Arquivos afetados (previstos)

**Novos:**
- `db/migrations/104_confenge_live_intelligence_v1.sql`
- `db/rollback/104_confenge_live_intelligence_v1_rollback.sql`
- `scripts/confenge_live_intelligence/__init__.py`
- `scripts/confenge_live_intelligence/schema.py`
- `scripts/confenge_live_intelligence/sources.py` — **REL-001** (v1.13): `pin_session_timezone()` antes de `MAX(updated_at)`; ler `TIMESTAMPTZ` sem o pin devolvia o mesmo instante com `tzinfo` diferente entre builds, o que já bastava para divergir o `snapshot_id`
- `scripts/confenge_live_intelligence/contract_date_resolver.py`
- `scripts/confenge_live_intelligence/fit.py`
- `scripts/confenge_live_intelligence/producer.py`
- `scripts/confenge_live_intelligence/verifier.py` — **REL-001** (v1.13): `normalize_source_as_of()` em `_rebuild_opportunity`/`_rebuild_company` — terceiro sítio da mesma classe, no read-back de `TIMESTAMPTZ` (verify falhava fechado sobre snapshot íntegro na mesma conexão do build)
- `scripts/confenge_live_intelligence/cli.py`
- `tests/confenge_live_intelligence/*.py` (novo diretório de testes)
- `tests/test_live_intelligence_outbound_equivalence.py`
- `docs/architecture/adr/ADR-0XX-confenge-live-intelligence-foundation.md` (registrar as decisões abertas do AC12)

**Nenhum arquivo outbound existente deve aparecer no File List final** (`scripts/confenge_target_fit/`, `scripts/opportunity_intel/`, `scripts/warmbly_bridge/`, `scripts/confenge_outreach_pipeline/`, `deploy/systemd/*`, `db/migrations/071*.sql` .. `103*.sql`). Se algum aparecer, é um desvio de escopo e deve ser justificado explicitamente ou removido.

---

## DoD

- [x] AC1–AC12 atendidos, com evidência (comando + saída) registrada no Dev Notes. **AC2 conforme reescopo v1.6** — os dois produtores nomeados pelo @po passam; o limite dessa evidência está declarado, não maquiado.
- [x] `ruff check scripts/confenge_live_intelligence/ tests/confenge_live_intelligence/` limpo (+ `ruff format --check`).
- [ ] Suíte completa (`pytest tests/ -q --tb=no`) — **NÃO ATENDIDO, declarado, não maquiado.** Nenhuma falha nova atribuível a esta rodada, mas **não** é "verde" e o baseline da v1.5 **não é comparável** (rodou sem `REQUIRE_REAL_DB=1`: 303 skipped vs 128 agora, ou seja, todos os testes `real_db` — inclusive os do motor — eram pulados no baseline). Sob `REQUIRE_REAL_DB=1` aparece **uma dependência de ordem pré-existente no próprio motor** (`test_blocked_when_watermark_is_missing`), registrada como **TD-LI-6**. Ver Dev Notes §"Suíte completa (DoD)". **Disposição do @po (v1.8): TD-LI-6 é dívida ACEITÁVEL, não bloqueador** — o checkbox permanece `[ ]` por honestidade de evidência (a suíte completa não está verde), mas isso é matéria de **veredito do @qa**, não de bloqueio do @po. Ver §Ruling do @po sobre TD-LI-6 e Change Log v1.8. **Adendo do @po (v1.10):** a segunda falha medida na v1.9 (`test_as_of_recovers_row_excluded_by_the_view`, TD-LI-7) **não** recebeu a mesma disposição — foi rulada **correção obrigatória nesta story** (RULING-LI-04), porque não depende de insumo externo e porque `today_utc()` também é chamada dentro da evidência de AR-1. Este checkbox só pode ser reavaliado após a re-medição exigida por RULING-LI-04. **Re-medição executada (@dev, v1.11):** TD-LI-7 **corrigido**, medição nova da suíte do motor = `1 failed / 121 passed`, feita **dentro** da janela de manifestação do defeito e com controle negativo. A única falha remanescente é TD-LI-6. O checkbox **permanece `[ ]`** — a suíte não está verde e afirmar o contrário seria selo sem evidência; a disposição de TD-LI-6 como dívida aceitável é do @po (RULING-LI-03) e sua classificação como `PASS`/`CONCERNS`/`FAIL` é autoridade exclusiva do @qa.
- [x] Gate P0 (AC2 **reescopado, v1.6**) executado: prova estática de não-referência + diff de catálogo de ACLs. Marcador `OUTBOUND_CADENCE_REDUCED=NO` reportado; os outros 3 permanecem `NÃO VERIFICADO` **por decisão do @po** e são herdados pelo follow-up bloqueante — reportá-los como `NO` aqui é violação de DoD, não conformidade.
- [x] `LIVE_INTELLIGENCE_HANDOFF_READY` reportado (**NO** em banco vazio — fail-closed correto; **YES** e **PARTIAL** alcançáveis e provados em `test_producer_state_criteria.py`). Ver §Marcadores obrigatórios.
- [x] Migration 104 revisada e aprovada por @data-engineer (autoridade exclusiva sobre schema/DDL) — a remoção da §9 e a reescrita da seção 3 do rollback **são** essa revisão; ADR-040 Achados 1 e 2 marcados como ratificados.
- [x] Decisões do AC12 registradas em ADR-040 (`reason_codes` = TEXT[]; role `confenge_live_intel_reader` novo, dropado no rollback; limitação de replay as-of; ausência intencional de kill switch).
- [x] Rollback testado: ciclo `104 aplicada → rollback → catálogo sem resíduo → 104 reaplicada` em `test_rollback_removes_every_object_and_reapply_is_clean` (12 passed no arquivo).
- [ ] Veredito de QA independente (@qa ≠ @dev). — **não é do @dev**
- [ ] PO fecha a story conforme protocolo (§7 do `aiox-project-operating-protocol.md`). — **não é do @dev**
- [x] Nenhuma dívida nova introduzida sem registro em follow-up com owner e severidade — TD-LI-1 absorvido pelo follow-up bloqueante; TD-LI-2 e TD-LI-3 RESOLVIDOS nesta rodada; TD-LI-4 e TD-LI-5 permanecem registrados com owner e severidade.

## Plano de Rollback

Um único arquivo, um único comando: `psql "$LOCAL_DATALAKE_DSN" -f db/rollback/104_confenge_live_intelligence_v1_rollback.sql`.

O rollback deve, em ordem (FKs antes de tabelas referenciadas, funções antes de nada que dependa delas):
```sql
BEGIN;
DROP FUNCTION IF EXISTS public.live_open_opportunities_as_of(DATE);
DROP TABLE IF EXISTS public.confenge_live_intelligence_events;
DROP TABLE IF EXISTS public.confenge_live_intelligence_fit;
DROP TABLE IF EXISTS public.confenge_live_intelligence_companies;
DROP TABLE IF EXISTS public.confenge_live_intelligence_opportunities;
DROP TABLE IF EXISTS public.confenge_live_intelligence_source_watermarks;
DROP TABLE IF EXISTS public.confenge_live_intelligence_snapshots;
-- + qualquer função/trigger de imutabilidade criada exclusivamente para essas tabelas

-- ★ OBRIGATÓRIO: DROP TABLE NÃO reverte ALTER DEFAULT PRIVILEGES nem remove o role.
-- Ambos são entradas de catálogo (pg_default_acl / pg_roles) que sobrevivem ao drop
-- das tabelas. Sem estas linhas, o rollback deixa resíduo e a 104 não é reaplicável
-- de forma limpa.
ALTER DEFAULT PRIVILEGES FOR ROLE <owner-do-104> IN SCHEMA public
    GRANT SELECT ON TABLES TO <...>;  -- inverso exato do que a 104 executou
-- Decisão do @dev/@data-engineer, a registrar no ADR do AC12: o role
-- confenge_live_intel_reader é DROPADO no rollback (DROP OWNED BY + DROP ROLE)
-- ou RETIDO como no-op inerte? Retê-lo é aceitável apenas se ele ficar sem
-- nenhum grant após o rollback — o que deve ser provado por teste.
COMMIT;
```

**Critério de aceite do rollback (verificável, não prosa):** após rodar o script em banco limpo com a 104 aplicada, uma consulta a `pg_default_acl` não retorna nenhuma entrada criada pela 104, e `\dp` sobre o schema `public` mostra o mesmo conjunto de grants que existia antes da 104. Reaplicar a 104 depois do rollback deve funcionar sem erro (idempotência do par migration/rollback).

Nenhuma tabela ou view outbound é tocada pelo rollback — por construção, o rollback só referencia objetos criados por esta story. Sem impacto no pipeline outbound antes, durante ou depois do rollback.

---

## Tasks / Subtasks

- [x] **Task 0 — Re-verificação de número de migration** (AC1, dependência)
  - [x] `gh pr list --state open` e `gh pr diff <n> --name-only | grep db/migrations` para cada PR aberto
  - [x] Confirmar `104` livre; se não, subir número e atualizar esta story
- [x] **Task 1 — LI-1: Fundação de schema** (AC6, AC10, AC12)
  - [x] `schema.py`: `ENGINE_ID`, `ENGINE_VERSION`, `SCHEMA_VERSION`, `live_hash()`, dataclasses frozen
  - [x] Decidir e documentar `reason_codes`: TEXT[] vs JSONB (AC12) → **TEXT[]**, ADR-040 §(a)
- [x] **Task 2 — LI-2: Migration 104 + barreira** (AC1, AC3, AC12) — **@data-engineer**
  - [x] 6 tabelas + `live_open_opportunities_as_of(DATE)`, espelhando padrão 089
  - [x] Revoke explícito por objeto + `ALTER DEFAULT PRIVILEGES` escopado por role dona — aplicado e testado. **Achado:** o `ALTER DEFAULT PRIVILEGES` é INERTE no PG16 (não grava `pg_default_acl`, não altera objeto futuro). AC3 passa pelos REVOKE explícitos, que funcionam. Registrado no ADR-040, Achado 2 → @data-engineer
  - [x] Criar/decidir role `confenge_live_intel_reader` (AC12)
  - [x] `db/rollback/104_..._rollback.sql` — **1 defeito corrigido pelo @dev** (ADR-040, Achado 1)
  - [x] Teste estático de aditividade (AC1) e de barreira (AC3)
- [x] **Task 3 — LI-3: Leitores as-of** (AC4, AC5)
  - [x] `sources.py` fixando TZ explicitamente na sessão
  - [x] Teste de recuperação de linha excluída + teste cross-timezone (com guarda anti-vacuidade)
- [x] **Task 4 — LI-4: Accessor de data** (AC12 nota)
  - [x] `contract_date_resolver.py` sobre `QUALIFYING_DATE_PRECEDENCE`, retorna `(date, trust, campo)`
- [x] **Task 5 — LI-5: FIT tri-estado** (AC6, AC7)
  - [x] `fit.py`: 5 dimensões, `fit_state`, ordenação lexicográfica
- [x] **Task 6 — LI-6: Producer** (AC8)
  - [x] `producer.py`: `BUILDING → READY_CANONICAL|PARTIAL|BLOCKED`, exclusão por linha contada
- [x] **Task 7 — Verifier (núcleo)** (AC9, AC10)
  - [x] `verifier.py`: re-derivação de hash fail-closed; validação whitelist de key-set
- [x] **Task 8 — CLI mínimo** (`build`, `verify`)
- [x] **Task 9 — Gate P0** (AC2 **reescopado v1.6**, AC11, marcadores)
  - [x] `tests/test_live_intelligence_outbound_equivalence.py` — AC1 completo; AC2 reescopado satisfeito pelos dois produtores nomeados pelo @po (ver Dev Notes)
  - [x] Teste estático glob de proibição de DML outbound (AC11)
- [x] **Task 10 — ADR e fechamento**
  - [x] `docs/architecture/adr/ADR-040-confenge-live-intelligence-foundation.md`
  - [x] Atualizar `docs/architecture/adr/INDEX.md`

---

## File List (entregue)

**Novos — código:**
- `scripts/confenge_live_intelligence/__init__.py`
- `scripts/confenge_live_intelligence/schema.py`
- `scripts/confenge_live_intelligence/sources.py`
- `scripts/confenge_live_intelligence/contract_date_resolver.py`
- `scripts/confenge_live_intelligence/fit.py`
- `scripts/confenge_live_intelligence/producer.py`
- `scripts/confenge_live_intelligence/verifier.py`
- `scripts/confenge_live_intelligence/cli.py`

**Novos — testes:**
- `tests/confenge_live_intelligence/__init__.py`
- `tests/confenge_live_intelligence/conftest.py` — **TD-LI-7** (v1.11): `today_utc()` → `today_cutoff_tz()`, derivando de `CUTOFF_TIMEZONE` importado de `schema.py` (fonte de fuso única, sem segundo literal)
- `tests/confenge_live_intelligence/test_schema.py`
- `tests/confenge_live_intelligence/test_fit.py`
- `tests/confenge_live_intelligence/test_sources_as_of.py` — **REL-001** (v1.13): `project_opportunity` recebe `source_as_of` do watermark real, re-lido a cada volta; **TD-LI-7** (v1.11): call sites atualizados + `test_fixture_civil_date_matches_the_engine_timezone` (guarda determinística, válida a qualquer hora)
- `tests/confenge_live_intelligence/test_producer_state_criteria.py` — **REL-001/TEST-001/REL-002** (v1.13): `test_replay_is_idempotent_for_the_same_universe` (vácuo) substituído por `test_replay_over_the_real_projection_is_idempotent` (projeção real, contagem total sem filtro de `snapshot_id`); novos `test_company_projection_source_as_of_comes_from_the_source_watermark` e `test_blocked_as_of_date_is_immune_to_the_os_timezone`; asserção de `as_of_date`/`snapshot_id` em `test_blocked_when_as_of_date_is_missing`; em `test_blocked_when_watermark_is_missing` **apenas** o kwarg `require_watermark` foi removido (asserções intactas — TD-LI-6 permanece aberta)
- `tests/confenge_live_intelligence/test_verifier.py` — **REL-001** (v1.13): novo `test_verify_on_the_same_connection_that_built_the_snapshot` (projeção real + sessão pinada em `CUTOFF_TIMEZONE`, a única combinação que discrimina)
- `tests/confenge_live_intelligence/test_no_outbound_dml_static.py`
- `tests/confenge_live_intelligence/test_no_outbound_write_runtime.py` — **AR-1** (v1.9); call sites de `today_cutoff_tz()` atualizados em **TD-LI-7** (v1.11), 3 testes re-medidos verdes
- `tests/confenge_live_intelligence/test_migration_grants_and_rollback.py`
- `tests/test_live_intelligence_outbound_equivalence.py`

**Novos — docs:**
- `docs/architecture/adr/ADR-040-confenge-live-intelligence-foundation.md`

**Modificados:**
- `scripts/confenge_live_intelligence/schema.py` — **AR-2** (v1.9): `WRITE_TARGET_ORDER` (única enumeração literal), `ALLOWED_WRITE_TARGETS` (derivada), `OutboundWriteAttemptError`, `assert_write_target()`
- `scripts/confenge_live_intelligence/producer.py` — **AR-2** (v1.9): `_persist()` deixa de ter tupla local de nomes de tabela; itera `WRITE_TARGET_ORDER` e valida por `assert_write_target()` antes de cada execução
- `scripts/confenge_live_intelligence/__init__.py` — **AR-2** (v1.9): re-exporta a allowlist e a guarda (`__all__`), para que o teste do AC11 as importe por nome
- `tests/confenge_live_intelligence/test_no_outbound_dml_static.py` — **AR-2** (v1.9): checker de AST para DML dinâmico + 10 auto-testes negativos + asserção de disjunção + proibição de acumulação
- `db/rollback/104_confenge_live_intelligence_v1_rollback.sql` — correção de defeito (seção 3), ver ADR-040 Achado 2. **Confirmada e reescrita pelo @data-engineer em 2026-09-02** (seção 3 agora vazia: sem `ALTER DEFAULT PRIVILEGES` na 104, não há inverso a emitir). TD-LI-3 RESOLVIDO.
- `db/migrations/104_confenge_live_intelligence_v1.sql` — **§9 removida pelo @data-engineer** (TD-LI-2 RESOLVIDO). Arquivo não tocado pelo @dev em nenhuma rodada.
- `docs/architecture/adr/INDEX.md` — entrada da ADR-040
- `docs/stories/story-confenge-live-intelligence-01.md` — esta story

**Nenhum arquivo outbound existente foi tocado.** `git diff --name-only` não contém
`scripts/confenge_target_fit/`, `scripts/opportunity_intel/`, `scripts/warmbly_bridge/`,
`scripts/confenge_outreach_pipeline/`, `deploy/systemd/*` nem `db/migrations/071*..103*.sql`.

---

## IDS — decisões de reuso

| Primitivo | Decisão | Justificativa |
|---|---|---|
| `public_contract_id()` (`scripts/confenge_contract_identity.py`) | **REUSE** (import direto) | Regra única de identidade pública; `allow_legacy_surrogate` respeitado — id vazio vira blocker, não descarte |
| `QUALIFYING_DATE_PRECEDENCE` + `contracting_date()` (`commercial_authority_v2.py`) | **REUSE** (import direto) | `contract_date_resolver.py` é wrapper fino; troca pelo #531 fica sendo mudança de uma função |
| `cnpj_root8()` (`commercial_authority_v2.py`) | **REUSE** (import direto) | Normalização única de raiz de CNPJ |
| `is_hollow_fact()` (`message_spine.py`) | **REUSE** (import direto) | AC7 exige exatamente esse predicado; reimplementar criaria drift com `send_readiness` |
| `sha256_payload()` (`inference_runtime/jobs.py:39`) | **ADAPT** | `live_hash()` reimplementa a mesma disciplina canonical-JSON+SHA256 sem importar o runtime de inferência (evita acoplamento). Equivalência byte-a-byte provada por `test_live_hash_matches_repo_canonical_discipline` |
| `split_sql()` / `is_executable()` (`scripts/ops/apply_migrations.py`) | **REUSE** (import direto nos testes) | Mesmo parser de produção executa migration/rollback no teste — sem divergência de parsing |
| `admit_ready_connection()` (`scripts/testing/real_db_guard.py`) | **REUSE** | Política de admissão real_db do repo; skip limpo sem `REQUIRE_REAL_DB=1` |
| `v_open_opportunities_canonical` | **NÃO reusado como fonte** (CREATE de função nova sobre `pncp_raw_bids`) | R2/AC4 — wrapper sobre a view só filtra para menos |

---

## Dev Notes

### Evidência de execução (@dev, 2026-09-02)

**AC1 — migration aplicada.**
```
$ python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
applied 104_confenge_live_intelligence_v1.sql
migrations_ok mode=upgrade applied=1 skipped=104 repaired=0
```
Teste estático por statement: `tests/test_live_intelligence_outbound_equivalence.py` — 8 passed.

**AC2 — `BLOCKED-PENDING-AUTHORIZATION`.** Ver seção dedicada abaixo.

**AC3 / rollback.** `tests/confenge_live_intelligence/test_migration_grants_and_rollback.py` — 12 passed
(re-executado em 2026-09-02 após a remoção da §9 pelo @data-engineer).
A 2ª parte do AC3 é uma condicional com **antecedente agora falso** ("QUANDO a 104 adicionar
`ALTER DEFAULT PRIVILEGES`") — a 104 não emite mais nenhum. O teste renomeado
`test_104_barrier_is_explicit_revokes_without_default_privileges` prova por statement, com o parser
real de `apply_migrations`, que (1) nenhum statement executável da 104 emite `ALTER DEFAULT
PRIVILEGES` e (2) existe `REVOKE` explícito para `PUBLIC` e `smartlic_public_reader` sobre cada uma
das 6 tabelas e sobre a função as-of. A asserção de `pg_default_acl` vazia é retida como guarda de
regressão (é a condição que faria a seção 3 do rollback precisar voltar a emitir o GRANT inverso).
Inclui o ciclo completo `104 aplicada → rollback → pg_default_acl vazio, role ausente, zero
objeto do motor, ACLs pré-existentes intactas → 104 reaplicada → catálogo idêntico ao inicial`.

**AC4/AC5.** `test_sources_as_of.py` — 5 passed, incluindo a guarda anti-vacuidade
(`test_boundary_row_is_timezone_sensitive_without_pinning`, que prova que a fixture de fronteira
02:30Z REALMENTE muda de conjunto entre UTC e `America/Sao_Paulo` sem a fixação de TZ).

**AC6/AC7/AC10.** `test_schema.py` (16 passed) + `test_fit.py` (13 passed).

**AC8.** `test_producer_state_criteria.py` — 10 passed. READY, PARTIAL (por dimensão requerida e
por data não resolvida) e BLOCKED (as_of ausente, watermark ausente, blocker injetado) todos alcançados.

**AC9.** `test_verifier.py` — 13 passed. Adulteração de qualquer um dos 6 hashes agregados, do
conteúdo de linha, da contagem de exclusão ou do `fit_state` produz exceção explícita.

**AC11.** `test_no_outbound_dml_static.py` — 18 passed (glob + AST, imune a docstring).

**CLI (Estado-alvo).**
```
$ python3 -m scripts.confenge_live_intelligence.cli build --effective-date 2026-09-02
{ "state": "BLOCKED", "blockers": ["watermark_missing_or_failed"],
  "LIVE_INTELLIGENCE_HANDOFF_READY": "NO" }          # banco de teste vazio ⇒ fail-closed correto
$ python3 -m scripts.confenge_live_intelligence.cli verify --snapshot-id NAO-EXISTE
VERIFY_FAILED: snapshot inexistente: 'NAO-EXISTE'    # exit 2
```

**Suíte do motor:** 95 passed (`tests/confenge_live_intelligence/` + gate P0).
**Regressão dirigida:** 391 passed, 34 skipped (`golden_path*`, `snapshot_reconciliation`,
`confenge_outreach_pipeline`, `confenge_target_fit`, `confenge_contact_resolution`,
`confenge_account_intelligence`, `confenge_activation`).
**Lint:** `ruff check` limpo; `ruff format --check` limpo (18 arquivos).

### AC2 — SATISFEITO conforme reescopo do @po (v1.6); protocolo de dois braços migrado

**Estado atual (v1.7).** O AC2 desta story é o reescopado pelo @po e nomeia seus dois
produtores. Ambos passam contra banco real:

| Produtor nomeado no AC2 v1.6 | Arquivo | Resultado |
|---|---|---|
| `test_no_outbound_module_imports_live_intelligence` | `tests/confenge_live_intelligence/test_no_outbound_dml_static.py:110` | PASS |
| `test_rollback_removes_every_object_and_reapply_is_clean` | `tests/confenge_live_intelligence/test_migration_grants_and_rollback.py` | PASS |

Somados a AC1 (aditividade estrutural do DDL, por statement) e AC11 (ausência de DML outbound
no código do motor), cobrem integralmente a formulação v1.6.

**O limite desta evidência permanece declarado, não maquiado:** ela prova ausência de acoplamento
de código e ausência de mudança de superfície de grants. Ela **não** prova igualdade byte-a-byte da
saída do pipeline outbound sob execução real — essa prova é a do follow-up bloqueante
[`story-confenge-live-intelligence-outbound-equivalence-gate.md`](story-confenge-live-intelligence-outbound-equivalence-gate.md),
e os 3 marcadores que dependem dela
seguem `NÃO VERIFICADO` (reportá-los como `NO` aqui seria violação de DoD).

**Registro histórico — por que estava bloqueado até a v1.5 (mantido para auditoria do @qa).**
O protocolo de dois braços do AC2 compara `queue_counts()`, que lê
`confenge_target_fit_dirty`. Para a comparação ser não-trivial, `run_pipeline()` precisa
**escrever** nessa tabela. Dois bloqueios independentes:

1. **Autorização.** `confenge_target_fit_dirty` está na lista de tabelas somente-SELECT da
   missão do @dev. Executar `run_pipeline()` violaria a regra dura. Não reinterpretei a regra.
2. **Fixture ausente.** O banco local está **vazio** (`pncp_raw_bids`, `v_contracts_canonical_v2`
   e `sc_public_entities` com 0 linhas). Com seed nulo, `queue_counts()` retorna `{}` nos dois
   braços e o teste passaria sem provar nada — um AC2 vazio seria pior que um AC2 declarado bloqueado.

**Evidência parcial entregue no lugar (rotulada como parcial, nunca como AC2 satisfeito):**
- prova estática de que nenhum módulo de `scripts/confenge_target_fit/`,
  `scripts/confenge_outreach_pipeline/`, `scripts/warmbly_bridge/`,
  `scripts/confenge_contact_resolution/` ou `scripts/opportunity_intel/` referencia
  `confenge_live_intelligence` (`test_no_outbound_module_imports_live_intelligence`);
- diff de catálogo pré/pós-104 sobre todos os objetos de `public`, provando que nenhuma ACL de
  objeto outbound mudou (`test_rollback_removes_every_object_and_reapply_is_clean`);
- AC1 e AC11 completos.

**O que é preciso para desbloquear:** (a) autorização explícita para `run_pipeline()` escrever em
tabelas outbound dentro de um banco descartável; (b) um segundo DSN descartável; (c) um dataset de
seed que exercite as 5 etapas do pipeline. Nada disso é decisão do @dev.

### Texto da story desatualizado pela remoção da §9 — sinalizado, NÃO editado (fora da autoridade do @dev)

A §9 da 104 (`ALTER DEFAULT PRIVILEGES`) foi removida pelo @data-engineer. Três trechos do corpo
normativo da story ainda a descrevem como parte da migration. São textos de **@po/@architect**
(`story-lifecycle.md`: Título/Descrição/AC/Escopo = @po); o @dev os reporta em vez de reescrevê-los,
para que sejam lidos como herdados-e-sinalizados, não como drift do @dev:

| Local | Texto atual | Estado real |
|---|---|---|
| **Escopo IN, item 2** | "revokes explícitos por objeto, `ALTER DEFAULT PRIVILEGES` (Decisão 8, §8.2–§8.4)" | A 104 não emite mais `ALTER DEFAULT PRIVILEGES`. A barreira é feita só pelos 14 REVOKE explícitos |
| **Riscos, linha R1** | "Revokes explícitos por objeto + `ALTER DEFAULT PRIVILEGES` na migration 104 + teste estático" | R1 segue mitigado, mas **apenas** por REVOKE explícito + teste estático por statement |
| **AC3, 2ª cláusula** | "`When` a migration 104 adicionar `ALTER DEFAULT PRIVILEGES` `Then` ela deve ser escopada por role dona..." | Condicional de **antecedente falso**: a 104 não adiciona nenhum. Satisfeita vacuamente e, mais forte, por construção. O teste `test_future_migration_under_a_different_role_is_not_affected` é retido como guarda de regressão caso a §9 volte |

Nenhum desses trechos invalida evidência entregue — todos apontam para uma barreira **mais** estrita
do que a descrita (mecanismo inerte removido, mecanismo efetivo mantido e agora provado por statement).

### Marcadores obrigatórios — estado real

| Marcador | Valor | Produzido por |
|---|---|---|
| `OUTBOUND_DISABLED` | **NÃO VERIFICADO** | depende do AC2 bloqueado |
| `OUTBOUND_VOLUME_REDUCED` | **NÃO VERIFICADO** | depende do AC2 bloqueado |
| `OUTBOUND_CADENCE_REDUCED` | **NO** | File List — nenhum `deploy/systemd/*` no diff |
| `OUTBOUND_EXISTING_QUEUE_INVALIDATED` | **NÃO VERIFICADO** | depende do AC2 bloqueado |
| `LIVE_INTELLIGENCE_HANDOFF_READY` | **NO** (banco vazio) / **YES** e **PARTIAL** alcançáveis e provados em `test_producer_state_criteria.py` | producer + testes de estado |

Os três marcadores `NÃO VERIFICADO` **não** são reportados como `NO`: declarar `NO` sem o teste
que o produz seria selo sem evidência.

### Conflito de regra reportado (não resolvido unilateralmente)

`.aiox/state/stories/confenge-live-intelligence-01.json` lista `pncp_raw_bids` e
`sc_public_entities` em `forbidden_write_targets`. Porém **AC4, AC5 e AC8 são inverificáveis
sem dados em `pncp_raw_bids`** (o banco local tem 0 linhas), e o próprio protocolo do AC2 exige
"o mesmo dataset fixo de seed, aplicado após as migrations". A lista parece herdada da lista de
objetos protegidos do AC1, que restringe o **DDL da migration**, não o seed de teste.

**Decisão do @dev, explicitada para ratificação do @po:**
- seed sintético **apenas** em `pncp_raw_bids`, sempre com prefixo `LI-TEST-`, com `DELETE`
  escopado ao prefixo no setup **e** no teardown da fixture;
- `sc_public_entities` **nunca** é escrita (`matched_entity_id` fica `NULL`; o `LEFT JOIN` cobre);
- nenhuma das demais tabelas da lista é tocada por nada além de `SELECT`.

**Estado do banco verificado após a suíte do motor:** `pncp_raw_bids` com **0 linhas `LI-TEST-`**,
`sc_public_entities=0`, `confenge_target_fit_dirty=0`, `opportunity_intel=0`. A garantia de teardown
ratificada pelo @po é sobre o **resíduo do motor**, e ela se sustenta.

**Aviso ao @qa (medido, não estimado):** após a **suíte completa**, `pncp_raw_bids` tem **5 linhas** —
nenhuma delas com prefixo `LI-TEST-`. São de testes alheios que compartilham o mesmo banco. Se o @qa
rodar a contagem crua e vir 5, isso **não** é resíduo do motor; a contagem correta para auditar esta
story é `WHERE pncp_id LIKE 'LI-TEST-%'`. Essas mesmas 5 linhas são a causa de TD-LI-6.

### Suíte completa (DoD) e comparação com baseline

```
$ python3 -m pytest tests/ -q --tb=no
1 failed, 6373 passed, 303 skipped, 11 deselected, 10 errors in 429.91s
```
**Re-execução em 2026-09-02 (v1.7), após a remoção da §9 — leitura honesta:**
```
$ REQUIRE_REAL_DB=1 python3 -m pytest tests/ -q --tb=no
17 failed, 6540 passed, 128 skipped, 11 deselected, 2 errors   # 1a execução
13 linhas FAILED/ERROR                                          # 2a execução, mesma árvore/env
```
Três leituras que o @qa precisa ter, nenhuma delas favorável a mim:
1. **O baseline da v1.5 não é comparável.** Ele rodou **sem** `REQUIRE_REAL_DB=1` (303 skipped vs 128 agora) — todos os testes `real_db`, inclusive os do motor, eram pulados. Logo não existe "falha nova vs. baseline" a declarar em nenhuma direção; existe uma **condição recém-exercitada**.
2. **A suíte é não-determinística neste banco compartilhado** (17 vs 13 falhas em duas execuções idênticas). Uma execução isolada não é evidência de nada aqui.
3. **Uma das falhas é do motor:** `test_blocked_when_watermark_is_missing`. Reproduzida deterministicamente — com as 5 linhas residuais alheias em `pncp_raw_bids` o teste falha mesmo rodando o arquivo sozinho (`READY_CANONICAL` != `BLOCKED`); com a tabela limpa, passa. Causa e não-corrigibilidade nesta story: **TD-LI-6**. As demais 12–16 falhas não têm relação com o motor (`golden_path_*`, `entity_resolver`, `weekly_cycle`, `live_consulting_pack`, `crawl_runtime_queue`, `canonical_entity_linkage`, `commercial_leads`).

**Registro da v1.5 (sem `REQUIRE_REAL_DB=1`), mantido para auditoria:** as 11 falhas/erros foram reproduzidas **de forma idêntica** em worktree pristino de `HEAD`
(`git worktree add ... HEAD --detach`): `BLOCKED_CODE_EXECUTION_SHA_MISMATCH` do gate de campanha,
`MissingDsnError` de `coverage_live_proof` e `assert 0 == 12` de `test_live_consulting_pack`
(banco vazio). **Pré-existentes — zero regressão introduzida por esta story.**

### Propriedade de atomicidade do snapshot (para o @qa)

`build_snapshot()` computa **todos** os hashes antes de qualquer escrita, e `_persist()` executa
delete-e-insert de header, opportunities, companies e fits sob um único `conn.commit()` no fim.
Consequências verificáveis: (1) falha no meio da persistência não deixa snapshot parcial;
(2) header e filhos **não podem** divergir dos hashes por construção — o `verifier.py` re-deriva
sobre o conteúdo persistido e é a prova independente disso.

### Dívida técnica registrada (com owner e severidade)

| # | Item | Owner | Severidade |
|---|---|---|---|
| TD-LI-1 | ~~AC2 não executado~~ — **promovido pelo @po (v1.6) a story de follow-up bloqueante** [`story-confenge-live-intelligence-outbound-equivalence-gate.md`](story-confenge-live-intelligence-outbound-equivalence-gate.md). Deixa de ser linha de dívida | @po (criar story) / @architect / @devops (2º DSN) | **BLOQUEANTE** para operacionalização |
| TD-LI-2 | ~~§9 da migration 104 (`ALTER DEFAULT PRIVILEGES`) é inerte no PG16~~ — **RESOLVIDO (2026-09-02)**: @data-engineer removeu a §9 da 104. A barreira passa a ser feita exclusivamente pelos REVOKE explícitos por objeto, agora provados por statement em `test_104_barrier_is_explicit_revokes_without_default_privileges` | @data-engineer | RESOLVIDO |
| TD-LI-3 | ~~Correção do rollback (seção 3) feita pelo @dev precisa de confirmação da autoridade de DDL~~ — **RESOLVIDO (2026-09-02)**: @data-engineer reescreveu a seção 3 do rollback (vazia, sem nada a reverter, com a condição de retorno documentada) | @data-engineer | RESOLVIDO |
| TD-LI-4 | `pncp_raw_bids` sem versionamento temporal — replay as-of histórico é detectável, não prevenível | @data-engineer | MEDIUM |
| TD-LI-5 | Kill switch próprio quando o motor for operacionalizado (cron/systemd) | @devops | MEDIUM |
| TD-LI-6 | `test_blocked_when_watermark_is_missing` depende de `pncp_raw_bids` **livre de linhas alheias**. Passa isolado; falha em execução da suíte completa sob `REQUIRE_REAL_DB=1`, porque testes não relacionados (`golden_path_*`, `crawl_runtime_queue`, `entity_*`) deixam linhas residuais no banco compartilhado e elas produzem watermark real ⇒ `READY_CANONICAL` em vez de `BLOCKED`. **Não é corrigível dentro desta story:** `fetch_source_watermark()` deriva o watermark de `MAX(updated_at)` sobre `pncp_raw_bids`, então estabelecer a pré-condição exigiria DELETE não escopado ao prefixo `LI-TEST-` numa tabela de `forbidden_write_targets` — a direção de falha escolhida (falhar em vez de apagar dado alheio) está documentada no docstring do teste e é deliberada. **Cobertura de AC8 não fica descoberta:** o ramo `BLOCKED` continua provado por `test_blocked_when_as_of_is_missing` e `test_blocked_snapshot_is_persisted_with_blockers`; apenas o gatilho *watermark ausente* fica inverificável em banco poluído. Correção adequada = isolamento de banco por teste (mesmo insumo do follow-up bloqueante: 2º DSN descartável) | @qa / @devops (2º DSN) | MEDIUM |

| TD-LI-7 | **RESOLVIDO na v1.11 (@dev).** Correção: `today_utc()` → `today_cutoff_tz()` em `conftest.py`, derivando de `ZoneInfo(CUTOFF_TIMEZONE)` com `CUTOFF_TIMEZONE` **importado por nome** de `scripts.confenge_live_intelligence.schema` — a mesma constante que `pin_session_timezone()` usa e que `policy_hash()` sela; zero segundo literal de fuso no fixture. 5 call sites atualizados. `scripts/confenge_live_intelligence/**` não tocado. Guarda determinística nova (`test_fixture_civil_date_matches_the_engine_timezone`) torna a prova independente da hora do relógio. Re-medição **dentro da janela de manifestação** (`current_date`=2026-09-03 vs SP=2026-09-02): `1 failed / 121 passed` — a falha de TD-LI-7 desapareceu, resta apenas TD-LI-6. 3 testes de AR-1 verdes isolados. Controle negativo (derivação UTC reintroduzida em memória) reproduz `2 failed`, provando que o verde é atribuível à correção. Ver §"TD-LI-7 — correção e re-medição (v1.11)". **Histórico do item abaixo, para auditoria.** ACHADO na v1.9. RULADO NA v1.10: CORRIGIR NESTA STORY, escopo autorizado (RULING-LI-04) — NÃO é dívida aceitável. `test_as_of_recovers_row_excluded_by_the_view` (`test_sources_as_of.py:33`) falha por **fronteira de fuso no fixture**, não por poluição de banco e não por defeito do motor. `today_utc()` (`conftest.py:136`) devolve a data em **UTC**, mas `live_open_opportunities_as_of()` resolve a data civil em **`America/Sao_Paulo`** (`pin_session_timezone`, AC5) — de propósito e corretamente. Entre ~21:00 e 00:00 UTC as duas datas divergem em 1 dia: medido em 2026-09-03 00:24 UTC → `current_date`=2026-09-03 e `(now() AT TIME ZONE 'America/Sao_Paulo')::date`=2026-09-02. Janela de ~3h/dia ⇒ verde nas execuções anteriores. **CORREÇÃO DO @po ao texto original:** (a) a alegação "cobertura de AC4 não fica descoberta porque `test_as_of_current_date_equals_canonical_view` continua provando a generalização estrita" **está superestimada** — esse teste **também** chama `today_utc()` (`:52`), assim como `test_session_timezone_is_pinned_before_reading` (`:60`); ele sobrevive à janela por sorte da distribuição do seed (`+30d`/`−10d` longe da fronteira), **não** por imunidade, logo a cobertura de AC4 não é independente do defeito; (b) `today_utc()` é chamada em `test_no_outbound_write_runtime.py:128` e `:183`, isto é, **dentro da única evidência de AR-1**, ação BLOQUEANTE do gate HIGH-RISK — o defeito contamina a prova do gate, não apenas um teste de leitura. Por (a)+(b) e pela ausência de identidade de causa raiz com RULING-LI-03 (aqui não falta insumo externo algum), o item **não** se classifica como dívida. Correção exigida: a data civil do teste deve derivar da **mesma fonte de fuso que o motor fixa**, sem segundo literal de `ZoneInfo` no fixture; `scripts/confenge_live_intelligence/**` não deve ser tocado; re-medição obrigatória da suíte do motor | @dev (correção, escopo autorizado v1.10) / @qa (classificação) | **HIGH** (era MEDIUM; elevado por contaminar a evidência de AR-1) |

Nenhum `TODO`/`FIXME` foi deixado no código.

### AR-1 e AR-2 — ações BLOQUEANTES do gate HIGH-RISK do @architect: RESOLVIDAS (@dev, v1.9)

Gatilho: veredito **INACEITÁVEL COM AÇÃO REQUERIDA** do @architect sobre o AC2/AC11,
registrado em `docs/architecture/adr/ADR-040-confenge-live-intelligence-foundation.md`,
§"Gate HIGH-RISK de arquitetura sobre o reescopo do AC2". Status revertido
InReview → InProgress para executá-las. AR-3, AR-4 e AR-5 **não** foram tocadas —
não são bloqueantes e AR-5 não é tarefa atribuída ao @dev.

**O achado era correto e foi confirmado por leitura.** `producer.py:502-513` continha
exatamente a idiom descrita: uma tupla local de nomes de tabela (literais **sem** verbo
DML) interpolada em `f"DELETE FROM public.{table} WHERE snapshot_id = %s"` (verbo DML
**sem** nome de tabela). A verificação do AC11 é por literal único contendo ambos ⇒ a
idiom passava por ela. Verificado também que **não havia escrita proibida viva**: a tupla
continha só `confenge_live_intelligence_*`. O defeito era de **prova**, não de comportamento
— que é precisamente o que o @architect afirmou.

**Varredura completa de SQL dinâmico no módulo** (AST: `JoinedStr`, `.format()`, `%`, `+`):
o único DML construído dinamicamente em `scripts/confenge_live_intelligence/**` era
`producer.py:511`. As demais interpolações são SELECT (`sources.py:70` `{AS_OF_FUNCTION}`,
`sources.py:92` `{CONTRACTS_VIEW}`, `sources.py:110` `LIMIT`) ou mensagens de erro.

#### AR-2 — allowlist única para DML interpolado

| Peça | Onde |
|---|---|
| Única enumeração literal de alvos de escrita | `schema.py` → `WRITE_TARGET_ORDER` (6 tabelas `confenge_live_intelligence_*`, na ordem de DELETE segura para as FKs) |
| Conjunto de membresia, **derivado** (não uma segunda lista) | `schema.py` → `ALLOWED_WRITE_TARGETS = frozenset(WRITE_TARGET_ORDER)` |
| Validação em runtime antes de executar DML | `schema.py` → `assert_write_target()`, levanta `OutboundWriteAttemptError` (fail-closed) |
| Exportação pelo pacote (exigida pelo texto de AR-2) | `__init__.py` → `__all__` |
| Consumo | `producer.py::_persist` → `for table in WRITE_TARGET_ORDER: cur.execute(f"DELETE FROM public.{assert_write_target(table)} ...")`. A tupla local foi **removida**; o DELETE de `confenge_live_intelligence_snapshots`, antes um literal separado, entrou na mesma ordem (último, por FK) |
| Prova estática com dentes | `test_no_outbound_dml_static.py` → `_dynamic_dml_violations()` (função **pura**, auto-testável) |

Regra que o checker impõe a **todo** módulo do glob: para todo DML construído
dinamicamente, cada slot interpolado tem de (a) passar por `assert_write_target()` e
(b) resolver a uma constante da allowlist **importada por nome** de
`scripts.confenge_live_intelligence` e **não re-vinculada** no módulo. Os identificadores
sancionados são **derivados** de `engine_pkg.__all__` em tempo de teste — uma lista escrita
à mão no arquivo de teste seria uma segunda allowlist e o teste passaria a proteger a si
mesmo em vez de proteger o motor.

**O critério de aceite explícito do @architect** ("uma tupla local nova em `events.py` tem
de quebrar o teste, não passar por ele") é provado por
`test_checker_rejects_every_known_evasion`, **10** casos, cada um uma fonte sintética
rodada contra o checker: `tupla_local` (o cenário nomeado), `slot_sem_guarda`,
`parametro_de_funcao`, `allowlist_sombreada`, `constante_estrangeira`, `format`,
`percent`, `concatenacao`, `acumulacao_augassign`, `acumulacao_join`.

**Família de acumulação — buraco encontrado e fechado antes de declarar AR-2 pronto.**
A primeira versão do checker olhava `JoinedStr`, `.format()`, `%` e `+`, e por isso
deixava passar `sql = "DELETE FROM public."; sql += table` e
`"".join(["DELETE FROM public.", table])`: em nenhum nó da AST o verbo DML e o slot
coexistem. O idiom **já existe neste pacote** (`sources.py:110`, `sql += f" LIMIT ..."`,
sobre um SELECT), logo era o caminho natural para `events.py`. `_accumulation_violations()`
impõe agora proibição plana: DML não pode ser montado por `+=` nem por `join()` — o
statement dinâmico tem de ser **uma expressão única**, onde a regra da allowlist é
verificável. A guarda é disparada pelo verbo DML, então a acumulação SELECT-only de
`sources.py` não produz falso positivo (confirmado: controle positivo verde sobre o glob real). `test_checker_accepts_the_sanctioned_idiom` é o controle
negativo do controle — impede que o checker degenere em rejeitar tudo.

**Fechamento do buraco de um nível acima** (o modo de falha que o @architect nomeou:
"sem essa amarração, AR-2 apenas reproduz o defeito do AC11 um nível acima"):
`test_write_allowlist_is_disjoint_from_outbound_tables` exige
`ALLOWED_WRITE_TARGETS ∩ OUTBOUND_TABLES = ∅` **e** que todo alvo comece com
`confenge_live_intelligence_`. Sem isso, bastaria acrescentar `opportunity_intel` à
allowlist para manter tudo verde.
`test_write_guard_rejects_outbound_target_at_runtime` cobre a metade de runtime sem banco.

**AR-1+AR-2 fechados NÃO equivalem a gate fechado.** O encaminhamento do próprio gate
exige AR-1 **e** AR-2 **e** a **condição AR-5**. Estado verificado de AR-5 em 2026-09-03:
`docs/stories/story-confenge-live-intelligence-outbound-equivalence-gate.md` **existe** —
foi criado pelo @sm em resposta a AR-5, está em `Draft`, ainda não validado pelo @po e ainda
untracked no git. Ou seja, a parte de AR-5 que o @architect nomeou ("um débito que referencia
uma story que não está no backlog") **deixou de valer**: o artefato não é mais inexistente.
Mas o artefato está em `Draft`, e julgar se isso satisfaz a condição do gate é autoridade do
@architect, não do @dev — assim como criar e validar o artefato é do @sm/@po conforme
RULING-LI-02. Registrado como `architect_gate.gate_satisfied: false` no state file **por
indeterminação declarada**, não por afirmação de que AR-5 falhou: serve para impedir que
alguém leia `AR-1: RESOLVIDO` + `AR-2: RESOLVIDO` como gate fechado.

> **SUPERADO pelo fechamento do gate (@architect, 2026-09-02) — nota do @dev, v1.11.** A
> indeterminação de AR-5 registrada acima **foi resolvida pelo @architect**, que fechou o
> gate: `architect_gate.gate_satisfied: true`, por **verificação independente** (leitura de
> código + execução própria: 3 passed em AR-1, 41 passed em AR-2, 15/15 objetos de
> `PROTECTED_OBJECTS` medidos presentes). Sobre AR-5, o @architect decidiu que a condição
> escrita pelo gate era de **existência** do artefato e que `Draft` a satisfaz — exigir
> validação do @po estenderia a própria condição e usurparia autoridade do @po. AR-3 e AR-4
> permanecem **abertas como dívida (CONCERNS)**, como o encaminhamento original já admitia.
> O selo do @architect declara seus próprios limites: **não** é veredito de qualidade
> (`PASS`/`CONCERNS`/`FAIL` segue autoridade exclusiva do @qa). Fonte: ADR-040, §"Fechamento
> do gate HIGH-RISK", e `architect_gate.gate_satisfied_note` no state file. O parágrafo acima
> fica preservado como registro do estado em que o @dev o escreveu, não como estado vivo.
>
> **Condição que o @architect anexou ao selo, e que esta rodada cumpre.** O campo
> `td_li_7_effect_on_ar1_evidence` determina: *"a correção altera `today_utc()`, chamada
> dentro do arquivo de evidência de AR-1, portanto a re-medição obrigatória do @dev TEM DE
> INCLUIR os 3 testes de AR-1; se regredirem, este selo cai com eles."* Os 3 testes foram
> re-medidos, **isoladamente e em suíte: 3 passed**. Nenhum regrediu — o selo não cai.
>
> **Divergência técnica registrada, sem reabrir nada.** O @architect mediu que a evidência de
> AR-1 é **estruturalmente insensível** ao deslocamento de fuso (seed em `now+30d`, state
> governado por presença de watermark, asserção incondicional; sonda em `--effective-date`
> delta −1/0/+1 → `READY_CANONICAL` nos três casos), o que **contradiz o fundamento (b)** de
> RULING-LI-04. O próprio @architect declara o limite do achado: os fundamentos (a), (c) e
> (d) sustentam o ruling por si sós, **RULING-LI-04 permanece de pé e vinculante**, e a
> correção de TD-LI-7 seguia obrigatória. Esta rodada a executou. A medição do @architect é
> **consistente** com a desta rodada: o ramo condicional de `verify` foi executado.

#### AR-1 — smoke de não-interferência em runtime

`tests/confenge_live_intelligence/test_no_outbound_write_runtime.py` (novo, `real_db`).

- **Cobertura:** todos os **15** objetos de `PROTECTED_OBJECTS` (importados de
  `tests/test_live_intelligence_outbound_equivalence.py`, sem lista paralela) que existem
  no banco — tabelas **e** views, conforme AR-1 ("cada objeto da lista protegida do AC1"),
  não apenas as 7 tabelas. Confirmado por `pg_class`: 15/15 presentes.
- **Instrumento:** `COUNT(*)` + `md5(string_agg(t::text ORDER BY t::text))` por objeto.
  Ordena por `t::text` e não por `ctid` para cobrir views e para não depender da ordem
  física das linhas.
- **Janela:** abre **depois** do `seed_bid()` e fecha **depois** do producer, exatamente
  como AR-1 determina — a fixture escreve em `pncp_raw_bids` sob a exceção `LI-TEST-`
  (RULING-LI-02) e envolver o seed produziria falha confusa atribuída ao motor.
  `conn.commit()` antes e depois, para comparar estado commitado e não segurar lock contra
  a conexão do CLI.
- **Execução real:** `cli build` (código 0, `state=READY_CANONICAL`) + `cli verify`
  completos, via `cli.main()` com `--created-by LI-TEST-ar1-runtime-smoke` (prefixado, para
  que o teardown da fixture o alcance).
- **Asserção P0 incondicional:** checksums idênticos byte-a-byte antes/depois. Vale também
  no caminho `BLOCKED`. **Só** a asserção sobre `cli verify` é condicionada a o build ter
  alcançado estado verificável — sob `pncp_raw_bids` poluída o build pode fechar `BLOCKED`
  (TD-LI-6) e `verify` falharia por motivo alheio à claim. Condicionalidade **declarada**
  no docstring do módulo, não silenciosa.
- **Anti-vacuidade** (`test_engine_did_write_its_own_tables_in_the_same_run`): se o build
  não escrevesse nada, os checksums outbound seriam idênticos trivialmente. Prova que o
  mesmo caminho de código persistiu seu próprio snapshot.
- **Dentes do instrumento** (`test_fingerprint_detects_a_single_row_change`): um checksum
  cego passaria sempre. Semeia uma linha `LI-TEST-` em `pncp_raw_bids` (única tabela
  protegida com autorização de escrita neste ciclo, por prefixo) e exige que o fingerprint
  **mude**. A cláusula de ausência de efeito colateral incide sobre as **tabelas base**:
  `v_open_opportunities_canonical` muda **por construção** quando `pncp_raw_bids` muda —
  isso é propriedade da view, não escrita.

**Por que AR-1 é mais forte que a prova estática:** não inspeciona código. Um caminho de
escrita construído de forma que o parser não reconheça continuaria invisível a AC11 e a
AR-2, mas não ao conteúdo observado das tabelas. Objetos protegidos não-vazios no momento
da medição (⇒ checksum não-vácuo): `opportunity_intel`=5,
`confenge_company_target_fit_current`=14, `confenge_company_target_fit_history`=24,
`confenge_target_fit_dirty`=14, `confenge_target_fit_events`=20,
`confenge_company_sector_current`=2, `confenge_company_sector_history`=2,
`v_open_opportunities_canonical`=1, `pncp_raw_bids`=6, `sc_public_entities`=1.

#### Evidência de execução (v1.9)

```
REQUIRE_REAL_DB=1 LOCAL_DATALAKE_DSN="postgresql://test:test@127.0.0.1:5433/extra_test" \
  python3 -m pytest tests/confenge_live_intelligence/ \
    tests/test_live_intelligence_outbound_equivalence.py -q --tb=short
→ 2 failed, 119 passed
```

`ruff check` e `ruff format --check` limpos (18 arquivos).

**As 2 falhas são pré-existentes e independentes de AR-1/AR-2**, medido por controle:
a mesma suíte **sem** o arquivo novo de AR-1 dá `2 failed, 116 passed` — as **mesmas** duas
falhas, os mesmos módulos, as mesmas mensagens. Os 3 testes de AR-1 e os 23 de AR-2 passam (o arquivo do AC11 vai de 18 para 41 testes).

| Falha | Causa raiz | Registro |
|---|---|---|
| `test_blocked_when_watermark_is_missing` | 5 linhas alheias em `pncp_raw_bids` (`777-1-1/2026`, `88888888888888-1-000099/2026`, `REALDB-IDEMPOTENCY-001`, `REALDB-SNAPSHOT-001`, `SYNTH-EDITAIS-REPORT-0001`) produzem watermark real | **TD-LI-6**, já rulado dívida aceitável (RULING-LI-03) |
| `test_as_of_recovers_row_excluded_by_the_view` | Fronteira de fuso **no fixture**: `today_utc()` em UTC vs. as-of em `America/Sao_Paulo`; janela de 3h/dia | **TD-LI-7** — **CORRIGIDO na v1.11** (RULING-LI-04). Ver §"TD-LI-7 — correção e re-medição". Medição superada |

**Resíduo do motor: zero.** Após a suíte: `LI-TEST-` em `pncp_raw_bids`=0,
`confenge_live_intelligence_snapshots`=0. Tabelas outbound com as **mesmas** contagens de
antes da execução (`confenge_target_fit_dirty`=14, `opportunity_intel`=5,
`sc_public_entities`=1) — nenhuma escrita nas 7 tabelas protegidas, conforme a regra dura.

#### Por que o status NÃO subiu para InReview nesta rodada (v1.9 — **SUPERADO pela v1.11**)

> **Nota de leitura ao @qa (v1.11):** esta subseção descreve a decisão da v1.9 e **não
> está mais viva**. TD-LI-7 foi corrigido nesta rodada (RULING-LI-04) e a medição
> `2 failed / 117 passed` está **superada** — ver §"TD-LI-7 — correção e re-medição
> (v1.11)" imediatamente abaixo. A única falha remanescente é TD-LI-6, já rulado dívida
> aceitável pelo @po (RULING-LI-03).

AR-1 e AR-2 estão implementadas, testadas e verdes. O gate de conclusão, porém, é
**conjuntivo**: ações fechadas **e** suíte verde. A suíte do motor está `2 failed / 117
passed`. Nenhuma das duas falhas é de AR-1/AR-2 e nenhuma é corrigível dentro do escopo
autorizado desta rodada (TD-LI-6 exige 2º DSN, insumo de @devops; TD-LI-7 é correção de
outro teste, fora de AR-1/AR-2 e sem autorização de ampliação de escopo). Subir para
InReview afirmando suíte verde seria selo sem evidência. O `next_agent` é o @po, a quem
cabe rular TD-LI-7 pelo mesmo mecanismo com que rulou TD-LI-6 — decisão de escopo, não
do @dev.

### TD-LI-7 — correção e re-medição (@dev, v1.11)

Executa RULING-LI-04 (@po, v1.10): TD-LI-7 é correção obrigatória nesta story, dentro do
escopo já autorizado. `scripts/confenge_live_intelligence/**` **não** foi tocado — a
função as-of está correta e alterá-la seria regressão, como o ruling determina.

#### A correção

`today_utc()` foi substituída por `today_cutoff_tz()` em `conftest.py`:

```python
from scripts.confenge_live_intelligence.schema import CUTOFF_TIMEZONE

def today_cutoff_tz() -> date:
    return datetime.now(tz=ZoneInfo(CUTOFF_TIMEZONE)).date()
```

**A propriedade de aceite do @po está atendida, e é o ponto do item.** O nome do fuso é
**importado por nome** de `scripts.confenge_live_intelligence.schema.CUTOFF_TIMEZONE` — a
**mesma** constante que `sources.pin_session_timezone()` usa como default e que
`schema.policy_hash()` sela no snapshot. Nenhum segundo literal `"America/Sao_Paulo"` foi
escrito no fixture. Uma segunda fonte de verdade reabriria exatamente o modo de falha que
AR-2 acabou de fechar para a allowlist de escrita: teste e motor voltariam a poder
divergir sem que nada quebrasse.

**Renomeação, não alias.** O nome `today_utc` passaria a mentir sobre o que a função faz;
manter um alias criaria dois nomes para uma derivação. Os 5 call sites nomeados no ruling
foram atualizados: `test_sources_as_of.py:22,52,60` (**medido** após a inserção do novo
teste: agora `:54,:84,:92`) e `test_no_outbound_write_runtime.py:128,183` (linhas
inalteradas). O novo teste usa a função em `:41,:42`. Varredura repo-wide
confirma zero ocorrência remanescente de `today_utc` sob `tests/` e `scripts/`.

#### A guarda determinística — por que "a suíte ficou verde" não seria evidência

TD-LI-7 se manifesta em ~3h/dia. **Fora** dessa janela, código corrigido e código
defeituoso produzem resultados idênticos: uma execução verde às 14:00 UTC não discrimina
nada. Para que a correção não dependa da hora do relógio, foi adicionado
`test_fixture_civil_date_matches_the_engine_timezone` (`test_sources_as_of.py`), que
compara a data do fixture com a data civil que o **próprio banco** resolve sob
`CUTOFF_TIMEZONE` — a mesma resolução que `live_open_opportunities_as_of` faz
internamente. Vale a **qualquer hora** e cobre, de lambuja, uma lacuna que a derivação
puramente em Python deixaria: divergência entre a tzdata do Python e a do PostgreSQL.

#### Re-medição — executada DENTRO da janela de manifestação

A medição foi feita de propósito dentro da janela, o que a torna **discriminante**:

| Grandeza | Valor medido |
|---|---|
| `now() AT TIME ZONE 'UTC'` (banco) | `2026-09-03 00:56:08` |
| `current_date` (banco, sessão `Etc/UTC`) | `2026-09-03` |
| `(now() AT TIME ZONE 'America/Sao_Paulo')::date` | `2026-09-02` |
| Datas divergem? | **SIM** — janela ativa |

**Contagem nova (supera `2 failed / 119 passed` da v1.9):**

```
REQUIRE_REAL_DB=1 pytest tests/confenge_live_intelligence/ \
  tests/test_live_intelligence_outbound_equivalence.py -q
→ 1 failed, 121 passed in 70.82s
```

A falha 2 (TD-LI-7) **desapareceu**, como o ruling previa. A única falha restante é
`test_blocked_when_watermark_is_missing` = **TD-LI-6**, já rulado dívida aceitável
(RULING-LI-03), com a mesma causa raiz e o mesmo owner (@devops / 2º DSN). Total sobe de
121 para 122 itens: +1 é a guarda determinística nova.

**Os 3 testes de evidência de AR-1 passam** — rodados também isoladamente, como exige a
condição de o defeito ter contaminado a prova do gate BLOQUEANTE:

```
pytest tests/confenge_live_intelligence/test_no_outbound_write_runtime.py -v
→ 3 passed in 71.65s
  test_build_and_verify_leave_every_protected_object_byte_identical  PASSED
  test_engine_did_write_its_own_tables_in_the_same_run               PASSED
  test_fingerprint_detects_a_single_row_change                       PASSED
```

**Controle negativo — a evidência que fecha o argumento.** Verde por si só ainda seria
compatível com "o teste não prova nada". Reintroduzindo em memória a derivação UTC
antiga (via plugin de pytest, sem editar arquivo), na mesma hora e no mesmo banco:

```
→ 2 failed, 4 passed
  FAILED test_fixture_civil_date_matches_the_engine_timezone
         AssertionError: fixture resolveu 2026-09-03 e o banco resolveu 2026-09-02
                         sob America/Sao_Paulo
  FAILED test_as_of_recovers_row_excluded_by_the_view
         AssertionError: leitor as-of nao recuperou a linha excluida pela view
```

Isto é: com o defeito, o teste original de TD-LI-7 falha com a mensagem exata do achado
original **e** a guarda nova acusa; com a correção, ambos passam. O verde é atribuível à
correção, não à hora do relógio.

#### Nota sobre a fronteira de `CURRENT_DATE` na evidência de AR-1

`v_open_opportunities_canonical` está em `PROTECTED_OBJECTS` e filtra por `CURRENT_DATE`,
então seu fingerprint poderia mudar sozinho na virada do dia — o próprio teste avisa
disso na mensagem de falha. Verificado que isso **não** foi movido pela correção:
`li_cli.main()` abre a **própria** conexão (`cli.py::_connect`), logo a sessão de
`live_conn` conserva o mesmo `TimeZone` (`Etc/UTC`, default do banco) nas duas capturas
de fingerprint — `antes` e `depois` são resolvidos sob o mesmo fuso. O que a correção
muda é o `--effective-date` passado ao `build`, não a resolução do fingerprint.

**Efeito colateral declarado:** como o `as_of` entregue ao `cli build` mudou de `D` para
`D-1` durante a janela, `payload["state"]` poderia mudar e com ele a execução do ramo
**condicional** `verify_code == 0`. Medido: o build fechou em estado verificável e a
asserção de `verify` foi executada nas duas execuções (isolada e em suíte) — o ramo
condicional **não** foi perdido silenciosamente.

#### Regra dura — reverificada após a re-medição

| Verificação | Valor |
|---|---|
| `LI-TEST-` em `pncp_raw_bids` | **0** |
| `confenge_live_intelligence_snapshots` | **0** |
| `confenge_target_fit_dirty` | **14** (inalterado) |
| `opportunity_intel` | **5** (inalterado) |
| `sc_public_entities` | **1** (inalterado) |

`ruff check` e `ruff format --check` limpos sobre `tests/confenge_live_intelligence/`.
Nenhum arquivo SQL e nenhum arquivo de `scripts/confenge_live_intelligence/**` tocado.

### REL-001 / TEST-001 / REL-002 — correção do FAIL de QA (@dev, v1.13, iteração 1/5 do QA Loop)

**Escopo estrito:** apenas os 3 bloqueadores de `return_to_dev.required_fixes` do gate.
Nada de `SEC-001`, `SEC-002`, `TEST-002..005`, `ARCH-001`, `REQ-001`, `REL-003`,
`DOC-001..003`, `MNT-001..007` foi tocado. `TD-LI-6` e `RULING-LI-01..04` permanecem
como estão. A migration 104 e o rollback **não** foram tocados (`scope_note` do gate).

#### REL-001 — `source_as_of` deriva do watermark observado da fonte

`project_opportunity()` e `project_companies()` passaram a receber `source_as_of` como
**parâmetro obrigatório**. O único produtor desse valor é
`sources.fetch_source_watermark(conn, "pncp")["watermark_at"]` — o `MAX(updated_at)` que
o gate apontou como já computado e descartado (`aggravating` de REL-001). Removidos os
três `datetime.now(tz=UTC)` do caminho de projeção. **Sem fallback de relógio de parede:**
ausência de watermark curto-circuita em `BLOCKED` **antes** de qualquer projeção.

Removido o parâmetro `require_watermark`: com o watermark load-bearing como proveniência
de `source_as_of`, "projetar sem watermark" deixou de ser um estado representável. Era a
única via pela qual um relógio de parede voltaria a ser necessário.

**[AUTO-DECISION]** Fonte do watermark do lado COMPANY (o gate deixa a decisão ao @dev,
`suggested_action` (1) de REL-001) → **o mesmo watermark de `fetch_source_watermark`, nos
dois sítios**, literalmente o que o gate escreve ("reusando o valor já retornado por
`fetch_source_watermark`", nomeando `producer.py:182-184` **e** `producer.py:260`).
Motivo: (a) ambos os planos são da fonte `pncp`; (b) a alternativa — um segundo watermark
sobre `pncp_supplier_contracts` — abriria **nova superfície de leitura** na base outbound,
o que exige @architect e não está em `scope_files`; (c) um único watermark por build é a
proveniência que §3 do impact-analysis exige sem criar segunda fonte de verdade.

**[AUTO-DECISION]** Corrigir agora (e não como follow-up) os dois sítios que **não** estavam no
gate — `sources.fetch_source_watermark` (pin de fuso) e `verifier._rebuild_*` (normalização no
read-back). Critério aplicado: (a) são a **mesma classe de defeito** que o bloqueador em reparo,
não achados independentes — ambos quebram a igualdade de hash para o mesmo instante; (b) os dois
arquivos **já constam de `scope_files`** (`sources.py`, `verifier.py`), logo não há ampliação de
autoridade; (c) deixá-los fora entregaria a correção de REL-001 com a metade de leitura ainda
quebrada — o `snapshot_id` ainda divergia entre replays só com o pin ausente (medido), e o verify
falharia fechado sobre snapshot íntegro. É exatamente o critério oposto ao que manteve
SEC-001/SEC-002/TEST-002..005/ARCH-001/REQ-001/DOC-001..003/MNT-001..007 intocados: esses são
classes **distintas** do bloqueador, com owner e prazo próprios no gate file. Todos os 6 arquivos
tocados nesta rodada constam de `scope_files`.

**Defeito adicional encontrado pela prova (não estava no gate, mesma classe de REL-001):**
`fetch_source_watermark` lia `MAX(updated_at)` (`TIMESTAMPTZ`) **sem** fixar o `TimeZone`
da sessão — violando o invariante declarado no docstring de `sources.py`. O primeiro build
lia o watermark antes de qualquer pin; o segundo, com a sessão já em `CUTOFF_TIMEZONE`. O
driver devolvia **o mesmo instante com `tzinfo` diferente**, e como `live_hash` serializa
`datetime` por `isoformat()`, o hash divergia de novo — REL-001 por outra via, que a
correção do relógio de parede **não** cobria (medido: `snapshot_id` ainda divergia com os
três `datetime.now()` já removidos). Corrigido nas duas frentes, por serem independentes:
`pin_session_timezone()` antes da leitura do watermark, e `normalize_source_as_of()`
(→ UTC) no ponto de construção dos dois objetos, tornando o hash função do **instante** e
não do fuso da sessão — a mesma propriedade que o AC5 exige do `universe_hash`.

Registrado explicitamente em `_persist`: `cutoff_at` / `closed_at` / `recorded_at` são
colunas de **auditoria** e não entram em `universe_hash_of`, `data_hash_of`, `fit_hash_of`,
`content_hash_of` nem nos hashes de linha (`*_PAYLOAD_KEYS`). O relógio de parede que
permanece ali é, por desenho, reescrito sob o **mesmo** `snapshot_id` no replay.

#### TEST-001 — propriedade de aceite que exercita a PROJEÇÃO

`test_replay_is_idempotent_for_the_same_universe` (vácuo) foi **substituído** por
`test_replay_over_the_real_projection_is_idempotent`: dois `build_snapshot()` **sem**
universo injetado, mesmo seed e mesmo `as_of`, **sem** fixar `source_as_of`. Assere
igualdade de `snapshot_id`, `content_hash`, `data_hash`, `universe_hash`; e a contagem
**TOTAL** de linhas das 6 tabelas do motor **sem filtro de `snapshot_id`** mais
`COUNT(DISTINCT snapshot_id) == 1`. O filtro `WHERE snapshot_id = %s` do teste antigo era
precisamente o que tornava a acumulação invisível: as linhas extras caíam sob **outro**
`snapshot_id`. Guardas anti-vacuidade: `state != BLOCKED`, `observed_opportunity_count >= 1`
e "o 1º build persistiu algo".

Adicionado `test_company_projection_source_as_of_comes_from_the_source_watermark`. Razão:
`v_contracts_canonical_v2` tem **0** linhas com fornecedor no DSN documentado (medido), logo
`project_companies` retorna `[]` e o teste de replay **não alcança** `producer.py:260` — o
sítio que o gate classifica como "SEMPRE relógio de parede, sem fallback". Sem este segundo
teste, a propriedade de aceite escrita no gate estaria satisfeita **provando metade do bug**.
As linhas são sintéticas em memória (semear `pncp_supplier_contracts` seria escrita no plano
outbound, proibida por AR-1/AR-2) e o `source_as_of` é **re-lido** do watermark real a cada
chamada — nada pinado à mão.

**Checagem de mutação (o que faltava ao teste antigo).** Cada sítio revertido
individualmente, com o resto da correção no lugar:

| Mutação | Teste que detectou | Resultado |
|---|---|---|
| `producer.py` sítio OPPORTUNITY → `datetime.now(tz=UTC)` | `test_replay_over_the_real_projection_is_idempotent` | **FAILED** (1 failed, 1 passed) |
| `producer.py` sítio COMPANY → `datetime.now(tz=UTC)` | `test_company_projection_source_as_of_comes_from_the_source_watermark` | **FAILED** (1 failed, 1 passed) |
| `_blocked_result` → `date.today()` | `test_blocked_as_of_date_is_immune_to_the_os_timezone` | **FAILED** (`{'Pacific/Kiritimati': 2026-09-03, 'Pacific/Niue': 2026-09-02}`) |

#### REL-002 — data civil de `_blocked_result` deriva de `CUTOFF_TIMEZONE`

Novo `producer.today_in_cutoff_timezone()`, com `CUTOFF_TIMEZONE` **importado por nome** de
`schema.py` — a mesma constante que `pin_session_timezone()` usa e que `policy_hash()` sela.
Nenhum segundo literal de fuso no módulo (a proibição que RULING-LI-04 impôs ao fixture,
agora no código de produção).

Propriedade de aceite em duas camadas. (1) `test_blocked_when_as_of_date_is_missing` passou a
assertar `as_of_date == today_cutoff_tz()` **e** a forma do `snapshot_id` — o gate registrou
que o teste "hoje não discrimina". (2) **Mas essa asserção só discrimina dentro da janela de
~3h/dia** em que os dois fusos divergem — medido: a mutação `date.today()` **passou** por ela
no horário desta rodada. Foi por isso que foi adicionado
`test_blocked_as_of_date_is_immune_to_the_os_timezone`: roda o mesmo build sob dois fusos de
SO cujos offsets distam **25h** (`Pacific/Kiritimati` UTC+14, `Pacific/Niue` UTC-11), onde
`date.today()` **nunca** pode dar a mesma data civil. Prova determinística a qualquer hora —
exatamente a lacuna que fez TD-LI-7 custar duas rodadas.

#### Terceiro sítio da mesma classe, encontrado por auditoria própria: o caminho de VERIFY

Depois de corrigir a escrita, verifiquei o **read-back**. `verifier.py` reconstrói os objetos
a partir de `row["source_as_of"]` — coluna `TIMESTAMPTZ`, devolvida pelo driver **no fuso da
sessão corrente** — e re-deriva `opportunity_hash`/`portfolio_hash`. Pela mesma propriedade
de `isoformat()`, isso significa hash diferente para o mesmo instante.

Todos os caminhos verdes existentes **desviavam** do estado que um build real deixa: os testes
do verifier injetam `opportunities=`/`companies=` (nunca chamam `fetch_source_watermark`, logo
nunca pinam a sessão), e `test_no_outbound_write_runtime.py` verifica via `cli verify`, que abre
conexão **nova** (`cli.py::_connect`). Nenhum exercitava build → verify **na mesma conexão**.
Medido nesse cenário, antes da correção:

```
sessao apos build: America/Sao_Paulo
source_as_of lido: 2026-09-02 23:03:23.434134-03:00
VERIFY FALHOU: hash de linha divergente (opportunity, opportunity_hash)
VERIFY CONEXAO NOVA (fuso default): OK      <- por isso passava
```

Ou seja: o verifier falharia **fechado** sobre um snapshot íntegro, e só na conexão que acabou
de construí-lo — a mesma forma de "passa 21 horas por dia" de REL-002. Corrigido aplicando
`normalize_source_as_of()` em `_rebuild_opportunity` e `_rebuild_company` (`verifier.py` já
consta de `scope_files`), com propriedade de aceite em
`test_verify_on_the_same_connection_that_built_the_snapshot`: usa a **projeção real**, assere que
a sessão ficou em `CUTOFF_TIMEZONE` (pré-condição explícita, senão o teste seria vácuo) e verifica
na **mesma** conexão. **Mutação D:** remover a normalização de `_rebuild_opportunity` → esse teste
**FAILED** com a mensagem exata acima; os outros 13 do arquivo continuam passando, o que mostra
que era o único que discriminava.

#### Prova real de idempotência (execução manual, fora da suíte)

Script de prova em scratchpad (não versionado), sobre snapshot sintético `LI-TEST-`, com
contagem **total** por tabela:

```
t0 (antes de qualquer build): opportunities=0  snapshots=0
build #1: LI-2026-10-01-4f7897258475c932295bc19496dde191 READY_CANONICAL | opportunities=1  snapshots=1
build #2: LI-2026-10-01-4f7897258475c932295bc19496dde191 READY_CANONICAL | opportunities=1  snapshots=1
snapshot_id igual: True | content_hash igual: True | data_hash igual: True | contagens iguais: True
snapshots do build: total=1 distinct_snapshot_id=1   → VEREDITO: IDEMPOTENTE
```

Controle negativo (mesmo script, com o sítio OPPORTUNITY revertido a `datetime.now()`):

```
build #2: LI-2026-10-01-68612abf07d77d719987cb2bdcbc9e65 | opportunities=2  snapshots=2
snapshot_id igual: False | contagens iguais: False | total=2 distinct_snapshot_id=2 → VEREDITO: ACUMULOU
```

Isto é a reprodução direta do mecanismo que o gate descreveu: `DELETE ... WHERE snapshot_id`
não encontrava o snapshot anterior e as tabelas do motor acumulavam (1 → 2 linhas por rodada).

#### Re-medição obrigatória (`remeasurement_required` do gate)

Suíte do motor, `REQUIRE_REAL_DB=1 LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test`:

```
pytest tests/confenge_live_intelligence/ tests/test_live_intelligence_outbound_equivalence.py
→ 1 failed, 124 passed
```

A única falha é `test_blocked_when_watermark_is_missing` = **TD-LI-6 / REL-003**, dívida já
rulada (RULING-LI-03) e explicitamente fora desta devolução. Baseline anterior: 1 failed /
121 passed — o delta de +3 são os três testes novos.

**AR-1 isolado** (condição anexada ao selo do @architect):
`pytest tests/confenge_live_intelligence/test_no_outbound_write_runtime.py` → **3 passed**.
Verificado **primeiro**, não por último: o caminho do CLI agora exige watermark, e um seed
que não deixasse `MAX(updated_at)` em `pncp_raw_bids` levaria o build a `BLOCKED` e derrubaria
o selo. `seed_bid` grava `updated_at`, logo o watermark existe e o estado não muda.

**TEST-004 corrigido — regressão dirigida COM o prefixo `REQUIRE_REAL_DB=1`** (a medição fraca
de 391/34 fica registrada como medida sem o prefixo, conforme o gate):

```
REQUIRE_REAL_DB=1 LOCAL_DATALAKE_DSN=... pytest \
  tests/test_golden_path_idempotency.py tests/test_golden_path_snapshot.py \
  tests/test_golden_path_canonical.py tests/test_snapshot_reconciliation.py \
  tests/confenge_outreach_pipeline tests/confenge_target_fit tests/confenge_contact_resolution \
  tests/confenge_account_intelligence tests/confenge_activation \
  tests/confenge_live_intelligence tests/test_live_intelligence_outbound_equivalence.py
→ 2 failed, 540 passed, 8 skipped
```

As duas falhas são as duas já caracterizadas pelo próprio gate: (1)
`test_dual_seed_and_bid_table_no_duplicate_keys` — `assert 1 >= 1000` sobre `sc_public_entities`
em banco sem volume, pré-condição alheia à 104; (2) TD-LI-6. Nenhuma falha nova.

**Lint:** `ruff check` limpo (`scripts/` inteiro + os testes tocados); `ruff format --check`
limpo (18 arquivos).

### Testing

- Localização de testes: `tests/confenge_live_intelligence/` (novo diretório, espelha `tests/confenge_outreach_pipeline/`, `tests/confenge_universe/` já existentes) + `tests/test_live_intelligence_outbound_equivalence.py` na raiz de `tests/` (padrão dos testes de golden path).
- Framework: `pytest`. Rodar localmente com `LOCAL_DATALAKE_DSN` configurado (ver `docs/DEVELOPMENT.md`).
- Testes de migration/grants precisam de banco Postgres real (`python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"` antes).
- Testes estáticos (AC1, AC11) **não** exigem banco — leem arquivos como texto/AST. Devem rodar em CI sem dependências externas.
- Não modificar nenhum dos 4 testes de golden path existentes — eles são a fixture de comparação "antes"; se precisarem de ajuste, é sinal de regressão, não de manutenção de teste.

### Notas de contexto (não inventar além disto)

- `pncp_raw_bids` é mutada in-place (sem `valid_from`/`valid_to`). Replay temporal completo de oportunidades históricas está **fora de escopo** desta wave — é limitação conhecida e documentada (impact-analysis §6.3, "Risco residual"), não um bug a corrigir aqui.
- **Ausência de kill switch é intencional.** Não reusar `truth_plane_kill_switch` do outbound — acoplaria os dois motores. Se operação precisar pausar o motor inbound, a forma é não invocar o CLI/producer (não há infraestrutura de pausa nesta story, e não deve ser criada aqui).
- Nenhum `CREATE TRIGGER` sobre tabelas outbound é permitido em nenhuma circunstância — nem para produzir eventos (isso é explicitamente proibido mesmo na story 2, que usará poll/CDC).

---

## QA Results

### Review Date: 2026-09-03

### Reviewed By: Quinn (@qa) — veredito independente, autoridade exclusiva (§3 e §6 do `aiox-project-operating-protocol.md`)

**Gate: FAIL → `docs/qa/gates/confenge-live-intelligence-01-live-intelligence-foundation.yml`** — **iteração 1/5 do QA Loop. SUPERADO pelo re-veredito da iteração 2/5 (CONCERNS), na subseção "Re-veredito" ao final desta seção.** O texto abaixo é preservado como histórico de auditoria, não como veredito vigente.

`reviewed_revision`: `commit:49989740` (branch `review/universe-parafiscal-clean`, story v1.11). Revisão **read-only**: nenhum arquivo de `scripts/`, `tests/` ou `db/` foi editado, nenhuma migration aplicada, nenhum DML manual executado.

#### Critério que separa o bloqueador de todo o resto: defeito de PROVA vs. defeito de COMPORTAMENTO

O gate HIGH-RISK do @architect foi fechado com AR-3 e AR-4 abertas como dívida HIGH. Isso estabelece, nesta story, que **lacuna de instrumento** (a prova é mais estreita que a propriedade, mas nada se comporta mal) **não bloqueia**. Aplico o mesmo critério com consistência: AR-3, AR-4, a estreiteza de `PROTECTED_OBJECTS`, a tautologia do AC10 e a asserção inalcançável do verifier são todas dessa classe e ficam registradas como dívida, não como bloqueio.

O bloqueador é de outra classe. É **comportamento**, reproduzido por mim, no caminho de produção.

#### Bloqueador — REL-001 + TEST-001 (high)

`source_as_of` cai em `datetime.now(tz=UTC)` em `producer.py:182-184` (o `row` do banco **nunca** contém a chave: o `RETURNS TABLE` de `live_open_opportunities_as_of` declara 25 colunas e nenhuma se chama `source_as_of`; as 3 ocorrências na 104 — `:276`, `:338`, `:456` — são colunas de destino) e é **incondicionalmente** relógio de parede em `producer.py:260` (`project_companies`, sem nem fallback). O campo entra em `as_payload()` → `content_hash()` → `data_hash_of()` → `content_hash_of()` → `_snapshot_id()`.

Reproduzido por mim, Python puro, sem tocar o banco:

```
row has source_as_of key: False
a.source_as_of 2026-09-03 01:35:18.567357+00:00
b.source_as_of 2026-09-03 01:35:19.671682+00:00
content_hash equal: False
data_hash equal: False
universe_hash equal: True
```

Dois builds sobre os **mesmos dados** e o **mesmo `as_of`** produzem `snapshot_id` diferente. Como `_persist` emite `DELETE ... WHERE snapshot_id = %s` antes de inserir, o DELETE nunca casa com o build anterior e as tabelas do motor **acumulam** snapshots em vez de reconstruir o mesmo. O comentário `producer.py:503` — "Replay idempotente: reconstroi o mesmo snapshot_id do zero" — é factualmente falso no caminho do banco.

**O elemento decisivo é a evidência, não só o defeito.** `test_replay_is_idempotent_for_the_same_universe` (`test_producer_state_criteria.py:207-223`) passa `opportunities=` **e** `companies=`, o que desvia em `producer.py:395-397` e faz `project_opportunity`/`project_companies` **nunca** serem chamados; os helpers fixam `source_as_of=UTC_NOW` literal exatamente no campo que a produção randomiza. Busca repo-wide por `snapshot_id ==|content_hash ==|data_hash ==` em `tests/` retorna apenas essas linhas: não há segundo teste da propriedade. Logo o checkbox de DoD linha 384 ("AC1–AC12 atendidos, **com evidência**") está selado sobre evidência vácua justamente para a propriedade que o Valor da story nomeia.

`REL-002` vai empacotado por economia de ciclo: `_blocked_result` (`producer.py:376-379`) usa `date.today()` (fuso do SO) em vez de `CUTOFF_TIMEZONE` — a **mesma classe** de TD-LI-7, que RULING-LI-04 rulou correção obrigatória. É o ponto cego daquele ruling (ele se escopou aos fixtures), não violação dele.

#### Resposta antecipada à objeção previsível

*"O motor não é operacionalizado (Escopo OUT: sem cron/systemd), logo a acumulação não tem raio de impacto vivo."* Não sustenta. O **Valor** e o **Estado-alvo** desta story nomeiam replayability como o entregável — não é efeito colateral de uma feature futura, é o produto. A wave seguinte constrói sobre esta fundação, e o teste vácuo garante que ninguém detectaria o defeito a jusante. Entregar a fundação de um handoff "replayable" que não replay é entregar a fundação errada.

#### O que este FAIL NÃO faz

- **Não reabre o gate do @architect.** ADR-040 permanece Accepted e `gate_satisfied: true`; o próprio `gate_satisfied_note`, item (1), reserva `PASS`/`CONCERNS`/`FAIL` exclusivamente ao @qa. Verifiquei a condição que o @architect anexou ao selo: reproduzi `1 failed / 121 passed` **dentro** da janela de manifestação de TD-LI-7 (banco: `utc_now` 2026-09-03 01:20, `current_date` 2026-09-03, `sao_paulo_date` 2026-09-02 — datas divergem) e os 3 testes de AR-1 passam. **O selo não cai.**
- **Não reabre RULING-LI-01 a LI-04.** A exceção de `pncp_raw_bids`, o reescopo do AC2, TD-LI-6 como dívida aceitável e a correção obrigatória de TD-LI-7 continuam valendo como decididos. TD-LI-6 (`REL-003`) foi **verificado, não re-litigado**: reproduzi nos dois sentidos como instruído, e confirmei o mecanismo em vez de aceitar a narrativa — `sources.py:116-133` retorna `None` quando `MAX(updated_at)` é NULL e o motor converte em BLOCKED, isto é, falha fechado, não mascara.
- **Não reabre AR-3/AR-4.** Seguem dívida HIGH, owner @dev, herdadas pelo follow-up.
- **Não cobra nada do protocolo de dois braços** preservado sob o AC2 — é do follow-up, conforme o aviso na própria story.

#### Verificado e aprovado (o que sustenta o resto da story)

Aditividade estrutural com prova **mais forte** que a da story (grep repo-wide por `confenge_live_intelligence` fora do pacote e de `tests/` retorna zero ocorrências, contra os 5 diretórios que o teste varre); barreira select-only medida no catálogo (`relacl` das 6 tabelas sem nenhuma entrada de `PUBLIC` ou de `smartlic_public_reader`, apenas SELECT para o reader; `pg_default_acl` em `public` com 0 linhas); resolução as-of paramétrica sem `CURRENT_DATE`/`now()` no corpo, com guarda anti-vacuidade real; zero trigger, zero `events.py`, zero referência a `confenge_target_fit_dirty` em todo o pacote; FIT sem nenhuma coluna numérica, com `fit_state` derivado por CHECK estrutural; um único sítio de DML dinâmico, guardado inline por `assert_write_target`; simetria migration/rollback com 12 passed e restauração no `finally`; resíduo do motor zero sob execução independente (0 linhas `LI-TEST-`, `confenge_live_intelligence_snapshots=0`); AC12 (a)-(d) registrados em ADR-040; stub de follow-up existente e absorvendo os dois débitos nomeados — AR-5 confere linha a linha.

#### Dívida registrada (CONCERNS-class, não bloqueia — detalhe completo no gate file)

| ID | Sev | Item | Owner |
|---|---|---|---|
| SEC-001 | high | AC10 "whitelist" é tautológica: os `*_PAYLOAD_KEYS` derivam dos próprios dataclasses, então `extra` é sempre vazio e a whitelist auto-expande. Única barreira viva é a blacklist de 11 termos, medida como não pegando `gestor_contrato`, `endereco`, `cep`, `nome_completo`. Sem `schema_hash` golden pinado | @dev |
| SEC-002 | medium | Asserção AC10 do verifier inalcançável: colunas extras da linha são descartadas por `_rebuild_*` antes da checagem; `payload_keyset_whitelisted` é selo sempre emitido | @dev |
| TEST-002 | medium | `PROTECTED_OBJECTS` colapsa os globs do AC1 em literais com `\b` e deixa 3 tabelas `canonical_snapshot_*` fora — e `test_no_outbound_write_runtime.py:37` importa a mesma tupla, então a evidência de AR-1 herda a lacuna | @dev |
| TEST-003 | medium | Regex `MUTATING` cobre 5 formas verbais; `DROP TRIGGER/CONSTRAINT/INDEX` passariam pelo teste P0 (= AR-4, já registrada) | @dev |
| TEST-004 | medium | "Regressão dirigida 391/34" foi medida **sem** `REQUIRE_REAL_DB=1`, e os 34 skips são exatamente os testes de banco outbound (inclui os 5 de `test_store_idempotency.py`). Re-medido: 1 failed / 416 passed / 8 skipped, falha alheia identificada | @dev |
| TEST-005 | medium | AC8 declara lista fechada de 6 blockers; 3 sem caminho de código e o gatilho de watermark cobre metade do que nomeia (`freshness_state` tem zero ocorrências no motor) | @dev / @po |
| ARCH-001 | medium | Exclusão de oportunidade é contaminada pelo lado COMPANY: uma empresa com `observed_ufs=()` zera 100% do universo consumível mantendo PARTIAL selado. **§7.2 vs §4.1 é ambiguidade de spec — adjudicação é do @architect, não minha** | @architect |
| REQ-001 | medium | `universe_hash` não inclui as contagens de exclusão, contra requisito literal da §7.2 (fail-closed segue intacto por outra via) | @architect |
| REL-003 | medium | TD-LI-6 — teste RED determinístico no DSN documentado; único sítio de asserção do blocker watermark. Dívida já rulada; registro nota técnica de que `monkeypatch` do módulo fecharia sem 2º DSN | @devops / @dev |
| DOC-001 | medium | Checkbox de DoD linha 394 selado `[x]` mas AR-3/AR-4 não têm portador de follow-up, e a enumeração está obsoleta em duas revisões | @po / @sm |
| DOC-002 | medium | §Plano de Rollback contradiz o rollback entregue (manda emitir o GRANT inverso da §9 removida) — quarta localização estale, não sinalizada; e a linha 425 escreve critério que o teste citado não verifica (= AR-3) | @po / @dev |
| SEC-003 / SEC-004 | low | Os 4 `ALTER ROLE ... SET` são inertes (role NOLOGIN; `SET ROLE` não reaplica GUCs — medido) e o `GRANT EXECUTE` na função as-of é incoerente com o grant-set (chamada DENIED sob `SET ROLE`), com teste assertando a capacidade inexercível | @data-engineer |
| MNT-001..007 / DOC-003 | low | FIND-LI-01 ainda aberto (state file não valida contra o schema); docstring do arquivo do P0 ainda diz AC2 BLOCKED; citação `:110` deveria ser `:128`; `_persist` faz DELETE em `events`; rollback não limpa o ledger `_migrations`; `matched_dimensions` sem consumidor; READY alcançável com zero empresas; `razao_social`/`objeto` podem conter PII de pessoa natural (MEI) | vários |

#### Limites da minha própria evidência (mesma disciplina que cobro)

Não provisionei 2º DSN descartável, logo **não** consigo atribuir falha alguma a pré-104 vs. pós-104 — declaro como limite, não como suposição. `test_snapshot_reconciliation.py` (8 testes) segue skipped por exigir `REQUIRE_TEST_DB=1` com DSN próprio: nem a minha medição fecha integralmente o conjunto nomeado pela story. Efeitos colaterais das minhas execuções, declarados para não serem atribuídos ao motor: `confenge_target_fit_dirty` foi de 14 para 18 (escrito pela suíte outbound) e JSONs sob `artifacts/` foram modificados por testes.

#### Devolução ao @dev — exatamente o que falta

1. **`source_as_of` deriva do watermark da fonte**, nos **dois** sítios (`producer.py:182-184` e `producer.py:260`). O valor já existe: `sources.fetch_source_watermark` retorna `watermark_at` e `producer.py:384-386` o usa apenas como teste booleano de presença, descartando-o. Proibido relógio de parede como fallback silencioso — ausência de watermark já tem ramo BLOCKED. A fonte do watermark do lado COMPANY é decisão sua com o @architect (o impact-analysis tem §201 para OPPORTUNITY e apenas a provenance de §179 para COMPANY); não a sobre-especifico.
2. **Teste que exercita a PROJEÇÃO:** dois `build_snapshot()` consecutivos **sem** universo injetado, mesmo seed e mesmo `as_of`, assertando igualdade de `snapshot_id` **e** `content_hash` **e** `data_hash`. Sem esta propriedade de aceite a correção fica sem guarda e o defeito recorre — precedente explícito de RULING-LI-04.
3. **`_blocked_result` deriva a data civil de `CUTOFF_TIMEZONE`**, importado **por nome** do módulo do motor. Mesma propriedade que RULING-LI-04 impôs ao fixture, agora aplicada ao código de produção. Proibido segundo literal de fuso.
4. **Re-medição obrigatória:** suíte do motor sob `REQUIRE_REAL_DB=1` com a nova contagem, **mais** os 3 testes de AR-1 isolados (a condição que o @architect anexou ao selo continua valendo: se regredirem, o selo cai com eles). Reportar também a regressão dirigida **com** o prefixo `REQUIRE_REAL_DB=1`, corrigindo TEST-004.

**Escopo:** todos os arquivos a tocar já constam de `scope_files` — não há ampliação. **Não** tocar a migration 104 nem o rollback nesta correção. **Não** corrigir os itens CONCERNS-class desta devolução: eles têm owner e prazo próprios no gate file.

---

### Re-veredito — QA Loop iteração 2/5 (@qa, 2026-09-03)

**Gate: CONCERNS → `docs/qa/gates/confenge-live-intelligence-01-live-intelligence-foundation.yml`**

`reviewed_revision`: `commit:49989740` + working tree com story v1.13. **Limite declarado de saída:** o pacote `scripts/confenge_live_intelligence/` e `tests/confenge_live_intelligence/` está **untracked**, logo o git não me dá baseline de diff. Verifiquei o **estado atual** dos arquivos, não o delta — a afirmação "apenas 6 arquivos tocados" não é verificável por mim e não a endosso. Endosso o que o código faz hoje.

#### Não confiei no relato — reexecutei tudo

Os três bloqueadores estão **corrigidos no caminho de produção**, e a prova é minha, não a do @dev.

**Prova independente de idempotência** (script próprio, 2 editais sintéticos `QA2-IDEM-` em `pncp_raw_bids` sob a exceção prefixo-escopada de RULING-LI-01, teardown em `finally`): **três** builds sobre o mesmo snapshot de entrada, separados por 1,5s de relógio de parede **e** sob fusos de SO a 25h de distância (default → `Pacific/Kiritimati` UTC+14 → `Pacific/Niue` UTC−11).

```
state          : READY_CANONICAL READY_CANONICAL READY_CANONICAL
snapshot_id    : LI-2026-10-01-3a32e64d0e002b700ebaa1a0ec258f8a
id equal 1==2  : True      id equal 1==3  : True
content equal  : True      data equal     : True      universe equal : True
opportunities  : 0 -> 2 -> 2 -> 2      snapshots : 0 -> 1 -> 1 -> 1
NO DUPLICATION : True | b1 persisted: True | distinct snaps : 1
verify ok      : 7 checks, verified_opportunities=2
```

Contagem **total por tabela, sem filtro de `snapshot_id`** — o instrumento que faltava ao teste antigo. `observed_opportunity_count=2` e `state != BLOCKED` confirmam que a **projeção foi exercitada**, não desviada. A última linha fecha o terceiro sítio que o @dev encontrou por auditoria própria: `verify_snapshot()` na **mesma conexão** que fez o build (portanto pinada em `CUTOFF_TIMEZONE`) — o cenário em que o verifier falhava fechado sobre snapshot íntegro — aprova os 7 checks.

**Verificação de código, não de comentário.** `project_opportunity`/`project_companies` exigem `source_as_of` como parâmetro keyword **obrigatório sem default**: um fallback de relógio de parede não é sequer representável sem alterar a assinatura. `datetime.now()` sobrevive em **um** sítio (`producer.py:567`), que alimenta só `cutoff_at`/`closed_at`/`recorded_at` — e isso está **provado empiricamente** pela igualdade de hash acima, não aceito pela leitura do comentário. Zero `date.today()` em código executável do pacote; zero segundo literal de fuso.

#### O vetor que ninguém havia exercitado — e por que ele não virou FAIL

Minha prova acima, **como a do @dev**, mantém o watermark **constante**. O caminho operacional normal é o oposto: um crawl **move** o watermark, todo hash de linha muda e o `DELETE ... WHERE snapshot_id` não casa com nada. Testei esse caminho (build → `UPDATE ... updated_at + 1h` escopado a `QA2-WM-` → build), depois de verificar por grep que a 104 **não** tem `UNIQUE`/`EXCLUDE` sobre estado:

```
build2 error   : None            ids differ     : True
snapshots rows : 2  →  ambos READY_CANONICAL, ambos superseded_at=None
verify OK      : os dois snapshots
```

Este era o teste que decidia o veredito. Se o INSERT tivesse quebrado por constraint, o motor falharia no seu **segundo build real** — comportamento, e **FAIL novo**. Não quebrou: coexistência é o comportamento correto de um store endereçado por conteúdo. O que falta é a **marcação do superado** — a 104 documenta a transição `READY_CANONICAL → SUPERSEDED` e tem `superseded_at` + CHECK, mas grep completo confirma que `SNAPSHOT_SUPERSEDED` **não tem emissor nem teste**. Registro como **REL-004 (medium)**: mesma classe de TEST-005 (enumeração fechada com membro sem emissor), sem consumidor vivo nesta wave. Não bloqueia.

#### Re-medição, executada por mim

| Medição | Resultado | Confere com o @dev |
|---|---|---|
| Suíte do motor (`REQUIRE_REAL_DB=1`) | **1 failed / 124 passed** (78,43s) | sim, dígito a dígito |
| **AR-1 isolado** (selo do @architect) | **3 passed** (0,54s) | sim — **o selo não cai** |
| Regressão dirigida **com** o prefixo | **2 failed / 540 passed / 8 skipped** | sim — **TEST-004 corrigido** |
| `ruff check` / `format --check` | limpos, 18 arquivos | sim |

A única falha do motor é `test_blocked_when_watermark_is_missing` = **TD-LI-6 / REL-003**, reproduzida isoladamente com a mensagem exata da causa raiz já rulada (`assert 'READY_CANONICAL' == 'BLOCKED'`). As duas da regressão dirigida são as duas que **eu mesma** caracterizei no gate anterior. **Nenhuma falha nova.**

#### Disposição dos 21 achados não-bloqueadores — decisão explícita

Reexaminei o fundamento de cada um contra o estado **atual** do código. **Nenhum deles bloqueia**, e nada nesta rodada mudou a razão: continuam sendo lacuna de **instrumento** (a prova é mais estreita que a propriedade), não defeito de **comportamento**. É o mesmo critério que o gate HIGH-RISK do @architect estabeleceu ao fechar com AR-3/AR-4 abertas como dívida HIGH — aplicá-lo com consistência é o que impede este gate de ser arbitrário. Owner, severidade e prazo item a item no gate file (`concerns_carried_forward`), mais os 2 novos (REL-004, REL-005).

Duas notas que merecem destaque por serem contraintuitivas:

- **SEC-001 é `high` e fica em CONCERNS.** O risco é de **drift futuro**, não de vazamento hoje: o texto literal do AC10 está atendido por teste dedicado e nenhum campo de contato existe no schema. A mitigação é uma linha de defesa a construir, não um defeito a reparar. **Se um campo novo entrar em qualquer dataclass do motor antes disso, o item volta como bloqueador.**
- **MNT-001 (FIND-LI-01) não condiciona este veredito — condiciona o fechamento do @po.** Por §8/§11 do protocolo os hooks leem o state file como fonte operacional, e ele segue com 1 erro de validação Draft7. Escrevi neste ciclo apenas os campos de veredito e **não** reescrevi `snapshot_evidence`, que é conteúdo de outro agente: não agravo o achado. Resolver antes de `po_closed=true`.

#### O que este CONCERNS NÃO faz

Não reabre o gate do @architect (re-verifiquei a condição anexada ao selo: 3 testes de AR-1 isolados, verde). Não reabre RULING-LI-01 a LI-04, nem o reescopo do AC2, nem a exceção de `pncp_raw_bids`. Não reclassifica TD-LI-6. Não reabre AR-3/AR-4.

#### Ratifico a decisão de escopo do @dev

O @dev corrigiu **dois** sítios que não estavam na minha lista (`sources.fetch_source_watermark` sem pin, `verifier._rebuild_*` sem normalização) e **não** tocou nenhum item CONCERNS-class. O critério é o correto e é o meu: mesma **classe** do bloqueador em reparo, arquivos já em `scope_files`, e deixá-los fora entregaria a correção com a metade de leitura quebrada — verifiquei que é verdade. Isso **não** é precedente para corrigir itens CONCERNS-class por conta própria.

#### Dois achados que só apareceram porque fui verificar uma afirmação minha

**PUB-002 (low) — este gate file não é versionado, e eu havia afirmado o contrário.** Ao condensar os 21 achados não-bloqueadores em uma linha cada, escrevi que os textos integrais ficavam "preservados no histórico deste arquivo (git)". Fui verificar: `git check-ignore -v` aponta `.gitignore:58` → `docs/qa/gates/`, e o `git log` deste arquivo é **vazio**. A afirmação era falsa e a condensação teria **destruído** a evidência medida que as stories de follow-up consomem — os 7 termos de PII que a blacklist de 11 não pega, as 3 tabelas `canonical_snapshot_*` fora de `PROTECTED_OBJECTS`, as contagens por família de `DROP`, a medição de inércia dos GUCs, a sonda `DENIED` do `GRANT EXECUTE`. **Restaurei os 21 blocos na íntegra** (`finding` / `why_not_blocking` / `suggested_action`), com a disposição desta iteração acrescentada por item em `qa_disposition_v2`. Consequência estrutural que fica registrada: um gate sobrescrito a cada iteração do QA Loop, sem histórico, **não é registro durável de dívida** — o registro durável é o da story, versionado. Isso promove **DOC-001** de higiene documental a única salvaguarda.

**PUB-001 (medium) — `reviewed_commit` aponta para um commit que não contém o código revisado.** `state.reviewed_commit` é `49989740`, mas `scripts/confenge_live_intelligence/`, `tests/confenge_live_intelligence/`, a migration 104 e o rollback estão **untracked**. Eu havia declarado o untracked como limite de evidência; a consequência operacional em §8 é mais dura que isso: as pré-condições **#5** (`reviewed_commit === HEAD`, "código não alterado após QA") e **#6** (working tree limpa) são hoje **mutuamente insatisfazíveis**. Commitar o pacote faz `HEAD ≠ 49989740` e quebra a #5; editar `reviewed_commit` à mão anula exatamente a garantia que o campo existe para dar. **Ação requerida antes do fechamento:** commitar o pacote e setar `reviewed_commit` para o SHA resultante. Minha re-confirmação é barata e **não é nova revisão** — como verifiquei o *estado* dos arquivos e não o delta, basta um `git diff` do commit contra o que eu li: diff vazio transfere o veredito. Não bloqueia este veredito; bloqueia publicação limpa se ficar sem registro.

#### Limites da minha evidência nesta iteração

O lado COMPANY da **projeção** não é alcançável pelo build no DSN documentado (`v_contracts_canonical_v2` sem fornecedor): meus builds fecharam com `verified_companies=0`. A cobertura desse sítio vem do teste dedicado do @dev, que **auditei** (re-lê o watermark real a cada chamada, nada pinado à mão), não de execução própria do caminho completo. Não provisionei 2º DSN. `test_snapshot_reconciliation.py` segue skipped. Efeitos colaterais das minhas execuções, declarados: seeds `QA2-IDEM-`/`QA2-WM-` criados e removidos (estado final auditado: zero linhas, zero snapshots); nenhum arquivo de `scripts/`, `tests/` ou `db/` editado; nenhuma migration aplicada.

---

## Handoff (pós-validação @po)

- **`next_agent`: @architect** (com **@data-engineer** obrigatório para a migration 104 / LI-2).
- **NÃO é @dev.** O bloco `## Handoff` genérico de `.aiox-core/development/tasks/validate-next-story.md` termina com `next_agent: @dev`, mas esse é o caminho STANDARD. A §2 do `.claude/rules/aiox-project-operating-protocol.md` exige, para HIGH-RISK (migration + segurança + dados): `@architect + @data-engineer → @sm → @po → @dev → @qa aprofundado → gate sistêmico → @po → @devops`. Ir direto ao @dev pularia dois gates obrigatórios.
- **`next_action`:** revisão de aditividade contra as 8 decisões fechadas do `impact-analysis.md`, e revisão de DDL/grants da 104 pelo @data-engineer, antes de qualquer linha de implementação.
- Estado operacional: `.aiox/state/stories/confenge-live-intelligence-01.json`.

---

## Change Log

| Data | Versão | Descrição | Autor |
|---|---|---|---|
| 2026-09-02 | 1.0 | Story criada a partir do impact-analysis + schema-draft (@architect + @data-engineer), com divergências do draft registradas e não reabertas | @sm |
| 2026-09-02 | 1.1 | Correções pós-revisão: AC2 fortalecido para cobrir migration aplicada/não aplicada (não só ausência de import); AC3 estendido com escopo de `ALTER DEFAULT PRIVILEGES` por role (verificado: 089/090 não usam o mecanismo hoje); baseline corrigido — `scripts/golden_path.py` é ingestão, não outbound; fonte real é `run_pipeline()`/`queue_counts()`/`send_readiness.py`/`export.py`; adicionada seção CodeRabbit Integration (enabled=true confirmado); Given/When/Then completado em AC6, AC8, AC11; marcador `OUTBOUND_CADENCE_REDUCED` reatribuído a verificação de File List, não a teste pytest; convenção de rollback confirmada contra `db/rollback/` existente | @sm |
| 2026-09-02 | 1.3 | **LI-2 (DDL) entregue.** Criados `db/migrations/104_confenge_live_intelligence_v1.sql` e `db/rollback/104_confenge_live_intelligence_v1_rollback.sql`. Task 0 re-executada no momento da implementação: `gh pr list --state open` → apenas #531 (reserva `103_contract_lifecycle_truth.sql`) e #528 (sem migration); **`104` confirmado livre**. As 6 divergências do draft resolvidas a favor do `impact-analysis.md` (tri-estado sem score; nomes `confenge_live_intelligence_*` em schema `public`; COMPANY sem campo copiado do outbound; PII por whitelist de colunas declaradas; `reason_codes` TEXT[]; número 104). Escopo mantido na lista fechada de §8.2 — RPCs e trigger de imutabilidade do draft **não** criados (padrão de engenharia, não contrato). Validação: sem DSN local disponível (porta 5433 recusada, `psql` ausente); arquivos validados pelo parser real de `scripts.ops.apply_migrations` (`split_sql`/`is_executable`/`version_key`) — 48 statements executáveis, dollar-quoting íntegro, zero violação de AC1 por statement e zero DML sobre tabela outbound. **Pendente para @dev:** testes de AC1/AC3 (subtask não marcada) e execução real da 104 + rollback contra banco | @data-engineer |
| 2026-09-02 | 1.4 | **Status: Ready → InProgress** (@dev inicia implementação, conforme `story-lifecycle.md`) | @dev |
| 2026-09-02 | 1.5 | **LI-1, LI-3, LI-4, LI-5, LI-6, verifier, CLI e suíte de testes entregues.** Migration 104 aplicada com sucesso no banco local (`applied=1 skipped=104`). 95 testes novos passando; regressão dirigida 391 passed / 34 skipped; `ruff check` + `ruff format --check` limpos. AC1, AC3, AC4, AC5, AC6, AC7, AC8, AC9, AC10, AC11, AC12 atendidos com evidência registrada em Dev Notes. **AC2 declarado BLOCKED-PENDING-AUTHORIZATION** por dois motivos independentes (escrita em `confenge_target_fit_dirty` proibida ao @dev; banco de teste vazio tornaria a comparação vacuosa) — evidência parcial entregue e rotulada como parcial. **Um defeito real corrigido no rollback da 104** (seção 3 emitia `GRANT EXECUTE ON FUNCTIONS TO PUBLIC` incondicional, criando entrada em `pg_default_acl` inexistente antes da 104 — contradizendo o comentário do próprio arquivo e o critério de aceite do rollback); passou a ser condicional. **Um achado reportado ao @data-engineer:** §9 da 104 (`ALTER DEFAULT PRIVILEGES`) é inerte no PostgreSQL 16. ADR-040 criada com as 4 decisões do AC12 + os 2 achados. 5 débitos técnicos registrados com owner e severidade. **Status permanece InProgress** — AC2 é P0 bloqueante e InReview seria selo sem evidência | @dev |
| 2026-09-02 | 1.6 | **Ruling do @po sobre os dois conflitos reportados pelo @dev (autoridade exclusiva de escopo).** (1) **Ratificada** a exceção pontual e escopada a `forbidden_write_targets`: seed sintético com prefixo `LI-TEST-` em `pncp_raw_bids` **apenas**, com DELETE escopado no setup **e** no teardown sob `try/finally`; `sc_public_entities` e demais alvos seguem SELECT-only sem exceção; `pncp_raw_bids` **permanece** na lista (a exceção convive, não reabre). AC4/AC5/AC8 ficam verificados como estão — nenhuma reformulação de texto necessária. (2) **AC2 reescopado**: a formulação de dois braços exige 2º DSN, dataset de seed de 5 etapas e autorização de escrita outbound — insumos que esta story não tem e cuja criação seria outra story. AC2 passa a exigir o que a evidência prova de fato (ausência de referência do outbound ao motor + diff de catálogo de ACLs), com o limite dessa evidência declarado explicitamente. O protocolo de dois braços é **preservado na íntegra** e promovido a story bloqueante nomeada `confenge-live-intelligence-outbound-equivalence-gate`, pré-requisito de qualquer operacionalização do motor; TD-LI-1 é absorvido por ela. (3) Os 3 marcadores `NÃO VERIFICADO` **acompanham o AC2**: reatribuídos ao follow-up, seguem reportados como `NÃO VERIFICADO` — declarar `NO` sem o teste que os produz seria selo sem evidência, e o @dev acertou em recusar. Story **permanece InProgress**; ratificação fecha conflito de regra, não fecha o P0. `next_agent`: @architect (reescopo de AC P0 contra as 8 decisões fechadas) + @data-engineer (TD-LI-2 inércia do `ALTER DEFAULT PRIVILEGES`, TD-LI-3 correção do rollback §3) | @po |
| 2026-09-02 | 1.7 | **Status permanece InProgress** (@dev). Gatilho: o @data-engineer removeu a §9 da 104 (`ALTER DEFAULT PRIVILEGES`, TD-LI-2) e reescreveu a seção 3 do rollback (TD-LI-3) — ambos os débitos passam a RESOLVIDO. Teste afetado atualizado: `test_alter_default_privileges_of_104_left_no_catalog_entry` → `test_104_barrier_is_explicit_revokes_without_default_privileges`; deixou de testar o resíduo de catálogo de um mecanismo inexistente e passa a testar o que de fato existe — ausência de `ALTER DEFAULT PRIVILEGES` **por statement executável** (verificação por substring no texto bruto daria falso positivo: o arquivo cita o termo em comentário 7 vezes explicando a remoção) e presença dos `REVOKE` explícitos sobre as 6 tabelas + a função. A asserção `pg_default_acl` vazia é retida como guarda de regressão. Docstrings de módulo e de `test_future_migration_under_a_different_role_is_not_affected` reescritos (antecedente do AC3 2ª parte agora falso; teste retido como guarda). **Por que NÃO subiu para InReview:** o AC2 v1.6 nomeia seus dois produtores (`test_no_outbound_module_imports_live_intelligence`, `test_rollback_removes_every_object_and_reapply_is_clean`) — ambos existem e passam, então o motivo que sustentava o InProgress na v1.5 ("AC2 é P0 bloqueante") de fato deixou de existir, e **todos os AC1–AC12 estão satisfeitos**. Mas o gate de conclusão é conjuntivo (ACs **e** testes verdes) e a suíte do motor **não está verde** sob a condição de execução da própria story: `test_blocked_when_watermark_is_missing` falha de forma reprodutível enquanto houver linhas alheias em `pncp_raw_bids` (TD-LI-6). Desbloquear exige um 2º DSN descartável — insumo fora da autoridade do @dev, exatamente como no AC2 da v1.5, cuja recusa o @po ratificou. Subir para InReview com um item de DoD autodeclarado não atendido seria selo sem evidência. Evidência: `pytest tests/confenge_live_intelligence/ tests/test_live_intelligence_outbound_equivalence.py` com `REQUIRE_REAL_DB=1` contra Postgres real → **95 passed** com `pncp_raw_bids` livre de linhas alheias; **94 passed / 1 failed** depois que a suíte completa deixa 5 linhas de testes alheios no banco compartilhado (a falha é sempre a mesma, `test_blocked_when_watermark_is_missing` = TD-LI-6, e é reproduzível nos dois sentidos); `ruff check` e `ruff format --check` limpos; resíduo **do motor** zero (`0` linhas `LI-TEST-` em `pncp_raw_bids`, `sc_public_entities=0`, `confenge_target_fit_dirty=0`, `opportunity_intel=0`). **Ressalva declarada:** a suíte **completa** sob `REQUIRE_REAL_DB=1` **não** está verde e o baseline da v1.5 **não é comparável** (rodou sem a variável — 303 skipped vs 128, todos os `real_db` pulados). Uma das falhas é do motor — `test_blocked_when_watermark_is_missing` — causada por 5 linhas residuais de testes alheios no banco compartilhado e **não corrigível dentro desta story** (exigiria DELETE não escopado em tabela de `forbidden_write_targets`); registrada como **TD-LI-6**, com o ramo `BLOCKED` do AC8 ainda coberto por outros dois testes. O checkbox de suíte completa do DoD permanece `[ ]`. Marcadores **não** alterados: os 3 `NÃO VERIFICADO` acompanham o follow-up, conforme ratificado pelo @po. Nenhum arquivo SQL tocado pelo @dev nesta rodada (autoridade do @data-engineer). `next_agent`: @architect (gate de arquitetura) + @qa (veredito independente) | @dev |
| 2026-09-02 | 1.8 | **Status: InProgress → InReview. Ruling do @po sobre TD-LI-6 (RULING-LI-03) + correção dos 3 textos normativos herdados da remoção da §9.** (1) **TD-LI-6 é dívida ACEITÁVEL, não bloqueador.** Razão decisiva: **identidade de causa raiz com RULING-LI-02** — o AC2 de dois braços foi reescopado exatamente porque desbloqueá-lo exige um 2º DSN descartável (owner @devops); TD-LI-6 tem a mesma causa raiz e o mesmo owner. Rulá-lo bloqueador contradiria o ruling anterior do @po na mesma story e estacionaria o trabalho aguardando insumo que nenhum agente do ciclo atual pode produzir. Reforça: o gatilho *watermark ausente* **está provado** (95 passed em banco limpo) e o ramo `BLOCKED` do AC8 segue coberto por outros dois testes — o que falta é reprodutibilidade sob banco poluído, isto é **teste não-determinístico, não AC não provado**. O defeito não é do motor (que falha fechado corretamente); é estado de tabela compartilhada por suítes alheias. A recusa do @dev em fazer `DELETE` não escopado em tabela de `forbidden_write_targets` é **ratificada** — a exceção da v1.6 é escopada por prefixo `LI-TEST-` e não se estende a isso. TD-LI-6 é **herdado** pela story de follow-up bloqueante `confenge-live-intelligence-outbound-equivalence-gate`, que já lista o 2º DSN como pré-requisito. (2) **Três textos normativos corrigidos** (autoridade exclusiva do @po, sinalizados e não editados pelo @dev, corretamente): **Escopo IN item 2** e **linha R1 da tabela de Riscos** passam a descrever a barreira como os 14 REVOKEs explícitos por objeto, sem `ALTER DEFAULT PRIVILEGES`; **AC3 2ª cláusula** deixa de ser condicional de antecedente falso (satisfeita vacuamente) e vira **proibição positiva** verificável — nenhum statement executável da 104 emite `ALTER DEFAULT PRIVILEGES`, com verificação obrigatoriamente por statement via parser real de `apply_migrations` (substring daria falso positivo: o arquivo cita o termo 7 vezes em comentários), mais REVOKE explícito para `PUBLIC` e `smartlic_public_reader` sobre as 6 tabelas e a função, mais `pg_default_acl` vazia. `test_future_migration_under_a_different_role_is_not_affected` deixa de ficar órfão: é nomeado na story como guarda de regressão do retorno da §9. (3) **InReview é handoff para veredito independente, não aprovação e não afirmação de suíte verde.** O checkbox de suíte completa do DoD permanece `[ ]`, declarado, com a disposição do @po anotada. Classificar TD-LI-6 como `PASS`/`CONCERNS`/`FAIL` é autoridade exclusiva do @qa e **não** é antecipada aqui. (4) **Nota de leitura ao @qa:** a Dev Notes contém, na §"Evidência de execução", a linha estale `AC2 — BLOCKED-PENDING-AUTHORIZATION`, remanescente da v1.5 e superada pela §"AC2 — SATISFEITO conforme reescopo do @po (v1.6)" logo abaixo. É seção do @dev e não foi reescrita pelo @po; não deve ser lida como contradição viva. A §"Texto da story desatualizado pela remoção da §9 — sinalizado, NÃO editado" está **resolvida por esta v1.8**. `next_agent`: @architect (gate HIGH-RISK de arquitetura sobre o reescopo do AC2, ainda não registrado como executado) → @qa (veredito independente) | @po |
| 2026-09-02 | 1.9 | **Status: InReview → InProgress (@dev). AR-1 e AR-2 do gate HIGH-RISK do @architect: RESOLVIDAS.** Gatilho: veredito **INACEITÁVEL COM AÇÃO REQUERIDA** sobre o AC2/AC11 (ADR-040, §"Gate HIGH-RISK de arquitetura sobre o reescopo do AC2"). **O achado do @architect era correto e foi confirmado por leitura:** `producer.py:502-513` continha a idiom que evade o AC11 — tupla local de nomes de tabela (literais **sem** verbo DML) interpolada em `f"DELETE FROM public.{table} ..."` (verbo DML **sem** nome de tabela), e a checagem do AC11 é por literal único contendo ambos. Verificado que **não havia escrita proibida viva** (a tupla só continha `confenge_live_intelligence_*`): o defeito era de **prova**, não de comportamento — exatamente como afirmado. Varredura AST completa do módulo (`JoinedStr`/`.format()`/`%`/`+`) confirmou que `producer.py:511` era o **único** DML dinâmico; as demais interpolações são SELECT (`sources.py:70`, `:92`, `:110`) ou mensagens de erro. **(1) AR-2 — allowlist única.** `schema.py` passa a ter `WRITE_TARGET_ORDER` como **única enumeração literal** de alvos de escrita (6 tabelas, na ordem de DELETE segura para as FKs), `ALLOWED_WRITE_TARGETS = frozenset(WRITE_TARGET_ORDER)` **derivada** (duas listas independentes seriam duas allowlists), `OutboundWriteAttemptError` e `assert_write_target()` que valida **antes** de executar, fail-closed. Re-exportadas em `__init__.py`/`__all__` conforme o texto de AR-2. `producer.py::_persist` deixa de ter tupla local: itera `WRITE_TARGET_ORDER` e interpola `assert_write_target(table)`; o DELETE de `confenge_live_intelligence_snapshots`, antes literal separado, entrou na mesma ordem (último, por FK). O teste do AC11 ganhou `_dynamic_dml_violations()`, função **pura** que exige, para todo DML dinâmico de qualquer módulo do glob, que cada slot (a) passe pela guarda e (b) resolva a constante **importada por nome** do pacote e **não re-vinculada** — com os identificadores sancionados **derivados de `__all__` em tempo de teste**, não escritos à mão. **O critério de aceite explícito do @architect** ("uma tupla local nova em `events.py` tem de quebrar o teste") é provado por 10 auto-testes negativos (**10**): `tupla_local`, `slot_sem_guarda`, `parametro_de_funcao`, `allowlist_sombreada`, `constante_estrangeira`, `format`, `percent`, `concatenacao`, `acumulacao_augassign`, `acumulacao_join`, mais o controle negativo `test_checker_accepts_the_sanctioned_idiom`. O modo de falha nomeado pelo @architect ("AR-2 apenas reproduz o defeito do AC11 um nível acima") é fechado por `test_write_allowlist_is_disjoint_from_outbound_tables`: sem ele, bastaria acrescentar `opportunity_intel` à allowlist para manter tudo verde. **(2) AR-1 — smoke de runtime.** Novo `tests/confenge_live_intelligence/test_no_outbound_write_runtime.py`: `COUNT(*)` + `md5(string_agg(t::text ORDER BY t::text))` dos **15** objetos de `PROTECTED_OBJECTS` (tabelas **e** views, conforme "cada objeto da lista protegida do AC1" — não apenas as 7 tabelas; 15/15 confirmados em `pg_class`), `cli build` (código 0, `READY_CANONICAL`) + `cli verify` completos, recaptura e igualdade byte-a-byte. Janela abre **depois** do `seed_bid()` e fecha **depois** do producer, como AR-1 determina. Asserção de checksum **incondicional** (vale no caminho `BLOCKED`); só a asserção sobre `verify` é condicionada a estado verificável, com a condicionalidade **declarada** no docstring em vez de virar flake. Acompanham um teste de **anti-vacuidade** (o build de fato persiste seu próprio snapshot — sem isso AR-1 provaria um no-op) e um de **dentes do instrumento** (o fingerprint detecta 1 linha nova; um checksum cego passaria sempre). **(3) Evidência real:** `2 failed, 119 passed` sob `REQUIRE_REAL_DB=1`; `ruff check`/`format --check` limpos. As 2 falhas são **pré-existentes e independentes**, medido por controle — a mesma suíte **sem** o arquivo de AR-1 dá `2 failed, 116 passed`, as mesmas duas falhas. Os 3 testes de AR-1 e os 23 de AR-2 passam. Uma é **TD-LI-6** (já rulado dívida aceitável). A outra é **TD-LI-7, achado novo desta rodada**: `test_as_of_recovers_row_excluded_by_the_view` falha por **fronteira de fuso no próprio fixture** — `today_utc()` devolve data em **UTC** e a função as-of resolve a data civil em **`America/Sao_Paulo`**; medido em 2026-09-03 00:24 UTC, `current_date`=2026-09-03 vs. SP=2026-09-02. Janela de manifestação de 3h/dia, o que explica o verde nas rodadas anteriores. A função as-of está correta; o teste é que mistura fusos. AC4 não fica descoberto (`test_as_of_current_date_equals_canonical_view` segue provando a generalização estrita). **Não corrigido: fora de AR-1/AR-2.** **(4) AR-3, AR-4 e AR-5 não tocadas** — não bloqueantes, e AR-5 não é tarefa do @dev. **AR-1+AR-2 fechados ≠ gate fechado:** o encaminhamento do @architect exige AR-1 E AR-2 E a condição AR-5. Verificado que `story-confenge-live-intelligence-outbound-equivalence-gate.md` **agora existe** (criado pelo @sm em resposta a AR-5, status `Draft`, untracked) — a parte de AR-5 sobre débito apontando para artefato inexistente deixou de valer. Se `Draft` satisfaz a condição é autoridade do @architect. Registrado como `architect_gate.gate_satisfied: false` **por indeterminação declarada**, não por afirmação de que AR-5 falhou, para que ninguém leia AR-1/AR-2 RESOLVIDO como gate fechado. **Buraco próprio encontrado e fechado antes de declarar AR-2 pronto:** a 1ª versão do checker deixava passar a família de acumulação (`sql += table`, `"".join([...])`), idiom que já existe em `sources.py:110`; `_accumulation_violations()` agora a proíbe. **(5) Por que NÃO subiu para InReview:** o gate é conjuntivo (ações fechadas **e** suíte verde) e a suíte não está verde. Nenhuma das duas falhas é de AR-1/AR-2 e nenhuma é corrigível no escopo autorizado (TD-LI-6 exige 2º DSN, insumo de @devops; TD-LI-7 é correção de outro teste). Afirmar suíte verde seria selo sem evidência. **Regra dura respeitada:** zero escrita nas 7 tabelas protegidas fora do seed `LI-TEST-` autorizado; resíduo do motor zero após a suíte (`LI-TEST-` em `pncp_raw_bids`=0, snapshots=0) e tabelas outbound com as mesmas contagens de antes (`confenge_target_fit_dirty`=14, `opportunity_intel`=5, `sc_public_entities`=1). Nenhum arquivo SQL tocado. `next_agent`: @po (rular TD-LI-7 — decisão de escopo, não do @dev) → @architect (confirmar AR-1/AR-2 como piso de evidência atendido) → @qa (veredito) | @dev |
| 2026-09-02 | 1.10 | **Ruling do @po sobre TD-LI-7 (RULING-LI-04): CORRIGIR AGORA, dentro do escopo já autorizado — NÃO é dívida aceitável. Status permanece InProgress.** O @dev pediu ruling "pelo mesmo mecanismo com que rulou TD-LI-6". **O mecanismo decide no sentido oposto.** RULING-LI-02 e RULING-LI-03 classificaram itens como dívida por **exigirem um insumo que nenhum agente do ciclo atual pode produzir** (2º DSN descartável, owner @devops) — nunca por serem custosos de corrigir. TD-LI-7 não tem essa propriedade: nenhum insumo externo, nenhuma escrita em `forbidden_write_targets`, nenhuma autoridade que o @dev não tenha. **Sem identidade de causa raiz, a analogia não se aplica** e estendê-la seria ampliar o precedente além da razão que o produziu. **(1) Não é ampliação de escopo:** `tests/confenge_live_intelligence/conftest.py` e `test_sources_as_of.py` **já constam de `scope_files`**; o @po autoriza explicitamente uma correção **dentro de arquivos que a story já possui** — o @qa não deve ler como scope creep. **(2) Argumento decisivo que faltava no texto do @dev:** `today_utc()` é chamada em `test_no_outbound_write_runtime.py:128` e `:183`, isto é, **dentro da única evidência de AR-1**, ação BLOQUEANTE do gate HIGH-RISK do @architect. Fechar o gate sobre um instrumento com janela de indeterminação de ~3h/dia conhecida não é aceitável — situação materialmente distinta de um teste de leitura flaky. **(3) Correção de fato ao texto do @dev:** a alegação "AC4 não fica descoberto porque `test_as_of_current_date_equals_canonical_view` segue provando a generalização estrita" **está superestimada** — esse teste também chama `today_utc()` (`:52`), assim como `test_session_timezone_is_pinned_before_reading` (`:60`); sobrevive à janela por **sorte da distribuição do seed** (`+30d`/`−10d` longe da fronteira), não por imunidade. A cobertura de AC4 **não é independente** do defeito, e o @qa não deve herdar a afirmação como escrita. **(4) É defeito latente generalizado**, 4 call sites em 2 arquivos, não "um teste flaky" — TD-LI-7 elevado de MEDIUM para **HIGH**. **(5) Propriedade de aceite, não "trocar uma linha":** a data civil do teste tem de **derivar da mesma fonte de fuso que o motor fixa** (`pin_session_timezone` / `America/Sao_Paulo`); um segundo literal de `ZoneInfo` escrito à mão no fixture seria **segunda fonte de verdade** — exatamente o modo de falha que AR-2 acabou de fechar para a allowlist — e permitiria a divergência reaparecer sem nada quebrar. `scripts/confenge_live_intelligence/**` **não** deve ser tocado: a função as-of está correta e alterá-la seria regressão. **(6) Re-medição obrigatória:** reexecutar a suíte do motor sob `REQUIRE_REAL_DB=1` e reportar a nova contagem; a medição `2 failed / 119 passed` fica superada. **(7) Ratificado do @dev:** o motor está correto e a recusa em corrigir fora do escopo autorizado foi o procedimento certo — trazer ao @po é o que a regra manda. **(8) Limites:** classificar TD-LI-7, a suíte completa e o gate como `PASS`/`CONCERNS`/`FAIL` é autoridade **exclusiva** do @qa e não é antecipada; `architect_gate.gate_satisfied` permanece `false` por indeterminação de AR-5, cuja suficiência é do @architect. `next_agent`: @dev (corrigir a derivação de data civil no fixture + re-medir) → @architect (AR-1/AR-2 como piso de evidência) → @qa (veredito) | @po |
| 2026-09-03 | 1.11 | **Status: InProgress → InReview. TD-LI-7 CORRIGIDO conforme RULING-LI-04, com re-medição executada dentro da janela de manifestação e controle negativo.** **(1) A correção.** `today_utc()` → `today_cutoff_tz()` em `tests/confenge_live_intelligence/conftest.py`, derivando de `ZoneInfo(CUTOFF_TIMEZONE)` com `CUTOFF_TIMEZONE` **importado por nome** de `scripts.confenge_live_intelligence.schema` — a **mesma** constante que `sources.pin_session_timezone()` usa como default e que `schema.policy_hash()` sela no snapshot. **Zero segundo literal de fuso no fixture**, atendendo a propriedade de aceite do @po: uma segunda fonte de verdade reabriria o modo de falha que AR-2 acabou de fechar para a allowlist de escrita. Renomeação em vez de alias, porque `today_utc` passaria a mentir sobre a função; os 5 call sites nomeados no ruling foram atualizados (`test_sources_as_of.py` + `test_no_outbound_write_runtime.py:128,183`) e varredura repo-wide confirma zero `today_utc` remanescente sob `tests/` e `scripts/`. **`scripts/confenge_live_intelligence/**` NÃO foi tocado** — a função as-of está correta, como o ruling determina. **(2) Guarda determinística — porque "a suíte ficou verde" não seria evidência.** TD-LI-7 se manifesta em ~3h/dia; fora da janela, código corrigido e defeituoso são indistinguíveis. Novo `test_fixture_civil_date_matches_the_engine_timezone` compara a data do fixture com a data civil que o **próprio banco** resolve sob `CUTOFF_TIMEZONE` — a mesma resolução de `live_open_opportunities_as_of`. Vale a qualquer hora e cobre também divergência entre a tzdata do Python e a do PostgreSQL, lacuna que a derivação puramente em Python deixaria. **(3) Re-medição, deliberadamente DENTRO da janela.** Banco em `now() AT TIME ZONE 'UTC'`=`2026-09-03 00:56:08`, `current_date`=`2026-09-03`, `(now() AT TIME ZONE 'America/Sao_Paulo')::date`=`2026-09-02` — **datas divergem, janela ativa, medição discriminante**. Contagem nova: **`1 failed, 121 passed`** (supera `2 failed / 119 passed` da v1.9). A falha de TD-LI-7 **desapareceu**; a única remanescente é `test_blocked_when_watermark_is_missing` = **TD-LI-6**, já rulado dívida aceitável (RULING-LI-03), mesma causa raiz e mesmo owner (@devops / 2º DSN). Total 121→122 itens: +1 é a guarda nova. **(4) Os 3 testes de evidência de AR-1 passam**, rodados também isoladamente (`3 passed in 71.65s`) — exigido porque o defeito contaminava a prova de ação BLOQUEANTE do gate HIGH-RISK. **(5) Controle negativo, a evidência que fecha o argumento.** Reintroduzindo a derivação UTC antiga em memória (plugin de pytest, sem editar arquivo), na mesma hora e no mesmo banco: `2 failed, 4 passed`, com `test_as_of_recovers_row_excluded_by_the_view` falhando com a mensagem exata do achado original e a guarda nova acusando `fixture resolveu 2026-09-03 e o banco resolveu 2026-09-02`. O verde é atribuível à correção, não à hora do relógio. **(6) Fronteira de `CURRENT_DATE` na evidência de AR-1 verificada, não assumida.** `v_open_opportunities_canonical` está em `PROTECTED_OBJECTS` e filtra por `CURRENT_DATE`; verificado que `li_cli.main()` abre a **própria** conexão (`cli.py::_connect`), logo a sessão de `live_conn` conserva o mesmo `TimeZone` nas duas capturas de fingerprint e a correção não moveu essa fronteira. **Efeito colateral declarado:** o `as_of` do `cli build` mudou de `D` para `D-1` na janela, o que poderia alterar `payload["state"]` e suprimir o ramo **condicional** `verify_code == 0`; medido que o build fechou em estado verificável e o ramo condicional foi executado nas duas rodadas — não foi perdido silenciosamente. **(7) Regra dura reverificada:** `LI-TEST-` em `pncp_raw_bids`=0, snapshots do motor=0, `confenge_target_fit_dirty`=14, `opportunity_intel`=5, `sc_public_entities`=1 (inalterados). `ruff check` + `ruff format --check` limpos. Nenhum arquivo SQL tocado. **(8) Por que InReview, e o que InReview NÃO afirma.** A v1.8 já havia decidido que a story sobe para InReview convivendo com TD-LI-6 declarado (InReview = handoff para veredito, não aprovação); a v1.10 a reverteu para InProgress **exclusivamente** para que TD-LI-7 fosse corrigido. Corrigido e re-medido, a condição que travava a story caiu. **Isto NÃO afirma:** que a suíte completa está verde (não está — checkbox do DoD permanece `[ ]`), que TD-LI-6 é `PASS` (classificação é autoridade **exclusiva** do @qa), nem qualquer coisa sobre o gate de arquitetura — **o gate já foi fechado pelo próprio @architect em 2026-09-02** (`architect_gate.gate_satisfied: true`, AR-5 satisfeita por condição de existência, AR-3/AR-4 abertas como CONCERNS), por verificação independente e **não** por aceite do relato do @dev; esta rodada não toca esse campo. **Correção de afirmação do @dev:** a redação inicial desta v1.11 dizia que `gate_satisfied` permanecia `false` por indeterminação de AR-5 — isso era leitura do estado da v1.9, **superada** pelo fechamento do @architect, e fica corrigido aqui em vez de permanecer como contradição viva (nota de supersessão também inserida na Dev Notes §AR-1/AR-2). **Condição do @architect cumprida por esta rodada:** `architect_gate.td_li_7_effect_on_ar1_evidence` determina que a re-medição TEM DE incluir os 3 testes de AR-1 e que, se regredirem, *o selo cai com eles*. Não regrediram — 3 passed isolados e em suíte. **Divergência técnica registrada sem reabrir escopo:** o @architect mediu que a evidência de AR-1 é estruturalmente insensível ao deslocamento de fuso (sonda `--effective-date` delta −1/0/+1 → `READY_CANONICAL` nos três casos), contradizendo o **fundamento (b)** de RULING-LI-04; o próprio @architect declara que (a), (c) e (d) sustentam o ruling por si sós e que **RULING-LI-04 permanece vinculante**. A medição desta rodada é consistente com a dele. `next_agent`: **@qa** (veredito independente). Justificativa das duas fontes, porque elas precisam ser conciliadas: RULING-LI-04 encadeou `@dev → @architect → @qa`, e o selo do @architect declara que **não** rotearia a story ao @qa enquanto RULING-LI-04 não estivesse satisfeita, deferindo o roteamento à *"decisão de escopo do @po, que este gate não toca"*. Ambas as condições agora caíram: RULING-LI-04 está executada (esta rodada) e o passo `@architect` do encadeamento **já foi executado pelo próprio @architect** em 2026-09-02 — gate fechado com verificação independente, mais a condição que ele anexou ao selo (re-medição incluir os 3 testes de AR-1) cumprida em `3 passed`. Resta o @qa. AR-3/AR-4 seguem abertas como dívida (CONCERNS), matéria do veredito do @qa | @dev |
| 2026-09-02 | 1.2 | Validated GO (9/10) — Status: Draft → Ready. Correções aplicadas pelo @po durante validação independente: (1) AC7 tinha predicado invertido (`is_hollow_fact() == False` para descrever objeto hollow) — corrigido para `is True`, com referência de linha à fonte; (2) AC2 era inverificável como escrito (as duas execuções compartilhariam um banco já mutado por `run_pipeline()`) — adicionado protocolo obrigatório de dois braços com bancos partindo do mesmo baseline limpo; (3) plano de rollback não revertia `ALTER DEFAULT PRIVILEGES` nem tratava o destino do role (ambos sobrevivem ao `DROP TABLE` como entradas de catálogo) — adicionados o inverso explícito e um critério de aceite verificável via `pg_default_acl`; (4) AC12 estendido de 2 para 4 itens abertos, dando owner e artefato (ADR) também à limitação de replay as-of e à ausência intencional de kill switch. Handoff HIGH-RISK: @architect (não @dev) | @po |
| 2026-09-03 | 1.12 | **QA Gate FAIL — Status: InReview → InProgress (@qa).** Gate file: `docs/qa/gates/confenge-live-intelligence-01-live-intelligence-foundation.yml`. **Critério do veredito: defeito de PROVA vs. defeito de COMPORTAMENTO.** O gate do @architect fechou com AR-3/AR-4 abertas como dívida HIGH, o que estabelece nesta story que lacuna de instrumento não bloqueia; aplico o mesmo critério com consistência e registro como dívida a tautologia do AC10 (SEC-001), a asserção inalcançável do verifier (SEC-002), a estreiteza de `PROTECTED_OBJECTS` (TEST-002) e o regex `MUTATING` (TEST-003, = AR-4). **O bloqueador é de comportamento, reproduzido pelo @qa em Python puro sem tocar o banco:** `source_as_of` cai em `datetime.now(tz=UTC)` em `producer.py:182-184` (o `RETURNS TABLE` da função as-of declara 25 colunas e nenhuma se chama `source_as_of`) e é incondicionalmente relógio de parede em `producer.py:260`; o campo entra em `content_hash()` → `data_hash_of()` → `_snapshot_id()`, logo dois builds sobre os mesmos dados e o mesmo `as_of` geram `snapshot_id` distinto (`content_hash equal: False`, `data_hash equal: False`, `universe_hash equal: True`), o `DELETE ... WHERE snapshot_id` de `_persist` nunca casa e as tabelas do motor ACUMULAM em vez de reconstruir — o comentário `producer.py:503` ("Replay idempotente") é falso no caminho de produção, contra o Valor e o Estado-alvo declarados da story. **Elemento decisivo:** `test_replay_is_idempotent_for_the_same_universe` passa `opportunities=` E `companies=`, desvia em `producer.py:395-397` e nunca chama a projeção, com os helpers fixando `source_as_of=UTC_NOW` exatamente no campo que a produção randomiza — o checkbox de DoD linha 384 ("com evidência") está selado sobre evidência vácua para essa propriedade; busca repo-wide confirma que não há segundo teste. Empacotado: `date.today()` em `_blocked_result` (REL-002), mesma classe de TD-LI-7 e ponto cego de RULING-LI-04. **Devolução com 3 propriedades de aceite + re-medição obrigatória incluindo os 3 testes de AR-1.** **O que este FAIL NÃO faz:** não reabre o gate do @architect (ADR-040 segue Accepted, `gate_satisfied: true`; verifiquei `1 failed / 121 passed` DENTRO da janela de TD-LI-7 e AR-1 3 passed — o selo não cai), não reabre RULING-LI-01..04, não reabre a exceção de `pncp_raw_bids`, não reclassifica TD-LI-6 como bloqueador (verificado nos dois sentidos, não re-litigado) e não reabre AR-3/AR-4. ARCH-001 (exclusão contaminada pelo lado COMPANY, §7.2 vs §4.1) fica como pedido de adjudicação ao @architect, não como bloqueio. Revisão read-only: nenhum arquivo de `scripts/`, `tests/` ou `db/` editado. | @qa |
| 2026-09-03 | 1.13 | **Status: InProgress → InReview. Os 3 bloqueadores do QA FAIL corrigidos (iteração 1/5 do QA Loop), com prova real e checagem de mutação.** **(1) REL-001.** `source_as_of` deixou de vir de `datetime.now()` nos três sítios: `project_opportunity()` e `project_companies()` agora **exigem** o parâmetro, cujo único produtor é `fetch_source_watermark(...)['watermark_at']` — o `MAX(updated_at)` que o gate apontou como já computado e descartado. Ausência de watermark curto-circuita em `BLOCKED` **antes** da projeção; `require_watermark` removido porque "projetar sem watermark" era a única via pela qual o relógio de parede voltaria a ser necessário. `[AUTO-DECISION]` watermark do lado COMPANY = o mesmo de `fetch_source_watermark` (literalmente a `suggested_action` (1) do gate, que nomeia os dois sítios); a alternativa (`MAX` sobre `pncp_supplier_contracts`) abriria nova superfície de leitura outbound, fora de `scope_files` e de autoridade do @dev. **(2) Defeito adicional que a prova revelou, mesma classe, não estava no gate:** `fetch_source_watermark` lia `TIMESTAMPTZ` **sem** fixar o `TimeZone` da sessão, violando o invariante do próprio `sources.py`; o mesmo instante voltava com `tzinfo` diferente entre os dois builds e, como `live_hash` usa `isoformat()`, o `snapshot_id` **ainda divergia** com os três `datetime.now()` já removidos. Corrigido nas duas frentes independentes: `pin_session_timezone()` antes da leitura e `normalize_source_as_of()` (→ UTC) na construção — hash função do instante, não do fuso, a mesma propriedade do AC5. **(3) TEST-001.** Teste vácuo substituído por dois `build_snapshot()` **sem** universo injetado e **sem** `source_as_of` fixado, com contagem **TOTAL** de linhas **sem filtro de `snapshot_id`** (o filtro era o que escondia a acumulação) mais `COUNT(DISTINCT snapshot_id) == 1`. Adicionado teste do lado COMPANY porque `v_contracts_canonical_v2` tem 0 fornecedores no DSN e o teste de replay **não alcança** `producer.py:260` — sem ele, a propriedade escrita no gate estaria satisfeita provando metade do bug. **(4) REL-002.** `today_in_cutoff_timezone()` com `CUTOFF_TIMEZONE` importado por nome (nenhum segundo literal de fuso); asserção de `as_of_date`/`snapshot_id` adicionada — e, como a mutação `date.today()` **passou** por essa asserção no horário desta rodada (janela de ~3h/dia), foi adicionado teste sob dois fusos de SO a **25h** de distância, onde `date.today()` nunca coincide: prova determinística a qualquer hora. **(4b) Terceiro sítio da mesma classe, encontrado por auditoria própria depois de corrigir a escrita: o caminho de VERIFY.** `verifier.py` reconstrói os objetos de `row['source_as_of']` (`TIMESTAMPTZ` lido no fuso da sessão) e re-deriva os hashes de linha — medido que o verify **falha fechado sobre um snapshot íntegro** quando roda na MESMA conexão que fez o build (que pina `CUTOFF_TIMEZONE`), e passa em conexão nova. Todo caminho verde existente desviava: os testes do verifier injetam o universo (nunca pinam) e `cli verify` abre conexão nova. Corrigido com `normalize_source_as_of()` em `_rebuild_opportunity`/`_rebuild_company` e travado por `test_verify_on_the_same_connection_that_built_the_snapshot` (projeção real + asserção da pré-condição de fuso). **(5) Checagem de mutação:** os 4 sítios revertidos individualmente, cada um detectado pelo seu teste (tabela nas Dev Notes). **(6) Prova real de idempotência** (manual, fora da suíte): `snapshot_id` idêntico, `opportunities` 1→1 e `snapshots` 1→1 entre replays; controle negativo com o defeito reintroduzido: 1→2 e 1→2, `distinct_snapshot_id=2`. **(7) Re-medição:** motor **1 failed / 124 passed** (única falha = TD-LI-6/REL-003, dívida rulada; baseline 121, delta = os 3 testes novos); **AR-1 isolado 3 passed** (verificado primeiro, por ser o selo sensível a regressão); regressão dirigida **COM** `REQUIRE_REAL_DB=1` = **2 failed / 540 passed / 8 skipped**, ambas as falhas já caracterizadas pelo gate (volume de `sc_public_entities` e TD-LI-6) — **TEST-004 corrigido**; `ruff check`/`format --check` limpos. **Nada fora dos 3 bloqueadores foi tocado:** SEC-001/002, TEST-002..005, ARCH-001, REQ-001, REL-003, DOC-001..003, MNT-001..007, TD-LI-6 e RULING-LI-01..04 permanecem como estão; migration 104 e rollback **não** tocados. | @dev |
| 2026-09-03 | 1.14 | **QA Gate CONCERNS (iteração 2/5 do QA Loop) — Status: InReview → Done.** Os 3 bloqueadores do FAIL estão **corrigidos no caminho de produção**, e a prova é do @qa, não aceite do relato do @dev. **(1) Prova independente de idempotência** (script próprio, seeds `QA2-IDEM-` prefixo-escopados sob RULING-LI-01, teardown em `finally`): **três** builds sobre o mesmo snapshot de entrada, separados por 1,5s de relógio de parede **e** sob fusos de SO a 25h de distância (`Pacific/Kiritimati` UTC+14, `Pacific/Niue` UTC−11) → `snapshot_id` idêntico (`LI-2026-10-01-3a32e64d…`), `content_hash`/`data_hash`/`universe_hash` iguais, contagem **total por tabela sem filtro de `snapshot_id`** inalterada (`opportunities` 2→2→2, `snapshots` 1→1→1), `COUNT(DISTINCT snapshot_id)=1`, anti-vacuidade OK (`READY_CANONICAL`, `observed_opportunity_count=2`, 1º build persistiu). **(2) O terceiro sítio, do @dev, verificado no cenário que discrimina:** `verify_snapshot()` na **mesma conexão** que fez o build (sessão pinada em `CUTOFF_TIMEZONE`) aprova os 7 checks — era exatamente onde o verifier falhava fechado sobre snapshot íntegro. **(3) Verificação de código, não de comentário:** `source_as_of` é parâmetro keyword **obrigatório sem default** nos dois sítios (fallback de relógio de parede não é representável sem mudar a assinatura); `datetime.now()` sobrevive em 1 sítio (`producer.py:567`, colunas de auditoria) e a igualdade de hash acima **prova** que ele não é insumo de hash; zero `date.today()` em código executável do pacote; zero segundo literal de fuso. **(4) O vetor que decidiu o veredito e que nenhum teste exercitava — nem o meu, nem o do @dev:** ambas as provas mantinham o **watermark constante**, mas o caminho operacional normal é o crawl **mover** o watermark, o que muda todo hash e faz o `DELETE ... WHERE snapshot_id` não casar. Testei (build → `UPDATE updated_at +1h` escopado → build), depois de confirmar por grep que a 104 não tem `UNIQUE`/`EXCLUDE` sobre estado: INSERT sucedeu, **dois** snapshots coexistem, ambos `READY_CANONICAL`, ambos verificáveis. Se tivesse quebrado por constraint, o motor falharia no seu **segundo build real** — comportamento, e FAIL novo. Não quebrou. **(5) Achado novo REL-004 (medium):** `SNAPSHOT_SUPERSEDED` existe na lista fechada de estados, na transição documentada da 104 (:136), em `superseded_at` e no CHECK — mas **sem emissor e sem teste**; dois `READY_CANONICAL` do mesmo `as_of_date` coexistem com `superseded_at=NULL` e sem desempate. Mesma classe de TEST-005, sem consumidor vivo nesta wave. **REL-005 (low):** nota de escopo — a garantia é "mesmos dados de entrada ⇒ mesmo id", **não** estabilidade do id por `as_of` entre crawls (`source_as_of` é o watermark **global**); consistente com o risco residual §6.3 já declarado, e ratifico a `[AUTO-DECISION]` do @dev de não abrir segunda superfície de leitura outbound. **(6) Re-medição executada por mim, conferindo dígito a dígito:** motor **1 failed / 124 passed**; **AR-1 isolado 3 passed** — a condição anexada ao selo do @architect segue satisfeita, **o selo não cai**; regressão dirigida **com** `REQUIRE_REAL_DB=1` **2 failed / 540 passed / 8 skipped** — **TEST-004 corrigido**; `ruff` limpo. A única falha do motor é TD-LI-6/REL-003 (dívida rulada, mensagem exata da causa raiz); as duas da dirigida são as que eu mesma caracterizei. **Nenhuma falha nova.** **(7) Disposição dos 21 não-bloqueadores:** todos permanecem CONCERNS/dívida com owner e prazo no gate file; reexaminei o fundamento de cada um contra o código atual e nada mudou a razão — são lacuna de **instrumento**, não de **comportamento**, o mesmo critério com que o @architect fechou o gate HIGH-RISK com AR-3/AR-4 abertas. **SEC-001 é `high` e fica em CONCERNS** porque o risco é drift futuro e o texto literal do AC10 está atendido — **mas volta como bloqueador se um campo novo entrar em qualquer dataclass do motor**. **MNT-001 não condiciona este veredito, condiciona o fechamento do @po** (§8/§11: hooks leem o state file); não o agravei — escrevi só os campos de veredito e não reescrevi `snapshot_evidence`, conteúdo de outro agente. **(8) Ratifico a decisão de escopo do @dev:** corrigir os 2 sítios da **mesma classe** fora da minha lista foi correto (arquivos já em `scope_files`; sem eles a correção sairia com a metade de leitura quebrada — verifiquei), e não tocar nenhum item CONCERNS-class foi correto. Não é precedente para auto-ampliação. **(9) Limites da minha evidência, declarados:** o pacote está **untracked**, logo não tenho baseline de diff — verifiquei o **estado** dos arquivos, não o delta, e não endosso "apenas 6 arquivos tocados"; o lado COMPANY da projeção não é alcançável pelo build neste DSN (`verified_companies=0`), sua cobertura vem do teste do @dev que **auditei**; sem 2º DSN; `test_snapshot_reconciliation.py` skipped. Seeds `QA2-` criados e removidos (estado final: zero linhas, zero snapshots); nenhum arquivo de `scripts/`, `tests/` ou `db/` editado; nenhuma migration aplicada. **`next_agent`: @po** (fechamento, com os 5 itens de `return_to_po` do gate) → @devops. **Não reabre** o gate do @architect, RULING-LI-01..04, o reescopo do AC2, a exceção de `pncp_raw_bids`, TD-LI-6 nem AR-3/AR-4. **(10) Dois achados que só apareceram porque fui verificar uma afirmação minha.** **PUB-002 (low):** ao condensar os 21 não-bloqueadores eu escrevi que os textos integrais ficavam "preservados no histórico deste arquivo (git)" — fui verificar e é **falso**: `git check-ignore -v` aponta `.gitignore:58` → `docs/qa/gates/` e o `git log` do gate é **vazio**. A condensação teria **destruído** a evidência medida que os follow-ups consomem (os 7 termos de PII fora da blacklist de 11, as 3 tabelas `canonical_snapshot_*` fora de `PROTECTED_OBJECTS`, as contagens por família de `DROP`, a inércia dos GUCs, a sonda `DENIED`). **Restaurei os 21 blocos na íntegra**, com `qa_disposition_v2` por item. Um gate sobrescrito a cada iteração e sem histórico **não é registro durável de dívida** — o da story é, o que promove DOC-001 a única salvaguarda. **PUB-001 (medium):** `state.reviewed_commit=49989740` **não contém o código que revisei** (pacote, migration e rollback untracked), logo as pré-condições §8 **#5** (`reviewed_commit === HEAD`) e **#6** (working tree limpa) são hoje **mutuamente insatisfazíveis**. Commitar o pacote antes do fechamento e setar `reviewed_commit` para o SHA resultante; minha re-confirmação é `git diff` contra o estado que li, não nova revisão. Não bloqueia o veredito; bloqueia publicação limpa. | @qa |
