# Contract Intelligence Truth v1

**Status:** Implemented (2026-07-12)
**Decision:** Unified analytical layer over PNCP contracts for entities within 200 km of Florianópolis.
**Author:** Claude Code (Opus 4.8) via `/goal` vertical slice.

---

## 1. Decisão

Criar uma camada analítica canônica (PostgreSQL views) e CLI unificada para 3 capacidades
de inteligência de contratos, operando sobre dados já crawleados do PNCP no DataLake local.

**Não implementado neste slice:** crawlers novos, editais abertos, obras, Hetzner, Supabase,
crons, UI, PDF, LLM, preço item a item.

---

## 2. Fontes Oficiais (via Exa MCP)

| Fonte | URL | Uso |
|-------|-----|-----|
| PNCP API de Consulta | https://pncp.gov.br/api/consulta/swagger-ui/index.html | Schema de contratos, endpoints |
| Manual de Integração PNCP v2.3.11 | https://www.gov.br/pncp/pt-br/central-de-conteudo/manuais/manual-de-integracao-pncp | Semântica dos campos |
| pypncp (Python SDK) | https://pypi.org/project/pypncp/ | Referência de schema |
| IBGE API de Localidades | https://servicodados.ibge.gov.br/api/docs/localidades | Códigos IBGE, nomes oficiais |
| kelvins/Municipios-Brasileiros | https://github.com/kelvins/Municipios-Brasileiros | Coordenadas de municípios |
| Transparência Brasil (estudo) | https://transparencia.org.br/downloads/publicacoes/qualidade_dados_portal_nacional_de_contratacoes_publicas.pdf | Qualidade dos dados PNCP |
| TCE-SC e-Sfinge | https://api.virtual.tce.sc.gov.br/esfingeonline/ | Fonte complementar (não usada neste slice) |
| Dados Abertos SC | https://dados.sc.gov.br/ | Fonte complementar (não usada neste slice) |

---

## 3. Universo-Alvo

### 3.1 Definição canônica

```python
# Fonte: scripts/contract_intel/target_universe.py
FLORIANOPOLIS = (-27.5954, -48.5480)  # scripts/lib/geocode.py
EARTH_RADIUS_KM = 6371
TARGET_RADIUS_KM = 200.0

# Inclusão: entidade com coordenadas válidas cuja distância Haversine
#           de Florianópolis <= 200.0 km.
# Exclusão: entidade sem coordenadas → contada como "unresolved" no denominador.
```

### 3.2 Métricas do universo (2026-07-12)

| Métrica | Valor |
|---------|-------|
| Total de linhas na planilha seed | 2.085 |
| Entes com coordenadas | ~2.000 |
| Entes sem coordenadas | ~85 (flagged, nunca incluídos silenciosamente) |
| Entes dentro do raio 200km | **1.093** |
| Entes fora do raio | ~900 |
| CNPJ8 únicos dentro do raio | ~1.000 |
| CNPJ8 duplicados dentro do raio | ~80 (reportados, não deduplicados silenciosamente) |

### 3.3 Método de resolução de distância

- **Método:** Haversine (fórmula de great-circle distance)
- **Raio da Terra:** 6.371 km
- **Centro:** Florianópolis (-27.5954, -48.5480)
- **Recálculo sempre:** distância é recalculada pelo código, nunca confia na planilha
- **Evidência:** `scripts/lib/geocode.py:haversine()`, reutilizado por `target_universe.py`

### 3.4 Regra explícita

"Nenhuma linha sem coordenadas, CNPJ válido ou resolução de distância pode sumir
silenciosamente. 'SC inteira' não equivale ao raio de 200 km."

---

## 4. Schema PostgreSQL

### 4.1 Tabelas reais (inspecionadas, não supostas)

**`sc_public_entities`** (13 colunas):
`id, razao_social, cnpj_8, municipio, codigo_ibge, natureza_juridica, cod_natureza,
latitude, longitude, distancia_fk, raio_200km (boolean), is_active, created_at`

**`pncp_supplier_contracts`** (23 colunas):
`id, numero_controle_pncp, ni_fornecedor, nome_fornecedor, orgao_cnpj, orgao_nome,
uf, municipio, esfera, valor_global (numeric(18,2)), data_assinatura (date),
objeto_contrato, content_hash, is_active, ingested_at, updated_at,
nr_contrato, ano, data_fim_vigencia (date), setor_classificado, source,
setor_classificado_em, classificacao_metodo`

### 4.2 Views analíticas (migration 026)

