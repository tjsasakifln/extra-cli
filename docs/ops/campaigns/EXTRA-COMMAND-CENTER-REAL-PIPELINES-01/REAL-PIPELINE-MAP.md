# REAL pipeline map — Command Center guided flows

Documentação dos entrypoints **canônicos existentes** no `extra-cli`.  
Nenhum comando foi inventado a partir do título do fluxo.

Política:

- **MODO REAL** (`data_mode=REAL` / `use_fixture=false`): adapters tipados → argv lista → subprocess sem shell.
- **MODO DEMONSTRAÇÃO** (`data_mode=FIXTURE` / `use_fixture=true`): fixture explícita; nunca prova LIVE.
- **Sem fallback silencioso** REAL → fixture.

---

## 1. Oportunidades para a Extra Construtora

| Campo | Valor |
|-------|--------|
| **workflow_id** | `workflow.extra.opportunities` |
| **capability_id (adapter)** | `extra.decision.finalize` (quando há weekly pack) / `extra.weekly.run` (quando não há) |
| **Módulo canônico** | `scripts.ops.extra_decision_loop` **ou** `scripts.ops.weekly_cycle` |
| **Comando** | `python -m scripts.ops.extra_decision_loop run --weekly-dir <dir> --out <out> [--max-shortlist N]` |
| | ou `python -m scripts.ops.weekly_cycle [--strict] [--skip-collect] [--limit N] --output-dir <dir>` |
| **Parâmetros UI** | `period_days`, `max_shortlist`, `data_mode`, `output_profile`, opcional `weekly_input` (avançado via params) |
| **Env** | `LOCAL_DATALAKE_DSN` (obrigatório no REAL) |
| **Fontes** | Datalake local / weekly pack; perfil Extra |
| **Artefatos esperados** | pacote decision/weekly sob out; normalizado `opportunities.json`, PDF/XLSX, `run-manifest.json` |
| **Status terminais** | `SUCCEEDED`, `FAILED`, `BLOCKED_CONFIG`, `BLOCKED_EXTERNAL`, `BLOCKED_DATA` |
| **Bloqueios** | DSN ausente; driver PG; módulo ausente; dir não gravável; exit 2 do pipeline |
| **R/W** | Escrita local em output allowlisted; sem mutação silenciosa do datalake além do que o pipeline canônico já faz |
| **Revisão humana** | Fila ACCEPT/REJECT/DEFER por item; hash invalida aceite |
| **Proibido** | auto-outreach; autoaceite DOD; shell arbitrário; fallback fixture |

---

## 2. Prospecção CONFENGE — fornecedores

| Campo | Valor |
|-------|--------|
| **workflow_id** | `workflow.confenge.suppliers` |
| **capability_id** | `confenge.suppliers.cycle.run` |
| **Módulo canônico** | `scripts.ops.confenge_commercial_target_router` |
| **Comando** | `python -m scripts.ops.confenge_commercial_target_router --target suppliers --run-mode DRY_RUN --population-mode BOUNDED_SAMPLE --out <dir> [--uf UF] [--max-contracts N]` |
| **Parâmetros UI** | `uf`, `max_companies`, `population_mode`, `data_mode` |
| **Env** | `LOCAL_DATALAKE_DSN`; `CONFENGE_REQUIRE_OFFICIAL_REGISTRY` (default fail-closed) |
| **Fontes** | contratos públicos + cadastro oficial (via registry wrapper quando exigido) |
| **Artefatos** | saída comercial do router; normalizado `suppliers.json`; PDF/XLSX; manifest |
| **Status** | `SUCCEEDED` / `FAILED` / `BLOCKED_*` (exit 2 → BLOCKED_DATA) |
| **Bloqueios** | DSN; registry fail-closed; permissões de saída |
| **R/W** | pipeline comercial local; default `DRY_RUN` no workbench |
| **Revisão humana** | por empresa/CNPJ |
| **Proibido** | e-mail/WhatsApp; auto-outreach; fixture silenciosa |

---

## 3. Prospecção CONFENGE — órgãos públicos

| Campo | Valor |
|-------|--------|
| **workflow_id** | `workflow.confenge.public_agencies` |
| **capability_id** | `confenge.public_agencies.cycle.run` |
| **Módulo canônico** | `scripts.ops.confenge_commercial_target_router` |
| **Comando** | `python -m scripts.ops.confenge_commercial_target_router --target public-agencies --run-mode DRY_RUN --public-agency-mode REACTIVE_OPPORTUNITY --public-agency-out <dir> [--uf UF] [--max-public-agency-leads N]` |
| **Parâmetros UI** | `uf`, `max_leads`, `mode`, `data_mode` |
| **Env** | `LOCAL_DATALAKE_DSN` |
| **Fontes** | pipeline `scripts.public_agency` via router |
| **Artefatos** | saída public-agencies; `public_agencies.json`; PDF/XLSX; manifest |
| **Status** | `SUCCEEDED` / `FAILED` / `BLOCKED_*` |
| **Bloqueios** | DSN; perfil/módulos; permissões |
| **R/W** | geração local de leads/dossiês preliminares |
| **Revisão humana** | classificação jurídica preliminar revisável |
| **Proibido** | afirmar contratação garantida; outreach; fixture silenciosa |

---

## 4. Documentos públicos de processos

| Campo | Valor |
|-------|--------|
| **workflow_id** | `workflow.process_documents` |
| **capability_id** | `process_documents.show` |
| **Módulo canônico** | `scripts.process_documents` |
| **Comando** | `python -m scripts.process_documents show <query>` (default REAL workbench) |
| | também allowlisted no adapter: `coverage`, `discover`, `build-corpus` |
| **Parâmetros UI** | `query`, `data_mode` |
| **Env** | DSN opcional para `show` (acervo local); collect/harvest exigem Avançado |
| **Fontes** | acervo process_documents / lake |
| **Artefatos** | `documents-index.json`; outputs em `output/process_documents` se existirem; PDF/XLSX quando rows; manifest |
| **Status** | `SUCCEEDED` / `FAILED` / `BLOCKED_*` |
| **Bloqueios** | query vazia; metacaracteres; módulo ausente |
| **R/W** | leitura/show por padrão |
| **Revisão humana** | pacote documental |
| **Proibido** | inventar cobertura; query com `;|&\`` |

---

## Preflight tipado

```json
{
  "status": "READY | BLOCKED_CONFIG | BLOCKED_EXTERNAL | BLOCKED_DATA | BLOCKED_PERMISSION",
  "checks": [],
  "limitations": [],
  "safe_to_run": true
}
```

API: `GET /api/workflows/{workflow_id}/preflight?data_mode=REAL|FIXTURE`

---

## Código

- Adapters: `scripts/command_center/adapters/`
- Runner: `scripts/command_center/workflows/runner.py`
- Registry capabilities: `scripts/command_center/capabilities/definitions.py`
