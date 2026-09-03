# LI-W2 — Decisões arquiteturais do export público, identidade e eventos

**Autor:** @architect (Aria) · **Status:** FECHADO (gate sistêmico, 2026-09-03) · **Versão:** 1.2

> **v1.2 — o que mudou em relação à v1.1 (gate sistêmico HIGH-RISK).** Três decisões pendentes
> fechadas: (1) derivação de `freshness.state` pinada (§A.2.3, novo) e a linha `source_as_of` de
> §A.2 passa a ser `min()` sobre os payloads emitidos; (2) o role de escrita de `extra_li_equiv`
> deixa de ser "extensão de `confenge_live_intel_reader`" e passa a ser o role dedicado
> `li_equiv_runner`, provisionado por `scripts/ops/li_equiv_db.py` (§E.7, reescrito); (3)
> parametrização dos testes estáticos/de catálogo da 104 para incluir a 105 (§F). Registrado
> também o esclarecimento de escopo sobre `content_hash` × re-persist (fim de §A.2.1, antes de
> §A.2.2). A norma
> operacional vive na story (AC3/AC4/AC10, Tasks 10/11); este documento é background.

Base do código: worktree `li-w2` @ `d80e7080`
(`scripts/confenge_live_intelligence/{schema,producer,fit,sources}.py`,
`db/migrations/104_confenge_live_intelligence_v1.sql`).

Contrato consumidor: **vendorizado** em `docs/contracts/confenge-live-intelligence-v1.json`
(cópia verbatim de `tjsasakifln/web-cfg` @ `dea6457a14b17279713fb357cbce6c6e8087ce6c`,
`sha256 875a999051df2134b4ee18513b1b2c5b1f1ec2d9b716096679079cd527692107`). Proveniência,
leituras normativas e a análise de `cnpj.cjs` estão em
`docs/contracts/confenge-live-intelligence-v1.md`.

> **v1.1 — o que mudou em relação à v1.0 (rodada de NO-GO do @po):** quatro decisões antes em
> aberto foram fechadas com o contrato real em mãos: (1) `compradores` deixa de carregar CNPJ cru
> (§A.4); (2) os riscos residuais #1 e #3 da v1.0 estão **resolvidos**, não mais "a verificar"
> (§Riscos); (3) `manifest.json` emite `schema`, não `contract` (§A.2); (4) as tabelas §A.2/A.3/
> A.4/C.2 foram inlineadas nas Dev Notes da story e este documento saiu do scratchpad efêmero
> para um caminho versionado.

---

## 0. Evidências verificadas (não re-derivar)

| Fato | Evidência |
|---|---|
| CNPJ de estabelecimento (14 dígitos) existe no datalake | `pncp_supplier_contracts.fornecedor_cnpj` só recebe valor quando `is_valid_cnpj14(digits)` — `scripts/contracts_identity.py:95-97,111-115`. Comentário da 076: *"Compatibility CNPJ-only key. CPF, foreign and unknown identities are always NULL."* Logo: 14 dígitos crus ou NULL, nunca formatado, nunca raiz. Exposto como `supplier_cnpj` na `v_contracts_canonical_v2` (077:184) e já lido por `sources.fetch_observed_portfolio`. |
| Bump de `SCHEMA_VERSION` custa zero | `SELECT count(*) FROM public.confenge_live_intelligence_snapshots` = 0 em `extra_test`; HEAD `d80e7080` não empurrado. Nenhum `snapshot_id` publicado seria órfão. |
| Fórmula do `event_id` já está ditada pela migration | 104:471-472 `UNIQUE (event_type, subject_key, prev_semantic_hash, semantic_hash)` + comentário *"Identidade da transicao, redundante com o event_id por construcao."* |
| `payload_fields`, `forbidden_conclusion_fields`, `forbidden_public_language`, `accepted_versions` e a fórmula de `hashCnpj` batem linha a linha com este documento | Conferido pelo @po contra o contrato vendorizado e contra `cnpj.cjs`; ver `docs/contracts/confenge-live-intelligence-v1.md`. |
| `observed_buyer_cnpjs` não tem garantia de 14 dígitos | `producer.py:297-298` faz `"".join(ch for ch in str(r.get("buyer_cnpj") or "") if ch.isdigit())` — extrai dígitos, **não valida comprimento**. `normalizeCnpj` do consumidor devolve `""` para qualquer coisa ≠ 14. Isso dita o caminho fail-closed de §A.4. |
| Mascarar `compradores` não altera nenhum resultado de fit | `fit.py:154-161` (`_dim_comparable_buyer`) compara `opportunity.orgao_cnpj in company.observed_buyer_cnpjs`, ou seja, o **campo interno** da `LiveCompany`, a montante da projeção pública. A projeção pública é folha; nada no motor lê de volta o payload público. |

---

## A) Estrutura do bundle

Três artefatos. Todos gerados **exclusivamente** a partir do snapshot selado
(`confenge_live_intelligence_*`) — nunca de releitura da view outbound, senão o
export deixa de ser função pura do snapshot e o replay determinístico morre.

### A.1 Mapeamentos de enum (não são identidades — são traduções)

| Interno (`schema.py`) | Público (contrato) | Nota |
|---|---|---|
| `SNAPSHOT_READY` (`READY_CANONICAL`) | `DATA_READY` | não é permissão de indexação |
| `SNAPSHOT_PARTIAL` | `DATA_HOLD` | bundle emitido, com `limitations` |
| `SNAPSHOT_BLOCKED` | `DATA_REJECT` | só `manifest.json`, sem `opportunities/` nem `companies/` |
| `SNAPSHOT_BUILDING`, `SNAPSHOT_SUPERSEDED` | — | não exportáveis, fail-closed |
| `DEADLINE_OPEN` | `ABERTA` | |
| `DEADLINE_CLOSED` | `ENCERRADA` | |
| `UNKNOWN` | `UNKNOWN` | |
| — | `SUSPENSA` | **nunca emitido**: nenhuma fonte no producer. Registrar em `limitations`. |

