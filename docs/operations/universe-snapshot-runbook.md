# Universe Snapshot Runbook

## Visao Geral

O sistema de snapshots do universo canonico garante que todas as metricas
analiticas sejam rastreaveis ate uma versao especifica da planilha seed.
Mudancas na planilha produzem novos snapshots sem alterar analises historicas.

## Arquitetura

```
Planilha Seed  ──>  load_canonical_universe()  ──>  Snapshot (DB)
                      (scripts/lib/universe.py)         │
                                                        ├── target_universe_runs (1 por seed)
                                                        └── target_universe_entities (N por run)
                                                              │
                                        Queries analiticas ──┘  (via universe_run_id)
```

## Componentes

### 1. Script de Snapshot

```
scripts/universe_tools.py
```

### 2. Tabelas de Snapshot

- `target_universe_runs` — metadados de cada snapshot (hash, data, git_sha)
- `target_universe_entities` — entidades individuais de cada snapshot

### 3. View Ativa

- `v_target_universe_active` — entidades incluídas no snapshot mais recente
- `v_target_universe_all` — todas as entidades do snapshot mais recente (incluindo excluídas)

### 4. Ledger de Divergencia

Compara seed vs `sc_public_entities` para identificar:
- Entidades na seed mas nao no DB
- Entidades no DB mas nao na seed
- Divergencias de nome/razao social

## Operacoes

### Gerar Snapshot

```bash
# Gerar snapshot da seed atual
python scripts/universe_tools.py snapshot generate

# Especificar seed alternativa
python scripts/universe_tools.py snapshot generate --seed "Extra - alvos de licitacao. R-0.xlsx"

# Bloquear se seed mudou sem snapshot (usado em CI)
python scripts/universe_tools.py snapshot generate --block-on-change
```

### Listar Snapshots

```bash
python scripts/universe_tools.py snapshot list
```

Exemplo de saida:

```
  ID  Seed SHA256           File                                      Total    Incl   Excl  Unres  Created                        Git
   1  a1b2c3d4e5f6...       Extra - alvos de licitacao. R-0.xlsx       2085   1093    992      0  2026-07-13T12:00:00+00:00     abcdef12
```

### Verificar Seed

```bash
# Exit code 42 se a seed mudou sem snapshot correspondente
python scripts/universe_tools.py check-seed
```

### Ledger de Divergencia

```bash
# Mostrar divergencias no terminal
python scripts/universe_tools.py divergence

# Salvar em arquivo JSON
python scripts/universe_tools.py divergence --output output/divergence-ledger.json
```

### Saida do Ledger

```json
{
  "matched_count": 1042,
  "in_seed_only_count": 51,
  "in_db_only_count": 406,
  "warnings_count": 12,
  "warnings": [
    "Name mismatch for CNPJ-8 12345678: seed='NOME A' vs DB='NOME B'"
  ]
}
```

## Bloqueio por Seed Change

Quando ativado, o sistema impede execucao de pipelines analiticas se
a seed foi alterada sem um novo snapshot. O bloqueio usa exit code 42:

```
ERROR: Seed hash changed from {old_hash} to {new_hash}.
Run 'python scripts/universe_tools.py snapshot generate' before proceeding.
```

### Como Ativar

Por ambiente:
- **dev:** `UNIVERSE_BLOCK_ON_SEED_CHANGE=false` (nao bloqueia)
- **staging:** `UNIVERSE_BLOCK_ON_SEED_CHANGE=true` (bloqueia)
- **production:** `UNIVERSE_BLOCK_ON_SEED_CHANGE=true` (bloqueia)

Por script:
```python
from scripts.universe_tools import check_seed
check_seed()
```

## Migracao de Queries

### Antes (DB flag)

```sql
SELECT e.*, c.*
FROM sc_public_entities e
JOIN pncp_supplier_contracts c ON c.orgao_cnpj LIKE e.cnpj_8 || '%'
WHERE e.raio_200km = TRUE
```

### Depois (snapshot)

```sql
SELECT e.*, c.*
FROM sc_public_entities e
JOIN target_universe_entities tue ON tue.cnpj8 = e.cnpj_8
  AND tue.radius_decision = 'included'
JOIN pncp_supplier_contracts c ON c.orgao_cnpj LIKE e.cnpj_8 || '%'
WHERE tue.universe_run_id = (SELECT MAX(id) FROM target_universe_runs)
```

### Usando a View Ativa

```sql
SELECT tuv.*, c.*
FROM v_target_universe_active tuv
JOIN pncp_supplier_contracts c ON c.orgao_cnpj LIKE tuv.cnpj8 || '%'
```

## Ambiente

| Ambiente | .env | Block on Change | Log Level |
|----------|------|-----------------|-----------|
| dev | `.env.dev` | false | DEBUG |
| staging | `.env.staging` | true | INFO |
| production | `.env.production` | true | WARNING |

Para ativar um ambiente:

```bash
export $(grep -v '^#' .env.production | xargs)
```

## Integridade dos Dados

### Verificacoes de Consistencia

1. **Total de entidades:** `target_universe_runs.total_rows` deve igualar o numero de linhas na planilha seed (excluindo cabecalho)
2. **Soma:** `included_rows + excluded_rows + unresolved_rows == total_rows`
3. **Denominador:** `included_rows` deve ser 1093 para a seed atual
4. **Hash:** `seed_sha256` deve corresponder ao SHA-256 do arquivo seed

### Diagnosticos

```bash
# Verificar consistencia do snapshot mais recente
python3 -c "
from scripts.lib.universe import load_canonical_universe
u = load_canonical_universe()
s = u.summary()
print(f'Total: {s[\"total_seed_rows\"]}')
print(f'Included: {s[\"within_radius\"]}')
print(f'Excluded: {s[\"outside_radius\"]}')
print(f'Unresolved: {s[\"unresolved_rows\"]}')
print(f'Resolution: {s[\"universe_resolution_coverage_percent\"]}%')
"
```

## Troubleshooting

| Problema | Causa | Solucao |
|----------|-------|---------|
| `relation "target_universe_runs" does not exist` | Migration 037 nao aplicada | `psql -f db/migrations/037_target_universe_snapshot.sql` |
| `exit code 42` | Seed alterada sem snapshot | `python scripts/universe_tools.py snapshot generate` |
| `No snapshots found` | Primeira execucao | `python scripts/universe_tools.py snapshot generate` |
| view `v_target_universe_active` nao existe | Migration 038 nao aplicada | `psql -f db/migrations/038_target_universe_active_view.sql` |
