"""Shared CLI argument validation helpers for intel-busca scripts.

All validators print a user-friendly error message to stderr and call
sys.exit(1) on failure.  They are intended to be called right after
argparse.parse_args() -- before any business logic runs.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from .constants import MAX_DIAS, MAX_PIPELINE_STEP, MAX_TOP, VALID_MODELS, VALID_UFS


def validate_cnpj(raw: str) -> str:
    """Validate and normalize a CNPJ string to 14 digits.

    Args:
        raw: CNPJ in any format (with dots, slashes, dashes, or plain digits).

    Returns:
        14-digit CNPJ string.

    Raises:
        SystemExit: If input doesn't contain exactly 14 digits after cleaning.
    """
    cleaned = re.sub(r"\D", "", raw)
    if len(cleaned) != 14:
        print(
            f"ERRO: CNPJ invalido: '{raw}' — deve conter exatamente 14 digitos "
            f"(encontrado {len(cleaned)}).",
            file=sys.stderr,
        )
        sys.exit(1)
    if not cleaned.isdigit():
        print(
            f"ERRO: CNPJ invalido: '{raw}' — deve conter apenas digitos.",
            file=sys.stderr,
        )
        sys.exit(1)
    return cleaned


def validate_ufs(raw: str) -> list[str]:
    """Validate and parse a comma-separated UF string.

    Args:
        raw: Comma-separated UF codes (e.g. "SC,PR,RS").

    Returns:
        List of valid, uppercase 2-letter UF codes.

    Raises:
        SystemExit: If any UF code is invalid or list is empty.
    """
    ufs = [u.strip().upper() for u in raw.split(",") if u.strip()]
    if not ufs:
        print("ERRO: --ufs nao pode ser vazio.", file=sys.stderr)
        sys.exit(1)
    invalid = [u for u in ufs if u not in VALID_UFS]
    if invalid:
        print(
            f"ERRO: UF(s) invalida(s): {', '.join(invalid)}. "
            f"UFs validas: {', '.join(sorted(VALID_UFS))}",
            file=sys.stderr,
        )
        sys.exit(1)
    return ufs


def validate_dias(dias: int) -> None:
    """Validate that --dias is a positive integer within range.

    Args:
        dias: Number of days for search period.

    Raises:
        SystemExit: If dias is not in [1, MAX_DIAS].
    """
    if dias < 1 or dias > MAX_DIAS:
        print(
            f"ERRO: --dias deve ser entre 1 e {MAX_DIAS} (recebido: {dias}).",
            file=sys.stderr,
        )
        sys.exit(1)


def validate_top(top: int, max_val: int = MAX_TOP) -> None:
    """Validate that --top is a positive integer within range.

    Args:
        top: Number of top items.
        max_val: Maximum allowed value.

    Raises:
        SystemExit: If top is not in [1, max_val].
    """
    if top < 1 or top > max_val:
        print(
            f"ERRO: --top deve ser entre 1 e {max_val} (recebido: {top}).",
            file=sys.stderr,
        )
        sys.exit(1)


def validate_input_file(path_str: str) -> Path:
    """Validate that --input file exists and is readable.

    Args:
        path_str: Path string from argparse.

    Returns:
        Resolved Path object.

    Raises:
        SystemExit: If file does not exist or is not a file.
    """
    p = Path(path_str)
    if not p.exists():
        print(f"ERRO: Arquivo nao encontrado: {p}", file=sys.stderr)
        sys.exit(1)
    if not p.is_file():
        print(f"ERRO: Caminho nao e um arquivo: {p}", file=sys.stderr)
        sys.exit(1)
    return p


def validate_input_json(path_str: str) -> Path:
    """Validate that --input is an existing file containing valid JSON.

    Args:
        path_str: Path string from argparse.

    Returns:
        Resolved Path object.

    Raises:
        SystemExit: If file does not exist, is not a file, or contains invalid JSON.
    """
    p = validate_input_file(path_str)
    try:
        with open(p, "r", encoding="utf-8") as f:
            json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERRO: JSON invalido em {p}: {e}", file=sys.stderr)
        sys.exit(1)
    return p


def validate_model(model: str) -> None:
    """Validate that --model is a known model name.

    Args:
        model: Model name string.

    Raises:
        SystemExit: If model is not in VALID_MODELS.
    """
    if model not in VALID_MODELS:
        print(
            f"ERRO: Modelo desconhecido: '{model}'. "
            f"Modelos validos: {', '.join(sorted(VALID_MODELS))}",
            file=sys.stderr,
        )
        sys.exit(1)


def validate_from_step(step: int) -> None:
    """Validate that --from-step is within the valid pipeline step range.

    Args:
        step: Step number (1-based).

    Raises:
        SystemExit: If step is not in [1, MAX_PIPELINE_STEP].
    """
    if step < 1 or step > MAX_PIPELINE_STEP:
        print(
            f"ERRO: --from-step deve ser entre 1 e {MAX_PIPELINE_STEP} (recebido: {step}).",
            file=sys.stderr,
        )
        sys.exit(1)
