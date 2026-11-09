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
