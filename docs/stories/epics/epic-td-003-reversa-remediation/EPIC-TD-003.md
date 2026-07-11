# EPIC: Reversa Remediation — Codebase Cleanup from Reversa Analysis

**Epic ID:** EPIC-TD-003
**Criado por:** @sm (River)
**Data:** 2026-07-11
**Status:** Draft

---

## Objetivo

Resolver os problemas estruturais identificados pela analise Reversa (commit e9729e1) que nao estavam cobertos pelas stories existentes de EPIC-TD-001 e EPIC-TD-002. O Reversa identificou 3 categorias de debitos tecnicos que requerem intervencao: (1) duplicacao sistematica de scripts (10 pares kebab vs snake_case), (2) acoplamento fragil via subprocess.run no pipeline de inteligencia, e (3) dependencia de producao incorreta (psycopg2-binary).

## Escopo

### Incluido

- Fase 1: Deduplicacao — Verificacao e remocao de 10 pares de scripts duplicados kebab/snake_case
- Fase 2: Refatoracao — Substituicao de subprocess.run por imports diretos em intel_pipeline.py
- Fase 3: Dependencias — Correcao de psycopg2-binary para psycopg2 em requirements.txt
- Fase 4: Module Import Fix — Criacao de stubs para packages clients/, ingestion/, supabase_client
- Fase 5: PNCP API v3 Migration — Correcao de URL base, pagination, schema response, escopo de crawl

### Excluido

- Renomeacao de modulos com hifen (ja coberto por EPIC-TD-002 / TD-7.1)
- Correcao de outros alertas do Reversa (httpx sem version pin, playwright comentado)
- Refatoracao de codigo duplicado em crawlers (ja coberto por TD-3.2)
- Novas funcionalidades ou features
- Migracao de outros adaptadores de API (DOM-SC, PCP, ComprasGov) — podem ser epics separados

## Fases

| Fase | Nome | Horas | Custo | Stories |
|------|------|-------|-------|---------|
| 1 | Deduplicacao | 8h | R$ 1.200 | 1 story |
| 2 | Refatoracao subprocess.run | 12h | R$ 1.800 | 1 story |
| 3 | Dependencias | 2h | R$ 300 | 1 story |
| 4 | Module Import Fix | 16h | R$ 2.400 | 1 story |
| 5 | PNCP API v3 Migration | 4h | R$ 600 | 1 story |
| **TOTAL** | | **42h** | **R$ 6.300** | **4 stories** |

## Criterios de Sucesso

- [ ] Zero scripts snake_case duplicados (6 pares identicos removidos)
- [ ] 4 pares divergentes documentados e preservados ate decisao humana
- [ ] intel_pipeline.py importa funcoes diretamente em vez de subprocess.run
- [ ] requirements.txt usa psycopg2 em vez de psycopg2-binary
- [ ] Todos os 127 arquivos Python podem ser importados sem ImportError
- [ ] Crawler PNCP funciona com API v3 (base URL, pagination, schema response)
- [ ] Coverage PNCP >= 80% para entidades SC 200km apos 3 runs incrementais
- [ ] Entity matching executa com dados PNCP reais pela primeira vez
- [ ] Todos os testes existentes continuam passando apos refatoracao

## Dependencias

- Analise Reversa: `_reversa_sdd/inventory.md`, `_reversa_sdd/code-analysis.md`, `_reversa_sdd/dependencies.md`
- EPIC-TD-002 / TD-7.1: renomeacao de modulos com hifen pode afetar este epic
- Confirmacao humana para os 4 pares com diferencas

## Story List

| Story ID | Nome | Fase | Horas | Debitos Ref. |
|----------|------|------|-------|-------------|
| TD-8.1 | Reversa Cleanup — Duplicacao, subprocess, psycopg2 | 1-3 | 22h | Reversa: duplicated scripts, subprocess.run, psycopg2-binary |
| TD-8.2 | Fix Broken Module Imports — Crawl, Ingestion, Intel Pipeline | 4 | 16h | Auditoria de imports: 37/127 arquivos com imports quebrados |
| TD-8.3 | Fix PNCP API v3 Migration — Crawler Parameter, Response Schema, Coverage | 5 | 4h | Swagger UI testing: API v2->v3 migration, coverage drop ~80%->0% |

## Riscos

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| Remocao de script snake_case quebra import em intel_pipeline.py | MEDIA | CRITICO | Verificar TODAS as referencias de import antes de deletar |
| intel-collect.py e intel_collect.py tem diferencas reais de funcionalidade (429 handling) | ALTA | CRITICO | Nao deletar — submeter a revisao humana |
| subprocess.run refactoring introduz regressao no pipeline | MEDIA | ALTO | Manter funcao _run_script como fallback durante transicao |
| psycopg2 compilado requer build tools no servidor | MEDIA | MEDIO | Documentar requisitos de instalacao |
| API v3 muda novamente sem aviso (ja e a 3a versao) | MEDIA | ALTO | Adicionar teste de smoke contra API ao vivo no CI; monitorar changelog PNCP |
| Entity matching falha porque nunca foi testado com dados reais | ALTA | ALTO | Executar matching manualmente apos primeiro crawl bem-sucedido, ajustar thresholds |
| Crawl scope expandido (30 dias, 7 modalidades) causa 429 rate-limit | ALTA | MEDIO | Respeitar delay entre requests, paginacao incremental, fallback para retry

---

## Documentos Referenciados

- Inventario Reversa: `_reversa_sdd/inventory.md`
- Code Analysis: `_reversa_sdd/code-analysis.md`
- Dependencias: `_reversa_sdd/dependencies.md`
- Gaps: `_reversa_sdd/gaps.md`

---

**Criado por:** @sm (River)
**Data:** 2026-07-11
