# CONFENGE_LIVE_INTELLIGENCE/1.0 — Análise de Impacto e Desenho Arquitetural Aditivo

> **Missão:** CONFENGE-REVENUE-MULTI-ENGINE-W1
> **Autoridade:** @architect (Aria)
> **Status:** DESIGN — nenhuma linha de código de produção ou migration real foi escrita
> **Branch de origem da análise:** `review/universe-parafiscal-clean`
> **Data:** 2026-09-02

---

## 0. Sumário executivo

Este documento fecha as 8 decisões arquiteturais para um novo motor **INBOUND** —
`CONFENGE_LIVE_INTELLIGENCE/1.0` — que observa oportunidades públicas abertas e as
relaciona a empresas com execução pública observável, produzindo um **handoff
snapshotado, replayable e fail-closed**.

O motor é **estritamente aditivo**. Ele:

- **lê** primitivos outbound existentes (identidade de contrato, precedência de datas,
  views canônicas) em modo read-only;
- **escreve** apenas em tabelas novas criadas pela migration `104`;
- **nunca** escreve em `confenge_target_fit_dirty`, `confenge_company_target_fit_*`,
  `opportunity_intel*`, `pncp_supplier_contracts` ou `canonical_snapshot_*`;
- **não** altera nenhuma view ou função pré-existente (inclusive `v_open_opportunities_canonical`).

O gate P0 da missão — *o pipeline outbound produz saída byte-idêntica com e sem o novo
módulo presente* — é garantido por construção (zero escrita cruzada) e verificado por
testes de equivalência modelados nos golden-path já existentes no repo.

---

## 1. Estado atual — o que já existe e é reutilizável

### 1.1 Primitivos validados (leitura direta do repo)

| Primitivo | Local | Papel no novo motor |
|---|---|---|
| `public_contract_id()` | `scripts/confenge_contract_identity.py:10-19` | Identidade canônica de contrato. **Reusar sem alteração.** Hierarquia `contrato_id → numero_controle_pncp → contract_id`, com `id` legado apenas sob `allow_legacy_surrogate=True`. |
| `QUALIFYING_DATE_PRECEDENCE` | `scripts/confenge_activation/commercial_authority_v2.py:39-44` | Precedência `data_assinatura → data_inicio → data_publicacao → data_publicacao_fonte`. `data_fim` deliberadamente excluída. **Fonte da implementação inicial do accessor de data.** |
| `evidence_hash()` | `commercial_authority_v2.py:174-189` | SHA256 posicional NUL-separado, byte-compatível com o Go da Warmbly. **Não será a disciplina de hash do handoff** — ver Decisão 2. |
| `corpus_hash()` | `commercial_authority_v2.py` | Agregação população-nível (digests ordenados, join `\n`). Padrão de agregação a espelhar. |
| `is_hollow_fact()` | `scripts/confenge_account_intelligence/message_spine.py:55-73` | CLAIM_POLICY: mínimo 24 chars, rejeita boilerplate/meta. **Reusar como gate de materialidade do campo `objeto` da OPPORTUNITY.** |
| `extract_contract_hook()` | `message_spine.py:85-115` | Extração de gancho contratual concreto. Modelo para a dimensão *objeto* do FIT. |
| `v_contracts_canonical_v2` | `db/migrations/077_contract_roles_canonical_v2.sql` | Papéis buyer/supplier, `match_confidence`, reason codes. **Fonte read-only do portfólio da COMPANY.** |
| `v_open_opportunities_canonical` | `db/migrations/049_pncp_resumable_backfill.sql:46-76` | View de oportunidades abertas. **NÃO replayable** — ver Decisão 6. |
| Padrão de snapshot | `089_canonical_snapshot_public_read_v1.sql` + `090_public_read_select_only_lock.sql` | Barreira `BUILDING/BLOCKED/READY_CANONICAL/SUPERSEDED`, hashes com `CHECK ~ '^[0-9a-f]{64}$'`, `blockers JSONB`, watermarks por fonte, select-only lock. **Padrão a espelhar.** |
| `idempotency_key()` / `sha256_payload()` | `scripts/inference_runtime/jobs.py:31-60` | Canonical JSON (`sort_keys=True`, `separators=(",",":")`, `ensure_ascii=False`) + SHA256, com `schema_version` **dentro** do payload hasheado. **Disciplina de hash escolhida.** |
| Fila CDC target-fit | `071_confenge_target_fit_continuous_refresh.sql:11` | `confenge_target_fit_dirty` + SCD-2 `_current`/`_history`. **PROIBIDO escrever. Somente leitura para derivação.** |
| `scripts/opportunity_intel/` | módulo existente | `ranking.py`, `scoring.py` produzem GO/REVIEW/NO_GO com score numérico. **PROIBIDO reusar como "fit" company↔opportunity.** |

### 1.2 PRs abertos e o que isso impõe

Verificação executada:

```
gh pr list --state open  →  #531, #528  (apenas dois)
gh pr diff 531 --name-only | grep db/migrations  →  db/migrations/103_contract_lifecycle_truth.sql
gh pr diff 528 --name-only | grep db/migrations  →  (vazio — 528 não adiciona migration)
ls db/migrations | tail -1  →  102_national_coverage_nullable_expected_units.sql
```

**Conclusão factual:** o maior número mergeado é `102`; `103` está reservado pelo PR #531
(não mergeado); `#528` não reserva nenhum número. **O próximo número livre é `104`.**

- **#531** (`feat/contract-lifecycle-truth-v1`) adicionaria `v_contract_lifecycle_truth_v1`
  com `lifecycle_state`, `lifecycle_trust`, `lifecycle_is_current_evidence` e a função
  `contract_contracting_date_v1(contract_id)`. Como **não está mergeado**, este motor
  **não pode depender dele** — mas deve ser **trocável para ele sem refatoração**.
- **#528** (commercial authority datalake-durable) toca `commercial_authority_v2.py`.
  Isso reforça a decisão de **não** acoplar o hash do handoff ao `evidence_hash()`
  daquele módulo, que está sob mudança ativa.

---

## 2. As 8 decisões fechadas

### DECISÃO 1 — Nome e estrutura do módulo Python

**Decisão:** `scripts/confenge_live_intelligence/` — proposta original **aceita com dois
módulos adicionais**, para tornar *estruturalmente visível* duas restrições que de outro
modo ficariam implícitas no código.

```
scripts/confenge_live_intelligence/
├── __init__.py
├── schema.py                 # ENGINE_ID, SCHEMA_VERSION, dataclasses frozen dos 3 objetos
├── contract_date_resolver.py # ★ O ÚNICO accessor de data/status de contrato (Dec. 7)
├── sources.py                # ★ Leitores as-of read-only (Dec. 6)
├── fit.py                    # Aderência observada por dimensão, tri-estado (Dec. 4)
├── producer.py               # Constrói o snapshot: BUILDING → READY|PARTIAL|BLOCKED
├── events.py                 # Os 5 triggers idempotentes (Dec. 5)
├── verifier.py               # Re-deriva hashes de um snapshot e falha fechado
└── cli.py                    # build / verify / replay / explain-fit
```

**Justificativa dos dois módulos extras:**

- **`contract_date_resolver.py`** — a missão exige *UM* accessor trocável quando #531
  mergear. Se a resolução de data ficar espalhada em `producer.py` e `fit.py`, a troca
  vira um refactor de risco. Isolá-la em módulo próprio torna a substituição uma
  mudança de uma função (`resolve_contracting_date()`), com `date_resolver_version`
  declarado no snapshot. **Não** re-derivamos a tabela-verdade de 28 células do #531.
