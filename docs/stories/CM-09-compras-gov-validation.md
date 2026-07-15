# CM-09: Validação e Ativação ComprasGov V3

**Epic:** EPIC-COVERAGE-MAX-200KM
**Status:** Done
**Risk:** STANDARD
**Created:** 2026-07-15

---

## Change Log

| Data | Transição | Agente | Notas |
|------|-----------|--------|-------|
| 2026-07-15 | Draft → Ready | @sm/@po | Story criada |
| 2026-07-15 | Ready → InProgress | @dev | Smoke test contra API real |
| 2026-07-15 | InProgress → InReview | @dev | Crawler funcional, 8 SC registros |
| 2026-07-15 | InReview → Done | @qa | PASS — crawler validado contra API real |

---

## Problema

ComprasGov V3 (`dadosabertos.compras.gov.br`) é fonte federal sem geo-restrição, crawler completo implementado mas NUNCA executado. API retorna dados da Lei 14.133/2021 com CNPJ, UF filter server-side funcional.

## Causa-Raiz

Crawler foi implementado mas nunca ativado no pipeline. Nenhum blocker técnico — API funciona de qualquer IP.

## Escopo IN

- Smoke test crawler contra API real
- Validar endpoint Lei 14.133 com UF=SC
- Confirmar transformação para schema pncp_raw_bids
- Documentar formatos de data (YYYY-MM-DD vs YYYYMMDD)

## Escopo OUT

- Otimização de page_size (já está 100, max 500)
- Ativação no systemd timer (requer deploy na VPS)
- Correção de campos opcionais (modalidade, valor — dependem da API)

## AC

1. **GIVEN** crawl("incremental") chamado **WHEN** API responde **THEN** retorna lista de dicts ou [] (nunca exception)
2. **GIVEN** _paginate com UF=SC e 45 dias **WHEN** API tem dados **THEN** retorna registros com CNPJ e UF preenchidos
3. **GIVEN** transform() chamado com registros crus **WHEN** schema válido **THEN** retorna registros no formato pncp_raw_bids

## Evidências

### Smoke test (2026-07-15):
```
Lei 14.133 SC 45d: 8 raw records
Sample: orgao=CONSELHO REGIONAL DE ENGENHARIA E AGRONOMIA DE SAN
  UF=SC, modalidade=None, valor=None
Transformed: 8 records
  uf=SC, orgao_cnpj=82511643000164
```

### Teste direto API:
```
HTTP 200, totalRegistros=8, totalPaginas=1
52 registros SC em 6.5 meses
47 registros SP em 45 dias
Date format: YYYY-MM-DD (≠ PNCP YYYYMMDD)
```

## Arquivos

- `scripts/crawl/compras_gov_crawler.py` — validado, sem alterações necessárias

## Rollback

```bash
# Nada a reverter — código não foi alterado
```

## DoD

- [x] Smoke test contra API real
- [x] Transform validado com dados reais
- [x] UF filter confirmado funcional
- [x] Sem geo-restrição confirmado
- [x] Ruff lint (sem alterações)
- [x] QA gate executado
- [ ] PO fechamento
