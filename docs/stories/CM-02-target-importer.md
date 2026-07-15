# CM-02 — Importador e Normalizador da Planilha de Alvos

**Epic:** EPIC-COVERAGE-MAX-200KM | **Onda:** 1 — Instrumentação
**Risk:** STANDARD | **Status:** Ready
**Asymmetric Score:** 85 | **Recall gain estimado:** 0% (instrumentação)

---

## Problema Econômico

A planilha "Extra - alvos de licitação. R-0.xlsx" é o golden dataset operacional,
mas não existe CLI para importá-la de forma idempotente e rastreável. O seed
`db/seed/001_sc_entities.py` existe, mas não oferece reconciliação, não detecta
mudanças entre versões da planilha e não produz artefatos de auditoria.

Sem importador versionado, cada atualização da planilha requer intervenção manual
e não há rastreabilidade de quais entes foram adicionados, removidos ou alterados.

## Hipótese

Um comando CLI que importa a planilha, detecta diffs contra o banco, registra a
versão e produz relatório de alterações resolve o problema de rastreabilidade e
permite automatizar a reconciliação (CM-03).

---

## Escopo (IN)

1. Comando `python scripts/opportunity_intel/cli.py targets import <planilha>`
2. Leitura da planilha com openpyxl (já usado no projeto)
3. Normalização dos campos: CNPJ (8 dígitos), IBGE (7 dígitos), coordenadas (decimal)
4. Upsert na tabela `sc_public_entities` (ON CONFLICT DO UPDATE)
5. Detecção de diffs: novas entidades, removidas, alteradas
6. Registro de versão da planilha (hash) e timestamp de importação
7. Relatório de alterações em `output/readiness/target-import-report.json`
8. Exit code: 0 (sucesso), 1 (erro técnico), 2 (planilha com problemas)

## Fora de Escopo (OUT)

- Atualização automática da planilha (ainda manual)
- Download da planilha de fonte externa
- Validação semântica dos dados (formato de CNPJ já é validado no seed existente)
- Geocodificação de entidades sem coordenadas (futuro CM-XX)

---

## Arquivos Prováveis

| Arquivo | Ação |
|---------|------|
| `scripts/opportunity_intel/cli.py` | Adicionar subcomando `targets import` |
| `scripts/opportunity_intel/target_importer.py` | NOVO — lógica de importação e diff |
| `db/migrations/043_target_import_log.sql` | NOVO — tabela de log de importação |
| `db/seed/001_sc_entities.py` | Refatorar para usar o novo importador |

## Dependências

- CM-01 (universo canônico confirmado) ✅
- PostgreSQL acessível
- openpyxl (já em requirements.txt)

---

## Critérios de Aceite

### AC-1: Importação idempotente
**Given** planilha com 2.085 entes e banco limpo
**When** executo `targets import` duas vezes
**Then** segunda execução não duplica registros e reporta "0 changes"

### AC-2: Detecção de novas entidades
**Given** banco com dados da versão anterior da planilha
**When** importo nova versão com 5 entes adicionais
**Then** relatório lista exatamente os 5 novos entes

### AC-3: Detecção de alterações
**Given** ente com CNPJ X no banco
**When** importo planilha onde mesmo CNPJ X tem novo município
**Then** registro é atualizado e diff é reportado

### AC-4: Normalização de campos
**Given** planilha com CNPJ "62.761.279" (com pontuação)
**When** importo
**Then** banco armazena "62761279" (apenas dígitos)

### AC-5: Relatório de auditoria
**Given** importação concluída
**When** verifico `output/readiness/target-import-report.json`
**Then** contém: spreadsheet_hash, imported_at, total_rows, new_count, updated_count, unchanged_count, errors[]

### AC-6: Exit code
**Given** planilha com 50 entes sem CNPJ
**When** executo com `--strict`
**Then** exit code = 2 e relatório lista os problemas

---

## Testes

1. **Unit:** `test_target_importer.py` — normalização de CNPJ, IBGE, coordenadas
2. **Unit:** diff detection com fixtures (2 entes alterados, 1 novo, 1 removido)
3. **Integration:** importa planilha real, verifica contagem = 2.085
4. **Integration:** segunda importação idêntica → zero changes

## Evidências Obrigatórias

- [ ] `output/readiness/target-import-report.json` gerado com sucesso
- [ ] `SELECT count(*) FROM sc_public_entities` = 2.085 após import
- [ ] Segunda execução: "0 changes detected"
- [ ] CNPJs normalizados (sem pontuação) no banco

---

## Rollback

```sql
-- Restaurar backup pré-importação ou reverter para seed original
DELETE FROM sc_public_entities;
-- Reexecutar seed original
python db/seed/001_sc_entities.py
```

## Comando de Validação

```bash
python scripts/opportunity_intel/cli.py targets import "Extra - alvos de licitação. R-0.xlsx"
python scripts/opportunity_intel/cli.py targets import "Extra - alvos de licitação. R-0.xlsx"  # segunda execução → 0 changes
python scripts/opportunity_intel/cli.py targets stats  # confirma 2.085 entes
```

---

## Definition of Done

- [ ] Comando `targets import` funcional
- [ ] Importação idempotente comprovada
- [ ] Relatório de diff gerado
- [ ] Testes unitários e de integração passando
- [ ] Lint e type check passando no arquivo novo
- [ ] Estado no banco: 2.085 entes, CNPJs normalizados
- [ ] State file AIOX atualizado

---

*CM-02 — AIOX Master Orion, 2026-07-15*
