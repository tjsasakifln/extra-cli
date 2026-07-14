# Lib — Entity Hierarchy (Hierarquia de Entidades)

> Gerado pelo Writer em 2026-07-13T16:30:00Z | doc_level: completo | Base: e9729e1

**Módulo:** `scripts/lib/entity_hierarchy.py` (352 linhas)
**Dependência:** HARD — entity matching (coverage por herança)
**Referência externa:** plano-mestre §3 (cobertura por ente)

---

## Interface

### Mapeamento de Relacionamento

```python
RELATIONSHIP_MAP: dict[str, str] = {
    "Órgão Público do Poder Executivo Municipal": "prefeitura",
    "Administração Municipal": "prefeitura",
    "Órgão Público do Poder Legislativo Municipal": "camara",
    "Fundação Pública de Direito Público Municipal": "fundacao",
    "Autarquia Municipal": "autarquia",
    "Serviço Autônomo Municipal": "autarquia",
    "Fundo Público da Administração Direta Municipal": "fundo",
    "Fundo Municipal": "fundo",
    "Conselho Municipal": "conselho",
}

HIERARCHICAL_NATUREZAS: frozenset[str]  # frozenset das chaves de RELATIONSHIP_MAP
```

### Funções Públicas

| Função | Retorno | Descrição |
|--------|---------|-----------|
| `build_entity_hierarchy(conn)` | `dict[str, int]` | Constrói hierarquia de entidades municipais, ligando secretarias/fundações/autarquias às suas prefeituras |
| `resolve_entity_coverage_cascade(entity_id, conn)` | `dict \| None` | Resolve cobertura com fallback hierárquico: tenta direta primeiro, depois hierarquia |
| `apply_hierarchical_coverage(conn, source)` | `dict[str, int]` | Aplica cobertura hierárquica para todas as entidades na entity_hierarchy |

### Estruturas de Retorno

**build_entity_hierarchy()** — dicionário de estatísticas:

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `inserted` | int | Linhas inseridas em entity_hierarchy |
| `skipped_no_ibge` | int | Entidades sem codigo_ibge |
| `skipped_no_prefeitura` | int | Entidades cujo codigo_ibge não tem prefeitura |
| `skipped_inactive` | int | Entidades com is_active = FALSE |
| `skipped_already_covered` | int | Entidades já com cobertura direta |
| `skipped_camara_with_bids` | int | Câmaras que já têm licitações próprias |
| `errors` | int | Erros de processamento |

**resolve_entity_coverage_cascade()** — dicionário de cobertura ou `None`:

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `is_covered` | bool | TRUE se cobertura encontrada |
| `match_method` | str | "direct" ou "hierarchical" |
| `source_entity_id` | int | ID da entidade que provê cobertura |
| `relationship` | str | (hierárquico apenas) "prefeitura", "fundacao", etc. |

**apply_hierarchical_coverage()** — dicionário de estatísticas:

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `updated` | int | Coberturas hierárquicas aplicadas |
| `skipped_parent_uncovered` | int | Pais sem cobertura |
| `errors` | int | Erros de processamento |

---

## Fluxo Principal

### 1. Construção da Hierarquia

```
build_entity_hierarchy(conn)
├── Passo 1: Carregar prefeituras (natureza_juridica = 'Município')
│   ├── SELECT id, cnpj_8, codigo_ibge, razao_social, municipio
│   │   FROM sc_public_entities WHERE natureza_juridica = 'Município'
│   │   AND is_active = TRUE AND codigo_ibge IS NOT NULL
│   └── Indexar por codigo_ibge (1:1 — 295 municípios esperados)
│
├── Passo 2: Carregar entidades agrupáveis
│   ├── SELECT id, razao_social, natureza_juridica, cnpj_8, codigo_ibge, is_active
│   │   FROM sc_public_entities
│   │   WHERE natureza_juridica != 'Município'
│   │     AND natureza_juridica = ANY(HIERARCHICAL_NATUREZAS)
│   └── Filtro: apenas naturezas que TÊM mapeamento hierárquico
│
├── Passo 3: Para cada entidade agrupável:
│   ├── 3.1 Pular se inativa (is_active = FALSE)
│   ├── 3.2 Pular se sem codigo_ibge
│   ├── 3.3 Pular se já tem cobertura direta não-hierárquica
│   ├── 3.4 [AC8] Pular câmaras com bids próprios
│   │   └── SELECT COUNT(*) FROM pncp_raw_bids WHERE LEFT(orgao_cnpj, 8) = cnpj_8
│   ├── 3.5 Encontrar prefeitura por codigo_ibge
│   ├── 3.6 Pular se codigo_ibge não tem prefeitura
│   └── 3.7 INSERT INTO entity_hierarchy (entity_id, parent_entity_id, relationship, match_confidence)
│
├── COMMIT no final
└── Retornar stats
```

