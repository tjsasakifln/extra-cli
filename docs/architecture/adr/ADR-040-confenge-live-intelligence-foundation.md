# ADR-040 — Fundação do motor CONFENGE_LIVE_INTELLIGENCE (decisões abertas do AC12)

- **Status:** **Accepted** (2026-09-02) — gate HIGH-RISK de arquitetura **FECHADO** com
  `gate_satisfied: true`, condicionado a AR-3 e AR-4 registradas como dívida (`CONCERNS`).
  Ver §"Fechamento do gate HIGH-RISK". O selo é **piso de evidência de arquitetura**, não
  veredito de qualidade (autoridade exclusiva do @qa) e não satisfaz RULING-LI-04.
- **Story:** `docs/stories/story-confenge-live-intelligence-01.md`
- **Normativo:** `docs/architecture/confenge-live-intelligence-impact-analysis.md`
- **Autor:** @dev (com @data-engineer para a decisão (b) e para os achados de catálogo)
- **Escopo:** registra **as quatro decisões abertas** que o AC12 atribui explicitamente ao @dev,
  mais dois achados empíricos de catálogo produzidos durante a implementação.

---

## Contexto

A story `confenge-live-intelligence-01` entrega a fundação de um motor **inbound**
(schema + producer + verifier + gate P0) estritamente aditivo ao pipeline outbound.
As oito decisões arquiteturais estruturais já estavam fechadas no `impact-analysis.md`
e **não são reabertas aqui**. O AC12 isola quatro itens que ficaram sem decisão
registrada e exige owner e artefato para cada um. Este é o artefato.

---

## Decisão (a) — `reason_codes` como `TEXT[]`

**Decisão:** `TEXT[]` em todas as tabelas do motor.

**Justificativa.** O critério declarado no AC12 é *consistência interna do motor*, não
consistência global do repositório — que hoje é bimodal (089 e o `schema-draft.sql` usam
`TEXT[]`; 071/072 usam `JSONB`). `TEXT[]` foi escolhido porque:

1. `reason_codes` é sempre um conjunto plano de rótulos de vocabulário fechado. `JSONB`
   permitiria estrutura aninhada, e a permissividade viraria drift.
2. `cardinality(reason_codes) > 0` é expressável diretamente em `CHECK` — e a 104 usa
   exatamente isso para tornar "exclusão sem motivo declarado" estruturalmente impossível.
   O equivalente em `JSONB` seria mais frouxo.
3. A família 089 (`canonical_snapshot_*`), que é a referência de engenharia do motor de
   snapshot, já usa `TEXT[]`.

**Exceção deliberada:** `blockers` permanece `JSONB` (espelhamento literal de 089) e
`evidence_refs` permanece `JSONB` porque é mapa, não conjunto. Não há mistura dentro do
mesmo conceito.

**Consequência aceita:** o motor inbound diverge de 071/072. Isso é intencional — são
motores diferentes com ciclos de mudança diferentes, que é a premissa da story.

---

## Decisão (b) — Role de leitura novo: `confenge_live_intel_reader` (owner: @data-engineer)

**Decisão:** role dedicado novo, **sem** reuso de `smartlic_public_reader`.

**Justificativa.** `smartlic_public_reader` tem contrato v1 publicado (`public_read_v1`,
janela de depreciação de 180 dias). Estender seu conjunto de objetos amplia um contrato
público já versionado sem passar por versionamento — o efeito colateral cai sobre
consumidores externos, não sobre o motor.

**Exclusão explícita registrada.** Cada objeto criado pela 104 recebe
`REVOKE ALL ... FROM smartlic_public_reader` imediatamente após o `CREATE`. Isso é
necessário e não redundante: os `REVOKE` de `090_public_read_select_only_lock.sql` usam
`ALL TABLES IN SCHEMA public`, que se aplica somente aos objetos existentes no momento da
execução, e não há `EVENT TRIGGER` reaplicando a barreira. Provado por
`tests/confenge_live_intelligence/test_migration_grants_and_rollback.py`.

**Grants do role novo.** Somente `SELECT` nas 6 tabelas do motor + `EXECUTE` na função
as-of + `USAGE` no schema + `CONNECT` no database. `default_transaction_read_only=on`,
`statement_timeout=2s`, `lock_timeout=500ms`. Teste dedicado prova que o role não recebeu
grant sobre nenhum objeto fora do prefixo `confenge_live_intelligence_`.

