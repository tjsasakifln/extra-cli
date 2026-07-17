# Definition of Done — Extra Consultoria

> Checklist viva para acompanhar a evolução do desenvolvimento do projeto.
>
> **Natureza do projeto:** ferramenta pessoal, single-user, destinada a apoiar Tiago Sasaki na execução da proposta de consultoria para a Extra Construtora.
>
> **Escopo funcional:** inteligência sobre editais, contratos, concorrentes e referências de valores; monitoramento recorrente; triagem e análise técnica de editais; análise de planilhas, composições e BDI; apoio à decisão e à elaboração de propostas; acompanhamento administrativo de contratos sem acompanhamento de obra.
>
> **Fora de escopo:** acompanhamento físico, financeiro, documental ou fotográfico de obras em execução.
>
> **Universo canônico:** planilha `Extra - alvos de licitação. R-0.xlsx`.
>
> **Meta mínima:** cobertura operacional auditável de **95% para editais** e **95% para contratos**, calculadas separadamente sobre os entes marcados na planilha como pertencentes ao raio de 200 km.
>
> **Agnosticidade de desenvolvimento:** os requisitos, evidências, comandos e gates deste documento não dependem de Claude Code, Codex, Cursor, AIOX, MCP proprietário, IDE específica ou qualquer outro agente. Ferramentas podem acelerar o trabalho; nenhuma delas define o que significa pronto.

---

## 1. Como usar este documento

- [x] Este arquivo está versionado na raiz do repositório como `DOD.md`. Evidência: branch `epic/plano-executivo-30d`, campanha EPIC-PLANO-EXECUTIVO-30D / PE-G0-01 (2026-07-16).
- [x] O documento é tratado como checklist de evolução do projeto, e não como Definition of Done de uma única story. Evidência: §35 gates + 3 róis; plano `extra-consultoria-plano-executivo.html`.
- [ ] Cada item só é marcado como concluído quando existir evidência verificável.
- [ ] Sempre que possível, a evidência é registrada ao lado do item no formato: `Evidência: <arquivo, comando, commit, relatório ou data>`.
- [ ] Código existente sem execução comprovada não é considerado concluído.
- [ ] Teste unitário isolado não substitui execução ponta a ponta.
- [ ] Presença de registros no banco não é tratada como prova de cobertura.
- [ ] Uma story marcada como `Done` não torna automaticamente concluído o requisito equivalente neste documento.
- [ ] Alterações de escopo são refletidas primeiro neste documento e nos documentos canônicos do projeto.
- [ ] Itens explicitamente marcados como opcionais não bloqueiam o fechamento do projeto.
- [ ] Todos os demais itens bloqueiam o respectivo gate.
- [ ] O projeto só é considerado integralmente concluído quando os três róis obrigatórios estiverem atendidos:
  - [ ] requisitos do estágio atual;
  - [ ] requisitos posteriores ao provisionamento da VPS;
  - [ ] requisitos independentes de infraestrutura.


### Estados, aplicabilidade e bloqueio

- [ ] Um item desmarcado permanece não aceito, mesmo que esteja parcialmente implementado.
- [ ] Um item só recebe `[x]` após validação e registro de evidência.
- [ ] Implementação parcial é anotada como `PARTIAL`, sem marcar o item como concluído.
- [ ] Dependência externa pendente é anotada como `BLOCKED`, com responsável, causa e próximo teste.
- [ ] Um requisito somente pode ser tratado como `NOT_APPLICABLE` quando a própria redação permitir aplicabilidade condicional ou quando houver decisão de escopo registrada por Tiago.
- [ ] `NOT_APPLICABLE` possui justificativa, data e evidência; não é usado para contornar promessa comercial.
- [ ] Campo indisponível na fonte é registrado como `SOURCE_UNAVAILABLE` ou `NOT_READY`, nunca como zero e nunca como concluído por conveniência.
- [ ] Um blocker externo não desaparece do gate; ele permanece visível até resolução ou alteração formal do escopo.
- [ ] Os gates consideram concluídos apenas itens `DONE` e itens legitimamente `NOT_APPLICABLE`.
- [ ] O estado de cada requisito pode ser reconstruído sem depender do histórico de uma conversa com agente de IA.

### Convenção de evidência

Um item pode ser marcado como concluído apenas quando pelo menos uma das evidências abaixo existir:

- [ ] teste automatizado reproduzível;
- [ ] comando documentado com exit code `0`;
- [ ] relatório JSON, CSV, Excel, PDF ou Markdown gerado pelo sistema;
- [ ] consulta SQL com resultado esperado;
- [ ] execução registrada em ledger, manifest ou tabela de runs;
- [ ] log datado e correlacionável;
- [ ] validação manual registrada por Tiago;
- [ ] commit ou pull request identificável;
- [ ] teste de restauração ou recuperação efetivamente executado;
- [ ] comparação com fonte oficial realizada na mesma data ou período.

---

## 2. Contrato funcional do projeto

### 2.1 Objetivo

- [ ] O sistema ajuda a localizar editais relevantes para a Extra Construtora.
- [ ] O sistema ajuda a verificar contratos históricos dos entes monitorados.
- [ ] O sistema ajuda a identificar vencedores e concorrentes observáveis.
- [ ] O sistema ajuda a formar referências de valores com semântica explícita.
- [ ] O sistema ajuda Tiago a decidir quais oportunidades merecem análise humana.
- [ ] O sistema reduz o risco de perda de oportunidades por monitoramento incompleto.
- [ ] O sistema produz evidências e relatórios utilizáveis na consultoria.
- [ ] O sistema continua sendo uma ferramenta pessoal, sem necessidade de produto SaaS.

### 2.2 Escopo incluído

- [ ] Monitoramento de editais abertos.
- [ ] Reconciliação de status de editais.
- [ ] Histórico de editais encerrados quando necessário para análise.
- [ ] Coleta de contratos dos últimos três anos, no mínimo.
- [ ] Atualização incremental de contratos após o backfill inicial.
- [ ] Mapeamento de fornecedores vencedores.
- [ ] Mapeamento de órgãos contratantes.
- [ ] Identificação de recorrência de contratação.
- [ ] Identificação de concentração de vencedores.
- [ ] Referências de valor estimado.
- [ ] Referências de valor homologado quando a fonte disponibilizar.
- [ ] Referências de valor contratado.
- [ ] Referências de valor pago quando a fonte disponibilizar.
- [ ] Diferenciação explícita entre os quatro tipos de valor.
- [ ] Exportação de dados para revisão manual.
- [ ] Geração de relatórios em PDF e Excel.
- [ ] Operação por CLI, scripts e arquivos.
- [ ] Uso local durante o estágio atual.
- [ ] Operação contínua em VPS no estágio posterior.
- [ ] Monitoramento recorrente de novas oportunidades e alterações relevantes.
- [ ] Triagem inicial de edital.
- [ ] Análise técnica aprofundada de edital quando solicitada.
- [ ] Análise de planilha orçamentária, composições e BDI quando os documentos estiverem disponíveis.
- [ ] Comparação de orçamento com referências oficiais e dados de mercado defensáveis.
- [ ] Apoio à decisão `GO`, `REVIEW` ou `NO_GO`.
- [ ] Apoio à organização e revisão de proposta, sem assumir assinatura ou responsabilidade da empresa.
- [ ] Acompanhamento administrativo de contratos: prazos, publicações, aditivos, vigência, renovação e sinais de relicitação.

### 2.3 Escopo excluído

- [ ] O projeto não contém módulo de diário de obra.
- [ ] O projeto não contém módulo de medição de obra.
- [ ] O projeto não contém acompanhamento de avanço físico.
- [ ] O projeto não contém acompanhamento financeiro da execução da obra.
- [ ] O projeto não contém gestão de fotos de obra.
- [ ] O projeto não contém fiscalização de campo.
- [ ] O projeto não contém gestão de aditivos de execução.
- [ ] O projeto não contém gestão de riscos de obra.
- [ ] O projeto não contém gestão de equipes de obra.
- [ ] O projeto não contém gestão de cronograma físico-financeiro.
- [ ] O projeto não contém portal para a contratada.
- [ ] O projeto não contém interface pública.
- [ ] O projeto não contém multi-tenant.
- [ ] O projeto não contém cobrança, assinatura ou Stripe.
- [ ] O projeto não contém autenticação complexa desnecessária.
- [ ] O projeto não contém dashboard web apenas por conveniência estética.
- [ ] O projeto não contém Kubernetes, Kafka, Redis ou Elasticsearch sem necessidade comprovada.
- [ ] O projeto não assina documentos em nome da Extra.
- [ ] O projeto não protocola propostas ou documentos automaticamente sem ação humana explícita.
- [ ] O projeto não assume responsabilidade técnica, jurídica, contábil ou comercial pela proposta apresentada pela empresa.
- [ ] O projeto não substitui advogado em impugnações, recursos ou pareceres jurídicos.
- [ ] O projeto não representa a empresa presencialmente em sessões de licitação.
- [ ] O projeto não fornece garantias financeiras, seguros ou crédito.
- [ ] O projeto não promete habilitação, adjudicação, vitória ou contratação.
- [ ] O projeto não executa o objeto contratado.

### 2.4 Usuário e forma de uso

- [ ] Tiago é o único usuário obrigatório do sistema.
- [ ] O fluxo principal pode ser executado sem interface web.
- [ ] Os comandos principais são claros e documentados.
- [ ] O sistema não exige conhecimento do código interno para tarefas operacionais recorrentes.
- [ ] A saída é legível para revisão humana.
- [ ] Erros são apresentados com causa provável e próximo passo.
- [ ] O sistema permite repetir uma execução sem criar inconsistência.
- [ ] O sistema permite retomar uma execução interrompida.
- [ ] O sistema permite identificar quando um dado não é confiável.
- [ ] O sistema não esconde limitações atrás de scores ou percentuais genéricos.

### 2.5 Correspondência obrigatória com a proposta comercial

> Esta seção traduz as promessas da proposta em capacidades verificáveis do sistema. A prestação humana da consultoria continua sob responsabilidade de Tiago; o software deve produzir dados e artefatos suficientes para que essas entregas sejam realizadas com rigor.

#### Configuração do diagnóstico

- [ ] Existe configuração canônica do perfil da Extra Construtora ou mecanismo equivalente versionado.
- [ ] A configuração registra região e universo monitorado.
- [ ] A configuração registra tipos de obra e serviços de engenharia relevantes.
- [ ] A configuração registra faixas de valor relevantes, quando definidas no alinhamento.
- [ ] A configuração registra modalidades aceitas ou priorizadas.
- [ ] A configuração registra restrições operacionais conhecidas da empresa.
- [ ] A configuração registra órgãos prioritários definidos no alinhamento.
- [ ] A configuração registra concorrentes indicados pelo cliente.
- [ ] A alteração do perfil não exige modificar regras espalhadas pelo código.
- [ ] Todo relatório identifica a versão do perfil utilizada.

#### Entregável A — ranking dos órgãos públicos

- [ ] O sistema gera ranking dos entes do universo que contratam obras e serviços compatíveis com o perfil.
- [ ] O ranking informa quantidade de contratações no período.
- [ ] O ranking informa valor contratado total.
- [ ] O ranking informa ticket médio com semântica explícita.
- [ ] O ranking informa frequência temporal de contratação.
- [ ] O ranking informa distribuição por modalidade.
- [ ] O ranking informa período de análise.
- [ ] O ranking informa fontes e cobertura aplicáveis.
- [ ] Entes consultados com resultado zero permanecem distinguíveis de entes não consultados.
- [ ] O ranking não favorece artificialmente entes com maior qualidade de dados sem alertar essa limitação.

#### Entregável B — mapeamento de 15 concorrentes observáveis

- [ ] O sistema consegue selecionar e justificar pelo menos 15 fornecedores vencedores relevantes, quando existirem dados suficientes no recorte.
- [ ] A seleção dos 15 possui regra reproduzível e configurável.
- [ ] Cada fornecedor possui CNPJ ou identidade canônica.
- [ ] Cada fornecedor possui quantidade de contratos identificados.
- [ ] Cada fornecedor possui valor contratado total.
- [ ] Cada fornecedor possui ticket contratado médio.
- [ ] Cada fornecedor possui órgãos em que venceu.
- [ ] Cada fornecedor possui distribuição geográfica.
- [ ] Cada fornecedor possui tipos de objeto em que venceu.
- [ ] Deságio só é apresentado quando valor estimado e valor homologado comparáveis estiverem ligados ao mesmo certame, lote ou item.
- [ ] Contrato só é chamado de ativo quando houver vigência e status atual suficientes para sustentar a afirmação.
- [ ] Capacidade operacional disponível de concorrente nunca é afirmada como fato sem evidência; inferências são rotuladas como hipótese.
- [ ] Quando não houver 15 concorrentes defensáveis, o relatório declara a insuficiência e apresenta todos os casos válidos, sem completar a lista com ruído.

#### Entregável C — contratos vincendos em 90 a 180 dias

- [ ] O sistema identifica contratos compatíveis com o perfil cuja vigência termina em janela configurável de 90 a 180 dias.
- [ ] A data de término usada possui fonte e data de verificação.
- [ ] Contratos sem data de vigência não entram silenciosamente na lista.
- [ ] Prorrogações e aditivos conhecidos atualizam a data efetiva.
- [ ] O sistema distingue vencimento contratual de término estimado.
- [ ] A lista informa órgão, objeto, contratado, valor, início, término e fonte.
- [ ] A probabilidade de relicitação possui metodologia documentada, variáveis observáveis e validação retrospectiva.
- [ ] Na ausência de modelo validado, o sistema usa classificação de evidência ou sinais de relicitação, não percentual fabricado.
- [ ] Toda previsão apresenta nível de confiança e limitações.

