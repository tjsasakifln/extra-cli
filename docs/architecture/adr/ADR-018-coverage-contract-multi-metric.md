# ADR-018 — Coverage Contract Multi-Metric

| Campo | Valor |
|-------|-------|
| **Status** | Accepted |
| **Data** | 2026-07-17 |
| **Decisores** | PM (Morgan), Architect, QA |
| **Epic** | E1 Operational coverage 95% |
| **Baseline** | commercial signal **116/1093 (10,61%)** — session 2026-07-17 |

---

## Contexto

Histórico de métricas conflitantes (39,4%, 100%, 265%, 4,76%, 52/1093, 116/1093, 133 combined) destruiu confiança. A sessão 2026-07-17 estabilizou o headline comercial em **116/1093** com `list_identity_ok`, mas o **alvo de proposta (95%)** refere-se a **cobertura operacional de fontes**, não a “órgãos com oportunidade comercial recente”.

Confundir as duas é **overclaim comercial**.

## Decisão

Adotar um **contrato multi-métrica** obrigatório. Todo relatório, CLI, DoD e material comercial deve expor no mínimo:

### Métricas canônicas

| ID | Nome | Definição | Alvo proposta |
|----|------|-----------|---------------|
| **M1** | `entities_with_recent_commercial_signal` | Entidades do universo 1.093 com ≥1 oportunidade OPEN/UPCOMING/RECENT matched (não RESULT genérico, não só ato oficial) | **Não é 95%** — cresce com mercado + recall |
| **M2** | `operational_source_coverage` | Entidades com ≥1 fonte **aplicável** e evidência `success_*` dentro do SLA da fonte | **≥ 95%** |
| **M3** | `monitoring_evidence_coverage` | Entidades com observation no evidence ledger (pode ser monitoring-only) | Informativo |
| **M4** | `bid_presence_coverage` | Entidades com ≥1 bid/contrato persistido | Informativo (≠ monitoring) |
| **M5** | `source_health` | Por fonte: success rate, last_success, blocker | SLA operacional |

### Regras inegociáveis

1. **Denominador fixo:** 1.093 = `sc_public_entities` `is_active AND raio_200km`. Proibido alterar denominador para “melhorar %”.
2. **Rename:** `commercial_opportunity_any` → **`entities_with_recent_commercial_signal`** em código, docs e JSON novos.
3. **Headline dual:** UI/CLI sempre mostra M1 e M2 lado a lado.
4. **Proibido** reportar M3 ou M4 como “cobertura 95% da proposta”.
5. Todo JSON de métrica inclui: `as_of`, `git_sha` (se aplicável), `numerator`, `denominator`, `formula`, `source_artifacts[]`.
6. **List identity:** `|covered| + |uncovered| = denominator` e `|covered| = numerator`.
7. Artefatos stale sem `as_of` válido → status `UNVERIFIED`, nunca % “bonito”.

### Rename de campos (migração)

| Legado | Canônico |
|--------|----------|
| `commercial_opportunity_any` | `entities_with_recent_commercial_signal` |
| `covered_200km` (ambíguo) | deprecar; mapear para M1 ou M4 conforme definição do artefato |
| `editais_crude_pct` | manter como M4-like histórico com label explícito |

## Alternativas rejeitadas

| Alternativa | Motivo |
|-------------|--------|
| Uma única métrica “coverage” | Semantic overload comprovado |
| Meta 95% em sinal comercial | Impossível e desonesto (depende do mercado) |
| Denominador flutuante (só “com dados”) | Infla artificialmente |

## Consequências

- E1 implementa calculadora + testes de identidade.
- Materiais comerciais e PRD delta alinhados.
- QA adversarial falha build se headline único sem dual-metric.

## Critérios de aceite

- [ ] Calculadora emite M1–M5 com fórmulas testadas
- [ ] `workspace coverage` e manifests usam nomes canônicos
- [ ] Testes: list identity 116=116 no fixture da sessão; denominador 1093 imutável
- [ ] Documentação PRD delta referencia este ADR

## Referências

- `docs/ops/session-2026-07-17/coverage_canonical.json`
- `docs/coverage-truth/` (histórico de inconsistências)
- Story `story-B2G-E1.S1.md`
