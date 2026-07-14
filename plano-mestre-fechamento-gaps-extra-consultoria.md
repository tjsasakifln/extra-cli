# Plano mestre para fechamento dos gaps do repositório `extra-consultoria`

**Base da avaliação:** estado atual do repositório `tjsasakifln/extra-consultoria`, artefatos operacionais QW-01 de 13/07/2026, proposta comercial da EXTRA EMPREITEIRA E CONSTRUTORA e planilha canônica de 2.085 instituições, das quais 1.093 estão no raio de 200 km.

## 1. Escopo operacional definitivo

O sistema é uma ferramenta pessoal de apoio à consultoria. Nesta fase, deve fazer quatro coisas e somente quatro coisas:

1. localizar e manter atualizados editais de licitações abertas;
2. consolidar contratos históricos dos últimos três anos;
3. mapear concorrentes com base em resultados e contratos efetivamente identificados;
4. produzir referências de valores com semântica rigorosa, distinguindo valor estimado, homologado, contratado e pago.

Acompanhamento físico, financeiro ou documental de obras em execução está fora do escopo. Não implementar diário de obra, medição, avanço físico, fotos, fiscalização, aditivos de execução, gestão de riscos de obra ou qualquer módulo semelhante.

A infraestrutura-alvo futura é uma VPS Hetzner com Supabase/PostgreSQL self-hosted e agendamentos assíncronos. Isso não é requisito desta etapa. A etapa atual deve permanecer local-first, com PostgreSQL local, armazenamento bruto local e execução manual/reproduzível. A migração para VPS só poderá começar depois de todos os gates analíticos e de dados deste documento passarem.

---

# 2. Veredito sobre a capacidade atual

## 2.1 Universo-alvo

**Estado:** próximo de pronto.

A planilha foi corretamente elevada a autoridade do universo. Ela contém 2.085 linhas válidas, 1.093 instituições dentro do raio e nenhuma decisão de raio pendente. O módulo `scripts/lib/universe.py` preserva raízes de CNPJ duplicadas, calcula identidade estável e impede que o flag antigo do banco seja usado como denominador.

**Gap restante:** essa verdade ainda não foi adotada por todo o código. `scripts/consulting_readiness.py` mantém outro carregador de universo e várias consultas ainda filtram `sc_public_entities.raio_200km`, flag que já divergiu da planilha. Toda métrica deve usar o mesmo snapshot canônico.

## 2.2 Editais abertos

**Estado:** crawler PNCP auditável, radar final ainda não confiável.

A execução QW-01 completou as 19 modalidades do endpoint PNCP de propostas abertas e recebeu 34 registros atuais. Porém o radar exportou 673 registros porque consulta todos os itens antigos que continuam com `is_active = TRUE`. O pipeline atual atualiza os 34 vistos, mas não inativa itens ausentes de um snapshot PNCP completo. Assim, 639 registros exibidos não foram reconfirmados na execução corrente.

O radar também é PNCP-only. Os demais canais estão cadastrados, mas não foram provados ponta a ponta. Além disso, somente 20,95% das 673 linhas exportadas tinham link oficial, o perfil comercial está quase todo sem parametrização e a story QW-01 ainda está `InReview`, com QA pendente e gates não executados no próprio artefato.

**Conclusão:** usar apenas como exploração e fila de revisão manual. Não usar como lista autônoma de editais efetivamente abertos até implementar reconciliação de snapshot.

## 2.3 Contratos históricos

**Estado:** parcial e semanticamente útil, mas incompleto.

Há milhões de contratos PNCP e views para histórico de três anos. O manifest disponível encontrou presença de contratos em 404 dos 1.093 entes, 36,98%. Esse percentual não significa automaticamente falha de cobertura, porque muitos entes podem legitimamente não ter contratos no período. O problema é que ainda não existe prova completa, fresca e por ente de que os demais 689 foram consultados com sucesso e retornaram zero.

O crawler de contratos possui outro problema: em `backfill_3y`, uma janela com páginas parcialmente coletadas pode ser registrada como concluída quando houve erro depois de obter algum dado. O upsert legado também usa `DO NOTHING`, impedindo atualização de contratos alterados posteriormente.

## 2.4 Concorrentes

**Estado:** vencedores históricos parciais, não inteligência competitiva concluída.

É possível listar fornecedores vencedores, quantidade de contratos, valor global, órgãos atendidos e ticket contratual. Isso não equivale a:

- conjunto completo de concorrentes participantes;
- taxa de vitória;
- deságio habitual;
- contratos ativos;
- capacidade operacional disponível.

O código recente de market share, award share e HHI também usa nomes de colunas incompatíveis com o schema operacional documentado em `db/migrations/026_contract_intel_truth_v1.sql`. Essas métricas precisam ser tratadas como não validadas até passarem em PostgreSQL real.

## 2.5 Preços praticados

**Estado:** não implementado.

O sistema tem valor estimado de alguns editais e valor global de contratos. Isso permite medir ticket estimado ou ticket contratado. Não permite chamar o resultado de “preço real praticado por tipo de obra”.

Para cumprir a proposta, é necessário ligar o mesmo certame e, idealmente, o mesmo item ou lote entre:

- valor estimado;
- valor homologado;
- valor contratado;
- valor pago.

Percentis de valores globais de contratos heterogêneos não são preço de mercado. Uma escola de R$ 8 milhões e uma pintura de R$ 80 mil não se tornam comparáveis porque ambas caíram na categoria “OBRAS”.

## 2.6 Infraestrutura

**Estado:** suficiente para implementação local.

PostgreSQL local é adequado. Hetzner, Supabase self-hosted e cron não fecham nenhum gap analítico. Migrar agora apenas tornaria automática a produção de dados ainda inconsistentes.

---

# 3. Definição obrigatória de “95% de cobertura”

Eliminar qualquer métrica global ambígua. O sistema deve publicar métricas independentes.

## 3.1 Cobertura de resolução do universo