#### Entregável D — painel de referências de preços

- [ ] O sistema produz referências apenas para grupos tecnicamente comparáveis.
- [ ] A regra de comparabilidade por tipo de obra, serviço, unidade, lote, porte, região e período está documentada.
- [ ] O painel informa quantidade de observações.
- [ ] O painel informa mediana.
- [ ] O painel informa percentil 25.
- [ ] O painel informa percentil 75.
- [ ] O painel informa mínimo e máximo apenas quando úteis e sem ocultar outliers.
- [ ] O painel informa evolução temporal quando a amostra permitir.
- [ ] O painel identifica se cada valor é estimado, homologado, contratado ou pago.
- [ ] O painel não denomina valores globais heterogêneos como “preço real praticado”.
- [ ] Categorias com amostra insuficiente são marcadas como `INSUFFICIENT_SAMPLE`.
- [ ] Critérios de exclusão e tratamento de outliers são reproduzíveis.

#### Entregável E — editais abertos e recomendação individual

- [ ] O relatório inclui editais comprovadamente abertos na data de corte ou semana de conclusão.
- [ ] Cada edital foi visto no snapshot completo mais recente ou reconfirmado individualmente.
- [ ] Cada edital é avaliado contra o perfil versionado da Extra.
- [ ] Cada edital recebe `GO`, `REVIEW` ou `NO_GO`.
- [ ] A apresentação ao cliente traduz `GO` e `NO_GO` como recomendação fundamentada de `PARTICIPAR` ou `NÃO PARTICIPAR`, preservando `REVIEW` quando depender de análise humana adicional.
- [ ] Cada recomendação mostra fatores favoráveis.
- [ ] Cada recomendação mostra fatores impeditivos ou riscos.
- [ ] Cada recomendação referencia dados e documentos oficiais disponíveis.
- [ ] Nenhuma recomendação promete vitória ou substitui análise jurídica, contábil ou técnica final.

#### Pacote final da consultoria

- [ ] O sistema gera PDF executivo e planilhas Excel a partir do mesmo conjunto de runs.
- [ ] PDF e Excel usam a mesma data de corte, universo, filtros e versão do perfil.
- [ ] Divergências entre PDF e Excel são detectadas automaticamente.
- [ ] O PDF possui estrutura suficiente para uma entrega executiva de aproximadamente 30 a 50 páginas quando o volume de evidências justificar.
- [ ] O Excel contém dados rastreáveis, filtros e abas necessárias à revisão.
- [ ] O pacote inclui sumário executivo, metodologia, universo, cobertura, limitações e anexos de evidência.
- [ ] O pacote inclui material de apoio para reunião de apresentação.
- [ ] Afirmações quantitativas no PDF podem ser reconciliadas com linhas ou agregações do Excel.
- [ ] O pacote final passa por aceite manual de Tiago antes de ser apresentado ao cliente.

### 2.6 Esteira recorrente de serviços, exceto acompanhamento de obras

#### Monitoramento mensal estratégico

- [ ] O sistema executa ou apoia ciclo recorrente de monitoramento sem exigir reconstrução manual do diagnóstico.
- [ ] O ciclo identifica editais novos desde a última execução.
- [ ] O ciclo identifica retificações, suspensões, revogações, reaberturas e alterações de prazo.
- [ ] O ciclo identifica contratos que entraram na janela de vencimento configurada.
- [ ] O ciclo atualiza o panorama de órgãos e vencedores com base em dados novos.
- [ ] O sistema gera relatório semanal de oportunidades ou periodicidade formalmente definida.
- [ ] O sistema gera relatório mensal consolidado.
- [ ] O relatório mensal informa variação em relação ao período anterior.
- [ ] O relatório mensal registra cobertura, freshness, blockers e fontes degradadas.
- [ ] O pacote mensal contém material de apoio para a reunião com o cliente.
- [ ] Alertas não substituem relatório consolidado e relatório não substitui alertas urgentes.

#### Triagem de edital

- [ ] Existe checklist configurável de pelo menos 15 a 20 pontos críticos.
- [ ] A triagem verifica objeto, escopo e aderência ao perfil da Extra.
- [ ] A triagem verifica datas, horários, pedidos de esclarecimento, impugnação e entrega.
- [ ] A triagem verifica modalidade, critério de julgamento e modo de disputa.
- [ ] A triagem verifica condições de participação, consórcios e subcontratação.
- [ ] A triagem verifica habilitação jurídica.
- [ ] A triagem verifica regularidade fiscal e trabalhista.
- [ ] A triagem verifica qualificação econômico-financeira.
- [ ] A triagem verifica capital social, patrimônio líquido, índices e garantias.
- [ ] A triagem verifica qualificação técnica operacional e profissional.
- [ ] A triagem verifica atestados, CAT, ART/RRT, parcelas de maior relevância e quantitativos mínimos.
- [ ] A triagem verifica visita técnica e declarações obrigatórias.
- [ ] A triagem verifica formato, validade e condições da proposta.
- [ ] A triagem verifica orçamento estimado, sigilo, regime de execução e reajuste.
- [ ] A triagem verifica sanções, responsabilidades e riscos contratuais relevantes.
- [ ] A triagem identifica inconsistências, ambiguidades e possíveis exigências restritivas para revisão humana.
- [ ] A triagem produz conclusão preliminar e lista de pendências para análise aprofundada.
- [ ] O resultado não é apresentado como parecer jurídico.

#### Análise técnica aprofundada de edital e orçamento

- [ ] O sistema permite vincular edital, anexos, projetos, memoriais, planilha, cronograma e minuta contratual ao mesmo caso.
- [ ] Todos os documentos do caso possuem hash, versão, origem e data de obtenção.
- [ ] O sistema detecta anexos mencionados e ausentes.
- [ ] O sistema detecta divergências entre edital, termo de referência, projeto, planilha e minuta quando tecnicamente verificáveis.
- [ ] A análise preserva rastreabilidade por página, item, célula ou trecho de origem.
- [ ] Quantitativos relevantes podem ser comparados entre documentos.
- [ ] Unidades, códigos, descrições e preços da planilha são normalizados.
- [ ] Composições são vinculadas aos respectivos serviços.
- [ ] Custos diretos, indiretos, encargos e BDI permanecem distinguíveis.
- [ ] A análise verifica coerência aritmética de subtotais, totais, percentuais e arredondamentos.
- [ ] A análise identifica itens sem composição, composição sem item e referência inconsistente.
- [ ] A análise compara preços com SINAPI, SICRO ou outras tabelas oficiais aplicáveis, respeitando mês, localidade, desoneração e unidade.
- [ ] Referências privadas ou históricas são identificadas separadamente das tabelas oficiais.
- [ ] Diferença de preço é acompanhada de base comparável e não é tratada isoladamente como erro.
- [ ] A análise registra riscos de exequibilidade e margem sem inventar custos internos não fornecidos pela Extra.
- [ ] O relatório diferencia achado objetivo, alerta técnico, hipótese e decisão que depende de especialista.

#### Análise crítica completa e decisão

- [ ] A decisão combina aderência técnica, documental, econômica, concorrencial, operacional e temporal.
- [ ] O modelo de decisão possui fatores, pesos ou regras documentados.
- [ ] Fatores eliminatórios não são compensados por score agregado.
- [ ] A recomendação informa informações faltantes que poderiam alterar a decisão.
- [ ] A recomendação informa riscos de caixa, garantias, prazo e mobilização quando houver dados fornecidos pela Extra.
- [ ] A projeção de margem usa custos e premissas fornecidos ou validados pela Extra.
- [ ] Cenários e sensibilidades são identificados como simulações.
- [ ] A conclusão final permanece sujeita ao aceite de Tiago e da empresa.

#### Apoio à elaboração da proposta

- [ ] O sistema gera checklist de documentos exigidos pelo edital.
- [ ] Cada documento possui responsável, status, validade e prazo.
- [ ] O sistema identifica documentos faltantes, vencidos ou incompatíveis.
- [ ] O sistema auxilia a montar matriz de conformidade edital × evidência da empresa.
- [ ] O sistema apoia revisão de coerência entre proposta comercial, planilha, cronograma e declarações.
- [ ] O sistema preserva versões das peças revisadas.
- [ ] O sistema registra comentários, pendências e decisões da revisão.
- [ ] O sistema não altera documento final sem rastreabilidade.
- [ ] A assinatura, responsabilidade, protocolo e envio permanecem com a Extra.
- [ ] O sistema não acessa portal de licitação para envio sem comando humano explícito e escopo específico futuro.

#### Acompanhamento administrativo de contratos, sem acompanhamento de obra

- [ ] O sistema registra contrato, órgão, contratado, objeto, valor, vigência e fonte.
- [ ] O sistema monitora publicações oficiais vinculadas ao contrato.
- [ ] O sistema registra termos aditivos, apostilamentos, suspensões, rescisões e prorrogações quando publicados.
- [ ] O sistema alerta sobre vencimentos administrativos configurados.
- [ ] O sistema alerta sobre vigência próxima do término.
- [ ] O sistema identifica sinais de renovação ou relicitação com grau de confiança explícito.
- [ ] O relatório mensal apresenta status documental e publicações observadas.
- [ ] O módulo não registra medição, diário, avanço físico, fotos, produção, produtividade ou fiscalização da obra.
- [ ] O módulo não declara situação física ou financeira da execução sem dados oficiais e escopo formal adicional.

---

# ROL 1 — DEFINITION OF DONE DO ESTÁGIO ATUAL

> Este rol deve ser concluído antes de considerar encerrada a fase local.
>
> O estágio atual é `local-first`, com PostgreSQL local, execução manual ou semiautomatizada e produção de evidências reproduzíveis.
>
> Provisionar a VPS antes deste rol estar concluído não resolve os gaps de dados, cobertura ou semântica.

---

## 3. Autoridade do universo monitorado

### 3.1 Planilha canônica

- [ ] A planilha `Extra - alvos de licitação. R-0.xlsx` é reconhecida como única fonte canônica do universo-alvo.
- [ ] O hash da planilha importada é registrado.
- [ ] A data de importação é registrada.
- [ ] A versão lógica da planilha é registrada.
- [ ] O total de linhas válidas é registrado.
- [ ] O total de entes dentro do raio de 200 km é calculado diretamente da coluna canônica.
- [ ] O total de entes fora do raio é calculado diretamente da coluna canônica.
- [ ] Nenhum número antigo de universo é mantido como constante solta no código.
- [ ] Nenhuma query usa um denominador alternativo sem justificativa explícita.
- [ ] O universo é recalculado quando o hash da planilha muda.
- [ ] A seed atual pode ser reconstruída a partir da planilha.
- [ ] A planilha pode ser importada mais de uma vez sem duplicação.
- [ ] A segunda importação de uma planilha idêntica resulta em `0 changes`.
- [ ] Entes novos são identificados.
- [ ] Entes removidos são identificados.
- [ ] Entes alterados são identificados.
- [ ] CNPJs são normalizados.
- [ ] Códigos IBGE são normalizados.
- [ ] Coordenadas são normalizadas.
- [ ] Distâncias são tratadas como valor numérico.
- [ ] O campo de pertencimento ao raio não é inferido quando já existe na planilha.
- [ ] Duplicidades legítimas de raiz de CNPJ não são eliminadas indevidamente.
- [ ] Cada ente possui identidade estável e reproduzível.
- [ ] O relatório de importação lista erros, alertas e mudanças.
- [ ] A importação falha de forma explícita quando a planilha não atende ao schema esperado.

### 3.2 Universo operacional

- [ ] O universo operacional é formado somente pelos entes marcados como pertencentes ao raio de 200 km.
- [ ] O baseline atual de 1.093 entes é confirmado para a versão corrente da planilha.
- [ ] O número 1.093 não é tratado como constante permanente.
- [ ] Cada ente do universo possui identificador interno.
- [ ] Cada ente possui nome canônico.
- [ ] Cada ente possui município ou classificação equivalente.
- [ ] Cada ente possui natureza jurídica.
- [ ] Cada ente possui evidência de inclusão no raio.
- [ ] Não existem entes `unknown` quanto ao pertencimento ao raio.
- [ ] Entes fora do raio não entram no denominador das metas de 95%.
- [ ] Entes dentro do raio não podem ser excluídos silenciosamente.
- [ ] Qualquer exclusão manual é registrada com motivo, autor e data.
- [ ] O sistema gera relatório de reconciliação entre planilha e banco.
- [ ] A contagem da planilha, da tabela canônica e do manifest coincide.
- [ ] O relatório de cobertura informa o hash da planilha usada como denominador.

---

## 4. Definição objetiva de cobertura

### 4.1 Fórmulas canônicas

- [ ] O sistema implementa as métricas abaixo sem versões concorrentes.

```text
universe_resolution =
entes com identidade válida e decisão de raio
/
total de linhas válidas da planilha
```

- [ ] `universe_resolution = 100%`.

```text
source_applicability_resolution =
pares ente × fonte × capacidade classificados como applicable ou not_applicable
/
total de pares que exigem decisão
```

- [ ] `source_applicability_resolution = 100%`.
- [ ] Nenhum par necessário permanece como `unknown`.

```text
capability_monitoring_coverage =
entes aplicáveis com ao menos uma combinação obrigatória de fontes
consultada integralmente, fresca e sem blocker
/
entes aplicáveis
```

- [ ] `capability_monitoring_coverage(open_tenders) >= 95%`.
- [ ] `capability_monitoring_coverage(historical_contracts) >= 95%`.
- [ ] A cobertura de editais é calculada separadamente da cobertura de contratos.
- [ ] A média entre as duas coberturas não é usada para mascarar uma delas.
- [ ] Uma fonte saudável para editais não prova cobertura de contratos.
- [ ] Uma fonte saudável para contratos não prova cobertura de editais.