`INDEX` / `PUBLISHABLE_*` nunca aparecem: decisão editorial é do consumidor.

### A.2 `manifest.json`

```
schema            "CONFENGE_LIVE_INTELLIGENCE/1.0"     literal; ver A.2.0
contract_version  "1.0"                                 §D
catalog_mode      "official_live"                       nunca "fixture"
official_live     true                                  só se snapshot veio do datalake real
producer_status   "official_live"                       evita producer_status_not_official_live
as_of             snapshots.as_of_date
generated_at      snapshots.cutoff_at (UTC, ISO8601)    valor declarado; ver A.2.1
source_as_of      min(source_as_of) sobre os payloads emitidos (watermark UTC) — pior caso [v1.2]
freshness         {max_age_hours:48, generated_at, source_as_of, state:"FRESH"|"STALE"}
                  bloco único, copiado verbatim para cada payload; derivação em A.2.3
data_state        §A.1
coverage          {opportunities_observed, opportunities_excluded, companies_observed,
                   companies_excluded, establishment_digests, buyers_unhashable}
limitations       [texto pt-BR; sempre inclui a ausência de SUSPENSA e o escopo da fonte]
epistemic_classes {campo → FACT|CALCULATION|INFERENCE|UNKNOWN}
reason_codes      snapshots.blockers ∪ reason codes agregados
sources           [{nome:"PNCP", as_of: source_as_of}]
index             {opportunities:[{opportunity_id, file, schema, content_hash}],
                   companies:[{company_digest, file, schema, content_hash}]}
manifest_hash     live_hash(manifest sem manifest_hash)
```

`snapshot_id`, `universe_hash`, `policy_hash`, `schema_hash`, `data_hash`,
`fit_hash`, `company_ref`, `company_root8` **ficam fora** do bundle público
(`snapshot_id` embute `content_hash` interno; `company_root8` é fragmento de CNPJ
cru). Ficam num `artifacts/.../li-audit.json` interno.

#### A.2.0 **DECISÃO (rodada 2): a chave de envelope chama-se `schema`, não `contract`**

A v1.0 deste documento emitia `contract: "CONFENGE_LIVE_INTELLIGENCE/1.0"`. Isso era um risco
real de rejeição: `schema_absent` está em `reject_reason_codes` do contrato, e a chave que o
próprio contrato usa no topo é `schema` (valor `"CONFENGE_LIVE_INTELLIGENCE/1.0"`).

Decisão, em três níveis, sem alias:

1. **Envelope (`manifest.json`): `schema = "CONFENGE_LIVE_INTELLIGENCE/1.0"`.** É o valor que o
   próprio contrato se autoatribui na chave de mesmo nome. Não existe `accepted_schemas` de nível
   de bundle no contrato — só por família — então esse valor de envelope não tem contra quem
   falhar; ele existe para que a negociação **encontre** a chave e não caia em `schema_absent`.
2. **Arquivo de payload: `schema` = o valor de família** (`"live-opportunity/1.0"` /
   `"company-fit-profile/1.0"`), que é exatamente o que é negociado contra
   `producer_contracts.<família>.accepted_schemas`. Já estava em §A.3/§A.4.
