"""Generate the final transparencia_config.yaml with all detected municipalities.

Merges:
- Pass 1: 64 Betha cities (atende.net)
- Pass 2: 10 Proprio cities (sc.gov.br) - verified, excluding false positives
- Legacy: existing manual entries not overwritten by detections
- Not found: 220+ cities listed as commented stubs
"""

import json
import sys
from collections import OrderedDict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.crawl.transparencia_crawler import _slugify

DATA_DIR = PROJECT_ROOT / "data"
CONFIG_PATH = PROJECT_ROOT / "config" / "transparencia_config.yaml"

# ── Load detection results ──

with open(DATA_DIR / "platform_detection_results_final.json") as f:
    final = json.load(f)

# ── Build full municipios dict ──

municipios = OrderedDict()

# Templates map
TEMPLATE_MAP = {
    "betha": "portal_transparencia_net",
    "ipam": "portal_transparencia_net",
    "egov": "e_gov_net",
    "proprio": "custom",
}

# 1. Pass 1: Betha cities
for d in final["detected_list_pass1"]:
    slug = d["slug"]
    municipios[slug] = {
        "nome": d["municipio"].title(),
        "ibge": d["ibge"],
        "portal_url": d["url"],
        "template": TEMPLATE_MAP.get(d["platform"], "custom"),
        "requires_js": False,
        "ativo": True,
    }

# 2. Pass 2: Proprio cities (verified)
proprio_municipios = {d["municipio"].strip().upper(): d for d in final["detected_list_pass2"]}

# Manually verified valid ones (Sombrio excluded - returns 500)
valid_proprio = [
    "ATALANTA", "BLUMENAU", "CHAPECO", "CRICIUMA", "GASPAR",
    "ICARA", "ITAJAI", "JOINVILLE", "LAGES", "URUBICI",
]

for d in final["detected_list_pass2"]:
    name = d["municipio"].strip().upper()
    if name in valid_proprio:
        slug = d["slug"]
        # Detect URL properly - some have different slug patterns
        url = d["url"]
        # Gaspar has portaltransparencia prefix, keep it
        municipios[slug] = {
            "nome": d["municipio"].title(),
            "ibge": d["ibge"],
            "portal_url": url,
            "template": "custom",
            "requires_js": False,
            "ativo": True,
        }

# 3. Keep manually configured entries that aren't in our detected set
# These were in the original config and may have working URLs we didn't test
manual_keep = {
    "florianopolis": {
        "nome": "Florianopolis",
        "ibge": "4205407",
        "portal_url": "https://florianopolis.e-gov.betha.com.br",
        "template": "e_gov_net",
        "requires_js": True,
        "wait_for": "div.lista-licitacoes",
        "ativo": True,
    },
    "sao-jose": {
        "nome": "Sao Jose",
        "ibge": "4216602",
        "portal_url": "https://sao-jose.atende.net/transparencia",
        "template": "portal_transparencia_net",
        "requires_js": True,
        "wait_for": "table.licitacao",
        "ativo": True,
    },
    "balneario-camboriu": {
        "nome": "Balneario Camboriu",
        "ibge": "4202008",
        "portal_url": "https://balneario-camboriu.e-gov.betha.com.br",
        "template": "e_gov_net",
        "requires_js": False,
        "ativo": True,
    },
    "tubarao": {
        "nome": "Tubarao",
        "ibge": "4218700",
        "portal_url": "https://tubarao.sc.gov.br",
        "template": "custom",
        "requires_js": False,
        "selectors": {"lista_licitacoes": "table.table-licitacoes"},
        "ativo": True,
    },
    "brusque": {
        "nome": "Brusque",
        "ibge": "4202909",
        "portal_url": "https://brusque.sc.gov.br",
        "template": "custom",
        "requires_js": False,
        "selectors": {"lista_licitacoes": "table.table-licitacoes"},
        "ativo": True,
    },
    "rio-do-sul": {
        "nome": "Rio do Sul",
        "ibge": "4214805",
        "portal_url": "https://riodosul.sc.gov.br",
        "template": "custom",
        "requires_js": False,
        "selectors": {"lista_licitacoes": "table.table-licitacoes"},
        "ativo": True,
    },
}

# Add manual entries that don't conflict with detected ones
for slug, entry in manual_keep.items():
    if slug not in municipios:
        municipios[slug] = entry

# ── Build the final config ──

config = OrderedDict()
config["# transparencia_config.yaml"] = "Auto-generated from batch platform detection"
config["# generated_at"] = final["generated_at"]
config["# summary"] = f"Total: {final['total']} | Detected: {len(municipios)} | Not found: {final['not_found']}"
config["# platforms"] = json.dumps(final["platforms"])

