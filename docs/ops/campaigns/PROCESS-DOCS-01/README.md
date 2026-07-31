# PROCESS-DOCS-01 — Public process documents capability

Campaign branch: `feat/public-process-documents-coverage`

## Capability

`procurement_process_documents` — discovery, collection, preservation, classification and audit of **public** administrative process documents for the 1.093-entity universe.

## Commands

```bash
python3 -m scripts.process_documents discover --all
python3 -m scripts.process_documents classify-activity --all
python3 -m scripts.process_documents collect --entity <canonical_id>
python3 -m scripts.process_documents collect --limit 20
python3 -m scripts.process_documents backfill --since 2023-07-01 --limit 50
python3 -m scripts.process_documents incremental --limit 50
python3 -m scripts.process_documents coverage --full
python3 -m scripts.process_documents process-recall
python3 -m scripts.process_documents financial-coverage
python3 -m scripts.process_documents completeness
python3 -m scripts.process_documents gaps
python3 -m scripts.process_documents build-corpus
python3 -m scripts.process_documents show <process_or_entity>
```

## Honesty

- DOD items remain **open** until live proofs meet thresholds.
- Do not average independent metrics.
- Do not close issue #137 or unblock PR #133 without corpus + FP/FN + suite green on exact HEAD.
- `READY_TO_SUBMIT` without human review is forbidden.

## Artifacts (operational, mostly gitignored)

- `output/process_documents/`
- `data/raw/process_documents/`
