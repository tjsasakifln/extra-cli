# Scope boundaries — Extra Consultoria

Canonical configuration: `config/scope_boundaries.yaml`  
Auditors:

- `python3 -m scripts.ops.audit_scope_boundaries`
- `python3 -m scripts.ops.audit_client_claim_boundaries`

## Included (examples)

- Open tender + historical contract monitoring  
- **Administrative** contract monitoring (prazos, publicações, aditivos administrativos, vigência)  
- Decision support (`GO` / `REVIEW` / `NO_GO`)  
- Proposal organization support (human remains responsible)  
- Local CLI and file-based operation  

## Explicitly excluded (examples)

- Diário / medição / avanço físico de obra  
- Fiscalização de campo, fotos de canteiro, equipes de obra  
- Gestão de aditivos **de execução física** (≠ aditivo administrativo)  
- Portal da contratada, interface pública multi-usuário, multi-tenant  
- Cobrança / assinatura SaaS / Stripe  
- Kubernetes / Kafka / Redis / Elasticsearch sem necessidade comprovada  
- Assinatura ou protocolo automático sem ação humana  
- Assunção de responsabilidade técnica/jurídica/contábil/comercial  
- Substituição de advogado; representação presencial  
- Garantias, seguros, crédito  
- Promessas de habilitação / adjudicação / vitória / contratação  
- Execução do objeto contratado  

## Distinctions (mandatory)

| Allowed | Forbidden |
|---------|-----------|
| Monitor aditivo administrativo | Gerir aditivo físico de execução |
| Gerar documento para revisão | Assinar em nome da Extra |
| Preparar checklist de protocolo | Protocolar sem humano |
| HTML local / CLI | Interface pública SaaS |
| Análise factual de edital | Parecer jurídico conclusivo |

## Enforcement

Static auditors classify matches as implementation vs documentation/disclaimer/test/fixture.  
Client claim guard scans client-facing surfaces with exception rules for DOD text and negations.

This document does **not** claim absolute absence of risk—only that audited surfaces were checked under the stated rules.
