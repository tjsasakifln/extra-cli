# ADR-019 — Entity Source Registry Canonical

| Campo | Valor |
|-------|-------|
| **Status** | Accepted |
| **Data** | 2026-07-17 |
| **Decisores** | PM (Morgan), Architect, Data Engineer |
| **Epic** | E2 Source registry & discovery |
| **Relacionados** | ADR-018, ADR-021, L1 source capability registry |

---

## Contexto

Existe registry de **fontes** (`scripts/crawl/registry.py`, 11 sources, capabilities tipadas). **Não** existe registry canônico **entidade → fontes aplicáveis → método de aquisição → status**.

Sem isso:

- `operational_source_coverage` (meta 95%) é incalculável de forma honesta;
- discovery (CIGA, portais, PNCP org) não tem onde gravar resultado;
- crawls “globais” não provam cobertura do universo 1.093.

L1 (2026-07-16) classificou matriz fonte×ente×capability como **PARTIAL/unknown**.

## Decisão

Estabelecer o **Entity Source Registry (ESR)** como source of truth operacional:

### Modelo lógico (mínimo)

```
EntitySourceBinding
  entity_id          # FK sc_public_entities
  source_id          # FK source registry (pncp, sc_compras, ciga_dom, ...)
  applicability      # applicable | not_applicable | unknown
  acquisition_method # api | html | pdf | ckan | manual | none
  portal_url         # opcional
  external_org_id    # id na fonte (CNPJ, código municipal, …)
  confidence         # 0-1 ou enum high|medium|low
  evidence_ref       # path/run_id que descobriu o binding
  last_verified_at
  last_success_at    # denormalizado do evidence ledger (opcional)
  status             # active | blocked | deprecated
  notes
```

### Regras

1. **Toda entidade do universo 1.093** deve ter ≥1 linha ESR (mesmo que `unknown` / `not_applicable` explícito).
2. **Unknown ≠ covered.** Só `applicable` + evidência de sucesso recente conta para M2 (ADR-018).
3. Discovery jobs (E2.S2) **só escrevem ESR + raw evidence**, não “inventam” coverage %.
4. Source-level registry (`registry.py`) permanece para capabilities/SLA da fonte; ESR compõe com ele.
5. Bloqueios de credencial (`SOURCE_BLOCKERS`) refletem em bindings `blocked` com motivo.
6. Export machine-readable: `output/registry/entity-source-registry.json` (não commitado — ADR-020) + snapshot carimbado em docs/ops quando gate de release.

### Bootstrap 1.093

- Seed: entidades ativas 200 km.
- Inferência inicial: PNCP por CNPJ quando match; SC Compras/CIGA quando presente em artefatos de sessão; resto `unknown`.
- Meta E2: 100% entidades com linha; maximizar `applicable` verificado.

## Alternativas rejeitadas

| Alternativa | Motivo |
|-------------|--------|
| Só evidence ledger sem applicability | Não distingue “não monitorado” de “monitorado vazio” |
| Planilha manual única | Não escala; sem proveniência |
| Assumir PNCP cobre 100% do universo | Falso (adesão voluntária / match gaps) |

## Consequências

- Desbloqueia cálculo de M2 e priorização de discovery.
- Stories E2.S1 (schema+load 1093) e E2.S2 (discovery pncp/ciga) são path crítico.
- Crawlers passam a poder rodar **por binding** (target set), não só full-scan cego.

## Critérios de aceite

- [ ] 1.093 entidades com ≥1 binding
- [ ] Query: % applicable vs unknown vs blocked
- [ ] Integração com calculadora ADR-018 M2
- [ ] Testes de integridade referencial entity_id/source_id

## Referências

- `docs/baseline/l1-source-capability-registry.md`
- `scripts/crawl/registry.py`
- Stories `story-B2G-E2.S1.md`, `story-B2G-E2.S2.md`
