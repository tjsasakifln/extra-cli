# Lib — Geocode (Coordenadas e Distância)

> Gerado pelo Writer em 2026-07-13T16:30:00Z | doc_level: completo | Base: e9729e1

**Módulo:** `scripts/lib/geocode.py` (322 linhas)
**Dependência:** HARD — opportunity_intel, contract_intel, cobertura geográfica
**Referência externa:** IBGE cache, plano-mestre §3 (dimensão geográfica de cobertura)

---

## Interface

### Constantes

| Constante | Valor | Descrição |
|-----------|-------|-----------|
| `CACHE_FILE` | `"data/geocode_cache.json"` | Arquivo de cache local |
| `IBGE_API_URL` | `"https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{ibge}"` | API do IBGE para nome oficial |
| `NOMINATIM_URL` | `"https://nominatim.openstreetmap.org/search"` | API OpenStreetMap para coordenadas |
| `NOMINATIM_RATE` | `1.0` | 1 requisição/segundo (política OSM) |
| `USER_AGENT` | `"ExtraConsultoria/1.0 (coverage-analysis)"` | User-Agent para Nominatim |
| `SC_BBOX` | `{"min_lat": -29.5, "max_lat": -25.5, "min_lon": -53.5, "max_lon": -48.0}` | Bounding box de Santa Catarina |
| `FLORIANOPOLIS` | `(-27.5954, -48.5480)` | Coordenadas da sede administrativa |
| `EARTH_RADIUS_KM` | `6371` | Raio médio da Terra (km) |

### Funções

| Função | Retorno | Descrição |
|--------|---------|-----------|
| `haversine(lat1, lon1, lat2, lon2)` | `float` | Distância em km entre dois pontos (fórmula de Haversine) |
| `validate_coords(lat, lon)` | `bool` | Valida se coordenadas estão dentro do bounding box de SC |

### Classe Geocoder

```python
class Geocoder:
    def __init__(self, cache_file: str = CACHE_FILE)

    # Geocoding
    def geocode(self, ibge: str | None = None, municipio: str | None = None)
        -> tuple[float | None, float | None, str]
        # Retorna (lat, lon, method) onde method é:
        #   'cache'        → acertou no cache local
        #   'nominatim'    → geocodificado via OpenStreetMap
        #   'failed'       → não foi possível geocodificar
        #   'out_of_bounds'→ coordenadas fora do bounding box SC

    def geocode_batch(self, entities: list[dict]) -> dict[str, Any]
        # Agrupa entidades por codigo_ibge, geocodifica cada município único
        # Retorna stats: geocoded, failed, total_municipios, total_entities, updated_ids

    # Cache
    def _load_cache(self, path: str) -> dict[str, Any]      # privado
    def _save_cache(self) -> None                             # privado

    # Stats
    stats: dict[str, int]  # cache_hit, ibge_api, nominatim, failed
```

---

## Fluxo Principal

### 1. Geocoding (3 níveis)

```
geocode(ibge, municipio)
├── Nível 1: Cache local
│   ├── Buscar por ibge no cache JSON
│   ├── Se encontrado e tem lat/lon → retornar ("cache")
│   └── Se não encontrado → continuar
│
├── Nível 2: IBGE API (nome oficial)
│   ├── Se ibge disponível:
│   │   GET https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{ibge}
│   │   Se 200 → extrair nome oficial do município
│   │   Se falha → log warning, continuar com nome original
│   └── Se ibge não disponível → continuar com municipio
│
├── Nível 3: Nominatim (coordenadas)
│   ├── Rate limit: sleep se < 1s desde última chamada
│   ├── Query: "{municipio_nome}, SC, Brazil"
│   ├── Params: format=json, limit=1, countrycodes=br, bounded=1, viewbox=SC_BBOX
│   ├── Se 200 e results não vazio:
│   │   ├── Extrair lat, lon do primeiro resultado
│   │   ├── validate_coords() → se fora do bounding box: ("out_of_bounds")
│   │   ├── Salvar no cache local
│   │   └── Retornar (lat, lon, "nominatim")
│   └── Se falha: log warning, retornar ("failed")
│
└── Se todos os níveis falham → (None, None, "failed")
```