```text
universe_resolution =
entes com decisão de raio e identidade válida
/
total de linhas válidas da planilha
```

Gate: **100%**. O valor atual é 100%.

## 3.2 Cobertura de aplicabilidade de fontes

```text
source_applicability_resolution =
pares ente × fonte × capacidade classificados como
applicable ou not_applicable
/
total de pares que precisam de decisão
```

Gate: **100%**. `unknown` não conta.

## 3.3 Cobertura de investigação por capacidade

Para cada capacidade (`open_tenders`, `historical_contracts`, `competitors`, `prices`):

```text
capability_monitoring_coverage =
entes aplicáveis com ao menos uma combinação de fontes obrigatórias
consultada integralmente, fresca e sem blocker
/
entes aplicáveis
```

Gate: **>= 95%**.

Uma consulta com zero registros conta como coberta somente quando:

- a fonte é aplicável;
- todo o escopo esperado foi executado;
- a paginação foi comprovadamente concluída;
- o período está registrado;
- o resultado foi persistido como `success_zero`;
- a execução está dentro da janela de freshness.

## 3.4 Presença de dados

```text
data_presence =
entes com ao menos um registro encontrado
/
entes aplicáveis
```

É métrica descritiva. Nunca deve ser usada como sinônimo de cobertura.

## 3.5 Completude de campos

Medir por tipo de registro. Exemplo para editais:

- identidade oficial;
- órgão canônico;
- objeto;
- modalidade;
- data de encerramento;
- status;
- URL oficial;
- valor estimado;
- data de última verificação;
- fonte e run_id.

Gate para campos essenciais: **>= 95%**. URL oficial e encerramento futuro devem ser obrigatórios para exibir uma oportunidade como acionável.

## 3.6 Frescor

- editais abertos: máximo de 24 horas;
- status de oportunidade prioritária: reconfirmação na execução mais recente;
- contratos históricos: backfill integral + incremental diário ou semanal;
- concorrentes: derivado da última carga contratual completa;
- preços: derivado da última carga de resultados, contratos e pagamentos disponível.

## 3.7 Cobertura de snapshot ativo

```text
active_snapshot_integrity =
registros exibidos como ativos que foram vistos no último snapshot completo
ou reconfirmados individualmente depois dele
/
registros exibidos como ativos
```

Gate: **100%**.

## 3.8 Validação de recall

Criar amostra-ouro estratificada por município, natureza jurídica e fonte. Comparar o sistema com a listagem oficial da fonte para a mesma data/período.

Gate: **recall >= 95%** para editais relevantes e **zero falsos “abertos”** na amostra prioritária.

---

# 4. Ordem obrigatória de execução

1. corrigir schema e autoridade do universo;
2. corrigir reconciliação de editais PNCP;
3. provar um fluxo completo local, do crawl ao relatório;
4. fechar contratos históricos e atualização;
5. fechar concorrentes;
6. implementar preço praticado;
7. provar cobertura multicanal;
8. gerar relatório final;
9. somente então desenhar deploy Hetzner/Supabase.

Nenhuma tarefa posterior pode mascarar blocker de uma tarefa anterior.

---

# 5. EPIC P0-01 — Congelar escopo e limpar a documentação

## Objetivo

Eliminar promessas, métricas e arquiteturas contraditórias.

## Implementações

- Atualizar `README.md`.
- Atualizar `docs/prd/PRD-consultoria-extra.md`.
- Atualizar `docs/decisions/contract-intelligence-truth-v1.md`.
- Atualizar `docs/decisions/adr-002-preco-praticado.md`.
- Marcar acompanhamento de obras explicitamente como `OUT_OF_SCOPE`.
- Remover ou corrigir números antigos de universo, cobertura e unresolved.
- Separar em cada documento:
  - `CURRENT_STATE`;
  - `TARGET_STATE`;
  - `KNOWN_BLOCKERS`;
  - `PROHIBITED_CLAIMS`.
- Não declarar PostgreSQL Hetzner, Supabase ou timers como realidade atual.
- Não declarar fonte como “ativa” apenas porque existe módulo Python.
- Não declarar preço praticado, deságio, win rate ou contratos ativos sem dados adequados.
- Transformar `docs/stories/epics/epic-master-b2g/story-FIX-SCHEMA-MISMATCH.md` em registro histórico ou reescrevê-la, pois ela contradiz o schema operacional posterior.

## Critérios de aceite

- Uma busca no repositório por números antigos de cobertura não encontra afirmações conflitantes.
- `README`, PRD, manifests e relatórios usam o mesmo total de 1.093 entes no raio para a seed corrente.
- Toda capability tem status `READY`, `PARTIAL`, `NOT_READY` ou `BLOCKED`.
- Nenhum documento mistura data presence com operational coverage.

---

# 6. EPIC P0-02 — Unificar o schema de banco

## Problema

Há pelo menos três verdades concorrentes:

- migrations antigas em `db/migrations`;
- migrations em `supabase/migrations`;
- dump `supabase/current-schema.sql`, extraído antes das migrations 026–029;
- schema operacional real usado pelas views Contract Intelligence Truth v1.

Isso já produziu queries com nomes incompatíveis.

## Decisão

`db/migrations` será a única linha de migrations operacionais enquanto o sistema for local. `supabase/migrations` ficará arquivado até o deploy futuro. Ao final, gerar um baseline novo e reproduzível.

## Implementações

### 6.1 Auditoria automática

Criar:

- `scripts/schema/audit_sql_references.py`;
- `tests/integration/test_all_sql_references.py`;
- `output/schema/schema-gap-report.json`;
- `output/schema/schema-gap-report.md`.

O script deve:

1. extrair SQL embutido nos arquivos Python;
2. identificar tabelas, views, funções e colunas;
3. consultar `information_schema`, `pg_catalog` e `pg_proc`;
4. executar `EXPLAIN` ou transação rollback-only para cada query parametrizada;
5. falhar se houver relation, column ou function ausente.

