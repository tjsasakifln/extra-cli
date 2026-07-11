# Permissões e Papéis — Extra Consultoria

> Gerado pelo Detective em 2026-07-11T21:30:00Z
> doc_level: completo
> Base: commit e9729e1

---

## Diagnóstico

🔴 **LACUNA** — O sistema **não implementa RBAC/ACL**. É uma aplicação single-user/single-tenant operada via CLI e systemd timers.

**Evidências:**
- Zero referências a `auth`, `login`, `user`, `role`, `permission`, `token`, `session` no código Python
- PostgreSQL configurado com `scram-sha-256` para único usuário `postgres`
- Systemd timers executam como `extra-consultoria` (sudo para journalctl/systemctl)
- Relatórios PDF são gerados localmente, sem controle de acesso
- Sem API HTTP — toda interação é CLI

🟡 **INFERIDO** — Design intencional. Plataforma de consultoria opera como ferramenta interna do consultor Tiago Sasaki, não como SaaS multi-usuário.

---

## Camadas de Acesso Identificadas

Apesar de não haver RBAC, existem **camadas de isolamento** implícitas:

### 1. Acesso ao Sistema Operacional (VPS Hetzner)

| Nível | Usuário | Acesso | Propósito |
|-------|---------|--------|-----------|
| Admin | `root` | SSH key-only, porta 2222 | Provisionamento, hardening |
| Operador | `extra-consultoria` | sudo para systemctl, journalctl | Operação dos crawlers |
| Database | `postgres` | localhost apenas, scram-sha-256 | Administração do banco |

🟢 CONFIRMADO — `provision-vps.sh`, `pg_hba.conf`, `fail2ban-jail.conf`.

### 2. Acesso ao Banco de Dados

| Conexão | Método | Auth |
|---------|--------|------|
| Socket Unix (postgres user) | `peer` | OS user match |
| Socket Unix (outros users) | `scram-sha-256` | Password |
| TCP localhost | `hostssl` + `scram-sha-256` | Password |
| TCP externo | `reject` | Bloqueado |

🟢 CONFIRMADO — `pg_hba.conf:1-106`.

### 3. Acesso a APIs Externas

| API | Auth | Escopo |
|-----|------|--------|
| PNCP | Public | Leitura de licitações |
| DOM-SC | HTTP Basic + X-API-Key | Leitura de publicações |
| DOE-SC | Bearer token (login) | Leitura de matérias |
| OpenAI | API Key (env var) | Embeddings + GPT-4.1-nano |
| Portal Transparência | API Key (env var) | CEIS/CNEP |
| BrasilAPI | Public | CNPJ + IBGE |
| IBGE | Public | Dados municipais |

🟢 CONFIRMADO — `config/settings.py`, cada crawler.

### 4. Acesso ao Sistema de Arquivos

| Path | Owner | Permissões |
|------|-------|-----------|
| `/opt/extra-consultoria/` | extra-consultoria | rwx (dono) |
| `data/` | extra-consultoria | rw — outputs de relatórios, cache, logs |
| `config/` | extra-consultoria | r — configs YAML |
| `.env` | extra-consultoria | r (0400) — secrets |

🟡 INFERIDO — Baseado no script de install e práticas de hardening documentadas.

---

## Notificações e Alertas

Dois templates de notificação para falhas:

| Template | Gatilho | Destino |
|----------|---------|---------|
| `onfailure@.service` | Crawler v1 falha | POST JSON → WEBHOOK_URL |
| `extra-onfailure@.service` | Crawler v2 falha | POST JSON → WEBHOOK_URL |

🟢 CONFIRMADO — `deploy/systemd/onfailure@.service`, `extra-onfailure@.service`.

**Frequências de monitoramento:**
- Health check: a cada 30 min
- Alertas: a cada 15 min
- Métricas: a cada 1 hora

---

## Recomendações (Forward)

Caso o sistema evolua para SaaS multi-cliente, os seguintes pontos de ACL seriam necessários:

1. **Isolamento de dados por cliente** — schema `client_<id>` ou RLS no PostgreSQL
2. **Autenticação de usuários** — cada cliente acessa apenas seus próprios relatórios
3. **Rate limiting por cliente** — evitar que um cliente consuma toda a cota de API
4. **Segregação de configs setoriais** — cada cliente com seu próprio `sectors_config.yaml`
5. **API HTTP com JWT** — substituir CLI por API para acesso multi-usuário

🔴 **LACUNA** — Nada disso existe atualmente. Sistema é estritamente single-tenant.
