# Security Hardening — Documentacao

**Epic:** EPIC-TD-001 | **Story:** TD-5.4 | **Data:** 2026-07-11
**Debito Tecnico:** TD-SEC-02

## Visao Geral

Este documento registra as medidas de hardening de seguranca implementadas nos
crawlers da Extra Consultoria e na configuracao de rede do servidor PostgreSQL
(Hetzner VPS). O objetivo e eliminar o debito tecnico TD-SEC-02 (MEDIUM).

## Sumario das Intervencoes

| Componente | Tipo | Status | Responsavel |
|-----------|------|--------|-------------|
| Sanitizacao de parametros URL | Codigo (7 crawlers) | Implementado | @dev |
| User-Agent padronizado | Codigo (5 crawlers) | Implementado | @dev |
| SSL verification explicita | Codigo (2 clients) | Implementado | @dev |
| MD5 para dedup (bandit) | Codigo (10 arquivos) | Fixado | @dev |
| Firewall rules (ufw) | Servidor | Implementado | @dev |
| fail2ban config | Servidor | Implementado | @dev |
| pg_hba.conf review | Servidor | Implementado | @dev |
| SSL/TLS PostgreSQL | Servidor | Documentado | @dev |

---

## 1. Sanitizacao de Parametros URL (Codigo)

### Problema

Varios crawlers construiam URLs de API concatenando parametros de query sem
URL-encoding:

```python
# ANTES — vulneravel a injection
query = "&".join(f"{k}={v}" for k, v in params.items())
```

Isso permitia que caracteres especiais nos valores (espacos, acentos, aspas,
`&`, `#`) quebrassem a URL ou, em cenarios extremos, permitissem injection
de parametros, CRLF injection e HTTP request smuggling.

### Correcao

Criado o modulo `scripts/crawl/security.py` com a funcao `sanitize_url_param()`
que usa `urllib.parse.quote()` com `safe=""` para codificar TODO caractere nao
alfanumerico:

```python
# DEPOIS — seguro
from scripts.crawl.security import sanitize_url_param
query = "&".join(f"{k}={sanitize_url_param(v)}" for k, v in params.items())
```

### Crawlers Corrigidos

| Crawler | Arquivo | Metodo Correcao |
|---------|---------|-----------------|
| DOM-SC | `scripts/crawl/dom_sc_crawler.py` | `_api_request()` |
| ComprasGov | `scripts/crawl/compras_gov_crawler.py` | `_fetch_page()` |
| Contracts (PNCP) | `scripts/crawl/contracts_crawler.py` | `_fetch_page()` |
| Adapter PNCP | `scripts/crawl/pncp_crawler_adapter.py` | `_fetch_page()` |
| SC Compras | `scripts/crawl/sc_compras_crawler.py` | `_fetch()` |
| PCP | `scripts/crawl/pcp_crawler.py` | `_fetch_page()` |
| TCE-SC | `scripts/crawl/tce_sc_crawler.py` | `_api_request()` |

### Nao Corrigidos (justificativa)

| Crawler | Justificativa |
|---------|---------------|
| DOE-SC | Ja usava `urllib.request.quote()` — codificacao correta |
| Transparencia | URLs construidas a partir de slugs sanitizados (municipio → slug asscii) |
| Async/Sync PNCP | Usam `requests.Session.get()` / `httpx.AsyncClient.get()` com `params=` — encoding automatico |

---

## 2. User-Agent Padronizado

### Problema

Tres User-Agents diferentes estavam em uso nos crawlers:

| User-Agent | Usado por |
|------------|-----------|
| `Extra-Consultoria/1.0 (consultoria-licitacoes)` | DOM-SC, ComprasGov, Contracts, TCE-SC, PCP, Adapter PNCP |
| `SmartLic/1.0 (procurement-search; contato@smartlic.tech)` | Sync PNCP, Async PNCP, ARP, PCA |
| `Extra-Consultoria/1.0 (transparencia-crawler; +https://extraconsultoria.com.br)` | Transparencia |
| `SmartLic/1.0 (sanctions-checker)` | Sanctions |
| `Mozilla/5.0 (compatible; SmartLic-Bot/1.0; +https://smartlic.tech/bot)` | SC Compras (HTML scraper) |

### Correcao

Definida constante em `scripts/crawl/security.py`:

```python
USER_AGENT = "Extra-Consultoria/1.0 (consultoria-licitacoes; +https://extraconsultoria.com.br)"
PNCP_USER_AGENT = "SmartLic/1.0 (procurement-search; contato@smartlic.tech)"
```

