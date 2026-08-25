# Índice de ADRs — Extra Consultoria

**Atualizado:** 2026-08-25

| ADR | Título | Status |
|-----|--------|--------|
| ADR-007 | Cloud hosting strategy | **Vigente** — runtime documentado: **Netcup** RS 2000 / Debian 13 / PG 17 (`ssh ec-prod`). Decisão de campanha original em ADR-007-v6.1. |
| ADR-007-v6.1 | Provider decision notes (PE-30D) | **Vigente** (complementar; preferência Netcup, fallback Hetzner; SO/DB da nota original podem divergir do host real — preferir inventário live) |
| ADR-008 | Infrastructure as code strategy | **Vigente** — playbook mínimo `deploy/ansible/site-contracts-ops.yml` (2026-07-23) |
| ADR-017 | Workspace CLI facade | **Vigente** |
| ADR-018 | Coverage contract multi-metric | **Vigente** |
| ADR-019 | Entity source registry canonical | **Vigente** |
| ADR-020 | Operational data not in git | **Vigente** |
| ADR-021 | Adapter architecture PNCP 429 fail-closed | **Vigente** |
| ADR-022 | Client profile sole commercial law | **Vigente** |
| ADR-028 | Entity freshness by capability (canonical universe) | **Vigente** |
| ADR-029 | Canonical full suite green | **Accepted** (2026-07-21) |
| ADR-030 | Dual capability coverage truth | **Accepted** (2026-07-21) |
| ADR-034 | CONFENGE commercial lead evidence model | **Accepted** (2026-07-25) |
| ADR-035 | CONFENGE authoritative target-fit feed | **Proposed** (2026-08-12) |
| ADR-036 | Universo integral e GO do piloto CONFENGE | **Proposed** (2026-08-10) |
| ADR-037 | Papel da contratada e primeiro toque delegado da CONFENGE | **Accepted by founder decision** (2026-08-25) |

## ADRs revogadas / supersedidas

Nenhuma ADR neste diretório está marcada como **Revogada** na data deste índice.  
Se uma ADR for supersedida, registre aqui com data, ADR substituta e motivo.

## Notas de runtime (não substituem ADR formal)

- **2026-07-23:** host de record = Netcup RS 2000 / Debian 13 / PG 17 / 16 GB; app `/opt/extra-consultoria`.  
- Claims `VPS_OPERATIONAL` / `LOCAL_READY` exigem gates DOD + evidência — não o mero host.

## Como atualizar

1. Criar ADR nova em `docs/architecture/adr/`.
2. Atualizar este `INDEX.md` (vigente ou revogada).
3. Referenciar no README/PRD apenas ADRs vigentes.
4. Não inventar selos de gate em texto de ADR sem evidência.
