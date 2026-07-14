# ADR-014: Fail-Closed CI Gates — Readiness + Freshness

**Data:** 2026-07-12
**Status:** Aceito
**Autor:** P1 Remediation (commits 0fef9de, 824af88, 5e7af23)
**Stakeholders:** Extra Consultoria

---

## Contexto

Após fase inicial de desenvolvimento com gates de CI relaxados, identificou-se que:

1. Era possível fazer deploy com cobertura < 95% sem alerta
2. Dados stale (PNCP > 24h sem atualização) podiam ser usados para consultoria sem aviso
3. Fontes bloqueadas (Selenium, CAPTCHA, credenciais) eram reportadas ambiguamente

O princípio "fail-closed" já era prática estabelecida no código (status unknown como default, never assume open), mas não era enforced nos gates de CI.

## Decisão

Implementar 2 gates de CI fail-closed como pré-condição de deploy:

### Consulting Readiness Gate
- **Threshold:** 95% de cobertura (`DEFAULT_THRESHOLD = 0.95`)
- **Denominador:** `conservative_monitoring_population` (inclui unresolved)
- **SOURCE_BLOCKERS:** 7 fontes com override hardcoded (NUNCA marcadas como sucesso)
- **Exit codes:** 0 = ready, 2 = not ready, 1 = technical failure

### Freshness Gate
- **SLA por fonte:** PNCP 24h, Contracts 24d (configurável via env vars)
- **Verificação:** `MAX(last_run_at) ≥ NOW() - SLA` para cada critical source
- **Exit codes:** 0 = all fresh, 2 = ≥1 stale, 1 = technical failure

### CI Integration
- Ambos gates são executados em sequência no CI
- Qualquer exit ≠ 0 bloqueia deploy
- Output JSON + CSV para auditoria

## Consequências

- Deploy só é possível com dados frescos e cobertura ≥ 95%
- Restaurado como crítico após P1 remediation (commit 0fef9de)
- Gates são independentes: readiness pode passar e freshness falhar, e vice-versa
- SOURCE_BLOCKERS garantem que fontes inacessíveis não sejam false-positive de cobertura
