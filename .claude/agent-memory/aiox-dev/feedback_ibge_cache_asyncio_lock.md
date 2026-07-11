---
name: ibge-cache-refactor-asyncio-lock
description: IBGEMunicipioCache uses asyncio.Lock instead of threading.Lock for async context
metadata:
  type: feedback
---

Para o cache IBGE refatorado em `_IBGEMunicipioCache`, usei `asyncio.Lock` em vez de `threading.Lock` (como sugerido nas ACs).

**Why:** `threading.Lock` bloqueia a thread do event loop quando usado com `lock.acquire()` em codigo async, derrotando o proposito do asyncio. A AC2 sugeria `threading.Lock` ou `threading.local`, mas em contexto async a ferramenta correta e `asyncio.Lock`, que e async-native e nao bloqueia o event loop.

**How to apply:** Para locks em codigo async, sempre usar `asyncio.Lock` em vez de `threading.Lock`. O `threading.Lock` bloqueia a thread, o que em asyncio significa bloquear o event loop inteiro. O AC foi ajustado para refletir `asyncio.Lock`.
