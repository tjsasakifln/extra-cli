# Onboarding: Consolidação dos Módulos de Alta Confiança

> Feature: `001-modulos-alta-confianca`
> Data: 2026-07-14
> Roadmap: `_reversa_forward/001-modulos-alta-confianca/roadmap.md`

## Pré-requisitos

- Docker 24+ e Docker Compose v2
- Python 3.12
- Git clone do repositório em `/mnt/d/extra consultoria/`
- Acesso ao PostgreSQL (local ou docker)

## Passo a passo para testar a feature

### 1. Bootstrap do ambiente local

```bash
# Tornar o bootstrap executável
chmod +x scripts/bootstrap_local.sh

# Executar bootstrap (idempotente — pode rodar múltiplas vezes)
./scripts/bootstrap_local.sh
```

**O que esperar:**
- PostgreSQL sobe via Docker (porta 5433)
- Todas as migrations (v1, v2, v3) são aplicadas
- Seed carregada: 2.085 entes SC + 1.093 universo canônico
- Schema fingerprint verificado
- Segunda execução é no-op (cada step reporta "já configurado")

### 2. Pipeline completo via Makefile

```bash
# Ver targets disponíveis
make help

# Pipeline completo (crawl → report)
make run-pipeline

# Apenas ingestão
make run-crawl

# Apenas relatórios (assume dados já ingeridos)
make run-report
```

**O que esperar:**
- `make run-pipeline` executa PNCP crawl completo
- `output/reports/` contém PDF + Excel
- Exit code 0

### 3. Testes e coverage gate

```bash
# Rodar todos os testes (unitários, sem slow)
make test

# Rodar com coverage e gate
pytest --cov=scripts --cov-report=term-missing -m "not slow"
python scripts/coverage_gate.py
```

**O que esperar:**
- `coverage_gate.py` emite JSON com coverage por módulo:
  ```json
  {
    "opportunity_intel": {"coverage_pct": 85.2, "pass": true},
    "coverage": {"coverage_pct": 78.1, "pass": false},
    ...
  }
  ```
- Exit code 0 se todos ≥ 80%, exit 2 se algum abaixo
- Relatório detalhado em `output/coverage/coverage-gate-report.json`

### 4. QW-01 Radar com snapshot reconciliation

```bash
# Executar radar completo
python scripts/opportunity_intel/cli.py radar --profile config/client_profiles/extra.yaml
```

**O que esperar:**
- Pipeline 12 etapas (incluindo a nova reconciliação)
- CSV em `output/runs/<run_id>/radar.csv`
- `manifest.json` com `reconciliation: {bids_inactivated: N, bids_kept: M}`
- `active_snapshot_integrity` = 100%
- Oportunidades PRIORITARIA têm `official_url` preenchida
- Oportunidades sem URL → REVISAR com `missing_fields: ["official_url"]`

### 5. Validação competitive intel schema

```bash
python -c "
from scripts.opportunity_intel.schema import connect_postgres
from scripts.opportunity_intel.validate_competitive_intel import validate_competitive_intel_schema
conn = connect_postgres()
result = validate_competitive_intel_schema(conn)
print(result.json(indent=2))
"
```

**O que esperar:**
```json
{
  "market_share": "pass",
  "hhi": "pass",
  "supplier_ranking": "pass"
}
```

### 6. CI gate unificado

```bash
# Executar todos os gates em sequência
bash scripts/ci_gate.sh
```

**O que esperar:**
- Saída JSON com status por etapa:
  ```json
  [
    {"stage": "ruff", "status": "pass", "duration_ms": 1234},
    {"stage": "pyright", "status": "pass", "duration_ms": 5678},
    {"stage": "bandit", "status": "pass", "duration_ms": 890},
    {"stage": "pytest", "status": "pass", "duration_ms": 45678},
    {"stage": "coverage_gate", "status": "pass", "duration_ms": 234}
  ]
  ```
- Exit code 0 se todos passam, 2 se qualquer etapa falha

### 7. Testar docker-compose future-proof

```bash
# Ambiente local (default)
docker compose -f docker-compose.local.yml up -d

# Simular ambiente VPS (mesmo compose, env diferente)
ENV=vps docker compose -f docker-compose.local.yml up -d
```

**O que esperar:**
- Ambos sobem sem erro
- PostgreSQL acessível em `127.0.0.1:5433`
- Serviço `app` executa bootstrap e fica pronto

## Verificações manuais

- [ ] `make help` lista todos os targets
- [ ] `./scripts/bootstrap_local.sh` é idempotente (rode 2×)
- [ ] `make test` passa sem erro (unit tests)
- [ ] `python scripts/coverage_gate.py` emite JSON válido
- [ ] `python scripts/opportunity_intel/cli.py radar` completa 12 etapas
- [ ] CSV do radar não contém PRIORITARIA sem URL
- [ ] `validate_competitive_intel_schema()` retorna 3 checks
- [ ] `bash scripts/ci_gate.sh` completa sequência completa
- [ ] `docker compose -f docker-compose.local.yml up` sobe banco + app

## Troubleshooting

| Problema | Causa provável | Solução |
|----------|---------------|---------|
| `make: command not found` | Make não instalado | `sudo apt install make` |
| Bootstrap falha no step 1 (DB) | Docker não rodando | `docker compose -f docker-compose.local.yml up -d` |
| Coverage gate falha em módulo | Testes insuficientes | Rodar `pytest --cov=scripts --cov-report=term-missing` para ver gaps |
| Reconciliação não roda | Execução parcial | Verificar `run_outcome.is_complete` no manifest |
| `docker-compose.local.yml` conflita porta 5433 | Outro PostgreSQL local | Ajustar `DB_PORT` no `.env` |

## Histórico de alterações

| Data | Alteração | Autor |
|------|-----------|-------|
| 2026-07-14 | Versão inicial gerada por `/reversa-plan` | reversa |
