# BASELINE — EXTRA-COMMAND-CENTER-CONSULTING-WORKBENCH-01

**Campaign:** `EXTRA-COMMAND-CENTER-CONSULTING-WORKBENCH-01`  
**Vehicle:** PR [#186](https://github.com/tjsasakifln/extra-cli/pull/186) · branch `feat/extra-local-command-center`  
**Recorded at:** 2026-07-31  
**Prior campaign:** `EXTRA-LOCAL-COMMAND-CENTER-01` (status `COMMAND_CENTER_READY_FOR_TIAGO_REVIEW` — **not** PASS for this campaign)

## SHAs exatos

| Ref | SHA |
|-----|-----|
| `HEAD` (branch tip) | `565e4c2a3f7d25501d9b7d847aace0b9c2ceaf84` |
| `origin/main` | `1718d6389c4e772bf3c5a45ac059871c32d83afc` |
| merge-base(HEAD, origin/main) | `1718d6389c4e772bf3c5a45ac059871c32d83afc` |
| commits on branch not in main | 7 |
| commits on main not in branch | **0** (branch already contains current main) |

Main tip message: `feat(process_documents): documentos públicos de processos (1093 entes) (#184)`.

Preserved main integrations (ancestors of merge-base):

- #181 Extra profile → actionable → decision (`89366040`)
- #183 CONFENGE official RFB CNPJ mirror → commercial shortlist (`9ac6f377`)
- #185 CONFENGE public-agency B2G vertical (`2eb2aac3`)
- #184 procurement process documents (`1718d638`)
- Canonical router: `scripts.ops.confenge_commercial_target_router` (used by supplier/agency capabilities)

## Arquitetura atual (PR #186 foundation)

```
bin/command-center                  # launcher: loopback bind, build SPA if needed
scripts/command_center/
  app.py                            # FastAPI: health, CSRF, jobs, reviews, decisions, artifacts
  job_runner.py                     # allowlisted subprocess, SSE logs, cancel sticky
  store.py                          # SQLite: jobs, logs, audit, reviews, decisions, prefs
  artifact_reader.py                # safe read under roots; PDF/XLSX = binary download only
  capabilities/definitions.py       # 29 allowlisted capabilities
  overview.py                       # home payload
  security.py / redaction.py        # path containment, argv assert, secret redaction
apps/command-center/                # React+Vite SPA (dist committed for launch)
docs/command-center/                # architecture, security, capability registry
tests/command_center/               # API security + capability argv contracts
```

**Security posture (keep):** allowlist argv, `shell=False`, loopback bind (IPv4+IPv6), CSRF, redaction, path containment, no DOD auto-accept, no auto-outreach, server-owned confirmation phrases.

**Persistence:** local SQLite under `data/command_center/` only — no main operational schema changes in foundation.

## Inventário de capabilities (29)

| ID | Category | Risk | Confirm | Path params? | Notes |
|----|----------|------|---------|--------------|-------|
| `cc.fixture.echo` | ops | read | no | no | Safe CI fixture |
| `cc.fixture.slow` | ops | read | no | no | Cancel test |
| `extra.profile.show` | extra | read | no | no | |
| `extra.profile.validate` | extra | read | no | no | |
| `extra.weekly.run` | extra | write_local | yes | advanced optional | needs DSN |
| `extra.actionable.run` | extra | write_local | yes | **required** weekly_input, out | |
| `extra.decision.review` | extra | read | no | optional path | |
| `extra.decision.finalize` | extra | human_decision | yes | **required** paths | |
| `extra.recurring.run` | extra | write_local | yes | **required** paths | |
| `confenge.suppliers.registry.health` | confenge_suppliers | read | no | no | |
| `confenge.suppliers.registry.lookup` | confenge_suppliers | read | no | no | |
| `confenge.suppliers.registry.coverage` | confenge_suppliers | read | no | no | |
| `confenge.suppliers.cycle.run` | confenge_suppliers | write_local | yes | advanced out | **router** target=suppliers |
| `confenge.public_agencies.cycle.run` | confenge_agencies | write_local | yes | advanced out | **router** target=public-agencies |
| `confenge.public_agencies.review.open` | confenge_agencies | read | no | advanced | |
| `confenge.all.cycle.run` | confenge_suppliers | write_local | yes | advanced | **router** target=all |
| `process_documents.discover` | process_documents | write_local | yes | no | |
| `process_documents.collect` | process_documents | write_local | yes | no | live |
| `process_documents.coverage` | process_documents | read | no | no | |
| `process_documents.corpus` | process_documents | write_local | yes | no | |
| `process_documents.show` | process_documents | read | no | query | |
| `process_documents.incremental` | process_documents | write_local | yes | no | |
| `ops.health` … `ops.recent_runs` | ops | read | no | no | 5 caps |
| `dod.status` / `dod.item.show` | dod | read | no | item_id | read-only; ACCEPT blocked in UI |

## Matriz capability → comando → entradas → saídas reais (consultivos)

| Fluxo consultivo | Capability principal | Comando canônico | Entradas típicas | Saídas reais do CLI | O que a UI mostra hoje |
|------------------|---------------------|------------------|------------------|---------------------|------------------------|
| Extra oportunidades | `extra.weekly` + `extra.actionable` + `extra.decision.finalize` | `python -m scripts.ops.weekly_cycle` / `extra_actionable` / `extra_decision_loop` | DSN, weekly pack paths, out dirs | JSON/JSONL/MD packs under `output/weekly`, decision packages | Form params + logs; paths often **required**; no PDF/XLSX generation in CC |
| CONFENGE fornecedores | `confenge.suppliers.cycle.run` | `confenge_commercial_target_router --target suppliers` | run_mode, population_mode, out optional | commercial run dir: queues, dossiers MD/JSON, xlsx when cycle produces them | Download binary; no in-browser XLSX/PDF viewer; coverage not preflighted as first-class |
| CONFENGE órgãos | `confenge.public_agencies.cycle.run` | router `--target public-agencies` | uf, max leads, mode, DSN | public-agency packages + review packs | Same as suppliers; legal language present in copy but not workbench review of classifications |
| Process documents | `process_documents.*` | `scripts.process_documents` / `scripts.workspace process-documents` | query, limit | `output/process_documents` coverage reports, files | Show/query returns JSON-ish logs; no coverage PDF/index XLSX workbench package |
| Revisão humana | store `review_items` + `/api/decisions` | N/A (local) | title/evidence text | decision rows in SQLite | **Text cards** ACCEPT/REJECT/DEFER; REJECT/DEFER do not force rationale/return date; ACCEPT not bound to artifact hashes; rationale often = title |

Artifact discovery: primarily `parse_result` / paths scraped into job record from CLI stdout parsing (`default_parse`). **No canonical `run-manifest.json` written by CC.**

## Evidências de execução (Fase 0)

### Launch

- Entry: `./bin/command-center` → listens dual loopback port **8765**
- SPA: `apps/command-center/dist/index.html` present; `GET /` → 200
- API: `/api/health`, `/api/overview`, `/api/reviews` → 200 during launch
- Snapshot: `/tmp/grok-goal-62c58f68453a/implementer/baseline-api.json` (scratch; not committed)

### Tasks measured (fixture / structural; no forged live evidence)

| Task | Clicks (approx) | Technical fields | Terminal? | Open external file? | Undetected artifacts | No in-browser view | Steps to usable deliverable |
|------|-----------------|------------------|-----------|---------------------|----------------------|--------------------|-----------------------------|
| Extra (weekly/actionable) | 6–12 | path `weekly_input`, `out`, DSN knowledge | often for DSN | yes for JSON/MD | high without path knowledge | PDF/XLSX absent | **blocked** without terminal/paths |
| CONFENGE suppliers cycle | 5–10 | run_mode, population_mode, optional out | if DSN/snapshot missing | yes | medium | PDF/XLSX not viewed | partial at best (download dump) |
| CONFENGE public agencies | 5–10 | uf, max leads, DSN | often | yes | medium | same | partial |
| process_documents show | 3–6 | free-text query | no for show | yes for PDFs | coverage opaque | PDF binary only | **no** coverage package |
| Human review | 2–4 | none for ACCEPT confirm | no | no | N/A | evidence is plain text only | decision recorded but **not** evidence-bound |

Fixture job `cc.fixture.echo` via TestClient: starts, completes (logs-only success). Review enqueue + list pending works. **Neither produces a consulting deliverable.**

### UI model mental (promessa vs real)

| Promessa / copy | Realidade baseline |
|-----------------|-------------------|
| “sem terminal” | True only for fixtures and read-only; path-required flows force filesystem knowledge |
| “resultados em tabela” | Tables for JSON list samples; sample capped (`artifact_sample_lines=200`); silent sample for large sets |
| “revisão humana” | Text cards; rationale defaults to **title**; no hash binding |
| “PDF/XLSX” | Treated as `kind: binary` → download message only |
| “capabilities” still primary IA | Home has “Ações principais” + areas, but deep paths still capability forms (`/actions/:id`) |
| Product model clients/projects/runs/bundles | **Absent** |
| Run manifest | **Absent** |
| Guided multi-step workflows A–E | **Absent** (single capability forms) |
| Presets / path-free defaults for common flows | Partial defaults only; required paths remain |

## Deficiências observadas (núcleo da campanha)

1. Outcome-first incomplete: capability forms remain the execution model.
2. Path-required consulting capabilities (`extra.actionable`, `extra.decision.finalize`, …).
3. Artifact discovery via stdout/parse, not manifest-primary.
4. No professional deliverable generation layer (PDF/XLSX with provenance) owned by CC.
5. PDF/XLSX not previewable in browser.
6. CSV/JSONL sample truncation without progressive pagination UX.
7. Review not object-bound; REJECT/DEFER weak validation; ACCEPT not hash-versioned.
8. No ExportBundle / checksum package.
9. No run comparison / “what changed”.
10. Tests prove presence/security/argv — **not** end-to-end consulting task completion to PDF/XLSX.
11. Prior terminal status `COMMAND_CENTER_READY_FOR_TIAGO_REVIEW` is **not** acceptance for WORKBENCH-01.

## Riscos

| Risk | Impact | Mitigation in campaign |
|------|--------|------------------------|
| Live DB/network unavailable in sandbox | Cannot prove live cycles | Fixture-backed flows + real renderers + honest coverage |
| Scope of 36 ACs vs foundation PR | BLOCKED if incomplete | Prefer honest BLOCKED over fake PASS |
| Parallel product/router temptation | Architecture freeze | Stay on PR #186; only `confenge_commercial_target_router` |
| Binary assets policy | PR reviewability fail | SVG brand only; no large PDF committed |
| Security regression for “UX ease” | FAIL gate | Keep allowlist/CSRF/path tests green |

## Lacunas UI ↔ funcionamento

- Home headline works; lacks “continuar”, deliverables, what-changed, data health depth, blocked remediation as first-class cards.
- Artifact center lists files; no primary_deliverable role, versioning, or bundle.
- Job page emphasizes logs over human stage timeline.
- Confirmation exists for sensitive caps but preflight does not show coverage/data-as-of/expected deliverables matrix.
- Mobile CSS partial; tables not proven at 390×844 for operational work.

## Critério de saída da Fase 0

- [x] SHAs recorded  
- [x] Architecture + capability inventory  
- [x] Capability → CLI → I/O matrix  
- [x] Launch + fixture/review evidence  
- [x] Task metrics + gaps + risks  
- [ ] Screenshots desktop/mobile (capture during implementation visual QA; policy: avoid large binaries in git)

**Fase 0 concluída para implementação.** No material product code preceded this document beyond diagnostic runs.
