# Acervo técnico-operacional — EXTRA EMPREITEIRA LTDA.

Guia operacional da base de conhecimento **canônica e consultável** do extra-cli.

> **Não é base paralela em Markdown.** Os dados vivem em `data/extra_technical_acervo.json`.  
> Este documento apenas explica o modelo, os guardrails e como consultar.

## Fonte de verdade

| Artefato | Caminho |
|----------|---------|
| Store canônico | `data/extra_technical_acervo.json` |
| Módulo | `scripts/technical_acervo/` |
| CLI | `python -m scripts.technical_acervo` |
| Testes | `tests/test_technical_acervo.py` |

## Contagens canônicas (seed atual)

| Entidade | Qtd | Notas |
|----------|-----|--------|
| CAT | **7** | Certidões distintas |
| CAO | **1** | nº 7-250004663-6 — **vencida** em 24/05/2025 |
| Experiências | **8** | Inclui São José (somente CAO) |
| Arquivos CAT | 8 PDFs | `arquivo5` ≡ `arquivo8` (mesma CAT 252025174528) |

## Separação conceitual (obrigatória)

| Conceito | Uso no sistema |
|----------|----------------|
| **Documento** | CAT, CAO ou ATESTADO (`technical_documents`) |
| **Experiência/obra** | Obra com período, contratante e itens (`technical_experiences`) |
| **ART** | Número(s) vinculados ao documento/experiência |
| **CAT** | Acervo técnico-profissional (com ou sem atestado registrado) |
| **CAO** | Histórico/capacidade **operacional** — **não** substitui CAT/atestado |
| **Atestado vinculado** | Flag `has_registered_attestation` na CAT |
| **Capacidade técnico-profissional** | RT (ex.: Guilherme Pereira de Andrade, CREA-SC 134481-6) |
| **Histórico operacional da PJ** | CAO + ressalvas de validade e finalidade |

**Regras de ouro**

1. CAT profissional **não** é prova irrestrita de capacidade operacional da PJ.
2. CAO **não** substitui CAT nem atestado registrado.
3. **Não somar** quantitativos de obras distintas por padrão (`allow_sum=false`).
4. Campos incertos ficam nulos + `review_required` / `review_flags` + fonte/página.
5. Quantidades: valor normalizado + unidade + texto original + página.
6. Sem CPF / data de nascimento em chunks, embeddings ou respostas normais.

## Deduplicação

Critérios: número da certidão, ART, hash de arquivo (quando disponível), aliases de origem.

Exemplo: `arquivo5.pdf` e `arquivo8.pdf` → **um** documento CAT nº **252025174528**, com ambos em `source_files` / `duplicate_aliases`.

## CAO — flags obrigatórias

- Status: `expired` (validade interna **2025-05-24**).
- Emissão interna: **2025-04-24** 14:21 (prevalece sobre o nome do arquivo).
- Nome de arquivo preservado: `Certidão Acervo Operacional emitida em 02-06-2026.pdf`.
- Review flag: `source_filename_date_conflicts_with_document_content`.
- O documento declara **não** ter finalidade de registrar atestado para concorrências públicas.
- Pode integrar **histórico operacional**; **não** apresentar como prova atual de habilitação.

## Experiência só-CAO

**Restauração – Centro Histórico de São José** (`exp-sao-jose-tombada-2024`):

- `evidence_level: operational_certificate_only`
- `individual_cat_not_provided: true`
- Não afirmar CAT individual disponível.

## CNPJ

- No atestado/documento de acervo: **24.515.663/0001-49**
- No perfil Extra versionado: **24.515.063/0001-49**
- Conflito registrado em `organizations[].cnpj_profile_conflict` com `review_required` — **não** sobrescrever o perfil em silêncio.

## CLI

```bash
# Inventário e integridade
python -m scripts.technical_acervo inventory

# Listar
python -m scripts.technical_acervo list
python -m scripts.technical_acervo list --type CAT

# Lookup
python -m scripts.technical_acervo show --cat 252025173593
python -m scripts.technical_acervo show --art 10023860-0
python -m scripts.technical_acervo show --cao 7-250004663-6
python -m scripts.technical_acervo show --file arquivo5.pdf

# Busca
python -m scripts.technical_acervo search "estrutura metalica" --min-qty 500 --unit m2
python -m scripts.technical_acervo search "prevenção contra incêndio"
python -m scripts.technical_acervo search "edificação tombada" --experiences-too

# Experiências
python -m scripts.technical_acervo experiences --contractor Cobasi
python -m scripts.technical_acervo experiences --cao-only

# Exigência de edital (sem somatório automático)
python -m scripts.technical_acervo match --service "estrutura metalica" --qty 500 --unit m2
python -m scripts.technical_acervo match --service "estrutura metalica" --qty 2000 --unit m2 --allow-sum

# Linguagem natural
python -m scripts.technical_acervo ask "A Extra possui acervo de estrutura metálica acima de 500 m²?"
python -m scripts.technical_acervo ask "A CAO está válida?"
python -m scripts.technical_acervo ask "arquivo5 e arquivo8 são documentos diferentes?"
python -m scripts.technical_acervo ask "Quais serviços estão comprovados somente por CAO?"

# Matriz e chunks
python -m scripts.technical_acervo matrix
python -m scripts.technical_acervo chunks --limit 20
```

Toda saída relevante inclui **documento, número, ART, quantitativo, unidade, fonte, página e ressalvas**, além do disclaimer de evidência vs parecer jurídico.

## Integração no monorepo

- **extra_ledger** (`data/extra_ledger.json` / `scripts/extra_ledger`): ledger comercial (oportunidades, propostas, contratos). O acervo técnico é módulo **irmão** de conhecimento documental — não mistura decisões comerciais com quantitativos de CAT.
- **perfil Extra** (`config/client_profiles/extra.yaml`): `cats_atestados` permanece **PENDING** até elicitação humana de habilitação; o store de acervo **não** marca automaticamente capacidade operacional como SET.
- **claim_language** (`scripts/lib/claim_language.py`): alinhado aos guardrails anti-overclaim; respostas de acervo usam disclaimer explícito.

## Testes

```bash
python3 -m pytest tests/test_technical_acervo.py -q --tb=short
```

Cobre as 15 checagens de aceite do OBJECTIVE (contagens, dedup, quantitativos-chave, tombada, CAO, PII, no auto-sum, proveniência, CLI real).

## Limitações remanescentes

- Seed canônico do OBJECTIVE (não OCR runtime dos PDFs).
- Hashes de arquivo só se os PDFs estiverem no workspace.
- Embeddings/pgvector opcionais **não** são gate; busca determinística + sinônimos basta.
- Resposta de `match` **nunca** afirma habilitação jurídica absoluta.
