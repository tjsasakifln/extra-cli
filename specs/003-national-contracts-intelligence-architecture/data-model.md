# Data Model — National Contracts Intelligence

## Entities

### 1. National contract fact (existing)

**Table:** `public.pncp_supplier_contracts`

| Field | Role |
|-------|------|
| `contrato_id` | Natural key (unique) |
| `orgao_cnpj`, `orgao_nome`, `orgao_cnpj_8` | Buyer identity |
| `fornecedor_cnpj`, `fornecedor_nome`, `fornecedor_cnpj_8` | Supplier identity |
| `objeto_contrato` | Object text |
| `valor_total` | Global contracted value (not unit price) |
| `uf`, `municipio` | Geography (may be null → unknown_uf) |
| `data_*`, `source_event_date`, windows | Temporal / provenance |
| `source`, `ingested_at`, `first_seen_at`, `last_seen_at` | Lineage |
| `is_active` | Soft presence |

**Validation:** Intelligence products count `is_active = true` unless noted.

### 2. Scope stamp (logical)

Not a table — embedded in views as constants and in JSON `scope_label`:

- `raw_national`
- `geo_sc`
- `intel_product`
- `canonical_sc_operational` (dual engine only)

### 3. Views (migration 059)

#### `v_intel_contracts_raw_national`

All active contracts + `scope_label = 'raw_national'`.

#### `v_intel_contracts_geo_sc`

Active contracts with `upper(uf) = 'SC'` + `scope_label = 'geo_sc'`.

#### `v_intel_supplier_geo`

Grain: `fornecedor_cnpj_8` (fallback nome hash if cnpj null).

| Column | Meaning | claim_class |
|--------|---------|-------------|
| supplier keys/names | identity | fact |
| ufs[] / uf_count | distinct UFs with contracts | fact |
| contract_count | count | fact |
| valor_sum / valor_p50 | value aggregates | fact/indicator |
| has_sc | bool UF SC present | fact |
| multi_uf | uf_count > 1 | fact |

#### `v_intel_agency_profile`

Grain: `orgao_cnpj_8` / orgao.

| Column | Meaning | claim_class |
|--------|---------|-------------|
| agency identity | | fact |
| contract_count, valor_sum | | fact |
| uf_mode | most common UF | indicator |
| supplier_count | distinct suppliers | fact |
| top concentration share | max supplier share | indicator |

### 4. Operational coverage (unchanged)

| Object | Role |
|--------|------|
| Canonical universe seed | U membership |
| `coverage_evidence` | per-entity source states |
| dual engine | A_C / N_C / gates |

**Relationship:** No FK from national contracts into U. Soft CNPJ match is diagnostic only.

### 5. Product run (output artifact)

JSON envelope per `contracts/product-output.schema.json`.

## State / transitions

National contract rows: crawler-owned (`is_active`, last_seen). Intelligence layer is read-only.

Coverage states: owned by dual/evidence writers — **out of mutation scope** for this feature.

## Indexes (recommendation only for V1)

Existing: UF+data, fornecedor, orgao, valor, GIN objeto, cnpj_8.  
Deferred: composite analytical indexes until after HC backfill / on isolated restore.