### 6.2 Contrato canônico de tabelas

Não permitir que módulos analíticos leiam diretamente schemas físicos divergentes. Criar views canônicas:

- `v_entities_canonical`;
- `v_open_opportunities_canonical`;
- `v_contracts_canonical`;
- `v_suppliers_canonical`;
- `v_value_observations_canonical`.

As views devem expor nomes estáveis. Para contratos:

```text
contract_key
orgao_cnpj14
orgao_cnpj8
orgao_nome
supplier_document
supplier_name
object_text
contracted_value
signed_at
valid_from
valid_to
source
source_id
ingested_at
last_seen_at
is_source_current
```

Adaptar o schema físico real para esses nomes dentro da view.

### 6.3 Migrações

Usar a próxima numeração livre após a HEAD real. Sugestão lógica:

- `030_schema_contract_and_canonical_views.sql`;
- `031_source_snapshot_reconciliation.sql`;
- `032_capability_coverage.sql`;
- `033_contract_versioning.sql`;
- `034_supplier_identity.sql`;
- `035_value_observations.sql`;
- `036_reporting_views.sql`.

Criar rollback correspondente para cada migration destrutiva. Migrations aditivas devem ser idempotentes.

### 6.4 Baseline reproduzível

Após aplicar todas as migrations:

```bash
pg_dump --schema-only --no-owner --no-privileges "$DATABASE_URL" \
  > db/current-schema.sql
```

Adicionar fingerprint SHA-256 ao run manifest.

### 6.5 Teste de instalação e upgrade

Testar:

1. banco PostgreSQL vazio;
2. cópia do banco local atual;
3. execução repetida das migrations;
4. rollback das migrations novas;
5. reconstrução integral das views.

## Critérios de aceite

- zero query com erro de schema;
- zero função com assinatura incompatível;
- `db/current-schema.sql` reflete a HEAD;
- `supabase/current-schema.sql` é removido, arquivado ou claramente marcado como histórico;
- fresh install e upgrade test passam;
- métricas de concorrência executam contra PostgreSQL real, não apenas mocks.

---

# 7. EPIC P0-03 — Tornar a planilha a única autoridade do universo

## Implementações

- Remover o carregador duplicado de `scripts/consulting_readiness.py`.
- Usar exclusivamente `scripts/lib/universe.py`.
- Criar tabela de snapshots:

```sql
target_universe_runs (
  id,
  seed_sha256,
  seed_filename,
  radius_km,
  total_rows,
  included_rows,
  excluded_rows,
  unresolved_rows,
  created_at,
  git_sha
);
```

```sql
target_universe_entities (
  universe_run_id,
  canonical_entity_key,
  seed_row,
  cnpj8,
  legal_name,
  municipality,
  ibge_code,
  legal_nature,
  latitude,
  longitude,
  distance_km,
  radius_decision,
  duplicate_root,
  db_entity_id,
  match_method,
  PRIMARY KEY (universe_run_id, canonical_entity_key)
);
```

- Toda execução analítica deve receber `universe_run_id`.
- Toda view analítica deve juntar pela identidade canônica, não por `raio_200km`.
- Manter ledger de divergência entre seed e `sc_public_entities`.
- Resolver manualmente a raiz duplicada `00394494`; não colapsar entidades diferentes.
- Bloquear execução se a planilha mudar e o novo hash não tiver snapshot gerado.

## Critérios de aceite

- todas as métricas retornam o mesmo denominador;
- zero consulta analítica contém `WHERE e.raio_200km IS TRUE`, exceto relatório diagnóstico de divergência;
- mudança de seed produz novo snapshot, sem alterar artefatos antigos;
- 1.093 entes incluídos e 992 excluídos para a seed atual;
- 0 unresolved.

---

# 8. EPIC P0-04 — Reconciliar snapshots de editais abertos

## Problema crítico

O endpoint PNCP `/api/consulta/v1/contratacoes/proposta` representa um snapshot de propostas abertas. Uma execução completa retornou 34 registros, mas o radar exportou 673 porque itens antigos não foram inativados.

## Schema

Adicionar a `opportunity_intel` ou tabela auxiliar:

```text
last_seen_source_run_id
first_seen_at
last_seen_at
source_active
source_inactive_at
source_inactive_reason
last_status_verified_at
last_status_verified_by
```

Criar:

```sql
source_snapshot_membership (
  source_run_id,
  source,
  scope_key,
  source_record_id,
  canonical_opportunity_key,
  seen_at,
  PRIMARY KEY (source_run_id, source_record_id)
);
```

## Algoritmo

Após uma execução PNCP completa:

1. persistir todos os IDs vistos;
2. confirmar que todas as 19 modalidades concluíram paginação;
3. dentro do escopo `source=pncp`, `UF=SC`, marcar como `source_active=FALSE` todo registro anteriormente ativo que não apareceu no snapshot;
4. usar `source_inactive_reason='absent_from_complete_open_snapshot'`;
5. nunca inativar registros quando a execução estiver `partial`, `failed` ou limitada por `max_pages/max_records`;
6. preservar histórico;
7. permitir reativação caso o ID reapareça;
8. radar só lê `source_active=TRUE`;
9. oportunidade prioritária exige `last_status_verified_at` dentro do SLA;
10. URLs sem domínio oficial ou vazio bloqueiam status “acionável”.

## Regras de consistência

- quantidade PNCP no radar deve ser igual ao conjunto atual do último snapshot completo, depois do filtro geográfico e de perfil;
- registros não vistos no último snapshot não podem aparecer como abertos;
- `is_active` de ingestão deve ser renomeado ou separado de status de negócio.

## Testes

- snapshot A: IDs 1,2,3;
- snapshot B completo: IDs 2,3;
- após B, ID 1 inativo;
- snapshot B parcial: ID 1 não pode ser inativado;
- ID 1 reaparece em C: reativado;
- execução zero completa: todos os registros do escopo ficam inativos;
- execução zero parcial: nenhum registro é alterado;
- concorrência entre dois runs: apenas run finalizado pode reconciliar;
- idempotência do mesmo run.

