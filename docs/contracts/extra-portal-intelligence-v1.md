# Projeção privada do Radar da Extra

Contrato `confenge.extra-intelligence/v1`, proprietário `extra-cli`. O consumidor
é o portal autenticado de `web-cfg`. Extração e avaliação de escopo são
distintas. O banco é consultado em transação única `REPEATABLE READ READ ONLY`.
Não se publica uma cópia da base nem se concede acesso ao site ou navegador.

## Inclusão, triagem e auditoria

- Descoberta inclui o recorte administrativo SC **e** uma busca limitada por
  menções a SC em registros publicados por entes externos. Não use busca
  textual para afirmar o local da obra. O filtro de palavras-chave ordena a
  fila de revisão e não elimina resultados sem palavras, como “implantação
  de elevatória”. Registro identificado fora da amostra pode ser revisto
  pela identidade canônica.
- A classificação afirma **execução física** de uma obra, não compra de
  materiais nem projeto sem execução. Consulte edital, TR, projetos, contrato e
  retificações. Aponte cada documento/trecho e SHA-256. Liste todos os locais
  da unidade contratada. Não use endereço, município ou UF do órgão.
- Um registro de revisão é congelado por impressão digital da linha de origem.
  Mudança material, duplicata, evidência insuficiente ou vínculo ausente volta
  à fila. Para exclusão definitiva, registre evidência e motivo demonstrável.
  Falta de informação não é exclusão. Origem oficial e identidade são validadas
  no documento antes da confirmação. Abrir o documento mais recente faz parte
  da revisão, inclusive aditivos que ampliem território ou prazo.
- O portal aplica a regra geográfica de São José/SC e reconfirma datas, status
  e semântica. Itens em revisão não entram na interface de decisão ou CSV.
  Cobertura do rastreio é parcial, especialmente nacional e para documentos
  sem local explícito. Auditar separadamente casos promovidos e uma amostra
  dos excluídos/pendentes, com estratos sem palavras-chave, entes externos, obras
  com mais de um local e municípios limítrofes. Denominadores por tipo são da
  consulta, não taxas de cobertura de todos os editais; não alegar 100%.

## Envelope e registro de revisão

O envelope contém `schema`, `scope=extra-sc-sao-jose-200/v1`, `producer=extra-cli`,
`mode=OFFICIAL_LIVE`, `generatedAt` (UTC), `sourceCut` (timestamp transacional),
`coverage.notices` e `coverage.contracts` (janela, quantidade consultada, não
revisados e truncamento), e `records` limitado a 1.000 e 2 MiB. A janela é a do
rastreio de novos casos. Contratos identificados e revisados podem ser mais
antigos e não são descartados pela janela de rastreio. `sourceCut` não é
horário de coleta de cada documento. Registros sem verificação operacional
recente não podem ser chamados de editais abertos.

Registro privado `{"schema":"extra-portal-review/v1","reviews":[]}`. Campos
de cada revisão:

| Campos | Semântica |
|---|---|
| `kind`, `key`, `fingerprint` | Tipo e identidade do registro na fila e impressão digital correspondente. |
| `reviewer`, `decision` | Responsável privado e `verified` ou `exclude`. |
| `physicalWork`, `family` | `true` para execução física. Famílias publicadas: edificacoes, viaria, saneamento, especiais, outras_obras. |
| `scopeEvidence`, `execution` | Documento com `kind,url,sha256,locator`. `execution` tem `basis=all_execution_sites` e `sites` com `code` do IBGE e `evidence` por local. Para município limítrofe, informar `point={lat,lon,uncertaintyM,evidence}` comprovado. |
| `statusEvidence`, `firstCheck` | Vínculo ao ato que permite verificar situação e prazo. Primeira verificação é uma ação, não uma conclusão de habilitação. |
| `endConflict`, `endEvidence` | Só `false` quando não há conflito de vigência comprovado; o aditivo/contrato precisa preservar o vínculo e a última data. |
| `amount` | Opcional. Somente com `type,cents,evidence`, sem presumir semântica pelo consolidado da base. |
| `comparison`, `reason` | Diferença documentada para comparação ou motivo de exclusão demonstrável. |

## Operação reversível na Netcup

O plano de produção usa um papel local dedicado e apenas SELECT por coluna.
Provisionar via `deploy/extra-portal/provision.sql` com administrador e usuário
de sistema homônimo `confenge-extra-intel`. Usar a venv operacional do
`extra-cli`, um checkout fixado do produtor em
`/opt/confenge-extra-portal/current`, diretório de projeção SGID 2750
`/var/lib/confenge-extra-portal` (dono produtor, grupo confenge-web), e registro
`/etc/confenge-extra-portal/review.json` do root com leitura pelo produtor.
Validar o serviço antes de habilitar `extra-portal-projection.timer`. A troca
atômica de um arquivo 0440 não substitui a última projeção válida em caso de
falha. O timer consulta cargas persistidas em até cinco minutos, sem depender
do agendamento de um crawler. Esse intervalo não prova a atualidade das fontes.

Exemplo operacional que retorna candidatos, não decisões:

```bash
runuser -u confenge-extra-intel -- /opt/extra-consultoria/.venv/bin/python \
  -m scripts.public_exports.extra_portal --register /etc/confenge-extra-portal/review.json \
  --review-queue contract --queue-size 25
```

O consumidor registra o caminho `EXTRA_PORTAL_INTELLIGENCE_PATH` no ambiente
do runtime (não no artefato web). Desabilitar o timer e retirar o caminho do
ambiente reverte a integração sem reverter o banco ou a PR 903.
