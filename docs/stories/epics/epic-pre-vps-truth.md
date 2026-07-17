# Epic: Pre-VPS Truth — Extra Consultoria

**Versão:** 1.0  
**Data:** 2026-07-17  
**Parent epic:** [`docs/stories/epic-technical-debt.md`](../epic-technical-debt.md) v3.0  
**Fonte:** `docs/prd/technical-debt-assessment.md` v3.0 FINAL · Waves 1–3 + pack UX ops  
**Autor:** Morgan (@pm) — Brownfield Discovery Phase 10  
**Status:** **Active / Ready for story drafting**  
**Budget:** ~**72–80h** (mid ~76h · ≈ R$ 11.400)  
**Posição operacional:** `LOCAL_RESILIENCE_READY` · **NÃO** `VPS_OPERATIONAL`

---

## Por que este epic existe

A wave v2 (Stories 1.1–1.5) entregou base de segurança, schema v3, universo, reconciliação e cobertura — mas a reassessment de 2026-07-17 mostrou **bloqueadores de produção** que a v2 subestimava:

1. Split-brain: path “oficial” grava em filesystem, não no PostgreSQL  
2. Dual runtime systemd (`extra-crawl-*` vs `pncp-crawl-*` / monitor)  
3. Health “healthy” com fixtures e SLA inventado  
4. Dual track de migrations + dump desatualizado  
5. SA JSON **ainda presente** no repositório após Story 1.1 Done  
6. Operador cego (sem progress, labels M1/M2 confusos, health só JSON)

**Regra C6:** proibido enable de timers oficiais e claim `VPS_OPERATIONAL` até esta onda fechar com evidência.

---

## Objetivo de negócio

Uma **verdade de dados** + **saúde honesta** + **secrets limpos** + **gate que impede claim falso** — para que a consultoria e a VPS não operem cegas.

---

## Escopo

### IN

| Wave | Foco | Stories | Horas |
|------|------|---------|-------|
| Wave 1 | Segurança + schema truth | 2.1, 2.4 | ~18h |
| Wave 2 | Health/checkpoint + truth gate | 2.3 | ~19–25h |
| Wave 3 | Writer único + systemd único | 2.2 | ~20h |
| Pack UX ops (∥) | Progress, human health, M1≠M2 | 2.5 | ~20h |

### OUT

- Elevação M2 (SYS-008), fatiar monitor (TD-010), Web UI (UX-01)  
- Provisionamento VPS / timers oficiais (ENV-02)  
- 118 débitos atomizados — **agrupamento por causa-raiz** apenas  

---

## Stories

| ID | Arquivo | Risco | Est. | Depende de |
|----|---------|-------|------|------------|
| 2.1 | [`../story-2.1-remove-sa-json-secret.md`](../story-2.1-remove-sa-json-secret.md) | HIGH-RISK | ~3h | — |
| 2.2 | [`../story-2.2-single-runtime-writer.md`](../story-2.2-single-runtime-writer.md) | HIGH-RISK | ~20h | 2.3 (preferível) |
| 2.3 | [`../story-2.3-honest-health-failclosed.md`](../story-2.3-honest-health-failclosed.md) | STANDARD | ~19h | 2.1 recomendado |
| 2.4 | [`../story-2.4-migration-single-track.md`](../story-2.4-migration-single-track.md) | HIGH-RISK | ~12–14h | — (∥ 2.1) |
| 2.5 | [`../story-2.5-cli-ops-ux-pre-vps.md`](../story-2.5-cli-ops-ux-pre-vps.md) | STANDARD | ~20h | UX-17 após 2.3 |

### Sequência

```text
2.1 ∥ 2.4  →  2.3  →  2.2  →  (ENV-02 bloqueado até aqui)
2.5 paralelo (UX-17 completo pós-2.3)
```

---

## Definition of Done do epic

- [ ] Stories 2.1–2.5 com status Done (ou WAIVED documentado)  
- [ ] Zero SA JSON no tree; gitignore + rotação se exposto  
- [ ] Apply path único `db/setup_db.sh`; dump HEAD regenerado  
- [ ] Path oficial grava PostgreSQL; uma família systemd  
- [ ] Health fail-closed (fixture ≠ live healthy); TQ-07 FAIL sem dual runtime  
- [ ] CLI: progress nos alvos, M1≠M2, `ops/health --human`  
- [ ] Nenhuma declaração `VPS_OPERATIONAL` sem evidência binária  
- [ ] Re-extração Reversa (crawl/resilience/ops) **recomendada** como follow-up pós-Done  

---

## Referências

- Assessment: `docs/prd/technical-debt-assessment.md` v3.0 FINAL  
- Report: `docs/reports/TECHNICAL-DEBT-REPORT.md` v3.0  
- Parent: `docs/stories/epic-technical-debt.md` v3.0  

---

## Change Log

| Data | Versão | Descrição | Autor |
|------|--------|-----------|-------|
| 2026-07-17 | 1.0 | Epic focado Pre-VPS Truth criado a partir do assessment v3.0 FINAL | Morgan (@pm) |
