# Handoff — DOC-DEEP-ANALYSIS-DECISION-INTEL-01

## Delivered

- Citation integrity fix in `edital_case` (`aderencia_perfil` document binding + excerpt token window)
- E2E evidence: edital_case verify **PASS**, budget_audit verify **PASS**
- DoD §2.2 / §2.6 triage + deep analysis + planilha/BDI marked with campaign evidence
- Ops docs updated with criterion of done (collection vs consulting)

## Reproduce

```bash
python3 -m pytest tests/edital_case/ tests/budget_audit/ -q --tb=no
```

## Artifacts

`artifacts/campaigns/DOC-DEEP-ANALYSIS-DECISION-INTEL-01/`
