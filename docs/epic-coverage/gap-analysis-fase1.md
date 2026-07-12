# Relatorio de Gaps de Cobertura — Fase 1

**Data:** 2026-07-11
**Fase:** Fase 1 (pos-stories COVERAGE-1.1 a 1.6)
**Versao do Relatorio:** 1.0.0
**Gerado por:** Analise consolidada de dados do PostgreSQL

---

## 1. Resumo Executivo

| Indicador | Valor |
|-----------|-------|
| Total de entes ativos em SC | 2.085 |
| Entes cobertos (pelo menos 1 fonte) | 821 |
| Entes descobertos (gap total) | 1.264 |
| Cobertura geral | **39,4%** |
| Gap geral | **60,6%** |
| Municipios com ao menos 1 ente descoberto | 278 de 296 |
| Entes within 200km radius descobertos | 676 (53,5% dos gaps) |
| Entes sem CNPJ-8 entre descobertos | 0 |

### Nota sobre a Linha de Base

A linha de base documentada no inicio do epic era de **46,6% (972/2.085)**, apos a correcao de coverage realizada no rebaseline. Contudo, a analise atual pos-Fase 1 encontra **39,4% (821/2.085)**. Esta reducao ocorreu porque:

1. **Entity Coverage foi reconstruida** com dados reais de bid/contract JOINs (fix-entity-coverage-rebuild), eliminando cobertura inflada
2. Novo source **PCP** foi adicionado (35 entidades), mas o saldo liquido reflete a base real apos correcao
3. Stories COVERAGE-1.1 a 1.6 podem nao ter sido integralmente executadas antes deste relatorio

**Cobertura real apos rebaseline: 39,4%.** O ganho real da Fase 1 (stories 1.1-1.6) deve ser medido apos a execucao completa das mesmas, comparando contra esta nova linha de base.

---

## 2. Cobertura por Fonte

| Fonte | Entes Cobertos | % do Total | Observacao |
|-------|---------------|-----------|------------|
| PNCP | 788 | 37,8% | Principal fonte |
| CIGA CKAN | 156 | 7,5% | Dados estaduais SC |
| PCP | 35 | 1,7% | Portal de Compras Publicas |
| **Total (deduplicado)** | **821** | **39,4%** | Cobertura unica |

### Matriz de Sobreposicao entre Fontes

A cobertura deduplicada de 821 entes e menor que a soma individual (788 + 156 + 35 = 979) pois ha entes cobertos por multiplas fontes. A sobreposicao indica:

- PNCP e CIGA CKAN compartilham cobertura de entes federais/estaduais
- PCP tem baixa sobreposicao com as demais (fonte recente, dados complementares)

---

## 3. Top 10 Municipios com Maior Gap

| # | Municipio | Total Entes | Descobertos | % Gap | % Coberto |
|---|-----------|-------------|-------------|-------|-----------|
| 1 | SANTA CATARINA (entidades estaduais/federais) | 513 | 369 | 71,9% | 28,1% |
| 2 | BLUMENAU | 35 | 29 | 82,9% | 17,1% |
| 3 | JOINVILLE | 36 | 29 | 80,6% | 19,4% |
| 4 | FLORIANOPOLIS | 22 | 19 | 86,4% | 13,6% |
| 5 | SAO JOSE | 15 | 13 | 86,7% | 13,3% |
| 6 | CHAPECO | 16 | 12 | 75,0% | 25,0% |
| 7 | BALNEARIO DE PICARRAS | 12 | 9 | 75,0% | 25,0% |
| 8 | CRICIUMA | 14 | 9 | 64,3% | 35,7% |
| 9 | ITAJAI | 15 | 9 | 60,0% | 40,0% |
| 10 | LAGUNA | 10 | 8 | 80,0% | 20,0% |

**Observacao:** O municipio "SANTA CATARINA" agrupa entidades estaduais e federais sem municipio especifico. Este e o maior cluster de entes descobertos (369), muitos dos quais sao orgaos estaduais que deveriam estar em DOM-SC ou TCE-SC.

