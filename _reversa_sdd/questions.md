# Perguntas para validação humana — 2026-07-28

> answer_mode: **chat** (Tiago)  
> Prioridade para fechar gaps de auditoria.

| # | Pergunta | Impacto | Default se sem resposta | Status |
|---|----------|---------|-------------------------|--------|
| Q1 | W006 deve ser **corrigido** (alinhar compose) ou **redefinido** o watch (local postgis intencional)? | Regression vermelho | Manter 🔴 até decisão | ✅ **Respondida 2026-07-27** |
| Q2 | Specs SDD completas para `commercial_leads` / `budget_audit` / `ops` CONFENGE são prioridade agora ou só audit docs bastam? | Writer effort | Audit docs = suficiente neste ciclo | aberta |
| Q3 | Há dump/DSN de produção seguro para Data Master / row counts? | G02 | Continuar 🔴 lacuna runtime | aberta |
| Q4 | National intel e CMI podem ser citados em propostas a clientes sob qual claim class? | Risco comercial | intel_product + non-claim only | aberta |
| Q5 | doc_level **detalhado** (flowcharts por função) vale uma segunda passagem? | Esforço | Manter **completo** | aberta |

---

## Respondidas

| Item | Resposta |
|------|----------|
| **Q1 / W006** | **Unificar.** Local deve igualar o oficial; extensão vector obrigatória; persistência de dados no PC não importa (prod Netcup VPS). Ação: alinhar `docker-compose.local.yml` test-db a `docker-compose.yml` (`pgvector/pgvector:pg16` + volume). **Não** redefinir o watch para aceitar postgis+tmpfs. Veredito W006 após unificação: 🟢 (evidência nos compose do root). |
| Nível de documentação | **2 Completo** |
| Objetivo | Atualizar completa e profundamente documentos de auditoria Reversa |