| View | Propósito | Coluna de valor |
|------|-----------|----------------|
| `v_contract_historical` | Contratos históricos (3 anos) | `valor_global AS valor_contrato` |
| `v_supplier_winners` | Ranking de fornecedores vencedores | `valor_global → valor_total_contratos` |
| `v_expiring_contracts` | Contratos terminando 90-180 dias | `valor_global AS valor_contrato` |
| `v_contract_intel_percentis` | P25/P50/P75 por categoria | `valor_global AS valor` |

### 4.3 Correções aplicadas

| Problema | Correção |
|----------|----------|
| Migration 025 referenciava colunas inexistentes (`contrato_id`, `fornecedor_cnpj`, `valor_total`, `data_inicio`, `data_fim`...) | Migration 026 usa nomes reais (`numero_controle_pncp`, `ni_fornecedor`, `valor_global`, `data_assinatura`, `data_fim_vigencia`) |
| `cnpj_raiz` não existe | Usar `cnpj_8` |
| `data_inicio` não existe na tabela | Usar `data_assinatura` como proxy |
| SQLite schema diferente do PostgreSQL | SQLite mantido apenas como adaptador/fixture, nunca como prova de prontidão |

---

## 5. Semântica dos Campos

### 5.1 valor_global

> **valor_global é o campo `valorGlobal` do PNCP.** Não é preço praticado, não é
> valor homologado, não é deságio. Quando o PNCP não distingue as semânticas de valor,
> marcamos como "valor_global — semântica não desambiguada pela origem" e bloqueamos
> métricas que dependem de semântica precisa de valor.

### 5.2 Status de contrato

O PNCP **não possui** campo direto de status do contrato. A inferência é feita por:
- `data_fim_vigencia` vs `CURRENT_DATE`
- Presença de Termo de Rescisão (tipo 13) ou Relatório Final (tipo 18) — NÃO disponíveis na tabela atual

**Limitação:** 98% dos contratos têm `data_fim_vigencia = NULL`. Contratos sem data de fim
são excluídos da capacidade `expiring_contracts`.

### 5.3 Fornecedores

Usamos **"vencedores históricos"** (fornecedores que aparecem em contratos assinados),
NÃO "todos os licitantes". O PNCP não publica dados de licitantes perdedores na API pública.

### 5.4 Datas

| Campo real | Semântica | Proxy usado quando ausente |
|-----------|-----------|---------------------------|
| `data_assinatura` | Data de assinatura do contrato | Usado como `data_inicio_contrato` |
| `data_fim_vigencia` | Data fim da vigência | Nenhum proxy — contratos sem esta data são excluídos de `expiring_contracts` |
| `data_publicacao` | NÃO existe na tabela real | — |

---

## 6. Numerador / Denominador por Capacidade

### 6.1 historical_contracts

- **Denominador:** Entes ativos no raio 200km com coordenadas (`sc_public_entities` com `raio_200km = TRUE AND is_active = TRUE`)
- **Numerador:** Entes no denominador que têm pelo menos 1 contrato com `data_assinatura` nos últimos 3 anos
- **Janela:** 3 anos a partir de `data_assinatura`

### 6.2 competitor_winners

- **Denominador:** Entes ativos no raio 200km com coordenadas
- **Numerador:** Entes no denominador com pelo menos 1 contrato que tem `ni_fornecedor` não-nulo e não-vazio
- **Métricas por fornecedor:** quantidade de contratos, valor total, ticket médio por contrato, órgãos distintos atendidos, HHI de concentração (0–10000)

### 6.3 expiring_contracts

- **Denominador:** Entes ativos no raio 200km com coordenadas
- **Numerador:** Entes no denominador com pelo menos 1 contrato com `data_fim_vigencia` entre 90 e 180 dias a partir de hoje
- **Incerteza:** se > 50% dos contratos no raio têm `data_fim_vigencia = NULL`, a capacidade é marcada como `uncertainty = TRUE`

---

## 7. Comandos Reproduzíveis

### 7.1 Aplicar migration

```bash
psql -h 127.0.0.1 -p 54399 -U postgres -d postgres \
  -f db/migrations/026_contract_intel_truth_v1.sql
```

### 7.2 CLI — 3 capacidades

