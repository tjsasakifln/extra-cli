# Tasks — Módulo `deploy`

> 🟢 CONFIRMADO

### T1: Install Script
- **Arquivo legado:** `deploy/install.sh`
- **Confiança:** 🟢
- **Descrição:** Bash script: apt-get dependências, configurar PostgreSQL 17, aplicar 12 migrations, seed entities, instalar 13 systemd timers, habilitar e iniciar.
- **Critério de pronto:** Script executável. Idempotente. Verificação pós-install.

### T2: Systemd Timers
- **Arquivo legado:** `deploy/systemd/*.service`, `*.timer`
- **Confiança:** 🟢
- **Descrição:** 13 pares service+timer. Staggered schedules. `RandomizedDelaySec=300`. `OnFailure=onfailure@%N.service`.
- **Critério de pronto:** Todos os timers ativos. Sem overlaps. OnFailure funcional.
