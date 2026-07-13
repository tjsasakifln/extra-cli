---
story_id: B2G-1
status: draft
priority: P0
epic: EPIC-MASTER-B2G-READINESS
agent: @dev
depends_on: []
---

# Story B2G-1: Resolver 604 Entidades Nao Resolvidas

## Context

O coverage_manifest atual (2026-07-12) reporta **604 entidades nao resolvidas** — linhas da planilha seed (`Extra - alvos de licitacao. R-0.xlsx`) que nao possuem coordenadas (latitude/longitude). Sem coordenadas:

1. Nao e possivel calcular distancia Haversine ate Florianopolis
2. Nao e possivel confirmar se estao dentro do raio de 200km
3. Sao contadas como "unresolved" no denominador — bloqueiam coverage >=95%
4. A regra explicita do projeto diz: "Nenhuma linha sem coordenadas pode sumir silenciosamente"

O BLoqueio atual: **coverage = 64.4%** (1.093/1.697). Os 604 unresolved impedem qualquer target de coverage >=95%.

### Causa Raiz

A planilha seed tem 2.085 linhas, mas apenas ~1.481 tem coordenadas preenchidas. As 604 restantes tem nome do municipio e/ou CEP, mas nao latitude/longitude. O geocode atual depende de coordenadas na planilha — nao consulta automaticamente API externa.

### Abordagem

1. Extrair municipio de cada entidade sem coordenadas (coluna `municipio` na planilha)
2. Consultar IBGE API de localidades (`https://servicodados.ibge.gov.br/api/docs/localidades`) para obter latitude/longitude do municipio
3. Alternativa: usar `kelvins/Municipios-Brasileiros` dataset (github) como fallback local
4. Atualizar planilha Excel com coordenadas obtidas
5. Recarregar `sc_public_entities` no PostgreSQL
6. Reprojetar coverage evidence — confirmar quantas entidades caem dentro do raio 200km
7. Verificar se coverage>=95% e atingivel apos resolucao

## Acceptance Criteria

1. **AC1: Diagnostico completo** — Script analisa as 604 entidades e determina quantos municipios unicos estao representados, quantos ja tem coordenadas via IBGE API, e quantos exigem fallback manual
2. **AC2: Geocode via IBGE API** — Para cada municipio sem coordenadas, consulta IBGE API e extrai latitude/longitude. Implementado em `scripts/geocode/ibge_geocoder.py`
3. **AC3: Fallback dataset local** — Para municipios nao encontrados na IBGE API, usar dataset `kelvins/Municipios-Brasileiros` como fallback. Implementado em `scripts/geocode/fallback_geocoder.py`
4. **AC4: Fallback logico** — Para entidades onde nem IBGE nem dataset local resolvem, usar coordenadas do municipio-sede (mesma logica de "centro do municipio"). Documentar explicitamente como "aproximacao"
5. **AC5: Planilha atualizada** — Script atualiza a planilha `Extra - alvos de licitacao. R-0.xlsx` com as coordenadas obtidas (nova aba ou colunas atualizadas), preservando backup original
6. **AC6: sc_public_entities recarregado** — Tabela `sc_public_entities` e truncada e recarregada com dados atualizados (coordenadas preenchidas)
7. **AC7: Coverage reprojetado** — `monitor.py --report-coverage` executa com zero entities unresolved e coverage >=95% OU relatorio claro do novo denominador
8. **AC8: Testes** — `pytest tests/test_geocode.py -v` passa com mocks da IBGE API
9. **AC9: Ruff check** — `ruff check scripts/geocode/` passa sem erros
10. **AC10: Relatorio final** — Documento com: qtd resolvidas por metodo, qtd dentro/fora do raio apos geocode, novo coverage %, entidades que permanecem unresolved (se houver) com justificativa

## Technical Design

### Arquivos a criar

