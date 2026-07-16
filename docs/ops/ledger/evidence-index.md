# Índice de evidências por seção do DoD

> **Story:** PE-G0-03 (G0.4)  
> **Fonte:** [`DOD.md`](../../../DOD.md)  
> **Atualizado em:** 2026-07-16  
> **Como atualizar:** ver [`README.md`](./README.md)

**Legenda de status:** `OPEN` · `PARTIAL` · `DONE` · `BLOCKED`

Regras de agregação da seção:

- `DONE` — todos os itens obrigatórios da seção concluídos com evidência;
- `PARTIAL` — ao menos um item com evidência ou progresso documentado, sem fechar a seção;
- `BLOCKED` — seção inteira ou item crítico bloqueado por dependência externa;
- `OPEN` — sem evidência no HEAD para a seção.

---

## Contrato funcional e regras gerais (pré-ROL)

| Seção | ROL | Status | Evidência path | Data |
|-------|-----|--------|----------------|------|
| §1 Como usar este documento | — | PARTIAL | `DOD.md` (itens versionamento + natureza checklist); campanha `docs/stories/epics/epic-plano-executivo-30d/` | 2026-07-16 |
| §2 Contrato funcional do projeto | — | OPEN | — | — |
| §2.1 Objetivo | — | OPEN | — | — |
| §2.2 Escopo incluído | — | OPEN | — | — |
| §2.3 Escopo excluído | — | OPEN | — | — |
| §2.4 Usuário e forma de uso | — | OPEN | — | — |
| §2.5–2.6 Entregáveis / capacidades (se presentes no DoD) | — | OPEN | — | — |

---

## ROL 1 — Estágio atual (local-first)

| Seção | ROL | Status | Evidência path | Data |
|-------|-----|--------|----------------|------|
| §3 Autoridade do universo monitorado | ROL1 | OPEN | Planejado: planilha canônica + seed; runbook `docs/operations/universe-snapshot-runbook.md` (infra, não aceite) | — |
| §4 Definição objetiva de cobertura | ROL1 | OPEN | Meta 95% sob freeze G0.3 → path alvo `docs/baseline/scope-freeze-95.md` (PE-G0-02) | — |
| §5 Ambiente local reproduzível | ROL1 | OPEN | PE-L1-01 | — |
| §6 Integridade do schema e persistência | ROL1 | OPEN | PE-L1-01; audits em `docs/audits/schema-divergence-DATA-FOUNDATION-2026-07-16.md` (diagnóstico, não aceite) | — |
| §7 Registro de fontes e aplicabilidade | ROL1 | OPEN | PE-C2-02 / research `docs/research/source-runtime-matrix-2026-07-16.md` | — |
| §8 Editais abertos | ROL1 | OPEN | PE-C2-*; cobertura não aceita sem runtime | — |
| §9 Contratos históricos | ROL1 | OPEN | PE-K3-01 | — |
| §10 Concorrentes e vencedores | ROL1 | OPEN | — | — |
| §11 Referências de valores | ROL1 | OPEN | — | — |
| §12 Pipeline de inteligência e relatórios | ROL1 | OPEN | PE-L1-03 (golden path) | — |
| §13 Testes do estágio atual | ROL1 | OPEN | PE-Q5-01 | — |
| §14 Backup e recuperação local | ROL1 | OPEN | PE-L1-03; `docs/ops/backup.md` (doc, não prova de restore) | — |
| §15 Aceite manual do estágio atual | ROL1 | OPEN | Requer Tiago | — |

---

## ROL 2 — Após provisionar a VPS

| Seção | ROL | Status | Evidência path | Data |
|-------|-----|--------|----------------|------|
| §16 Decisão e contratação da infraestrutura | ROL2 | OPEN | Fora da janela GATE-0/1; credenciais V6.2 bloqueadas na epic | — |
| §17 Provisionamento básico | ROL2 | OPEN | `docs/ops/vps-provisioning.md` (doc prévia; não é aceite DoD) | — |
| §18 Hardening da VPS | ROL2 | OPEN | — | — |
| §19 Deploy reproduzível | ROL2 | OPEN | — | — |
| §20 Migração do banco local para a VPS | ROL2 | OPEN | — | — |
| §21 Serviços e timers | ROL2 | OPEN | — | — |
| §22 Backup e disaster recovery na VPS | ROL2 | OPEN | — | — |
| §23 Observabilidade e alertas | ROL2 | OPEN | — | — |
| §24 Operação contínua e independência do ambiente local | ROL2 | OPEN | — | — |