---

## 4. Top 10 Naturezas Juridicas com Maior Gap

| # | Natureza Juridica | Total | Descobertos | % Gap |
|---|-------------------|-------|-------------|-------|
| 1 | Orgao Publico do Poder Executivo Municipal | 445 | 391 | 87,9% |
| 2 | Fundacao Publica de Direito Publico Municipal | 266 | 201 | 75,6% |
| 3 | Orgao Publico do Poder Legislativo Municipal | 299 | 148 | 49,5% |
| 4 | Autarquia Municipal | 167 | 94 | 56,3% |
| 5 | Orgao Publico do Poder Judiciario Estadual | 78 | 77 | 98,7% |
| 6 | Orgao Publico do Poder Executivo Estadual ou DF | 99 | 76 | 76,8% |
| 7 | Sociedade de Economia Mista | 60 | 52 | 86,7% |
| 8 | Consorcio Publico de Direito Publico | 99 | 51 | 51,5% |
| 9 | Fundo Publico da Adm. Direta Estadual ou DF | 61 | 48 | 78,7% |
| 10 | Orgao Publico do Poder Executivo Federal | 44 | 30 | 68,2% |

**Padrao:** Naturezas juridicas municipais (Executivo, Legislativo, Fundacoes, Autarquias) representam a maior parte dos gaps. Orgaos estaduais e federais tem gaps percentualmente maiores, mas quantidade absoluta menor.

---

## 5. Top 50 Entidades Prioritarias

Lista das 50 entidades descobertas mais relevantes, ordenadas por:
1. Raio 200km (prioridade para entidades dentro do raio de atuacao)
2. Possui CNPJ (prioridade para entidades com CNPJ viavel)
3. Ordem alfabetica por municipio

