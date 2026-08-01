# Triagem Técnica de Edital — fixture-multi-doc-01

- Gerado em: `2026-08-01T15:01:07.184883+00:00`
- Recomendação preliminar: **REVIEW**
- Documentos: 5
- Checklist items: 36
- Findings: 48

## Disclaimer

AVISO: este case pack é triagem técnica operacional e NÃO substitui análise jurídica, responsabilidade técnica, ART/RRT, parecer formal nem decisão comercial humana. Validação humana obrigatória.

## Sumário executivo

Recomendação **REVIEW** com base em análise automática rastreável.

### Motivos

- perfil Extra incompleto / pending elicitation
- 2 itens críticos bloqueantes
- 2 anexos essenciais ausentes
- conflitos documentais/datas
- itens críticos sem evidência plena

### Fatores favoráveis

- Objeto e escopo da contratação
- Datas e horários críticos
- Prazos de esclarecimentos e impugnações
- Modalidade licitatória
- Critério de julgamento
- Modo de disputa
- Consórcio — permissão e condições
- Subcontratação — limites e vedações
- Habilitação jurídica
- Regularidade fiscal
- Regularidade trabalhista (CNDT)
- Qualificação econômico-financeira
- Índices econômicos (LG, SG, LC etc.)
- Qualificação técnica operacional
- Atestados, CAT, ART ou RRT

### Fatores impeditivos / atenção

- Inconsistências e ambiguidades entre documentos
- Anexos referidos e ausentes do pacote
- Minuta do Contrato
- projeto básico
- conflito datas sessao

## Documentos analisados

- `doc-001` — aviso_data_conflitante.pdf — tipo=AVISO sha256=`3f12a7c92aaf…` quality=OK
- `doc-002` — mentions_missing.txt — tipo=TERMO_DE_REFERENCIA sha256=`0a2068a11942…` quality=OK
- `doc-003` — sample_edital.pdf — tipo=EDITAL sha256=`b2fa4506aefe…` quality=OK
- `doc-004` — sample_planilha.xlsx — tipo=PLANILHA_ORCAMENTARIA sha256=`fb6dd663f7be…` quality=EXTRACTION_FAILED
- `doc-005` — sample_tr.docx — tipo=TERMO_DE_REFERENCIA sha256=`0c1476812a38…` quality=OK

## Documentos ausentes / ambíguos

- **MISSING** `Anexo II` ← doc-002 p.None
- **MISSING** `Minuta do Contrato` ← doc-002 p.None
- **MISSING** `Anexo I` ← doc-003 p.4
- **MISSING** `Anexo III` ← doc-003 p.4
- **MISSING** `Anexo IV` ← doc-003 p.4
- **MISSING** `Cronograma Físico-Financeiro` ← doc-003 p.4
- **MISSING** `Cronograma` ← doc-003 p.4
- **MISSING** `Modelo de Proposta` ← doc-003 p.4
- **MISSING** `Memorial Descritivo` ← doc-003 p.4
- **MISSING** `projeto básico` ← doc-005 p.None

## Linha do tempo

- **sessao**: raw=`26/08/2026` norm=`2026-08-26` doc=`doc-001` p.1
- **sessao**: raw=`25/08/2026` norm=`2026-08-25` doc=`doc-003` p.3
- **impugnacao**: raw=`20/08/2026` norm=`2026-08-20` doc=`doc-003` p.2
- **visita_tecnica**: raw=`20/08/2026` norm=`2026-08-20` doc=`doc-003` p.2
- **execucao**: raw=`180` norm=`None` doc=`doc-003` p.3
- **execucao**: raw=`180` norm=`None` doc=`doc-005` p.None
- ⚠ CONFLITO sessao: ['2026-08-25', '2026-08-26']

## Checklist

### objeto_escopo — Objeto e escopo da contratação
- status: **SATISFIED** (critical=True)
- evidência: doc=`doc-003` locator=`page:1` page=`1`
- trecho: _Objeto: Contratação de empresa para reforma predial de prédio público
Critério de julgamento: menor preço
Modalidade: Pregão Eletrônico
Modo de disputa: aberto_
- análise: trecho localizado no pacote documental

