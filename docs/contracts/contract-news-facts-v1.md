# `confenge.contract-news-facts/v1`

Produtor: `scripts.public_exports.contract_news`, proprietário `extra-cli`.
Consumidor editorial: `web-cfg`. Os fatos são entregues em diretório privado;
a publicação usa somente a saída validada do consumidor.

## Entrada e seleção

Produção lê `--radar-pointer /var/lib/confenge-market-radar/current.json`.
Alternativamente, `--dsn` usa PostgreSQL com papel já limitado a SELECT.
O produtor não cria grants, não coleta páginas de listagem e não escreve na
base ou na projeção Radar.

O consumidor entrega `--published-ids` com esta forma exata:

```json
{"published_ids":[],"recheck_ids":[]}
```

`published_ids` contém no máximo 10.000 IDs PNCP canônicos, sem duplicações.
`recheck_ids` é um subconjunto com até cinco IDs distintos, escolhidos pelo
consumidor conforme a revisão mais antiga. A ausência do arquivo é permitida na
primeira execução. IDs já publicados não concorrem como novidades.

Cada execução consulta no máximo vinte detalhes oficiais, incluindo as
revisões. A janela nova cobre hoje e os seis dias anteriores em
`America/Sao_Paulo`. A origem persistida e sua última ingestão devem ter no
máximo 26 horas; o snapshot Radar deve ter sido gerado há no máximo 36 horas.
Relógios futuros acima de cinco minutos e ordenação temporal invertida são
rejeitados. A seleção preliminar é limitada e usa o valor da projeção somente
como heurística interna. O ranking final usa o valor oficial confirmado.

O detalhe oficial fica em
`https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/contratos/{ano}/{sequencial}`.
O host e o caminho derivam do ID validado. Não há redirecionamento, retry nem
origem arbitrária; cada resposta tem limite de 256 KiB e timeout de 15 segundos.

## Documento de saída

| Campo | Contrato |
| --- | --- |
| `schema` | `confenge.contract-news-facts/v1` |
| `producer` | `extra-cli` |
| `generated_at` | Data e hora UTC da geração |
| `source_as_of` | Corte da projeção persistida, preservado sem renovação artificial |
| `ingestion_latest_at` | Última ingestão representada pela origem |
| `window_start`, `window_end` | Datas inclusivas da janela editorial nova |
| `source_timezone_without_offset` | `America/Sao_Paulo`; regra para horários PNCP sem offset |
| `producer_commit` | SHA completo do bundle aprovado, quando informado no modo Radar |
| `radar_contract`, `radar_sha256` | Versão e digest da projeção consumida, no modo Radar |
| `radar_source_as_of`, `radar_generated_at` | Corte e geração originais do Radar |
| `selection` | Limites, quantidade de consultas, verificações e exclusões por motivo |
| `records` | Até vinte registros confirmados, ordenados por valor e ID |
| `recheck_results` | Resultado de cada revisão solicitada |

O documento completo tem limite de 512 KiB. A troca do arquivo é atômica, com
fsync e modo `0440`. Um lock exclusivo impede execuções concorrentes para o
mesmo destino. O diretório de destino deve existir e ser previamente autorizado.

## Registro confirmado

| Campo | Contrato |
| --- | --- |
| `id` | `numeroControlePNCP` canônico, padrão `NNNNNNNNNNNNNN-2-NNNNNN/AAAA` |
| `buyer` | Razão social do órgão; texto saneado |
| `supplier` | Razão social do fornecedor pessoa jurídica; texto saneado |
| `supplier_type` | Sempre `PJ`; identificador fiscal não é exportado |
| `object` | Objeto integral de 40 a 5.120 caracteres, sem truncamento silencioso |
| `value.amount` | Decimal positivo em string, menor que 10^15 e até quatro casas |
| `value.kind` | `valorGlobal` positivo ou fallback explícito `valorInicial` |
| `value.currency` | `BRL` |
| `source_url` | URL exata do contrato no portal oficial PNCP |
| `source_api_url` | URL exata do detalhe consultado, associada ao digest |
| `source_sha256` | SHA-256 dos bytes UTF-8 do corpo oficial recebido |
| `source_published_at` | Publicação PNCP em UTC |
| `source_checked_at` | Momento da confirmação oficial em UTC |
| `source_updated_at` | Atualização oficial em UTC ou `null` |
| `signed_at` | Data de assinatura `AAAA-MM-DD` ou `null` |
| `starts_at`, `ends_at` | Datas de vigência `AAAA-MM-DD` ou `null` |
| `administrative_location.city`, `.state` | Município/UF da unidade administrativa ou `null` |

Somente contrato inicial de despesa, com pessoa jurídica e CNPJ válido, entra
nessa versão. O valor não é estimativa, soma de aditivos ou execução financeira.
O lugar administrativo não prova lugar da obra. Ausência de assinatura não é
preenchida pela publicação. Texto, valores e datas nunca são inventados para
completar registro; mínimos incompletos excluem o candidato.

Cada item de `recheck_results` tem `id`, `status` e `reason`.
`verified` também entrega o registro em `records`. `ineligible` descreve
reprovação semântica na resposta oficial. `unavailable` não é evidência de
cancelamento e não autoriza inferência de que o contrato deixou de existir.

## Bundle aprovado e execução

Em checkout limpo do SHA aprovado:

```bash
python3 -S scripts/public_exports/package_contract_news.py \
  --sha "$PRODUCER_SHA" \
  --output /tmp/contract-news-producer.tar.gz
```

O empacotador inclui o fechamento real dos imports do modo Radar, sem instalar
dependências externas, e um `producer-manifest.json` com versão, repositório,
commit e SHA-256 de cada arquivo. Antes de empacotar, confere cada arquivo contra
`git show` desse commit. O pipeline web deve conferir o manifesto após extrair
em diretório privado e executar a partir desse diretório. Não se extrai sobre o
checkout operacional do coletor.

Com diretórios já provisionados para o usuário autorizado:

```bash
python3 -S -m scripts.public_exports.contract_news \
  --radar-pointer /var/lib/confenge-market-radar/current.json \
  --published-ids /var/lib/confenge-web/contract-news/private/published-ids.json \
  --output /var/lib/confenge-web/contract-news/private/facts.json \
  --producer-commit "$PRODUCER_SHA"
```

Saída normal: JSON resumido com `ok`, schema, digest e contagens.
Código `75` indica concorrência; demais falhas retornam `1`. Logs não expõem
DSN, corpo bruto da resposta, credenciais ou dados individuais descartados.
A indisponibilidade total do PNCP preserva o arquivo anterior e falha a etapa.

O agendamento pertence ao workflow web em `main`, a cada quatro horas no minuto
55, após a rotina existente do Radar. O exportador não possui segredo OpenAI;
essa configuração pertence ao consumidor editorial. A validação de acesso deve
informar somente existência/legibilidade da configuração, nunca seu conteúdo.
