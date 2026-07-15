# Red Team Econômico — Feature Audit

**Data:** 2026-07-14
**Contexto:** Investigacao READ-ONLY sobre 7 apostas de feature para a Plataforma de Inteligencia em Licitacoes da Extra Construtora
**Metodo:** Exame de codigo, PRD, manifests, coverage-truth, data, e docs existentes
**Posicao:** Cetico -- demonstrar que a feature NAO deve ser construida AGORA

---

## Sumario Executivo

Das 7 apostas examinadas, **nenhuma deveria ser implementada no estado atual do projeto**. O motivo nao e que as ideias sao ruins em si -- e que o projeto tem problemas estruturais nao resolvidos que tornariam qualquer construcao nessas areas um exercicio de vaidade tecnica:

1. **604 entidades sem coordenadas** impedem cobertura confiavel (<64.4%)
2. **Metricas comerciais ALL NOT_READY** -- sem preco praticado, desagio, ou win rate
3. **15 contradicoes de manifest** documentadas (fase 0 audit) -- numeros nao fecham
4. **8/11 systemd timers pendentes** -- automacao basica incompleta
5. **Extra Ledger tem 1 (UMA) oportunidade registrada** -- zero uso real
6. **Budget part-time (~10-15h/semana)** -- construir features novas em vez de estabilizar e'sucumba'

> **Tese central:** O valor do sistema hoje nao esta em features exoticas. Esta em ter dados limpos, coverage real >90%, e metricas comerciais basicas funcionando. Tudo o mais e' wishful thinking.

---

## 1. Oportunidade->Decisao Pipeline

**O que seria:** Pipeline automatizado que classifica oportunidade, verifica aderencia ao perfil da Extra, gera briefing, e recomenda participar ou nao.

### O que JA existe

O modulo `opportunity_intel/` ja implementa:

- **Radar** (`radar.py` 32K LOC) -- orquestracao QW-01 com scoring, positivo/negativo, recomendacao triage (PRIORITARIA/REVISAR/DESCARTAR)
- **Scoring** (`scoring.py` 9K LOC) -- `RadarScores` com `data_confidence_score` e `client_fit_score`, pesos configuraveis por perfil
- **Ranking** (`ranking.py` 14K LOC) -- ranking de oportunidades priorizadas
- **CLI** (`cli.py` 29K LOC) -- comandos `list`, `show`, `explain`, `coverage`, `source-health`, `update`, `export`, `radar`
- **Perfil de cliente** (`config/client_profiles/extra.yaml`) -- pesos, termos, setores, thresholds de triagem
- **Extra Ledger** (`extra_ledger/cli.py` 19K LOC) -- registro manual de decisoes (participar/nao participar), propostas, contratos

### Argumento contra implementar

**A decisao ja pode ser tomada manualmente em poucos minutos?** Sim, e ja e. O radar ja produz triagem (PRIORITARIA/REVISAR/DESCARTAR) com scoring explicito. O CLI `explain` mostra os fatores. O que falta nao e pipeline -- e uso real.

**Os dados sao suficientes para uma recomendacao confiavel?** Nao. O `data_confidence_score` depende de:
- Dados de fonte oficial PNCP (ok)
- Entity matching confiavel (parcial -- 604 entidades sem coordenadas)
- Freshness dentro da janela (479 fresh, 605 unknown -- METADE desconhecida)
- Preco estimado vs. valor contratado (comercial NOT_READY)

Uma recomendacao automatizada com dados de cobertura <65% e metrica comercial inexistente nao e inteligencia -- e ruido com formato bonito.

**Tiago realmente usaria isso semanalmente?** O Extra Ledger tem 1 (uma) oportunidade registrada desde que foi criado. O ledger proprietario de decisoes esta vazio. Quem nao registra a decisao manual, nao vai confiar na decisao automatica. O comportamento real de Tiango mostra que o processo de decisao ainda e' humano e ocorre fora do sistema.

**Veredito:** NAO CONSTRUIR. O que precisava ser construido ja foi (radar + scoring + CLI + ledger). O que falta e adocao, dados limpos, e metricas comerciais. Automa'cao adicional aqui e' automatizar o vazio.

