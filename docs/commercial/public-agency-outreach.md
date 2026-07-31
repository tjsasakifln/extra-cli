# Outreach a órgãos públicos

## Regras

- Apenas contatos **institucionais públicos**
- Sem e-mail/telefone pessoal, dados familiares, perfis privados
- WhatsApp só se canal institucional oficialmente publicado
- **Nenhum disparo automático** — `outreach_sent` sempre false no ciclo

## Estados de relacionamento

`IDENTIFIED` → `RESEARCHED` → `HUMAN_REVIEW_REQUIRED` → `APPROVED_FOR_OUTREACH` → …

Bloqueios: `CONFLICT_BLOCKED`, `DO_NOT_CONTACT`, `DISQUALIFIED`

## Aprovação

Somente Tiago (ou operador autorizado) promove para `APPROVED_FOR_OUTREACH` após:

1. clearance de conflito documentado  
2. revisão de classificação jurídica se ambígua  
3. confirmação do contato em fonte pública  
4. revisão da mensagem (sem promessa de dispensa)