```text
data_presence =
entes com ao menos um registro encontrado
/
entes aplicáveis
```

- [ ] `data_presence` é publicada apenas como métrica descritiva.
- [ ] `data_presence` nunca é chamada de cobertura.
- [ ] Ente sem registros pode ser considerado coberto somente mediante `success_zero` válido.

```text
active_snapshot_integrity =
registros exibidos como ativos vistos no último snapshot completo
ou reconfirmados individualmente depois dele
/
registros exibidos como ativos
```

- [ ] `active_snapshot_integrity = 100%`.

### 4.2 Critério de `success_zero`

Uma consulta que retorna zero registros só conta como cobertura quando:

- [ ] o ente foi identificado corretamente;
- [ ] a fonte foi classificada como aplicável;
- [ ] a capacidade consultada foi identificada;
- [ ] o período consultado foi registrado;
- [ ] todos os parâmetros relevantes foram registrados;
- [ ] a paginação foi iniciada corretamente;
- [ ] a paginação foi concluída;
- [ ] não houve timeout não tratado;
- [ ] não houve erro parcial escondido;
- [ ] não houve página ignorada;
- [ ] não houve resposta truncada;
- [ ] não houve blocker de autenticação;
- [ ] não houve blocker de rate limit pendente;
- [ ] não houve erro de schema;
- [ ] a resposta vazia foi persistida como `success_zero`;
- [ ] o run possui `run_id`;
- [ ] o run possui timestamps de início e fim;
- [ ] o run possui fonte e capability;
- [ ] o run está dentro da janela de freshness;
- [ ] a evidência pode ser auditada posteriormente.

### 4.3 Freshness

- [ ] Editais abertos possuem idade máxima de 24 horas.
- [ ] O status de oportunidade prioritária é reconfirmado na execução mais recente.
- [ ] Contratos possuem backfill integral mínimo de três anos.
- [ ] Contratos possuem atualização incremental com intervalo máximo de sete dias.
- [ ] Alterações em contratos já existentes são atualizadas no banco.
- [ ] Concorrentes herdam a freshness da carga contratual e de resultados.
- [ ] Referências de preços informam a data de corte.
- [ ] O manifest informa freshness por fonte e por capability.
- [ ] Dados vencidos são marcados como `stale`.
- [ ] Dados sem prova de atualização são marcados como `unknown`.
- [ ] `stale` e `unknown` não contam para o numerador de cobertura.
- [ ] O freshness gate falha de modo fechado.
- [ ] Não existe opção silenciosa que converta freshness desconhecida em aprovada.

---

## 5. Ambiente local reproduzível

### 5.1 Pré-requisitos

- [ ] A versão canônica do Python está documentada.
- [ ] A versão canônica do PostgreSQL está documentada.
- [ ] As dependências Python estão declaradas.
- [ ] O projeto pode ser instalado em ambiente limpo.
- [ ] O `.env.example` contém todas as variáveis obrigatórias.
- [ ] O `.env.example` não contém segredos reais.
- [ ] O `.env` real está no `.gitignore`.
- [ ] Arquivos de credenciais locais não são versionados.
- [ ] O setup não depende de caminhos absolutos do computador de Tiago.
- [ ] O setup não depende de estado manual não documentado.
- [ ] O setup informa claramente dependências externas.
- [ ] O setup falha com mensagem útil quando uma dependência obrigatória está ausente.

### 5.2 Bootstrap

- [ ] Existe um comando único ou sequência curta para subir o PostgreSQL local.
- [ ] Existe um comando único para aplicar migrations.
- [ ] Existe um comando único para executar seeds.
- [ ] Existe um comando único para validar o ambiente.
- [ ] O bootstrap funciona em banco vazio.
- [ ] O bootstrap funciona em segunda execução.
- [ ] A segunda execução não duplica dados.
- [ ] A segunda execução não altera checksums de migrations já aplicadas.
- [ ] O bootstrap produz log.
- [ ] O bootstrap retorna exit code não zero em falha.
- [ ] A falha de uma migration interrompe a sequência.
- [ ] O bootstrap não deixa transação abortada sem rollback.
- [ ] O ledger de migrations é consultável.
- [ ] O schema resultante pode ser reconstruído do zero.
- [ ] O schema reconstruído coincide com o schema usado pelos scripts.
- [ ] O banco local pode ser descartado e recriado sem intervenção artesanal.

---

## 6. Integridade do schema e persistência

### 6.1 Schema canônico

- [ ] `db/migrations` é a linha canônica de migrations do estágio atual.
- [ ] Migrations alternativas são marcadas como legadas ou futuras.
- [ ] Não existem tabelas referenciadas pelo código e ausentes do banco.
- [ ] Não existem colunas referenciadas pelo código e ausentes do banco.
- [ ] Não existem views referenciadas pelo código e ausentes do banco.
- [ ] Não existem funções SQL referenciadas pelo código e ausentes do banco.
- [ ] Queries críticas passam por `EXPLAIN` ou execução rollback-only.
- [ ] O audit de schema gera relatório.
- [ ] O audit de schema falha em divergência.
- [ ] O schema possui constraints coerentes.
- [ ] O schema possui índices para consultas operacionais.
- [ ] O schema registra provenance.
- [ ] O schema registra `source`.
- [ ] O schema registra `run_id`.
- [ ] O schema registra timestamps de coleta.
- [ ] O schema registra timestamps de atualização.
- [ ] O schema diferencia dado bruto de dado normalizado.
- [ ] O schema diferencia edital de contrato.
- [ ] O schema diferencia status oficial de status inferido.
- [ ] O schema diferencia valores estimados, homologados, contratados e pagos.

### 6.2 Idempotência e atualização

- [ ] Reexecutar o mesmo crawl não cria duplicatas.
- [ ] Registros alterados na fonte são atualizados.
- [ ] `DO NOTHING` não é usado onde atualização posterior é necessária.
- [ ] Upserts possuem chave canônica definida.
- [ ] A estratégia de deduplicação é determinística.
- [ ] A estratégia de deduplicação não depende apenas de similaridade textual.
- [ ] A deduplicação tenta primeiro o identificador oficial.
- [ ] A deduplicação usa número PNCP quando aplicável.
- [ ] A deduplicação usa órgão, processo e edital quando necessário.
- [ ] Hash é usado apenas como fallback controlado.
- [ ] Duplicatas cross-source são reconciliadas.
- [ ] A origem de cada campo relevante é rastreável.
- [ ] Atualizações não apagam provenance anterior necessária à auditoria.
- [ ] Falhas parciais não são registradas como execução concluída.
- [ ] Checkpoints só avançam após persistência confirmada.
- [ ] Runs interrompidos podem ser retomados.
- [ ] Runs retomados não reiniciam desnecessariamente todo o período.

---

## 7. Registro de fontes e aplicabilidade

### 7.1 Registry de fontes

- [ ] Existe registry canônico de fontes.
- [ ] Cada fonte possui identificador estável.
- [ ] Cada fonte possui URL ou endpoint canônico.
- [ ] Cada fonte informa capacidades suportadas.
- [ ] Cada fonte informa cobertura geográfica.
- [ ] Cada fonte informa necessidade de credenciais.
- [ ] Cada fonte informa limites de paginação conhecidos.
- [ ] Cada fonte informa rate limits conhecidos.
- [ ] Cada fonte informa estratégia de retry.
- [ ] Cada fonte informa estratégia de backoff.
- [ ] Cada fonte informa status operacional.
- [ ] Cada fonte informa data da última validação.
- [ ] Cada fonte informa bloqueadores conhecidos.
- [ ] Cada fonte informa se é primária, complementar ou gap-fill.
- [ ] Código existente sem validação real é marcado como `implemented_not_proven`.
- [ ] Fonte sem acesso é marcada como `blocked`.
- [ ] Fonte não aplicável é marcada como `not_applicable`.
- [ ] Fonte aplicável e testada é marcada como `active`.
- [ ] Fonte não é chamada de ativa apenas porque existe crawler.

### 7.2 Matriz ente × fonte × capability

- [ ] Cada ente possui decisão de aplicabilidade para editais.
- [ ] Cada ente possui decisão de aplicabilidade para contratos.
- [ ] A aplicabilidade pode variar por capability.
- [ ] A aplicabilidade possui justificativa.
- [ ] A aplicabilidade possui data de validação.
- [ ] A aplicabilidade possui fonte da decisão.
- [ ] Entes com múltiplas fontes obrigatórias possuem combinação definida.
- [ ] A combinação mínima de fontes é explícita.
- [ ] Fontes complementares não substituem silenciosamente fontes obrigatórias.
- [ ] Bloqueadores por ente são registrados.
- [ ] Bloqueadores por fonte são registrados.
- [ ] Bloqueadores por capability são registrados.
- [ ] Pares `unknown` aparecem em relatório de gaps.
- [ ] O gate final exige zero pares `unknown` necessários.

---

## 8. Editais abertos

### 8.1 Coleta

- [ ] O crawler PNCP usa endpoint vigente.
- [ ] O crawler PNCP usa parâmetros validados.
- [ ] O limite real de página está documentado.
- [ ] A paginação percorre todas as páginas.
- [ ] O crawler lida com 403.
- [ ] O crawler lida com 429.
- [ ] O crawler lida com 5xx.
- [ ] O crawler lida com timeout.
- [ ] O crawler usa retry com backoff.
- [ ] O crawler registra latência.
- [ ] O crawler registra total de páginas.
- [ ] O crawler registra total de registros recebidos.
- [ ] O crawler registra total de registros persistidos.
- [ ] O crawler registra erros por página.
- [ ] O crawler não considera uma janela concluída quando houve erro parcial.
- [ ] Fontes adicionais aplicáveis são executadas.
- [ ] Pelo menos uma fonte complementar ao PNCP está provada ponta a ponta quando necessária para atingir 95%.
- [ ] A coleta pode ser executada por período.
- [ ] A coleta pode ser executada por fonte.
- [ ] A coleta pode ser executada em modo incremental.
- [ ] A coleta pode ser retomada.

### 8.2 Status e snapshot

- [ ] O sistema produz snapshot completo de editais ativos.
- [ ] O snapshot possui identificador.
- [ ] O snapshot possui timestamp.
- [ ] O snapshot possui fonte.
- [ ] O snapshot possui parâmetros de consulta.
- [ ] Registros vistos no snapshot são marcados como reconfirmados.
- [ ] Registros ausentes do snapshot completo deixam de ser exibidos como ativos.
- [ ] A desativação respeita regras para fontes que não entregam snapshot completo.
- [ ] O sistema diferencia `open`, `upcoming`, `closed`, `suspended`, `revoked`, `annulled`, `failed` e `unknown`.
- [ ] Status `unknown` não é apresentado como edital aberto.
- [ ] Um edital fechado não reaparece como aberto por resíduo histórico.
- [ ] Um edital suspenso é identificado.
- [ ] Um edital revogado é identificado.
- [ ] Um edital anulado é identificado.
- [ ] A data de encerramento é validada.
- [ ] Edital com encerramento passado não é exibido como aberto sem justificativa oficial.
- [ ] `active_snapshot_integrity = 100%`.
- [ ] Existe relatório de itens removidos do snapshot ativo.
- [ ] Existe relatório de itens com status conflitante entre fontes.

### 8.3 Campos mínimos do edital

- [ ] Identificador oficial.
- [ ] Ente canônico.
- [ ] Unidade compradora quando disponível.
- [ ] Número do processo.
- [ ] Número do edital ou contratação.
- [ ] Modalidade.
- [ ] Objeto.
- [ ] Data de publicação.
- [ ] Data e hora de encerramento.
- [ ] Status.
- [ ] URL oficial.
- [ ] Fonte.
- [ ] `run_id`.
- [ ] Data da última verificação.
- [ ] Valor estimado quando disponível.
- [ ] Município ou abrangência.
- [ ] Classificação AEC.
- [ ] Justificativa do score.
- [ ] Indicador de dados incompletos.
- [ ] Completude dos campos essenciais >= 95%.
- [ ] URL oficial e encerramento futuro são obrigatórios para uma oportunidade ser classificada como acionável.

### 8.4 Relevância para a Extra

- [ ] Existe filtro explícito para engenharia, construção e infraestrutura.
- [ ] Palavras-chave são versionadas.
- [ ] CPVs ou classificações equivalentes são versionados.
- [ ] Regras de inclusão são explicáveis.
- [ ] Regras de exclusão são explicáveis.
- [ ] O score não é uma caixa-preta.
- [ ] O sistema distingue `GO`, `REVIEW` e `NO_GO`.
- [ ] Toda classificação possui fatores visíveis.
- [ ] O usuário pode revisar falsos positivos.
- [ ] O usuário pode marcar falsos negativos identificados.
- [ ] Feedback manual pode ser exportado para calibração.
- [ ] A amostra-ouro inclui oportunidades relevantes e irrelevantes.
- [ ] Recall de editais relevantes >= 95% na amostra-ouro.
- [ ] Existem zero falsos “abertos” na amostra prioritária.
- [ ] A amostra é estratificada por município, natureza jurídica e fonte.

---

## 9. Contratos históricos

### 9.1 Escopo temporal

