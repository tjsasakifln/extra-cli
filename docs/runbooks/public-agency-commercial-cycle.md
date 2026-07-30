# Runbook — ciclo comercial public-agencies

## Pré-requisitos

- DSN com `pncp_supplier_contracts` (ex.: `LOCAL_DATALAKE_DSN`)
- Python deps do projeto (`pyyaml`, `psycopg2`, `openpyxl` opcional para xlsx)

## Execução

```bash
export LOCAL_DATALAKE_DSN='postgresql://user:pass@host:5433/pncp_datalake'
make confenge-commercial-cycle CONFENGE_COMMERCIAL_TARGET=public-agencies

# parâmetros úteis via env/flags do confenge_commercial_cycle:
# --uf SC --as-of 2026-07-15 --max-public-agency-leads 20
# --priority-population-max 50000
```

## Testes

```bash
make test-public-agency
# ou
python3 -m pytest tests/public_agency/ -q
```

## Interpretar saída

1. Abrir `public-agency-summary.md` e `public-agency-report.html`
2. Revisar `public-agency-conflict-review.csv`
3. Ler dossiers em `dossiers/`
4. Kit em `commercial-kit/` (credenciais = revisão necessária até comprovadas)
5. **Não contatar** até clearance + aprovação humana

## Falhas

| reason | Significado |
|--------|-------------|
| SOURCE_FAILURE | DSN/SQL/fonte falhou (não interpretar como universo vazio) |
| EMPTY_VALID_RESULT | Fonte ok, zero linhas |
| NO_PUBLISHABLE_LEADS | Avaliados mas nenhum passou nos gates |
| FILTER_REMOVED_ALL | Filtros removeram todos |

## Atualizar tetos

Editar `config/legal/direct_contracting_thresholds.yaml` (nova vigência). Rodar testes de fronteira.
