# Lib — Universe (CanonicalUniverse)

> Gerado pelo Writer em 2026-07-13T16:30:00Z | doc_level: completo | Base: e9729e1

**Módulo:** `scripts/lib/universe.py` (354 linhas)
**Dependência:** HARD — opportunity_intel, contract_intel, QW-01 radar
**Referência externa:** plano-mestre §7 (P0-03 Universe Authority), Story 1.3

---

## Interface

### Dataclasses

```python
@dataclass(frozen=True)
class CanonicalEntity:
    entity_id: str              # extra-{sha256[:20]} — identidade única imutável
    seed_row: int               # linha na planilha (2-based)
    razao_social: str           # nome normalizado da seed
    cnpj8: str                  # primeiros 8 dígitos do CNPJ
    municipio: str              # município da seed
    codigo_ibge: str            # código IBGE de 7 dígitos
    natureza_juridica: str      # classificação jurídica
    latitude: float | None      # coordenada da seed (pode ser None)
    longitude: float | None     # coordenada da seed (pode ser None)
    distancia_km: float | None  # distância até Florianópolis (seed)
    radius_decision: str        # included | excluded | unresolved
    within_radius: bool | None  # True = dentro, False = fora, None = não resolvido
    decision_method: str        # seed_radius_flag | seed_distance_fallback | insufficient_seed_evidence
    identity_key: str           # cnpj8|municipio_normalizado|razao_social_normalizado
    duplicate_root: bool        # True se cnpj8 tem mais de uma entidade na seed
    suspicious_duplicate: bool  # True se identity_key não é única na seed
    db_entity_id: int | None    # ID em sc_public_entities (preenchido se conn fornecido)
    db_match_method: str | None # método de matching com o banco (ex: "cnpj8")
```

```python
@dataclass
class CanonicalUniverse:
    seed_path: str
    seed_sha256: str
    radius_km: float
    entities: list[CanonicalEntity]
    duplicate_roots: list[str]
    suspicious_duplicate_keys: list[str]

    # Propriedades derivadas
    @property
    def included(self) -> list[CanonicalEntity]                        # within_radius is True
    @property
    def excluded(self) -> list[CanonicalEntity]                         # within_radius is False
    @property
    def unresolved(self) -> list[CanonicalEntity]                       # within_radius is None
    @property
    def conservative_monitoring_population(self) -> list[CanonicalEntity]  # included + unresolved
    @property
    def resolution_coverage(self) -> float                              # 0-100%

    # Métodos
    def by_entity_id(self) -> dict[str, CanonicalEntity]
    def included_by_cnpj8(self) -> dict[str, list[CanonicalEntity]]
    def resolve_opportunity(cnpj, orgao_nome, municipio) -> tuple[CanonicalEntity | None, str]
    def summary() -> dict[str, Any]
    def to_snapshot() -> dict[str, Any]
```

### Funções Públicas

| Função | Retorno | Descrição |
|--------|---------|-----------|
| `load_canonical_universe(seed_path, radius_km, conn)` | `CanonicalUniverse` | Carrega e valida a seed como única autoridade do universo |
| `get_canonical_universe(conn, seed_path)` | `int` | Legacy: retorna `len(universe.included)` |
| `normalize_cnpj8(cnpj)` | `str` | Extrai os 8 primeiros dígitos do CNPJ |
| `normalize_identity_text(value)` | `str` | NFKD → ASCII → strip → upper |
| `sha256_file(path)` | `str` | Hash SHA-256 do arquivo (streaming) |

### Constantes

| Constante | Valor Padrão | Descrição |
|-----------|-------------|-----------|
| `DEFAULT_SEED_PATH` | `"Extra - alvos de licitação. R-0.xlsx"` | Caminho da seed canônica |
| `DEFAULT_RADIUS_KM` | `200.0` | Raio padrão de Florianópolis |
| `CANONICAL_UNIVERSE` | `1093` | Valor histórico (novo código DEVE usar `load_canonical_universe`) |

---

## Fluxo Principal

### 1. Carregamento da Seed

```
load_canonical_universe()
├── 1.1 Validar seed_path existe
├── 1.2 Abrir workbook com openpyxl (read_only, data_only)
├── 1.3 Validar sheet "Entes Públicos SC" existe
├── 1.4 Iterar rows (min_row=2), pular linhas vazias
├── 1.5 Para cada row: _parse_seed_row()
│   ├── Extrair cnpj8, razao_social, municipio, ibge, natureza
│   ├── Extrair coordenadas (latitude, longitude)
│   ├── Extrair distancia_km
│   ├── Determinar radius_decision:
│   │   ├── "SIM" na coluna raio_200km → within_radius=True
│   │   ├── "NAO" na coluna raio_200km → within_radius=False
│   │   ├── distancia_km disponível → within_radius = dist <= radius_km
│   │   └── Nenhum dos acima → within_radius=None (unresolved)
│   └── Gerar identity_key = cnpj8|municipio_normalizado|razao_normalizado
├── 1.6 Detectar duplicatas (CNPJ8 roots duplicados, identity_keys duplicadas)
├── 1.7 Opcional: load_db_entities(conn) para matching com sc_public_entities
├── 1.8 Gerar entity_id = "extra-{sha256[:20]}"
├── 1.9 Montar CanonicalUniverse
├── 1.10 _validate_universe()
│   ├── entities não vazia
│   ├── entity_ids únicos
│   ├── radius decisions cobrem todos
│   └── resolution_coverage em [0, 100]
└── 1.11 Retornar CanonicalUniverse
```

