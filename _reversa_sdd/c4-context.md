# C4 Contexto (Nível 1) — Extra Consultoria

> Gerado pelo Architect em 2026-07-11T22:00:00Z
> doc_level: completo

```mermaid
C4Context
    title Sistema de Inteligência em Licitações — Extra Consultoria

    Person(consultor, "Consultor Tiago Sasaki", "Opera o sistema via CLI na VPS, interpreta relatórios PDF/Excel para recomendar licitações aos clientes")
    Person(cliente, "Cliente (Construtora)", "Recebe relatórios de inteligência e propostas comerciais geradas pelo sistema")

    System(extra, "Plataforma Extra Consultoria", "Ingestão multi-source de licitações, pipeline analítico com IA, geração de relatórios executivos")

    System_Ext(pncp, "PNCP API", "Portal Nacional de Contratações Públicas — licitações, contratos, ARP, PCA")
    System_Ext(dom_sc, "DOM-SC API", "Diário Oficial dos Municípios de SC — 600+ órgãos")
    System_Ext(doe_sc, "DOE-SC API", "Diário Oficial do Estado de SC — 513 entidades")
    System_Ext(pcp, "PCP v2 API", "Portal de Compras Públicas — 100+ municípios")
    System_Ext(compras_gov, "ComprasGov API", "Dados abertos de compras federais — 2 endpoints")
    System_Ext(tce_sc, "TCE-SC (SCMWeb)", "Tribunal de Contas do Estado — licitações + contratos")
    System_Ext(transparencia, "Portais Transparência", "170+ portais municipais — Betha/Ipam/E-gov/Genérico")
    System_Ext(openai, "OpenAI API", "GPT-4.1-nano (classificação + análise) + text-embedding-3-small")
    System_Ext(brasilapi, "BrasilAPI", "CNPJ + IBGE — enriquecimento cadastral e geográfico")
    System_Ext(portal_transp, "Portal da Transparência", "CEIS + CNEP + CEPIM + CEAF — sanções")
    System_Ext(sicaf, "SICAF", "Sistema de Cadastro de Fornecedores — Playwright/captcha")
    System_Ext(hetzner, "Hetzner Storage Box", "Backup diário pg_dump — retenção 7+4")

    Rel(consultor, extra, "SSH + CLI", "python scripts/crawl/monitor.py")
    Rel(consultor, extra, "Recebe PDF/Excel", "data/output/")
    Rel(extra, pncp, "GET licitações/contratos", "HTTPS/JSON")
    Rel(extra, dom_sc, "GET publicações", "HTTPS/JSON + Basic Auth")
    Rel(extra, doe_sc, "GET matérias", "HTTPS/JSON + Bearer")
    Rel(extra, pcp, "GET processos", "HTTPS/JSON")
    Rel(extra, compras_gov, "GET licitações", "HTTPS/JSON")
    Rel(extra, tce_sc, "GET licitações/contratos", "HTTPS/HTML")
    Rel(extra, transparencia, "GET portais municipais", "HTTPS/HTML scraping")
    Rel(extra, openai, "POST chat + embeddings", "HTTPS/JSON + API Key")
    Rel(extra, brasilapi, "GET cnpj/ibge", "HTTPS/JSON")
    Rel(extra, portal_transp, "GET sanções", "HTTPS/JSON + API Key")
    Rel(extra, sicaf, "GET cadastro", "HTTPS/HTML + Playwright")
    Rel(extra, hetzner, "rsync backup", "sshfs")

    Rel(extra, cliente, "Entrega relatórios", "PDF + Excel por email/manualmente")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Personas

| Persona | Descrição | Interação |
|---------|----------|-----------|
| **Consultor Tiago Sasaki** | Opera o sistema, interpreta resultados, recomenda licitações | CLI, SSH, systemd timers |
| **Cliente (Construtora)** | Recebe relatórios de inteligência e propostas comerciais | PDF, Excel (entrega manual) |

## Sistemas Externos

| Sistema | Tipo | Dados | Frequência |
|---------|------|-------|-----------|
| PNCP API | Fonte primária | Licitações, contratos, ARP, PCA | Full diário + inc 3×/dia |
| DOM-SC API | Fonte municipal | Publicações de 600+ órgãos | 3×/dia |
| DOE-SC API | Fonte estadual | Matérias do diário oficial | Diário |
| PCP v2 API | Fonte municipal | Processos de compra | 2×/dia |
| ComprasGov API | Fonte federal | Licitações federais (legado + Lei 14.133) | Diário |
| TCE-SC | Fonte fiscal | Licitações + contratos TCE | Diário |
| Portais Transparência | Fonte municipal | 170+ portais (4 templates) | Semanal |
| OpenAI | IA | GPT-4.1-nano + embeddings | On-demand (pipeline Intel) |
| BrasilAPI | Enriquecimento | CNPJ + IBGE | Batch diário |
| Portal Transparência | Compliance | CEIS, CNEP, CEPIM, CEAF | On-demand |
| SICAF | Cadastral | Verificação de fornecedor | On-demand (pipeline Intel) |
| Hetzner Storage Box | Backup | pg_dump diário | Diário 06:00 UTC |
