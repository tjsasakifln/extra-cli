# Frontend & UX Specification — Extra Consultoria

**Version:** 3.0  
**Date:** 2026-07-17  
**Author:** Uma (UX Design Expert Agent)  
**Status:** Brownfield Discovery Phase 3 — Assessment Complete  
**Previous:** v1.0 (2026-07-13)

---

## 1. Resumo executivo

A Extra Consultoria é uma **plataforma de inteligência B2G CLI-first**. Não existe SPA React, não existe `package.json` de aplicação, não existe servidor FastAPI/HTMX/Streamlit em runtime de produto. A superfície de UX é **híbrida e orientada a artefatos**:

| Camada | Status 2026-07-17 | Tecnologias | Público |
|--------|-------------------|-------------|---------|
| **CLI operacional** | **Primária** | `argparse`, `print`/`rich`, `psycopg2` | Consultor (Tiago) + operadores |
| **Facade Workspace** | **Nova (2026-07-17)** | `scripts/workspace` | Consultor — jornada diária unificada |
| **Relatórios PDF** | **Primária (cliente)** | `reportlab` (estética Big Four) | Cliente / comercial |
| **Relatórios Excel** | **Primária** | `openpyxl`, `pandas` | Consultor + cliente |
| **HTML estático gerado** | **Secundária** | HTML+CSS embutido, SVG charts | Executivo / sessão comercial |
| **Ops / health** | **Primária (ops)** | CLI JSON + ASCII dashboard | Operador / CI / pré-VPS |
| **Web UI interativa** | **NÃO EXISTE** (backlog UX-01) | — | — |

### Verdade de produto (não inventar)

- Zero frontend web interativo em produção.
- Interação humana típica: **terminal local ou SSH** → CLI → arquivos em `output/` / `docs/ops/`.
- Documentos HTML (plano executivo, sessão comercial, dashboard de cobertura) são **artefatos gerados ou versionados**, abertos no browser — não apps.
- Design system de tokens existe de forma **implícita e duplicada** nos PDFs/HTML (charcoal navy + bronze), não como biblioteca compartilhada.

---

## 2. Modelo de UX do produto

```text
                    ┌─────────────────────────────────────┐
                    │     Persona: Tiago (consultor)      │
                    │     Persona: Operador / DevOps      │
                    └──────────────┬──────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
   ┌─────────────┐         ┌──────────────┐         ┌──────────────┐
   │ CLI / TUI   │         │ Relatórios   │         │ Ops Health   │
   │ workspace   │         │ PDF/Excel/   │         │ dashboard +  │
   │ opp_intel   │         │ HTML estático│         │ ops/health   │
   │ datalake    │         └──────────────┘         └──────────────┘
   │ crawl/mon.  │
   └─────────────┘
          │
          ▼
   Artefatos em output/, docs/ops/, data/
```

### Superfícies UX (inventário 2026-07-17)

| ID | Superfície | Entry point | Formato de saída |
|----|------------|-------------|------------------|
| S1 | Workspace facade | `python -m scripts.workspace <cmd>` | Tabelas ASCII + JSON |
| S2 | Opportunity Intel | `python -m scripts.opportunity_intel.cli` | Tabelas ASCII + JSON/CSV |
| S3 | DataLake local | `python scripts/local_datalake.py` | **rich** tables + JSON |
| S4 | Crawl monitor | `python scripts/crawl/monitor.py` | Logs + coverage |
| S5 | Golden path | `python scripts/golden_path.py` / `make golden-path` | **rich** (opcional) + ledger JSON |
| S6 | Buyer intel | `python scripts/buyer_intel/cli.py` | Tabelas + CSV |
| S7 | Contract intel | `python scripts/contract_intel/cli.py` | Tabelas + manifesto JSON/CSV |
| S8 | Health dashboard (legado) | `python scripts/health-dashboard.py` | ASCII / summary / JSON / watch |
| S9 | Ops health (resiliência) | `python -m scripts.ops.health` | **JSON always** + exit codes honestos |
| S10 | PDF executivo Big Four | `scripts/reports/executive_report.py` | PDF |
| S11 | Excel executivo | `scripts/reports/executive_excel.py` | XLSX |
| S12 | PDF consultoria / proposta / B2G | `generate_*_pdf.py`, `generate-report-b2g.py` | PDF |
| S13 | Excel inteligência | `scripts/intel_excel.py` | XLSX |
| S14 | Sessão comercial B2G | `scripts/reports/commercial_b2g_session.py` | HTML + JSON + CSV + XLSX |
| S15 | Plano executivo HTML | `extra-consultoria-plano-executivo.html` | HTML estático + SVG charts |
| S16 | Dashboard cobertura | `docs/epic-coverage/dashboard-cobertura.html` | HTML estático |

