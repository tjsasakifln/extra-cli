# ADR-003: Crawlers com HTTP Síncrono

**Status:** Aceito
**Data:** 2026-07-10
**Decisor:** Tiago Sasaki
**Fonte:** `docs/architecture/architecture.md`, commit `352dac5`

---

## Contexto

Crawlers multi-source precisam fazer requisições HTTP para 8 APIs diferentes. A escolha natural em Python moderno seria `httpx` com `asyncio`. Porém, os crawlers rodam em systemd timers (contexto síncrono).

## Decisão

**Usar `urllib.request` (HTTP síncrono) nos crawlers chamados pelo monitor.py. Manter `httpx` apenas para jobs async isolados (enricher).**

## Justificativa

- Systemd timers executam um script Python por vez — sem benefício de concorrência
- `urllib` é stdlib — zero dependências
- Código síncrono é mais fácil de debugar em cron jobs
- Cada crawler é independente e sequencial por design
- Rate limiting das APIs torna concorrência contraproducente

## Consequências

- ✅ Código mais simples e direto
- ✅ Menos dependências (httpx só onde realmente precisa)
- ✅ Fácil de debugar com `print()` e logs lineares
- ❌ Crawlers não paralelizam requisições dentro de uma execução
- ❌ Performance limitada a uma requisição por vez
