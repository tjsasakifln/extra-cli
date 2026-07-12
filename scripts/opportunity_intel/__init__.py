"""Opportunity Intelligence — tracking de licitações abertas.

Vertical ponta a ponta para localizar, consolidar, deduplicar,
consultar e exportar licitações abertas para a Extra Construtora
nos entes públicos num raio de 200 km de Florianópolis.

Modules:
    models:     Dataclasses (OpportunityRecord, CrawlRequest, FetchResult)
    crawler_base: Base crawler with retry/backoff/rate limit/checkpoint
    transformer: Record normalization from raw source data
    dedup:      Cross-source deduplication (4 levels)
    status:     Canonical status calculation
    ranking:    Explainable ranking (GO/REVIEW/NO_GO, score 0-100)
    cli:        CLI (list, show, explain, coverage, source-health, update, export)
    manifest:   Coverage manifest generation
"""

__version__ = "1.0.0"
