# Gold Standard Baseline — CONFENGE Commercial Ready

**Status:** `BLOCKED_COMMERCIAL_RELEVANCE_NOT_PROVEN`  
**Created:** 2026-07-25T23:54:05Z  
**PR:** #144 (`campaign/confenge-commercial-ready-01`)

## SHAs

| Ref | SHA |
|-----|-----|
| PR HEAD | `7c8b56b6063b8315422178e20f2a250bea752c85` |
| main | `8344254942ec48978566317df16d7b3e3caabd89` |

## Last published run (preserved)

| Field | Value |
|-------|-------|
| run_id | `cl-20260725T232722Z-3e11387a` |
| snapshot_id | `bb1fa54ececca5ab5d68a700e103d5103a5fa424f233344d41d955543cc4d8d3` |
| dataset_rows | 60000 |
| candidate_contracts | 33682 |
| candidate_suppliers | 7670 |
| published_leads | 20 |

## Sector fit distribution (contaminated denominator)

```json
{
  "STRONG_ENGINEERING_FIT": 4791,
  "CONFLICTING": 308,
  "POSSIBLE_ENGINEERING_FIT": 1826,
  "OUT_OF_SCOPE": 745
}
```

## Known methodological defects

### DENOMINATOR_CONTAMINATION (CRITICAL)

Sector concentration calculated only on prefiltered relevant contracts (relevant/prefiltered), not full supplier history. Produces false STRONG_ENGINEERING_FIT (e.g. 1/1=100%).

Evidence: `pipeline.load_contract_universe returns filter_relevant_contracts(kept) only; group_by_supplier never loads non-matching contracts`

### INFLATED_STRONG_RATE (CRITICAL)

4791 STRONG_ENGINEERING_FIT of ~7670 candidates is statistically implausible and indicates circular classification

Evidence: `sector_fit_distribution STRONG=4791`

### CNAE_NOT_INTEGRATED (HIGH)

Pipeline passes cnae_principal=None for virtually all suppliers; CONFIRMED path unused

Evidence: `evaluate_supplier_validity called without cnae in pipeline.run_pipeline`

### WEAK_STRONG_THRESHOLDS (HIGH)

STRONG allowed with ratio>=0.60 and relevant>=2, or even ratio>=0.99 and relevant>=1; name+1 contract can become STRONG

Evidence: `sector_fit.STRONG_CONCENTRATION=0.60 STRONG_MIN_RELEVANT=2 plus ratio>=0.99 path`

### FULL_POPULATION_AMBIGUOUS (HIGH)

FULL_POPULATION means full prefilter scan, not full snapshot discovery or full candidate history

Evidence: `POPULATION_FULL skips LIMIT but still applies SQL prefilter and only keeps relevant rows`

### HUMAN_METRICS_UNVERIFIED (HIGH)

Human precision labels insufficient; blockers already note BLOCKED_INSUFFICIENT_HUMAN_LABELS

Evidence: `['BLOCKED_INSUFFICIENT_HUMAN_LABELS', 'BLOCKED_PENDING_HUMAN_ACCEPTANCE', 'soak_no_write_proven_unavailable']`

### SNAPSHOT_BINDING_WEAK (MEDIUM)

Binding primarily row_count + sample_hashes; need canonical_table_hash verification gate

Evidence: `{'ok': True, 'status': 'BOUND', 'declared_row_count': 60000, 'database_row_count': 60000, 'min_date': '2026-02-13', 'max_date': '2026-07-23', 'sample_hashes': ['00000000000191-2-000004/2026:50052653000192:871dd87a1f8dd86e0e7db63314adce94', '00000000000191-2-000009/2026:63056469000162:9d1f42e66ce0dfc826509cfaffeba22c', '00000000000191-2-000013/2026:31834991000131:e3e30f0fb9f15d81639ab53fdcea37a6', '00000000000191-2-000020/2026:89278519000140:fd2a1b4044d0f97f34ae9829f156088b', '00000000000191-2-000024/2026:33624704000194:5b32f5760c24803cea3f8f35922e9cea'], 'table_snapshot_hash': 'bb1fa54ececca5ab5d68a700e103d5103a5fa424f233344d41d955543cc4d8d3', 'schema_version': 'pncp_supplier_contracts@campaign', 'reasons': [], 'justified_filter': False, 'filter_note': None, 'table': 'pncp_supplier_contracts'}`

## Current blockers

```json
[
  "BLOCKED_INSUFFICIENT_HUMAN_LABELS",
  "BLOCKED_PENDING_HUMAN_ACCEPTANCE",
  "soak_no_write_proven_unavailable"
]
```

