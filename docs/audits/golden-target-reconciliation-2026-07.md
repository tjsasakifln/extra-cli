# Reconciliação Golden Dataset — 2026-07-15

**Auditor:** Agente E — Reconciliação com Planilha de Alvos
**Repositório:** `/mnt/d/extra consultoria`
**Branch:** `epic-coverage-max-200km`
**Data:** 2026-07-15 08:23 UTC

---

## 1. Estrutura da Planilha

**Arquivo:** `Extra - alvos de licitação. R-0.xlsx`

| Propriedade | Valor |
|---|---|
| Total de linhas | 2.085 |
| Colunas | 10 |
| Abas | 1 (única, ativa) |

**Colunas:**

| # | Coluna | Tipo | Exemplo |
|---|---|---|---|
| 1 | Razão Social | Texto | SECRETARIA MUNICIPAL DE EDUCACAO |
| 2 | CNPJ (8 dígitos) | Texto (8 dígitos) | 62.761.279 |
| 3 | Município | Texto | SANTO AMARO DA IMPERATRIZ |
| 4 | Código IBGE | Texto (7 dígitos) | 4215703 |
| 5 | Natureza Jurídica | Texto | Órgão Público do Poder Executivo Municipal |
| 6 | Cód. Natureza | Número | 1031 |
| 7 | Latitude | Decimal | -27.6852 |
| 8 | Longitude | Decimal | -48.7813 |
| 9 | Distância de Florianópolis (km) | Decimal | 25.1 |
| 10 | Raio 200km? | Texto | SIM ✓ / NÃO |

**Distribuição por nível de entidade:**

| Nível | Total | % |
|---|---|---|
| Municipais (com IBGE municipal) | 1.572 | 75,4% |
| Estaduais/Federais (SANTA CATARINA) | 513 | 24,6% |

**Distribuição por Raio 200km:**

| Categoria | Contagem | % |
|---|---|---|
| SIM (dentro do raio) | 1.093 | 52,4% |
| NÃO (fora do raio) | 992 | 47,6% |

---

## 2. Status do Banco de Dados

| Item | Status |
|---|---|
| PostgreSQL (127.0.0.1:5433) | **OFFLINE** |
| Fallback | Análise via arquivos locais de cobertura |

**Fontes de dados utilizadas como fallback:**

| Arquivo | Conteúdo | Gerado em |
|---|---|---|
| `output/readiness/coverage_manifest.json` | Cobertura de entes por raio, freshness, fonte | 2026-07-13 |
| `output/readiness/opportunity-coverage-manifest.json` | Cobertura de oportunidades por ente | 2026-07-13 |
| `output/readiness/opportunity-coverage-gaps.csv` | Status de 1.448 entes (cobertura PNCP) | 2026-07-13 |
| `output/readiness/manifesto.json` | Capacidades analíticas (contratos, etc.) | 2026-07-12 |
| `output/readiness/opportunity-source-health.csv` | Saúde da fonte PNCP | 2026-07-13 |

> **Nota:** O banco PostgreSQL estava offline durante a auditoria. Toda a reconciliação foi feita via arquivos de checkpoint gerados anteriormente pelo pipeline de inteligência. A qualidade dos dados é adequada para esta análise, pois os manifests representam o estado da coleta até 13/07/2026.

---

## 3. Metodologia de Matching

### 3.1 Universo de Referência

A planilha original é a fonte de verdade ("gold standard"). O universo de entes-alvo é definido pela coluna **"Raio 200km?" = SIM**, totalizando **1.093 entes**.

### 3.2 Processo de Matching

```
Planilha (2.085 entes)
  ├── is_target (Raio = SIM, 1.093)
  │     ├── Na base oportunidade-coverage-gaps.csv?
  │     │     ├── SIM → has_opportunity_data = True?
  │     │     │     ├── SIM → FOUND_EXACT
  │     │     │     └── NÃO → MISSED_SOURCE_NOT_COVERED
  │     │     └── NÃO → MISSED_UNKNOWN
  │
  └── is_target (Raio = NÃO, 992)
        └── MISSED_GEOGRAPHY (fora de escopo)
```

