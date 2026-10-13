# Contract Lifecycle Truth v1

**Status:** implementado (migration `103_contract_lifecycle_truth.sql`), aguardando gate de QA
**Decisão:** aditiva — nenhum objeto pré-existente foi alterado
**Autor:** Dex (@dev) — story `docs/stories/story-contract-lifecycle-truth-v1.md`
**Data:** 2026-09-01
**Contrato:** `CONTRACT_LIFECYCLE_TRUTH/1.0`

Documento autocontido: a tabela-verdade completa está reproduzida aqui na
íntegra, para que este arquivo sirva de referência sem depender da story.

---

## 1. Decisão

`v_contracts_canonical_v2` (migration 077) expõe `is_active`. Em produção esse
campo é **100% TRUE / 0% FALSE** — ele não carrega informação e não consegue
distinguir "contrato comprovadamente ativo hoje" de "contrato histórico".

Ao mesmo tempo, `scripts/contracts_truth.py` + migration 091 já carimbam
`status_normalized` e `quality_state` em `public.pncp_supplier_contracts`, e
nenhuma dessas 12 colunas é carregada pela view canônica.

**Decidido:** adicionar uma view nova, puramente aditiva,
`public.v_contract_lifecycle_truth_v1`, que **projeta** (nunca re-deriva) esses
carimbos em um vocabulário explícito de ciclo de vida, mais três funções SQL
sancionadas que reproduzem a precedência da data do ato contratual e o piso da
janela rolante de três anos.

**Não decidido / explicitamente fora de escopo:** nenhum consumidor foi
religado à view nova. `commercial_authority_v2.py` e o `QUALIFICATION_SQL` de
`rebuild_commercial_qualification.py` continuam lendo `v_contracts_canonical_v2`
sem alteração, portanto **quem qualifica para o ICP não mudou**.

### Por que isto não é consolidação (contabilidade honesta)

Antes desta story havia **2 implementações** da precedência da data do ato
contratual: o Python em `commercial_authority_v2.contracting_date()` e o `CASE`
SQL inline dentro de `QUALIFICATION_SQL`. Depois desta story há **3** (as duas
acima mais `contract_contracting_date_v1`/`contract_contracting_date_field_v1`).

Isso é um aumento deliberado e temporário de duplicação. A story 3 substitui o
`CASE` inline do rebuilder por leitura das funções novas, e a contagem volta a
2. Até lá, o `CASE` inline e as funções novas são **duas cópias mantidas
independentemente que podem divergir** — risco registrado e aceito, não
esquecido. O teste de paridade SQL-vs-Python (AC3) existe exatamente para tornar
essa consolidação futura segura.

---

## 2. Schema PostgreSQL

### 2.1 Objetos criados pela migration 103

| Objeto | Tipo | Assinatura / grão |
|---|---|---|
| `public.contract_contracting_date_v1` | FUNCTION (IMMUTABLE, PARALLEL SAFE) | `(DATE, DATE, DATE, DATE) RETURNS DATE` |
| `public.contract_contracting_date_field_v1` | FUNCTION (IMMUTABLE, PARALLEL SAFE) | `(DATE, DATE, DATE, DATE) RETURNS TEXT` |
| `public.contract_window_floor_v1` | FUNCTION (IMMUTABLE, PARALLEL SAFE) | `(anchor DATE) RETURNS DATE` |
| `public.v_contract_lifecycle_truth_v1` | VIEW | 1 linha por `dedup_key` |

Nenhum `ALTER`, nenhum `DROP`, nenhum `CREATE OR REPLACE` sobre objeto
pré-existente. As migrations 077, 091 e 101 não foram tocadas.

### 2.2 População e grão

- **Filtro de população** replicado de `077_contract_roles_canonical_v2.sql:212`,
  escrito parentetizado porque `AND` liga mais forte que `OR`:
  `WHERE (contract.data_inicio IS NOT NULL OR contract.data_publicacao IS NOT NULL)`.
  Paridade de população com `v_contracts_canonical_v2` é intencional.
- **Chave de dedupe:** `COALESCE(NULLIF(canonical_contract_id, ''), contrato_id)`.
  `canonical_contract_id` (091) não tem constraint de unicidade e não foi
  backfilled; linhas sem ele caem para `contrato_id`, que é `UNIQUE`
  (`pncp_supplier_contracts_contrato_id_key`), e nunca são colapsadas com
  linhas alheias.
