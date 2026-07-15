# CM-13 — Deduplicação Multicanal e Aliases de Compradores

**Epic:** EPIC-COVERAGE-MAX-200KM | **Onda:** 2 — Correções de Alto Retorno
**Risk:** HIGH-RISK | **Status:** Ready
**Asymmetric Score:** 92 | **Recall gain estimado:** +6% (via redução de falsos misses)

---

## Problema Econômico

O sistema atual sofre duas falhas de matching que causam perda de oportunidades:

1. **Secretarias publicam no CNPJ da prefeitura.** Uma licitação da "Secretaria
   Municipal de Educação de Joinville" é publicada com o CNPJ da Prefeitura de
   Joinville, mas a planilha lista a secretaria com CNPJ próprio (8 dígitos
   diferentes). O matching por CNPJ falha → recall = 0% para 179 secretarias.

2. **Sem dedup cross-source.** Um edital publicado no PNCP e no portal da
   transparência municipal gera 2 registros distintos. O usuário vê duplicação
   e perde confiança. A consolidação manual é inviável em escala.

3. **CNPJ de fundo vs prefeitura.** Fundos municipais (FMAS, FMS, FME) têm
   CNPJs próprios mas publicam compras no CNPJ da prefeitura. Mesmo problema
   das secretarias.

**Impacto:** 179 secretarias + 61 autarquias + dezenas de fundos = ~280 entes
com recall 0% devido a falha de matching, não a falta de dados.

## Hipótese

Uma tabela de hierarquia de CNPJs (ente subordinate → ente publicante) permite
resolver o matching sem alterar o banco de licitações. A dedup cross-source com
hash canônico multi-fonte elimina duplicação sem depender de IDs externos.

---

## Escopo (IN)

1. Tabela `entity_aliases`: mapeia CNPJ subordinate → CNPJ publicante
2. Seed inicial: secretarias → prefeitura do mesmo município (via IBGE)
3. Seed inicial: fundos municipais → prefeitura
4. Detecção automática: entes mesmo município, mesma natureza → agrupar
5. Nova função `resolve_publishing_cnpj(cnpj_8)` → CNPJ raiz publicante
6. Hash canônico cross-source: `sha256(modalidade + objeto_normalizado + orgao_raiz + data_publicacao + valor_total)`
7. Tabela `dedup_cross_source` ou view materializada
8. Atualizar reconciliation para usar `resolve_publishing_cnpj()`

## Fora de Escopo (OUT)

- Machine learning para matching fuzzy (determinístico apenas)
- Alteração da chave primária de tabelas existentes
- Matching de CNPJs entre estados diferentes
- Desambiguação manual de aliases (postergado para interface admin)

---

## Arquivos Prováveis

| Arquivo | Ação |
|---------|------|
| `db/migrations/045_entity_aliases.sql` | NOVO — tabela entity_aliases |
| `db/seed/002_entity_aliases.sql` | NOVO — seed secretarias→prefeituras |
| `scripts/lib/entity_resolver.py` | NOVO — resolve_publishing_cnpj() |
| `scripts/opportunity_intel/reconciliation.py` | Atualizar matching |
| `scripts/crawl/common.py` | Novo generate_cross_source_hash() |
| `scripts/coverage/manifest.py` | Atualizar para usar resolver |
| `scripts/lib/dedup.py` | NOVO — cross-source dedup engine |

## Dependências

- CM-02 (importador da planilha)
- CM-03 (reconciliação golden dataset)
- PostgreSQL acessível

---

## Critérios de Aceite

### AC-1: Secretaria resolve para prefeitura
**Given** secretaria CNPJ "62761279" em Joinville
**When** chamo `resolve_publishing_cnpj("62761279")`
**Then** retorna CNPJ da Prefeitura de Joinville ("82926551")

### AC-2: Matching de oportunidades para secretarias
**Given** edital publicado pela Prefeitura de Joinville (CNPJ "82926551...")
**When** reconciliação processa "Secretaria Municipal de Educação de Joinville"
**Then** opportunity é matched (FOUND_EXACT) — não MISSED

### AC-3: Dedup cross-source
**Given** mesmo edital no PNCP (source=pncp) e portal transparência (source=transparencia)
**When** executo dedup
**Then** sistema identifica como mesmo edital e consolida (mantém 1 registro canônico)

### AC-4: Seed cobre todas as secretarias no raio
**Given** 179 secretarias municipais no raio de 200km
**When** executo seed de aliases
**Then** 100% das secretarias têm alias para prefeitura do mesmo IBGE

### AC-5: Hash determinístico
**Given** mesmo edital com formatação ligeiramente diferente nos campos
**When** gero hash cross-source
**Then** mesmo hash (campos normalizados antes do hash)

### AC-6: Sem falsos positivos
**Given** dois editais diferentes da mesma prefeitura, mesma modalidade, mesmo mês
**When** gero hash cross-source
**Then** hashes diferentes (objeto_normalizado e valor_total diferenciam)

---

## Testes

1. **Unit:** `resolve_publishing_cnpj()` — secretaria → prefeitura
2. **Unit:** `resolve_publishing_cnpj()` — fundo → prefeitura
3. **Unit:** `resolve_publishing_cnpj()` — prefeitura → ela mesma (idempotente)
4. **Unit:** `generate_cross_source_hash()` — determinístico com campos normalizados
5. **Unit:** `generate_cross_source_hash()` — diferencia editais distintos
6. **Integration:** seed cria aliases para todas as secretarias no raio
7. **Integration:** reconciliação re-classifica secretarias de MISSED → FOUND
8. **Integration:** dedup cross-source em fixtures reais

## Evidências Obrigatórias

- [ ] `SELECT count(*) FROM entity_aliases` > 179 (todas as secretarias)
- [ ] Recall de secretarias executivas municipais: 0% → >50%
- [ ] Hash cross-source gera mesmo valor para mesmo edital de fontes diferentes
- [ ] Nenhum falso positivo em 100 exemplos de teste

---

## Rollback

```sql
DROP TABLE IF EXISTS entity_aliases;
-- Reexecutar reconciliação sem resolver
```

## Comando de Validação

```bash
# Criar aliases
python db/seed/002_entity_aliases.py

# Verificar resolução
python -c "
from scripts.lib.entity_resolver import resolve_publishing_cnpj
# Secretaria de Educação de Joinville → Prefeitura de Joinville
print(resolve_publishing_cnpj('62761279'))
"

# Reexecutar reconciliação com aliases
python scripts/opportunity_intel/cli.py reconcile --targets config/target_entities_200km.csv
# Verificar: recall de secretarias > 0%
```

---

## Asymmetric Score Detalhado

```
Recall Gain:          6% (afeta ~280 entes com recall 0%)
Entity Importance:    6/10 (secretarias são compradoras indiretas)
Opportunity Value:    7/10 (desbloqueia dados já existentes no banco)
Failure Probability:  10/10 (falha CERTA — 0% recall comprovado)
Reuse Factor:         9/10 (resolver beneficia todas as fontes e reconciliações)
Effort:               4/10 (tabela simples + seed determinístico)
Operational Risk:     2/10 (não altera tabelas de produção, só adiciona)
                    ------
Asymmetric Score:    ~92
```

---

*CM-13 — AIOX Master Orion, 2026-07-15*
