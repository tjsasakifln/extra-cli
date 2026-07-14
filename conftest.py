"""Shared fixtures for the Extra Consultoria test suite.

Fixtures here are available automatically to all tests in ``tests/``
(pytest conftest discovery). Keep shared mock factories and reusable
fixtures that span multiple test modules.

Scope convention:
  - ``function`` (default) — fresh fixture per test (safest for mutating tests).
  - ``session`` — only for truly immutable fixtures (connection strings, etc.).
"""

from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Generic helper fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_pncp_item() -> dict[str, Any]:
    """A minimal valid PNCP API item for most transform tests."""
    return {
        "numeroControlePNCP": "98765432100001",
        "objetoCompra": "Aquisicao de equipamentos de informatica",
        "valorTotalEstimado": 150000.00,
        "modalidadeId": 5,
        "modalidadeNome": "Pregao Eletronico",
        "situacaoCompraNome": "Divulgado",
        "orgaoEntidade": {
            "razaoSocial": "Prefeitura Municipal de Florianopolis",
            "cnpj": "12345678000199",
            "esferaId": 3,
        },
        "unidadeOrgao": {
            "ufSigla": "SC",
            "municipioNome": "Florianopolis",
            "codigoMunicipioIbge": "4205407",
        },
        "dataPublicacaoPncp": "2026-07-10T10:00:00Z",
        "dataAberturaProposta": "2026-08-01T09:00:00Z",
        "dataEncerramentoProposta": "2026-08-15T18:00:00Z",
        "linkSistemaOrigem": "https://sistema-origem.example.gov/98765432100001",
    }
