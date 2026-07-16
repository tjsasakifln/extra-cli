# C2.5 — Runtime CIGA CKAN (prova HEAD)

**Story:** PE-C2-05  
**Data:** 2026-07-16  
**Auth:** nenhuma  

## Comando / método

Amostra de **3/90** resources do mês `domsc-publicacoes-de-12-2025` (não backfill completo).

## Resultado

| Métrica | Valor |
|---------|--------|
| Meses disponíveis no portal | 54 |
| Target | `domsc-publicacoes-de-12-2025` |
| Resources no mês | 90 |
| Resources amostrados | 3 |
| Publicações procurement | 533 |
| Transformados | 533 |
| Tempo | ~6.1 s |
| Status | **OK** |

Artefato: `output/ciga-ckan/runtime-domsc-publicacoes-de-12-2025.json`

## Sample (honesto)

- `source_id`: 7786214  
- `municipio`: Gaspar  
- `link`: diariomunicipal.sc.gov.br/?q=id:…  
- `orgao_cnpj`: **null** (não no JSON CIGA)  
- `valor_total_estimado`: **null** (não no JSON CIGA)  

## Conclusão

Path público CIGA Dados **operacional sem API key**. C2.5 não está mais blocked por credencial no caminho canônico.
