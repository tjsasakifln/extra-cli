# EXTRA-OPS-95-FOUNDATION — OSS Architecture Harvest (M0.5)

**UTC:** 2026-07-19T02:31:00Z  
**Política:** nenhuma adoção sem benchmark comparativo e impacto mensurável no DOD.  
**Artefato máquina:** `oss-decisions.json`

## SmartLic — três dimensões

| Dimensão | Decisão | Notas |
|----------|----------|-------|
| 1. Arquitetura / padrões | **BORROW_PATTERN** seletivo | Checkpoint, fail-closed fetch, paginação — já parcialmente no Extra |
| 2. Corpus / dataset comparador | **DEFER** | Stale; só fixtures offline / corpus rotulado |
| 3. Fonte operacional | **REJECT** (caminho crítico) | Não eleva cobertura/freshness |

Herança: `NEXT-30D-ROI-MAIN-R2/SMARTLIC-REUSE-MATRIX.md` v2.0.0.

## Matriz de candidatos

| ID | Componente | Problema DOD | Solução atual | Decisão | Justificativa curta | Próximo |
|----|------------|--------------|---------------|---------|---------------------|---------|
| OSS-01 | SmartLic code patterns | Ingestão/resiliência | Crawlers Extra tipados | **BORROW_PATTERN** | Extra já superior em vários pontos | Nenhum port em massa |
| OSS-02 | SmartLic dataset | Cobertura/freshness | Coleta própria | **DEFER** | Stale | Fora do crítico |
| OSS-03 | OCDS | Encadeamento edital→contrato | Tabelas operacionais + views | **ADAPT** (camada) | Semântica + provenance sem remodelar DB | Piloto mapping amostra |
| OSS-04 | ocdskit | Validação serialização OCDS | Validação ad hoc | **DEFER** até piloto OCDS | Depende de OSS-03 | Benchmark 1 |
| OSS-05 | Kingfisher Collect/Process | Coleta/processamento OCDS | Crawlers próprios | **REJECT** full / **BORROW_PATTERN** | Peso ops alto, multi-serviço | Só padrões |
| OSS-06 | Pandera | Contratos de dados / fail-before-promote | Pydantic parcial + PG CHECK | **ADAPT** piloto | Proporcional; complementa PG | Benchmark 2 schemas críticos |
| OSS-07 | Great Expectations | Idem | — | **REJECT** (agora) | Mais pesado que Pandera no estágio | Comparativo só |
| OSS-08 | Splink | Matching residual | CNPJ/IBGE/regras + rapidfuzz | **DEFER** piloto residual | Só após determinístico esgotado | Benchmark 3 |
| OSS-09 | Dedupe | Matching residual | — | **REJECT** preferindo Splink se piloto | Menos ativo / Spark-ish | Comparativo |
| OSS-10 | Evidently | Drift/recall/precisão | recall_benchmark scaffold | **DEFER** | Útil p/ N09 se amostra existir | Benchmark 4 |
| OSS-11 | Docling | PDF/tabelas editais | Parsers atuais | **DEFER** piloto docs reais | OCR/tabelas; fallback chain | Benchmark 5 |
| OSS-12 | Prefect | Orquestração resume | Scripts + checkpoints + manifests | **DEFER** | Só se reduzir complexidade total | Benchmark 6 |
| OSS-13 | Dagster | Orquestração | — | **REJECT** (agora) | Mais pesado, sem ganho claro | Comparativo |
| OSS-14 | OpenContracts | Anotação/rastreio trechos | Dossiers textuais | **BORROW_PATTERN** | Não instalar plataforma | Padrões de citação |

## Regras de decisão

- **ADOPT:** só após benchmark com melhoria material + testes + rollback.  
- **ADAPT:** camada fina / schemas / mapping, sem substituir core.  
- **BORROW_PATTERN:** copiar ideia, zero dependência nova.  
- **DEFER:** valor possível, não no caminho crítico da cobertura 95%.  
- **REJECT:** complexidade ou desalinhamento local-first.

## Ordem de pilotos (pós cobertura mínima)

1. **Pandera** (fail-closed promote) — ROI alto, esforço baixo  
2. **OCDS intermediate mapping** — encadeamento + valores  
3. **Splink residual** — só com gold labels  
4. **Docling** — se parser atual falhar em amostra real  
5. **Prefect** — só se 3 ciclos manuais mostrarem dor de orquestração  
6. **Evidently** — acoplado a N09 gold sample  

## Itens DOD potencialmente impactados (após prova)

- § cobertura / provenance / success_zero  
- § entity matching residual  
- § encadeamento edital-contrato / semântica de valores  
- § recall / precisão / amostra-ouro  
- § análise documental  
- § execução retomável / packages  

Nenhum checkbox fechado apenas por esta matriz.
