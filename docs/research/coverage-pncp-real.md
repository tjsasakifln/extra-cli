# Relatório de Cobertura Real do PNCP

**Data:** 2026-07-11
**Executor:** @analyst (AIOX)
**Story:** FEAT-0.1 — Validar Cobertura Real do PNCP
**Epic:** EPIC-FEAT-001 — Crawlers de Cobertura

---

## Resumo Executivo

O PNCP (Portal Nacional de Contratações Públicas) **cobre apenas 8.2% das entidades públicas de Santa Catarina dentro do raio de 200km de Florianópolis**. Com 1.003 de 1.093 entidades descobertas, o gap de cobertura é massivo e exige a implementação de TODOS os crawlers planejados nas Fases 1-2.

---

## Metodologia

### Parâmetros do Crawl

| Parâmetro | Valor |
|-----------|-------|
| UFs consultadas | SC, PR, RS |
| Modalidades | 4 (Concorrência), 5 (Pregão Eletrônico), 6 (Concurso), 7 (Dispensa) |
| Período | 30 dias (2026-06-11 a 2026-07-11) |
| Máx. páginas por consulta | 20 |
| Total de entidades SC ativas | 2.085 |
| Entidades no raio 200km | 1.093 |

### Correção de API

Durante a execução, foi identificado que a URL base da API do PNCP foi alterada:

| Antes | Depois |
|-------|--------|
| `https://pncp.gov.br/api/consulta/v1` | `https://pncp.gov.br/pncp-consulta/v1` |

A variável de ambiente `PNCP_BASE` foi utilizada para sobrepor o valor padrão. O bug afeta todos os crawlers que usam a URL antiga (`adapter.py`, `async_client.py`, `pncp_pca_crawler.py`, `pncp_arp_crawler.py`, `sync_client.py`, `contracts_crawler.py`).

### Melhoria de Performance

O crawler original usa consultas dia-a-dia (30 dias × 12 combinações UF/mod = 360+ chamadas). Para este crawl, foi implementada consulta por **blocos semanais**, reduzindo as chamadas de API para 60 e o tempo total de ~30min para ~5min.

---

## Resultados do Crawl

### Dados Brutos

| Métrica | Valor |
|---------|-------|
| Registros brutos obtidos da API | 1.463 |
| Registros transformados e upsertados | 1.463 |
| Bids correspondidos (matched) | 528 |
| Entidades únicas cobertas pelo PNCP | 214 |

### Distribuição por Modalidade

| Modalidade | Bids | Matched | % Match |
|------------|------|---------|---------|
| 4 — Concorrência | 598 | 230 | 38.5% |
| 5 — Pregão Eletrônico | 82 | 19 | 23.2% |
| 6 — Concurso | 600 | 228 | 38.0% |
| 7 — Dispensa | 184 | 51 | 27.7% |
| **Total** | **1.464** | **528** | **36.1%** |

### Distribuição por UF

| UF | Bids | Órgãos distintos |
|----|------|-----------------|
| PR | 458 | 237 |
| RS | 508 | 246 |
| SC | 498 | 223 |

### Métodos de Matching

| Método | Bids | % |
|--------|------|---|
| CNPJ (8 dígitos) | 498 | 94.3% |
| Nome normalizado | 26 | 4.9% |
| Fuzzy | 3 | 0.6% |
| Desconhecido | 1 | 0.2% |

---

## Análise de Cobertura

### Cobertura Geral (todas as fontes)

| Grupo | Total | Cobertas | % Cobertura |
|-------|-------|----------|-------------|
| Raio 200km | 1.093 | 90 | 8.2% |
| Fora raio 200km | 992 | 131 | 13.2% |
| **Total SC** | **2.085** | **221** | **10.6%** |

### Cobertura por Fonte

| Fonte | Entidades cobertas (200km) | Entidades cobertas (total) |
|-------|---------------------------|---------------------------|
| PNCP | 87 | 214 |
| PCP | 4 | 13 |
| Ambas | 1 (overlap) | 6 (overlap) |

### Gap de Cobertura

| Métrica | Valor |
|---------|-------|
| Entidades SC ativas | 2.085 |
| Entidades dentro do raio 200km | 1.093 |
| Cobertas por PNCP (raio 200km) | 87 |
| Cobertas por PCP (raio 200km) | 4 |
| **Descobertas (raio 200km)** | **1.003 (91.8%)** |

---

## Breakdown por Natureza Jurídica (Não Cobertas, Raio 200km)

| Natureza Jurídica | Qtd | % do Gap |
|-------------------|-----|----------|
| Orgao Publico do Poder Executivo Municipal | 179 | 17.8% |
| Fundacao Publica de Direito Publico Municipal | 116 | 11.6% |
| Orgao Publico do Poder Legislativo Municipal | 96 | 9.6% |
| Orgao Publico do Poder Executivo Estadual ou DF | 95 | 9.5% |
| Orgao Publico do Poder Judiciario Estadual | 78 | 7.8% |
| Fundo Publico da Administracao Direta Estadual ou DF | 61 | 6.1% |
| Sociedade de Economia Mista | 58 | 5.8% |
| Autarquia Municipal | 58 | 5.8% |
| Autarquia Federal | 50 | 5.0% |
| Municipio | 40 | 4.0% |
| Consorcio Publico de Direito Publico | 35 | 3.5% |
| Empresa Publica | 31 | 3.1% |
| Autarquia Estadual ou DF | 15 | 1.5% |
| Servico Social Autonomo | 15 | 1.5% |
| Fundacao Publica de Direito Publico Estadual ou DF | 10 | 1.0% |
| Demais (13 tipos) | 66 | 6.6% |
| **Total** | **1.003** | **100%** |