## Critérios de aceite

- `active_snapshot_integrity = 100%`;
- radar PNCP não contém registro ausente do último snapshot completo;
- artefato registra quantos foram ativados, atualizados, inativados e reativados;
- o gap 34 versus 673 deixa de existir.

---

# 9. EPIC P0-05 — Modelo de cobertura por fonte, ente e capacidade

## Schema

Criar ou evoluir `coverage_evidence` para conter:

```text
canonical_entity_key
capability
source
data_type
applicability
applicability_reason
scope_key
period_start
period_end
source_run_id
state
pages_expected
pages_processed
records_expected
records_fetched
records_persisted
freshness_status
checked_at
next_due_at
error_code
error_message
evidence_metadata
```

Estados permitidos:

- `not_applicable`;
- `pending`;
- `running`;
- `success_with_data`;
- `success_zero`;
- `partial`;
- `error`;
- `blocked`;
- `stale`.

## Registry de fontes

Expandir `scripts/crawl/registry.py`:

```yaml
name:
capabilities:
  - open_tenders
  - historical_contracts
  - awards
  - payments
  - publications
authority_level: primary | complementary | fallback
entity_types:
credential_names:
snapshot_semantics: full_snapshot | date_window | append_only
freshness_sla_hours:
supports_pagination:
supports_zero_proof:
reconciliation_strategy:
```

Corrigir o registry para não tratar `contracts` genericamente como `bids` e não tratar `selenium` como fonte.

## Matriz de aplicabilidade

Criar `config/source_applicability.yaml` e tabela materializada. A decisão deve considerar:

- esfera e natureza jurídica;
- município;
- plataforma de compras conhecida;
- disponibilidade de PNCP;
- fonte estadual, federal ou municipal;
- necessidade da capacidade analisada.

Nenhum agente deve presumir que todas as 13 fontes são exigidas para todos os 1.093 entes.

## Critérios de aceite

- 100% dos pares necessários têm aplicabilidade decidida;
- coverage manifest é emitido por capacidade;
- `success_zero` exige paginação completa;
- data presence não altera coverage;
- blockers têm ação recomendada e responsável.

---

# 10. EPIC P0-06 — Provar fontes de editais além do PNCP

## Ordem de implementação

Provar uma fonte por vez. Não executar `all` enquanto cada adapter não tiver teste ponta a ponta.

1. `pncp`;
2. `compras_gov`;
3. `sc_compras`;
4. `dom_sc`;
5. `pcp`;
6. `tce_sc`;
7. `transparencia`;
8. `doe_sc`, somente se necessário;
9. Selenium apenas como infraestrutura.

## Contrato obrigatório do adapter

Cada fonte deve implementar:

```python
crawl(request) -> SourceRunResult
transform(raw_records) -> list[CanonicalOpportunity]
persist(records, run_id) -> PersistResult
reconcile(run_result) -> ReconcileResult
health() -> SourceHealth
```

`SourceRunResult` deve carregar:

- status;
- escopo;
- páginas esperadas/processadas;
- registros esperados/recebidos;
- regra de conclusão;
- erros;
- raw payload location;
- timestamps;
- versão do parser.

## Fontes já descritas no repositório

- PNCP editais abertos: `scripts/opportunity_intel/pncp_crawler.py`, endpoint `/api/consulta/v1/contratacoes/proposta`.
- PNCP contratos: `scripts/crawl/contracts_crawler.py`, endpoint `/api/consulta/v1/contratos`.
- DOM-SC: `scripts/crawl/dom_sc_crawler.py`, endpoint `/?r=remote/list`, Basic Auth CPF:CNPJ + `X-API-Key`.
- ComprasGov: `scripts/crawl/compras_gov_crawler.py`.
- SC Compras: `scripts/crawl/sc_compras_crawler.py`.
- Portal de Compras Públicas: `scripts/crawl/pcp_crawler.py`.
- TCE-SC: `scripts/crawl/tce_sc_crawler.py`.
- Transparência: `scripts/crawl/transparencia_crawler.py`.

Usar os módulos existentes como fonte de endpoint, payload e transform. Não buscar uma nova fonte antes de testar e documentar a fonte já implementada.

## Deduplicação cross-source

Criar:

```sql
opportunity_source_links (
  canonical_opportunity_key,
  source,
  source_record_id,
  official_url,
  match_method,
  match_score,
  reviewed,
  created_at,
  UNIQUE (source, source_record_id)
);
```

Prioridade de identidade:

1. `numeroControlePNCP`;
2. CNPJ do órgão + número do processo + número do edital;
3. CNPJ + modalidade + ano + número;
4. fallback fuzzy com objeto e datas, sempre em fila de revisão.

Não fundir automaticamente quando score abaixo do limiar.

## Critérios de aceite

- ao menos 95% dos entes têm uma estratégia de monitoramento aplicável e fresca;
- cada fonte tem smoke real opt-in;
- cada fonte tem fixture gravada;
- cada fonte diferencia zero de falha;
- cada fonte salva raw payload imutável;
- cada fonte tem reconciliação compatível com sua semântica;
- o manifest mostra ganho marginal de cobertura de cada fonte.

---

# 11. EPIC P0-07 — Perfil comercial real da EXTRA

## Problema

`config/client_profiles/extra.yaml` possui apenas alguns termos de objeto. Modalidades, cidades prioritárias, faixa de valor, prazo mínimo, documentos obrigatórios e termos negativos estão vazios.

## Schema/configuração obrigatória

Adicionar:

```yaml
company:
  legal_name: EXTRA EMPREITEIRA E CONSTRUTORA
  cnpj: "24515063000149"
  headquarters: Sao Jose/SC

geography:
  max_distance_km: 200
  priority_municipalities: []
  excluded_municipalities: []

commercial:
  minimum_estimated_value:
  maximum_estimated_value:
  minimum_days_to_deadline:
  allowed_modalities: []
  excluded_modalities: []
  maximum_simultaneous_projects:
  preferred_contract_duration_months:

qualification:
  required_cae_categories: []
  maximum_required_capital:
  minimum_technical_capacity_rules: []

documents:
  require_official_notice: true
  require_attachments: true
  require_budget_sheet: false

objects:
  positive_categories: [...]
  negative_categories: [...]
  positive_terms: [...]
  negative_terms: [...]
```

Campos sem informação devem ser `null`, nunca inventados. Enquanto os campos críticos estiverem nulos, o sistema não pode emitir PARTICIPAR/NÃO PARTICIPAR.

## Taxonomia inicial de engenharia

Incluir regras para:

- reforma predial;
- manutenção predial;
- construção de edificações;
- ampliação;
- adequação;
- recuperação;
- retrofit;
- pintura;
- cobertura e telhado;
- acessibilidade;
- instalações elétricas;
- instalações hidrossanitárias;
- prevenção contra incêndio;
- escolas, UBS, hospitais, prédios administrativos;
- serviços continuados de manutenção;
- obra global versus serviço unitário.

Separar ou excluir:

- pavimentação;
- rodovias;
- saneamento pesado;
- pontes;
- dragagem;
- locação de mão de obra pura;
- materiais sem execução;
- limpeza e zeladoria sem engenharia;
- consultoria e projeto sem obra, salvo decisão do perfil.

## Calibração

Criar dataset rotulado de no mínimo:

- 100 oportunidades relevantes;
- 100 irrelevantes;
- 30 casos limítrofes.

Medir:

- precision;
- recall;
- falsos negativos;
- falsos positivos;
- concordância entre regra e revisão humana.

## Saída

Manter três classes automáticas:

- `PRIORITARIA`;
- `REVISAR`;
- `DESCARTAR`.

A recomendação final `PARTICIPAR` ou `NÃO PARTICIPAR` deve ser um campo separado, preenchido após revisão humana do consultor.

---

# 12. EPIC P0-08 — Contratos históricos completos e atualizáveis

## Corrigir o crawler

Em `scripts/crawl/contracts_crawler.py`:

- uma janela com erro após alguma página deve ser `partial`;
- janela `partial` nunca entra em `completed_windows`;
- armazenar página final, total de páginas e erro;
- retomar exatamente da página falha;
- validar `totalPaginas` e `totalRegistros`;
- persistir raw payload por janela;
- não usar `DO NOTHING` para contratos já existentes;
- atualizar campos mutáveis;
- manter histórico de versões.

## Versionamento

Criar:

```sql
contract_versions (
  id,
  contract_key,
  source_run_id,
  content_hash,
  payload,
  valid_from,
  valid_to,
  is_current
);
```

Campos alteráveis:

- valor;
- vigência;
- fornecedor;
- objeto;
- situação;
- URL;
- unidade;
- aditivos;
- data de atualização da fonte.

## Datas e vigência

Separar:

- data de assinatura;
- início de vigência;
- fim original;
- fim efetivo;
- data de rescisão;
- data de publicação;
- última atualização.

Não confundir `is_active` da linha com contrato vigente.

## Qualidade

Quarentenar:

- datas fora do período plausível;
- datas futuras absurdas;
- fim anterior ao início;
- valores negativos;
- valores acima de limiar configurável;
- CNPJ inválido;
- contrato sem ID oficial;
- duplicidade incompatível.

Criar `data_quality_issues` com severidade, regra, registro e resolução.

## Cobertura histórica

Executar três anos completos em janelas. Para cada ente:

- `success_with_data` se houver contratos;
- `success_zero` se a busca completa não retornar;
- `partial/error` se qualquer janela falhar.

A cobertura não é 404/1.093. Esse é data presence. A cobertura só passa quando pelo menos 95% dos entes tiverem investigação completa.

## Índices

Criar índices no schema canônico:

- órgão CNPJ8 + data de assinatura;
- fornecedor + data;
- fim efetivo;
- objeto por trigram/FTS;
- source + source_id;
- contract_key;
- current version.

## Critérios de aceite

- 100% das janelas do backfill concluídas ou blocker explícito;
- nenhuma janela parcial marcada como completa;
- segunda execução atualiza contrato modificado;
- datas anômalas não entram nas views analíticas;
- manifest diferencia investigação de presença;
- 95% de cobertura histórica auditável.

---

# 13. EPIC P0-09 — Inteligência de concorrentes correta

## Identidade de fornecedor

Criar:

```sql
suppliers (
  supplier_key,
  document_type,
  document_number,
  normalized_name,
  display_name,
  entity_type,
  first_seen_at,
  last_seen_at
);
```

Criar aliases:

```sql
supplier_aliases (
  supplier_key,
  source,
  raw_document,
  raw_name,
  confidence,
  reviewed
);
```

Tratar:

- CNPJ com máscara;
- filiais;
- CPF;
- consórcios;
- nomes abreviados;
- mudanças de razão social;
- fornecedor ausente.

## Universo analítico

Toda métrica deve filtrar:

- snapshot canônico de 1.093 entes;
- período de três anos;
- categorias relevantes à EXTRA;
- contratos válidos e atuais;
- valores semanticamente contratados;
- registros fora da quarentena.

## Métricas permitidas

- quantidade de contratos vencidos;
- valor total contratado;
- ticket médio e mediano contratual;
- P25/P50/P75 de tickets;
- órgãos atendidos;
- municípios atendidos;
- distribuição por categoria;
- evolução anual;
- market share por quantidade;
- market share por valor;
- award share por órgão;
- HHI por órgão e segmento;
- concentração geográfica;
- contratos com vigência comprovadamente ativa;
- ranking top 15.

## Métricas proibidas sem dados adicionais

- win rate;
- taxa de sucesso;
- todos os licitantes;
- deságio habitual;
- margem;
- capacidade ociosa;
- probabilidade de não participar.

