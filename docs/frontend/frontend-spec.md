# Frontend & UX Specification — Extra Consultoria

**Version:** 1.0  
**Date:** 2026-07-13  
**Author:** Uma (UX Design Expert Agent)  
**Status:** Assessment Complete

---

## Executive Summary

The Extra Consultoria project has **zero web frontend**. All user interaction is exclusively through **CLI (command line interface)** tools and **generated output files** (PDF, Excel, CSV, JSON). There is no web server, no API layer, no browser-based UI, and no graphical interface of any kind.

### Current UI Layers

| Layer | Count | Technologies | User Base |
|-------|-------|-------------|-----------|
| CLI Tools | ~70 Python scripts with `main()` | `argparse`, `rich`, `psycopg2` | Internal team (VPS/SSH access) |
| Terminal Output | All CLIs | `print()`, `rich.Console`, ASCII tables | Internal team |
| PDF Reports | 3 generators | `reportlab`, `fpdf`, `openpyxl` | Clients (via email) |
| Excel Reports | 2 generators | `openpyxl`, `pandas` | Internal team, clients |
| JSON/CSV Export | Multiple CLIs | `csv`, `json` modules | Internal team, data analysts |
| HTML Dashboard | 1 static HTML | Coverage report | Internal (epic-coverage) |

---

## CLI Interface Inventory

All CLIs use `argparse` with subparsers. A total of **70+ Python scripts** define command-line entry points. Below are the primary user-facing tools.

### 1. Opportunity Intelligence CLI

**File:** `scripts/opportunity_intel/cli.py`  
**Commands:** 8

| Command | Arguments | Output Format | UX Quality |
|---------|-----------|--------------|------------|
| `radar` | `--profile`, `--seed`, `--window-days`, `--output-dir`, `--update`, `--timeout`, `--max-retries`, `--max-pages`, `--max-records`, `--dsn` | JSON to stdout + filesystem | Fair (wall of JSON, no progress) |
| `list` | `--status`, `--uf`, `--municipio`, `--modalidade`, `--ranking`, `--source`, `--search`, `--valor-min`, `--limit`, `--format` | Table or JSON | Fair (basic ASCII table, 20-char truncation) |
| `show` | `id` (positional), `--dsn` | Structured text (key-value pairs in sections) | Good (well-organized multi-section display) |
| `explain` | `id` (positional), `--dsn` | Structured text with emoji markers | Good (clear positive/negative/blocker breakdown) |
| `coverage` | `--format`, `--dsn` | Table or JSON | Fair (same truncated table) |
| `source-health` | `--format`, `--dsn` | Table or JSON + runs history | Fair |
| `update` | `--source`, `--mode`, `--limit`, `--dsn` | JSON status + counts | Poor (no progress bar, runs synchronously) |
| `export` | `--format`, `--output`, `--status`, `--ranking`, `--limit`, `--dsn` | JSON/CSV file | Good (clear success message with count) |

**UX Issues:**
- `_print_table()` truncates values at 20 characters and limits to 10 columns — too aggressive for meaningful analysis
- No `rich` library usage — raw ASCII formatting with manual alignment
- Hardcoded column exclusion suppresses relevant fields (e.g., `ranking_fatores`)
- `radar` command outputs raw JSON to stdout — no human-readable summary
- No progress indicator for `update` command that may run for minutes
- Table columns are dynamically derived from dict keys — inconsistent ordering

### 2. DataLake Local CLI

**File:** `scripts/local_datalake.py`  
**Commands:** 7

| Command | Arguments | Output Format | UX Quality |
|---------|-----------|--------------|------------|
| `stats` | None | ASCII table with `pg_size_pretty` | Good |
| `search` | `--uf`, `--dias`, `--modalidades`, `--query`, `--texto`, `--valor-min/max`, `--modo`, `--limit`, `--head`, `--json` | Rich formatted + JSON | **Good** (uses `rich` library) |
| `supplier` | `--cnpj`, `--dias`, `--limit`, `--head`, `--json` | Rich formatted + JSON | Good |
| `pricing` | `--keywords`, `--uf`, `--meses` | ASCII stats (P10-P90, Mean, StdDev, CV) | Good (statistical rigor) |
| `competitors` | `--keywords`, `--meses`, `--limit` | ASCII formatted table with currency | Good |
| `detail` | `--pncp-id`, `--json` | Key-value pairs (truncated at 200 chars) | Fair |
| `coverage` | `--baseline`, `--gaps`, `--snapshot`, `--export` | **Rich formatted** (Panel, Table, boxes) | **Excellent** (best CLI UX in project) |

