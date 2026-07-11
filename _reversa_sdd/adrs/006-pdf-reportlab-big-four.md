# ADR-006: ReportLab para PDFs Estilo Big Four

**Status:** Aceito
**Data:** 2026-07-10
**Decisor:** Tiago Sasaki
**Fonte:** `docs/architecture/architecture.md`, commit `ceecf7b`

---

## Contexto

Os relatórios de inteligência precisam ser apresentados ao decisor da Extra Construtora em formato profissional. O código original do smartlic.tech já usava ReportLab com 10K+ linhas de templates validados.

## Decisão

**Manter ReportLab para geração de PDFs. Não migrar para WeasyPrint, LaTeX ou HTML-to-PDF.**

## Justificativa

- Código existente validado (10K+ linhas de templates)
- Estética "Big Four" (consultorias como McKinsey, Deloitte) já implementada
- ReportLab dá controle preciso sobre posicionamento e tipografia
- Sem dependência de navegador headless ou LaTeX
- Single-user: performance de geração não é crítica

## Consequências

- ✅ PDFs com aparência profissional consistente
- ✅ Reaproveitamento de código existente
- ❌ ReportLab tem curva de aprendizado íngreme para novos templates
- ❌ Código de template verboso (Programmatic PDF)