## Gate state

```json
{
  "CI_CONFENGE_Commercial_Validity": "SUCCESS (structural; does not prove commercial relevance)",
  "campaign_status": "BLOCKED",
  "technical_status": "BLOCKED",
  "rc_technical_pass_revoked": true
}
```

## Top-20 snapshot (pre-fix)

```json
[
  {
    "rank": 1,
    "cnpj14": "12253900000120",
    "razao_social": "BRANIX EMPREENDIMENTOS LTDA",
    "score_total": 9.737,
    "supplier_sector_fit": "STRONG_ENGINEERING_FIT",
    "contract_relevance": "PASS",
    "commercial_signal_fit": "PASS",
    "geography_fit": "PASS"
  },
  {
    "rank": 2,
    "cnpj14": "95257945000108",
    "razao_social": "CONSTRUBRÁS CONSTRUTORA LTDA",
    "score_total": 9.5276,
    "supplier_sector_fit": "STRONG_ENGINEERING_FIT",
    "contract_relevance": "PASS",
    "commercial_signal_fit": "PASS",
    "geography_fit": "PASS"
  },
  {
    "rank": 3,
    "cnpj14": "27254414000101",
    "razao_social": "FAK EMPREENDIMENTOS LTDA",
    "score_total": 9.5,
    "supplier_sector_fit": "STRONG_ENGINEERING_FIT",
    "contract_relevance": "PASS",
    "commercial_signal_fit": "PASS",
    "geography_fit": "PASS"
  },
  {
    "rank": 4,
    "cnpj14": "19648512000197",
    "razao_social": "KARAIBA CONSULTORIA E PROJETOS LTDA.",
    "score_total": 9.5,
    "supplier_sector_fit": "STRONG_ENGINEERING_FIT",
    "contract_relevance": "PASS",
    "commercial_signal_fit": "PASS",
    "geography_fit": "PASS"
  },
  {
    "rank": 5,
    "cnpj14": "38517835000196",
    "razao_social": "PROJESOL ENGENHARIA LTDA",
    "score_total": 9.2243,
    "supplier_sector_fit": "STRONG_ENGINEERING_FIT",
    "contract_relevance": "PASS",
    "commercial_signal_fit": "PASS",
    "geography_fit": "PASS"
  },
  {
    "rank": 6,
    "cnpj14": "45145494000130",
    "razao_social": "CONSTRUTORA IRMAOS WARTHA LTDA",
    "score_total": 9.1,
    "supplier_sector_fit": "STRONG_ENGINEERING_FIT",
    "contract_relevance": "PASS",
    "commercial_signal_fit": "PASS",
    "geography_fit": "PASS"
  },
  {
    "rank": 7,
    "cnpj14": "15247296000117",
    "razao_social": "IBERICA CONSTRUÇÕES CIVIS E VIARIAS LTDA ME",
    "score_total": 8.9406,
    "supplier_sector_fit": "STRONG_ENGINEERING_FIT",
    "contract_relevance": "PASS",
    "commercial_signal_fit": "PASS",
    "geography_fit": "PASS"
  },
  {
    "rank": 8,
    "cnpj14": "07192929000109",
    "razao_social": "CONSTRUTORA JLV LTDA",
    "score_total": 8.7,
    "supplier_sector_fit": "STRONG_ENGINEERING_FIT",
    "contract_relevance": "PASS",
    "commercial_signal_fit": "PASS",
    "geography_fit": "PASS"
  },
  {
    "rank": 9,
    "cnpj14": "52067902000149",
    "razao_social": "WE TORRES ARTEFATOS DE CIMENTO E PRE MOLDADOS LTDA",
    "score_total": 8.7,
    "supplier_sector_fit": "STRONG_ENGINEERING_FIT",
    "contract_relevance": "PASS",
    "commercial_signal_fit": "PASS",
    "geography_fit": "PASS"
  },
  {
    "rank": 10,
    "cnpj14": "62913677000178",
    "razao_social": "ALIANCA ENGENHARIA E PAVIMENTACAO LTDA",
    "score_total": 8.7,
    "supplier_sector_fit": "STRONG_ENGINEERING_FIT",
    "contract_relevance": "PASS",
    "commercial_signal_fit": "PASS",
    "geography_fit": "PASS"
  }
]
```

---

This baseline marks the starting point for gold-standard remediation.
No commercial relevance is claimed. Status remains **BLOCKED**.
