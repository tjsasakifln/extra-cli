# C4 Contexto (Nível 1) — Extra Consultoria

> Gerado pelo Architect em 2026-07-13T17:30:00Z
> doc_level: completo
> Base: commit 249340d (QW-01 Radar + Competitive Intel + Readiness Gates)
> Delta: +2 verticais de produto (Opportunity Intel, Contract Intel), +3 gates de CI

```mermaid
C4Context
    title Sistema de Inteligência B2G — Extra Consultoria

    Person(consultor, "Consultor Tiago Sasaki", "Opera o sistema via CLI na VPS, interpreta relatórios e QW-01 radar para recomendar licitações")
    Person(cliente, "Cliente (Construtora)", "Recebe relatórios de inteligência, propostas comerciais e análises competitivas")

    System(extra, "Plataforma Extra Consultoria", "Ingestão multi-source → Evidence Ledger → QW-01 Radar → Competitive Intel → Relatórios executivos. Fail-closed CI gates.")

    System_Ext(pncp, "PNCP API v3", "Portal Nacional de Contratações Públicas — licitações + contratos. Fonte primária ativa.")
    System_Ext(apis_muni, "APIs Municipais/Estaduais", "DOM-SC, DOE-SC, PCP, TCE-SC — bloqueadas (Selenium/CAPTCHA/creds)")
    System_Ext(compras_gov, "ComprasGov API", "Dados abertos federais — documentado, não ingerido (bloqueio: API key)")
    System_Ext(transparencia, "Portais Transparência", "295+ portais municipais — bloqueados (detecção automática ativa, crawling inativo)")
    System_Ext(openai, "OpenAI API", "GPT-4.1-nano (classificação + análise) + text-embedding-3-small")
    System_Ext(brasilapi, "BrasilAPI", "CNPJ + IBGE — enriquecimento cadastral e geográfico")
    System_Ext(portal_transp, "Portal da Transparência", "CEIS + CNEP + CEPIM + CEAF — sanções")
    System_Ext(ibge, "IBGE API", "Dados municipais, população, coordenadas")
    System_Ext(hetzner, "Hetzner Storage Box", "Backup diário pg_dump — retenção 7+4")
    System_Ext(seed, "Planilha Seed", "Extra - alvos de licitação. R-0.xlsx — autoridade canônica de membership (1093 entidades)")

    Rel(consultor, extra, "SSH + CLI", "python scripts/opportunity_intel/cli.py radar|list|show|explain")
    Rel(consultor, extra, "Recebe CSV/PDF/Excel", "data/output/ + output/readiness/")
    Rel(extra, pncp, "GET licitações/contratos", "HTTPS/JSON — fonte crítica ativa (SLA 24h)")
    Rel(extra, apis_muni, "GET publicações", "HTTPS/JSON+HTML — BLOQUEADAS (SOURCE_BLOCKERS)")
    Rel(extra, compras_gov, "GET licitações", "HTTPS/JSON — NÃO INGERIDO")
    Rel(extra, transparencia, "GET portais", "HTTPS/HTML — DETECTADOS, NÃO CRAWLING")
    Rel(extra, openai, "POST chat + embeddings", "HTTPS/JSON + API Key — on-demand")
    Rel(extra, brasilapi, "GET cnpj/ibge", "HTTPS/JSON — batch enriquecimento")
    Rel(extra, portal_transp, "GET sanções", "HTTPS/JSON + API Key — compliance")
    Rel(extra, ibge, "GET municipios", "HTTPS/JSON — cache 90 dias")
    Rel(extra, hetzner, "rsync backup", "sshfs — diário 06:00 UTC")
    Rel(extra, seed, "Lê xlsx", "SHA-256 auditável — autoridade de membership")

    Rel(extra, cliente, "Entrega relatórios", "PDF + Excel + CSV radar")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Personas

| Persona | Descrição | Interação |
|---------|----------|-----------|
| **Consultor Tiago Sasaki** | Opera o sistema, interpreta QW-01 radar, recomenda licitações | CLI, SSH, systemd timers, QW-01 CSV |
| **Cliente (Construtora)** | Recebe relatórios de inteligência, propostas e análises competitivas | PDF, Excel, CSV (entrega manual) |

## Sistemas Externos

| Sistema | Tipo | Dados | Status |
|---------|------|-------|--------|
| PNCP API v3 | Fonte primária ATIVA | Licitações + contratos (SLA 24h) | ✅ Critical source |
| DOM-SC API | Fonte municipal | Publicações de 600+ órgãos | 🔴 Bloqueada (Selenium) |
| DOE-SC API | Fonte estadual | Matérias do diário oficial | 🔴 Bloqueada (cert. digital) |
| PCP v2 API | Fonte municipal | Processos de compra | 🔴 Bloqueada (Selenium+CAPTCHA) |
| ComprasGov API | Fonte federal | Licitações federais | 🟡 Não ingerido (API key) |
| TCE-SC (SCMWeb) | Fonte fiscal | Licitações + contratos | 🔴 Bloqueada (acesso instável) |
| Portais Transparência | Fonte municipal | 295+ portais (detectados) | 🔴 Bloqueados (Selenium) |
| OpenAI | IA | GPT-4.1-nano + embeddings | ✅ On-demand |
| BrasilAPI | Enriquecimento | CNPJ + IBGE | ✅ Batch diário |
| IBGE API | Enriquecimento | Dados municipais | ✅ Cache 90 dias |
| Portal Transparência | Compliance | CEIS, CNEP, CEPIM, CEAF | ✅ On-demand |
| Planilha Seed | Membership | Universo canônico (1093 entidades) | ✅ SHA-256 auditável |
| Hetzner Storage Box | Backup | pg_dump diário | ✅ Diário 06:00 UTC |
