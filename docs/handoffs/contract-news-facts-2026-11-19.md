# Handoff: fatos para notícias de contratos, 2026-11-19

## Estado e escopo

`IMPLEMENTED + FIXTURE_PROVEN`. Não há afirmação de execução VPS, publicação
real ou recorrência nesta entrega. O produtor recebe identidades da base já
persistida e confirma somente detalhes oficiais, com limite de vinte consultas.

O modo operacional lê o Radar existente sem credencial de PostgreSQL, novo
grant ou root. O workflow de `web-cfg` executará um bundle fixado em SHA aprovado
com o usuário de deploy e diretórios privados/públicos sob
`/var/lib/confenge-web/contract-news`. A rotina e o checkout de ingestão não são
alterados. Fonte e ranking conservam a distinção entre valor contratado e
heurística histórica de seleção.

## Evidência local

- Testes focados cobrem semântica oficial, limite de consultas, correção de
  registros antigos, dados pessoais, identidades, datas, valores, falhas HTTP,
  escrita atômica e concorrência.
- O teste de integração SQLite cria uma projeção com o produtor `market_radar`
  existente e a consome com o novo leitor; valida digest, schema, idade,
  permissões, identidade e ausência de escrita no snapshot.
- Nenhum teste de fixture substitui consulta real ao PostgreSQL de produção,
  disponibilidade externa do PNCP, segredo OpenAI ou execução agendada.
- O bundle é produzido sem `site-packages`, com manifesto de SHA-256 por arquivo
  e conferência dos bytes contra o commit selecionado.

Comandos reproduzíveis:

```bash
python -m pytest tests/public_exports/test_contract_news.py -q -o addopts=''
python -m ruff check scripts/public_exports/contract_news.py \
  scripts/public_exports/package_contract_news.py \
  tests/public_exports/test_contract_news.py
python -m scripts.ops.check_generated_artifacts_policy --base origin/main
python -m scripts.ops.check_pr_reviewability --base origin/main
```

## Gates restantes

1. Revisão independente e CI do SHA exato da PR do produtor.
2. Consumidor e agendamento web com o SHA aprovado, preservando proteção de
   ambiente e concorrência com deploy.
3. Preflight autorizado no ambiente: leitura do Radar, escrita nos diretórios
   já permitidos, Python e existência da configuração OpenAI, sem divulgar
   valores secretos.
4. Exportação e publicação reais com recibos de origem, seguida de execução
   agendada observada. Somente essa evidência permite avançar o claim de operação.

Contrato: `docs/contracts/contract-news-facts-v1.md`.
Decisão: `docs/architecture/adr-contract-news-facts.md`.
