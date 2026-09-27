# Retenção proporcional de armazenamento

## Objetivo e limite de segurança

`scripts.ops.storage_retention` reserva espaço para cada novo pacote PNCP
reclamando **pelo menos o mesmo número de bytes lógicos** em dados antigos. A
rotina só pode apagar:

1. arquivos regulares antigos sob raízes explicitamente permitidas (por padrão
   `/var/lib/extra-consultoria/backups/tmp` e `/tmp/pg-backup`); e
2. mediante `--prune-contract-history`, versões superadas de
   `public.contract_version_history`.

A tabela canônica `public.pncp_supplier_contracts` não faz parte da superfície
de exclusão. A versão mais recente do histórico de cada contrato também é
sempre preservada. Um arquivo novo informado por `--incoming-path` é protegido.

Exceção opt-in: `--allow-canonical-purge` (ou
`STORAGE_RETENTION_ALLOW_CANONICAL_PURGE=1` no crawler) permite eliminar apenas
contratos canônicos **concluídos e frios**, do mais antigo para o mais novo. O
default permanece desligado. A rotina exige horizonte mínimo de 30 dias
(recomendado: 730), trigger de versionamento desabilitado e nenhum FK de entrada
fora de `contract_role_links ON DELETE CASCADE`. Em apply canônico, um
`minimum_free_bytes` físico positivo também é obrigatório.

## Contrato operacional

- dry-run é o padrão; mutação exige `--apply`;
- candidatos são processados do mais antigo para o mais novo;
- arquivos recentes e o número configurado em `--protect-newest` por raiz e
  classe de nome não são elegíveis;
- symlinks, raiz `/`, fuga da raiz permitida e arquivos alterados entre plano e
  exclusão causam falha fechada;
- um lock exclusivo persistente em
  `/var/lib/extra-consultoria/locks/storage-retention.lock` impede duas
  limpezas concorrentes; CLI, preflight e hook usam exatamente esse caminho e
  falham fechado se ele não estiver acessível;
- quando o histórico é habilitado, um advisory lock PostgreSQL de sessão cobre
  a mutação inteira;
- `SATISFIED` só é emitido quando o aumento observado por `disk_usage` no mesmo
  filesystem, limitado aos blocos realmente removidos, é maior ou igual ao
  alvo; falta de candidatos termina com código `2`;
- exclusão de histórico ocorre em lotes com commit, usa `SKIP LOCKED` e termina
  em `VACUUM (ANALYZE)` para tornar as páginas reutilizáveis pelo PostgreSQL;
- a poda canônica opt-in também usa lotes, `SKIP LOCKED`, cascata declarada de
  `contract_role_links` e `VACUUM`; contratos ativos (`data_fim IS NULL`) ou
  dentro do hot horizon nunca são elegíveis. Cada lote adquire lock de tabela
  que bloqueia DDL e revalida triggers/FKs dentro da mesma transação do DELETE;
- a idade canônica usa somente relógios da fonte/contrato
  (`source_updated_at`, `data_atualizacao_fonte`, `data_publicacao_fonte`,
  `data_publicacao`, `data_assinatura` e `data_fim`). `ingested_at` e
  `last_seen_at` são relógios operacionais locais e não rejuvenescem contratos
  históricos após backfill. Datas da fonte futuras ou recentes protegem a linha;
- além de `data_fim` antiga, a poda canônica exige
  `status_normalized = 'COMPLETED'` e `quality_state = 'VALID'`. Rótulos
  ausentes, em revisão, quarentenados ou contraditórios falham fechado e não
  entram na superfície de exclusão;
- o relatório separa bytes físicos comprovados de arquivos e bytes lógicos
  reutilizáveis por relação. Páginas da canônica (incluindo o crescimento de
  `contract_role_links`) só quitam crescimento canônico; páginas de
  `contract_version_history` só quitam crescimento do histórico. Nenhuma delas
  é contabilizada como aumento de `df`.

## Uso

Planejar a compensação de um pacote completo:

```bash
python3 -m scripts.ops.storage_retention \
  --incoming-path /var/lib/extra-consultoria/incoming/pncp-package.jsonl \
  --file-root /var/lib/extra-consultoria/backups/tmp \
  --prune-contract-history
```

Aplicar, preservando arquivos das últimas 24 horas e ao menos o mais novo:

```bash
python3 -m scripts.ops.storage_retention \
  --incoming-bytes 104857600 \
  --file-root /var/lib/extra-consultoria/backups/tmp \
  --min-age-hours 24 \
  --protect-newest 1 \
  --prune-contract-history \
  --history-min-age-days 30 \
  --allow-canonical-purge \
  --canonical-hot-horizon-days 730 \
  --space-path /var/lib/postgresql \
  --minimum-free-bytes 10737418240 \
  --safety-factor 1.25 \
  --max-reclaim-bytes 21474836480 \
  --output /var/lib/extra-consultoria/evidence/storage-retention.json \
  --apply
```

`LOCAL_DATALAKE_DSN` é obrigatório apenas quando
`--prune-contract-history` é usado. O DSN nunca é incluído no relatório.
`--minimum-free-bytes` aumenta o alvo de limpeza quando necessário; o JSON
registra espaço livre antes e depois. Como `VACUUM` normal reutiliza páginas no
PostgreSQL mas não reduz necessariamente o arquivo da relação no filesystem,
o relatório mantém bytes lógicos de histórico separados dos bytes de arquivos.
O fator de segurança padrão reserva 25% para WAL, índices e temporários; o limite
máximo impede uma única chamada de excluir um volume ilimitado.

`SATISFIED_REUSABLE` significa que bytes lógicos equivalentes foram removidos da
mesma relação que cresceu e ficaram reutilizáveis após `VACUUM`; não significa
aumento de `df`. O relatório expõe `canonical_required_bytes`,
`history_required_bytes` e `matched_relation_reusable_bytes` para permitir a
auditoria dessa correspondência. `SATISFIED` continua reservado ao aumento
físico observado no filesystem. O low-watermark físico permanece obrigatório
para WAL e temporários.

## Integração com PNCP e backup

O crawler chama a retenção logo após cada `_upsert_batch` durável quando
`STORAGE_RETENTION_ENABLED=1`. `STORAGE_RETENTION_APPLY=1` também exige
`STORAGE_RETENTION_SPACE_PATH`; um déficit físico faz a janela falhar fechada,
sem alegar rollback do batch já confirmado. Para dumps, a raiz temporária deve
ser a mesma configurada em `BACKUP_TEMP_DIR`; dumps publicados e o snapshot
atual não devem ser passados como raiz de limpeza.

Configuração inicial recomendada no host:

```text
STORAGE_RETENTION_FILE_ROOT=/var/lib/extra-consultoria/backups/tmp
STORAGE_RETENTION_FILE_ROOTS=/var/lib/extra-consultoria/backups/tmp:/tmp/pg-backup
STORAGE_RETENTION_ENABLED=1
STORAGE_RETENTION_APPLY=0
STORAGE_RETENTION_SPACE_PATH=/var/lib/postgresql
STORAGE_RETENTION_LOW_FREE_BYTES=10737418240
STORAGE_RETENTION_MINIMUM_FREE_BYTES=10737418240
```

Ao ativar `STORAGE_RETENTION_APPLY=1`, `SPACE_PATH` e
`LOW_FREE_BYTES` positivo são obrigatórios e são validados antes de qualquer
upsert. `MINIMUM_FREE_BYTES` controla o gate pós-commit e, se omitido, herda
`LOW_FREE_BYTES`; recomenda-se declarar ambos explicitamente com o mesmo valor.

Antes da primeira execução com `--apply`, executar o dry-run, revisar o JSON e
confirmar que somente arquivos temporários antigos e versões históricas
superadas aparecem como elegíveis.

## Limite arquitetural

Sem o opt-in canônico, a política não promete retenção contínua quando não
restarem temporários elegíveis. Com o opt-in, ela mantém capacidade reutilizável
na mesma relação, mas ainda não promete redução do arquivo físico nem substitui
headroom de WAL/temporários. Particionamento temporal e descarte de partições
continuam sendo a alternativa para devolução previsível de espaço ao filesystem.
Shortfall fica `DEGRADED` no report e no ledger; o preflight tenta limpar
arquivos antigos e recusa o próximo batch antes da mutação se o watermark físico
continuar inseguro.

A rotação `BACKUP_BYTE_BALANCED_RETENTION` atua no volume onde os dumps diários
foram publicados (normalmente o mount off-site). Ela limita esse volume, mas não
é evidência de espaço livre no filesystem do PostgreSQL da VPS.
