# Operação da projeção de mercado público

Escopo: somente a projeção `confenge.market-radar/v1`. Este documento não
declara VPS_OPERATIONAL para o produto Extra nem aceita incidentes existentes.

## Instalação

1. Integrar código após CI verde e testes do item. Identificar o SHA exato.
2. Criar usuário de sistema `confenge-radar`, sem shell, grupo primário próprio `confenge-radar`, sem membership em `confenge-web`.
   Aplicar `deploy/market-radar/provision.sql` como administrador no banco
   `pncp_datalake`. Conferir os privilégios de escrita ausentes. A autenticação
   é peer local; não há senha no evento, no site ou no repositório.
   A ativação exige conexão como o usuário dedicado, zero memberships e
   ausência de CREATE no banco/schema ou privilégios de escrita na tabela.
   O provisionamento aborta se encontrar esses privilégios. TEMP herdado de
   PUBLIC pode permanecer: não revogar privilégios globais de outros serviços.
   É risco residual do papel interno, sem endpoint SQL público; conter por
   código fixo, timeouts, usuário isolado e acompanhamento de espaço.
3. Instalar o exportador e o contrato de documentação em release imutável
   `/opt/confenge-market-radar-producer/releases/<sha>`, root como proprietário.
   O symlink `current` seleciona a release. Usar o Python/psycopg2 já instalado
   em `/opt/extra-consultoria/.venv`; não alterar o checkout operacional.
4. Instalar os units versionados de `deploy/systemd/extra-market-radar.*`.
   O serviço usa `confenge-radar:confenge-radar` e escreve somente em
   `/var/lib/confenge-market-radar` (2750). Snapshots são 0440. O runtime web
   recebe leitura por grupo e nenhum direito de escrita na projeção ou banco.
5. Executar uma vez, conferir retorno, pointer, digest, contagens, exclusões,
   datas e consultas. Só então ativar o timer. Conferir o próximo disparo.

## Verificação e diagnóstico

`systemctl status extra-market-radar.service` e
`journalctl -u extra-market-radar.service` mostram execução e falhas, sem
termos de visitantes. `systemctl list-timers extra-market-radar.timer` mostra
cadência. `current.json` registra SHA-256, bytes e metadados da projeção.
Uma nova consulta à base não prova ingestão recente: conferir separadamente
`ingestion_latest_at`. O consumidor fecha quando geração passa de 36 horas
ou corte/incorporação passam de 48 horas, ou metadados são inválidos.

Reconciliação deve comparar o número de contratos oficiais deduplicados
elegíveis com `record_count`, descontando exclusões adicionais de identidade,
texto e datas registradas pelo produtor. Repetir uma busca representativa no
SQLite e pela API; contar compradores e fornecedores no mesmo recorte.

Não usar o estado do crawler como autoridade comercial. Este consumidor não
modifica nenhuma campanha. Uma falha de exportação conserva a versão anterior
somente enquanto ela permanecer válida para o consumidor.

## Recuperação

Parar o timer interrompe novas projeções. Preservar pointer e logs necessários
ao diagnóstico. Reverter `current` para release aprovada e executar novamente.
Um pointer anterior só pode ser restaurado se o arquivo existe, o digest
confere e as datas continuam válidas; não renovar timestamps manualmente.
O deploy/rollback web segue o controlador canônico de bundles do web-cfg.
Falha do radar não deve derrubar a prontidão global do site.

## Evidência

Registrar na entrega o SHA integrado, CI, horário real da execução, contagens
e exclusões, tamanho, duração, identidade implantada do site, URL verificada,
consulta reproduzível e estado do timer. Configuração não prova recorrência;
exportação manual não prova um disparo agendado. Não versionar snapshots,
originais institucionais, credenciais ou logs brutos.

## Evidência limitada observada — 2026-11-09

