# User Story — Pipeline de Inteligência

> 🟢 CONFIRMADO — `intel_pipeline.py`

## US1: Consultor analisa oportunidades para um CNPJ

**Como** Tiago Sasaki (Consultor de Inteligência),
**Quero** executar o pipeline de inteligência para um CNPJ da Extra Construtora,
**Para** identificar as melhores oportunidades de licitação e gerar relatório para o decisor.

### Cenário 1: Pipeline completo (caminho feliz)

- **Dado** que o CNPJ 01721078000168 está cadastrado e tem CNAEs de engenharia
- **Quando** executo `python scripts/intel_pipeline.py --cnpj 01721078000168 --ufs SC`
- **Então** o sistema coleta licitações das últimas 24h no DataLake
- **E** enriquece os dados cadastrais via BrasilAPI
- **E** classifica cada edital via LLM (SIM/NAO)
- **E** extrai documentos relevantes
- **E** analisa em 5 dimensões (HAB, FIN, GEO, PRAZO, COMP)
- **E** gera PDF e Excel em `output/`

### Cenário 2: CNPJ sem licitações no período

- **Dado** que não há licitações novas para o CNPJ nos últimos 3 dias
- **Quando** executo o pipeline
- **Então** o GATE 1 (Cobertura) retorna WARN
- **E** o relatório indica "Sem licitações no período" com data da última coleta

### Cenário 3: Edital irrelevante bloqueado

- **Dado** que um edital é de "material de limpeza" (cross_sector_exclusion)
- **Quando** o GATE 3 (LLM) processa o edital
- **Então** o edital é classificado como NAO
- **E** não avança para os stages seguintes
- **E** aparece na seção "Descartados" do relatório

---

## US2: Consultor gera panorama de mercado

**Como** Tiago Sasaki,
**Quero** visualizar o panorama de licitações de engenharia civil em SC,
**Para** entender tendências de mercado, sazonalidade e concorrência.

### Cenário 1: Panorama setorial

- **Dado** que existem licitações de engenharia nos últimos 90 dias
- **Quando** executo `python scripts/reports/panorama.py --setor engenharia --uf SC --dias 90`
- **Então** vejo volume por modalidade, top 20 municípios, heatmap mensal
- **E** vejo top fornecedores (concorrência)
- **E** posso exportar para Excel com `--output-excel`

---

## US3: Consultor monitora cobertura

**Como** Tiago Sasaki,
**Quero** saber quais órgãos SC não estão sendo monitorados,
**Para** ajustar crawlers ou adicionar fontes de dados.

### Cenário 1: Coverage report diário

- **Dado** que 2.085 órgãos SC estão cadastrados
- **Quando** o systemd timer `coverage-report.timer` dispara às 09:00 UTC
- **Então** o relatório mostra cobertura % por raio e por fonte
- **E** lista entidades descobertas no raio 200km
- **E** exit code 1 se houver uncovered (alerta)