## Correções imediatas

- reescrever `_compute_market_share`, `_compute_award_share`, `_compute_hhi` e ranking para ler `v_contracts_canonical`;
- não consultar nomes físicos de colunas;
- passar `universe_run_id`;
- remover filtros por `e.raio_200km`;
- excluir a própria EXTRA do ranking competitivo ou mostrá-la em seção separada;
- testar com PostgreSQL real;
- validar denominadores;
- impedir soma duplicada de contratos;
- usar `COUNT(DISTINCT contract_key)`.

## “Contratos ativos”

Só classificar ativo quando houver:

- fim efetivo >= data atual;
- ausência de rescisão;
- status contratual compatível;
- última atualização dentro do SLA.

Caso contrário, usar `vigencia_desconhecida`.

## Critérios de aceite

- top 15 reproduzível e rastreável;
- todas as linhas têm fornecedor canônico;
- métricas executam no schema real;
- nenhuma saída chama award share de win rate;
- contratos ativos têm evidência de vigência;
- cobertura de concorrentes calculada pela cobertura contratual, não pela quantidade de fornecedores.

---

# 14. EPIC P1-01 — Preço praticado com semântica correta

## Regra central

Valor global de contrato é **ticket contratual**, não preço praticado por tipo de obra.

Preço comparável exige unidade de comparação. A prioridade é item/lote. Para obra global, só há preço unitário comparável se houver área, quantidade, unidade ou composição compatível.

## Modelo de dados

Criar:

```sql
procurement_events (
  procurement_key,
  canonical_entity_key,
  process_number,
  notice_number,
  modality,
  object_text,
  publication_date,
  opening_date,
  closing_date,
  source_status,
  official_url
);
```

```sql
procurement_items (
  item_key,
  procurement_key,
  item_number,
  lot_number,
  description,
  category_code,
  unit_raw,
  unit_normalized,
  quantity,
  estimated_unit_value,
  estimated_total_value
);
```

```sql
awards (
  award_key,
  procurement_key,
  item_key,
  supplier_key,
  homologated_unit_value,
  homologated_total_value,
  homologated_at,
  source,
  source_id,
  official_url
);
```

```sql
contracts_canonical (
  contract_key,
  procurement_key,
  item_key,
  supplier_key,
  contracted_value,
  signed_at,
  effective_end_at,
  source
);
```

```sql
payments (
  payment_key,
  contract_key,
  commitment_number,
  committed_value,
  liquidated_value,
  paid_value,
  reference_date,
  source
);
```

```sql
value_observations (
  observation_key,
  procurement_key,
  item_key,
  contract_key,
  value_type,
  value,
  unit,
  reference_date,
  source,
  source_id,
  extraction_method,
  confidence,
  raw_evidence_location
);
```

`value_type`:

- `estimated_unit`;
- `estimated_total`;
- `homologated_unit`;
- `homologated_total`;
- `contracted_total`;
- `committed`;
- `liquidated`;
- `paid`.

## Fontes e prioridade

- valor estimado: PNCP edital/item, depois DOM-SC;
- valor homologado: DOM-SC resultado estruturado, depois outra fonte que já o exponha;
- valor contratado: PNCP contratos;
- valor pago: TCE-SC, depois portais de transparência.

Não usar LLM como fonte primária numérica. LLM pode sugerir extração para fila de revisão, sempre com evidência do trecho e validação determinística.

## Matching cross-source

Ordem:

1. número PNCP;
2. CNPJ do órgão + processo;
3. CNPJ + edital + ano;
4. contrato referenciando processo;
5. fuzzy object/date/value somente para `review_required`.

Criar `cross_source_matches`:

```text
left_source_id
right_source_id
match_method
match_score
evidence
status
reviewed_by
reviewed_at
```

Nunca calcular deságio com match não aprovado abaixo do limiar.

## Taxonomia de preços

Criar `config/construction_taxonomy.yaml` com categorias e subcategorias. No mínimo:

- construção de edifício;
- reforma geral;
- manutenção predial;
- ampliação;
- pintura;
- cobertura/telhado;
- instalações elétricas;
- instalações hidrossanitárias;
- climatização;
- prevenção contra incêndio;
- acessibilidade;
- recuperação estrutural;
- serviços preliminares;
- demolição;
- esquadrias;
- revestimentos;
- pavimentação externa;
- urbanização.

Separar contratação global de item unitário.

## Normalização de unidades

Mapear:

- `m2`, `m²`, `M2` → `m2`;
- `m3`, `m³` → `m3`;
- `m`, `ml` quando metro linear → `m`;
- `kg`;
- `un`, `unid` → `un`;
- `h`, `hora` → `h`;
- `mes`, `mês` → `month`;
- `serviço`, `global`, `vb` → `global`.

Itens `global` não entram em percentil unitário.

## Deságio

```text
desagio_pct =
(estimated_value - homologated_value)
/
estimated_value
× 100
```

Somente para o mesmo item/lote ou evento integral comprovadamente equivalente.

## Percentis

Para cada grupo comparável:

- mesma categoria/subcategoria;
- mesma unidade;
- mesma granularidade;
- período explicitado;
- mínimo de 5 observações válidas.

Publicar:

- N;
- mínimo;
- P25;
- mediana;
- P75;
- máximo;
- data inicial/final;
- quantidade de outliers;
- cobertura de fonte.

N < 5: não publicar percentil como referência robusta.

## Outliers

Usar IQR ou MAD por grupo. Não excluir definitivamente. Marcar:

- `valid`;
- `suspect`;
- `excluded_from_aggregate`;
- motivo.

## Evolução temporal

Publicar valores nominais. Só publicar valores reais corrigidos quando uma série oficial de inflação estiver carregada e versionada.

## Critérios de aceite

