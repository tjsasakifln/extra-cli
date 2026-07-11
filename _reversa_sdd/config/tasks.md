# Tasks — Módulo `config`

> 🟢 CONFIRMADO

### T1: Settings Module
- **Arquivo legado:** `config/settings.py`
- **Confiança:** 🟢
- **Descrição:** `os.getenv()` para todas as configs com defaults documentados. Paths absolutos via `Path(__file__).resolve()`. Auto-criação de diretórios de output.
- **Critério de pronto:** Todas as env vars mapeadas. Defaults sensíveis. Paths resolvidos.

### T2: Sectors Config YAML
- **Arquivo legado:** `config/sectors_config.yaml`
- **Confiança:** 🟢
- **Descrição:** 13 setores com schema completo. Loader Python (`intel_sector_loader.py`). Validação de schema na carga.
- **Critério de pronto:** 13 setores carregáveis. Loader funcional. Schema validado.

### T3: Abbreviations YAML
- **Arquivo legado:** `config/abbreviations.yaml`
- **Confiança:** 🟢
- **Descrição:** Dicionário extensível. `load_abbreviations_from_yaml()` em `name_normalizer.py` faz merge com built-in dict.
- **Critério de pronto:** YAML carregável. Merge funcional. Fallback para built-in.
