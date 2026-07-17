# Pre-VPS Readiness — resiliência local

| Campo | Valor |
|---|---|
| Data | 2026-07-17 |
| Escopo | PNCP, CIGA/DOM-SC público e SC Compras |
| Estado | `LOCAL_RESILIENCE_READY` |
| Não implica | `LOCAL_READY`, `VPS_OPERATIONAL` ou `PROJECT_DONE` |
| Diagnóstico anterior | `docs/operations/LOCAL-RESILIENCE-DIAGNOSIS.md` |

## Decisão

**READY para iniciar o provisionamento futuro da VPS.** O contrato de coleta, os
gates fail-closed e o caminho local controlado são reproduzíveis sem internet e
sem manter uma sessão interativa aberta. Nenhuma VPS foi provisionada ou ativada.

Esta decisão valida a mecânica de resiliência. Ela não declara 95% de cobertura,
freshness real das fontes externas nem scheduler em produção.

## Contrato operacional

O caminho canônico é:

```text
SourceAdapter.fetch(request) -> FetchResult
SourceAdapter.normalize(raw) -> list[CanonicalRecord]  # sem rede
SourceAdapter.health() -> SourceHealth
```

Estados: `success`, `empty_confirmed`, `partial`, `rate_limited`,
`auth_blocked`, `error`. Somente resultados completos, com proveniência,
janela conhecida e sem erro bloqueante podem produzir evidence satisfatória e
avançar watermark.

| Fonte | Contrato | Paginação | `empty_confirmed` | Resume | Validação local |
|---|---|---:|---:|---:|---|
| PNCP | ADR-021 canônico | Sim | Sim, com paginação concluída | janela + modalidade + página | Validado |
| CIGA/DOM-SC público | ADR-021 via bridge raw-first explícito | Por recurso CKAN | Não para zero de entidade | recurso/checkpoint legado projetado | Validado |
| SC Compras | ADR-021 canônico | Virtual sobre bulk | Não para zero de target | ano + página virtual | Validado |
| Demais fontes | Legado explícito | Por adapter | Não validado | Heterogêneo | Não contam para cobertura operacional |

## Separação das quatro camadas

1. Retry HTTP trata uma requisição transitória, com limite e backoff.
2. Checkpoint/resume persiste a fatia e retoma exatamente a pendência.
3. Reagendamento fica a cargo do futuro timer, sem converter falha em sucesso.
4. Evidence/freshness só aceita completude provada e watermark confirmado.

## Source of truth e persistência

- Checkpoint canônico: filesystem persistente em
  `RESILIENCE_CHECKPOINT_PATH`, escrita por `fsync` + `os.replace`.
- Raw: `RESILIENCE_RAW_PATH/<source>/<sha256>.json`, antes de normalize,
  gitignored, deduplicado pelo SHA-256 do JSON canônico.
- Evidence: ledger append-only por source/run/scope em
  `RESILIENCE_EVIDENCE_PATH`.
- Watermark: `RESILIENCE_OPS_PATH/watermarks`; só é gravado depois de evidence
  satisfatória.
- DLQ: `RESILIENCE_DLQ_PATH`, deduplicada por source + payload hash + tipo de
  erro, com replay manual.
- Banco: migration aditiva `054_local_resilience_contract.sql` projeta os
  campos de completude e uma constraint satisfatória fail-closed.

Raw e logs removem headers sensíveis; DSNs não fazem parte da proveniência. O
hash canônico é SHA-256 do JSON serializado com chaves ordenadas. Hashes legados
podem existir nos crawlers antigos, mas não são a identidade do caminho ADR-021.

## Configuração

Todos os valores aceitam override por environment variable e são validados no
startup:

| Variável | Default |
|---|---:|
| `RESILIENCE_CONNECT_TIMEOUT` | 10 s |
| `RESILIENCE_READ_TIMEOUT` | 120 s |
| `RESILIENCE_MAX_RETRIES` | 5 |
| `RESILIENCE_BASE_DELAY` / `MAX_DELAY` | 1 / 60 s |
| `RESILIENCE_JITTER` | 0,2 |
| `RESILIENCE_RATE_LIMIT_FALLBACK` | 60 s |
| `RESILIENCE_REQUEST_DELAY` | 0,5 s |
| `RESILIENCE_PAGE_SIZE` / `MAX_PAGES` | 50 / 200 |
| `RESILIENCE_CIRCUIT_BREAKER_THRESHOLD` | 5 |
| `RESILIENCE_CIRCUIT_BREAKER_COOLDOWN` | 300 s |
| `RESILIENCE_DAILY_REQUEST_BUDGET` | 5.000 |
| `RESILIENCE_FRESHNESS_SLA_HOURS` | 24 h |
| `RESILIENCE_STATE_PATH` | `output/resilience` |

O exemplo completo para o futuro host está em
`deploy/systemd/extra-collector.env.example`.

## Comandos canônicos

```bash
make resilient-smoke
make resilient-local-cycle
make resilience-gate
python3 -m scripts.ops.health
```

O ciclo controlado executa pre-check, validação de migration, health das fontes,
os três adapters, resume, evidence, freshness, contrato de coverage e resumo.
Fixtures nunca incrementam cobertura real. `--live` é opt-in.

Exit codes do health:

- `0`: saudável e dentro do SLA;
- `1`: degradado (partial, checkpoint ou DLQ pendente);
- `2`: bloqueado, rate limited, auth blocked, error ou stale.

## Matriz de requisitos e evidência

| Requisito | Status | Arquivo | Teste/evidência | Risco residual |
|---|---|---|---|---|
| Diagnóstico no código | OK | `LOCAL-RESILIENCE-DIAGNOSIS.md` | inventário de 11 adapters | fontes legadas |
| Contrato canônico | OK | `_base/crawler.py` | `test_fetch_result.py` | compatibilidade legada |
| Fail-closed 429/partial/zero | OK | `crawler.py`, `monitor.py` | `test_local_resilience.py` | comportamento externo |
| PNCP referência | OK | `resilience/adapters.py` | retry + circuit + budget + resume | limites reais da API |
| CIGA e SC Compras | OK | `resilience/adapters.py` | contract/zero/resume | zero de target não provado |
| Checkpoint/resume | OK | `resilience/state.py` | interrupção/no-reprocess | filesystem deve ser persistente |
| Watermark | OK | `resilience/state.py` | 429/partial/crash | transação DB será validada no host |
| DLQ | OK | `resilience/state.py` | poison/dedup/replay | replay ainda manual |
| Raw/proveniência | OK | `resilience/state.py` | hash/dedup/redaction | retenção depende do disco futuro |
| Evidence ledger | OK | state + migration 054 | partial/zero/provenance | migration ainda não aplicada em VPS |
| Observabilidade | OK | `scripts/ops/health.py` | ciclo + freshness SLA | alerta externo não configurado |
| Orquestração local | OK | `resilient_cycle.py`, Makefile | três targets | live depende das fontes |
| Chaos/idempotência | OK | `test_local_resilience.py` | 429/crash/poison/paginação | sem soak real |
| systemd futuro | PREPARADO | `deploy/systemd/extra-crawl-*` | validator estático | não habilitado |
| Segurança | OK local | redaction + gitignore + units | ruff/bandit existente | hardening do host futuro |

## Cenários adversariais comprovados

| Cenário | Resultado esperado e observado |
|---|---|
| 429 | `rate_limited`, checkpoint pendente, evidence não satisfatória, sem watermark |
| Paginação parcial | `partial` quando fetched < expected |
| Resume | página concluída lida do raw; fetch não é repetido |
| Crash após raw/canonical | checkpoint permanece; watermark ausente |
| Zero ambíguo | `partial`, nunca `empty_confirmed` |
| Poison record | DLQ deduplica, lote segue e replay conclui |
| Watermark | commit rejeitado sem evidence completa e proveniência |
| Circuit breaker | abre no threshold e não executa retry infinito |
| Budget | nova fatia é bloqueada após esgotamento diário |