- nenhum relatório chama ticket global de preço unitário;
- pelo menos uma cadeia estimado → homologado validada ponta a ponta;
- deságio calculado apenas com linkage comprovado;
- percentis incluem N e unidade;
- toda observação possui fonte e evidência;
- cobertura de preço é publicada separadamente;
- `commercial_metrics.practiced_prices` só fica `READY` quando a amostra mínima e cobertura definidas forem atingidas.

---

# 15. EPIC P1-02 — Contratos vincendos e relicitação

A proposta inclui contratos com vencimento em 90–180 dias. Isso não é acompanhamento de obra; é inteligência de mercado e permanece no escopo.

## Implementações

- consolidar fim original e fim efetivo;
- ingerir aditivos de prazo quando disponíveis;
- ingerir rescisão/extinção;
- marcar `vigency_confidence`;
- criar view `v_contracts_expiring_90_180`;
- agrupar contratos semelhantes por órgão, categoria e fornecedor;
- identificar sequência histórica de substituição.

## Probabilidade de relicitação

Não publicar probabilidade numérica até existir dataset histórico de:

- contrato encerrado;
- novo processo similar;
- intervalo entre encerramento e nova publicação;
- resultado positivo/negativo.

Enquanto isso, usar indicadores:

- `historical_reprocurement_count`;
- `median_days_to_reprocurement`;
- `same_category_reprocured`;
- `confidence`;
- `signal = high|medium|low|unknown`.

## Critérios de aceite

- contrato só aparece se fim efetivo tiver confiança suficiente;
- 90–180 dias calculados a partir da data de geração do relatório;
- ausência de fim é `unknown`, não “não vence”;
- probabilidade não é inventada;
- toda inferência mostra histórico usado.

---

# 16. EPIC P1-03 — Relatório e planilhas da consultoria

## Run único

Criar comando:

```bash
python -m scripts.consulting.cli build-delivery \
  --profile config/client_profiles/extra.yaml \
  --seed "Extra - alvos de licitação. R-0.xlsx" \
  --period-years 3 \
  --output output/deliveries
```

O comando deve:

1. congelar universo;
2. verificar freshness;
3. executar readiness;
4. gerar datasets;
5. bloquear claims não prontos;
6. gerar Excel;
7. gerar conteúdo estruturado do PDF;
8. emitir manifest.

## Estrutura do Excel

1. `Resumo`;
2. `Universo_Alvo`;
3. `Cobertura`;
4. `Saude_Fontes`;
5. `Editais_Abertos`;
6. `Editais_Revisao`;
7. `Contratos_Historicos`;
8. `Concorrentes_Top15`;
9. `Concorrentes_Por_Orgao`;
10. `Precos`;
11. `Contratos_Vincendos`;
12. `Qualidade_Dados`;
13. `Metodologia`;
14. `Proveniencia`.

## Campos mínimos em editais

- recommendation automática;
- recommendation final humana;
- score de confiança;
- score de aderência;
- blockers;
- órgão;
- município;
- distância;
- objeto;
- modalidade;
- valor estimado;
- abertura;
- encerramento;
- dias restantes;
- URL oficial;
- fontes;
- última verificação;
- run_id.

## PDF

O PDF deve ser gerado a partir dos mesmos datasets e manifest. Nenhum número pode ser digitado manualmente sem referência ao dataset.

## Gate de publicação

Bloquear geração final ou inserir seção explícita de limitações quando:

- coverage < 95%;
- qualquer fonte obrigatória está stale;
- open snapshot integrity < 100%;
- schema gate falhou;
- preços não têm amostra;
- top 15 não passou integração;
- campos críticos abaixo de 95%.

## Critérios de aceite

- PDF e Excel compartilham run_id;
- números reconciliam;
- links oficiais funcionam;
- claims bloqueados aparecem como indisponíveis;
- artefatos antigos são imutáveis;
- relatório final tem data/hora, git SHA, seed SHA e schema fingerprint.

---

# 17. EPIC P1-04 — Orquestração local reproduzível

## Ambiente

Fixar PostgreSQL 16, versão já usada na execução QW-01.

Criar ou revisar:

- `docker-compose.local.yml`;
- `.env.example`;
- `Makefile`;
- `scripts/bootstrap_local.sh`;
- `scripts/backup_local.sh`;
- `scripts/restore_local.sh`;
- `scripts/run_local_pipeline.sh`.

## Comandos

```bash
make bootstrap
make db-up
make migrate
make seed-universe
make ingest-open
make reconcile-open
make ingest-contracts
make build-analytics
make readiness
make delivery
make test-fast
make test-integration
make test-all
make backup
```

## Armazenamento

```text
data/
  raw/<source>/<run_id>/
  checkpoints/<source>/
  quarantine/
  cache/
output/
  runs/<run_id>/
  deliveries/<delivery_id>/
  schema/
```

Raw payload deve ser gzip, imutável e identificado por SHA-256.

## Transações

- uma transação por lote;
- savepoint por página/janela quando necessário;
- rollback em falha;
- run só finaliza após persistência e evidence ledger;
- reconciliação ocorre somente após commit da carga completa.

## Performance

- `EXPLAIN ANALYZE` das consultas principais;
- índices usados;
- sem full scan desnecessário em milhões de contratos;
- `VACUUM ANALYZE` após backfill;
- paginação de exportações;
- limite de memória configurável.

---

# 18. EPIC P1-05 — QA e gates

## Gates obrigatórios

### Código

- `ruff check`;
- `ruff format --check`;
- `mypy` nos módulos críticos;
- `python -m compileall`;
- `bandit`;
- `pip-audit`.

### Banco

- fresh install;
- upgrade;
- idempotência;
- schema fingerprint;
- zero query incompatível;
- constraints validadas;
- rollback test.

### Testes

- unitários;
- integração PostgreSQL;
- contract tests de cada fonte;
- fixtures;
- smoke real opt-in;
- end-to-end local;
- golden report.

### Cobertura

Não aceitar apenas cobertura global baixa mascarada por muitos módulos auxiliares. Gate de pelo menos 80% para:

