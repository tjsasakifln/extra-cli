# COPY-SEMANTIC-DUPLICATION-AUDIT

## Metrics (sample from integrity_sample on prior feed bags)

```
{
  "total_drafts": 30,
  "compared_pairs": 435,
  "high_similarity_pairs": 435,
  "max_similarity": 1.0,
  "pair_fraction_high": 1.0,
  "threshold": 0.82,
  "blocked": true,
  "reason_codes": [
    "near_duplicate_any_high_pair",
    "semantic_template_near_duplicate",
    "near_duplicate_extreme_pair",
    "near_duplicate_batch_fraction",
    "near_duplicate_family_fraction:diagnostico_contratual_b2g",
    "identical_transition_reuse",
    "identical_cta_mass_reuse"
  ],
  "sample_pairs": [
    {
      "a": "20569802000124",
      "b": "42126310000105",
      "lexical_similarity_raw": 0.8333,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.9048,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    },
    {
      "a": "20569802000124",
      "b": "27819676000168",
      "lexical_similarity_raw": 0.7692,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.8261,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    },
    {
      "a": "20569802000124",
      "b": "20308285000130",
      "lexical_similarity_raw": 0.7692,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.8261,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    },
    {
      "a": "20569802000124",
      "b": "38218230000102",
      "lexical_similarity_raw": 0.8333,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.8636,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    },
    {
      "a": "20569802000124",
      "b": "34894434000102",
      "lexical_similarity_raw": 0.8,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.8636,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    },
    {
      "a": "20569802000124",
      "b": "37646562000117",
      "lexical_similarity_raw": 0.8333,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.8636,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    },
    {
      "a": "20569802000124",
      "b": "50482484000120",
      "lexical_similarity_raw": 0.8,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.8261,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    },
    {
      "a": "20569802000124",
      "b": "02577913000109",
      "lexical_similarity_raw": 0.913,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.9048,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    },
    {
      "a": "20569802000124",
      "b": "09616071000198",
      "lexical_similarity_raw": 0.8333,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.8636,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    },
    {
      "a": "20569802000124",
      "b": "10703032000107",
      "lexical_similarity_raw": 0.7692,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.8261,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    },
    {
      "a": "20569802000124",
      "b": "29876900000189",
      "lexical_similarity_raw": 0.7037,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.75,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    },
    {
      "a": "20569802000124",
      "b": "05269841000112",
      "lexical_similarity_raw": 0.8,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.8636,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    }
  ],
  "lexical_similarity_raw_max": 0.9545,
  "semantic_template_similarity_max": 1.0,
  "normalized_skeleton_similarity_max": 1.0,
  "high_semantic_pairs": 435,
  "cta_reuse_rate": 1.0,
  "opening_reuse_rate": 0.0,
  "sentence_pattern_reuse_rate": 0.0667,
  "dominant_skeleton_share": 0.0667,
  "metrics": {
    "lexical_similarity_raw": 0.9545,
    "semantic_template_similarity": 1.0,
    "normalized_skeleton_similarity": 1.0,
    "CTA_reuse_rate": 1.0,
    "opening_reuse_rate": 0.0,
    "sentence_pattern_reuse_rate": 0.0667,
    "transition_reuse_rate": 0.931,
    "dominant_skeleton_share": 0.0667,
    "high_semantic_pairs": 435
  }
}
```

## Blind template

```
{
  "pass": false,
  "blocked": true,
  "reason_codes": [
    "near_duplicate_any_high_pair",
    "semantic_template_near_duplicate",
    "near_duplicate_extreme_pair",
    "near_duplicate_batch_fraction",
    "near_duplicate_family_fraction:diagnostico_contratual_b2g",
    "identical_transition_reuse",
    "identical_cta_mass_reuse"
  ],
  "metrics": {
    "lexical_similarity_raw": 0.9545,
    "semantic_template_similarity": 1.0,
    "normalized_skeleton_similarity": 1.0,
    "CTA_reuse_rate": 1.0,
    "opening_reuse_rate": 0.0,
    "sentence_pattern_reuse_rate": 0.0667,
    "transition_reuse_rate": 0.931,
    "dominant_skeleton_share": 0.0667,
    "high_semantic_pairs": 435
  },
  "sample_pairs": [
    {
      "a": "20569802000124",
      "b": "42126310000105",
      "lexical_similarity_raw": 0.8333,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.9048,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    },
    {
      "a": "20569802000124",
      "b": "27819676000168",
      "lexical_similarity_raw": 0.7692,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.8261,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    },
    {
      "a": "20569802000124",
      "b": "20308285000130",
      "lexical_similarity_raw": 0.7692,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.8261,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    },
    {
      "a": "20569802000124",
      "b": "38218230000102",
      "lexical_similarity_raw": 0.8333,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.8636,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    },
    {
      "a": "20569802000124",
      "b": "34894434000102",
      "lexical_similarity_raw": 0.8,
      "semantic_template_similarity": 1.0,
      "normalized_skeleton_similarity": 0.8636,
      "similarity": 1.0,
      "service_id": "diagnostico_contratual_b2g"
    }
  ],
  "question": "Se eu remover os fatos variáveis, estas mensagens ainda parecem o mesmo template?",
  "answer": "YES_SAME_TEMPLATE"
}
```

**Gate: FAIL** — removing variable facts still yields the same template (YES_SAME_TEMPLATE).

Thresholds were fixed **before** scoring (see near_duplicate.py defaults): skeleton cluster 30%, opening 30%, transition 40%, CTA 50%, semantic sim 0.78.