**UX Advantages:**
- Uses `rich` library for colored output, styled tables, panels, and boxes
- `--json` flag is a boolean toggle (simpler than `--format table|json`)
- `--head` flag controls how many results to display without losing query scope
- Coverage dashboard has color-coded status indicators
- Monetary values consistently formatted as `R$ X,xxx.xx`

### 3. Health Dashboard

**File:** `scripts/health-dashboard.py`  
**Modes:** 4

| Mode | Output | UX Quality |
|------|--------|------------|
| Default | Full ASCII dashboard with `[OK]`/`[WARN]`/`[FAIL]` icons | Good (well-structured, organized sections) |
| `--summary` | One-line key=value pairs for monitoring integration | Good |
| `--json` | Complete JSON dump | Good |
| `--watch` | Auto-refresh every N seconds | Good (daemon-like UX) |

**Exit Codes:** 0 (OK), 1 (Warnings), 2 (Critical) — best in project

### 4. Report Generation Tools

| Script | Description | Output | UX Quality |
|--------|-------------|--------|------------|
| `reports/panorama.py` | Market panorama | Terminal + Excel + PDF | Fair (terminal section is basic ASCII) |
| `reports/coverage_gaps.py` | Uncovered entities export | Excel with multiple sheets | Fair (file output only) |
| `reports/coverage_weekly.py` | Weekly coverage report | Terminal + Excel | Fair |
| `generate-report-b2g.py` | Full B2G consulting report (287KB) | Excel + PDF | Good (comprehensive) |
| `generate_consultoria_pdf.py` | Consulting PDF (66KB) | PDF | Good |
| `generate_proposta_pdf.py` | Proposal PDF (44KB) | PDF | Good |
| `intel-excel.py` / `intel_excel.py` | Intelligence Excel | Excel | Fair |

---

## Report/Output Formats

### Terminal Output Quality

The project uses **two visual paradigms** for terminal output:

**Paradigm 1: rich** (modern, colored, styled)
- Used by: `local_datalake.py` (coverage command)
- Features: `rich.table.Table`, `rich.console.Console`, `rich.panel.Panel`, `rich.box`
- Colors: Green for success, red for errors, cyan for headers, yellow for warnings
- Professional appearance with box-drawing characters

**Paradigm 2: Raw print/ASCII** (legacy, monochrome)
- Used by: `opportunity_intel/cli.py`, `health-dashboard.py`, `panorama.py`
- Features: `"".format()` padding, manual column alignment
- Colors: None (monochrome)
- Table borders: Manual `===`, `---` separators

### Generated File Formats

| Format | Library | Quality Level | Notes |
|--------|---------|--------------|-------|
| **PDF** | `reportlab`, `fpdf` | Professional | Styled reports with headers, tables, logos |
| **Excel (.xlsx)** | `openpyxl` | Professional | Multi-sheet, styled cells, charts |
| **CSV** | `csv.DictWriter` | Good | UTF-8 with BOM for Excel compatibility |
| **JSON** | `json.dump` | Good | `ensure_ascii=False`, `indent=2`, `default=str` |
| **HTML** | Jinja2 (via coverage) | Basic | Single static HTML dashboard |

### Output Directory Structure

```
output/
  excels/        — Excel reports
  logs/          — Crawl/ingestion logs
  pdfs/          — Generated PDFs
  qw-01/         — QW-01 radar runs (Snapshots, manifests, CSVs, XLSX, Markdown summaries)
  readiness/     — Readiness assessment (coverage gaps, manifests, health reports)
  reports/
    coverage/    — Coverage gap Excel exports
```

---

## User Journey Maps

### Journey 1: Daily Operations Monitoring

```
User logs into VPS
  → python scripts/health-dashboard.py
  → [OK] db, [OK] disk, [OK] storage
  → Crawl stats: 12 runs today, 98% success rate
  → Backup: 3h ago, 450MB
  → Alerts: 0 critical, 2 warnings
```

**Pain points:** No color in terminal (uses ASCII `[OK]` instead of `rich` green), no web dashboard for quick glance.

### Journey 2: Finding Bidding Opportunities

```
User wants to find open engineering bids in SC:
  → python scripts/opportunity_intel/cli.py list --status open --uf SC --modalidade concorrencia --ranking GO
  → Table displayed with 20-char truncated columns
  → python scripts/opportunity_intel/cli.py show 42
  → Full detail page with all fields organized in sections
  → python scripts/opportunity_intel/cli.py explain 42
  → Ranking factors broken down (positives, negatives, blockers)
```

**Pain points:** Table truncation hides relevant data. Must use `show` on each ID to see full details. No way to open URLs directly in browser.

### Journey 3: Supplier/Competitor Research

