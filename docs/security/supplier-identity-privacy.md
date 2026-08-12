# Supplier identity privacy policy

**Scope:** supplier identifiers ingested from PNCP contracts
**Status:** enforced by migration 076 and application tests; acceptance remains
subject to branch review and merge.

## Data handling

- `CNPJ`: validate both check digits, store the normalized 14 digits, and allow
  the legacy `fornecedor_cnpj` compatibility key and commercial-registry join.
- `CPF`: validate both check digits and store the normalized 11 digits only in
  the restricted contract fact table. `fornecedor_cnpj` must be `NULL`.
- `FOREIGN`: preserve the original identifier as
  `FOREIGN:<country>:<original>`; never coerce it to digits or CNPJ.
- `UNKNOWN`: preserve missing/invalid identity explicitly with a reason code;
  never promote it to CNPJ.

## Export, logs, and telemetry

Raw CPF is forbidden in reports, exports, logs, exception messages, metrics,
and telemetry. The only allowed display value is `CPF:***.***.***-**`.
`supplier_identifier_hash` is an internal correlation aid, not anonymization
and not an export substitute. Pipelines report identity type and counts, not
the internal CPF value. An invalid 11-digit identifier is exported only as
`UNKNOWN:MASKED`.

Commercial supplier discovery and `supplier_registry` accept only validated
`supplier_id_type='CNPJ'` rows. They must not query `supplier_identifier` for
CPF, foreign, or unknown identities.