- [ ] O backfill cobre no mínimo os últimos três anos.
- [ ] A data inicial do backfill é registrada.
- [ ] A data final do backfill é registrada.
- [ ] O período é particionado em janelas controladas.
- [ ] Cada janela possui checkpoint.
- [ ] Cada janela possui status.
- [ ] Cada janela possui contagem de páginas.
- [ ] Cada janela possui contagem de registros.
- [ ] Cada janela possui contagem de erros.
- [ ] Uma janela com erro parcial não é marcada como concluída.
- [ ] Uma janela concluída pode ser comprovada por manifest.
- [ ] O backfill pode ser retomado após interrupção.
- [ ] O backfill não reinicia janelas concluídas sem necessidade.

### 9.2 Coleta e atualização

- [ ] O crawler de contratos usa endpoint vigente.
- [ ] A paginação real é validada.
- [ ] Filtros por ente são validados.
- [ ] Filtros por UF são validados.
- [ ] Quando o filtro da API não funciona, existe pós-filtro explícito e testado.
- [ ] Contratos alterados são atualizados.
- [ ] A atualização preserva histórico necessário.
- [ ] O sistema identifica contrato novo.
- [ ] O sistema identifica contrato alterado.
- [ ] O sistema identifica duplicata.
- [ ] O sistema identifica cancelamento ou extinção quando a fonte informa.
- [ ] O sistema registra aditivos somente como dado contratual, sem transformar isso em acompanhamento de obra.
- [ ] O sistema registra vigência quando disponível.
- [ ] O sistema registra valor global.
- [ ] O sistema registra fornecedor.
- [ ] O sistema registra CNPJ do fornecedor.
- [ ] O sistema registra ente contratante.
- [ ] O sistema registra objeto.
- [ ] O sistema registra fonte.
- [ ] O sistema registra URL oficial quando disponível.
- [ ] O sistema registra `run_id`.
- [ ] O sistema registra data de última atualização.
- [ ] O incremental roda com intervalo máximo de sete dias no estágio local, ainda que manualmente.
- [ ] A cobertura de contratos >= 95% é provada por ente aplicável.
- [ ] Entes sem contratos encontrados possuem `success_zero` válido.
- [ ] Presença de contrato em 404 entes, ou qualquer outra quantidade, não é confundida com cobertura.

### 9.3 Qualidade contratual

- [ ] CNPJ do fornecedor é normalizado.
- [ ] Ente contratante é reconciliado com o universo.
- [ ] Contratos de entes fora do raio não entram na métrica principal.
- [ ] Contratos sem ente reconciliado entram em fila de resolução.
- [ ] Valores negativos ou inválidos são sinalizados.
- [ ] Datas inconsistentes são sinalizadas.
- [ ] Contratos duplicados cross-source são reconciliados.
- [ ] Contratos com versões divergentes preservam provenance.
- [ ] O sistema distingue contrato, ata, empenho e resultado.
- [ ] O sistema não chama valor contratado de valor pago.
- [ ] O sistema não chama valor global de preço unitário.
- [ ] O sistema não mistura objetos heterogêneos em uma única referência sem classificação.
- [ ] Existe relatório de completude dos campos contratuais.
- [ ] Campos essenciais possuem completude >= 95% quando a fonte os disponibiliza.
- [ ] Campos estruturalmente indisponíveis são marcados como indisponíveis, não como zero.

---

## 10. Concorrentes e vencedores

### 10.1 Escopo honesto

- [ ] O sistema diferencia vencedor identificado de participante identificado.
- [ ] O sistema não afirma conhecer todos os concorrentes quando a fonte não expõe participantes.
- [ ] O sistema não calcula win rate sem denominador de propostas apresentadas.
- [ ] O sistema não calcula deságio sem valor estimado e valor homologado comparáveis.
- [ ] O sistema não infere capacidade ociosa do concorrente sem dado apropriado.
- [ ] O sistema não trata quantidade de contratos como sinônimo de capacidade técnica.
- [ ] O sistema informa as limitações de cada indicador.

### 10.2 Entregas mínimas

- [ ] Ranking de fornecedores vencedores.
- [ ] Quantidade de contratos por fornecedor.
- [ ] Valor contratado por fornecedor.
- [ ] Ticket contratado médio por fornecedor.
- [ ] Número de entes atendidos por fornecedor.
- [ ] Distribuição por município.
- [ ] Distribuição por natureza do ente.
- [ ] Distribuição por setor ou tipo de objeto.
- [ ] Recorrência de contratação.
- [ ] Última contratação conhecida.
- [ ] Concentração por órgão.
- [ ] Concentração por fornecedor.
- [ ] Market share contratual quando semanticamente válido.
- [ ] HHI quando semanticamente válido.
- [ ] Fonte e data de corte em todas as métricas.
- [ ] Exportação para Excel.
- [ ] Relatório de concorrentes para revisão manual.
- [ ] Queries executadas em PostgreSQL real.
- [ ] Testes validam nomes reais de tabelas e colunas.
- [ ] O relatório distingue métricas prontas, parciais e indisponíveis.

---

## 11. Referências de valores

### 11.1 Semântica obrigatória

- [ ] `valor_estimado` possui definição explícita.
- [ ] `valor_homologado` possui definição explícita.
- [ ] `valor_contratado` possui definição explícita.
- [ ] `valor_pago` possui definição explícita.
- [ ] Os quatro campos não são intercambiáveis.
- [ ] O relatório exibe o tipo de valor.
- [ ] O relatório exibe a fonte do valor.
- [ ] O relatório exibe a data de referência.
- [ ] O relatório exibe a unidade de comparação.
- [ ] O relatório exibe se o valor é global, por lote, por item ou unitário.
- [ ] Valor ausente não é substituído por zero.
- [ ] Valor inferido é marcado como inferido.
- [ ] Valor oficial é marcado como oficial.
- [ ] Valores de objetos heterogêneos não são agregados sem classificação adequada.
- [ ] Valores de períodos muito distintos são acompanhados de data.
- [ ] Atualização monetária, quando usada, é explicitada.
- [ ] Percentis só são calculados sobre amostra comparável.
- [ ] O tamanho da amostra é informado.
- [ ] Outliers são identificados.
- [ ] O sistema não chama percentil de contratos globais de “preço real praticado” sem base técnica.

### 11.2 Encadeamento do certame

- [ ] O sistema tenta relacionar edital, resultado e contrato.
- [ ] O relacionamento usa identificador oficial quando disponível.
- [ ] O relacionamento por processo é validado.
- [ ] O relacionamento por número de contratação é validado.
- [ ] O relacionamento por lote ou item é preservado quando disponível.
- [ ] O relacionamento incerto é marcado como incerto.
- [ ] O relacionamento manual pode ser registrado.
- [ ] O relatório informa o percentual de registros encadeados.
- [ ] O sistema não calcula deságio em registros não encadeados.
- [ ] O sistema não calcula diferença percentual entre grandezas não equivalentes.
- [ ] O sistema produz pelo menos uma referência de valor tecnicamente defensável por categoria relevante.
- [ ] Quando não houver dados suficientes, o sistema declara `NOT_READY`.

---

## 12. Pipeline de inteligência e relatórios

### 12.1 Golden path local

- [ ] Existe um comando canônico de golden path.
- [ ] O golden path sobe ou valida o banco.
- [ ] O golden path aplica migrations.
- [ ] O golden path aplica seed.
- [ ] O golden path importa ou valida a planilha-alvo.
- [ ] O golden path executa fontes mínimas.
- [ ] O golden path persiste dados.
- [ ] O golden path executa freshness gate.
- [ ] O golden path calcula cobertura.
- [ ] O golden path reconcilia snapshot de editais.
- [ ] O golden path gera relatório de editais.
- [ ] O golden path gera relatório de contratos.
- [ ] O golden path gera relatório de concorrentes.
- [ ] O golden path gera relatório de referências de valores.
- [ ] O golden path gera Excel.
- [ ] O golden path gera PDF.
- [ ] O golden path gera ledger.
- [ ] O golden path gera logs.
- [ ] O golden path retorna exit code não zero em qualquer gate obrigatório.
- [ ] O golden path pode ser reexecutado sem duplicação.
- [ ] O golden path pode ser executado em ambiente limpo.
- [ ] O tempo total de execução é registrado.
- [ ] A versão do código é registrada.
- [ ] O hash da planilha é registrado.
- [ ] A versão do schema é registrada.
- [ ] Os relatórios apontam o período de referência.
- [ ] Os relatórios apontam limitações conhecidas.

### 12.2 Saídas operacionais

- [ ] Lista de editais acionáveis.
- [ ] Lista de editais para revisão.
- [ ] Lista de editais descartados com motivo.
- [ ] Lista de oportunidades removidas do snapshot.
- [ ] Lista de entes sem cobertura de editais.
- [ ] Lista de entes sem cobertura de contratos.
- [ ] Lista de blockers por fonte.
- [ ] Lista de runs stale.
- [ ] Relatório de contratos por ente.
- [ ] Relatório de contratos por fornecedor.
- [ ] Relatório de concorrentes.
- [ ] Relatório de concentração.
- [ ] Relatório de referências de valores.
- [ ] Relatório de completude.
- [ ] Relatório de coverage.
- [ ] Relatório de recall.
- [ ] Relatório de source health.
- [ ] Exportação CSV.
- [ ] Exportação Excel.
- [ ] Relatório PDF.
- [ ] Todos os relatórios incluem data de geração.
- [ ] Todos os relatórios incluem versão do universo.
- [ ] Todos os relatórios incluem fonte.
- [ ] Todos os relatórios incluem status de confiabilidade.
- [ ] Todos os relatórios evitam afirmações não suportadas.

---

## 13. Testes do estágio atual

### 13.1 Testes unitários

- [ ] Normalização de CNPJ.
- [ ] Normalização de IBGE.
- [ ] Normalização de coordenadas.
- [ ] Cálculo de identidade de ente.
- [ ] Importação idempotente da planilha.
- [ ] Detecção de novos entes.
- [ ] Detecção de entes alterados.
- [ ] Detecção de entes removidos.
- [ ] Cálculo de cobertura.
- [ ] Regra de `success_zero`.
- [ ] Freshness.
- [ ] Paginação.
- [ ] Retry.
- [ ] Backoff.
- [ ] Checkpoint.
- [ ] Resume.
- [ ] Deduplicação.
- [ ] Reconciliação de snapshot.
- [ ] Classificação de status.
- [ ] Classificação AEC.
- [ ] Regras de score.
- [ ] Semântica de valores.
- [ ] Encadeamento edital-contrato.
- [ ] Geração de manifest.
- [ ] Geração de relatórios.

### 13.2 Testes de integração

- [ ] Banco vazio até schema completo.
- [ ] Importação da planilha real.
- [ ] Segunda importação sem mudanças.
- [ ] Crawl real de pequeno período.
- [ ] Persistência real.
- [ ] Reexecução sem duplicação.
- [ ] Atualização de registro alterado.
- [ ] Execução de `success_zero`.
- [ ] Falha parcial não marcada como sucesso.
- [ ] Retomada por checkpoint.
- [ ] Reconciliação de ente.
- [ ] Reconciliação de snapshot.
- [ ] Backfill de contratos de janela pequena.
- [ ] Incremental após backfill.
- [ ] Geração real de PDF.
- [ ] Geração real de Excel.
- [ ] Queries analíticas em PostgreSQL real.
- [ ] Golden path completo.

### 13.3 Testes de contrato com fontes

- [ ] Endpoint PNCP válido.
- [ ] Schema PNCP esperado.
- [ ] Paginação PNCP válida.
- [ ] Endpoint PCP válido.
- [ ] Schema PCP esperado.
- [ ] Endpoint ComprasGov válido.
- [ ] Schema ComprasGov esperado.
- [ ] Endpoint de cada fonte ativa validado.
- [ ] Mudança de campo obrigatório gera alerta.
- [ ] Resposta vazia inesperada gera alerta.
- [ ] Redução abrupta de volume gera alerta.
- [ ] HTTP 403 é distinguido de zero registros.
- [ ] HTTP 429 é distinguido de zero registros.
- [ ] HTTP 5xx é distinguido de zero registros.
- [ ] Timeout é distinguido de zero registros.

### 13.4 Qualidade mínima

- [ ] `ruff` passa no código alterado.
- [ ] `mypy` passa no caminho crítico definido.
- [ ] `pytest` passa na suíte obrigatória.
- [ ] `bandit` não aponta vulnerabilidade HIGH no código de produção.
- [ ] `pip-audit` não aponta vulnerabilidade conhecida sem tratamento.
- [ ] Pre-commit está configurado.
- [ ] CI falha de modo fechado.
- [ ] Nenhum gate obrigatório usa `continue-on-error`.
- [ ] Nenhum gate obrigatório usa `|| true`.
- [ ] A suíte crítica não depende de serviço externo instável sem mock ou marcação adequada.
- [ ] Testes lentos possuem marcação.
- [ ] Testes que exigem fonte real podem ser executados sob demanda.
- [ ] O coverage mínimo é definido para caminhos críticos, não como número cosmético global.
- [ ] Código crítico sem teste possui justificativa registrada.
- [ ] QA não depende exclusivamente do implementador.

---

## 14. Backup e recuperação local

- [ ] Existe backup local do PostgreSQL.
- [ ] O backup usa formato restaurável.
- [ ] O arquivo de backup possui data.
- [ ] O arquivo de backup possui integridade verificada.
- [ ] Existe retenção mínima definida.
- [ ] Existe script de restore.
- [ ] O restore foi testado em banco separado.
- [ ] O restore recompõe migrations.
- [ ] O restore recompõe dados.
- [ ] O restore recompõe o universo-alvo.
- [ ] O restore preserva provenance.
- [ ] Existe instrução de recuperação após corrupção local.
- [ ] Existe instrução de recuperação após exclusão acidental.
- [ ] O backup não contém segredo exposto.
- [ ] Dados brutos necessários à reprodutibilidade são preservados ou podem ser recoletados.
- [ ] PDFs e anexos não são armazenados no PostgreSQL sem justificativa.
- [ ] Metadados de arquivos incluem hash, tamanho, tipo e origem.
- [ ] Um teste de restauração real está registrado antes de fechar o estágio local.

