---
story_id: B2G-E4.S1
title: "Workspace CLI: today / opportunities / coverage"
status: InProgress
priority: P0
risk_level: STANDARD
effort: L
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E4
depends_on: [B2G-E1.S1]
blocks: [B2G-E4.S2, B2G-E4.S3, B2G-E5.S2]
adr: [ADR-017, ADR-018]
---

# Story B2G-E4.S1: Workspace CLI facade (today / opportunities / coverage)

## Contexto

Tiago opera N CLIs. ADR-017 define facade `workspace` como UX primária. Peças existem em `opportunity_intel`, coverage session artifacts, source-health.

## Valor de negócio

Rotina diária &lt;15 min; caminho único para dual-metric e oportunidades.

## Escopo

**IN:** Entry point `workspace` (ou `python -m scripts.workspace`) com subcomandos `today`, `opportunities`, `coverage`; delegação aos módulos existentes; `--format text|json`; dual headline coverage.

**OUT:** Feedback humano (E5.S3); scheduler (E3); UI web.

## Acceptance Criteria

1. **AC1 — today**  
   **Given** ambiente com DB/artefatos configurados,  
   **When** `workspace today`,  
   **Then** imprime: as_of, source-health resumido, top oportunidades (ou contagem), dual coverage M1 (+ M2 se disponível).

2. **AC2 — opportunities**  
   **Given** dados de oportunidades,  
   **When** `workspace opportunities --status open --limit 20`,  
   **Then** lista id, órgão, prazo, score/flag, fonte; exit 0 se dados ok.

3. **AC3 — coverage**  
   **Given** contrato ADR-018,  
   **When** `workspace coverage`,  
   **Then** exibe `entities_with_recent_commercial_signal` e slot `operational_source_coverage` (valor ou unmeasured).

4. **AC4 — facade**  
   **Given** implementação,  
   **When** inspeciona código,  
   **Then** não reimplementa ranking/crawl; orquestra módulos existentes.

5. **AC5 — help**  
   **Given** CLI,  
   **When** `--help`,  
   **Then** documenta os 3 subcomandos e exit codes (0/1/2).

## Fontes de dados

opportunity_intel store/DB; coverage calculator; registry health; session baseline se fallback documentado.

## Dependências

B2G-E1.S1 (nomes métricas). Ideal E1.S2 para M2 real (senão unmeasured).

## Riscos

| Risco | Mitigação |
|-------|-----------|
| Sem DB | Mensagem clara exit 1/2; não crash traceback cru |
| Dados stale | E4.S2 hard-gate; aqui ao menos mostrar as_of |

## Testes

- CLI tests com monkeypatch/fixtures
- Snapshot text mínimo opcional
- Garante dual keys no JSON coverage

## Evidência

- Saída `--format json` em output/ (gitignore) durante demo
- pytest CLI

## Definition of Done

- [ ] AC1–5
- [ ] README/runbook one-liner para Tiago
- [ ] ADR-017 link

## Comandos de validação

```bash
pytest tests/ -k "workspace" -v
# Pós-impl:
# python -m scripts.workspace today
# python -m scripts.workspace opportunities --status open --limit 20
# python -m scripts.workspace coverage --format json
# Alternativa opportunity_intel enquanto facade sobe:
python scripts/opportunity_intel/cli.py list --status open --limit 20
python scripts/opportunity_intel/cli.py coverage
python scripts/opportunity_intel/cli.py source-health
```

## Comando operacional Tiago (alvo)

```bash
workspace today
workspace opportunities
workspace coverage
```

## File List (dev)

- (a preencher)

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | InProgress — agents de implementação |
