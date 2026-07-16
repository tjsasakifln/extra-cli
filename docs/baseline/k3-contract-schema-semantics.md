# K3 — Schema e semântica canônica de contratos

**Story:** PE-K3-01  
**Data:** 2026-07-16  
**Objetivo:** fechar inventário de tabelas/colunas e semântica estimado / homologado / contratado / pago; listar divergências schema×código com severidade.

---

## 1. Tabelas e artefatos principais

| Artefato | Tipo | Papel | Migration(s) chave |
|----------|------|-------|--------------------|
| `pncp_supplier_contracts` | tabela física | Fatos de contratos (PNCP + fontes) | `002`, `013` (`is_active`), `021c` (IBGE), `033` versioning |
| `contract_version_history` | tabela | Histórico de mudanças de contrato | `033_contract_versioning.sql` |
| `pncp_raw_bids` | tabela | Editais / valores estimados | `001`, `023` |
| `opportunity_intel` | tabela | Oportunidades unificadas (estimado + homologado + `valor_semantica`) | `027`, `029` |
| `coverage_evidence` | ledger | Prova de cobertura (incl. capability contracts) | `024`–`029`, `040` |
| `entity_coverage` | tabela | Agregado por entidade/fonte (flags/contagens) | `009`, `012`, `021a`, `022` |
| `v_contracts_canonical` | view canônica | Contrato estável para consumers | `030` |
| `v_contract_historical` | view analítica | Contratos 3 anos no raio 200 km | `025a` / `026` |
| `v_supplier_winners` | view | Ranking de vencedores | `025a` / `026` |
| `v_expiring_contracts` | view | Janela 90–180 dias fim de vigência | `025a` / `026` |
| `v_value_observations_canonical` | view | Observações de valor bid+contrato | `030` |
| `v_coverage_manifest` | view | Cobertura por capability×source | `040` |
| `scripts/lib/value_semantics.py` | Python | Enum e mapeamento semântico | N/A (código) |

---

## 2. Colunas de valor e datas — inventário

### 2.1 `pncp_supplier_contracts` (declaração migration 002)

| Coluna (002) | Tipo | Uso declarado |
|--------------|------|---------------|
| `contrato_id` | TEXT UNIQUE | ID externo |
| `orgao_cnpj` / `orgao_nome` | TEXT | Órgão contratante |
| `fornecedor_cnpj` / `fornecedor_nome` | TEXT | Fornecedor |
| `objeto_contrato` | TEXT | Objeto |
| **`valor_total`** | NUMERIC(18,2) | Valor do contrato (nome legado na migration) |
| `data_inicio` / `data_fim` | DATE | Vigência (nomes legados) |
| `data_publicacao` | DATE | Publicação |
| `uf` / `municipio` | TEXT | Local |
| `source` / `source_id` | TEXT | Proveniência |
| `ingested_at` | TIMESTAMPTZ | Ingestão |

Colunas adicionadas depois:

| Coluna | Migration | Nota |
|--------|-----------|------|
| `is_active` | 013 | Soft delete / filtro de ativos |
| `codigo_municipio_ibge` | 021c | Match geográfico |
| `municipio_inferido` | 021c | Flag de inferência |

### 2.2 Drift documentado na migration 026 (produção real vs 002)

A migration `026_contract_intel_truth_v1.sql` documenta que o PostgreSQL real (em algum momento) usava:

| Nome “real” citado em 026 | Nome em 002 / views |
|---------------------------|---------------------|
| `numero_controle_pncp` | `contrato_id` |
| `ni_fornecedor` | `fornecedor_cnpj` |
| `nome_fornecedor` | `fornecedor_nome` |
| **`valor_global`** | **`valor_total`** |
| `data_assinatura` | `data_inicio` |
| `data_fim_vigencia` | `data_fim` |
| (sem `data_publicacao`) | `data_publicacao` existe no 002 |

**Importante:** as views em 026/025a/030 no repositório **ainda referenciam** `valor_total`, `contrato_id`, `fornecedor_cnpj`, `data_inicio`, `data_fim` — ou seja, o **código versionado das views assume o schema 002-style**, enquanto o **comentário 026** alerta para drift de produção. Isso é a divergência central K3.

### 2.3 Editais (`pncp_raw_bids`)

