# QW-01 — Baseline auditável

Gerado em 2026-07-13 (UTC). Este documento registra o estado anterior às alterações do QW-01.

## Identidade da revisão

- Repositório: `tjsasakifln/extra-consultoria`
- Branch: `main`
- Git SHA: `0fef9debf195af19953dcbfb702b2ad499369b11`
- Último commit: `fix: restore critical readiness CI gates`
- Worktree já estava suja. Foram preservadas mudanças preexistentes em `.claude/agent-memory/aiox-dev/MEMORY.md`, três arquivos `output/readiness/opportunity-*`, cinco memórias não rastreadas e `Extra - alvos de licitação. R-0.backup.xlsx`.
- A configuração AIOX referencia `docs/framework/{coding-standards,tech-stack,source-tree}.md` e fallbacks em `docs/pt/framework/`; os seis arquivos estão ausentes (falha de configuração, não de código do radar).

## Ambiente e PostgreSQL real

- `python` não existe; `python3` é Python 3.12.3.
- `psql` cliente 18.4, servidor PostgreSQL 16.14.
- Container: `smartlic-datalake`, exposto em `127.0.0.1:54399`.
- DSN local auditado: `postgresql://postgres:***@127.0.0.1:54399/postgres`.
- Fingerprint pré-migration das colunas do schema `public`: `f58ddc6b1ee82a41b321d3b30248d865000c6e20787d76477f21b93ebf115fcd` (459 linhas normalizadas de `information_schema.columns`).
- Estruturas candidatas já existentes: `coverage_evidence`, `entity_coverage`, `opportunity_coverage`, `opportunity_intel`, `opportunity_runs`, `opportunity_checkpoints`, `ingestion_runs`, `pncp_raw_bids`, `pncp_supplier_contracts` e `sc_public_entities`.

## Universo-alvo

- Seed: `Extra - alvos de licitação. R-0.xlsx`.
- SHA-256: `d65f272812cf8dc95f3ca78c5db9a2fb2a39a759e5633eb3fb91891ad10a5486`.
- Linhas da seed: 2.085; `SIM ✓`: 1.093; `NÃO`: 992; sem coordenadas: 0.
- CNPJ raízes únicos: 2.082.
- O CNPJ raiz `00394494` aparece quatro vezes. Não há duplicidade da chave composta normalizada `(cnpj8, município, razão social)`; as quatro linhas são identidades legítimas distintas.
- Banco: 2.088 linhas, 2.085 ativas, 1.445 ativas com `raio_200km=TRUE` e `distancia_fk<=200`, mais três inativas. A flag do banco não representa a população canônica da seed.

## Dados locais

- `pncp_raw_bids`: 259.161 registros ativos; 115.022 têm `matched_entity_id`; 997 entes distintos têm presença. A maior `data_publicacao` é 2202-10-13, logo existem outliers temporais.
- `opportunity_intel`: 96.682 registros PNCP de produção; 46.555 estão classificados como `open`, além de cinco fixtures `test_batch`.
- `opportunity_runs`: somente uma run PNCP, `failed`, com zero registros/páginas e sem mensagem de erro.
- `opportunity_coverage`: vazio.
- `pncp_supplier_contracts`: 3.689.859 registros ativos; o schema real usa `numero_controle_pncp`, `ni_fornecedor`, `nome_fornecedor`, `valor_global` e `data_assinatura`. Não existe `data_publicacao`; há outlier `data_assinatura=8406-05-16`.
- `coverage_evidence`: 7.943 linhas em estados de sucesso. As evidências reconstruídas a partir de presença persistida não têm período consultado nem prova de paginação e, portanto, não provam monitoramento ou `success_zero`.

## Pipelines concorrentes observados

- `scripts/crawl/monitor.py`: ingestão ampla em `pncp_raw_bids`, ledger `coverage_evidence` e múltiplas fontes.
- `scripts/opportunity_intel/`: segunda ingestão PNCP independente em `opportunity_intel`, com `opportunity_runs`, checkpoints e coverage próprios.
- `scripts/consulting_readiness.py`: readiness global e métricas de contratos.
- `scripts/contract_intel/`: universo próprio derivado da mesma planilha.