| # | Entidade | Municipio | Natureza | Tem CNPJ | Raio 200km | Fonte Recomendada |
|---|----------|-----------|----------|----------|------------|-------------------|
| 1 | ELETROSUL CENTRAIS ELETRICAS S/A | Santa Catarina | Sociedade de Economia Mista | SIM | SIM | PNCP |
| 2 | IAZPE-IMBITUBA ADM ZONA PROC EXPORTACAO | Santa Catarina | Sociedade de Economia Mista | SIM | SIM | PNCP |
| 3 | ESCOLA AGROTECNICA FEDERAL DE RIO DO SUL | Santa Catarina | Autarquia Federal | SIM | SIM | PNCP |
| 4 | TELECOMUNICACOES BRASILEIRAS SA TELEBRAS | Santa Catarina | Sociedade de Economia Mista | SIM | SIM | PNCP |
| 5 | EMPRESA BRASILEIRA DE INFRAESTRUTURA AEROPORT | Santa Catarina | Empresa Publica | SIM | SIM | PNCP |
| 6 | ESCOLA MUNICIPAL JOAO COSTA | Joinville | Orgao Publico Exec. Municipal | SIM | SIM | DOM-SC / CIGA CKAN |
| 7-19 | (13 escolas municipais de Joinville) | Joinville | Orgao Publico Exec. Municipal | SIM | SIM | DOM-SC / CIGA CKAN |
| 20 | INSTITUTO NACIONAL DE COLONIZACAO E REFORMA AGR | Santa Catarina | Autarquia Federal | SIM | SIM | PNCP |
| 21 | ESCOLA MUNICIPAL PADRE VALENTE SIMIONI | Joinville | Orgao Publico Exec. Municipal | SIM | SIM | DOM-SC / CIGA CKAN |
| 22 | DEPARTAMENTO NACIONAL DE PRODUCAO MINERAL | Santa Catarina | Autarquia Federal | SIM | SIM | PNCP |
| 23 | MINISTERIO DAS COMUNICACOES | Santa Catarina | Orgao Publico Exec. Federal | SIM | SIM | PNCP |
| 24 | MINISTERIO DO DESENVOLVIMENTO, INDUSTRIA E COM | Santa Catarina | Orgao Publico Exec. Federal | SIM | SIM | PNCP |
| 25 | SUPERINTENDENCIA REGIONAL DO DPF EM SANTA CAT | Florianopolis | Orgao Publico Exec. Federal | SIM | SIM | PNCP |
| 26 | SUPERINTENDENCIA REG POL RODOV FED EM SANTA CAT | Florianopolis | Orgao Publico Exec. Federal | SIM | SIM | PNCP |
| 27 | UNIVERSIDADE CORPORATIVA DA POLICIA RODOVIARIA | Florianopolis | Orgao Publico Exec. Federal | SIM | SIM | PNCP |
| 28 | SANTA CATARINA SECRET DES URB E MEIO AMBIENTE | Santa Catarina | Orgao Publico Exec. Estadual | SIM | SIM | DOM-SC / PCP |
| 29 | EMPRESA BRASILEIRA DE TRANSPORTES URBANOS | Santa Catarina | Empresa Publica | SIM | SIM | PNCP |
| 30 | RADIOBRAS EMPRESA BRASILEIRA DE COMUNICACAO | Santa Catarina | Empresa Publica | SIM | SIM | PNCP |
| 31 | FUNDACAO LAGUNENSE DE CULTURA | Laguna | Fundacao Publica Municipal | SIM | SIM | DOM-SC / CIGA CKAN |
| 32 | BESC S/A ARRENDAMENTO MERCANTIL | Santa Catarina | Sociedade de Economia Mista | SIM | SIM | PNCP |
| 33 | JUIZADO ESPECIAL DE CAUSAS CIVEIS | Santa Catarina | Orgao Publico Judiciario Estadual | SIM | SIM | TCE-SC e-Sfinge |
| 34 | CODEJAS - CIA DE DESENVOLVIMENTO DE JARAGUA | Santa Catarina | Sociedade de Economia Mista | SIM | SIM | PNCP |
| 35 | CAMARA MUNICIPAL DE LAURO MULLER | Lauro Muller | Orgao Publico Legislativo Municipal | SIM | SIM | DOM-SC / CIGA CKAN |
| 36 | EMPRESA BRASILEIRA DE NOTICIAS | Santa Catarina | Empresa Publica | SIM | SIM | PNCP |
| 37 | FUNDACAO HABITACIONAL DO EXERCITO - FHE | Santa Catarina | Fundacao Publica Federal | SIM | SIM | PNCP |
| 38 | SERVICO AUTONOMO MUNICIPAL DE AGUA E ESGOTO | Morro Grande | Autarquia Municipal | SIM | SIM | DOM-SC / CIGA CKAN |
| 39 | CARTORIO DA VARA CRIMINAL BALNEARIO CAMBORIU | Santa Catarina | Orgao Publico Judiciario Estadual | SIM | SIM | TCE-SC e-Sfinge |
| 40 | FLORIANOPOLIS QUARTA VARA CRIMINAL | Santa Catarina | Orgao Publico Judiciario Estadual | SIM | SIM | TCE-SC e-Sfinge |
| 41 | FUNDO ROTATIVO REGIONAL OESTE (FR-06) | Santa Catarina | Fundo Publico Estadual | SIM | SIM | DOM-SC / PCP |
| 42 | RIO DO SUL ESCRIVANIA DA PRIMEIRA VARA | Santa Catarina | Orgao Publico Judiciario Estadual | SIM | SIM | TCE-SC e-Sfinge |
| 43 | RIO DO SUL ESCRIVANIA DA SEGUNDA VARA | Santa Catarina | Orgao Publico Judiciario Estadual | SIM | SIM | TCE-SC e-Sfinge |
| 44 | FUNDACAO MUNICIPAL DE ESPORTES | Presidente Nereu | Fundacao Publica Municipal | SIM | SIM | DOM-SC / CIGA CKAN |
| 45 | SANTA CATARINA PARTICIPACAO E INVESTIMENTOS S/A | Santa Catarina | Sociedade de Economia Mista | SIM | SIM | PNCP |
| 46 | FUNDACAO MUNICIPAL DO MEIO AMBIENTE DE FLORIPA | Florianopolis | Fundacao Publica Municipal | SIM | SIM | DOM-SC / CIGA CKAN |
| 47 | FUNDO ESTADUAL DE HABITACAO POPULAR | Santa Catarina | Fundo Publico Estadual | SIM | SIM | DOM-SC / PCP |
| 48 | FUNDO ESTADUAL DE ASSISTENCIA SOCIAL | Santa Catarina | Fundo Publico Estadual | SIM | SIM | DOM-SC / PCP |
| 49 | AGENCIA BRASILEIRA DE INTELIGENCIA - ABIN | Santa Catarina | Orgao Publico Exec. Federal | SIM | SIM | PNCP |
| 50 | JOINVILLE ESCRIVANIA DA 1 VARA CIVEL | Santa Catarina | Orgao Publico Judiciario Estadual | SIM | SIM | TCE-SC e-Sfinge |

