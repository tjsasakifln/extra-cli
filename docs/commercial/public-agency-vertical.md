# Vertical comercial — órgãos públicos (CONFENGE)

## O que o sistema faz

Integra à `make confenge-commercial-cycle` a modalidade **public-agencies**, que prospecta **órgãos e entidades públicas** (não fornecedores privados) com sinais de possível necessidade técnica em obras e serviços de engenharia.

Pacote: `scripts/public_agency/`  
Campanha: `CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01`

## O que o sistema **não** faz

- Não vende nem garante dispensa de licitação ou contratação direta
- Não substitui fiscal/gestor público (art. 117)
- Não envia outreach automático
- Não emite parecer jurídico
- Não inventa atestados, ART, acervo ou credenciais
- Não mistura `PUBLIC_AGENCY_PROSPECT` com supplier leads

## Entrypoint

```bash
# apenas órgãos públicos
make confenge-commercial-cycle CONFENGE_COMMERCIAL_TARGET=public-agencies

# ou
export LOCAL_DATALAKE_DSN=postgresql://...
python3 -m scripts.ops.confenge_commercial_cycle \
  --target public-agencies \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --uf SC \
  --as-of 2026-07-15 \
  --max-public-agency-leads 20
```

Default do ciclo continua sendo **suppliers** (comportamento histórico preservado).

## Artefatos

Saída padrão: `output/confenge-commercial/public-agencies/`

- `public-agency-leads.csv|json`
- `public-agency-review-template.xlsx`
- `public-agency-report.html` / `public-agency-summary.md`
- `public-agency-run-result.json` (SHA-bound)
- `public-agency-*-ledger/explanations/queues/flags`
- `public-agency-manifest.json` + `public-agency-checksums.sha256`
- `dossiers/` · `commercial-kit/` · `proposals/`

## Estados honestos

- Elegibilidade: apenas `POTENTIALLY_ELIGIBLE_FOR_DIRECT_CONTRACTING`
- Somatório anual: frequentemente `DIRECT_CONTRACTING_SUM_UNKNOWN`
- COI: default `CONFLICT_CHECK_PENDING` (ausência de match ≠ ausência de conflito)
- Ready campaign: `READY_FOR_TIAGO_REVIEW_PUBLIC_AGENCY_VERTICAL` (não é ACCEPTED comercial)

## Referências

- Runbook: `docs/runbooks/public-agency-commercial-cycle.md`
- Legal: `docs/commercial/direct-contracting-compliance.md`
- Baseline/final: `docs/campaigns/confenge-public-agency-technical-services/`
