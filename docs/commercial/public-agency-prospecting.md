# Prospecção de órgãos públicos

## Tipos

| Tipo | Significado |
|------|-------------|
| `PUBLIC_AGENCY_PROSPECT` | Entidade compradora / órgão |
| supplier commercial lead | Empresa privada fornecedora (ciclo legado) |

Filas: `public_agency_leads` vs `supplier_leads`.

## Modos

### REACTIVE_OPPORTUNITY

Há contrato/publicação recente observável compatível com serviços CONFENGE.

### PROACTIVE_INSTITUTIONAL_PROSPECT

Não há oportunidade formal isolada; o dossier fala em **sinais de possível necessidade técnica**, nunca “o órgão está contratando” sem publicação.

## Gates de publicabilidade

Um município pequeno **não** entra só por ser pequeno. Exige:

1. identidade oficial válida  
2. ≥1 sinal material de necessidade  
3. ≥1 evidência oficial  
4. aderência a oferta do catálogo  
5. explicação legível  
6. sem bloqueio COI crítico / compliance  
7. canal institucional ou justificativa de pesquisa  

Categorias: `PUBLISHABLE` | `REVIEW_REQUIRED` | `RESEARCH_REQUIRED` | `COMPLIANCE_BLOCKED` | `CONFLICT_BLOCKED` | `NOT_A_FIT`

## Fontes

- PNCP histórico (`pncp_supplier_contracts` lado órgão)
- IBGE população (YAML + suplemento SC)
- Sem scraping nacional frágil como dependência crítica

## Scoring

`priority = 0.30·need + 0.25·fit + 0.20·timing + 0.15·evidence + 0.10·access − penalties`

Explicável por lead (`score.decomposition`, `signals`).