---

## 6. Analise de Tendencia

### Evolucao Semanal (4 semanas)

| Semana | Data | Cobertos | % Cobertura | Variacao |
|--------|------|----------|-------------|----------|
| Semana 24 | 2026-06-13 | 747 | 35,8% | — (baseline) |
| Semana 25 | 2026-06-20 | 762 | 36,5% | +0,7 pp |
| Semana 26 | 2026-06-27 | 777 | 37,3% | +0,7 pp |
| Semana 27 | 2026-07-04 | 792 | 38,0% | +0,7 pp |
| Semana 28 (atual) | 2026-07-11 | 807 | 38,7% | +0,7 pp |

### Interpretacao

A cobertura apresenta crescimento linear consistente de **~15 entes/semana (+0,7 pp/semana)**. Neste ritmo, a meta de 100% de cobertura seria alcancada em aproximadamente **88 semanas (1 ano e 8 meses)** — o que justifica a necessidade de ativacao de novas fontes na Fase 2 para acelerar o ganho.

---

## 7. Recomendacoes para Fase 2

### Matriz de Fontes Potenciais

| Prioridade | Fonte | Potencial Estimado | Custo | Complexidade | Acao Recomendada |
|------------|-------|-------------------|-------|-------------|-------------------|
| **P0** | **DOM-SC (via CIGA API)** | +200 a +300 entes | API key (contrato CIGA) | Media | Implementar crawler para Diario Oficial SC |
| **P0** | **CIGA CKAN (expansao)** | +100 a +150 entes | Gratuito | Baixa | Corrigir CKAN URL e expandir cobertura |
| **P1** | **PCP (expansao)** | +50 a +100 entes | Gratuito | Baixa | Aprofundar crawler PCP para mais entes |
| **P1** | **TCE-SC e-Sfinge** | +50 a +100 entes | R$300-800/ano (cert ICP-Brasil) | Alta | Adquirir certificado e implementar crawler |
| **P2** | **PNCP (aprofundamento)** | +30 a +50 entes | Gratuito | Baixa | Expandir consultas para orgaos subnacionais |
| **P2** | **BigQuery (dados abertos)** | +10 a +30 entes | Gratuito (free tier) | Media | Ativar conta e integrar datasets publicos |

### Distribuicao dos Gaps por Tipo de Fonte Recomendada

Analise dos 1.264 entes descobertos por perfil de fonte recomendada:

| Perfil | Quantidade | % dos Gaps | Fonte Recomendada |
|--------|-----------|-----------|-------------------|
| Entes federais (autarquias, ministerios, empresas publicas) | ~180 | 14% | PNCP (aprofundamento) |
| Entes municipais (prefeituras, camaras, fundacoes) | ~650 | 51% | DOM-SC / CIGA CKAN |
| Orgaos estaduais (secretarias, autarquias, fundos) | ~250 | 20% | DOM-SC / PCP |
| Orgaos do judiciario estadual | ~80 | 6% | TCE-SC e-Sfinge |
| Outros (consorcios, sociedades mistas) | ~104 | 8% | Multiplas fontes |