> ROL 2 **não bloqueia** `BASELINE_LOCKED` nem `LOCAL_FOUNDATION`. Bloqueia `VPS_OPERATIONAL` / `PROJECT_DONE`.

---

## ROL 3 — Independente de infraestrutura

| Seção | ROL | Status | Evidência path | Data |
|-------|-----|--------|----------------|------|
| §25 Verdade, linguagem e claims permitidos | ROL3 | PARTIAL | Ledger ativo (`docs/ops/ledger/`); freeze de claims planejado em `docs/baseline/scope-freeze-95.md` (PE-G0-02) | 2026-07-16 |
| §26 Simplicidade arquitetural | ROL3 | OPEN | — | — |
| §27 Organização e manutenção do código | ROL3 | OPEN | — | — |
| §28 Segurança proporcional ao uso pessoal | ROL3 | OPEN | — | — |
| §29 Rastreabilidade e auditoria | ROL3 | PARTIAL | Este ledger + stories PE-G0-*; runs/coverage ledger de DB ainda não aceitos como DoD DONE | 2026-07-16 |
| §30 Performance e custo | ROL3 | OPEN | — | — |
| §31 Documentação operacional | ROL3 | PARTIAL | `docs/ops/*` existente; gaps de runbooks de coverage/freshness | 2026-07-16 |
| §32 Agnosticidade de agentes, IDEs e modelos | ROL3 | OPEN | DoD §32 exige fonte canônica sem dependência de agente | — |
| §33 Governança pessoal do desenvolvimento | ROL3 | PARTIAL | [`raci-kickoff.md`](./raci-kickoff.md) (G0.5) | 2026-07-16 |
| §34 Aceite final da utilidade | ROL3 | OPEN | Requer Tiago + gates | — |

---

## Gates consolidados (DoD §35) e gates da campanha 30d

| Seção / Gate | ROL / Campanha | Status | Evidência path | Data |
|--------------|----------------|--------|----------------|------|
| §35.1 `LOCAL_READY` | DoD | OPEN | Depende ROL1 + ROL3 aplicável + 95% editais/contratos | — |
| §35.2 `VPS_OPERATIONAL` | DoD | OPEN | Depende ROL2 | — |
| §35.3 `PROJECT_DONE` | DoD | OPEN | Depende LOCAL_READY + VPS_OPERATIONAL + ROL3 | — |
| **GATE-0 `BASELINE_LOCKED`** | Campanha G0.1–G0.5 | **PARTIAL** | [`GATE-0-BASELINE-LOCKED.md`](./GATE-0-BASELINE-LOCKED.md) | 2026-07-16 |
| GATE-1 `LOCAL_FOUNDATION` | Campanha L1.1–L1.8 | OPEN | Path alvo: `docs/ops/ledger/GATE-1-LOCAL-FOUNDATION.md` (PE-L1-04) | — |

---

## Snapshot GATE-0 (detalhe operacional)

| Critério G0 | Task | Status | Evidência path | Data |
|-------------|------|--------|----------------|------|
| DoD versionado na raiz | G0.1 | PARTIAL | `DOD.md`; plano `extra-consultoria-plano-executivo.html`; story PE-G0-01 (`InProgress`) | 2026-07-16 |
| Rebaseline HEAD | G0.2 | OPEN | Path alvo: `docs/baseline/rebaseline-2026-07-16.md` (PE-G0-02) | — |
| Freeze meta 95% / claims | G0.3 | OPEN | Path alvo: `docs/baseline/scope-freeze-95.md` (PE-G0-02) | — |
| Ledger de evidências ativo | G0.4 | PARTIAL | `docs/ops/ledger/README.md` + este índice | 2026-07-16 |
| RACI kick-off | G0.5 | PARTIAL | `docs/ops/ledger/raci-kickoff.md` | 2026-07-16 |

---

## Histórico de atualizações do índice

| Data | Alteração | Autor |
|------|-----------|-------|
| 2026-07-16 | Criação do índice (PE-G0-03); seções iniciais OPEN/PARTIAL conforme HEAD | @dev (PE-G0-03) |