### 2. Resolução de Cobertura com Cascade

```
resolve_entity_coverage_cascade(entity_id, conn)
├── Nível 1: Cobertura direta
│   ├── SELECT is_covered, match_method, source FROM entity_coverage WHERE entity_id = ?
│   └── Se is_covered = TRUE → retornar match direto
│
├── Nível 2: Cobertura via hierarquia
│   ├── SELECT h.parent_entity_id, h.relationship, ec.is_covered
│   │   FROM entity_hierarchy h
│   │   LEFT JOIN entity_coverage ec ON ec.entity_id = h.parent_entity_id
│   │   WHERE h.entity_id = ?
│   └── Se parent_covered = TRUE → retornar cobertura hierárquica
│
└── Se nenhum nível → retornar None
```

### 3. Aplicação em Massa de Cobertura Hierárquica

```
apply_hierarchical_coverage(conn, source="pncp")
├── Buscar entidades em entity_hierarchy cujo parent tem cobertura
│   mas a entidade filha NÃO tem cobertura (ou tem hierarchical apenas)
├── Para cada entidade:
│   └── INSERT INTO entity_coverage (is_covered=TRUE, match_method='hierarchical')
├── COMMIT
└── Retornar stats
```

---

## Regras de Negócio

| # | Regra | Severidade |
|---|-------|-----------|
| RN-H01 | **Prefeitura é o pai**: toda entidade hierárquica municipal é filha da prefeitura do mesmo `codigo_ibge`. | 🔴 |
| RN-H02 | **Cobertura direta prevalece**: entidades já cobertas por matching direto (não hierárquico) não são sobrescritas. | 🔴 |
| RN-H03 | **Câmaras com bids próprios** mantêm cobertura direta (AC8). Câmaras sem bids são agrupadas à prefeitura. | 🔴 |
| RN-H04 | **Entidades inativas** (`is_active = FALSE`) são puladas — não entram na hierarquia. | 🟡 |
| RN-H05 | **Entidades sem `codigo_ibge`** não podem ser hierarquizadas — sem geografia não há prefeitura pai. | 🟡 |
| RN-H06 | **Dois `Município` para o mesmo IBGE** é condição de erro — log warning, a última prevalece. | 🟡 |
| RN-H07 | **Hierarquia é 1 nível** (filho → prefeitura). Não há suporte para hierarquia multi-nível neste módulo. | 🟢 |
| RN-H08 | **Match confidence fixo em `'hierarchical'`**. Não há score probabilístico — a relação é determinística por natureza jurídica. | 🟢 |

---

## Dependências

| Dependência | Tipo | Uso |
|------------|------|-----|
| `config.logging_config` | interno | Logger estruturado |
| `sc_public_entities` | banco | Tabela de entidades públicas |
| `entity_hierarchy` | banco | Tabela de hierarquia (INSERT/UPSERT) |
| `entity_coverage` | banco | Tabela de cobertura por ente |

---

## Riscos e Lacunas

| # | Risco/Lacuna | Status | Impacto |
|---|-------------|--------|---------|
| 🟡 L-H01 | **Mapeamento de naturezas jurídicas** pode estar incompleto. Novas naturezas jurídicas municipais não mapeadas são silenciosamente ignoradas (não entram no SELECT de entidades agrupáveis). | 🟡 | Revisão periódica do RELATIONSHIP_MAP necessária. |
| 🟢 L-H02 | Upsert na entity_hierarchy (`ON CONFLICT DO UPDATE`) já implementado. | 🟢 RESOLVIDO | Re-execução é idempotente. |
| 🟡 L-H03 | **Cobertura hierárquica não reavalia automaticamente** quando a cobertura do pai muda. `apply_hierarchical_coverage()` precisa ser chamada explicitamente. | 🟡 | Risco de cobertura hierárquica ficar dessincronizada. |
| 🟢 L-H04 | Rollback automático em caso de erro no build ou apply. | 🟢 RESOLVIDO | Transação não deixa estado corrompido. |
| 🟡 L-H05 | **Cascade coverage resolve apenas 1 nível** (filho → pai). Entidades cujo pai é outra entidade hierárquica (ex: fundação de autarquia) não são resolvidas. | 🟡 | Fora do escopo atual. |
