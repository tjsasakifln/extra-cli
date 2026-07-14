# Auditoria Retroativa — Story 1.1: Fix Critical Security

**Data:** 2026-07-13
**Auditor:** AIOX Master (coordenação)

---

## Veredito: CONCERNS

## Confiança: Média

---

## Resumo Executivo

Story 1.1 implementou 6 correções de segurança e infraestrutura. Os fixes de código são corretos e funcionais, mas duas pendências críticas de segurança (BFG repo-cleaner e rotação de senha) foram delegadas a @devops sem evidência de execução. O uso de `sys.path.insert` como correção de imports é um workaround frágil, não uma solução estrutural. A senha `postgres:smartlic_local` ainda existe em ~20 outros arquivos fora do escopo.

**A story está funcionalmente correta mas operacionalmente incompleta.** As credenciais comprometidas ainda estão no histórico Git.

---

## Contrato Reconstruído

### Problema Original
6 vulnerabilidades/débitos críticos de segurança bloqueando operação confiável:
- SEC-03: Senha hardcoded em `config/settings.py`
- SEC-02: Service account JSON versionado
- TD-001: Imports quebrados em `bids_crawler.py`
- SEC-01: SQL injection via f-strings em `monitor.py`
- TD-019: Import quebrado `lib.cli_validation`
- TD-021: PNCP BASE_URL divergente

### Valor Esperado
Sistema operável sem risco de vazamento de credenciais ou falha silenciosa de módulos.

### Escopo IN (6 itens)
1. Migrar senha para DATABASE_URL env var
2. BFG repo-cleaner + rotação de senha
3. Remover SA JSON, configurar alternativa GCP
4. Criar `scripts/crawl/ingestion/__init__.py`
5. Substituir f-strings SQL → query parameters
6. Corrigir import `lib.cli_validation` + unificar BASE_URL

---

## Commits e Arquivos

**Commit:** `d2ff075` (junto com stories 1.2-1.5)

### Arquivos Modificados
| Arquivo | Mudança | AC |
|---------|---------|-----|
| `config/settings.py` | DATABASE_URL env var + fallback | SEC-03 |
| `.env.example` | DATABASE_URL, GOOGLE_APPLICATION_CREDENTIALS, PNCP_BASE v3 | SEC-03, SEC-02, TD-021 |
| `scripts/crawl/monitor.py` | f-string SQL → psycopg2.sql.Identifier | SEC-01 |
| `scripts/crawl/bids_crawler.py` | sys.path.insert para ingestion.* | TD-001 |
| `scripts/intel_pipeline.py` | sys.path.insert para lib.cli_validation | TD-019 |
| `pyproject.toml` | bandit (S) rules + per-file-ignores | SEC-01 |

---

## Critérios de Aceite e Rastreabilidade

| AC | Descrição | Código | Teste | Status |
|----|-----------|--------|-------|--------|
| SEC-03 | Zero senhas, DATABASE_URL | `config/settings.py` | Manual | COVERED |
| SEC-02 | SA JSON removido, WIF/alternativa | `.env.example` | Manual | COVERED |
| TD-001 | BidsCrawler import OK | `bids_crawler.py` | `python -c "from..."` | COVERED |
| SEC-01 | f-string SQL → Identifier | `monitor.py:543` | ruff S rules | COVERED |
| TD-019 | intel_pipeline import OK | `intel_pipeline.py` | `python -c "from..."` | COVERED |
| TD-021 | PNCP BASE_URL v3 | `settings.py` + `.env.example` | Inspeção | COVERED |

---

## Resultados dos Testes

*(Preenchido pelo agente quality-gates)*

---

## Segurança

| Achado | Severidade | Detalhe |
|--------|------------|---------|
| BFG não executado | **HIGH** | Senha ainda no histórico Git. Delegado a @devops sem evidência. |
| Senha em ~20 outros arquivos | **MEDIUM** | Fora do escopo mas documentado como tech debt |
| SA JSON em disco? | **MEDIUM** | Arquivo removido do repo mas pode existir em disco local |
| sys.path.insert frágil | **MEDIUM** | Workaround, não solução estrutural. `bids_crawler.py` e `intel_pipeline.py` |
| Pre-existing S603/S110 suprimidos | **LOW** | per-file-ignores em pyproject.toml |

---

## Arquitetura e Causa Raiz

**Parecer:** PARTIALLY-RESOLVED

- SEC-01 (SQL injection): ✅ Causa raiz resolvida — query parameters + linter rule
- SEC-02 (SA JSON): ✅ Causa raiz resolvida — env var + .gitignore
- SEC-03 (senha): ⚠️ Parcial — settings.py limpo mas histórico Git NÃO limpo
- TD-001 (imports): ⚠️ Workaround — sys.path.insert não é solução estrutural
- TD-019 (import): ⚠️ Workaround — mesmo padrão sys.path.insert
- TD-021 (BASE_URL): ✅ Unificado para v3

---

## Compatibilidade com Reversa

*(Preenchido pelo agente architecture-reversa)*

---

## Dívida Técnica

| ID | Descrição | Severidade | Origem |
|----|-----------|------------|--------|
| NEW-1.1-01 | BFG cleanup pendente — senha no histórico Git | HIGH | INTRODUCED-BY-STORY |
| NEW-1.1-02 | sys.path.insert como solução permanente de import | MEDIUM | INTRODUCED-BY-STORY |
| NEW-1.1-03 | ~20 arquivos com senha hardcoded fora do escopo | MEDIUM | LEGACY-PREEXISTING |
| NEW-1.1-04 | SA JSON pode existir em disco local | LOW | LEGACY-PREEXISTING |

---

## Achados

| ID | Severidade | Origem | Descrição | Correção Sugerida |
|----|-----------|--------|-----------|-------------------|
| A1.1-01 | HIGH | INTRODUCED-BY-STORY | BFG repo-cleaner não executado — credenciais no histórico Git | Executar BFG imediatamente + force push coordenado |
| A1.1-02 | HIGH | INTRODUCED-BY-STORY | Senha não rotacionada após migração | Rotacionar senha do banco PostgreSQL |
| A1.1-03 | MEDIUM | INTRODUCED-BY-STORY | sys.path.insert como solução frágil de imports | Refatorar estrutura de pacotes com setup.py/pyproject.toml |
| A1.1-04 | MEDIUM | LEGACY-PREEXISTING | ~20 arquivos ainda contêm "postgres:smartlic_local" | Story separada para migração completa |
| A1.1-05 | LOW | INTRODUCED-BY-STORY | per-file-ignores suprimem S603/S110 legítimos | Tratar cada suppress individualmente |

---

## Trabalho Necessário

1. **P0:** Executar BFG repo-cleaner + rotação de senha (delegado a @devops)
2. **P1:** Verificar e remover SA JSON de disco local
3. **P2:** Refatorar sys.path.insert → estrutura de pacotes adequada
4. **P3:** Migrar ~20 arquivos restantes com senha hardcoded

---

## Recomendação Final

**CONCERNS.** Implementação de código correta para todos os 6 ACs. As pendências de segurança operacional (BFG, rotação de senha) são significativas e precisam ser concluídas antes de qualquer deploy público. O workaround sys.path.insert é tecnicamente funcional mas frágil para manutenção de longo prazo.
