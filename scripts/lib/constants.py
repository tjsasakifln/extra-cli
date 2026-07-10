"""Shared constants for the intel-busca pipeline.

Provides canonical validation sets and version info used across all
intel-* CLI scripts.
"""
from __future__ import annotations

VALID_UFS = frozenset([
    'AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO',
    'MA', 'MG', 'MS', 'MT', 'PA', 'PB', 'PE', 'PI', 'PR',
    'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO',
])

INTEL_VERSION = '4.1.0'

VALID_MODELS = frozenset([
    'gpt-4.1-nano', 'gpt-4.1-mini', 'gpt-4.1',
    'gpt-4o-mini', 'gpt-4o',
])

MAX_DIAS = 365
MAX_TOP = 100
MAX_PIPELINE_STEP = 7