3. **Entrada de `index`: ganha `schema`** com o mesmo valor de família do arquivo apontado. Custa
   uma string por arquivo e permite ao consumidor negociar **antes** de baixar cada payload —
   relevante num bundle estático com fan-out por digest (§Riscos #2).

`contract` **deixa de existir** no manifest. Não emitir as duas chaves: alias é ambiguidade
gratuita e um segundo lugar para divergir. `contract_version` permanece com esse nome — é o nome
que o contrato usa.

#### A.2.1 O manifest NÃO é reproduzível em replay — e isso é declarado

`cutoff_at` é `datetime.now(tz=UTC)` no momento do persist, e o replay reescreve
esse valor sob o **mesmo** `snapshot_id` — o próprio comentário de
`producer.py:560-566` documenta isso, por desenho (colunas de auditoria não são
insumo de hash). Consequência: `generated_at`, `freshness.state` e portanto
`manifest_hash` variam entre dois exports do mesmo snapshot.

Decisão: **aceitar e declarar**, não selar um timestamp em hash. O que é estável
em replay é o `content_hash` de cada arquivo de `opportunities/` e `companies/`
— porque a projeção pública exclui as colunas de auditoria. Nenhum teste deve
afirmar `manifest_hash` estável entre execuções; o teste correto compara o
manifest **sem** `generated_at`/`freshness`/`manifest_hash`. Escrever isso no
docstring de `export.py`, senão alguém escreve o teste errado e ele falha meses
depois sem explicação.

**Esclarecimento de escopo (v1.2) — `content_hash` × re-persist.** `freshness` está em
`payload_fields` das duas famílias, logo entra no payload e **entra no `content_hash`**; e
`freshness.generated_at` vem de `cutoff_at`. Isso não quebra o determinismo exigido: `cutoff_at`
só é reescrito num **re-persist**, nunca por um export. Dois exports do mesmo snapshot já selado
leem o mesmo `cutoff_at` e produzem o mesmo `content_hash`. Um re-persist muda todo `content_hash`
mesmo com dado idêntico — churn de cache do consumidor, **não** de evento (eventos chaveiam em
`semantic_hash`, §C.2, que não contém `freshness` nem `source_as_of`). **Rejeitado:** excluir
`freshness` do `content_hash` — o contrato não pina essa fórmula e `content_hash_mismatch` é
`reject_reason_code`; exclusão de autoria nossa é divergência não verificável.

#### A.2.2 Invariante do conjunto de arquivos

- `manifest.index` é **exatamente** o conjunto de arquivos emitidos. Nem mais, nem menos.
- Toda linha do snapshot ausente do `index` é contabilizada em `coverage.*_excluded`.

Daí decorre a escolha: linhas com `row_completeness_state != ROW_COMPLETE`
(que `_apply_row_exclusions` mantém no snapshot e `_persist` grava) **não viram
arquivo**. Elas entram só em `coverage.opportunities_excluded` /
`coverage.companies_excluded`, com seus `exclusion_reason_codes` agregados em
`manifest.reason_codes`. O `data_state` é **de snapshot**, uniforme em todos os
arquivos — não se carimba `DATA_HOLD` em linha boa por causa de linha vizinha
excluída; o que sinaliza a parcialidade é `coverage` + `limitations`.

#### A.2.3 **DECISÃO (gate sistêmico, v1.2): derivação de `freshness.state`**

O contrato **não define enum para `state`** — o bloco `freshness` dele não tem essa chave.
`FRESH`/`STALE` é forma de autoria do produtor (mesma classe do risco aberto #5). O que o contrato
pina é a **regra** (`stale_rule`, `max_age_hours: 48`) e dois reason codes **dele**
(`freshness_absent` → reject, `freshness_stale` → hold, nunca emitidos por nós).

Regra pinada (norma operacional e pseudocódigo executável vivem na **emenda do AC3** da story —
aqui fica o resumo e o porquê):

1. `generated_at` e `source_as_of` são **serializados primeiro** (ISO-8601 UTC,
   `timespec="seconds"`) e `state` é derivado das **mesmas strings emitidas** — o consumidor
   recomputa a partir das strings, e derivar de `datetime` em memória abriria janela de
   discordância silenciosa.
2. `state = "STALE"` se `generated_at − source_as_of > 48h`, **estrito**; 48h exatas → `FRESH`
   (*"exceeds"*).
3. `source_as_of` do bloco é `min()` sobre todos os payloads emitidos (pior caso), e o bloco é
   computado **uma vez** e copiado verbatim para o manifest e para cada payload — é o que
   "`freshness` idem manifest" de §A.3/§A.4 significa.
4. `source_as_of` ausente/não-parseável é **invariante fail-closed** (export aborta, nada
   escrito), não branch: a coluna é `TIMESTAMPTZ NOT NULL` (104:276,338,456) e o campo é
   `datetime` não-Optional (`schema.py:220,281`). Nenhum reason code novo para ramo morto.
5. `STALE` → código interno `source_as_of_beyond_max_age`; delta negativo → `FRESH` (fórmula do
   contrato) + `source_as_of_after_generated_at`. Ambos disjuntos dos 14 códigos do contrato.
6. **`data_state` não é rebaixado por `STALE`.** `hold_reason_codes` é vocabulário de veredito do
   consumidor (já fixado como não-emissível por produtor, risco #1(b)); `data_state` é propriedade
   de snapshot (§A.2.2). `DATA_READY` + `state:"STALE"` são dois eixos verdadeiros. §A.1 intacto.

### A.3 `opportunities/<opportunity_id>.json` — grain `opportunity_id`

| Campo do contrato | Origem real |
|---|---|
| `schema` | literal `"live-opportunity/1.0"` |
| `opportunity_id` | `LiveOpportunity.opportunity_id` (`row.bid_id` ou `row.pncp_id`, `producer.py:227`) |
| `objeto` | `LiveOpportunity.objeto`; `null` quando `objeto_state == UNKNOWN` |
| `valor` | `{faixa: valor_band, estimado_brl: valor_estimado_brl, estado: valor_state}` — rótulo `VALUE_BANDS`, nunca preço/oferta da CONFENGE; `limitations` carrega a frase de `value_semantics` |
| `orgao` | `{nome: orgao_nome, cnpj: orgao_cnpj, estado: orgao_state}` |
| `local` | `{uf, municipio, codigo_ibge, estado: geo_state}` |
| `prazo` | `{status: map(deadline_state), data_encerramento, data_publicacao}` |
| `fonte` | `{sistema: LiveOpportunity.source ("pncp"), source_id, link_edital}` |
| `as_of` | `snapshots.as_of_date` |
| `freshness` | idem manifest |
| `coverage` | `{row_completeness_state, dimensoes_desconhecidas}` |
| `limitations` | texto pt-BR |
| `epistemic_classes` | `objeto/orgao/local/prazo.data_* = FACT` (leitura direta da fonte); `valor.faixa = CALCULATION` (`value_band()`); `prazo.status = CALCULATION` (comparação com `as_of`, `producer.py:217-224`); qualquer campo com `*_state == UNKNOWN` → `UNKNOWN`. `INFERENCE` **não é emitido em W2** |
| `data_state` | §A.1 |
| `reason_codes` | `LiveOpportunity.reason_codes ∪ exclusion_reason_codes` (nossos códigos internos, disjuntos dos 14 códigos de negociação do contrato — ver §Riscos #1) |
| `content_hash` | `live_hash(payload público sem content_hash)`. **Não** reusar `LiveOpportunity.content_hash()`: aquele é do payload interno e inclui `source_as_of`; o consumidor verifica o que recebeu |

#### A.3.1 **DECISÃO (rodada 2): `orgao.cnpj` permanece — e a assimetria é do contrato**

`orgao.cnpj` (CNPJ do órgão comprador) **permanece** no payload `live-opportunity/1.0`. A razão
não é conveniência, é a estrutura do contrato:

- `producer_contracts.live_opportunity` **não possui bloco `identity`**. Não há
  `raw_cnpj_in_payload` a violar ali.
- `orgao` está explicitamente em `producer_contracts.live_opportunity.payload_fields`.
- O CNPJ de órgão público licitante é dado oficial publicado na própria fonte (PNCP), sobre
  entidade pública, não sobre o visitante.

A restrição `raw_cnpj_in_payload: false` vive dentro de
`producer_contracts.company_fit_profile.identity` e é honrada **integralmente** naquele payload
(§A.4) — inclusive para CNPJ de terceiros. Ou seja: a assimetria entre os dois arquivos é uma
leitura literal do contrato, não uma interpretação frouxa de uma regra única.

Fica registrado aqui **e** em `docs/contracts/confenge-live-intelligence-v1.md` §1, para que a
distinção seja recuperável sem depender desta sessão.

A flag de supressão de `orgao.cnpj` em `public_policy.py` permanece — desligada por padrão — como
rollback barato caso o consumidor passe a exigir. Ela **não** cobre mais `compradores[]`, porque
`compradores` deixou de carregar CNPJ (§A.4).

### A.4 `companies/<company_digest>.json` — grain `company_digest`

Um arquivo **por digest de estabelecimento**, todos projetando o mesmo perfil
raiz. É isso que faz o lookup do visitante bater com raiz ou filial em hosting
estático.

| Campo do contrato | Origem real |
|---|---|
| `schema` | literal `"company-fit-profile/1.0"` |
| `company_digest` | §B.1 (varia por arquivo; único campo que difere entre os arquivos do mesmo root) |
| `perfil` | `{razao_social: LiveCompany.razao_social, contratos_observados: len(portfolio_contract_ids), contratacao_mais_recente: most_recent_contracting_date}` — **sem** `company_root8` e **sem** `company_ref` |
| `categorias` | `LiveCompany.observed_objects` |
| `faixas` | `LiveCompany.observed_value_bands` |
| `geografias` | `LiveCompany.observed_ufs` |
| `compradores` | `[{buyer_digest}]` derivado de `LiveCompany.observed_buyer_cnpjs` — **sem CNPJ cru**, ver §A.4.1 |
| `oportunidades_aderentes` | fits com `fit_state == FIT_OBSERVED` do mesmo `company_root8`, ordenados por `fit.ordering_key` (lexicográfico, sem score): `[{opportunity_id, matched_dimensions, unknown_dimensions, reason_codes}]` |
| `gaps` | dimensões `NO_MATCH` por oportunidade |
| `unknowns` | `LiveCompanyOpportunityFit.unknown_dimensions` agregadas + `LiveCompany.reason_codes` |
| `as_of`,`freshness`,`coverage`,`limitations`,`data_state`,`reason_codes` | idem A.3 |
| `epistemic_classes` | `categorias/faixas/geografias/compradores/perfil = FACT`; `oportunidades_aderentes/gaps = CALCULATION` (comparação determinística de 5 dimensões, `fit.py`); `unknowns = UNKNOWN`; `INFERENCE` não emitido |
| `content_hash` | `live_hash(payload público sem content_hash)` |

`limitations` **obrigatoriamente** contém `disclaimer_pt`:
*"Aderência histórica não é habilitação, capacidade nem recomendação. Os dados
descrevem o histórico público declarado nas fontes citadas e podem estar
incompletos."*

Nunca emitir: `habilitado`, `elegivel`, `capacidade`, `recomendacao`, `vencedor`,
`probabilidade_vitoria`, `should_bid`, `INDEX`. Nunca emitir as strings
`extra-cli`, `scripts.public_read`, `scripts.live_intelligence`, `SmartLic` —
inclusive dentro de `limitations`/`fonte`. O `verifier.py` passa a provar as duas
listas sobre o bundle serializado, não sobre o dict.

#### A.4.1 **DECISÃO (rodada 2): `compradores` sai do CNPJ cru — opção (a)**

**A v1.0 deste documento estava errada.** Ela mantinha `compradores` = `observed_buyer_cnpjs`
(CNPJ cru dos órgãos compradores) dentro de `companies/*.json`. Esse arquivo **é** o payload
`company-fit-profile/1.0`, e é exatamente esse payload que o contrato governa com
`raw_cnpj_in_payload: false` + a nota **sem qualificação** *"The payload never carries a raw
CNPJ."* Não é leitura alternativa: é colisão.

**Decisão: opção (a).** `company-fit-profile/1.0` é livre de CNPJ cru de ponta a ponta —
da empresa-alvo **e** de terceiros. Nova forma:

```json
"compradores": [ { "buyer_digest": "0f3a…" }, … ]   // ordenado lexicográfico por buyer_digest
```

`buyer_digest = sha256("confenge-conversion|" + cnpj14).hexdigest()[:16]` — **a mesma função** de
`company_digest` (§B.1), mesma paridade com `hashCnpj`, mesma implementação em `identity.py`.
Nenhum segundo esquema de identidade.

Por que **objeto** e não lista plana de strings: `compatibility` do contrato é
`additive_nullable_within_v1`. Acrescentar uma chave a um objeto (`nome`, `uf`, no dia em que a
projeção de company carregar isso) é aditivo; converter `string` → objeto depois seria quebra. O
objeto de uma chave hoje é o formato que não obriga a quebrar amanhã.

**Caminho fail-closed obrigatório — o @dev vai errar isto se não estiver escrito.**
`producer.py:297-298` monta `observed_buyer_cnpjs` extraindo dígitos **sem validar comprimento**;
`normalizeCnpj` do consumidor devolve `""` para qualquer entrada ≠ 14 dígitos. Portanto:

- CNPJ de comprador com ≠ 14 dígitos **não** vira `buyer_digest`. É **omitido** de `compradores`.
- Cada omissão soma em `manifest.coverage.buyers_unhashable` e emite o reason code interno
  `buyer_cnpj_not_hashable` no payload da company.
- **Proibido** emitir `buyer_digest: ""` (o retorno de `hashCnpj` para entrada inválida) — string
  vazia como identidade é exatamente o descarte silencioso que este motor rejeita em toda parte.
- `observed_buyer_cnpjs` **não muda** internamente: continua a tupla de dígitos crus na
  `LiveCompany`, entra em `COMPANY_PAYLOAD_KEYS`/`portfolio_hash()` como já entra hoje. A mudança
  é **só na projeção pública**. `schema_hash()` não muda por causa desta decisão.

**Nenhum resultado de fit muda.** `fit.py:154-161` (`_dim_comparable_buyer`) compara
`opportunity.orgao_cnpj in company.observed_buyer_cnpjs` — o campo **interno**, a montante da
projeção pública. A projeção pública é folha: nada no motor a lê de volta. Confirmar isso num
teste de não-regressão de `dim_comparable_buyer`, para que o QA não precise perguntar.

`compradores` permanece `FACT` em `epistemic_classes`: um digest de uma observação continua sendo
a observação, só que sob a chave de lookup do consumidor.

**Efeito colateral aceito e declarado:** dentro de um mesmo bundle, um `buyer_digest` é
reversível por força bruta sobre os `orgao.cnpj` presentes em `opportunities/*.json` (que
permanecem crus, §A.3.1). Isso é **intencional e inofensivo**: são entidades públicas, e a
correlação é justamente o que permite ao consumidor exibir "você já atendeu este órgão". A
proteção que o contrato pede é sobre o CNPJ do **visitante**, e essa continua absoluta — nenhum
CNPJ de empresa, cru ou mascarado, existe em qualquer lugar do bundle.

---

## B) `company_ref` (interno) vs `company_digest` (público)

### B.1 `company_digest` — público, paridade obrigatória com o consumidor

```
cnpj14  = apenas dígitos, exatamente 14 posições (senão: sem digest, fail-closed)
digest  = sha256("confenge-conversion|" + cnpj14).hexdigest()[:16]
```

Reimplementação byte-a-byte de `scripts/conversion/cnpj.cjs hashCnpj` (web-cfg).
Namespace (`"confenge-conversion"`), separador (`|`) e truncamento (16) são **do consumidor**:
não versionamos nem alteramos. Prova: teste com vetores fixos (CNPJ conhecido → digest esperado),
não `assert hash == hash`.

**A mesma função serve `buyer_digest` (§A.4.1).** Uma única implementação em `identity.py`, dois
usos — nunca duas fórmulas.

Um digest por estabelecimento observado. Nunca reversível para o payload: o
bundle não contém CNPJ de empresa cru nem mascarado, e a URL é `companies/<digest>.json`.

### B.2 `company_ref` — interno, nosso namespace, versionado

```
company_ref = "cref1:" + sha256(
    "confenge-live-intelligence|company_ref|v1|" + company_root8
).hexdigest()[:32]
```

- Derivado da **raiz** (`company_root8`, já validado em `LiveCompany.__post_init__`),
  logo 1:1 com a empresa e N digests → 1 `company_ref`.
- Versão explícita no prefixo (`cref1:`). Mudança de fórmula = `cref2:`, coexistência
  possível, sem ambiguidade em replay.
- É **pseudônimo**, não anonimização: o espaço de CNPJ-8 é pequeno o suficiente para
  força bruta. Por isso **nunca** aparece em payload público, URL pública ou log
  compartilhado. Uso: coluna do motor, `subject_key` de evento, arquivo de auditoria
  interno, handoff futuro.
- Distinto de share token (share token é credencial, tem TTL e revogação;
  `company_ref` é identidade, é permanente e não autoriza nada).

### B.3 Como export, evento e replay convergem no mesmo `company_ref`

O elo digest↔ref precisa nascer **dentro do snapshot selado**, senão o export
depende de uma releitura da view e o replay diverge. Portanto:

**Adicionar a `LiveCompany`:**
- `observed_establishment_cnpjs: tuple[str, ...]` — `sorted(set())` dos
  `supplier_cnpj` de 14 dígitos das linhas agrupadas em
  `producer.project_companies` (mesmo laço que já produz `observed_buyer_cnpjs`,
  `producer.py:297-299`). CNPJ cru **interno** é precedente existente
  (`observed_buyer_cnpjs`) e `FORBIDDEN_PII_KEY_TERMS` cobre `cpf`, não `cnpj`.

**`company_ref` é MÉTODO, não campo.** `LiveCompany` é `@dataclass(frozen=True)`:
atribuir em `__post_init__` levantaria `FrozenInstanceError` sem
`object.__setattr__`. Pior, como campo ele entraria em `COMPANY_PAYLOAD_KEYS`
(derivado de `fields(LiveCompany)`, `schema.py:360`) e em `portfolio_hash()` —
redundante, já que é função pura de `company_root8`, que já está no payload, e
construível de forma inconsistente. Vira método ao lado de `portfolio_hash()`.
Decorre disto:
- `schema_hash()` muda **apenas** por causa de `observed_establishment_cnpjs`;
- a coluna `company_ref` da migration 105 é preenchida pelo producer chamando o método;
- `FIT_CORE` (§C.2) deriva `company_ref` de
  `LiveCompanyOpportunityFit.company_root8` pelo mesmo método — a dataclass de fit
  não ganha campo novo e a concordância é garantida por construção.

**Consequência declarada e aceita:** `COMPANY_PAYLOAD_KEYS` muda → `schema_hash()`
muda → `content_hash` → `snapshot_id`. É uma quebra **versionada e intencional**:
`SCHEMA_VERSION → "confenge-live-intelligence-schema/1.1"`, `ENGINE_VERSION → "1.1"`.
Custo verificado = zero (0 snapshots persistidos, HEAD não empurrado). Registrar
como decisão, não deixar como efeito colateral.

**Rejeitado:** calcular estabelecimentos/digests em tempo de export a partir de
`v_contracts_canonical_v2`. Isso (a) tornaria o export função da view e não do
snapshot, matando o replay, e (b) criaria uma segunda fonte de identidade de
empresa — mesma classe de defeito que o comentário de `WRITE_TARGET_ORDER`
(`schema.py:40-44`) já rejeitou para allowlists.

**Miss de lookup (fail-closed, nunca inventar perfil):** filial cujo CNPJ nunca
apareceu em contrato observado, ou cujo dígito verificador é inválido na fonte
(`fornecedor_cnpj` fica NULL a montante), não gera digest. O visitante recebe 404
do hosting; o `manifest.coverage.establishment_digests` e um
`reason_code = establishment_cnpj_not_observed` no manifest declaram a lacuna.

**Asserção obrigatória:** toda company `ROW_COMPLETE` produz ≥1 digest de
estabelecimento. Isso vale hoje só porque `fornecedor_cnpj` é 14-ou-NULL a
montante — `project_companies` não impõe nada (`cnpj_root8` faz `[:8]` sem
checar comprimento 14, `commercial_authority_v2.py:60-61`). Sem a asserção, uma
company com zero digests seria contada em `companies_observed` sem arquivo e sem
reason_code: invisibilidade silenciosa.

---

## C) `event_id` determinístico e mudança material

### C.1 `event_id`

```
event_id = live_hash({
    "event_type": ..., "subject_key": ...,
    "prev_semantic_hash": ..., "semantic_hash": ...,
})   # 64 hex, satisfaz o CHECK do PK (104:446)
```

Exatamente a tupla de `uq_live_intel_event_transition` (104:471-472) — a DDL já
declara o `event_id` como redundante com ela. **Não** incluir `snapshot_id`,
`source_as_of` nem `created_at`: qualquer um deles contradiz o comentário da
migration e quebra o replay. Persistência com `ON CONFLICT (event_id) DO NOTHING`.

### C.2 `semantic_hash` ≠ `content_hash()`

`source_as_of` está em `OPPORTUNITY_PAYLOAD_KEYS`, logo
`LiveOpportunity.content_hash()` muda a cada tick do watermark. Reusá-lo
regeneraria eventos exatamente no churn que a missão proíbe. Cada tipo tem uma
projeção semântica explícita, e `semantic_hash = live_hash(projeção)`.

| Tipo | `subject_key` | Projeção semântica | Critério de emissão |
|---|---|---|---|
| `NEW_OPPORTUNITY` | `opportunity:<id>` | `OPPORTUNITY_CORE` | `id` ausente no snapshot base; `prev_semantic_hash=""`, `prev_snapshot_id=NULL` (bootstrap, 104:466-469) |
| `OPPORTUNITY_CHANGED` | `opportunity:<id>` | `OPPORTUNITY_CORE` = `{opportunity_id, objeto, objeto_state, valor_band, valor_state, modalidade_id, modalidade_state, uf, municipio, codigo_ibge, geo_state, orgao_cnpj, orgao_state, row_completeness_state}` | `prev ≠ novo` |
| `DEADLINE_CHANGED` | `opportunity:<id>` | `DEADLINE_CORE` = `{opportunity_id, data_encerramento, deadline_state}` | `prev ≠ novo`. Separado de `OPPORTUNITY_CORE` porque `OPEN→CLOSED` por avanço do `as_of` é material e não deve poluir o outro tipo |
| `FIT_BECAME_RELEVANT` | `company:<company_ref>` | `FIT_CORE` = `{company_ref, opportunity_id, fit_state, matched_dimensions}` | só na transição **para** `fit_state == OBSERVED_FIT`. Downgrade não emite em W2 (declarado, não esquecido) |
| `COMPANY_PORTFOLIO_CHANGED` | `company:<company_ref>` | — | **W2 não emite.** Existe no CHECK da 104 (:450) mas o critério de materialidade depende do ciclo de crawl outbound, fora do escopo da story |

Fora de `OPPORTUNITY_CORE`, deliberadamente: `source_as_of` (churn puro),
`valor_estimado_brl` (centavos oscilam — a faixa é o fato material),
`link_edital`, `reason_codes`, todos os hashes.

`OPPORTUNITY_CORE` usa `orgao_cnpj` **cru** — é projeção **interna**, alimenta `semantic_hash` e
nunca é serializada num payload público. Não confundir com §A.3/§A.4.

**`subject_key` de eventos de empresa usa `company_ref`, não `company_digest`.**
`company_digest` é 1:N por empresa e fragmentaria um evento lógico em N linhas; a
tabela de eventos já tem `REVOKE` para leitores públicos (104:475-476), então não
há motivo para usar o identificador público internamente.

### C.3 Mudança material

Mudança material **é** `prev_semantic_hash <> semantic_hash` — ou seja,
`chk_live_intel_event_is_transition` (104:464) é a definição, não uma checagem
redundante. O diff é entre o snapshot base selado (`prev_snapshot_id`, estado
`READY_CANONICAL` ou `PARTIAL`) e o corrente. Replay do mesmo par de snapshots
produz o mesmo conjunto de `event_id`, byte a byte — é isso que o teste prova.

---

## D) `contract_version` = `1.0`

Emitimos a string `"1.0"`. `accepted_versions` das **duas** famílias
(`live_opportunity` e `company_fit_profile`) é `["1.0", "v1.0.0"]`, logo
`contract_version_unsupported` não pode disparar.

**Nota para não ser "corrigido" depois:** o contrato se autodeclara
`contract_version: "v1.0.0"` no topo. A diferença entre o que emitimos e o que o contrato exibe é
**tolerada por construção** — as duas strings estão em `accepted_versions`. Não trocar `"1.0"` por
`"v1.0.0"` sem motivo: qualquer troca é churn com risco e zero ganho.

O `SCHEMA_VERSION` interno vai a `1.1` (§B.3); as duas linhas de versão são **independentes** por
desenho: schema interno é do motor, `contract_version` é do contrato público.

---

## E) Prova de equivalência outbound com DB isolado (TD-LI-6, agora)

Mesma instância Postgres, database nova. Não é host novo.

1. `CREATE DATABASE extra_li_equiv TEMPLATE template0;` em `127.0.0.1:5433`.
   DSN: `postgresql://test:test@127.0.0.1:5433/extra_li_equiv`.
   Motivo: o watermark do DSN principal é compartilhado com os demais testes e
   contamina o caso `BLOCKED` (TD-LI-6).
2. `python3 -m scripts.ops.apply_migrations --dsn "$LI_EQUIV_DSN"` (inclui a 104 e a 105).
3. Seed determinístico de fixture: linhas em `pncp_raw_bids` com `updated_at`
   fixo (watermark determinístico) e em `pncp_supplier_contracts` com
   `fornecedor_cnpj` válido, incluindo **raiz + filial** do mesmo CNPJ-8 para
   exercitar §B, **e ao menos um `buyer_cnpj` com ≠ 14 dígitos** para exercitar o caminho
   fail-closed de §A.4.1.
4. Captura BEFORE, dois instrumentos independentes:
   - conteúdo: por objeto outbound tocado por `sources.py`
     (`pncp_raw_bids`, `pncp_supplier_contracts`, `contract_role_links`,
     `sc_public_entities`): `md5(string_agg(t::text, '|' ORDER BY t::text))` + `count(*)`;
   - escrita: `n_tup_ins / n_tup_upd / n_tup_del` de `pg_stat_all_tables`
     (chamar `pg_stat_clear_snapshot()` antes de cada leitura). Isso pega até um
     write seguido de rollback do mesmo valor, que o digest de conteúdo não pegaria.
5. Rodar `build_snapshot(..., persist=True)` contra o DSN isolado, e o export.
6. Captura AFTER. Asserção: digests idênticos **e** delta de `n_tup_*` = 0 para
   todo objeto fora de `ALLOWED_WRITE_TARGETS`.
7. Reforço estrutural (não só asserção de teste): executar o build sob o role
   dedicado **`li_equiv_runner`**. **REESCRITO em v1.2 (gate sistêmico).** A redação da v1.1
   (*"estendendo `confenge_live_intel_reader`, já criado pela 104"*) está **revogada**:
   `CREATE ROLE` é **cluster-global** (só os grants são por-database), logo estender o role de
   leitura o alargaria em `extra_test` e em **produção** para satisfazer um teste local —
   contradição direta com o próprio §E. Desenho correto:
   - role **novo e distinto** `li_equiv_runner`, criado e destruído **só** por
     `scripts/ops/li_equiv_db.py`, nunca por migration (as 104/105 não ganham `GRANT
     INSERT/DELETE`);
   - grants derivados de `schema.WRITE_TARGET_ORDER` **importado por nome** — nunca uma segunda
     lista literal (AR-2/ADR-040, `schema.py:40-46`) — com `SELECT, INSERT, UPDATE, DELETE` +
     `USAGE` de sequence nessas tabelas e `SELECT` e nada mais no outbound (enumerar "só
     INSERT/DELETE" quebraria o `UPDATE` do persist);
   - guarda fail-closed de DSN (dbname == `extra_li_equiv` + host loopback);
   - teardown `DROP OWNED BY` → `DROP DATABASE` → `DROP ROLE`, obrigatório: role vazado é
     resíduo de catálogo cluster-global.
   Qualquer DML outbound falha por permissão dentro do motor.
8. Teardown: alvo `make li-equiv` cria, roda e derruba a database.

---

## F) Arquivos do W2

**Novos**

| Arquivo | Responsabilidade |
|---|---|
| `scripts/confenge_live_intelligence/identity.py` | `cnpj_digest()` (paridade com `hashCnpj`; serve `company_digest` **e** `buyer_digest`) e `company_ref_from_root8()` (namespace interno versionado) |
| `scripts/confenge_live_intelligence/public_policy.py` | Mapas de enum público, `epistemic_classes`, `disclaimer_pt`, listas de campos e linguagem proibidos, flag de supressão de `orgao.cnpj` |
| `scripts/confenge_live_intelligence/export.py` | Monta `manifest.json`, `opportunities/*.json`, `companies/*.json` a partir do snapshot selado |
| `scripts/confenge_live_intelligence/events.py` | Diff entre snapshots, projeções semânticas por tipo, `event_id`, persistência idempotente |
| `db/migrations/105_confenge_live_intelligence_company_ref.sql` | Colunas aditivas `company_ref` e `observed_establishment_cnpjs` + índice; zero DML outbound |
| `scripts/ops/li_equiv_db.py` | Cria/aplica/derruba o database isolado de equivalência **e é o dono único do role dedicado `li_equiv_runner`** (§E.7, v1.2) — nenhuma migration concede DML |
| `fixtures/confenge_live_intelligence/equivalence_seed.sql` | Seed determinístico com raiz + filial + comprador não-hasheável |
| `tests/confenge_live_intelligence/test_identity.py` | Vetores fixos de paridade do digest com o JS; N digests → 1 `company_ref`; `cnpj` ≠ 14 dígitos → sem digest (nunca `""`) |
| `tests/confenge_live_intelligence/test_events.py` | Replay determinístico; ausência de churn por `as_of`/watermark |
| `tests/confenge_live_intelligence/test_export_contract.py` | Key-set exato vs. contrato **vendorizado**; `schema` presente no manifest, em cada payload e em cada entrada de `index`; ausência de CNPJ cru em `companies/*.json`; disjunção entre nossos `reason_codes` e os 14 do contrato; campos/linguagem proibidos; `content_hash` verificável |
| `tests/confenge_live_intelligence/test_outbound_equivalence.py` | Prova de §E contra o DSN isolado |

**Alterados**

| Arquivo | Mudança |
|---|---|
| `scripts/confenge_live_intelligence/schema.py` | `observed_establishment_cnpjs` em `LiveCompany`; `company_ref()` como método; `SCHEMA_VERSION`→`1.1`, `ENGINE_VERSION`→`1.1` |
| `scripts/confenge_live_intelligence/producer.py` | Coleta de CNPJ14 de estabelecimento em `project_companies`; persistência das colunas novas; encadeia geração de eventos após selar o snapshot |
| `scripts/confenge_live_intelligence/cli.py` | Subcomandos `export` e `events` |
| `scripts/confenge_live_intelligence/verifier.py` | Verificação do bundle público serializado (hashes, key-set, campos/linguagem proibidos, ausência de CNPJ cru em `companies/*.json`) |
| `Makefile` | Alvo `li-equiv` |
| `tests/test_live_intelligence_outbound_equivalence.py` | **[v1.2]** Parametrizar as constantes `MIGRATION`/`ROLLBACK` (`:32-33`) para os quatro caminhos (104/105 + rollbacks) e estender os testes de `:69/:74/:92/:104/:114`. **Não** criar arquivo novo para a 105 — seria um segundo instrumento para a mesma proposição |
| `tests/confenge_live_intelligence/test_migration_grants_and_rollback.py` | **[v1.2]** Mesmas constantes (`:34-35`) em tupla; `:229/:250` parametrizado sobre as duas migrations; `:290` vira ciclo empilhado (104+105 → r105 → r104 → resíduo → reaplicar); funções novas no mesmo arquivo para `attacl IS NULL` das colunas da 105 e `relacl` inalterado |
| `docs/contracts/confenge-live-intelligence-v1.json` / `.md` | Contrato vendorizado + proveniência (novos, mas são docs, não código) |

---

## Riscos residuais

> Os riscos #1 e #3 da v1.0 deste documento (`"a verificar contra #573 quando acessível"` e
> `"precisa confirmação do consumidor antes do go-live"`) estão **RESOLVIDOS**. O contrato foi
> obtido, lido na íntegra e vendorizado; as duas incógnitas viraram decisão registrada. A lista
> abaixo é a lista pós-resolução.

### RESOLVIDOS nesta rodada (mantidos por rastreabilidade)

| Item da v1.0 | Resolução | Evidência |
|---|---|---|
| #1(a) *"a negociação de schema roda também sobre `manifest.json`, que emite `contract` e não `schema`?"* | Resolvido: o manifest passa a emitir `schema` (§A.2.0), `contract` é removido, e cada entrada de `index` ganha `schema`. `schema_absent` deixa de ser alcançável. | Contrato `dea6457a…`: chave de topo `schema`, `reject_reason_codes` inclui `schema_absent`, `accepted_schemas` por família. |
| #1(b) *"`reason_codes` é validado contra enum fechado?"* | Resolvido: os 14 códigos do topo são veredictos de **negociação do consumidor** (`schema_absent`, `content_hash_mismatch`, `fixture_as_live`, `producer_status_not_official_live`…), nenhum emissível por um produtor sobre seus próprios dados; e `reason_codes` também está em `payload_fields` das duas famílias, logo o campo de payload é de autoria do produtor. Salvaguarda: `test_export_contract.py` assere **disjunção** entre nossos códigos e os 14 do contrato. | Contrato `dea6457a…`, blocos `reason_codes`, `reject_reason_codes`, `producer_contracts.*.payload_fields`. |
| #1(c) *paridade do `hashCnpj` depende de repo externo não mergeado* | Reduzido a risco de mudança futura, não de incógnita atual: fórmula lida nos dois blobs relevantes (`8b88a894e` @ `dea6457a…`, `1a5452a2d` @ `909621a05…`), idênticas em `hashCnpj`; divergência restrita à coerção de entrada não-string em `onlyDigits`, sem efeito para CNPJ string. Mitigação permanente: vetores fixos no teste + proveniência congelada em `docs/contracts/confenge-live-intelligence-v1.md`. | `git diff` dos dois blobs, registrado no `.md` de proveniência. |
| #3 *`orgao.cnpj` no payload público é leitura nossa* | Resolvido por adjudicação estrutural: `live_opportunity` não tem bloco `identity`; `company_fit_profile` tem, e passa a ser cumprido **integralmente** (§A.4.1 remove o CNPJ cru de `compradores`). A assimetria é do contrato. Documentada em dois lugares versionados. | Contrato `dea6457a…`, `producer_contracts.*`. §A.3.1, §A.4.1 e `docs/contracts/confenge-live-intelligence-v1.md` §1. |

### ABERTOS

1. **Mudança futura do consumidor no `hashCnpj`.** Se web-cfg alterar o salt
   `"confenge-conversion"`, o separador `|` ou o truncamento em 16, todo lookup quebra
   **silenciosamente** (404 em massa, sem erro). É o modo de falha mais caro do bundle porque não
   levanta exceção em lugar nenhum. Mitigação: vetores fixos em `test_identity.py` (falham na
   hora se reimplementarmos errado) + proveniência congelada (permite diff dirigido a cada
   re-vendorização). **Não mitigável do nosso lado além disso** — é acoplamento a repo externo por
   desenho do contrato.
2. **Fan-out de arquivos por digest.** Empresas com muitas filiais multiplicam
   `companies/*.json` (conteúdo idêntico salvo `company_digest`). Aceitável em W2; revisar se o
   bundle passar da ordem de dezenas de MB. O `schema` por entrada de `index` (§A.2.0) mitiga
   parcialmente ao permitir negociação sem download.
3. **`compradores` perde legibilidade humana.** Após §A.4.1, o consumidor só resolve um
   `buyer_digest` para nome cruzando com `orgao.cnpj` das `opportunities/` do mesmo bundle — o que
   cobre apenas compradores que também aparecem como órgão de oportunidade viva. Compradores
   históricos ficam como digest opaco. Aceito: `LiveCompany` não carrega nome de comprador hoje, e
   inventar um seria segunda fonte de identidade. Evolução aditiva (`compradores[].nome`) fica
   disponível justamente porque a forma escolhida é objeto, não string.