--------------------------------------------------

## 2. Monitoramento Executivo Periodico

**O que seria:** Relatorio semanal/mensal automatico com panorama do mercado, novos editais, tendencias.

### O que JA existe

- **Relatorio Panorama** (`reports/panorama.py` 12K LOC) -- PDF (Big Four aesthetic) + Excel setorial
- **Relatorio Cobertura Semanal** (`reports/coverage_weekly.py` 44K LOC) -- cobertura por fonte
- **Coverage Truth** (`coverage-truth-2026-07-12.md`) -- auditoria de verdade
- **Health Dashboard** (`health-dashboard.py` 16K LOC) -- CLI dashboard com `--watch`
- **3/11 systemd timers ativos** -- pncp-crawl-full, pncp-crawl-inc, coverage-report
- **Script de geração de relatorio B2G** (`generate-report-b2g.py` 288K LOC)

### Argumento contra implementar

**O cliente pediu isso?** Nao ha' evidencia no PRD, nas stories, ou nos gaps registrados de que a Extra Construtora tenha pedido um relatorio executivo automatico. O PRD lista "relatorio panorama" como M5 e ele ja existe. A demanda documentada e' por dados frescos e cobertura, nao por mais relatorios.

**Os dados mudam com frequencia suficiente para justificar?** O coverage manifest mostrou que 605 entidades tem "unknown" freshness. 9 estao stale. A frequencia de mudanca real dos dados nao e' diaria ou semanal para a maioria das entidades -- o que muda e' a coleta, nao os dados subjacentes. Um relatorio automatico que mostra os mesmos numeros toda semana e' barulho.

**E' so' um dashboard bonito ou muda decisoes?** O relatorio Panorama ja existe em PDF + Excel. A pergunta que o relatorio executivo responde e' "devo participar deste edital?" -- e isso o radar + CLI ja faz. Um relatorio periodico generico (numero de editais abertos por setor, ticket medio) nao muda nenhuma decisao de participacao. Decisoes sao tomadas por edital especifico, nao por tendencia macro.

**O custo de oportunidade:** Cada hora gasta formatando relatorio executivo e' uma hora nao gasta resolvendo os 604 unresolved ou fazendo os 8 timers faltantes funcionarem.

**Veredito:** NAO CONSTRUIR. O relatorio Panorama ja entrega o valor executivo. Automacao de periodicidade (systemd timers) ja esta' planejada e parcialmente implementada. Completar os timers e' suficiente. Qualquer coisa adicional e' estetica.

--------------------------------------------------

## 3. Dossie Automatizado de Edital

**O que seria:** Baixar edital automaticamente, extrair requisitos, prazos, riscos, gerar dossie estruturado.

### Contexto tecnico real

Edital no Brasil:
- **Formatos:** PDF escaneado (imagem), PDF digital nativo, DOCX, HTML, JPG de mural fisico
- **Orgaos:** ~2.085 entes SC, cada um com portal proprio, layout proprio, parser proprio
- **PNCP API** publica nao expoe propostas perdedoras, valores homologados item a item, nem empenhos
- **DOM-SC** muda formato HTML com frequencia (risco documentado no PRD)
- **Transparencia municipal** e' gap-fill -- portais instaveis por natureza

### Argumento contra implementar

**Editais sao estruturados o suficiente para extracao automatica?** Nao. Editais brasileiros sao notoriamente desestruturados:
- Objeto descrito em linguagem natural variavel
- Requisitos de habilitação espalhados em segoes diferentes
- Prazos em formatos inconsistentes ("30 dias", "30/06/2026", "30 de junho de 2026")
- Anexos como plantas, planilhas, memoriais descritivos em formatos variados

**Formatos variam entre orgaos -- o parser quebraria constantemente?** Sim. O DOM-SC ja quebra quando muda HTML. Agora multiplique isso por 2.085 orgaos com portais diferentes. Cada orgao publica edital do seu jeito. Um parser generalista para edital Brasileiro e' um problema de P&D que empresas como JusBrasil levam anos resolvendo com equipes dedicadas.

