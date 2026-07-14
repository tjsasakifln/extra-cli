# Opportunity Intelligence — Requirements (v1.0)

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d
> **Fontes brownfield:** plano-mestre §4, §8 (P0-04), §13 (P0-09), §22 (DoD); epic-technical-debt.md stories 1.4, 1.5

## Visão Geral

Motor de inteligência de licitações abertas B2G. Opera o QW-01 Radar — pipeline auditável que faz crawl de 8+ fontes, transforma registros brutos em oportunidades canônicas, calcula status determinístico (3 níveis), aplica scoring duplo (data confidence + client fit) e ranking determinístico (24 regras: 6 hard blocks, 9 positivas, 9 negativas). Toda recomendação é triagem para revisão humana, nunca veredito definitivo.

## Responsabilidades

- Crawl multi-fonte de editais abertos (PNCP, ComprasGov, SC Compras, DOM-SC, TCE-SC, DOE-SC, PCP, Transparência)
- Transformação de registros brutos → `CanonicalOpportunity` com status canônico determinístico
- QW-01 Radar: pipeline auditável com manifest, readiness gate, exit code padronizado
- Scoring duplo independente: data_confidence (0-100) + client_fit (0-100)
- Ranking determinístico: GO / REVIEW / NO_GO com fatores rastreáveis
- Deduplicação cross-source (PNCP ID → CNPJ+processo → fuzzy fallback)
- Export CSV/JSON com 34 colunas (RADAR_COLUMNS)
- Manifest de cobertura por fonte, ente e capacidade

## Regras de Negócio

- **Regra #1:** QW-01 Radar usa threshold de monitoring coverage de 95%. Exit code 2 se abaixo. 🟢 `radar.py:32`
- **Regra #2:** Status canônico em 3 níveis: source_map → temporal → heuristic. Janela 90/365 dias para modalidades sem data explícita. 🟢 `status.py:45-48`
- **Regra #3:** Ranking determinístico com 24 regras (6 HARD_BLOCKS + 9 POSITIVE + 9 NEGATIVE). NO_GO é default para dados insuficientes. 🟢 `ranking.py:49-80`
- **Regra #4:** Nunca emitir veredito definitivo de participação. Triagem sempre para humano (PRIORITARIA / REVISAR / DESCARTAR). 🟢 `scoring.py:12`
- **Regra #5:** Scoring sempre duplo e independente. Data confidence NUNCA influencia client fit. 🟢 `scoring.py:28-35`
- **Regra #6:** Market share, HHI e supplier ranking (Regra #9) só com dados contratuais confirmados (não com editais abertos). 🟢 `ranking.py`
- **Regra #7:** Crawl usa circuit breaker + retry exponencial com jitter. 3 tentativas máx. 🟢 `crawler_base.py`
- **Regra #8:** Freshness SLA: editais abertos máx 24h; status de oportunidade prioritária exige reconfirmação na execução mais recente. 🟢 `radar.py`

🔴 **LACUNA (plano-mestre §8):** Snapshot reconciliation não implementado. Radar exporta 673 registros mas execução PNCP completa retorna apenas 34. Itens antigos com `is_active=TRUE` não são inativados quando ausentes do snapshot completo. `active_snapshot_integrity` ≠ 100%.

🔴 **LACUNA (plano-mestre §2.2):** Radar é PNCP-only. Demais canais cadastrados mas não provados ponta a ponta. Apenas 20.95% das linhas exportadas têm link oficial. Perfil comercial quase sem parametrização.

🔴 **LACUNA (plano-mestre §13):** Métricas de competitive intelligence (market share, HHI, award share) usam nomes de colunas incompatíveis com schema operacional documentado em `db/migrations/026`. Precisam ser validadas em PostgreSQL real.

## Requisitos Funcionais

| ID | Requisito | Prioridade | Critério de Aceite |
|----|-----------|-----------|-------------------|
| RF-OI01 | CLI com 8 comandos: radar, list, show, explain, coverage, source-health, update, export | Must | `cli.py --help` lista todos |
| RF-OI02 | QW-01 Radar: pipeline completo com manifest, readiness gate, exit code (0=ok, 1=data gaps, 2=below threshold, 3=schema/fatal) | Must | Execução produz `output/runs/<run_id>/` com CSV + manifest.json |
| RF-OI03 | Crawl multi-fonte: adapter contract (crawl → transform → persist → reconcile → health) por fonte | Must | Cada fonte testada ponta a ponta com fixture |
| RF-OI04 | Status canônico determinístico: open / upcoming / closed / suspended / revoked / annulled / failed / unknown | Must | `status.py` cobre 9 valores canônicos |
| RF-OI05 | Ranking: GO (≥70), REVIEW (40-69), NO_GO (<40) com lista de fatores positivos, negativos e blockers | Must | `ranking.py` rastreável por regra |
| RF-OI06 | Scoring duplo: data_confidence_score + client_fit_score independentes | Must | `scoring.py:score_opportunity()` retorna `RadarScores` |
| RF-OI07 | Deduplicação cross-source: PNCP ID → CNPJ+processo → fuzzy (score < limiar → fila revisão) | Must | `dedup.py` com 3 níveis de matching |
| RF-OI08 | Manifest de cobertura: monitoring_coverage% por fonte e ente, readiness global, blockers | Should | `manifest.py` emite JSON + stdout |
| RF-OI09 | PNCP audit: execução das 19 modalidades do endpoint `/api/consulta/v1/contratacoes/proposta` | Must | `pncp_audit.py:run_pncp_open_monitoring()` |
| RF-OI10 | Perfil de cliente (ClientProfile) com weights configuráveis para scoring | Should | `config/client_profiles/extra.yaml` carregado por `profile.py` |
| RF-OI11 | Snapshot reconciliation: inativar registros ausentes do snapshot completo, NUNCA em execução parcial | Must | 🔴 NÃO IMPLEMENTADO — P0-04 pendente |
| RF-OI12 | URL oficial obrigatória para oportunidades acionáveis (PRIORITARIA) | Must | 🔴 NÃO IMPLEMENTADO — 20.95% têm link |