**Web UI (SPA/HTMX):** inexistente. UX-01 permanece backlog P3 (epic technical debt).

---

## 3. Personas

### P1 — Tiago (consultor / dono do fluxo comercial)

| Atributo | Detalhe |
|----------|---------|
| Papel | Extra Construtora — decide GO/REVIEW/NO_GO em editais SC (raio ~200 km) |
| Ambiente | Terminal local com PostgreSQL DataLake; guia em `docs/operations/workspace-guide.md` |
| Objetivos | Fila do dia, triagem, dossiê, briefing, decisão HITL, relatório comercial |
| Frustrações | Truncamento de tabelas, comandos longos sem progresso, CLIs sobrepostos, métricas de cobertura confundidas com sinal comercial |
| Ferramentas-chave | `workspace today/opportunities/dossier/decide/briefing`, `opportunity_intel`, relatórios PDF/Excel/HTML |

### P2 — Operador / DevOps

| Atributo | Detalhe |
|----------|---------|
| Papel | Manter crawl, freshness, resiliência local, gates pré-VPS |
| Ambiente | Local agora; VPS futura (ainda **não** provisionada em 2026-07-17) |
| Objetivos | Health honesto, fail-closed, golden path, timers systemd (futuro) |
| Frustrações | Health “verde” enganoso (fixture ≠ live), fontes degradadas (ex.: PNCP timeout), falta de progress em crawls longos |
| Ferramentas-chave | `scripts/ops/health.py`, `health-dashboard.py`, `golden_path.py`, `crawl/monitor.py`, `freshness_gate.py` |

### P3 — Cliente final (indireto)

| Atributo | Detalhe |
|----------|---------|
| Papel | Recebe PDF/Excel de inteligência — **não** usa CLI |
| UX | Estética Big Four, linguagem comercial, gaps honestos (não inventar GO) |

---

## 4. Fluxos primários

### Fluxo A — Manhã do consultor (canonical 2026-07-17)

```text
workspace today
  → coverage_contract_cli report
  → source_registry stats/gaps
  → workspace opportunities --ranking GO,REVIEW
  → workspace dossier <ID>
  → opportunity_intel update / crawl monitor (se freshness baixa)
  → workspace briefing
  → workspace decide --id N --decision approve|reject|override
```

Guia: [`docs/operations/workspace-guide.md`](../operations/workspace-guide.md).

### Fluxo B — Crawl → Intel → Relatório → Abordagem comercial

```text
1. INGESTÃO
   crawl/monitor.py --source pncp|sc_compras|... --mode full|incremental
   opportunity_intel update --source pncp
   ops/resilient_cycle (pipeline de resiliência local)

2. INTELIGÊNCIA
   opportunity_intel list/show/explain/briefing
   workspace opportunities / dossier
   buyer_intel ranking|perfil
   contract_intel historico|fornecedores|ativos

3. RELATÓRIO
   make report-executivo  → PDF + Excel
   commercial_b2g_session → HTML/JSON/CSV/XLSX
   panorama / intel_excel / generate_*_pdf

4. ABORDAGEM COMERCIAL
   briefing + decide (HITL)
   artefatos em output/reports/ e docs/ops/session-*/
```

### Fluxo C — Golden path (prova ponta a ponta)

```text
make golden-path
  → DB up → crawl fontes → freshness gate → PDF+Excel
  → ledger em output/golden-path/ledger.json
  → exit codes fail-closed (0–5)
```