- **Desempate determinístico:**
  `DISTINCT ON (dedup_key) ... ORDER BY dedup_key, last_seen_at DESC NULLS LAST, id DESC`.
  `id` é a PK serial da tabela base, então a ordenação é total e nunca empata.
- **Join de papéis** reutilizado verbatim de 077:169-212
  (`contract_role_links` → `sc_public_entities`). Nenhum join novo foi inventado.

---

## 3. Semântica dos campos

### 3.1 Universo de enums (autoridade: `scripts/contracts_truth.py:59-71`)

- `status_normalized` ∈ `{ACTIVE_PROVEN, COMPLETED, CANCELLED, TERMINATED, SUSPENDED, UNKNOWN, NULL}`
  — 6 valores carimbados (`ACTIVITY_STATES`) mais `NULL` (linha nunca carimbada).
- `quality_state` ∈ `{VALID, REVIEW, QUARANTINED, NULL}` — 3 valores carimbados
  (`QUALITY_STATES`) mais `NULL`.

### 3.2 `lifecycle_state` — função de `status_normalized` APENAS

| `status_normalized` | `lifecycle_state` |
|---|---|
| `ACTIVE_PROVEN` | `ACTIVE_PROVEN` |
| `COMPLETED` | `COMPLETED` |
| `CANCELLED` | `CANCELLED` |
| `TERMINATED` | `TERMINATED` |
| `SUSPENDED` | `SUSPENDED` |
| `UNKNOWN` | `UNKNOWN` |
| `NULL` | `UNKNOWN` (ausência de carimbo nunca é prova de atividade nem de encerramento) |

A view **projeta, nunca re-deriva**: ela jamais inventa um `status_normalized`
que `classify_contract_activity` não tenha carimbado.

### 3.3 `lifecycle_trust` — função de `quality_state` APENAS

| `quality_state` | `lifecycle_trust` |
|---|---|
| `VALID` | `TRUSTED` |
| `REVIEW` | `REVIEW` |
| `QUARANTINED` | `UNTRUSTED` |
| `NULL` | `UNSTAMPED` |

### 3.4 `lifecycle_is_current_evidence` — o AND-gate

```
lifecycle_is_current_evidence :=
    (lifecycle_state = 'ACTIVE_PROVEN') AND (lifecycle_trust = 'TRUSTED')
```

Equivalentemente: `TRUE` **se e somente se**
`status_normalized = 'ACTIVE_PROVEN' AND quality_state = 'VALID'`. Qualquer
outra combinação é `FALSE`. É `TRUE` em exatamente 1 das 28 células, por
projeto — é o sinal mais estrito da view. Quem quiser um sinal mais frouxo
(por exemplo "está em `ACTIVE_PROVEN` independentemente de confiança") lê
`lifecycle_state` diretamente.

Na SQL o gate usa `IS NOT DISTINCT FROM` nos dois lados, de modo que o
resultado é sempre estritamente `TRUE`/`FALSE` mesmo quando um dos carimbos é
`NULL` (fail-closed, nunca `NULL` de três valores).

### 3.5 `lifecycle_reason_codes` — vocabulário e cardinalidade

| Código | Emitido quando |
|---|---|
| `LIFECYCLE_UNSTAMPED` | `status_normalized IS NULL` |
| `LIFECYCLE_LEGACY_IS_ACTIVE_IGNORED` | `status_normalized IS NULL` **e** `is_active = TRUE` |
| `LIFECYCLE_QUALITY_UNSTAMPED` | `quality_state IS NULL` |
| `LIFECYCLE_TRUSTED` | `quality_state = 'VALID'` |
| `LIFECYCLE_REVIEW` | `quality_state = 'REVIEW'` |
| `LIFECYCLE_UNTRUSTED` | `quality_state = 'QUARANTINED'` |

É o array de **todos** os códigos cuja condição vale, não uma escolha 1-de-N:

1. **Exatamente um código de qualidade, sempre** (os 4 valores de
   `quality_state` são exaustivos e mutuamente exclusivos).
2. **Mais `LIFECYCLE_UNSTAMPED`, aditivamente**, quando `status_normalized IS NULL`.
3. **Mais `LIFECYCLE_LEGACY_IS_ACTIVE_IGNORED`, aditivamente**, quando
   `status_normalized IS NULL` **e** `is_active = TRUE` (subconjunto estrito do
   caso 2 — nunca dispara sem o `LIFECYCLE_UNSTAMPED` também disparar).

