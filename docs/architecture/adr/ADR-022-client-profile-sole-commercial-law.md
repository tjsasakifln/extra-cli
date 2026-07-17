# ADR-022 — Client Profile as Sole Commercial Law for Ranking

| Campo | Valor |
|-------|-------|
| **Status** | Accepted |
| **Data** | 2026-07-17 |
| **Decisores** | PM (Morgan), Architect |
| **Epic** | E5 Opportunities & triage |
| **Relacionados** | ADR-017, QW-01, sectors_config, opportunity ranking |

---

## Contexto

Ranking e triagem de oportunidades hoje dependem de:

- keywords / setores em configs dispersos;
- regras do radar QW-01;
- scores opportunity_intel;
- eventuais prompts LLM no intel_pipeline legado;

sem um **único perfil comercial versionado** que diga o que é “bom para a Extra/CONFENGE”.

Resultado: scores não explicáveis de ponta a ponta; risco de GO para objeto fora do mandato; impossibilidade de feedback humano estruturado.

## Decisão

O **Client Profile** é a **única lei comercial** para ranking, triagem e filtros default do workspace.

### Conteúdo mínimo do profile (versionado)

```yaml
profile_id: extra-construtora-sc-200km
version: 1
client_name: Extra Construtora
geography:
  uf: SC
  radius_km: 200
  universe_ref: sc_public_entities.raio_200km
sectors:           # CNAE / keywords / objetos preferidos
  include: [...]
  exclude: [...]
modalities:
  prefer: [...]
  avoid: [...]
value_band:
  min_brl: ...
  max_brl: ...
hard_exclusions:   # sempre NO-GO
  - physical_obra_execution_tracking  # fora de escopo plataforma
  - ...
scoring_weights:   # dimensões explicáveis
  fit_sector: 0.3
  fit_geo: 0.2
  value_fit: 0.2
  deadline_urgency: 0.15
  competition_signal: 0.15
feedback_policy:
  store_human_labels: true
  human_label_overrides_model: true
```

### Regras

1. **Um profile ativo por workspace session** (default Extra). Multi-cliente futuro = N profiles, nunca N leis hard-coded.
2. Ranking, `explain`, e filtros `workspace opportunities` **leem só o profile** (+ dados da oportunidade). Proibido segundo caminho silencioso de keywords.
3. **Human feedback** (GO/NO-GO/WATCH do Tiago) grava label ligado a `profile_version` + `opportunity_id`; labels humanas **sobrescrevem** score automático na UI/lista operacional.
4. Mudança de weights = bump de `version`; relatórios citam `profile_id@version`.
5. O que está fora do profile (ex.: obra física) **não** entra como feature de ranking “criativa”.

## Alternativas rejeitadas

| Alternativa | Motivo |
|-------------|--------|
| LLM como lei | Não auditável; viola No Invention sem ground truth |
| Múltiplos scores “secretos” por módulo | Inexplicável para cliente |
| Hard-code Extra em cada regra | Impede evolução e testes |

## Consequências

- E5 implementa loader + validação de profile.
- E4 workspace exige profile resolvido.
- QA verifica: oportunidade excluded por hard_exclusion nunca aparece como GO.
- Migração: consolidar `sectors_config.yaml` + regras radar no profile v1 (ADAPT, não inventar setores novos).

## Critérios de aceite

- [ ] Profile YAML/JSON versionado em config (git)
- [ ] `explain` cita dimensões e profile version
- [ ] Feedback humano persistido e refletido em `workspace opportunities`
- [ ] Testes: exclusion list → NO-GO

## Referências

- `config/sectors_config.yaml`
- `docs/decisions/qw-01-canonical-opportunity-pipeline.md`
- `docs/prd/capability-matrix-b2g-proposta.md` (C2, C7, C10)
- Stories E5.*