| Coluna | Semântica |
|--------|-----------|
| `valor_total_estimado` | **Valor estimado** do edital (PNCP) |
| `data_publicacao` / `data_abertura` / `data_encerramento` | Ciclo do edital |

### 2.4 `opportunity_intel` (027)

| Coluna | Semântica |
|--------|-----------|
| `valor_estimado` | Estimado |
| `valor_homologado` | Homologado (quando fonte fornece) |
| `valor_semantica` | Label textual da semântica aplicada |
| `data_homologacao` | Data do resultado |

### 2.5 View canônica de contratos (`v_contracts_canonical`, 030)

Expõe: `contrato_id`, `valor` (= `c.valor_total`), datas `data_inicio`/`data_fim`/`data_publicacao`, órgão/fornecedor, entity match por `LEFT(fornecedor_cnpj,8)` — **nota:** join por fornecedor, não por órgão (semântica de “supplier contracts”).

### 2.6 Observações de valor (`v_value_observations_canonical`, 030)

- Bids: `valor_total_estimado` → `valor`, type `bid`.
- Contracts: usa `valor_total` na continuação da view (observação de valor contratual).

---

## 3. Semântica canônica de valores

### 3.1 Ciclo de vida (código canônico)

Fonte: `scripts/lib/value_semantics.py`

| Enum | Label | Estágio | Fonte típica |
|------|-------|---------|--------------|
| `ESTIMADO` | valor_estimado | Edital — o que o ente espera pagar | PNCP bids → `valor_total_estimado` |
| `HOMOLOGADO` | valor_homologado | Resultado / adjudicação | ComprasGov (ainda pouco/nulo no lake) |
| `CONTRATADO` | valor_contratado | Contrato assinado | PNCP contracts → coluna física `valor_global` **mapeada** como contratado |
| `PAGO` | valor_pago | Empenho / desembolso real | TCE/SC (ainda não ingerido de forma plena) |
| `GLOBAL` | valor_global | Total indiferenciado PNCP | **não** é “preço praticado” |

Mapeamento oficial no código:

```text
SOURCE_VALUE_TYPES["pncp"]["bids"]      = ESTIMADO
SOURCE_VALUE_TYPES["pncp"]["contracts"] = CONTRATADO  # via valor_global
SOURCE_VALUE_TYPES["compras_gov"]["bids"] = HOMOLOGADO
SOURCE_VALUE_TYPES["tce_sc"]["contracts"] = PAGO
```

`coluna_para_semantica`:

| Coluna DB | Semântica |
|-----------|-----------|
| `valor_total_estimado`, `valor_estimado` | ESTIMADO |
| `valor_homologado` | HOMOLOGADO |
| `valor_global` | CONTRATADO |
| `valor_pago` | PAGO |
| `valor_total` | **não** está no mapping → “semântica não classificada” se usado cru |

### 3.2 O que NÃO se pode alegar

Documentado em `value_semantics.py`, `consulting_readiness._compute_contract_value_aggregation` e comentários da 026:

| Alegação | Permitida? | Motivo |
|----------|------------|--------|
| `valor_global` / contratado = “preço praticado” | **Não** | Não reflete pagamentos parciais, aditivos, rescisões |
| deságio item-a-item estimado→homologado com só PNCP | **Não** (sem linkage) | PNCP não liga item de edital a item de contrato de forma confiável no lake |
| diferencial entidade (avg estimado vs avg contratado) | **Sim, com disclaimer** | `entity_price_differential` — média populacional, **não** deságio real |
| valor pago | **Só com TCE/empenho** | ainda incompleto |

### 3.3 Deságio

Funções:

- `calculate_desagio(estimado, homologado_ou_contratado)`
- `compute_bid_contract_desagio(estimado, valor_global_contrato)` → semantica `estimado→contratado`

Uso correto: sempre rotular a transição (`estimado→homologado` vs `estimado→contratado`).

---

## 4. Código consumidor (amostra)

| Consumer | Coluna de valor usada | Risco |
|----------|----------------------|-------|
| `scripts/lib/value_semantics.py` | `valor_global` (canônico) | Alinha com 026-real |
| `consulting_readiness._compute_contract_value_aggregation` | `c.valor_global` | Quebra se DB só tiver `valor_total` |
| `scripts/buyer_intel/cli.py` | `c.valor_total` | Quebra se DB só tiver `valor_global` |
| Views 025a/026/030 | `c.valor_total` | Dependem do schema 002-style |
| `v_contracts_canonical` | alias `valor` ← `valor_total` | Idem |
| upsert RPC 006 | `valor_total` no JSON | Schema 002 |

