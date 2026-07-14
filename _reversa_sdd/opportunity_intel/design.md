# Opportunity Intelligence — Design Técnico (v1.0)

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d

## Interface

### CLI (8 comandos)

| Comando | Entrada | Saída | Exit codes |
|---------|---------|-------|------------|
| `radar --profile <yaml>` | ClientProfile YAML | CSV + manifest.json em `output/runs/<run_id>/` | 0=ok, 1=data gaps, 2=below 95%, 3=fatal |
| `list --status open --uf SC --limit 20` | Filtros SQL | Tabela formatada (Rich) | 0 |
| `show <id>` | opportunity_key | Detalhe completo (JSON) | 0/1 |
| `explain <id>` | opportunity_key | Fatores de ranking + scores | 0/1 |
| `coverage` | — | Dashboard cobertura por fonte/ente | 0 |
| `source-health` | — | Status de cada fonte (ok/stale/error) | 0 |
| `update --source <name>` | source name | Run result | 0/1 |
| `export --format csv\|json -o <path>` | Filtros | Arquivo CSV/JSON | 0 |

### Classes/Funções Core

| Símbolo | Assinatura | Retorno | Observação |
|---------|-----------|---------|------------|
| `score_opportunity` | `(row, entity, profile, status_evidence, now, freshness_window_days)` | `RadarScores` | Duplo scoring independente |
| `calculate_canonical_status` | `(source, source_status, data_encerramento, modalidade, now)` | `str` | 3 níveis: source→temporal→heuristic |
| `run_pncp_open_monitoring` | `(conn, entities, run_id, ...)` | `PncpRunOutcome` | 19 modalidades PNCP |
| `load_canonical_universe` | `(seed_path, radius_km)` | `CanonicalUniverse` | 1.093 entes no raio |
| `load_client_profile` | `(profile_path)` | `ClientProfile` | YAML com weights configuráveis |
| `validate_qw01_schema` | `(conn)` | `SchemaValidation` | Gate pré-radar |

## Fluxo Principal (QW-01 Radar)

1. **Gate de entrada:** `validate_qw01_schema()` — verifica schema, extensions, migrations 🟢 `schema.py`
2. **Carregar universo:** `load_canonical_universe(seed, 200km)` → 1.093 entes 🟢 `lib/universe.py`
3. **Carregar perfil:** `load_client_profile(profile_path)` → `ClientProfile` com weights 🟢 `profile.py`
4. **Crawl PNCP:** `run_pncp_open_monitoring()` — 19 modalidades, paginação completa 🟢 `pncp_audit.py`
5. **Crawl complementar:** `iter_sources()` → cada fonte com adapter contract 🟢 `crawler_base.py`
6. **Transform:** raw → `CanonicalOpportunity` com status canônico 🟢 `transformer.py`, `status.py`
7. **Deduplicar:** cross-source matching 3 níveis (PNCP ID → CNPJ+processo → fuzzy) 🟢 `dedup.py`
8. **Score:** `score_opportunity()` para cada registro — data_confidence + client_fit independentes 🟢 `scoring.py`
9. **Rank:** regras determinísticas (24 regras) → GO/REVIEW/NO_GO 🟢 `ranking.py`
10. **Readiness gate:** `monitoring_coverage_percent ≥ 95%` → exit code 🟢 `radar.py`
11. **Export:** CSV 34 colunas + manifest.json + evidence ledger 🟢 `radar.py`
12. **🔴 Snapshot reconciliation (NÃO IMPLEMENTADO):** inativar ausentes do snapshot completo 🟡 `plano-mestre §8`

## Fluxos Alternativos

- **Crawl incremental:** `--mode incremental` usa checkpoint por data, retoma de onde parou
- **Fonte única:** `update --source pncp` executa apenas uma fonte
- **Sem perfil:** scoring usa defaults conservadores, todos os weights = 0
- **Universo vazio:** radar aborta com exit code 3 (fatal)
- **Schema mismatch:** `validate_qw01_schema()` falha → radar aborta antes de qualquer crawl

## Dependências

