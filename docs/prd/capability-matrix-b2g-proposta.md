# Matriz de Capacidades — Proposta Comercial B2G (CONFENGE / Extra)

| Campo | Valor |
|-------|-------|
| **Versão** | 1.0 |
| **Data** | 2026-07-17 |
| **Autor** | Morgan (PM) — AIOX |
| **Branch** | `epic/b2g-operational-platform-2026-07-17` |
| **PRD base** | `docs/prd/PRD-consultoria-extra.md` v2.0 |
| **PRD delta** | `docs/prd/PRD-b2g-operational-platform-delta.md` |
| **Epic** | `docs/stories/epics/epic-b2g-operational-platform/EPIC-B2G-OPERATIONAL-PLATFORM.md` |

---

## 1. Baseline honesto (2026-07-17)

> **Não confundir sinal comercial com cobertura operacional.**

| Métrica | Numerador | Denominador | % | Fonte de verdade |
|---------|-----------|-------------|---|------------------|
| **entities_with_recent_commercial_signal** (ex-`commercial_opportunity_any`) | **116** | **1.093** | **10,61%** | `docs/ops/session-2026-07-17/coverage_canonical.json` |
| **operational_source_coverage** (alvo 95%) | **não medido de forma canônica multi-fonte** | **1.093** | **≪ 95%** | Requer registry por entidade + evidence ledger |
| Editais raw históricos (baseline path) | 52 | 1.093 | 4,76% | `output/coverage/next30d-metrics-final.json` |
| Pilot contratos 90d nacional | partial (path_proof 1d) | — | NO-GO 3y | same |
| Universo canônico 200 km | — | **1.093** | fixed | `sc_public_entities` `is_active AND raio_200km` |

**Implicação comercial:** a proposta pode prometer **95% de cobertura operacional** (órgãos monitorados com fonte ativa e evidência recente), mas o baseline atual de **sinal comercial acionável** é **116/1.093 (~10,6%)**. Usar 116 como se fosse “cobertura 95%” é fraude de métrica.

---

## 2. Persona operacional e entregáveis

| Papel | Persona | Interface primária | Entregável cliente |
|-------|---------|--------------------|--------------------|
| Consultor | Tiago Sasaki | **Workspace CLI** (`workspace today/opportunities/coverage`) | Briefing diário + lista priorizada |
| Decisor Extra | Diretoria | PDF/Excel semanal | Panorama + ranking de órgãos |
| Operação | @devops / Tiago | timers + health | SLA de freshness por fonte |

---

## 3. Matriz por capacidade da proposta

Legenda de status:

| Status | Significado |
|--------|-------------|
| **EXISTE** | Código + evidência de execução real |
| **PARCIAL** | Código ou dados parciais; não atende AC comercial |
| **FALTA** | Não existe componente utilizável |
| **BLOQUEADO** | Depende de credencial, infra ou decisão externa |

---

### C1 — Monitorar órgãos no raio 200 km (meta 95% cobertura operacional)

| Dimensão | Conteúdo |
|----------|----------|
| **Requisito de negócio** | Todo órgão do universo 1.093 (200 km) deve ter ≥1 fonte aplicável monitorada com evidência de sucesso recente (SLA por fonte). Meta: **operational_source_coverage ≥ 95%**. |
| **Dados necessários** | Universo canônico; registry entidade→fonte; evidence ledger (`coverage_evidence`); timestamps `last_success_at` por (entity, source). |
| **Fontes de dados** | PNCP, SC Compras, CIGA/DOM, DOM-SC, PCP, TCE-SC, ComprasGov, Transparência, DOE-SC, contracts. |
| **Componentes existentes** | `sc_public_entities` (1.093); crawlers 11 fontes no registry; `coverage_truth.py`; session 2026-07-17 (116 commercial). |
| **Componentes faltantes** | Registry **por entidade** (não só por fonte); métrica `operational_source_coverage` canônica; scheduler permanente comprovado; fail-closed em zero-result/429. |
| **Risco** | **CRÍTICO** — prometer 95% sem registry + scheduler = overselling. Baseline sinal comercial 10,6%. |
| **AC (resumo)** | Given universo 1.093, When `workspace coverage` roda, Then reporta `operational_source_coverage` e `entities_with_recent_commercial_signal` **separados**, com denominador fixo 1.093. |
| **Comando Tiago** | `workspace coverage` · `python scripts/opportunity_intel/cli.py coverage` · `python scripts/opportunity_intel/cli.py source-health` |
| **Entregável cliente** | Dashboard de cobertura (CLI/HTML) + lista de órgãos sem fonte / sem evidência. |
| **Status** | **PARCIAL** — universo e crawlers existem; métrica 95% **não atingida** e **não instrumentada canonicamente**. |
| **Epic dono** | E1 Operational coverage 95% · E2 Source registry |

