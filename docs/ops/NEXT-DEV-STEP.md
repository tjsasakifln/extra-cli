# Próximo passo de desenvolvimento (sem reconstruir contexto)

**Atualizado:** 2026-07-18  
**Branch épica:** `epic/advance-30d-local-ready-20260718`  
**Campanha:** ADVANCE-30D-LOCAL-READY

## Comando único

```bash
python3 squads/extra-dod-roi/scripts/cli.py force-next
```

Isso re-rankeia, materializa a story AIOX Draft do `ranking[0]` e bloqueia implementação até `@po` Ready.

## Estado honesto

| Item | Estado |
|------|--------|
| Cobertura operacional | **0%** (meta 95%) — prioridade de produto |
| LOCAL_READY | **NOT_READY** |
| PG local (extra-test-db) | porta 5433; schema ainda precisa de migrations completas |
| DOE-SC / VPS pay / aceite Tiago | **BLOCKED_EXTERNAL** / humano |

## Artefatos

- Scorecard: `squads/extra-dod-roi/state/campaigns/advance-30d-20260718/scorecard.json`
- Manifesto: `.../MANIFEST.md`
- Glossário: `docs/GLOSSARY.md`
- Changelog: `CHANGELOG.md`