---

## Decisão de Priorização dos Crawlers

Com base no gap real de 91.8% (1.003 entidades descobertas dentro do raio 200km), **NENHUM crawler adicional pode ser depriorizado**. Todos os crawlers planejados para as Fases 1-2 são necessários. A ordem de prioridade recomendada é:

### Prioridade 1 (Alto Impacto) — Fase 1

1. **DOM-SC Crawler** — O Diario Oficial dos Municipios de SC publica atos oficiais de todas as 295 prefeituras e camaras municipais. E a fonte com maior potencial de cobertura para entidades municipais (maioria do gap: 179 orgaos executivos municipais + 116 fundacoes municipais + 96 orgaos legislativos municipais = 391 entidades, 39% do gap).
2. **TCE-SC Crawler** — O Tribunal de Contas de SC possui dados de licitacoes e contratos de todos os orgaos estaduais e municipais. Essencial para os 95 orgaos executivos estaduais e 78 judiciarios.

### Prioridade 2 (Médio Impacto) — Fase 2

3. **ComprasGov Crawler** — Compras federais. Essencial para 50 autarquias federais, 39 orgaos executivos federais e 31 empresas publicas (120 entidades, 12% do gap).
4. **SC Compras Crawler** — Compras estaduais de SC. Focado nos 95 orgaos executivos estaduais.
5. **PCP v2 Crawler (refatoracao)** — O PCP atual ja cobre 13 entidades. A nova versao pode expandir significativamente.

### Estimativa de Impacto

| Fase | Crawlers | Entidades Adicionais Esperadas | Cobertura Projetada |
|------|----------|-------------------------------|-------------------|
| Fase 1 | DOM-SC + TCE-SC | ~400-600 | 45-65% |
| Fase 2 | ComprasGov + SC Compras + PCP v2 | ~200-300 | 65-90% |
| Crawlers especializados | Contracts, Transparencia | ~100-200 | >90% |

---

## Achados Técnicos Adicionais

### 1. API PNCP com URL Alterada

A URL base da API publica do PNCP mudou de `/api/consulta/v1` para `/pncp-consulta/v1`. A API antiga retorna timeout. Todos os crawlers do projeto que usam a URL antiga precisam ser atualizados:

- `scripts/crawl/adapter.py` (linha 53)
- `scripts/crawl/async_client.py` (linha 135)
- `scripts/crawl/pncp_crawler_adapter.py` (linha 33 — overrideable via env var)
- `scripts/crawl/pncp_pca_crawler.py` (linha 52)
- `scripts/crawl/pncp_arp_crawler.py` (linha 53)
- `scripts/crawl/sync_client.py` (linha 45)
- `scripts/crawl/contracts_crawler.py` (linha 42)

### 2. Keyword Filter Limitante

O filtro `_ENGINEERING_KEYWORDS` na linha 43-52 do `pncp_crawler_adapter.py` bloqueia bids que nao contenham palavras-chave de engenharia. Para o coverage assessment, foi necessario desabilitar este filtro via `INGESTION_KEYWORDS`. Isso revela que muitas entidades publicam licitacoes nao-engenharia no PNCP.

### 3. Colunas de Metadados de Matching Ausentes

A tabela `pncp_raw_bids` nao possui as colunas `match_method`, `match_score`, `match_confidence` que o modulo `scripts.matching.entity_matcher` espera. Foram adicionadas via ALTER TABLE para permitir o matching cascade completo.

### 4. Configuracao de Logging Incompativel

O arquivo `config/logging_config.py` usa `datetime.UTC` que nao existe em Python 3.12 (deveria ser `datetime.timezone.utc`). Isso causa logging errors nao-fatais durante a execucao do matching.

---

## Anexos

### Comandos de Reprodução

```bash
# Crawl com URL corrigida
export LOCAL_DATALAKE_DSN="postgresql://postgres@127.0.0.1:5433/pncp_datalake"
export PNCP_BASE="https://pncp.gov.br/pncp-consulta/v1"
export PNCP_MAX_PAGES=20
export INGESTION_UFS="SC,PR,RS"
export INGESTION_MODALIDADES="4,5,6,7"
export INGESTION_DATE_RANGE_DAYS=30
export PNCP_REQUEST_DELAY=0.2
export INGESTION_KEYWORDS="e"

python3 scripts/crawl/_coverage_crawl.py
```

### Queries de Verificação

```sql
-- Total de entidades cobertas
SELECT COUNT(*) FROM entity_coverage WHERE is_covered = TRUE;

-- Entidades no raio 200km sem cobertura
SELECT COUNT(*) FROM sc_public_entities e
WHERE e.is_active = TRUE AND e.raio_200km = TRUE
  AND e.id NOT IN (SELECT entity_id FROM entity_coverage WHERE is_covered = TRUE);

-- Breakdown por natureza juridica das descobertas
SELECT e.natureza_juridica, COUNT(*) AS total
FROM sc_public_entities e
WHERE e.is_active = TRUE AND e.raio_200km = TRUE
  AND e.id NOT IN (SELECT entity_id FROM entity_coverage WHERE is_covered = TRUE)
GROUP BY e.natureza_juridica ORDER BY total DESC;

-- Bids do PNCP por modalidade
SELECT modalidade_id, COUNT(*) AS total, COUNT(*) FILTER (WHERE matched_entity_id IS NOT NULL) AS matched
FROM pncp_raw_bids WHERE source = 'pncp' GROUP BY modalidade_id ORDER BY modalidade_id;
```

---

## Histórico

| Data | Versão | Descrição | Autor |
|------|--------|-----------|-------|
| 2026-07-11 | 1.0 | Relatório inicial de cobertura PNCP | @analyst |
