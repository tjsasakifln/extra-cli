# Contract analysis adapter — `public-read-contract-analysis/1.0`

Consumer: `web-cfg/contract-analysis` (web-cfg#83, PR #85).

This namespace **adapts** the already-consumed contract. It does not change
required fields, rename `data_state`, or invent INDEX.

Version negotiation:

- shipped schema string remains `public-read-contract-analysis/1.0`;
- `publication_readiness` is an alias of `data_state` for PR #85;
- `source_refs` is an alias of `official_refs`;
- additive nullable fields only.

`DATA_READY` means the FACTUAL pack is usable. It is not permission to index.
