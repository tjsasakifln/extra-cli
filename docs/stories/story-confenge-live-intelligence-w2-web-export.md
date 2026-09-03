# Story: CONFENGE Live Intelligence — W2 Web Export (Exporter, Identidade, Eventos)

**Status:** Done

> **✅ GATE SISTÊMICO HIGH-RISK APROVADO (@architect, 2026-09-03, v1.1).** As três decisões
> pendentes estão fechadas **dentro da story**, não em sessão: (1) derivação de `freshness.state`
> pinada na **emenda do AC3**; (2) role de escrita de `extra_li_equiv` com dono explícito
> (`scripts/ops/li_equiv_db.py`, role dedicado `li_equiv_runner` — **não**
> `confenge_live_intel_reader`), Task 10; (3) parametrização dos dois testes existentes para a
> 105, Task 11. Um achado adicional virou esclarecimento de escopo do **AC4** (`content_hash` e
> re-persist) — não é defeito e não bloqueia. **Próximo agente: @dev**, a partir da Task 2.

> **Validação GO do @po (2026-09-03, rodada 3, v1.0.4).** Rubrica 10 pontos: 9.6/10. Prontidão
> para implementação: 9/10. Os três bloqueadores da v1.0.2 estão **fechados e auditados no
> worktree** (não por alegação). Próximo agente: **@data-engineer** (migration 105) → **@architect**
> (gate sistêmico, com dois itens nomeados) → **@dev**. Ver Change Log v1.0.4.

**Nível de risco:** HIGH-RISK (nova migration `105`, mudança de `SCHEMA_VERSION`/`ENGINE_VERSION`,
contrato público consumido por sistema externo). Fluxo obrigatório: @data-engineer (migration
105) → @architect (revisão de impacto, já pré-fechada no documento de decisões — ver abaixo) →
@sm (esta story) → @po → @dev → @qa aprofundado → gate sistêmico → @po → @devops.

> **✅ Adjudicação do @architect (2026-09-03, rodada 2 — responde ao NO-GO do @po v1.0.2).**
> Os três bloqueadores de adjudicação estão **fechados**, e o fechamento é auditável sem depender
> de sessão:
> (a) **§A.2/§A.3/§A.4/§C.2 estão inlineadas** nas Dev Notes desta story (tabelas literais, não
> ponteiros) — ver "Layout do bundle" e "Projeções semânticas de evento";
> (b) o documento de arquitetura **saiu do scratchpad** e vive versionado em
> `docs/architecture/confenge-live-intelligence-w2-decisions.md` (v1.1), com os riscos residuais
> #1 e #3 **resolvidos** (não mais "a verificar") e a evidência registrada; o contrato do
> consumidor foi **vendorizado** em `docs/contracts/confenge-live-intelligence-v1.json` (+ `.md`
> de proveniência), o que também encerra o bloqueador (3) da v1.0.1 e torna `test_export_contract.py`
> escrevível offline;
> (c) **`compradores` deixa de carregar CNPJ cru** — decisão do @architect, opção (a):
> `company-fit-profile/1.0` é livre de CNPJ cru de ponta a ponta, inclusive de terceiros. AC6 foi
> reescrito. `orgao.cnpj` em `opportunities/*.json` permanece, porque `producer_contracts.live_opportunity`
> **não tem bloco `identity`** — a assimetria é do contrato, não do produtor.
> Decisão adicional da mesma rodada: `manifest.json` emite **`schema`**, não `contract` (AC1),
> para não cair em `schema_absent`. A sequência HIGH-RISK do cabeçalho continua correta; o gate
> sistêmico após a 105 permanece.

**Insumo de arquitetura (fechado, não reabrir):**
`docs/architecture/confenge-live-intelligence-w2-decisions.md` v1.1 (@architect), seções A–F.
Toda decisão de nomenclatura de campo, fórmula de hash e mapeamento de enum abaixo vem desse
documento. **O conteúdo normativo necessário à implementação está inlineado nas Dev Notes desta
story** — o @dev não precisa abrir o documento para implementar; ele é background e histórico de
decisão. Se story e documento divergirem em algum detalhe, isso é um defeito a corrigir por
adjudicação do @architect, não uma licença para o @dev escolher.

## Referências cruzadas

- Story de origem: `docs/stories/story-confenge-live-intelligence-01.md` (motor v1, mergeado em
  `64c04a43`/`a0b99fd6`).
- Migration base: `db/migrations/104_confenge_live_intelligence_v1.sql` (tabela `events` nasce
  vazia; esta story é o "LI-7" citado no comentário de `104` — quem popula `events`).
- Contrato consumidor: web-cfg PR #573 (schemas `live-opportunity/1.0`, `company-fit-profile/1.0`),
  **vendorizado** neste repo em `docs/contracts/confenge-live-intelligence-v1.json` (cópia verbatim
  de `tjsasakifln/web-cfg` @ `dea6457a14b17279713fb357cbce6c6e8087ce6c`, `sha256 875a9990…`), com
  proveniência e leituras normativas em `docs/contracts/confenge-live-intelligence-v1.md`.
- Documento de decisões do @architect: `docs/architecture/confenge-live-intelligence-w2-decisions.md` (v1.1).
- Story irmã (não sobreposta, ver "Relação com a story de equivalência de dois braços" abaixo):
  `docs/stories/story-confenge-live-intelligence-outbound-equivalence-gate.md` (Draft, absorve
  TD-LI-1, TD-LI-6, AR-3, AR-4, REL-004, REL-005 na tabela de débitos daquela story, v1.1).

## Story

**Como** o sistema web-cfg (consumidor externo do contrato `CONFENGE_LIVE_INTELLIGENCE/1.0`),
**eu quero** um bundle estático (`manifest.json` + `opportunities/*.json` + `companies/*.json`)
gerado deterministicamente a partir de um snapshot selado do motor Live Intelligence, com
identidade de empresa por CNPJ de estabelecimento e um feed de eventos idempotente,
**para que** eu possa publicar oportunidades e perfis de aderência sem nunca receber CNPJ cru/
mascarado de empresa, sem inventar rótulos de habilitação/recomendação, e com garantia de que o
motor nunca escreveu em nenhuma tabela outbound do pipeline.

## Acceptance Criteria

Numeração `ACn` referencia as seções do documento de arquitetura entre colchetes.

**AC1 — Bundle estruturalmente correto e fail-closed por `data_state` [§A.1, §A.2.2]**
- Given um snapshot `SNAPSHOT_READY` (`READY_CANONICAL`)
  When `export.py` roda sobre ele
  Then `manifest.json` traz `data_state="DATA_READY"`, `catalog_mode="official_live"`,
  `official_live=true`, `producer_status="official_live"`, `schema="CONFENGE_LIVE_INTELLIGENCE/1.0"`,
  `contract_version="1.0"`, e `manifest.index` lista exatamente um arquivo por
  `opportunities/<opportunity_id>.json` e `companies/<company_digest>.json` emitido — nem mais,
  nem menos.
- **A chave de envelope chama-se `schema`, não `contract` [§A.2.0].** `contract` **não é emitido**
  em lugar nenhum do manifest (sem alias — alias é um segundo lugar para divergir). Motivo:
  `schema_absent` está em `reject_reason_codes` do contrato e a chave que o próprio contrato usa
  no topo é `schema`. Três níveis, todos obrigatórios:
  (i) `manifest.schema = "CONFENGE_LIVE_INTELLIGENCE/1.0"`;
  (ii) cada payload já carrega seu `schema` de família (`"live-opportunity/1.0"` /
  `"company-fit-profile/1.0"`), que é o valor negociado contra
  `producer_contracts.<família>.accepted_schemas`;
  (iii) **cada entrada de `manifest.index` ganha `schema`** com o mesmo valor de família do
  arquivo apontado, para permitir negociação antes do download —
  `index.opportunities[] = {opportunity_id, file, schema, content_hash}` e
  `index.companies[] = {company_digest, file, schema, content_hash}`.
- Given um snapshot `SNAPSHOT_PARTIAL`
  When exportado
  Then `data_state="DATA_HOLD"`, `manifest.json` inclui `limitations` não-vazio, e apenas as
  linhas `row_completeness_state == ROW_COMPLETE` viram arquivo; toda linha excluída soma em
  `coverage.opportunities_excluded`/`coverage.companies_excluded` com seus
  `exclusion_reason_codes` agregados em `manifest.reason_codes`.
- Given um snapshot `SNAPSHOT_BLOCKED`
  When exportado
  Then apenas `manifest.json` é emitido (`data_state="DATA_REJECT"`), sem diretório
  `opportunities/` nem `companies/`.
- Given um snapshot `SNAPSHOT_BUILDING` ou `SNAPSHOT_SUPERSEDED`
  When `export.py` é invocado
  Then o export falha fail-closed (nenhum arquivo escrito) — nenhum desses dois estados é
  exportável, por design (§A.1). Nota: emissão de `SUPERSEDED` em si (REL-004) não é escopo
  desta story — ver "Fora de escopo".

> **Emenda do @architect (2026-09-03, adjudicação do QA REQ-001) — `official_live` é
> proveniência REIVINDICADA, nunca literal.** Esta emenda resolve uma **contradição já existente
> dentro da própria story**, não acrescenta requisito: o primeiro Given do AC1 manda
> `official_live=true` incondicionalmente, enquanto a tabela §A.2 das Dev Notes (validada pelo
> @po na v1.0.4) qualifica *"`official_live` true — **só se snapshot veio do datalake real**"*.
> As duas leituras não podem ser verdadeiras ao mesmo tempo. **§A.2 governa**, e passa a ser
> operacional.

- Given que o contrato define `catalog_mode.official_live` como *"only when producers are live
  official artifacts and **claimed_live is true**"* e `catalog_mode.fixture` como *"labeled
  fixture; never consumed or labeled as live"*
  When o bundle é montado
  Then `catalog_mode` é um **parâmetro do export** (`build_bundle`/`export_bundle`
  `catalog_mode=`, CLI `--catalog-mode`), com vocabulário fechado
  `{"fixture", "official_live"}` e **default fail-closed `"fixture"`**; `official_live` e
  `producer_status` são **derivados** desse único parâmetro (`official_live ==
  (catalog_mode == "official_live")`; `producer_status == catalog_mode`). Valor fora do
  vocabulário → `LiveIntelligenceExportError` antes de qualquer `write`.
- Given um export feito sem declarar proveniência (banco de teste, seed sintético, `extra_li_equiv`,
  CI)
  Then o bundle sai **rotulado `fixture`** (`official_live: false`,
  `producer_status: "fixture"`) e o consumidor o recusa por
  `producer_status_not_official_live` — que é exatamente o efeito desejado. Omitir a
  reivindicação **nunca** pode produzir um bundle rotulado live. Este é o defeito que o @qa
  reproduziu (REQ-001) e o que esta emenda fecha: o rótulo deixa de ser literal e passa a exigir
  afirmação deliberada de quem exporta.
- **`catalog_mode` NÃO é função do `state` do snapshot — rejeitado explicitamente.** Proveniência
  e completude são eixos independentes, exatamente como `freshness.state` e `data_state` na
  emenda do AC3. `official_live: true` com `data_state: "DATA_REJECT"` é **coerente** (produtor
  real, nada publicável), e rebaixar a proveniência por causa do estado do snapshot criaria um
  terceiro eixo implícito que o contrato não tem. O mapa de §A.1 permanece **intacto**.
- **Nenhum reason code novo é criado para o caminho `fixture`.** `catalog_mode`/`official_live`/
  `producer_status` já declaram a proveniência de forma explícita, e `fixture_as_live` é código
  de veredito do **consumidor** — a disjunção do AC3 continua valendo sem exceção.
- **Limite honesto, declarado:** isto é uma **reivindicação**, não uma verificação de origem. O
  produtor não tem modo fixture e não existe coluna de proveniência no snapshot; adicionar uma
  exigiria migration `106` e está **fora de escopo**. Foi também rejeitado vetar a reivindicação
  por marcador de seed (`LI-TEST-`): todo seed do repositório carrega o prefixo, logo o veto
  tornaria o próprio AC1 inverificável por teste. O que muda — e é o que importa — é o
  **default**.
- Given `test_export_contract.py`
  Then as asserções obrigatórias são: export sem reivindicação → `catalog_mode == "fixture"`,
  `official_live is False`, `producer_status == "fixture"`, **e `data_state` inalterado**
  (`DATA_READY`), provando a independência dos eixos; `catalog_mode` inválido → erro fail-closed
  sem diretório de saída criado; e o caminho `official_live` (o do primeiro Given deste AC) só
  vale sob reivindicação explícita.

> **Ratificação do @architect (2026-09-03, adjudicação do QA DOC-001) — bundle sem payload
> emitido.** Um bundle exportável **sem nenhum payload** tem exatamente **dois** sub-casos, e
> ambos seguem **o mesmo caminho**, sem reason code novo:
> (i) `SNAPSHOT_BLOCKED`, que por este AC nunca emite payload; e
> (ii) universo **legitimamente vazio** em `READY_CANONICAL`/`SNAPSHOT_PARTIAL`.
> Tratamento único e ratificado: o export **prossegue** (universo vazio é snapshot selado válido,
> não corrupção — o ramo de aborto da emenda do AC3 nomeia apenas `generated_at`/`source_as_of`
> ausentes ou sem fuso); `manifest.index` com **zero** arquivo satisfaz o "nem mais, nem menos"
> deste AC; e, como não existe `min(source_as_of)`, o bloco `freshness` reflete o `cutoff_at` do
> próprio snapshot, **substituição declarada** em `limitations` via
> `LIMITATION_NO_PAYLOAD_EMITTED`. **Nenhum reason code novo** — inventar um seria mais uma
> string a um hífen de distância do vocabulário do consumidor, pelo mesmo argumento já usado no
> ramo morto de `freshness_absent`. Recusar o export aqui foi **rejeitado**: seria substituir
> regra pinada por juízo próprio, a classe de desvio que a emenda do AC3 existe para eliminar.
> A rota implementada pelo @dev e verificada pelo @qa está **ratificada como está** — nada a
> mudar no código.

**AC2 — Export é função pura do snapshot selado, nunca da view outbound [preâmbulo §A]**
- Given o mesmo `snapshot_id` já persistido
  When `export.py` roda duas vezes seguidas
  Then nenhuma chamada a `v_contracts_canonical_v2` (ou qualquer view outbound) ocorre durante o
  export — todo dado do bundle vem das tabelas `confenge_live_intelligence_*` do snapshot selado.

**AC3 — `generated_at`/`source_as_of` nunca vêm de wall-clock direta no export, e `freshness.state`
é derivado por fórmula pinada [§A.2.1, §A.2.3]**
- Given um snapshot persistido com `cutoff_at` e `as_of_date` conhecidos
  When `manifest.json` é gerado
  Then `generated_at` é lido de `snapshots.cutoff_at` (não de `datetime.now()` chamado dentro de
  `export.py`) e `source_as_of`/`as_of` refletem os watermarks/`as_of_date` gravados no
  snapshot — `export.py` nunca chama `datetime.now()`.

> **Emenda do @architect no gate sistêmico (2026-09-03) — fecha o risco aberto #4 levantado pelo
> @po na v1.0.4.** A derivação de `freshness.state` deixa de ser escolha do @dev. Esta é a
> **única** definição normativa da regra em toda a story; Dev Notes só explica o porquê.

- Given os dois insumos do bloco `freshness` (`snapshots.cutoff_at` e o watermark `source_as_of`),
  When o bloco é montado,
  Then o @dev implementa **exatamente** isto, sem variação:

```python
FRESHNESS_MAX_AGE_HOURS = 48          # docs/contracts/...v1.json → freshness.max_age_hours

# (0) INSUMOS — os dois vêm do snapshot selado, nunca de wall-clock (Given acima).
generated_at_dt = snapshots.cutoff_at
source_as_of_dt = min(source_as_of de TODOS os payloads emitidos)   # pior caso, fail-closed

# (1) INVARIANTE fail-closed — não é branch de runtime.
#     source_as_of é TIMESTAMPTZ NOT NULL na 104 (:276, :338, :456) e `datetime`
#     não-Optional em LiveOpportunity/LiveCompany (schema.py:220, :281). Ausência ou
#     valor não-aware é corrupção de snapshot, não um estado exportável:
if generated_at_dt is None or source_as_of_dt is None or tzinfo ausente em qualquer um:
    raise  # export aborta, NENHUM arquivo escrito (nem manifest)

# (2) SERIALIZA PRIMEIRO, DERIVA DEPOIS — as duas datas viram string antes da comparação.
generated_at = generated_at_dt.astimezone(UTC).isoformat(timespec="seconds")   # "...+00:00"
source_as_of = source_as_of_dt.astimezone(UTC).isoformat(timespec="seconds")

# (3) estado derivado das MESMAS strings que serão emitidas
age = datetime.fromisoformat(generated_at) - datetime.fromisoformat(source_as_of)
state = "STALE" if age > timedelta(hours=FRESHNESS_MAX_AGE_HOURS) else "FRESH"

freshness = {"max_age_hours": FRESHNESS_MAX_AGE_HOURS,
             "generated_at": generated_at,
             "source_as_of": source_as_of,
             "state": state}
```

- **`source_as_of` do bloco é o pior caso do bundle:** `min(source_as_of)` sobre **todos** os
  payloads emitidos (`opportunities/` ∪ `companies/`). O bloco `freshness` é computado **uma vez**
  e copiado **verbatim** para o `manifest.json` e para cada payload — é isso que "`freshness` idem
  manifest" das tabelas §A.3/§A.4 significa. **Proibido** computar `freshness` por arquivo: dois
  arquivos do mesmo bundle com `state` divergente é ambiguidade que o contrato não resolve.
- **Comparação é estrita (`>`).** Exatamente 48h → `FRESH`. Motivo: o contrato diz *"exceeds
  max_age_hours"*. Teste de fronteira obrigatório: 48h exatas → `FRESH`; 48h + 1s → `STALE`.
- Given `state == "STALE"`
  Then `manifest.reason_codes` inclui o código **interno** `source_as_of_beyond_max_age` e
  `limitations` ganha uma linha pt-BR declarando o atraso. **`freshness_stale` NUNCA é emitido por
  nós** — está entre os 14 códigos de veredito do consumidor, e a `test_export_contract.py` assere
  **disjunção** (Task 11). O que acontece do lado de lá é consequência declarada, não emissão
  nossa: o consumidor recomputa a mesma fórmula sobre as mesmas strings, obtém `STALE`, emite
  `freshness_stale` e **segura** o bundle (`hold_reason_codes`). Concordância byte-a-byte é o
  objetivo inteiro desta emenda.
- Given `source_as_of` ausente/não-parseável
  Then o caminho é o (1) acima: **export aborta**, nada é escrito. Não emitimos bundle algum, e
  portanto não existe caminho em que o consumidor recompute `freshness_absent` (reject) sobre um
  artefato nosso. `freshness_absent` e `as_of_unparseable` também são códigos **dele**, nunca
  nossos. Nenhum reason code interno é criado para este caso — ele é inalcançável por construção
  (`NOT NULL` no banco + tipo não-Optional na dataclass), e inventar um código para um ramo morto
  seria mais uma string a um hífen de distância do vocabulário do consumidor.
- Given `source_as_of > generated_at` (delta negativo — anomalia de relógio/watermark)
  Then `state` permanece `FRESH` (a fórmula do contrato não é satisfeita: delta negativo não
  "excede" 48h), **e** o código interno `source_as_of_after_generated_at` entra em
  `manifest.reason_codes` com linha em `limitations`. **Proibido** rotular `STALE` aqui: divergir
  da fórmula do consumidor para "ser conservador" reintroduz exatamente a falha silenciosa que
  esta emenda existe para eliminar.
- **`data_state` NÃO é rebaixado por `state == "STALE"`.** Os dois eixos são independentes:
  `data_state` é propriedade **do snapshot** (§A.2.2 — completude estrutural), `freshness.state` é
  idade em relação ao SLO de publicação. `DATA_READY` + `state: "STALE"` é coerente, não
  contraditório — `DATA_READY` já é declaradamente *não* permissão de indexação. O mapa de §A.1
  (AC1) permanece **intacto**.
- Given `test_export_contract.py`
  Then as asserções obrigatórias são: fronteira de 48h nos dois sentidos; `freshness` idêntico
  (igualdade de dict) entre `manifest.json` e todo payload; `source_as_of` do bloco == `min` dos
  payloads; `state` recomputado a partir das strings serializadas bate com o emitido; e os dois
  códigos internos (`source_as_of_beyond_max_age`, `source_as_of_after_generated_at`) são
  disjuntos dos 14 do contrato.

**AC4 — Determinismo de replay é escopado ao `content_hash` por arquivo, não ao manifest inteiro [§A.2.1]**
- Given o mesmo `snapshot_id` selado
  When o export roda duas vezes em momentos diferentes
  Then o `content_hash` de cada `opportunities/<id>.json` e `companies/<digest>.json` é
  idêntico entre as duas execuções, e o `manifest.json` das duas execuções é idêntico quando
  comparado **excluindo** `generated_at`, `freshness` e `manifest_hash` (esses três campos
  variam por desenho porque `cutoff_at` é reescrito a cada persist/replay sob o mesmo
  `snapshot_id` — comportamento documentado em `producer.py:560-566`, não um bug).
  Nenhum teste desta story pode afirmar `manifest_hash` estável entre execuções — isso é
  proibido explicitamente pelo documento de arquitetura.

> **Esclarecimento de escopo do @architect no gate sistêmico (2026-09-03) — não é defeito, é
> precisão de leitura.** Como `freshness` está em `payload_fields` das duas famílias, ele **entra**
> no payload e portanto **entra** no `content_hash`; e `freshness.generated_at` vem de `cutoff_at`.
> A estabilidade que o AC4 exige continua verdadeira porque `cutoff_at` só é reescrito em um
> **re-persist** (`build_snapshot(..., persist=True)` de novo), **nunca** por um export: dois
> exports do mesmo snapshot já selado leem o mesmo `cutoff_at` do banco e produzem o mesmo
> `content_hash`. O "momentos diferentes" do Given acima é **sem re-persist intercalado** — é
> assim que o teste deve ser escrito.
> Consequência declarada e aceita: um re-persist do mesmo `snapshot_id` muda `cutoff_at` → muda
> `freshness` → muda **todo** `content_hash`, mesmo com dado idêntico. Isso é churn para o
> consumidor (cache/refetch), **não** churn de evento: eventos chaveiam em `semantic_hash`
> (§C.2), que não contém `freshness` nem `source_as_of`. **Rejeitado** como solução: excluir
> `freshness` do `content_hash`. O contrato não pina a fórmula do `content_hash` e
> `content_hash_mismatch` é `reject_reason_code` — qualquer exclusão de nossa autoria é uma
> divergência que não temos como verificar contra o consumidor.
> Teste obrigatório: `content_hash` estável em dois exports sem re-persist. **Proibido** escrever
> teste que afirme `content_hash` estável **através** de re-persist — falharia por desenho.

**AC5 — Campos e linguagem proibidos nunca aparecem, sobre o bundle serializado [§A.4, "Nunca emitir"]**
- Given qualquer `opportunities/*.json` ou `companies/*.json` emitido
  When o bundle serializado (JSON de disco, não o dict Python em memória) é verificado por
  `verifier.py`
  Then nenhuma das strings `habilitado`, `elegivel`, `capacidade`, `recomendacao`, `vencedor`,
  `probabilidade_vitoria`, `should_bid` aparece como chave ou valor, e `INDEX` nunca aparece como
  **valor de enum de status/`data_state`** (o campo `manifest.index`, que é o índice obrigatório
  de arquivos do bundle, não é afetado por essa proibição — são coisas diferentes).
- E nenhuma das strings `extra-cli`, `scripts.public_read`, `scripts.live_intelligence`, `SmartLic`
  aparece em nenhum lugar do bundle serializado, incluindo dentro de `limitations` e `fonte`.

