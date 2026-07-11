# Lacunas — Extra Consultoria

> Gerado pelo Reviewer em 2026-07-11T17:00:00Z
> doc_level: completo

---

## Lacunas por Severidade

### 🟡 Moderado (5)

| ID | Lacuna | Unit(s) afetada(s) | Impacto |
|----|--------|-------------------|---------|
| G1 | `deploy/design.md` e `docs/design.md` não gerados | deploy, docs | Baixo — módulos simples, requirements + tasks suficientes |
| G2 | `intel_pipeline.py` usa `subprocess.run()` — dependência não declarada em `spec-impact-matrix.md` | intel, crawl | Médio — pode gerar falsos negativos em análise de impacto |
| G3 | Funções de scripts `intel_*.py` marcadas como 🟡 "inferred" — apenas `intel_pipeline.py` foi lido por completo | intel | Médio — detalhes de implementação podem divergir |
| G4 | Cobertura de testes <30% documentada mas sem recomendações específicas de quais módulos priorizar | Todos | Médio — plano de testes ausente |
| G5 | `c4-components.md` lista `subprocess.run` entre componentes mas `design.md` do intel não detalha o contrato de comunicação entre processos | intel | Baixo — contrato implícito via CLI args |

### 🟢 Cosmético (3)

| ID | Lacuna | Unit(s) afetada(s) |
|----|--------|-------------------|
| G6 | Nomes de arquivos nos fluxogramas usam `.py` mas poderiam usar nomes lógicos | crawl, intel |
| G7 | `user-stories/` cobre pipeline e panorama, mas não cobre deploy e manutenção | user-stories |
| G8 | `openapi/` não foi gerado — sistema não expõe API REST (decisão arquitetural correta, mas faltou nota explicativa) | openapi |

---

## Arquivos Faltantes por Unit

| Unit | requirements.md | design.md | tasks.md |
|------|:---:|:---:|:---:|
| crawl | ✅ | ✅ | ✅ |
| intel | ✅ | ✅ | ✅ |
| reports | ✅ | ✅ | ✅ |
| lib | ✅ | ✅ | ✅ |
| config | ✅ | ✅ | ✅ |
| db | ✅ | ✅ | ✅ |
| deploy | ✅ | ❌ | ✅ |
| docs | ✅ | ❌ | ✅ |

---

## Recomendações

1. **Preencher `deploy/design.md` e `docs/design.md`** — baixa prioridade, módulos simples
2. **Refatorar `intel_pipeline.py`** — substituir `subprocess.run()` por imports diretos (elimina G2 e G5)
3. **Adicionar testes** — prioridade: crawl > intel > reports (módulos com mais lógica de negócio)
4. **Adicionar `openapi/README.md`** — explicar que o sistema é CLI-only, sem REST API
