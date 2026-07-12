---
name: re-qa-td-8.2-resolved
description: Story TD-8.2 RE-QA PASS — 3 CONCERNS issues resolved (AC6 deprecation, AC7 deprecation, AC14 requirements.txt), 134/134 imports
metadata:
  type: project
---

# Story TD-8.2 RE-QA — PASS

**Verdict:** PASS (re-validacao apos CONCERNS)

**3 CONCERNS issues all resolved:**

1. **AC6** — `scripts/crawl/pncp_arp_crawler.py`: deprecation docstring adicionada na linha 1: "DEPRECATED: ARP crawling integrado ao pncp_crawler.py..."
2. **AC7** — `scripts/crawl/pncp_pca_crawler.py`: deprecation docstring adicionada na linha 1: "DEPRECATED: PCA crawling integrado ao pncp_crawler.py..."
3. **AC14** — `requirements.txt`: rarfile>=4.0, pymupdf4llm>=0.1.0, pytesseract>=0.3.10 adicionados como opcionais comentados

**Validacoes:** 134/134 imports PASS, ruff zero novos erros, 31/31 testes TD-8.2 relevantes PASS.

**Nota:** `tests/test_transparencia_crawler.py` tem SyntaxError (leading zeros) de outro story paralelo — nao e regressao do TD-8.2.

**Story:** docs/stories/epics/epic-td-003-reversa-remediation/story-TD-8.2-fix-module-imports.md
