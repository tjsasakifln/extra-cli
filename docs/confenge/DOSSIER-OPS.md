# Dossiê B2G — runbook operacional

Motor: `scripts/dossier/`. Contrato: [`docs/contracts/confenge-dossier-v1.md`](../contracts/confenge-dossier-v1.md).
Oferta ligada: `CFG-DIAG-EXP-v1` (Diagnóstico B2G de Expansão).

## Produzir um dossiê

```bash
export DATABASE_URL="postgresql://…/pncp_datalake"   # ou LOCAL_DATALAKE_DSN
make dossier CNPJ=00820854000114
# equivalente:
python3 -m scripts.dossier build --cnpj 00820854000114 --out artifacts/dossier/00820854000114
python3 -m scripts.dossier verify --dir artifacts/dossier/00820854000114
```

Saída em `artifacts/dossier/<CNPJ>/`:

| Arquivo | Destino | Contém a empresa? |
| --- | --- | --- |
| `dossier.json` | entrega paga | sim |
| `dossier.md` | entrega paga, documento humano | sim |
| `public-read.json` | página pública no web-cfg | não |
| `manifest.json` | referência no Warmbly | só hashes |

`verify` recalcula os hashes, revarre por afirmação proibida e compara cada
valor privado contra o corpo público. Um dossiê que não passa no `verify` não
sai da máquina.

## Publicar a projeção pública

```bash
make dossier-handoff DOSSIER_OUT=artifacts/dossier/00820854000114
```

Escreve em `${CONFENGE_HANDOFF_DIR:-~/.local/share/confenge/handoffs}/confenge-dossier/official-live-01/`
com `READY.json` **ou** `BLOCKED.json` e `SHA256SUMS.txt`. Só
`public-read.json` atravessa. `READY` exige `official_live` **e** `DATA_READY`
**e** `publication_readiness=DATA_READY`; qualquer outra coisa é `BLOCKED`.

Do lado do consumidor (`web-cfg`):

```bash
python3 -m scripts.market_panorama build
```

A página nasce `noindex`. INDEX é decisão editorial do web-cfg, aprovada
individualmente e vinculada ao hash do payload.

## Códigos de saída do `build`

| Código | Significado |
| --- | --- |
| `0` | ok |
| `2` | sem DSN (`--dsn`, `DATABASE_URL` ou `LOCAL_DATALAKE_DSN`) |
| `3` | conteúdo com afirmação proibida — nada foi escrito |
| `4` | `--strict` e o estado não é `DATA_READY` |
| `5` | `DATA_REJECT` |

`handoff` acrescenta `6` (vazamento de identidade detectado antes de escrever)
e `7` (o rendezvous escrito não passou na própria verificação).

## Quando o estado não é `DATA_READY`

`DATA_HOLD` e `DATA_REJECT` são respostas honestas, não falhas do processo.
Leia `reason_codes` no `manifest.json`:

| Código | O que fazer |
| --- | --- |
| `identity_not_found` | o CNPJ não está no `supplier_registry`; conferir o número |
| `no_canonical_contracts` | a empresa não tem contrato canônico no DataLake |
| `insufficient_contracts` / `insufficient_buyers` | carteira pequena demais para o diagnóstico prometido |
| `no_price_reference` | nenhuma categoria com painel comparável |
| `focal_outside_panel_range` | há categoria fora da faixa; a posição percentílica é omitida de propósito |
| `no_open_opportunities_for_buyers` | nenhum edital aberto observado; ausência de observação não é ausência de edital |
| `official_table_missing` | a view esperada não existe no DSN apontado |

Nenhum desses códigos autoriza preencher o vazio à mão. O documento declara o
que não sabe.

## Produção

O motor é somente-leitura sobre o DataLake e não escreve em nenhuma tabela.
No host de record:

```bash
ssh ec-prod "cd /opt/extra-consultoria && DATABASE_URL=\$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-) \
  python3 -m scripts.dossier build --cnpj <CNPJ> --out artifacts/dossier/<CNPJ>"
```

Não há timer para isso: um dossiê é produzido quando há uma conta para
diagnosticar, não em ciclo.

## Limites que o motor impõe e não se deve contornar

- `UNKNOWN` nunca vira zero, e `valued_count` acompanha `contract_count` para
  que uma soma parcial não seja lida como total.
- Um `fixture` nunca pode se declarar `official_live`.
- Concorrentes vêm da categoria **principal** da empresa; dividir comprador não
  basta, uma prefeitura compra papel e asfalto da mesma lista.
- Onde a mediana da empresa fica mais de 10x fora da faixa interquartil do
  painel, nenhuma posição percentílica é declarada e nenhum achado é emitido.
- Achado é fato mais pergunta. O dossiê não afirma direito, desequilíbrio
  econômico-financeiro, dano ou que um reajuste seja devido.
