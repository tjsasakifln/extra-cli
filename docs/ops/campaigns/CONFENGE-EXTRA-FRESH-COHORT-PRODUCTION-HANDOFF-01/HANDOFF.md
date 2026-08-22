# HANDOFF — CONFENGE-EXTRA-FRESH-COHORT-PRODUCTION-HANDOFF-01

## Veredito

`EXTRA_FRESH_COHORT_PRODUCED_AND_HANDED_OFF`

Producer fresco no host de record, feed privado `confenge.outreach.v1` com
**N=50**, exatamente uma `preferred_initial` por account, `PROBABILISTIC_OR_RISKY`
fora do conjunto, PII fora do Git, import canônico no Warmbly concluído.
`auto_send=false`. Nenhum e-mail saiu do extra-cli. Zero SMTP.

## O que foi executado

1. `origin/main` em `a58781da` (PR #447) recebeu o fail-closed de associação e a
   cascata de discovery via **PR #448**, squash-merge `a213e28d`.
2. Producer real: SHA executado `20e857b1` (mesma tree que `a213e28d`),
   `--use-activation-planner --activation-capacity 500 --allow-network
   --enable-web-search`, SearXNG privado, sem replay.
3. Universo: datalake PNCP, 4 426 908 contratos → 52 771 empresas de construção;
   hot set 500 `ACTIONABLE_NOW`; `as_of=2026-08-22`.
4. Cascata: site oficial / evidência pública / role / generic / freemail
   associado. Sem SMTP, sem send.
5. Feed privado em
   `/var/lib/extra-consultoria/private/outreach/cohorts/20260822T023405Z/confenge.outreach.v1.json`
   modo `0600`, SHA-256 `9e22699996d04b5a4d6c0324583bcba855205ae8ba82b04ec292b8729aca7c04`.
6. Import Warmbly: `confenge import --feed https://confenge-feed:8443/controlled-email-cohort-fresh.json`
   → `status=completed`, 50 leads processados, 0 erros.
7. Warmbly derivou `cohort_hash` / `recipient_set_hash` via `confenge cohort prepare --org-id`
   (não copiados à mão; não SQL).

## Funil (sem PII)

| Chave | Valor |
| --- | ---: |
| accounts considered | 500 |
| official domain | 321 |
| any public email | 122 |
| DIRECT_PERSON | 0 |
| ROLE_OR_DEPARTMENT | 21 |
| GENERIC_COMPANY | 91 |
| PUBLIC_COMPANY_FREEMAIL | 2 |
| RISKY | 121 |
| controlled eligible | 89 |
| preferred initial (capped) | 50 |
| no email | 378 |
| no domain | 179 |
| blocked | 430 |
| suppressed | 0 |
| double preferred | 0 |
| yield | 0.10 |
| as_of | 2026-08-22 |

Cohort extra-cli (N=50): GENERIC_COMPANY 38, ROLE_OR_DEPARTMENT 12.

O export nacional do pipeline falhou em `source_watermark` incompleto no snapshot
full-universe. O cohort bounded usou o hot set de 500 + `build_leads` / stamp
shipped. Não é replay histórico.

## Sample QA (estratificado, sem mailbox)

Amostra de 3 GENERIC + 3 ROLE. Em todos: `source_type` ∈ {`site`,`contact_page`},
`mailbox_company_evidence=OBSERVED`, URL não é unsubscribe, domínio da mailbox
coincide com o host da página. `official_host` do campo website do universo
estava vazio — isso não invalida evidência de site crawl. Nenhuma classe
bloqueada por erro sistemático.

Hosts públicos da amostra (não são e-mail): `encopav.com.br`, `novatec.com.br`,
`jatobeton.com.br`, `sinarco.com.br`, `supremaanalitica.com.br`,
`medvitalis.com.br`.

Warmbly, após import, aplicou gates próprios (`missing_provenance` / suppression)
e congelou 7 destinatários. Isso é o plano de envio do Warmbly, não o recorte
do extra-cli. O feed de 50 foi recebido.

## Hashes e SHAs

| Papel | Valor |
| --- | --- |
| merged extra-cli | `a213e28dab51e81f71505395e84bc4fa2366c6e4` |
| executed extra-cli | `20e857b1bdd774ac577a3db14316749738acb2cb` |
| trees iguais | sim |
| feed SHA-256 | `9e22699996d04b5a4d6c0324583bcba855205ae8ba82b04ec292b8729aca7c04` |
| Warmbly cohort_id | `controlled-afbd52e775a7` |
| Warmbly cohort_hash | `afbd52e775a77bf8fefbf362776e586f74a3189576d70d8c4ae26d875a1b1961` |
| Warmbly recipient_set_hash | `b06ebc8cb94a7da79aec5cb0a614b30879b0726b3d7893d81997370eef438cb6` |

## Testes

`python3 -m pytest tests/test_controlled_email_eligibility.py tests/test_email_reachability_engine.py tests/confenge_outreach_pipeline/test_pipeline.py tests/warmbly_bridge/ tests/confenge_contact_resolution/test_discovery_precision.py` → 123 passed. PR #448 `Test All` verde.

## Não aconteceu

- Envio de e-mail pelo extra-cli
- SMTP probe
- `auto_send=true`
- Commit de mailbox / PII
- Padding para 50
- RISKY no default
- SQL no Warmbly
