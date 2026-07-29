# Extra Recurring Delivery — Runbook

Comparação CLI-first de pacotes semanais (`extra-weekly`) para detectar deltas e gerar relatórios de recorrência, alertas urgentes e apoio de reunião.

**Não é:** dashboard, frontend, SaaS, fila, streaming ou notificação multi-canal.

## Comando canônico

```bash
python3 -m scripts.ops.extra_recurring_delivery run \
  --current-run /caminho/weekly-atual \
  --delivery-out /caminho/externo/ao/git \
  [--previous-run /caminho/weekly-anterior] \
  [--previous-monthly /caminho/mensal-anterior] \
  [--profile config/client_profiles/extra.yaml] \
  [--expiry-window-days 180] \
  [--as-of YYYY-MM-DD]
```

### Validar pack (WeeklyInput)

```bash
python3 -m scripts.ops.extra_recurring_delivery validate-weekly \
  --current-run /caminho/weekly-run
```

## Makefile (para o integrator adicionar)

**Não editar o Makefile neste PR** — trecho sugerido:

```makefile
.PHONY: extra-recurring-delivery test-extra-recurring-delivery
# Compare weekly packs → external recurring delivery (deltas + reports + alerts).
# CURRENT_RUN required. PREVIOUS_RUN optional (FIRST_RUN if omitted).
# DELIVERY_OUT should be outside git for client packs.
extra-recurring-delivery:
	@test -n "$(CURRENT_RUN)" || (echo "ERROR: set CURRENT_RUN=/path/to/weekly-current"; exit 2)
	@test -n "$(DELIVERY_OUT)" || (echo "ERROR: set DELIVERY_OUT=/path/external"; exit 2)
	@echo "==> Extra Recurring Delivery"
	@echo "    CURRENT_RUN=$(CURRENT_RUN)"
	@echo "    PREVIOUS_RUN=$(PREVIOUS_RUN)"
	@echo "    DELIVERY_OUT=$(DELIVERY_OUT)"
	python3 -m scripts.ops.extra_recurring_delivery run \
		--current-run "$(CURRENT_RUN)" \
		--delivery-out "$(DELIVERY_OUT)" \
		$(if $(PREVIOUS_RUN),--previous-run "$(PREVIOUS_RUN)",) \
		$(if $(PREVIOUS_MONTHLY),--previous-monthly "$(PREVIOUS_MONTHLY)",) \
		$(if $(PROFILE),--profile "$(PROFILE)",) \
		$(if $(EXPIRY_WINDOW_DAYS),--expiry-window-days "$(EXPIRY_WINDOW_DAYS)",) \
		$(if $(AS_OF),--as-of "$(AS_OF)",)
	@echo "==> done (see DELIVERY_OUT / manifest.json)"

test-extra-recurring-delivery:
	python3 -m pytest tests/test_extra_recurring_delivery.py -q --tb=short --no-cov
```

Uso:

```bash
make extra-recurring-delivery \
  CURRENT_RUN=/path/weekly-current \
  PREVIOUS_RUN=/path/weekly-previous \
  DELIVERY_OUT=/path/external \
  AS_OF=2026-07-29
```

## Entradas

| Flag | Obrigatório | Descrição |
|------|-------------|-----------|
| `--current-run` | sim | Dir do weekly pack atual (`manifest.json` + `checksums.json` + CSVs) |
| `--previous-run` | não | Weekly anterior; se omitido → status `FIRST_RUN` (sem crash) |
| `--previous-monthly` | não | Dir/arquivo de comparativo mensal anterior |
| `--delivery-out` | sim | Saída externa |
| `--profile` | não | Default `config/client_profiles/extra.yaml` |
| `--expiry-window-days` | não | Default `180` — janela `[0, N]` dias para contratos |
| `--as-of` | não | Data de referência `YYYY-MM-DD` |

### WeeklyInput (interface congelada)

