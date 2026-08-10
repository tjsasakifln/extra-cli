# COPY-SEMANTIC-DUPLICATION-AUDIT

near_dup_blocked: **False**  
reasons: ['near_duplicate_ok']

blind_template: **NO_SUFFICIENT_VARIATION**  
reasons: ['near_duplicate_ok']

```
near_dup_metrics: {
  "lexical_similarity_raw": 0.6418,
  "semantic_template_similarity": 0.6364,
  "normalized_skeleton_similarity": 0.6066,
  "CTA_reuse_rate": 0.325,
  "opening_reuse_rate": 0.0,
  "sentence_pattern_reuse_rate": 0.025,
  "transition_reuse_rate": 0.0789,
  "dominant_skeleton_share": 0.025,
  "high_semantic_pairs": 0
}
blind_metrics: {
  "lexical_similarity_raw": 0.775,
  "semantic_template_similarity": 0.775,
  "normalized_skeleton_similarity": 0.7632,
  "CTA_reuse_rate": 0.325,
  "opening_reuse_rate": 0.0,
  "sentence_pattern_reuse_rate": 0.025,
  "transition_reuse_rate": 0.0769,
  "dominant_skeleton_share": 0.025,
  "high_semantic_pairs": 0
}
```

Normalization removes company/CNPJ/UF/org/object/values/dates before blind compare.
