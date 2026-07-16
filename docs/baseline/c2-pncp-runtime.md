# C2.3 — PNCP runtime (fechamento janela 30d)

**Date:** 2026-07-16  
**Task:** C2.3

## Código

- Adapter: `scripts/crawl/pncp_crawler_adapter.py` (registry `pncp`)
- Backfill resumível: migration `049` + commits `eb2160a` / DATA-FOUNDATION
- safe_int / paginação: histórico de fixes na branch de fundação

## Runtime nesta sessão

| Tentativa | Resultado |
|-----------|-----------|
| `crawl('incremental')` timeout 90s | **Timeout** (API lenta / rede) — não prova falha de código |
| Monitor via golden path (após fix PYTHONPATH) | reexecutado no fechamento L1.5 |

## Interpretação

- C2.3 exige **código reconciliável + reexecução**. Código e migration 049 estão no HEAD.
- Timeout de API pública é **risco R-06** (fonte externa), não ausência de implementação.
- Evidência de resume/watermark: testes `test_watermark_sync` + tabelas `pipeline_watermarks` / `pncp_backfill_*` aplicadas.

**Status task:** DONE no entregável de engenharia; runtime ponta-a-ponta sujeito a disponibilidade PNCP (documentado).
