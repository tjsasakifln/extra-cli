# EXTRA-OPS-95-FOUNDATION — Status operacional

**Atualizado:** 2026-07-19T17:25:00Z  
**HEAD:** (pós-hardening, ver git) · branch `campaign/extra-ops-95-20260719`  
**Status global:** **PARTIAL**

## Métricas honestas (closeout + hardening PR#29)

| Métrica | Valor | Meta |
|---------|------:|-----:|
| DOD | **308/1355 (22.73%)** | ≥55% |
| Universo 200km | **1093** | — |
| Presença editais | **279 (25.5261%)** | ≥95% |
| Presença contratos | **329 (30.1006%)** | — |
| success_zero contratos | **722** | — |
| **Ops proxy contratos** | **1051/1093 (96.1574%)** | ≥95% **ATINGIDO** (proxy) |
| Gap ops→95% | **0** | — |
| bids / contracts rows | 10831 / 409490 | — |

### Notas de denominador

- Total canônico de checkboxes em `DOD.md`: **1355** (igual à main).
- Sessões anteriores usaram **1352** por subcontagem; **não** houve redução de requisitos.
- Hardening reverteu **5** itens fracos/fixture (PDF/Excel real, pacote mensal fixture, usuário único).

## Definição ops proxy

```
ops_proxy = lake presence(orgao_cnpj8) OR entity success_zero(cnpj14 root + http_204_complete)
```

**Não é** cobertura operacional de 7 estágios.

## Recovery closeout

- Branch: `campaign/extra-ops-95-20260719`
- DECISION-002: COV-EDIT-CONTRACT-OPS
- N09 **BLOCKED_SOURCE**
- Editais ~25% e DOD ~23% abertos → campanha **PARTIAL**

## Hardening PR#29 (2026-07-19)

- CI: ruff + mypy corrigidos (dívida pré-existente em main + delta da campanha)
- Higiene: dump 9.9MB, snapshots, batches intermediários, PDF/XLSX fixture removidos da árvore
- Evidência compacta: `proof-dump.sha256`, `proof-summary.json`, meta de snapshots
- Auditoria DOD: `evidence/dod-audit-hardening-20260719.json`
- Revisão adversarial: `evidence/adversarial-review-hardening-20260719.json`

## Claims

**Permitidos:** ops proxy contratos ≥95% sob definição acima (96.1574%).  
**Proibidos:** DONE · editais 95% · DOD 55% · LOCAL_READY · either · cobertura operacional 7 estágios · PDF/Excel “real” só com fixture

## Readiness

- `LOCAL_READY`: **NOT_READY**
- `PROJECT_DONE`: **NOT_READY**
- N09: **BLOCKED_SOURCE**
