# Error Handling Pattern -- Crawlers

> Documento de padrao estabelecido durante Story TD-3.4.
> Aplicavel a todos os crawlers do sistema que usam a interface `crawl(mode) -> list[dict]` / `transform(records) -> list[dict]`.

## 1. Principios

1. **Fail early, fail loud** -- Erros de configuracao e autenticacao devem falhar imediatamente com mensagem clara, nao silenciosamente.
2. **Excecoes especificas** -- Nunca usar `except Exception` generico. Sempre capturar a hierarquia real: `HTTPError`, `URLError`, `TimeoutError`, `OSError`, `JSONDecodeError`, `ValueError`, `TypeError`, `KeyError`, `AttributeError`.
3. **Contexto nas mensagens** -- Toda mensagem de erro deve incluir: URL, entidade/ID relevante, status code (quando HTTP), e o nome do tipo da excecao.
4. **Retry com backoff** -- Toda requisicao HTTP deve ter retry com backoff exponencial para erros transientes (5xx, 429, timeout, connection reset).
5. **Nao mascarar erros** -- Erros de autenticacao (401) e validacao (400, 404, 422) nao devem ser retentados -- falham imediatamente.

## 2. Padrao de Retry

```python
MAX_RETRIES = int(os.getenv("CRAWLER_MAX_RETRIES", "3"))
HTTP_TIMEOUT = int(os.getenv("CRAWLER_HTTP_TIMEOUT", "30"))

for attempt in range(MAX_RETRIES + 1):
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Extra-Consultoria/1.0 (consultoria-licitacoes)")
        req.add_header("Accept", "application/json")

        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)

    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            _logger.error("[CRAWLER] Auth failure (401) on %s", url)
            return None  # Nao retentar
        if exc.code == 429:
            retry_after = int(exc.headers.get("Retry-After", "60"))
            _logger.warning("[CRAWLER] Rate limited (429) on %s. Waiting %ds", url, retry_after)
            time.sleep(retry_after)
            continue
        if exc.code in (404, 400):
            _logger.debug("[CRAWLER] HTTP %d on %s (not retryable)", exc.code, url)
            return None  # Nao retentar
        if attempt < MAX_RETRIES:
            delay = 2.0 ** attempt
            _logger.debug("[CRAWLER] HTTP %d on %s, retry %d/%d in %.1fs",
                          exc.code, url, attempt + 1, MAX_RETRIES, delay)
            time.sleep(delay)
            continue
        _logger.error("[CRAWLER] HTTP %d after %d retries on %s", exc.code, MAX_RETRIES, url)
        return None

    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if attempt < MAX_RETRIES:
            delay = 2.0 ** attempt
            _logger.debug("[CRAWLER] Connection error on %s, retry %d/%d in %.1fs: %s",
                          url, attempt + 1, MAX_RETRIES, delay, exc)
            time.sleep(delay)
            continue
        _logger.error("[CRAWLER] Connection failed on %s after %d retries: %s: %s",
                      url, MAX_RETRIES, type(exc).__name__, exc)
        return None

    except json.JSONDecodeError as exc:
        _logger.error("[CRAWLER] Invalid JSON from %s: %s", url, exc)
        return None
```

## 3. Mensagens de Erro Contextuais

### Formato padrao de log:

| Componente | Formato | Exemplo |
|-----------|---------|---------|
| Prefixo | `[CRAWLER_NOME]` | `[PCP]` |
| Acao | descricao sucinta | `Fetch error` |
| Contexto | URL, ID, status | `on https://api.example.com/endpoint` |
| Tentativa | `(attempt N/M)` | `(attempt 1/3)` |
| Detalhe | tipo + mensagem | `HTTPError: 500` |

### Exemplos:

```python
# Erro HTTP com contexto
_logger.warning(
    "[PCP] HTTP %d after %d retries on %s: %s",
    exc.code, MAX_RETRIES, url, body_text,
)

# Erro de transformacao com ID da entidade
_logger.warning(
    "[CRAWLER] Transform error (entity=%s): %s: %s",
    entity_id, type(exc).__name__, exc,
)

# Erro de conexao com tipo
_logger.error(
    "[CRAWLER] Request failed on %s after %d retries: %s: %s",
    url, MAX_RETRIES, type(exc).__name__, exc,
)
```

## 4. Hierarquia de Excecoes para Crawlers HTTP

```
BaseException
 +-- Exception
      +-- OSError
      |    +-- urllib.error.URLError
      |         +-- urllib.error.HTTPError  (codigo HTTP 4xx/5xx)
      +-- TimeoutError  (subclasse de OSError no Python 3.11+)
      +-- json.JSONDecodeError  (subclasse de ValueError)
      +-- ValueError
      +-- TypeError
      +-- KeyError
      +-- AttributeError
```

### Regras de captura:

1. **`urllib.error.HTTPError`** -- Erros HTTP com status code. Capturar PRIMEIRO (mais especifico).
2. **`OSError`** -- `URLError`, `ConnectionError`, `ConnectionResetError`. Capturar como fallback HTTP/net.
3. **`TimeoutError`** -- Timeouts de socket. Capturar separadamente para diagnosticar lentidao.
4. **`json.JSONDecodeError`** -- Resposta invalida. Capturar separadamente do HTTP.
5. **`ValueError`, `TypeError`, `KeyError`, `AttributeError`** -- Erros de transformacao/dados.
6. **`Exception`** -- ULTIMO recurso, apenas para "unexpected" errors que indicam bugs.
   Sempre incluir `type(exc).__name__` no log.

## 5. Onde Nao Retentar

| Status | Acao | Motivo |
|--------|------|--------|
| 400 Bad Request | Fail imediato | Request mal formado, retentar nao adianta |
| 401 Unauthorized | Fail imediato | Credenciais invalidas |
| 403 Forbidden | Fail imediato | Sem permissao, retentar nao adianta |
| 404 Not Found | Fail imediato | Recurso nao existe |
| 422 Unprocessable | Fail imediato | Parametros invalidos |
| 429 Too Many Requests | Retentar | Rate limiting, esperar `Retry-After` |
| 5xx Server Error | Retentar | Erro transiente do servidor |
| DNS / Connection Reset | Retentar | Erro de rede transiente |
| Timeout | Retentar | Rede lenta, pode ser transiente |

## 6. Checklist de Implementacao

Ao criar ou modificar um crawler, verificar:

- [ ] `except Exception` generico substituido por excecoes especificas
- [ ] Retry com backoff exponencial implementado em todas as requisicoes HTTP
- [ ] Mensagens de erro incluem URL, entidade/ID, status code, tipo da excecao
- [ ] Timeout configurado via env var com default documentado
- [ ] Erros 401/403/404 nao sao retentados
- [ ] Erros 429 usam `Retry-After` header
- [ ] `json.JSONDecodeError` capturado separadamente
- [ ] Transformadores capturam `(KeyError, ValueError, TypeError, AttributeError)` com ID da entidade
- [ ] Rate limiting implementado entre requisicoes (`time.sleep(DELAY)`)

---

*Versao: 1.0.0 | Atualizado: 2026-07-11 | Story TD-3.4*
