# Evidence — DoD §25 claim language guards

**Story:** `ROI-cand-dyn-slice-d7ab09cdef56`  
**Cycle:** `cyc-2026-07-18T125719Z`  
**Branch:** `extra-roi/cand-claim-language`

## Items

| DoD | Guard |
|-----|-------|
| Ausência de dados ≠ ausência de licitação sem consulta | `absence_is_not_no_tender` |
| Vencedor ≠ conjunto completo de concorrentes | `winners_are_not_complete_competitors` |
| Participante não id. ≠ inexistente | `unidentified_participant_not_nonexistent` |
| Win rate sem propostas | `win_rate` |
| Score ≠ probabilidade sem calibração | `score_is_not_probability` |
| Relatórios exibem limitações | `report_has_limitations` |
| Nenhum doc afirma acompanhar obras | `text_forbids_works_tracking` |

## Artifacts

- `scripts/lib/claim_language.py`
- `scripts/reports/run_metadata.py` (CLAIMS_FORBIDDEN extended)
- `tests/test_claim_language.py` — 9 passed

## Explicit non-claims

- Orphan empty bullet not flipped
- Does not wire every historical report CLI path yet (guards are library + unit proof)
