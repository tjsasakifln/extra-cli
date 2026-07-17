# Diagnóstico pré-implementação — resiliência local

Data: 2026-07-17  
Branch de trabalho: `feat/local-resilience-ready-20260717`  
Estado observado: **NOT_READY**

Este documento registra o estado confirmado no código antes da implementação da missão de preparação pré-VPS. Ele não reutiliza como fato os claims arquiteturais e não declara `LOCAL_READY`, `VPS_OPERATIONAL` ou cobertura de 95%.

## Superfície auditada

Foram lidos `README.md`, `DOD.md`, ADR-021, arquitetura-alvo, diagnóstico adversarial, stories B2G-E3.S1–S3, registry, contratos de crawler, monitor, orchestrator, PNCP, CIGA público, SC Compras, checkpoint, watermark, DLQ, raw/evidence e freshness.

O registry contém 11 adapters ativos: `pncp`, `ciga_ckan`, `pcp`, `compras_gov`, `sc_compras`, `contracts`, `transparencia`, `tce_sc`, `doe_sc`, `mides_bigquery` e `dom_sc`. Apenas PNCP, CIGA/DOM público e SC Compras estão no escopo de validação operacional desta missão; os demais devem continuar explicitamente legados/não validados para este gate.

## Achados confirmados no código

| Área | Estado anterior | Risco operacional |
|---|---|---|
| Contrato | Existem ao menos três `FetchResult`: ingestion base, opportunity-intel e contracts. O base não possui status semântico, páginas esperadas, resume token, provenance ou warnings. | Dois consumidores podem interpretar a mesma falha de formas diferentes. |
| Monitor | `monitor.py` aceita `list` legada e converte zero sem erro explícito em `empty`; `_map_evidence_state()` converte `empty` em `success_zero`. | **False empty** e cobertura inflada quando o crawler engole erro e retorna `[]`. |
| Estados | `CrawlerResult` usa `success/degraded/failed/skipped/empty`, diferente de ADR-021. | `rate_limited`, `auth_blocked` e `partial` perdem semântica. |
| HTTP PNCP | `_http_get_json()` trata 408, 425, 429 e 5xx com retry finito, backoff, jitter, `Retry-After` e timeouts separados. 401/403 são erros não transitórios. | Após esgotar 429 o retorno não o distinguia semanticamente de outras falhas. |
| PNCP paginação | Há validação de schema e contradição de página vazia; o agregado registra apenas `pages_fetched` em metadata. | Ausência de `pages_expected` agregado e de prova por janela/modalidade. |
| PNCP checkpoint | `crawl(..., resume=True)` usa watermark `source=pncp, scope_key=page`. | Scope global colide entre janela/modalidade; pode pular ou repetir página incorreta. |
| PNCP watermark | Página era commitada após fetch, antes de persistência canônica/evidence no monitor. | Crash entre fetch e persistência pode avançar progresso não confirmado. |
| Circuit breaker | Há implementação e wrapper PNCP, mas o adapter operacional principal não a usa de forma comprovada. | Série de 429 pode consumir todo o job/budget. |
| Request budget | Limites de retries/páginas existem; não há budget diário canônico aplicado ao run. | Job pode exceder o orçamento de requests apesar de retries finitos. |
| CIGA público | `ciga_dom_publications.py` persiste raw, hash, checkpoint por resource/file e evidence. Status terminal ainda inclui `empty/failed/partial`; CLI retorna zero para `partial`. | Scheduler pode interpretar parcial como sucesso. Contrato não é `SourceAdapter`. |
| SC Compras | `run()` possui raw pages, checkpoint, run evidence e dedupe. `crawl()` legado retorna `[]` em falha e o monitor pode gerar `success_zero`. CLI aceita `partial` com exit 0. | False success/empty no caminho legado. |
| Checkpoints | Há formatos em PostgreSQL e JSON específicos por fonte, além de watermark. | Sem source of truth comum, atomicidade e scopes request/page/window/run não são uniformes. |
| DLQ | Migration 045 e `DurableDLQ` preservam payload/erro/retry; `dlq_sync` é fallback. | Deduplicação por hash não é garantida no schema; falha sistêmica pode ser confundida com poison record por chamadores. |
| Raw/provenance | CIGA e SC Compras persistem raw antes de etapas posteriores; PNCP principal calcula hash pós-transform e não persiste cada resposta antes da normalização. | Cadeia raw→canonical incompleta no adapter de referência. |
| Hash | PNCP calcula SHA-256 do JSON raw dentro de `transform`; run evidence também usa hashes de arquivo/JSON. | Contrato do hash canônico não está centralizado. |
| Evidence | Ledger SQL distingue `success_zero/partial/falhas`, mas `monitor.py` pode fabricar `success_zero` a partir de retorno legado vazio e evidence é exception-safe/fail-open se a gravação falhar. | Falta de provenance/completude pode não bloquear cobertura. |
| Freshness | Gate e SLAs existem, porém não dependem de um resumo único que combine último attempt/success, partial, 429, checkpoint e DLQ. | Operador precisa ler artefatos dispersos. |
| Orquestração | `monitor.py` e `orchestrator.py` coexistem. O orchestrator usa checkpoint diário e pode gravá-lo após um retorno agregado sem status ADR-021. | Dois caminhos oficiais e reagendamento confundido com resiliência. |
| systemd | Há muitas units, dois templates `OnFailure` e nomes mistos. | Scheduler existente não prova segurança do pipeline e pode reiniciar sem política semântica. |
| Configuração | Timeouts/retries/delay PNCP e SC estão em constantes/env distintos. | Defaults divergentes e valores inválidos não falham uniformemente no startup. |
| Segurança | Há User-Agent e filtros parciais; raw/evidence podem guardar headers/URLs sem sanitização canônica. | Risco de DSN/token em logs ou provenance por novos adapters. |

## Semântica HTTP observada

| Evento | PNCP anterior | CIGA/SC anterior | Veredito pré-mudança |
|---|---|---|---|
| 401/403 | erro não transitório, sem `auth_blocked` | erro genérico/retorno vazio conforme path | NOT_READY |
| 408/425 | retry PNCP | não uniforme | PARTIAL |
| 429 | retry finito + `Retry-After`; ao esgotar, erro genérico | retry próprio; status agregado não canônico | NOT_READY |
| 500/502/503/504 | retry finito PNCP/SC | CIGA depende do helper | PARTIAL |
| 200 HTML/JSON inválido/schema | PNCP rejeita; paths legados variam | não uniforme | PARTIAL |
| 204/zero | PNCP confirma vazio no request isolado | CIGA/SC não possuem prova uniforme | NOT_READY |

## Decisão de implementação

1. Tornar o contrato em `scripts/crawl/ingestion/_base/crawler.py` a única definição canônica e fornecer adaptador explícito para respostas legadas.
2. Criar source of truth de checkpoint canônico persistente e atômico, com scopes request/page/window/run; watermarks só representam scopes concluídos.
3. Fazer o caminho operacional pré-VPS usar apenas adapters prioritários canônicos; monitor/orchestrator antigos ficam como wrappers legados.
4. Exigir completeness + provenance para evidence satisfatória; `partial`, `rate_limited`, `auth_blocked` e `error` nunca contam.
5. Entregar health/gates/smoke/chaos locais e units systemd apenas preparadas, sem habilitá-las.

## Gate antes da implementação

**NOT_READY**, pelos blockers: contrato paralelo, false empty no monitor, checkpoint PNCP com scope insuficiente, watermark antecipado, evidence sem predicate único de completude, CIGA/SC partial com exit 0, ausência de health consolidado e systemd concorrente.