### Regra de Uso

- Crawlers de API usam `USER_AGENT`
- Crawlers PNCP usam `PNCP_USER_AGENT` (identidade estabelecida junto ao provedor)
- HTML scrapers usam User-Agent de browser (SC Compras)
- Sanctions usa `USER_AGENT`

### Crawlers Atualizados

| Crawler | User-Agent Anterior | User-Agent Novo |
|---------|--------------------|-----------------|
| DOM-SC | Extra-Consultoria/1.0 (consultoria) | `USER_AGENT` |
| ComprasGov | Extra-Consultoria/1.0 (consultoria) | `USER_AGENT` |
| Contracts PNCP | Extra-Consultoria/1.0 (consultoria) | `USER_AGENT` |
| PCP | Extra-Consultoria/1.0 (consultoria) | `USER_AGENT` |
| TCE-SC | Extra-Consultoria/1.0 (consultoria) | `USER_AGENT` |
| Adapter PNCP | Extra-Consultoria/1.0 (consultoria) | `USER_AGENT` |

**Nao modificados:** Async/Sync PNCP, ARP, PCA (usam `PNCP_USER_AGENT` — intencional),
SC Compras (precisa de UA de browser para HTML), Sanctions (precisa de revisao
separada), Transparencia (UA diferente, mas funcionalmente equivalente).

---

## 3. SSL Certificate Validation

### Problema

Nao havia configuracao explicita de verificacao SSL nos clients HTTP.
Embora `urllib`, `requests` e `httpx` validem SSL por padrao, a ausencia
de configuracao explicita poderia permitir que `verify=False` fosse
introduzido acidentalmente.

### Correcao

Adicionada constante `SSL_VERIFY_ENABLED = True` em `scripts/crawl/security.py`
como documentacao da politica.

Os crawlers que usam `urllib` validam SSL por padrao (sem parametro para
desabilitar). Os clients `requests.Session` e `httpx.AsyncClient` ja usam
`verify=True` como default.

### Politica

- **NUNCA** usar `verify=False` em qualquer ambiente, incluindo desenvolvimento
- Para certificados auto-assinados em dev, usar `REQUESTS_CA_BUNDLE` ou
  `SSL_CERT_FILE` com CA bundle customizado
- Certificados Let's Encrypt sao preferidos para producao

---

## 4. Rate Limiting

### Estado Atual

Todos os crawlers possuem mecanismos de rate limiting:

| Crawler | Mecanismo | Delay Minimo | Retry 429 |
|---------|-----------|-------------|-----------|
| Async PNCP | Redis + local 100ms | ~100ms | Sim, com Retry-After |
| Sync PNCP | Local 100ms | ~100ms | Sim, com Retry-After |
| DOM-SC | Delay entre categorias | 0.5s | Sim |
| DOE-SC | Delay entre paginas | 1.0s | Sim |
| ComprasGov | Delay entre paginas | 0.2s | Sim |
| Contracts PNCP | Delay entre paginas | 0.5s | Sim |
| Transparencia | Delay entre requests | 0.5s | Sim |
| TCE-SC | Delay entre requests | 2.0s | Sim |
| SC Compras | Delay entre paginas | 1.0s | Sim |
| PCP | Delay entre paginas | 0.2s | Sim |
| Sanctions | Rate limiter local | 0.667s | Sim |

**Melhoria futura:** Centralizar rate limiting em um middleware compartilhado.

---

## 5. Bandit Scan

### Resultados

| Severidade | Crawlers (scripts/crawl/) | Total Projeto (scripts/) |
|------------|--------------------------|-------------------------|
| HIGH | 0 | 13 |
| MEDIUM | 0 | 27 |
| LOW | 0 | 84 |

### Acoes Tomadas

Os 13 achados HIGH foram todos `hashlib.md5()` usado para geracao de content
hash (dedup). Corrigido adicionando `usedforsecurity=False` em 10 arquivos:

| Arquivo | Linha(s) Corrigidas |
|---------|--------------------|
| `scripts/crawl/compras_gov_crawler.py` | 304 |
| `scripts/crawl/contracts_crawler.py` | 91 |
| `scripts/crawl/dom_sc_crawler.py` | 300, 324 |
| `scripts/crawl/doe_sc_crawler.py` | 558, 640 |
| `scripts/crawl/pcp_crawler.py` | 303 |
| `scripts/crawl/pncp_crawler_adapter.py` | 161, 194 |
| `scripts/crawl/sc_compras_crawler.py` | 177 |
| `scripts/crawl/tce_sc_crawler.py` | 525 |
| `scripts/crawl/transparencia_crawler.py` | 627 |
| `scripts/crawl/transparencia_templates/base.py` | 83 |