> **Emenda do @architect (2026-09-03, adjudicação do QA SEC-001) — "aparece como chave ou valor"
> significa IGUALDADE para `FORBIDDEN_FIELDS`, e SUBSTRING para `FORBIDDEN_STRINGS`. Os dois
> modos são deliberados e não são intercambiáveis.** Decisão: **manter a comparação por
> igualdade** (opção (a) do @qa). **Nenhuma mudança de código.**
>
> - **O motivo não é preferência, é impossibilidade.** `adherence_semantics.disclaimer_pt` do
>   contrato vendorizado é literalmente *"Aderência histórica não é habilitação, **capacidade**
>   nem recomendação…"* e contém a substring exata `capacidade`, que está em
>   `forbidden_conclusion_fields`. Esse disclaimer é **obrigatório** em `limitations` de todo
>   payload (§A.4 / AC6). Ler `FORBIDDEN_FIELDS` por substring sobre valores torna o AC5
>   **insatisfazível por construção**: todo bundle conforme falharia a própria verificação. Uma
>   das duas leituras é impossível; a outra é a implementada. Não é trade-off, é imposição do
>   contrato.
> - **O que o contrato proíbe é a conclusão, não a palavra.** `forbidden_conclusion_fields` é
>   uma lista de **campos/valores de conclusão** — um valor que *seja* a conclusão. A palavra
>   dentro da frase que existe justamente para **negar** a conclusão é o oposto de uma violação.
> - **Correção de premissa (não repetir a leitura de que só há campos estruturados).** Existem
>   sim campos de **texto livre** no bundle: `objeto`, `orgao.nome` e `perfil.razao_social`. Eles
>   não são exceção esquecida — são campos `FACT` de **autoria de terceiros**, copiados verbatim
>   da fonte pública. Um `objeto` de edital plausivelmente contém "comprovação de capacidade
>   técnica". Varrê-los por substring produziria um dos dois desfechos, ambos piores que o risco
>   latente: (i) fail-closed sobre dado público legítimo, negando publicação por causa da prosa
>   do órgão licitante; ou (ii) a tentação de **sanear um campo `FACT`**, que é violação de
>   contrato mais grave do que a que se pretendia evitar.
> - **Risco residual aceito, com tripwire explícito.** O caso do @qa (`"recomendacao: forte"`
>   como valor) não é alcançável hoje: nenhum caminho do produtor emite valor de conclusão, e
>   todo campo de autoria **nossa** é estruturado ou enumerado. **Se algum campo de texto livre
>   de autoria própria (resumo gerado, rótulo redigido, nota editorial) for algum dia adicionado
>   a um payload, esta decisão é reaberta** — a condição de reabertura é essa, não a passagem do
>   tempo.
> - `FORBIDDEN_STRINGS` (jargão interno: `extra-cli`, `SmartLic`, …) permanece por **substring**
>   sobre o bundle serializado, e deve permanecer: o contrato as trata como
>   `forbidden_public_language` — proibição de **aparecer**, não de ser o valor. Ressalva
>   honesta: não há caminho **conhecido** em que apareçam em prosa de terceiros, mas `SmartLic` é
>   nome de produto e um `objeto` de edital que descreva a contratação desse sistema abortaria o
>   export. É comportamento **herdado**, verificado verde pelo @qa, e não é reaberto aqui; se o
>   caso se materializar, a correção é allowlist de ocorrência em campo `FACT` de terceiros, não
>   afrouxar a lista.

**AC6 — Nenhum CNPJ bruto/mascarado de empresa/estabelecimento no bundle público [§A.3, §A.4, §B]**
- Given qualquer arquivo de `companies/*.json`
  When inspecionado
  Then não contém `company_root8`, `company_ref`, nem nenhum CNPJ de fornecedor/estabelecimento
  em formato cru ou mascarado — apenas `company_digest` (§B.1) identifica a empresa.
- Given qualquer arquivo de `companies/*.json` (payload `company-fit-profile/1.0`)
  When inspecionado por regex de 14 dígitos consecutivos e por padrão de CNPJ mascarado sobre o
  **JSON serializado**
  Then **nenhum CNPJ cru ou mascarado de qualquer entidade** aparece — nem da empresa-alvo, nem de
  terceiros. Isso inclui `compradores`: o campo passa a ser
  `[{ "buyer_digest": "<16 hex>" }, …]`, ordenado lexicograficamente por `buyer_digest`, **nunca**
  CNPJ [§A.4.1]. Motivo: `producer_contracts.company_fit_profile.identity` declara
  `raw_cnpj_in_payload: false` com a nota **sem qualificação** *"The payload never carries a raw
  CNPJ"*, e esse bloco governa exatamente este payload.
- Given `buyer_digest`
  When calculado
  Then usa **a mesma função** de `company_digest` (`identity.cnpj_digest`, §B.1):
  `sha256("confenge-conversion|" + cnpj14).hexdigest()[:16]`. Nenhum segundo esquema de identidade.
- Given um `buyer_cnpj` com número de dígitos ≠ 14 (possível: `producer.py:297-298` extrai dígitos
  **sem validar comprimento**, e `normalizeCnpj` do consumidor devolve `""` para qualquer coisa
  ≠ 14)
  When `companies/*.json` é gerado
  Then esse comprador é **omitido** de `compradores`, soma em `manifest.coverage.buyers_unhashable` e emite
  o reason code interno `buyer_cnpj_not_hashable` no payload da company. Emitir
  `buyer_digest: ""` é **proibido** — string vazia como identidade é descarte silencioso.
- Given a mudança acima
  When a suíte de fit roda
  Then **nenhum resultado de fit muda**: `fit.py:154-161` (`_dim_comparable_buyer`) compara
  `opportunity.orgao_cnpj in company.observed_buyer_cnpjs`, ou seja, o campo **interno** da
  `LiveCompany`, a montante da projeção pública. `observed_buyer_cnpjs` permanece intacto na
  dataclass e em `COMPANY_PAYLOAD_KEYS`/`portfolio_hash()` — logo `schema_hash()` **não** muda por
  causa desta decisão (só pelo `observed_establishment_cnpjs`, AC8/§B.3). Teste de não-regressão
  de `dim_comparable_buyer` é obrigatório.
- Given `orgao.cnpj` (comprador público) em `opportunities/*.json`
  When inspecionado
  Then **permanece no payload** [§A.3.1]. A assimetria com `companies/*.json` é **do contrato**:
  `producer_contracts.live_opportunity` **não possui bloco `identity`**, `orgao` está em seus
  `payload_fields`, e CNPJ de órgão público licitante é dado oficial publicado na fonte (PNCP).
  Registrado também em `docs/contracts/confenge-live-intelligence-v1.md` §1 para não virar
  ambiguidade futura. Existe uma flag de supressão de `orgao.cnpj` em `public_policy.py`,
  **desligada por padrão** (rollback barato caso o consumidor passe a exigir); ela **não** cobre
  `compradores`, que já não carrega CNPJ.
- Given que, dentro de um mesmo bundle, um `buyer_digest` é reversível por força bruta sobre os
  `orgao.cnpj` das `opportunities/*.json`
  When isso for levantado em QA
  Then é **efeito aceito e declarado**, não defeito: são entidades públicas, e a correlação é o que
  permite ao consumidor exibir "você já atendeu este órgão". A proteção que o contrato exige é
  sobre o CNPJ do **visitante**, e essa permanece absoluta.

**AC7 — `company_digest` bate byte-a-byte com `hashCnpj` do web-cfg [§B.1]**
- Given um CNPJ de estabelecimento de 14 dígitos conhecido
  When `identity.py` calcula `company_digest`
  Then o resultado é `sha256("confenge-conversion|" + cnpj14).hexdigest()[:16]` — provado contra
  vetores fixos (CNPJ conhecido → digest esperado copiado da reimplementação do
  `cnpj.cjs hashCnpj`), nunca `assert hash == hash`.
- Given uma empresa com raiz + N filiais observadas (`observed_establishment_cnpjs`)
  When exportada
  Then N arquivos `companies/<digest>.json` são emitidos, um por CNPJ de estabelecimento
  observado, todos com o mesmo `perfil`/`categorias`/`faixas`/etc. e `company_digest` distinto
  por arquivo.

**AC8 — `company_ref` interno, nunca no payload público [§B.2, §B.3]**
- Given `LiveCompany.company_ref()` (método, não campo — `LiveCompany` é `@dataclass(frozen=True)`)
  When chamado
  Then retorna `"cref1:" + sha256("confenge-live-intelligence|company_ref|v1|" + company_root8).hexdigest()[:32]`.
- Given qualquer arquivo público (`opportunities/*.json`, `companies/*.json`, `manifest.json`)
  When inspecionado
  Then `company_ref` nunca aparece — uso restrito a coluna interna (migration 105),
  `subject_key` de evento de empresa, e artefato de auditoria interno
  (`artifacts/.../li-audit.json`).
- Given uma company `ROW_COMPLETE` cujo CNPJ de filial nunca apareceu em contrato observado (ou
  tem dígito verificador inválido a montante, ficando NULL em `fornecedor_cnpj`)
  When `project_companies` roda
  Then essa filial não gera digest (miss fail-closed), e a company ainda assim produz **pelo
  menos um** digest de estabelecimento a partir de outro CNPJ observado — asserção obrigatória
  de §B.3. Se por algum motivo uma company `ROW_COMPLETE` chegar a zero digests, o export levanta
  erro (não emite silenciosamente uma company invisível sem arquivo e sem reason_code), e
  `manifest.reason_codes` inclui `establishment_cnpj_not_observed` quando aplicável.

**AC9 — `event_id` determinístico, replay idempotente [§C.1, §C.3]**
- Given `event_type`, `subject_key`, `prev_semantic_hash`, `semantic_hash` de uma transição
  When `event_id` é calculado
  Then `event_id = live_hash({"event_type":..., "subject_key":..., "prev_semantic_hash":...,
  "semantic_hash":...})` — exatamente a tupla de `uq_live_intel_event_transition`
  (`104:471-472`), sem incluir `snapshot_id`, `source_as_of` nem `created_at`. O resultado
  satisfaz `event_id ~ '^[0-9a-f]{64}$'` (CHECK do PK, `104:446`) e
  `chk_live_intel_event_is_transition` (`prev_semantic_hash <> semantic_hash`, `104:464`).
- Given um par de snapshots base→corrente processado duas vezes (replay)
  When `events.py` roda
  Then o mesmo conjunto de `event_id` é produzido byte a byte nas duas rodadas, e a persistência
  usa `ON CONFLICT (event_id) DO NOTHING` (idempotência sem duplicar).
- Given `NEW_OPPORTUNITY`
  When a oportunidade é nova no snapshot base
  Then `prev_semantic_hash=""` e `prev_snapshot_id=NULL` (bootstrap, satisfaz
  `chk_live_intel_event_bootstrap`, `104:466-469`).
- Given `OPPORTUNITY_CHANGED`/`DEADLINE_CHANGED`
  When a projeção semântica (`OPPORTUNITY_CORE`/`DEADLINE_CORE`, ver Dev Notes) muda entre
  snapshot base e corrente
  Then o evento é emitido; se `source_as_of`, `valor_estimado_brl`, `link_edital`, `reason_codes`
  ou qualquer hash mudarem sozinhos (sem mudança na projeção semântica), **nenhum** evento é
  emitido — churn de watermark/centavos não gera evento.
- Given `FIT_BECAME_RELEVANT`
  When um fit transiciona **para** `fit_state == OBSERVED_FIT`
  Then o evento é emitido com `subject_key = "company:<company_ref>"` (não `company_digest` —
  o `company_ref` interno é 1:1 com a empresa; `company_digest` fragmentaria o evento em N
  linhas por filial). Downgrade de fit (`OBSERVED_FIT` → outro estado) **não** emite evento
  nesta story (declarado, não é bug).
- Given `COMPANY_PORTFOLIO_CHANGED`
  Then esta story **não emite** esse tipo de evento (existe no CHECK da 104 mas o critério de
  materialidade depende do ciclo de crawl outbound, fora de escopo).

**AC10 — Prova de equivalência outbound contra DB isolado, TD-LI-6 [§E]**
- Given a database `extra_li_equiv` criada via `CREATE DATABASE extra_li_equiv TEMPLATE template0;`
  no mesmo cluster (`127.0.0.1:5433`), migrations aplicadas até a 105 inclusive, e seed
  determinístico com raiz + filial do mesmo CNPJ-8
  When `build_snapshot(..., persist=True)` roda contra esse DSN isolado
  Then a captura BEFORE/AFTER de conteúdo (`md5(string_agg(t::text, '|' ORDER BY t::text))` +
  `count(*)` por `pncp_raw_bids`, `pncp_supplier_contracts`, `contract_role_links`,
  `sc_public_entities`) é idêntica, **e** o delta de `n_tup_ins/n_tup_upd/n_tup_del` de
  `pg_stat_all_tables` (após `pg_stat_clear_snapshot()`) é zero para todo objeto fora de
  `ALLOWED_WRITE_TARGETS`.
- Given o mesmo DSN isolado
  When o build roda sob o role **dedicado `li_equiv_runner`** — criado e destruído
  exclusivamente por `scripts/ops/li_equiv_db.py` (Task 10), **nunca** por migration — com apenas
  `SELECT` nos objetos outbound e DML só nas tabelas de `WRITE_TARGET_ORDER`
  Then qualquer DML outbound falharia por permissão — reforço estrutural, não só asserção de
  teste.
  > **Adjudicação do @architect no gate sistêmico (2026-09-03), item (i) do @data-engineer.**
  > A redação anterior deste bullet (*"sob o role `confenge_live_intel_reader` (estendido da
  > 104)"*) está **revogada** e é incorreta. `confenge_live_intel_reader` é role de **leitura** e
  > vive em todo database que aplicar a 104/105, produção inclusive: conceder-lhe DML alargaria
  > permissão em produção para satisfazer um teste local — contradição direta com o próprio AC10.
  > O role de escrita da prova de equivalência é **outro role, com outro nome**, provisionado fora
  > do escopo das migrations 104/105. Ver Task 10 para o dono, o ciclo de vida e a derivação dos
  > grants.
- Given `test_blocked_when_watermark_is_missing` (existente em
  `tests/confenge_live_intelligence/test_producer_state_criteria.py:197-217`)
  When esse teste roda contra `extra_li_equiv` em vez do DSN de teste compartilhado
  Then passa deterministicamente **sem** alterar as asserções originais (`result.state ==
  SNAPSHOT_BLOCKED`, `BLOCKER_WATERMARK_MISSING in result.blockers`) e **sem** ampliar o escopo
  do `DELETE FROM public.pncp_raw_bids WHERE pncp_id LIKE 'LI-TEST-%'` (`conftest.py:23`,
  `SEED_PREFIX = "LI-TEST-"`) — a correção do não-determinismo é isolamento de banco
  (`extra_li_equiv` via `make li-equiv`), não relaxamento de assert nem prefixo mais amplo.

**AC11 — `contract_version` fixo em `1.0`, `SCHEMA_VERSION`/`ENGINE_VERSION` em `1.1` [§D, §B.3]**
- Given qualquer bundle exportado
  When `manifest.json` é inspecionado
  Then `contract_version == "1.0"` sempre (o contrato público não muda), independente de
  `schema.SCHEMA_VERSION` ter avançado para `"confenge-live-intelligence-schema/1.1"` e
  `ENGINE_VERSION` para `"1.1"` internamente — as duas linhas de versão são independentes por
  desenho.
- **Nota anti-"correção" [§D]:** o contrato se autodeclara `contract_version: "v1.0.0"` no topo.
  A divergência com o `"1.0"` que emitimos é **tolerada por construção**: `accepted_versions` das
  **duas** famílias é `["1.0", "v1.0.0"]`, logo `contract_version_unsupported` não pode disparar.
  Não trocar `"1.0"` por `"v1.0.0"` — é churn com risco e zero ganho.

## Fora de escopo (Escopo OUT — explícito)

- Merge do PR #538/companion; aplicação da migration `105` em produção; instalação de timer/cron
  na VPS. Fase de publicação, posterior e separada.
- Qualquer alteração em `targeting`, `CLAIM_POLICY`, fila (`queue_counts()`) ou cadência do
  outbound.
- **Emissão de `SUPERSEDED`** (REL-004, dívida absorvida pela story
  `story-confenge-live-intelligence-outbound-equivalence-gate.md`, exige adjudicação prévia do
  @architect sobre a máquina de estados — só se materializa na operacionalização do motor).
- **Endurecimento do regex `MUTATING`** em `tests/test_live_intelligence_outbound_equivalence.py:54`
  (AR-4, absorvida pela mesma story irmã) — não confundir com o novo
  `tests/confenge_live_intelligence/test_outbound_equivalence.py` desta story (§F), que é
  instrumento diferente para uma proposição diferente (ver abaixo).
- O "protocolo de dois braços" completo (Banco A ≤102 vs Banco B ≤104+, `run_pipeline()` real,
  comparação de `queue_counts()`/payload do warmbly/veredito de `send_readiness.py`) — isso é o
  Escopo IN da story irmã, não desta. Rodar `run_pipeline()` tocaria fila/outreach, que está
  fora do escopo desta story por definição.

## Relação com a story de equivalência de dois braços (não sobreposição)

A story `story-confenge-live-intelligence-outbound-equivalence-gate.md` (Draft) prova uma
proposição diferente da desta story: *a presença do motor não muda as saídas outbound do
pipeline real* (`run_pipeline()` completo, dois bancos, comparação de artefatos de fila/outreach).
O AC10 desta story (§E do documento de arquitetura) prova algo mais estreito: *rodar
`build_snapshot`/export não escreve em nenhuma tabela outbound* (digest de conteúdo + delta de
`pg_stat_all_tables` + role restrito a `SELECT`). Os dois instrumentos compartilham apenas a
necessidade de um banco isolado — que é exatamente o insumo que TD-LI-6 precisa.

**Declaração para o @po resolver na validação (`*validate-story-draft`):** a tabela de débitos da
story irmã (v1.1) já lista TD-LI-6 como absorvido por ela, com o argumento de que o "2º DSN"
provisionado por @devops para o protocolo de dois braços resolveria TD-LI-6 como efeito
colateral. Esta story (`W2`) cria e usa `extra_li_equiv` no cluster de teste local via
`scripts/ops/li_equiv_db.py`/`make li-equiv` — isso pode discharge, como efeito colateral, a
dependência bloqueante "@devops provisiona 2º DSN" da story irmã, mas essa é uma leitura desta
story (@sm), não uma reivindicação: **@po precisa reconciliar as duas tabelas de débito** para
que TD-LI-6 não apareça como "resolvido" em dois lugares com dois donos diferentes. Nenhuma
edição foi feita na story irmã — fora de autoridade do @sm.

> **Adjudicação do @po (2026-09-03, `*validate-next-story`).** Duas decisões, ambas já aplicadas
> à tabela de débitos da story irmã (v1.2), sem tocar em nenhum AC, escopo ou `closure-key` dela:
>
> 1. **TD-LI-6 é de titularidade desta story (W2), especificamente do AC10.** Motivo: o AC10 traz
>    um critério de fechamento concreto e testável (`extra_li_equiv`, `make li-equiv`, reexecução
>    de `test_blocked_when_watermark_is_missing` com asserções originais intactas e sem ampliar o
>    `DELETE ... LIKE 'LI-TEST-%'`), enquanto a absorção na story irmã era especulativa
>    ("resolveria como efeito colateral"). A titularidade está fixada ao **AC10**, não à story em
>    abstrato: se o AC10 cair num reescopo, TD-LI-6 vira dívida sem portador e precisa ser
>    reatribuído explicitamente — não retorna à story irmã por default.
> 2. **A leitura do @sm sobre discharge do 2º DSN é REJEITADA.** `extra_li_equiv` é **um** banco
>    em nível de migration ≤105. O protocolo de dois braços da story irmã exige **dois** bancos em
>    níveis **distintos** (Banco A ≤102, Banco B ≤104+). A dependência bloqueante "@devops
>    provisiona 2º DSN" da story irmã permanece **intacta**, e esta story não a descarrega.

## Tasks / Subtasks

- [x] Task 1 — Migration 105 (@data-engineer → @architect) (AC8, AC9, AC11)
  - [x] `db/migrations/105_confenge_live_intelligence_company_ref.sql`: colunas aditivas
    `company_ref` e `observed_establishment_cnpjs` em `confenge_live_intelligence_companies`
    (ou tabela equivalente), + índice. Zero DML outbound, zero alteração de coluna existente.
  - [x] Confirmar `REVOKE`/grants idênticos ao padrão da 104 para as colunas novas.
  - [x] Rodar `apply_migrations` contra `extra_test` local e confirmar idempotência (`IF NOT
    EXISTS`).
  - [x] `db/rollback/105_confenge_live_intelligence_company_ref_rollback.sql` (espelha o padrão
    da 104), executado e reaplicado contra `extra_test` — ciclo aplicar → reverter → reaplicar
    sem resíduo de catálogo.

  > **Entrega do @data-engineer (Dara, 2026-09-03).** Validado contra PostgreSQL 16.15 real
  > (`extra-test-db`, `postgresql://test:test@127.0.0.1:5433/extra_test`), não apenas por leitura
  > de SQL. Provado: colunas com tipo/nulidade esperados; `pg_attribute.attacl IS NULL` nas duas
  > colunas novas (nenhum grant de coluna — a 104 também não tem); `pg_class.relacl` da tabela
  > **idêntico** antes/depois (`{test=arwdDxt/test,confenge_live_intel_reader=r/test}`);
  > `pg_default_acl` em `public` continua com 0 linhas; nenhuma coluna pré-105 alterada;
  > reexecução do arquivo pelo mesmo parser de `apply_migrations` é no-op; os dois `CHECK`
  > exercitados por INSERT real (9 casos, transação revertida — `extra_test` continua com 0
  > snapshots); rollback remove índice/CHECKs/colunas, é idempotente e permite reaplicar a 105.
  > Varredura estática de aditividade (mesmo instrumento de
  > `tests/test_live_intelligence_outbound_equivalence.py`) sobre os 10 statements da migration e
  > os 7 do rollback: **zero** objeto outbound alcançado por statement mutante ou DML.
  >
  > **Dois itens ficam para adjudicação do @architect no gate sistêmico (não são omissão):**
  > (i) a extensão do role `confenge_live_intel_reader` com `INSERT/DELETE` nas
  > `confenge_live_intelligence_*` exigida pelo **AC10** **não** entra na 105 — concedê-la aqui
  > alargaria o role em todo database que aplicar a migration, inclusive produção, contradizendo
  > o próprio AC10 (role de leitura). Ela pertence ao banco isolado `extra_li_equiv`
  > (Task 10, `scripts/ops/li_equiv_db.py`), e hoje está sem dono explícito na story;
  > (ii) `tests/test_live_intelligence_outbound_equivalence.py` e
  > `tests/confenge_live_intelligence/test_migration_grants_and_rollback.py` apontam **apenas**
  > para a 104 — estender a parametrização deles para a 105 é escopo do @dev na Task 11.

- [x] Task 2 — `schema.py`: `observed_establishment_cnpjs` + `company_ref()` (AC7, AC8, AC11)
  - [x] Adicionar `observed_establishment_cnpjs: tuple[str, ...]` a `LiveCompany` (sorted set de
    CNPJ14 de `supplier_cnpj`, mesmo laço que produz `observed_buyer_cnpjs`, `producer.py:297-299`).
  - [x] Adicionar `company_ref()` como **método** ao lado de `portfolio_hash()` — NUNCA como
    campo (evita `FrozenInstanceError`, evita contaminar `COMPANY_PAYLOAD_KEYS`/`portfolio_hash()`).
  - [x] Bump `SCHEMA_VERSION` → `"confenge-live-intelligence-schema/1.1"`, `ENGINE_VERSION` →
    `"1.1"`.
  - [x] Confirmar em `LiveCompanyOpportunityFit` que `company_ref` é derivado do mesmo método a
    partir de `company_root8` (sem campo novo na dataclass de fit).

- [x] Task 3 — `identity.py`: `cnpj_digest` + `company_ref` (AC6, AC7, AC8)
  - [x] `cnpj_digest(cnpj: str) -> str | None`:
    `sha256("confenge-conversion|" + cnpj14).hexdigest()[:16]`; devolve `None` (**nunca `""`**)
    quando a entrada não tem exatamente 14 dígitos. **Função única**, usada tanto para
    `company_digest` quanto para `buyer_digest` (AC6) — proibido criar um segundo esquema.
  - [x] `company_ref_from_root8(company_root8: str) -> str`:
    `"cref1:" + sha256("confenge-live-intelligence|company_ref|v1|" + company_root8).hexdigest()[:32]`.
  - [x] Vetores fixos de teste (CNPJ conhecido → digest esperado). Referência congelada da função
    do consumidor: `docs/contracts/confenge-live-intelligence-v1.md` (blobs `8b88a894e` /
    `1a5452a2d` de `scripts/conversion/cnpj.cjs`).

- [x] Task 4 — `producer.py`: coleta e persistência (AC7, AC8)
  - [x] Coletar `observed_establishment_cnpjs` no laço existente de `project_companies`.
  - [x] Persistir `company_ref` (via método) e `observed_establishment_cnpjs` nas colunas novas
    da 105.
  - [x] Asserção: toda company `ROW_COMPLETE` produz ≥1 digest de estabelecimento; erro explícito
    se zero (não invisibilidade silenciosa).
  - [x] Encadear geração de eventos (`events.py`) logo após selar o snapshot.

- [x] Task 5 — `public_policy.py`: mapas de enum, epistemic classes, disclaimer, listas
  proibidas (AC1, AC5, AC6)
  - [x] Mapas de A.1 (`SNAPSHOT_READY→DATA_READY`, `SNAPSHOT_PARTIAL→DATA_HOLD`,
    `SNAPSHOT_BLOCKED→DATA_REJECT`, `DEADLINE_OPEN→ABERTA`, `DEADLINE_CLOSED→ENCERRADA`,
    `UNKNOWN→UNKNOWN`; `SUSPENSA` nunca emitido, registrado em `limitations`).
  - [x] Constante `FORBIDDEN_FIELDS` (habilitado, elegivel, capacidade, recomendacao, vencedor,
    probabilidade_vitoria, should_bid, `INDEX` como valor de enum).
  - [x] Constante `FORBIDDEN_STRINGS` (extra-cli, scripts.public_read, scripts.live_intelligence,
    SmartLic).
  - [x] Flag de supressão (desligada por padrão) para `orgao.cnpj` **somente** — `compradores` já
    não carrega CNPJ (AC6/§A.4.1), então não há o que suprimir ali.
  - [x] `disclaimer_pt` de §A.4 ("Aderência histórica não é habilitação...").

