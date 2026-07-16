# C2.5 — DOM-SC desbloqueado via CIGA Dados (público)

**Story:** PE-C2-05  
**Data:** 2026-07-16  
**Fonte canônica:** `ciga_ckan` → `https://dados.ciga.sc.gov.br`

---

## Evidência oficial (e-mail CIGA)

Resumo do e-mail recebido por Tiago:

- Integração recomendada: **CIGA Dados** (publicações DOM em formato estruturado)
- Portal: https://dados.ciga.sc.gov.br
- **Dados públicos** — sem cadastro e **sem chave de autenticação**
- Documentação API: https://docs.ckan.org/en/2.9/api/

Isso **invalida** o blocker que exigia `DOM_SC_CPF` / `DOM_SC_CNPJ` / `DOM_SC_API_KEY` para operar DOM/SC no caminho recomendado.

---

## Arquitetura dual-path

| Path | Source | Auth | Papel |
|------|--------|------|-------|
| **Canônico** | `ciga_ckan` | Nenhuma | Publicações + coverage |
| Legado | `dom_sc` | CPF+CNPJ+API key | API `remote/list` (opcional) |

---

## Prova API pública

```text
GET https://dados.ciga.sc.gov.br/api/3/action/status_show → success
package_search q=diario → datasets domsc-publicacoes-*
datasets mensais: ~54 (ex. 01-2023 … 12-2025)
resource: ZIP com JSON { "autopublicacoes": [ ... ] }
campos: codigo, titulo, data, entidade, municipio, categoria, link, texto, url
```

---

## Mudanças de código (PE-C2-05)

- `transform()` real em `ciga_ckan_crawler.py` (não retorna `[]` por design)
- `SOURCE_PURPOSE = "hybrid"`
- Registry: `open_tenders` + `coverage_truth`, sem credentials
- Config/notes: removido “requer contrato/API key” do path público
- Path autenticado documentado como legado em `.env.example`

---

## O que NÃO afirmar

- Cobertura ≥95% de editais via DOM
- Paridade com PNCP (sem valor, sem CNPJ no JSON CIGA)
- Que o path `dom_sc` autenticado está operacional sem credenciais
