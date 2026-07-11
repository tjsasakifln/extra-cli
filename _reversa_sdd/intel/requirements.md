# Intel Pipeline — Requirements

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo | Base: e9729e1

## Visão Geral

Pipeline analítico de 7 estágios com 5 quality gates. Transforma um CNPJ em relatório executivo PDF+Excel com inteligência de mercado, análise de oportunidades e recomendações de participação em licitações. Usa GPT-4.1-nano para classificação e extração estruturada.

## Responsabilidades

- Coleta exaustiva de licitações do PNCP para um CNPJ com CNAE keyword gate
- Enriquecimento cadastral (SICAF, sanções) e geográfico (distâncias, IBGE)
- Análise LLM de 21 campos por edital com adversarial review
- Extração de texto de documentos (PDF, ZIP, XLSX) com OCR fallback
- Geração de relatórios executivos Excel (4 planilhas) e PDF (9 seções)
- 5 quality gates com auto-fix entre estágios

## Regras de Negócio

- R4: Capacidade 10× capital social — editais acima vão para consórcio 🟢
- R5: Bid score threshold 0.45 — abaixo força NAO PARTICIPAR 🟢
- R6: 6 regras de override (EXPIRADO, sancionada, CNAE 0%, CNAE<20%+fit<15%, score<0.20) 🟢
- R7: 4 hard-incompatible patterns CNAE+regex 🟢
- R11: Max 3 docs/edital, 50MB/download, 60K chars/edital 🟢
- R14: CNAE gate probabilístico: base 60% + bônus/penalidade, threshold 35% 🟢
- R15: HHI competição: ≤2=BAIXA, ≤5=MEDIA, ≤10=ALTA, >10=MUITO_ALTA 🟢
- R16: Zero false negative — prioriza recall sobre precision 🟡

## Requisitos Funcionais

| ID | Requisito | Prioridade | Fonte |
|----|-----------|-----------|-------|
| RF-I01 | Coletar licitações PNCP com 12 sub-etapas e adaptive rate limiter | Must | `intel-collect.py:1-3193` |
| RF-I02 | Aplicar CNAE keyword gate probabilístico (threshold 35%) | Must | `intel-collect.py:1186-1464` |
| RF-I03 | Fallback LLM (GPT-4.1-nano) para casos ambíguos | Should | `intel-collect.py:1465` |
| RF-I04 | Semantic dedup: Jaccard > 80% + valor ±15% + mesmo órgão | Must | `intel-collect.py:407-488` |
| RF-I05 | Enriquecer empresa: SICAF + CEIS/CNEP/CEPIM/CEAF | Must | `intel-enrich.py:195-250` |
| RF-I06 | Enriquecer editais: distâncias OSRM, IBGE, custo, simulação, victory profile | Must | `intel-enrich.py:252-400` |
| RF-I07 | Filtrar enriquecimento a editais dentro de 10× capital social | Must | `intel-enrich.py:271-284` |
| RF-I08 | Validar semanticamente (4 hard-incompatible patterns) | Must | `intel-validate.py:98-120` |
| RF-I09 | Validar completeness (forbidden words, enums, embedded "Nao consta") | Must | `intel-validate.py:338-450` |
| RF-I10 | Validar coerência (6 override rules, expired removal) | Must | `intel-validate.py:499-579` |
| RF-I11 | Analisar com GPT-4.1-nano: 21 campos estruturados | Must | `intel-analyze.py:750-795` |
| RF-I12 | Computar bid score 7 dimensões (threshold 0.45) | Must | `intel-analyze.py:279-378` |
| RF-I13 | Programmatic override antes do LLM (CNAE 0%, score < 0.20) | Must | `intel-analyze.py:883-928` |
| RF-I14 | Extrair texto de PDFs: pymupdf4llm → PyMuPDF → OCR | Must | `intel-extract-docs.py:117-185` |
| RF-I15 | Selecionar top20: filtro 5-pass + opportunity score | Must | `intel-extract-docs.py:636-683` |
| RF-I16 | Gerar Excel 4 planilhas com 31 colunas | Must | `intel-excel.py:1-1031` |
| RF-I17 | Gerar PDF executivo 9 seções (Big Four aesthetic) | Must | `intel-report.py:1-2178` |
| RF-I18 | Executar quality gates com auto-fix entre estágios | Must | `intel_pipeline.py:200-700` |

## Requisitos Não Funcionais

| Tipo | Requisito | Evidência | Confiança |
|------|----------|----------|-----------|
| Performance | Subprocess timeouts: collect=600s, enrich=300s, llm=120s, extract=600s | `intel_pipeline.py:timeouts` | 🟢 |
| Performance | Adaptive rate limiter: 150ms base, 2s max, growth/decay dinâmico | `intel-collect.py:214-279` | 🟢 |
| Custo | GPT-4.1-nano: 1/10 do custo do GPT-4.1, ~$0.01/edição | `intel-analyze.py:model default` | 🟡 |
| Qualidade | Adversarial review cross-model reduz viés de confirmação | `intel-analyze.py:945` | 🟡 |
| Resiliência | Fallback analysis se LLM falhar (análise mínima sem IA) | `intel-analyze.py:1063` | 🟢 |

## Critérios de Aceitação

```gherkin
Cenário: Pipeline completo gera relatório para CNPJ
Dado CNPJ válido "12345678000199" com CNAE de engenharia
E UFs=["SC"], dias=90, top=20
Quando intel_pipeline.py executa todos os 7 estágios
Então JSON em data/intel/ contém empresa + editais[] + top20[]
E Excel gerado com 4 planilhas
E PDF gerado com 9 seções
E Todos os 5 gates retornam PASS

Cenário: CNAE gate rejeita edital de alimentação para engenharia
Dado CNPJ com CNAE principal 42 (construção)
E edital com objeto "Aquisição de merenda escolar"
Quando apply_cnae_keyword_gate é executado
Então cnae_compatible = False
E gate2_decision = "INCOMPATIVEL"

Cenário: Override força NAO PARTICIPAR para edital expirado
Dado edital com status_temporal = "EXPIRADO"
E bid_score = 0.85 (acima do threshold)
Quando gate5_recomendacao é executado
Então recomendacao_acao = "NAO PARTICIPAR"
E edital removido do top20
```
