# ADR-015: Estágios Semânticos de Valor — Regra #8 (Deságio)

**Data:** 2026-07-12
**Status:** Aceito
**Autor:** Regra #8 — Deságio Reclassificado (commit 132df3e)
**Stakeholders:** Extra Consultoria

---

## Contexto

O sistema lida com valores financeiros de licitações em diferentes estágios do ciclo de vida:

- **PNCP bids:** `valor_total_estimado` — o que o governo ESPERA pagar
- **PNCP contracts:** `valor_global` — teto contratual máximo assinado
- **ComprasGov:** valor homologado por item/lote (não ingerido)
- **TCE/SC:** empenhos efetivos (não ingerido)

Inicialmente, `valor_global` do PNCP era tratado ambiguamente — ora como "preço praticado", ora como valor contratual. Isso gerava comparações inválidas: deságio calculado entre `valor_total_estimado` de um bid e `valor_global` de um contrato não relacionado.

## Decisão

Criar sistema de 5 estágios semânticos de valor, imutáveis e tipados:

| Estágio | Significado | Fonte |
|---------|------------|-------|
| `ESTIMADO` | Valor do edital — expectativa | PNCP bids |
| `HOMOLOGADO` | Valor homologado — resultado | ComprasGov |
| `CONTRATADO` | Valor contratual — teto assinado | PNCP contracts |
| `PAGO` | Valor pago — empenho efetivo | TCE/SC |
| `GLOBAL` | Total indiferenciado — NÃO usar como "preço" | PNCP default |

**Regra fundamental:** Deságio = `(ESTIMADO − HOMOLOGADO) / ESTIMADO`. Só é válido entre estágios da MESMA licitação. NUNCA entre `valor_global` e outro estágio sem verificar que representam a mesma entidade contratual.

**Mapeamento:** `SOURCE_VALUE_TYPES` mapeia cada `(source, entity_type)` ao seu `ValorSemantica`. Novas fontes devem declarar seu estágio semântico antes da ingestão.

## Consequências

- `valor_global` do PNCP é semanticamente `CONTRATADO` (teto assinado), NÃO "preço praticado"
- Cálculo de deságio invalidado entre estágios diferentes — `calculate_desagio()` retorna `None` para inputs inválidos
- Reclassificado como LIMITED: a regra existe mas fontes complementares (ComprasGov, TCE/SC) não estão ingeridas
- ComprasGov e TCE/SC documentados como futuras fontes no `SOURCE_VALUE_TYPES`