Modo canônico: **strict fail-closed** (default). `--no-strict` é legado permissivo, não canônico.

### Fluxo D — Saúde operacional (pré-VPS)

```text
python -m scripts.ops.health --env development   # JSON, live; nunca greenwash fixture
python scripts/health-dashboard.py [--summary|--json|--watch]
```

Estado documentado: `LOCAL_RESILIENCE_READY` — **não** implica `VPS_OPERATIONAL` nem cobertura 95%.

---

## 5. Padrões de design CLI

### 5.1 Entry points e discovery

| Padrão | Exemplos | Avaliação UX |
|--------|----------|--------------|
| `python -m scripts.<pkg>` | workspace, opportunity_intel, ops.health | Bom (importável, documentável) |
| `python scripts/<file>.py` | local_datalake, golden_path, health-dashboard | Bom (legado familiar) |
| `make <target>` | golden-path, report-executivo, run-report | Excelente para rituais |
| Subparsers argparse | Quase todos | Padrão dominante |

**~86 scripts** com `ArgumentParser` sob `scripts/` — superfície ampla; a facade `workspace` é a resposta parcial à fragmentação.

### 5.2 Formatação de saída

| Paradigma | Onde | Características |
|-----------|------|-----------------|
| **rich** (moderno) | `local_datalake.py` (coverage), `golden_path.py` (opcional) | Cores, Panel, Table, box-drawing |
| **ASCII fixo** | `opportunity_intel`, `workspace`, `health-dashboard` | Monocromático, truncamento |
| **JSON always** | `ops/health` | Máquina-first; humano lê JSON indentado |
| **JSON opt-in** | `--json` ou `--format json` | Inconsistente entre CLIs |

### 5.3 Tabelas

| Implementação | Truncamento | Limite linhas | Notas |
|---------------|-------------|---------------|-------|
| `opportunity_intel._print_table` | **20 chars**, max **10 colunas**, 50 rows | Alto | Oculta `objeto`/`orgao_nome` úteis |
| `workspace.common.print_table` | Cap **48** chars/coluna | Melhor | Ainda sem `rich` |
| `local_datalake` `rich.Table` | Controlado pelo rich | Excelente | Referência de qualidade |

### 5.4 Exit codes (fail-closed)

| Tool | Códigos | Semântica |
|------|---------|-----------|
| `ops/health` | 0 / 1 / 2 | healthy / degraded / blocked_or_stale\|no_live_evidence |
| `health-dashboard` | 0 / 1 / 2 | OK / warnings / critical |
| `golden_path` | 0–5 | success; failed; partial; freshness fail; report fail; degraded |
| `contract_intel` | ≠0 se readiness < 95% | Gate de capacidade |
| `opportunity_intel` / `workspace` | 0 / 1 genérico | Menos granular |

**Princípio UX de ops:** fixture **nunca** pinta live de verde. Claims explícitos: `"claim": "operational live"` vs `"fixture/test mechanics only"`.

### 5.5 Mensagens de erro e fail-closed

Padrões desejáveis (já presentes em partes do código):

- Mensagem humana em stdout + log: `"Erro de banco de dados: ..."`, `"PG: UNAVAILABLE — ..."`.
- Status de degradação explícito: `DEGRADED`, `EMPTY`, `UNAVAILABLE` (workspace sections).
- Relatório comercial: **não inventa GO**; flags `live_fetch` vs atestação; confidence badges.
- Golden path: statuses `success | success_zero | partial | degraded | empty | failed`.

Padrões ainda fracos:

- Tracebacks ocasionais em scripts legados.
- Comandos longos (`update`, `radar`, crawls) **sem progress bar** (UX-02).
- Validação de args tardia (erro SQL em vez de “UF inválida”) (UX-12).

### 5.6 Flags de formato (inconsistência)

| Padrão | Tools |
|--------|-------|
| `--format table\|json` | opportunity_intel |
| `--json` boolean | workspace, local_datalake, health-dashboard, ops/health |
| Sem flag de formato | maioria dos generators de PDF |

---

## 6. UX de relatórios

### 6.1 PDF — estética Big Four

