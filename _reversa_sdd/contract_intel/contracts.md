# Contract Intelligence — Contratos Externos

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d

## Contrato: PNCP Contratos

| Campo | Valor |
|-------|-------|
| **Endpoint** | `https://pncp.gov.br/api/consulta/v1/contratos` |
| **Método** | GET |
| **Autenticação** | Não requer (API pública) |
| **Paginação** | `?pagina=1&tamanhoPagina=100` |
| **Parâmetros** | `dataPublicacaoInicio`, `dataPublicacaoFim`, `uf`, `municipio`, `orgaoCnpj`, `fornecedorCnpj`, `palavraChave` |
| **Retorno** | JSON: `{totalRegistros, totalPaginas, pagina, tamanhoPagina, data[]}` |
| **Adapter** | `scripts/crawl/contracts_crawler.py` |

### Schema de resposta (campos usados)

```json
{
  "totalRegistros": 1500000,
  "totalPaginas": 15000,
  "data": [{
    "orgaoCnpj": "string",
    "orgaoNome": "string",
    "unidadeOrgaoCnpj": "string",
    "fornecedorCnpj": "string",
    "fornecedorNome": "string",
    "numeroContrato": "string",
    "objetoContrato": "string",
    "valorGlobal": "number",
    "dataAssinatura": "string (ISO date)",
    "dataInicioVigencia": "string (ISO date)",
    "dataFimVigencia": "string (ISO date)",
    "dataPublicacaoPncp": "string (ISO datetime)",
    "situacaoContrato": "string",
    "numeroControlePNCP": "string (ID canônico)",
    "linkSistemaOrigem": "string"
  }]
}
```

## Contrato: Target Universe

### Input (seed spreadsheet)

Colunas esperadas (ordem fixa, 0-indexed):
0. `razao_social`
1. `cnpj8`
2. `municipio`
3. `ibge_code`
4. `natureza_juridica`
5. `cod_natureza`
6. `latitude`
7. `longitude`
8. `distancia_km` (pré-calculada na planilha)
9. `raio_200km` ('SIM ✓' ou '')

### Output (TargetUniverse)

```python
@dataclass
class TargetEntity:
    razao_social: str
    cnpj8: str
    municipio: str
    ibge_code: str
    natureza_juridica: str
    latitude: float | None
    longitude: float | None
    distancia_km: float  # Haversine calculado
    within_200km: bool
    canonical_entity_key: str  # identidade estável

@dataclass
class TargetUniverse:
    entities: list[TargetEntity]  # 1.093 dentro do raio
    excluded: list[TargetEntity]  # 992 fora do raio
    duplicates: list[dict]  # CNPJ-base duplicados
    without_coords: list[dict]  # sem coordenadas
    seed_sha256: str
    radius_km: float
    generated_at: str
```

## Views Canônicas (PostgreSQL)

| View | Propósito | Status |
|------|-----------|--------|
| `v_entities_canonical` | Entes do universo com identidade canônica | 🔴 Não materializada |
| `v_contracts_canonical` | Contratos com nomes de coluna estáveis | 🔴 Não materializada |
| `v_suppliers_canonical` | Fornecedores com identidade unificada | 🔴 Não materializada |
| `v_value_observations_canonical` | Observações de valor com semântica | 🔴 Não materializada |

> As views estão definidas no plano-mestre §6.2 mas ainda não foram implementadas como migrations.
