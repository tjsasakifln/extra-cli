# Handoff — revisão humana Tiago (PENDING_HUMAN)

## Pacote principal (Leonardo)

**Path (VPS):** `/home/extra-consultoria/extra-deliveries/EXTRA-FIRST-CLIENT-DECISION-B2G-20260729/`

| Campo | Valor |
|-------|-------|
| run_id | extra-first-20260729T130300Z-5e2ff211cf |
| weekly | weekly-20260729T124604Z-3eff464362 (exit 0) |
| terminal_state | BUNDLE_READY_FOR_HUMAN_MERGE |
| shortlist | 6 (todos REVIEW) |
| GO | 0 (intake crítico PENDING) |
| deep_dive | 82575812000120-1-000299/2026 → https://pncp.gov.br/app/editais/82575812000120/2026/299 |
| human-review | **PENDING_HUMAN** — não preencher reviewed_by/decision automaticamente |

## Pacote recorrente

**Path:** `/home/extra-consultoria/extra-deliveries/EXTRA-RECURRING-20260729/`

- 52 eventos (47 contratos entrando na janela de vencimento; 5 NEW_WINNER)
- 47 alertas urgentes **e** relatórios semanal/mensal presentes

## Checklist de revisão (12 itens)

1. Data de corte 2026-07-29 correta?
2. Fontes críticas saudáveis (pncp opportunities/contracts = fresh)?
3. Editais shortlist realmente abertos?
4. Links oficiais PNCP funcionam?
5. Valores rotulados (estimado vs contratado)?
6. Nenhuma capacidade inventada da Extra?
7. Recomendações defensáveis (REVIEW only)?
8. Descartes com motivo (44 blocked)?
9. Limitações no PDF e Excel?
10. Decisões para Leonardo claras (intake + shortlist)?
11. Próximos passos com responsável/prazo?
12. Pacote apresentável sem código?

## 5 achados principais

1. Weekly pós-deploy exit 0 com universo canônico 1093.
2. 6 oportunidades em REVIEW; zero GO (campos financeiros/técnicos PENDING).
3. 47 contratos na janela de vencimento 180d — material de alerta operacional.
4. 5 mudanças de vencedor detectadas entre runs.
5. Pacote histórico exit_code=2 **não** é entrega; este pacote sim.

## Riscos da apresentação

- Comparação recorrente usa previous weekly de SHA antigo (ainda exit 0).
- Intervalo entre runs < 7 dias (prova de capacidade, não soak semanal).
- Dossiê de edital NOT_AVAILABLE (sem documentos baixados).

## Ações recomendadas

1. Tiago revisa PDF/Excel e preenche human-review.json manualmente.
2. Completar intake (capital_giro, garantia, CAT, margem) com Leonardo.
3. Agendar próxima weekly no timer (segunda 03:32) e regenerar recorrente D+7.
