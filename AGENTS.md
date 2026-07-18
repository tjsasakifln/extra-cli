# AGENTS.md — adaptador fino (Codex / agentes compatíveis)

**Guia canônico:** [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)  
**DoD:** [`DOD.md`](DOD.md)

Este arquivo **não** define requisitos de produto. Em conflito, prevalece:

1. `DOD.md`  
2. ADR vigente  
3. Código testado  
4. Evidência reproduzível  

## Comandos (mesmos do guia canônico)

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
python3 -m pytest tests/ -q --tb=no -x
python3 -m scripts.golden_path --dsn "$LOCAL_DATALAKE_DSN"
python3 squads/extra-dod-roi/scripts/cli.py force-next
```

## Escopo / arquitetura / operação

Ver seções 2–3 de `docs/DEVELOPMENT.md`. Não inventar selos (`LOCAL_READY`, 95%, VPS) sem evidência.
