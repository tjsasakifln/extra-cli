# PE-L1-02 — Reconciliação do universo canônico (evidência real)

**Story:** PE-L1-02  
**Executado em:** 2026-07-16T22:11:51Z  
**Commit HEAD:** `1f7aa7c`  
**Módulo:** `scripts/lib/universe.py`  
**Autoridade:** planilha seed — **não** flags de raio no DB

## Veredito

| Check | Status | Valor |
|-------|--------|-------|
| Planilha encontrada | **PASS** | `Extra - alvos de licitação. R-0.xlsx` (156 599 bytes) |
| Sheet obrigatória | **PASS** | `Entes Públicos SC` |
| Load via `load_canonical_universe()` | **PASS** | sem exception |
| Total no raio (within_radius) | **PASS** | **1093** |
| Match constante legada `CANONICAL_UNIVERSE` | **PASS** | `1093 == 1093` |
| Resolução 100% das linhas seed | **PASS** | unresolved = 0 |
| Import no DB (`target_universe_entities`) | **NÃO FEITO / gap** | count = **0** em `pncp_datalake` |
| Match DB entities (`db_matched_rows`) | **0** nesta execução | `conn=None` (só planilha) |
| Cobertura 95% de bids/oportunidades | **NÃO MEDIDO** | fora do escopo L1.2; **não inventado** |

## Evidência programática

```text
SEED_PATH /mnt/d/extra consultoria/Extra - alvos de licitação. R-0.xlsx
SEED_EXISTS True
SEED_SIZE 156599
SEED_SHA256 d65f272812cf8dc95f3ca78c5db9a2fb2a39a759e5633eb3fb91891ad10a5486
LEGACY_CONSTANT_CANONICAL_UNIVERSE 1093
```

### `CanonicalUniverse.summary()` (JSON real)

```json
{
  "seed_path": "/mnt/d/extra consultoria/Extra - alvos de licitação. R-0.xlsx",
  "seed_sha256": "d65f272812cf8dc95f3ca78c5db9a2fb2a39a759e5633eb3fb91891ad10a5486",
  "radius_km": 200.0,
  "total_seed_rows": 2085,
  "resolved_rows": 2085,
  "unresolved_rows": 0,
  "within_radius": 1093,
  "outside_radius": 992,
  "conservative_monitoring_denominator": 1093,
  "universe_resolution_coverage_percent": 100.0,
  "duplicate_cnpj_roots": ["00394494"],
  "suspicious_duplicate_keys": [],
  "db_matched_rows": 0,
  "identity_formula": "sha256(normalized_cnpj8|normalized_municipio|normalized_razao_social)",
  "radius_formula": "seed column 'Raio 200km?': SIM = included, NAO = excluded; missing/unknown decision remains unresolved"
}
```

### Contagens derivadas

| Métrica | Valor | Uso |
|---------|-------|-----|
| Linhas seed parseadas | 2085 | numerador bruto da planilha |
| Incluídos no raio 200 km | **1093** | **denominador canônico de monitoramento no raio** |
| Fora do raio | 992 | excluídos |
| Unresolved | 0 | sem decisão de raio ambígua |
| Conservative monitoring population | 1093 | included + unresolved (QW-01) |
| Resolution coverage | 100.0% | % de linhas com decisão de raio |
| Duplicate CNPJ roots | 1 (`00394494`) | ambiguidade possível em resolve por CNPJ8 |
| `sc_public_entities` no DB local | 2085 | alinhado ao total seed, **não** ao filtro de raio |
| `target_universe_entities` no DB local | **0** | snapshot de universo **não** materializado |

### Decisões de raio

```text
radius_decision_counts {'included': 1093, 'excluded': 992}
decision_method_counts {'seed_radius_flag': 2085}
```

Todas as decisões vieram da coluna da planilha (`seed_radius_flag`), não de geocoding runtime.

## Regras de autoridade (código)

De `scripts/lib/universe.py`:

1. Planilha é a **única autoridade** de membership do universo Extra.
2. Flags de raio no DB são **diagnóstico**, nunca denominador.
3. Constante `CANONICAL_UNIVERSE = 1093` é **histórico/compat**; código novo deve usar `load_canonical_universe`.
4. Identity key: `sha256(normalized_cnpj8|normalized_municipio|normalized_razao_social)`.

## Planilha × código

| Fonte | within_radius / baseline |
|-------|--------------------------|
| Planilha via openpyxl + `load_canonical_universe` | 1093 |
| Constante `CANONICAL_UNIVERSE` | 1093 |
| Delta | **0** |

Backup observado no repo: `Extra - alvos de licitação. R-0.backup.xlsx` (não usado nesta reconciliação).

## O que **não** foi feito / unknown

1. **Import versionado** para `target_universe_entities` / `target_universe_runs` — tabela vazia no datalake local.
2. **Join com `enriched_entities` / matching** — `db_matched_rows=0` nesta run (sem `conn`).
3. **Cobertura de oportunidades/open tenders sobre os 1093** — **não calculada**; qualquer % inventada seria falsa.
4. **Hash assinado em ledger de release** além do SHA-256 da planilha reportado acima.
5. **Validação se a planilha em produção VPS é a mesma** (mesmo SHA-256).

## Comando para reproduzir

```bash
cd "/mnt/d/extra consultoria"
python3 - <<'PY'
from scripts.lib.universe import load_canonical_universe, CANONICAL_UNIVERSE, sha256_file, DEFAULT_SEED_PATH
from pathlib import Path
import json
p = Path(DEFAULT_SEED_PATH)
print('sha256', sha256_file(p))
u = load_canonical_universe()
print(json.dumps(u.summary(), indent=2, ensure_ascii=False))
print('match_legacy', u.summary()['within_radius'] == CANONICAL_UNIVERSE)
PY
```