Reutiliza `validate_weekly_pack` de `extra_first_client_delivery`:

- `manifest.json`, `checksums.json` válidos
- `opportunities.csv` obrigatório
- Opcionais: `contracts.csv`, `competitors.csv`, `orgaos.csv`, `source_health.csv`

Layout gerado por `python -m scripts.ops.weekly_cycle` / `make extra-weekly`.

## EventDelta (interface congelada)

Campos: `entity_type`, `entity_id`, `event_type`, `previous_value`, `current_value`, `detected_at`, `source_run_id`, `previous_run_id`, `official_url`, `severity`, `action_required`.

### `event_type` permitidos

| Tipo | Detecção |
|------|----------|
| `NEW_TENDER` | ID de oportunidade só no current (não em FIRST_RUN) |
| `DEADLINE_CHANGED` | `data_encerramento` mudou |
| `STATUS_CHANGED` | status genérico mudou |
| `SUSPENDED` / `REVOKED` / `REOPENED` / `RECTIFIED` | transição de status classificada |
| `CONTRACT_ENTERED_EXPIRY_WINDOW` | contrato entrou na janela 0–N dias |
| `NEW_WINNER` | fornecedor novo no panorama |
| `WINNER_CONCENTRATION_CHANGED` | top1 share Δ ≥ 5pp |
| `SOURCE_DEGRADED` | level de freshness piorou vs previous |
| `FRESHNESS_BREACH` | age > SLA ou level stale/never_crawled/degraded |

## Saídas obrigatórias (`--delivery-out`)

| Artefato | Função |
|----------|--------|
| `weekly-report.md` | Relatório semanal consolidado |
| `weekly-report.xlsx` | Mesmo conteúdo (planilhas) |
| `weekly-delta.json` / `.csv` | Todos os EventDelta |
| `tender-events.csv` | Eventos (mesma grade; foco editais) |
| `expiring-contracts.csv` | Contratos na janela |
| `orgaos-winners-delta.csv` | Deltas de vencedores/concentração |
| `urgent-alerts.json` / `.csv` | Subconjunto urgente (**separado**) |
| `monthly-report.md` | Relatório mensal comparativo |
| `monthly-comparison.json` | Variação de métricas |
| `meeting-support.md` | Pauta de reunião |
| `source-health.json` | Saúde das fontes + breaches |
| `manifest.json` / `checksums.json` | Integridade do pack de entrega |

## Fail-closed

| Condição | Exit |
|----------|------|
| `--current-run` ausente / não é dir | 2 |
| Pack sem manifest/checksums/opportunities ou checksum inválido | 2 |
| `--previous-run` informado mas path inexistente | 2 |
| Sucesso | 0 |
| Erro técnico inesperado | 1 |

Regras:

- Alertas **nunca** substituem relatórios consolidados (sempre grava ambos).
- Relatórios existem mesmo com **zero** alertas (`SUCCESS_ZERO` / `FIRST_RUN`).
- Fixtures de teste **não** são path de evidência operacional.

## Status de delta

| Status | Quando |
|--------|--------|
| `FIRST_RUN` | Sem `--previous-run` |
| `SUCCESS_ZERO` | Previous presente e zero eventos |
| `OK` | Há pelo menos um EventDelta |

## Testes

```bash
python3 -m pytest tests/test_extra_recurring_delivery.py -q --tb=short --no-cov
# ou (após integrator):
make test-extra-recurring-delivery
```

## Reuso

- `scripts.ops.extra_first_client_delivery.validate_weekly_pack` / `load_csv_rows`
- `scripts.ops.strategic_monthly_monitor.contracts_in_window` / `compute_variation`
- Weekly pack layout de `scripts.ops.weekly_cycle.stage_delivery`

## Claims proibidos

- Cobertura operacional 95%
- `VPS_OPERATIONAL` / `PROJECT_DONE`
- Notificações multi-canal em tempo real
- Fixtures como evidência de produção
