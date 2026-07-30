# Extra — Decision loop (EXTRA-PROFILE-TO-ACTIONABLE-DECISION-01)

- **Gerado:** 2026-07-30T12:38:39Z
- **Weekly:** `output/weekly/weekly-20260730T123831Z-8bdf4632d9`
- **Perfil:** `extra_construtora@v3:aeaa8551547e`
- **profile_hash:** `aeaa8551547e167addfff707b642782b71d9526b8b8a8b8aa91b3a8cceaae92f`
- **Resultado:** **NO_ACTIONABLE_TENDER**
- **Candidatos avaliados:** 5
- **Shortlist:** 0

## Distribuição de estados

- `NO_VERIFIABLE_FUTURE_DEADLINE`: 5

## Shortlist acionável

**NO_ACTIONABLE_TENDER** — vazio defensável. Expirados=0, sem prazo verificável=5, bloqueados por perfil=0, fonte insuficiente=0.

### Ações para aumentar cobertura
- Melhorar normalização de prazos e timezone na fonte PNCP.
- Completar intake do perfil Extra: capital_giro, capacidade_garantia, capacidade_simultanea, cats_atestados, margem_minima

## Premissas e ausências

- Campos críticos PENDING no perfil: capital_giro, capacidade_garantia, capacidade_simultanea, cats_atestados, margem_minima
- Ausência de dado **não** foi convertida em capacidade.
- Aceite humano **não** foi fabricado (estado READY_FOR_HUMAN_ACCEPTANCE).

## Próximo passo

Registrar decisões com `scripts.ops.extra_decision_review` e só então emitir `PASS_EXTRA_DECISION_LOOP_ACCEPTED` via finalize com package-decision humana.