**Destino no rollback: DROP.** O role é removido (`DROP OWNED BY` + `DROP ROLE`),
condicionado ao marcador `COMMENT ON ROLE 'managed-by-extra-migration-104'` (padrão de
089). Reter um role inerte deixaria uma identidade de banco sem dono nem contrato; dropá-lo
torna o par migration/rollback simétrico e verificável por `SELECT 1 FROM pg_roles`
retornando zero linhas. Se o role possuir objetos fora do database, a exceção é capturada e
o role é retido com `NOTICE` — mesmo comportamento de 089.

---

## Decisão (c) — Replay as-of sobre `pncp_raw_bids` mutável: risco residual ACEITO

**Decisão:** registrado como **risco residual aceito nesta wave**, não como bug a corrigir.

`pncp_raw_bids` é mutada in-place (sem `valid_from`/`valid_to`). Um `UPDATE` posterior ao
fechamento do snapshot altera a base sobre a qual o snapshot foi derivado.

**Superfície de detecção (o que É coberto):**
- `universe_hash` + `data_hash` selados no header do snapshot;
- `verifier.py` re-deriva todos os hashes a partir do conteúdo **persistido no snapshot**
  e falha fechado em qualquer divergência;
- um replay do producer sobre a mesma `as_of_date` que produza `universe_hash` diferente do
  snapshot selado evidencia a mutação da base.

**O que NÃO é coberto:** a divergência é **detectada, não prevenida**. Não há como
reconstruir o estado histórico exato de `pncp_raw_bids` anterior ao `UPDATE`. Replay
temporal completo de oportunidades históricas está fora de escopo desta wave
(impact-analysis §6.3, R5).

**Follow-up de backlog (owner: @data-engineer):** versionamento temporal de `pncp_raw_bids`
(`valid_from`/`valid_to` ou tabela de histórico) — severidade MEDIUM, sem prazo definido.

---

## Decisão (d) — Ausência intencional de kill switch

**Decisão:** o motor inbound **não** reusa `truth_plane_kill_switch` do outbound e **não**
cria mecanismo próprio de pausa nesta story.

**Justificativa.** Reusar o kill switch outbound acoplaria os dois motores por um canal de
controle compartilhado — exatamente o acoplamento que a existência de um motor separado
pretende evitar. Um acionamento do kill switch outbound passaria a ter efeito colateral no
inbound, e vice-versa, criando dependência operacional invisível entre times com ciclos de
mudança diferentes.

**Mecanismo de pausa vigente:** não invocar o CLI/producer. O motor não é operacionalizado
nesta story (sem cron, sem systemd unit) — não há processo contínuo a pausar.

**Follow-up de backlog (owner: @devops, severidade MEDIUM):** quando o motor for
operacionalizado (story futura com cron/systemd), ele **precisa** de kill switch próprio,
independente do `truth_plane_kill_switch`. Essa story não deve ser aceita sem ele.

---

## Achado 1 (@dev → @data-engineer, ratificado) — §9 da 104 era inerte em PostgreSQL 16

O `ALTER DEFAULT PRIVILEGES FOR ROLE <owner> IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS
FROM PUBLIC` da §9 **não produzia efeito observável**: uma função criada depois pela mesma
role continua com `proacl = NULL` (default do PostgreSQL, que inclui `EXECUTE` para
`PUBLIC`). Os outros dois `REVOKE` da §9 também não gravavam linha em `pg_default_acl`.
Medido em **PostgreSQL 16.15**, com controle de sensibilidade do probe (um `REVOKE`
explícito sobre a função criada inverte o resultado, logo o instrumento não é cego).

**O que está provado é o efeito, não o mecanismo.** A causa interna no PostgreSQL não foi
determinada e a documentação oficial sugere o contrário — a medição é o fato; a explicação
não é tratada como tal.

**Decisão aplicada (@data-engineer, autoridade exclusiva sobre DDL): §9 removida.** A
barreira de segurança do motor **não** é um mecanismo de default privileges global: são os
**14 `REVOKE` explícitos por objeto** (2 por tabela nas 6 tabelas + 2 na função as-of,
contra `PUBLIC` e contra `smartlic_public_reader`), emitidos imediatamente após cada
`CREATE`. Esses funcionam e estão provados por
`tests/confenge_live_intelligence/test_migration_grants_and_rollback.py`. Manter §9 gerava
falsa sensação de proteção para objetos futuros.