---

### C2 — Oportunidades atuais e futuras

| Dimensão | Conteúdo |
|----------|----------|
| **Requisito de negócio** | Superfície diária de editais abertos + pipeline futuro (PCA, ARP, avisos) filtrados pelo perfil Extra/CONFENGE. |
| **Dados necessários** | Editais abertos com prazo; modalidade; objeto; órgão resolvido; status; classificação setorial AEC. |
| **Fontes de dados** | PNCP (bids), SC Compras, CIGA DOM, PCP, DOM-SC, ComprasGov; PCA/ARP para “futuro”. |
| **Componentes existentes** | `opportunity_intel/` (radar, ranking, list/show/explain); sessão SC com 757 open / 68 engineering / 14 GO; QW-01 pipeline. |
| **Componentes faltantes** | Workspace unificado; PCA/ARP em escala; freshness &lt;24h multi-fonte; feedback humano no ranking. |
| **Risco** | **ALTO** — ranking sem perfil cliente canônico gera ruído; fontes secundárias intermitentes. |
| **AC** | Given perfil Extra ativo, When `workspace opportunities --status open`, Then lista ≥N oportunidades com prazo, órgão, score e proveniência de fonte. |
| **Comando Tiago** | `workspace today` · `workspace opportunities` · `python scripts/opportunity_intel/cli.py list --status open` · `... explain <id>` |
| **Entregável cliente** | Lista diária priorizada + dossiê por oportunidade (explain). |
| **Status** | **PARCIAL** — pipeline existe; UX operacional (workspace) e multi-fonte estável **faltam**. |
| **Epic dono** | E4 Daily workspace · E5 Opportunities & triage |

---

### C3 — Análise histórica de contratação (3 anos)

| Dimensão | Conteúdo |
|----------|----------|
| **Requisito de negócio** | Histórico de 3 anos de contratações por órgão do universo para volume, modalidades, sazonalidade e padrões. |
| **Dados necessários** | Contratos + compras históricas com datas, valores, fornecedor, objeto, órgão; janela ≥36 meses. |
| **Fontes de dados** | PNCP contracts; TCE-SC; (secundário) portais de transparência. |
| **Componentes existentes** | `contracts_crawler.py`; `pncp_supplier_contracts` (~63k rows parciais); contract_intel CLI; pilot path_proof 1d **GO**, 90d nacional **NO-GO**. |
| **Componentes faltantes** | Backfill 3 anos controlado; checkpoints resilientes; schema provenance por contrato; GO-NO-GO 3y. |
| **Risco** | **CRÍTICO** — volume e rate-limit PNCP; divergência banco/arquivo/relatório; incompleteness silenciosa. |
| **AC** | Given órgão X no universo, When consulta histórico 36m, Then retorna série temporal com coverage% da janela e flag se incompleto. |
| **Comando Tiago** | `python scripts/local_datalake.py supplier --cnpj …` · contract_intel CLI · futuros `workspace org-history` |
| **Entregável cliente** | Dossiê histórico do órgão (PDF/Excel) + gaps explícitos. |
| **Status** | **PARCIAL** — dados parciais; **3 anos não comprovados** (go_no_go_3y = NO-GO). |
| **Epic dono** | E6 Org history & ranking |

---

### C4 — Concorrentes e vencedores

