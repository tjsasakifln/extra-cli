# Contexto documental para notícias, 2026-11-20

## Escopo e estado

`IMPLEMENTED + FIXTURE_PROVEN`, com uma consulta documental real isolada.
Não há aceite de recorrência nem de publicação pelo consumidor nesta evidência.
O enriquecimento permanece no produtor `extra-cli`, sem mutação do Data Lake,
projeção Radar, plano comercial, timers ou credenciais do host.

O contrato v1 recebe contexto opcional de compra vinculada e anexos do próprio
contrato. A versão de contexto é `confenge.contract-news-context/v1`. O pacote
inclui um extrator PDF offline verificável para funcionar com Python `-S` mesmo
sem Poppler instalado. Os textos são insumos privados de apuração; a publicação
deve conservar somente referências e afirmações efetivamente verificadas.

## Verificação

- 109 testes focados passaram, incluindo os 76 testes anteriores do produtor.
- Testes novos recusam identidade divergente, URL de anexo não vinculada,
  endpoint antigo com erro JSON/HTTP 200, valores não finitos, ultrapassagem dos
  limites de chamadas/páginas, adulteração da dependência e falsa cobertura
  completa quando um documento falha.
- A auditoria identificou disputa das duas vagas documentais por notícias
  publicadas estáveis. A correção reserva uma vaga para recheck e outra para
  novidade, preserva a ordem enviada pelo consumidor e gira novas candidatas
  a cada quatro horas. Testes demonstram que duas publicadas não impedem uma
  nova, que a próxima janela avança após candidata ilegível e que todas as
  posições do conjunto limitado são alcançadas, inclusive além da sexta.
- Um PDF sintético válido é extraído pelo pypdf real em subprocesso `python -S`
  com Poppler indisponível no teste. Não exige rede nem instalação no host.
- Ruff passou nos arquivos alterados de código e testes.
- Consulta isolada confirmou a compra
  `19493732000199-1-000101/2026`, vinculada ao contrato
  `19493732000199-2-000329/2026`. A compra declara credenciamento, processo 102,
  número 36 e valor estimado de R$ 139.800.261,37. Esse valor coincide com o
  campo global do registro contratual, sem comprovar ordem de execução ou pagamento.
- Dois anexos oficiais foram lidos localmente: termo de credenciamento de onze
  páginas e contrato de execução de vinte páginas. O segundo delimita iluminação
  de cemitério em Conquista/MG e valor estimado de R$ 54.674,84. A distinção entre
  esses instrumentos é material para a notícia e depende da revisão editorial.
  O segundo anexo também contém páginas sem texto extraível: o resultado registra
  cobertura textual parcial, sem afirmar leitura de plantas ou imagens.
- A consulta completa pelo produtor, com transporte real de contrato, compra,
  listagem e dois PDFs, terminou com cinco requisições e sem erros de contexto.
  Foi uma verificação isolada, sem leitura do Data Lake de produção ou publicação
  do consumidor, e não comprova recorrência.

Fontes públicas da consulta isolada:

- https://pncp.gov.br/app/contratos/19493732000199/2026/329
- https://pncp.gov.br/app/editais/19493732000199/2026/101
- https://pncp.gov.br/pncp-api/v1/orgaos/19493732000199/contratos/2026/329/arquivos/1
- https://pncp.gov.br/pncp-api/v1/orgaos/19493732000199/contratos/2026/329/arquivos/2

## Comandos e aceite restante

```bash
python -m pytest tests/public_exports/test_contract_news.py \
  tests/public_exports/test_contract_news_context.py -q -o addopts='' --tb=short
python -m ruff check scripts/public_exports/contract_news.py \
  scripts/public_exports/contract_news_context.py scripts/public_exports/pdf_extract.py \
  scripts/public_exports/package_contract_news.py tests/public_exports/test_contract_news.py \
  tests/public_exports/test_contract_news_context.py
python -m scripts.ops.check_generated_artifacts_policy --base origin/main
python -m scripts.ops.check_pr_reviewability --base origin/main
```

Restam revisão independente, CI do SHA exato, fixação desse produtor no consumidor
web, execução produtiva, leitura do resultado público e observação da rotina.
Reversão: retornar o pin produtor e o consumidor ao conjunto anteriormente aceito,
preservando o ledger e os arquivos privados de apuração.

## Correção da seleção documental em 2026-11-21

Na Netcup, dois lotes confirmaram 17 registros cada e não iniciaram nova
apuração. Cada lote testou somente um novo contrato, além do recheck da matéria
já publicada. O PNCP listou um PDF de 9.898.732 bytes para a primeira candidata
inviável. No outro lote, o extrator registrou `document_page_limit_or_invalid`.
A seleção passa à próxima candidata no mesmo lote, dentro dos limites
documentados. O teste de regressão cobre a substituição após falha de PDF na
presença de recheck já publicado. O aceite produtivo depende de rodar o bundle
aprovado e verificar a publicação pública pelo consumidor.

O diagnóstico também encontrou contratos legíveis de 8 a 14 páginas cujo texto
ultrapassava o limite anterior de 32.000 caracteres. Aumentar o limite de texto
para 64.000 permite aproveitar esses PDFs sem truncar o conteúdo. A verificação
de integridade do Radar recebe prazo próprio, já que o `quick_check` excedeu
30 segundos em replays na Netcup.
