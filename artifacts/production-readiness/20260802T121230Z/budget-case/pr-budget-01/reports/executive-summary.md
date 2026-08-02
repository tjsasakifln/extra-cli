# Executive Summary — Budget Audit

- **Case ID:** pr-budget-01
- **Generated:** 2026-08-01T20:00:53Z
- **Documents:** 1
- **Budget items:** 12
- **Findings:** 31
- **Severity:** {'MEDIUM': 27, 'HIGH': 4}
- **Arithmetic checks:** 22 ({'PASS': 17, 'MATERIAL_DIFFERENCE': 2, 'NOT_EVALUATED': 3})
- **total_sale_price_sum=5256.25**
- **total_direct_cost_sum=None**
- **BDI components:** 8
- **bdi_sum_percent_points=30.5**

## Scope & limitations

- Human remains responsible for price formation, margin, competitive strategy and professional seal.
- System does not invent BDI, margins, win probability or internal costs.
- Missing formula cache is never treated as zero.
- Official references require explicit manifest (system, month, locality, regime).

## Top findings

- **MEDIUM** `F-0001` Material arithmetic difference — cells: Orcamento Analitico!E3, Orcamento Analitico!H3, Orcamento Analitico!I3, Orcamento Analitico!F3
- **MEDIUM** `F-0002` Material arithmetic difference — cells: Orcamento Analitico!E8, Orcamento Analitico!H8, Orcamento Analitico!I8, Orcamento Analitico!F8
- **HIGH** `F-0003` Formula issue: BROKEN_REFERENCE — cells: Orcamento Analitico!I4
- **MEDIUM** `F-0004` Formula issue: EXTERNAL_REFERENCE — cells: Auxiliar!B2
- **MEDIUM** `F-0005` NEGATIVE_VALUE — cells: Orcamento Analitico!A9, Orcamento Analitico!B9, Orcamento Analitico!C9, Orcamento Analitico!D9, Orcamento Analitico!E9, Orcamento Analitico!F9, Orcamento Analitico!H9, Orcamento Analitico!I9, Orcamento Analitico!G9
- **MEDIUM** `F-0006` NEGATIVE_VALUE — cells: Orcamento Analitico!A9, Orcamento Analitico!B9, Orcamento Analitico!C9, Orcamento Analitico!D9, Orcamento Analitico!E9, Orcamento Analitico!F9, Orcamento Analitico!H9, Orcamento Analitico!I9, Orcamento Analitico!G9
- **MEDIUM** `F-0007` DUPLICATE_CODE — cells: Orcamento Analitico!A2, Orcamento Analitico!B2, Orcamento Analitico!C2, Orcamento Analitico!D2, Orcamento Analitico!E2, Orcamento Analitico!F2, Orcamento Analitico!H2, Orcamento Analitico!I2, Orcamento Analitico!G2, Orcamento Analitico!A5, Orcamento Analitico!B5, Orcamento Analitico!C5, Orcamento Analitico!D5, Orcamento Analitico!E5, Orcamento Analitico!F5, Orcamento Analitico!H5, Orcamento Analitico!I5, Orcamento Analitico!G5, Curva ABC!A2, Curva ABC!B2, Curva ABC!C2, Curva ABC!D2, Curva ABC!E2
- **MEDIUM** `F-0008` DUPLICATE_CODE — cells: Orcamento Analitico!A3, Orcamento Analitico!B3, Orcamento Analitico!C3, Orcamento Analitico!D3, Orcamento Analitico!E3, Orcamento Analitico!F3, Orcamento Analitico!H3, Orcamento Analitico!I3, Orcamento Analitico!G3, Orcamento Analitico!A6, Orcamento Analitico!B6, Orcamento Analitico!C6, Orcamento Analitico!D6, Orcamento Analitico!E6, Orcamento Analitico!F6, Orcamento Analitico!H6, Orcamento Analitico!I6, Orcamento Analitico!G6
- **MEDIUM** `F-0009` DUPLICATE_CODE — cells: Orcamento Analitico!A7, Orcamento Analitico!B7, Orcamento Analitico!C7, Orcamento Analitico!D7, Orcamento Analitico!E7, Orcamento Analitico!F7, Orcamento Analitico!H7, Orcamento Analitico!I7, Orcamento Analitico!G7, Curva ABC!A3, Curva ABC!B3, Curva ABC!C3, Curva ABC!D3, Curva ABC!E3
- **HIGH** `F-0010` NEGATIVE_QUANTITY — cells: Orcamento Analitico!A9, Orcamento Analitico!B9, Orcamento Analitico!C9, Orcamento Analitico!D9, Orcamento Analitico!E9, Orcamento Analitico!F9, Orcamento Analitico!H9, Orcamento Analitico!I9, Orcamento Analitico!G9
- **MEDIUM** `F-0011` ZERO_QUANTITY — cells: Orcamento Analitico!A10, Orcamento Analitico!B10, Orcamento Analitico!C10, Orcamento Analitico!D10, Orcamento Analitico!E10, Orcamento Analitico!F10, Orcamento Analitico!H10, Orcamento Analitico!I10, Orcamento Analitico!G10
- **MEDIUM** `F-0012` SAME_CODE_DIFFERENT_QTY — cells: —
- **MEDIUM** `F-0013` SAME_CODE_DIFFERENT_QTY — cells: —
- **MEDIUM** `F-0014` MISSING_COEFFICIENT — cells: Composicoes!A4, Composicoes!B4, Composicoes!C4, Composicoes!E4
- **MEDIUM** `F-0015` NEGATIVE_COEFFICIENT — cells: Composicoes!A5, Composicoes!B5, Composicoes!C5, Composicoes!D5, Composicoes!E5, Composicoes!F5

## Non-claims

- BDI legal
- BDI ilegal
- BDI correto
- BDI abusivo
- BDI conforme TCU
- BDI is margin
- Inexequibility conclusion
- Legal compliance of BDI
- Optimal bid suggestion
