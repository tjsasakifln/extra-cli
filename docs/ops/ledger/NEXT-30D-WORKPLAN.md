# NEXT-30D Workplan — Janela PERT (30 ≤ ES &lt; 60 + CP ≥ 30)

**Campanha:** `NEXT-30D-MULTIAGENT`  
**SHA base:** `77ff8a8`  
**Fórmula:** `dur = ceil((o+4m+p)/6)`; `ES = max(EF deps)` (igual HTML `extra-consultoria-plano-executivo.html`)  
**Critério de sucesso:** (1) tarefas executáveis da janela; (2) CP consecutivos com PERT ≥ 30 dias úteis.

## Tabela da janela

| ID | Tarefa | Deps | o | m | p | PERT | ES | EF | CP/folga | Owner | Subsistema | Evidência necessária | Paralelo? | Risco conflito |
|----|--------|------|---|---|---|------|----|----|----------|-------|------------|----------------------|-----------|----------------|
| L1.8 | Manifesto fundação | L1.6,L1.7 | 1 | 2 | 4 | 3 | 31 | 34 | CP | A1 | ledger/GATE-1 | manifesto HEAD | sim (docs) | baixo |
| C2.3 | PNCP resume/backfill | L1.8,C2.2 | 6 | 8 | 13 | 9 | 34 | 43 | CP | A5/A4 | pncp_backfill | run e2e ou BLOCKED | parcial | API timeout |
| C2.4 | PCP + TCE-SC | L1.8,C2.2 | 5 | 7 | 11 | 8 | 34 | 42 | +1 | residual | pcp/tce | só se gap | sim | baixo |
| C2.5 | DOM/CIGA | L1.8,C2.2 | 5 | 7 | 11 | 8 | 34 | 42 | +1 | residual | ciga_ckan | já evidence | sim | baixo |
| C2.6 | ComprasGov | L1.8,C2.2 | 4 | 6 | 10 | 7 | 34 | 41 | +17 | residual | compras_gov | já evidence | sim | baixo |
| K3.1 | Schema contratos | L1.8 | 3 | 4 | 7 | 5 | 34 | 39 | +14 | A2 | migrations/schema | audit | sim | migrations |
| Q5.1 | Testes críticos | L1.8 | 4 | 5 | 8 | 6 | 34 | 40 | +61 | A7 | tests/ | 82 PASS claim fix | sim | baixo |
| Q5.4 | Lint/tipos/segurança | Q5.1 | 4 | 5 | 8 | 6 | 40 | 46 | +61 | A7 | ruff/mypy/bandit/CI | gates exit 0 | sim | CI |
| K3.3 | Fontes alt. contratos | K3.1,C2.4,C2.5 | 8 | 12 | 18 | 12 | 42 | 54 | +11 | A5 | tce/ciga contracts | paths integrados | sim | médio |
| **C2.7** | DOE-SC, SC Compras, residuais | C2.3–C2.5 | 10 | 15 | 20 | **15** | 43 | 58 | **CP** | A4 | sc_compras, doe_sc | ingest real + coverage | parcial | **alto (CP)** |
| C2.8 | Aliases/dedup | C2.3,C2.4 | 5 | 7 | 11 | 7 | 43 | 50 | +8 | A6 | lib/dedup, pipeline | dedup rows + CLI | sim | opportunity_intel |
| C2.9 | Status/snapshots | C2.3 | 5 | 8 | 12 | 8 | 43 | 51 | +7 | A4 | opportunity_intel | integrity metric | sim | médio |
| **K3.2** | Backfill PNCP 3y | K3.1,C2.3 | 8 | 12 | 18 | **12** | 43 | 55 | +10 | A5 | contracts_crawler | pilot 90d → go/no-go | sim | API/rate |
| K3.4 | Vigência/incremental | K3.2,K3.3 | 6 | 9 | 14 | 9 | 55 | 64 | +10 | A5 | contracts | pós-pilot | seq | médio |
| **C2.10** | Auditar cobertura editais | C2.6–C2.9 | 3 | 5 | 8 | **5** | 58 | 63 | **CP** | A4 | coverage_truth | report editais | seq CP | médio |
| C2.11 | Remediação gaps editais | C2.10 | 6 | 10 | 15 | **10** | 63 | 73 | **CP** | A4 | multi-source | gaps remediated ou escalate | seq CP | alto |

## CP acumulado (trabalho novo prioritário) — FINAL

| Ordem | ID | PERT | Cum | Status final |
|-------|-----|------|-----|--------------|
| 1 | C2.7 | 15 | 15 | **DONE** public sc_compras; DOE **BLOCKED_EXTERNAL** |
| 2 | C2.10 | 5 | 20 | **DONE** measured 4.76% |
| 3 | C2.11 | 10 | **30** | **DONE** formal escalate (not fake 95%) |

**CP PERT ≥ 30 achieved** without declaring DoD 95%.

Paralelo que não entra no CP mas fecha janela: K3.2 (12), C2.8 (7), C2.9 (8), Q5.4 (6), golden fail-closed, schema.

## Ondas

1. **Foundation:** baseline, schema, golden fail-closed, CI  
2. **Data:** sc_compras, contracts 90d, dedup, snapshot  
3. **Intelligence:** reports A–E, PDF×Excel  
4. **Accept:** gates A–D, audit, DoD, HTML, PR  

## Regras de paralelismo

- Worktrees/branches por frente; merge via A1  
- `monitor.py` / `golden_path.py` / `DOD.md` / HTML: ownership explícito  
- V6.2 BLOCKED_EXTERNAL — não consome capacidade  
