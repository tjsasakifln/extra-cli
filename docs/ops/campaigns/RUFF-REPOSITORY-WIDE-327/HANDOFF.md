# Ruff Repository-Wide — Issue #327

## Resultado

- Baseline reproduzido em `d0ce8474`: **298 findings**, 207 corrigíveis e 91 manuais, em 97 arquivos.
- Base da onda final: `main@5c233b351edf6c8d9ed2a76001957f2e9c071461`.
- Implementação do gate final: `afb9cc33` (o SHA exato de merge em `main` fica registrado na issue #327 após a CI).
- Ruff: **0 findings** com `ruff==0.15.12` e `ruff check .`.
- Nenhum `lint.select`, `lint.ignore`, threshold ou exclusão ampla foi reduzido.
- TD-7.1 permanece `InProgress`: mypy e cobertura continuam fora do escopo da #327.

## Histograma por onda

| Estado | Findings | Delta |
|---|---:|---:|
| Baseline | 298 | — |
| Testes em subdiretórios (PR #336) | 240 | -58 |
| Testes raiz (PR #337) | 195 | -45 |
| Squad DOD e controlador (PR #338) | 102 | -93 |
| Tooling, segurança e gate final | 0 | -102 |

Baseline por regra: F401 68; I001 57; UP017 36; S603 22; S607 18; S311 14;
UP035 12; UP006 10; F841/S608/W291 9 cada; UP015/W293 7 cada; E741/S108 3
cada; F601/S310/S324/S602 2 cada; N806/N818/S101/S314/UP028/W292 1 cada.

## Alterações de contrato

- CI e `make lint` bloqueiam findings Python em todo o repositório.
- `make lint-fix` aplica somente autofixes seguros repository-wide.
- O formatter permanece separado e limitado a `scripts/`; não houve reformatação repository-wide.
- O monitor AIOX rejeita URLs sem esquema HTTP(S) e hostname.
- XML de avaliação usa `lxml` sem entidades e sem rede.
- Identificadores SQL do seed PostgreSQL usam `psycopg2.sql.Identifier`; valores continuam parametrizados.

## Riscos e dívidas preservadas

- O formatter Ruff 0.15.12 propõe mudanças em scripts históricos; isso não faz parte do gate de lint nem desta campanha.
- Dois testes antigos do squad divergem do estado atual de governança: ledger declara 50 aceitos enquanto a reconstrução retorna 0, e um teste ainda exige que `Test All` seja apenas manual embora o job já seja obrigatório. Nenhum foi ocultado ou alterado.
- Ambientes PostgreSQL locais sem `pgvector` exigem o modo upgrade tolerante; a CI usa `pgvector/pgvector:pg16`.

## Verificação

```bash
python3 -m ruff check .
python3 -m ruff check . --statistics
make lint
python3 -m pytest tests/test_ruff_repository_gate.py -q -o addopts=''
python3 -m scripts.ops.check_generated_artifacts_policy --base origin/main
python3 -m scripts.ops.check_pr_reviewability --base origin/main
```

O fechamento da #327 exige ainda a CI de `main` verde no SHA exato de merge, sem jobs skipped.
