# Relatorio de Valor Comercial — Extra Consultoria

**Data:** 2026-07-14
**Tipo:** Investigacao READ-ONLY
**Autor:** Atlas (Analyst Agent) — Synkra AIOX
**Fontes:** `docs/prd/PRD-consultoria-extra.md`, `docs/audits/*.md`, `docs/assessment/purpose-fit-gap-2026-07-12.md`, `docs/ops/onboarding.md`, `docs/ops/runbook.md`, `docs/coverage-truth/coverage-truth-2026-07-12.md`, `config/client_profiles/extra.yaml`, `docs/decisions/adr-002-preco-praticado.md`, `scripts/local_datalake.py`, `EPIC-MASTER-B2G-READINESS.md`

---

## 1. As 5 Frentes da Consultoria

O PRD v2.0 (`docs/prd/PRD-consultoria-extra.md`) define cinco frentes de valor, mas elas aparecem de forma diferente entre o PRD e as auditorias tecnicas. Abaixo, a consolidacao:

### Frente 1 — Diagnostico e Panorama Setorial
**Status real:** PARTIAL (geradores PDF/Excel existem, pipeline end-to-end nao implementado, zero outputs em producao)

O script `scripts/reports/panorama.py` gera relatorios PDF estilo Big Four e Excel com openpyxl. A arquitetura existe: `GenerateConsultoriaPDF` em `scripts/generate_consultoria_pdf.py` e `GeneratePropostaPDF` em `scripts/generate_proposta_pdf.py`. Porem, sem PostgreSQL online, nenhum output e gerado.

**Arquivos entregues:** `scripts/reports/panorama.py`, `scripts/generate_consultoria_pdf.py`, `scripts/generate_proposta_pdf.py`, `scripts/intel_excel.py`
**Entregavel prometido:** Relatorio panorama setorial em PDF + Excel com metricas de mercado
**Gap:** Pipeline end-to-end nao implementado. Step 7 (`intel_report.py`) do pipeline Intel nao existe fisicamente (audit C5).

### Frente 2 — Monitoramento de Editais e Oportunidades
**Status real:** READY (parcial) — PNCP funcional, mas sem filtro AEC/200km, sem geracao de dossier por edital

O modulo `scripts/opportunity_intel/` (QW-01 Radar) tem 8 arquivos, 85/85 testes passando, CLI com 7 subcomandos, ranking deterministico GO/REVIEW/NO_GO com 20 regras e scoring dual-axis (data_confidence + client_fit). O perfil do cliente esta em `config/client_profiles/extra.yaml` com 3 desired object types (reforma predial, manutencao predial, construcao de edificios publicos), 5 positive terms, 3 hard blocks.

**Arquivos entregues:** 8 arquivos em `scripts/opportunity_intel/`, `cli.py` com 7 subcomandos
**Entregavel prometido:** Briefing diario de oportunidades priorizadas
**Gap:** Briefing diario nao existe como comando. Dossier por oportunidade nao implementado. PostgreSQL offline impede qualquer execucao.

### Frente 3 — Analise de Concorrentes e Vencedores Historicos
**Status real:** PARTIAL — estrutura existe, dados nao populados

`v_supplier_winners` com calculo de HHI (Herfindahl-Hirschman Index) implementado em view SQL. `victory_profile.py` e `win_loss_tracker.py` existem mas sem dados. 63.679 fornecedores identificados em manifesto PG, mas sem distincao por orgao/setor. Market share historico e possivel, win rate real nao.

**Arquivos entregues:** `scripts/competitive_intel_validation.py`, views `v_supplier_winners`
**Entregavel prometido:** Ranking de concorrentes, win rate, ticket medio por concorrente
**Gap:** Win rate requer tracking manual de propostas enviadas pela Extra Construtora — nao e viavel por API publica. Ticket medio por concorrente e PARTIAL (existe em `v_supplier_winners` mas sem distincao orgao/setor).

### Frente 4 — Precificacao e Desagio
**Status real:** NOT_READY — 4 metricas comerciais bloqueadas