| Componente | Relação | Como usa |
|------------|--------|----------|
| `scripts/lib/universe.py` | Hard | Carrega 1.093 entes canônicos do raio 200km |
| `scripts/lib/geocode.py` | Hard | Cálculo de distância (Haversine) |
| `scripts/crawl/registry.py` | Hard | `iter_sources()` para crawl multi-fonte |
| `scripts/crawl/circuit_breaker.py` | Hard | Proteção em crawls HTTP |
| `scripts/matching/` | Soft | Entity matching (órgão → sc_public_entities) |
| `scripts/opportunity_intel/schema.py` | Hard | Conexão PostgreSQL, validação, fingerprint |
| `config/client_profiles/extra.yaml` | Config | Perfil comercial com weights de scoring |
| PostgreSQL (local) | Hard | `opportunity_intel` table, views, evidence ledger |
| OpenAI GPT-4.1 Nano | Soft | Classificação de categoria (opcional, não determinístico) |

## Decisões de Design Identificadas

| Decisão | Evidência no código | Confiança |
|---------|---------------------|-----------|
| Scoring sempre duplo e independente (data ≠ fit) | `scoring.py:28-35` | 🟢 |
| Nunca emitir veredito PARTICIPAR/NÃO PARTICIPAR | `scoring.py:12`, ADR-016 | 🟢 |
| Ranking determinístico, LLM opcional como enrichment | `ranking.py:13-17` | 🟢 |
| PNCP como fonte primária, demais complementares | `radar.py`, `pncp_audit.py` | 🟢 |
| Exit code padronizado (0/1/2/3) com semântica definida | `radar.py:RadarExecution.exit_code` | 🟢 |
| Monitoring threshold 95% (abaixo = exit code 2) | `radar.py:32` | 🟢 |
| CSV com 34 colunas fixas (RADAR_COLUMNS) | `radar.py:35-70` | 🟢 |
| Run idempotente: run_id UUID, git_sha, seed_sha256, schema_fingerprint | `schema.py`, `radar.py` | 🟢 |

## Estado Interno

| Estado | Onde | Persistência |
|--------|------|-------------|
| `RadarExecution` | `radar.py` dataclass | `manifest.json` no output dir |
| `RadarScores` | `scoring.py` dataclass |嵌入 CSV (colunas score) |
| `PncpRunOutcome` | `pncp_audit.py` | `manifest.json` |
| `CanonicalUniverse` | `lib/universe.py` | Carregado da planilha seed a cada run |
| `ClientProfile` | `profile.py` | YAML em `config/client_profiles/` |
| Checkpoint de crawl | `crawler_base.py` | `data/checkpoints/<source>/` |

## Observabilidade

| Sinal | Método | Local |
|-------|--------|-------|
| Run manifest | `manifest.json` com todas as métricas | `output/runs/<run_id>/` |
| Exit code | 0/1/2/3 padronizado | stdout + `$?` |
| Evidence ledger | `coverage_evidence` table | PostgreSQL |
| Logging | JSON estruturado por fonte/run | stdout + journald |
| Schema fingerprint | SHA-256 do schema | `manifest.json` |

## Riscos e Lacunas

- 🔴 **P0-04 Snapshot reconciliation:** Radar exporta 673 registros mas só 34 foram vistos na execução corrente. Sem reconciliação, 639 registros são exibidos sem reconfirmação.
- 🔴 **P0-06 Fontes complementares:** Apenas PNCP provado ponta a ponta. 7 outras fontes cadastradas mas sem smoke test real.
- 🔴 **P0-07 Perfil EXTRA:** `extra.yaml` quase vazio (apenas alguns termos de objeto). Sem parametrização, scoring de client_fit é essencialmente aleatório.
- 🔴 **P0-09 Competitive Intel:** Métricas de market share/HHI usam nomes de colunas incompatíveis com `db/migrations/026`. Precisam ser reescritas contra `v_contracts_canonical`.
- 🟡 Apenas 20.95% das oportunidades têm link oficial. URL oficial deveria ser obrigatória para PRIORITARIA.
- 🟡 Dedup cross-source com fuzzy fallback pode gerar falsos positivos. Sem revisão humana, matches abaixo do limiar vão para fila de revisão.