**PDFs de edital sao frequentemente imagens escaneadas?** Sim. Edital escaneado (imagem, nao texto) e' a norma em orgaos menores. Isso exige OCR, que:
- Erra em documentos com layout complexo
- Nao extrai tabelas corretamente (planilhas de preco)
- Tem custo de API (se usar OCR cloud) ou complexidade de setup (se usar Tesseract local)
- Processamento de lote para 1.694 editais abertos exigiria horas de CPU

**O que ja existe:** O modulo `pncp_audit.py` (22K LOC) ja faz monitoramento de abertos. O `radar.py` ja cruza com entidades e perfis. O **valor real** nao esta no dossie do edital -- esta em saber que o edital existe e se e' relevante. A leitura do edital e' uma atividade de alto valor que um consultor experiente (Tiago) faz melhor que um parser generico.

**Veredito:** NAO CONSTRUIR. Este e' o maior "vale da morte" tecnico da lista. Tentar parser de edital brasileiro automatico e' um projeto de 6-12 meses que provavelmente nunca atinge precisao aceitavel. O que faz sentido: o radar ja identifica editais relevantes; o humano baixa e le o edital. Isso e' barato, confiavel, e usa a inteligencia onde ela importa.

--------------------------------------------------

## 4. Apoio a Preparacao de Proposta

**O que seria:** Templates, calculo de precos, checklist automatico para preparar propostas.

### O que JA existe

- **Build de dados de proposta** (`build-proposta-data.py` 15K LOC) -- coleta dados para proposta
- **Geracao de proposta PDF** (`generate_proposta_pdf.py` 44K LOC) -- PDF de proposta
- **Simulador de lances** (`bid_simulator.py` -- existe, mencionado no PRD como C2)
- **Extra Ledger** -- registro de propostas apresentadas (vazio: 0 propostas)

### Argumento contra implementar

**Isso nao e' melhor feito no Excel com conhecimento humano?** Sim. A preparacao de proposta envolve:
- Precificacao baseada em custo real de insumos (cimento, aco, mao de obra)
- Conhecimento da regiao (logistica, sindicatos, encargos sociais)
- Margem estrategica (quanto apertar para ganhar vs. quanto arriscar)
- Documentacao de habitilitacao (certidoes, balancos, atestados tecnicos)

O Excel e' a ferramenta certa para isso porque e' flexivel, auditavel, e o engenheiro responsavel pela proposta ja sabe usar. Tentar substituir por automacao e' construir um ERP fiscal do zero.

**O valor esta na automacao ou no conhecimento de negocio?** 100% no conhecimento de negocio. Preco de proposta nao se calcula com template -- se calcula com:
- Planilha de composicao de custos (SINAPI, propria)
- Historico de precos de insumos
- Conhecimento de qual orgao paga em dia vs. atrasa
- Margem para recurso, taxa de administracao, BDI

Nenhum desses fatores esta disponivel como dado estruturado no sistema.

**Checklist automatico:** O que faz sentido e' um checklist de documentos para habitilitacao. Isso e' uma lista estatica (certidao federal, estadual, municipal, FGTS, INSS, balanco, etc.) que pode ser documentada em um README.md. Nao precisa de feature.

**Veredito:** NAO CONSTRUIR. Automacao de proposta e' construir um sistema de precificacao -- um dominio de negocios complexo que a Extra Construtora ja resolve com Excel e conhecimento humano. O sistema de inteligencia deve alimentar a decisao de *participar ou nao*, nao a precificacao da proposta.

--------------------------------------------------

## 5. Acompanhamento Contratual

**O que seria:** Contratos conquistados, marcos, pagamentos, prazos.

### O que JA existe

- **Contract Intel** (`contract_intel/cli.py` 48K LOC) -- historico de contratos, ranking de fornecedores, contratos a expirar (90-180 dias), manifesto de readiness
- **Views PostgreSQL** (`v_contract_historical`, `v_supplier_winners`) -- 423.239 contratos carregados
- **404 entes com contratos** (37% do universo confirmado)
- **Extra Ledger** (`extra_ledger/cli.py`) -- secao de contratos (vazia: 0 contratos registrados)
- **Contract Intelligence Truth v1** (documentada como ADR-001)

### Argumento contra implementar