- **`sources.py`** — os leitores as-of são o ponto onde o motor toca dados outbound.
  Concentrá-los em um módulo permite auditar em um único arquivo que **todo acesso é
  `SELECT`** e que nenhum caminho escreve em tabela outbound.

**Constantes de identidade (em `schema.py`):**

```
ENGINE_ID      = "CONFENGE_LIVE_INTELLIGENCE"
ENGINE_VERSION = "1.0"
SCHEMA_VERSION = "confenge-live-intelligence/1.0"
```

**Trade-off avaliado:** empacotar tudo em 5 arquivos (proposta original) é mais enxuto,
mas perde a visibilidade estrutural das duas restrições mais frágeis do design. Custo de
2 arquivos extras é desprezível frente ao risco de a troca do #531 virar refactor.

---

### DECISÃO 2 — Disciplina de hash ÚNICA

**Decisão:** **canonical-JSON + SHA256**, no padrão de `inference_runtime/jobs.py:31-37`,
com `schema_version` **dentro** do payload hasheado. Uma única disciplina para *todos*
os hashes do motor: header do snapshot, `semantic_hash` de evento, e `fit_hash`.

```
_canonical_json(obj) = json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":"))
live_hash(obj)       = sha256(_canonical_json(obj).encode("utf-8")).hexdigest()
```

Todo payload hasheado carrega obrigatoriamente:

```json
{ "schema_version": "confenge-live-intelligence/1.0", "...": "..." }
```

**Por que NÃO `evidence_hash()`:**

1. **Acoplamento externo indevido.** `evidence_hash()` é, por contrato explícito no
   próprio docstring, *byte-compatível com o Go da Warmbly*: "field order and the NUL
   separator are part of the contract". Vincular um handoff inbound de 3 objetos em
   evolução a um contrato de interoperabilidade externo significa que **qualquer campo
   novo em OPPORTUNITY quebraria a Warmbly ou seria drift silencioso**. São duas
   preocupações distintas que não devem compartilhar disciplina.
2. **Posicional é frágil sob evolução.** `evidence_hash()` é uma lista posicional de 7
   strings unidas por `\x00`. Inserir um campo no meio é indetectável pelo hash em si;
   remover um muda o significado de todas as posições seguintes. Canonical JSON com
   `sort_keys=True` é **independente de ordem de campo** — a estrutura carrega o nome.
3. **Versionamento visível vs. drift silencioso.** Com `schema_version` dentro do
   payload — exatamente como `idempotency_key()` já faz — adicionar um campo é uma
   **mudança de versão visível**, não um drift. Este é o critério decisivo.
4. **#528 está mexendo em `commercial_authority_v2.py`.** Depender do hash de um módulo
   sob mudança ativa adiciona risco de merge sem benefício.

**Compatibilidade:** ambas as disciplinas produzem 64 hex chars, satisfazendo o
`CHECK (~ '^[0-9a-f]{64}$')` do padrão 089. A escolha é semântica, não sintática.

**Regra de agregação (espelhando `corpus_hash`):** hashes de coleção são
`sha256("\n".join(sorted(digests_individuais)))`. Ordenação explícita, não dependente da
ordem de leitura do banco.

**Restrição registrada:** `evidence_hash()` **continua sendo usado sem alteração** onde
já é usado (outbound / Warmbly). O novo motor não o chama e não o modifica.

---

### DECISÃO 3 — Contrato de dados dos 3 objetos

Regras transversais aos três objetos:

- **Sem PII, sem contato.** Nenhum campo de e-mail, telefone, nome de pessoa física,
  cargo ou perfil social. A fronteira contato/PII pertence ao outbound e permanece lá.
- **UNKNOWN é explícito e tipado.** Nunca `NULL` implícito, nunca `""`, nunca zero como
  proxy de ausência. Todo campo derivado carrega um estado do enum
  `{OBSERVED, UNKNOWN}` e, quando UNKNOWN, um `reason_code`.
- **Proveniência obrigatória por campo derivado.** `source`, `source_ref`, `source_as_of`.
- **Frozen dataclasses.** Imutáveis, para que o hash de um objeto seja função pura dele.

#### 3.1 OPPORTUNITY

| Campo | Tipo | Proveniência | UNKNOWN quando |
|---|---|---|---|
| `opportunity_id` | TEXT (PK) | `pncp_raw_bids.pncp_id` | nunca — se ausente, a linha é rejeitada (fail-closed) |
| `objeto` | TEXT | `pncp_raw_bids.objeto_compra` | `is_hollow_fact()` → `OBJETO_HOLLOW` |
| `objeto_state` | ENUM | derivado | — |
| `valor_estimado_brl` | NUMERIC | `valor_total_estimado` | nulo ou ≤ 0 → `VALOR_NAO_PUBLICADO` |
| `valor_state` | ENUM | derivado | — |
| `modalidade_id` / `modalidade` | TEXT | fonte | ausente → `MODALIDADE_NAO_INFORMADA` |
| `uf` | TEXT(2) | fonte | ausente → `GEO_UF_DESCONHECIDA` |
| `municipio` / `codigo_ibge` | TEXT | fonte | ausente → `GEO_MUNICIPIO_DESCONHECIDO` |
| `orgao_cnpj` | TEXT(14) | fonte | ausente → `COMPRADOR_SEM_CNPJ` |
| `orgao_nome` | TEXT | fonte | — |
| `data_publicacao` | DATE | fonte | — |
| `data_encerramento` | DATE | fonte | nulo → `PRAZO_NAO_PUBLICADO` |
| `deadline_state` | ENUM | derivado as-of | `OPEN` / `CLOSED` / `UNKNOWN` |
| `link_edital` | TEXT | `link_pncp` | — |
| `source` / `source_id` | TEXT | fonte | — |
| `source_as_of` | TIMESTAMPTZ | watermark da fonte | — |
| `opportunity_hash` | TEXT(64) | `live_hash(payload)` | — |

**`valor_estimado` NÃO participa de nenhum cálculo aritmético de score.** É usado apenas
para classificar em faixa observada (Decisão 4).

#### 3.2 COMPANY

| Campo | Tipo | Proveniência | UNKNOWN quando |
|---|---|---|---|
| `company_root8` | TEXT(8) (PK) | `cnpj_root8()` de `commercial_authority_v2` | — |
| `razao_social` | TEXT | `v_contracts_canonical_v2` | — |
| `portfolio_contract_ids` | TEXT[] | `public_contract_id()` sobre `v_contracts_canonical_v2` role=SUPPLIER | vazio → `PORTFOLIO_VAZIO` |
| `observed_objects` | TEXT[] | objetos dos contratos, filtrados por `is_hollow_fact()` | vazio → `OBJETO_NAO_OBSERVAVEL` |
| `observed_value_bands` | ENUM[] | faixa dos valores observados | vazio → `VALOR_NAO_OBSERVAVEL` |
| `observed_ufs` | TEXT(2)[] | UFs dos contratos | vazio → `GEO_NAO_OBSERVAVEL` |
| `observed_buyer_cnpjs` | TEXT(14)[] | CNPJs dos órgãos compradores | vazio → `COMPRADOR_NAO_OBSERVAVEL` |
| `most_recent_contracting_date` | DATE | **`contract_date_resolver.resolve_contracting_date()`** | precedência não resolve → `DATA_CONTRATACAO_UNKNOWN` |
| `date_resolver_version` | TEXT | constante do resolver | — |
| `portfolio_hash` | TEXT(64) | `live_hash(...)` | — |