A segunda metade do AC3 ("migration futura sob outra role não é afetada") continua
satisfeita — agora por construção (a 104 não escreve em `pg_default_acl`), não porque um
mecanismo inerte a satisfazia por acidente. Rigorosamente, a condicional do AC3 (2ª parte)
passa a ter **antecedente falso**: a 104 não adiciona `ALTER DEFAULT PRIVILEGES` algum.

O teste que media o achado foi **renomeado e reorientado** ao que de fato existe:
`test_alter_default_privileges_of_104_left_no_catalog_entry` →
`test_104_barrier_is_explicit_revokes_without_default_privileges`. Ele agora prova, por
**statement executável** (via o parser real de `apply_migrations` — uma busca por substring no
texto bruto daria falso positivo, já que o arquivo cita o termo em comentário explicando a
remoção), que (1) nenhum statement da 104 emite `ALTER DEFAULT PRIVILEGES` e (2) os 14 `REVOKE`
explícitos existem. A asserção de `pg_default_acl` vazia é **retida como guarda de regressão**:
é exatamente a condição que faria a seção 3 do rollback precisar voltar a emitir o `GRANT`
inverso (ver Achado 2).

**Consequência aceita:** objetos criados por migrations **futuras** do motor não herdam
proteção automática. Cada nova migration deve emitir seus próprios `REVOKE` explícitos **e
estender o teste estático de barreira ao seu próprio arquivo** — o teste atual lê a 104 como
texto e só cobre a 104. Não há hoje mecanismo que verifique migrations futuras.

## Achado 2 (@dev → @data-engineer, ratificado) — defeito corrigido no rollback da 104