**A Extra ja tem sistema de ERP para isso?** Provavelmente sim. Empresa de construcao civil de medio porte tem:
- ERP fiscal/contabil (domino, sap, torque, etc.)
- Sistema de gestao de contratos
- Planilha de cronograma fisico-financeiro
- Acompanhamento de obra separado

O dado de "contratos conquistados" e "marcos" vive no ERP, nao no data lake de licitacoes. A Extra Construtora nao vai largar o ERP dela para usar um CLI de consultoria.

**Os dados de execucao contratual estao disponiveis?** Nao. O dado disponivel no PNCP e' o contrato assinado (`valor_global`). O que importa para acompanhamento contratual:
- Medicoes (etapas fisicas executadas)
- Faturamento e recebimento
- Aditivos de prazo e valor
- Reajustes
- Recebimento provisorio e definitivo

Nada disso esta nos dados publicos. Isso e' dado interno da construtora.

**O PRD explicitamente exclui acompanhamento de obras:** "Fora de escopo agora: acompanhamento de obras, gestao de execucao contratual" (PRD secao Viao).

**Veredito:** NAO CONSTRUIR. Acompanhamento contratual e' dado interno de ERP, nao dado publico de licitacao. Construir isso seria duplicar (mal) o que um ERP ja faz, com dados que nao estao disponiveis. O Contract Intel ja fornece o que faz sentido: historico de contratos para analise de mercado.

--------------------------------------------------

## 6. Inteligencia de Compradores e Concorrentes

**O que seria:** Perfil de orgaos compradores, historico de vencedores, analise de concorrencia.

### O que JA existe

- **Buyer Intel** (`buyer_intel/cli.py` 19K LOC + `ranking.py` 10K LOC) -- ranking de compradores, perfil por CNPJ
- **Contract Intel suppliers** (`v_supplier_winners`) -- ranking de fornecedores por qtd, valor, ticket, HHI
- **Competitive Intel Validation** (`competitive_intel_validation.py` 13K LOC) -- validacao de schema para queries de concorrencia
- **Win/Loss Tracker** (`win_loss_tracker.py` -- existe, mas win rate NOT_READY sem tracking de propostas enviadas)
- **Victory Profile** (`victory_profile.py` -- existe, estrutura base)
- **Target Universe** (`target_universe.py` 12K LOC) -- universo-alvo de 1.093 entes

### Argumento contra implementar

**Dados de concorrentes sao completos e confiaveis?** Nao. O que existe:
- Fornecedores vencedores em contratos: PARCIAL -- identifica quem ganhou contratos passados
- Win rate: NOT_READY -- requer saber quantas propostas cada concorrente enviou, o que nao e' dado publico
- Ticket medio por concorrente: PARCIAL -- calculado como `valor_total / qtd_contratos`, mas nao distingue por orgao/setor
- Market share: depende de cobertura de contratos completa (404/1.093 entes = 37% com contratos)

Os dados de concorrentes sao um espelho furado: voce ve quem ganhou, mas nao ve quem tentou. Sem o denominador (propostas enviadas), qualquer "win rate" e' enganoso.

**Isso realmente muda a decisao de participar ou nao?** Duvidoso. A decisao de participar de um edital e' dominada por:
1. Aderencia ao objeto (a Extra faz isso?)
2. Capacidade operacional (tem equipe disponivel?)
3. Viabilidade economica (da margem?)
4. Documentacao em dia (habilitacao ok?)

Saber que "Concorrente X ganhou 3 contratos da Prefeitura de Florianopolis no ultimo ano" e' interessante mas raramente muda a decisao. Se o edital e' bom e a Extra tem capacidade, ela participa. Se nao tem, nao participa. O historico do concorrente informa a precificacao (talvez), nao a decisao.

**O que ja foi construido:** Buyer Intel, Supplier Rankings, Competitive Intel Validation -- essencialmente o que se propoe ja existe como CLI. Falta usar, nao construir.

**Veredito:** NAO CONSTRUIR. O que faz sentido (ranking de compradores, fornecedores vencedores, ticket medio) ja existe. Melhorar a qualidade dos dados (cobertura de contratos) e' mais importante que adicionar novas analises. Win rate continuara NOT_READY ate que a Extra comece a registrar suas propostas no Extra Ledger -- e ate hoje tem 0 propostas registradas.