**Sem** `target_fit_class`, **sem** `target_fit_score`, **sem** qualquer campo copiado de
`confenge_company_target_fit_current`. A COMPANY do motor inbound é uma projeção
**independente** do portfólio observado.

#### 3.3 COMPANY_OPPORTUNITY_FIT

| Campo | Tipo | Semântica |
|---|---|---|
| `company_root8` | TEXT(8) | FK lógica |
| `opportunity_id` | TEXT | FK lógica |
| `dim_object` | ENUM | `MATCH` / `NO_MATCH` / `UNKNOWN` |
| `dim_value_band` | ENUM | idem |
| `dim_geography` | ENUM | idem |
| `dim_comparable_buyer` | ENUM | idem |
| `dim_recency` | ENUM | idem |
| `matched_dimensions` | TEXT[] | nomes das dimensões em MATCH — **evidência, não contagem** |
| `unknown_dimensions` | TEXT[] | nomes das dimensões em UNKNOWN, com reason codes |
| `evidence_refs` | JSONB | `contract_id` / `opportunity_id` que sustentam cada MATCH |
| `fit_state` | ENUM | `OBSERVED_FIT` / `NO_OBSERVED_FIT` / `INSUFFICIENT_EVIDENCE` |
| `fit_hash` | TEXT(64) | `live_hash(tupla de dimensões + evidências)` |

**Nenhum campo numérico de score. Nenhuma percentagem. Nenhum `matched_count`.**

---

### DECISÃO 4 — FIT: aderência observada por dimensão, tri-estado

**Decisão:** cinco dimensões independentes, cada uma em **tri-estado
`MATCH / NO_MATCH / UNKNOWN`**. Sem score, sem percentual, sem reuso de
`target_fit_score` ou `ranking_score`.

**Por que tri-estado e não booleano:** um booleano força "ausência de dado" a colapsar em
`NO_MATCH`. Isso é uma afirmação falsa — "não sabemos se a empresa atua nessa UF" não é
"a empresa não atua nessa UF". O tri-estado preserva a distinção epistêmica e alimenta
o critério PARTIAL da Decisão 7.

#### 4.1 As cinco dimensões

| Dimensão | MATCH quando | UNKNOWN quando |
|---|---|---|
| `dim_object` | há ≥1 objeto observado da COMPANY com sobreposição lexical determinística com o `objeto` da OPPORTUNITY (normalização + n-gramas, limiar declarado em constante versionada) | `objeto` da OPPORTUNITY é hollow, **ou** `observed_objects` vazio |
| `dim_value_band` | a faixa do `valor_estimado` da OPPORTUNITY está em `observed_value_bands` | `valor_estimado` UNKNOWN **ou** `observed_value_bands` vazio |
| `dim_geography` | `uf` da OPPORTUNITY ∈ `observed_ufs` | `uf` UNKNOWN **ou** `observed_ufs` vazio |
| `dim_comparable_buyer` | `orgao_cnpj` ∈ `observed_buyer_cnpjs` (comparação por raiz 8 e por CNPJ14) | `orgao_cnpj` UNKNOWN **ou** `observed_buyer_cnpjs` vazio |
| `dim_recency` | `most_recent_contracting_date` dentro da janela de 3 anos relativa ao `as_of_date` (mesma janela do `commercial_authority_v2`) | `most_recent_contracting_date` UNKNOWN (resolver não estabeleceu data) |

#### 4.1.1 Dimensões REQUERIDAS vs. OPCIONAIS

Distinção necessária para o critério da Decisão 7. É declarada aqui, versionada, e entra
no `policy_hash`.

| Dimensão | Classe | Justificativa |
|---|---|---|
| `dim_object` | **REQUERIDA** | Sem objeto material dos dois lados não há afirmação de aderência possível |
| `dim_geography` | **REQUERIDA** | UF é publicada de forma confiável no PNCP; ausência indica dado degradado |
| `dim_recency` | **REQUERIDA (nível COMPANY)** | Resolvida uma vez por COMPANY, não por par. Ver §7.2 |
| `dim_value_band` | OPCIONAL | `valor_estimado` é legitimamente não publicado em muitos editais. UNKNOWN aqui é fato do mundo, não degradação |
| `dim_comparable_buyer` | OPCIONAL | Portfólio pequeno legitimamente não cobre o comprador. UNKNOWN é informativo, não defeito |

UNKNOWN em dimensão **OPCIONAL** é registrado em `unknown_dimensions` e **não** degrada o
estado do snapshot.

**Faixas de valor (`observed_value_bands`)** são um enum ordinal fixo e versionado
(ex.: `ATE_100K`, `100K_1M`, `1M_10M`, `ACIMA_10M`), declarado em `schema.py` e incluído
no `policy_hash`. Bordas são constantes, não parâmetros de runtime.

#### 4.2 `fit_state` — regra determinística

```
se qualquer dimensão == MATCH             → OBSERVED_FIT
senão se qualquer dimensão == UNKNOWN     → INSUFFICIENT_EVIDENCE
senão                                     → NO_OBSERVED_FIT
```

#### 4.3 Ordenação determinística e explicável

Se houver ordenação (listagem para consumo humano), **não usar contagem de dimensões
casadas** — contagem é um score disfarçado, que reintroduz por outra via o percentual
mágico que a missão proíbe.

**Ordenação = tupla lexicográfica sobre prioridade fixa e declarada de dimensões:**

```
PRIORIDADE_DIMENSOES = (
    "dim_object",            # aderência de objeto é a evidência mais forte
    "dim_comparable_buyer",  # já vendeu para comprador comparável
    "dim_geography",
    "dim_value_band",
    "dim_recency",
)

chave_ordenacao = (
    tuple(0 if estado(d) == MATCH else 1 if estado(d) == UNKNOWN else 2
          for d in PRIORIDADE_DIMENSOES),   # 1º: tupla lexicográfica
    -ordinal(data_encerramento_ou_MAX),      # 2º: recência / urgência de prazo
    fit_hash,                                # 3º: desempate estável
)
```

A prioridade é uma **decisão declarada e versionada** (entra no `policy_hash`), não um
peso ajustável. Explicabilidade: para qualquer par ordenado, a justificativa é
"casou `dim_object`, o outro não" — uma afirmação verificável, não um número.

**Trade-off aceito:** essa ordenação é menos "fina" que um score contínuo — muitos pares
empatam na tupla e caem no desempate por recência/hash. Isso é intencional: empate
honesto é preferível a ranking falsamente preciso.

---

### DECISÃO 5 — Triggers idempotentes

**Decisão:** cinco tipos de evento, todos **derivados por diff entre snapshots
consecutivos do próprio motor**, gravados em `confenge_live_intelligence_events`
(tabela nova). Nenhum evento é derivado de escuta em tabela outbound; nenhum evento
escreve em tabela outbound.

#### 5.1 Anatomia comum

```
event_id       = live_hash({schema_version, engine_id, event_type, subject_key,
                            prev_semantic_hash,      -- ★ estado ANTERIOR
                            semantic_hash})          --   estado NOVO
event_type     ∈ {NEW_OPPORTUNITY, OPPORTUNITY_CHANGED, DEADLINE_CHANGED,
                  FIT_BECAME_RELEVANT, COMPANY_PORTFOLIO_CHANGED}
subject_key    = identidade estável do sujeito (ver tabela abaixo)
prev_semantic_hash = live_hash(campos materiais em N-1); "" no bootstrap
semantic_hash  = live_hash(campos materiais em N)
reason_codes   = TEXT[]
source_as_of   = TIMESTAMPTZ  -- watermark efetiva da fonte
snapshot_id    = FK para o snapshot que produziu o evento
prev_snapshot_id = FK para o snapshot base do diff (NULL no bootstrap)
```

