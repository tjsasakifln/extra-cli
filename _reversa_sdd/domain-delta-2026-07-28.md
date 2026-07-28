# Delta de Domínio — 2026-07-28

> Complemento a `domain.md` (base 2026-07-13/17).  
> HEAD `ffbb9608` | Detective re-extração auditoria  
> 🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA

---

## Glossário novo / atualizado

| Termo | Definição | Fonte | Conf. |
|-------|-----------|-------|-------|
| **Dual Capability Coverage** | Cobertura canônica separada em `open_tenders` e `historical_contracts`; não usar `entity_coverage.is_covered` como autoridade | `dual_capability_coverage.py`, mig 058 | 🟢 |
| **CONFENGE** | Campanha commercial-ready com freeze de inputs, packages de evidência, dual-head SHA e status terminal SSoT | `ops/confenge_*` | 🟢 |
| **CMI** | Contract Market Intelligence — competitors, values, concentration com proofs por item DoD | `ops/cmi_item_proofs.py`, reports §12 | 🟢 |
| **Commercial Lead** | Fornecedor ranqueado para abordagem comercial com score explicável e estado de funil | mig 062, `commercial_leads` | 🟢 |
| **Offer Selection v4** | Seleção multi-bucket de oferta sugerida com margem mínima e limite de flip single-signal | `scoring.py` SELECTION_RULE_VERSION | 🟢 |
| **NOT_COMPUTABLE** | Sinal/score que não pode ser calculado por falta de dado — nunca inventar | commercial_leads, supplier_registry | 🟢 |
| **Canonical Linkage** | Golden records organs/suppliers + links auditáveis; strong keys não auto-merge em conflito | mig 061, `linkage` | 🟢 |
| **National Intel Layer** | Views L1 raw_national / L2 geo_sc / L3 intel_product — **não** coverage operacional | mig 060 | 🟢 |
| **ORPT** | Vertical de relatórios operacionais + metadata unificada PDF/Excel/CSV | `reports/*` PRs #159–#160 | 🟢 |
| **Snapshot Write Guard** | Trigger opt-in que bloqueia mutação de `pncp_supplier_contracts` em snapshot restaurado | mig 064 | 🟢 |
| **Budget Audit** | Auditoria aritmética de BDI/composições sem claim legal/abusivo | `budget_audit` | 🟢 |
| **Edital Relevance Recall** | Fundação §8.4 de recall com labels humanos dual-blind + Wilson CI | `edital_relevance_recall.py` | 🟢 |
| **DoD Controller** | Harness de convergência: scan/status/next/verify/accept com ACCEPTED só com evidência+main+CI | `tools/dod_controller.py` | 🟢 |

---

## Regras de negócio novas (R41+)

### R41: Dual capability é autoridade de coverage monitoring
**Regra:** Gates de monitoring coverage usam `dual_capability_coverage` + `coverage_evidence`. `entity_coverage` é legado/diagnóstico.

🟢 — mig 058 comments + `dual_capability_coverage.py`.

### R42: success_zero exige paginação completa
**Regra:** Estado `success_zero` só é coberto se houver prova de paginação completa (zero real, não falha silenciosa).

🟢 — `coverage/states.py`.

### R43: Score comercial ≠ probabilidade de conversão
**Regra:** `score_total` / offer scores são prioridade de revisão humana; explicitamente não claim de conversão/desejo.

🟢 — `LeadScore.as_dict` language_note.

### R44: Limite de flip single-signal (0.50)
**Regra:** Taxa de mudança de oferta sob ablação de um único sinal não pode exceder 0.50 (gate).

🟢 — `MAX_SINGLE_SIGNAL_OFFER_CHANGE_RATE`.

### R45: Margem mínima entre ofertas (0.10)
**Regra:** Oferta selecionada precisa de margem ≥ 0.10 vs alternativa.

🟢 — `MIN_SELECTED_OFFER_MARGIN`.

### R46: Strong keys conflitantes recusam merge
**Regra:** CNPJ14/CNPJ8/IBGE conflitantes → classification `ambiguous`, não auto-merge.

🟢 — `linkage/resolve.py` `refuse_merge` / `conflicting_strong_ids`.