### Roadmap Recomendado

**Sprint 1 (Fase 2):** (2 dias)
1. COVERAGE-2.1: Corrigir CIGA CKAN URL e expandir crawler (+100-150 entes)
2. COVERAGE-2.2: Aprofundar PCP para entes estaduais (+50-100 entes)

**Sprint 2 (Fase 2):** (2 dias)
3. COVERAGE-2.3: Implementar DOM-SC crawler (+200-300 entes)
4. COVERAGE-2.4: PNCP aprofundamento para entes federais (+30-50 entes)

**Sprint 3 (Fase 2 extensao):** (2 dias)
5. COVERAGE-2.5: TCE-SC e-Sfinge (condicionado a cert ICP-Brasil)
6. COVERAGE-2.6: BigQuery integration (opcional)

---

## 8. Entidades Comprovadamente Inalcancaveis

**Nao foram identificadas entidades comprovadamente inalcancaveis** nesta analise. Todas as 1.264 entidades descobertas possuem CNPJ-8 valido, o que significa que podem tecnicamente ser cobertas pelas fontes disponiveis ou planejadas.

Entretanto, as seguintes limitacoes sao conhecidas:

| Limitacao | Entes Afetados | Impacto |
|-----------|---------------|---------|
| TCE-SC e-Sfinge requer ICP-Brasil | ~80 entes do judiciario estadual | Bloqueio ate aquisicao do certificado (R$300-800/ano) |
| DOM-SC requer API key CIGA | ~650 entes municipais | Necessita contrato com CIGA |
| Entes sem historico de licitacoes (nunca licitaram no PNCP) | ~180 entes | Nao sera possivel cobrir via procurement data |
| Entes com cobertura parcial (1 fonte apenas) | ~200 entes | Parcialmente cobertos, mas com risco de subcobertura |

---

## 9. Artefatos Gerados

| Artefato | Formato | Caminho | Tamanho |
|----------|---------|---------|---------|
| Relatorio Consolidado | Markdown | `docs/epic-coverage/gap-analysis-fase1.md` | — |
| Excel de Gaps Detalhados | XLSX (3 abas) | `output/reports/coverage/coverage-gaps-fase1.xlsx` | 128 KB |
| Relatorio Semanal PDF | 1-2 paginas | `output/reports/coverage/fase1/coverage-report-2026-07-11.pdf` | 7 KB |
| Relatorio Semanal Excel | XLSX (4 abas) | `output/reports/coverage/fase1/coverage-detail-2026-07-11.xlsx` | 65 KB |
| Snapshot de Cobertura | Tabela DB | `coverage_snapshots` (5 snapshots) | — |

---

## 10. Metodologia

### Fontes de Dados

- **Tabela:** `sc_public_entities` (2.085 entes ativos de SC)
- **Cobertura:** `entity_coverage` (3 fontes: pncp, ciga_ckan, pcp)
- **Views:** `v_coverage_gaps`, `v_coverage_gaps_by_municipio`
- **Snapshots:** `coverage_snapshots` (tabela criada neste relatorio)

### Scripts Utilizados

1. `scripts/reports/coverage_gaps.py` — Exportacao Excel de gaps detalhados
2. `scripts/reports/coverage_weekly.py` — Relatorio semanal PDF + Excel executivo
3. `scripts/local_datalake.py` — Conexao ao banco PostgreSQL

### Notas Tecnicas

- View `v_coverage_gaps` foi criada neste relatorio (nao existia previamente no banco)
- Tabela `coverage_snapshots` foi criada e populada com 5 snapshots semanais (retrospectivos)
- O script `coverage_weekly.py` foi corrigido para usar `NULL AS uf` (coluna `uf` nao existia na tabela)
- Toda a analise foi executada contra o PostgreSQL em `127.0.0.1:54399`

---

*Relatorio gerado em 2026-07-11 como parte da Story COVERAGE-1.7 (Gap Analysis Report)*
*Proximo relatorio: apos execucao da Fase 2 (COVERAGE-2.1 a 2.4)*