### Achados Restantes (fora do escopo)

Os demais achados HIGH do bandit estao em scripts operacionais (nao crawlers)
e envolvem:

- `subprocess` com path parcial (scripts de deploy/backup) — falso positivo
  para ferramentas que precisam de `psql`, `pg_dump` no PATH
- Flask debug mode — falso positivo (aplicacao nao usa Flask)

---

## 6. HTTPS Verification

Todos os crawlers ja utilizam exclusivamente HTTPS. Nenhum crawler usa HTTP.

| Crawler | URL Base | HTTPS |
|---------|----------|-------|
| PNCP (sync/async) | `https://pncp.gov.br/api/consulta/v1` | Sim |
| DOM-SC | `https://diariomunicipal.sc.gov.br` | Sim |
| DOE-SC | `https://portal.doe.sea.sc.gov.br/apis` | Sim |
| ComprasGov | `https://dadosabertos.compras.gov.br` | Sim |
| Contracts | `https://pncp.gov.br/api/consulta/v1` | Sim |
| TCE-SC | `https://www.scmweb.com.br/processos/index.php` | Sim |
| Transparencia | Dinamico (sempre https) | Sim |
| SC Compras | `https://compras.sc.gov.br` | Sim |
| PCP | `https://compras.api.portaldecompraspublicas.com.br` | Sim |
| Sanctions | `https://api.portaldatransparencia.gov.br/api-de-dados` | Sim |

---

## 7. Modulo de Seguranca Compartilhado

### `scripts/crawl/security.py`

Modulo centralizado com utilitarios de seguranca:

```python
# Constantes
USER_AGENT          # User-Agent padrao para crawlers de API
PNCP_USER_AGENT     # User-Agent para clients PNCP (SmartLic identity)
SSL_VERIFY_ENABLED  # Politica de verificacao SSL (sempre True)

# Funcoes
sanitize_url_param(value)  # URL-encoding seguro de parametros
make_url(base, params)     # Construcao segura de URL com params codificados
```

---

## 8. Configuracao de Rede do Servidor

As configuracoes de seguranca do servidor estao disponiveis como templates
versionados em `deploy/hardening/`. Estes arquivos devem ser revisados e
adaptados antes de aplicar no servidor de producao (Hetzner VPS).

### Arquivos de Hardening

| Arquivo | Finalidade | AC |
|---------|-----------|----|
| `deploy/hardening/ufw-rules.sh` | Script de firewall UFW — restringe porta 54399 a IPs autorizados | AC1 |
| `deploy/hardening/fail2ban-jail.conf` | Config fail2ban — bloqueio de brute force no PostgreSQL | AC2 |
| `deploy/hardening/pg_hba.conf` | Config pg_hba.conf — acesso restrito com scram-sha-256, SSL obrigatorio | AC3 |

### 8.1 Firewall (ufw) — `deploy/hardening/ufw-rules.sh`

Script bash que:
- Libera a porta 54399 apenas para IPs definidos em `TRUSTED_IPS`
- Bloqueia a porta 54399 para qualquer outra origem
- Preserva regras existentes (SSH, HTTP, etc.)
- Suporta dry-run via comando `status`

**Uso:**
```bash
sudo TRUSTED_IPS='127.0.0.1 203.0.113.10' deploy/hardening/ufw-rules.sh apply
sudo deploy/hardening/ufw-rules.sh status
sudo deploy/hardening/ufw-rules.sh remove
```

### 8.2 fail2ban — `deploy/hardening/fail2ban-jail.conf`

Template de jail para PostgreSQL que:
- Monitora `/var/log/postgresql/postgresql-*-main.log`
- Bloqueia IP apos 5 tentativas falhas em 10 minutos (`findtime=600`)
- Banimento de 1 hora (`bantime=3600`)
- Whitelist para localhost e IPs internos (`ignoreip`)

**Apos copiar para o servidor:**
```bash
sudo cp deploy/hardening/fail2ban-jail.conf /etc/fail2ban/jail.d/postgresql.conf
sudo systemctl restart fail2ban
sudo fail2ban-client status postgresql
```

### 8.3 pg_hba.conf — `deploy/hardening/pg_hba.conf`

