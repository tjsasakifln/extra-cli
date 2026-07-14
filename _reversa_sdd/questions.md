# Perguntas para Validação Humana — Extra Consultoria (v3.0)

> Gerado pelo Reviewer em 2026-07-13 | doc_level: completo | Base: 249340d
> **Revisão:** 5 agentes QA paralelos, 24 lacunas consolidadas
> **answer_mode:** chat

---

## Q1: Módulo `intel/` — Manter ou migrar para `root_scripts/`?

**Contexto:** As matrizes (code-spec-matrix, spec-impact-matrix) tratam `intel/` como módulo separado, mas ele NÃO existe na lista oficial de 17 módulos do `surface.json`. Os 8 scripts do pipeline legado (intel_pipeline.py, intel-collect.py, etc.) estão funcionalmente em `scripts/` (top-level), que pertence a `root_scripts/`.

**Opções:**
1. Manter `intel/` como módulo legado separado (18º módulo) — preserva documentação existente
2. Migrar conteúdo do `intel/` para `root_scripts/` — consolida, mas perde granularidade
3. Criar sub-pasta `root_scripts/intel_legacy/` — meio termo

**Impacto:** code-spec-matrix, spec-impact-matrix, 8 entradas de arquivos

---

## Q2: Módulo `lib/` — 4 submódulos críticos sem documentação

**Contexto:** A spec de `lib/` documenta 10 submódulos, mas `scripts/lib/` tem 14. Os 4 ausentes são os MAIS REFERENCIADOS por outros módulos:
- `universe.py` — usado como HARD dependency por opportunity_intel e contract_intel
- `geocode.py` — Haversine, coordenadas, distância
- `entity_hierarchy.py` — hierarquia de entidades (município→estado→federal)
- `value_semantics.py` — semântica de valores (pré-requisito para P1-01)

**Pergunta:** Devo gerar sub-specs detalhadas para esses 4 módulos agora, ou documentá-los como parte da spec existente de `lib/`?

---

## Q3: 76 arquivos Python não mapeados na code-spec-matrix

**Contexto:** A matriz lista ~135 arquivos (92% de cobertura), mas ~76 arquivos Python existem no disco sem entrada individual. Incluem crawlers ativos (ciga_ckan, mides_bigquery, doe_sc_selenium, selenium_crawler), subdiretórios inteiros (crawl/clients/, crawl/ingestion/), e scripts auxiliares.

**Pergunta:** Expandir a matriz para 100% (listando todos os ~277 .py) ou manter agrupamento por módulo (cobertura atual de ~70% dos arquivos individuais)?

---

## Q4: Diagnose e Transparência — Aprofundar agora ou depois?

**Contexto:** Ambos os módulos têm specs superficiais (2 FRs cada para 25K e 14K LOC respectivamente). São módulos periféricos — não bloqueiam os EPICs P0 prioritários.

**Pergunta:** Aprofundar a documentação desses módulos agora (custo: ~2h, 4-6 specs adicionais) ou deixar como está e priorizar apenas quando forem alvo de desenvolvimento?

---

## Q5: Baseline de commits — Normalizar?

**Contexto:** `docs/requirements.md` referencia commit `e9729e1` (2026-07-11) enquanto `docs/design.md` referencia `249340d` (2026-07-13). Outros specs da extração anterior também podem ter bases divergentes.

**Pergunta:** Devo normalizar TODOS os specs para a base `249340d` (HEAD atual) ou manter a base original de cada spec (rastreabilidade histórica)?
