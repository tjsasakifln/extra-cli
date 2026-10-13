# AGENTS.md — adaptador fino (Codex / agentes compatíveis)

**Guia canônico:** [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)  
**DoD:** [`DOD.md`](DOD.md)

Este arquivo **não** define requisitos de produto. Em conflito, prevalece:

1. `DOD.md`  
2. ADR vigente  
3. Código testado  
4. Evidência reproduzível  

## Comandos (mesmos do guia canônico)

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
python3 -m pytest tests/ -q --tb=no -x
python3 -m scripts.golden_path --dsn "$LOCAL_DATALAKE_DSN"
make extra-weekly   # ou: python3 -m scripts.ops.weekly_cycle --strict
python3 -m scripts.workspace today
python3 squads/extra-dod-roi/scripts/cli.py force-next
```

Onboarding: [`README.md`](README.md) · Hub: [`docs/INDEX.md`](docs/INDEX.md)

## Escopo / arquitetura / operação

Ver seções 2–3 de `docs/DEVELOPMENT.md`. Não inventar selos (`LOCAL_READY`, 95%, VPS) sem evidência.  
Host de record (Netcup / `ec-prod`) ≠ `VPS_OPERATIONAL`.

## DOD Convergence (obrigatório)

**Norma:** `DOD.md` prevalece sobre código, stories e handoffs.

Plano comercial CONFENGE (não é spec de produto aqui): PNCP live = ingestão
assíncrona + telemetria; operação comercial lê o Data Lake persistido.
Lei: `DOD.md` § P0 plano comercial / #468 · ADR-039 Accepted/Effective ·
`docs/contracts/confenge-commercial-plane/v1/operating-authority.json` ·
runbook `docs/ops/confenge-commercial-plane-authority.md`.
Preflight: `python3 -m scripts.ops.check_confenge_commercial_plane`.
Linter de plano: `python3 -m scripts.ops.check_confenge_campaign_plan --file <arquivo>`.
Não tratar “source run canônico”, PR #528 ou `PENDING_ONSUCCESS` como instrução vigente.

**Harness:** `python3 tools/dod_controller.py` · docs: `docs/ops/dod-convergence.md` · estado: `.dod/`

```bash
python3 tools/dod_controller.py scan
python3 tools/dod_controller.py status
python3 tools/dod_controller.py next
python3 tools/dod_controller.py start ITEM_ID
python3 tools/dod_controller.py verify ITEM_ID
python3 tools/dod_controller.py accept ITEM_ID   # só com gates; ACCEPTED no main
python3 tools/dod_controller.py audit
python3 tools/dod_controller.py report
```

**Regras invioláveis:**

- Nenhum merge sem CI verde e sem o teste do item correspondente passando.
- Nenhuma mudança de arquitetura fora do raio de impacto sem aviso explícito.
- Atualizar `DOD.md` / ADRs / handoffs faz parte do Done de cada item.
- Se dois subagentes colidirem no mesmo arquivo, parar a onda.
- Primeira onda pequena e validada antes de escalar.
- Não reduzir thresholds; não `skip`/`xfail`/mocks irreais para ocultar defeitos.
- Job `skipped` ≠ aprovado; ausência de execução ≠ sucesso.
- Somente estado `ACCEPTED` (evidência + main + CI) marca `[x]` no `DOD.md`.
- Um item por vez (máx. 2 pré-requisitos). Spec Kit: integração `grok`, workflow `dod-convergence`.
- Constituição: `.specify/memory/constitution.md`.

## Fronteira de aquisição PNCP (invariante global, leitura obrigatória)

A VPS/Data Lake é a fronteira de aquisição da CONFENGE. PNCP live é upstream
assíncrono: toda família de dados segue `fonte oficial → coletor resiliente
na VPS → raw/CAS → Data Lake canônico → consumidor`; o consumidor lê apenas
o estado persistido.

Proibido: qualquer consumidor (campanha, relatório, view, Warmbly, web-cfg,
meetcfg, ou **esta sessão**) depender de PNCP live. Proibido criar um
segundo caminho de aquisição fora da VPS/Data Lake. Proibido manter o
polling manual (`--from-pncp` ou equivalente) como operação permanente: um
coletor novo, após provado com um payload real, migra para job na VPS com
timer, retry/backoff, checkpoint/resume e idempotência.

Chamada PNCP live nesta sessão só é legítima para discovery técnico, captura
do primeiro payload real de uma família nova, teste/canário de nova
integração, ou diagnóstico excepcional. PNCP indisponível não bloqueia
trabalho downstream sobre dados já persistidos; ausência de dado novo é
`UNKNOWN`/`STALE`, nunca inventada.

Lei: ADR-039 §"Extensão — fronteira de aquisição assíncrona (global)".
Preflight: `python3 -m scripts.ops.check_confenge_campaign_plan --file <arquivo>`.

## PR governance (fail-closed)

Before opening or marking ready for review:

```bash
python3 -m scripts.ops.check_generated_artifacts_policy --base origin/main
python3 -m scripts.ops.check_pr_reviewability --base origin/main   # add --draft if draft
```

Policies: `docs/generated-artifacts-policy.md`, `docs/pr-reviewability-policy.md`.
Do not commit PDF/XLSX/bulk dumps/logs; keep heavy evidence as Actions artifacts.
Ready PRs: ≤60 files, ≤10k textual lines, single capability. Exact HEAD SHA must match CI.