**★ A identidade é a TRANSIÇÃO, não o estado de destino.** Este é o ponto mais sutil do
mecanismo, e errá-lo produz perda silenciosa de sinal.

**Contraexemplo se a identidade fosse apenas `(subject_key, semantic_hash)`:** o prazo de
um edital vai de 15 → 20 (snapshot 5, emite `semantic_hash(20)`), e depois volta de
20 → 15 (snapshot 7, emitiria `semantic_hash(15)`). Se o snapshot 3 já tivesse emitido
`semantic_hash(15)`, o `ON CONFLICT DO NOTHING` **engoliria silenciosamente uma reversão
real de prazo** — um sinal comercial de alto valor, perdido. O mesmo vale para
`OPPORTUNITY_CHANGED` e para `FIT_BECAME_RELEVANT`, onde
`UNKNOWN → MATCH → UNKNOWN → MATCH` é genuinamente um segundo sinal, não uma repetição.

Incluir `prev_semantic_hash` no material do `event_id` preserva as duas propriedades:

- **Idempotência mantida:** reprocessar o mesmo diff (mesmo par anterior→novo) produz o
  mesmo `event_id`; nenhuma linha nova.
- **Reversão preservada:** `(20→15)` e `(15→20)` são transições distintas, logo
  `event_id` distintos, logo dois eventos.

**Mudança imaterial** (ex.: reformatação de `orgao_nome`) não altera nenhum dos dois
hashes e **não** gera evento.

`snapshot_id` e `prev_snapshot_id` permanecem **fora** do material do hash — de propósito.
Eles são metadados de linhagem; incluí-los faria todo replay gerar eventos novos,
destruindo a idempotência.

#### 5.2 Definição por tipo

| `event_type` | `subject_key` | Campos no `semantic_hash` | Regra de emissão |
|---|---|---|---|
| `NEW_OPPORTUNITY` | `opportunity_id` | `opportunity_id`, `objeto`, `orgao_cnpj`, `uf` | `opportunity_id` presente em N, ausente em N-1 |
| `OPPORTUNITY_CHANGED` | `opportunity_id` | `objeto`, `valor_estimado`, `modalidade_id`, `uf`, `orgao_cnpj` | `opportunity_hash` mudou **e** o delta toca ≥1 campo material |
| `DEADLINE_CHANGED` | `opportunity_id` | `data_encerramento`, `deadline_state` | apenas `data_encerramento`/`deadline_state` mudaram. Separado de `OPPORTUNITY_CHANGED` porque a ação comercial é distinta |
| `FIT_BECAME_RELEVANT` | `(company_root8, opportunity_id)` | tupla das 5 dimensões + `fit_state` | tupla de fit em N difere da tupla em N-1 **e** `fit_state` em N == `OBSERVED_FIT`. Transição `UNKNOWN → MATCH` conta; `MATCH → MATCH` não |
| `COMPANY_PORTFOLIO_CHANGED` | `company_root8` | `portfolio_hash` (derivado de `portfolio_contract_ids` ordenados + bands + UFs + buyers) | `portfolio_hash` mudou entre N-1 e N |

#### 5.3 `FIT_BECAME_RELEVANT` — a restrição crítica

A fila `confenge_target_fit_dirty` (migration 071) é o mecanismo CDC do **outbound**.
Escrever nela faria o novo motor disparar recomputação de target-fit outbound —
violando o gate P0 de equivalência byte-idêntica.

**Regra absoluta:**

```
confenge_target_fit_dirty          → NUNCA INSERT / UPDATE / DELETE
confenge_company_target_fit_current → SELECT permitido apenas para diagnóstico;
                                      NUNCA como insumo de fit_state
confenge_company_target_fit_history → idem
confenge_target_fit_events          → NUNCA escrever
```

`FIT_BECAME_RELEVANT` é derivado **exclusivamente** do diff da tupla de fit entre
`confenge_live_intelligence_fit` do snapshot N e do snapshot N-1 — tabelas do próprio
motor. Um teste estático deve assertar que nenhum arquivo em
`scripts/confenge_live_intelligence/` contém `INSERT`/`UPDATE`/`DELETE` seguido de
qualquer nome de tabela outbound.

#### 5.4 Fluxo (ASCII)

```
  ┌──────────────────────── READ-ONLY ────────────────────────┐
  │ pncp_raw_bids   sc_public_entities   v_contracts_canonical_v2 │
  └───────┬───────────────┬───────────────────────┬───────────┘
          │               │                       │
          ▼ (as_of_date explícito — Decisão 6)     ▼
    ┌───────────────────────────────────────────────────┐
    │  sources.py   (SELECT-only, as-of parametrizado)   │
    └───────────────────────┬───────────────────────────┘
                            ▼
    ┌───────────────────────────────────────────────────┐
    │  contract_date_resolver.py  (o ÚNICO accessor)     │
    │  hoje: precedência CA/2.0  |  amanhã: #531 fn      │
    └───────────────────────┬───────────────────────────┘
                            ▼
    ┌──────────────┬──────────────┬─────────────────────┐
    │ OPPORTUNITY  │   COMPANY    │  COMPANY_OPPTY_FIT  │  ← fit.py (tri-estado)
    └──────┬───────┴──────┬───────┴──────────┬──────────┘
           └──────────────┴──────────────────┘
                            ▼
    ┌───────────────────────────────────────────────────┐
    │  producer.py  → snapshot BUILDING                  │
    │  hashes: universe / policy / schema / data / fit    │
    │  watermarks por fonte                              │
    └───────────────────────┬───────────────────────────┘
                            ▼  diff vs snapshot N-1
    ┌───────────────────────────────────────────────────┐
    │  events.py  → 5 tipos, ON CONFLICT DO NOTHING      │
    └───────────────────────┬───────────────────────────┘
                            ▼
              READY_CANONICAL | PARTIAL | BLOCKED   (Decisão 7)
                            ▼
    ┌───────────────────────────────────────────────────┐
    │  verifier.py — re-deriva TODOS os hashes e falha   │
    │  fechado em qualquer divergência                   │
    └───────────────────────────────────────────────────┘

  ╳ NENHUMA SETA DE ESCRITA CRUZA PARA:
    opportunity_intel* · confenge_target_fit_* · pncp_supplier_contracts
    canonical_snapshot_* · v_open_opportunities_canonical
```

---

### DECISÃO 6 — Replayability do `v_open_opportunities_canonical`

#### 6.1 O problema, precisamente

`db/migrations/049_pncp_resumable_backfill.sql:75-76`:

```sql
WHERE b.data_encerramento >= CURRENT_DATE
   OR (b.data_encerramento IS NULL AND b.data_publicacao >= CURRENT_DATE - INTERVAL '30 days')
```

O `CURRENT_DATE` está **dentro** do `WHERE` da própria view.

#### 6.2 Por que um "wrapper" sobre a view NÃO resolve

O enunciado original propõe "wrapper com data efetiva explícita". **Isso não funciona**,
e o motivo precisa ficar registrado porque é a armadilha mais fácil deste design.