---

## 15. Aceite manual do estágio atual

- [ ] Tiago consegue instalar o projeto seguindo apenas a documentação.
- [ ] Tiago consegue recriar o banco local.
- [ ] Tiago consegue importar a planilha.
- [ ] Tiago consegue executar o golden path.
- [ ] Tiago consegue gerar uma lista atual de editais.
- [ ] Tiago consegue identificar a data da última verificação de cada edital.
- [ ] Tiago consegue identificar por que uma oportunidade recebeu `GO`, `REVIEW` ou `NO_GO`.
- [ ] Tiago consegue identificar entes sem cobertura.
- [ ] Tiago consegue distinguir ente sem dado de ente não consultado.
- [ ] Tiago consegue consultar contratos de um ente.
- [ ] Tiago consegue consultar contratos de um fornecedor.
- [ ] Tiago consegue gerar ranking de vencedores.
- [ ] Tiago consegue gerar referências de valores com tipo claramente identificado.
- [ ] Tiago consegue gerar PDF e Excel.
- [ ] Tiago consegue repetir a execução sem duplicar dados.
- [ ] Tiago consegue retomar uma execução interrompida.
- [ ] Tiago consegue identificar uma fonte quebrada.
- [ ] Tiago consegue identificar freshness vencida.
- [ ] Tiago consegue restaurar um backup.
- [ ] Tiago considera o fluxo útil para a consultoria real.
- [ ] A cobertura auditável de editais é >= 95%.
- [ ] A cobertura auditável de contratos é >= 95%.
- [ ] O recall de editais relevantes é >= 95% na amostra-ouro.
- [ ] A integridade do snapshot ativo é 100%.
- [ ] Não existem afirmações de acompanhamento de obras.
- [ ] O gate `LOCAL_READY` foi registrado com data, commit e evidências.

---

# ROL 2 — DEFINITION OF DONE APÓS PROVISIONAR A VPS

> Este rol começa após a contratação e disponibilização da VPS.
>
> A VPS não redefine o produto. Ela apenas torna contínuo, remoto e independente do computador local um fluxo que já deve estar tecnicamente válido.

---

## 16. Decisão e contratação da infraestrutura

- [ ] O provedor foi escolhido com justificativa.
- [ ] A região foi escolhida com justificativa.
- [ ] O custo mensal estimado foi registrado.
- [ ] O limite mensal aceitável foi registrado.
- [ ] CPU, RAM e disco foram dimensionados.
- [ ] O dimensionamento considera crescimento do PostgreSQL.
- [ ] O dimensionamento considera crawlers concorrentes.
- [ ] O dimensionamento considera geração de relatórios.
- [ ] A possibilidade de expansão de disco foi verificada.
- [ ] A política de snapshots do provedor foi verificada.
- [ ] A política de suporte foi verificada.
- [ ] A política de backup externo foi definida.
- [ ] A hipótese de bloqueio geográfico do PNCP foi testada.
- [ ] O crawler real foi executado a partir da região candidata.
- [ ] O teste registrou status HTTP.
- [ ] O teste registrou latência.
- [ ] O teste registrou timeouts.
- [ ] O teste registrou quantidade de registros.
- [ ] O teste registrou paginação.
- [ ] O teste registrou consistência de schema.
- [ ] A diferença de registros entre regiões está dentro da tolerância definida.
- [ ] Não houve bloqueio 403 por origem geográfica.
- [ ] A região final foi aprovada com base no teste.

---

## 17. Provisionamento básico

- [ ] A VPS usa Ubuntu 24.04 LTS ou versão formalmente aprovada.
- [ ] A versão do PostgreSQL coincide com a versão canônica.
- [ ] A versão do Python coincide com a versão canônica.
- [ ] O hostname está definido.
- [ ] O timezone está definido.
- [ ] O relógio está sincronizado.
- [ ] Existe usuário não-root para a aplicação.
- [ ] O usuário de aplicação possui home e permissões adequadas.
- [ ] O diretório da aplicação está definido.
- [ ] O diretório de dados está definido.
- [ ] O diretório de logs está definido.
- [ ] O diretório temporário está definido.
- [ ] O provisionamento é executado por script ou Ansible.
- [ ] O provisionamento é idempotente.
- [ ] A segunda execução do provisionamento não quebra a máquina.
- [ ] O provisionamento gera log.
- [ ] O provisionamento retorna exit code não zero em falha.
- [ ] Não existe etapa essencial exclusivamente manual e não documentada.
- [ ] Nenhum agente de desenvolvimento ou IDE assistida, incluindo Claude Code, Codex, Cursor ou equivalente, é instalado na VPS como dependência operacional.
- [ ] A operação da VPS não depende de sessão interativa de IA.
- [ ] Node.js não é instalado sem necessidade.
- [ ] Docker não é instalado sem necessidade.
- [ ] Serviços desnecessários são removidos ou desabilitados.

---

## 18. Hardening da VPS

- [ ] Acesso SSH somente por chave.
- [ ] Chave ed25519 ou equivalente moderno.
- [ ] Password authentication desabilitado.
- [ ] Login root direto desabilitado.
- [ ] X11 forwarding desabilitado.
- [ ] Usuário de aplicação sem privilégios excessivos.
- [ ] `sudo` restrito.
- [ ] UFW com default deny.
- [ ] Apenas portas necessárias abertas.
- [ ] PostgreSQL não exposto publicamente.
- [ ] Acesso ao PostgreSQL por localhost, túnel SSH, rede privada ou Tailscale.
- [ ] Fail2ban ativo.
- [ ] Política de bloqueio validada.
- [ ] Atualizações de segurança automáticas ativas.
- [ ] Política de reboot definida.
- [ ] A política de reboot foi testada.
- [ ] Chaves possuem política de rotação.
- [ ] Segredos não aparecem em logs.
- [ ] DSNs são mascarados em logs.
- [ ] Arquivos `.env` possuem permissões mínimas.
- [ ] A chave de backup possui escopo mínimo.
- [ ] A chave de deploy possui escopo mínimo.
- [ ] Tentativas de acesso são auditáveis.
- [ ] Portas abertas são verificadas externamente.
- [ ] Um scan básico não encontra serviço inesperado exposto.

---

## 19. Deploy reproduzível

- [ ] O deploy parte de commit identificado.
- [ ] O commit passou pelos gates obrigatórios.
- [ ] O deploy não exige edição manual de código na VPS.
- [ ] O código é sincronizado por método definido.
- [ ] Dependências são instaladas de forma determinística.
- [ ] Migrations são executadas de forma controlada.
- [ ] Seeds são executadas de forma controlada.
- [ ] O deploy possui pre-check.
- [ ] O deploy possui smoke test.
- [ ] O deploy possui freshness gate.
- [ ] O deploy possui health check.
- [ ] O deploy possui rollback de código.
- [ ] O deploy possui estratégia de recuperação de banco.
- [ ] O deploy interrompe em falha.
- [ ] O deploy registra início, fim e versão.
- [ ] O deploy pode ser reexecutado.
- [ ] O deploy não depende de sessão SSH artesanal.
- [ ] O deploy pode ser iniciado do ambiente local de Tiago.
- [ ] Existe runbook de deploy.
- [ ] Existe runbook de rollback.
- [ ] Existe runbook de recuperação após deploy incompleto.

---

## 20. Migração do banco local para a VPS

- [ ] Backup final do banco local foi criado.
- [ ] Hash ou integridade do backup foi validado.
- [ ] Banco de destino foi criado.
- [ ] Migrations foram aplicadas.
- [ ] Restore foi executado.
- [ ] Contagem de entes coincide.
- [ ] Hash da planilha coincide.
- [ ] Contagem de editais coincide dentro da regra definida.
- [ ] Contagem de contratos coincide dentro da regra definida.
- [ ] Contagem de fornecedores coincide.
- [ ] Ledger de migrations coincide.
- [ ] Views críticas funcionam.
- [ ] Queries críticas funcionam.
- [ ] Golden path funciona na VPS.
- [ ] Relatórios gerados na VPS coincidem com o baseline.
- [ ] Diferenças são explicadas.
- [ ] O banco local é mantido temporariamente como fallback.
- [ ] A data de corte da migração foi registrada.
- [ ] O primeiro incremental pós-migração foi executado.
- [ ] Não houve duplicação após o primeiro incremental.
- [ ] A VPS passou a ser a fonte operacional após aceite explícito.

---

## 21. Serviços e timers

- [ ] Cada crawler ativo possui service unit.
- [ ] Cada crawler recorrente possui timer.
- [ ] Cada service usa `EnvironmentFile`.
- [ ] Cada service roda com usuário apropriado.
- [ ] Cada service possui timeout.
- [ ] Cada service possui política de restart coerente.
- [ ] Cada service possui `OnFailure`.
- [ ] Existe apenas um padrão de template `OnFailure`.
- [ ] O payload de alerta é consistente.
- [ ] Todos os services críticos têm cobertura de alerta.
- [ ] Timers são escalonados para evitar concorrência desnecessária.
- [ ] Timers usam timezone documentado.
- [ ] Timers possuem `RandomizedDelaySec` quando apropriado.
- [ ] O crawl de editais atende freshness <= 24h.
- [ ] O incremental de contratos atende freshness <= 7 dias.
- [ ] O freshness gate possui timer.
- [ ] O coverage report possui timer.
- [ ] O health check possui timer.
- [ ] O check de alertas possui timer.
- [ ] A coleta de métricas possui timer.
- [ ] O backup possui timer.
- [ ] O teste de restore possui timer ou rotina periódica documentada.
- [ ] Timers desabilitados são intencionais e documentados.
- [ ] Selenium genérico não roda como fonte independente.
- [ ] O status de todos os timers é exportável.
- [ ] O atraso de execução é detectado.
- [ ] Uma falha silenciosa é detectada em até 30 minutos.
- [ ] A execução manual continua possível.

---

## 22. Backup e disaster recovery na VPS

- [ ] Backup é armazenado fora da VPS principal.
- [ ] Backup é criptografado em trânsito.
- [ ] Backup possui retenção diária.
- [ ] Backup possui retenção semanal.
- [ ] Backup possui integridade verificada.
- [ ] Falha de backup gera alerta.
- [ ] Último backup válido é monitorado.
- [ ] O backup não é substituído por snapshot do provedor.
- [ ] O restore foi testado em banco separado.
- [ ] O restore completo foi testado.
- [ ] O restore de schema foi testado.
- [ ] O restore de dados foi testado.
- [ ] O tempo de restauração foi registrado.
- [ ] A perda total da VPS foi simulada.
- [ ] Uma nova VPS foi provisionada.
- [ ] O código foi reimplantado.
- [ ] O banco foi restaurado.
- [ ] Os timers foram reativados.
- [ ] O golden path foi executado.
- [ ] O freshness gate voltou a passar.
- [ ] O RPO aceitável foi definido.
- [ ] O RTO aceitável foi definido.
- [ ] O procedimento de desastre está documentado.
- [ ] Credenciais de recuperação estão acessíveis de forma segura.
- [ ] A recuperação não depende de memória pessoal não documentada.

---

## 23. Observabilidade e alertas

- [ ] Logs estruturados estão ativos.
- [ ] Logs possuem timestamp.
- [ ] Logs possuem nível.
- [ ] Logs possuem serviço.
- [ ] Logs possuem fonte.
- [ ] Logs possuem `run_id` ou correlation id.
- [ ] Logs não expõem segredos.
- [ ] Retenção de journald está configurada.
- [ ] Uso de disco é monitorado.
- [ ] Uso de memória é monitorado.
- [ ] Load average é monitorado.
- [ ] Crescimento do banco é monitorado.
- [ ] Dead tuples são monitoradas.
- [ ] Autovacuum é monitorado.
- [ ] Duração dos crawlers é monitorada.
- [ ] Taxa de sucesso dos crawlers é monitorada.
- [ ] Volume coletado é monitorado.
- [ ] HTTP 403 é monitorado.
- [ ] HTTP 429 é monitorado.
- [ ] HTTP 5xx é monitorado.
- [ ] Timeouts são monitorados.
- [ ] Freshness por fonte é monitorada.
- [ ] Coverage por capability é monitorada.
- [ ] Último backup válido é monitorado.
- [ ] Falhas de migration são monitoradas.
- [ ] Timers atrasados são monitorados.
- [ ] Alertas possuem destino configurado.
- [ ] O destino de alerta foi testado.
- [ ] O alerta possui contexto suficiente para ação.
- [ ] O sistema evita tempestade de alertas.
- [ ] Existe rate limiting ou deduplicação de alertas.
- [ ] Falha no webhook é detectável.
- [ ] Existe fallback de notificação ou registro persistente.
- [ ] Tiago consegue consultar saúde geral com um comando.

---

## 24. Operação contínua e independência do ambiente local

