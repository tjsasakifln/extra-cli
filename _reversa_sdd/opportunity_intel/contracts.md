# Opportunity Intelligence — Contratos Externos

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d

## Contrato: PNCP Propostas Abertas

| Campo | Valor |
|-------|-------|
| **Endpoint** | `https://pncp.gov.br/api/consulta/v1/contratacoes/proposta` |
| **Método** | GET |
| **Autenticação** | Não requer (API pública) |
| **Paginação** | `?pagina=1&tamanhoPagina=100` |
| **Parâmetros** | `dataPublicacaoInicio`, `dataPublicacaoFim`, `uf`, `municipio`, `modalidade` (19 valores), `orgaoCnpj`, `palavraChave` |
| **Retorno** | JSON: `{totalRegistros, totalPaginas, pagina, tamanhoPagina, data[]}` |
| **Rate limit** | Não documentado; circuit breaker local com 3 retries |
| **Adapter** | `scripts/opportunity_intel/pncp_crawler.py` |

### Schema de resposta (campos usados)

```json
{
  "totalRegistros": 34,
  "totalPaginas": 1,
  "pagina": 1,
  "data": [{
    "orgaoCnpj": "string",
    "orgaoNome": "string",
    "unidadeOrgaoCnpj": "string",
    "unidadeOrgaoNome": "string",
    "modalidadeNome": "string",
    "objeto": "string",
    "dataPublicacaoPncp": "string (ISO date)",
    "dataAberturaProposta": "string (ISO datetime)",
    "dataEncerramentoProposta": "string (ISO datetime)",
    "valorEstimado": "number",
    "situacaoCompra": "string",
    "numeroControlePNCP": "string (ID canônico)",
    "linkSistemaOrigem": "string (URL oficial)",
    "municipio": "string",
    "uf": "string"
  }]
}
```

## Contrato: Outras Fontes (Adapter Contract)

Cada fonte deve implementar:

```python
class SourceAdapter:
    def crawl(self, request: CrawlRequest) -> SourceRunResult: ...
    def transform(self, raw_records: list[dict]) -> list[CanonicalOpportunity]: ...
    def persist(self, records: list[CanonicalOpportunity], run_id: str) -> PersistResult: ...
    def reconcile(self, run_result: SourceRunResult) -> ReconcileResult: ...
    def health(self) -> SourceHealth: ...
```

### SourceRunResult

| Campo | Tipo | Descrição |
|-------|------|-----------|
| status | `str` | `success`, `partial`, `error`, `zero` |
| scope_key | `str` | Identificador do escopo (ex: `pncp/sc/2026-07-13`) |
| pages_expected | `int\|None` | Páginas esperadas (None se desconhecido) |
| pages_processed | `int` | Páginas efetivamente processadas |
| records_expected | `int\|None` | Registros esperados |
| records_fetched | `int` | Registros obtidos |
| records_persisted | `int` | Registros persistidos no banco |
| completion_rule | `str` | `all_pages`, `max_pages`, `max_records`, `error` |
| errors | `list[dict]` | Erros encontrados |
| raw_payload_location | `str` | Caminho para payload bruto (gzip) |
| started_at | `datetime` | Início da execução |
| finished_at | `datetime` | Fim da execução |
| parser_version | `str` | Versão do parser usado |

## Contrato: QW-01 Radar Output

### CSV (34 colunas fixas)

`RADAR_COLUMNS` = (opportunity_key, source, source_ids, official_url, entity_id, orgao_cnpj, orgao_nome, municipio, distancia_km, objeto, categoria, modalidade, valor_estimado, valor_semantica, data_publicacao, data_abertura, data_encerramento, dias_restantes, status_canonico, status_evidence, data_confidence_score, client_fit_score, triage_recommendation, positive_factors, negative_factors, blockers, missing_fields, first_seen_at, last_seen_at, run_id, generated_at, git_sha, seed_sha256, schema_fingerprint)

### manifest.json

```json
{
  "run_id": "uuid",
  "generated_at": "ISO8601",
  "git_sha": "40-char",
  "seed_sha256": "64-char",
  "schema_fingerprint": "64-char",
  "readiness": "READY|PARTIAL|NOT_READY",
  "universe_resolution_percent": 100.0,
  "monitoring_coverage_percent": 20.95,
  "exit_code": 2,
  "total_opportunities": 673,
  "active_snapshot_count": 34,
  "sources": {
    "pncp": {"status": "success", "records": 34, "coverage": 20.95},
    "compras_gov": {"status": "not_proven", "records": 0, "coverage": null}
  },
  "blockers": ["snapshot_reconciliation_pending", "complementary_sources_unproven"]
}
```

## Exit Codes

| Código | Significado | Gatilho |
|--------|-------------|---------|
| 0 | Sucesso | Coverage ≥ 95%, sem blockers fatais |
| 1 | Data gaps | Coverage < 100% mas ≥ 95%, ou campos ausentes |
| 2 | Below threshold | Coverage < 95% (MONITORING_THRESHOLD) |
| 3 | Fatal | Schema inválido, migrations pendentes, universo vazio |