```
User wants to check a supplier:
  → python scripts/local_datalake.py supplier --cnpj 46391815000189
  → Rich formatted list of contracts

User wants pricing benchmarks:
  → python scripts/local_datalake.py pricing --keywords "pavimentacao" --uf SC
  → Statistical distribution with P10-P90

User wants top competitors:
  → python scripts/local_datalake.py competitors --keywords "engenharia"
  → Ranked table of competitors by contract volume
```

**UX Highlights:** This journey has the best CLI experience — `rich` formatting, clear stats, proper currency formatting.

### Journey 4: Data Ingestion & Radar

```
User triggers data update:
  → python scripts/opportunity_intel/cli.py update --source pncp
  → ... (long wait with no progress indicator)
  → JSON status and counts

User then runs radar:
  → python -m scripts.opportunity_intel.cli radar --profile config/client_profiles/extra.yaml
  → ... (long wait with minimal output)
  → Final JSON dump including exit_code
  → Files generated in output/qw-01/
```

**Pain points:** NO progress bars or spinners. The `update` and `radar` commands run silently for potentially minutes. Users stare at a blank terminal.

### Journey 5: Report Generation

```
User generates client report:
  → python scripts/reports/panorama.py --output-pdf
  → Terminal output shows sections
  → PDF saved to output/pdfs/
  → Can also get Excel version

User generates full consulting report:
  → python scripts/generate-report-b2g.py --input data.json --output report.pdf
  → PDF generated (287K script — very large)
```

**Pain points:** The `generate-report-b2g.py` is 287KB (single file) — monolith that bundles all B2G report logic. No user confirmation before overwriting.

---

## UX Consistency Assessment

### Consistency Score: **4/10**

| Metric | Rating | Details |
|--------|--------|---------|
| Argument naming | **6/10** | Inconsistent: `--format` vs `--json`, `--output` vs `--output-dir`, `--limit` vs `--head` |
| Output formatting | **3/10** | Two visual paradigms (rich vs raw), no standardized table component |
| Error handling | **4/10** | Some tools catch and format errors, others dump tracebacks |
| Exit codes | **3/10** | 0/1 (local_datalake), 0/1/2 (health-dashboard), sys.exit(1) directly (opportunity_intel) |
| Help/docstrings | **6/10** | Most tools have good usage examples, some are minimal |
| Progress indication | **1/10** | No tool uses progress bars/spinners |
| Color/formatting | **4/10** | Only one tool (local_datalake coverage) uses rich colors |
| Visual hierarchy | **5/10** | Section headers, separators exist but vary between tools |

### Inconsistency Catalog

1. **Dual display libraries** — `rich` vs raw `print()`. The `rich` library is already a dependency (imported in `local_datalake.py`) but only used by one command within that tool.

2. **Output format flags** — Three different patterns exist:
   - `--format table|json` (opportunity_intel)
   - `--json` boolean flag (local_datalake, health-dashboard)
   - No format option (most report scripts)

3. **Exit code strategy** — Three patterns:
   - `sys.exit(1)` directly (opportunity_intel)
   - `return 0/1` (local_datalake)
   - `sys.exit(0/1/2)` (health-dashboard, best pattern)

4. **Table display** — No shared table component:
   - `_print_table()` in opportunity_intel/cli.py — self-rolled, truncates data
   - `rich.table.Table` in local_datalake.py — professional but limited to one command
   - Manual `print()` with `format()` in panorama.py and health-dashboard.py

5. **Monetary formatting** — `_fmt_money()` in opportunity_intel/cli.py vs inline `f"R$ {v:,.2f}"` in local_datalake.py

6. **Date formatting** — `_fmt_date()` in opportunity_intel (dd/mm/YYYY) vs raw ISO strings in other tools

---

## Identified Technical Debts

