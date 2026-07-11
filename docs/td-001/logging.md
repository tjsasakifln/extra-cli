# Logging Estruturado — Documentacao

**Epic:** EPIC-TD-001 | **Story:** TD-5.1 | **Data:** 2026-07-11

## Visao Geral

O sistema de logging estruturado substitui `print()` e logs soltos por um sistema
padronizado com formato JSON, correlation IDs e niveis de severidade.

### Componentes

| Componente | Localizacao | Descricao |
|-----------|-------------|-----------|
| Logging config | `config/logging_config.py` | Configuracao centralizada com JSON formatter, correlation IDs, rotacao |
| Settings | `config/settings.py` | Variaveis de ambiente LOG_LEVEL, LOG_FORMAT, LOG_MAX_BYTES etc. |
| Documentacao | `docs/td-001/logging.md` | Este documento |

### Modulos Integrados

| Modulo | Arquivo | Tipo de Log |
|--------|---------|-------------|
| Enricher | `scripts/crawl/enricher.py` | INFO/WARNING/ERROR com metricas de enriquecimento |
| Orchestrator | `scripts/crawl/orchestrator.py` | INFO/WARNING com pipeline phases |
| Entity Matcher | `scripts/matching/entity_matcher.py` | INFO com estatisticas de matching |
| Coverage Calculator | `scripts/coverage/calculator.py` | INFO com relatorio de cobertura |
| Intel Pipeline | `scripts/intel_pipeline.py` | INFO com gate results, pipeline lifecycle |
| Health Check | `scripts/health_check.py` | INFO/WARNING/ERROR com resultados de checagem |

## Formato JSON

Cada registro de log e uma linha JSON com estes campos:

```json
{
  "timestamp": "2026-07-11T10:30:00.000000+00:00",
  "level": "INFO",
  "module": "scripts.crawl.enricher",
  "correlation_id": "a1b2c3d4e5f6",
  "message": "Concluido em 12.3s — enriquecidos=45, ignorados=0, falhas=2",
  "extra_data": {
    "enriched": 45,
    "skipped": 0,
    "failed": 2
  }
}
```

### Campos

| Campo | Tipo | Obrigatorio | Descricao |
|-------|------|-------------|-----------|
| `timestamp` | string (ISO-8601) | Sim | Momento do evento em UTC |
| `level` | string | Sim | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `module` | string | Sim | Nome do modulo (`__name__`) |
| `correlation_id` | string | Sim | ID de correlacao (12 char hex) |
| `message` | string | Sim | Mensagem formatada |
| `extra_data` | object | Nao | Dados estruturados adicionais |
| `exc_info` | string | Nao | Stack trace (apenas ERROR+) |

## Correlation IDs

Correlation IDs permitem rastrear uma operacao atraves de multiplos modulos.

### Uso

```python
from config.logging_config import (
    get_logger, set_correlation_id, get_correlation_id, reset_correlation_id,
)

# Iniciar operacao com novo correlation ID
cid = set_correlation_id()

# Em modulos subsequentes, o mesmo ID e propagado via contextvars
logger = get_logger(__name__)
logger.info("Operacao em progresso")

# Obter o ID corrente
current_cid = get_correlation_id()

# Limpar ao final da operacao
reset_correlation_id()
```

## Configuracao por Ambiente

### Desenvolvimento (`APP_ENV=dev` — padrao)

- Saida: stderr (capturado pelo systemd/journald em modo servico)
- Formato: JSON (ou text se `LOG_FORMAT=text`)
- Nivel padrao: INFO

### Producao (`APP_ENV=prod`)

- Saida: arquivo com rotacao em `output/logs/`
- Tamanho maximo: 10 MB (`LOG_MAX_BYTES`)
- Backup: 5 arquivos (`LOG_BACKUP_COUNT`)
- Formato: JSON

### Variaveis de Ambiente

| Variavel | Padrao | Descricao |
|----------|--------|-----------|
| `APP_ENV` | `dev` | Ambiente (`dev` ou `prod`) |
| `LOG_LEVEL` | `INFO` | Nivel padrao de log |
| `LOG_FORMAT` | `json` | Formato (`json` ou `text`) |
| `LOG_DIR` | `output/logs/` | Diretorio de logs (prod) |
| `LOG_MAX_BYTES` | `10485760` | Tamanho maximo por arquivo (10 MB) |
| `LOG_BACKUP_COUNT` | `5` | Numero de backups rotacionados |

## Health Check Integration

O `health_check.py` utiliza o logging estruturado para registrar resultados:

- `health_check started` — ao iniciar a checagem
- `health_check completed` — ao finalizar, com `exit_code` e resultados detalhados
- Nivel do log reflete a gravidade: INFO (0), WARNING (1), ERROR (2)

O JSON original para journald continua sendo emitido via `print(json.dumps(report))`
para compatibilidade com o parser do systemd.

## Metricas Capturadas

Os logs estruturados capturam automaticamente:

- **Duracao de crawl**: segundos por execucao no orchestrator
- **Contagem de registros**: fetched, upserted, matched (orchestrator)
- **Resultados de matching**: CNPJ, name_normalized, fuzzy, unmatched (entity_matcher)
- **Cobertura**: total entidades, cobertas, descobertas (calculator)
- **Health check**: status DB, storage, disk, sistema (health_check.py)
- **Quality gates**: passed/failed com issues e fixes (intel_pipeline)

## Boas Praticas

1. **Sempre use `get_logger(__name__)`** — nunca crie loggers manualmente
2. **Use niveis adequados** — DEBUG para detalhes, INFO para operacoes normais,
   WARNING para situacoes inesperadas nao-criticas, ERROR para falhas
3. **Passe dados estruturados em `extra_data`** — facilita analise futura
4. **Propague correlation IDs** — sempre chame `set_correlation_id()` no inicio
   de uma operacao top-level
5. **Nao use `print()`** — sempre use o logger (exceto para contratos explicitos
   como o JSON do health_check para journald)