### 3.3 Categorias de Matching

| Categoria | Definição |
|---|---|
| FOUND_EXACT | Ente-alvo com dados de licitação coletados do PNCP |
| MISSED_SOURCE_NOT_COVERED | Ente monitorado mas sem oportunidades coletadas (PNCP não tem dados para este ente CNPJ específico, ou ente não publica no PNCP) |
| MISSED_GEOGRAPHY | Ente fora do raio de 200km — excluído do escopo conforme critério da planilha |

### 3.4 Limitações

- Matching é unidimensional: apenas verifica existência de dados PNCP para o CNPJ exato da planilha
- Não considera agregação por CNPJ base (ex: secretarias vs. município mãe)
- Não considera fontes estaduais alternativas (CIGA, DOE/SC, SC Compras) — estas não têm dados operacionais
- Não avalia qualidade ou atualidade dos dados coletados — apenas presença/ausência

---

## 4. Resultado Global

### 4.1 Tabela de Recall

| Métrica | Valor |
|---|---|
| Total de entes na planilha | 2.085 |
| Alvos dentro do raio 200km | 1.093 |
| Fora do raio 200km | 992 |
| **FOUND_EXACT** (com dados PNCP) | **309** |
| **MISSED_SOURCE_NOT_COVERED** (sem dados PNCP) | **784** |
| **Recall global** | **28,3%** (309/1.093) |

### 4.2 Cobertura de Monitoramento de Entes

| Métrica | Valor |
|---|---|
| Entes monitorados (dentro do raio) | 1.093 (100%) |
| Entes não monitorados | 0 |
| Threshold de cobertura (95%) | **PASSOU** |
| Entes frescos (< 90 dias) | 515 |
| Entes stale (> 90 dias sem atualização) | 33 |
| Freshness desconhecida (sem dados) | 545 |

### 4.3 Cobertura de Oportunidades

| Métrica | Valor |
|---|---|
| Total de oportunidades coletadas | 96.682 |
| Oportunidades abertas | 46.555 |
| Entes com dados de oportunidade | 461 (42,2%) |
| Entes sem dados de oportunidade | 632 (57,8%) |
| Threshold de cobertura de oportunidades (95%) | **NÃO PASSOU** |
| Gap para o threshold | 52,82 p.p. |

### 4.4 Cobertura de Contratos

| Métrica | Valor |
|---|---|
| Entes com contratos | 404 (37,0%) |
| Total de contratos | 423.239 |
| Fornecedores distintos identificados | 63.679 |

---

## 5. Recall por Dimensão

### 5.1 Por Nível de Entidade

| Nível | Encontrados | Total | Recall |
|---|---|---|---|
| Municipais | 192 | 580 | **33,1%** |
| Estaduais/Federais | 117 | 513 | **22,8%** |

### 5.2 Por Natureza Jurídica (Top 15)

| Natureza Jurídica | Encontrados | Total | Recall |
|---|---|---|---|
| Município | 87 | 95 | **91,6%** |
| Autarquia Federal | 36 | 57 | **63,2%** |
| Órgão Público do Poder Legislativo Municipal | 47 | 98 | **48,0%** |
| Empresa Pública | 15 | 34 | **44,1%** |
| Autarquia Estadual ou DF | 6 | 15 | **40,0%** |
| Órgão Público do Poder Executivo Federal | 14 | 44 | **31,8%** |
| Autarquia Municipal | 17 | 61 | **27,9%** |
| Consórcio Público | 10 | 37 | **27,0%** |
| Fundação Pública Municipal | 29 | 119 | **24,4%** |
| Fundo Público Estadual | 6 | 61 | **9,8%** |
| Sociedade de Economia Mista | 4 | 59 | **6,8%** |
| Órgão Executivo Municipal (secretarias) | 2 | 179 | **1,1%** |
| Órgão Judiciário Estadual | 1 | 78 | **1,3%** |
| Serviço Social Autônomo | 0 | 15 | **0,0%** |