| ID | Debt | Severity | Impact | Effort (h) |
|----|------|----------|--------|------------|
| UX-01 | **No web UI** — all interaction requires SSH/VPS access | HIGH | Limits user base to technical team; no client-facing portal | 80+ |
| UX-02 | **No progress indicators** — long-running commands (update, radar, PDF generation) show no feedback | HIGH | Users don't know if tool is stuck or progressing; may abort prematurely | 8 |
| UX-03 | **Dual display paradigm** — `rich` vs raw `print()` with no shared component | MEDIUM | Inconsistent visual quality; harder to maintain; code duplication | 12 |
| UX-04 | **Table truncation in opportunity_intel** — `_print_table()` truncates at 20 chars / 10 cols | MEDIUM | Users cannot read key data (objeto, orgao_nome) without switching to JSON | 4 |
| UX-05 | **Inconsistent exit codes** — 0/1 vs 0/1/2 across tools | LOW | Scripting/monitoring integrations behave unpredictably | 2 |
| UX-06 | **Inconsistent output flags** — `--format table|json` vs `--json` boolean | LOW | Cognitive load on users switching between tools | 2 |
| UX-07 | **No pagination** for large result sets (list can return up to 500 rows) | LOW | Terminal scrolling overflow; no interactive browsing | 6 |
| UX-08 | **Empty output on errors** — some tools print nothing on failure (just exit code) | MEDIUM | Users don't know what went wrong; must rerun with debug flags | 3 |
| UX-09 | **Coverage dashboard duplicated** in both opportunity_intel and local_datalake CLIs | MEDIUM | Code duplication; different UX; users confused which to use | 6 |
| UX-10 | **Monolithic report generator** — `generate-report-b2g.py` at 287KB single file | MEDIUM | Hard to maintain; long startup time; high cognitive load for developer | 16 |
| UX-11 | **No terminal hyperlinks** — source URLs are printed as plain text, not clickable | LOW | Users cannot quickly open PNCP pages in browser | 2 |
| UX-12 | **No input validation messages** — CLI args are validated only at DB query time | LOW | Users get SQL errors instead of friendly "invalid UF code" messages | 4 |

### Priority Debt Resolution Roadmap

**Immediate (next sprint):**
1. **UX-02** — Add `rich.progress.Progress` or `tqdm` to `update` and `radar` commands (8h)
2. **UX-04** — Fix `_print_table` to not truncate key identifier columns; use `rich.Table` (4h)

**Short-term (current quarter):**
3. **UX-03** — Migrate all CLI table output to `rich.Table` (12h)
4. **UX-05/06** — Standardize exit codes and output flags across all CLIs (4h)
5. **UX-08** — Add error message output to all CLI tools (3h)
6. **UX-09** — Consolidate coverage commands into single entry point (6h)

**Medium-term:**
7. **UX-11** — Add clickable terminal hyperlinks via `rich` (2h)
8. **UX-12** — Add `argparse` type validators with friendly messages (4h)
9. **UX-07** — Add interactive pager or --pager flag for long results (6h)
10. **UX-10** — Refactor monolithic report generator into modular pipeline (16h)

**Long-term strategic:**
11. **UX-01** — Evaluate web UI framework (FastAPI+HTMX for light MVP, Streamlit for internal dashboards, or Django for full client portal) (80h+)

---

## Observations for Design System

The project currently has **no design tokens, no component library, and no shared visual primitives** for its terminal output. If a terminal UI (TUI) or web UI is introduced in the future, the following should be standardized:

- **Color palette:** Green (success), Red (error), Yellow (warning), Cyan (highlight), Dim (metadata) — already implied by `rich` usage in local_datalake.py
- **Status icons:** `[OK]`, `[WARN]`, `[FAIL]` (health-dashboard) or emoji-based `✓`, `✗`, `⊘` (opportunity_intel explain)
- **Monetary format:** Always `R$ X.xxx,xx` with proper thousands and decimal separators
- **Date format:** `dd/mm/YYYY` (Brazilian standard) for all human-readable output
- **Table style:** Use `rich.Table` with `box=box.SIMPLE` (consistent with existing best example)
- **Error format:** `[ERROR] Human-readable message` — never raw tracebacks

---

## Appendix: All CLI Scripts with `main()` Entry Points

The following 70+ scripts define `main()` functions with CLI entry points. The ones listed below are the primary user-facing tools; the remainder are utility/internal:

| Script | Lines | Primary Function |
|--------|-------|-----------------|
| `opportunity_intel/cli.py` | 686 | Opportunity search, ranking, radar |
| `local_datalake.py` | 684 | DataLake queries (search, supplier, pricing, competitors) |
| `health-dashboard.py` | 473 | System health monitoring |
| `reports/panorama.py` | ~400 | Market panorama report |
| `reports/coverage_gaps.py` | ~200 | Coverage gap export |
| `generate-report-b2g.py` | 7,115 | Full B2G consulting report (largest file) |
| `generate_consultoria_pdf.py` | 1,661 | Consulting PDF generation |
| `generate_proposta_pdf.py` | ~1,100 | Proposal PDF generation |
| `intel_pipeline.py` | 496 | Full intelligence pipeline |
| `intel-analyze.py` | 706 | Intelligence analysis |
| `intel-collect.py` | 1,273 | Intelligence collection |
| `intel-enrich.py` | 250 | Entity enrichment |
| `freshness_gate.py` | 203 | Data freshness validation |

---

*End of Frontend & UX Specification. Generated by Uma (UX Design Expert Agent) on 2026-07-13.*
