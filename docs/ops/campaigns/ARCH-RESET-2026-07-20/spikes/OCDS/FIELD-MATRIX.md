# Local model → OCDS 1.1.5 field matrix (spike)

**Decision target:** `ADOPT_AS_REFERENCE` / export layer — **not** physical PostgreSQL model.  
**Baseline:** main `d6d9e19` · bridge `scripts/ocds_bridge/mapping.py`

| # | Local field / concept | OCDS path | Cardinality | Notes / BR gap |
|--:|-----------------------|-----------|-------------|----------------|
| 1 | `numero_controle_pncp` | `ocid` / `tender.id` / `extra:provenance.official_id` | 1 | PNCP control number as official id |
| 2 | `id` (internal) | `id` | 1 | Internal surrogate not OCDS-stable |
| 3 | `data_publicacao_pncp` | `date` | 0..1 | Publication, not always award date |
| 4 | release kind tender | `tag[]=tender` | 1 | |
| 5 | procurement initiation | `initiationType=tender` | 1 | |
| 6 | `objeto_compra` | `tender.title` | 0..1 | Description often longer than title |
| 7 | `situacao_nome` | `tender.status` | 0..1 | Local vocab ≠ OCDS status enum |
| 8 | `valor_total_estimado` | `tender.value.amount` | 0..1 | Estimated, not awarded |
| 9 | `moeda` | `tender.value.currency` | 0..1 | Default BRL |
| 10 | `modalidade_nome` | `tender.procurementMethodDetails` | 0..1 | Not mapped to open/selective/limited |
| 11 | `orgao_cnpj` | `buyer.id` as `BR-CNPJ-*` | 0..1 | Party scheme local |
| 12 | `orgao_nome` | `buyer.name` | 0..1 | |
| 13 | buyer role | `buyer` object | 1 | procuringEntity often same as buyer in BR portals |
| 14 | `content_hash` | `extra:provenance.content_hash` | 0..1 | Extension field |
| 15 | `raw_uri` | `extra:provenance.raw_uri` | 0..1 | Extension |
| 16 | source system | `extra:provenance.source` | 1 | pncp / pncp_contracts |
| 17 | `contrato_id` | `contracts[].id` / `ocid` | 1 | |
| 18 | `objeto_contrato` | `contracts[].title` | 0..1 | |
| 19 | `situacao` (contrato) | `contracts[].status` | 0..1 | Local vocab |
| 20 | `valor_global`/`valor_total` | `contracts[].value.amount` | 0..1 | **Not paid** |
| 21 | value semantics paid? | `extra:value_semantics.is_paid=false` | 1 | Fail-closed: contracted ≠ paid |
| 22 | `data_assinatura` | `contracts[].dateSigned` | 0..1 | |
| 23 | `data_vigencia_inicio` | `contracts[].period.startDate` | 0..1 | |
| 24 | `data_vigencia_fim` | `contracts[].period.endDate` | 0..1 | |
| 25 | `orgao_cnpj` (contract) | `parties[role=buyer].id` | 0..1 | |
| 26 | `fornecedor_cnpj` | `parties[role=supplier].id` | 0..1 | |
| 27 | `fornecedor_nome` | `parties[role=supplier].name` | 0..1 | |
| 28 | `numero_controle_pncp_compra` | `extra:provenance.linked_tender_id` | 0..1 | Link tender↔contract |
| 29 | award amount | `awards[].value` | — | **Not mapped yet** (gap) |
| 30 | award supplier | `awards[].suppliers` | — | **Not mapped yet** (gap) |
| 31 | documents / PDF URI | `tender.documents[]` | — | **Not mapped yet** (gap) |
| 32 | items / lots | `tender.items[]` / `lots[]` | — | **Not mapped yet** (gap) |
| 33 | amendments / aditivos | `contracts[].amendments` | — | **Not mapped yet** (gap) |
| 34 | implementation / payments | `contracts[].implementation` | — | Out of scope (no physical works) |
| 35 | IBGE municipality | party address | — | Local enrichment, not OCDS core |
| 36 | universe 1093 entity | — | — | Project-specific; not OCDS entity |

**Counted critical mappings present:** 28 rows with mapping path · **gaps:** awards, documents, items/lots, amendments.

## Brazilian localization notes

- Status vocabularies from PNCP do not match OCDS `tender.status` enums → keep local status + map optionally later.
- CNPJ party ids use local scheme `BR-CNPJ-*` (not fully registered org-id scheme).
- Extensions under `extra:*` are intentional and will **fail strict OCDS schema** unless packaged as OCDS extension.
