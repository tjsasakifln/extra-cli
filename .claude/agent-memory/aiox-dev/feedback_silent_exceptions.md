---
name: feedback-silent-exceptions
description: Silent except Exception blocks must log with _logger.exception() — never pass silently
metadata:
  type: feedback
---

NUNCA usar `except Exception` sem `_logger.exception("mensagem descritiva com contexto")`, rollback se houver transacao ativa, e decisao explicita documentada sobre propagar vs retornar default.

**Why:** O usuario foi enfatico: blocos `except Exception` silenciosos convertem falhas em vazio/sucesso, mascarando bugs de conexao, timeout e corrupcao de dados. Cada um precisa de rastro auditavel.

**How to apply:** Sempre que editar um `except Exception`, aplicar o padrao:
1. `_logger.exception("mensagem com contexto")` para stack trace completo
2. Rollback se houver transacao ativa
3. Comentario documentando por que e seguro retornar default (ex: "cache is best-effort, not critical path")
4. Preferir tipo de excecao especifico (psycopg2.Error, asyncpg.PostgresError) quando viavel