### aderencia_perfil — Aderência ao perfil operacional Extra
- status: **NEEDS_HUMAN** (critical=True)
- evidência: doc=`doc-003` locator=`page:1` page=`1`
- trecho: _Objeto: Contratação de empresa para reforma predial de prédio público
Critério de julgamento: menor preço
Modalidade: Pregão Eletrônico
Modo de disputa: aberto_
- análise: perfil com pendências (priority_municipalities); termos positivos no texto: ['reforma predial']. Não autoriza GO automático.

### datas_horarios — Datas e horários críticos
- status: **SATISFIED** (critical=True)
- evidência: doc=`doc-001` locator=`page:1` page=`1`
- trecho: _AVISO DE LICITAÇÃO
Abertura da sessão: 26/08/2026 às 09:00
Edital nº 99/2026_
- análise: trecho localizado no pacote documental

### esclarecimentos_impugnacoes — Prazos de esclarecimentos e impugnações
- status: **SATISFIED** (critical=True)
- evidência: doc=`doc-003` locator=`page:3` page=`3`
- trecho: _Página 3
Data de abertura da sessão: 25/08/2026 às 09:00
Prazo para impugnação: 20/08/2026
Prazo de execução: 180 dias
Garantia de proposta: 1% do valor estimado
Garantia contratual: 5% sobre o valo_
- análise: trecho localizado no pacote documental

### modalidade — Modalidade licitatória
- status: **SATISFIED** (critical=True)
- evidência: doc=`doc-003` locator=`page:1` page=`1`
- trecho: _Página 1
EDITAL DE PREGÃO ELETRÔNICO Nº 99/2026
Processo: 1234/2026
Órgão: Prefeitura Municipal de Exemplo/SC
Objeto: Contratação de empresa para reforma pr_
- análise: trecho localizado no pacote documental

### criterio_julgamento — Critério de julgamento
- status: **SATISFIED** (critical=True)
- evidência: doc=`doc-003` locator=`page:1` page=`1`
- trecho: _menor preço
Modalidade: Pregão Eletrônico
Modo de disputa: aberto_
- análise: trecho localizado no pacote documental

### modo_disputa — Modo de disputa
- status: **SATISFIED** (critical=False)
- evidência: doc=`doc-003` locator=`page:1` page=`1`
- trecho: _Modo de disputa: aberto_
- análise: trecho localizado no pacote documental

### condicoes_participacao — Condições de participação
- status: **NOT_FOUND** (critical=True)
- evidência: doc=`None` locator=`None` page=`None`
- análise: padrão não localizado no texto extraído

### consorcio — Consórcio — permissão e condições
- status: **SATISFIED** (critical=False)
- evidência: doc=`doc-003` locator=`page:3` page=`3`
- trecho: _Consórcio: não será permitido
Subcontratação: limitada a 30%_
- análise: trecho localizado no pacote documental

### subcontratacao — Subcontratação — limites e vedações
- status: **SATISFIED** (critical=False)
- evidência: doc=`doc-003` locator=`page:3` page=`3`
- trecho: _valor do contrato
Valor estimado: R$ 1.250.000,00
Consórcio: não será permitido
Subcontratação: limitada a 30%_
- análise: trecho localizado no pacote documental

### habilitacao_juridica — Habilitação jurídica
- status: **SATISFIED** (critical=True)
- evidência: doc=`doc-003` locator=`page:2` page=`2`
- trecho: _Página 2
1. Habilitação jurídica: ato constitutivo e contrato social
2. Regularidade fiscal federal, estadual e municipal; FGTS
3. Regularidade trabalhi_
- análise: trecho localizado no pacote documental

### regularidade_fiscal — Regularidade fiscal
- status: **SATISFIED** (critical=True)
- evidência: doc=`doc-003` locator=`page:2` page=`2`
- trecho: _Página 2
1. Habilitação jurídica: ato constitutivo e contrato social
2. Regularidade fiscal federal, estadual e municipal; FGTS
3. Regularidade trabalhista: CNDT
4. Qualificação econômico-financeira: balanço pat_
- análise: trecho localizado no pacote documental

### regularidade_trabalhista — Regularidade trabalhista (CNDT)
- status: **SATISFIED** (critical=True)
- evidência: doc=`doc-003` locator=`page:2` page=`2`
- trecho: _e contrato social
2. Regularidade fiscal federal, estadual e municipal; FGTS
3. Regularidade trabalhista: CNDT
4. Qualificação econômico-financeira: balanço patrimonial
5. Índices: Liquidez Geral >= 1,0; Liquidez Corrente >=_
- análise: trecho localizado no pacote documental

