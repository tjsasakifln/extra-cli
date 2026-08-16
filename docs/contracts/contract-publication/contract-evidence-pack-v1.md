# `contract-evidence-pack/1.0`

Also accepted as `contract_evidence_pack/1.0`.

Immutable, hashable factual pack. Every `FACT` and `CALCULATION` carries
evidence refs. `INFERENCE` is never serialized as `FACT`. `UNKNOWN` stays
visible. The pack never contains brand copy, SEO titles, CTA, index/noindex
or a legal accusation.

Hash: SHA-256 of canonical JSON (`sort_keys`, compact separators) excluding
`content_hash`. `producer_sha` is the git HEAD (or a hash of the producer
module when git is unavailable).