## Requisitos Não Funcionais

| Tipo | Requisito inferido | Evidência no código | Confiança |
|------|--------------------|---------------------|-----------|
| Performance | Crawl com timeout configurável, páginas paginadas | `crawler_base.py` | 🟢 |
| Segurança | Conexão PostgreSQL via psycopg2, DSN via env var | `cli.py:42-45`, `schema.py:connect_postgres()` | 🟢 |
| Disponibilidade | Circuit breaker + retry com exponential backoff (3 tentativas) | `crawler_base.py`, `scripts/crawl/circuit_breaker.py` | 🟢 |
| Auditabilidade | Todo run tem run_id UUID, git_sha, seed_sha256, schema_fingerprint | `radar.py:RADAR_COLUMNS`, `schema.py:git_identity()` | 🟢 |
| Observabilidade | Logging estruturado JSON, métricas de execução por fonte | `radar.py`, `manifest.py` | 🟡 |

## Critérios de Aceitação

```gherkin
Dado uma execução QW-01 completa com perfil "extra.yaml"
Quando o radar processa 19 modalidades PNCP para SC
Então o CSV de saída contém 34 colunas (RADAR_COLUMNS)
E o manifest.json registra monitoring_coverage_percent
E exit_code é 0 se coverage ≥ 95%, 2 se abaixo

Dado um edital com status "revogada" na fonte
Quando o status canônico é calculado
Então status_canonico = "revoked" (source_map tem precedência)

Dado uma oportunidade sem objeto e sem órgão
Quando o ranking é calculado
Então blockers incluem "sem_objeto" e "sem_orgao"
E ranking = "NO_GO"

Dado uma execução PNCP parcial (max_pages ou erro)
Quando a reconciliação de snapshot é tentada
Então NENHUM registro é inativado
E o manifest registra "reconciliation_skipped: partial_run"

Dado uma oportunidade PRIORITARIA sem URL oficial
Quando o radar exporta
Então a oportunidade é degradada para REVISAR
E missing_fields inclui "official_url"
```

## Prioridade (MoSCoW)

| Requisito | MoSCoW | Justificativa |
|-----------|--------|---------------|
| Crawl PNCP | Must | Caminho crítico, única fonte comprovada ponta a ponta |
| QW-01 Radar | Must | Produto principal, execução diária |
| Status canônico | Must | Base para ranking e scoring |
| Scoring duplo | Must | Diferencia qualidade do dado de aderência ao perfil |
| Ranking determinístico | Must | Triagem humana depende dele |
| Snapshot reconciliation | Must | 🔴 P0-04 — sem isso, radar não é confiável |
| Fontes complementares (não-PNCP) | Should | P0-06 — necessário para cobertura ≥95% |
| Perfil EXTRA completo | Should | P0-07 — sem parametrização, scoring é genérico |
| Competitive intel (market share, HHI) | Should | P0-09 — métricas ainda não validadas em PostgreSQL real |
| Export formatos adicionais (Parquet) | Could | CSV/JSON atendem caso atual |

## Rastreabilidade de Código

| Arquivo | Função / Classe | Cobertura |
|---------|-----------------|-----------|
| `scripts/opportunity_intel/cli.py` | `cmd_radar`, `cmd_list`, `cmd_show`, `cmd_explain`, `cmd_coverage`, `cmd_source_health`, `cmd_update`, `cmd_export` | 🟢 |
| `scripts/opportunity_intel/radar.py` | `RadarExecution`, `MONITORING_THRESHOLD`, `RADAR_COLUMNS` | 🟢 |
| `scripts/opportunity_intel/ranking.py` | `Rule`, `HARD_BLOCKS`, `POSITIVE_FACTORS`, `NEGATIVE_FACTORS` | 🟢 |
| `scripts/opportunity_intel/scoring.py` | `score_opportunity()`, `RadarScores`, `TRIAGE_VALUES` | 🟢 |
| `scripts/opportunity_intel/status.py` | `calculate_canonical_status()`, `_PNCP_STATUS_MAP` | 🟢 |
| `scripts/opportunity_intel/crawler_base.py` | Base crawler com circuit breaker, retry, checkpoint | 🟢 |
| `scripts/opportunity_intel/pncp_audit.py` | `run_pncp_open_monitoring()`, `PncpRunOutcome` | 🟢 |
| `scripts/opportunity_intel/pncp_crawler.py` | PNCP-specific crawler adapter | 🟢 |
| `scripts/opportunity_intel/transformer.py` | Transformação raw → canônico | 🟢 |
| `scripts/opportunity_intel/dedup.py` | Deduplicação cross-source 3 níveis | 🟢 |
| `scripts/opportunity_intel/manifest.py` | Manifest de cobertura e readiness | 🟢 |
| `scripts/opportunity_intel/models.py` | SQLAlchemy models | 🟢 |
| `scripts/opportunity_intel/schema.py` | `validate_qw01_schema()`, `schema_fingerprint()`, `git_identity()` | 🟢 |
| `scripts/opportunity_intel/profile.py` | `load_client_profile()`, `ClientProfile` | 🟢 |
| `scripts/opportunity_intel/backfill.py` | Backfill de dados históricos | 🟡 |
