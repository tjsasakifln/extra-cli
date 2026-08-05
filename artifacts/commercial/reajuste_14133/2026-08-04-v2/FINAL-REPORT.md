# FINAL-REPORT — reajuste 14.133 commercial queue v2 (PR #200)

**As-of:** 2026-08-04  
**Module:** 2.0.0  
**Terminal status:** `BLOCKED_INSUFFICIENT_VERIFIED_OUTREACH_LEADS`  
**Evidence commit:** `9b6f92072aaf8eecceabc83fd15d209d0f17d4b9`  
**Git SHA (run tree at generation):** `c39e52e5865677c121084d5ae7afaf99f1a63902`  
**Source:** ssh / ssh:ec-prod  
**Generated:** 2026-08-05T01:31:39Z

## 1. What v1 delivered vs why it was insufficient

v1 produced a **contract-level** queue heavily biased by `--max-source-rows=25000` + `ORDER BY valor_total DESC`, with:
- `LEGAL_REGIME_UNKNOWN` treated as commercial queue material
- HTML/object-only “verification”
- PDF binary counted as docs accessible
- fixed freshness/contradiction placeholders
- no supplier consolidation (GAIA, PLANATERRA, etc. repeated as independent leads)
- no `OUTREACH_*` gates distinct from legal status
- commercial files only local / not PR-verifiable

## 2. v2 corrections (code)

- Keyset pagination (`valor_total`, `contrato_id`); default **no** silent 25k cap
- Soft temporal prefilter (signature <12m not hard-exclude)
- Document pipeline states; PDF binary ≠ text extracted ≠ gate pass
- Index only when inside reajuste clause window
- Legal regime conflict detection
- Value quality (billion-scale outliers blocked from financial score)
- Real freshness + material contradictions
- Giant-group heuristics broadened
- Supplier portfolio consolidation + economic same-obra dedupe
- `OUTREACH_READY` / `WITHOUT_VALUE` / `DOCUMENT_REQUEST` / `NOT_READY`
- CLI: `manual_review` default False (never `or True`); `max_source_rows` default None
- 78 unit tests (v1+v2) green

## 3. Campaign execution (Sul — Etapa A)

| Metric | Value |
|--------|------:|
| Universe eligible (pré-filtro Sul) | 27634 |
| Rows read | 27634 |
| Execution complete | True |
| Sampling | none (full prefilter) |
| Construction classified | 7577 |
| Supplier portfolios | 2721 |
| Deep document fetches | 220 |
| OUTREACH_READY suppliers | 0 |
| OUTREACH_READY_WITHOUT_VALUE | 0 |
| DOCUMENT_REQUEST_CANDIDATE | 1 |
| NOT_READY | 2720 |
| Regime 14.133 proven (contracts) | 1 |

UF distribution: `{"PR": 13073, "SC": 6641, "RS": 7920}`  
Value bands: `{"ge_1b": 17, "300m_1b": 47, "50m_300m": 1191, "5m_50m": 5713, "lt_5m": 20666}`

### Terminal honesty

`BLOCKED_INSUFFICIENT_VERIFIED_OUTREACH_LEADS`

After processing the **entire** Sul prefilter (27634 rows) and **220** prioritized deep document fetches, fewer than 15 suppliers meet `OUTREACH_READY*`.  
**No invented ready leads.** PNCP HTML/API rarely expose full contract text with regime clause + data-base + index in-clause.

## 4. Top 15 Sul suppliers (intelligence / document-request — not auto-outreach)

