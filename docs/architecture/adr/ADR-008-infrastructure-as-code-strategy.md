# ADR-008: Estratégia de Infrastructure as Code

**Status:** Proposed
**Date:** 2026-07-15
**Decision by:** @architect (Aria) + @devops (Gage)

---

## 1. Contexto

O projeto Extra Consultoria gerencia infraestrutura em nuvem para execução de crawlers, banco de dados, relatórios e rotinas operacionais. É necessário definir a estratégia de automação de infraestrutura em dois estágios:

1. **Estágio atual (máquina única):** uma VPS de produção com PostgreSQL, aplicação Python, systemd timers e rotinas de backup.
2. **Estágio futuro (múltiplas máquinas):** possibilidade de staging, workers separados, banco separado, redes privadas, firewalls gerenciados.

Documentos antigos mencionavam Terraform como baseline, mas o escopo atual (máquina única) não justifica provisionamento programático de infraestrutura.

---

## 2. Decisão

### Estágio 1: Ansible como ferramenta primária

**Ansible configura sistemas.** É a ferramenta principal para o estágio de máquina única:

- Instalação e configuração de pacotes (PostgreSQL, Python, systemd, ferramentas de backup)
- Criação de usuários e grupos
- Deploy de código e dependências
- Configuração de systemd timers e serviços
- Hardening de segurança (SSH, firewall, fail2ban)
- Configuração de backups
- Tuning de PostgreSQL
- Configuração de monitoramento

O playbook Ansible substitui o script `deploy/provision-vps.sh` como forma canônica de configurar a VPS, oferecendo idempotência, rastreabilidade e reexecução segura.

### Estágio 2: OpenTofu ou Terraform como camada futura

**OpenTofu/Terraform provisionam infraestrutura.** Serão introduzidos quando houver infraestrutura efetivamente provisionável por API:

- VPS criada e destruída por API
- Staging e produção como ambientes distintos
- Volumes adicionais
- Firewalls gerenciados
- Redes privadas
- DNS
- Múltiplas máquinas
- Workers separados
- Banco separado da aplicação

---

## 3. Separação de Responsabilidades

| Ferramenta | Responsabilidade | Quando |
|-----------|-----------------|--------|
| **Ansible** | Configuração de sistemas | Desde o início (Estágio 1) |
| **OpenTofu/Terraform** | Provisionamento de infraestrutura | Quando houver API de infraestrutura (Estágio 2) |

As ferramentas são complementares, não concorrentes. Ansible configura o que já existe. Terraform/OpenTofu cria o que ainda não existe.

---

## 4. Gatilhos Objetivos para Adoção do Estágio 2

OpenTofu ou Terraform devem ser adotados quando pelo menos **dois** dos seguintes critérios forem atendidos:

1. Necessidade de recriar a VPS a partir de código (disaster recovery, ambiente de staging idêntico).
2. Necessidade de gerenciar múltiplas máquinas (produção + staging, workers separados).
3. Necessidade de gerenciar recursos de rede (VPC, subnets, firewalls via API).
4. Necessidade de gerenciar DNS como código.
5. Necessidade de gerenciar volumes/block storage como código.
6. Mudança para provedor com API de infraestrutura madura (Hetzner Cloud, AWS, GCP, Azure).

**Enquanto houver apenas uma máquina fixa sem necessidade de recriação programática, Ansible sozinho é suficiente.**

---

## 5. O que NÃO faz parte do estágio atual

- **Kubernetes:** não há carga de trabalho que justifique orquestração de containers. Systemd é adequado para serviços e timers em máquina única.
- **Docker em produção:** a aplicação Python pode executar diretamente no SO com virtualenv/uv. Docker é usado apenas para desenvolvimento local (container de teste PostgreSQL).
- **Múltiplas máquinas:** não há necessidade atual de separar banco, aplicação e workers em máquinas distintas.
- **Redis, Kafka, Elasticsearch, filas distribuídas:** sem necessidade comprovada.

---

## 6. Evolução de Dependências Python

A documentação recomenda como evolução futura:

- Adoção de `pyproject.toml` como arquivo central de configuração do projeto (já existe parcialmente para ruff, mypy, bandit).
- Uso de `uv` para gerenciamento de dependências e ambientes virtuais.
- Geração e versionamento de `uv.lock` para reprodutibilidade.
- Eliminação gradual de dependências abertas apenas com `>=`.
- Criação de ambientes reproduzíveis para local, CI e produção.

Esta evolução não é executada nesta tarefa. O `requirements.txt` permanece como fonte de dependências atual.

---

## 7. Consequências

- `deploy/provision-vps.sh` permanece como implementação existente, mas o caminho canônico de configuração passa a ser playbook Ansible.
- Documentação operacional é atualizada para refletir Ansible como ferramenta primária de configuração.
- Terraform/OpenTofu não são mais apresentados como baseline ou progresso automático.
- Referências a `hcloud` CLI e Hetzner Cloud API são mantidas como documentação histórica, não como requisito.
- A documentação de deploy passa a descrever fluxo determinístico e repetível (não dependente de sessão interativa do Claude Code).

---

## 8. Referências

- ADR-007: Cloud Hosting Strategy (`docs/architecture/adr/ADR-007-cloud-hosting-strategy.md`)
- Cloud Deployment Plan: `docs/ops/cloud-deployment-plan.md`
- VPS Provisioning (existente): `docs/ops/vps-provisioning.md`
- Deploy scripts: `deploy/provision-vps.sh`, `deploy/install.sh`

## Amendment 2026-07-23

Minimal playbook materialized at `deploy/ansible/site-contracts-ops.yml` (inventory `deploy/ansible/inventory/hosts.yml`) for idempotent unit/timer apply. Host was bootstrapped via shell; Ansible is now the re-apply path for contracts ops surface.
