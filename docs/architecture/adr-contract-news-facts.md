# ADR: fatos oficiais para notícias de contratos

- Data: 2026-11-19
- Estado: `EXECUTE_NOW`, implementação local sujeita aos gates do SHA aprovado
- Escopo: produtor de fatos públicos; não altera ingestão nem plano comercial

## Problema

O site CONFENGE precisa publicar notícias sobre contratos relevantes de engenharia
a partir da base já coletada. O campo histórico `valor_total` combina origens
semânticas diferentes e não prova, isoladamente, o valor contratado. O objeto
persistido também pode estar truncado. A redação não pode converter essas
heurísticas em fatos, estimativas em contratos, empenhos em obras ou a sede do
órgão em local de execução.

## Decisão

`extra-cli` produz `confenge.contract-news-facts/v1`. A base persistida fornece
somente identidades candidatas. O produtor confirma até vinte identidades por
execução nos respectivos detalhes oficiais do PNCP, sem paginação ou varredura
adicional. Até cinco consultas são reservadas à revisão de notícias publicadas.
O site fornece os IDs conhecidos e os IDs devidos para revisão.

A produção usa o snapshot existente `confenge.market-radar/v1`, cujo diretório
já é legível pelo usuário de deploy web. O produtor valida contrato, estado,
idade, tamanho, digest, arquivo imutável, integridade e estrutura SQLite. O
SQLite é aberto somente para leitura, pelo mesmo descritor cujo digest foi
conferido, sem carregar extensões ou executar schema não confiável. As consultas
possuem limite, parâmetros separados e prazo máximo. O ID PNCP é reconstruído
apenas de uma URL oficial canônica e conferido contra o ID opaco da projeção.

O caminho PostgreSQL permanece disponível para operação já autorizada com papel
somente SELECT. A transação repetível e somente leitura termina antes das
consultas HTTP. Nenhum grant é criado pelo exportador.

O valor histórico pode ordenar a busca preliminar limitada. Somente
`valorGlobal` positivo, ou `valorInicial` positivo quando o primeiro está ausente
ou zerado, entra no contrato de saída. O nome do campo acompanha o valor como
string decimal. A ordenação final usa exclusivamente os valores confirmados.
Essa seleção não representa uma classificação nacional exaustiva.

São elegíveis apenas contrato inicial (`tipoContrato.id=1`), despesa,
fornecedor pessoa jurídica com CNPJ válido, objeto completo e pertinente à
engenharia, identidade consistente e publicação nos últimos sete dias do
calendário brasileiro. Correções explícitas podem consultar publicações mais
antigas. Contatos e identificadores pessoais são removidos dos textos. Datas
ausentes continuam nulas. A localização é administrativa, sem inferência sobre
o local da obra. Estimativas, empenhos, receitas e instrumentos de tipo diferente
não entram na primeira versão.

## Enriquecimento documental autorizado em 2026-11-20

A solicitação do fundador exige qualidade editorial além da reescrita do
registro. O produtor acrescenta `editorial_context` opcional ao contrato v1,
preservando os campos e limites da confirmação inicial. O contexto contém a
contratação explicitamente vinculada por `numeroControlePncpCompra` e anexos
listados pelo próprio contrato. Nenhuma relação é inferida por similaridade de
texto, valor, fornecedor ou município.

A API vigente de compras usa `/api/consulta/v1/orgaos/.../compras/...`. A resposta
de erro JSON que o caminho antigo devolve com HTTP 200 é recusada por identidade.
São no máximo cinco compras distintas, com reaproveitamento dentro da rodada,
duas vagas documentais, seis listagens e seis PDFs na rodada, com até três PDFs
por contrato. Todo o enriquecimento tem prazo máximo
de 120 segundos. Uma vaga documental pertence ao primeiro recheck na ordem do
consumidor, que prioriza atualização editorial e a consulta documental mais
antiga. A outra pertence a uma candidata nova, em rodízio por janelas sucessivas
de quatro horas dentro do conjunto limitado ordenado pelo valor oficial.
Quando uma das classes está vazia, a outra pode usar as duas vagas. Se um lote
novo encontra um anexo indisponível ou não obtém contexto suficiente, a vaga
passa à próxima candidata do rodízio na mesma execução, até cinco tentativas.
As compras das candidatas sondadas têm prioridade no orçamento de cinco
consultas. As métricas desse contexto são separadas das vinte
confirmações de contrato, que permanecem preservadas para todos os rechecks.

