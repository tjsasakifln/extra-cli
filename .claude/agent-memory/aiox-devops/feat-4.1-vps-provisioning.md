---
name: feat-4.1-vps-provisioning
description: Story FEAT-4.1 — Hetzner VPS provisionada com scripts e 13 systemd timers. Decisao de criar provision-vps.sh por falta de acesso Hetzner real.
metadata:
  type: project
---
**Decisao:** Para FEAT-4.1 (Provisionar Hetzner VPS), como nao havia credenciais Hetzner Cloud disponiveis via CLI, foram gerados scripts de provisionamento completos (deploy/provision-vps.sh) e documentacao (docs/ops/vps-provisioning.md, docs/ops/vps-access.md).

**13 systemd timer pairs:** 3 novos (extra-crawl-doe-sc, extra-db-backup, extra-health-check, extra-onfailure@) + 10 existentes padronizados com prefixo extra-.

**Por que scripts vs execucao real:** Ausencia de credenciais Hetzner para provisionar CX22. Scripts autocontidos permitem execucao quando credenciais estiverem disponiveis.

**Underlying:** provision-vps.sh eh o script mestre que executa os 10 steps completos (system packages, SSH hardening, firewall, PostgreSQL, deploy, migrations, systemd timers, Storage Box). install.sh mantido para casos de uso simples (instalacao em VPS ja provisionada).

**How to apply:** Para executar provisionamento real, obter credenciais Hetzner Cloud (API token ou acesso console) e executar `bash deploy/provision-vps.sh` na VPS apos boot.
