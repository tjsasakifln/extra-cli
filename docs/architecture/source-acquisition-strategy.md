# Source Acquisition Strategy — Extra Consultoria

**Versão:** 1.0 | **Data:** 2026-07-15 | **Autor:** AIOX Master (Orion)
**Branch:** `epic-coverage-max-200km`

---

## 1. Estratégia de Aquisição

### Princípios

1. **Escada de aquisição** (simples → complexo): API JSON → HTML parsing → PDF extraction → Browser automation → OCR
2. **Adapter parametrizado > Crawler específico.** Mesma família tecnológica = mesmo adapter.
3. **Agregador > Individual.** PNCP cobre todos os entes; DOM-SC cobre ~280 municípios. Priorizar.
4. **Fail-closed, nunca fail-silent.** Zero resultados deve ser investigado, não aceito.

### Ordem de prioridade por fonte

| Prioridade | Fonte | Justificativa | Ganho marginal |
|------------|-------|---------------|----------------|
| P0 | PNCP (editais + contratos) | Única fonte funcionando, maior cobertura potencial | +35% recall |
| P1 | DOM-SC | ~280 municípios SC, já implementado, API funcional | +15% recall |
| P2 | PCP/TCE-SC expandido | ~100+ municípios, API pública, crawl_by_municipio() existe | +10% recall |
| P3 | Portais transparência (Betha/IPM) | 231 municípios sem detecção, adapter reutilizável | +15% recall |
| P4 | DOE-SC | 513 entes estaduais, API funcional mas requer auth | +5% recall |
| P5 | Compras.gov.br | Órgãos federais em SC | +3% recall |
| P6 | CIGA CKAN | Dados agregados, atualmente stale (até Dez/2025) | +2% recall |

---

## 2. Arquitetura-Alvo

```
┌─────────────────────────────────────────────────────────┐
│                   SOURCES (8+)                          │
│  PNCP │ DOM-SC │ PCP │ DOE-SC │ ComprasGov │ TCE-SC    │
│  SC Compras │ Transparência (Betha/IPM/e-Gov)           │
└──────────┬──────────────────────────────────────────────┘
           │ CrawlerProtocol.fetch(mode)
           ▼
┌─────────────────────────────────────────────────────────┐
│              RAW ZONE (novo)                            │
│  raw_data JSONB ─ source, fetched_at, content_hash,     │
│  raw_payload, http_status, headers                      │
└──────────┬──────────────────────────────────────────────┘
           │ Transformer.normalize(raw) → canonical
           ▼
┌─────────────────────────────────────────────────────────┐
│           CANONICAL ZONE (PostgreSQL)                   │
│  pncp_raw_bids │ pncp_supplier_contracts               │
│  pncp_opportunities │ pncp_raw_atas │ pncp_raw_pca     │
└──────────┬──────────────────────────────────────────────┘
           │ DedupEngine (cross-source)
           ▼
┌─────────────────────────────────────────────────────────┐
│           PRESENTATION LAYER                            │
│  CLI │ Briefing PDF │ Manifest JSON │ CSV exports       │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Interfaces de Crawler (Pós-Unificação)

Meta: convergir 3 paradigmas → 1 interface canônica.

```python
class CrawlerProtocol(Protocol):
    """Interface canônica para todos os crawlers."""
    source: str
    def crawl(self, request: CrawlRequest) -> list[dict]: ...
    def transform(self, records: list[dict]) -> list[dict]: ...
    def health_check(self) -> SourceHealth: ...
```

`CrawlRequest` unificado:
```python
@dataclass
class CrawlRequest:
    mode: Literal["full", "incremental", "backfill"]
    date_start: date | None = None
    date_end: date | None = None
    uf: str = "SC"
    max_pages: int = 200
    page_size: int = 50
```

---

## 4. Raw Zone (Desenho)

Cada registro bruto preservado em `raw_data`:

```sql
CREATE TABLE raw_data (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT,              -- ID na fonte (pncp_id, etc.)
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_payload JSONB NOT NULL,  -- resposta original completa
    content_hash TEXT NOT NULL,  -- SHA-256 do payload
    http_status INTEGER,
    headers JSONB,
    crawl_batch_id TEXT,
    error_message TEXT
);
CREATE INDEX ON raw_data(source, fetched_at);
CREATE INDEX ON raw_data(source_id) WHERE source_id IS NOT NULL;
```

---

## 5. Deduplicação Cross-Source

Ordem determinística (4 níveis):

1. **ID oficial da fonte** (pncp_id, dom_sc_id, etc.)
2. **Número PNCP** (se disponível na fonte)
3. **Órgão + processo + edital** (normalizados: sem pontuação, lowercase, zeros à esquerda removidos)
4. **Hash canônico** (SHA-256 de: modalidade + objeto_normalizado + orgao_raiz + data_publicacao + valor_total)

Hash Level 3 e 4 incluem normalização:
- Número edital: strip zeros, espaço único
- Órgão: CNPJ raiz (8 dígitos)
- Objeto: lowercase, strip, normalize whitespace

---

## 6. Resiliência

| Mecanismo | Estado atual | Estado-alvo |
|-----------|-------------|-------------|
| Circuit breaker | STUB (is_degraded=False) | 5 falhas → open, 30s half-open |
| Rate limiter | Redis+local (PNCP only) | Por domínio, todos os crawlers |
| Retry | Exponential backoff, 3 retries | Manter, adicionar jitter |
| Checkpoint | Data-based | Page-level + data-based |
| Lock distribuído | Inexistente | Advisory lock PostgreSQL |
| Zero anômalo | Não detectado | Gate: avg_histórica > 0 ∧ atual = 0 → alerta |

---

## 7. Famílias Tecnológicas de Portais

| Família | Tecnologia | Método | Municípios estimados |
|---------|-----------|--------|---------------------|
| Betha / Atende.Net | Angular SPA + API JSON interna | Reverse-engineer API JSON | ~120 |
| IPM Sistemas | ASP.NET + DataTables | HTML parsing + XHR | ~50 |
| e-Gov / Pública | WordPress + plugins | RSS/API REST | ~30 |
| Elotech | JavaServer Faces | HTML parsing | ~15 |
| Fly Transparência | React SPA | API JSON interna | ~10 |
| GovBR | Plataforma gov.br | API REST | ~5 |
| Genérico (outros) | Diversos | Selenium/Playwright fallback | ~65 |

---

## 8. Plano de Execução

### Fase 1: Unificar (CM-06, CM-09)
- interface CrawlerProtocol como caminho canônico
- Raw zone para PNCP + DOM-SC
- Circuit breaker real

### Fase 2: Expandir (CM-07, CM-08, CM-10)
- DOM-SC com execução real
- TCE-SC expandido para municípios
- Betha adapter (maior família, ~120 municípios)

### Fase 3: Completar (CM-11, CM-12)
- IPM adapter
- Anexos e PDFs
- OCR para documentos escaneados (apenas se indispensável)

---

*Source Acquisition Strategy v1.0 — 2026-07-15*
