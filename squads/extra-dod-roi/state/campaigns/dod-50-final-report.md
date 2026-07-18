# Campaign DoD-50 Final Report

**Status:** SUCCESS
**PASS matrix (post audit-matrix):** 53
**Target:** 50
**Draft PR:** https://github.com/tjsasakifln/extra-consultoria/pull/24
**Branch:** `extra-roi/campaign-dod-50-20260718T003950Z`

## Structural gate

```bash
python3 squads/extra-dod-roi/scripts/cli.py campaign audit-matrix --write
python3 squads/extra-dod-roi/scripts/cli.py campaign audit-matrix   # must exit 0
```

SUCCESS requires: audit exit 0, consistency_ok, matrix_count ≥ 50, all qa_verdict=PASS.

## Stories (post-purge)

{'ROI-campaign-batch2-docs-truth': 26, 'ROI-cand-dyn-slice-44e18f3702d5': 9, 'ROI-campaign-batch3-ops-config': 13, 'ROI-campaign-batch4-ops-docs': 5}

## Purged by audit-matrix (not counted)

- URLs de fontes centralizadas (hardcodes em 29 arquivos)
- Win rate sem propostas (base_win_rate + unguarded sites)
- Score ≠ probabilidade (probabilidade_vitoria em reports)
- Process triad §1 (CONCERNS / unchecked)
- except Exception:pass / universal run_id / provenance / destructive confirm

## main

Not merged. Human review: PR #24.
