# Selenium Failed Portals — COVERAGE-3.1 AC7

> **Story:** COVERAGE-3.1 | **Data:** 2026-07-11
> **Executor:** @dev (Dex)
> **Propósito:** Documentar portais JS-rendered onde o Selenium crawler falhou (timeout, CAPTCHA, site offline).

## Metodologia

Para cada portal na lista JS-rendered (`data/js_portals_list.json`, 66 portais), o `SeleniumBatchCrawler` tenta:

1. Detectar framework JS (React/Angular/Vue/Next.js/Nuxt.js/unknown)
2. Renderizar pagina com headless Chrome (timeout: 5 min)
3. Extrair bids da pagina renderizada
4. Se falhar: retry unico apos 3s
5. Se retry falhar: salvar screenshot em `data/selenium_debug/` para diagnostico

## Resultados

### Pendente

O crawl batch completo ainda nao foi executado (requer ambiente com ChromeDriver).
Esta secao sera preenchida apos execucao do batch:

```bash
python scripts/crawl/monitor.py --source selenium --mode full
```

### Legenda de Motivos de Falha

| Motivo | Descricao | Acao |
|--------|-----------|------|
| `timeout` | Pagina nao renderizou dentro de 5 min | Tentar com timeout maior (10 min); fallback Playwright |
| `captcha` | CAPTCHA (reCAPTCHA v2/v3) bloqueou acesso | Documentar como `blocked_by_anti_bot`; sem resolucao automatizada |
| `offline` | Site retornou 503/502 ou nao respondeu | Verificar status do portal; tentar em outro horario |
| `driver_error` | ChromeDriver crashou ou nao respondeu | Verificar versao do ChromeDriver; tentar Firefox fallback |
| `no_content` | Pagina renderizou mas nenhum bid encontrado | Portal pode usar estrutura nao suportada; investigar manualmente |
| `unsupported_framework` | Framework JS nao reconhecido | Tentar extracao generica (tabelas HTML) |
| `cloudflare` | Cloudflare/anti-bot bloqueou acesso | Tentar Playwright com stealth mode |

## Estrutura do Relatorio

Para cada portal com falha, registrar:

```markdown
### {municipio} ({slug})

- **URL:** {url}
- **Plataforma:** {platform}
- **Framework detectado:** {framework}
- **Status:** FAILED
- **Motivo:** {motivo}
- **Screenshot:** `data/selenium_debug/{slug}_{timestamp}.png`
- **Tentativas:** {attempts}
- **Observacoes:** {notas}
```

---

*Relatorio gerado automaticamente. Preencher apos execucao do batch.*