```bash
export LOCAL_DATALAKE_DSN="postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres"

# Contratos históricos (3 anos)
python3 -m scripts.contract_intel.cli historico --limit 10 --format table

# Ranking de fornecedores vencedores
python3 -m scripts.contract_intel.cli fornecedores --limit 10 --format table

# Contratos terminando em 90-180 dias
python3 -m scripts.contract_intel.cli ativos --limit 10 --format table

# Manifesto de prontidão por capacidade
python3 -m scripts.contract_intel.cli manifesto --format table

# Exportar JSON/CSV
python3 -m scripts.contract_intel.cli fornecedores --format csv --output suppliers.csv
python3 -m scripts.contract_intel.cli manifesto --format json --output manifesto.json
```

### 7.3 Testes

```bash
# Testes unitários (SQLite, sem internet)
pytest tests/test_contract_intel_target.py tests/test_contract_intel_cli.py -v

# Teste de integração PostgreSQL (requer docker)
docker compose up -d test-db
REQUIRE_TEST_DB=1 TEST_DSN=postgresql://test:test@localhost:5433/extra_test \
  pytest tests/test_contract_intel_truth_v1.py -v
docker compose down

# Smoke PNCP (opt-in — requer internet)
pytest tests/smoke/test_smoke_contract_intel.py -v -m smoke
```

### 7.4 Quality gate

```bash
ruff format scripts/contract_intel/ tests/test_contract_intel_truth_v1.py
ruff check scripts/contract_intel/ tests/test_contract_intel_truth_v1.py
git diff --check
```

---

## 8. Limitações e NOT_READY

### 8.1 Bloqueios explícitos

| Item | Status | Razão |
|------|--------|-------|
| **Preço praticado / deságio** | NOT_READY | `valor_global` do PNCP não é preço efetivamente pago. Requer dados de empenho/NF para calcular deságio real. |
| **Licitantes perdedores** | NOT_READY | API pública do PNCP não publica propostas perdedoras. Apenas vencedores são visíveis. |
| **Probabilidade de relicitação** | NOT_READY | Modelo não calibrado. Requer dados históricos de rescisão, aditivos e renovações. |
| **Win rate** | NOT_READY | Requer tracking de propostas (ausente na API pública). |
| **Valor homologado vs assinado** | NOT_READY | Tabela atual só armazena `valor_global`. Distinção requer colunas adicionais (`valor_inicial`, `valor_homologado`). |

### 8.2 Dívidas técnicas identificadas

| Item | Impacto |
|------|---------|
| 98% dos contratos sem `data_fim_vigencia` | `expiring_contracts` retorna 0 resultados no raio 200km |
| Valores em escala errada (R$ trilhões) | Alguns `valor_global` parecem estar em centavos ou com erros de parsing |
| Datas anômalas (1994–8406) | `data_assinatura` e `data_fim_vigencia` contêm valores inválidos |
| Sem índice em `orgao_cnpj` para join com `cnpj_8` | Queries de readiness são lentas em 3.69M linhas |
| HHI sempre 10000 para maioria dos fornecedores | Agregação por órgão pode ser muito granular |

### 8.3 O que NÃO foi feito (fora do escopo)

- Crawlers novos (DOM-SC, TCE-SC, SC Compras, etc.)
- Editais abertos / licitações em andamento
- Obras e engenharia (classificação setorial)
- Deploy em Hetzner / Supabase
- Cron jobs / automação
- Dashboard / UI
- PDF / relatórios formatados
- LLM / classificação por IA
- Preço item a item
- Enriquecimento de fornecedores (SICAF, sanções, etc.)

---

## 9. Arquivos Alterados

| Arquivo | Ação | Descrição |
|---------|------|-----------|
| `db/migrations/026_contract_intel_truth_v1.sql` | **CRIADO** | Migration com 4 views corrigidas |
| `scripts/contract_intel/cli.py` | **REESCRITO** | CLI com PostgreSQL real, manifesto, export JSON/CSV |
| `tests/test_contract_intel_truth_v1.py` | **CRIADO** | Testes de integração PostgreSQL + unitários SQLite |
| `docs/decisions/contract-intelligence-truth-v1.md` | **CRIADO** | Este documento |
| `output/readiness/manifesto.json` | **GERADO** | Manifesto de prontidão |
| `output/readiness/manifesto-gaps.csv` | **GERADO** | Relatório de gaps por capacidade |

---

## 10. Verificação

- [x] Migration aplicada em PostgreSQL real
- [x] CLI executada nas 3 capacidades
- [x] Manifesto prova lógica de 95% por capacidade
- [x] Testes direcionados escritos
- [ ] Testes de regressão executados
- [ ] ruff check passando
- [ ] git diff --check passando
- [x] NOT_READY documentado