### qualificacao_economica — Qualificação econômico-financeira
- status: **SATISFIED** (critical=True)
- evidência: doc=`doc-003` locator=`page:2` page=`2`
- trecho: _fiscal federal, estadual e municipal; FGTS
3. Regularidade trabalhista: CNDT
4. Qualificação econômico-financeira: balanço patrimonial
5. Índices: Liquidez Geral >= 1,0; Liquidez Corrente >= 1,0
6. Qualificação técnica: at_
- análise: trecho localizado no pacote documental

### capital_patrimonio — Capital social / patrimônio líquido mínimo
- status: **NOT_FOUND** (critical=False)
- evidência: doc=`None` locator=`None` page=`None`
- análise: padrão não localizado no texto extraído

### indices_economicos — Índices econômicos (LG, SG, LC etc.)
- status: **SATISFIED** (critical=False)
- evidência: doc=`doc-003` locator=`page:2` page=`2`
- trecho: _Liquidez Geral >= 1,0; Liquidez Corrente >= 1,0
6. Qualificação técnica: atestado de capacidade técnica e CAT
7. Visita técnica facult_
- análise: trecho localizado no pacote documental

### garantia_proposta — Garantia de proposta
- status: **RISK** (critical=False)
- evidência: doc=`doc-003` locator=`page:3` page=`3`
- trecho: _/08/2026 às 09:00
Prazo para impugnação: 20/08/2026
Prazo de execução: 180 dias
Garantia de proposta: 1% do valor estimado
Garantia contratual: 5% sobre o valor do contrato
Valor estimado: R$ 1.250.000,00
Consórcio: não_
- análise: exigência localizada; validar impacto operacional

### garantia_contrato — Garantia contratual
- status: **RISK** (critical=False)
- evidência: doc=`doc-003` locator=`page:3` page=`3`
- trecho: _/08/2026
Prazo de execução: 180 dias
Garantia de proposta: 1% do valor estimado
Garantia contratual: 5% sobre o valor do contrato
Valor estimado: R$ 1.250.000,00
Consórcio: não será permitido
Subcontratação: limitada a_
- análise: exigência localizada; validar impacto operacional

### qualificacao_tecnica_operacional — Qualificação técnica operacional
- status: **SATISFIED** (critical=True)
- evidência: doc=`doc-003` locator=`page:2` page=`2`
- trecho: _Qualificação técnica: atestado de capacidade técnica e CAT
7. Visita técnica facultativa em 20/08/2026_
- análise: trecho localizado no pacote documental

### qualificacao_tecnica_profissional — Qualificação técnica profissional
- status: **NOT_FOUND** (critical=True)
- evidência: doc=`None` locator=`None` page=`None`
- análise: padrão não localizado no texto extraído

### atestados_cat_art — Atestados, CAT, ART ou RRT
- status: **SATISFIED** (critical=True)
- evidência: doc=`doc-003` locator=`page:2` page=`2`
- trecho: _CAT
7. Visita técnica facultativa em 20/08/2026_
- análise: trecho localizado no pacote documental

### parcelas_relevancia — Parcelas de maior relevância
- status: **NOT_FOUND** (critical=False)
- evidência: doc=`None` locator=`None` page=`None`
- análise: padrão não localizado no texto extraído

### quantitativos_minimos — Quantitativos mínimos de atestação
- status: **SATISFIED** (critical=False)
- evidência: doc=`doc-003` locator=`page:3` page=`3`
- trecho: _1% do valor estimado
Garantia contratual: 5% sobre o valor do contrato
Valor estimado: R$ 1.250.000,00
Consórcio: não será permitid_
- análise: trecho localizado no pacote documental

### visita_tecnica — Visita técnica
- status: **RISK** (critical=False)
- evidência: doc=`doc-003` locator=`page:2` page=`2`
- trecho: _Visita técnica facultativa em 20/08/2026_
- análise: exigência localizada; validar impacto operacional

### declaracoes_obrigatorias — Declarações obrigatórias
- status: **NOT_FOUND** (critical=False)
- evidência: doc=`None` locator=`None` page=`None`
- análise: padrão não localizado no texto extraído

