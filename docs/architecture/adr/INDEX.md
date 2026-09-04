# Índice de ADRs — Extra Consultoria

**Atualizado:** 2026-09-04

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
| ADR-038 | National census entity-authority boundary | **Proposed** (2026-08-29) |
| ADR-039 | Desacoplamento da ingestão PNCP do plano comercial outbound | **Accepted/Effective** (2026-09-02) — PR #535 merge `ad4d18f8`; QA `d99dc92c`; story Done / PASS. Não adota `COMMERCIAL_AUTHORITY/2.0`. |
| ADR-040 | Fundação do motor CONFENGE_LIVE_INTELLIGENCE (decisões abertas do AC12) | **Accepted** (2026-09-02) — gate HIGH-RISK de arquitetura FECHADO (`gate_satisfied: true`) com AR-3/AR-4 registradas como dívida. Piso de evidência de arquitetura, **não** veredito do @qa. Ver §"Fechamento do gate HIGH-RISK" |

## ADRs revogadas / supersedidas

A cascata systemd `OnSuccess` PNCP→outbound descrita em handoffs anteriores a
2026-09-02 está **supersedida** por ADR-039. O arquivo ADR-038 *deste* índice
permanece a fronteira de autoridade do censo nacional; a ADR-038 de população
`COMMERCIAL_AUTHORITY/2.0` existiu só no PR #528 e **não** é vigente.

## Notas de runtime (não substituem ADR formal)

- **2026-07-23:** host de record = Netcup RS 2000 / Debian 13 / PG 17 / 16 GB; app `/opt/extra-consultoria`.  
- Claims `VPS_OPERATIONAL` / `LOCAL_READY` exigem gates DOD + evidência — não o mero host.

## Como atualizar

1. Criar ADR nova em `docs/architecture/adr/`.
2. Atualizar este `INDEX.md` (vigente ou revogada).
3. Referenciar no README/PRD apenas ADRs vigentes.
4. Não inventar selos de gate em texto de ADR sem evidência.