| Dimensão | Conteúdo |
|----------|----------|
| **Requisito de negócio** | Quem ganha o quê nos órgãos-alvo; win rate relativo; perfil de concorrente por modalidade/objeto. |
| **Dados necessários** | Fornecedor vencedor por contrato/item; CNPJ normalizado; histórico de participações se disponível. |
| **Fontes de dados** | PNCP contracts (fornecedor); TCE-SC; (limitado) atas/resultados em portais. |
| **Componentes existentes** | `v_supplier_winners` (legado); `competitive_intel_validation.py`; B2G-3 story draft; capability `competitors` no registry (fonte `contracts`). |
| **Componentes faltantes** | Entity resolution de fornecedores; win-rate com denominador honesto (propostas enviadas vs só vencedores públicos); relatório cliente. |
| **Risco** | **ALTO** — APIs públicas raramente expõem perdedores; win-rate sem base de propostas é **enviesado**. |
| **AC** | Given setor/órgão, When `competitors report`, Then top-N vencedores com volume R$, #contratos e nota de limitação de dados. |
| **Comando Tiago** | `local_datalake.py supplier` · futuros `workspace competitors` · `opportunity_intel` competitive modules |
| **Entregável cliente** | Mapa de concorrentes + ranking de vencedores por órgão/setor. |
| **Status** | **PARCIAL** — estrutura base; métricas comerciais NOT_READY no PRD legado. |
| **Epic dono** | E7 Competitors & winners |

---

### C5 — Contratos a vencer / probabilidade de relicitação

| Dimensão | Conteúdo |
|----------|----------|
| **Requisito de negócio** | Alertar contratos próximos do fim e estimar chance de nova licitação (recompra). |
| **Dados necessários** | Data fim de vigência; valor; objeto; histórico de renovação/relicitação do órgão. |
| **Fontes de dados** | PNCP contracts (vigência); diários oficiais (aditivos); PCA (intenção futura). |
| **Componentes existentes** | Schema de contratos parcial; ARP crawler (código); nenhum modelo de probabilidade em produção. |
| **Componentes faltantes** | Campo vigência confiável multi-fonte; job de expiração; modelo heurístico de re-bidding; alerta no workspace. |
| **Risco** | **ALTO** — datas de vigência incompletas/ausentes em muitas fontes; modelo sem ground truth. |
| **AC** | Given horizonte 90/180 dias, When `workspace expiring`, Then lista contratos com fim de vigência, órgão e score de re-bidding com evidência. |
| **Comando Tiago** | futuros `workspace expiring` · contract_intel filtros de vigência |
| **Entregável cliente** | Radar de contratos a vencer (semanal). |
| **Status** | **FALTA** (quase total). |
| **Epic dono** | E8 Expiring contracts |

---

### C6 — Inteligência de preços

| Dimensão | Conteúdo |
|----------|----------|
| **Requisito de negócio** | Preço praticado por objeto/unidade/órgão para ancorar propostas. |
| **Dados necessários** | Itens de contrato com unidade, quantidade, valor unitário; normalização de objeto. |
| **Fontes de dados** | PNCP itens de contrato; (limitado) atas de registro de preço. |
| **Componentes existentes** | ADR-002 preço praticado; `bid_simulator.py`; capability `prices` **sem fonte** no registry L1. |
| **Componentes faltantes** | Modelo de preço canônico; coleta de itens em escala; outliers; série temporal. |
| **Risco** | **CRÍTICO** — sem itens unitários, “preço médio” por objeto livre é pseudo-ciência. |
| **AC** | Given objeto normalizado, When consulta preço, Then retorna P25/P50/P75, N amostras, janela e fontes — ou `NOT_READY` explícito. |
| **Comando Tiago** | futuros `workspace prices` · intel_pipeline stages de preço |
| **Entregável cliente** | Tabela de referência de preços + nota metodológica. |
| **Status** | **FALTA** / capability registry: **prices = zero sources**. |
| **Epic dono** | E9 Price intelligence |

---

### C7 — Triagem de edital e análise técnica

