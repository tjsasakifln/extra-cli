# Guia de Troubleshooting — Extra Consultoria

> **Criado em:** 2026-07-11
> **Propósito:** Diagnosticar e resolver problemas comuns no sistema de inteligencia em licitacoes.
> **Story:** TD-6.1 -- Documentacao Operacional

## Sumario

- [Falha de Conexao com Banco](#falha-de-conexao-com-banco)
- [Crawler Timeout](#crawler-timeout)
- [API Key Expirada](#api-key-expirada)
- [Erro de Permissao](#erro-de-permissao)
- [Migration Falhou](#migration-falhou)
- [Backup Falhou](#backup-falhou)
- [Purge Nao Executou](#purge-nao-executou)
- [Falha no Entity Matching](#falha-no-entity-matching)
- [Cobertura Estagnada](#cobertura-estagnada)
- [Disco Cheio](#disco-cheio)
- [PSQL Connection Refused](#psql-connection-refused)
- [Storage Box Indisponivel](#storage-box-indisponivel)
- [Crawler Nao Encontrou Registros](#crawler-nao-encontrou-registros)

---

## Falha de Conexao com Banco

### Sintomas

```
psycopg2.OperationalError: could not connect to server
Connection refused
Is the server running on host "..." and accepting TCP/IP connections?
```

### Causas Provaveis

1. PostgreSQL nao esta rodando
2. Firewall bloqueando porta 5432
3. DSN incorreto no `.env`
4. Rede indisponivel

### Diagnosticos

```bash
# 1. Verificar se PostgreSQL esta rodando
systemctl status postgresql

# 2. Verificar porta
ss -tlnp | grep 5432

# 3. Testar conexao diretamente
psql $LOCAL_DATALAKE_DSN -c "SELECT 1"

# 4. Verificar firewall
ufw status verbose

# 5. Verificar DSN configurado
grep LOCAL_DATALAKE_DSN .env
```

### Resolucao

```bash
# Iniciar PostgreSQL se parado
sudo systemctl start postgresql

# Verificar pg_hba.conf para conexoes remotas (se aplicavel)
sudo cat /etc/postgresql/17/main/pg_hba.conf | grep -E "^host"

# Liberar firewall (se necessario)
sudo ufw allow 5432/tcp
```

---

## Crawler Timeout

### Sintomas

```
httpx.ReadTimeout: timed out
requests.exceptions.ConnectionError
Crawling ... (stuck for minutes)
```

### Causas Provaveis

1. API externa lenta ou indisponivel
2. Rate limiting da API fonte
3. Rede do VPS congestionada
4. Muitos orgaos configurados sem delay entre batches

### Diagnosticos

```bash
# 1. Verificar logs do crawl
journalctl -u pncp-crawl-full.service --no-pager -n 50 | grep -i "timeout\|error\|fail"

# 2. Verificar conectividade com a API fonte
curl -s -o /dev/null -w "%{http_code}" "https://pncp.gov.br/api/consulta/v1/"

# 3. Verificar tempo de resposta
curl -s -o /dev/null -w "Tempo: %{time_total}s\n" "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao?pagina=1"

# 4. Verificar uso de recursos durante o crawl
htop
```

### Resolucao

```bash
# Aumentar timeout (configurar no .env)
PNCP_READ_TIMEOUT=30   # default: 15s
PNCP_MAX_RETRIES=3     # default: 1

# Reduzir concorrencia (configurar no .env)
INGESTION_BATCH_DELAY_S=2.0   # aumentar delay entre batches

# Executar crawl incremental em vez de full
python scripts/crawl/monitor.py --source pncp --mode incremental

# Se API estiver fora do ar, aguardar e tentar novamente mais tarde
python scripts/crawl/monitor.py --source pncp --mode full --dry-run
```

---

## API Key Expirada

### Sintomas

```
HTTP 401 Unauthorized
HTTP 403 Forbidden
"API key invalid" or "Invalid credentials"
```

### Causas Provaveis

1. `DOM_SC_API_KEY` expirada ou revogada
2. `OPENAI_API_KEY` expirada ou sem creditos
3. `PORTAL_TRANSPARENCIA_API_KEY` expirada

### Diagnosticos

```bash
# 1. Verificar quais keys estao configuradas
grep -E "API_KEY|OPENAI" .env | grep -v "#" | grep "="

# 2. Verificar healthcheck (reporta keys faltantes)
python scripts/healthcheck.py

# 3. Testar DOM-SC key diretamente
curl -s -o /dev/null -w "%{http_code}" \
  -H "X-API-Key: $DOM_SC_API_KEY" \
  "https://www.diariomunicipal.sc.gov.br/api/..."

# 4. Testar OpenAI key
curl -s https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -o /dev/null -w "%{http_code}"
```

### Resolucao

| API Key | Onde Renovar | Custo |
|---------|-------------|-------|
| `DOM_SC_API_KEY` | Solicitar ao suporte do DOM-SC | Gratuita |
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys | Paga (credito) |
| `PORTAL_TRANSPARENCIA_API_KEY` | https://portaldatransparencia.gov.br/api-de-dados | Gratuita |

Apos renovar, atualizar o `.env` no VPS:

```bash
# Editar .env no VPS
nano /opt/extra-consultoria/.env

# Ou via scp
scp .env ec-prod:/opt/extra-consultoria/.env

# Recarregar servicos (se necessario)
sudo systemctl restart pncp-crawl-full.service
```

---

## Erro de Permissao

### Sintomas

```
PermissionError: [Errno 13] Permission denied
psycopg2.errors.InsufficientPrivilege
sudo: permission denied
```

### Causas Provaveis

1. Scripts sem permissao de execucao (`chmod +x`)
2. Usuario `extra-consultoria` sem acesso a diretorios
3. PostgreSQL sem permissao para o usuario
4. Arquivo `.env` com permissoes incorretas

### Diagnosticos

```bash
# 1. Verificar permissoes dos scripts
ls -la scripts/backup-database.sh
ls -la scripts/restore-database.sh

# 2. Verificar usuario atual
whoami

# 3. Verificar acesso ao diretorio do app
ls -la /opt/extra-consultoria/

# 4. Verificar permissao do .env
ls -la /opt/extra-consultoria/.env
ls -la .env
```

### Resolucao

```bash
# Corrigir permissoes de scripts
chmod +x scripts/backup-database.sh
chmod +x scripts/restore-database.sh
chmod +x scripts/apply-migrations.sh

# Corrigir dono do diretorio
sudo chown -R extra-consultoria:extra-consultoria /opt/extra-consultoria

# Proteger .env (apenas dono le)
chmod 600 .env
chmod 600 /opt/extra-consultoria/.env

# Conceder permissao no PostgreSQL (se necessario)
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE pncp_datalake TO postgres;"
```

---

## Migration Falhou

### Sintomas

```
ERRO: Falha ao aplicar 013_td-1.1_gin_index_objeto_contrato.sql
ERROR: relation "pncp_raw_bids" already exists
ERROR: column "nova_coluna" already exists
```

### Causas Provaveis

1. Migration ja foi aplicada manualmente (sem tracking)
2. Conflito entre migrations v1 (`db/migrations/`) e v2 (`supabase/migrations/`)
3. Erro de sintaxe SQL na migration
4. Checksum diverge do registro em `_migrations`

### Diagnosticos

```bash
# 1. Verificar status das migrations
bash scripts/apply-migrations.sh --status

# 2. Verificar migrations registradas
psql $LOCAL_DATALAKE_DSN -c "SELECT * FROM public._migrations ORDER BY version;"

# 3. Verificar migrations ja aplicadas manualmente
psql $LOCAL_DATALAKE_DSN -c "\dt public.*"

# 4. Verificar conteudo da migration que falhou
cat supabase/migrations/013_td-1.1_gin_index_objeto_contrato.sql
```

### Resolucao

```bash
# Opcao 1: Pular migration ja aplicada (registrar manualmente)
psql $LOCAL_DATALAKE_DSN -c "
  INSERT INTO public._migrations (version, name, applied_at, checksum)
  VALUES ('013', '013_td-1.1_gin_index_objeto_contrato.sql', NOW(), '$(sha256sum supabase/migrations/013_td-1.1_gin_index_objeto_contrato.sql | cut -d" " -f1)');
"

# Opcao 2: Corrigir e reaplicar
# Editar o SQL para ser idempotente (ex: ADD COLUMN IF NOT EXISTS)
# Depois reaplicar:
bash scripts/apply-migrations.sh

# Opcao 3: Executar SQL manualmente com tratamento de erro
psql $LOCAL_DATALAKE_DSN -c "
  DO \$\$
  BEGIN
    ALTER TABLE pncp_raw_bids ADD COLUMN IF NOT EXISTS nova_coluna TEXT;
  END \$\$;
"
```

---

## Backup Falhou

### Sintomas

```
[ERROR] Backup falhou: conexao com Storage Box perdida
[ERROR] pg_dump failed: could not connect to database
[ERROR] Espaco em disco insuficiente
```

### Causas Provaveis

1. Storage Box offline ou inacessivel
2. `.env` sem as variaveis de backup
3. Espaco em disco esgotado temporariamente
4. Chave SSH da Storage Box expirou ou foi removida

### Diagnosticos

```bash
# 1. Verificar ultimo log de backup
tail -50 /var/log/backup-database.log

# 2. Testar conexao SSH com Storage Box
ssh -p 23 -i /root/.ssh/storage_box u123456@u123456.your-storagebox.de

# 3. Verificar se o ponto de montagem existe
ls -la /mnt/storage-box/

# 4. Verificar espaco em disco
df -h /

# 5. Verificar configuracao
grep -E "BACKUP_|STORAGE" /etc/backup-database.conf
```

### Resolucao

```bash
# 1. Remontar Storage Box manualmente
mkdir -p /mnt/storage-box
sshfs -p 23 -o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3 \
  u123456@u123456.your-storagebox.de:backups/postgresql \
  /mnt/storage-box

# 2. Executar backup manualmente
/usr/local/bin/backup-database.sh

# 3. Se a chave SSH foi perdida, regenerar e adicionar no Hetzner Robot
ssh-keygen -t ed25519 -f ~/.ssh/storage_box -N ""
cat ~/.ssh/storage_box.pub  
# Adicionar em: https://robot.hetzner.com > Storage Box > SSH Keys
```

---

## Purge Nao Executou

### Sintomas

```
Tabela pncp_raw_bids muito grande (> 5GB)
Crawls lentos devido a tabela cheia
```

### Causas Provaveis

1. Timer do purge parado ou desabilitado
2. Erro silencioso no SQL RPC
3. `INGESTION_PURGE_GRACE_DAYS` muito alto

### Diagnosticos

```bash
# 1. Verificar timer
systemctl status pncp-purge.timer

# 2. Verificar ultima execucao
journalctl -u pncp-purge.service --no-pager -n 30

# 3. Verificar idade dos registros
psql $LOCAL_DATALAKE_DSN -c "
  SELECT MIN(data_publicacao) AS mais_antigo,
         MAX(data_publicacao) AS mais_recente,
         COUNT(*) AS total
  FROM pncp_raw_bids;
"
```

### Resolucao

```bash
# Executar purge manualmente
sudo systemctl start pncp-purge.service

# Verificar resultado
psql $LOCAL_DATALAKE_DSN -c "SELECT purge_old_records(400);"

# Verificar reducao
psql $LOCAL_DATALAKE_DSN -c "
  SELECT COUNT(*) FROM pncp_raw_bids
  WHERE data_publicacao < NOW() - INTERVAL '400 days';
"
```

---

## Falha no Entity Matching

### Sintomas

```
Muitos registros "unmatched" no relatorio de crawl
matched = 0 nos resultados do crawl
```

### Causas Provaveis

1. Orgaos na planilha `sc_public_entities` desatualizados
2. Razoes sociais divergentes entre fonte e cadastro
3. Nomes com acentos ou formatacao diferente
4. Fallback `difflib` ativado (rapidfuzz nao instalado), resultando em match de qualidade inferior

### Diagnosticos

```bash
# 1. Verificar unmatched entities
psql $LOCAL_DATALAKE_DSN -c "
  SELECT match_method, match_confidence, COUNT(*) AS total
  FROM pncp_raw_bids
  GROUP BY match_method, match_confidence
  ORDER BY total DESC;
"

# 2. Verificar bids unmatched
psql $LOCAL_DATALAKE_DSN -c "
  SELECT pncp_id, orgao_razao_social, municipio, orgao_cnpj
  FROM pncp_raw_bids
  WHERE matched_entity_id IS NULL
  LIMIT 20;
"

# 3. Verificar se rapidfuzz esta instalado
python -c "import rapidfuzz; print('rapidfuzz OK')" 2>&1 || echo "rapidfuzz ausente — usando fallback difflib (lento, menos preciso)"
```

### Resolucao

```bash
# Instalar rapidfuzz (melhor performance e precisao)
pip install rapidfuzz

# Re-executar entity matching (sobre bids unmatched)
python -c "
import psycopg2, os, json
from scripts.matching.entity_matcher import match_entities_cascade
from scripts.crawl.orchestrator import load_entities
conn = psycopg2.connect(os.getenv('LOCAL_DATALAKE_DSN'))
entities = load_entities(conn)
stats = match_entities_cascade(conn, 'pncp', entities)
print(json.dumps(stats, indent=2))
conn.close()
"
```

---

## Cobertura Estagnada

### Sintomas

```
Relatorio de cobertura mostra mesmo numero por dias seguidos
Novas entidades nunca ficam "covered"
```

### Causas Provaveis

1. As entidades nao cobertas nao possuem CNPJ nem razao social compativeis com as fontes
2. A fonte de dados nao possui registros para aquela entidade
3. Trigger de coverage esta com problema

### Diagnosticos

```bash
# 1. Verificar entidades nunca cobertas
psql $LOCAL_DATALAKE_DSN -c "
  SELECT e.id, e.razao_social, e.municipio, e.cnpj_8
  FROM sc_public_entities e
  LEFT JOIN entity_coverage ec ON e.id = ec.entity_id
  WHERE ec.last_covered_at IS NULL
  ORDER BY e.municipio
  LIMIT 20;
"

# 2. Verificar trigger de coverage
psql $LOCAL_DATALAKE_DSN -c "
  SELECT tgname AS trigger_name,
         pg_get_triggerdef(t.oid) AS trigger_def
  FROM pg_trigger t
  WHERE tgrelid = 'pncp_raw_bids'::regclass
    AND tgname LIKE '%coverage%';
"
```

### Resolucao

```bash
# Recalcular coverage manualmente
python -c "
import psycopg2, os
conn = psycopg2.connect(os.getenv('LOCAL_DATALAKE_DSN'))
cur = conn.cursor()
cur.execute('REFRESH MATERIALIZED VIEW CONCURRENTLY entity_coverage')  # se aplicavel
conn.commit()
cur.close()
conn.close()
"
```

---

## Disco Cheio

### Sintomas

```
NO space left on device
Disk usage > 90%
Healthcheck reporta disk: FAIL
```

### Causas Provaveis

1. Backups acumulados sem retention adequada
2. Logs do systemd sem rotacao
3. Cache local (data/intel/) acumulado

### Diagnosticos

```bash
# 1. Verificar uso de disco
df -h /

# 2. Verificar diretorios mais pesados
du -sh /var/log/
du -sh /opt/extra-consultoria/data/

# 3. Verificar backups na Storage Box
ls -lh /mnt/storage-box/daily/ | wc -l
```

### Resolucao

```bash
# Limpar cache do pipeline intel
rm -rf /opt/extra-consultoria/data/intel/*

# Forcar rotacao de logs
sudo journalctl --rotate
sudo journalctl --vacuum-time=7d

# Verificar e forcar retention de backup
/usr/local/bin/backup-database.sh --retention-only
```

---

## PSQL Connection Refused

### Sintomas

```
psql: error: connection to server at "..." failed
Connection refused
Is the server running on that host and accepting TCP/IP?
```

### Causas Provaveis

1. PostgreSQL configurado para escutar apenas localhost (sem conexao remota)
2. Porta 5432 bloqueada
3. `pg_hba.conf` sem entrada para o IP de origem

### Resolucao

```bash
# Verificar listen_addresses
sudo cat /etc/postgresql/17/main/postgresql.conf | grep listen_addresses

# Se estiver como localhost, alterar para *
sudo sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" /etc/postgresql/17/main/postgresql.conf

# Adicionar entrada no pg_hba.conf
echo "host pncp_datalake postgres 0.0.0.0/0 md5" | sudo tee -a /etc/postgresql/17/main/pg_hba.conf

# Reiniciar PostgreSQL
sudo systemctl restart postgresql
```

---

## Storage Box Indisponivel

### Sintomas

```
mount error: could not resolve hostname
ssh: connect to host <username>.your-storagebox.de port 23: Connection timed out
```

### Causas Provaveis

1. Storage Box em manutencao Hetzner
2. Rede do VPS instavel
3. Chave SSH nao configurada corretamente

### Resolucao

```bash
# Testar conectividade basica
ping -c 3 u123456.your-storagebox.de

# Testar SSH verbose
ssh -vvv -p 23 -i /root/.ssh/storage_box u123456@u123456.your-storagebox.de

# Se timeout, verificar se Hetzner Robot esta OK
# Acessar: https://robot.hetzner.com > Storage Box > Status

# Tentar remontar com opcoes alternativas
umount /mnt/storage-box 2>/dev/null
sshfs -p 23 -o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,connect_timeout=30 \
  u123456@u123456.your-storagebox.de:backups/postgresql \
  /mnt/storage-box

# Se Storage Box ficar offline por periodo prolongado, backups falharao
# Nestes casos, considerar backup local temporario:
pg_dump --format=custom $LOCAL_DATALAKE_DSN > /tmp/backup_emergencia.dump
```

---

## Crawler Nao Encontrou Registros

### Sintomas

```
Fetched: 0 records
No records found for source X
```

### Causas Provaveis

1. API fonte sem dados no periodo configurado (date range)
2. Parametros de busca incorretos
3. API fonte fora do ar temporariamente

### Diagnosticos

```bash
# 1. Verificar logs do crawler
journalctl -u pncp-crawl-full.service --no-pager -n 30 | grep -i "fetch\|found\|records"

# 2. Testar API fonte diretamente
curl -s "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao?pagina=1&tamanho=1" | python -m json.tool | head -20

# 3. Verificar configuracao de data range
grep INGESTION_DATE_RANGE_DAYS .env
```

### Resolucao

```bash
# Aumentar janela de busca
INGESTION_DATE_RANGE_DAYS=7     # para full crawl
INGESTION_INCREMENTAL_DAYS=7    # para incremental

# Tentar modo full (mais abrangente)
python scripts/crawl/monitor.py --source pncp --mode full
```

---

## Cache IBGE Nao Atualiza

### Sintomas

```
Lookup vazio no backfill de codigos IBGE
Unmatched municipios no relatorio de enriquecimento
```

### Causas Provaveis

1. Cache IBGE expirou (TTL padrao: 7 dias) e API IBGE esta offline
2. Primeira execucao sem dados em cache
3. API IBGE retornou dados parciais ou inconsistentes

### Diagnosticos

```bash
# 1. Verificar estado do cache IBGE
python -c "
from scripts.crawl.enricher import _ibge_cache
print(f'Cache size: {_ibge_cache.size}')
print(f'Is cached: {_ibge_cache.is_cached}')
print(f'TTL: {_ibge_cache._ttl}s ({_ibge_cache._ttl/86400:.1f} days)')
"

# 2. Testar API IBGE diretamente
curl -s --max-time 10 "https://servicodados.ibge.gov.br/api/v1/localidades/municipios" | head -c 200
```

### Resolucao

```bash
# Forcar renovacao do cache (prox. chamada fara nova requisicao)
python -c "from scripts.crawl.enricher import _ibge_cache; _ibge_cache.clear(); print('Cache cleared')"

# O cache e thread-safe (asyncio.Lock) -- nao ha risco de race condition
# Nao e necessario reiniciar servicos; a limpeza e instantanea
```

### Nota Tecnica: Refatoracao do Cache

Na Story TD-6.2, o cache IBGE foi refatorado de variaveis module-level
(`_IBGE_MUNICIPIOS_CACHE`, `_IBGE_MUNICIPIOS_CACHE_TS`) para uma classe
encapsulada (`_IBGEMunicipioCache`) com `asyncio.Lock`. Isso elimina race
conditions em contexto async (debito TD-SYS-004, severidade HIGH).

A API permanece a mesma (`_fetch_ibge_municipio_lookup()`), mas o estado
interno do cache nao e mais acessivel via `global`. Para inspecao, use
o singleton `_ibge_cache`:

```python
from scripts.crawl.enricher import _ibge_cache
_ibge_cache.clear()       # forca renovacao
_ibge_cache.size          # numero de entradas em cache
_ibge_cache.is_cached     # True se ha dados em cache
```

---

## Contribuindo com Novos Casos

Encontrou um problema nao documentado aqui? Adicione ao guia:

1. Abra um PR com o novo caso no formato acima
2. Inclua: sintomas, causa raiz, diagnostico e resolucao
3. Referencie a story TD-6.1

---

> **Ultima atualizacao:** 2026-07-11
> **Story:** TD-6.1 -- Documentacao Operacional