- `scripts/lib/universe.py`;
- `scripts/opportunity_intel`;
- reconciliação;
- coverage;
- contract pipeline;
- supplier metrics;
- price pipeline;
- report builder.

## Testes de dados

- CNPJ e identidade;
- duplicidade;
- datas;
- valores;
- paginação;
- zero real;
- freshness;
- stale;
- reconciliação;
- cross-source matching;
- denominadores;
- percentis;
- deságio;
- consistência Excel/PDF.

## QA humana

A story só muda para `Done` depois de:

- execução em banco real local;
- inspeção de amostra;
- relatório QA;
- blockers resolvidos;
- artefato operacional com gates executados no mesmo run.

A QW-01 atual não passa por estar `InReview`, QA pendente e `test_results.status=not_run_for_this_artifact`.

---

# 19. EPIC P1-06 — Observabilidade

## Logs

JSON estruturado com:

- timestamp;
- run_id;
- source;
- capability;
- entity;
- scope;
- page;
- event;
- duration_ms;
- status;
- error_code.

## Métricas

- última execução por fonte;
- duração;
- páginas;
- registros;
- inserts/updates/inativados;
- erros;
- freshness;
- coverage;
- data presence;
- campos ausentes;
- matches automáticos/manuais;
- quarentena;
- tamanho do banco.

## Alertas locais

Mesmo antes de VPS, gerar `output/health/latest.json` e saída não zero quando:

- fonte stale;
- run parcial;
- coverage cai;
- número de registros varia anormalmente;
- schema muda;
- parser perde campos;
- credencial ausente;
- disco insuficiente.

---

# 20. EPIC P2 — Preparação para Hetzner/Supabase, somente após readiness local

## Pré-condições

- todas as P0 concluídas;
- editais sem stale;
- schema único;
- contratos atualizáveis;
- concorrentes validados;
- preço com semântica;
- cobertura >=95%;
- relatório reproduzível;
- backup/restore testado.

## ADR de deploy

Documentar:

- versão PostgreSQL;
- extensões;
- volumes;
- backup;
- retenção;
- secrets;
- TLS;
- firewall;
- atualizações;
- observabilidade;
- cron;
- rollback;
- restore test;
- custo.

## Agendamento sugerido futuro

- editais PNCP: a cada 6 horas;
- fontes complementares: diário, conforme limitação;
- contratos incrementais: diário;
- backfill/reconciliação: semanal;
- readiness: após cada carga;
- relatório interno: semanal;
- backup: diário;
- restore drill: mensal.

Não codificar cron como substituto de idempotência.

---

# 21. Lista P0 de blockers que impedem uso confiável agora

- [ ] reconciliar snapshot PNCP e inativar ausentes;
- [ ] impedir radar de ler oportunidades não reconfirmadas;
- [ ] tornar URL oficial obrigatória para oportunidades acionáveis;
- [ ] unificar schema físico e canônico;
- [ ] atualizar dump do schema;
- [ ] corrigir queries de market share/HHI;
- [ ] remover filtros analíticos por `raio_200km`;
- [ ] usar `universe_run_id` em todas as análises;
- [ ] corrigir checkpoint parcial de contratos;
- [ ] permitir atualização de contratos já existentes;
- [ ] provar backfill de três anos;
- [ ] separar coverage de data presence;
- [ ] definir aplicabilidade por fonte;
- [ ] provar fontes complementares;
- [ ] completar perfil da EXTRA;
- [ ] calibrar classificação de objeto;
- [ ] separar triagem automática de recomendação final;
- [ ] criar identidade canônica de fornecedores;
- [ ] validar top 15 no PostgreSQL real;
- [ ] bloquear win rate/deságio/contratos ativos sem evidência;
- [ ] implementar modelo de preços item/lote;
- [ ] gerar entrega PDF/Excel a partir do mesmo run;
- [ ] executar gates no próprio artefato;
- [ ] concluir QA.

---

# 22. Definition of Done do projeto local

O projeto estará apto a apoiar a consultoria quando, no mesmo run:

1. a seed tiver resolução de 100%;
2. a cobertura de investigação de cada capability essencial for >=95%;
3. todos os editais exibidos estiverem no snapshot mais recente ou reconfirmados;
4. 95% dos editais acionáveis tiverem campos críticos e URL oficial;
5. o histórico contratual de três anos tiver janelas completas;
6. zero janela parcial estiver marcada como concluída;
7. top 15 concorrentes executar no schema real e tiver rastreabilidade;
8. preço praticado estiver claramente separado de ticket contratual;
9. percentis tiverem unidade, categoria e N mínimo;
10. deságio for calculado apenas no mesmo item/lote;
11. contratos vincendos tiverem vigência confiável;
12. PDF e Excel compartilharem run_id;
13. migrations passarem em banco vazio e upgrade;
14. gates técnicos passarem;
15. QA humana aprovar amostra;
16. manifest não contiver claim proibido;
17. exit code for 0.

Até lá, o status geral correto é `PARTIAL / NOT CLIENT-READY`.

---

# 23. Comando de trabalho recomendado ao agente

O agente executor deve trabalhar na ordem P0, criando uma branch por epic. Para cada epic:

1. ler os arquivos citados neste documento;
2. registrar baseline;
3. escrever testes que falham;
4. implementar;
5. rodar testes unitários;
6. rodar PostgreSQL real local;
7. gerar artefato de evidência;
8. atualizar documentação;
9. executar QA gate;
10. só então avançar.

O agente não deve:

- pesquisar ou adicionar novas fontes antes de provar as existentes;
- alterar o escopo para acompanhamento de obras;
- iniciar deploy Hetzner;
- promover metricas parciais a READY;
- reconstruir evidência retroativamente sem run real;
- tratar ausência de dados como sucesso sem prova;
- aceitar teste mock como validação do schema;
- usar LLM para inventar ou confirmar valores;
- marcar uma story concluída sem artefato operacional do mesmo commit.