## Systemd preparado, não ativado

Há um serviço por fonte prioritária, timers escalonados, `RandomizedDelaySec`,
`Persistent=true`, `flock`, usuário não-root, `EnvironmentFile`, timeout,
`Restart=no`, journald e `OnFailure=extra-onfailure@%n.service`. O validador
estático impede regressão desses itens. Rate limit preserva o exit code e não
entra em restart infinito.

## Troubleshooting

1. Execute `python3 -m scripts.ops.health` e localize source/status/checkpoint.
2. Em `rate_limited`, preserve o checkpoint; aguarde cooldown/budget e execute o
   mesmo source novamente. Não edite watermark.
3. Em `partial`, compare `pages_fetched`/`pages_expected` e o `resume_token`.
4. Em `error` com 200, inspecione raw/provenance para HTML ou schema drift.
5. Em DLQ, corrija o normalizer e use o replay manual; erro sistêmico continua
   bloqueando o run.
6. Em stale, execute a fonte e só aceite novo `last_success` se a evidence for
   satisfatória.

## Resultados de validação

Registrados em DoD §44. Gate mínimo local (2026-07-17, branch
`feat/local-resilience-ready-20260717`):

| Comando | Resultado |
|---|---|
| `ruff check` (módulos resiliência) | pass |
| `mypy --follow-imports=skip` (7 arquivos) | pass |
| `python3 -m scripts.ops.validate_systemd` | pass |
| `make resilient-smoke` | **181 passed**, 24 skipped (~14s) |
| `tests/test_local_resilience.py` + chaos 429 | **35 passed** (~10s) |
| `make resilient-local-cycle` (2×) | exit 0, status `healthy` (idempotente) |
| `python3 -m scripts.ops.health` (2×) | exit 0 |
| `python3 -m scripts.ops.validate_systemd` | pass |

Fixtures controladas; `--live` é opt-in e não faz parte do gate de READY.

**Nota honesta sobre filtros amplos `-k`:** ao rodar
`pytest -k "checkpoint or resume or watermark or dlq"` e
`pytest -k "chaos or resilience or idempot"` no repositório inteiro,
podem aparecer falhas em `tests/test_opportunity_integration.py` (mock de DB
sem tabelas `opportunity_*`). Isso é **pré-existente e fora do caminho
ADR-021**. O gate canônico é `make resilience-gate` / `make resilient-smoke`.
Filtros com `and not opportunity` passam.

## Riscos residuais

- Código: adapters não prioritários continuam legados e não contam cobertura.
- Fonte externa: mudanças de schema, auth, indisponibilidade e rate limit reais.
- Infraestrutura: volume, permissões, backup/restore e retenção só após contratar.
- Cobertura: esta entrega não mede nem declara 95%.
- Operação: alertas externos, reboot e soak de 24 h pertencem à E3.S3/VPS.

## Checklist para iniciar o provisionamento

1. Escolher provedor/região e sizing sem alterar o contrato do pipeline.
2. Criar usuário não-root, volume persistente e firewall mínimo.
3. Instalar Python 3.12, PostgreSQL 16 e dependências travadas.
4. Configurar `EnvironmentFile` fora do git, com DSN mascarado em logs.
5. Fazer backup do banco origem e testar restore antes de migration.
6. Aplicar migrations, incluindo 054, em banco de staging do host.
7. Copiar/parametrizar units; executar o validador estático antes de habilitar.
8. Rodar `make resilience-gate` e um ciclo live manual por fonte.
9. Confirmar raw, checkpoint, evidence, watermark, DLQ e health no volume.
10. Habilitar timers escalonados; provar reboot, `Persistent=true` e lock.
11. Observar por pelo menos 24 h e registrar last_attempt/last_success/SLA.
12. Somente então avaliar o gate `VPS_OPERATIONAL` da E3.S3.