A semantica de valores esta corretamente documentada (ADR-002 em `docs/decisions/adr-002-preco-praticado.md`): valor_estimado, valor_homologado, valor_contratado, valor_pago. O unico disponivel hoje e `valor_global` em `pncp_supplier_contracts`. Preco praticado, desagio, win rate e probabilidade de relicitacao estao todos NOT_READY.

**Arquivos entregues:** `docs/decisions/adr-002-preco-praticado.md`, `value_semantics.py`
**Entregavel prometido:** Preco praticado comparavel por item/lote, desagio (estimado vs homologado)
**Gap:** API publica PNCP nao expoe propostas perdedoras nem valores homologados item a item. DOM-SC tem potencial para valor homologado via scraping HTML, mas fonte esta bloqueada por credenciais. TCE-SC tem potencial para valor_pago, mas crawler e lento e tem 1.318 records apenas.

### Frente 5 — Acompanhamento e Inteligencia Contratual
**Status real:** NOT_READY — zero implementacao

PRD declara "fora de escopo" para acompanhamento de obras e execucao contratual. O ledger da Extra (contratos proprios da construtora) nao existe. `build-proposta-data.py` e um esqueleto sem checklist, matriz ou tracking. Zero implementacao de acompanhamento contratual.

**Arquivos entregues:** `scripts/build-proposta-data.py` (esqueleto)
**Entregavel prometido:** Acompanhamento de contratos vigentes, alertas de renovacao e relicitacao
**Gap:** Fora de escopo declarado no PRD. Requer decisoao arquitetural para inclusao.

---

## 2. Proposta Comercial ou Contrato

Nao foi encontrado nenhum documento de proposta comercial formal, contrato de prestacao de servicos, SLA, precificacao ou termo de abertura no diretorio `docs/`. A unica referencia indireta a valor esta no PRD v2.0:

> "Servico de consultoria, nao SaaS" (Won't Have W3)
> "Budget mensal: ~$75/mes (Hetzner VPS ~15EUR/mes + OpenAI ~$30-50/mes + Dominios/Misc ~$10/mes)"
> "Single client (Extra Construtora)"

O contexto estratefico mudou durante a auditoria de 2026-07-14 (audit-b2g-readiness):
> "Contexto estrategico atualizado: De 'Extra Construtora analytics' para 'CONFENGE commercial intelligence'"

**Conclusao:** Nao ha contrato ou proposta formal documentada. O modelo de negocio e consultoria B2G (Business-to-Government) onde a Extra Consultoria vende inteligencia de licitacoes para a Extra Empreiteira (e potencialmente CONFENGE). Sem contrato documentado, nao e possivel validar SLAs, entregaveis contratuais ou valor financeiro acordado.

---

## 3. Decisoes Recorrentes da Extra Empreiteira

Com base na analise do perfil do cliente (`config/client_profiles/extra.yaml`) e nas capacidades do sistema, as decisoes recorrentes sao:

### 3A. Decisao de Perseguicao (Pursuit Decision)
**Descricao:** Decidir se a empreiteira deve ou nao preparar proposta para um edital especifico.
**Criterios atuais (do perfil extra.yaml):**
- Distancia maxima: 200km de Florianopolis
- Objetos desejados: reforma predial, manutencao predial, construcao de edificios publicos
- Hard blocks: prazo futuro, nao terminal/suspenso
- Scoring: data_confidence (70% minimo) + client_fit (55% minimo)
**Frequencia:** Diaria (editais sao publicados continuamente)
**Responsavel:** Tiago Sasaki (consultor), reportando ao decisor da construtora
**Sistema atual:** Sem automatizacao — depende de busca manual nos portais

### 3B. Decisao de Precificacao (Pricing Decision)
**Descricao:** Definir o valor da proposta com base em precos historicos praticados por orgaos similares.
**Criterios:** Valor homologado historico por orgao, modalidade, objeto similar
**Frequencia:** Semanal (a cada edital de interesse)
**Responsavel:** Tiago Sasaki / Diretor da construtora
**Sistema atual:** Manual — levantamento em planilhas, sem baseline estruturada
**Gap critico:** Todas as 4 metricas comerciais estao NOT_READY

### 3C. Decisao de Alocacao (Resource Allocation)
**Descricao:** Em qual(is) edital(is) concentrar recursos de proposta (tempo, engenheiros, documentacao).
**Criterios:** Probabilidade de vitoria, ticket medio, prazo, margem estimada
**Frequencia:** Semanal (ciclo de reuniao de diretoria)
**Responsavel:** Diretoria da construtora
**Sistema atual:** Sem suporte — decisao baseada em experiencia e relacionamento

### 3D. Decisao de Parceria / Subempreitada
**Descricao:** Identificar concorrentes que ganham contratos similares e avaliar parceria ou subempreitada.
**Criterios:** Vencedores historicos por orgao, ticket medio, especializacao
**Frequencia:** Mensal
**Responsavel:** Tiago Sasaki / Diretor Comercial
**Sistema atual:** Manual — consulta a vencedores conhecidos, sem base dados sistematizada

### 3E. Decisao de Expansao Geografica
**Descricao:** Quais municipios/regioes tem maior concentracao de licitacoes no perfil da empresa.
**Criterios:** Volume de contratos no raio 200km, orgaos compradores ativos, concorrencia por regiao
**Frequencia:** Mensal / Trimestral
**Responsavel:** Diretoria
**Sistema atual:** Manual — baseada em experiencia regional

### 3F. Decisao de Segmentacao (Qual orgao priorizar)
**Descricao:** Identificar orgaos publicos com maior potencial (volume, prazo de pagamento, recorrencia).
**Criterios:** Historico de contratacoes, pontualidade, modalidades utilizadas
**Frequencia:** Mensal
**Responsavel:** Tiago Sasaki
**Sistema atual:** Sem suporte — ranking de orgaos nao implementado

---

## 4. Gargalos Operacionais de Tiago Sasaki

### Gargalo 1 — PostgreSQL Offline (CRITICAL)
**Problema:** O banco PostgreSQL esta offline (porta 5433 timeout confirmado em auditoria de 2026-07-14). Sem banco, 0% dos CLIs funcionam: `local_datalake.py`, `opportunity_intel/cli.py`, `panorama.py`, `healthcheck.py` — todos dependem de `LOCAL_DATALAKE_DSN`.
**Impacto:** Zero valor comercial entregue. O sistema e uma casca de codigo sem dados.
**Tempo para resolver:** ~30 minutos (docker compose up + aplicar migrations + seed)
**Evidencia:** Auditoria Max Evolution C1: "PostgreSQL offline → 0% valor comercial entregue"

### Gargalo 2 — Dados sem Freshness Comprovada (CRITICAL)
**Problema:** Mesmo com banco online, a cobertura de freshness e parcial. Apenas PNCP tem dados: 479 entes fresh (43.8%), 605 unknown. 9 fontes com 0 entidades verificadas. 10930 combinacoes entidade+fonte sem evidencia.
**Impacto:** Qualquer analise sobre dados existentes pode estar baseada em dados obsoletos. O `freshness_gate.py` existe (exit code 2 para stale/never) mas nunca e executado.
**Evidencia:** `docs/coverage-truth/coverage-truth-2026-07-12.md`

### Gargalo 3 — Credenciais Bloqueadas (ALTO)
**Problema:** 7 de 14 crawlers bloqueados por credenciais nao obtidas:
- DOM-SC: falta DOM_SC_CPF, DOM_SC_CNPJ, DOM_SC_API_KEY
- DOE-SC: falta DOE_SC_LOGIN, DOE_SC_PASSWORD
- MiDES/BigQuery: requer credenciais Google Cloud
- SC Compras: portal offline
- Transparencia: 75/295 portais detectados, crawl nunca executado

**Impacto:** Monocultura de dados — 100% dos dados vem de PNCP. Sem diversificacao de fontes, a cobertura e parcial e o valor consultivo e limitado.
**Evidencia:** Auditoria B2G Readiness secao 3.3

### Gargalo 4 — VPS Hetzner Nunca Provisionada (ALTO)
**Problema:** A infraestrutura de producao (Hetzner VPS, 4 vCPU, 8GB RAM, 160GB SSD) nunca foi provisionada. Os scripts de deploy existem (`deploy/provision-vps.sh`, 405 linhas; `deploy/install.sh`, 82 linhas) mas nunca foram executados. 20 systemd timer pairs existem como arquivos, nenhum ativo.
**Impacto:** crawlers rodam localmente (WSL), sem permanencia 24/7, sem automacao de coleta, sem backups rodando.
**Evidencia:** Auditoria B2G Readiness secao 2.4, ontologies secao 5

### Gargalo 5 — Schema Banco vs Codigo Divergente (ALTO)
**Problema:** 10 tabelas referenciadas no codigo nao existem no banco. Migration v3 (`006-v3-unified-schema.sql`) nunca aplicada. Column name mismatch entre crawler e SQLite. 6 denominadores de universo diferentes (1.093, 1.448, 1.481, 1.697, 2.085, 1.000).
**Impacto:** Manifestos reportam numeros inconsistentes (ex: coverage de 265.95% matematicamente impossivel). Relatorios contradizem uns aos outros.
**Evidencia:** Auditoria B2G Readiness SCHEMA-01, UNIVERSE-01, MANIFEST-01

### Gargalo 6 — Producao Manual de Relatorios (MEDIO)
**Problema:** Nao existe comando `briefing-diario`. O pipeline Intel (7 stages) nunca completa — Step 5 e manual, Step 7 (`intel_report.py`) nao existe fisicamente. Os relatorios PDF e Excel exigem execucao manual de multiplos scripts.
**Impacto:** Tiago gasta tempo operacional (setup de ambiente, verificacao de dados) ao inves de tempo consultivo (analise, recomendacao).
**Evidencia:** Auditoria Full-Spectrum B2G secao 5, auditoria Max Evolution C5

### Gargalo 7 — Confianca em "Done" Falso (MEDIO)
**Problema:** Multiplas stories marcadas como "Done" tem ACs nao verificados em ambiente real. FEAT-4.1 (VPS) marcada Done mas VPS nunca provisionada. TD-8.5 (backfill) marcada Done com 39.4% coverage contra meta de 85%+. ACs rebaixados durante QA para aprovar story.
**Impacto:** Tiago nao pode confiar no status reportado pelo sistema. O estado real e sempre pior que o documentado.
**Evidencia:** Auditoria B2G Readiness secao 3.1

---

## 5. Informacoes que Tiago Precisa Produzir Manualmente Hoje

Com base na analise de capacidades vs gaps, Tiago Sasaki produz manualmente:

### 5A. Lista de Editais Abertos Viaveis
**Como faz hoje:** Navegacao manual em PNCP, DOM-SC e portais municipais.
**Custo:** 2-4h/dia de busca + triagem manual
**O que o sistema deveria fazer (e nao faz):** `opportunity_intel/cli.py list --ranking GO --limit 10` — mas PostgreSQL offline.

### 5B. Estimativa de Preco para Proposta
**Como faz hoje:** Consulta a precos historicos conhecidos, contatos, planilha pessoal.
**Custo:** 1-3h por proposta
**O que o sistema deveria fazer:** `valor_contratado` historico por orgao/modalidade + desagio estimado — mas metricas NOT_READY.

### 5C. Analise de Concorrentes por Edital
**Como faz hoje:** Conhecimento de mercado, relacao com concorrentes, ligacoes.
**Custo:** 30min-1h por edital
**O que o sistema deveria fazer:** `v_supplier_winners` com HHI, ranking de vencedores por orgao — mas dados nao populados.

### 5D. Relatorio de Panorama Setorial para Diretoria
**Como faz hoje:** Planilha Excel manual compilando dados de diversas fontes.
**Custo:** 4-8h/mensal (reuniao de diretoria)
**O que o sistema deveria fazer:** `panorama.py` com PDF Big Four + Excel — mas pipeline incompleto.

### 5E. Acompanhamento de Contratos Vincendos
**Como faz hoje:** Planilha de controle proprio, sem automacao.
**Custo:** 2-4h/semanal
**O que o sistema deveria fazer:** Views de contratos com `data_fim_vigencia` — mas 98% dos contratos sem este campo populado.

### 5F. Decisao de Perseguicao (Go/No-Go)
**Como faz hoje:** Intuicao + experiencia + poucos dados estruturados.
**Custo:** Decisao de alto valor sem suporte analitico
**O que o sistema deveria fazer:** Scoring deterministico GO/REVIEW/NO_GO — mas sem dados para alimentar.

---

## 6. Outputs que Poderiam Ser Apresentados ao Cliente Imediatamente

Mesmo com o estado atual (PostgreSQL offline, metricas NOT_READY), existem outputs viaveis com dados ja disponiveis ou com esforco minimo:

### Output Imediato Nivel 1 — Com Banco Subindo (30 min)
**Pre-requisito:** docker compose up + migrations + seed

| Output | Script | Dados | Valor Percebido |
|--------|--------|-------|-----------------|
| Lista de editais abertos priorizados | `opportunity_intel/cli.py list --ranking GO` | PNCP API live | ALTO — substitui 2-4h de busca manual |
| Coverage report de orgaos SC | `monitor.py --report-coverage` | Entity seed 2.085 orgaos | MEDIO — mostra quem esta sendo monitorado |
| Source health (quais fontes funcionam) | `opportunity_intel/cli.py source-health` | Ingestion runs | MEDIO — diagnostico de cobertura |
| Estatisticas do DataLake | `local_datalake.py stats` | Bids existentes | BAIXO-MEDIO — volume bruto sem analise |
| Fornecedores vencedores historicos | `local_datalake.py supplier --cnpj` | Contracts (se populados) | ALTO-MEDIO — se contratos estiverem no banco |

### Output Imediato Nivel 2 — Com Dados PNCP (1-2 dias)
**Pre-requisito:** Crawl PNCP incremental executado

| Output | Script | Volume Estimado | Valor Percebido |
|--------|--------|-----------------|-----------------|
| Relatorio panorama PDF + Excel | `panorama.py --output-excel` | ~1.694 editais abertos | ALTO — apresentavel a diretoria |
| Oportunidades ranking GO | `cli.py list --ranking GO --limit 20` | ~20 oportunidades | ALTO — acao imediata |
| Export CSV de oportunidades | `cli.py export --format csv` | ~1.694 linhas | MEDIO — analise em Excel |
| Manifesto de cobertura | `manifest.py` | 1.093 entes no raio 200km | MEDIO — baseline para melhoria |

### Output Imediato Nivel 3 — Com Dados Contratuais (2-5 dias)
**Pre-requisito:** Contracts crawler executado (backfill)

| Output | Script | Volume Estimado | Valor Percebido |
|--------|--------|-----------------|-----------------|
| Contract Intelligence Report | `contract_intel/cli.py` | ~423.239 contratos (se PNCP) | ALTO — precificacao, concorrentes |
| Supplier ranking com HHI | View `v_supplier_winners` | 63.679 fornecedores | ALTO-MEDIO — concentracao de mercado |
| Ticket medio por concorrente | View `v_supplier_winners` | Por fornecedor | ALTO — baseline de precos |

### Output Imediato Nivel 4 — Sem Banco (Hoje, sem PostgreSQL)
| Output | Forma de Obter | Valor |
|--------|----------------|-------|
| Listagem de 14 crawlers com status | Leitura de codigo + auditorias | BAIXO — informativo |
| Perfil do cliente (extra.yaml) | `config/client_profiles/extra.yaml` | BAIXO — ja conhecido |
| Diagnostico de cobertura teorica | Auditorias em `docs/audits/` | MEDIO — mostra gaps |
| Mapa de fontes de dados | `docs/architecture/system-architecture.md` | BAIXO — documentacao |

---

## 7. Valor Financeiro Estimado por Tipo de Decisao

Valores sao estimativas baseadas no mercado de consultoria B2G e no porte presumido da Extra Empreiteira (media/grande construtora catarinense). Tabela comparativa com e sem o sistema:

### 7A. Decisao de Perseguicao (Go/No-Go)
| Sem sistema | Com sistema | Ganho |
|-------------|-------------|-------|
| 2-4h/dia de busca manual em 5+ portais | 30s de CLI com ranking deterministico | ~4h/semana liberadas = R$ 800-1.600/semana (custo hora consultor R$ 50-100/h) |
| Taxa de acerto estimada: 30% (intuicao) | Taxa de acerto potencial: 60%+ (dados + scoring) | 2-3 editais viaveis adicionais/mes com ticket medio estimado R$ 500K-2M |
| Risco de perder edital relevante: ALTO | Risco reduzido por cobertura sistematizada | 1-2 editais perdidos/mes recuperados |

**Valor estimado anual:** R$ 100K-500K (em editais adicionais capturados)

### 7B. Decisao de Precificacao
| Sem sistema | Com sistema | Ganho |
|-------------|-------------|-------|
| Preco baseado em experiencia e convivencia de mercado | Preco baseado em historico real de valores homologados por orgao+modalidade | Margem 2-5% melhor (evitar superfaturamento que perde licitacao ou subfaturamento que reduz margem) |
| Risco de desagio inadequado: perder proposta (preco alto) ou margem (preco baixo) | Desagio calculado com baseline de dados reais | 1-2 propostas adicionais vencidas/ano |

**Valor estimado anual:** R$ 200K-1M (em margem adicional + propostas vencidas)

### 7C. Decisao de Alocacao de Recursos
| Sem sistema | Com sistema | Ganho |
|-------------|-------------|-------|
| Times de proposta dedicados a editais com baixa chance de vitoria | Alocacao baseada em scoring de leads + probabilidade de vitoria | 10-20% de eficiencia da equipe de propostas |
| Custo de proposta: R$ 5K-20K por edital (engenheiro, documentacao, garantia) | Reducao de propostas em editais com baixo score | Economia de R$ 50K-200K/ano em propostas nao realizadas |

**Valor estimado anual:** R$ 50K-200K (economia em propostas mal direcionadas)

### 7D. Decisao de Parceria / Subempreitada
| Sem sistema | Com sistema | Ganho |
|-------------|-------------|-------|
| Parcerias baseadas em networking | Parcerias baseadas em dados de vencedores historicos + ticket medio | 1-2 parcerias adicionais/ano em editais de maior porte |
| Risco de escolher parceiro sem capacidade comprovada | Due diligence baseada em historico real | Reducao de risco de proposta conjunta |

**Valor estimado anual:** R$ 100K-300K (em parcerias viaveis adicionalmente)

### 7E. Decisao de Segmentacao de Orgaos
| Sem sistema | Com sistema | Ganho |
|-------------|-------------|-------|
| Foco em orgaos conhecidos (relacionamento) | Foco em orgaos com maior volume, recorrencia e margem | 20-30% mais eficiencia na prospeccao |
| Risco de concentrar em poucos orgaos | Carteira diversificada com 404+ orgaos compradores | Reducao de risco de dependencia de 1-2 orgaos |

**Valor estimado anual:** R$ 50K-150K (em eficiencia de prospeccao)

### Tabela Resumo de Valor

| Decisao | Frequencia | Valor Unitario Estimado | Valor Anual Estimado | Confianca |
|---------|-----------|------------------------|---------------------|-----------|
| Perseguicao (Go/No-Go) | Diaria (5-10/dia) | R$ 200-1.000/lance adicional | R$ 100K-500K | MEDIA |
| Precificacao | Semanal (2-3/semana) | R$ 5K-50K/proposta (margem) | R$ 200K-1M | BAIXA |
| Alocacao de recursos | Semanal | R$ 1K-5K/proposta (eficiencia) | R$ 50K-200K | BAIXA-MEDIA |
| Parceria / Subempreitada | Mensal | R$ 10K-50K/parceria | R$ 100K-300K | BAIXA |
| Segmentacao de orgaos | Mensal | R$ 5K-15K (eficiencia) | R$ 50K-150K | BAIXA |
| **Total estimado** | | | **R$ 500K-2.15M/ano** | |

**Nota:** Confianca BAIXA reflete ausencia de dados financeiros reais do negocio da Extra Empreiteira. Os valores sao estimativas de mercado B2G para construtora de medio porte em Santa Catarina com atuacao em licitacoes publicas. Para refinamento, seria necessario obter: ticket medio real da Extra Empreiteira, numero de propostas/mes, taxa de vitoria atual e margem media.

---

## 8. Frequencia de Cada Tipo de Decisao

### Diaria
| Decisao | Volume | Janela | Cenario Atual |
|---------|--------|--------|---------------|
| Perseguicao (Go/No-Go) | 5-10 editais/dia para triar | 24-48h (prazo de proposta) | Manual, 2-4h/dia de Tiago |
| Verificacao de freshness | 1x/dia | 24h SLA | Nao realizada (freshness_gate.py nunca executado) |

### Semanal
| Decisao | Volume | Janela | Cenario Atual |
|---------|--------|--------|---------------|
| Precificacao | 2-3 propostas/semana | 5-10 dias uteis | Manual, 1-3h/proposta |
| Alocacao de recursos | 1 reuniao de diretoria | Semanal | Sem suporte analitico |
| Relatorio de cobertura semanal | 1x/semana | Segunda-feira | Script existe, nunca automatizado |

### Mensal
| Decisao | Volume | Janela | Cenario Atual |
|---------|--------|--------|---------------|
| Segmentacao de orgaos | 1 revisao/mes | Mensal | Sem suporte |
| Parceria / Subempreitada | 1-2 avaliacoes/mes | Mensal | Manual, networking |
| Relatorio panorama setorial | 1x/mes | Reuniao de diretoria | Manual, 4-8h de trabalho |

### Trimestral
| Decisao | Volume | Janela |
|---------|--------|--------|
| Expansao geografica | 1 revisao/trimestre | Trimestral |
| Revisao de perfil de cliente | 1x/trimestre | Apos 3 meses de dados |
| Benchmark de cobertura vs meta 95% | 1x/trimestre | Apos backfill completo |

---

## 9. Linha do Tempo Recomendada para Gerar Valor

Com base nos gargalos identificados e nos outputs viaveis, a sequencia recomendada para entregar valor comercial ao cliente e:

### Semana 1 (Fase 0 — Desbloqueio)
| Acao | Tempo | Output | Valor Gerado |
|------|-------|--------|-------------|
| Subir PostgreSQL + aplicar migrations | 30 min | Banco online | Desbloqueia todos os CLIs |
| Executar crawl PNCP incremental | 2h | Editais abertos no banco | Primeira lista de oportunidades |
| Rodar `opportunity_intel/cli.py list --ranking GO` | 30s | 10-20 leads priorizados | ALTO — Tiago deixa de buscar manualmente |

### Semana 2 (Fase 1 — Primeiro Entregavel ao Cliente)
| Acao | Tempo | Output |
|------|-------|--------|
| Gerar panorama PDF + Excel | 1h | Relatorio apresentavel a diretoria |
| Exportar CSV de oportunidades | 30s | Planilha para decisor |
| Corrigir URL PNCP (B2G-FIX-01) | 4-6h | Crawler funcional com URL correta |

### Semana 3-4 (Fase 2 — Infraestrutura)
| Acao | Tempo | Output |
|------|-------|--------|
| Provisionar VPS Hetzner | 4-6h | Crawlers 24/7 |
| Configurar systemd timers | 2-4h | Automacao de coleta |
| Backup automatizado + restore testado | 4-6h | Seguranca operacional |

### Mes 2 (Fase 3-4 — Dados)
| Acao | Tempo | Output |
|------|-------|--------|
| Backfill PNCP contratos | 6-8h + execucao | Contratos historicos no banco |
| Ativar PCP + ComprasGov | 4-6h cada | Diversificacao de fontes |
| Obter credenciais DOM-SC | Externa | Desbloqueia 280 municipios SC |

### Mes 3 (Fase 5 — Inteligencia)
| Acao | Tempo | Output |
|------|-------|--------|
| Pipeline de sinais comerciais | 12-16h | Preco praticado, desagio |
| Scoring de leads 12 dimensoes | 6-8h | Priorizacao refinada |
| Dossie automatico por oportunidade | 8-12h | Entregavel consultivo completo |

---

## 10. Riscos Comerciais

### Risco 1 — CONFENGE sem contrato formalizado
O contexto mudou de Extra Construtora para CONFENGE, mas nao ha contrato, SLA ou termo de abertura documentado. Risco de trabalhar em entregavel sem alinhamento de expectativas.
**Mitigacao:** Documentar escopo, entregaveis e valor antes de avancar.

### Risco 2 — Dependencia de PNCP (monocultura)
100% dos dados vem de PNCP. Se a API PNCP mudar de URL novamente (ja aconteceu), todo o sistema para. Se a API for descontinuada ou rate-limited, nao ha fallback.
**Mitigacao:** Ativar fontes complementares (PCP, ComprasGov) como prioridade maxima.

### Risco 3 — Credenciais externas nunca obtidas
DOM-SC e DOE-SC estao bloqueados por credenciais que dependem de terceiros. Sem essas fontes, a cobertura de SC nunca ultrapassara ~50%.
**Mitigacao:** Iniciar com PNCP + PCP + ComprasGov. Tratar DOM-SC/DOE-SC como ganho marginal, nao como dependencia critica.

### Risco 4 — Ciclo de desenvolvimento part-time
PRD estima 10-15h/semana de Tiago para desenvolvimento. O roadmap de 3 meses para entregar valor real requer ~250-340h de trabalho (auditoria B2G). Isso significa 4-6 meses no ritmo atual.
**Mitigacao:** Priorizar entregas de valor imediato (Semanas 1-2) antes de investir em infraestrutura complexa.

### Risco 5 — Confusao entre "Done (script)" e "Done (producao)"
O maior risco comercial e a diferenca entre o que o sistema parece ser (baseado em documentacao) e o que realmente entrega (baseado em dados reais em producao). Atualmente, 0% de capacidade comercial real.
**Mitigacao:** Estabelecer gate objetivo para cada entregavel: "so esta pronto quando executou em producao e gerou output."

---

## 11. Conclusao

O projeto Extra Consultoria tem **base tecnica solida** (~117K LOC Python, 14 crawlers, 41 migrations, 1.230 testes, scoring deterministico, CLI funcional, documentacao extensa) mas **zero entrega comercial no momento presente** devido ao PostgreSQL offline, VPS nunca provisionada e metricas comerciais bloqueadas.

O valor potencial e estimado em **R$ 500K-2.15M/ano** para a Extra Empreiteira, concentrado em 5 tipos de decisao (perseguicao, precificacao, alocacao, parceria, segmentacao).

O primeiro entregavel ao cliente (lista de oportunidades priorizadas + relatorio panorama) pode ser gerado **em menos de 2 horas de trabalho** apos subir o banco PostgreSQL, que leva 30 minutos.

O maior risco comercial e conceitual: o sistema parece mais pronto do que realmente esta devido a documentacao inflada (stories "Done" com ACs nao verificados). A realidade e que nenhum crawler opera em producao, nenhum backup foi testado com restore real, e 7 das 14 fontes estao bloqueadas.

**Recomendacao:** Priorizar a entrega de valor imediato (banco online + crawl PNCP + primeiro relatorio ao cliente) antes de investir em infraestrutura de longo prazo. O cliente precisa ver um resultado concreto para justificar o investimento continuo no projeto.