### 2. Resolução de Oportunidade

```
resolve_opportunity(cnpj, orgao_nome, municipio)
├── 2.1 Normalizar cnpj8 do candidato
├── 2.2 Buscar em included_by_cnpj8()
├── 2.3 Se 0 candidatos → "cnpj_root_not_in_target_universe"
├── 2.4 Se 1 candidato → "cnpj8_unique"
├── 2.5 Se múltiplos: cascade de matching
│   ├── (razao_social + municipio) → "cnpj8_name_municipality"
│   ├── só razao_social → "cnpj8_name"
│   ├── só municipio → "cnpj8_municipality"
│   └── nenhum → "ambiguous_duplicate_cnpj_root"
└── 2.6 Retornar (entity, reason)
```

---

## Regras de Negócio

| # | Regra | Severidade |
|---|-------|-----------|
| RN-U01 | A planilha seed é a **única autoridade** de membership no universo alvo. Flags de banco (`raio_200km`) são dado diagnóstico, nunca denominador. | 🔴 |
| RN-U02 | Entidades **sem coordenadas** não são excluídas — ficam `unresolved` (within_radius=None). O gate de 100% de resolução bloqueia análise até resolução manual. | 🔴 |
| RN-U03 | Duplicatas de CNPJ8 **não são colapsadas** automaticamente — são reportadas em `duplicate_roots` para decisão manual. | 🔴 |
| RN-U04 | Duplicatas suspeitas (identity_key duplicada) geram entity_id estável com sufixo `|occurrence=N`. | 🟡 |
| RN-U05 | O denominador conservador de monitoramento (`conservative_monitoring_population`) inclui `included + unresolved` — nunca exclui entidades não resolvidas. | 🔴 |
| RN-U06 | `CANONICAL_UNIVERSE = 1093` existe para compatibilidade retroativa. **Código novo** DEVE derivar o denominador de `load_canonical_universe()`. | 🟡 |
| RN-U07 | Matching com banco (`sc_public_entities`) é feito por CNPJ8. Entidades sem match no banco são incluídas normalmente no universo — ausência no banco não é critério de exclusão. | 🟡 |

---

## Algoritmo de Distância

No carregamento da seed, a decisão de raio segue esta prioridade:

1. **Coluna "Raio 200km?"** — Se valor normalizado começa com "SIM" ou "NAO", é autoritativo.
2. **Distância calculada na seed** — Se `distancia_km` está presente e é numérica, usa `<= radius_km`.
3. **Evidência insuficiente** — Nenhum dos anteriores → unresolved.

> A distância Haversine é calculada externamente (planilha ou geocode.py) e armazenada na seed. O módulo `universe.py` **não recalcula** distância — apenas avalia o flag e o fallback.

---

## Fórmula de Identidade

```
identity_key = cnpj8 + "|" + normalize_identity_text(municipio) + "|" + normalize_identity_text(razao_social)
entity_id = "extra-" + sha256(identity_key se única, ou identity_key + "|occurrence=N" se duplicata)[:20]
```

---

## Dependências

| Dependência | Tipo | Uso |
|------------|------|-----|
| `openpyxl` | externa | Leitura do arquivo XLSX seed |
| `hashlib` | stdlib | SHA-256 do arquivo e entity_ids |
| `re, unicodedata` | stdlib | Normalização de texto |
| `dataclasses` | stdlib | CanonicalEntity, CanonicalUniverse |
| `scripts/lib/geocode.py` | lib | 🟡 **indireta** — distância Haversine usada para gerar a seed (não chamada diretamente) |

---

## Riscos e Lacunas

| # | Risco/Lacuna | Status | Impacto |
|---|-------------|--------|---------|
| 🔴 L-U01 | **Carregador duplicado em `consulting_readiness.py`** — `load_target_universe()` é uma implementação paralela que lê a mesma seed com lógica diferente. P0-03 exige remoção. | 🔴 NÃO RESOLVIDO | Duas verdades concorrentes para o mesmo universo. Denominadores podem divergir. |
| 🟡 L-U02 | Matching com banco via `load_db_entities()` é por CNPJ8 apenas. Entidades com mesmo CNPJ8 mas municípios diferentes no banco não são desambiguadas. | 🟡 | Possível falso positivo no match. |
| 🟡 L-U03 | Seed carregada integralmente em memória (via `list(worksheet.iter_rows())`). Com ~2.085 linhas é aceitável, mas sem streaming para escalar. | 🟡 | Sem impacto atual. Monitorar se seed crescer. |
| 🟢 L-U04 | Validação de unicidade de entity_id e cobertura de decisões. | 🟢 RESOLVIDO | `_validate_universe()` garante consistência. |
| 🟡 L-U05 | `resolve_opportunity()` usa `included_by_cnpj8()` que só busca entidades `within_radius=True`. Entidades unresolved ou excluded não são candidatas a matching. | 🟡 | Correto por design — fora do universo alvo não são oportunidades. |
