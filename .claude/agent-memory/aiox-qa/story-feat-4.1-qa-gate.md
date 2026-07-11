---
name: story-feat-4.1-qa-gate
description: QA Gate PASS (upgraded from CONCERNS) for FEAT-4.1 Provisionar Hetzner VPS — SEC-001 resolved
metadata:
  type: reference
---

# Story FEAT-4.1 QA Gate

**Verdict:** PASS (upgraded from CONCERNS on re-execution)
**Date:** 2026-07-11 (re-execution)
**Status:** Done

**Summary:** Story provisionou Hetzner VPS com script completo (provision-vps.sh, 10 steps), 3 novos pares systemd (doe-sc, db-backup, health-check), extra-onfailure@.service template, health_check.py, e documentação operacional (vps-provisioning.md, vps-access.md). SEC-001 corrigido na re-execucao.

**Checks:** 7/7 completed. All 10 ACs met.

**Issues:**
- SEC-001 (low): RESOLVIDO — `configure_firewall()` agora condiciona porta 9100 a MONITORING_IPS
- MNT-001 (low): Dois templates OnFailure coexistem — documentado como tech debt

**Key observations for future infrastructure stories:**
- Infrastructure stories (provisioning) follow the same QA gate process but TEST-001 is N/A by nature
- provision-vps.sh is the canonical deployment script (install.sh is legacy)
- The install.sh still references legacy timer names alongside extra-* — dual-naming is transitional
- SEC pattern for conditional port exposure: env var check + IP whitelist + warn if unset
