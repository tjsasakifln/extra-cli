# Fase 0 — Ativar Root Server Netcup (RS 2000 G12 · MNZ)

**Status:** bloqueado em ação no painel Netcup (conta existe; servidor ainda não up).  
**SKU:** RS 2000 G12 · IPv4 · Manassas (MNZ)  
**SO alvo:** Ubuntu 24.04 LTS  
**Depois:** `docs/ops/vps-access.md` + `deploy/provision-vps.sh`

---

## 1. Onde clicar

| Painel | URL | Uso |
|--------|-----|-----|
| CCP (Customer Control Panel) | https://www.customercontrolpanel.de/ | Contratos, pedidos, faturas, upgrade de plano |
| SCP (Server Control Panel) | link no e-mail / CCP → produto → SCP | Power, reinstall OS, VNC, snapshots, senha root |

## 2. Checklist de ativação

1. [ ] Confirmar no CCP o contrato **RS 2000 G12** e localização **MNZ**.
2. [ ] Abrir o **SCP** do servidor.
3. [ ] **Media / Images:** selecionar imagem **Ubuntu 24.04 LTS** (64-bit).
4. [ ] **Reinstall / Install** e aguardar boot (console VNC se precisar).
5. [ ] Anotar **IPv4** público (e IPv6 se houver).
6. [ ] Obter **senha root** (e-mail de entrega ou “reset password” no SCP).
7. [ ] Testar console **VNC** no SCP (plano de emergência).
8. [ ] (Recomendado) Criar **snapshot** “fresh-ubuntu-24.04” antes do provision.
9. [ ] (Opcional) Agendar snapshots diários no SCP.

## 3. Handoff para o agente (copiar no chat)

Preencher e colar (senha **não** precisa ir pro git; pode ir só no chat seguro):

```text
NETCUP_READY
IP: x.x.x.x
OS: Ubuntu 24.04 LTS
SSH: root + password (temporária) | ou key already installed
SCP: <url ou “via CCP”>
SNAPSHOT: yes/no
BACKUP_PREFERENCE: A Netcup storage | B rsync local | C S3-compatible | D TBD
AUTH_HARDEN: yes  # permite mudar SSH para 2222 + key-only
```

## 4. Primeiro acesso (você ou agente)

```bash
# Do laptop
ssh root@x.x.x.x
# aceitar host key; autenticar com senha do e-mail

# Instalar chave de produção (se ainda não)
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo 'COLE_AQUI_O_CONTEUDO_DE_extra-consultoria-prod.pub' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

No laptop:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/extra-consultoria-prod -C "extra-prod@$(hostname)"
ssh-copy-id -i ~/.ssh/extra-consultoria-prod.pub root@x.x.x.x
```

`~/.ssh/config`:

```sshconfig
Host ec-prod
    HostName x.x.x.x
    Port 22
    User root
    IdentityFile ~/.ssh/extra-consultoria-prod
    IdentitiesOnly yes
```

Após harden (`provision-vps.sh`): mudar `Port` para `2222` e `User` para `extra-consultoria`.

## 5. Provision (só com chave root validada)

```bash
# No laptop, na raiz do repo
scp deploy/provision-vps.sh root@x.x.x.x:/root/
ssh root@x.x.x.x
export ENABLE_TIMERS=minimal
export HARDWARE_PROFILE=rs2000-16g
# opcional: export SKIP_SSH_HARDEN=1  # se quiser endurecer SSH em passo separado
bash /root/provision-vps.sh
```

## 6. O que NÃO fazer na Fase 0

- Não commitar IP/senha/DSN no git.
- Não ligar todos os timers (`ENABLE_TIMERS=full`) no primeiro boot.
- Não declarar `VPS_OPERATIONAL` só porque o servidor ligou.
- Não instalar Claude/Codex/Cursor na VPS.

## 7. Referências

- Pacote compra: `docs/ops/v6.2-procurement-credentials-package.md`
- ADR provedor: `docs/architecture/adr/ADR-007-v6.1-provider-decision.md`
- Provision: `deploy/provision-vps.sh`
- Acesso: `docs/ops/vps-access.md`
- DoD ROL 2: `DOD.md` §16+