- [ ] A VPS executa crawlers sem o computador local ligado.
- [ ] A VPS executa relatórios sem o computador local ligado.
- [ ] A VPS executa backups sem o computador local ligado.
- [ ] A VPS executa health checks sem o computador local ligado.
- [ ] A VPS executa alertas sem o computador local ligado.
- [ ] A operação não depende de Claude Code, Codex, Cursor ou qualquer outro agente de desenvolvimento.
- [ ] A operação não depende de terminal aberto.
- [ ] A operação não depende de login diário.
- [ ] O sistema retoma após reboot.
- [ ] PostgreSQL inicia após reboot.
- [ ] Services iniciam conforme configuração.
- [ ] Timers permanecem habilitados após reboot.
- [ ] Um reboot controlado foi testado.
- [ ] Uma falha de crawler foi simulada.
- [ ] Um atraso de fonte foi simulado.
- [ ] Uma falha de backup foi simulada.
- [ ] Um disco próximo do limite foi simulado ou testado.
- [ ] Uma chave inválida foi simulada.
- [ ] Alertas foram recebidos.
- [ ] O runbook permitiu recuperação.
- [ ] O sistema operou por sete dias consecutivos sem falha crítica não detectada.
- [ ] Durante os sete dias, editais mantiveram freshness <= 24h.
- [ ] Durante os sete dias, contratos mantiveram freshness <= 7 dias.
- [ ] Durante os sete dias, cobertura de editais permaneceu >= 95%.
- [ ] Durante os sete dias, cobertura de contratos permaneceu >= 95%.
- [ ] Durante os sete dias, backups foram concluídos.
- [ ] Ao menos um restore foi validado no período.
- [ ] O custo real foi registrado.
- [ ] O custo real permaneceu dentro do limite aprovado.
- [ ] O gate `VPS_OPERATIONAL` foi registrado com data, commit e evidências.

---

# ROL 3 — DEFINITION OF DONE INDEPENDENTE DA INFRAESTRUTURA

> Estes requisitos podem e devem evoluir antes, durante e depois do provisionamento da VPS.
>
> Eles impedem que o projeto fique tecnicamente sofisticado e, ainda assim, pouco confiável ou pouco útil para a consultoria.

---

## 25. Verdade, linguagem e claims permitidos

- [ ] Todo indicador possui definição.
- [ ] Todo indicador possui fórmula.
- [ ] Todo indicador possui denominador.
- [ ] Todo indicador possui data de corte.
- [ ] Todo indicador possui fonte.
- [ ] Todo indicador possui status de prontidão.
- [ ] `READY` significa executado e validado.
- [ ] `PARTIAL` significa útil com limitações explícitas.
- [ ] `NOT_READY` significa não disponível.
- [ ] `BLOCKED` significa impedido por dependência externa ou técnica.
- [ ] Código existente não é chamado de capacidade pronta.
- [ ] Dado antigo não é chamado de dado atual.
- [ ] Presença de dados não é chamada de cobertura.
- [ ] Ausência de dados não é chamada de ausência de licitação sem consulta válida.
- [ ] Valor contratado não é chamado de preço praticado.
- [ ] Vencedor conhecido não é chamado de conjunto completo de concorrentes.
- [ ] Participante não identificado não é tratado como inexistente.
- [ ] Win rate não é calculado sem propostas enviadas.
- [ ] Deságio não é calculado sem grandezas comparáveis.
- [ ] Score não é chamado de probabilidade sem calibração.
- [ ] Relatórios exibem limitações relevantes.
- [ ] Nenhum documento afirma que o projeto acompanha obras.
- [ ] Nenhum documento promete capacidade fora do escopo.
- [ ] README, PRD, DOD, manifests e relatórios usam as mesmas definições.
- [ ] Números conflitantes são eliminados ou contextualizados historicamente.

---

## 26. Simplicidade arquitetural

- [ ] Cada componente possui problema claro a resolver.
- [ ] Componentes sem uso são removidos, arquivados ou marcados como legados.
- [ ] Não existem dois orquestradores ativos sem divisão explícita.
- [ ] Não existem dois pipelines canônicos para a mesma entrega.
- [ ] Não existem arquivos duplicados com hífen e underscore para a mesma função.
- [ ] Não existem dois templates de alerta concorrentes.
- [ ] Não existem duas linhas de migrations operacionais concorrentes.
- [ ] Não existe dependência de Supabase sem necessidade funcional.
- [ ] Não existe interface web sem necessidade funcional.
- [ ] Não existe autenticação interna desnecessária.
- [ ] Não existe camada de API interna sem consumidor.
- [ ] Não existe fila distribuída sem volume que a justifique.
- [ ] Não existe cache adicional sem gargalo comprovado.
- [ ] Não existe ferramenta de observabilidade pesada sem necessidade.
- [ ] A arquitetura pode ser explicada em uma página.
- [ ] O fluxo principal pode ser entendido por outro desenvolvedor.
- [ ] O custo cognitivo é tratado como custo real.
- [ ] A solução mais simples que atende ao requisito é preferida.

---

## 27. Organização e manutenção do código

- [ ] Estrutura de pastas está documentada.
- [ ] Nomes de módulos são consistentes.
- [ ] Imports funcionam sem hacks de `sys.path` desnecessários.
- [ ] Funções públicas possuem docstring quando necessário.
- [ ] Funções críticas possuem type hints.
- [ ] Exceções são específicas.
- [ ] Erros não são engolidos.
- [ ] Não existem `except Exception: pass`.
- [ ] Falhas externas possuem contexto.
- [ ] Logs não substituem tratamento de erro.
- [ ] Configuração é centralizada.
- [ ] Constantes de domínio são centralizadas.
- [ ] URLs de fontes são centralizadas.
- [ ] Timeouts são configuráveis.
- [ ] Retries são configuráveis.
- [ ] Janelas de freshness são configuráveis.
- [ ] Thresholds de coverage são configuráveis.
- [ ] Defaults são documentados.
- [ ] Mudanças de schema exigem migration.
- [ ] Mudanças de métrica exigem atualização da definição.
- [ ] Código legado possui plano de remoção.
- [ ] TODOs críticos possuem issue ou story.
- [ ] Comentários não contradizem o código.
- [ ] Scripts operacionais possuem `--help`.
- [ ] Scripts operacionais possuem exit codes consistentes.
- [ ] Scripts operacionais suportam `--dry-run` quando aplicável.
- [ ] Scripts destrutivos exigem confirmação ou flag explícita.
- [ ] Scripts destrutivos possuem backup ou rollback documentado.

---

## 28. Segurança proporcional ao uso pessoal

- [ ] Nenhum segredo está versionado.
- [ ] Histórico git foi verificado para segredos expostos.
- [ ] Segredos expostos foram rotacionados.
- [ ] `.env.example` usa placeholders.
- [ ] Tokens têm escopo mínimo.
- [ ] Chaves antigas são removidas.
- [ ] Dependências vulneráveis são tratadas.
- [ ] Arquivos de saída não expõem segredos.
- [ ] Logs não expõem segredos.
- [ ] Dumps não são publicados.
- [ ] Planilhas privadas não são publicadas.
- [ ] O repositório permanece privado.
- [ ] Dados pessoais desnecessários não são coletados.
- [ ] A coleta respeita fontes públicas e limites razoáveis.
- [ ] Rate limits são respeitados.
- [ ] User-Agent é identificável quando apropriado.
- [ ] Crawlers não tentam contornar autenticação indevidamente.
- [ ] Credenciais de fontes autorizadas são armazenadas com cuidado.
- [ ] A segurança é suficiente para um sistema pessoal sem criar burocracia inútil.
- [ ] Controles adicionais são adotados apenas diante de risco real.

---

## 29. Rastreabilidade e auditoria

- [ ] Cada execução possui `run_id`.
- [ ] Cada execução possui versão do código.
- [ ] Cada execução possui versão do schema.
- [ ] Cada execução possui hash da planilha.
- [ ] Cada execução possui fonte.
- [ ] Cada execução possui capability.
- [ ] Cada execução possui parâmetros.
- [ ] Cada execução possui período.
- [ ] Cada execução possui timestamps.
- [ ] Cada execução possui status.
- [ ] Cada execução possui contagens.
- [ ] Cada execução possui erros.
- [ ] Cada execução possui checkpoint.
- [ ] Cada relatório referencia runs de origem.
- [ ] Cada registro crítico possui provenance.
- [ ] Mudanças manuais são auditáveis.
- [ ] Overrides manuais possuem motivo.
- [ ] Overrides manuais possuem data.
- [ ] Overrides manuais possuem autor.
- [ ] A evidência de coverage pode ser reconstruída.
- [ ] A evidência de `success_zero` pode ser reconstruída.
- [ ] A evidência de freshness pode ser reconstruída.
- [ ] A evidência de recall pode ser reconstruída.
- [ ] A evidência de snapshot pode ser reconstruída.
- [ ] O DOD aponta para os artefatos finais de aceite.

---

## 30. Performance e custo

- [ ] O tempo do golden path é medido.
- [ ] O tempo de cada crawler é medido.
- [ ] O tempo de cada relatório é medido.
- [ ] Queries lentas são identificadas.
- [ ] Índices são baseados em consultas reais.
- [ ] Não existe otimização prematura sem evidência.
- [ ] O crescimento diário do banco é medido.
- [ ] O crescimento mensal é estimado.
- [ ] O espaço de dados brutos é medido.
- [ ] O espaço de PDFs e anexos é medido.
- [ ] O custo de APIs pagas é medido.
- [ ] O custo de LLM é medido.
- [ ] Chamadas de LLM são cacheadas quando apropriado.
- [ ] O sistema funciona sem LLM em capacidades determinísticas.
- [ ] LLM não decide coverage.
- [ ] LLM não decide freshness.
- [ ] LLM não inventa valores ausentes.
- [ ] LLM não substitui fonte oficial.
- [ ] O custo mensal total é compatível com o valor da consultoria.
- [ ] Uma otimização só é priorizada quando reduz custo, tempo ou risco relevante.

---

## 31. Documentação operacional

- [ ] README descreve o estado atual real.
- [ ] README descreve o escopo.
- [ ] README descreve o fora de escopo.
- [ ] README descreve setup.
- [ ] README descreve comandos principais.
- [ ] README descreve fontes.
- [ ] README descreve métricas de coverage.
- [ ] README não confunde alvo futuro com realidade atual.
- [ ] PRD está alinhado ao DOD.
- [ ] ADRs vigentes estão identificadas.
- [ ] ADRs revogadas estão identificadas.
- [ ] Existe runbook local.
- [ ] Existe runbook de VPS.
- [ ] Existe runbook de backup.
- [ ] Existe runbook de restore.
- [ ] Existe runbook de deploy.
- [ ] Existe runbook de rollback.
- [ ] Existe runbook de fonte quebrada.
- [ ] Existe runbook de schema drift.
- [ ] Existe runbook de cobertura abaixo de 95%.
- [ ] Existe runbook de freshness vencida.
- [ ] Existe glossário.
- [ ] Existe matriz de fontes.
- [ ] Existe matriz de capabilities.
- [ ] Existe registro de blockers.
- [ ] Existe changelog ou histórico equivalente.
- [ ] O próximo passo de desenvolvimento pode ser identificado sem reconstruir todo o contexto.

---

## 32. Agnosticidade de agentes, IDEs e modelos

### 32.1 Fonte canônica de verdade

- [ ] `DOD.md`, README, PRD, ADRs, runbooks, código, migrations, testes e artefatos versionados são a fonte de verdade do projeto.
- [ ] Nenhuma decisão obrigatória existe apenas em histórico de chat, memória de agente, prompt oculto ou sessão local.
- [ ] Instruções específicas de ferramenta apenas apontam para documentos canônicos; não criam requisitos paralelos.
- [ ] `CLAUDE.md`, `AGENTS.md`, regras do Cursor e arquivos equivalentes não se contradizem.
- [ ] Existe um guia canônico de desenvolvimento, como `docs/DEVELOPMENT.md`, compartilhado por todas as ferramentas.
- [ ] `CLAUDE.md` referencia o guia canônico e contém apenas adaptações indispensáveis ao Claude Code.
- [ ] `AGENTS.md` referencia o guia canônico e contém apenas adaptações indispensáveis ao Codex ou agentes compatíveis.
- [ ] As regras do Cursor referenciam o guia canônico e contêm apenas adaptações indispensáveis ao editor.
- [ ] Os três pontos de entrada indicam o mesmo comando de setup, validação e golden path.
- [ ] Os três pontos de entrada indicam os mesmos documentos de escopo, arquitetura e operação.
- [ ] Quando existirem instruções específicas para uma ferramenta, elas funcionam como adaptadores finos e dispensáveis.
- [ ] A remoção de qualquer arquivo específico de Claude Code, Codex ou Cursor não elimina requisitos de produto, dados, qualidade ou operação.
- [ ] Em caso de conflito, prevalecem DOD, ADR vigente, código testado e evidência reproduzível, nessa ordem definida pelo projeto.

### 32.2 Unidade de trabalho portável

- [ ] Toda tarefa relevante pode ser compreendida por um agente novo sem acesso à conversa que a originou.
- [ ] Toda tarefa registra objetivo.
- [ ] Toda tarefa registra contexto mínimo necessário.
- [ ] Toda tarefa registra escopo incluído.
- [ ] Toda tarefa registra fora de escopo.
- [ ] Toda tarefa referencia os itens pertinentes do DOD.
- [ ] Toda tarefa possui critérios de aceite objetivos.
- [ ] Toda tarefa informa comandos de validação.
- [ ] Toda tarefa informa artefatos de evidência esperados.
- [ ] Toda tarefa informa riscos e rollback quando aplicável.
- [ ] Toda tarefa informa dependências externas e blockers conhecidos.
- [ ] Nenhuma tarefa exige interpretar expressões vagas como “deixar perfeito”, “resolver tudo” ou “funcionar bem” sem critérios mensuráveis.

### 32.3 Comandos e validação independentes de agente

