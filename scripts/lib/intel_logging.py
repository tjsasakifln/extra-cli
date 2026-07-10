"""Shared logging configuration for intel-busca pipeline scripts."""
from __future__ import annotations

import logging
import os
import sys


def setup_intel_logging(script_name: str, level: str | None = None) -> logging.Logger:
    """Configure logging for an intel script.

    Args:
        script_name: Name of the script (e.g., 'intel-collect')
        level: Override log level (DEBUG, INFO, WARNING, ERROR).
               Default: INFO, or INTEL_LOG_LEVEL env var.

    Returns:
        Configured logger instance.
    """
    log_level = level or os.environ.get("INTEL_LOG_LEVEL", "INFO")

    logger = logging.getLogger(f"intel.{script_name}")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.DEBUG)

        # Format: [intel-collect] INFO: message
        formatter = logging.Formatter(
            f"[{script_name}] %(levelname)s: %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