A seção 3 do `db/rollback/104_..._rollback.sql` emitia, incondicionalmente,
`ALTER DEFAULT PRIVILEGES ... GRANT EXECUTE ON FUNCTIONS TO PUBLIC` como inverso do
`REVOKE` da migration. Verificado no mesmo probe: o `REVOKE` da 104 **não gravava** linha em
`pg_default_acl`, mas o `GRANT` inverso **grava** — criando exatamente a entrada de catálogo
que o critério de aceite do rollback proíbe ("`pg_default_acl` não retorna nenhuma entrada
criada pela 104"), e concedendo a `PUBLIC` um privilégio que a 104 nunca havia removido.

**Correção final:** com a §9 removida da migration, o rollback **não tem inverso a emitir**.
A seção 3 permanece vazia e documentada: o critério de aceite passa a ser verdadeiro por
construção, não por compensação condicional. Coberto por
`test_rollback_removes_every_object_and_reapply_is_clean`, que assere `pg_default_acl == []`
após o rollback e igualdade completa de ACLs após reaplicar a 104.

---

## Consequências

- O motor inbound é consumível por um único role, sem interseção com o contrato público v1.
- O par migration/rollback é simétrico e verificável por catálogo, não por prosa.
- Dois follow-ups de backlog ficam registrados com owner e severidade (versionamento de
  `pncp_raw_bids`; kill switch próprio na operacionalização).
- Os dois achados de DDL foram confirmados e resolvidos pelo @data-engineer: a §9 da 104
  foi removida e a seção 3 do rollback ficou vazia por construção. A barreira de segurança
  do motor são os 14 `REVOKE` explícitos por objeto — não um mecanismo de default
  privileges.

---

## Gate HIGH-RISK de arquitetura sobre o reescopo do AC2 (@architect, 2026-09-02)

- **Autoridade:** @architect (impacto sistêmico / aditividade), §2–§3 de
  `.claude/rules/aiox-project-operating-protocol.md`.
- **Objeto do gate:** o reescopo do AC2 (P0) feito pelo @po na v1.6 da story —
  de "protocolo de dois braços com execução real de `run_pipeline()`" para
  "não-referência de módulos outbound ao motor + diff de catálogo de ACLs".
- **Veredito:** **INACEITÁVEL COM AÇÃO REQUERIDA.** Não é ratificação. O escopo
  reduzido é defensável; a **evidência compensatória citada para sustentá-lo tem
  defeito verificado** e é load-bearing para o P0 "Não regredir outbound".
- **Status desta ADR na data do veredito:** permanecia **Proposed**. Este gate registrava
  decisão e ações exigidas; não emitia selo (`INDEX.md`: "não inventar selos de gate sem
  evidência"). **SUPERADO** pela §"Fechamento do gate HIGH-RISK" abaixo, que emite o selo
  contra evidência medida. O texto original desta seção é preservado sem alteração.

### Achado 1 — a redução de *escopo* é arquiteturalmente sã (não re-litigar)

O motor não é operacionalizado nesta story (sem cron/systemd, sem integração com
`message_spine.py` — Escopo OUT). Diferir a comparação byte-a-byte da **saída do
pipeline outbound** para `confenge-live-intelligence-outbound-equivalence-gate` é
legítimo: aquela prova responde "a *presença da migration* altera a saída outbound?",
que só se torna materialmente relevante quando o motor for acionado periodicamente.
O raciocínio do @po sobre o 2º DSN (RULING-LI-02 / RULING-LI-03) **não é reaberto**.

### Achado 2 — a evidência compensatória tem defeito verificado (o que bloqueia)

O AC2 v1.6 declara-se coberto "somados a AC1 e **AC11**". O AC11 afirma provar
"ausência de `INSERT`/`UPDATE`/`DELETE` referenciando qualquer tabela outbound".
**Ele não prova isso.** `tests/confenge_live_intelligence/test_no_outbound_dml_static.py`
prova apenas a ausência de **um único literal de string** que contenha
simultaneamente um verbo DML e o nome de uma tabela outbound. O próprio código
entregue usa a idiom que evade esse teste:

```python
# scripts/confenge_live_intelligence/producer.py:502-513
for table in ("confenge_live_intelligence_events", ...):   # nomes: literal SEM verbo DML
    cur.execute(f"DELETE FROM public.{table} WHERE snapshot_id = %s", ...)  # verbo DML SEM nome
```

Se um dia essa tupla incluir uma tabela outbound, o AC11 continua verde. A prova é
de **ausência de literal**, não de comportamento em runtime — e o AC2 reduzido
depende dela para a única afirmação que realmente importa ao P0: *o motor não
escreve no estado outbound*.

**Por que isto não é dívida da classe TD-LI-6** (o precedente será invocado; ele não
se aplica): TD-LI-6 foi aceito porque (i) o ramo do AC **estava** provado, (ii) a falha
era não-determinismo de infraestrutura e (iii) o insumo faltante era inproduzível por
qualquer agente do ciclo. Este achado falha nos três: a afirmação **não** está provada,
é **defeito de desenho de teste** (não flakiness) e o conserto cabe em ~10 linhas de
um arquivo existente, com o DSN único que já existe.

### Achado 3 — o diff de ACL descrito no AC2 não é o diff que o teste executa

O AC2 v1.6 e a Dev Notes descrevem "catálogo de ACLs **antes e depois da 104**".
`test_rollback_removes_every_object_and_reapply_is_clean` captura `before_rollback`
**já com a 104 aplicada** e compara contra pós-rollback e pós-reaplicação. Isso prova
que *o rollback* não altera ACL outbound — não que *a 104* não altera. O risco real é
baixo (verificado: a 104 não emite nenhum `GRANT`/`REVOKE` sobre objeto outbound), mas
o texto do AC afirma mais do que o teste entrega. Defeito de honestidade de evidência.

### Achado 4 — o gate estático de aditividade não cobre a superfície de privilégio

`MUTATING` em `tests/test_live_intelligence_outbound_equivalence.py:54` cobre
`ALTER TABLE|ALTER VIEW|DROP TABLE|DROP VIEW|CREATE OR REPLACE`. Um
`GRANT`/`REVOKE`/`COMMENT ON`/`ALTER DEFAULT PRIVILEGES`/`CREATE POLICY` sobre objeto
outbound passaria pelo AC1 sem falhar. Hoje não há violação viva — é buraco de
regressão em um gate P0.

### Ação mínima requerida antes de `Done` (nenhuma exige o 2º DSN)

| # | Ação | Severidade | Owner |
|---|---|---|---|
| **AR-1** | **Smoke de não-interferência em runtime.** Sobre o DSN único já em uso e seeds `LI-TEST-`: capturar `COUNT(*)` + `md5` do dump ordenado de **cada** objeto da lista protegida do AC1, executar `cli build` + `cli verify` completos, recapturar e exigir igualdade byte-a-byte. Janela de checksum abre **depois** do `seed_bid()` e fecha **depois** do producer — a fixture escreve em `pncp_raw_bids`, e envolver o seed produz falha confusa. Prova comportamento observado, não ausência de import | **BLOQUEANTE** | @dev |
| **AR-2** | **Fechar a evasão de SQL dinâmico do AC11.** Percorrer o AST: para todo literal DML com slot de interpolação (`f-string`/`.format`/`%`), exigir que os nomes de tabela interpolados sejam resolvíveis a **uma única constante nomeada, exportada pelo pacote do motor e importada por nome** pelo teste do AC11. Critério de aceite explícito: o teste deve **falhar** se qualquer módulo do glob construir DML interpolado a partir de um nome não resolvível àquela constante — uma tupla local nova em `events.py` (story 2) tem de quebrar o teste, não passar por ele. Sem essa amarração, AR-2 apenas reproduz o defeito do AC11 um nível acima | **BLOQUEANTE** | @dev |
| **AR-3** | **Baseline pré-104 real de ACL.** No mesmo fixture: rollback → snapshot → reaplicar 104 → snapshot → comparar `relacl`/`proacl` de todo objeto outbound. Corrige a divergência entre o texto do AC2 e o que o teste faz. **Não bloqueia `Done`**: o risco subjacente já está descartado por inspeção direta (a 104 não emite `GRANT`/`REVOKE` sobre objeto outbound). É correção de honestidade de evidência, não de afirmação falsa | HIGH (evidência) | @dev |
| **AR-4** | Ampliar `MUTATING` para `GRANT`, `REVOKE`, `ALTER DEFAULT PRIVILEGES`, `ALTER SEQUENCE`, `CREATE POLICY`, `CREATE RULE`, `CREATE INDEX ... ON`, `COMMENT ON` sobre objeto protegido | HIGH (hardening) | @dev |
| **AR-5** | **Condição do próprio gate de arquitetura, não tarefa atribuída.** `docs/stories/story-confenge-live-intelligence-outbound-equivalence-gate.md` **não existe** (verificado em `docs/stories/`). Este gate **não pode ser considerado satisfeito enquanto TD-LI-1 e TD-LI-6 apontarem para artefato inexistente** — um débito que referencia uma story que não está no backlog é risco invisível, e é sobre risco sistêmico invisível que a autoridade do @architect incide. A criação e a validação do artefato permanecem inteiramente sob RULING-LI-02 (@sm/@po); nada aqui reabre escopo | **CONDIÇÃO DO GATE** | conforme RULING-LI-02 |

### Por que AR-1 é a prova certa, e por que não torna o follow-up redundante

AR-1 é **mais forte** que o protocolo de dois braços para a pergunta do P0 "o motor
pode tocar o estado outbound?", porque observa diretamente o conteúdo das tabelas
outbound em vez de inferi-lo da saída do pipeline. O follow-up permanece necessário
porque responde a **outra** pergunta — "a presença da 104 altera a *saída* do
`run_pipeline()`?" — que exige os três insumos de @devops/@po já registrados.

### Decisões arquiteturais confirmadas neste gate (não reabrir)

- Aditividade estrutural do DDL da 104: **confirmada** por statement, contra as 8 decisões
  do `impact-analysis.md`.
- Barreira select-only exclusivamente por `REVOKE` explícito por objeto, sem
  `ALTER DEFAULT PRIVILEGES`: **arquiteturalmente aprovada** — mecanismo medido e provado
  substitui mecanismo afirmado e inerte.
- Escrita do motor confinada a `confenge_live_intelligence_*` com escopo `snapshot_id`:
  **confirmada por leitura de código** (`producer.py:495-664`); é o que AR-1 e AR-2 passam
  a proteger contra regressão.
- Leitura outbound estritamente `SELECT`, sem copiar campos de fit/sector para a COMPANY
  (Decisão 3, §3.2): **confirmada** em `sources.py:83-113` (lê apenas
  `v_contracts_canonical_v2`).
- Ausência de kill switch e não-reuso de `truth_plane_kill_switch`: **mantidas** — acoplar
  os motores destruiria o isolamento que justifica a story.

### Encaminhamento

`Done` da story só é arquiteturalmente admissível com **AR-1 e AR-2** fechados e com a
**condição AR-5** satisfeita. AR-3 e AR-4 são aceitáveis como `CONCERNS` documentado se
@qa assim julgar — nenhum dos dois cobre afirmação falsa. Classificar
`PASS`/`CONCERNS`/`FAIL` permanece autoridade exclusiva do @qa; este gate define o
**piso de evidência**, não o veredito.

---

## Fechamento do gate HIGH-RISK (@architect, 2026-09-02)

- **Autoridade:** @architect, mesma base do veredito original (§2–§3 de
  `.claude/rules/aiox-project-operating-protocol.md`).
- **Veredito:** **GATE FECHADO — `gate_satisfied: true`.** O veredito
  "INACEITÁVEL COM AÇÃO REQUERIDA" é **substituído**, não apagado: AR-1, AR-2 e a
  condição AR-5 estão satisfeitas contra evidência **medida por este agente**, não
  contra relato. AR-3 e AR-4 permanecem **abertas como dívida** (`CONCERNS`), como o
  próprio Encaminhamento já admitia.
- **Status desta ADR:** **Proposed → Accepted.**

### AR-2 — SATISFEITA (bloqueante)

O achado original era `producer.py:502-513`: tupla local de nomes de tabela interpolada
em f-string, com verbo DML e nome de tabela em literais separados — evasão da checagem
por literal único do AC11. Verificado no código entregue:

| Exigência do texto de AR-2 | Onde está | Verificado |
|---|---|---|
| Enumeração literal **única** | `schema.py:45` `WRITE_TARGET_ORDER` (6 alvos); `ALLOWED_WRITE_TARGETS:53` é **derivada** (`frozenset(WRITE_TARGET_ORDER)`), não uma segunda lista | ✅ |
| Constante **exportada pelo pacote** | `__init__.py` → `__all__` (`ALLOWED_WRITE_TARGETS`, `WRITE_TARGET_ORDER`, `assert_write_target`) | ✅ |
| **Importada por nome** pelo teste do AC11 | `test_no_outbound_dml_static.py:29-30` importa o pacote e a constante; `_sanctioned_allowlist_names()` **deriva** os nomes sancionados de `engine_pkg.__all__` em vez de listá-los à mão — uma lista local seria uma segunda allowlist e o teste passaria a proteger a si mesmo | ✅ |
| Resolução do slot a essa constante | `_dynamic_dml_violations()` exige, por slot: passagem por `assert_write_target()`, resolução a um `ast.Name`, *binding* rastreável, raiz sancionada, importada do pacote e **não re-vinculada** no módulo | ✅ |
| **Critério de aceite explícito:** tupla local nova (ex.: `events.py`, story 2) tem de **quebrar** o teste | `test_checker_rejects_every_known_evasion[tupla_local]` — é literalmente o cenário nomeado no gate | ✅ |
| "Sem essa amarração, AR-2 reproduz o defeito um nível acima" | `test_write_allowlist_is_disjoint_from_outbound_tables` fecha o modo de falha residual: bastaria acrescentar `opportunity_intel` à allowlist para todo o resto continuar verde | ✅ |
| Tupla local não pode voltar ao `producer.py` | `test_producer_persist_uses_the_allowlist_loop` proíbe qualquer coleção literal de nomes de tabela no módulo | ✅ |

O @dev **excedeu** o texto de AR-2 em um ponto que o gate não havia previsto e que era
buraco real: a família de **acumulação** (`sql += table`, `"".join([verbo, table])`) não
produz nenhum nó de AST que contenha verbo DML e slot simultaneamente, logo escapava do
próprio checker. `_accumulation_violations()` a proíbe, disparada pelo verbo DML — de
modo que a acumulação **SELECT-only** já existente em `sources.py:110` não gera falso
positivo. Isso importa porque esse idiom já vive no pacote e é o caminho natural para
`events.py` na story 2.

**Evidência de execução (medida por este agente):**
`tests/confenge_live_intelligence/test_no_outbound_dml_static.py` → **41 passed**
(inclui os 10 auto-testes negativos, o controle negativo do controle
`test_checker_accepts_the_sanctioned_idiom` — sem ele o checker poderia ser um
`assert False` — e a guarda de runtime `test_write_guard_rejects_outbound_target_at_runtime`,
que prova falha fechada sem banco).

**Limite honesto da prova estática, declarado:** o checker dispara quando o verbo DML
aparece nas *partes literais* do nó. Uma construção que interpole **o próprio verbo**
fica fora do texto de AR-2 e fora do checker. AR-1 é exatamente o controle compensatório
dessa classe — é por isso que as duas ações eram conjuntas, e não alternativas.

### AR-1 — SATISFEITA (bloqueante)

`tests/confenge_live_intelligence/test_no_outbound_write_runtime.py`. Conferido contra o
texto de AR-1, cláusula por cláusula:

- **Sem lista paralela.** Os objetos vêm de `PROTECTED_OBJECTS` (a lista do AC1),
  importada de `tests/test_live_intelligence_outbound_equivalence.py`, filtrada pelo que
  existe em `pg_class`. **Medido: 15 de 15 presentes no DSN de teste** (13 tabelas base +
  `v_contracts_canonical_v2` e `v_open_opportunities_canonical` como views); **nenhum
  ausente**. O fingerprint não é escopado a um subconjunto.
- **`COUNT(*)` + md5 do dump ordenado** por `t::text` (não `ctid`), de modo que views
  também sejam cobertas e o hash não dependa da ordem física.
- **Janela conforme AR-1:** abre **depois** de `seed_bid()` e fecha **depois** do
  producer, como o gate determinou.
- **`cli build` + `cli verify` completos**, com igualdade byte-a-byte **incondicional** —
  a asserção P0 vale também no ramo `BLOCKED`; só a asserção sobre o *exit code* de
  `verify` é condicionada a estado verificável, e a condicionalidade está declarada no
  docstring do módulo.
- **Anti-vacuidade:** `test_engine_did_write_its_own_tables_in_the_same_run` prova que o
  mesmo caminho de código escreve de fato em `confenge_live_intelligence_snapshots` —
  sem isso, AR-1 provaria um no-op.
- **Dentes do instrumento:** `test_fingerprint_detects_a_single_row_change` prova que um
  checksum cego não passaria sempre, e distingue corretamente *view que muda por
  construção* de *escrita em tabela base*.

**Evidência de execução (medida por este agente):** 3 passed sob
`REQUIRE_REAL_DB=1`, `LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test`.

**Sonda adicional deste gate — o ramo `verify` é o executado.** A condicionalidade
declarada poderia esconder que `cli verify` nunca roda. Medido no mesmo fixture:
`state=READY_CANONICAL`, `code=0`, `blockers=[]`, `observed_opportunity_count=1`. Logo o
caminho condicional **não** é o caminho tomado, e a cláusula "build + verify completos"
de AR-1 está de fato exercida.

### Efeito de TD-LI-7 sobre a evidência de AR-1 — medido, e é nulo

RULING-LI-04 (@po) elevou TD-LI-7 a HIGH invocando, como argumento decisivo (b), que
`today_utc()` é chamada em `test_no_outbound_write_runtime.py:128` e `:183`, "dentro da
única evidência de AR-1", deixando uma janela de indeterminação de ~3h/dia sob a própria
prova do gate. **Este gate mediu essa hipótese e ela não se sustenta para AR-1** —
por razão **estrutural**, não por sorte:

- o seed usa `data_encerramento = now + 30d`, logo um deslocamento de ±1 dia em
  `--effective-date` não pode virar um edital de aberto para fechado;
- o `state` do snapshot é governado por **presença de watermark** (é essa a mecânica da
  própria análise de TD-LI-6), não pela data civil;
- a asserção de checksum é **incondicional** nos dois ramos.

Sonda: `--effective-date` em `delta = −1 / 0 / +1` → `READY_CANONICAL` nos três casos,
`opps=1`, `blockers=[]`. Ou seja, `cli verify` roda em toda a janela.

**Limite deste achado, para que o @qa não o leia como reabertura.** Ele contradiz
**apenas o fundamento (b)** de RULING-LI-04. Os fundamentos (a) — não há ampliação de
escopo, os arquivos já constam de `scope_files` —, (c) — a cobertura de AC4 não é
independente do defeito, porque `test_as_of_current_date_equals_canonical_view` também
chama `today_utc()` e sobrevive por distribuição do seed — e (d) — defeito latente
generalizado, não um teste flaky — **sustentam o ruling por si sós**. RULING-LI-04
**permanece de pé e é vinculante**; escopo é autoridade do @po e este gate **não a
reabre**. A correção continua obrigatória nesta story.

**Nota adiante, e não uma AR nova.** A correção exigida por RULING-LI-04 altera
`today_utc()`, chamada dentro do arquivo de evidência de AR-1. Portanto a re-medição
obrigatória do @dev **tem de incluir os 3 testes de AR-1**; se eles regredirem, este
selo cai com eles.

### AR-5 — CONDIÇÃO SATISFEITA

`docs/stories/story-confenge-live-intelligence-outbound-equivalence-gate.md` **existe**
(status `Draft`, criada pelo @sm). A condição que este gate escreveu era de
**existência** — "não pode ser considerado satisfeito enquanto TD-LI-1 e TD-LI-6
apontarem para artefato inexistente" — e explicitamente deferiu criação **e validação**
a RULING-LI-02 (@sm/@po). Verificado que o stub absorve **os dois** débitos nomeados:
TD-LI-1 (linha 77) e TD-LI-6 (linha 78), com o 2º DSN descartável como pré-requisito
declarado. O risco que a AR-5 combatia era **débito apontando para artefato inexistente**;
esse risco deixou de existir.

**Exigir validação do @po antes de fechar AR-5 seria estender a condição que este gate
escreveu e usurpar autoridade do @po.** Não é feito. `Draft` satisfaz AR-5.

### AR-3 e AR-4 — permanecem ABERTAS como dívida (`CONCERNS`)

| # | Estado verificado | Encaminhamento |
|---|---|---|
| **AR-3** | Não implementada. `test_rollback_removes_every_object_and_reapply_is_clean` continua capturando `before_rollback` já com a 104 aplicada | Dívida HIGH (evidência). Não bloqueia: o risco subjacente segue descartado por inspeção direta — a 104 não emite `GRANT`/`REVOKE` sobre objeto outbound. Owner @dev; classificação do @qa |
| **AR-4** | Não implementada — confirmado: `MUTATING` em `tests/test_live_intelligence_outbound_equivalence.py:54` continua cobrindo apenas `ALTER TABLE\|ALTER VIEW\|DROP TABLE\|DROP VIEW\|CREATE OR REPLACE`. `GRANT`/`REVOKE`/`COMMENT ON`/`ALTER DEFAULT PRIVILEGES`/`CREATE POLICY` sobre objeto protegido passariam pelo AC1 | Dívida HIGH (hardening). Buraco de regressão em gate P0, sem violação viva hoje. Owner @dev; classificação do @qa |

### O que este selo NÃO é

1. **Não é veredito de qualidade.** `PASS`/`CONCERNS`/`FAIL` é autoridade **exclusiva**
   do @qa. Este gate fecha o **piso de evidência de arquitetura**.
2. **Não satisfaz RULING-LI-04** e **não roteia a story para o @qa.** A story permanece
   `InProgress` com `next_agent: @dev`, pela correção de TD-LI-7 e pela re-medição
   obrigatória — decisão de escopo do @po, que este gate não toca. Roteamento não é
   autoridade do @architect.
3. **Não altera o AC2 reescopado nem RULING-LI-02/LI-03.** O follow-up
   `confenge-live-intelligence-outbound-equivalence-gate` permanece **bloqueante** para
   qualquer story que operacionalize o motor (cron/systemd, integração com
   `message_spine.py`, personalização de outbound). AR-1 responde "o motor pode tocar o
   estado outbound?"; o follow-up responde "a presença da 104 altera a *saída* do
   `run_pipeline()`?" — perguntas distintas, e a segunda continua sem resposta.
4. **Não fecha AR-3 e AR-4.** Se o @qa julgar que qualquer uma delas deve ser corrigida
   antes de `Done`, este gate não se opõe — o piso de evidência é mínimo, não máximo.