Ordem no array: código de qualidade primeiro, depois `LIFECYCLE_UNSTAMPED`,
depois `LIFECYCLE_LEGACY_IS_ACTIVE_IGNORED`. Cardinalidade de 1 a 3, nunca 0.

**`is_active` é lido mas nunca projetado.** Ele só decide se o marcador de
auditoria `LIFECYCLE_LEGACY_IS_ACTIVE_IGNORED` é emitido; jamais influencia
`lifecycle_state`, `lifecycle_trust` ou `lifecycle_is_current_evidence`.

### 3.6 Tabela-verdade completa (7 × 4 = 28 combinações, exaustiva)

Formato da célula: `lifecycle_state / lifecycle_trust / lifecycle_is_current_evidence`.

| `status_normalized` ↓ \ `quality_state` → | `VALID` | `REVIEW` | `QUARANTINED` | `NULL` |
|---|---|---|---|---|
| `ACTIVE_PROVEN` | `ACTIVE_PROVEN / TRUSTED / TRUE` | `ACTIVE_PROVEN / REVIEW / FALSE` | `ACTIVE_PROVEN / UNTRUSTED / FALSE` | `ACTIVE_PROVEN / UNSTAMPED / FALSE` |
| `COMPLETED` | `COMPLETED / TRUSTED / FALSE` | `COMPLETED / REVIEW / FALSE` | `COMPLETED / UNTRUSTED / FALSE` | `COMPLETED / UNSTAMPED / FALSE` |
| `CANCELLED` | `CANCELLED / TRUSTED / FALSE` | `CANCELLED / REVIEW / FALSE` | `CANCELLED / UNTRUSTED / FALSE` | `CANCELLED / UNSTAMPED / FALSE` |
| `TERMINATED` | `TERMINATED / TRUSTED / FALSE` | `TERMINATED / REVIEW / FALSE` | `TERMINATED / UNTRUSTED / FALSE` | `TERMINATED / UNSTAMPED / FALSE` |
| `SUSPENDED` | `SUSPENDED / TRUSTED / FALSE` | `SUSPENDED / REVIEW / FALSE` | `SUSPENDED / UNTRUSTED / FALSE` | `SUSPENDED / UNSTAMPED / FALSE` |
| `UNKNOWN` | `UNKNOWN / TRUSTED / FALSE` | `UNKNOWN / REVIEW / FALSE` | `UNKNOWN / UNTRUSTED / FALSE` | `UNKNOWN / UNSTAMPED / FALSE` |
| `NULL` | `UNKNOWN / TRUSTED / FALSE` | `UNKNOWN / REVIEW / FALSE` | `UNKNOWN / UNTRUSTED / FALSE` | `UNKNOWN / UNSTAMPED / FALSE` |

**A célula `(ACTIVE_PROVEN, REVIEW)` é explícita, não indefinida:**
`lifecycle_state` permanece `ACTIVE_PROVEN` porque estado de atividade e flag de
qualidade são dimensões ortogonais, carimbadas por dois classificadores
diferentes (`classify_contract_activity` e `classify_contract_quality`).
`lifecycle_trust = 'REVIEW'` propaga a flag honestamente em vez de escondê-la.
`lifecycle_is_current_evidence = FALSE` porque o AND-gate exige `TRUSTED`, não
apenas "não `UNTRUSTED`".

### 3.7 Data do ato contratual e janela de qualificação

- **Precedência:** `data_assinatura → data_inicio → data_publicacao → data_publicacao_fonte`
  (primeiro não-NULL vence), idêntica a `QUALIFYING_DATE_PRECEDENCE`
  (`commercial_authority_v2.py:39-44`). `data_fim` está deliberadamente fora: é
  estimativa de fim de execução e tornaria a janela não-determinística.
- **Caso todos-NULL:** `contract_contracting_date_v1` retorna SQL `NULL` (a
  contraparte DATE do `None` do Python) e `contract_contracting_date_field_v1`
  retorna `''` (string vazia), **nunca** SQL `NULL` — espelhando
  `return None, ""` em `commercial_authority_v2.py:133` byte a byte.