**Tokens de design (duplicados em `executive_report.py`, `intel_report.py`, `generate-report-b2g.py`):**

| Token | Hex | Uso |
|-------|-----|-----|
| `INK` | `#1B2A3D` | Texto principal / headers |
| `ACCENT` | `#8B7355` | Bronze / regras / destaques |
| `SIGNAL_RED` | `#B5342A` | Risco / NO_GO |
| `SIGNAL_GREEN` | `#1B7A3D` | Sucesso / GO |
| `SIGNAL_AMBER` | `#B8860B` | Atenção / REVIEW |
| Tipografia | Times-Roman (serif) | Estética consultoria |

**Seções típicas do executivo Extra:** capa → sumário → ranking de órgãos → GO/REVIEW/NO_GO → contratos vincendos → painel de valores → concorrentes → metodologia/confiança.

**Qualidade UX PDF:** alta para o cliente; monolito `generate-report-b2g.py` (~7.4k linhas) permanece dívida de manutenção (UX-10).

### 6.2 Excel

| Generator | Propósito | UX |
|-----------|-----------|-----|
| `executive_excel.py` | Espelho rastreável do PDF | Bom (multi-sheet) |
| `intel_excel.py` | Inteligência por CNPJ/pipeline | Bom |
| `coverage_gaps.py` / `coverage_weekly.py` | Cobertura | Operacional |
| `commercial_b2g_session.write_xlsx` | Sessão comercial | Bom |
| `panorama.py --output-excel` | Panorama de mercado | Fair |

### 6.3 HTML estático

#### A) Sessão comercial B2G (`commercial_b2g_session.py` → HTML)

Exemplo: `docs/ops/session-2026-07-17/commercial-b2g-session-sc.html`

- CSS variables alinhadas aos tokens Big Four (`--ink`, `--amber`, `--red`, `--green`).
- Badges de confidence (`low` / `low_to_medium` / `medium`).
- Flags honestas live_fetch vs atestação.
- Tabelas de oportunidades com links externos (Compras SC).
- **UX forte** para leitura em browser sem app.

#### B) Plano executivo (`extra-consultoria-plano-executivo.html`)

- Título: “Extra Consultoria — Estado operacional B2G”.
- Charts **real vs planejado** em SVG; commits 2026-07-17:
  - `fdaf792` — restore charts
  - `d3e82ba` — full-width responsive no Chrome
- Viewport + `@media` presentes; ~22 ocorrências `aria-*` (baseline a11y parcial).
- Artefato de governança/DoD — **não** é app de produto.

#### C) Dashboard cobertura

- `docs/epic-coverage/dashboard-cobertura.html` — estático, epic coverage.
- `validate_coverage.py` também embute HTML com search/sort JS simples.

### 6.4 Diretórios de saída

```text
output/
  excels/          Excel
  pdfs/            PDFs
  reports/         Executivo, comercial, coverage
  qw-01/           Radar auditável
  golden-path/     Ledger de validação
  readiness/       Manifestos e reconciliação
  session-*/       Artefatos de sessão
docs/ops/session-*/  HTML/markdown de sessão comercial
```

---

## 7. Dashboards e saúde do operador

### 7.1 `scripts/ops/health.py` (canônico resiliência 2026-07-17)

- Saída **sempre JSON**.
- Freshness tripla: collection / content / operational.
- Live default: ignora fixtures; inconsistências listadas.
- Exit 2 se sem evidência live ou stale/blocked.
- Integrado a Makefile / CI mental model pré-VPS.

### 7.2 `scripts/health-dashboard.py` (legado TD-5.5)

- Dashboard ASCII completo, `--summary`, `--json`, `--watch`.
- Checks: DB, disk, storage, crawl stats, backup, alerts.
- Exit 0/1/2 — bom para humano no terminal.

### 7.3 Prioridade pré-VPS (operator experience)