O produtor da [PR #582](https://github.com/tjsasakifln/extra-cli/pull/582) foi
instalado a partir de `9f6ea98ca211166be4a47eb846080ba55b718a79`; o
[CI de main 42640898048](https://github.com/tjsasakifln/extra-cli/actions/runs/42640898048)
foi bem-sucedido. As provas sanitizadas externas registram uma execução manual
e duas ocorrências agendadas, todas distintas:

- Manual, 12:24:07–12:29:26 BRT: `radar-producer-final-verification.json`
  confirmou `2.119.086` registros, `2.036.903.936` bytes e digest
  `0a87278080d536fd976db310f2d6c49bc218ce848880d059a71f36d6bb14adb2` para
  a projeção `confenge.market-radar/v1` em `READY`.
- Agendada, 14:22:02–14:26:42 BRT: a primeira ocorrência de
  `extra-market-radar.timer`/`extra-market-radar.service` durou 280 s,
  terminou com saída zero e publicou o digest
  `54c7fab3403fc592005438584b23a6867ee31d9d54bb355e1849dc27f4f2c36c`.
  O artefato registra `source_as_of` 2026-11-09T17:22:02.347128Z,
  `generated_at` 2026-11-09T17:22:04.196337Z e
  `ingestion_latest_at` 2026-11-09T15:18:10.298403Z.
- Agendada, 18:22:00–18:26:59 BRT: a segunda ocorrência durou 299 s, usou
  186,709 s de CPU e terminou com saída zero. `LastTrigger` do timer coincidiu
  com o início do serviço. O consumidor somente-leitura confirmou digest
  `208ad74b98ce5635e811340d878d908300cd12c285b5f42e1b6a08202231bd0a`,
  `2.119.086` registros e `2.036.903.936` bytes, com hash, quick-check,
  metadados e contagem aprovados. Os três timestamps do snapshot foram
  `source_as_of` 2026-11-09T21:22:01.100051Z, `generated_at`
  2026-11-09T21:22:05.418944Z e `ingestion_latest_at`
  2026-11-09T19:22:51.250561Z.
- Reconciliação: `source_row_count=qualified_row_count=2.119.145`; após
  `rejected_after_select_count=59`, o `record_count=2.119.086` foi conferido.
  `excluded_count=1.870.504` é métrica separada e não deve ser confundida com
  rejeições após a seleção.
- Na primeira ocorrência, o pico foi 2.143.817.728 bytes e os eventos de
  memória foram zero. Na segunda, 58 amostras observaram
  `MemoryPeak=MemoryMax=2.147.483.648` bytes, `memory.events max=158`,
  `high=0`, `oom=0`, `oom_kill=0` e `oom_group_kill=0`. Conforme a
  [interface de memória cgroup v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html#memory-interface-files),
  `max` registra pressão no limite, não OOM por si só. É um limite operacional
  observado, não folga nem SLA. Não há alteração do limite nesta entrega; a
  marcação `max` não bloqueou a entrega porque a execução terminou com sucesso
  e a integridade foi confirmada.

Os intervalos BRT são registros do relógio do host/systemd; os três metadados
de fonte acima são timestamps UTC do snapshot. Comparações com o relógio da
estação de trabalho exigem normalização de fuso e consideração do desvio
entre os relógios; esses registros não são horários medidos pela estação.

Esses fatos comprovam somente essas execuções. Não comprovam recorrência
futura, disponibilidade contínua ou `VPS_OPERATIONAL` global. Em observações
futuras, registrar duração, tamanho e contadores de memória, sem que isso crie
uma rotina ou promessa de monitoramento. As evidências não retêm linhas de
contrato, buscas de visitantes, identidades de entidades ou credenciais.

## Retomada registrada — 2026-11-10

O estado foi lido após a conclusão da execução de 06:22:35–06:28:05 BRT,
sem observação contínua: o `LastTrigger` do timer é igual ao início do serviço,
que terminou com saída zero, `Result=success`, duração de 330 s e 188,247 s de
CPU. O produtor instalado continua a release
`9f6ea98ca211166be4a47eb846080ba55b718a79`. Essa leitura registrada não prova
todas as execuções noturnas nem disponibilidade contínua.

O consumidor somente-leitura confirmou hash, `quick_check` SQLite, metadados e
contagem do snapshot `56069ace210a0395c3ad700e51cc01539830ac1e5baaa36cc07891674bc27896`:
`2.127.193` contratos e `2.044.895.232` bytes. A reconciliação separa
`source_row_count=qualified_row_count=2.127.253`,
`rejected_after_select_count=60` e `excluded_count=1.868.709`. A consulta
independente engenharia/SC/12 meses retornou 1.124 contratos, 279 compradores
e 652 fornecedores. Os metadados UTC foram `source_as_of`
2026-11-10T09:22:35.359725Z, `generated_at`
2026-11-10T09:22:38.502725Z e `ingestion_latest_at`
2026-11-10T03:26:39.179569Z.

`MemoryPeak=MemoryMax=2 GiB` nesta leitura de estado. Os contadores de eventos
de memória não foram coletados durante essa execução; portanto esta evidência
não declara contadores zero. As provas sanitizadas são
`work/radar-producer-resume-2026-11-10.json` e
`work/radar-producer-service-resume-2026-11-10.json`; as evidências históricas
de 09/11 permanecem válidas e distintas.

Na mesma sessão, a terceira ocorrência agendada diretamente observada — não a
terceira execução total — ocorreu em 10/11, das 10:20:20 às 10:25:13 BRT. O
timer e o serviço correlacionaram o início; a execução terminou com sucesso,
293 s e 181,187819 s de CPU. Em 59 amostras, `MemoryPeak=MemoryMax=2 GiB`,
`memory.events max=638`, `high=0`, `oom=0`, `oom_kill=0` e
`oom_group_kill=0`. Isto registra pressão no limite sem OOM observado, não
folga, SLA ou continuidade garantida.

O consumidor somente-leitura confirmou o digest
`5f071600b403230c3f38468014cc0bebbb8737de22f62710f6beaa59a750834a`,
`2.127.193` contratos, `2.044.895.232` bytes e o recorte independente
engenharia/SC/12 meses de 1.124 contratos, 279 compradores e 652 fornecedores.
Os metadados UTC são `source_as_of` 2026-11-10T13:20:20.654812Z,
`generated_at` 2026-11-10T13:20:24.852862Z e `ingestion_latest_at`
2026-11-10T12:01:33.009989Z. A prova sanitizada é
`work/radar-producer-third-observed-2026-11-10.json`.

### Publicação e validação

Em 10/11/2026, a Netcup publicou o Radar junto com a revisão
`10e28b9c0bff214a483dc1c4fedaf99ce8ffd4e2` de `web-cfg/main`, descendente
direta do merge da PR #795. O release 42819790710 concluiu os nove jobs na
primeira tentativa. As identidades públicas de build e runtime responderam
HTTP 200 com a revisão promovida. [Radar publicado](https://confenge.com.br/ferramentas/radar-mercado-publico/)
· [Release canônico](https://github.com/tjsasakifln/web-cfg/actions/runs/42819790710).

O consumidor `confenge-deploy` releu o snapshot às 11:43:10 BRT e confirmou
hash, integridade SQLite, metadados, contagem e acesso somente leitura. O
ETag da API pública correspondeu ao mesmo digest. A consulta engenharia/SC/12
meses reproduziu os quatro totais da consulta SQLite independente, com
1.124 contratos, 279 compradores, 652 fornecedores e 1.124 contratos com valor
informado. A consulta nacional reproduziu os 2.127.193 registros da projeção.
Filtros de vigência, rankings, páginas 20 e 21 e rejeições HTTP também passaram.

O navegador conferiu os filtros, rankings, paginação, cópia do endereço
canônico e catálogo em telas de 1280 e 375 px. O CSV preparado para a página 2
correspondeu aos 25 registros exibidos. A carteira estava ativa e exibiu o
modal anônimo, com zero URLs de entrega e zero requisições mutantes de
comércio. Na simulação de falha de configuração, a consulta continuou
funcionando, o convite de indicação ficou oculto e a emissão foi bloqueada.
O fluxo normal registrou zero erros de console e de página. [Registro do aceite](../handoffs/market-radar-public-projection-2026-11-09.md).

Consultas, filtros, rankings e paginação são livres. Pela ADR-TOOLS-001, a
carteira ativa usa um crédito por emissão de CSV, com primeira emissão da
conta verificada como cortesia. A entrega é local quando o comércio está
explicitamente desabilitado. A autorização recebe identificador da ferramenta
e da solicitação, formato, tamanho e hash. A entrega autenticada é coberta
pelo fixture do navegador.