- **Piso da janela:** `contract_window_floor_v1(anchor)` = âncora menos 3 anos
  com normalização Go-style de estouro de dia **para a frente**
  (`2024-02-29` − 3a → `2021-03-01`, não `2021-02-28`, pois 2021 não é
  bissexto). Idêntico a `add_years_go(anchor, -3)`. `CURRENT_DATE - INTERVAL '3 years'`
  **não é aceitável**: o Postgres trunca o dia do mês em vez de rolar para a
  frente, divergindo de Go/Python exatamente no caso 29-fev.
- **`contracting_date_in_qualification_window`** =
  `contracting_date BETWEEN contract_window_floor_v1(CURRENT_DATE) AND CURRENT_DATE`,
  com `COALESCE(..., FALSE)`. O limite superior é `CURRENT_DATE`, casando com a
  exclusão `resolved > today` de `qualify_root` (`commercial_authority_v2.py:225`).
  A view e o teste de paridade chamam **a mesma função** — existe uma única
  implementação da aritmética do piso, nunca duas cópias.

---

## 4. Comandos reproduzíveis

### 4.1 Aplicar a migration

```bash
export LOCAL_DATALAKE_DSN="postgresql://test:test@127.0.0.1:5433/extra_test"
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
```

### 4.2 Gate real de banco (prova AC6-AC15)

```bash
REQUIRE_REAL_DB=1 LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test \
  python3 -m pytest tests/test_contract_lifecycle_truth.py \
                    tests/test_contract_lifecycle_truth_precedence.py \
                    tests/test_contract_lifecycle_truth_window.py -m real_db -v
```

Sob `REQUIRE_REAL_DB=1`, `real_db_skip_is_forbidden()` (`tests/conftest.py`)
transforma um skip inesperado em falha. **Um `SKIPPED` não conta como PASS**:
uma execução verde sob essa invocação é, ela própria, a evidência de que os
testes rodaram de verdade.

### 4.3 Testes estáticos (sem banco)

```bash
python3 -m pytest tests/test_contract_lifecycle_truth_migration_static.py \
                  tests/test_contract_lifecycle_truth_no_rebind.py \
                  tests/integration/test_all_sql_references.py -v
```

### 4.4 Suíte completa e lint

```bash
python3 -m pytest tests/ -q --tb=no -x
ruff check scripts/ tests/
ruff format --check scripts/ tests/
```

### 4.5 Distribuição real (pós-deploy, NÃO parte da suíte)

`scripts/reports/contract_lifecycle_distribution.sql` produz a distribuição por
célula `lifecycle_state` × `lifecycle_trust`.

**NOT_READY:** a consulta é correta e reprodutível, mas **ainda não foi rodada
contra dados reais**. O DataLake local de teste está vazio de dados de produção,
então ela retorna zero linhas ali — um resultado vazio não é evidência de nada.
Rodar como passo de verificação pós-deploy contra uma cópia read-only de
produção ou staging.

---

## 5. Limitações e NOT_READY

| Item | Estado | Nota |
|---|---|---|
| Ramo terminal da regra (`CANCELLED`/`TERMINATED`/`SUSPENDED`) | Código correto, **inalcançável por dados reais** | Produção tem **0 contratos** nesses estados: o campo de situação oficial do PNCP ainda não está ligado ao carimbador. Cenário A1 é testável apenas por fixture sintética. Não é lacuna da story. |
| Distribuição real por célula | NOT_READY | DB local vazio; ver §4.5. |
| `status_observed_at` | Nunca populado por `stamp_contract_truth_labels` | Backfill de ~2,86M linhas — story 2. |
| Divergência da precedência | Risco aceito e registrado | O `CASE` inline de `rebuild_commercial_qualification.py` e as funções novas são cópias independentes até a story 3. |
| Índice em `status_normalized`/`lifecycle_state` | Não criado | `EXPLAIN` em produção mostrou Seq Scan mesmo filtrando por `status_normalized` a 12,9% de seletividade — sem ganho comprovado. Revisitar quando a view tiver consumidores reais. |
| População além do filtro de v2 | Não ampliada | Contratos com `data_inicio` e `data_publicacao` ambos `NULL` são invisíveis aqui, como em v2. Ampliar só quando houver consumidor concreto. |

---

## 6. Arquivos alterados

