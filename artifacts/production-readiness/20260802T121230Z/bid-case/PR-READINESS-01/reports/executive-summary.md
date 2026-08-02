# Readiness report — PR-READINESS-01

- System status: **SYSTEM_FAIL**
- Package status: **BLOCKED_BY_MISSING_DOCUMENT**
- Reference date: 2026-08-01
- Requirements: 22
- Documents: 22
- Findings: 13
- Blockers: 11

## Blockers

- **CRITICAL** `IDENTITY_MISMATCH`: Inconsistency for REQ-JUR-003 — identity inconsistency: REPRESENTATION_POWER_UNPROVEN, SIGNATORY_NOT_FOUND
- **CRITICAL** `IDENTITY_MISMATCH`: Inconsistency for REQ-JUR-004 — identity inconsistency: SIGNATORY_NOT_FOUND
- **CRITICAL** `EXPIRED_DOCUMENT`: Expired document for REQ-FIS-002 — document expired
- **CRITICAL** `IDENTITY_MISMATCH`: Inconsistency for REQ-FIS-003 — identity inconsistency: CNPJ_MISMATCH, LEGAL_NAME_MISMATCH
- **CRITICAL** `EXPIRED_DOCUMENT`: Expired document for REQ-FIS-005 — document expired
- **CRITICAL** `MISSING_DOCUMENT`: Missing mandatory document for REQ-GAR-001 — no document of required type
- **CRITICAL** `IDENTITY_MISMATCH`: Inconsistency for REQ-FIS-006 — identity inconsistency: CNPJ_MISMATCH, LEGAL_NAME_MISMATCH
- **CRITICAL** `SIGNATORY_PROBLEM`: Representation power unproven on doc-03_procuracao_fraca — powers missing or insufficient for bid acts
- **HIGH** `SIGNATORY_PROBLEM`: Signatory problem on doc-03_procuracao_fraca — SIGNATORY_MISMATCH
- **HIGH** `SIGNATORY_PROBLEM`: Signatory problem on doc-04_documento_signatario — SIGNATORY_NOT_FOUND
- **CRITICAL** `IDENTITY_MISMATCH`: CNPJ mismatch on doc-07_certidao_municipal_cnpj_outro — document CNPJ 99999999000191 != expected 12345678000199

## Limitations

- Operational support only — not a legal opinion.
- Does not assert habilitacao definitiva.
- Does not authenticate signatures biometrically.
- Does not submit to any portal.
- SIMULATION_ONLY package until human acceptance.

## Non-claims

- READY_TO_SUBMIT
- HABILITADA
- PROPOSTA APROVADA
- GARANTIA ACEITA
- Parecer jurídico
- Autenticidade biométrica de assinatura
- Protocolo em portal

Model SHA-256: `78e6c8f9afefbe26c3aaf2c6ab874286b43582ad90831020d56e150587e28b62`