| Dimensão | Conteúdo |
|----------|----------|
| **Requisito de negócio** | Classificar GO / NO-GO / WATCH com explicação; extrair requisitos técnicos do edital. |
| **Dados necessários** | Metadados do edital + texto/anexos; regras do perfil cliente; classificação AEC. |
| **Fontes de dados** | Metadados multi-fonte; download de documentos PNCP; (futuro) OCR. |
| **Componentes existentes** | Ranking/scoring opportunity_intel; 14 GO na sessão; radar rules; LLM gate no intel_pipeline legado. |
| **Componentes faltantes** | Pipeline de anexos; OCR; checklist técnico estruturado; feedback loop humano→regras. |
| **Risco** | **ALTO** — PDF escaneado opaco; LLM sem ground truth; overfit de keywords. |
| **AC** | Given oportunidade, When `explain <id>`, Then retorna veredito, dimensões de score, regras acionadas e links de anexos. |
| **Comando Tiago** | `opportunity_intel/cli.py explain <id>` · `workspace opportunities --triage` |
| **Entregável cliente** | Ficha de triagem (1 página) por edital prioritário. |
| **Status** | **PARCIAL** — triagem por metadados existe; análise técnica profunda **falta**. |
| **Epic dono** | E5 Opportunities & triage · E10 Edital analysis |

---

### C8 — Apoio à proposta

| Dimensão | Conteúdo |
|----------|----------|
| **Requisito de negócio** | Montar pacote de apoio: histórico do órgão, preços, concorrentes, riscos, checklist. |
| **Dados necessários** | União de C3–C7 + perfil cliente. |
| **Fontes de dados** | Todas as anteriores + templates de proposta. |
| **Componentes existentes** | intel_pipeline report stages; panorama PDF/Excel; dossiê draft (INTEL-04). |
| **Componentes faltantes** | Template de dossiê comercial unificado; export one-shot por oportunidade; versionamento. |
| **Risco** | **MÉDIO** — depende de C3–C7; risco de “relatório bonito com dados vazios”. |
| **AC** | Given oportunidade GO, When `workspace proposal-pack <id>`, Then gera PDF/Excel com seções preenchidas ou marcadas NOT_READY. |
| **Comando Tiago** | futuros `workspace proposal-pack` · `intel_pipeline.py` · panorama |
| **Entregável cliente** | Pacote de apoio à proposta (PDF + Excel). |
| **Status** | **PARCIAL** (peças) / **FALTA** (produto integrado). |
| **Epic dono** | E11 Proposal support |

---

### C9 — Monitoramento de contratos administrativos

| Dimensão | Conteúdo |
|----------|----------|
| **Requisito de negócio** | Acompanhar contratos em vigor do cliente e do mercado (aditivos, sanções, publicações). |
| **Dados necessários** | Contratos ativos; atos oficiais (DOM/DOE); sanções SICAF. |
| **Fontes de dados** | PNCP contracts; CIGA DOM; DOE-SC; SICAF (`sanctions.py`). |
| **Componentes existentes** | official_acts schema (sessão multi-source); sanctions module; contracts tables. |
| **Componentes faltantes** | Watchlist de contratos; matching aditivo↔contrato; alertas de mudança. |
| **Risco** | **MÉDIO** — volume de atos oficiais alto; false positives de matching. |
| **AC** | Given watchlist, When rotina diária, Then diff de atos/contratos novos com proveniência. |
| **Comando Tiago** | futuros `workspace contracts watch` · health de official_acts |
| **Entregável cliente** | Alerta de movimentação contratual (resumo semanal). |
| **Status** | **PARCIAL** — ingestão de atos existe; monitoramento orientado a contrato **falta**. |
| **Epic dono** | E12 Admin contract monitoring |
| **Fora de escopo** | Acompanhamento físico de **obra** (ver PRD delta). |

---

### C10 — Rotina diária / semanal do consultor