--------------------------------------------------

## 7. Melhoria de Dados, Cobertura, Backfill

**O que seria:** Mais fontes, mais historia, backfill de 3 anos, melhoria de cobertura.

### O que JA existe

- **8 crawlers ativos** (PNCP, PNCP-ARP, PNCP-PCA, DOM-SC, PCP, ComprasGov, SC Compras, TCE-SC) + 1 gap-fill (Transparencia)
- **Cobertura atual:** 64.4% (1.093/1.697 conservativo)
- **604 entidades unresolved** (sem coordenadas)
- **Backfill** (`opportunity_intel/backfill.py` 14K LOC) -- multi-source backfill pipeline
- **Pipeline de pipeline** (`intel_pipeline.py`) -- 7-stage pipeline existente
- **9 migrations de schema** aplicadas
- **423.239 contratos** carregados (mas 37% entes apenas)
- **Coverage Truth** instrumentado com auditoria de contradicoes

### Argumento contra implementar

**Vale o esforco antes de ter um uso que justifique?** O uso ja existe -- a plataforma tem dados, tem CLI, tem radar. O problema e' que os dados sao incompletos e contraditorios. Mas isso nao significa que mais dados resolvem.

**Backfill de 3 anos e' necessario ou e' perfeccionismo?** E' perfeccionismo, e perigoso. O PRD ja diz: "na fase corrente, o baseline operacional e' local-first, com prioridade absoluta em freshness auditavel de editais e contratos historicos". Backfill de 3 anos significa:
- Reprocessar 423.239 contratos existentes (possivelmente com schema novo)
- Crawlear historico de fontes que podem ou nao ter dados retroativos
- Validar consistencia com o que ja existe (15 contradicoes ja documentadas)
- Duplicar registros se dedup nao funcionar direito
- Meses de dados com qualidade desconhecida

**O gargalo nao e' cobertura -- e' consistencia.** As 15 contradicoes documentadas na Fase 0 Audit mostram que o problema fundamental e': manifests que nao concordam entre si, queries que retornam numeros diferentes para a mesma metrica, denominadores que mudam conforme quem pergunta. Adicionar mais dados antes de resolver as contradicoes e' construir sobre areia.

**A cobertura real importa menos que a confianca na cobertura.** 64.4% com 604 "unknowns" e' menos valido que 50% com 0 unknowns. Porque com 50% e 0 unknowns voce sabe que os 50% sao reais. Com 64.4% e 604 unknowns, voce nao sabe se e' 64.4% ou 40% ou 80% -- os 604 podem estar dentro ou fora do raio.

**Prioridade correta (documentada no PRD Fase 3):** "B2G-1: Resolver 604 entidades nao resolvidas (geocode via IBGE)". Isto desbloqueia cobertura confiavel. Depois disso, backfill faz sentido.

**Veredito:** NAO CONSTRUIR AGORA. Resolver os 604 unresolved primeiro. Depois de ter um denominador estavel e confiavel, ai sim fazer backfill. Mas backfill de 3 anos e' suspecto: dados de 2023 sao de schema diferente, fontes diferentes, qualidade desconhecida. Backfill util = dados recentes (ultimos 12 meses) com schema atual. O resto e' archive, nao pipeline.

--------------------------------------------------

## Analise Consolidada

### O que o Red Team recomendaria fazer (em vez destas 7 features)

| Prioridade | Acao | Impacto | Esforco estimado |
|---|---|---|---|
| P0 | Resolver 604 entidades sem coordenadas (B2G-1) | Desbloqueia cobertura confiavel | 2-4h (geocode via IBGE + nome municipio) |
| P0 | Corrigir 15 contradicoes de manifest | Dados consistentes, metricas confiaveis | 4-8h (alinhar queries, denominador canonico) |
| P0 | Ativar 8 systemd timers pendentes | Automacao basica funcionando | 2-4h (debug + systemctl enable) |
| P1 | Fechar 604 unknowns em freshness | Saber se dados sao frescos ou nao | 2-6h (crawlear entidades sem cobertura) |
| P1 | Corrigir transaction abort em consulting_readiness.py | Metricas comerciais deixam de crashar | 1h (ROLLBACK apos timeout) |
| P2 | Usar o Extra Ledger de verdade (registrar 1 decisao por semana) | Dado proprietario comeca a existir | 5min/semana (manual) |
| P3 | Completar Contract Intelligence (404/1.093 entes com contratos) | Cobertura de contratos util | 8-16h (depende de crawlers) |