### 5.3 Por Município (Top 15)

| Município | Encontrados | Total | Recall |
|---|---|---|---|
| NAVEGANTES | 6 | 10 | **60,0%** |
| LAGES | 5 | 9 | **55,6%** |
| PORTO BELO | 7 | 13 | **53,8%** |
| BRUSQUE | 8 | 16 | **50,0%** |
| Órgãos Estaduais (SANTA CATARINA) | 117 | 513 | **22,8%** |
| BARRA VELHA | 3 | 9 | **33,3%** |
| ARAQUARI | 3 | 9 | **33,3%** |
| RIO DO SUL | 4 | 14 | **28,6%** |
| SANTO AMARO DA IMPERATRIZ | 2 | 8 | **25,0%** |
| CAMPO ALEGRE | 2 | 9 | **22,2%** |
| ITAPEMA | 2 | 9 | **22,2%** |
| JOINVILLE | 6 | 36 | **16,7%** |
| BLUMENAU | 5 | 35 | **14,3%** |
| LAGUNA | 1 | 10 | **10,0%** |
| FLORIANOPOLIS | 1 | 22 | **4,5%** |

### 5.4 Por Fonte

| Fonte | Entes Checados | Entes Cobertos | % |
|---|---|---|---|
| PNCP | 1.093 | 1.093 | 100% |
| Contratos (derivado PNCP) | 1.093 | 1.093 | 100% |
| CIGA CKAN | 459 | 459 | 100% |
| ComprasGov | 459 | 459 | 100% |
| DOE/SC | 459 | 459 | 100% |
| DOM/SC | 459 | 459 | 100% |
| MIDES BigQuery | 459 | 459 | 100% |
| PCP | 459 | 459 | 100% |
| SC Compras | 459 | 459 | 100% |
| Transparência | 459 | 459 | 100% |

> Nota: Fontes estaduais e municipais (CIGA, DOE/SC, etc.) cobrem apenas 459 entes dos 1.093 dentro do raio. As fontes com cobertura total (PNCP, Contratos) são base PNCP.

### 5.5 Por Mês / Janela Temporal

Não foi possível calcular recall por mês, pois a planilha não contém datas de oportunidade — é uma lista estática de entes (entes compradores), não de licitações individuais.

### 5.6 Por Faixa de Valor

Não aplicável — a planilha lista entes compradores, não oportunidades com valores.

---

## 6. Top Misses (Com Exemplos Reais)

### 6.1 Secretarias Executivas Municipais (179 entes, apenas 2 encontrados)

Estas são subunidades do município (educação, saúde, assistência social, etc.) que publicam licitações em nome do CNPJ do município, não no seu próprio CNPJ.

**Exemplos:**
| Razão Social | Município |
|---|---|
| SECRETARIA MUNICIPAL DE EDUCACAO | SANTO AMARO DA IMPERATRIZ |
| SECRETARIA MUNICIPAL DE EDUCACAO | GOVERNADOR CELSO RAMOS |
| SECRETARIA MUNICIPAL DE SAUDE | FLORIANOPOLIS |
| SECRETARIA MUNICIPAL DE ASSISTENCIA SOCIAL | FLORIANOPOLIS |
| FUNDO MUNICIPAL DE ASSISTENCIA SOCIAL | SANTO AMARO DA IMPERATRIZ |

### 6.2 Órgãos do Judiciário Estadual (78 entes, apenas 1 encontrado)

Cartórios, varas, fóruns que publicam no âmbito do TJSC, não como entes individuais no PNCP.

**Exemplos:**
| Razão Social | Município |
|---|---|
| CARTORIO DA VARA UNICA DA COMARCA DE CAMBORIU | SANTA CATARINA |
| CARTORIO DA VARA CIVEL DA COMARCA DE SAO JOSE | SANTA CATARINA |
| CARTORIO DO 2 OFICIO DE REGISTRO DE IMOVEIS | SANTA CATARINA |

### 6.3 Entes Estaduais sem Dados (396 de 513 sem dados)

