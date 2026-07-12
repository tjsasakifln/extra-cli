# Municipios Inviaveis — Portais de Transparencia Individuais (COVERAGE-3.2)

> **Story:** COVERAGE-3.2 | **Gerado em:** 2026-07-11
> **Total municipios residuais:** 220 | **Com URL candidate:** 220

## Criterios de Inviabilidade

| Codigo | Criterio | Descricao |
|--------|----------|-----------|
| `no_url` | Sem URL | Nenhuma URL de portal identificada para o municipio |
| `offline` | Site Offline | Portal retorna 0/403/404 permanente apos 2 tentativas |
| `captcha_blocked` | CAPTCHA | Portal exige CAPTCHA irresoluvel automaticamente |
| `requires_login` | Login | Portal exige autenticacao para acesso |
| `no_content` | Sem dados | Portal existe mas sem dados de licitacao publicos |
| `unreachable_or_no_content` | Inacessivel/vazio | Combinacao de erro de rede e conteudo vazio |

## Municipios Processados

### OK (com bids extraidos)

*Nenhum municipio processado ainda — esta documentacao sera atualizada apos execucao do scraper.*

### Inviaveis

*Nenhum municipio marcado como inviavel ainda — esta documentacao sera atualizada apos execucao do scraper.*

---

## Metodologia

1. **Level 1 — Template Generico HTTP:** `requests` + `BeautifulSoup` com 4 templates:
   - `table` — tabela HTML
   - `div[class*=licit]` — divs de licitacao
   - `ul.lista-contratos` — listas de contratos
   - `section[class*=dados]` — sections de dados
2. **Level 2 — Fallback Selenium:** se Level 1 retornar 0 bids ou status != 200
3. **Inviavel:** se ambos falharem, documentar com causa raiz

## Atualizacao

Para atualizar este relatorio apos executar o scraper:
```bash
python -m scripts.fix.scrape_residual_portals --mode full --verbose
```
O checkpoint em `data/scrape_residual_progress.json` contem a lista de inviaveis
que pode ser usada para regenerar este documento.

## Referencias

- `data/residual_portals.csv` — Lista completa de 220 municipios residuais com URLs candidatas
- `data/scrape_residual_progress.json` — Checkpoint de progresso com resultados
- `scripts/fix/scrape_residual_portals.py` — Script de scraping
- `config/transparencia_config.yaml` — Templates customizados (AC9)