### 2. Batch Geocoding

```
geocode_batch(entities)
├── Agrupar entidades por codigo_ibge (único município = 1 chamada Nominatim)
├── Para cada município único:
│   └── geocode(ibge, municipio)
├── Coletar stats
└── Retornar {geocoded, failed, total_municipios, total_entities, updated_ids}
```

### 3. Cálculo de Distância Haversine

```
haversine(lat1, lon1, lat2, lon2)
├── Converter graus decimais para radianos
├── dlat = lat2_r - lat1_r
├── dlon = lon2_r - lon1_r
├── a = sin²(dlat/2) + cos(lat1_r) * cos(lat2_r) * sin²(dlon/2)
├── c = 2 * arcsin(sqrt(a))
└── retornar EARTH_RADIUS_KM * c
```

---

## Regras de Negócio

| # | Regra | Severidade |
|---|-------|-----------|
| RN-G01 | Cache local tem precedência sobre chamadas externas. Operação offline usa apenas cache. | 🔴 |
| RN-G02 | Rate limiting Nominatim é obrigatório (1 req/s) — violação pode resultar em bloqueio de IP. | 🔴 |
| RN-G03 | Coordenadas fora do bounding box de SC são rejeitadas (`out_of_bounds`) — não entram no cache. | 🟡 |
| RN-G04 | Agrupamento por município no batch: N entidades do mesmo município geram no máximo 1 chamada Nominatim. | 🟢 |
| RN-G05 | IBGE API retorna apenas nome oficial (NÃO coordenadas). A coordenada vem sempre do Nominatim. | 🟡 |
| RN-G06 | Cache legado (formato `{"municipio|UF": [lat, lon]}`) é migrado automaticamente para formato novo. | 🟢 |

---

## Formato do Cache

```json
{
  "4205407": {
    "municipio": "Florianópolis",
    "lat": -27.5954,
    "lon": -48.5480,
    "method": "nominatim",
    "cached_at": "2026-07-13T12:00:00"
  },
  "4200054": {
    "municipio": "Abdon Batista",
    "lat": -27.6100,
    "lon": -51.0230,
    "method": "legacy_cache",
    "cached_at": "2026-07-13T12:00:00"
  }
}
```

Chave primária: código IBGE de 7 dígitos. Fallback: nome do município.

---

## Dependências

| Dependência | Tipo | Uso |
|------------|------|-----|
| `requests` | externa | Chamadas HTTP para IBGE API e Nominatim |
| `math` | stdlib | Haversine (radians, sin, cos, asin, sqrt) |
| `json` | stdlib | Cache em arquivo |
| `time` | stdlib | Rate limiting Nominatim |
| `os` | stdlib | Verificação de existência do cache |

---

## Riscos e Lacunas

| # | Risco/Lacuna | Status | Impacto |
|---|-------------|--------|---------|
| 🟢 L-G01 | Cache com migração automática de formato legado. | 🟢 RESOLVIDO | Retrocompatibilidade garantida. |
| 🟡 L-G02 | Dependência de API externa (Nominatim) sem fallback para outra fonte de coordenadas. Se Nominatim estiver fora do ar, geocoding falha totalmente fora do cache. | 🟡 | Impacto médio: cache já cobre municípios previamente resolvidos. |
| 🟡 L-G03 | IBGE API é chamada apenas para obter nome oficial do município. Se o nome passado já é o oficial, a chamada é desperdício. | 🟡 | Otimização possível: pular IBGE API quando nome foi verificado recentemente. |
| 🟡 L-G04 | `FLORIANOPOLIS` e `EARTH_RADIUS_KM` são constantes soltas no módulo. Módulos externos importam diretamente — renomear quebraria consumers. | 🟡 | Manter como constantes públicas com documentação clara. |
| 🟢 L-G05 | Rate limiting Nominatim implementado corretamente com `time.sleep()`. | 🟢 RESOLVIDO | Conforme política OSM. |