```json
[
  {
    "ranking": 1,
    "razao_social": "SURG CIA DE SERVICOS DE URBANIZACAO DE G",
    "cnpj_masked": "75646273****",
    "sede_uf": "PR",
    "qtd_contratos": 7,
    "outreach_status": "DOCUMENT_REQUEST_CANDIDATE",
    "score": 18.54,
    "melhor_contrato": "76178037000176-2-000112/2025",
    "valor_portfolio": 88966450.82
  },
  {
    "ranking": 2,
    "razao_social": "CONSTRUCOES SCHOROEDER EIRELI    -",
    "cnpj_masked": "10249046****",
    "sede_uf": "SC",
    "qtd_contratos": 20,
    "outreach_status": "NOT_READY_FOR_OUTREACH",
    "score": 21.41,
    "melhor_contrato": "04892707000100-2-000445/2023",
    "valor_portfolio": 303872762.08
  },
  {
    "ranking": 3,
    "razao_social": "NEOVIA INFRAESTRUTURA RODOVIARIA LTDA",
    "cnpj_masked": "02955426****",
    "sede_uf": "PR",
    "qtd_contratos": 14,
    "outreach_status": "NOT_READY_FOR_OUTREACH",
    "score": 20.99,
    "melhor_contrato": "04892707000100-2-000142/2024",
    "valor_portfolio": 775936923.8299999
  },
  {
    "ranking": 4,
    "razao_social": "QUALIDADE MINERACAO LTDA",
    "cnpj_masked": "00820854****",
    "sede_uf": "SC",
    "qtd_contratos": 37,
    "outreach_status": "NOT_READY_FOR_OUTREACH",
    "score": 20.76,
    "melhor_contrato": "82951344000140-2-000031/2024",
    "valor_portfolio": 426838475.71
  },
  {
    "ranking": 5,
    "razao_social": "GAIA RODOVIAS LTDA.",
    "cnpj_masked": "03257777****",
    "sede_uf": "SC",
    "qtd_contratos": 11,
    "outreach_status": "NOT_READY_FOR_OUTREACH",
    "score": 20.67,
    "melhor_contrato": "82951344000140-2-000038/2024",
    "valor_portfolio": 225219956.83
  },
  {
    "ranking": 6,
    "razao_social": "AGUAS DE PALHOCA S.A",
    "cnpj_masked": "57341135****",
    "sede_uf": "SC",
    "qtd_contratos": 1,
    "outreach_status": "NOT_READY_FOR_OUTREACH",
    "score": 20.35,
    "melhor_contrato": "82892316000108-2-000632/2024",
    "valor_portfolio": 238000000.0
  },
  {
    "ranking": 7,
    "razao_social": "ENGERAMA ENGENHARIA E EMPREENDIMENTOS LTDA",
    "cnpj_masked": "79096020****",
    "sede_uf": "PR",
    "qtd_contratos": 1,
    "outreach_status": "NOT_READY_FOR_OUTREACH",
    "score": 20.18,
    "melhor_contrato": "76105543000135-2-000098/2024",
    "valor_portfolio": 154990000.0
  },
  {
    "ranking": 8,
    "razao_social": "PLANATERRA-TERRAPLENAGEM E PAVIMENTACAO LTDA",
    "cnpj_masked": "82743832****",
    "sede_uf": "SC",
    "qtd_contratos": 24,
    "outreach_status": "NOT_READY_FOR_OUTREACH",
    "score": 19.78,
    "melhor_contrato": "04892707000100-2-000542/2024",
    "valor_portfolio": 829482415.0500001
  },
  {
    "ranking": 9,
    "razao_social": "CEGE ENGENHARIA LTDA",
    "cnpj_masked": "04484014****",
    "sede_uf": "SC",
    "qtd_contratos": 10,
    "outreach_status": "NOT_READY_FOR_OUTREACH",
    "score": 19.7,
    "melhor_contrato": "82951344000140-2-000036/2024",
    "valor_portfolio": 105171698.5
  },
  {
    "ranking": 10,
    "razao_social": "CONSORCIO CONSTRUTOR ESTRADAS RURAIS",
    "cnpj_masked": "57155217****",
    "sede_uf": "PR",
    "qtd_contratos": 1,
    "outreach_status": "NOT_READY_FOR_OUTREACH",
    "score": 19.67,
    "melhor_contrato": "07820337000194-2-000010/2024",
    "valor_portfolio": 96850536.0
  },
  {
    "ranking": 11,
    "razao_social": "ENDEAL ENGENHARIA E CONSTRUÇÕES LTDA",
    "cnpj_masked": "03430585****",
    "sede_uf": "PR",
    "qtd_contratos": 1,
    "outreach_status": "NOT_READY_FOR_OUTREACH",
    "score": 19.63,
    "melhor_contrato": "12092636000190-2-000005/2024",
    "valor_portfolio": 118876086.76
  },
  {
    "ranking": 12,
    "razao_social": "CONSORCIO PALMEIRA",
    "cnpj_masked": "57437373****",
    "sede_uf": "PR",
    "qtd_contratos": 1,
    "outreach_status": "NOT_READY_FOR_OUTREACH",
    "score": 19.54,
    "melhor_contrato": "76669324000189-2-000083/2024",
    "valor_portfolio": 257215008.0
  },
  {
    "ranking": 13,
    "razao_social": "CONSORCIO VALE DO RIBEIRA",
    "cnpj_masked": "53673938****",
    "sede_uf": "PR",
    "qtd_contratos": 1,
    "outreach_status": "NOT_READY_FOR_OUTREACH",
    "score": 19.14,
    "melhor_contrato": "76669324000189-2-000013/2024",
    "valor_portfolio": 56919000.0
  },
  {
    "ranking": 14,
    "razao_social": "ARTELESTE CONSTRUCOES LTDA",
    "cnpj_masked": "75911438****",
    "sede_uf": "PR",
    "qtd_contratos": 3,
    "outreach_status": "NOT_READY_FOR_OUTREACH",
    "score": 19.05,
    "melhor_contrato": "04892707000100-2-000169/2024",
    "valor_portfolio": 252880457.74
  },
  {
    "ranking": 15,
    "razao_social": "SETEP CONSTRUCOES S.A",
    "cnpj_masked": "83665141****",
    "sede_uf": "SC",
    "qtd_contratos": 7,
    "outreach_status": "NOT_READY_FOR_OUTREACH",
    "score": 19.04,
    "melhor_contrato": "04892707000100-2-000324/2023",
    "valor_portfolio": 106078651.69
  }
]
```

## 5. Artifacts

Directory: `output/commercial/reajuste_14133/2026-08-04-v2/`

Required files present (see `checksums.sha256`). Heavy XLSX/JSON stay under `output/` per generated-artifacts policy; PR carries this report + hashes + sanitised sample.

## 6. Tests

```
python3 -m pytest tests/commercial/test_reajuste_14133.py tests/commercial/test_reajuste_14133_v2.py -q --no-cov
# 78 passed
```

## 7. Recommended first contact sequence

**Do not send messages automatically.** Given zero `OUTREACH_READY`, recommended sequence is **document-request exploratory only** for strong mid-market Sul constructors after manual PDF retrieval:

1. Review Top 15 portfolios in Excel `SUPPLIER_PORTFOLIOS` / `SUL_SC_PRIORITY`
2. For each: download full contract + edital from organ portal / PNCP anexos
3. Confirm Lei 14.133 excerpt + reajuste clause + data-base + index
4. Only then promote to `OUTREACH_READY` with human_confirmed flags
5. Language if contacting earlier: exploratory document request template (see `DOCUMENT_REQUEST` sheet)

## 8. Limitations

- Official index series (SINAPI/SICRO/INCC) not auto-fetched → `valor_potencial` remains null (correct)
- Apostila absence ≠ no prior reajuste
- Human review uses campaign evidence; full clause confirmation still needs organ PDFs
- National complement written under `nacional/` when completed