Um wrapper que faça `SELECT ... FROM v_open_opportunities_canonical WHERE <predicado as-of>`
só pode **filtrar para menos** o que a view já entregou. As linhas que a view **excluiu**
são irrecuperáveis por qualquer consulta descendente.

**Contraexemplo concreto:** um edital com `data_encerramento = 2026-08-15`. Hoje
(2026-09-02) a view o exclui — `2026-08-15 >= 2026-09-02` é falso. Um replay as-of
`2026-08-01` **precisa** desse edital (ele estava aberto naquela data), mas nenhum
wrapper sobre a view consegue ressuscitá-lo. O replay produziria um universo
silenciosamente menor — exatamente a quebra de idempotência que o design tenta evitar.

#### 6.3 A solução

**Novo leitor as-of que vai à tabela base, não à view.** A migration 104 cria uma função
aditiva (nome proposto: `public.live_open_opportunities_as_of(p_as_of DATE)`) que
reproduz a projeção de colunas de 049 — incluindo o `LEFT JOIN sc_public_entities` — e
**re-expressa o predicado com o parâmetro explícito**:

```sql
-- Forma conceitual. NÃO é a migration final.
WHERE b.data_encerramento >= p_as_of
   OR (b.data_encerramento IS NULL
       AND b.data_publicacao >= p_as_of - INTERVAL '30 days')
```

**Propriedades:**

- `v_open_opportunities_canonical` **permanece intocada** — nenhum `CREATE OR REPLACE`,
  nenhum `DROP`. Todo consumidor outbound continua vendo bytes idênticos.
- Equivalência verificável: `live_open_opportunities_as_of(CURRENT_DATE)` deve retornar
  o **mesmo conjunto** que `v_open_opportunities_canonical`. Isso vira um teste de
  equivalência (a nova função é uma generalização estrita da view, não um fork
  divergente).
- Todo snapshot grava `as_of_date` no header e no `universe_hash`. Replay do mesmo
  `snapshot_id` em qualquer data futura reproduz o mesmo universo.

**Risco residual — mutabilidade de `pncp_raw_bids`:** a função as-of resolve a
dependência de *data*, mas não a de *estado da tabela base*. Se uma linha de
`pncp_raw_bids` for atualizada após o snapshot N, o replay de N pode divergir.
**Mitigação:** o `universe_hash` do snapshot cobre o conjunto de
`(opportunity_id, opportunity_hash)` observado; o `verifier.py` recomputa e **falha
fechado** se divergir, transformando um replay silenciosamente errado em um erro alto e
visível. Snapshot temporal completo (versionamento de linha em `pncp_raw_bids`) fica
**fora de escopo** desta wave — exigiria tocar tabela outbound.

---

### DECISÃO 7 — Critério READY / PARTIAL / BLOCKED

**Decisão fechada ANTES da implementação**, sobre propriedades **mensuráveis do
snapshot** — nunca sobre condições do repositório.

#### 7.1 Por que NÃO "PARTIAL até #531 mergear"

Amarrar o estado do handoff a "o PR #531 não mergeou" é um critério **não avaliável em
runtime**. O produtor não sabe o estado do git. Pior: no dia em que #531 mergear, o
critério vira vacuidade e será racionalizado — "agora podemos marcar READY" — sem que
nenhuma propriedade dos dados tenha sido verificada.

**Em vez disso, o estado é definido por propriedades dos dados, e a dependência de #531
alimenta esse critério mecanicamente.**

#### 7.2 O critério

**Nível de agregação — a armadilha.** "PARTIAL se ≥1 dimensão requerida é UNKNOWN" é
ambíguo, e a leitura ingênua (*qualquer linha, qualquer UNKNOWN*) torna
`READY_CANONICAL` **inalcançável para sempre** — inclusive depois do #531 — porque
dados reais de `pncp_raw_bids` sempre conterão *algum* edital com objeto hollow ou UF
ausente. Um estado que nunca dispara é pior que nenhum estado.

**Portanto o critério é de completude por linha, com exclusão explícita — não de
degradação global.**

**Regra de universo (aplicada ANTES do estado do snapshot):**

- OPPORTUNITY com UNKNOWN em dimensão REQUERIDA (`dim_object`, `dim_geography`) é
  **excluída do universo de fit**, gravada em
  `confenge_live_intelligence_opportunities` com
  `row_completeness_state = 'EXCLUDED_INCOMPLETE'` + `exclusion_reason_codes`.
- COMPANY com `most_recent_contracting_date` UNKNOWN (`dim_recency` não resolvida) é
  **excluída do universo de fit**, com
  `row_completeness_state = 'EXCLUDED_UNRESOLVED_DATE'`.
- Linhas excluídas **permanecem visíveis e contadas** — nunca são descartadas
  silenciosamente. `excluded_opportunity_count` e `excluded_company_count` são campos do
  header e entram no `universe_hash`.

**Estado do snapshot:**

| Estado | Condição |
|---|---|
| **BLOCKED** | `blockers` não vazio (lista fechada abaixo). Fail-closed. |
| **PARTIAL** | Sem blockers, hashes conferem, mas `excluded_opportunity_count > 0` **ou** `excluded_company_count > 0` — ou seja, o universo publicado é um subconjunto declarado do universo observado. |
| **READY_CANONICAL** | Sem blockers, todos os hashes re-derivados batem, **e** nenhuma exclusão: toda linha observada tem `row_completeness_state = 'COMPLETE'`. |

**Consequência desejada:** UNKNOWN em dimensão **OPCIONAL** (`dim_value_band`,
`dim_comparable_buyer`) **não** exclui a linha e **não** degrada o snapshot. É registrado
em `unknown_dimensions` e propagado ao consumidor. Isso mantém `READY_CANONICAL`
alcançável no mundo real, onde valor estimado frequentemente não é publicado.

#### 7.2.1 Contrato de consumo do PARTIAL

`PARTIAL` é um **estado terminal e consumível**, não um estado de erro. Isto precisa ser
explícito: §7.3 concede que, enquanto #531 não mergear, PARTIAL será o estado prático da
maioria dos snapshots. Se PARTIAL não fosse consumível, a W1 entregaria um motor **sem
saída utilizável** — um resultado inaceitável.

Requisitos, iguais aos de `READY_CANONICAL`:

- `closed_at IS NOT NULL` e `content_hash IS NOT NULL` — sem isso é impossível
  distinguir "ainda construindo, atualmente incompleto" de "fechado como incompleto".
- `blockers = '[]'::JSONB`.

Obrigações do consumidor (parte do contrato, verificável em teste):

1. Deve exibir `excluded_opportunity_count` / `excluded_company_count` — nunca apresentar
   um snapshot PARTIAL como cobertura total.
2. Deve exibir `unknown_dimensions` de cada FIT.
3. **NUNCA** pode interpretar `UNKNOWN` como `NO_MATCH`. Um consumidor que colapsa os
   dois estados está fora de contrato.

**Gatilhos de BLOCKED (fail-closed, lista fechada):**

1. Hash re-derivado pelo `verifier.py` diverge do gravado.
2. Identidade contraditória: mesmo `opportunity_id` com dois `opportunity_hash` na
   mesma janela de construção.
3. `public_contract_id()` retorna vazio para um contrato do portfólio sem
   `allow_legacy_surrogate` explícito.
4. Watermark de fonte requerida ausente, ou `freshness_state ∈ {FAILED, BLOCKED}`.
5. `as_of_date` ausente ou não determinístico no header.
6. Tentativa detectada de escrita em tabela outbound.