### R47: Auto-accept linkage só exact/deterministic ≥ 0.99
**Regra:** `auto_accept` requer classification exact|deterministic_composite e score ≥ 0.99.

🟢 — `AUTO_ACCEPT_MIN_SCORE = 0.99`.

### R48: National intel não é coverage operacional SC
**Regra:** Views `v_intel_*` e produtos national_intel não podem ser rotulados como coverage operacional / M2.

🟢 — comments SQL mig 060 + `lineage.py` claim class.

### R49: Multi-UF é fato de contratos, não parceria
**Regra:** Footprint multi-UF de fornecedor é fato agregado de contratos.

🟢 — COMMENT ON VIEW `v_intel_supplier_geo`.

### R50: BDI audit nunca claim legal/abusivo
**Regra:** Auditoria BDI é aritmética/estrutura; nunca legal/ilegal/abusivo sem revisão normativa humana; BDI ≠ margem.

🟢 — docstring `budget_audit/bdi.py`.

### R51: Percent points BR em componentes BDI
**Regra:** Componentes BDI em planilhas BR tratam 3 como 3% (percent points), com exceção Excel percent-format.

🟢 — `_as_fraction` role=component.

### R52: Relatórios operacionais fail-closed
**Regra:** Tabela ausente / query impossível → erro tipado, não lista vazia que simula “zero resultados”.

🟢 — `OperationalQueryError` / `OperationalReportError`.

### R53: Metadata unificada PDF/Excel
**Regra:** Relatórios comerciais compartilham `run_metadata` comparável (run_id, git SHA, sample size).

🟢 — `run_metadata.py`.

### R54: Snapshot guard opt-in
**Regra:** Com `app.confenge_snapshot_guard=on`, mutações em `pncp_supplier_contracts` exigem `app.allow_snapshot_mutation=on`.

🟢 — mig 064.

### R55: Artefatos pesados fora do git
**Regra:** PDF/XLSX/bulk dumps/logs não entram em PR ready; policy fail-closed.

🟢 — `check_generated_artifacts_policy.py` + docs policy.

### R56: PR reviewability fail-closed
**Regra:** Ready PR ≤60 files, ≤10k textual lines, single capability; HEAD SHA deve bater.

🟢 — `check_pr_reviewability.py` + AGENTS.md.

### R57: supplier_registry never invent
**Regra:** Cadastro CNAE só de fonte versionada; missing = NOT_COMPUTABLE.

🟢 — COMMENT supplier_registry + commercial_leads.

### R58: CONFENGE dual-head truth
**Regra:** `pr_head` ≠ merge checkout SHA em PRs; status terminal não mentir com dummy SHA.

🟢 — `confenge_final_status.py` + CI env vars.

### R59: DoD ACCEPTED só com evidência + main + CI
**Regra:** Controller não marca item ACCEPTED sem gates; job skipped ≠ aprovado.

🟢 — `tools/dod_controller.py` + DOD.md normas.

### R60: Commercial state machine de funil
**Regra:** Estados `NEW…DO_NOT_CONTACT` com overrides humanos auditados.

🟢 — CHECK constraints mig 062.

---

## ADRs retroativos sugeridos (023+)

| ADR | Título | Evidência |
|-----|--------|-----------|
| 023 | Dual capability coverage as-is authority | mig 058, dual_capability_coverage.py |
| 024 | CONFENGE commercial campaign fail-closed packages | ops/confenge_* |
| 025 | Commercial leads multi-bucket scoring non-claim | commercial_leads/scoring.py |
| 026 | Canonical entity linkage strong-key refuse-merge | linkage + mig 061 |
| 027 | National intel layered views ≠ operational coverage | mig 060 |
| 028 | ORPT operational reports + unified metadata | reports ORPT |
| 029 | Snapshot write guard for restored commercial DBs | mig 064 |
| 030 | Budget audit arithmetic-only non-legal claims | budget_audit |

*(Arquivos ADR individuais gerados em `_reversa_sdd/adrs/`.)*

---

## Máquinas de estado novas

Ver atualização em `state-machines.md` seções: commercial_leads, coverage (refresh), confenge run status, linkage classification.
