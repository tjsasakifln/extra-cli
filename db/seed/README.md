# Seed Scripts — db/seed/

Scripts para popular tabelas do banco de dados PostgreSQL a partir de
planilhas, CSVs e APIs externas.

## Seed: SC Public Entities

### Descricao

`seed_sc_entities.py` importa os ~2.085 entes publicos catarinenses da
planilha `Extra - alvos de licitacao. R-0.xlsx` para a tabela
`sc_public_entities`, com:

- Resolucao de codigos IBGE faltantes via BrasilAPI (com cache local)
- Calculo de distancia (Haversine) de Florianopolis
- Clasificacao raio_200km (<= 200 km)
- Upsert idempotente via `ON CONFLICT (cnpj_8) DO UPDATE`
- `is_active = TRUE` para todos os registros

### Pre-requisitos

- Python 3.10+
- `psycopg2` (conector PostgreSQL): `pip install psycopg2-binary`
- `openpyxl` (leitor Excel): `pip install openpyxl`
- `requests` (requisicoes HTTP): `pip install requests`
- Planilha `Extra - alvos de licitacao. R-0.xlsx` na raiz do projeto
- Banco PostgreSQL acessivel (ver `LOCAL_DATALAKE_DSN`)

### Instalacao

```bash
pip install psycopg2-binary openpyxl requests
```

### Uso Basico

```bash
# Usando DSN da variavel de ambiente
python -m db.seed.seed_sc_entities

# DSN explicito
python -m db.seed.seed_sc_entities --dsn postgresql://user:pass@host:5432/db

# Dry-run: mostra o que seria inserido sem tocar no banco
python -m db.seed.seed_sc_entities --dry-run

# Pular busca de IBGE (usar so o cache local)
python -m db.seed.seed_sc_entities --no-ibge-fetch
```

### Idempotencia

O script pode ser executado quantas vezes necessario:

```bash
# Primeira execucao
python -m db.seed.seed_sc_entities
# Saida: Upsert complete: 2085 inserted, 0 updated

# Segunda execucao (nada muda)
python -m db.seed.seed_sc_entities
# Saida: Upsert complete: 0 inserted, 0 updated  (ou N updated se houve mudancas)

# Apos atualizar a planilha com novos entes
python -m db.seed.seed_sc_entities
# Saida: Upsert complete: 5 inserted, 2085 updated
```

O `ON CONFLICT (cnpj_8) DO UPDATE` garante que rodar 2x nao duplica
registros. Registros existentes sao atualizados com os dados mais
recentes da planilha.

### Cache IBGE

O script mantem um cache local dos codigos IBGE em `data/ibge_cache.json`
para evitar chamadas repetidas a API. O cache e criado automaticamente
na primeira execucao.

Para forcar refresh do cache, delete o arquivo:
```bash
rm data/ibge_cache.json
python -m db.seed.seed_sc_entities
```

### Variaveis de Ambiente

| Variavel | Default | Descricao |
|----------|---------|-----------|
| `LOCAL_DATALAKE_DSN` | `required via LOCAL_DATALAKE_DSN (no default password)` | String de conexao PostgreSQL |
| `IBGE_CACHE_PATH` | `data/ibge_cache.json` | Caminho para o cache IBGE |

### Execucao Agendada

Para re-execucao periodica (ex.: novos entes adicionados a planilha):

```bash
# Adicionar ao crontab (executar todo dia 1 de cada mes as 3h)
0 3 1 * * cd /caminho/para/o/projeto && python -m db.seed.seed_sc_entities >> /var/log/seed_sc_entities.log 2>&1
```

### Verificacao

```sql
-- Total
SELECT COUNT(*) FROM sc_public_entities;

-- Ativos
SELECT COUNT(*) FROM sc_public_entities WHERE is_active = TRUE;

-- Com IBGE pendente
SELECT municipio, COUNT(*) FROM sc_public_entities
WHERE codigo_ibge IS NULL
GROUP BY municipio;

-- Dentro do raio de 200km de Florianopolis
SELECT COUNT(*) FROM sc_public_entities WHERE raio_200km = TRUE;
```