### Features que realmente deveriam ser construidas (quando chegar a hora)

1. **Alertas Telegram (C1 do PRD)** -- baixo esforco, alto valor: "edital relevante apareceu" notifica no celular
2. **Relatorio de sazonalidade (S2)** -- estrutura base existe em panorama.py, precisa de refinement
3. **Dashboard TUI (C4)** -- `rich` dashboard no terminal, esforco moderado, valor visual alto

### Padroes identificados nas 7 apostas

1. **Wishful thinking sobre qualidade dos dados:** Todas as features assumem que os dados sao completos, consistentes, e confiaveis. Eles nao sao. 15 contradicoes, 604 unresolved, freshness 50% unknown.

2. **Substituir processo humano onde ele funciona:** O Tiago consultor toma decisoes, le editais, negocia precos. Tentar automatizar o trabalho do consultor e' construir um sistema para substituir o unico usuario pagante.

3. **Vaidade tecnica:** "Dossie automatizado de edital" e "apoio a proposta" soam impresionantes mas sao projetos de P&D que consomem meses e nunca atingem precisao aceitavel.

4. **Custo de oportunidade ignorado:** Cada feature gasta 2-8 semanas de desenvolvimento part-time (~10-15h/semana) que poderiam ser usadas para estabilizar o baseline.

5. **PRD ja diz "nao":** O PRD explicitamente exclui acompanhamento contratual ("fora de escopo") e define prioridades (Fases 1-7) que nenhuma destas 7 features segue.

### Confianca nas recomendacoes

| Feature | Confianca | Fundamento |
|---|---|---|
| 1. Oportunidade->Decisao | ALTA (90%) | Ja existe, Extra Ledger prova nao-uso |
| 2. Monitoramento executivo | ALTA (90%) | Ja existe, 8/11 timers pendentes |
| 3. Dossie de edital | ALTA (85%) | Problema de P&D, nao de automate |
| 4. Apoio a proposta | ALTA (95%) | Excel faz melhor, PRD exclui |
| 5. Acompanhamento contratual | ALTA (95%) | PRD exclui, ERP existe |
| 6. Intel compradores/concorrentes | MEDIA (75%) | Ja existe, win rate impossivel sem dado proprio |
| 7. Melhoria cobertura/backfill | MEDIA (70%) | Necessario mas nao agora -- resolver contradicoes primeiro |

---

## Post Scriptum: A Unica Feature que Vale

Se eu fosse recomendar UMA unica feature para construir, seria:

**Preco Praticado (B2G-2) -- a metrica comercial que desbloqueia tudo.**

Sem ela:
- O radar nao pode recomendar com confianca ("este edital paga bem?")
- O ranking de compradores e' incompleto ("este orgao paga acima da media?")
- O dossie de edital nao teria analise de preco
- A preparacao de proposta continuaria 100% no Excel

Com ela:
- "Pregoes da Prefeitura de Florianopolis tem desagio medio de 12%"
- "Ticket medio para reforma de escola e' R$ 350-500K na regiao"
- "Concorrente X ganha com margem apertada (desagio medio 8%), Y ganha com margem confortavel (21%)"

Mas isso exige: schema estavel (B2G-5), coverage confiavel (B2G-1), e dados de propostas homologadas que a API PNCP nao expoe. Ou seja: so' faz sentido quando a base estiver limpa e quando Tiago come'car a alimentar o Extra Ledger com dados reais de propostas.

**Ate' la, a feature mais importante e' nao construir features. E' limpar a casa.**

---

_Relatorio gerado por Red Team Economico (investigacao READ-ONLY). Nenhum arquivo de codigo ou configuracao foi modificado._