- [ ] Setup, testes, lint, migrations, crawls, relatórios, backup e restore são executados por comandos de shell, Python, Make ou mecanismo aberto equivalente.
- [ ] Nenhum gate obrigatório depende de slash command exclusivo de uma ferramenta.
- [ ] Nenhum gate obrigatório depende de MCP proprietário.
- [ ] Nenhum gate obrigatório depende de uma extensão específica de IDE.
- [ ] Existe comando canônico de validação completa, como `make verify`, `make golden-path` ou equivalente documentado.
- [ ] O comando canônico produz exit code determinístico.
- [ ] O comando canônico produz resumo legível e artefato estruturado.
- [ ] Claude Code, Codex e Cursor recebem o mesmo resultado ao executar os mesmos comandos no mesmo commit e ambiente.
- [ ] Validações subjetivas possuem checklist explícita e registro de aceite humano.
- [ ] Alterações produzidas por qualquer agente passam pelos mesmos testes e gates.

### 32.4 Ambiente reproduzível e contexto transferível

- [ ] Versões de Python, PostgreSQL e dependências estão fixadas ou delimitadas de forma reproduzível.
- [ ] Dependências possuem lock ou estratégia equivalente documentada.
- [ ] Variáveis de ambiente necessárias aparecem em `.env.example` sem segredos.
- [ ] Dados de teste e fixtures necessários estão versionados ou podem ser gerados por comando documentado.
- [ ] Caminhos locais, nomes de usuário e detalhes da máquina de um agente não entram no código.
- [ ] O repositório contém instruções suficientes para retomada após troca de agente.
- [ ] O estado atual, próximo passo, blockers e evidências não dependem de memória conversacional.
- [ ] Um handoff entre Claude Code, Codex e Cursor pode ocorrer usando apenas o repositório e os acessos externos documentados.
- [ ] Artefatos temporários de agente não são confundidos com documentação canônica.

### 32.5 Autoridade e segurança de execução

- [ ] Agentes podem propor alterações, mas decisões de escopo permanecem sob autoridade de Tiago.
- [ ] Nenhum agente publica, faz merge, provisiona infraestrutura, altera dados de produção ou rotaciona credenciais sem autorização explícita quando a ação tiver efeito externo relevante.
- [ ] O agente que implementa não pode substituir evidência de teste por autodeclaração de sucesso.
- [ ] Revisão independente pode ser realizada por outro agente, outra sessão sem contexto, teste automatizado ou validação humana proporcional ao risco.
- [ ] Divergências entre agentes são resolvidas por execução reproduzível, documentação canônica e decisão registrada, não por autoridade presumida do modelo.
- [ ] Ferramentas proprietárias são conveniências opcionais e possuem alternativa manual ou aberta para operações críticas.

---

## 33. Governança pessoal do desenvolvimento

- [ ] Toda mudança relevante possui story, issue ou registro equivalente.
- [ ] Critérios de aceite são definidos antes da implementação relevante.
- [ ] Mudanças de alto risco possuem plano de rollback.
- [ ] Mudanças de schema recebem revisão específica.
- [ ] Mudanças em coverage recebem revisão específica.
- [ ] Mudanças em freshness recebem revisão específica.
- [ ] Mudanças em deduplicação recebem revisão específica.
- [ ] Mudanças em segurança recebem revisão específica.
- [ ] Mudanças em fontes possuem teste de contrato.
- [ ] Mudanças em relatórios possuem validação visual.
- [ ] QA é executado antes de publicação.
- [ ] Commits têm escopo claro.
- [ ] Branch principal permanece utilizável.
- [ ] Débito técnico crítico não é escondido por documentação.
- [ ] Stories marcadas como Done possuem evidências.
- [ ] O estado do DOD é atualizado após entregas relevantes.
- [ ] O DOD não é atualizado apenas no encerramento do projeto.
- [ ] Itens concluídos não são desmarcados sem registro da regressão.
- [ ] Regressões geram correção priorizada.
- [ ] O projeto privilegia utilidade real para a consultoria.
- [ ] Trabalho sem impacto no escopo é despriorizado.
- [ ] Infraestrutura não é usada para fugir de problemas de dados.
- [ ] Refinamento estético não é usado para fugir de problemas de cobertura.

---

## 34. Aceite final da utilidade

- [ ] Tiago usa o sistema em uma situação real de consultoria.
- [ ] O sistema encontra oportunidades que merecem análise.
- [ ] O sistema não exibe oportunidades encerradas como abertas.
- [ ] O sistema informa o que não conseguiu monitorar.
- [ ] O sistema permite investigar um ente específico.
- [ ] O sistema permite investigar um fornecedor específico.
- [ ] O sistema permite investigar um objeto ou setor.
- [ ] O sistema permite consultar contratos dos últimos três anos.
- [ ] O sistema permite comparar fornecedores vencedores.
- [ ] O sistema permite produzir referência de valores sem confundir grandezas.
- [ ] O sistema gera material apresentável ao cliente.
- [ ] O sistema reduz trabalho manual repetitivo.
- [ ] O sistema não cria falsa segurança.
- [ ] O sistema é simples o bastante para ser mantido por Tiago.
- [ ] O sistema pode ser recuperado após falha.
- [ ] O sistema pode ser atualizado sem procedimento improvisado.
- [ ] O sistema pode continuar operando sem dependência diária do ambiente local.
- [ ] O custo é aceitável.
- [ ] O benefício prático supera o custo de manutenção.
- [ ] Tiago aprova formalmente o sistema como apto para apoiar a proposta.
- [ ] O gate `PROJECT_DONE` foi registrado com data, commit e evidências.

---

# 35. Gates consolidados

## 35.1 Gate `LOCAL_READY`

O gate `LOCAL_READY` só pode ser marcado quando:

- [ ] Todos os itens obrigatórios do ROL 1 estão concluídos.
- [ ] Os itens aplicáveis do ROL 3 estão concluídos.
- [ ] O universo canônico está reconciliado.
- [ ] A cobertura de editais é >= 95%.
- [ ] A cobertura de contratos é >= 95%.
- [ ] O recall de editais relevantes é >= 95%.
- [ ] A integridade do snapshot ativo é 100%.
- [ ] O golden path local passa.
- [ ] PDF e Excel são gerados.
- [ ] Backup e restore local foram testados.
- [ ] Tiago executou aceite manual.
- [ ] A evidência foi registrada.

**Status:** [ ] NÃO ATINGIDO  
**Data:**  
**Commit:**  
**Evidências:**  

---

## 35.2 Gate `VPS_OPERATIONAL`

O gate `VPS_OPERATIONAL` só pode ser marcado quando:

- [ ] Todos os itens obrigatórios do ROL 2 estão concluídos.
- [ ] Deploy é reproduzível.
- [ ] Hardening foi validado.
- [ ] Banco foi migrado.
- [ ] Timers estão ativos.
- [ ] Alertas foram testados.
- [ ] Backup externo funciona.
- [ ] Restore foi testado.
- [ ] O sistema sobrevive a reboot.
- [ ] A operação independe do computador local.
- [ ] O sistema operou sete dias sem falha crítica não detectada.
- [ ] A cobertura de editais permaneceu >= 95%.
- [ ] A cobertura de contratos permaneceu >= 95%.
- [ ] A evidência foi registrada.

**Status:** [ ] NÃO ATINGIDO  
**Data:**  
**Commit:**  
**Evidências:**  

---

## 35.3 Gate `PROJECT_DONE`

O gate `PROJECT_DONE` só pode ser marcado quando:

- [ ] `LOCAL_READY` foi atingido.
- [ ] `VPS_OPERATIONAL` foi atingido.
- [ ] Todos os itens obrigatórios do ROL 3 estão concluídos.
- [ ] O projeto cumpre o escopo da proposta, exceto acompanhamento de obras.
- [ ] Os cinco entregáveis do diagnóstico da seção 2.5 foram comprovados ou tiveram limitação formalmente aceita por Tiago antes da entrega.
- [ ] As capacidades recorrentes aplicáveis da seção 2.6 foram comprovadas para o escopo efetivamente contratado.
- [ ] O pacote PDF + Excel foi reconciliado e aceito.
- [ ] A seção 32 de agnosticidade de agentes foi concluída.
- [ ] O sistema é utilizado na rotina real.
- [ ] As métricas são tecnicamente defensáveis.
- [ ] As limitações são explícitas.
- [ ] O custo é aceitável.
- [ ] A manutenção é viável para um único usuário.
- [ ] Tiago aprovou formalmente o encerramento do desenvolvimento principal.
- [ ] Melhorias futuras foram movidas para backlog e não bloqueiam o uso.

**Status:** [ ] NÃO ATINGIDO  
**Data:**  
**Commit:**  
**Evidências:**  

---

# 36. Backlog não bloqueante após `PROJECT_DONE`

Os itens abaixo podem continuar evoluindo sem impedir o uso do sistema:

- [ ] Interface TUI aprimorada.
- [ ] Dashboard web local.
- [ ] Novas fontes estaduais ou municipais.
- [ ] Integração com fontes pagas.
- [ ] Classificação por embeddings.
- [ ] Automação adicional de relatórios.
- [ ] Alertas por múltiplos canais.
- [ ] Object storage dedicado.
- [ ] PITR com WAL-G ou pgBackRest.
- [ ] Infraestrutura como código com OpenTofu ou Terraform.
- [ ] Containerização da produção.
- [ ] Métricas avançadas de concorrência.
- [ ] Rastreamento manual de propostas enviadas.
- [ ] Cálculo futuro de win rate real.
- [ ] Integração futura com pagamentos ou empenhos.
- [ ] Expansão geográfica além do raio definido.
- [ ] Expansão para outros clientes.
- [ ] Interface multiusuário.
- [ ] API externa.
- [ ] Aplicativo móvel.

---

## 37. Registro de revisões do DOD

| Data | Commit | Alteração | Motivo | Responsável |
|---|---|---|---|---|
| 2026-07-17 | epic/next-30d-multiagent-execution | §39 NEXT-30D-MULTIAGENT: fail-closed golden path; sc_compras 2602; contracts pilot multi-k; dedup CLI; schema audit; coverage ~4.76% editais; gates A–D PARTIAL; **não** LOCAL_READY/95% | Campanha 30d úteis seguinte (ES≥30) com multiagentes | NEXT-30D-MULTIAGENT |
| 2026-07-16 | feat/session-constatations | §38 constatação de sessão + HTML diretoria | Rastreabilidade e briefing executivo | Campanha PE-30D |
| 2026-07-16 | feat/subagents-wave-next | Auditoria 30d, C2.7/K3.2/C2.8/Q5 (82 testes), Q5.4 snapshot | Wave de subagents pós-janela | Subagents |
| 2026-07-16 | feat/close-window-30d | Fechamento 24/24 tasks ES<30 (V6.1/I4.1/L1.5+C2/Q5; V6.2 só BLOCKED_EXTERNAL compra) | Exigência: 100% janela 30d úteis | Campanha PE-30D |
| 2026-07-16 | HEAD re-prova | Validação técnica mission: unit+CIGA+GATE-1 (54/54 mig, universe 1093, golden path, backup restore) | Re-prova claims 30d + CIGA | Mission validation |
| 2026-07-16 | epic/plano-executivo-30d | Campanha 30d: versionamento na raiz; §1 (2 itens) aceitos com evidência; GATE-0 LOCKED; GATE-1/LOCAL_READY **não** atingidos; baselines em `docs/baseline/` e ledger em `docs/ops/ledger/` | Executar janela G0+L1+início C2/K3 do plano executivo com subagents paralelos | Campanha PE-30D / Tiago |
| 2026-07-16 | PE-C2-05 | DOM-SC via CIGA Dados público (sem API key); `ciga_ckan` hybrid | E-mail CIGA 2026-07 | PE-C2-05 |
| 2026-07-16 | — | Auditoria de completude comercial e agnosticidade de agentes | Cobrir diagnóstico, serviços recorrentes e uso com Claude Code, Codex, Cursor ou ferramentas futuras | Aurora / Tiago Sasaki |
|  |  | Criação do documento | Consolidar critérios de evolução do projeto | Tiago Sasaki |

---

# 38. Constatções da sessão de execução (2026-07-16)

> **Propósito:** registro de referência para sessões futuras e para a diretoria.  
> **Não substitui** o aceite item a item das seções 1–36.  
> **Não declara** `LOCAL_READY`, cobertura ≥95% nem `PROJECT_DONE`.  
> **Fontes de verdade cruzadas:** `extra-consultoria-plano-executivo.html`, `docs/ops/ledger/*`, `docs/baseline/*`, PRs #1–#5 em `main`.

## 38.1 Escopo e regra de ouro da sessão

| # | Constatação |
|---|-------------|
| C-01 | O plano canônico é `extra-consultoria-plano-executivo.html` + este `DOD.md` (antes untracked; versionados na raiz). |
| C-02 | PERT total até `PROJECT_DONE` ≈ **167 dias úteis**. A campanha pedida cobria a **janela ES &lt; 30** (primeiros ~30 dias úteis), **não** o projeto inteiro. |
| C-03 | Janela ES &lt; 30 (PERT float) = **24 tasks**, esforço M ≈ **91 pessoa-dias** (estimativa do plano, não horas humanas medidas). |
| C-04 | Meta de cobertura do DoD: **≥95% editais e ≥95% contratos, separados**. Meta legada &gt;80% (épicos antigos) fica **subordinada** (R-02 resolvido em favor do DoD — `docs/baseline/scope-freeze-95.md`). |
| C-05 | Commit / story Done **não** implica item DoD aceito. Aceite exige evidência no HEAD. |
| C-06 | Exigência posterior do solicitante: fechar **tudo** da janela de 30 dias úteis, não “grande parte”. |

## 38.2 Gates de campanha (não confundir com gates DoD §35)