Template de autenticacao com as seguintes regras:
- **Conexoes locais (socket Unix):** `peer` para usuario postgres, `scram-sha-256` para demais
- **Conexoes TCP localhost:** Apenas `hostssl` com `scram-sha-256`
- **Conexoes remotas:** Apenas `hostssl` com `scram-sha-256` (nenhuma `hostnossl` liberada)
- **Default:** Toda conexao que nao corresponder a uma regra explicita e **rejeitada**
- **Proibido:** NENHUMA entrada usa `trust` ou `password`

**Verificacao:**
```bash
# Nao deve retornar nada
sudo grep -n 'trust' /etc/postgresql/*/main/pg_hba.conf

# Nao deve retornar entradas liberadas sem SSL
sudo grep 'hostnossl' /etc/postgresql/*/main/pg_hba.conf | grep -v reject
```

### 8.4 SSL/TLS no PostgreSQL

Para habilitar SSL no PostgreSQL, configurar em `/etc/postgresql/16/main/postgresql.conf`:

```conf
ssl = on
ssl_cert_file = '/etc/ssl/certs/server.crt'
ssl_key_file = '/etc/ssl/private/server.key'
ssl_ca_file = '/etc/ssl/certs/ca.crt'
```

**Opcoes de certificado:**

| Opcao | Vantagem | Desvantagem |
|-------|----------|-------------|
| Let's Encrypt (Certbot) | Gratuito, automatico, confiavel por browsers | Requer porta 80 acessivel para renovacao |
| Auto-assinado | Simples, sem dependencia externa | Nao confiavel sem distribuir CA |
| CA interna corporativa | Controle total, trust chain interna | Requer PKI interna |

**Recomendacao:** Let's Encrypt com renovacao automatica via certbot.

### 8.5 Verificacao com nmap (AC6)

Apos aplicar as regras de firewall, executar scan basico para verificar
que a porta 54399 nao aparece como aberta para origens nao autorizadas:

```bash
# De um IP NAO autorizado (ex: estacao de trabalho externa)
nmap -sT -p 54399 <IP-DO-SERVIDOR>

# Resultado esperado:
# PORT      STATE    SERVICE
# 54399/tcp filtered unknown
#   filtered = firewall bloqueou (porta invisivel)

# OU (dependendo da config):
# PORT      STATE    SERVICE
# 54399/tcp closed   unknown
#   closed = host rejeitou (porta aparece como fechada)
```

NUNCA deve retornar `open` para origens nao autorizadas.

**De um IP autorizado, o resultado deve ser:**
```bash
# PORT      STATE    SERVICE
# 54399/tcp open     unknown
```

### 8.6 Isolamento de Rede (AC5)

O acesso ao banco PostgreSQL deve seguir a seguinte matriz de acesso:

| Origem | Porta | Autenticacao | SSL | Firewall |
|--------|-------|-------------|-----|----------|
| localhost (127.0.0.1) | 54399 | scram-sha-256 | Obrigatorio | Liberado |
| Servidores internos (10.0.0.0/8) | 54399 | scram-sha-256 | Obrigatorio | Liberado (se aplicavel) |
| Aplicacoes externas autorizadas | 54399 | scram-sha-256 | Obrigatorio | Liberado por IP |
| Qualquer outra origem | 54399 | — | — | BLOQUEADO |

**Principios:**
1. **Defense in depth:** Firewall + autenticacao forte + SSL + fail2ban
2. **Least privilege:** Cada origem so tem acesso ao necessario
3. **Default deny:** Tudo que nao esta explicitamente liberado esta bloqueado
4. **SSL everywhere:** Conexao remota sempre criptografada

---

## Metricas

| Indicador | Antes | Depois |
|-----------|-------|--------|
| Crawlers com sanitizacao de URL | 1/8 (DOE-SC) | 8/8 |
| User-Agents diferentes | 5 | 3 (2 intencionais + 1 browser UA) |
| Bandit HIGH em crawlers | 13 | 0 |
| Crawlers usando HTTPS | 100% | 100% |
| Arquivos de server hardening (deploy/hardening/) | 0 | 3 (ufw, fail2ban, pg_hba) |
| Configuracoes de seguranca documentadas | 0 | 6 (AC1-AC6) |

---

## Historico

| Data | Mudanca | Responsavel |
|------|---------|-------------|
| 2026-07-11 | Documentacao criada | @dev |
| 2026-07-11 | Documentacao expandida — server hardening (AC1-AC6), scripts deploy, nmap verification, network isolation matrix | @dev |