| Arquivo | Natureza |
|---|---|
| `db/migrations/103_contract_lifecycle_truth.sql` | novo — 3 funções + 1 view, aditivo |
| `scripts/reports/contract_lifecycle_distribution.sql` | novo — consulta de distribuição (NOT_READY) |
| `scripts/schema/audit_sql_references.py` | editado — `KNOWN_VIEWS` +1, `KNOWN_FUNCTIONS` +3 |
| `tests/integration/test_migration_fresh_install.py` | editado — `EXPECTED_VIEWS` 23 → 24 |
| `tests/integration/test_all_sql_references.py` | inalterado (passa com os novos registros) |
| `tests/test_contract_lifecycle_truth.py` | novo — AC4-AC14, AC18 secundário, tabela de 28 células |
| `tests/test_contract_lifecycle_truth_precedence.py` | novo — AC3, paridade SQL-vs-Python |
| `tests/test_contract_lifecycle_truth_window.py` | novo — AC15, paridade do piso da janela |
| `tests/test_contract_lifecycle_truth_migration_static.py` | novo — AC1, aditividade + diff contra `scope_files` |
| `tests/test_contract_lifecycle_truth_no_rebind.py` | novo — AC18, prova estrutural de não-religação |
| `docs/decisions/contract-lifecycle-truth-v1.md` | novo — este documento |
| `docs/stories/story-contract-lifecycle-truth-v1.md` | editado — checkboxes, Dev Agent Record |
| `.aiox/state/stories/contract-lifecycle-truth-v1.json` | editado — status e gates |

**Não alterados, por construção e por teste:** `db/migrations/077`, `091`, `101`,
`scripts/confenge_activation/commercial_authority_v2.py`,
`scripts/confenge_activation/rebuild_commercial_qualification.py`,
`scripts/contracts_truth.py`, `scripts/testing/connection_policy.py`.

---

## 7. Checklist de verificação

- [x] Migration sem `ALTER`, sem `DROP`, `CREATE OR REPLACE` só para os 4 nomes que ela própria cria
- [x] `git diff` contra a base de merge é subconjunto de `scope_files`
- [x] 3 funções existem, `is_deterministic = 'YES'` (IMMUTABLE) e `pg_proc.proparallel = 's'` (PARALLEL SAFE)
- [x] Precedência SQL idêntica à Python nas 4 permutações mais o caso todos-NULL; campo retorna `''`, nunca `NULL`
- [x] Piso da janela idêntico a `add_years_go(anchor, -3)` para `2024-02-29` → `2021-03-01` e `2026-09-01` → `2023-09-01`
- [x] `contract_window_floor_v1(CURRENT_DATE)` = `window_floor(datetime.now(UTC))` com sessão fixada em UTC
- [x] Tabela-verdade de 28 células asserida célula a célula, incluindo o array exato de `lifecycle_reason_codes`
- [x] `lifecycle_is_current_evidence` é `TRUE` em exatamente 1 das 28 células
- [x] `is_active` não é coluna projetada da view
- [x] Dedupe: 1 linha por `dedup_key`, desempate por `last_seen_at DESC NULLS LAST, id DESC`
- [x] Paridade de população com `v_contracts_canonical_v2`
- [x] `commercial_authority_v2.py` e `QUALIFICATION_SQL` não referenciam nenhum objeto novo
- [ ] Distribuição real por célula executada contra cópia de produção (pós-deploy — ver §4.5)
- [ ] Migration aplicada a um banco **novo e limpo** — não exercitado pelo @dev: neste ambiente só existia o
      banco já migrado até a 102, onde a aplicação foi limpa
      (`applied 103_contract_lifecycle_truth.sql`, `migrations_ok mode=upgrade applied=1 skipped=104`).
      A 103 é `CREATE OR REPLACE` apenas para os próprios 4 objetos e depende só de objetos de 077/091,
      portanto é segura em fresh install por construção — mas isso é afirmação estrutural, não execução.
      Deixado para o @qa confirmar.

### Nota sobre os gates de lint

`ruff check scripts/ tests/` passa no repositório inteiro. `ruff format --check scripts/ tests/` reporta
**705 arquivos** que seriam reformatados — desvio pré-existente do repositório, não desta story: os 7
arquivos Python tocados aqui estão todos em `7 files already formatted`, e o gate real do repositório
(`tests/test_ruff_repository_gate.py`) passa com 4/4.