config["templates"] = {
    "portal_transparencia_net": {
        "name": "Portal Transparencia .NET",
        "description": "Template mais comum em municipios de SC — tabela .licitacao",
        "selectors": {
            "lista_licitacoes": "table.licitacao",
            "modalidade": "td:nth-child(2)",
            "data": "td:nth-child(1)",
            "objeto": "td:nth-child(3)",
            "orgao": "td:nth-child(4)",
            "valor": "td:nth-child(5)",
            "link": "a",
        },
    },
    "e_gov_net": {
        "name": "e-Gov .NET",
        "description": "Segundo mais comum — plataforma e-gov da Betha",
        "selectors": {
            "lista_licitacoes": "div.lista-licitacoes table",
            "modalidade": "td:nth-child(1)",
            "data": "td:nth-child(2)",
            "objeto": "td:nth-child(3)",
            "valor": "td:nth-child(4)",
            "link": "a",
        },
    },
    "custom": {
        "name": "Custom (HTML scraping especifico)",
        "description": "Template customizado — requer selectors definidos por municipio",
        "selectors": {},
    },
}

config["municipios"] = municipios

# ── Write to file ──

def dict_to_yaml(data, indent=0):
    """Custom YAML emitter with OrderedDict support and comments."""
    lines = []
    prefix = " " * indent

    if isinstance(data, OrderedDict):
        for key, value in data.items():
            if isinstance(key, str) and key.startswith("#"):
                # It's a comment/header
                comment_text = key.lstrip("#").strip()
                lines.append(f"{prefix}# {comment_text}")
            else:
                if isinstance(value, (dict, OrderedDict)):
                    lines.append(f"{prefix}{key}:")
                    lines.append(dict_to_yaml(value, indent + 2))
                elif isinstance(value, list):
                    lines.append(f"{prefix}{key}:")
                    for item in value:
                        lines.append(f"{prefix}- {item}")
                elif isinstance(value, bool):
                    lines.append(f"{prefix}{key}: {'true' if value else 'false'}")
                elif value is None:
                    lines.append(f"{prefix}{key}: null")
                else:
                    lines.append(f"{prefix}{key}: {value}")
    elif isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, OrderedDict)):
                lines.append(f"{prefix}{key}:")
                lines.append(dict_to_yaml(value, indent + 2))
            elif isinstance(value, list):
                lines.append(f"{prefix}{key}:")
                for item in value:
                    lines.append(f"{prefix}- {item}")
            elif isinstance(value, bool):
                lines.append(f"{prefix}{key}: {'true' if value else 'false'}")
            elif value is None:
                lines.append(f"{prefix}{key}: null")
            else:
                lines.append(f"{prefix}{key}: {value}")

    return "\n".join(lines)


yaml_str = dict_to_yaml(config)

# Add comment footer with not-found municipios
yaml_str += "\n\n# ── NAO ENCONTRADOS ({}) ──\n".format(final["not_found"])
for nome in final["not_found_list"]:
    slug = _slugify(nome)
    yaml_str += f"# {slug}:  # {nome.title()} — IBGE pendente, URL pendente\n"

# Backup original
if CONFIG_PATH.exists():
    backup = CONFIG_PATH.with_suffix(".yaml.bak")
    CONFIG_PATH.rename(backup)
    print(f"Backup saved: {backup}")

# Write new config
with open(CONFIG_PATH, "w", encoding="utf-8") as f:
    f.write(yaml_str)

total_entries = len(config["municipios"])
print(f"\nConfig written: {CONFIG_PATH}")
print(f"Active municipios in config: {total_entries}")
print(f"Not found (commented): {final['not_found']}")

# Summary by template
from collections import Counter

tmpl_counts = Counter(m["template"] for m in municipios.values())
print("\nTemplate distribution in config:")
for tmpl, count in tmpl_counts.most_common():
    print(f"  {tmpl}: {count}")

# Summary by platform
plat_counts = Counter()
for d in final["detected_list_pass1"]:
    plat_counts[d["platform"]] += 1
for d in final["detected_list_pass2"]:
    if d["municipio"].strip().upper() in valid_proprio:
        plat_counts[d["platform"]] += 1
for slug in manual_keep:
    plat_counts["manual"] += 1

print("\nPlatform distribution in config:")
for plat, count in plat_counts.most_common():
    print(f"  {plat}: {count}")
print(f"  TOTAL: {sum(plat_counts.values())}")
