# Handoff — projeção pública do Radar de Mercado Público (2026-11-09)

## Estado de entrega

O produtor da [PR #582](https://github.com/tjsasakifln/extra-cli/pull/582) foi
instalado de `9f6ea98ca211166be4a47eb846080ba55b718a79`; o
[CI de main 42640898048](https://github.com/tjsasakifln/extra-cli/actions/runs/42640898048)
foi bem-sucedido. A execução manual de 12:24:07–12:29:26 BRT confirmou
`2.119.086` registros, `2.036.903.936` bytes e digest
`0a87278080d536fd976db310f2d6c49bc218ce848880d059a71f36d6bb14adb2` em
`radar-producer-final-verification.json`.

A primeira ocorrência agendada, 14:22:02–14:26:42 BRT, durou 280 s e terminou
com saída zero; publicou o digest
`54c7fab3403fc592005438584b23a6867ee31d9d54bb355e1849dc27f4f2c36c`.
`radar-producer-first-scheduled-2026-11-09.json` registra `source_as_of`
2026-11-09T17:22:02.347128Z, `generated_at` 2026-11-09T17:22:04.196337Z e
`ingestion_latest_at` 2026-11-09T15:18:10.298403Z. A leitura do consumidor foi
somente para ponteiro/snapshot e confirmou digest, quick-check SQLite,
metadados e contagem. O pico foi 2.143.817.728 bytes, com eventos de memória
zero sob `MemoryMax=2 GiB`; isso não demonstra folga de capacidade.

A segunda ocorrência foi observada entre 18:22:00–18:26:59 BRT: 299 s,
186,709 s de CPU, saída zero e `LastTrigger` do timer igual ao início do
serviço. Sua verificação somente-leitura confirmou o digest
`208ad74b98ce5635e811340d878d908300cd12c285b5f42e1b6a08202231bd0a`,
`2.119.086` registros, `2.036.903.936` bytes, hash, quick-check, metadados e
contagem. Os timestamps UTC são `source_as_of` 2026-11-09T21:22:01.100051Z,
`generated_at` 2026-11-09T21:22:05.418944Z e `ingestion_latest_at`
2026-11-09T19:22:51.250561Z.

Reconciliação: `source_row_count=qualified_row_count=2.119.145`; descontadas
`rejected_after_select_count=59`, a projeção tem `record_count=2.119.086`.
`excluded_count=1.870.504` é uma métrica separada, não rejeições pós-seleção.

Nas 58 amostras da segunda ocorrência, `MemoryPeak=MemoryMax=2.147.483.648`
bytes, `memory.events max=158`, `high=0`, `oom=0`, `oom_kill=0` e
`oom_group_kill=0`; a primeira ocorrência teve eventos zero. A
[documentação de cgroup v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html#memory-interface-files)
explica que `max` é pressão no limite, não OOM por si só. Não é folga nem SLA;
não há alteração do limite nesta entrega, e a marcação `max` não bloqueou a
entrega porque sucesso e integridade foram confirmados. Acompanhar duração, tamanho e contadores em observações futuras
não constitui rotina ou garantia de continuidade.

Os intervalos BRT vêm do relógio do host/systemd; os timestamps da fonte são
UTC do snapshot, não medições do relógio da estação de trabalho. São provas de
duas ocorrências, não de recorrência futura ou disponibilidade contínua.

Em 10/11, uma leitura registrada após a conclusão da execução de
06:22:35–06:28:05 BRT encontrou `LastTrigger` igual ao início do serviço,
`Result=success`, saída zero, 330 s e 188,247 s de CPU. A fonte instalada
permanece `9f6ea98ca211166be4a47eb846080ba55b718a79`. Trata-se de estado lido
após a conclusão, não de vigilância contínua nem prova de todas as execuções
noturnas.

Como `confenge-deploy`, o consumidor confirmou leitura sem escrita, hash,
`quick_check`, metadados e contagem do snapshot
`56069ace210a0395c3ad700e51cc01539830ac1e5baaa36cc07891674bc27896`:
`2.127.193` contratos e `2.044.895.232` bytes. A reconciliação é
`source_row_count=qualified_row_count=2.127.253`, menos
`rejected_after_select_count=60`; `excluded_count=1.868.709` permanece
métrica separada. A consulta independente engenharia/SC/12 meses retornou
1.124 contratos, 279 compradores e 652 fornecedores. Os relógios UTC do
snapshot são `source_as_of` 2026-11-10T09:22:35.359725Z, `generated_at`
2026-11-10T09:22:38.502725Z e `ingestion_latest_at`
2026-11-10T03:26:39.179569Z.

O estado registrou `MemoryPeak=MemoryMax=2 GiB`, mas os contadores de eventos
de memória não foram coletados nessa execução; não alegar contadores zero.
As provas sanitizadas são `work/radar-producer-resume-2026-11-10.json` e
`work/radar-producer-service-resume-2026-11-10.json`. Elas complementam, sem
substituir, as evidências de 09/11.

Ainda na sessão, a terceira ocorrência agendada diretamente observada — não a
terceira execução total — ocorreu em 10/11, das 10:20:20 às 10:25:13 BRT. O
timer e o serviço correlacionaram o início; houve sucesso, 293 s e 181,187819 s
de CPU. Nas 59 amostras, `MemoryPeak=MemoryMax=2 GiB`,
`memory.events max=638`, `high=0`, `oom=0`, `oom_kill=0` e
`oom_group_kill=0`: pressão no limite sem OOM observado, sem demonstrar folga,
SLA ou continuidade garantida.

O consumidor somente-leitura confirmou o digest
`5f071600b403230c3f38468014cc0bebbb8737de22f62710f6beaa59a750834a`,
`2.127.193` contratos e `2.044.895.232` bytes; a consulta independente
engenharia/SC/12 meses retornou 1.124 contratos, 279 compradores e 652
fornecedores. Os metadados UTC são `source_as_of`
2026-11-10T13:20:20.654812Z, `generated_at` 2026-11-10T13:20:24.852862Z e
`ingestion_latest_at` 2026-11-10T12:01:33.009989Z. Evidência sanitizada:
`work/radar-producer-third-observed-2026-11-10.json`.

## Contrato e limites

- Fonte PNCP; contratos persistidos na janela móvel dos últimos 24
  meses-calendário pela publicação original, fornecedores pessoa jurídica
  e qualidade `VALID`.
- A cobertura não é censitária. Vigência é sinal de pesquisa, não confirmação
  de licitação nova ou renovação; unidade compradora não prova execução local.
- Valores não são totalizados e não representam pagamentos, pois a origem não
  distingue valor global, inicial ou estimado.
- Não anexar linhas de contrato, buscas, dados de contato, identificadores de
  entidades, credenciais ou snapshots nesta documentação.

## Publicação e aceite em 10/11/2026

O consumidor web da [PR #795](https://github.com/tjsasakifln/web-cfg/pull/795)
foi integrado por merge commit em
`49db1609a8c470bced81b16a2ff06c6a4d00662a`. O CI exato do head candidato
`44bc868273916f3ea1ecf3e9ca64cb611b3c58bd` foi aprovado; o site-ci canônico
do main 49db também passou na [tentativa 1 do job
129814917399](https://github.com/tjsasakifln/web-cfg/actions/runs/42811811191/job/129814917399),
com agregado 129834945814. A PR #799 já está integrada.

A tentativa 1 do release 49db falhou no teste Event semantics do pSEO na
rota de diagnóstico de defesa de margem. A causa ficou indeterminada. Com
a integração de uma nova revisão de `main`, a tentativa 2 foi cancelada
antes de empacotamento, stage ou SSH. [Histórico do release 49db](https://github.com/tjsasakifln/web-cfg/actions/runs/42811811191).

A PR #804 integrou os ajustes de carteira, login social e CSP na revisão
`10e28b9c0bff214a483dc1c4fedaf99ce8ffd4e2`, descendente direta de 49db. A mesma
promoção publicou o Radar. Os checks independentes de `main` e os nove jobs
do release canônico passaram na primeira tentativa. A promoção atômica
terminou às 11:16:28 BRT e o workflow às 11:19:19 BRT. [PR #804](https://github.com/tjsasakifln/web-cfg/pull/804)
· [Release 42819790710](https://github.com/tjsasakifln/web-cfg/actions/runs/42819790710).

| Evidência | Resultado |
|---|---|
| Qualificação e runtime | Candidato `MEASURED_PASS`, promoção aprovada e 589 de 589 HTML reconciliados pelo digest. A medição Lighthouse pública cobriu a home e uma oportunidade. |
| Identidades públicas | `build-info` e `runtime-info` HTTP 200 com o SHA `10e28b9c0bff214a483dc1c4fedaf99ce8ffd4e2`, também observado em `main`. |
| Snapshot | A releitura às 11:43:10 BRT confirmou `5f071600b403230c3f38468014cc0bebbb8737de22f62710f6beaa59a750834a`. O ETag público carregou o mesmo SHA-256. |
| API do Radar | 16 cenários aprovados. Engenharia/SC/12 meses retornou 1.124 contratos, 279 compradores, 652 fornecedores e 1.124 contratos com valor, iguais ao SQLite independente. A consulta nacional retornou 2.127.193. |
| Tempos da API | Requisição inicial de metadados em 6.197 ms. As seis consultas seguintes ficaram entre 288 e 3.004 ms. São tempos desta execução. |
| Navegador | 12 verificações aprovadas em desktop e tela de 375 px. Incluem filtros, rankings, paginação, catálogo, links do PNCP, cópia canônica e isolamento da falha da configuração da carteira. Zero erros de console e de página no fluxo normal. |
| CSV e carteira | O arquivo preparado reproduziu as nove colunas dos 25 registros da página 2. A carteira ativa exibiu o modal anônimo, com zero URLs de entrega e zero requisições mutantes de comércio. |

A API também conferiu a ordem e as datas do recorte de fim de vigência em
90 dias, a separação entre as páginas 20 e 21, as rejeições HTTP esperadas
e a ausência de exposição do ponteiro e do snapshot nas rotas sondadas.
No navegador, a configuração de carteira indisponível manteve a consulta
ativa, ocultou a indicação e bloqueou a emissão. A inspeção do CSV público
cobriu as células observadas. Os fixtures locais cobrem fórmulas maliciosas e
entrega após autorização. O percurso de produção foi anônimo.

A aceitação específica foi registrada em `outputs/radar-public-acceptance/`
com os relatórios `api-acceptance.json` e `acceptance.json` e as capturas
`desktop-preview-1280.png`, `desktop-1280.png` e `mobile-375.png`. Os revisores
adversariais de produto e publicação aprovaram a evidência. [Qualificação](https://github.com/tjsasakifln/web-cfg/actions/runs/42819790710/artifacts/13771348242)
· [Aceitação canônica do runtime](https://github.com/tjsasakifln/web-cfg/actions/runs/42819790710/artifacts/13773015065)
· [Radar em produção](https://confenge.com.br/ferramentas/radar-mercado-publico/).

## Governança preservada

O aceite registrado cobre o Radar na revisão publicada. O item Radar do
`DOD.md` depende do aceite formal pelo controlador. O estado `VPS_OPERATIONAL`
tem seu próprio conjunto de verificações.