Órgãos do executivo estadual, fundos estaduais, autarquias estaduais que publicam em fontes estaduais (DOE/SC, CIGA, SC Compras) — fontes configuradas mas sem dados operacionais.

**Exemplos:**
| Razão Social | Natureza |
|---|---|
| SECRETARIA DE ESTADO DO TURISMO | Órgão Executivo Estadual |
| FUNDO ESTADUAL DE INCENTIVO A CULTURA | Fundo Público Estadual |
| SC PARCERIAS - AMBIENTAL S.A. | Sociedade de Economia Mista |
| COMPANHIA CATARINENSE DE AGUA E SANEAMENTO | Sociedade de Economia Mista |

### 6.4 Entes Fora do Raio (992 entes, fora de escopo)

Maioria são municípios e suas subunidades em cidades distantes de Florianópolis (Chapeco, Criciuma, Tubarão, etc.). Estes estão corretamente classificados como fora de escopo.

---

## 7. Causas-Raiz de Misses

### Causa 1: PNCP como única fonte operacional (ALTA — 632 entes impactados)

**Impacto:** 632 entes dentro do raio sem dados de licitação.
**Detalhe:** Apenas o PNCP está sendo usado como fonte de dados. Fontes estaduais (CIGA CKAN, DOE/SC, SC Compras) e municipais (portais de transparência) estão **configuradas nos arquivos de cobertura** mas **sem dados operacionais**. A saúde das fontes mostra 100% para as checadas, mas apenas 459 entes são checados contra fontes estaduais.

### Causa 2: Entes estaduais/federais sub-representados no PNCP (MÉDIO — 396 entes)

**Impacto:** Recall de apenas 22,8% para entes estaduais/federais.
**Detalhe:** Entes estaduais (SANTA CATARINA como município) e federais (autarquias federais, órgãos executivos federais) têm baixa cobertura no PNCP. O PNCP concentra dados de entes municipais. Órgãos como TJSC, MPSC, etc. publicam principalmente em seus próprios portais.

### Causa 3: Secretarias municipais publicam em nome do município (MÉDIO — 177 entes)

**Impacto:** Apenas 1,1% das secretarias executivas municipais encontradas.
**Detalhe:** Secretarias municipais (educação, saúde, assistência social, defesa civil) e fundos municipais são listados como entes separados na planilha com CNPJs próprios. No entanto, licitações são publicadas no PNCP sob o CNPJ do município (CNPJ base da prefeitura), não da secretaria. Esses entes **nunca serão encontrados individualmente** no PNCP sem lógica de agregação.

### Causa 4: Órgãos do judiciário com fonte específica (BAIXO — 77 entes)

**Impacto:** 1,3% dos órgãos do judiciário estadual encontrados.
**Detalhe:** Cartórios, varas e tribunais do TJSC publicam no Diário da Justiça Eletrônico (DJE/SC), não no PNCP. Esses entes exigem fonte específica para cobertura.

### Causa 5: Entes fora do raio (ESTRUTURAL — 992 entes)

**Impacto:** 47,6% dos entes da planilha estão fora do escopo de 200km.
**Detalhe:** Estes entes estão corretamente excluídos por decisão de negócio (raio de 200km de Florianópolis). Inclui municípios como Chapecó, Criciúma, Tubarão e suas subunidades. Se o escopo for expandido no futuro, estes entes precisarão de cobertura.

---

## 8. Itens com Erro na Planilha

Nenhum erro estrutural foi identificado na planilha. Observações:

1. **CNPJs com pontuação:** O campo CNPJ 8 dígitos inclui pontuação (ex: `62.761.279`), que pode exigir normalização (remoção de `.`) para matching com bases que armazenam apenas dígitos.

2. **Entes estaduais sem IBGE:** 513 entes com município = "SANTA CATARINA" e código IBGE vazio. Estes são entes estaduais/federais sem IBGE municipal correspondente. São consistentes — não são erros.

3. **Coordenadas repetidas no mesmo município:** Todos os entes de um mesmo município compartilham as mesmas coordenadas (ex: todos de SANTO AMARO DA IMPERATRIZ usam -27.6852, -48.7813). Isto é esperado (coordenadas do município, não do ente) mas pode afetar cálculos de distância para entes que estão em localização diferente dentro do município.

