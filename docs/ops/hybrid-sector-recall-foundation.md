# Hybrid sector retrieval foundation

**operational.enabled = false** by default. Synthetic adversarial fixtures only
(built by `tests.fixtures.hybrid_sector.build_synthetic_corpus` — small Level B corpus).

## Unlock

See issue #138. Real corpus, dual labeling, real embeddings/LLM required before READY.

```bash
python -m scripts.ops.campaign_hybrid_sector_recall --help
python -m tests.fixtures.hybrid_sector.build_synthetic_corpus
```
