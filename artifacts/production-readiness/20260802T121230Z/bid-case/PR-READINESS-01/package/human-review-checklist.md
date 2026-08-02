# Human review checklist

Package status: `BLOCKED_BY_MISSING_DOCUMENT`

This checklist does **not** authorize portal submission.

## Blockers
- [CRITICAL] Inconsistency for REQ-JUR-003: identity inconsistency: REPRESENTATION_POWER_UNPROVEN, SIGNATORY_NOT_FOUND
- [CRITICAL] Inconsistency for REQ-JUR-004: identity inconsistency: SIGNATORY_NOT_FOUND
- [CRITICAL] Expired document for REQ-FIS-002: document expired
- [CRITICAL] Inconsistency for REQ-FIS-003: identity inconsistency: CNPJ_MISMATCH, LEGAL_NAME_MISMATCH
- [CRITICAL] Expired document for REQ-FIS-005: document expired
- [CRITICAL] Missing mandatory document for REQ-GAR-001: no document of required type
- [CRITICAL] Inconsistency for REQ-FIS-006: identity inconsistency: CNPJ_MISMATCH, LEGAL_NAME_MISMATCH
- [CRITICAL] Representation power unproven on doc-03_procuracao_fraca: powers missing or insufficient for bid acts
- [HIGH] Signatory problem on doc-03_procuracao_fraca: SIGNATORY_MISMATCH
- [HIGH] Signatory problem on doc-04_documento_signatario: SIGNATORY_NOT_FOUND
- [CRITICAL] CNPJ mismatch on doc-07_certidao_municipal_cnpj_outro: document CNPJ 99999999000191 != expected 12345678000199

## Missing mandatory (still in denominator)

- REQ-GAR-001: Garantia de proposta 1%

## Reviewer actions
- [ ] Confirm no private documents will be committed to Git
- [ ] Confirm expired documents are not treated as valid
- [ ] Engineer review of technical candidates
- [ ] Legal review of representation powers
- [ ] Explicit human acceptance before any protocol attempt
