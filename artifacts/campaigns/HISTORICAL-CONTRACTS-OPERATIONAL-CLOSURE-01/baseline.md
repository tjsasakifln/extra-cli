# Baseline — HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

**Inspected at:** 2026-07-22 (local workspace)  
**Repository:** `tjsasakifln/extra-cli`  
**Machine-readable twin:** `baseline.json`

## 1. Git / CI

| Item | Value | Classificação |
|------|-------|----------------|
| Branch local | `docs/dual-stamp-same-truth` | trabalho |
| HEAD local | `a38981bfa616b8f47363da6ff91b12a28bec218c` | **integrado à main** |
| `origin/main` | mesmo SHA | **igual** |
| vs `origin/main` | `0 0` | sem delta de commits |
| Último merge | PR #120 dual same-truth stamps | docs/ops |
| SHA semântico dual aceito | `abcd067…` (PR #118) | medição |
| CI no HEAD | run `29926125170` **success** (push main) | **CI verde** |

Últimos commits relevantes: stamps/honest accept da campanha dual; **não** preenchem numerador operacional de contratos.

## 2. Medição dual (reproof em artefato local)

Fonte: `output/coverage/dual-coverage-historical_contracts.json` (`as_of` 2026-07-22T13:29:06Z, stamped `abcd067`).

| Métrica | Valor | Classificação |
|---------|-------|----------------|
| Universo | 1093 | implementado + integrado |
| Denominador aplicável | 946 | medido |
| Numerador coberto | **0** | **operacionalmente vazio** |
| coverage_pct | 0.0% | gate FAIL |
| applicability_unknown | **147** | **bloqueia readiness 100%** |
| never_checked | 946 | sem evidence válida |
| success_with_data / success_zero | 0 / 0 | ausente |
| data_presence (descritivo) | 1 entidade | **nunca é cobertura** |
| measurement_success | true | motor honesto |
| coverage_gate_pass | false | falha correta |
| reconciliation_ok | true | partições coerentes |

**Conclusão de seleção:** critérios da campanha **não** estão satisfeitos → **permanece** historical_contracts (não troca para open_tenders).

## 3. Matriz de estado (presença ≠ prova operacional)

Legenda: I=implementado · M=main · T=teste · PG=Postgres real · SRC=fonte real · OPS=aceito · DOC=só doc · OBS=obsoleto · BLK=bloqueado · ABS=ausente

| Capacidade | I | M | T | PG | SRC | OPS | Notas |
|------------|---|---|---|----|-----|-----|-------|
| Motor dual + ADR-030 | ✓ | ✓ | ✓ | parcial | — | ✓ medição | **não** preenche contratos |
| Política de fontes v2 | ✓ | ✓ | parcial | — | — | parcial | 147 unknown |
| Crawler contratos + checkpoint | ✓ | ✓ | ✓ | parcial | parcial | ✗ | janelas parciais; 429 |
| Piloto 90d runner | ✓ | ✓ | ✓ | parcial | parcial | ✗ | artifact **seal**, NO-GO 3y |
| Backfill 3 anos comprovado | parcial | ✓ | parcial | ✗ | ✗ | ✗ | checkpoint 3y **vazio** |
| Incremental ≤7d canônico | parcial | parcial | parcial | ✗ | ✗ | ✗ | weekly só reusa lake |
| Adapter coverage_evidence/entidade | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | **ausente** (gap central) |
| Weekly fail-closed contratos | ✗ | ✗ | ✗ | — | — | ✗ | declara reuso |
| Gate 95% historical_contracts | ✓ (gate) | ✓ | ✓ | medição | ✗ | ✗ | numerador 0 |

## 4. Aplicabilidade unknown (147)

- **blocker:** `applicability_unknown`
- **justification:** `required_source_unknown`
- **padrão:** consórcios, companhias de urbanização, agências intermunicipais sem `esfera` resolvida para `required_combinations`
- **não** foram marcadas `not_applicable` (correto sob fail-closed)
- **ação exigida:** atributos canônicos + regras auditáveis + hash de política; proibido hardcode de esfera pontual sem justificativa

## 5. Piloto / backfill (evidência em disco)

### 5.1 `pilot-90d-next30d.json`

- `status=partial`, `go_no_go_3y=NO-GO`
- `sealed=true` com nota: *não substitui crawl live 90d*
- 3 janelas planejadas; artifact com 1 janela path_proof
- **Classificação:** atestação / fixture de selagem — **não** GO operacional

### 5.2 `pilot-7d-smoke.json`

- `status=success` no span 7d, ainda **NO-GO** para 3y (span &lt; 90)

### 5.3 Checkpoints

| Arquivo | Estado |
|---------|--------|
| `contracts_backfill_3y.json` | `completed_windows=[]`, fetched=0 → **vazio** |
| `contracts_full.json` | 11 janelas ok, 3 falhas, ~813k fetched, last_error **429** → **parcial**, não 3y |

## 6. Weekly cycle

- Entry canônico: `make extra-weekly` → `python3 -m scripts.ops.weekly_cycle --strict`
- Contratos: `_contracts_reuse_run` / *“contracts not re-crawled; lake rows reused with explicit freshness”*
- **Divergência:** produto consultivo integral não pode pretender freshness contratual ≤7d sem incremental comprovado

## 7. Specs / ADRs

| Artefato | Papel | Estado |
|----------|-------|--------|
| `specs/001-dual-capability-coverage-truth/` | medição dual | presente e convergida |
| `specs/002-historical-contracts-operational-coverage/` | operação 3y + evidence | **ausente** (criar) |
| ADR-030 | spine `coverage_evidence` | Accepted; backfill **fora** do escopo de medição |
| `config/source_applicability.yaml` v2.0.0 | combinações obrigatórias | active; `historical_contracts` → `pncp+contracts` |

**Decisão de Spec Kit:** criar **002** (operação) sem reabrir metrologia da 001, salvo contradição demonstrada.

## 8. PRs abertas

Inventário de hipóteses (muitas draft/CONFLICTING, bases defasadas). **Não** são autoridade nem merge automático.

## 9. Banco local na inspeção

- DSN canônico: `postgresql://test:test@127.0.0.1:5433/extra_test`
- Porta 5433 **não** escutava no momento da inspeção (compose `test-db` a subir)
- Migrations no repo até `058_dual_capability_coverage_views.sql`
- Presença de linhas em DB legado **não** prova coverage dual por entidade

## 10. Divergências registradas

1. **DIV-01** Medição honesta + CI verde ≠ capacidade operacional  
2. **DIV-02** Seal de piloto ≠ live 90d GO  
3. **DIV-03** Weekly reusa lake vs freshness incremental exigida  
4. **DIV-04** 147 unknown por atributos de esfera/natureza  
5. **DIV-05** Crawl nacional ≠ adapter `coverage_evidence` por entidade  
6. **DIV-06** Papéis `pncp`+`contracts` exigem contrato semântico (sem double-count)  
7. **DIV-07** PRs antigas ≠ trabalho aproveitável sem rebase/prova  

## 11. Próximos passos (ordem)

1. Branch de campanha a partir de `origin/main`  
2. Spec Kit 002 completa (spec/plan/tasks/checklists/analyze)  
3. Resolver aplicabilidade 100%  
4. Piloto live 90d → GO  
5. Backfill ≥1095 dias + incremental  
6. Adapter de evidence + dual ≥95%  
7. Weekly fail-closed + produto  
8. Testes/CI/revisão/DOD só com prova  

## 12. Non-claims neste baseline

Não se declara: LOCAL_READY, PRE_VPS, VPS_OPERATIONAL, dual total PASS, open_tenders 95%, 3y backfill completo, piloto 90d success nacional, valor pago, PROJECT_DONE.