- `scripts/geocode/__init__.py` — Pacote geocode
- `scripts/geocode/ibge_geocoder.py` — Consulta IBGE API de localidades
- `scripts/geocode/fallback_geocoder.py` — Fallback com dataset local
- `scripts/geocode/seed_updater.py` — Atualiza planilha Excel + recarrega sc_public_entities
- `scripts/geocode/cli.py` — CLI para executar geocode: `python scripts/geocode/cli.py --resolve --reload`
- `tests/test_geocode.py` — Testes unitarios com mock da IBGE API

### Arquivos a modificar

- `scripts/local_datalake.py` — Adicionar comando `resolve-entities` se aplicavel

### Fluxo

```
1. Ler planilha seed (todas as 2.085 linhas)
2. Identificar 604 entidades sem coordenadas
3. Agrupar por municipio unico
4. Para cada municipio:
   a. Consultar IBGE API (codigo IBGE do municipio -> coordenadas)
   b. Se falhar, usar fallback dataset local
   c. Se falhar, usar coordenada do municipio-sede
5. Atualizar DataFrame em memoria
6. Salvar planilha com coordenadas (preservar original como .bak)
7. Conectar ao PostgreSQL e recarregar sc_public_entities
8. Executar coverage report
9. Gerar relatorio final
```

### IBGE API

Endpoint: `https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{codigo_ibge}`

Resposta esperada:
```json
{
  "id": 4205407,
  "nome": "Florianopolis",
  "microrregiao": {
    "mesorregiao": {
      "UF": { "sigla": "SC", "nome": "Santa Catarina" }
    }
  },
  "latitude": -27.5969,
  "longitude": -48.5495
}
```

Ou buscar por nome: `https://servicodados.ibge.gov.br/api/v1/localidades/municipios?nome={nome}`

Depois extrair coordenadas do resultado — a API retorna `latitude` e `longitude` como floats.

## Files to Create/Modify

- **CREATE** `scripts/geocode/__init__.py`
- **CREATE** `scripts/geocode/ibge_geocoder.py`
- **CREATE** `scripts/geocode/fallback_geocoder.py`
- **CREATE** `scripts/geocode/seed_updater.py`
- **CREATE** `scripts/geocode/cli.py`
- **CREATE** `tests/test_geocode.py`
- **MODIFY** `Extra - alvos de licitacao. R-0.xlsx` (coordenadas atualizadas)

## Rollback

- Backup da planilha original salvo como `Extra - alvos de licitacao. R-0.xlsx.bak`
- Script de rollback: `scripts/geocode/rollback.py` restaura backup e recarrega dados originais
- `sc_public_entities` recarregavel do backup via `monitor.py --reload-entities`

## Observability

- Log estruturado em `logs/geocode-{timestamp}.log`
- Relatorio salvo em `output/geocode/relatorio-final.md`
- Coverage manifesto regenerado automaticamente apos reload

## Security Considerations

- IBGE API e publica, sem autenticacao — sem risco de vazamento
- Planilha seed sem dados sensiveis (apenas CNPJ, razao social, municipio)
- Backup da planilha mantido no mesmo diretorio — garantir que .bak nao seja versionado (.gitignore)

## Tests

- `test_ibge_geocoder_success` — Mock de resposta bem-sucedida da IBGE API
- `test_ibge_geocoder_not_found` — Mock de 404 da API
- `test_fallback_geocoder` — Teste com dataset local
- `test_seed_updater` — Teste com planilha temporaria
- `test_full_pipeline` — Integracao: geocode -> update -> reload (com PostgreSQL test)

## Definition of Done

- [ ] AC1 a AC10 implementados e verificados
- [ ] `ruff check scripts/geocode/` retorna 0 erros
- [ ] `pytest tests/test_geocode.py -v` retorna all passed
- [ ] Coverage manifesto apos execucao mostra `unresolved = 0`
- [ ] Relatorio final gerado em `output/geocode/relatorio-final.md`
