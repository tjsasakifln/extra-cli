# C4 Contexto (Nível 1) — Extra Consultoria

> Gerado pelo Architect em 2026-07-11T15:00:00Z
> 🟢 CONFIRMADO — baseado em `docs/architecture/architecture.md`, PRD, `config/settings.py`

---

```mermaid
C4Context
    Person(consultor, "Tiago Sasaki", "Consultor de Inteligência em Licitações")
    System(extra, "Extra Consultoria Platform", "Coleta, armazena e analisa licitações públicas para a Extra Construtora")

    System_Ext(pncp, "PNCP API", "Portal Nacional de Contratações Públicas")
    System_Ext(domsc, "DOM-SC", "Diário Oficial dos Municípios de SC")
    System_Ext(pcp, "PCP v2", "Portal de Compras Públicas")
    System_Ext(comprasgov, "ComprasGov v3", "Dados Abertos de Compras Federais")
    System_Ext(tcesc, "TCE-SC ESFINGE", "SCMWeb — Sistema de Compras SC")
    System_Ext(transparencia, "Portais Transparência", "Betha/Ipam/E-gov municipais")
    System_Ext(openai, "OpenAI API", "GPT-4.1-nano — Classificação de editais")
    System_Ext(brasilapi, "BrasilAPI", "CNPJ, razão social, CNAE")
    System_Ext(ibge, "IBGE API", "Municípios, códigos IBGE")

    Rel(consultor, extra, "SSH / CLI", "Terminal (WSL → Hetzner VPS)")
    Rel(extra, pncp, "Busca licitações", "HTTPS REST")
    Rel(extra, domsc, "Busca contratos/convênios/empenhos", "HTTPS REST (API Key)")
    Rel(extra, pcp, "Busca licitações municipais", "HTTPS REST")
    Rel(extra, comprasgov, "Busca compras federais", "HTTPS REST")
    Rel(extra, tcesc, "Busca licitações TCE-SC", "HTTPS JSON API")
    Rel(extra, transparencia, "Busca editais municipais", "HTTPS Web Scraping")
    Rel(extra, openai, "Classifica editais", "HTTPS REST (API Key)")
    Rel(extra, brasilapi, "Enriquece CNPJ", "HTTPS REST")
    Rel(extra, ibge, "Enriquece municípios", "HTTPS REST")
```

## Personas

| Persona | Papel | Acesso |
|---------|-------|--------|
| **Tiago Sasaki** | Consultor de Inteligência — único usuário | SSH no Hetzner VPS, acesso total ao PostgreSQL |

## Sistemas Externos

| Sistema | Tipo | Protocolo | Autenticação | Cobertura |
|---------|------|-----------|--------------|-----------|
| **PNCP API** | Fonte primária de licitações | HTTPS REST | Pública | Nacional |
| **DOM-SC** | Diário Oficial Municipal SC | HTTPS REST | API Key | ~280 municípios SC |
| **PCP v2** | Portal de Compras Públicas | HTTPS REST | Pública | 100+ municípios SC |
| **ComprasGov v3** | Compras federais | HTTPS REST | Pública | Órgãos federais SC |
| **TCE-SC ESFINGE** | Sistema de Compras SC (SCMWeb) | HTTPS JSON API | Pública | TCE-SC e entes estaduais |
| **Portais Transparência** | Betha/Ipam/E-gov | HTTPS Web Scraping | Pública | Gap-fill municipal |
| **OpenAI API** | Classificação LLM | HTTPS REST | API Key | — |
| **BrasilAPI** | Enriquecimento CNPJ | HTTPS REST | Pública | Nacional |
| **IBGE API** | Enriquecimento municípios | HTTPS REST | Pública | Nacional |

## Fluxos de Dados

| Fluxo | Direção | Frequência | Volume |
|-------|---------|------------|--------|
| Crawl → DataLake | Inbound | Diário (8 fontes) | ~500-2000 bids/dia |
| Enriquecimento → DataLake | Inbound | Diário | ~50-500 CNPJs/dia |
| Pipeline Intel → PDF/Excel | Outbound | On-demand | 1 relatório por CNPJ |
| Panorama → Terminal/PDF/Excel | Outbound | On-demand / Semanal | 1 relatório |
| Coverage Report → Terminal | Outbound | Diário | 1 relatório |
