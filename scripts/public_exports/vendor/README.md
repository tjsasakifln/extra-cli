# PDF text dependency

`pypdf-6.21.4-py3-none-any.whl` is the unmodified pure-Python wheel distributed
by the pypdf project on PyPI. It is a code dependency of the bounded contract
news evidence reader, not a generated report or client artifact.

- Version: `6.21.4`
- SHA-256: `33e4fb41ca352810eb4e9838aa0d82d6888a5f8bf682f43e99cce5faa666255c`
- Source: https://pypi.org/project/pypdf/6.21.4/
- License and attribution: `pypdf-6.21.4.dist-info/licenses/LICENSE` inside the wheel
- Runtime: a separate `python -S` process, no host installation or network
- Scope: non-encrypted PDFs of at most 2 MiB and 20 pages; CPU, memory, wall time
  and text output are limited before editorial use

The packager verifies this digest and the exact committed bytes. The consumer
verifies the bundle manifest before execution. The isolated extraction process
verifies the wheel digest again before importing it. An upgrade requires a
reviewed version/hash change and PDF extraction tests; never replace it from an
unpinned dependency installation on the host.