- [x] Task 6 — `export.py`: monta o bundle a partir do snapshot selado (AC1, AC2, AC3, AC4, AC6)
  - [x] `manifest.json` conforme §A.2 (campos, `manifest_hash = live_hash(manifest sem
    manifest_hash)`, docstring explícito sobre não-reprodutibilidade de `generated_at`/
    `freshness`/`manifest_hash` em replay).
  - [x] `opportunities/<opportunity_id>.json` conforme tabela §A.3 (incluindo `content_hash =
    live_hash(payload público sem content_hash)`, distinto de
    `LiveOpportunity.content_hash()`).
  - [x] `companies/<company_digest>.json` conforme tabela §A.4, um arquivo por digest de
    estabelecimento observado, com `compradores = [{buyer_digest}]` (sem CNPJ cru, AC6) e o
    caminho fail-closed de comprador não-hasheável (`manifest.coverage.buyers_unhashable` +
    `buyer_cnpj_not_hashable`).
  - [x] `manifest.index` como conjunto exato de arquivos emitidos, cada entrada com
    `{..., file, schema, content_hash}`; linhas excluídas só em `coverage.*_excluded`.
  - [x] Chave de envelope `schema` no manifest (**não** `contract`, sem alias) e `schema` de
    família em cada payload (AC1).
  - [x] Export nunca chama `datetime.now()`; nunca lê `v_contracts_canonical_v2`.

- [x] Task 7 — `events.py`: diff, projeções semânticas, `event_id`, persistência (AC9)
  - [x] `OPPORTUNITY_CORE`, `DEADLINE_CORE`, `FIT_CORE` conforme tabela §C.2.
  - [x] `event_id = live_hash({event_type, subject_key, prev_semantic_hash, semantic_hash})`.
  - [x] `ON CONFLICT (event_id) DO NOTHING`.
  - [x] `NEW_OPPORTUNITY`, `OPPORTUNITY_CHANGED`, `DEADLINE_CHANGED`, `FIT_BECAME_RELEVANT` —
    critérios de emissão exatos de §C.2. `COMPANY_PORTFOLIO_CHANGED` não emitido.

- [x] Task 8 — `verifier.py`: prova do bundle serializado (AC5, AC6)
  - [x] Verificação roda sobre o JSON serializado em disco, não sobre o dict Python.
  - [x] Confere `FORBIDDEN_FIELDS`, `FORBIDDEN_STRINGS` e hashes recomputáveis.
  - [x] Confere **ausência de qualquer CNPJ cru ou mascarado em `companies/*.json`** — empresa,
    estabelecimento **e** comprador (AC6). Em `opportunities/*.json`, `orgao.cnpj` é esperado e
    não é violação.

- [x] Task 9 — `cli.py`: subcomandos `export` e `events` (suporte às tasks 6/7)

- [x] Task 10 — `scripts/ops/li_equiv_db.py` + `Makefile` `li-equiv` + fixture (AC10)
  - [x] Cria `extra_li_equiv` (`TEMPLATE template0`), aplica migrations até 105, roda seed
    determinístico (`fixtures/confenge_live_intelligence/equivalence_seed.sql`, raiz + filial do
    mesmo CNPJ-8 **e** ao menos um `buyer_cnpj` com ≠ 14 dígitos para exercitar AC6),
    derruba ao final (`DROP DATABASE`).
  - [x] **Role dedicado `li_equiv_runner` — `scripts/ops/li_equiv_db.py` é o dono único.**

  > **Adjudicação do @architect no gate sistêmico (2026-09-03) — fecha o item (i) deixado em
  > aberto pelo @data-engineer na entrega da Task 1.** O provisionamento do role de escrita de
  > `extra_li_equiv` tem dono explícito a partir daqui: `scripts/ops/li_equiv_db.py`, **fora do
  > escopo das migrations 104/105**. Nenhuma migration ganha `GRANT INSERT/DELETE`.
  >
  > **Fato de Postgres que dita o desenho: `CREATE ROLE` é cluster-global, não por database.**
  > "Role local do `extra_li_equiv`" não existe; o que é por-database são os **grants**. Daí,
  > sem liberdade de escolha:
  >
  > 1. **Nome distinto e não colidente: `li_equiv_runner`.** Reusar ou estender
  >    `confenge_live_intel_reader` é **proibido** — ele é cluster-global e o alargamento valeria
  >    em `extra_test` e em produção.
  > 2. **Criado só pelo script, só no cluster de teste local.** `CREATE ROLE li_equiv_runner
  >    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT` (com `LOGIN` + senha efêmera se o build
  >    precisar de DSN próprio) e `GRANT CONNECT ON DATABASE extra_li_equiv`. Nenhum grant em
  >    nenhum outro database.
  > 3. **Grants derivados de `schema.WRITE_TARGET_ORDER`, importado por nome — nunca uma segunda
  >    lista literal dentro do script.** `SELECT, INSERT, UPDATE, DELETE` + `USAGE` nas sequences
  >    dessas tabelas; `SELECT` e **nada mais** em qualquer objeto outbound. Motivo: lista
  >    paralela mantida à mão é uma segunda allowlist — exatamente o defeito que o comentário de
  >    `WRITE_TARGET_ORDER` (`schema.py:40-46`, AR-2/ADR-040) já rejeitou. Enumerar "só
  >    INSERT/DELETE" por palpite também quebraria o persist, que faz `UPDATE`.
  > 4. **Guarda fail-closed na entrada do script:** aborta se o dbname do DSN ≠ `extra_li_equiv`
  >    ou se o host não for loopback (`127.0.0.1`/`localhost`). O script nunca pode ser apontado
  >    para `extra_test` nem para produção por engano de variável de ambiente.
  > 5. **Teardown obrigatório e idempotente:** `DROP OWNED BY li_equiv_runner` (dentro de
  >    `extra_li_equiv`) → `DROP DATABASE extra_li_equiv` → `DROP ROLE IF EXISTS li_equiv_runner`.
  >    Role vazado é resíduo de catálogo **cluster-global**. Precisão para o @dev não tratar isso
  >    como opcional: `test_rollback_removes_every_object_and_reapply_is_clean`
  >    (`tests/confenge_live_intelligence/test_migration_grants_and_rollback.py:290`) compara o
  >    **conjunto inteiro** de `pg_roles` antes/depois **dentro da mesma execução** — um role já
  >    vazado antes não a quebra retroativamente, mas um vazamento **concorrente** quebra, e o
  >    ruído cai sobre um teste que nada tem a ver com esta story.
  > 6. **`li_equiv_db.py` nunca escreve em `extra_test` nem em produção**, e não entra em nenhum
  >    caminho de deploy — é ferramenta de teste local.

- [x] Task 11 — Testes (AC1–AC11)
  - [x] `tests/confenge_live_intelligence/test_identity.py` — vetores fixos de `cnpj_digest`
    (serve `company_digest` e `buyer_digest`); vetor negativo (≠ 14 dígitos → `None`, nunca `""`);
    N digests → 1 `company_ref`; miss fail-closed.
  - [x] Não-regressão de `dim_comparable_buyer` (AC6): a mudança de `compradores` é só na projeção
    pública; `fit.py:154-161` lê `observed_buyer_cnpjs` interno e nenhum resultado de fit muda.
  - [x] `tests/confenge_live_intelligence/test_events.py` — replay determinístico; ausência de
    churn por `as_of`/watermark/centavos; bootstrap `prev_semantic_hash=""`.
  - [x] `tests/confenge_live_intelligence/test_export_contract.py` — roda contra o contrato
    **vendorizado** (`docs/contracts/confenge-live-intelligence-v1.json`), nunca contra rede ou
    `.campaign/`: key-set exato de cada payload == `payload_fields` da família **∪ `{"schema"}`**
    (o contrato traz 15 `payload_fields` em `live_opportunity` e 17 em `company_fit_profile`, e
    **`schema` não está em nenhuma das duas listas** — é chave de envelope aditiva, permitida por
    `compatibility: additive_nullable_within_v1` e exigida por `schema_absent` ∈
    `reject_reason_codes`; asserção de igualdade crua contra `payload_fields` falharia);
    `schema` no manifest, em
    cada payload e em cada entrada de `index`; **ausência da chave `contract`** no manifest;
    ausência de CNPJ cru/mascarado em `companies/*.json`; **disjunção** entre os `reason_codes`
    emitidos e os 14 códigos do contrato; campos/linguagem proibidos sobre o bundle serializado;
    `content_hash` recomputável; `manifest.index` == conjunto de arquivos emitidos.
  - [x] `tests/confenge_live_intelligence/test_outbound_equivalence.py` — prova de AC10 contra
    `extra_li_equiv`.
  - [x] Rodar `test_blocked_when_watermark_is_missing` (arquivo existente) contra `extra_li_equiv`
    sem alterar suas asserções nem o prefixo `LI-TEST-` do DELETE.
  - [x] **Fronteira e concordância de `freshness` (AC3, emenda do gate):** 48h exatas → `FRESH`;
    48h + 1s → `STALE`; bloco `freshness` idêntico (igualdade de dict) entre `manifest.json` e
    **todo** payload; `source_as_of` do bloco == `min` dos payloads emitidos; `state` recomputado
    a partir das strings serializadas bate com o emitido; `source_as_of_beyond_max_age` e
    `source_as_of_after_generated_at` disjuntos dos 14 códigos do contrato. Estas asserções vivem
    em `test_export_contract.py` — não criar arquivo novo para elas.
  - [x] **Estabilidade de `content_hash` (AC4, esclarecimento do gate):** dois exports do mesmo
    snapshot **sem re-persist** → `content_hash` idêntico por arquivo. **Proibido** escrever
    asserção de estabilidade **através** de re-persist.
  - [x] **Parametrizar os dois testes estáticos/de catálogo existentes para incluir a 105 —
    NÃO criar arquivo de teste novo para a 105.**

  > **Adjudicação do @architect no gate sistêmico (2026-09-03) — fecha o item (ii) deixado em
  > aberto pelo @data-engineer.** Os dois arquivos abaixo hoje apontam **só** para a 104. A 105 é
  > coberta **estendendo-os**, porque são o instrumento canônico da proposição "nenhum statement
  > alcança objeto outbound" / "a barreira é feita só de REVOKE explícito". Um terceiro arquivo
  > para a 105 seria um segundo instrumento para a mesma proposição — a mesma classe de defeito
  > que a story já rejeita em identidade e em allowlist. **O que é proibido é arquivo novo
  > duplicado; funções de teste novas dentro desses dois arquivos são bem-vindas.**
  >
  > **`tests/test_live_intelligence_outbound_equivalence.py`** (estático, sem banco):
  > - `:32-33` — trocar as constantes `MIGRATION`/`ROLLBACK` por tuplas dos **quatro** caminhos
  >   (migrations 104 e 105 + os dois rollbacks correspondentes), com `ids` explícitos
  >   (`migration-104`, `rollback-104`, `migration-105`, `rollback-105`).
  > - `:74` e `:92` (`test_no_mutating_statement_touches_outbound_object`,
  >   `test_no_dml_over_outbound_object`) — já são `@pytest.mark.parametrize`: estender a lista
  >   para os quatro caminhos. Nenhuma asserção muda.
  > - `:104` e `:114` (`test_no_trigger_over_outbound_object`,
  >   `test_migration_does_not_create_dedicated_schema`) — hoje iteram só sobre `MIGRATION`:
  >   parametrizar sobre as **duas** migrations.
  > - `:69` (`test_migration_104_exists`) — parametrizar sobre os quatro caminhos (renomear para
  >   algo como `test_migration_files_exist`; renomear é aceitável, duplicar não).
  > - Nota de sanidade já verificada pelo @data-engineer: o único token mutante da 105 é
  >   `ALTER TABLE public.confenge_live_intelligence_companies`, tabela do próprio motor, ausente
  >   de `PROTECTED_OBJECTS` — a extensão deve passar sem tocar em `PROTECTED_OBJECTS` nem em
  >   `MUTATING`/`DML`. Se passar a exigir relaxamento de regex, **pare**: isso é sinal de defeito
  >   na migration, não no teste. (O endurecimento do regex `MUTATING`, AR-4, continua fora de
  >   escopo — é da story irmã.)
  >
  > **`tests/confenge_live_intelligence/test_migration_grants_and_rollback.py`** (`real_db`):
  > - `:34-35` — mesmas constantes viram tuplas ordenadas (104 → 105 para aplicar; 105 → 104 para
  >   reverter).
  > - `:229/:250` (`test_104_barrier_is_explicit_revokes_without_default_privileges`) —
  >   parametrizar sobre as duas migrations: nenhuma das duas emite `ALTER DEFAULT PRIVILEGES`.
  > - `:290` (`test_rollback_removes_every_object_and_reapply_is_clean`) — virar ciclo
  >   **empilhado**: aplicar 104+105 → rollback 105 → rollback 104 → checagem de resíduo (a que já
  >   existe) → reaplicar 104+105. As asserções atuais permanecem; muda a ordem dos arquivos.
  > - Adicionar (função nova, mesmo arquivo) as asserções de catálogo que o @data-engineer já
  >   provou manualmente na Task 1, para virarem guarda de regressão: `pg_attribute.attacl IS
  >   NULL` para `company_ref` e `observed_establishment_cnpjs`, e `pg_class.relacl` de
  >   `confenge_live_intelligence_companies` **idêntico** antes e depois da 105.

- [~] Task 12 — Quality gate (@dev, antes de "Ready for Review") — **PARCIAL** (só PRC-001 aberto)
  - [x] `ruff check` / `ruff format` **executados e limpos**; `mypy` **executado** —
    a redação original ("não instalado neste ambiente") foi superada: o @dev instalou `mypy`
    2.3.1 em venv isolado na correção do MNT-001 (Change Log v1.2.1) e o @qa **re-executou**
    de forma independente na rodada 2 (`mypy` 12 erros / 6 arquivos, delta −7 confirmado por
    conteúdo, `export.py` fora da lista). Dos 12 restantes, **5 são baseline pré-existente e
    fora de escopo** (`verifier.py:253/256/257/258`, `cli.py:38`) e **zero** é novo desta
    story após a adjudicação REQ-001 (v1.3). **Reconciliação do @po (2026-09-03)** — o
    subitem fecha; o `[~]` do pai permanece só por causa do CodeRabbit abaixo.
  - [ ] CodeRabbit self-healing — **NÃO executado**: a CLI existe
    (`~/.local/bin/coderabbit`) mas está **`signed out`** (`coderabbit auth status`), e
    autenticação exige credencial que esta sessão não possui. Não simulado. Item aberto para
    o @qa/@devops — pedir a credencial ou rodar o Pre-PR do @devops.

## 🤖 CodeRabbit Integration

### Story Type Analysis

**Primary Type**: Database
**Secondary Type(s)**: API (contrato público de exportação), Integration (paridade com web-cfg
`hashCnpj`)
**Complexity**: High — nova migration aditiva, mudança de `SCHEMA_VERSION`/`ENGINE_VERSION`,
contrato público consumido por sistema externo, prova de equivalência com role dedicado.

### Specialized Agent Assignment

**Primary Agents**:
- @dev (pre-commit reviews)
- @data-engineer (migration 105, colunas aditivas, grants/REVOKE)

**Supporting Agents**:
- @architect (mudança de `SCHEMA_VERSION`, contrato público, gate HIGH-RISK)
- @qa (verificação do contrato público, prova de equivalência)

### Quality Gate Tasks

- [ ] Pre-Commit (@dev): Rodar `coderabbit --prompt-only -t uncommitted` antes de marcar a story
  como completa.
- [ ] Pre-PR (@devops): Rodar `coderabbit --prompt-only --base main` antes de criar o PR.
- [ ] Pre-Deployment (@devops): não aplicável — aplicação da 105 em produção é Escopo OUT desta
  story.

### Self-Healing Configuration

**Expected Self-Healing**:
- Primary Agent: @dev (light mode)
- Max Iterations: 2
- Timeout: 15 minutos
- Severity Filter: CRITICAL

**Predicted Behavior**:
- CRITICAL issues: auto_fix (até 2 iterações)
- HIGH issues: document_only (registrado em Dev Notes como dívida)

### CodeRabbit Focus Areas

**Primary Focus**:
- Schema compliance: colunas aditivas da 105, sem alteração de coluna existente, grants/REVOKE
  simétricos à 104.
- Nenhum CNPJ de empresa/estabelecimento cru/mascarado escapando para `export.py`/`verifier.py`.

**Secondary Focus**:
- `company_ref` implementado como método, nunca como campo de dataclass frozen.
- Determinismo de `event_id`/`content_hash` — nenhuma dependência de `datetime.now()` fora dos
  pontos já documentados (`producer.py:560-566`).

## Dev Notes

### Contexto herdado da story-01

O motor v1 (`schema.py`, `producer.py`, `fit.py`, `sources.py`, migration `104`) já está
mergeado (`64c04a43`). A tabela `confenge_live_intelligence_events` nasce vazia na 104 — esta
story é quem primeiro escreve nela (comentário da 104: *"Nasce vazia na 104; LI-7 popula"*).

### Layout do bundle — tabelas normativas inlineadas

> Estas quatro tabelas são a cópia literal de §A.2/§A.3/§A.4/§C.2 de
> `docs/architecture/confenge-live-intelligence-w2-decisions.md` v1.1. Estão aqui porque o @dev
> implementa a partir da story, não do documento. Se divergirem, é defeito a adjudicar com o
> @architect.

#### Mapeamento de enum público [§A.1]

| Interno (`schema.py`) | Público (contrato) | Nota |
|---|---|---|
| `SNAPSHOT_READY` (`READY_CANONICAL`) | `DATA_READY` | não é permissão de indexação |
| `SNAPSHOT_PARTIAL` | `DATA_HOLD` | bundle emitido, com `limitations` |
| `SNAPSHOT_BLOCKED` | `DATA_REJECT` | só `manifest.json` |
| `SNAPSHOT_BUILDING`, `SNAPSHOT_SUPERSEDED` | — | não exportáveis, fail-closed |
| `DEADLINE_OPEN` | `ABERTA` | |
| `DEADLINE_CLOSED` | `ENCERRADA` | |
| `UNKNOWN` | `UNKNOWN` | |
| — | `SUSPENSA` | **nunca emitido** (nenhuma fonte no producer); registrar em `limitations` |

`INDEX`/`PUBLISHABLE_*` nunca aparecem — decisão editorial é do consumidor.

#### `manifest.json` [§A.2]