---

## 5. Divergências schema × código (severidade)

| ID | Severidade | Divergência | Evidência |
|----|------------|-------------|-----------|
| K3-D1 | **P0** | Nome da coluna de valor: `valor_total` (migrations 002/views/buyer_intel) vs `valor_global` (value_semantics, consulting_readiness, comentário 026) | Paths acima |
| K3-D2 | **P0** | Identidade do contrato: `contrato_id` vs `numero_controle_pncp` documentados como alternativos | 026 header vs 002/030 |
| K3-D3 | **P1** | Datas de vigência: `data_inicio`/`data_fim` vs `data_assinatura`/`data_fim_vigencia` | 026 header vs views |
| K3-D4 | **P1** | Fornecedor: `fornecedor_cnpj` vs `ni_fornecedor` | 026 |
| K3-D5 | **P1** | Comentário da view 026 diz “Value column is valor_global” mas o SELECT usa `c.valor_total AS valor_contrato` | inconsistência **dentro** do mesmo arquivo SQL |
| K3-D6 | **P1** | `coluna_para_semantica("valor_total")` retorna `None` enquanto muitas queries usam `valor_total` | value_semantics vs buyers |
| K3-D7 | **P2** | `v_contracts_canonical` faz JOIN entity pelo **fornecedor**, não pelo órgão — adequado a “supplier intel”, inadequado se o consumer espera “contratos do ente comprador” | 030 |
| K3-D8 | **P2** | Homologado e pago ainda sem pipeline completo no lake | opportunity_intel colunas existem; ComprasGov/TCE “not yet ingested” no value_semantics |
| K3-D9 | **P2** | Freshness gate filtra `pncp_supplier_contracts` com `data_source='pncp_contracts'` se coluna `source` existir — precisa bater com valores reais de `source` na base | `freshness_gate.py` CRITICAL_SOURCES |

---

## 6. Semântica canônica recomendada (contrato de dados)

Até unificação física (story de schema HIGH-RISK), o **contrato lógico** a usar em docs e novos códigos:

| Conceito de negócio | Preferência de coluna | Semântica (`ValorSemantica`) | Fonte |
|---------------------|----------------------|------------------------------|-------|
| Valor estimado do edital | `pncp_raw_bids.valor_total_estimado` | ESTIMADO | PNCP |
| Valor homologado | `opportunity_intel.valor_homologado` / ComprasGov | HOMOLOGADO | complementar |
| Valor contratado (assinado) | preferir **`valor_global`** se existir; senão `valor_total` **com alias documentado** | CONTRATADO | PNCP contratos |
| Valor pago | empenho TCE / futuro `valor_pago` | PAGO | TCE/SC |
| Preço praticado | **não disponível** como coluna única PNCP | — | proibido no discurso comercial |

**Regra de ouro:** todo relatório deve carregar `valor_semantica` ou o enum equivalente; nunca rotular `valor_global` como pago ou homologado.

---

## 7. AC PE-K3-01

| AC | Entrega |
|----|---------|
| 1. Listar tabelas/colunas e semântica estimado/homologado/contratado/pago | §§1–3 deste documento |
| 2. Divergências schema×código com severidade | §5 (K3-D1…D9) |

**Não alterado nesta story:** migrations/código de unificação de colunas (exige @architect + @data-engineer, HIGH-RISK, testes de view/upsert).

---

## 8. Follow-ups prioritários

1. **P0:** inventário real `information_schema` em cada ambiente (local/VPS) e ADR de nome canônico (`valor_global` vs `valor_total`).  
2. **P0:** views 025–030 e consumers Python alinhados a **um** nome físico; ou views que `COALESCE`/renomeiam.  
3. **P1:** estender `coluna_para_semantica` com alias `valor_total` → CONTRATADO (mudança pequena e testável — candidata a story FAST/STANDARD se consensus de semântica).  
4. **P1:** pipeline homologado (ComprasGov) e pago (TCE) para fechar o ciclo de 4 estágios.  
5. **P2:** documentar join órgão vs fornecedor nas views canônicas no contrato Story 1.2.