| Prioridade | Item | Por quê |
|------------|------|---------|
| P0 | Health live honesto (`ops/health`) | Evita “verde falso” antes de provisionar VPS |
| P0 | Golden path strict | Prova crawl→report sem sessão interativa eterna |
| P0 | Workspace `today` legível | Consultor não precisa memorizar 10 CLIs |
| P1 | Progress em crawls longos (UX-02) | Operador não mata processo “travado” |
| P1 | Mensagens fail-closed legíveis (não só JSON) | Humano + máquina |
| P2 | Unificar tabela CLI em `rich` (UX-03/04) | Reduz erro de leitura comercial |
| P3 | Web UI (UX-01) | **Fora** do caminho crítico pré-VPS |

---

## 8. Acessibilidade e usabilidade (CLI + relatórios)

| Dimensão | Estado | Débito |
|----------|--------|--------|
| Contraste PDF | Bom (navy/bronze em fundo claro) | — |
| HTML comercial | Bom contraste; sticky headers | — |
| HTML executivo charts | Responsivo pós-fix 2026-07-17; aria parcial | UX-13 (a11y charts) |
| Terminal color | Só onde `rich` existe | UX-03 |
| Screen reader / CLI | N/A estruturado; texto linear ok | — |
| Truncamento de dados | Crítico em opp_intel | UX-04 |
| Progress / feedback | Quase ausente | UX-02 |
| Hyperlinks no terminal | Plain text URLs | UX-11 |
| Confusão de métricas | Cobertura ≠ sinal comercial (documentado no guide) | UX-14 |
| Sobreposição de CLIs | workspace vs opp_intel vs datalake | UX-15 |
| Paginação interativa | Inexistente (limit/ cap) | UX-07 |
| Idioma | CLI misto PT/EN; docs ops em PT | UX-16 |

**Score de consistência UX (atualizado):** **5/10** (era 4/10 em v1.0)  
Ganhos: workspace facade, commercial HTML, ops health fail-closed, charts executivos, design tokens PDF reutilizados no HTML.  
Ainda fraco: dual display, progress, truncamento, ausência de web UI.

---

## 9. Design system (notas)

Não há design system formal (tokens CSS/Tailwind/shadcn). Existe **sistema implícito de marca consultoria**:

### 9.1 Tokens de marca (de facto)

```text
INK     #1B2A3D   charcoal navy
ACCENT  #8B7355   bronze
RED     #B5342A
GREEN   #1B7A3D
AMBER   #B8860B
BG      #F5F6F8   (HTML)
LINK    #0563C1   (HTML)
```

### 9.2 Convenções CLI desejadas (alvo)

| Elemento | Padrão alvo |
|----------|-------------|
| Sucesso | verde / `[OK]` / ✓ |
| Aviso | amarelo / `[WARN]` |
| Falha | vermelho / `[FAIL]` / ✗ |
| Bloqueio | ⊘ |
| Dinheiro | `R$ X.xxx,xx` (pt-BR) |
| Data humana | `dd/mm/YYYY` |
| Tabela | `rich.Table` + `box.SIMPLE` |
| Erro | `[ERROR] mensagem humana` — sem traceback default |
| JSON | `ensure_ascii=False`, `indent=2`, `default=str` |

### 9.3 Web UI futura (se UX-01 avançar)

- **Não** copiar o preset AIOX `nextjs-react` cegamente: o produto é B2G ops, não SaaS genérico.
- Candidatos honestos: **FastAPI + HTMX** (MVP interno), ou Streamlit (dashboard ops). Portal cliente full = investimento 80h+.
- Reusar tokens Big Four e o modelo de honesty flags do HTML comercial.

---

## 10. Débitos Frontend/UX

### Legenda de status

| Status | Significado |
|--------|-------------|
| **OPEN** | Ainda presente, sem resolução |
| **PARTIAL** | Mitigado em parte da superfície |
| **RESOLVED** | Resolvido de forma verificável |
| **NEW** | Identificado nesta revisão v3.0 |
| **DEFERRED** | Explicitamente fora do escopo atual / pós-VPS |

### Catálogo

