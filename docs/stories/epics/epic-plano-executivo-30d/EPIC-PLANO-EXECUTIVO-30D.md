# EPIC-PLANO-EXECUTIVO-30D

**Epic ID:** EPIC-PLANO-EXECUTIVO-30D  
**Versão:** 1.0  
**Data:** 2026-07-16  
**Status:** Active  
**Risco:** HIGH-RISK (dados, cobertura, publicação)  
**Fontes canônicas:**
- `DOD.md`
- `extra-consultoria-plano-executivo.html`

---

## Objetivo

Executar a janela dos **primeiros 30 dias úteis** do plano executivo:

1. **GATE-0** `BASELINE_LOCKED` (G0.1–G0.5)
2. **GATE-1** `LOCAL_FOUNDATION` (L1.1–L1.8)
3. Avanço comprovado no início de **C2/K3/Q5** (sem prometer 95%)
4. Atualizar `DOD.md` + HTML com evidências
5. Publicar em `main` via AIOX (@devops)

## Fora de escopo desta epic

- `EDITAIS_95`, `CONTRATOS_95`, `LOCAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE`
- Provisionar VPS real (V6.2 bloqueado sem credenciais)
- DOM-SC sem credencial (C2.5)

## Meta de cobertura

O DoD exige **≥95% editais** e **≥95% contratos** separadamente. Qualquer meta legada >80% fica subordinada ao DoD (decisão G0.3).

## Stories

| ID | Título | Tasks plano | Status |
|----|--------|-------------|--------|
| PE-G0-01 | Versionar DoD/plano e registrar autoridade | G0.1 | Ready |
| PE-G0-02 | Rebaseline HEAD + freeze escopo/claims | G0.2, G0.3 | Ready |
| PE-G0-03 | Ledger de evidências + RACI kick-off | G0.4, G0.5 | Ready |
| PE-L1-01 | Ambiente limpo + fresh migrations | L1.1, L1.3 | Ready |
| PE-L1-02 | Universo canônico + registry capability | L1.2, L1.4 | Ready |
| PE-L1-03 | Golden path + idempotência + backup/restore | L1.5, L1.6, L1.7 | Ready |
| PE-L1-04 | Manifesto GATE-1 LOCAL_FOUNDATION | L1.8 | Draft |
| PE-C2-01 | Fórmulas cobertura + success_zero/freshness | C2.1, C2.2 | Ready |
| PE-C2-02 | Evidências runtime PNCP/PCP/ComprasGov | C2.3, C2.4, C2.6 | Draft |
| PE-K3-01 | Schema e semântica canônica de contratos | K3.1 | Ready |
| PE-Q5-01 | Testes unitários do caminho crítico | Q5.1 | Ready |
| PE-CLOSE-01 | Atualizar DoD/HTML + publicação main | close | Draft |

## Gates da campanha

| Gate | Critério |
|------|----------|
| GATE-0 | DoD versionado; rebaseline; ledger; RACI |
| GATE-1 | Fresh install, golden path, resume, restore no HEAD |
| PUBLICATION | Stories Done + QA + PO close + @devops PR→main |

## Anti-padrões

- Marcar DoD sem evidência no HEAD
- Tratar `data_presence` como cobertura
- Fake green em blockers externos
- Push sem @devops / sem state file