## Execuções de baseline

### Suíte crítica existente

Comando:

```bash
python3 -m pytest tests/test_freshness_gate.py tests/test_universe.py tests/test_manifest.py tests/test_consulting_readiness.py tests/test_coverage_truth.py tests/test_resolve_unresolved_entities.py -o addopts='' --tb=short -v
```

Resultado: `105 passed, 1 skipped` em 12,77 s. O skip é de uma consulta de gaps. A suíte passa, mas testa explicitamente o inteiro hardcoded 1.093 e não detecta a divergência entre a população do manifest e a consulta de gaps.

### Consulting readiness

Executado contra PostgreSQL, com outputs isolados em `/tmp/qw-01-baseline`.

Resultado observado: exit code 0, `PASS 99,7%` (`1090/1093`). Este PASS não é válido para QW-01 porque:

- considera sucesso em qualquer fonte em vez de todas as fontes aplicáveis;
- aceita evidência reconstruída a partir de presença de dados;
- 518 entes estavam fresh, 33 stale e 539 unknown;
- seis fontes foram classificadas como bloqueadas;
- três métricas excederam statement timeout;
- quatro métricas usaram colunas inexistentes (`contrato_id`/`fornecedor_cnpj`).

Classificação: falha de código e de qualidade da evidência.

### Freshness gate

Resultado: exit code 1, erro técnico explícito: `pncp_supplier_contracts missing required business date column data_publicacao`.

Classificação: schema drift corretamente exposto, mas a especificação da fonte está errada. Para contratos, a data de negócio existente é `data_assinatura`.

### Opportunity manifest

Resultado: exit code 2, `42,18%` de presença (`461/1093`) e 46.555 registros `open`.

Problemas: a métrica é presença, não monitoramento; o denominador é hardcoded; a consulta de gaps usa `sc_public_entities.raio_200km`, população de 1.445; os caminhos retornados no resultado apontam para `output/readiness` mesmo quando o output foi isolado.

Classificação: falha de código e artefatos versionados obsoletos.

### Opportunity CLI

- `coverage`: mostra registros por status/ranking, mas a seção por entidade está vazia.
- `source-health`: apresenta 96.682 registros como health, embora a única run PNCP esteja `failed`.
- O comando direto por arquivo (`python scripts/...`) falha em imports; a forma por módulo (`python3 -m scripts...`) funciona.
- `update --source all` seleciona somente `pncp` e `pncp_publication`, duas estratégias da mesma fonte.
- `--mode dry-run` não impede persistência no caminho atual, portanto não foi executado.

Classificação: falha de código/configuração operacional.

## Bugs confirmados

- `scripts/opportunity_intel/crawler_base.py` descarta `totalPaginas` e `totalRegistros` obtidos pelo parser.
- O checkpoint recebe `len(results)` (páginas acumuladas) como se fossem registros.
- O limite é avaliado em páginas, embora o modelo não diferencie `max_pages` de limite de registros.
- Erros de página podem resultar em status `completed` se não ultrapassarem 50% dos registros.
- `completed_zero` não exige prova de escopo completo.
- `status.py` classifica `Divulgada no PNCP` e publicação recente como `open`, sem exigir prazo futuro ou endpoint que prove proposta aberta.
- O ranking mistura confiança, aderência e recomendação e usa `GO/NO_GO`.
- O README contém números fixos, semântica de “preços praticados”, fontes não comprovadamente operacionais e comandos com `python` inexistente neste ambiente.

## Estado do baseline

`FAIL`: o banco contém dados úteis e recentes, mas readiness de monitoramento não está provada. A causa é majoritariamente código/evidência; não há ausência de credencial para PNCP. Outputs antigos não podem ser usados como prova de uma nova execução.