| ID | Débito | Severidade | Status | Notas 2026-07-17 |
|----|--------|------------|--------|------------------|
| **UX-01** | **Web UI interativa** (FastAPI+HTMX / portal) | HIGH | **DEFERRED** | Backlog P3 em epic-technical-debt; **não iniciado**; fora do caminho pré-VPS |
| **UX-02** | Sem progress indicators em comandos longos | HIGH | **OPEN** | `update`, `radar`, crawls, PDF generation |
| **UX-03** | Dual display: `rich` vs raw `print` | MEDIUM | **PARTIAL** | rich em local_datalake + golden_path; workspace/opp_intel ainda ASCII |
| **UX-04** | Truncamento agressivo em opportunity_intel (20c/10 cols) | MEDIUM | **OPEN** | workspace cap 48c é melhor, mas opp_intel inalterado |
| **UX-05** | Exit codes inconsistentes | LOW | **PARTIAL** | golden_path 0–5 e ops/health 0/1/2 são referência; opp_intel ainda 0/1 |
| **UX-06** | Flags de output inconsistentes (`--format` vs `--json`) | LOW | **OPEN** | |
| **UX-07** | Sem paginação interativa | LOW | **OPEN** | limits fixos |
| **UX-08** | Erros silenciosos / pouca mensagem | MEDIUM | **PARTIAL** | workspace e opp_intel melhoraram mensagens; legado permanece |
| **UX-09** | Coverage duplicado (opp_intel vs datalake vs contract) | MEDIUM | **PARTIAL** | `coverage_contract_cli` + workspace coverage; ainda múltiplas entradas |
| **UX-10** | Monólito `generate-report-b2g.py` (~7.4k linhas) | MEDIUM | **OPEN** | executive_report modular ajuda, monólito permanece |
| **UX-11** | URLs não clicáveis no terminal | LOW | **OPEN** | |
| **UX-12** | Validação de input pouco amigável | LOW | **OPEN** | |
| **UX-13** | A11y incompleta em charts HTML executivos | LOW | **NEW** | Charts restaurados/responsivos; aria parcial, não auditado WCAG |
| **UX-14** | Risco de confusão cobertura vs sinal comercial | HIGH | **PARTIAL** | Documentado no workspace-guide; UI CLI ainda não separa visualmente com força |
| **UX-15** | Fragmentação de CLIs (muitos entry points) | MEDIUM | **PARTIAL** | Facade `workspace` + guide; CLIs legados ainda necessários |
| **UX-16** | Mistura PT/EN em mensagens CLI | LOW | **NEW** | Impacta legibilidade do consultor |
| **UX-17** | Ops health JSON-only (sem vista humana rich) | MEDIUM | **NEW** | Correto para máquina; operador humano prefere summary ASCII |
| **UX-18** | HTML comercial sem navegação multi-página / TOC sticky global | LOW | **NEW** | Aceitável para sessão única |

### Contagem

| Categoria | Qtd |
|-----------|-----|
| OPEN | 6 |
| PARTIAL | 6 |
| RESOLVED | 0* |
| NEW | 4 |
| DEFERRED | 1 (UX-01) |

\*Nenhum débito v1.0 foi **totalmente** resolvido; vários foram **parcialmente** mitigados. Charts HTML (não listados em v1.0) foram **corrigidos** em commits de docs (não contam como UX-xx RESOLVED de produto CLI).

### Roadmap de resolução (priorizado para operador pré-VPS)

**Imediato (pré-VPS / próxima sprint ops):**

1. **UX-02** — Progress/`rich.progress` em crawl update + golden_path etapas (8h)
2. **UX-17** — `ops/health --human` summary ASCII com mesmos exit codes (2h)
3. **UX-14** — Labels explícitos no workspace: “sinal comercial” vs “cobertura operacional” (3h)
4. **UX-04** — Colunas prioritárias sem truncar `id`, `ranking`, `orgao_nome` (4h)

**Curto prazo:**

5. **UX-03 + UX-15** — Workspace como única facade documentada; rich tables compartilhadas (12h)
6. **UX-05/06** — Padronizar exit codes e flags (4h)
7. **UX-08** — Mensagem em todo `sys.exit(≠0)` (3h)

**Médio prazo:**

8. **UX-09/10** — Consolidar coverage entry + modularizar PDF B2G (22h)
9. **UX-11/12/07/16** — Polish CLI (14h)
10. **UX-13/18** — A11y HTML e polish comercial (6h)

