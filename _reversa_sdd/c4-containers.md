# C4 Containers (Nível 2) — Extra Consultoria

> Gerado pelo Architect em 2026-07-11T15:00:00Z
> 🟢 CONFIRMADO — baseado em `docs/architecture/architecture.md`, código, deploy/

---

```mermaid
C4Container
    Person(consultor, "Tiago Sasaki", "Consultor")

    System_Boundary(hetzner, "Hetzner VPS (Ubuntu 24.04)") {
        Container(cli, "Python CLI Scripts", "Python 3.12", "Scripts de crawl, intel pipeline e relatórios. Executados via terminal SSH ou systemd timers.")
        Container(db, "PostgreSQL 17", "PostgreSQL + psycopg2", "DataLake: licitações, contratos, órgãos, cobertura. 12 migrations. FTS PT-BR.")
        Container(systemd, "systemd Timers", "systemd (Linux)", "13 timers para scheduling de crawlers. Template onFailure para notificação de erros.")
    }

    System_Ext(pncp, "PNCP API", "Licitações federais + adesão voluntária")
    System_Ext(domsc, "DOM-SC", "Contratos, convênios, empenhos municipais")
    System_Ext(pcp, "PCP v2", "Licitações municipais")
    System_Ext(comprasgov, "ComprasGov v3", "Compras federais")
    System_Ext(tcesc, "TCE-SC ESFINGE", "SCMWeb JSON API")
    System_Ext(transparencia, "Portais Transparência", "Betha/Ipam/E-gov")
    System_Ext(openai, "OpenAI API", "GPT-4.1-nano")
    System_Ext(brasilapi, "BrasilAPI", "CNPJ data")
    System_Ext(ibge, "IBGE API", "Municipality data")

    Rel(consultor, cli, "SSH / execução de scripts", "Terminal")
    Rel(systemd, cli, "Dispara execução programada", "Exec systemd service")
    Rel(cli, pncp, "Busca licitações", "HTTPS/urllib")
    Rel(cli, domsc, "Busca atos oficiais", "HTTPS/urllib + API Key")
    Rel(cli, pcp, "Busca licitações", "HTTPS/urllib")
    Rel(cli, comprasgov, "Busca compras", "HTTPS/urllib")
    Rel(cli, tcesc, "Busca TCE-SC", "HTTPS/urllib")
    Rel(cli, transparencia, "Busca editais", "HTTPS/urllib + BeautifulSoup")
    Rel(cli, openai, "Classifica editais", "HTTPS/httpx")
    Rel(cli, brasilapi, "Enriquece CNPJ", "HTTPS/httpx")
    Rel(cli, ibge, "Enriquece municípios", "HTTPS/httpx")
    Rel(cli, db, "Leitura/escrita", "psycopg2 (SQL direto)")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Containers

| Container | Tecnologia | Responsabilidade | Escala |
|-----------|-----------|------------------|--------|
| **Python CLI Scripts** | Python 3.12 | Crawlers, pipeline intel, relatórios, PDF/Excel | Single-process |
| **PostgreSQL 17** | PostgreSQL | DataLake: storage, FTS, RPCs, triggers | Single-instance (Hetzner VPS) |
| **systemd Timers** | systemd | Scheduling de 13 crawlers com staggered timers | 13 timers, 1 host |

## Comunicação

| De | Para | Protocolo | Síncrono? |
|----|------|-----------|-----------|
| CLI Scripts | PostgreSQL | psycopg2 (TCP :5432) | Sim |
| CLI Scripts | PNCP, DOM-SC, PCP, ComprasGov, TCE-SC, Transparência | HTTPS (urllib) | Sim |
| CLI Scripts | OpenAI, BrasilAPI, IBGE | HTTPS (httpx) | Sim/Async |
| systemd | CLI Scripts | Exec systemd service | Sim |
