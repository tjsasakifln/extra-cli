# CONFENGE — Universo nacional de construção/engenharia B2G

## Objetivo

Produzir a entidade canônica por **grupo econômico operacional** de empresas
**privadas** de construção/engenharia que atuam em contratos públicos, para
alimentar outreach da CONFENGE em **escala nacional**.

## Premissa de produto

O **score NÃO decide** se uma empresa “merece” abordagem. Toda empresa que
pertença legitimamente ao universo-alvo permanece elegível para
pesquisa/outreach. Score, sinais e potencial **apenas ordenam** a fila e
ajudam a escolher ângulo/serviço.

## Fonte canônica

| Dado | Fonte |
|------|--------|
| Contratos públicos | `pncp_supplier_contracts` (datalake) |
| Cadastro (opcional) | `supplier_registry` / company registry |
| Relevância de objeto | `scripts.commercial_leads.contract_relevance` |
| Fit setorial | `scripts.commercial_leads.sector_fit` |
| Corroboração | `scripts.coverage.sector_engineering` |
| Identidade CNPJ | `scripts.company_registry.normalization` + linkage keys |

## CLI

```bash
# Produção — varredura nacional completa (sem Top-N silencioso)
python3 -m scripts.confenge_universe build \
  --out output/confenge_universe \
  --dsn "$LOCAL_DATALAKE_DSN"

# Offline / fixtures
python3 -m scripts.confenge_universe build \
  --out /tmp/universe_out \
  --csv tests/fixtures/confenge_universe/contracts_sample.csv \
  --dnc tests/fixtures/confenge_universe/dnc.txt \
  --as-of 2026-08-01

# Amostra diagnóstica (NÃO é prova full-scale)
python3 -m scripts.confenge_universe build \
  --out output/confenge_universe_sample \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --max-rows 50000
```

### Saídas

- `confenge-universe-v1.jsonl` — uma linha por entidade canônica
- `confenge-universe-manifest-v1.json` — `as_of`, hash/versão da fonte, repo SHA,
  contagens e reconciliação `input = eligibles + exclusions`

## Campos principais (JSONL)

- Identidade: `cnpj14`, `cnpj_root`, `razao_social`, `nome_fantasia`, UF/município, situação
- Evidência B2G construção: `construction_evidence`
- Carteira: `portfolio` (agregada + recente, órgãos, UFs, categorias, amostra de contratos)
- Sinais temporais: `temporal_signals` (observacionais — **não** inventam atraso/reajuste/Lei 14.133)
- `priority_score` / `priority_reason` — **somente ordenação**
- `outreach_eligibility`: `ELIGIBLE` | `DNC` | `INVALID_IDENTITY` | `NOT_CONSTRUCTION` | …

## Dedupe

Por padrão, matriz/filiais colapsam no **CNPJ raiz**. Aliases e estabelecimentos
são retidos. Exceção de marca decisória independente só com evidência de nomes
fortemente divergentes + atividade de construção em ambos.

## Invariantes

1. Contrato grande ≠ lead bom; só contexto.
2. Empresa nacional robusta **permanece** no universo.
3. Volume/valor/anualidade isolados não são vendidos como “dor”.
4. Não inventar Lei 14.133, reajuste, reequilíbrio ou atraso sem evidência.
5. DNC humano prevalece para outreach (estado `DNC`), sem apagar do universo de pesquisa.
6. Nenhum subset silencioso como verdade de produção.

## Composição com o motor CONFENGE

Este universo é a **população nacional** de alvos de construção B2G. Filas
comerciais (`commercial_leads`, reajuste 14.133, Top-N operacionais) **consomem
e ordenam** subconjuntos para campanhas específicas; não substituem este
universo. Score de prioridade aqui alimenta ordenação inicial; sinais de campanha
mais finos continuam nos funis especializados.

## Memória limitada

Leitura por **keyset** (`contrato_id`) em lotes; agregação incremental por
entidade; amostra limitada de contratos recentes. Testes de escala sintética
≥250k linhas verificam ausência de materialização gigante do stream.