**Longo prazo / estratégico:**

11. **UX-01** — Web UI (80h+) — **somente após** VPS estável e fluxo CLI diário consolidado

---

## 11. Inventário resumido de CLIs user-facing

| Script | Linhas (aprox.) | Função UX |
|--------|-----------------|-----------|
| `workspace/cli.py` | ~1.3k (módulo) | Facade diária do consultor |
| `opportunity_intel/cli.py` | 852 | Radar, list, show, explain, coverage, health, update, export, briefing, reconcile |
| `local_datalake.py` | 683 | Search, supplier, pricing, competitors, coverage **rich** |
| `golden_path.py` | ~800+ | Pipeline E2E fail-closed |
| `health-dashboard.py` | 472 | Dashboard ops ASCII |
| `ops/health.py` | ~350 | Saúde resiliência JSON |
| `crawl/monitor.py` | multi-source | Orquestração de crawl |
| `buyer_intel/cli.py` | ranking/perfil | Inteligência de órgãos |
| `contract_intel/cli.py` | histórico/manifesto | Contratos e readiness |
| `reports/executive_report.py` | PDF Big Four | Entrega cliente |
| `reports/executive_excel.py` | Excel | Rastreabilidade |
| `reports/commercial_b2g_session.py` | HTML+bundle | Sessão comercial honesta |
| `generate-report-b2g.py` | 7469 | PDF B2G monolítico |
| `generate_consultoria_pdf.py` | 1666 | PDF consultoria |
| `generate_proposta_pdf.py` | 1214 | PDF proposta |
| `intel_pipeline.py` / `intel_*.py` | vários | Pipeline de inteligência |

---

## 12. Mudanças desde v1.0 (2026-07-13 → v3.0 2026-07-17)

| Área | Mudança |
|------|---------|
| Facade | **Novo** `scripts/workspace` + workspace-guide |
| Opportunity CLI | Comandos `briefing` + `reconcile` |
| Ops | **Novo** `scripts/ops/health.py` fail-closed live |
| Resiliência | Contrato local ADR-021; `LOCAL_RESILIENCE_READY` |
| Relatórios | `executive_report` / `executive_excel` / `commercial_b2g_session` |
| HTML | Sessão comercial SC; plano executivo com charts real-vs-planned corrigidos |
| Makefile | `golden-path`, `report-executivo` |
| Web UI | Continua **inexistente** (UX-01 deferred) |
| Consistência UX | 4/10 → **5/10** |

---

## 13. Recomendações de design (Uma)

1. **Não construir SPA agora.** O ROI pré-VPS está em CLI legível + health honesto + relatórios honestos.
2. **Tratar `workspace` como a home screen do consultor.** Todo comando “secundário” deve ser linkado a partir do guide e, idealmente, de `workspace --help` epilog.
3. **Extrair `scripts/ux_cli.py` (shared):** `print_table_rich`, `fmt_money`, `fmt_date`, `exit_codes`, `progress`.
4. **Um design token file** (`docs/frontend/brand-tokens.md` ou YAML) consumido por PDF e HTML — hoje a paleta está copiada.
5. **Honesty UX como princípio de marca:** badges de confidence, live_fetch flags, “não inventar GO” — já é diferencial do HTML comercial; propagar para CLI.
6. **Pré-VPS operator pack:** `ops/health --human` + progress em crawl + `workspace today` estável.

---

## 14. Verificação (como revalidar este spec)

```bash
# Superfícies CLI
python -m scripts.workspace --help
python -m scripts.opportunity_intel.cli --help
python scripts/local_datalake.py --help
python -m scripts.ops.health --env development; echo exit:$?

# Relatórios
ls scripts/reports/
ls docs/ops/session-2026-07-17/*.html
test -f extra-consultoria-plano-executivo.html

# Ausência de web app de produto
# (não deve haver package.json de app fora de .aiox-core)
find . -name package.json -not -path './.aiox-core/*' -not -path './node_modules/*' | head
```

---

*Fim da Frontend & UX Specification v3.0. Gerado por Uma (UX Design Expert Agent) em 2026-07-17 — Brownfield Discovery Phase 3.*
