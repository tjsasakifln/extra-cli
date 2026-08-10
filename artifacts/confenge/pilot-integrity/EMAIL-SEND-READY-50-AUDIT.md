# EMAIL-SEND-READY ≥50 AUDIT

## Count

EMAIL_SEND_READY = **62** (gate ≥50: **True**)

## How achieved (honest)

- Structural-ready (MessageSpine complete + SERVICE_FIT): 4203
- Contact index: COMPANY_OWNED + VERIFIED emails only
- Expanded via real network enrichment (`expand-esr-20260810`) + nested extraction of prior verified candidates
- **No** TARGET_PROBABLE promotion
- **No** free-mail
- **No** invented emails
- Placeholders filtered

## Service distribution

```
{
  "gestao_monitoramento_contratual": 46,
  "apoio_licitacoes_propostas": 12,
  "medicoes_glosas_memoria": 1,
  "auditoria_orcamento_bdi": 1,
  "reforco_temporario_backoffice": 2
}
```

## Audit first 50 counters

```
{
  "FALSE_TARGET": 0,
  "WRONG_CONTACT": 0,
  "UNSUPPORTED_SERVICE": 0,
  "HOLLOW_COPY": 0,
  "UNSAFE_CLAIM": 0
}
```

## Near-dup / blind

- near_dup_blocked: False
- blind_template: NO_SUFFICIENT_VARIATION
- metrics: {"lexical_similarity_raw": 0.6418, "semantic_template_similarity": 0.6364, "normalized_skeleton_similarity": 0.6066, "CTA_reuse_rate": 0.325, "opening_reuse_rate": 0.0, "sentence_pattern_reuse_rate": 0.025, "transition_reuse_rate": 0.0789, "dominant_skeleton_share": 0.025, "high_semantic_pairs": 0}