**Espelhando 089:** `blockers JSONB NOT NULL DEFAULT '[]'` +
`CHECK (state <> 'READY_CANONICAL' OR (closed_at IS NOT NULL AND blockers = '[]'::JSONB))`.
Isso torna "READY com blockers" **estruturalmente impossível**, não apenas proibido.

#### 7.3 Como a dependência de #531 se resolve mecanicamente

`contract_date_resolver.resolve_contracting_date()` declara `date_resolver_version` e
retorna um par `(date, trust)`:

- **Hoje** (`date_resolver_version = "ca-v2-precedence/1.0"`): implementado sobre
  `QUALIFYING_DATE_PRECEDENCE` (`commercial_authority_v2.py:39-44`). Quando a precedência
  não estabelece uma data de contratação, retorna `trust = UNKNOWN`. `dim_recency` vira
  `UNKNOWN` → o snapshot resolve para **PARTIAL** — *mecanicamente*, sem que ninguém
  escreva "PARTIAL porque #531 não mergeou".
- **Depois de #531**: trocar a implementação para `contract_contracting_date_v1()` e
  bumpar `date_resolver_version`. Onde o lifecycle truth estabelece a data com
  `lifecycle_trust` suficiente, `dim_recency` deixa de ser UNKNOWN e o mesmo snapshot
  resolve para **READY** — **sem editar o critério**.

**Portanto:** a resposta à pergunta da missão é *sim, na prática o handoff será PARTIAL
enquanto #531 não mergear* — mas essa é uma **consequência observada**, não a regra. A
regra é "UNKNOWN em dimensão requerida ⇒ PARTIAL".

**Não re-derivamos a tabela-verdade de 28 células do #531.** O resolver expõe apenas
`(date, trust)`; toda a semântica de lifecycle permanece no #531.

---

### DECISÃO 8 — Migration: número, escopo e barreira de segurança

#### 8.1 Número