### formato_proposta — Formato e validade da proposta
- status: **NOT_FOUND** (critical=True)
- evidência: doc=`None` locator=`None` page=`None`
- análise: padrão não localizado no texto extraído

### orcamento_estimado — Orçamento estimado e eventual sigilo
- status: **SATISFIED** (critical=False)
- evidência: doc=`doc-003` locator=`page:3` page=`3`
- trecho: _impugnação: 20/08/2026
Prazo de execução: 180 dias
Garantia de proposta: 1% do valor estimado
Garantia contratual: 5% sobre o valor do contrato
Valor estimado: R$ 1.250.000,00
Consórcio: não será permitido
Subcont_
- análise: trecho localizado no pacote documental

### regime_execucao — Regime de execução
- status: **NOT_FOUND** (critical=False)
- evidência: doc=`None` locator=`None` page=`None`
- análise: padrão não localizado no texto extraído

### reajuste — Reajuste / repactuação
- status: **NOT_FOUND** (critical=False)
- evidência: doc=`None` locator=`None` page=`None`
- análise: padrão não localizado no texto extraído

### sancoes — Sanções e multas
- status: **NEEDS_HUMAN** (critical=False)
- evidência: doc=`doc-003` locator=`page:4` page=`4`
- trecho: _Anexo IV - Modelo de Proposta
Cronograma Físico-Financeiro
Memorial Descritivo
Sanções e multas conforme Lei 14.133/2021_
- análise: trecho localizado; interpretação jurídica/comercial humana necessária

### riscos_contratuais — Riscos contratuais relevantes
- status: **NOT_FOUND** (critical=True)
- evidência: doc=`None` locator=`None` page=`None`
- análise: padrão não localizado no texto extraído

### inconsistencias — Inconsistências e ambiguidades entre documentos
- status: **BLOCKER** (critical=True)
- evidência: doc=`None` locator=`None` page=`None`
- trecho: _['sessao']_
- análise: 0 conflitos confirmados de campo; 1 variações de formato; 1 de datas

### anexos_ausentes — Anexos referidos e ausentes do pacote
- status: **BLOCKER** (critical=True)
- evidência: doc=`None` locator=`None` page=`None`
- trecho: _Anexo II; Minuta do Contrato; Anexo I; Anexo III; Anexo IV; Cronograma Físico-Financeiro; Cronograma; Modelo de Proposta; Memorial Descritivo; projeto básico_
- análise: 10 anexos referidos ausentes; 0 ambíguos

### prazo_execucao — Prazo de execução e cronograma
- status: **SATISFIED** (critical=True)
- evidência: doc=`doc-003` locator=`page:3` page=`3`
- trecho: _Prazo de execução: 180 dias
Garantia de proposta: 1% do valor estimado
Garantia contratual: 5% sobre o valor do contrato
Valor estimado:_
- análise: trecho localizado no pacote documental

### local_obra — Local da obra/serviço e logística
- status: **NOT_FOUND** (critical=False)
- evidência: doc=`None` locator=`None` page=`None`
- análise: padrão não localizado no texto extraído

### me_epp — Tratamento ME/EPP e cotas
- status: **NOT_FOUND** (critical=False)
- evidência: doc=`None` locator=`None` page=`None`
- análise: padrão não localizado no texto extraído


## Riscos

- **medium** Checklist NEEDS_HUMAN: Aderência ao perfil operacional Extra
- **medium** Checklist NOT_FOUND: Condições de participação
- **medium** Checklist NOT_FOUND: Capital social / patrimônio líquido mínimo
- **high** Checklist RISK: Garantia de proposta
- **high** Checklist RISK: Garantia contratual
- **medium** Checklist NOT_FOUND: Qualificação técnica profissional
- **medium** Checklist NOT_FOUND: Parcelas de maior relevância
- **high** Checklist RISK: Visita técnica
- **medium** Checklist NOT_FOUND: Declarações obrigatórias
- **medium** Checklist NOT_FOUND: Formato e validade da proposta
- **medium** Checklist NOT_FOUND: Regime de execução
- **medium** Checklist NOT_FOUND: Reajuste / repactuação
- **medium** Checklist NEEDS_HUMAN: Sanções e multas
- **medium** Checklist NOT_FOUND: Riscos contratuais relevantes
- **critical** Checklist BLOCKER: Inconsistências e ambiguidades entre documentos
- **critical** Checklist BLOCKER: Anexos referidos e ausentes do pacote
- **medium** Checklist NOT_FOUND: Local da obra/serviço e logística
- **medium** Checklist NOT_FOUND: Tratamento ME/EPP e cotas
- **critical** Conflito de datas em sessao: ['2026-08-25', '2026-08-26']
- **high** Anexo ausente: Anexo II
- **high** Anexo ausente: Minuta do Contrato
- **high** Anexo ausente: Anexo I
- **high** Anexo ausente: Anexo III
- **high** Anexo ausente: Anexo IV
- **high** Anexo ausente: Cronograma Físico-Financeiro
- **high** Anexo ausente: Cronograma
- **high** Anexo ausente: Modelo de Proposta
- **high** Anexo ausente: Memorial Descritivo
- **high** Anexo ausente: projeto básico