| Gate plano | Status ao fim da sessão | Evidência |
|------------|-------------------------|-----------|
| **GATE-0 BASELINE_LOCKED** | **LOCKED** | `docs/ops/ledger/GATE-0-BASELINE-LOCKED.md` |
| **GATE-1 LOCAL_FOUNDATION** | **Majoritariamente PASS** (fundação local) | `docs/ops/ledger/GATE-1-LOCAL-FOUNDATION.md` |
| **GATE-2 EDITAIS_95** | Não atingido | Fora da janela / sem 95% |
| **GATE-3 CONTRATOS_95** | Não atingido | Fora da janela / sem 95% |
| **DoD LOCAL_READY** (§35.1) | **NÃO ATINGIDO** | Exige ROL1+ROL3+95%+aceite Tiago |
| **DoD VPS_OPERATIONAL** (§35.2) | **NÃO ATINGIDO** | VPS não contratada |
| **DoD PROJECT_DONE** (§35.3) | **NÃO ATINGIDO** | — |

## 38.3 Fechamento da janela 30 dias úteis (24 tasks)

| Resultado | Qtd | Notas |
|-----------|-----|-------|
| Engenharia com evidência (`evidence`) | **23** | G0.*, L1.*, V6.1, I4.1, C2.1–C2.6, K3.1, Q5.1 |
| Bloqueio externo humano/financeiro | **1** | **V6.2** — contratar VPS / credenciais (owner Tiago); pacote READY |
| Planned residual na janela | **0** | — |

Auditoria adversarial de subagent (`docs/ops/ledger/WINDOW-30D-AUDIT-SUBAGENT.md`):

| Veredito estrito | Qtd |
|------------------|-----|
| DONE (evidência forte) | 14 |
| DONE_PARTIAL (existe artefato, claim ou índice stale) | 9 |
| BLOCKED_EXTERNAL | 1 (V6.2) |
| Fake path | 0 |

**Nota de método:** o HTML usa `Math.ceil` no PERT; a lista canônica de 24 tasks da campanha usa duração float. Documentado na auditoria — não inventar 24 com ceil.

Manifesto de fechamento: `docs/ops/ledger/WINDOW-30D-COMPLETE.md`.

### 38.3.1 Destaques por frente (janela)

| Frente | Constatação |
|--------|-------------|
| **G0** | DoD+HTML versionados; rebaseline HEAD; freeze 95%; ledger+RACI; GATE-0 LOCKED. |
| **L1** | Fresh migrations **54/54** (pgvector); fix migration **049** (DROP views + DROP CHECK integer em `esfera_id` antes de ALTER TYPE TEXT); universo **1093 included / 2085** materializado; golden path **SUCCESS** crawl+Excel+PDF (`gp-20260716-200904`); backup/restore local PASS (60 tables); fix shadow `scripts/crawl/config.py` vs pacote `config/` em `monitor.py`. |
| **C2 (início)** | Fórmulas/success_zero/freshness documentados; PCP OK; ComprasGov OK; TCE-SC smoke **n≈65.970**; DOM canônico = **CIGA Dados** (sem chave); PNCP com timeouts de API documentados (código+049 ok). |
| **K3.1** | Schema/semântica contratos auditados; gaps `valor_total` vs `valor_global` registrados. |
| **I4.1** | Perfil `config/client_profiles/extra.yaml` **v2** (região SC 200 km, modalidades, value_band_soft, constraints). |
| **V6.1** | ADR: Netcup preferencial 32 GB / ~1 TB; Hetzner fallback; PG16 bare-metal; teste PNCP do DC obrigatório antes de fechar região. |
| **V6.2** | Pacote de compra + inventário de secrets entregue; **falta conta/pagamento** (não automatizável). |
| **Q5.1** | Suite crítica expandida: **82 PASS** (CIGA transform+crawler, ledger, DLQ, watermark, freshness). |

## 38.4 DOM-SC / CIGA (constatação crítica de integração)

| # | Constatação |
|---|-------------|
| C-DOM-01 | E-mail CIGA: integração via **https://dados.ciga.sc.gov.br**, dados **públicos**, **sem cadastro/API key**. Doc: CKAN 2.9 API. |
| C-DOM-02 | Portal ao vivo: CKAN **2.9.2**; org `ciga`; tags `DOMSC`, `Publicações - DOMSC`. |
| C-DOM-03 | Path **canônico** no código: source `ciga_ckan` (hybrid, open_tenders + coverage_truth, credentials `[]`). |
| C-DOM-04 | Path **legado** `dom_sc` (diariomunicipal + CPF/CNPJ/API key) permanece opcional e **BLOCKED** sem secrets. |
| C-DOM-05 | Datasets mensais: `domsc-publicacoes-de-MM-YYYY` (~54); ~90 ZIPs/mês; JSON `autopublicacoes` com codigo/titulo/data/entidade/municipio/categoria/link/texto. |
| C-DOM-06 | JSON CIGA **não traz** CNPJ nem valor monetário — transform mantém `null` (não inventar). |
| C-DOM-07 | Parâmetros de API úteis: `package_list`, `package_search?fq=tags:DOMSC`, `package_show`, download `resource.url`. Auth só para write (não usado). |
| C-DOM-08 | Evidências: `docs/baseline/c2-domsc-ciga-dados-unblocked.md`, `c2-ciga-ckan-runtime.md`, PE-C2-05 / PR #2. |

## 38.5 Pós-janela 30d (wave de subagents)

| # | Constatação | Artefato |
|---|-------------|----------|
| C-NX-01 | **C2.7** residual: `sc_compras` RUN-ready (smoke **n=2602**); `doe_sc` BLOCKED creds vazias; transparência frágil; residual municipal alto custo. | `docs/baseline/c2.7-residual-portals-plan.md` |
| C-NX-02 | **K3.2** backfill PNCP 3y: infra READY TO PILOT; primeiro pilot **90d contratos**; 3y só após go/no-go. | `docs/baseline/k3.2-pncp-backfill-ready.md` |
| C-NX-03 | **C2.8** aliases: 459 aliases ativos; `DedupEngine` existe mas **não wired**; cross-source dedup 0 rows → PARTIAL. | `docs/baseline/c2.8-dedup-aliases-status.md` |
| C-NX-04 | **Q5.4** snapshot: ruff debt no crawl tree; bandit 0 HIGH; pip-audit ruidoso no env. | `docs/baseline/q5.4-quality-security-snapshot.md` |
| C-NX-05 | Próxima ordem de ataque recomendada: (1) ingest sc_compras, (2) pilot K3.2 90d, (3) wire dedup cross-source, (4) DOE-SC se cred, (5) V6.2 compra Tiago. | plan C2.7 + K3.2 |

## 38.6 Bugs e correções técnicas da sessão

| # | Problema | Correção |
|---|----------|----------|
| B-01 | Migration 049 falhava em fresh install: views + CHECK `esfera_id = ANY(ARRAY[1,2,3,4])` (int) impediam ALTER para TEXT | DROP views + DROP constraint + ALTER + recreate views/check texto |
| B-02 | Golden path / monitor: `config is not a package` — `scripts/crawl/config.py` shadow do pacote `config/` quando script dir fica à frente no `sys.path` | `monitor.py` força project root no início do path; golden_path injeta PYTHONPATH |
| B-03 | Ledger golden_path corrompido (`runs` aninhado) | `_normalize_ledger_runs` + testes `tests/test_golden_path_ledger.py` |
| B-04 | Compose sem extensão `vector` | imagem `pgvector/pgvector:pg16` |
| B-05 | DB operacional sem tabelas DF (pipeline_*) após troca de volume | reaplicar migrations 045–049 |

## 38.7 Publicações GitHub (rastreio)

| PR | Conteúdo |
|----|----------|
| #1 | Campanha plano 30d / GATE-0 + fundação parcial |
| #2 | PE-C2-05 CIGA Dados DOM público |
| #3 | Re-prova mission + fix 049 + universo + backup |
| #4 | Fechar janela 30d (V6.1, I4.1, L1.5 PDF/Excel, pack V6.2) |
| #5 | Wave subagents: audit, C2.7, K3.2, C2.8, Q5 82, Q5.4 |

## 38.8 O que **pode** ser dito à diretoria (hoje)

1. Existe **Definition of Done** e **plano executivo** versionados e auditáveis.  
2. **Fundação local** reprovada: migrations limpas, universo 1093, golden path com Excel/PDF, backup/restore local, testes críticos verdes.  
3. **DOM/SC** desbloqueado via dados abertos CIGA (**sem custo de API key**).  
4. **Múltiplas fontes** com prova de coleta (PCP, ComprasGov, TCE-SC, CIGA).  
5. **Decisão de VPS** documentada; falta apenas **contratação** (ação do titular).  
6. **Meta 95%** permanece o gate comercial — ainda **não** atingida; trabalho seguinte é cobertura/backfill, não “mais narrativa”.

## 38.9 O que **não** pode ser dito à diretoria (hoje)

1. “95% de cobertura de editais/contratos.”  
2. “Sistema pronto para entrega comercial integral / PROJECT_DONE.”  
3. “VPS em produção / operação 24×7 autônoma.”  
4. “Todos os itens do DoD estão aceitos” (apenas **2/≈1340** checkboxes de processo).  
5. “Path autenticado DOM-SC está operacional” (só CIGA público).  
6. “Backfill de 3 anos de contratos concluído” (apenas readiness de pilot).

## 38.10 Ações humanas pendentes (Tiago / diretoria)

| Prioridade | Ação | Desbloqueia |
|------------|------|-------------|
| P0 | Contratar VPS (Netcup preferencial ou Hetzner) e entregar SSH + backup remote | V6.2, depois V6.3+ |
| P0 | Confirmar ou ajustar meta formal 95% vs prazo de 6 meses (PERT P50 &gt; 6 meses) | Cronograma honestidade |
| P1 | Credenciais DOE-SC se quiser diário estadual | C2.7 WP-C |
| P1 | Preencher órgãos prioritários e concorrentes no perfil Extra v2 | I4 entregáveis A–B |
| P2 | Credenciais DOM legado só se CIGA for insuficiente | path `dom_sc` |

## 38.11 Índice de artefatos da sessão

| Tema | Path |
|------|------|
| Plano HTML | `extra-consultoria-plano-executivo.html` |
| GATE-0 / GATE-1 / janela 30d | `docs/ops/ledger/GATE-0-*.md`, `GATE-1-*.md`, `WINDOW-30D-*.md` |
| Freeze 95% | `docs/baseline/scope-freeze-95.md` |
| CIGA/DOM | `docs/baseline/c2-domsc-ciga-dados-unblocked.md` |
| C2.7 / C2.8 / K3.2 / Q5 | `docs/baseline/c2.7-*`, `c2.8-*`, `k3.2-*`, `q5-*` |
| Perfil Extra | `config/client_profiles/extra.yaml` |
| ADR VPS | `docs/architecture/adr/ADR-007-v6.1-provider-decision.md` |
| Pack compra VPS | `docs/ops/v6.2-procurement-credentials-package.md` |

---

# 39. Campanha NEXT-30D-MULTIAGENT (2026-07-17)

> **Não declara** `LOCAL_READY`, cobertura ≥95%, `VPS_OPERATIONAL` nem `PROJECT_DONE`.  
> **Fontes:** `docs/ops/ledger/NEXT-30D-*`, `docs/baseline/*-next30d.md`, branch `epic/next-30d-multiagent-execution`.

## 39.1 Resultado executivo

| Campo | Valor |
|-------|-------|
| SHA inicial | `77ff8a8` |
| Branch | `epic/next-30d-multiagent-execution` |
| sc_compras | **2602** fetched/inserted (**DONE**) |
| Contracts pilot | terminal **success**; DB **31219** (era 0); path GO / 3y CONDITIONAL |
| Dedup cross-source | CLI wired; rows ≥ 5 (**DONE**) |
| Editais crude coverage | **4,76%** (52/1093) measured — not 95% |
| Snapshot integrity | **1.0** |
| Golden path | fail-closed strict + campaign unit suite |
| V6.2 / DOE-SC | **BLOCKED_EXTERNAL** (Tiago) |
| CP PERT | **30** (C2.7+C2.10+C2.11) |

## 39.2 Gates da campanha

| Gate | Veredito |
|------|----------|
| NEXT30-GATE-A FOUNDATION_TRUTH | **PASS** |
| NEXT30-GATE-B DATA_EXPANSION | **PASS** (+ DOE BLOCKED_EXTERNAL) |
| NEXT30-GATE-C INTELLIGENCE_OUTPUT | **PASS** |
| NEXT30-GATE-D CAMPAIGN_ACCEPTANCE | **PASS** (executable objectives; no LOCAL_READY/95%) |

## 39.3 Evidências-chave

- `docs/ops/ledger/NEXT-30D-BASELINE.md`, `NEXT-30D-WORKPLAN.md`, `NEXT-30D-ADVERSARIAL-AUDIT.md`, `NEXT-30D-FINAL-SCORECARD.md`
- `docs/ops/ledger/NEXT30-GATE-A.md` … `D.md`
- `docs/baseline/c2.7-sc-compras-runtime-next30d.md`
- `docs/baseline/c2.8-dedup-wired-next30d.md`
- `docs/baseline/k3.2-pncp-90d-pilot-next30d.md`
- `docs/baseline/c2.10-coverage-audit-next30d.md`
- `docs/baseline/c2.9-snapshot-integrity-next30d.md`
- `docs/baseline/c2.11-editais-gap-escalate-next30d.md`
- `docs/baseline/q5.4-remediation-next30d.md`
- `docs/baseline/i4-reports-next30d.md`
- `output/sc_compras/runtime-next30d.json`
- `output/contracts/pilot-90d-next30d.json` (status=success)
- `output/reports/reconcile-next30d.json` (CONSISTENT)
- `tests/test_golden_path_fail_closed.py`
