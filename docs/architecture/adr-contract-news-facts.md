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