## Inconsistências

- **FORMAT_VARIATION** data_sessao: {'doc-001': 'Abertura', 'doc-003': 'abertura'}

## Pendências humanas

- [NEEDS_HUMAN] Aderência ao perfil operacional Extra
- [NOT_FOUND] Condições de participação
- [NOT_FOUND] Capital social / patrimônio líquido mínimo
- [NOT_FOUND] Qualificação técnica profissional
- [NOT_FOUND] Parcelas de maior relevância
- [NOT_FOUND] Declarações obrigatórias
- [NOT_FOUND] Formato e validade da proposta
- [NOT_FOUND] Regime de execução
- [NOT_FOUND] Reajuste / repactuação
- [NEEDS_HUMAN] Sanções e multas
- [NOT_FOUND] Riscos contratuais relevantes
- [BLOCKER] Inconsistências e ambiguidades entre documentos
- [BLOCKER] Anexos referidos e ausentes do pacote
- [NOT_FOUND] Local da obra/serviço e logística
- [NOT_FOUND] Tratamento ME/EPP e cotas

## Evidências (matriz)

- F0001: `page:1` — Objeto: Contratação de empresa para reforma predial de prédio público
Critério de julgamento: menor preço
Modalidade: Pregão Eletrônico
Modo de disputa: aberto
- F0002: `page:1` — Objeto: Contratação de empresa para reforma predial de prédio público
Critério de julgamento: menor preço
Modalidade: Pregão Eletrônico
Modo de disputa: aberto
- F0003: `page:1` — AVISO DE LICITAÇÃO
Abertura da sessão: 26/08/2026 às 09:00
Edital nº 99/2026
- F0004: `page:3` — Página 3
Data de abertura da sessão: 25/08/2026 às 09:00
Prazo para impugnação: 20/08/2026
Prazo de execução: 180 dias
Garantia de proposta: 1% do valor estimad
- F0005: `page:1` — Página 1
EDITAL DE PREGÃO ELETRÔNICO Nº 99/2026
Processo: 1234/2026
Órgão: Prefeitura Municipal de Exemplo/SC
Objeto: Contratação de empresa para reforma pr
- F0006: `page:1` — menor preço
Modalidade: Pregão Eletrônico
Modo de disputa: aberto
- F0007: `page:1` — Modo de disputa: aberto
- F0009: `page:3` — Consórcio: não será permitido
Subcontratação: limitada a 30%
- F0010: `page:3` — valor do contrato
Valor estimado: R$ 1.250.000,00
Consórcio: não será permitido
Subcontratação: limitada a 30%
- F0011: `page:2` — Página 2
1. Habilitação jurídica: ato constitutivo e contrato social
2. Regularidade fiscal federal, estadual e municipal; FGTS
3. Regularidade trabalhi
- F0012: `page:2` — Página 2
1. Habilitação jurídica: ato constitutivo e contrato social
2. Regularidade fiscal federal, estadual e municipal; FGTS
3. Regularidade trabalhista: CND
- F0013: `page:2` — e contrato social
2. Regularidade fiscal federal, estadual e municipal; FGTS
3. Regularidade trabalhista: CNDT
4. Qualificação econômico-financeira: balanço pat
- F0014: `page:2` — fiscal federal, estadual e municipal; FGTS
3. Regularidade trabalhista: CNDT
4. Qualificação econômico-financeira: balanço patrimonial
5. Índices: Liquidez Gera
- F0016: `page:2` — Liquidez Geral >= 1,0; Liquidez Corrente >= 1,0
6. Qualificação técnica: atestado de capacidade técnica e CAT
7. Visita técnica facult
- F0017: `page:3` — /08/2026 às 09:00
Prazo para impugnação: 20/08/2026
Prazo de execução: 180 dias
Garantia de proposta: 1% do valor estimado
Garantia contratual: 5% sobre o valor
- F0018: `page:3` — /08/2026
Prazo de execução: 180 dias
Garantia de proposta: 1% do valor estimado
Garantia contratual: 5% sobre o valor do contrato
Valor estimado: R$ 1.250.000,0
- F0019: `page:2` — Qualificação técnica: atestado de capacidade técnica e CAT
7. Visita técnica facultativa em 20/08/2026
- F0021: `page:2` — CAT
7. Visita técnica facultativa em 20/08/2026
- F0023: `page:3` — 1% do valor estimado
Garantia contratual: 5% sobre o valor do contrato
Valor estimado: R$ 1.250.000,00
Consórcio: não será permitid
- F0024: `page:2` — Visita técnica facultativa em 20/08/2026
- F0027: `page:3` — impugnação: 20/08/2026
Prazo de execução: 180 dias
Garantia de proposta: 1% do valor estimado
Garantia contratual: 5% sobre o valor do contrato
Valor estimado: 
- F0030: `page:4` — Anexo IV - Modelo de Proposta
Cronograma Físico-Financeiro
Memorial Descritivo
Sanções e multas conforme Lei 14.133/2021
- F0032: `None` — ['sessao']
- F0033: `None` — Anexo II; Minuta do Contrato; Anexo I; Anexo III; Anexo IV; Cronograma Físico-Financeiro; Cronograma; Modelo de Proposta; Memorial Descritivo; projeto básico
- F0034: `page:3` — Prazo de execução: 180 dias
Garantia de proposta: 1% do valor estimado
Garantia contratual: 5% sobre o valor do contrato
Valor estimado:
- F0037: `None` — ['2026-08-25', '2026-08-26']
- F0038: `line:1` — Conforme Anexo II - Planilha Orçamentária e Minuta do Contrato, os licitantes devem observar o Termo de Referência.
- F0039: `line:1` — Conforme Anexo II - Planilha Orçamentária e Minuta do Contrato, os licitantes devem observar o Termo de Referência.
- F0040: `page:4` — Página 4
Anexos deste edital:
Anexo I - Termo de Referência
Anexo II - Planilha Orçamentária
Anexo III - Minuta do Contrato
Anexo IV - Mo
- F0041: `page:4` — xo I - Termo de Referência
Anexo II - Planilha Orçamentária
Anexo III - Minuta do Contrato
Anexo IV - Modelo de Proposta
Cronograma Físico-Financeiro
Memorial D
- F0042: `page:4` — o II - Planilha Orçamentária
Anexo III - Minuta do Contrato
Anexo IV - Modelo de Proposta
Cronograma Físico-Financeiro
Memorial Descritivo
Sanções e multas conf
- F0043: `page:4` — nexo III - Minuta do Contrato
Anexo IV - Modelo de Proposta
Cronograma Físico-Financeiro
Memorial Descritivo
Sanções e multas conforme Lei 14.133/2021
- F0044: `page:4` — nexo III - Minuta do Contrato
Anexo IV - Modelo de Proposta
Cronograma Físico-Financeiro
Memorial Descritivo
Sanções e multas conforme Lei 14.133/2021
- F0045: `page:4` — ilha Orçamentária
Anexo III - Minuta do Contrato
Anexo IV - Modelo de Proposta
Cronograma Físico-Financeiro
Memorial Descritivo
Sanções e multas conforme Lei 14
- F0046: `page:4` — Anexo IV - Modelo de Proposta
Cronograma Físico-Financeiro
Memorial Descritivo
Sanções e multas conforme Lei 14.133/2021
- F0047: `paragraph:1` — Objeto: reforma predial conforme projeto básico.
- F0048: `None` — {'doc-001': 'Abertura', 'doc-003': 'abertura'}

---

AVISO: este case pack é triagem técnica operacional e NÃO substitui análise jurídica, responsabilidade técnica, ART/RRT, parecer formal nem decisão comercial humana. Validação humana obrigatória.
