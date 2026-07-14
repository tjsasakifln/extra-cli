# Resolucao da Raiz Duplicada 00394494

## Contexto

A planilha seed contem 4 entradas com o CNPJ-8 `00394494`:

| Row | Raza Social | Municipio | Raio 200km? |
|-----|------------|-----------|-------------|
| 907 | MINISTERIO DA JUSTICA E SEGURANCA PUBLICA | SANTA CATARINA | SIM |
| 2084 | SUPERINTENDENCIA REGIONAL DO DPF EM SANTA CATARINA | FLORIANOPOLIS | SIM |
| 2085 | SUPERINTENDENCIA REG.POL.RODOV.FED. EM SANTA CATARINA | FLORIANOPOLIS | SIM |
| 2086 | UNIVERSIDADE CORPORATIVA DA POLICIA RODOVIARIA FEDERAL | FLORIANOPOLIS | SIM |

## Analise

As 4 entradas representam **entidades juridicas legitima e distintas** dentro da mesma estrutura organizacional do Ministerio da Justica (CNPJ raiz 00394494):

1. **MINISTERIO DA JUSTICA E SEGURANCA PUBLICA** — orgao central, sede em BRASILIA mas cadastrado como "SANTA CATARINA" na planilha (provavelmente por atuacao no estado)
2. **SUPERINTENDENCIA REGIONAL DO DPF EM SANTA CATARINA** — unidade regional da Policia Federal em Florianopolis
3. **SUPERINTENDENCIA REG.POL.RODOV.FED. EM SANTA CATARINA** — unidade regional da Policia Rodoviaria Federal em Florianopolis
4. **UNIVERSIDADE CORPORATIVA DA POLICIA RODOVIARIA FEDERAL** — unidade de ensino/capacitacao da PRF em Florianopolis

## Decisao

**Nao ha duplicidade a resolver.** As 4 entidades sao entidades distintas e legitimas. O sistema ja as trata corretamente:

- O `CanonicalEntity.identity_key` combina `(cnpj8 | municipio_normalizado | razao_social_normalizada)`, produzindo 4 chaves unicas
- O `CanonicalEntity.duplicate_root` esta correto ao marcar `True` para todas (CNPJ-8 repetido funciona como alerta, nao como erro)
- O metodo `resolve_opportunity()` usa a cadeia completa de identidade para resolver ambiguiade, nunca apenas o CNPJ-8

## Acoes

1. Manter as 4 entradas na planilha seed (sao dados corretos da fonte)
2. Manter `duplicate_root = True` como flag de alerta no `CanonicalEntity`
3. Nao colapsar nem remover nenhuma das 4 entradas
4. Documentar esta decisao para referência futura

## Autor

Dex (Builder) — 2026-07-13
Aprovado via analise dos dados da seed `load_canonical_universe()`.