Os anexos são lidos apenas em URLs derivadas da identidade exata e confirmadas
na listagem oficial, sem redirecionamentos. Cada PDF tem limite de 2 MiB e vinte
páginas. Extração tem limites de CPU, memória, tempo e saída; usa Poppler quando
disponível ou uma wheel pypdf de versão e digest fixados, incluída no bundle.
O fallback roda em processo `python -S` separado, sem instalação ou rede no host.
O texto saneado é evidência privada para apuração, com até 32.000 caracteres por
documento. A publicação não deve transportar esse texto nem dados de signatários.
Fonte, identificador, título, digest e data de consulta permitem rastreabilidade.

`documents_status` informa `complete`, `partial`, `unavailable` ou
`not_collected`; zero anexos confirmados não prova inexistência de contratação.
Documento excedente, ilegível, criptografado ou indisponível nunca recebe
alegação de leitura integral. A modalidade, o valor estimado da compra e o valor
do campo contratual permanecem conceitos separados, mesmo quando os números
coincidem. Anexo de execução específico não substitui silenciosamente o valor
do contrato de credenciamento. A interpretação e as ressalvas materialmente
necessárias pertencem à redação e à revisão do consumidor.

## Responsabilidade e execução

- `extra-cli`: identidade, fonte oficial, confirmação, semântica, seleção
  limitada, fatos e motivos de exclusão.
- `web-cfg`: seleção editorial final, OpenAI, limites de publicação, verificação
  do texto, conteúdo público, SEO, conversão, correções e histórico privado.
- O workflow web em `main` executa a cada quatro horas, no minuto 55, depois da
  cadência existente do Radar. Ele instala em área privada um bundle do produtor
  fixado em SHA aprovado. Não altera o checkout operacional do coletor.
- A execução usa `/var/lib/confenge-web/contract-news/private` para fatos e
  estado; o conteúdo renderizado pertence a
  `/var/lib/confenge-web/contract-news/public`.

Não há timer de sistema novo, novo grant, exigência de root, dependência entre
ingestão e plano comercial, mutação de contratos, feed, campanha ou SMTP. O modo
Radar utiliza somente a biblioteca padrão Python. O empacotador registra cada
arquivo e seu SHA-256 em manifesto, incluindo a identidade do commit produtor.

## Falhas, evidência e reversão

Arquivo obsoleto, digest divergente, schema inesperado, concorrência e
indisponibilidade total da fonte não substituem o último arquivo válido. A
gravação é atômica. Falha desta rotina não bloqueia o Radar nem o coletor.
Uma revisão individual informa `verified`, `ineligible` ou `unavailable`; a
decisão editorial pertence ao consumidor.

Testes de fixture demonstram o contrato e a integração local SQLite. Aceite em
produção exige CI do SHA exato, execução no host com a identidade esperada,
fatos reais rastreáveis e observação de execução agendada. A primeira execução
isolada não comprova recorrência. A reversão desabilita o agendamento web ou
retorna o SHA do bundle e o consumidor aprovados anteriormente, preservando o
estado privado para auditoria.

Contrato operacional: `docs/contracts/contract-news-facts-v1.md`.

## Referências oficiais

- [Consultar contrato ou empenho](https://pncp.gov.br/manual/pt-br/latest/contrato_empenho/consultar_contrato_ou_empenho.html)
- [Consultar tipos de contrato](https://pncp.gov.br/manual/pt-br/latest/tabelas_de_dominio/consultar_tipos_de_contrato.html)
- [Manual oficial da API de consultas, versão 1.0](https://www.gov.br/pncp/pt-br/pncp/manuais/ManualPNCPAPIConsultasVerso1.0.pdf/@@display-file/file)
