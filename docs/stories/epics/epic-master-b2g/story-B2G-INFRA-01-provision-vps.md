---
story_id: B2G-INFRA-01
title: "Provisionar VPS Hetzner CX22 e preparar ambiente base"
status: ready
priority: P0
risk_level: STANDARD
effort: M
agent: "@devops"
epic: EPIC-MASTER-B2G-READINESS
phase: 1
depends_on: [B2G-FIX-01, B2G-FIX-02, B2G-FIX-03, B2G-FIX-04]
blocks: [B2G-INFRA-02, B2G-INFRA-03, B2G-INFRA-04, B2G-CRAWL-01]
---

# Story B2G-INFRA-01: Provisionar VPS Hetzner

## Problema

O deploy atual roda apenas em ambiente local (WSL2). Para operação contínua, é necessária uma VPS Hetzner. Scripts de provisionamento existem (`deploy/provision-vps.sh`, 405 linhas) mas **nunca foram executados em VPS real**. Nomenclatura de systemd timers está inconsistente entre `install.sh` (padrão antigo) e `provision-vps.sh` (padrão novo `extra-*`), sendo que 11 dos 13 timers listados no provision-vps.sh não correspondem a arquivos reais em `deploy/systemd/`.

## Valor de Negócio

VPS permite crawlers 24/7, elimina dependência de máquina local ligada, e é o pré-requisito para qualquer operação contínua. Custo: ~€7.40/mês (CX22 €4.50 + Storage Box €2.90).

## Escopo

### IN
- Criar VPS Hetzner CX22 (2 vCPU, 4GB RAM, 40GB SSD) via `hcloud` CLI
- Ubuntu 24.04 LTS, região Nuremberg
- Executar `provision-vps.sh` e validar cada step
- Corrigir TODOS os nomes de systemd timers para padrão unificado
- Unificar `install.sh` e `provision-vps.sh` — eliminar duplicação
- Documentar IP, credenciais, e acesso no formato `docs/ops/vps-access.md`
- Validar que `systemctl list-timers 'extra-*'` mostra todos os timers

### OUT
- Configuração de backup (B2G-INFRA-04)
- Deploy de aplicação com dados reais (B2G-INFRA-02)
- Terraform/OpenTofu (manter shell script)

## Acceptance Criteria

### AC1: VPS criada e acessível
**Given** credenciais Hetzner Cloud (API token)
**When** `hcloud server create` é executado com os parâmetros CX22
**Then** VPS fica acessível via SSH em até 2 minutos
**And** IP documentado em `docs/ops/vps-access.md`

### AC2: provision-vps.sh executa limpo
**Given** VPS Ubuntu 24.04 recém-criada
**When** `bash deploy/provision-vps.sh` executa como root
**Then** todos os 10 steps completam sem erro
**And** output final mostra "VPS Provisioning Complete"

### AC3: Nomenclatura de systemd unificada
**Given** timers instalados em `/etc/systemd/system/`
**When** `ls /etc/systemd/system/extra-*` executa
**Then** TODOS os timers seguem o padrão `extra-*` (nomes de arquivo = nomes de timer)
**And** não existem timers com padrão antigo (`pncp-*`, `dom-sc-*`, etc.)

### AC4: systemctl list-timers funcional
**Given** timers instalados e habilitados
**When** `systemctl list-timers 'extra-*'` executa
**Then** todos os timers listados com próximo agendamento

### AC5: Scripts de provisionamento unificados
**Given** `deploy/install.sh` e `deploy/provision-vps.sh`
**When** comparados
**Then** usam a MESMA lista de timers
**And** usam a MESMA nomenclatura
**And** não há duplicação de lógica

## Tasks

- [ ] Task 1: Obter API token Hetzner Cloud
- [ ] Task 2: Criar VPS via `hcloud server create` (ou console)
- [ ] Task 3: Configurar DNS (se aplicável) e documentar IP
- [ ] Task 4: Executar `provision-vps.sh` e corrigir falhas
- [ ] Task 5: Renomear TODOS os arquivos em `deploy/systemd/` para padrão `extra-*`
- [ ] Task 6: Atualizar `provision-vps.sh` com lista correta de timers
- [ ] Task 7: Unificar `install.sh` para delegar ao `provision-vps.sh` ou remover
- [ ] Task 8: Validar `systemctl list-timers 'extra-*'`
- [ ] Task 9: Atualizar `docs/ops/vps-access.md` com dados reais

## Definition of Done

- [ ] VPS Hetzner CX22 provisionada e acessível via SSH
- [ ] provision-vps.sh executado com sucesso (todos os steps)
- [ ] 20+ systemd timers instalados com nomenclatura unificada `extra-*`
- [ ] systemctl list-timers 'extra-*' funcional
- [ ] install.sh e provision-vps.sh consistentes
- [ ] docs/ops/vps-access.md atualizado com dados reais
- [ ] Firewall ativo (ufw), SSH em porta não-padrão, fail2ban ativo

## Arquivos Afetados

- `deploy/provision-vps.sh` (correção de nomes de timers)
- `deploy/install.sh` (unificação ou remoção)
- `deploy/systemd/*` (rename para padrão `extra-*`)
- `docs/ops/vps-access.md`
- `docs/ops/vps-provisioning.md`

## Bloqueadores Externos

- **Credenciais Hetzner Cloud** (API token) — necessário antes de iniciar
