# Discovery: CKAN públicos de SC (Dados Abertos + CIGA)

**Data (UTC):** ver `timestamp` em `sc-ckan-discovery.json`  
**Método:** GET-only via `urllib`, sem credenciais, sem bypass de captcha  
**User-Agent:** `Extra-Consultoria/1.0`

## Resultado executivo

| Portal | Action API pública | Auth necessária (leitura) | Uso para procurement |
|--------|--------------------|---------------------------|----------------------|
| [dados.sc.gov.br](https://dados.sc.gov.br/) | **Sim (HTTP 200)** | **Não** | Catálogo DOE bulk + links de compras |
| [www.dados.sc.gov.br](https://www.dados.sc.gov.br/) | **Sim (HTTP 200)** | **Não** | Alias do mesmo CKAN |
| [dados.ciga.sc.gov.br](https://dados.ciga.sc.gov.br/) | **Sim (HTTP 200)** | **Não** | DOM-SC mensal (ZIP/JSON) — canônico municipal |
| [diariomunicipal.sc.gov.br](https://diariomunicipal.sc.gov.br/) | HTML 200 | N/A (portal) | UI DOM; dados estruturados via CIGA |
| [portal.doe.sea.sc.gov.br](https://portal.doe.sea.sc.gov.br/) | HTML 200 | N/A (portal) | UI DOE; bulk em repositório aberto |

**Nenhum endpoint de leitura Action API foi marcado BLOCKED_EXTERNAL.**  
APIs de escrita/admin CKAN exigem token — isso **não** invalida a leitura pública.

## Endpoints que funcionam (amostra)

### Dados Abertos SC (`https://dados.sc.gov.br/api/3/action/…`)

| Endpoint | Status | Notas |
|----------|--------|-------|
| `package_search?q=diario&rows=10` | 200 | count≈7; inclui `diario-oficial-sc-publicacoes` |
| `package_search?q=compras&rows=10` | 200 | count≈8; pregao/editais/PCA |
| `package_search?q=licitações` | 200 | count≈9 |
| `package_search?q=licita` | 200 | **count=0** (query fraca, não falha de API) |
| `package_search?q=contratos` | 200 | count≈20 |
| `package_list?limit=20` | 200 | lista pública |
| `package_show?id=diario-oficial-sc-publicacoes` | 200 | **28 resources** CSV/XLSX 2012–2025 |
| `package_show?id=diario-oficial-sc-edicoes` | 200 | 2 resources (CSV/XLSX 2011–2025) |
| `resource_show?id=…` | 200 | metadados de cada arquivo |
| `status_show` / `site_read` | 200 | health do CKAN |

**Datastore:** resources DOE bulk têm `datastore_active=null` — não usar `datastore_search`; baixar CSV/XLSX direto de  
`https://portal.doe.sea.sc.gov.br/repositorio/dadosabertos/…`.

### CIGA Dados (`https://dados.ciga.sc.gov.br/api/3/action/…`)

| Endpoint | Status | Notas |
|----------|--------|-------|
| `package_search?q=domsc&rows=5` | 200 | count≈428 |
| `package_search?q=diario&rows=5` | 200 | count≈519 |
| `package_list?limit=20` | 200 | autopublicações + domsc-* |
| `package_show?id=domsc-publicacoes-de-07-2026` | 200 | dezenas de ZIPs diários |
| `status_show` | 200 | health |

### Portais HTML

| URL | Status |
|-----|--------|
| `https://www.diariomunicipal.sc.gov.br/` | 200 |
| `https://diariomunicipal.sc.gov.br/` | 200 |
| `https://portal.doe.sea.sc.gov.br/` | 200 |

## Endpoints que falham

Na rodada live de discovery (**leitura pública**): **nenhuma falha HTTP** nos Action APIs testados.

Observações (não são bloqueios de API):

- `q=licita` → 0 resultados (usar `licitações` / `compras` / `contratos`).
- `datastore_search` não se aplica aos resources DOE (sem DataStore ativo).
- API autenticada DOE (`/apis/doe-api` + Bearer) **não** foi revalidada aqui; continua separada do CKAN.

## Pacote-chave: `diario-oficial-sc-publicacoes`

- **Título:** Diário Oficial SC - Publicações  
- **Resources:** 28 (pares CSV + XLSX por ano, 2012–2025)  
- **Campos descritos no notes do CKAN:** número da publicação, edição, data, órgão, categoria, assunto, tipo de ato, links de extrato/edição  
- **Crawler novo:** `scripts/crawl/dados_abertos_sc_crawler.py` (modo `smoke` lista resources; não exige login)

## DOE autenticado vs CKAN público

| Caminho | Auth | Latência / frescor | Papel |
|---------|------|--------------------|-------|
| `doe_sc_crawler.py` → REST Bearer | **Sim** (DOE_SC_LOGIN/PASSWORD) | Quase real-time | Busca operacional incremental |
| `dados_abertos_sc_crawler.py` → CKAN + CSV/XLSX | **Não** | Bulk anual (histórico / reuso) | Complemento aberto, sem token |
| `ciga_ckan_crawler.py` → CIGA DOM | **Não** | Mensal/ZIP | Canônico **municipal** |

**Conclusão:** a API autenticada do DOE-SC **ainda é necessária** para ingestão near-real-time de publicações estaduais. O CKAN de `dados.sc.gov.br` **não a substitui**, mas oferece **publicações DOE em bulk sem token** — útil para histórico, cobertura e fallback sem credencial.

## Crawlers existentes (repo)

| Arquivo | Fonte |
|---------|--------|
| `scripts/crawl/ciga_ckan_crawler.py` | CIGA / DOM-SC público |
| `scripts/crawl/doe_sc_crawler.py` | DOE-SC API autenticada |
| `scripts/crawl/dom_sc_crawler.py` | DOM legado autenticado (preferir CIGA) |
| `scripts/crawl/dados_abertos_sc_crawler.py` | **Novo** — catálogo dados.sc.gov.br |
| `scripts/crawl/discover_ciga_packages.py` | **Novo** — CLI listagem pacotes DOM CIGA |

## Como reproduzir

```bash
python -m scripts.crawl.dados_abertos_sc_crawler --mode smoke
python -m scripts.crawl.discover_ciga_packages --q domsc --rows 10
pytest tests/test_dados_abertos_sc_crawler.py -v
```

Evidência estruturada: [`sc-ckan-discovery.json`](./sc-ckan-discovery.json)