**`104_confenge_live_intelligence_v1.sql`**, com base na verificação da §1.2
(mergeado até `102`; `103` reservado por #531; `#528` sem migration).

**Regra de guarda:** se #531 mergear antes desta implementação, `103` estará ocupado e
`104` continua livre. Se outro PR reivindicar `104` no intervalo, re-executar a
verificação de §1.2 e subir o número — **nunca reutilizar**.

#### 8.2 Escopo — apenas objetos novos

**Cria (todos novos):**

```
confenge_live_intelligence_snapshots          -- header, espelhando 089
confenge_live_intelligence_source_watermarks  -- espelhando canonical_snapshot_source_watermarks
confenge_live_intelligence_opportunities      -- OPPORTUNITY por snapshot
confenge_live_intelligence_companies          -- COMPANY por snapshot
confenge_live_intelligence_fit                -- COMPANY_OPPORTUNITY_FIT por snapshot
confenge_live_intelligence_events             -- os 5 triggers, PK = event_id
live_open_opportunities_as_of(DATE)           -- função as-of (Decisão 6)
```

**Constraints herdadas do padrão 089:**

- Todo hash: `CHECK (~ '^[0-9a-f]{64}$')`
- `state TEXT NOT NULL DEFAULT 'BUILDING' CHECK (state IN ('BUILDING','BLOCKED','PARTIAL','READY_CANONICAL','SUPERSEDED'))`
- `blockers JSONB NOT NULL DEFAULT '[]'::JSONB`
- `cutoff_timezone TEXT NOT NULL DEFAULT 'America/Sao_Paulo' CHECK (cutoff_timezone = 'America/Sao_Paulo')` — ver §8.4
- `as_of_date DATE NOT NULL`
- `excluded_opportunity_count INTEGER NOT NULL CHECK (>= 0)`
- `excluded_company_count INTEGER NOT NULL CHECK (>= 0)`
- `SET LOCAL lock_timeout = '5s'; SET LOCAL statement_timeout = '120s';`

**★ Guarda estrutural cobrindo AMBOS os estados terminais.** Replicar o CHECK de 089
apenas para `READY_CANONICAL` deixaria "PARTIAL com blockers" proibido só em prosa —
inconsistente com o padrão que este documento adota, de tornar estados inválidos
*estruturalmente impossíveis*. Como §7.2.1 estabelece que PARTIAL é terminal e
consumível, ele exige as mesmas garantias:

```sql
CHECK (
  state NOT IN ('READY_CANONICAL', 'PARTIAL')
  OR (closed_at IS NOT NULL AND content_hash IS NOT NULL AND blockers = '[]'::JSONB)
)
```

Sem `closed_at`/`content_hash` no PARTIAL seria impossível distinguir "ainda construindo,
atualmente incompleto" de "fechado como incompleto" — e um consumidor poderia ler um
snapshot em construção como se fosse um handoff válido.

**PROIBIDO — nenhum `ALTER`, `DROP` ou `CREATE OR REPLACE` sobre:**

```
opportunity_intel*            confenge_company_target_fit_current
confenge_target_fit_dirty     confenge_company_target_fit_history
confenge_target_fit_events    confenge_target_fit_shadow
pncp_supplier_contracts       canonical_public_snapshots
canonical_snapshot_*          canonical_public_events_v1
v_open_opportunities_canonical  v_contracts_canonical_v2
pncp_raw_bids                 sc_public_entities
```

#### 8.3 ★ FLAG DE SEGURANÇA — os revokes de 090 NÃO cobrem objetos novos

**Achado.** A migration `090_public_read_select_only_lock.sql:366-368` executa:

```sql
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM smartlic_public_reader;
REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM smartlic_public_reader;
REVOKE USAGE ON SCHEMA public FROM smartlic_public_reader;
```

`ALL TABLES` / `ALL FUNCTIONS` em PostgreSQL aplica-se aos objetos **existentes no momento
da execução**. Não é uma política persistente. A verificação (`grep "EVENT TRIGGER"` em
090) **não encontrou event trigger** que reaplique revokes a objetos criados depois.

**Implicação:** qualquer tabela ou função que a migration 104 criar no schema `public`
nasce **fora** da barreira select-only de 090. Isso é uma regressão de superfície de
segurança se não for tratada explicitamente.

**Mitigação obrigatória na migration 104 (duas camadas):**

1. **Revoke explícito por objeto**, imediatamente após cada `CREATE`, para
   `smartlic_public_reader` e `PUBLIC` — não confiar em `ALL TABLES`. **Esta é a barreira
   de segurança real do motor**, e a única.
2. **Teste estático de barreira**: assertar que, para cada objeto criado por 104, existe
   um `REVOKE` correspondente no mesmo arquivo.

> **Camada descartada — `ALTER DEFAULT PRIVILEGES`.** O design previa uma terceira camada
> (`ALTER DEFAULT PRIVILEGES` para o role proprietário no schema `public`, de modo que
> objetos futuros do motor nascessem sem grants para o reader). Medida em **PostgreSQL
> 16.15** durante a implementação, ela é **inerte**: não grava linha em `pg_default_acl` e
> uma função criada depois nasce com `proacl = NULL` (`PUBLIC` mantém `EXECUTE`). Foi
> removida da 104 pelo @data-engineer — ver ADR-040, Achado 1. **Consequência:** não há
> proteção automática para objetos de migrations futuras. Cada nova migration do motor deve
> emitir seus próprios `REVOKE` explícitos **e estender a camada 2 ao seu próprio arquivo** —
> o teste estático lê a 104 como texto (§3.1) e não cobre migrations subsequentes.

#### 8.4 ★ O as-of é dependente de timezone

`db/migrations/049_pncp_resumable_backfill.sql:33-35` faz `ALTER COLUMN ... TYPE
TIMESTAMPTZ` em `data_publicacao`, `data_abertura` e `data_encerramento`.

Portanto, em `data_encerramento >= p_as_of` com `p_as_of DATE`, o PostgreSQL promove a
`DATE` para `TIMESTAMPTZ` na **`TimeZone` da sessão**. Replay do mesmo `snapshot_id` a
partir de uma sessão com `TimeZone` diferente (UTC em CI vs. `America/Sao_Paulo` em
produção) desloca a fronteira em até 3 horas e **produz um universo diferente** — a mesma
classe de hazard de replay que 089 já guarda com
`cutoff_timezone CHECK (= 'America/Sao_Paulo')`.

**Mitigação (espelhando 089):**

1. `cutoff_timezone` fixado no header do snapshot com o mesmo CHECK de 089.
2. Parâmetro permanece tipado `DATE` (semanticamente é um dia civil, não um instante).
3. `sources.py` define o timezone **explicitamente** na sessão antes de qualquer leitura
   as-of, em vez de herdar o default do ambiente — a herança é a causa raiz.
4. Teste de replay executando o mesmo `snapshot_id` sob duas `TimeZone` de sessão
   distintas, asserindo `universe_hash` idêntico.

**Alternativa avaliada — schema dedicado `live_intelligence_v1`:** isolaria os grants
por schema (`REVOKE USAGE ON SCHEMA` cobre tudo dentro dele) e é arquiteturalmente mais
limpo. **Trade-off:** introduz um schema novo no `search_path`, exigindo revisão de
`scripts/schema/` e das ferramentas de migração; aumenta o raio de mudança justamente na
wave que precisa provar zero impacto outbound. **Recomendação: `public` com revokes
explícitos nesta wave; schema dedicado como item de backlog** quando não houver gate de
equivalência byte-idêntica em jogo.

---

## 3. Compatibilidade retroativa e o gate P0

### 3.1 Argumento de equivalência

O pipeline outbound produz saída byte-idêntica com e sem o novo módulo porque:

1. Nenhum arquivo existente em `scripts/` é modificado.
2. Nenhuma view, função ou tabela existente é alterada.
3. O novo módulo não é importado por nenhum caminho de código outbound.
4. `confenge_target_fit_dirty` — o único mecanismo pelo qual uma escrita poderia
   propagar para o outbound — é read-only para o novo motor.
5. Todo acesso a dados outbound passa por `sources.py`, auditável como SELECT-only.

### 3.2 Testes de equivalência (modelados nos golden-path existentes)

| Teste existente (no tree) | Papel como modelo |
|---|---|
| `tests/test_golden_path_idempotency.py` | Executar duas vezes com o módulo presente; asserir saída idêntica |
| `tests/test_golden_path_snapshot.py` | Snapshot outbound antes/depois da migration 104 |
| `tests/test_golden_path_canonical.py` | Projeções canônicas inalteradas |
| `tests/test_snapshot_reconciliation.py` | Modelo de reconciliação para o `verifier.py` |

**Assertiva estática obrigatória (P0):** um teste que lê
`db/migrations/104_confenge_live_intelligence_v1.sql` como **texto** e falha se o arquivo
contiver `ALTER`, `DROP` ou `CREATE OR REPLACE` nomeando qualquer objeto da lista de
§8.2. Este teste é o guarda-corpo mais barato e mais confiável do design — ele falha em
CI antes de qualquer banco ser tocado.

> Nota: o design **não** depende de `scripts/schema/audit_sql_references.py` nem de
> `tests/test_contract_lifecycle_truth_migration_static.py` — ambos existem apenas no
> diff do PR #531 (não mergeado) e não estão na árvore.

---

## 4. Riscos

| # | Risco | Sev. | Mitigação |
|---|---|---|---|
| R1 | Objetos de 104 nascem fora da barreira select-only de 090 | **ALTA (segurança)** | Revokes explícitos por objeto (barreira real) + teste estático de barreira (§8.3). `ALTER DEFAULT PRIVILEGES` foi descartado por ser inerte no PG16 — ver §8.3 e ADR-040 |
| R2 | Wrapper as-of sobre a view não recupera linhas excluídas → universo silenciosamente menor no replay | **ALTA** | Ir à tabela base `pncp_raw_bids`; teste de equivalência `as_of(CURRENT_DATE) == view` (§6.3) |
| R3 | Escrita acidental em `confenge_target_fit_dirty` dispara recomputação outbound | **ALTA** | Teste estático de proibição de DML sobre tabelas outbound em todo o módulo (§5.3) |
| R4 | Colisão de número de migration se outro PR reivindicar 104 | MÉDIA | Re-verificar `gh pr diff <n> --name-only` no momento da implementação; nunca reutilizar número |
| R5 | Mutação de `pncp_raw_bids` após o snapshot quebra o replay | MÉDIA | `universe_hash` + `verifier.py` fail-closed (§6.3). Snapshot temporal completo fora de escopo |
| R6 | "Contagem de dimensões casadas" reintroduzida como score na implementação | MÉDIA | Nenhum campo numérico no schema do FIT; ordenação por tupla lexicográfica (§4.3) |
| R7 | UNKNOWN colapsado em NO_MATCH, produzindo afirmação falsa | MÉDIA | Tri-estado obrigatório; `unknown_dimensions` explícito; PARTIAL derivado de UNKNOWN |
| R8 | Merge de #531 vira refactor em vez de troca de uma função | MÉDIA | `contract_date_resolver.py` como único ponto de acesso + `date_resolver_version` |
| R9 | Drift silencioso de schema se o hash não carregar versão | MÉDIA | `schema_version` **dentro** do payload hasheado (§Decisão 2) |
| R10 | `#528` altera `commercial_authority_v2.py` sob o novo motor | BAIXA | Motor consome apenas `QUALIFYING_DATE_PRECEDENCE` e `cnpj_root8()` (estáveis); não usa `evidence_hash()` |
| R11 | Critério de estado por "qualquer linha com UNKNOWN" torna READY inalcançável para sempre | **ALTA** | Completude por linha + exclusão explícita contada; dimensões REQUERIDAS enumeradas (§4.1.1, §7.2) |
| R12 | Identidade de evento pelo estado de destino engole reversões (15→20→15) | **ALTA** | `prev_semantic_hash` no material do `event_id`: identidade é a transição (§5.1) |
| R13 | Replay sob `TimeZone` de sessão diferente produz universo diferente (colunas TIMESTAMPTZ) | **ALTA** | `cutoff_timezone` no header + `sources.py` fixa o TZ explicitamente + teste de replay cross-TZ (§8.4) |
| R14 | "PARTIAL com blockers" proibido só em prosa | MÉDIA | CHECK estrutural cobrindo ambos os estados terminais (§8.2) |
| R15 | Consumidor lê PARTIAL como cobertura total, ou UNKNOWN como NO_MATCH | MÉDIA | Contrato de consumo explícito e testável (§7.2.1) |

---

## 5. Interface para @sm — incrementos sugeridos

Todas as stories são **aditivas**. Nenhuma toca outbound.

### LI-1 — Fundação de schema e disciplina de hash
`scripts/confenge_live_intelligence/{__init__,schema}.py`.
Constantes `ENGINE_ID`/`SCHEMA_VERSION`, `live_hash()`, dataclasses frozen dos 3 objetos
com estados UNKNOWN tipados. **AC:** `live_hash` é independente de ordem de campo;
`schema_version` presente em todo payload hasheado; nenhum campo de PII/contato.
**Dependências:** nenhuma. **Risco:** BAIXO.

### LI-2 — Migration 104 (aditiva) + barreira de segurança
`db/migrations/104_confenge_live_intelligence_v1.sql`.
6 tabelas novas + função `live_open_opportunities_as_of(DATE)`, espelhando 089.
Revokes explícitos por objeto (§8.3). **AC:** teste estático prova ausência de
`ALTER`/`DROP`/`CREATE OR REPLACE` sobre objetos outbound; todo objeto criado tem REVOKE
correspondente. **Dependências:** LI-1. **Risco:** ALTO (HIGH-RISK: migration + segurança
→ exige @data-engineer).

### LI-3 — Leitores as-of read-only
`sources.py`. **AC:** `live_open_opportunities_as_of(CURRENT_DATE)` retorna conjunto
idêntico a `v_open_opportunities_canonical`; teste de recuperação de linha prova que um
edital encerrado ontem aparece em as-of de anteontem; **teste de replay cross-timezone
assere `universe_hash` idêntico sob duas `TimeZone` de sessão distintas (§8.4)**;
auditoria SELECT-only. **Dependências:** LI-2. **Risco:** ALTO.

### LI-4 — Accessor único de data de contrato
`contract_date_resolver.py`. Implementação sobre `QUALIFYING_DATE_PRECEDENCE`,
retornando `(date, trust)` + `date_resolver_version`. **AC:** único ponto do módulo que
resolve data de contrato; trocar para `contract_contracting_date_v1()` é mudança de uma
função; **não** re-deriva a tabela-verdade de #531. **Dependências:** LI-1. **Risco:** MÉDIO.

### LI-5 — FIT por dimensão, tri-estado
`fit.py`. 5 dimensões `MATCH/NO_MATCH/UNKNOWN`, `fit_state`, ordenação lexicográfica.
**AC:** nenhum campo numérico no output; nenhum import de `opportunity_intel.scoring`/
`ranking`; UNKNOWN nunca colapsa em NO_MATCH; ordenação estável e reproduzível.
**Dependências:** LI-1, LI-3, LI-4. **Risco:** MÉDIO.

### LI-6 — Producer e barreira de snapshot
`producer.py`. Ciclo `BUILDING → READY|PARTIAL|BLOCKED` com o critério da Decisão 7.
**AC:** exclusão por linha com reason code e contagem (não degradação global);
`excluded_*_count > 0` ⇒ PARTIAL; zero exclusões ⇒ READY; blockers ⇒ BLOCKED;
**teste prova que READY é alcançável com dados realistas contendo UNKNOWN em dimensão
OPCIONAL**; PARTIAL tem `closed_at` e `content_hash`.
**Dependências:** LI-2..LI-5. **Risco:** ALTO.

### LI-7 — Eventos idempotentes
`events.py`. Os 5 tipos, diff snapshot N vs N-1, `ON CONFLICT DO NOTHING`.
**AC:** reprocessar o mesmo diff não cria linha nova; mudança imaterial não gera evento;
**teste de reversão prova que a sequência de prazo 15→20→15 emite dois eventos distintos
(§5.1)**; `FIT_BECAME_RELEVANT` derivado apenas de tabelas do próprio motor.
**Dependências:** LI-6. **Risco:** ALTO.

### LI-8 — Verifier fail-closed + CLI
`verifier.py`, `cli.py` (`build`/`verify`/`replay`/`explain-fit`).
**AC:** re-derivação de hash divergente ⇒ BLOCKED, nunca degradação silenciosa;
`explain-fit` produz justificativa textual sem número.
**Dependências:** LI-6, LI-7. **Risco:** MÉDIO.

### LI-9 — Gate P0 de equivalência outbound
`tests/test_live_intelligence_outbound_equivalence.py` + teste estático da migration.
**AC:** golden path produz saída byte-idêntica com e sem o módulo; nenhum arquivo do
módulo contém DML sobre tabela outbound; migration 104 sem `ALTER`/`DROP`/`CREATE OR REPLACE`
sobre objetos outbound. **Dependências:** LI-2..LI-8. **Risco:** ALTO — **gate bloqueante
de publicação**.

### Ordem sugerida

```
LI-1 → LI-2 → LI-3 ─┐
       LI-1 → LI-4 ─┴→ LI-5 → LI-6 → LI-7 → LI-8 → LI-9 (gate)
```

**Nível de risco AIOX:** LI-2, LI-3, LI-6, LI-7, LI-9 são **HIGH-RISK** (migration,
segurança, dados). LI-2 exige participação de **@data-engineer**. LI-9 é gate bloqueante
antes de qualquer publicação.

---

## 6. Registro de decisões automáticas

`[AUTO-DECISION]` Estrutura do módulo → 5 arquivos propostos + `contract_date_resolver.py`
+ `sources.py` (razão: tornar estruturalmente visíveis a troca do #531 e a fronteira
read-only).

`[AUTO-DECISION]` Disciplina de hash → canonical-JSON+SHA256 com `schema_version` no
payload (razão: independência de ordem de campo, versionamento visível, desacoplamento do
contrato Warmbly, e `commercial_authority_v2.py` está sob mudança no #528).

`[AUTO-DECISION]` Estratégia as-of → leitor sobre `pncp_raw_bids`, não wrapper sobre a
view (razão: o `CURRENT_DATE` está no WHERE da view; linhas excluídas são irrecuperáveis
por qualquer consulta descendente).

`[AUTO-DECISION]` Critério de estado → propriedades mensuráveis do snapshot, não estado
do repositório (razão: "PARTIAL até #531" não é avaliável em runtime e seria racionalizado
no merge).

`[AUTO-DECISION]` Ordenação do FIT → tupla lexicográfica sobre prioridade declarada
(razão: contagem de dimensões casadas é score disfarçado).

`[AUTO-DECISION]` Placement de schema → `public` com revokes explícitos, schema dedicado
para backlog (razão: minimizar raio de mudança na wave que precisa provar equivalência
byte-idêntica).

`[AUTO-DECISION]` Número de migration → `104`, verificado contra os dois únicos PRs
abertos (#531 reserva 103; #528 sem migration).

`[AUTO-DECISION]` Nível de agregação do critério de estado → completude por linha com
exclusão explícita e contada, não degradação global (razão: a leitura "qualquer linha,
qualquer UNKNOWN" tornaria READY inalcançável para sempre, mesmo após o #531).

`[AUTO-DECISION]` Dimensões REQUERIDAS → `dim_object`, `dim_geography`, `dim_recency`;
OPCIONAIS → `dim_value_band`, `dim_comparable_buyer` (razão: valor estimado e cobertura
de comprador são legitimamente ausentes no mundo real; tratá-los como requeridos
confundiria fato do mundo com degradação de dado).

`[AUTO-DECISION]` PARTIAL é terminal e consumível, com as mesmas garantias estruturais de
READY (razão: §7.3 concede que PARTIAL será o estado prático antes do #531; PARTIAL não
consumível faria a W1 entregar um motor sem saída utilizável).

`[AUTO-DECISION]` Identidade de evento inclui `prev_semantic_hash` (razão: identidade
pelo estado de destino engoliria reversões reais via `ON CONFLICT DO NOTHING`).

---

*Documento de arquitetura. Nenhum código de produção ou migration real foi escrito.
Implementação requer stories validadas pelo @po conforme o protocolo AIOX.*