| Dimensão | Conteúdo |
|----------|----------|
| **Requisito de negócio** | Tiago opera em &lt;15 min/dia: o que mudou, o que priorizar, o que reportar. |
| **Dados necessários** | Diff diário de oportunidades; coverage deltas; falhas de fonte; top GO. |
| **Fontes de dados** | Agregação de todas as camadas (workspace). |
| **Componentes existentes** | CLIs fragmentados (`local_datalake`, `opportunity_intel`, `monitor.py`, contract_intel); relatórios one-off. |
| **Componentes faltantes** | **Workspace CLI facade** (ADR-017); rotina semanal/mensal automatizada; checklist operacional documentado. |
| **Risco** | **ALTO** — sem facade, consultor se perde em 10 CLIs; execução manual não escala. |
| **AC** | Given manhã de trabalho, When `workspace today`, Then imprime: freshness por fonte, top oportunidades, alertas, coverage headline dual-metric. |
| **Comando Tiago** | `workspace today` · `workspace opportunities` · `workspace coverage` · relatório semanal |
| **Entregável cliente** | Briefing diário (interno) + relatório semanal/mensal (cliente). |
| **Status** | **FALTA** facade; **PARCIAL** peças. |
| **Epic dono** | E4 Daily workspace · E13 Weekly/monthly reports |

---

## 4. Mapa capacidade → epic (prioridade vertical)

| # | Capacidade | Epic | Prioridade |
|---|------------|------|------------|
| C1 | Cobertura operacional 95% | E1 + E2 + E3 | P0 |
| C2 | Oportunidades atuais/futuras | E4 + E5 | P0 |
| C10 | Rotina consultor | E4 + E13 | P0 |
| C3 | Histórico 3 anos | E6 | P1 |
| C4 | Concorrentes | E7 | P1 |
| C7 | Triagem/análise | E5 + E10 | P1 |
| C5 | Contratos a vencer | E8 | P2 |
| C6 | Preços | E9 | P2 |
| C8 | Apoio proposta | E11 | P2 |
| C9 | Contratos admin | E12 | P2 |

---

## 5. Gaps transversais (todas as capacidades)

| Gap | Impacto | ADR / Epic |
|-----|---------|------------|
| Métrica comercial ≠ cobertura operacional | Overselling | ADR-018 · E1 |
| Sem registry entidade→fonte | Impossível provar 95% | ADR-019 · E2 |
| Artefatos operacionais no git / raw dumps | Repo poluído, dados stale | ADR-020 · E3 |
| 429 / rate-limit sem fail-closed | Perda silenciosa | ADR-021 · E3 |
| Ranking sem lei comercial única | Scores inconsistentes | ADR-022 · E5 |
| Workspace fragmentado | Rotina inviável | ADR-017 · E4 |
| Sem scheduler permanente comprovado | Coleta ad-hoc | E3 |
| Entity resolution incompleta | Duplos / órfãos | E2 · E6 |
| Banco ≠ arquivo ≠ relatório | Confiança zero | E1 · E3 |
| Backup/observabilidade não provados | Risco operacional | E3 (ops) |

---

## 6. Honestidade comercial — o que pode ser prometido agora

| Promessa | Pode prometer? | Condição |
|----------|----------------|----------|
| Monitoramento do universo 1.093 | **Parcial** | Com disclosure de % real e dual-metric |
| 95% cobertura operacional | **Só como meta de roadmap** | Após E1–E3 com evidência |
| 116 órgãos com sinal comercial recente | **Sim** | Como baseline, não como cobertura |
| Oportunidades abertas multi-fonte SC | **Sim, com freshness stamp** | PNCP + SC Compras + CIGA DOM |
| Histórico 3 anos completo | **Não** | go_no_go_3y = NO-GO |
| Preço praticado robusto | **Não** | capability prices sem fonte |
| Win-rate real de propostas Extra | **Não** | sem CRM de propostas |
| Acompanhamento de obra física | **Fora de escopo** | PRD delta |

---

## 7. Referências

- Baseline sessão: `docs/ops/session-2026-07-17/coverage_canonical.json`, `session_summary.json`
- Registry L1: `docs/baseline/l1-source-capability-registry.md`
- Auditoria readiness: `docs/audits/audit-b2g-readiness-2026-07-14.md`
- PRD: `docs/prd/PRD-consultoria-extra.md`
- Arquitetura-alvo: `docs/architecture/b2g-operational-target-architecture.md`
- Diagnóstico adversarial: `docs/architecture/adversarial-diagnosis-b2g-2026-07-17.md`