```
schema            "CONFENGE_LIVE_INTELLIGENCE/1.0"     literal (NÃO "contract" — AC1)
contract_version  "1.0"                                 AC11
catalog_mode      "fixture" | "official_live"           PARÂMETRO do export, default "fixture"
official_live     catalog_mode == "official_live"       derivado; nunca literal (emenda do AC1)
producer_status   == catalog_mode                       "official_live" evita
                                                        producer_status_not_official_live;
                                                        "fixture" faz o consumidor recusar — que
                                                        é o efeito desejado num bundle de teste
as_of             snapshots.as_of_date
generated_at      snapshots.cutoff_at (UTC, ISO8601)    valor declarado, nunca datetime.now()
source_as_of      min(source_as_of) sobre os payloads emitidos (watermark UTC) — pior caso
freshness         {max_age_hours:48, generated_at, source_as_of, state:"FRESH"|"STALE"}
                  bloco computado UMA vez e copiado verbatim para cada payload;
                  derivação pinada no AC3 (emenda do gate sistêmico) — não improvisar
data_state        mapa acima
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

**Fora do bundle público, sem exceção:** `snapshot_id`, `universe_hash`, `policy_hash`,
`schema_hash`, `data_hash`, `fit_hash`, `company_ref`, `company_root8`. Vão para
`artifacts/.../li-audit.json` interno.

**Invariante do conjunto de arquivos [§A.2.2]:** `manifest.index` é **exatamente** o conjunto de
arquivos emitidos. Linhas com `row_completeness_state != ROW_COMPLETE` **não viram arquivo** —
entram só em `coverage.*_excluded`, com `exclusion_reason_codes` agregados em
`manifest.reason_codes`. `data_state` é **de snapshot**, uniforme: não se carimba `DATA_HOLD` em
linha boa por causa de linha vizinha excluída.

#### `opportunities/<opportunity_id>.json` — grain `opportunity_id` [§A.3]

| Campo do contrato | Origem real |
|---|---|
| `schema` | literal `"live-opportunity/1.0"` |
| `opportunity_id` | `LiveOpportunity.opportunity_id` (`row.bid_id` ou `row.pncp_id`, `producer.py:227`) |
| `objeto` | `LiveOpportunity.objeto`; `null` quando `objeto_state == UNKNOWN` |
| `valor` | `{faixa: valor_band, estimado_brl: valor_estimado_brl, estado: valor_state}` — rótulo `VALUE_BANDS`, nunca preço/oferta da CONFENGE; `limitations` carrega a frase de `value_semantics` |
| `orgao` | `{nome: orgao_nome, cnpj: orgao_cnpj, estado: orgao_state}` — `cnpj` **permanece cru**, AC6 |
| `local` | `{uf, municipio, codigo_ibge, estado: geo_state}` |
| `prazo` | `{status: map(deadline_state), data_encerramento, data_publicacao}` |
| `fonte` | `{sistema: LiveOpportunity.source ("pncp"), source_id, link_edital}` |
| `as_of` | `snapshots.as_of_date` |
| `freshness` | idem manifest |
| `coverage` | `{row_completeness_state, dimensoes_desconhecidas}` |
| `limitations` | texto pt-BR |
| `epistemic_classes` | `objeto/orgao/local/prazo.data_* = FACT`; `valor.faixa = CALCULATION` (`value_band()`); `prazo.status = CALCULATION` (comparação com `as_of`, `producer.py:217-224`); qualquer campo com `*_state == UNKNOWN` → `UNKNOWN`. `INFERENCE` **não é emitido** |
| `data_state` | mapa acima |
| `reason_codes` | `LiveOpportunity.reason_codes ∪ exclusion_reason_codes` (códigos internos do produtor, disjuntos dos 14 códigos de negociação do contrato) |
| `content_hash` | `live_hash(payload público sem content_hash)`. **Não** reusar `LiveOpportunity.content_hash()` — aquele é do payload interno e inclui `source_as_of` |

#### `companies/<company_digest>.json` — grain `company_digest` [§A.4]

Um arquivo **por digest de estabelecimento**, todos projetando o mesmo perfil raiz — é isso que
faz o lookup do visitante bater com raiz ou filial em hosting estático.

| Campo do contrato | Origem real |
|---|---|
| `schema` | literal `"company-fit-profile/1.0"` |
| `company_digest` | `identity.cnpj_digest(cnpj14)` (§B.1); único campo que difere entre os arquivos do mesmo root |
| `perfil` | `{razao_social: LiveCompany.razao_social, contratos_observados: len(portfolio_contract_ids), contratacao_mais_recente: most_recent_contracting_date}` — **sem** `company_root8`, **sem** `company_ref` |
| `categorias` | `LiveCompany.observed_objects` |
| `faixas` | `LiveCompany.observed_value_bands` |
| `geografias` | `LiveCompany.observed_ufs` |
| `compradores` | `[{buyer_digest}]` — `identity.cnpj_digest` sobre `LiveCompany.observed_buyer_cnpjs`, ordenado lexicograficamente. **Sem CNPJ cru** (AC6). CNPJ ≠ 14 dígitos → omitido + `manifest.coverage.buyers_unhashable` + `buyer_cnpj_not_hashable`; `buyer_digest: ""` é proibido |
| `oportunidades_aderentes` | fits com `fit_state == FIT_OBSERVED` do mesmo `company_root8`, ordenados por `fit.ordering_key` (lexicográfico, sem score): `[{opportunity_id, matched_dimensions, unknown_dimensions, reason_codes}]` |
| `gaps` | dimensões `NO_MATCH` por oportunidade |
| `unknowns` | `LiveCompanyOpportunityFit.unknown_dimensions` agregadas + `LiveCompany.reason_codes` |
| `as_of`,`freshness`,`coverage`,`limitations`,`data_state`,`reason_codes` | idem `opportunities/` |
| `epistemic_classes` | `categorias/faixas/geografias/compradores/perfil = FACT` (digest de uma observação continua sendo a observação); `oportunidades_aderentes/gaps = CALCULATION` (comparação determinística de 5 dimensões, `fit.py`); `unknowns = UNKNOWN`; `INFERENCE` não emitido |
| `content_hash` | `live_hash(payload público sem content_hash)` |

`limitations` **obrigatoriamente** contém o `disclaimer_pt` do contrato:
*"Aderência histórica não é habilitação, capacidade nem recomendação. Os dados descrevem o
histórico público declarado nas fontes citadas e podem estar incompletos."*

### Projeções semânticas de evento — `OPPORTUNITY_CORE`/`DEADLINE_CORE`/`FIT_CORE` [§C.2]

`source_as_of` está em `OPPORTUNITY_PAYLOAD_KEYS`, logo `LiveOpportunity.content_hash()` muda a
cada tick do watermark. Reusá-lo regeneraria eventos exatamente no churn que esta story proíbe.
Cada tipo tem projeção explícita, e `semantic_hash = live_hash(projeção)`.

| Tipo | `subject_key` | Projeção semântica | Critério de emissão |
|---|---|---|---|
| `NEW_OPPORTUNITY` | `opportunity:<id>` | `OPPORTUNITY_CORE` | `id` ausente no snapshot base; `prev_semantic_hash=""`, `prev_snapshot_id=NULL` (bootstrap, `104:466-469`) |
| `OPPORTUNITY_CHANGED` | `opportunity:<id>` | `OPPORTUNITY_CORE` = `{opportunity_id, objeto, objeto_state, valor_band, valor_state, modalidade_id, modalidade_state, uf, municipio, codigo_ibge, geo_state, orgao_cnpj, orgao_state, row_completeness_state}` | `prev ≠ novo` |
| `DEADLINE_CHANGED` | `opportunity:<id>` | `DEADLINE_CORE` = `{opportunity_id, data_encerramento, deadline_state}` | `prev ≠ novo`. Separado de `OPPORTUNITY_CORE` porque `OPEN→CLOSED` por avanço do `as_of` é material e não deve poluir o outro tipo |
| `FIT_BECAME_RELEVANT` | `company:<company_ref>` | `FIT_CORE` = `{company_ref, opportunity_id, fit_state, matched_dimensions}` | só na transição **para** `fit_state == OBSERVED_FIT`. Downgrade não emite nesta story (declarado, não esquecido) |
| `COMPANY_PORTFOLIO_CHANGED` | `company:<company_ref>` | — | **não emitido nesta story.** Existe no CHECK da 104 (`:450`) mas o critério de materialidade depende do ciclo de crawl outbound, fora de escopo |

**Fora de `OPPORTUNITY_CORE`, deliberadamente:** `source_as_of` (churn puro), `valor_estimado_brl`
(centavos oscilam — a faixa é o fato material), `link_edital`, `reason_codes`, todos os hashes.

`OPPORTUNITY_CORE` usa `orgao_cnpj` **cru** — é projeção **interna**, alimenta `semantic_hash` e
nunca é serializada em payload público. Não confundir com as tabelas de `opportunities/`/`companies/`
acima.

`subject_key` de evento de empresa usa `company_ref`, **não** `company_digest`: `company_digest`
é 1:N por empresa e fragmentaria um evento lógico em N linhas; a tabela de eventos já tem `REVOKE`
para leitores públicos (`104:475-476`).

**Mudança material [§C.3]** *é* `prev_semantic_hash <> semantic_hash` — `chk_live_intel_event_is_transition`
(`104:464`) é a definição, não checagem redundante. O diff é entre o snapshot base selado
(`prev_snapshot_id`, estado `READY_CANONICAL` ou `PARTIAL`) e o corrente.

### Por que `freshness.state` é como o AC3 manda — racional, não norma

> A **fórmula** está no AC3 e **só** lá (a story aplica a si mesma a proibição de alias do AC1).
> Esta seção é o porquê, para o @dev e o @qa não reabrirem cada ponto na revisão.

- **O contrato não define enum para `freshness.state`.** O bloco `freshness` do contrato tem
  `policy`, `layer`, `max_age_hours`, `generated_at`, `source_as_of`, `expires_rule`,
  `stale_rule`, `invalidation_*`, `refresh` — e **nenhuma chave `state`**. `FRESH`/`STALE` é
  **forma de autoria do produtor**, mesma classe do risco aberto #5 (`manifest.sources`), não
  enum herdado. O que o contrato pina é a **regra** (`stale_rule`, `max_age_hours: 48`), e é
  exatamente a regra que o AC3 replica. O que existe de enumerado do lado do consumidor são os
  reason codes `freshness_absent` (reject) e `freshness_stale` (hold) — **dele**, não nossos.
- **Por que serializar antes de comparar.** O consumidor recomputa `stale_rule` a partir das
  **strings** que recebe no JSON. Se derivarmos de `datetime` em memória com microssegundos e
  serializarmos truncando, existe uma janela em que o nosso rótulo e o dele discordam sobre o
  mesmo bundle. Derivar das strings emitidas fecha a janela por construção.
- **Por que `>` estrito e 48h exatas → `FRESH`.** O contrato diz *"exceeds max_age_hours"*.
  `>=` seria uma regra diferente da dele — divergência de um segundo, silenciosa.
- **Por que o ramo "não parseável" é invariante e não branch.** `source_as_of` é `TIMESTAMPTZ NOT
  NULL` na 104 (`:276`, `:338`, `:456`) e `datetime` **não-Optional** em `LiveOpportunity`/
  `LiveCompany` (`schema.py:220`, `:281`). Ausência aqui é corrupção de snapshot, não estado
  exportável: o export aborta. Emitir um bundle que já sabemos que vai virar `freshness_absent`
  (reject) do outro lado seria publicar lixo com carimbo.
- **Por que nenhum reason code novo para esse ramo.** Ele é inalcançável por construção, e um
  código nosso a um hífen do `as_of_unparseable` do contrato é convite a colisão de leitura
  humana e a falso positivo no teste de disjunção.
- **Por que `data_state` não é rebaixado quando `state == "STALE"`.** `hold_reason_codes:
  ["freshness_stale"]` pertence ao vocabulário de **veredito do consumidor** — o mesmo conjunto
  de 14 códigos que a adjudicação da v1.0.3 (risco #1(b)) já fixou como *"nenhum emissível por um
  produtor sobre seus próprios dados"*. Usá-lo para decidir o **nosso** `data_state` reimportaria
  a leitura que aquela adjudicação rejeitou. Além disso `data_state` é propriedade **do snapshot**
  (§A.2.2), uniforme e de completude estrutural; frescor é outro eixo. `DATA_READY` +
  `state: "STALE"` é coerente: o snapshot está completo **e** envelhecido, e `DATA_READY` já é
  declaradamente não-permissão de indexação. O mapa de §A.1 (AC1) fica intacto.
- **Por que `min(source_as_of)` e bloco único.** As tabelas §A.3/§A.4 dizem `freshness` "idem
  manifest"; um bloco por arquivo com `state` divergente dentro do mesmo bundle é ambiguidade que
  o contrato não resolve, e `freshness.source_as_of` do contrato é singular (*"producer snapshot
  cutoff"*). Pior caso (`min`) é a escolha fail-closed: nunca rotula `FRESH` um bundle que carrega
  um payload velho.

### `company_ref` é método, não campo — motivo técnico

`LiveCompany` é `@dataclass(frozen=True)`. Atribuir `company_ref` em `__post_init__` levantaria
`FrozenInstanceError` sem `object.__setattr__`. Pior: como campo, entraria em
`COMPANY_PAYLOAD_KEYS` (derivado de `fields(LiveCompany)`, `schema.py:360`) e em
`portfolio_hash()` — redundante, já que é função pura de `company_root8`, que já está no
payload. Vira método ao lado de `portfolio_hash()`. A coluna `company_ref` da migration 105 é
preenchida pelo producer chamando o método; `FIT_CORE` deriva `company_ref` do mesmo método a
partir de `LiveCompanyOpportunityFit.company_root8` — a dataclass de fit não ganha campo novo.

### Por que `SCHEMA_VERSION`/`ENGINE_VERSION` sobem para 1.1

`observed_establishment_cnpjs` entra em `COMPANY_PAYLOAD_KEYS` → muda `schema_hash()` → muda
`content_hash` → muda `snapshot_id`. É quebra versionada e intencional, custo zero verificado
(`SELECT count(*) FROM public.confenge_live_intelligence_snapshots` = 0 em `extra_test`, HEAD
`d80e7080` não empurrado).

### O que rejeitar se aparecer durante a implementação

Calcular estabelecimentos/digests em tempo de export a partir de `v_contracts_canonical_v2` é
**rejeitado explicitamente** no documento de arquitetura: tornaria o export função da view (não
do snapshot, matando o replay) e criaria uma segunda fonte de identidade de empresa — mesma
classe de defeito que `WRITE_TARGET_ORDER` (`schema.py:40-44`) já rejeitou para allowlists.

### `manifest_hash` não é estável em replay — não escrever o teste errado

`cutoff_at` é `datetime.now(tz=UTC)` no momento do persist; o replay reescreve esse valor sob o
mesmo `snapshot_id` (comportamento documentado, `producer.py:560-566`). `generated_at`,
`freshness.state` e `manifest_hash` variam entre duas execuções do mesmo snapshot — isso é
aceito e declarado, não um bug a corrigir. O que é estável é o `content_hash` por arquivo de
`opportunities/`/`companies/` (a projeção pública exclui colunas de auditoria).

### Riscos residuais — estado pós-adjudicação do @architect (rodada 2)

**Resolvidos** (eram os riscos #1 e #3 da v1.0 do documento de arquitetura; não são mais "a
verificar", e é isso que descarrega o gate de adjudicação apontado pelo @po):

| Incógnita da v1.0 | Resolução | Evidência |
|---|---|---|
| A negociação de schema roda sobre `manifest.json`, que emitia `contract` e não `schema`? | **Sim, e por isso o manifest passa a emitir `schema`** (AC1). `contract` é removido, sem alias; cada entrada de `index` também ganha `schema`. `schema_absent` deixa de ser alcançável. | Contrato vendorizado `dea6457a…`: chave de topo `schema`, `reject_reason_codes` ⊇ `schema_absent`, `accepted_schemas` por família. |
| `reason_codes` do payload é validado contra enum fechado do consumidor? | **Não.** Os 14 códigos do topo são veredictos de negociação do consumidor (`schema_absent`, `content_hash_mismatch`, `fixture_as_live`, `producer_status_not_official_live`, …), nenhum emissível por um produtor sobre seus próprios dados; e `reason_codes` está em `payload_fields` das duas famílias, logo o campo de payload é de autoria do produtor. Salvaguarda: `test_export_contract.py` assere **disjunção** entre nossos códigos e os 14 do contrato. | Contrato `dea6457a…`, blocos `reason_codes`, `reject_reason_codes`, `producer_contracts.*.payload_fields`. |
| `orgao.cnpj` no payload público precisa de confirmação do consumidor? | **Não.** `producer_contracts.live_opportunity` não tem bloco `identity`; `company_fit_profile` tem, e passa a ser cumprido integralmente (AC6 remove CNPJ cru de `compradores`). A assimetria é do contrato. | Contrato `dea6457a…`, `producer_contracts.*`; registrado em `docs/contracts/confenge-live-intelligence-v1.md` §1. |
| Fórmula de `hashCnpj` conferida? | **Sim, nos dois blobs relevantes** (`8b88a894e` @ `dea6457a…` e `1a5452a2d` @ `909621a05…`): `hashCnpj`, salt `"confenge-conversion"`, separador `\|`, `sha256`, truncamento 16 são byte-a-byte idênticos. A única divergência entre os blobs está em `onlyDigits` e afeta **exclusivamente a coerção de entrada não-string** (`typeof` guard → `String(raw == null ? "" : raw)`); para uma `string` de CNPJ ambas reduzem a `raw.replace(/\D/g,"")`. | `git diff` dos dois blobs, registrado em `docs/contracts/confenge-live-intelligence-v1.md`. **Correção de citação:** `909621a05` é ponta de branch, não o commit que modificou `cnpj.cjs` — esse é `eefc556fc`. |

**Abertos** (declarados, não bloqueiam):

1. **Mudança futura do consumidor no `hashCnpj`** — se o salt, o separador ou o truncamento
   mudarem, todo lookup quebra **silenciosamente** (404 em massa, sem exceção em lugar nenhum).
   Mitigação: vetores fixos em `test_identity.py` + proveniência congelada em
   `docs/contracts/confenge-live-intelligence-v1.md` (permite diff dirigido a cada
   re-vendorização). Não mitigável além disso — é acoplamento a repo externo por desenho do
   contrato.
2. **Fan-out de arquivos por digest** — empresas com muitas filiais multiplicam
   `companies/*.json` (conteúdo idêntico salvo `company_digest`). Aceitável nesta story; revisar
   se o bundle passar da ordem de dezenas de MB. O `schema` por entrada de `index` mitiga
   parcialmente (negociação sem download).
3. **`compradores` perde legibilidade humana** após AC6 — o consumidor só resolve um
   `buyer_digest` para nome cruzando com `orgao.cnpj` das `opportunities/` do mesmo bundle, o que
   cobre apenas compradores que também aparecem como órgão de oportunidade viva. Aceito:
   `LiveCompany` não carrega nome de comprador, e inventar um seria segunda fonte de identidade.
   A forma escolhida (objeto, não string) mantém `compradores[].nome` disponível como evolução
   **aditiva** — coerente com `compatibility: additive_nullable_within_v1` do contrato.
4. ~~**Derivação de `freshness.state` não está pinada por nenhum AC**~~ — **FECHADO no gate
   sistêmico do @architect (2026-09-03).** A fórmula está pinada na emenda do **AC3**
   (serializa → deriva das strings, `>` estrito, `min(source_as_of)`, bloco único copiado
   verbatim, ramo não-parseável como invariante fail-closed, `data_state` não rebaixado), com
   racional em Dev Notes ("Por que `freshness.state` é como o AC3 manda") e asserções obrigatórias
   na Task 11. **Registro para o @qa:** `freshness.state` **não** é enum do contrato — o bloco
   `freshness` do contrato não tem chave `state`; `FRESH`/`STALE` é forma de autoria do produtor,
   mesma classe do item #5 abaixo. Aceito e declarado, não "incógnita resolvida".
5. **Forma de `manifest.sources` é de autoria do produtor, não do contrato.** `source_absent` ∈
   `reject_reason_codes` exige o campo **presente**, mas o contrato não pina seu formato —
   `source_families` é a lista de famílias de payload (`live-opportunity/1.0`,
   `company-fit-profile/1.0`), não um schema de fonte. Emitir `[{nome:"PNCP", as_of}]` com chave
   em pt-BR é aditivo e legítimo; risco aceito é o consumidor esperar chave em inglês. Aceito e
   declarado, não bloqueia.

### Registro `FIT_OBSERVED` vs `OBSERVED_FIT` — não são dois valores

`schema.py:92` define `FIT_OBSERVED: Final[str] = "OBSERVED_FIT"`. A tabela §A.4 escreve
`fit_state == FIT_OBSERVED` (nome da constante) e o AC9 escreve `fit_state == OBSERVED_FIT`
(valor da constante). **Ambos corretos, registros diferentes.** O @dev deve comparar contra a
constante `schema.FIT_OBSERVED` — nunca contra o literal `"FIT_OBSERVED"`, que não existe como
valor em lugar nenhum.

### Testing

- Localização: `tests/confenge_live_intelligence/` (padrão já estabelecido pela story-01).
- Testes marcados `@pytest.mark.real_db` seguem a política do `conftest.py` raiz (SKIP limpo
  sem `REQUIRE_REAL_DB=1`, falha nomeada com a flag).
- `test_outbound_equivalence.py` roda contra `extra_li_equiv` (DSN isolado), nunca contra
  `extra_test` compartilhado — motivo: watermark do DSN principal é compartilhado com as demais
  suítes e contaminaria o caso `BLOCKED` (mesma causa raiz de TD-LI-6).
- `test_blocked_when_watermark_is_missing` é reexecutado contra `extra_li_equiv` sem alterar
  suas asserções originais nem o escopo do `DELETE ... LIKE 'LI-TEST-%'`.
- Vetores fixos, nunca `assert hash == hash`, para `company_digest` **e** `buyer_digest` (mesma
  função `identity.cnpj_digest`). Incluir vetor negativo: CNPJ ≠ 14 dígitos → sem digest, nunca
  `""`.
- `test_export_contract.py` roda contra o contrato **vendorizado**
  (`docs/contracts/confenge-live-intelligence-v1.json`), não contra rede nem contra
  `.campaign/overnight/web-cfg`. Asserções obrigatórias: key-set exato de cada payload ==
  `payload_fields` da família **∪ `{"schema"}`** (15+1 em `live_opportunity`, 17+1 em
  `company_fit_profile` — `schema` é envelope aditivo, não `payload_field`);
  `schema` presente no manifest, em cada payload e em cada entrada de `index`;
  ausência de `contract` no manifest; ausência de qualquer CNPJ cru/mascarado em
  `companies/*.json` (regex sobre o JSON serializado); **disjunção** entre os `reason_codes` que
  emitimos e os 14 códigos do contrato; `forbidden_conclusion_fields` e
  `forbidden_public_language` sobre o bundle serializado.
- Não-regressão de fit: `dim_comparable_buyer` continua idêntico após a mudança de `compradores`
  (a projeção pública é folha; `fit.py:154-161` lê `observed_buyer_cnpjs` interno).
- O seed de `extra_li_equiv` inclui ao menos um `buyer_cnpj` com ≠ 14 dígitos, para exercitar
  `manifest.coverage.buyers_unhashable` / `buyer_cnpj_not_hashable`.
- `[Source: docs/architecture/confenge-live-intelligence-w2-decisions.md §A-F, v1.1]` — todo
  detalhe técnico desta story vem desse documento (com as tabelas normativas inlineadas acima);
  nenhuma invenção de campo/algoritmo.

## Reconciliação de débitos e itens de publicação (@po, 2026-09-03)

Tabela de bookkeeping do `po-close-story`. **Distinção deliberada:** *débito técnico* é trabalho
que sobrevive à story e precisa de portador; *item de publicação* é um gate que roda **uma vez**
antes do push e depois deixa de existir. Misturar os dois transforma um passo de processo em
dívida permanente — que é exatamente o erro que esta tabela evita com PRC-001.

| ID | Classe | Estado | Dono | Portador / evidência |
|---|---|---|---|---|
| **TD-LI-6** | Débito técnico | ✅ **FECHADO por esta story (AC10)** | — | Banco isolado `extra_li_equiv` via `scripts/ops/li_equiv_db.py` + `make li-equiv`; `test_blocked_when_watermark_is_missing` passa determinísticamente com asserções originais intactas e `DELETE ... LIKE 'LI-TEST-%'` inalterado. Verificado de forma independente pelo @qa (§6 do gate rodada 1) e re-confirmado na rodada 2. A story irmã já foi reconciliada (v1.2): TD-LI-6 saiu de "absorvido lá" para "dono formal aqui" — **e agora fecha**. Não retorna à story irmã por default. |
| **PRC-001** | **Item de publicação — NÃO é débito técnico** | ⏳ Aberto | **@devops** | `coderabbit --prompt-only --base main` no Pre-PR. Roda **uma vez**, antes do push. Se voltar limpo (ou só não-CRITICAL), o veredito equivale a PASS sem nova rodada de @qa (declaração do próprio @qa). Se voltar CRITICAL, volta ao @dev e o gate reabre. **Não entra em nenhuma tabela de dívida técnica** — não há nada para carregar depois que rodar. |
| **MNT-001** | Achado de QA | ✅ Resolvido | fechado | `mypy` 12/6, delta −7, re-verificado por conteúdo pelo @qa. |
| **REQ-001** | Achado de QA | ✅ Resolvido | fechado | `catalog_mode` reivindicado, default fail-closed `fixture` (adjudicação @architect v1.3, re-verificada no caminho que falhou). |
| **SEC-001** | Achado de QA | ✅ Fechado por adjudicação | fechado | Emenda do AC5 (igualdade para `FORBIDDEN_FIELDS`, substring para `FORBIDDEN_STRINGS`), com tripwire nomeado de reabertura. Sem mudança de código. |
| **DOC-001** | Achado de QA | ✅ Fechado por ratificação | fechado | Ratificação do AC1 (bundle sem payload emitido). Sem mudança de código. |
| **ENV-001** | Higiene de working tree | ⏳ Pré-existente, **fora do escopo desta story** | @devops | Sujeira alheia em `artifacts/predictive/*` e `docs/ops/campaigns/*`, medida pelo @qa como **delta zero** atribuível a esta story. Instrução operacional: **não incluir no PR** — é filtro de staging, não dívida desta story. |

**Baseline de dívida introduzida por esta story: 5 erros de `mypy`** — todos **pré-existentes**
(`verifier.py:253/256/257/258`, `cli.py:38`, `_connect` sem anotação de retorno). Zero dívida
nova. Nenhum débito novo é criado por este fechamento.

## Change Log

| Data | Versão | Descrição | Autor |
|------|--------|-----------|-------|
| 2026-09-03 | 1.0 | Criação da story a partir do documento de decisões arquiteturais fechado pelo @architect (`li-w2-architecture-decisions.md`). Status Draft — sem validação do @po, sem implementação. | @sm (River) |
| 2026-09-03 | 1.0.1 | **Validação NO-GO (@po, `*validate-next-story`). Rubrica 10 pontos: 8.5/10. Prontidão para implementação: 5/10 — este é o número que decide.** Bloqueadores: (1) **`li-w2-architecture-decisions.md` não existe** — busca por nome, por conteúdo (`confenge-conversion`, `cref1`, `OPPORTUNITY_CORE`, `company_digest`) e em `git log --all` não retorna nada no repo, no worktree nem em `.campaign/`. A story declara esse documento como fonte de verdade normativa ("quando a story e o documento divergirem, o documento é a fonte de verdade"), o que torna a norma inauditável; (2) **Tasks 6 e 7 são inexecutáveis** — as tabelas de campo §A.2/§A.3/§A.4 (layout de `manifest.json`/`opportunities`/`companies`) e §C.2 (projeções `OPPORTUNITY_CORE`/`DEADLINE_CORE`/`FIT_CORE` e critérios exatos de emissão) só existem no documento ausente e **não** foram reproduzidas inline; (3) **`docs/contracts/confenge-live-intelligence-v1.json` não existe** em `docs/contracts/` — `test_export_contract.py` (Task 11), que exige "key-set exato vs. contrato #573", não pode ser escrito; (4) **o gate HIGH-RISK do @architect não pode ser considerado descarregado** — o cabeçalho afirma revisão "já pré-fechada no documento de decisões", e o documento é irrecuperável. Não-bloqueadores (Should-Fix): ausência dos campos `executor`/`quality_gate`/`quality_gate_tools` do `story-tmpl.yaml` (drift do repo — só 4 de 60 stories os carregam) e ausência de estimativa de complexidade em pontos/T-shirt (só "Complexity: High" dentro do bloco CodeRabbit). **Verificado e aprovado:** toda citação de linha conferida bate exatamente (`104:446/464/466-469/471-472`, `conftest.py:23` `SEED_PREFIX`, `producer.py:556-570`, `schema.py:360`, `WRITE_TARGET_ORDER schema.py:40-46`, `MUTATING` em `test_live_intelligence_outbound_equivalence.py:54`); a fórmula de `company_digest` de AC7 confere byte-a-byte com `hashCnpj` real (`.campaign/overnight/web-cfg/scripts/conversion/cnpj.cjs:47-51`). **A sequência HIGH-RISK do cabeçalho está correta e não deve ser reescrita** — o defeito é a alegação de descarga, não a ordem. **Encaminhamento:** @architect (publicar/commitar §A–F ou apontar onde vivem; confirmar ou retirar a alegação "pré-fechada") → @sm (inlinear §A.2/A.3/A.4/C.2 nas Dev Notes) → @po (revalidar) → @data-engineer (migration 105) → @architect (gate sistêmico) → @dev. Status permanece **Draft**. | @po (Pax) |
| 2026-09-03 | 1.0.2 | **Revalidação NO-GO (@po, `*validate-next-story`), com `li-w2-architecture-decisions.md` disponível e lido na íntegra (387 linhas, §A–F). Rubrica 10 pontos: 9.2/10. Prontidão para implementação: 6/10 — este é o número que decide.** **Bloqueadores da v1.0.1 encerrados:** (1) o documento de arquitetura **existe** e §A–F é auditável — a norma deixou de ser inauditável; (2) o contrato consumidor **é acessível localmente** em `.campaign/overnight/web-cfg`, ref `origin/feat/live-intelligence-w1` @ `dea6457a14b17279713fb357cbce6c6e8087ce6c` — `test_export_contract.py` (Task 11) é escrevível hoje. **Verificado contra o contrato real:** `payload_fields` de `live_opportunity` e `company_fit_profile` batem **exatamente** com as tabelas §A.3/§A.4 (16 campos cada, incluindo `schema`); `forbidden_conclusion_fields` e `forbidden_public_language` batem exatamente com o AC5; `prazo_status_enum` confirma `SUSPENSA` como valor do contrato nunca emitido por nós (§A.1); `hashCnpj` confere byte-a-byte com o AC7 (`.campaign/overnight/web-cfg/scripts/conversion/cnpj.cjs:47-51`, salt `confenge-conversion`, `slice(0,16)`, HEAD `909621a05`); `accepted_versions:["1.0","v1.0.0"]` valida §D. **Risco residual #1(b) encerrado a favor da leitura de §A.3:** os 14 `reason_codes` do contrato são códigos do verificador/rejeição do consumidor, não enum fechado do payload do produtor. **Bloqueadores remanescentes (Must-Fix):** (1) **§A.2/§A.3/§A.4/§C.2 não estão inlineadas nas Dev Notes** — AC9 remete explicitamente a "ver Dev Notes" para `OPPORTUNITY_CORE`/`DEADLINE_CORE`/`FIT_CORE` e o conteúdo não está lá; as formas aninhadas (`valor{faixa,estimado_brl,estado}`, `local{uf,municipio,codigo_ibge,estado}`, `prazo{status,data_encerramento,data_publicacao}`, `fonte{sistema,source_id,link_edital}`, `perfil{razao_social,contratos_observados,contratacao_mais_recente}`, ordenação de `oportunidades_aderentes` por `fit.ordering_key`, atribuições campo-a-campo de `epistemic_classes`) não são recuperáveis do texto dos ACs. Tasks 6 e 7 seguem inexecutáveis a partir de story + repo. O documento declara no cabeçalho "não vai para o PR", o que torna o inline obrigatório — salvo decisão do @architect de committá-lo no repo e referenciar por caminho relativo; (2) **a alegação de revisão de impacto "pré-fechada" é contradita pelo próprio documento** — Riscos Residuais #1 ("a **verificar** contra #573 quando acessível — não adivinhar agora") e #3 ("Precisa de confirmação do consumidor antes do go-live"); documento que difere itens a confirmação externa não constitui gate sistêmico descarregado; (3) **`compradores[].cnpj` em `companies/*.json` colide com o contrato** — `producer_contracts.company_fit_profile.identity` traz `raw_cnpj_in_payload: false` e a nota sem qualificação "The payload never carries a raw CNPJ", dentro do bloco que governa exatamente esse payload, enquanto o AC6 manda a flag de supressão desligada por padrão. Tasks 8 e 11 não podem ser escritas sem saber em que direção asseverar. Não alterei o AC6: é decisão de contrato externo (@architect), fora da autoridade do @po. **Should-Fix:** (a) nomear na story o caminho resolvível do contrato e fixar os dois refs (`dea6457a` do contrato, `909621a05` do `cnpj.cjs`) — a própria mitigação do risco #1 do documento pede esse pin; (b) decidir se `manifest.json` precisa emitir `schema` além de `contract`, já que `schema_absent` é `reject_reason_code` e a chave de topo do contrato é `schema`; (c) campos `executor`/`quality_gate`/`quality_gate_tools` do `story-tmpl.yaml` ausentes (drift do repo); (d) sem estimativa em pontos/T-shirt fora do bloco CodeRabbit. **Encaminhamento:** @architect (itens 2 e 3 + decidir inline vs. commitar o documento) → @sm (item 1) → @po revalida → @data-engineer (migration 105) → @architect (gate sistêmico) → @dev. Status permanece **Draft**. | @po (Pax) |
| 2026-09-03 | 1.0.3 | **Adjudicação do @architect (Aria) — fecha os três Must-Fix e os dois Should-Fix de contrato da v1.0.2. Quatro decisões:** (1) **`compradores` sai do CNPJ cru — opção (a).** `company-fit-profile/1.0` passa a ser livre de CNPJ cru de ponta a ponta, inclusive de terceiros: `compradores` vira `[{buyer_digest}]` via a **mesma** `identity.cnpj_digest` de `company_digest`. Razão: o bloco `producer_contracts.company_fit_profile.identity` governa exatamente esse payload e sua nota é literal e sem qualificação. `orgao.cnpj` **permanece** em `opportunities/*.json` porque `producer_contracts.live_opportunity` **não tem bloco `identity`**, `orgao` está em seus `payload_fields` e é dado oficial de entidade pública — a assimetria é do contrato, e está registrada em dois artefatos versionados (AC6 + `docs/contracts/confenge-live-intelligence-v1.md` §1). Caminho fail-closed adicionado (CNPJ ≠ 14 dígitos → omitido, `manifest.coverage.buyers_unhashable`, `buyer_cnpj_not_hashable`; `buyer_digest: ""` proibido), e verificado que **nenhum resultado de fit muda** (`fit.py:154-161` lê `observed_buyer_cnpjs` interno, a montante da projeção pública; `schema_hash()` não muda por esta decisão). (2) **Riscos residuais #1 e #3 RESOLVIDOS**, não mais "a verificar": contrato lido na íntegra e **vendorizado** em `docs/contracts/confenge-live-intelligence-v1.json` (`dea6457a14b17279713fb357cbce6c6e8087ce6c`, `sha256 875a999051df2134b4ee18513b1b2c5b1f1ec2d9b716096679079cd527692107`) com proveniência em `.md`; `reason_codes` do topo confirmado como vocabulário do verificador (salvaguarda: asserção de **disjunção** em `test_export_contract.py`). **Correção de citação do handoff:** `909621a05` é ponta de branch, não o commit que modificou `cnpj.cjs` — esse é `eefc556fc`. Os blobs relevantes são `8b88a894e` (@ `dea6457a`) e `1a5452a2d` (@ `909621a05`); eles **diferem**, mas a diferença está inteiramente em `onlyDigits` e afeta só coerção de entrada não-string — `hashCnpj`, salt, separador, `sha256` e truncamento são byte-a-byte idênticos, logo a paridade não depende de qual revisão o consumidor mergear. (3) **`manifest.json` emite `schema`, não `contract`** (sem alias), com `schema` também em cada entrada de `manifest.index`; `contract_version` permanece `"1.0"` e ganha nota anti-"correção" (o contrato se autodeclara `"v1.0.0"`, mas `accepted_versions` das duas famílias contém ambas — trocar seria churn com risco). (4) **Inline direto (opção a):** §A.2/§A.3/§A.4/§C.2 reescritas literalmente nas Dev Notes ("Layout do bundle" e "Projeções semânticas de evento"), e o documento de arquitetura saiu do scratchpad para `docs/architecture/confenge-live-intelligence-w2-decisions.md` (v1.1). O documento passa a ser **background**, não fonte normativa remota: a story é autossuficiente para o @dev. **Artefatos alterados:** cabeçalho, Referências cruzadas, AC1, AC6, AC11, Tasks 3/5/6/8/10/11, Dev Notes (2 seções novas + Riscos residuais reescritos + Testing), Rollback. **Novos:** `docs/architecture/confenge-live-intelligence-w2-decisions.md`, `docs/contracts/confenge-live-intelligence-v1.json`, `docs/contracts/confenge-live-intelligence-v1.md`. Status permanece **Draft** — aguarda revalidação do @po. | @architect (Aria) |
| 2026-09-03 | 1.0.4 | **Validação GO (@po, `*validate-next-story`, rodada 3). Rubrica 10 pontos: 9.6/10. Prontidão para implementação: 9/10. Status Draft → Ready.** **Os três Must-Fix da v1.0.2 estão fechados, verificados no worktree e não por alegação:** (1) **inline confirmado literal** — §A.2 (bloco `manifest.json`), §A.3 (16 linhas de tabela), §A.4 (18 linhas) e §C.2 (5 tipos de evento com projeções e critérios) estão nas Dev Notes ("Layout do bundle", "Projeções semânticas de evento") e conferem palavra a palavra com `docs/architecture/confenge-live-intelligence-w2-decisions.md` v1.1 linhas 58-90/139-215/183-215/377-404; as formas aninhadas que a v1.0.2 apontou como irrecuperáveis (`valor{faixa,estimado_brl,estado}`, `local{...}`, `prazo{...}`, `fonte{...}`, `perfil{...}`, ordenação por `fit.ordering_key`, atribuições campo-a-campo de `epistemic_classes`) estão todas presentes. Tasks 6 e 7 são executáveis a partir de story + repo. (2) **gate de adjudicação descarregado** — os riscos residuais #1 e #3 saíram de "a verificar" para RESOLVIDOS com evidência versionada; documento em `docs/architecture/` (tracked), não em scratchpad. (3) **`compradores[].cnpj` resolvido** — AC6 reescrito reflete corretamente a decisão (a): `compradores = [{buyer_digest}]` via a **mesma** `identity.cnpj_digest`, ordenado lexicograficamente, `buyer_digest: ""` proibido; assimetria com `orgao.cnpj` justificada e verificada contra o contrato. **Verificações independentes desta rodada:** `sha256` do contrato vendorizado confere (`875a9990…`, calculado no worktree); `producer_contracts.company_fit_profile.identity.raw_cnpj_in_payload == false` com a nota literal, e `producer_contracts.live_opportunity` **não tem** bloco `identity` — a assimetria do AC6 é do contrato, confirmado; `forbidden_conclusion_fields` (8) e `forbidden_public_language` (4) batem exatamente com o AC5; `reason_codes` do topo tem **14** códigos (`reject_reason_codes` 13 + `hold_reason_codes` 1) — a contagem da story está certa; `accepted_versions: ["1.0","v1.0.0"]` nas duas famílias valida a nota anti-"correção" do AC11; `producer.py:296-299` confirma a extração de `buyer_cnpj` **sem validação de comprimento** (`"".join(ch for ch in str(...) if ch.isdigit())`), logo o caminho fail-closed do AC6 (omissão + `manifest.coverage.buyers_unhashable` + `buyer_cnpj_not_hashable`, com seed de ≠14 dígitos na Task 10 e teste na Task 11) cobre um risco **real**, não hipotético; `fit.py:154-161` confirma que `_dim_comparable_buyer` lê `company.observed_buyer_cnpjs` interno — nenhum resultado de fit muda por AC6, e `schema_hash()` não muda por esta decisão; `fit.ordering_key` existe (`fit.py:226`); `producer.py:556-570` confirma a não-reprodutibilidade declarada de `cutoff_at` (AC4). **CORREÇÃO DE REGISTRO — a v1.0.2 afirmou errado.** Aquela entrada declarou que `payload_fields` "batem exatamente com as tabelas §A.3/§A.4 (**16 campos cada, incluindo `schema`**)". Isso é **falso** contra o contrato vendorizado: `live_opportunity.payload_fields` tem **15** entradas, `company_fit_profile.payload_fields` tem **17**, e **`schema` não está em nenhuma das duas**. O conteúdo das tabelas está certo (§A.3 = 15+`schema`, §A.4 = 17+`schema`); errada era a contagem e a alegação de conferência. Consequência corrigida nesta rodada: Task 11, Testing e DoD diziam "key-set exato vs. `payload_fields`", o que, tomado ao pé da letra junto com "`schema` em cada payload" (AC1), tornaria `test_export_contract.py` autocontraditório e o teste falharia. Reescrito para `payload_fields ∪ {"schema"}`, com a justificativa (`schema` é envelope aditivo permitido por `compatibility: additive_nullable_within_v1` e exigido por `schema_absent` ∈ `reject_reason_codes`). **Edição editorial do @po, não mudança de AC nem de escopo** — o desenho do AC1 permanece intacto e correto. **Dois riscos abertos novos, nenhum bloqueante:** (#4) **`freshness.state` não é derivado por nenhum AC** — o contrato pina `stale_rule`/`expires_rule`/`max_age_hours: 48`, a story pina só a forma e a origem dos insumos; divergência causa `freshness_stale` (hold) silencioso no consumidor. **Encaminhado ao gate sistêmico do @architect** por ser decisão normativa fora da autoridade do @po; entrou também no DoD. (#5) **forma de `manifest.sources`** não é pinada pelo contrato (`source_families` é lista de famílias de payload, não schema de fonte) — `[{nome:"PNCP", as_of}]` é aditivo e legítimo; aceito e declarado. Registrada também a diferença de **registro** `FIT_OBSERVED` (nome da constante, §A.4) vs `OBSERVED_FIT` (valor, `schema.py:92`, AC9): ambos corretos, mas o @dev deve comparar contra `schema.FIT_OBSERVED` e nunca contra o literal `"FIT_OBSERVED"`. **Should-Fix remanescentes (não bloqueiam):** campos `executor`/`quality_gate`/`quality_gate_tools` do `story-tmpl.yaml` ausentes (drift do repo, 4/60 stories os carregam) e ausência de estimativa em pontos/T-shirt fora do bloco CodeRabbit. **Orçamento de PR:** o branch atual soma 25 arquivos / 6342 linhas adicionadas vs. `origin/main`; os 3 docs novos (527+192+113) + a story (832) + o ajuste da story irmã (2) levam a **~29 arquivos / ~8008 linhas**, ainda dentro de `MAX_FILES_READY=60` e `MAX_TEXTUAL_LINES_ADDED=10_000` (`scripts/ops/check_pr_reviewability.py:31-32`). **Mas restam só ~1992 linhas de folga: a implementação do W2 (11 arquivos novos, incluindo migration 105 e 4 módulos de teste) NÃO cabe neste PR e deve ir em PR separado.** Registrado como restrição de publicação, não como bloqueio da story. **Sequência HIGH-RISK confirmada:** @data-engineer (migration 105, Task 1) → @architect (gate sistêmico, com o item #4 nomeado) → @dev. | @po (Pax) |
| 2026-09-03 | 1.1 | **GATE SISTÊMICO HIGH-RISK — APROVADO (@architect, Aria). Story liberada para o @dev.** Três decisões pendentes fechadas, nenhuma fora da autoridade do @architect, nenhum bloqueio novo. **(1) `freshness.state` pinado (fecha o risco aberto #4 do @po).** Confirmado primeiro que **o contrato NÃO define enum para `freshness.state`** — o bloco `freshness` de `docs/contracts/confenge-live-intelligence-v1.json` não tem chave `state`; `FRESH`/`STALE` é forma de autoria do produtor, mesma classe do risco #5 (`manifest.sources`). O que o contrato pina é a regra (`stale_rule`, `max_age_hours: 48`) e dois reason codes **dele** (`freshness_absent` → reject, `freshness_stale` → hold). Fórmula pinada como **emenda ao AC3** (não AC novo — preserva a numeração AC1–AC11 usada em Task 11/DoD): serializar `generated_at`/`source_as_of` em ISO-8601 UTC `timespec="seconds"` **antes** de comparar e derivar `state` das **mesmas strings emitidas** (fecha a janela de discordância com a recomputação do consumidor); `>` **estrito** (48h exatas → `FRESH`); `source_as_of` do bloco é `min()` sobre os payloads emitidos (pior caso, fail-closed) e o bloco é computado **uma vez** e copiado verbatim para o manifest e para todo payload — é o que "`freshness` idem manifest" de §A.3/§A.4 significa. Ramo "não parseável/ausente": tratado como **invariante fail-closed** (export aborta, nada escrito), não branch de runtime — `source_as_of` é `TIMESTAMPTZ NOT NULL` na 104 (`:276`,`:338`,`:456`) e `datetime` não-Optional em `schema.py:220`/`:281`, logo é corrupção de snapshot, não estado exportável; **nenhum reason code novo** para ramo morto. `STALE` → código interno `source_as_of_beyond_max_age`; delta negativo → `FRESH` (fórmula do contrato) + `source_as_of_after_generated_at`; ambos disjuntos dos 14 do contrato. **`data_state` NÃO é rebaixado por `STALE`** — `hold_reason_codes` pertence ao vocabulário de veredito do **consumidor**, já fixado como não-emissível por produtor na adjudicação v1.0.3 (risco #1(b)), e `data_state` é propriedade de snapshot (§A.2.2); `DATA_READY` + `state:"STALE"` são dois eixos verdadeiros, não contradição. **AC1 e o mapa de §A.1 permanecem intactos.** **(2) Dono do role de escrita de `extra_li_equiv` (fecha o item (i) do @data-engineer).** `scripts/ops/li_equiv_db.py` é o dono único; role **dedicado `li_equiv_runner`**, fora do escopo das migrations 104/105. Fato que dita o desenho: **`CREATE ROLE` é cluster-global**, só os grants são por-database — logo "role local" não existe e reusar/estender `confenge_live_intel_reader` alargaria permissão em `extra_test` e em produção, contradizendo o próprio AC10. Grants derivados de `schema.WRITE_TARGET_ORDER` importado por nome (nunca segunda lista literal — AR-2/ADR-040, `schema.py:40-46`), incluindo `UPDATE` e `USAGE` de sequence, que uma enumeração por palpite ("só INSERT/DELETE") quebraria no persist. Guarda fail-closed de DSN (dbname == `extra_li_equiv` + loopback) e teardown obrigatório `DROP OWNED BY` → `DROP DATABASE` → `DROP ROLE`. **O segundo bullet do AC10 foi reescrito** — a redação anterior (`confenge_live_intel_reader` estendido) está revogada por incorreta. **(3) Extensão dos testes estáticos/de catálogo para a 105 (fecha o item (ii) do @data-engineer).** Confirmado: **parametrizar os dois arquivos existentes, nunca criar arquivo novo para a 105** — seriam dois instrumentos para a mesma proposição, a classe de defeito que a story já rejeita em identidade e allowlist. Pontos exatos nomeados na Task 11 (`test_live_intelligence_outbound_equivalence.py:32-33/:69/:74/:92/:104/:114`; `test_migration_grants_and_rollback.py:34-35/:229/:250/:290` com ciclo de rollback **empilhado** 104+105 → r105 → r104 → resíduo → reaplicar), mais as asserções de catálogo que o @data-engineer provou à mão na Task 1 (`attacl IS NULL`, `relacl` inalterado) promovidas a guarda de regressão. Funções novas dentro desses dois arquivos são permitidas; arquivo novo duplicado não. **Achado adicional do gate, registrado como esclarecimento de escopo do AC4 — não é defeito e não bloqueia:** `freshness` ∈ `payload_fields` → entra no payload → entra no `content_hash`, e `freshness.generated_at` vem de `cutoff_at`. A estabilidade exigida pelo AC4 continua verdadeira porque `cutoff_at` só é reescrito em **re-persist**, nunca por export; o Given do AC4 é "dois exports **sem re-persist intercalado**", e é assim que o teste deve ser escrito. Churn declarado: re-persist muda todo `content_hash` mesmo com dado idêntico — churn de cache do consumidor, **não** de evento (eventos chaveiam em `semantic_hash`, que não contém `freshness`). **Rejeitado** excluir `freshness` do `content_hash`: o contrato não pina essa fórmula e `content_hash_mismatch` é reject code — exclusão de nossa autoria seria divergência não verificável. **Artefatos alterados:** AC3 (emenda normativa), AC4 (esclarecimento), AC10 (2º bullet reescrito), Task 10, Task 11, Dev Notes (bloco §A.2 do manifest + seção nova de racional de `freshness` + risco #4 movido para fechado), DoD (4 itens novos, substituindo a referência futura "conforme a regra pinada pelo @architect"). `docs/architecture/confenge-live-intelligence-w2-decisions.md` → **v1.2** na mesma passada, para que story e documento não divirjam. **Nenhum AC de escopo, nenhum mapa de enum e nenhuma tabela inlineada validada pelo @po na v1.0.4 foi alterado.** **Veredito: APROVADO — @dev pode prosseguir da Task 2 em diante.** Restrição de publicação da v1.0.4 permanece: a implementação vai em PR separado. | @architect (Aria) |
| 2026-09-03 | 1.2 | **Implementação das Tasks 2-11 (@dev, Dex). Status Ready → InReview.** Novos: `identity.py` (§B.1/§B.2, `cnpj_digest` única para `company_digest` **e** `buyer_digest`, `None` nunca `""`), `public_policy.py` (mapas §A.1, listas proibidas provadas como cópia do contrato, `build_freshness` como **função pura** — é o que torna a fronteira de 48h testável sem banco), `export.py` (bundle montado **inteiro em memória** antes do primeiro `write`, para que o fail-closed seja estrutural), `events.py` (LI-7: projeções `OPPORTUNITY_CORE`/`DEADLINE_CORE`/`FIT_CORE`, `event_id` = tupla de transição, `ON CONFLICT DO NOTHING`), `scripts/ops/li_equiv_db.py` + seed + `make li-equiv`. Alterados: `schema.py` (campo aditivo `observed_establishment_cnpjs`, `company_ref()` como **método**, bumps 1.1), `producer.py`, `verifier.py` (rebuild da coluna nova + `verify_bundle` sobre o JSON de disco), `cli.py`. Testes: 4 arquivos novos + parametrização dos **dois** existentes para a 105 (nenhum arquivo novo para a 105, conforme adjudicação). **Resultado real:** 237 passed / 33 skipped / 1 failed na suíte geral — os 33 skipped e o 1 failed são o arquivo e o teste do AC10, que passam sob `make li-equiv` (33 passed + 1 passed, teardown sem resíduo). `ruff` limpo; **`mypy` não instalado** e **CodeRabbit `signed out`** — os dois itens do DoD ficam abertos e declarados, não simulados. **Duas ambiguidades resolvidas dentro do texto da story:** bundle sem payload emitido — BLOCKED **e** universo vazio — recebe UM tratamento (`cutoff_at` + `LIMITATION_NO_PAYLOAD_EMITTED`, nenhum reason code novo); e AC8 pedindo o erro no export enquanto a Task 4 pede no producer (implementados os dois). Sete `[AUTO-DECISION]` registradas nas Completion Notes. **Nenhuma asserção existente relaxada; `PROTECTED_OBJECTS`/`MUTATING`/`DML` e o `DELETE ... LIKE 'LI-TEST-%'` intactos.** | @dev (Dex) |
| 2026-09-03 | 1.2.1 | **Correção do MNT-001 do QA (@dev, Dex). Status permanece InReview — o veredito é do @qa, não meu.** Escopo estritamente de tipagem, **zero mudança de comportamento de runtime**, confirmado pelo próprio @qa como não-bug. `export.py`: `export_bundle` atribui `manifest: dict[str, Any] = bundle["manifest"]` e retorna o local anotado — o `write_text` do manifest passa a usar a mesma variável, o que também remove a segunda indexação do dict. `cli.py`: a variável `report`, reusada entre ramos com tipos disjuntos, virou `bundle_report` (ramo `export`) e `snapshot_report` (ramo `verify`). **Renomeação pura, deliberadamente sem reestruturar o fluxo:** indentar o ramo `verify` sob um `if args.command == "verify"` deixaria `main()` (anotada `-> int`) com um caminho de fall-through sem `return` e trocaria 6 erros por um `Missing return statement` sob `warn_unreachable = true`. **Nenhum `# type: ignore`** — `warn_unused_ignores = true` converteria um ignore redundante em erro novo. **Evidência (mypy 2.3.1 em venv isolado, config do `pyproject.toml`, mesmo comando antes e depois):** 19 erros / 7 arquivos → **12 erros / 6 arquivos**, delta exato de −7, com `export.py` saindo por completo da lista. A baseline de 5 pré-existentes segue intacta e fora de escopo (`verifier.py:253/256/257/258`, `cli.py:38` — `_connect` sem anotação de retorno). `ruff check` e `ruff format --check` limpos nos dois arquivos. **Testes:** `tests/confenge_live_intelligence/` + `tests/test_live_intelligence_outbound_equivalence.py` = 232 passed / 33 skipped / 1 failed; o único failure é `test_producer_state_criteria.py::test_blocked_when_watermark_is_missing`, que é a **dívida TD-LI-6 já documentada no docstring do próprio teste** (o DSN `extra_test` compartilhado tem 5 linhas em `pncp_raw_bids` fora do prefixo `LI-TEST-`, então há watermark real e o `build_snapshot` retorna `READY_CANONICAL` em vez de `BLOCKED`) — **pré-existente e provadamente alheio a esta correção**: nem `test_producer_state_criteria.py` nem `producer.py` importam `cli.py` ou `export.py`. Os 33 skipped são o arquivo do AC10, que exige `make li-equiv`. **Ressalva de cobertura, declarada e não mascarada:** o ramo `export` do CLI não é exercido por nenhum teste (só `test_no_outbound_write_runtime.py` chama `li_cli.main`, e apenas com `build`/`verify`) — a renomeação de `bundle_report` está verificada **por inspeção e por mypy**, não por execução. | @dev (Dex) |
| 2026-09-03 | 1.3 | **Adjudicação dos três itens LOW do QA (@architect, Aria). Status permanece InReview — o veredito é do @qa.** **(1) SEC-001 → manter comparação por IGUALDADE, sem mudança de código.** O motivo é impossibilidade, não preferência: `adherence_semantics.disclaimer_pt` do contrato vendorizado contém literalmente a substring `capacidade`, que está em `forbidden_conclusion_fields`, e o disclaimer é obrigatório em `limitations` de **todo** payload — ler `FORBIDDEN_FIELDS` por substring sobre valores torna o AC5 insatisfazível por construção. Corrigida a premissa herdada do encaminhamento: **existem** campos de texto livre no bundle (`objeto`, `orgao.nome`, `perfil.razao_social`), mas são `FACT` de autoria de **terceiros** copiados verbatim da fonte pública; varrê-los por substring negaria publicação de dado público legítimo ou incentivaria **sanear um campo `FACT`** — violação de contrato pior que o risco latente. Residual aceito com **tripwire nomeado**: se um campo de texto livre de autoria **própria** entrar em algum payload, a decisão é reaberta. Emenda registrada no AC5. **(2) DOC-001 → ratificado, sem mudança de código.** Bundle sem payload emitido tem dois sub-casos — `SNAPSHOT_BLOCKED` e universo legitimamente vazio em `READY_CANONICAL`/`PARTIAL` — e ambos seguem **um único** caminho: export prossegue (universo vazio é snapshot selado válido, não corrupção; o ramo de aborto da emenda do AC3 nomeia só `generated_at`/`source_as_of` ausentes ou sem fuso), `manifest.index` com zero arquivo satisfaz o "nem mais, nem menos" do AC1, `freshness` cai no `cutoff_at` do próprio snapshot e a substituição é **declarada** em `limitations` via `LIMITATION_NO_PAYLOAD_EMITTED`, **sem reason_code novo**. Ratificação registrada no AC1. **(3) REQ-001 → código alterado.** `official_live` deixa de ser literal. O contrato define `catalog_mode.official_live` como *"only when producers are live official artifacts and **claimed_live is true**"*: `catalog_mode` vira parâmetro de `build_bundle`/`export_bundle` e do CLI (`--catalog-mode`), vocabulário fechado `{fixture, official_live}`, **default fail-closed `fixture`**, com `official_live` e `producer_status` **derivados** do mesmo parâmetro (um só lugar onde a proposição "este bundle é oficial ao vivo" pode ser afirmada). O bundle que o @qa gerou do seed de `extra_li_equiv` agora sai `catalog_mode: "fixture"` / `official_live: false`, e o consumidor o recusa por `producer_status_not_official_live` — o efeito desejado. **A emenda resolve uma contradição pré-existente**, não acrescenta requisito: o primeiro Given do AC1 mandava `official_live=true` incondicionalmente enquanto §A.2 dizia "só se veio do datalake real"; §A.2 governa. **Rejeitado** gatilhar por `state` do snapshot — proveniência e completude são eixos independentes, mesma doutrina de `freshness.state` × `data_state`, e `official_live: true` + `DATA_REJECT` é coerente (produtor real, nada publicável); o mapa de §A.1 permanece intacto. **Rejeitado** vetar a reivindicação por marcador de seed (`LI-TEST-`): todo seed do repo o carrega, o veto tornaria o próprio AC1 inverificável por teste. **Limite declarado e não vendido como mais do que é:** isto é reivindicação, não verificação de origem — coluna de proveniência no snapshot exigiria migration `106`, fora de escopo. **Evidência desta rodada** (`REQUIRE_REAL_DB=1`, `extra_test`): `tests/confenge_live_intelligence/` + `tests/test_live_intelligence_outbound_equivalence.py` = **234 passed / 33 skipped / 1 failed**, e o único failure é `test_blocked_when_watermark_is_missing` (TD-LI-6, idêntico à baseline do @qa e do @dev, passa sob `make li-equiv`); `test_export_contract.py` isolado = **45 passed** (43 anteriores + 2 novos); `ruff check`/`ruff format --check` limpos em `scripts/confenge_live_intelligence/` e `tests/confenge_live_intelligence/`; `mypy` = **12 erros / 6 arquivos**, exatamente a baseline pós-MNT-001 do @dev — **zero erro novo**. **Fecha também a ressalva de cobertura da v1.2.1** (o ramo `export` do CLI não era exercido por nenhum teste): o caminho foi rodado de ponta a ponta por mim contra `extra_test`, nos dois modos e com `--verify-bundle` — sem reivindicação → `catalog_mode: "fixture"`, `official_live: false`, `data_state: "DATA_READY"`, `bundle_checks` populado; com `--catalog-mode official_live` → `official_live: true` e o mesmo `data_state`. O `verify_bundle` **não** carrega invariante escondida de liveness, e o snapshot usado tinha universo vazio, o que exercitou de quebra a rota ratificada em DOC-001 (`files: 0`, bundle emitido). Snapshot de prova removido de `extra_test` (`snapshots restantes: 0`, `seeds LI-TEST restantes: 0`). **Consequência de processo, declarada:** a alteração de `export.py`/`cli.py`/`public_policy.py` é **posterior** ao gate de QA, que o próprio @qa registrou como feito sobre a árvore não commitada em `HEAD d80e7080` — a evidência daquele gate **não cobre** este código. É necessária re-verificação do @qa **escopada a AC1/AC5 e ao contrato do bundle** (não o gate inteiro). MNT-001 segue endereçado pelo @dev aguardando re-verificação e PRC-001 (CodeRabbit) segue com o @devops: **PASS não está disponível até esses dois fecharem**, e um fechamento com CONCERNS exige dono e prazo para ambos (§6 do protocolo). | @architect (Aria) |
| 2026-09-03 | 1.4 | **Fechamento administrativo do @po (Pax), `po-close-story.md` — executado PARCIALMENTE, com dois atos DECLARADOS COMO NÃO EXECUTÁVEIS PELO @po, e o motivo é autoridade, não juízo.** **(A) O que foi feito:** (1) **Veredito de QA aceito** — CONCERNS, escopo reduzido a **1** item (PRC-001, dono @devops). Pelo §8 do protocolo, publicação é evidence-based e aceita PASS, CONCERNS **ou** WAIVED; o próprio gate declara que "CONCERNS aqui NÃO bloqueia o fechamento do @po nem o push do @devops". Aceito sem waiver e sem re-litígio. (2) **Checkboxes reconciliados** — Tasks 1 a 11 já estavam **todas** `[x]` e foram conferidas uma a uma contra a evidência do @qa, não contra o relato do @dev; **Task 12 permanece `[~]`** e a redação do subitem de tipagem foi **corrigida** (dizia "`mypy` NÃO executado — não instalado", superado pela v1.2.1 e pela re-execução independente do @qa: 12 erros / 6 arquivos, 5 de baseline pré-existente, **zero novo**). O subitem de `mypy` fecha; o pai continua `[~]` **só** por causa do CodeRabbit — marcar o pai `[x]` com PRC-001 aberto seria fechar por vontade, não por evidência. No DoD, marcados `[x]`: AC1–AC11 verificados (base: injeção adversarial do @qa, §1 do gate), veredito de QA independente emitido, `ruff`+`mypy`, `pr-reviewability` (**com qualificação obrigatória: fecha apenas sob PR decomposto**) e `generated-artifacts`. Nenhum checkbox foi marcado sem evidência nomeada. (3) **Tabela de débitos criada e reconciliada** (seção nova acima) — **TD-LI-6 FECHADO por esta story via AC10**, com a story irmã já reconciliada na v1.2 dela e coerente (linha tachada, "dono formal: W2/AC10", guarda de não-retorno por default). **PRC-001 classificado como ITEM DE PUBLICAÇÃO, não débito técnico**: é um gate que roda uma vez antes do push e desaparece; registrá-lo como dívida criaria um item permanente para um passo de processo. **Dívida nova introduzida por esta story: ZERO.** (4) **State file criado** em `.aiox/state/stories/confenge-live-intelligence-w2-web-export.json`, que não existia (o @qa apontou a lacuna e corretamente não escreveu nele). **(B) O que o @po NÃO fez, e por quê:** **(i) Status permanece `InReview` — a transição `InReview → Done` é autoridade EXCLUSIVA do @qa** (`story-lifecycle.md`; `po-close-story.md` §Authority Boundary: *"This task never changes story lifecycle status"*, §Forbidden: *"Setting or rewriting story Status"*). CONCERNS **determina** `Done`, e o @qa apenas não registrou a transição ao emitir o veredito da rodada 2. É um ato de **uma linha**, devido ao @qa, não um gate reaberto. O @po não o executa nem "documenta a nuance" — assumir autoridade alheia é o desvio que o §3 do protocolo proíbe nominalmente. **(ii) `po_closed` permanece `false`** no state file, pela mesma razão: `po_closed: true` com `status: InReview` é precisamente o estado inconsistente que os hooks existem para pegar (§11). O fechamento do @po está **pronto e integralmente executado no que é administrativo** — ele passa a `true` no instante em que o @qa registrar `Done`, sem nova rodada de análise. **(C) `closure-key` NÃO emitido — no-op declarado, conforme o passo 2 do `po-close-story.md`.** As três formas aceitas de chave são `:commit:<sha>`, `:pr:<number>` e `:digest:<reviewed_revision>`. **Não existe nenhuma das três:** `HEAD = d80e7080` é o commit **anterior** à implementação, todo o código da story continua `M`/`??` (**nada commitado** — fato registrado pelo próprio @qa), não há PR, e a proveniência do gate é "a árvore de trabalho como está agora", que não é um digest determinístico. O passo 2 é explícito: sem uma das três formas, *"stop before every write and report a read-only no-op; do not update the epic/backlog or Change Log"* com chave. Esta entrada é, portanto, **bookkeeping de reconciliação e NÃO uma entrada de fechamento** — deliberadamente sem `closure-key`. Usar `d80e7080` seria proveniência **falsa** (afirmaria que o @qa revisou código que aquele commit não contém), exatamente o que as precondições da task rejeitam. **(D) Consequência direta: `publication_authorized = false`, e a razão é mais forte que "prudência".** O §8 exige `reviewed_commit === HEAD`; **não existe commit para colocar em `reviewed_commit`** (gravado `null`, com nota). @devops autoriza depois de: commitar a árvore (é esse commit que vira `reviewed_commit`), rodar o CodeRabbit Pre-PR (PRC-001) e decompor o PR. **(E) Correção de registro sobre "o que falta para publicar":** falta **mais** que CodeRabbit + PR separado + push. A lista honesta e completa está em `next_action` do state file, e inclui o **commit da árvore de trabalho** (hoje inexistente) e o filtro de **ENV-001** (sujeira alheia pré-existente que não deve entrar no PR). | @po (Pax) |
| 2026-09-03 | 1.5 | **Registro da transição de status InReview → Done (@qa, Quinn) — ato formal devido, não gate reaberto.** O veredito da rodada 2 é **CONCERNS** e `story-lifecycle.md` é literal: "PASS, CONCERNS, and WAIVED move the story to `Done`" e "@qa MUST update the story status and Change Log before reporting the gate result". A transição não havia sido registrada por omissão minha ao emitir o veredito da rodada 2; o @po corretamente não a executou (`po-close-story.md` proíbe alterar Status). **Nenhuma reanálise foi feita e nenhum item do gate foi reavaliado.** Verificação de provenência executada antes do registro, para confirmar que a árvore ainda é a árvore revisada: (a) `git status` do worktree — nenhum arquivo de código novo ou removido em relação ao gate; (b) `mtime` de **todos** os 25 `scope_files` — o mais recente arquivo de código é `03:03:35` (`cli.py`, `public_policy.py`, `test_export_contract.py`), anterior às únicas escritas posteriores, que são `docs/stories/` (`03:21:41`) e `.aiox/state/` (`03:25:22`), ambas do @po; (c) reprodução por **conteúdo** de duas afirmações do meu próprio bloco da rodada 2 — `ruff check` + `ruff format --check` em `scripts/confenge_live_intelligence/`, `tests/confenge_live_intelligence/` e `scripts/ops/li_equiv_db.py` devolveram `All checks passed!` / `26 files already formatted` (mesmo contador de arquivos, byte-estável), e `test_export_contract.py` coletou **45** testes. **O aviso de invalidação por edição de código posterior NÃO foi acionado — o gate da rodada 2 permanece válido.** **PRC-001 continua ABERTO** e Done **não** o fecha nem autoriza publicação: `publication_authorized` permanece `false`, dono @devops, por dois motivos independentes (PRC-001 não rodou; não há commit, logo `reviewed_commit === HEAD` é insatisfazível). Se o CodeRabbit Pre-PR voltar com CRITICAL, a story retorna ao @dev por **nova story de correção**, não por reversão de status. `po_closed` permanece `false` — é campo do @po, não meu. | @qa (Quinn) |

## Dev Agent Record

### Agent Model Used

Claude Opus 5 (`claude-opus-5[1m]`) — agente @dev (Dex), sessão autônoma YOLO,
worktree `confenge-live-intelligence-01`.

### Debug Log References

Ambiente: PostgreSQL 16.15 (`extra-test-db`, `postgresql://test:test@127.0.0.1:5433/extra_test`).
Todas as suítes rodadas com `REQUIRE_REAL_DB=1` — sem a flag, os testes `real_db`
fazem SKIP limpo e o relatório seria verde falso.

**Baseline antes da implementação (HEAD `d80e7080`):** 129 passed, 1 failed
(`test_blocked_when_watermark_is_missing` — TD-LI-6, exatamente a dívida que o AC10 fecha).

**Resultado final (`pytest tests/confenge_live_intelligence/ tests/test_live_intelligence_outbound_equivalence.py tests/test_apply_migrations.py`):**
`237 passed, 33 skipped, 1 failed`.
- Os **33 skipped** são `test_outbound_equivalence.py`, que exige `LI_EQUIV_RUNNER_DSN`.
  Sob `make li-equiv` esse arquivo roda e dá **33 passed**.
- O **1 failed** é `test_blocked_when_watermark_is_missing` contra o `extra_test`
  compartilhado — o mesmo da baseline, e é o comportamento declarado da própria dívida.
  Sob `make li-equiv` (banco isolado) ele **passa**: `1 passed`.

**`make li-equiv` de ponta a ponta:** `33 passed` (AC10) + `1 passed`
(`test_blocked_when_watermark_is_missing` contra `extra_li_equiv`) + teardown sem resíduo
(`extra_li_equiv/li_equiv_runner removidos`).

**Lint:** `ruff check` e `ruff format` limpos em todos os arquivos novos/alterados.
**Type check:** `mypy` **não está instalado** neste ambiente (`No module named mypy`) —
não executado, não simulado. Item do DoD que permanece **não verificado**.

**Achado operacional (não é defeito desta story, mas atrapalha o @qa):**
`test_rollback_removes_every_object_and_reapply_is_clean` reaplicava **apenas a 104**,
dropando as colunas da 105 e quebrando toda a suíte seguinte. O ciclo empilhado da Task 11
(104+105 → r105 → r104 → resíduo → reaplicar 104+105) corrige isso — era exatamente o
motivo pelo qual o @architect exigiu o empilhamento.

### Completion Notes List

**Decisões autônomas registradas (nenhuma reabre item pinado por @po/@architect):**

- `[AUTO-DECISION]` **Reexecução de `test_blocked_when_watermark_is_missing` contra
  `extra_li_equiv`** → `tests/confenge_live_intelligence/conftest.py` passa a honrar
  `LI_EQUIV_DSN` (DSN **administrativo** no banco isolado), redirecionando `LOCAL_DATALAKE_DSN`
  localmente e restaurando no `finally`.
  *Razão:* a story exige rodar o teste contra o banco isolado sem alterar suas asserções nem
  ampliar o `DELETE ... LIKE 'LI-TEST-%'`. `scripts/testing/real_db_guard.py` é infra
  **compartilhada** e não foi tocada. O `pncp_id` do seed usa deliberadamente o prefixo
  `LI-TEST-`, para que o DELETE existente o alcance **sem ampliar escopo**.
- `[AUTO-DECISION]` **Dois DSNs, não um** → `LI_EQUIV_RUNNER_DSN` (role restrito
  `li_equiv_runner`, usado só por `test_outbound_equivalence.py`) e `LI_EQUIV_DSN`
  (administrativo, usado pelas fixtures que precisam de DML de seed).
  *Razão:* o AC10 exige o role restrito **para a prova de equivalência**; o
  `DELETE` da fixture do conftest é, por desenho, impossível sob esse role. Usar um DSN só
  tornaria uma das duas exigências inexequível.
- `[AUTO-DECISION]` **`FORBIDDEN_FIELDS` comparado por IGUALDADE, não por substring**
  (`verifier.assert_no_forbidden_content`).
  *Razão:* o `disclaimer_pt` **obrigatório** do contrato contém a palavra `capacidade`
  ("Aderência histórica não é habilitação, **capacidade** nem recomendação"). Substring
  tornaria o AC5 autocontraditório com o AC6/§A.4. A proibição é de campo/valor de conclusão,
  não da palavra dentro da frase que existe para **negar** a conclusão.
- `[AUTO-DECISION]` **Tokens hexadecimais são mascarados antes da varredura de CNPJ**
  (`verifier.assert_no_raw_cnpj`).
  *Razão:* um `company_digest` (16 hex) ou `content_hash` (64 hex) pode conter 14 dígitos
  consecutivos **por acaso** (~4,5% de chance por hash de 64 chars) — a prova de AC6 seria
  um teste instável. A máscara só se aplica a valores que **já foram validados** contra
  `^[0-9a-f]{16}$`/`^[0-9a-f]{64}$`, e nenhum CNPJ (14 chars) satisfaz esses formatos.
- `[AUTO-DECISION]` **`valor.estimado_brl` é emitido como STRING decimal normalizada.**
  *Razão:* mesma disciplina de `schema._json_default`; um float no JSON público
  reintroduziria erro de representação num campo que o consumidor compara contra o documento
  de origem. O contrato não pina o tipo.
- `[AUTO-DECISION]` **`test_outbound_equivalence.py` só recebe o marcador `real_db` quando
  `LI_EQUIV_RUNNER_DSN` existe.**
  *Razão:* `tests/conftest.py:29-44` converte **qualquer** skip de item `real_db` em FALHA sob
  `REQUIRE_REAL_DB=1`. Declarar `real_db` sem o banco seria afirmar capacidade que o ambiente
  não tem, e a alternativa (rodar contra `extra_test`) é a causa raiz de TD-LI-6.
- `[AUTO-DECISION]` **Espera ancorada antes de ler `pg_stat_all_tables`** (AC10).
  *Razão:* `pgstat_report_stat` só descarrega as estatísticas pendentes a cada ~1s
  (`PGSTAT_MIN_INTERVAL`). Ler logo após o commit devolveria ZERO para **toda** tabela —
  inclusive as outbound — e o delta zero seria **falso passe**. A espera é ancorada na escrita
  do próprio motor: quando ela aparece, o flush ocorreu.

**Ambiguidades encontradas — RESOLVIDAS dentro do texto da story, não empurradas ao @qa:**

1. **Bundle sem nenhum payload emitido** (`BLOCKED` por AC1, **e** universo legitimamente
   vazio em `READY`/`PARTIAL`). A emenda do AC3 define `source_as_of = min` sobre os payloads
   emitidos, e não há nenhum. **Um único tratamento para os dois casos:** o bloco usa
   `cutoff_at` nos dois campos e a substituição é **declarada** em `limitations`
   (`public_policy.LIMITATION_NO_PAYLOAD_EMITTED`). Nenhum reason code novo foi inventado.
   *Registro de correção de rota:* a primeira implementação abortava o export para o caso
   `READY`-vazio ("não publicar catálogo vazio parecendo fresco"). **Isso estava errado** e foi
   desfeito: o ramo (1) da emenda do AC3 nomeia três condições de aborto — `generated_at`
   ausente, `source_as_of` ausente, `tzinfo` ausente — e o racional é explícito (`TIMESTAMPTZ
   NOT NULL` + tipo não-Optional ⇒ ausência é **corrupção de snapshot**). Universo vazio não é
   corrupção, e o AC1 não abre exceção para catálogo vazio: `manifest.index` com zero arquivo
   satisfaz "nem mais, nem menos". Recusar o export seria substituir a fórmula pinada por juízo
   próprio — a mesma classe de desvio que a emenda já proibiu no ramo de delta negativo.
   Teste: `test_sealed_snapshot_with_empty_universe_still_emits_a_bundle`. Verificado também
   pela CLI contra o `extra_test` vazio: `data_state: DATA_READY`, `files: 0`, verifier verde.
2. **AC8 tem o erro no export; a Task 4 pede a asserção no producer.** Implementadas **as
   duas** (defesa em profundidade, mesma condição): `project_companies` levanta
   `LiveIntelligenceProducerError` e `export.build_bundle` levanta
   `LiveIntelligenceExportError`. Nenhuma delas é silenciosa.

**Ordem de implementação (incrementos, cada um com a suíte rodada antes do seguinte):**
schema+identity+persistência+rebuild do verifier → `public_policy` → `export` → verificação de
bundle → `events` + encadeamento → `cli` → `li_equiv_db`+seed+Makefile → testes + parametrização.

**Defeito prevenido no incremento 1:** `verifier._rebuild_company` não lia
`observed_establishment_cnpjs`; com o default `()` da dataclass, o rebuild divergiria do array
persistido, `portfolio_hash()` mudaria e o verifier falharia fechado sobre um snapshot
**íntegro** — mesma classe do defeito de fuso já documentado em `_rebuild_opportunity`.

### File List

**Entregue (Task 1, @data-engineer, 2026-09-03) — arquivos criados e validados contra
`extra_test`:**

- `db/migrations/105_confenge_live_intelligence_company_ref.sql` (novo)
- `db/rollback/105_confenge_live_intelligence_company_ref_rollback.sql` (novo)

**Entregue (Tasks 2-12, @dev, 2026-09-03) — lista REAL do diff:**

Novos:
- `scripts/confenge_live_intelligence/identity.py` (Task 3)
- `scripts/confenge_live_intelligence/public_policy.py` (Task 5)
- `scripts/confenge_live_intelligence/export.py` (Task 6)
- `scripts/confenge_live_intelligence/events.py` (Task 7)
- `scripts/ops/li_equiv_db.py` (Task 10)
- `fixtures/confenge_live_intelligence/equivalence_seed.sql` (Task 10)
- `tests/confenge_live_intelligence/test_identity.py` (Task 11)
- `tests/confenge_live_intelligence/test_events.py` (Task 11)
- `tests/confenge_live_intelligence/test_export_contract.py` (Task 11)
- `tests/confenge_live_intelligence/test_outbound_equivalence.py` (Task 11)

Alterados:
- `scripts/confenge_live_intelligence/schema.py` (Task 2 — campo aditivo, `company_ref()`, bumps 1.1)
- `scripts/confenge_live_intelligence/producer.py` (Task 4 — coleta, persistência, asserção AC8, encadeamento de eventos)
- `scripts/confenge_live_intelligence/verifier.py` (Tasks 2/8 — rebuild da coluna nova + `verify_bundle`)
- `scripts/confenge_live_intelligence/cli.py` (Task 9 — subcomandos `export` e `events`)
- `tests/confenge_live_intelligence/conftest.py` (Task 11 — redireção por `LI_EQUIV_DSN`, sem tocar `real_db_guard`)
- `tests/confenge_live_intelligence/test_migration_grants_and_rollback.py` (Task 11 — parametrização 104/105, ciclo empilhado, guardas de catálogo)
- `tests/test_live_intelligence_outbound_equivalence.py` (Task 11 — parametrização para os 4 caminhos SQL)

**Correção QA MNT-001 (@dev, 2026-09-03) — apenas tipagem, zero mudança de comportamento:**

- `scripts/confenge_live_intelligence/export.py` (`export_bundle`: local anotado
  `manifest: dict[str, Any] = bundle["manifest"]`, elimina o `no-any-return` da linha 585)
- `scripts/confenge_live_intelligence/cli.py` (`main`: variável `report` desmembrada em
  `bundle_report` — ramo `export` — e `snapshot_report` — ramo `verify`)
- `Makefile` (Task 10 — alvos `li-equiv`, `li-equiv-up`, `li-equiv-down`)

**Adjudicação QA REQ-001 (@architect, 2026-09-03) — proveniência reivindicada, não literal:**

- `scripts/confenge_live_intelligence/public_policy.py` (`CATALOG_MODE_FIXTURE`,
  `PRODUCER_STATUS_FIXTURE`, `CATALOG_MODES`, `DEFAULT_CATALOG_MODE`, `producer_status_for()`)
- `scripts/confenge_live_intelligence/export.py` (`build_bundle`/`export_bundle` recebem
  `catalog_mode=` com default fail-closed; os três campos do manifest derivam do parâmetro;
  validação de vocabulário antes de qualquer `write`)
- `scripts/confenge_live_intelligence/cli.py` (`--catalog-mode`, eco de
  `catalog_mode`/`official_live` no payload de saída)
- `tests/confenge_live_intelligence/test_export_contract.py` (fixture `ready_bundle` passa a
  **reivindicar** `official_live`; dois testes novos: default → `fixture` com `data_state`
  intacto, e `catalog_mode` inválido → fail-closed sem diretório criado)

**Não alterados, confirmados no diff:** `targeting`, `CLAIM_POLICY`, fila, cadência do outbound,
`scripts/testing/real_db_guard.py`, migrations 104/105 (nenhum `GRANT INSERT/DELETE` adicionado).

## Definition of Done

- [x] Todos os AC1–AC11 verificados por teste automatizado (não apenas descritos). **A emenda do
  AC3 (derivação de `freshness.state`) e o esclarecimento do AC4 (`content_hash` × re-persist) são
  parte de "AC3 verificado" e "AC4 verificado"** — as asserções correspondentes na Task 11 não são
  opcionais nem um item à parte. A numeração continua AC1–AC11 por decisão do gate (emenda, não
  AC novo).
  > **Marcado pelo @po no fechamento (2026-09-03), com base na evidência do @qa, não em
  > alegação do @dev.** O gate CONCERNS rodada 1 (§1 "Rastreabilidade AC → teste que falha de
  > verdade") provou por **injeção adversarial** que os testes dos 11 ACs realmente falham
  > quando a regra é violada, e a rodada 2 re-verificou AC1/AC5 pós-emenda (`test_export_contract.py`
  > isolado = 45 passed). Nenhum AC ficou descoberto.
- [x] `test_blocked_when_watermark_is_missing` passa determinísticamente contra `extra_li_equiv`,
  asserções originais intactas, `DELETE` ainda escopado a `LI-TEST-`.
- [x] `verifier.py` prova ausência de campos/strings proibidos sobre o bundle serializado em
  disco (não sobre dict Python).
- [x] `test_export_contract.py` roda contra o contrato **vendorizado** em `docs/contracts/`
  (não contra rede nem `.campaign/`), e o `sha256` do arquivo vendorizado ainda bate com o
  registrado em `docs/contracts/confenge-live-intelligence-v1.md`.
- [x] Key-set de cada payload asserido como `payload_fields ∪ {"schema"}` (nunca igualdade crua
  contra `payload_fields`, que não contém `schema`).
- [x] `freshness.state` implementado **exatamente** conforme a fórmula da emenda do **AC3**
  (serializa → deriva das strings emitidas; `>` estrito; `min(source_as_of)`; bloco único copiado
  verbatim para manifest e todo payload; `source_as_of` ausente/não-parseável → export aborta;
  `data_state` **não** rebaixado por `STALE`), com as asserções de fronteira e concordância da
  Task 11 passando. Nenhum dos 14 códigos do contrato (`freshness_stale`, `freshness_absent`,
  `as_of_unparseable`, …) é emitido por nós — disjunção provada.
- [x] `content_hash` provado estável em dois exports **sem re-persist** (AC4, esclarecimento do
  gate); nenhum teste afirma estabilidade através de re-persist.
- [x] `extra_li_equiv` roda sob o role dedicado `li_equiv_runner`, criado e destruído **só** por
  `scripts/ops/li_equiv_db.py`; nenhuma migration ganhou `GRANT INSERT/DELETE`;
  `confenge_live_intel_reader` continua **SELECT-only** em todo database (comprovado pelos testes
  de grants da Task 11); teardown não deixa role nem database residual no cluster; grants do role
  derivados de `schema.WRITE_TARGET_ORDER`, sem segunda lista literal.
- [x] `tests/test_live_intelligence_outbound_equivalence.py` e
  `tests/confenge_live_intelligence/test_migration_grants_and_rollback.py` **parametrizados** para
  cobrir 104 **e** 105 (migrations + rollbacks), sem arquivo de teste novo para a 105 e sem
  relaxar `PROTECTED_OBJECTS`/`MUTATING`/`DML`; ciclo de rollback empilhado (104+105 → rollback
  105 → rollback 104 → resíduo → reaplicar) verde; `attacl IS NULL` nas duas colunas novas e
  `relacl` inalterado provados por asserção, não por inspeção manual.
- [x] Nenhum CNPJ cru ou mascarado — de empresa, estabelecimento **ou** comprador — em
  `companies/*.json` (AC6), provado por regex sobre o JSON serializado.
- [x] Suíte de fit passa sem alteração de asserção: a mudança de `compradores` não altera nenhum
  resultado de `dim_comparable_buyer`.
- [x] `ruff check` e `ruff format` passam nos arquivos novos/alterados. **`mypy` executado** —
  redação original superada (ver Task 12): `mypy` 2.3.1 em venv isolado, **12 erros / 6 arquivos**,
  dos quais **5 são baseline pré-existente** (`verifier.py:253/256/257/258`, `cli.py:38`) e
  **zero é novo desta story** (delta −7 do MNT-001 re-verificado pelo @qa por conteúdo; a
  adjudicação REQ-001 da v1.3 fechou com a mesma contagem, "zero erro novo"). Item **fechado**;
  a redução da baseline de 5 é dívida pré-existente, não desta story.
- [x] Migration 105 aplicada e revertida (`apply_migrations` + rollback) contra `extra_test`
  local, sem erro.
- [x] `make li-equiv` cria, roda e derruba `extra_li_equiv` de ponta a ponta sem intervenção
  manual.
- [x] QA independente (não o @dev implementador) emite veredito PASS/CONCERNS/FAIL/WAIVED.
  **Emitido: CONCERNS** (@qa Quinn, sessão distinta da do @dev, HIGH-RISK aprofundado), rodada 1
  e re-verificação escopada na rodada 2 — escopo reduzido a **1** item (PRC-001, dono @devops).
  O próprio gate declara: *"CONCERNS aqui NÃO bloqueia o fechamento do @po nem o push do @devops"*.
- [x] ~~@po reconcilia a menção de TD-LI-6 nesta story com a tabela de débitos da story irmã~~
  **Descarregado na validação (@po, 2026-09-03), não no fechamento.** TD-LI-6 é titularidade
  desta story via **AC10**; a tabela de débitos da story irmã foi ajustada (v1.2). Não reexecutar
  no `po-close-story` — ver Change Log v1.0.1 e a seção "Relação com a story de equivalência".
- [x] Nenhuma alteração em `targeting`/`CLAIM_POLICY`/fila/cadência do outbound (fora de escopo,
  confirmado no diff final).
- [x] `docs/pr-reviewability-policy.md` conferido antes do "ready": esta story toca migration +
  Makefile + runtime, ou seja **3 das 4** categorias do "multi-capability mix" — não dispara o
  gate (ele exige as 4, incluindo pack comercial), mas está a um passo. Se o escopo crescer para
  caminho de deliverable comercial, decompor o PR antes de pedir review.
  > **Qualificação obrigatória do @po no fechamento (2026-09-03).** Este item fecha **apenas
  > sob PR decomposto**. A restrição de publicação da v1.0.4 permanece **viva e não
  > descarregada**: o branch já somava ~29 arquivos / ~8008 linhas antes da implementação,
  > contra `MAX_FILES_READY=60` / `MAX_TEXTUAL_LINES_ADDED=10_000`
  > (`scripts/ops/check_pr_reviewability.py:31-32`) — folga de ~1992 linhas, insuficiente para
  > os 11 arquivos da implementação W2. **A implementação vai em PR separado.** Se @devops
  > empacotar tudo em um PR só, este checkbox volta a `[ ]` por construção.
- [x] Artefatos de docs desta rodada conferidos contra `docs/generated-artifacts-policy.md`: o
  contrato vendorizado tem 7449 bytes, muito abaixo do teto de 256 KiB para schemas/JSON de
  evidência, e `docs/**` não tem limite de linhas — **nenhuma entrada em
  `docs/generated-artifacts-exceptions.json` é necessária**.

## Rollback

- Reverter os commits aditivos desta story (nenhuma coluna/tabela existente é alterada, apenas
  colunas novas aditivas na 105 e módulos novos — reversão é remoção limpa).
- `DROP DATABASE extra_li_equiv;` no cluster de teste local (não afeta `extra_test` nem
  produção).
- Rollback da migration 105 documentado no próprio arquivo de migration (`DOWN`/seção de
  reversão, padrão já usado na 104).
- Se `orgao.cnpj` precisar ser suprimido por exigência futura do consumidor, a flag em
  `public_policy.py` é o rollback barato — não requer nova migration nem reexport retroativo do
  motor. (`compradores` já nasce sem CNPJ, AC6.)

## QA Results

### Gate Decision: **CONCERNS**

**Revisor:** @qa (Quinn) — QA independente, sessão distinta da do @dev
**Data:** 2026-09-03
**Nível:** HIGH-RISK — revisão aprofundada
**Ambiente:** PostgreSQL 16.15 real (`postgresql://test:test@127.0.0.1:5433/extra_test`),
`REQUIRE_REAL_DB=1` exportado em **todas** as invocações de pytest (sem a flag, os itens
`real_db` fazem SKIP e o relatório seria verde falso — armadilha declarada pelo próprio @dev).
**Método:** nenhum item abaixo foi aceito a partir do relatório do @dev. Cada afirmação tem
comando rodado por mim e saída real. Sondagens adversariais foram feitas chamando as funções
diretamente em script descartável — **nenhum arquivo de código da aplicação foi modificado**.

---

#### Veredito em uma linha

Os 11 ACs estão implementados e cobertos por testes que **realmente falham** quando a regra é
violada (provado por injeção adversarial, não por leitura de nome de teste). AC10/TD-LI-6, o
contrato público, a paridade de `company_digest` com o consumidor, o determinismo de replay e a
migration 105 foram verificados de forma independente e **passam**. O gate não é PASS por **dois
itens de DoD não cumpridos** (`mypy` e CodeRabbit) — sendo que o `mypy`, que o @dev declarou como
"não executado", eu **executei** e ele acusa **7 erros novos** introduzidos por esta story — mais
uma divergência real (LOW) entre a letra do AC5 e a implementação.

---

### 1. Rastreabilidade AC → teste que falha de verdade

| AC | Verificação independente | Resultado |
|---|---|---|
| AC1 | bundle real gerado por mim via CLI; `manifest.schema` presente, chave `contract` **ausente**; `index` == conjunto exato de arquivos; `test_blocked_snapshot_emits_only_the_manifest` e `test_non_exportable_state_writes_nothing` (BUILDING/SUPERSEDED) verdes | **PASS** |
| AC2 | `grep` por `v_contracts_canonical_v2`/view outbound em `export.py`: só ocorre em **docstring**; `test_export_never_reads_an_outbound_view` verde | **PASS** |
| AC3 | `build_freshness` chamada por mim na fronteira: 47h59m→FRESH, **48h exatas→FRESH**, 48h+1s→STALE, delta negativo→FRESH+`source_as_of_after_generated_at`; os 4 ramos de invariante (`None`×2, `tzinfo` ausente ×2) **abortam**; bloco `freshness` idêntico entre manifest e todo payload no bundle real | **PASS** |
| AC4 | dois exports do mesmo snapshot selado **sem re-persist**: `content_hash` idêntico nos 3 arquivos e manifest byte-a-byte idêntico | **PASS** |
| AC5 | injeção adversarial no `verifier` (ver §5) | **PASS com ressalva LOW** |
| AC6 | bundle real: `compradores: [{"buyer_digest": "be02f0a4e6f97fd8"}]`; regex de 14 dígitos e de CNPJ mascarado sobre `companies/*.json` → **zero hits**; `coverage.buyers_unhashable: 1` + `reason_codes: ["buyer_cnpj_not_hashable"]` emitidos no artefato real (seed com `buyer_cnpj` de 6 dígitos); `orgao.cnpj: "12345678000199"` presente em `opportunities/` (permitido) | **PASS** |
| AC7 | ver §3 — paridade byte-a-byte contra o `hashCnpj` do consumidor rodado em Node | **PASS** |
| AC8 | `company_ref` ausente de todo payload; `subject_key` de evento real = `company:cref1:8def98a00f44b26b792fa3dcd75f10bb`, igual ao meu cálculo independente; verifier falha fechado se `company_root8`/`company_ref` vazarem | **PASS** |
| AC9 | ver §4 — replay idempotente contra constraint real | **PASS** |
| AC10 | ver §6 — `make li-equiv` rodado por mim, 33+1 passed, teardown sem resíduo | **PASS** |
| AC11 | bundle real: `contract_version: "1.0"`, `schema: "CONFENGE_LIVE_INTELLIGENCE/1.0"` | **PASS** |

Suíte LI reproduzida por mim, número idêntico ao relatado pelo @dev:
`237 passed, 33 skipped, 1 failed` (o 1 failed é TD-LI-6 contra `extra_test`, comportamento
declarado, e passa contra `extra_li_equiv`).

---

### 2. Contrato público — key-set, listas proibidas, disjunção

`sha256` do contrato vendorizado confere: `875a999051df2134b4ee18513b1b2c5b1f1ec2d9b716096679079cd527692107`
(igual ao registrado em `docs/contracts/confenge-live-intelligence-v1.md`).

Rodado por mim sobre o bundle **serializado em disco**:

```
expected opp 16  com 18                     # payload_fields (15/17) ∪ {"schema"}
opportunities/LI-TEST-EQUIV-BID-001.json  keyset==union: True  diff: set()
companies/b1e38ce6b408a119.json           keyset==union: True  diff: set()
companies/e3a9c746f2818389.json           keyset==union: True  diff: set()
manifest: chave 'contract' presente? False
forbidden_public_language (4/4): nenhuma presente
forbidden_conclusion_fields (8/8): nenhuma presente
companies/*.json → cnpj14: []  masked: []
reason_codes emitidos ∩ os 14 do contrato = set()   # disjunção provada
```

`manifest.reason_codes` do artefato real: `["buyer_cnpj_not_hashable", "source_as_of_beyond_max_age"]`
— ambos internos, nenhum dos 14 do consumidor. `manifest.freshness.state == "STALE"` **sem**
rebaixar `data_state` (segue `DATA_READY`), exatamente como a emenda do AC3 manda.

---

### 3. `company_digest` / `company_ref` — paridade provada contra o consumidor

Não me contentei com os vetores do teste: rodei a função **real do consumidor** em Node
(`.campaign/overnight/web-cfg/scripts/conversion/cnpj.cjs`, `hashCnpj`) e comparei com o Python:

| CNPJ | `hashCnpj` (Node, consumidor) | `identity.cnpj_digest` (Python) | sha256 recalculado por mim |
|---|---|---|---|
| 11222333000181 | `b1e38ce6b408a119` | `b1e38ce6b408a119` | `b1e38ce6b408a119` |
| 00000000000191 | `9d83951eeebe7a08` | `9d83951eeebe7a08` | `9d83951eeebe7a08` |
| 12345678000195 | `d67fda759f405f42` | `d67fda759f405f42` | `d67fda759f405f42` |
| 61695227000193 | `9deb523137936cb4` | `9deb523137936cb4` | `9deb523137936cb4` |

Três fontes independentes concordam byte-a-byte. `FIXED_VECTORS` em `test_identity.py:42-46` são
**literais hardcoded**, não recomputação da implementação — a asserção é real, não `hash == hash`.
Negativos: `<14`, `>14`, `""`, `None` → todos `None`, **nunca** `""`. Pontuação aceita
(`11.222.333/0001-81` == `11222333000181`), igual ao `onlyDigits` do consumidor.

**N estabelecimentos → 1 `company_ref`:** o bundle real emitiu 2 arquivos
(`b1e38ce6b408a119`, `e3a9c746f2818389`) com o **mesmo** `perfil`/`categorias`/`faixas`/
`geografias` e `company_digest` distinto, e o único evento de empresa usa
`company:cref1:8def98a00f44b26b792fa3dcd75f10bb` — igual ao meu
`sha256("confenge-live-intelligence|company_ref|v1|11222333")[:32]`.

---

### 4. Determinismo do event feed — constraint real, não só código

Constraints verificadas no catálogo do banco (`pg_constraint`), não no SQL:

```
confenge_live_intelligence_events_pkey        :: PRIMARY KEY (event_id)
uq_live_intel_event_transition                :: UNIQUE (event_type, subject_key,
                                                          prev_semantic_hash, semantic_hash)
chk_live_intel_event_is_transition            :: CHECK (prev_semantic_hash <> semantic_hash)
chk_live_intel_event_bootstrap                :: CHECK ((prev=''AND prev_snap IS NULL) OR ...)
event_id_check                                :: CHECK (event_id ~ '^[0-9a-f]{64}$')
```

O `ON CONFLICT (event_id) DO NOTHING` está ancorado numa **PK real**. Rodei o feed duas vezes
contra o mesmo snapshot:

```
rodada 1 → 2 eventos (NEW_OPPORTUNITY bootstrap, FIT_BECAME_RELEVANT bootstrap; prev='' , prev_snapshot_id=NULL)
rodada 2 → count=2, md5(string_agg(event_id)) = 277e49000d0255841e52b21caeb47253   # nenhuma duplicação
```

Recalculei `live_hash({event_type, subject_key, prev_semantic_hash, semantic_hash})` para os dois
eventos persistidos: **MATCH** nos dois — a tupla do `event_id` é exatamente a de
`uq_live_intel_event_transition`, sem `snapshot_id`/`source_as_of`/`created_at`.

---

### 5. Sondagem adversarial do `verifier` (AC5/AC6)

Injetei payloads maliciosos e observei se o verifier **levanta**:

| Sonda | Resultado |
|---|---|
| chave `recomendacao` | **RAISE** |
| valor exatamente `"recomendacao"` (aninhado) | **RAISE** |
| valor `"should_bid"` dentro de lista/dict | **RAISE** |
| valor `"INDEX"` em `data_state` | **RAISE** |
| `manifest.index` legítimo | passa (carve-out correto) |
| `"extra-cli"` dentro de `limitations` | **RAISE** (substring) |
| `"SmartLic"` no meio de uma frase | **RAISE** (substring) |
| CNPJ cru aninhado / CNPJ mascarado | **RAISE** nos dois |
| CNPJ cru colocado **sob a chave** `company_digest` (não-hex16) | **RAISE** — a máscara valida o formato antes, não é strip cego |
| **valor `"recomendacao: forte"`** | **PASSA — não detectado** ⚠️ |

A máscara `_mask_hex_tokens` está correta e estreita: só substitui valores de chave declarada
(`company_digest`/`buyer_digest`/`content_hash`/`manifest_hash`) que **já satisfazem**
`^[0-9a-f]{16}$`/`^[0-9a-f]{64}$`. Um CNPJ (14 chars) não satisfaz nenhum dos dois, então não
existe caminho em que um CNPJ real seja engolido pela máscara. Confirmado empiricamente.
As duas listas usam modos de comparação diferentes, como declarado: `FORBIDDEN_FIELDS` por
igualdade, `FORBIDDEN_STRINGS` por substring.

---

### 6. Migrations 104+105 e DB isolado `extra_li_equiv`

**Migration 105 lida linha a linha:** puramente aditiva (`ADD COLUMN IF NOT EXISTS` ×2, 2 CHECK
idempotentes via `DO $$`, 1 índice parcial), **zero DML**, **zero objeto outbound**, e os
`REVOKE`/`GRANT` são reasserção simétrica ao padrão da 104 — **nenhum `GRANT INSERT/DELETE`**.
Rollback simétrico e idempotente. Catálogo verificado por mim em banco real:

```
pg_attribute.attacl  → company_ref: None ; observed_establishment_cnpjs: None
pg_class.relacl      → {test=arwdDxt/test, confenge_live_intel_reader=r/test}   # 'r' = SELECT-only
```

Ciclo empilhado (104+105 → r105 → r104 → resíduo → reaplicar 104+105) roda dentro de
`test_migration_grants_and_rollback.py` e **passa**; conferi depois que `company_ref` e
`observed_establishment_cnpjs` continuam existindo em `extra_test` — o defeito operacional que o
@dev relatou (reaplicar só a 104) está de fato corrigido.

**`make li-equiv` rodado por mim de ponta a ponta** (106 migrations aplicadas → 105 inclusive):

```
tests/confenge_live_intelligence/test_outbound_equivalence.py  →  33 passed
tests/.../test_producer_state_criteria.py::test_blocked_when_watermark_is_missing  →  1 passed
extra_li_equiv/li_equiv_runner removidos
```

**TD-LI-6 confirmado como fechado:** o mesmo teste falha contra `extra_test` compartilhado e passa
contra `extra_li_equiv`, com as asserções originais intactas e o `DELETE ... LIKE 'LI-TEST-%'` sem
ampliação de escopo.

**Teardown sem resíduo — verificado por consulta, não por confiança na mensagem do script:**

```
select rolname from pg_roles   where rolname   = 'li_equiv_runner'  →  []
select datname from pg_database where datname  = 'extra_li_equiv'   →  []
select count(*) from pncp_raw_bids where pncp_id like 'LI-TEST-%'   →  0
select count(*) from confenge_live_intelligence_snapshots           →  0
```

Role cluster-global não vazou. `extra_test` intacto.

---

### 7. Edge cases de segurança

- **`buyer_cnpj` com ≠ 14 dígitos:** exercitado no artefato real — comprador **omitido**,
  `coverage.buyers_unhashable: 1`, `reason_codes: ["buyer_cnpj_not_hashable"]`. Nenhum
  `buyer_digest: ""` em lugar nenhum (a função devolve `None`, provado nos 4 negativos).
- **BLOCKED:** `test_blocked_snapshot_emits_only_the_manifest` verde; BUILDING/SUPERSEDED não
  escrevem nem o manifest (fail-closed estrutural — o bundle é montado inteiro em memória antes do
  primeiro `write`).
- **Bundle sem payload (universo vazio) — o item que o @dev pediu veredito:** **concordo com a
  rota final do @dev.** O ramo de aborto da emenda do AC3 nomeia exatamente três condições
  (`generated_at` ausente, `source_as_of` ausente, `tzinfo` ausente) e nenhuma é satisfeita por um
  universo vazio; AC1 é satisfeito por `index` com zero arquivo ("nem mais, nem menos"). Recusar o
  export seria substituir a fórmula pinada por juízo próprio — a mesma classe de desvio que a
  emenda proíbe no ramo de delta negativo. A substituição de `source_as_of` por `cutoff_at` é
  **declarada** em `limitations` (`LIMITATION_NO_PAYLOAD_EMITTED`), verificado no artefato e no
  teste `test_sealed_snapshot_with_empty_universe_still_emits_a_bundle`. Fica registrado como
  **LOW** apenas o pedido de ratificação do @architect, já que a story não nomeia o caso.

---

### 8. Regressão no outbound

- Suíte estática (`test_live_intelligence_outbound_equivalence.py`, 4 caminhos SQL) e de runtime
  (`test_no_outbound_dml_static.py`, `test_no_outbound_write_runtime.py`): **verdes**. Diff
  auditado: parametrização pura, `PROTECTED_OBJECTS`/`MUTATING`/`DML` **intactos**, nenhuma
  asserção relaxada. A única mudança de mecanismo (`_strip_sql_comments` antes de buscar
  `ALTER DEFAULT PRIVILEGES`) é correção de falso positivo legítima — o comentário que **explica**
  por que a migration não emite o statement estava disparando a asserção.
- Prova de AC10 sob role restrito: `test_runner_role_has_no_write_privilege_on_outbound_object` e
  `test_runner_role_dml_on_outbound_base_table_raises` — barreira estrutural, não só asserção.
- **Suíte completa do repositório:** `10 failed, 6731 passed, 161 skipped, 2 errors`. Rodei as
  mesmas 9 falhas não-LI + 2 errors contra a **árvore de baseline extraída do HEAD `d80e7080`**
  (sem as mudanças da story): reproduzem **idênticas** (`9 failed, 2 errors`). São lacunas
  pré-existentes de ambiente (DSN com prefixo `extra_real_db_`, golden path, seed de aliases),
  **não regressão desta story**. A 10ª é TD-LI-6, já explicada.

---

### 9. Lacunas de DoD

| Item | Status verificado por mim |
|---|---|
| `ruff check` / `ruff format` | **limpo** — `All checks passed!`, `27 files already formatted` |
| `mypy` | **executado por mim** (instalei em venv isolado; `pip` do sistema é PEP-668). **NÃO passa** — ver MNT-001 |
| CodeRabbit | **`signed out`** confirmado por mim (`coderabbit auth status`). Não executável nesta sessão |

---

### Issues

| ID | Sev | Descrição | Ação |
|---|---|---|---|
| **MNT-001** | **MEDIUM** | `mypy` acusa **7 erros novos** no código desta story (baseline do HEAD nos mesmos arquivos tem 5, todos pré-existentes): `export.py:585` `no-any-return`; `cli.py:139/143/144/146/147/148` — a variável `report` é reusada entre o ramo `export` (`BundleVerificationReport`) e o ramo `verify` (`VerificationReport`), e o mypy infere o primeiro tipo. **Confirmei que não é bug de runtime**: o ramo `export` faz `return 0` antes. É higiene de tipo, mas o DoD exige `mypy` limpo e ele **não** está. | @dev: renomear a variável do ramo `export` e anotar o retorno em `export.py:585`. Custo baixo. |
| **PRC-001** | **MEDIUM** | CodeRabbit não executado (CLI `signed out`). Story HIGH-RISK com contrato público — o item Pre-PR do @devops passa a ser **obrigatório**, não opcional. | @devops: `coderabbit --prompt-only --base main` antes do PR. |
| **SEC-001** | **LOW** | `assert_no_forbidden_content` compara `FORBIDDEN_FIELDS` por **igualdade** de valor. Um valor como `"recomendacao: forte"` **não é detectado**. A `[AUTO-DECISION]` do @dev é bem fundamentada (o `disclaimer_pt` obrigatório contém a palavra `capacidade`, e substring tornaria AC5 autocontraditório com AC6/§A.4), mas a letra do AC5 diz "aparece como chave **ou valor**". Hoje nenhum caminho do produtor gera esse valor, então é risco latente, não defeito ativo. | @architect adjudica: manter igualdade (e registrar a leitura no AC5) **ou** trocar por substring com allowlist explícita da frase do disclaimer. Não bloqueia. |
| **DOC-001** | **LOW** | O tratamento de "bundle sem payload emitido" (universo vazio **e** BLOCKED) é derivado corretamente de AC1 + emenda do AC3, mas **não é nomeado por nenhum AC**. Concordo com a implementação; o que falta é ratificação. | @architect: uma linha no AC1 ou no AC3 fecha isso permanentemente. |
| **REQ-001** | **LOW** | `export.py:535` emite `"official_live": True` como **literal**, sem nenhuma condição de proveniência. A tabela §A.2 das Dev Notes diz `official_live true — só se snapshot veio do datalake real`, e o contrato traz `fixture_as_live` entre os `reject_reason_codes` e `catalog_mode.fixture: "labeled fixture; never consumed or labeled as live"`. Comprovado na prática: o bundle que gerei a partir do **seed sintético** de `extra_li_equiv` saiu rotulado `official_live: true` / `catalog_mode: "official_live"`. Defensável hoje (o producer não tem modo fixture — o seed entra em `pncp_raw_bids`, tabela real do datalake), mas a condicional de §A.2 está **não implementada** e um bundle de fixture é rotulado live por construção — exatamente o que `fixture_as_live` existe para pegar. | @architect: ou implementar a condição de proveniência, ou registrar em §A.2 que o produtor não tem modo fixture e o literal é correto. Não bloqueia. |
| **MNT-001** | ~~MEDIUM~~ **ENDEREÇADO (@dev, 2026-09-03)** — aguarda re-verificação do @qa | Os 7 erros foram corrigidos **sem alterar comportamento de runtime**. `export.py`: `export_bundle` passou a atribuir `manifest: dict[str, Any] = bundle["manifest"]` e retornar o local anotado (o `write_text` usa a mesma variável). `cli.py`: a variável `report` foi desmembrada em `bundle_report` (ramo `export`, linhas 105-107) e `snapshot_report` (ramo `verify`, linhas 139-148) — renomeação pura, nenhuma reestruturação de fluxo (indentar o ramo `verify` sob um `if` criaria um caminho sem `return` e um erro novo sob `warn_unreachable`). **Nenhum `# type: ignore`** (`warn_unused_ignores = true` transformaria um ignore redundante em erro novo). **Evidência:** `mypy` (2.3.1, venv isolado, config do `pyproject.toml`) sobre os dois arquivos — **antes: 19 erros em 7 arquivos; depois: 12 erros em 6 arquivos**, delta exato de −7. A baseline de 5 pré-existentes nos mesmos arquivos permanece intacta e fora do escopo desta story (`verifier.py:253/256/257/258`, `cli.py:38`). `ruff check` e `ruff format --check` limpos nos dois arquivos. | @qa: re-verificar e reemitir veredito. |
| **SEC-001** | ~~LOW~~ **ADJUDICADO (@architect, 2026-09-03)** — manter igualdade, **sem mudança de código** | Emenda normativa no **AC5**. A leitura "substring sobre valores" é **insatisfazível por construção**: o `disclaimer_pt` obrigatório do contrato contém a substring `capacidade`, que está em `forbidden_conclusion_fields` — todo bundle conforme falharia a própria verificação. Corrigida também a premissa do encaminhamento: **existem** campos de texto livre (`objeto`, `orgao.nome`, `perfil.razao_social`), mas são `FACT` de autoria de **terceiros**; varrê-los por substring negaria publicação de dado público legítimo ou incentivaria sanear um campo `FACT` — violação pior que o risco evitado. Residual aceito **com tripwire**: se algum campo de texto livre de autoria **própria** entrar num payload, a decisão é reaberta. | Fechado. Nenhuma ação para @dev. |
| **DOC-001** | ~~LOW~~ **RATIFICADO (@architect, 2026-09-03)** — **sem mudança de código** | Ratificação no **AC1**, nomeando os **dois** sub-casos (BLOCKED e universo legitimamente vazio em READY/PARTIAL) como **um único** caminho: export prossegue, `index` com zero arquivo satisfaz "nem mais, nem menos", `freshness` cai no `cutoff_at` do snapshot e a substituição é declarada em `limitations` via `LIMITATION_NO_PAYLOAD_EMITTED`, **sem reason_code novo**. A rota do @dev, com a qual o @qa concordou, está ratificada como está. | Fechado. Nenhuma ação para @dev. |
| **REQ-001** | ~~LOW~~ **ENDEREÇADO (@architect, 2026-09-03)** — **código alterado**, exige re-verificação do @qa | Emenda normativa no **AC1** + implementação. `official_live` deixa de ser literal: `catalog_mode` vira parâmetro de `build_bundle`/`export_bundle` e do CLI (`--catalog-mode`), vocabulário fechado `{fixture, official_live}`, **default fail-closed `fixture`**, com `official_live`/`producer_status` **derivados** dele. O bundle que o @qa gerou do seed agora sai `catalog_mode: "fixture"` / `official_live: false`, recusado pelo consumidor por `producer_status_not_official_live`. **Rejeitado** gatilhar por `state` do snapshot (proveniência e completude são eixos independentes — mesma doutrina de `freshness.state` × `data_state`) e **rejeitado** vetar por marcador de seed (`LI-TEST-` está em todo seed do repo; o veto tornaria o AC1 inverificável). Limite declarado: é **reivindicação**, não verificação de origem — coluna de proveniência exigiria migration 106, fora de escopo. Arquivos: `public_policy.py`, `export.py`, `cli.py`, `test_export_contract.py` (+2 testes novos). Evidência: `234 passed / 33 skipped / 1 failed` (o failed é TD-LI-6, idêntico à baseline do @qa); `ruff` limpo; `mypy` **12 erros / 6 arquivos**, exatamente a baseline pós-MNT-001 — **zero erro novo**. | @qa: re-verificar AC1/AC5 e reemitir veredito. |
| **ENV-001** | **LOW** | Rodar a suíte completa reescreve artefatos versionados (`artifacts/predictive/*`, `docs/ops/campaigns/*`). **Pré-existente** — já estava no `git status` antes desta revisão. Fora do escopo da story; registrado para o @devops não confundir com entrega. | @devops: não incluir no PR desta story. |

---

### Riscos residuais aceitos (não são issues)

- `buyer_digest` é reversível por força bruta sobre os `orgao.cnpj` das `opportunities/` do mesmo
  bundle — **efeito declarado e aceito no AC6**, sobre entidades públicas. A proteção que o
  contrato exige é sobre o CNPJ do **visitante**, e essa permanece absoluta: nenhum CNPJ de
  empresa/estabelecimento existe no bundle, em nenhuma forma.
- Re-persist do mesmo `snapshot_id` muda `cutoff_at` → muda `freshness` → muda todo
  `content_hash`. Churn de cache do consumidor, **não** de evento (`semantic_hash` não contém
  `freshness`). Esclarecimento do gate sistêmico, respeitado pelos testes — nenhum teste afirma
  estabilidade **através** de re-persist.

---

### Verificações extras que voltaram limpas (registro explícito, não omissão)

- **`min(source_as_of)` não é prova vácua.** O fixture `ready_bundle` usa watermarks
  **distintos** (`opportunity = UTC_NOW`, `company = UTC_NOW + 3h`), e
  `test_manifest_source_as_of_is_the_min_over_emitted_payloads` ainda traz guarda anti-vacuidade
  explícita (`assert len(watermarks) >= 2, "prova vacua: um unico watermark nao distingue min de max"`).
  A asserção **discrimina**: trocar `min` por `max` a quebra. (O bundle que eu gerei manualmente
  tinha watermark único, então **não** serviria como prova — por isso fui ao fixture.)
- **Máscara hexadecimal do `verifier` não é strip cego.** Confirmado por sonda: um CNPJ cru posto
  **sob a chave** `company_digest` é detectado, porque o formato é validado antes de mascarar.

### Estado operacional — item de handoff (fora da minha autoridade)

`.aiox/state/stories/` contém **apenas** `confenge-live-intelligence-01.json`, que é o state da
story **anterior** (motor W1: `status=Done`, `qa_verdict=CONCERNS`, `po_closed=true`,
`reviewed_commit=a0b99fd6`, já publicada). **Não existe state file para esta story W2.** Como a
publicação é evidence-based sobre esse arquivo (§8 do protocolo: `qa_verdict`, `gates`,
`reviewed_commit === HEAD`, `publication_authorized`), @po/@devops precisam criar o state desta
story antes do `po-close-story`/push. Não escrevi nada em `.aiox/state/` — minha autoridade é a
seção QA Results.

**Aviso sobre `reviewed_commit`:** esta revisão foi feita sobre a **árvore de trabalho não
commitada** (`HEAD = d80e7080`; todo o código da story está `M`/`??`). Quem commitar precisa saber
que a evidência de QA antecede o hash do commit — se houver qualquer alteração de código depois
deste gate, a evidência **não** cobre o commit resultante e o gate precisa ser reexecutado.

### Encaminhamento

**CONCERNS** — a story **não retorna ao início do ciclo**. O trabalho substantivo está correto,
provado e sem regressão. Para virar PASS:

1. @dev corrige **MNT-001** (7 erros de `mypy`) — mudança mecânica, sem tocar comportamento.
2. @devops executa **PRC-001** (CodeRabbit Pre-PR) — obrigatório por ser HIGH-RISK com contrato
   público.
3. @architect adjudica **SEC-001** e **DOC-001** — nenhum dos dois bloqueia publicação.

Se o @po decidir fechar com CONCERNS, MNT-001 e PRC-001 devem ir para o backlog **com dono e
prazo**, não como observação. `data_state` do gate: nenhum AC está descoberto, nenhuma asserção
foi relaxada, nenhum teste é decorativo.

### Para o @qa — o que verificar primeiro (do @dev)

1. **Ambiguidade 1 das Completion Notes** — o tratamento de bundle sem payload emitido
   (`BLOCKED` **e** universo vazio) é derivado do texto do AC1 + emenda do AC3, mas a story
   não trata o caso explicitamente. Merece veredito. Se o @architect entender que um catálogo
   vazio **não** deve ser publicável, a mudança é de uma linha (`raise` no ramo
   `no_payload_emitted`) e um teste.
2. **`mypy` não foi executado** (não instalado no ambiente). Item do DoD **não verificado**.
3. **`test_blocked_when_watermark_is_missing` falha contra `extra_test` e passa contra
   `extra_li_equiv`** — é o comportamento declarado de TD-LI-6, não uma regressão. Rodar
   `make li-equiv` para confirmar.
4. **Nenhuma asserção existente foi relaxada.** `PROTECTED_OBJECTS`, `MUTATING`, `DML` e o
   `DELETE ... LIKE 'LI-TEST-%'` estão intactos. A única mudança de mecanismo em teste
   existente é a remoção de comentário SQL antes da busca por `ALTER DEFAULT PRIVILEGES`
   (falso positivo: a própria explicação em comentário disparava a asserção na 105).

---

## QA Results — Re-verificação escopada (rodada 2)

### Gate Decision: **CONCERNS** (mantido, com escopo reduzido a **1** item)

**Revisor:** @qa (Quinn) — mesma autoridade, sessão distinta do @dev e do @architect
**Data:** 2026-09-03
**Escopo:** re-verificação **escopada**, não o gate inteiro. Verifiquei apenas o que mudou desde
a rodada 1 (MNT-001, REQ-001) e o que precisava de ratificação sem código (SEC-001, DOC-001),
mais uma prova de **não-regressão por confinamento** sobre o que já estava aprovado.
**Ambiente:** PostgreSQL 16.15 real (`postgresql://test:test@127.0.0.1:5433/extra_test` e
`extra_li_equiv`), `REQUIRE_REAL_DB=1` em **todas** as invocações de pytest.
**Método:** nenhum item aceito a partir do relatório do @dev ou do @architect. Cada afirmação
abaixo tem comando rodado por mim e saída real. Sondas adversariais em script descartável, já
removido — **nenhum arquivo de código da aplicação foi modificado**.

---

### 1. MNT-001 — `mypy` (MEDIUM) → **RESOLVIDO**

Invocação exata (a contagem depende dela; registro para ninguém ler "12" fora de contexto):

```
mypyvenv/bin/mypy scripts/confenge_live_intelligence/ scripts/ops/li_equiv_db.py
→ Found 12 errors in 6 files (checked 13 source files)     [mypy 2.3.1, config do pyproject.toml]
```

Confirmado: **12 erros / 6 arquivos**, exatamente o reportado. Mas o número não é a prova — a
prova é o **conteúdo do delta**, que também confirmei:

| Arquivo | Rodada 1 (@qa) | Agora | Leitura |
|---|---|---|---|
| `export.py` | `:585 no-any-return` | **zero erros** | corrigido |
| `cli.py` | `:38` (baseline) + `:139/143/144/146/147/148` (6 novos) | **apenas `:39 no-untyped-def`** (`_connect`) | os 6 novos sumiram; a baseline apenas **deslocou +1 linha** por causa do novo `import public_policy as policy` |
| `verifier.py` | `:253/256/257/258` (baseline) | `:253/256/257/258` | **byte-estável**, intocado |

Delta exato **−7**, baseline de 5 pré-existentes nos arquivos da LI intacta. Os 7 erros restantes
estão em `scripts/crawl/observation_lineage.py`, `scripts/confenge_activation/commercial_authority_v2.py`,
`scripts/contracts_truth.py` e `scripts/confenge_account_intelligence/message_spine.py` — todos
pré-existentes e fora do escopo desta story. **Zero `# type: ignore` introduzido.**

`ruff check` e `ruff format --check` sobre `scripts/confenge_live_intelligence/` e
`tests/confenge_live_intelligence/`: `All checks passed!` / `26 files already formatted`.

### 2. Suíte — **CONFIRMADA**, e o único failure é mesmo TD-LI-6

```
REQUIRE_REAL_DB=1 pytest tests/confenge_live_intelligence/ \
  tests/test_live_intelligence_outbound_equivalence.py tests/test_apply_migrations.py
→ 1 failed, 239 passed, 33 skipped in 6.33s
```

O `239` reconcilia com o `234` do @architect: ele não incluiu `tests/test_apply_migrations.py`
(5 testes). O único failure é
`test_producer_state_criteria.py::test_blocked_when_watermark_is_missing`
(`assert 'READY_CANONICAL' == 'BLOCKED'`) — **TD-LI-6, comportamento declarado**, não regressão.

`make li-equiv` rodado por mim, ponta a ponta:

```
migrations_ok mode=upgrade applied=106 skipped=0 repaired=0   (inclui 104 e 105)
tests/confenge_live_intelligence/test_outbound_equivalence.py → 33 passed
test_producer_state_criteria.py::test_blocked_when_watermark_is_missing → 1 passed
extra_li_equiv/li_equiv_runner removidos
```

Confirmado: **o teste que falha contra `extra_test` passa contra `extra_li_equiv`.** É exatamente
a assinatura de TD-LI-6, e o teardown do banco isolado funciona.

`test_export_contract.py` isolado: **45 passed** — bate com o relatado.

### 3. REQ-001 — `catalog_mode`/`official_live` (LOW) → **RESOLVIDO, provado no caminho que falhou**

Não usei os testes do @architect como evidência. Reproduzi **o mesmo caminho da rodada 1**: seed
sintético em `extra_li_equiv` (`LI-TEST-REQA-001` em `pncp_raw_bids`), `build_snapshot` →
`STATE=READY_CANONICAL`, `snapshot_id=LI-2026-09-03-43eab62befac66c392521b2848fb8bd3`, e exportei
o **mesmo snapshot** três vezes pelo CLI real.

**(a) Default (sem `--catalog-mode`) — era este o bundle que na rodada 1 saiu `official_live: true`:**

```
{'schema': 'CONFENGE_LIVE_INTELLIGENCE/1.0', 'catalog_mode': 'fixture',
 'official_live': False, 'producer_status': 'fixture',
 'data_state': 'DATA_READY', 'contract_version': '1.0'}
```

O default **é** fail-closed. O bundle da rodada 1 (seed sintético rotulado live) **não é mais
gerável por acidente** — só sob reivindicação deliberada. E `data_state` permanece `DATA_READY`:
proveniência **não** rebaixou completude, os eixos são independentes como a emenda manda.

**(b) `--catalog-mode official_live`, mesmo snapshot:**

```
{'catalog_mode': 'official_live', 'official_live': True,
 'producer_status': 'official_live', 'data_state': 'DATA_READY'}
'contract' in manifest → False    (AC1: a chave de envelope é `schema`, sem alias)
```

`official_live` e `producer_status` são **derivados** do único parâmetro, coerentes entre si.

**(c) Fail-closed, nos dois níveis.** CLI: `--catalog-mode live` é recusado pelo próprio argparse
(`invalid choice: 'live' (choose from 'fixture', 'official_live')`), diretório de saída **não
criado**. API (contornando o argparse, que é onde um chamador programático entraria) — sondei
cinco variantes:

```
'live'          → LiveIntelligenceExportError | dir criado? False
'OFFICIAL_LIVE' → LiveIntelligenceExportError | dir criado? False
''              → LiveIntelligenceExportError | dir criado? False
None            → LiveIntelligenceExportError | dir criado? False
'Fixture'       → LiveIntelligenceExportError | dir criado? False
```

Vocabulário fechado e **case-sensitive**, sem coerção silenciosa. A validação está em
`build_bundle` (`export.py:376`), que roda **antes** do `root.mkdir` de `export_bundle`
(`export.py:610` → `:612`) — nenhum arquivo no disco quando o rótulo é inválido.

**Direção inversa da independência dos eixos, fechada por construção (não é lacuna de cobertura).**
Provei empiricamente `fixture` + `DATA_READY`. O caso `official_live: true` com
`data_state: "DATA_REJECT"` não precisa de teste porque a derivação é uma linha só —
`official_live = catalog_mode == policy.CATALOG_MODE_OFFICIAL_LIVE` (`export.py:380`) — e **não
recebe o `state` do snapshot como entrada**. O acoplamento que a emenda proíbe é estruturalmente
impossível, não apenas não-observado.

**Superfície de chamada auditada.** `grep` por chamadores de `export_bundle`/`build_bundle` fora
de testes: **um único** em produção, `scripts/confenge_live_intelligence/cli.py:107`, que propaga
`args.catalog_mode` com default `fixture`. Não existe segundo caminho capaz de emitir um bundle
rotulado live sem reivindicação. (`scripts/contract_publication/cli.py` tem um `export_bundle`
homônimo de outro módulo, com seu próprio `claimed_live` — não relacionado.)

### 4. AC1 e AC5 pós-emenda — **SATISFEITOS**

**AC1** — reli as duas emendas do @architect (proveniência reivindicada; ratificação de bundle sem
payload). Tudo o que o AC1 exige está verificado acima: envelope `schema` sem alias `contract`,
`contract_version="1.0"`, `catalog_mode` parâmetro com vocabulário fechado e default fail-closed,
`official_live`/`producer_status` derivados, erro antes de qualquer `write`, independência de
eixos. As asserções obrigatórias que a emenda nomeia existem e discriminam
(`test_export_without_an_explicit_claim_is_labeled_fixture`,
`test_invalid_catalog_mode_fails_closed`, `test_ready_snapshot_emits_data_ready_envelope`) — as
45 do arquivo passam. A ratificação DOC-001 não pediu mudança de código e a rota implementada
continua como o @qa já havia validado.

**AC5** — a emenda diz: **igualdade** para `FORBIDDEN_FIELDS`, **substring** para
`FORBIDDEN_STRINGS`. Verifiquei no código (`verifier.py:429-450`) que é exatamente isso:
`field_name == key.lower()` e `field_name == token.strip().lower()` (igualdade, chave **e**
valor), `forbidden.lower() in serialized.lower()` (substring) para o jargão interno, e o `INDEX`
tratado como valor de enum e não como o campo `manifest.index`. **Nenhuma mudança de código foi
feita nem era necessária** — a emenda ratifica o comportamento existente, e o texto do AC5 agora
descreve o que o código faz. A contradição que eu havia apontado (letra do AC5 × implementação)
está fechada no lado da norma, que era onde ela cabia.

### 5. Confinamento — nada do que já estava aprovado foi tocado

Quatro provas independentes, não uma:

1. **mtime.** `find scripts tests db -newermt "2026-09-03 02:40" -type f \( -name "*.py" -o -name "*.sql" \)`
   retorna **exatamente** `export.py`, `cli.py`, `public_policy.py`, `test_export_contract.py`.
   Nenhum `.sql`, nenhuma migration.
2. **`verifier.py` é byte-estável.** Os erros de `mypy` estão em `253/256/257/258` nas **duas**
   rodadas. Um arquivo editado nessa região teria deslocado as linhas.
3. **`cli.py` deslocou exatamente +1** (`:38` → `:39`), consistente com o único `import` novo, e
   `export.py` moveu o bloco de proveniência de `:535` (literal) para `:558-562` (derivação),
   drift compatível com parâmetro + docstring, não com reestruturação.
4. **`grep -rln catalog_mode`** não retorna `identity.py`, `events.py`, `verifier.py`,
   `producer.py` nem `schema.py`.

Consequência: contrato/key-set, `company_digest`/`company_ref` (AC7/AC8), determinismo do event
feed (AC9), `freshness` 48h (AC3), migrations 104+105 e a equivalência `extra_li_equiv` (AC10)
seguem cobertos pela evidência da rodada 1, e a suíte verde acima (239 passed + 33 na li-equiv)
confirma que continuam verdes. `FRESHNESS_MAX_AGE_HOURS = 48` intacto em `public_policy.py:183`.
AC2/AC3 re-conferidos por amostragem: o espião de conexão (`test_export_reads_no_outbound_object`)
não vê nenhuma view outbound, e `test_export_source_has_no_wall_clock_call` continua
discriminante — a única ocorrência de `datetime.now(` em `export.py` está em **docstring**
(`:16`), e o teste remove docstrings e comentários antes de assertar.

### 6. Higiene de working tree

`git status` (tracked) idêntico à baseline **ENV-001** da rodada 1 — as minhas execuções foram
escopadas aos diretórios da LI e **não** produziram churn novo em `artifacts/predictive/*` nem em
`docs/ops/campaigns/*`. @devops não recebe sujeira adicional para separar.
Sondas descartáveis e bundles gerados foram removidos; `extra_li_equiv`/`li_equiv_runner`
derrubados ao final.

---

### Issues — estado consolidado

| ID | Sev | Estado | Dono |
|---|---|---|---|
| **MNT-001** | MEDIUM | ✅ **RESOLVIDO** — re-verificado por mim (`mypy` 12/6, delta −7 confirmado por conteúdo) | fechado |
| **REQ-001** | LOW | ✅ **RESOLVIDO** — re-verificado por mim no mesmo caminho que falhou na rodada 1 | fechado |
| **SEC-001** | LOW | ✅ **FECHADO** por adjudicação do @architect (AC5), sem mudança de código — leitura conferida contra `verifier.py` | fechado |
| **DOC-001** | LOW | ✅ **FECHADO** por ratificação do @architect (AC1), sem mudança de código | fechado |
| **PRC-001** | MEDIUM | ⏳ **ABERTO — único item restante** | **@devops** |
| **ENV-001** | LOW | ⏳ pré-existente, fora do escopo da story | @devops (não incluir no PR) |

### Por que CONCERNS e não PASS

Porque o critério de PASS foi escrito por mim na rodada 1 e ainda não foi cumprido: *"Para virar
PASS: (1) @dev corrige MNT-001; (2) @devops executa PRC-001 (CodeRabbit Pre-PR) — **obrigatório**,
não opcional; (3) @architect adjudica SEC-001 e DOC-001."* Os itens (1) e (3) estão fechados e
re-verificados. O item (2) **não**. Emitir PASS agora seria revisar em silêncio uma barra que eu
mesmo registrei uma rodada atrás — e não custaria menos: pelo §8 do protocolo, publicação é
evidence-based e aceita `qa_verdict` **PASS, CONCERNS ou WAIVED**.

**CONCERNS aqui NÃO bloqueia o fechamento do @po nem o push do @devops.** É um rótulo honesto de
que uma verificação obrigatória do gate HIGH-RISK ainda não rodou, não um veto. O trabalho
substantivo está correto, provado e sem regressão: nenhum AC descoberto, nenhuma asserção
relaxada, nenhum teste decorativo.

**Encaminhamento — um único passo:** @devops roda
`coderabbit --prompt-only --base main` no Pre-PR. Se voltar limpo (ou só com achados
não-CRITICAL), PRC-001 fecha e o veredito equivale a PASS sem nova rodada de @qa. Se voltar com
CRITICAL, retorna ao @dev e o gate é reaberto.

### Aviso sobre `reviewed_commit` — provou-se load-bearing

Na rodada 1 registrei que o gate era sobre a **árvore de trabalho não commitada** e que qualquer
alteração de código posterior invalidaria a evidência. Foi exatamente o que aconteceu, e é por
isso que esta re-verificação existe. Restabelecendo com os fatos atuais:

- `HEAD = d80e7080`; todo o código da story continua `M`/`??` — **nada commitado**.
- Esta re-verificação cobre a árvore de trabalho **como está agora**. Qualquer edição de código
  posterior a este bloco invalida também este gate.
- **Continua não existindo state file para a W2** em `.aiox/state/stories/` (só o
  `confenge-live-intelligence-01.json`, da story anterior). Como a publicação é evidence-based
  sobre esse arquivo (`qa_verdict`, `gates`, `reviewed_commit === HEAD`,
  `publication_authorized`), @po/@devops precisam criá-lo antes do `po-close-story`/push. Não
  escrevi em `.aiox/state/` — minha autoridade é a seção QA Results.

---

### Transição de status — InReview → **Done** (@qa, Quinn, 2026-09-03)

**Ato formal devido, não uma nova rodada de gate.** O veredito desta story é **CONCERNS**
(rodada 2, escopo reduzido a PRC-001). `story-lifecycle.md` é explícito: *"PASS, CONCERNS, and
WAIVED move the story to `Done`"* e *"@qa MUST update the story status and Change Log before
reporting the gate result"*. Eu emiti o veredito e **não** registrei a transição — a omissão é
minha, e é ela que este bloco corrige. O @po agiu corretamente ao não executá-la:
`po-close-story.md` lista "Setting or rewriting story Status" em Forbidden.

**Provenência verificada antes de registrar** (o gate da rodada 2 cobre a árvore de trabalho, e
eu mesmo declarei que qualquer edição de código posterior o invalidaria):

| Verificação | Resultado |
|---|---|
| `git status` do worktree | nenhum arquivo de código adicionado, removido ou renomeado em relação ao gate |
| `mtime` dos **25** `scope_files` | código mais recente = `03:03:35` (`cli.py`, `public_policy.py`, `test_export_contract.py`); escritas posteriores são só `docs/stories/` `03:21:41` e `.aiox/state/` `03:25:22`, ambas do @po |
| `ruff check` + `ruff format --check` (LI + `li_equiv_db.py`) | `All checks passed!` / `26 files already formatted` — **contador idêntico** ao da rodada 2 |
| `test_export_contract.py` | **45** testes coletados — idêntico ao da rodada 2 |

O `mtime` sozinho seria ordenação inferida; as duas últimas linhas são reprodução **por
conteúdo** de afirmações do meu próprio bloco da rodada 2. **O aviso de invalidação não foi
acionado: o gate permanece válido.**

**O que Done NÃO significa aqui — e a distinção é load-bearing:**

- **PRC-001 continua ABERTO.** Done reflete o veredito de qualidade; não fecha o item de
  publicação. Dono: @devops.
- **`publication_authorized` continua `false`**, por dois motivos independentes e cada um
  suficiente: (1) o CodeRabbit Pre-PR não rodou; (2) **não há commit** — `HEAD = d80e7080` é
  anterior à implementação, logo `reviewed_commit === HEAD` (§8) é insatisfazível por construção.
  Done **não** é autorização de push.
- **`po_closed` continua `false`** — é campo do @po. Não o promovo em nome de outro agente.
- **Se o CodeRabbit voltar com CRITICAL**, a correção entra como **nova story**, não como
  reversão `Done → InProgress` (§11 do protocolo bloqueia essa transição). Registro isto
  explicitamente para que ninguém tente reabrir por regressão de status.

**Próximo agente: @po** (promover `po_closed`), depois @devops (commitar filtrando ENV-001 →
CodeRabbit Pre-PR → decompor o PR → `publication_authorized`).