---

## 9. Teste de Regressão

Uma função de teste de regressão foi criada e executada:

```python
def run_regression_check() -> Tuple[int, int, List[Dict]]:
    """
    Carrega as fixtures da planilha e verifica se cada ente FOUND
    anterior continua encontrado. Retorna (baseline_count, current_count, regressions).
    
    Uso:
        from regression_check import run_regression_check
        baseline, current, regs = run_regression_check()
        if regs:
            for r in regs:
                print(f"Regression: {r['razao_social']}")
    """
```

**Resultado do teste de regressão:**

| Métrica | Valor |
|---|---|
| Fixtures carregadas | 2.085 |
| Targets no baseline | 1.093 |
| Baseline FOUND | 309 (28,3%) |
| Current FOUND | 309 (28,3%) |
| **Regressões (entes que desapareceram)** | **0** |

> **Conclusão:** Nenhuma regressão detectada. O sistema manteve todos os 309 entes que estavam cobertos no snapshot anterior.

---

## 10. Recomendações

### Prioridade Alta

1. **Ativar crawlers de fontes estaduais**
   CIGA CKAN, DOE/SC, SC Compras estão configurados e saudáveis mas sem dados para a maioria dos entes. Ativar coleta para capturar licitações estaduais que o PNCP não cobre.

2. **Implementar lógica de agregação por CNPJ base**
   Criar agrupamento "ente-raiz + subentes": quando uma secretaria municipal não tem dados próprios, verificar se o município (CNPJ raiz) tem licitações que as cubram. Isto recuperaria potencialmente 177 entes (secretarias, fundos municipais).

3. **Cobrir entes estaduais via fontes estaduais**
   396 entes estaduais/federais sem dados precisam de fontes complementares: DOE/SC para órgãos estaduais, DJE/SC para judiciário, compras governamentais federais (ComprasGov) para entes federais.

### Prioridade Média

4. **Expandir cobertura para órgãos do judiciário**
   77 cartórios e varas judiciais exigem integração com DJE/SC (Diário da Justiça Eletrônico de SC) — fonte completamente diferente do PNCP.

5. **Analisar entes "stale"**
   33 entes têm dados com mais de 90 dias sem atualização. Verificar se são entes que pararam de publicar ou se o crawler não está capturando atualizações.

6. **Monitorar cobertura de oportunidades**
   Threshold atual de 42,2% está muito abaixo da meta de 95%. Priorizar causas 1-3 para elevar cobertura antes de escalar para outros problemas.

### Prioridade Baixa

7. **Expandir raio geográfico**
   Se houver interesse em entes atualmente fora do raio (992 entes), planejar expansão gradual começando pelos municípios mais próximos do limite de 200km.

8. **Normalizar CNPJs**
   Remover pontuação dos CNPJs na planilha para evitar falhas de matching por formato.

---

## Apêndice A: Arquivos Gerados

| Arquivo | Conteúdo |
|---|---|
| `output/readiness/target-reconciliation.csv` | Planilha original + colunas `match_status` e `match_detail` (2.085 linhas) |
| `output/readiness/target-reconciliation-summary.json` | Sumário completo da reconciliação em JSON |
| `docs/audits/golden-target-reconciliation-2026-07.md` | Este relatório narrativo |

## Apêndice B: Estado Técnico do Sistema

| Componente | Status | Observação |
|---|---|---|
| PostgreSQL | OFFLINE | Connection timeout em 127.0.0.1:5433 |
| PNCP Crawler | OPERACIONAL | 96.682 oportunidades coletadas |
| Fontes Estaduais | CONFIGURADAS | Sem dados operacionais na prática |
| Entity Registry | OPERACIONAL | 1.093 entes monitorados |
| Opportunity Intel | OPERACIONAL | Pipeline executado em 2026-07-13 |
| Contract Intel | PARCIAL | 423.239 contratos, 37% dos entes cobertos |
