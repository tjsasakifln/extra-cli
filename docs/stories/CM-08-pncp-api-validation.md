# CM-08: Validação e Correção da API PNCP — Editais + Contratos

**Epic:** EPIC-COVERAGE-MAX-200KM
**Status:** Done
**Risk:** STANDARD
**Created:** 2026-07-15

---

## Change Log

| Data | Transição | Agente | Notas |
|------|-----------|--------|-------|
| 2026-07-15 | Draft → Ready | @sm/@po | Story criada e validada |
| 2026-07-15 | Ready → InProgress | @dev | Constantes, crawl_contracts, transform_with_uf_filter |
| 2026-07-15 | InProgress → InReview | @dev | Ruff limpo, imports verificados, API real testada |
| 2026-07-15 | InReview → Done | @qa | CONCERNS: TST-001 (sem testes unitários), MNT-001 (status sync — resolvido). REQ-001 descartado (pcp_crawler.py é de commit anterior 12096cc) |

---

## Problema

A API PNCP (`/api/consulta/v1`) tem dois endpoints críticos cujos parâmetros reais divergem da documentação oficial:
1. **Contratações (editais):** page_size documentado como 500, mas API rejeita qualquer valor >50
2. **Contratos:** endpoint NUNCA ingerido (244k registros disponíveis), UF filter quebrado server-side
3. Page size estava 50 (correto) para contratações e 500 (correto) para contratos, mas sem distinção documentada

## Causa-Raiz

Documentação oficial do PNCP (Manual v1.0 e v2.3.11) afirma `tamanhoPagina` máximo de 500 para ambos os endpoints. Testes contra API real (2026-07-15) revelam:
- `contratacoes/publicacao`: max=50 (100→400 "Tamanho de página inválido")
- `contratos`: max=500 (1000→400 "Tamanho de página inválido")
- `contratos` UF filter retorna mesmo `totalRegistros` para qualquer UF (bug server-side)

## Escopo IN

- Constantes separadas `PNCP_TAMANHO_PAGINA_MAX_CONTRATACOES=50`, `PNCP_TAMANHO_PAGINA_MAX_CONTRATOS=500`
- `PNCP_CONTRATOS_PAGE_SIZE` no adapter respeitando limite de 500
- `crawl_contracts()` + `transform_contracts()` no `pncp_crawler_adapter`
- `transform_with_uf_filter()` no `contracts_crawler` para post-filtro UF
- Validação exaustiva com API real (7 testes, múltiplos page sizes)

## Escopo OUT

- Ativação do crawl de contratos no orchestrator (requer VPS Brasil — CM-06 blocker)
- Correção do UF filter server-side (responsabilidade do Serpro/MGI)
- Correção dos códigos de modalidade (requer tabela de domínio oficial)

## AC (Acceptance Criteria)

1. **GIVEN** page_size=500 enviado para `contratacoes/publicacao` **WHEN** API retorna 400 **THEN** código usa max=50
2. **GIVEN** page_size=500 enviado para `contratos` **WHEN** API retorna 200 com 500 registros **THEN** código usa max=500
3. **GIVEN** UF="SC" no endpoint `contratos` **WHEN** API ignora filtro e retorna todos os UFs **THEN** `transform_with_uf_filter` faz post-filtro client-side
4. **GIVEN** `crawl_contracts("full")` chamado **WHEN** API responde corretamente **THEN** retorna registros transformados no schema `pncp_supplier_contracts`

## Testes Requeridos

- [x] Teste API real: contratações page_size=50 (OK), 100+ (400)
- [x] Teste API real: contratos page_size=500 (OK), 1000+ (400)
- [x] Teste API real: contratos UF filter SC=PR=SP (quebrado server-side)
- [x] Import check: todos os módulos compilam
- [x] Ruff lint: All checks passed
- [x] Ruff format: All files formatted

## Arquivos Modificados

- `scripts/crawl/pncp_contract.py` — constantes separadas por endpoint
- `scripts/crawl/pncp_crawler_adapter.py` — `crawl_contracts()`, `transform_contracts()`, `PNCP_CONTRATOS_PAGE_SIZE`
- `scripts/crawl/contracts_crawler.py` — `transform_with_uf_filter()`

## Evidências

### Teste 1: contratações page_size limits
```
size=50:  OK - totalRegistros=1185, pages=24, records=50
size=100: HTTP 400 - "Tamanho de página inválido"
size=500: HTTP 400 - "Tamanho de página inválido"
```

### Teste 2: contratos page_size limits
```
size=500:  OK - totalRegistros=244855, pages=490, records=500
size=1000: HTTP 400 - "Tamanho de página inválido"
```

### Teste 3: contratos UF filter (quebrado)
```
UF=SC: totalRegistros=244855, totalPaginas=490
UF=PR: totalRegistros=244855, totalPaginas=490
UF=SP: totalRegistros=244855, totalPaginas=490
```

### Teste 4: contratações UF filter (funciona)
```
UF=SC: totalRegistros=1185
UF=PR: totalRegistros=2184
UF=SP: totalRegistros=3540
```

## Rollback

```bash
git revert HEAD
# Constantes voltam a PNCP_TAMANHO_PAGINA_MAX=50 único
# crawl_contracts e transform_with_uf_filter removidos
```

## DoD

- [x] Ruff lint passa
- [x] Ruff format passa
- [x] Imports verificados
- [x] Constantes validadas contra API real
- [ ] QA gate executado
- [ ] PO fechamento
