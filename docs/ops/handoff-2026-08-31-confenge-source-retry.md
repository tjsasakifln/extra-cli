# Handoff: retry limitado da fonte CONFENGE

**Data:** 2026-08-31  
**Estado:** `VERIFIED` no branch; requer CI, merge e validação live para `ACCEPTED`

## Incidente

O ciclo PNCP das 08:00 BRT terminou `partial` depois de detectar mudança de
população durante a paginação. O serviço aguardaria o próximo slot de quatro
horas, enquanto a autoridade de freshness usada para nova publicação expirava.
O pipeline downstream permaneceu corretamente fechado, mas sem uma tentativa
curta de recuperação.

## Contrato implementado

- `0` continua sendo o único sucesso que aciona `OnSuccess`.
- `75` significa writer lock ocupado e não é sucesso nem condição de retry.
- `77` é emitido somente quando todos os erros observados são transitórios:
  source-population drift, timeout, conexão, rate limit ou HTTP 5xx.
- O systemd executa no máximo uma nova tentativa após cinco minutos dentro da
  janela de quatro horas. Códigos estruturais `1` e `2` não reiniciam.
- A cadeia permanece serial e só avança para o freshness gate depois de um
  resultado `0`.
- O pin imutável instala apenas as unidades-base versionadas da cadeia
  CONFENGE, preserva drop-ins e EnvironmentFiles, e só então aplica os
  drop-ins do release e faz `daemon-reload`.

O retry não transforma freshness vencida em aprovada e não altera a
`COMMERCIAL_AUTHORITY/2.0`. Integridade do last-good, saúde da fonte e
autoridade comercial continuam sinais separados.

## Verificação do branch

```text
pytest focado: 133 passed
ruff check: PASS
git diff --check: PASS
```

## Aceite live

Depois do merge, cortar e pinar o release imutável. Em seguida comprovar:

1. exit `77` mantém downstream parado;
2. uma única tentativa ocorre após cinco minutos;
3. exit `0` aciona freshness gate, target-fit, contact cycle e feed cycle;
4. exit `1`, `2` ou `75` não reinicia nem aciona downstream;
5. `pin_release.py verify <sha>` não encontra drift de unidade ou release.

