"""Declarative capability model."""

from __future__ import annotations

import importlib
import shutil
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

from scripts.command_center.config import REPO_ROOT


class RiskLevel(StrEnum):
    READ = "read"
    WRITE_LOCAL = "write_local"
    HUMAN_DECISION = "human_decision"
    DESTRUCTIVE = "destructive"


class Availability(StrEnum):
    AVAILABLE = "available"
    MISSING_MODULE = "missing_module"
    MISSING_DEPS = "missing_deps"
    DISABLED = "disabled"


@dataclass
class ParamSpec:
    name: str
    label: str
    type: str = "string"  # string|int|bool|path|select|textarea
    required: bool = False
    default: Any = None
    description: str = ""
    example: str | None = None
    choices: list[str] | None = None
    advanced: bool = False
    sensitive: bool = False


@dataclass
class Capability:
    id: str
    name: str
    description: str
    category: str
    argv_builder: Callable[[dict[str, Any]], list[str]]
    params: list[ParamSpec] = field(default_factory=list)
    required_env: list[str] = field(default_factory=list)
    required_modules: list[str] = field(default_factory=list)
    output_roots: list[str] = field(default_factory=list)
    risk: RiskLevel = RiskLevel.READ
    requires_confirmation: bool = False
    confirmation_phrase: str | None = None
    allow_cancel: bool = True
    docs: list[str] = field(default_factory=list)
    timeout_sec: int | None = None
    fixture: bool = False
    expected_pr: str | None = None
    parse_result: Callable[[int, str, str, dict[str, Any]], dict[str, Any]] | None = None

    def detect_availability(self) -> tuple[Availability, str | None]:
        if self.fixture:
            return Availability.AVAILABLE, None
        for mod in self.required_modules:
            try:
                importlib.import_module(mod)
            except Exception:
                # Also accept file path presence for scripts packages
                pathish = REPO_ROOT / Path(*mod.split("."))
                if pathish.with_suffix(".py").exists() or (pathish / "__init__.py").exists() or (pathish / "__main__.py").exists():
                    continue
                return (
                    Availability.MISSING_MODULE,
                    f"Módulo `{mod}` ainda não disponível nesta versão"
                    + (f" (esperado em {self.expected_pr})." if self.expected_pr else "."),
                )
        if not shutil.which(sys.executable):
            return Availability.MISSING_DEPS, "Python não encontrado."
        return Availability.AVAILABLE, None

    def public_dict(self) -> dict[str, Any]:
        avail, reason = self.detect_availability()
        phrase = self.confirmation_phrase
        if self.requires_confirmation and not phrase:
            phrase = "CONFIRMO"
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "availability": avail.value,
            "unavailable_reason": reason,
            "risk": self.risk.value,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_phrase": phrase,
            "allow_cancel": self.allow_cancel,
            "params": [
                {
                    "name": p.name,
                    "label": p.label,
                    "type": p.type,
                    "required": p.required,
                    "default": p.default,
                    "description": p.description,
                    "example": p.example,
                    "choices": p.choices,
                    "advanced": p.advanced,
                    "sensitive": p.sensitive,
                }
                for p in self.params
            ],
            "required_env": self.required_env,
            "output_roots": self.output_roots,
            "docs": self.docs,
            "timeout_sec": self.timeout_sec,
            "fixture": self.fixture,
            "expected_pr": self.expected_pr,
        }


def python_m(*module_and_args: str) -> list[str]:
    return [sys.executable, "-m", *module_and_args]


def default_parse(exit_code: int, stdout: str, stderr: str, params: dict[str, Any]) -> dict[str, Any]:
    from scripts.command_center.status_normalize import normalize_exit, public_status_dict

    status = normalize_exit(exit_code, stdout=stdout, stderr=stderr)
    artifacts: list[str] = []
    for line in (stdout + "\n" + stderr).splitlines():
        line = line.strip()
        if not line:
            continue
        for marker in ("output/", "artifacts/", "data/command_center/"):
            if marker in line:
                # crude path extraction
                for token in line.replace(",", " ").split():
                    if marker in token:
                        artifacts.append(token.strip("\"'"))
    return {
        **public_status_dict(status),
        "artifacts": artifacts[:50],
        "blocker": status.technical_code if status.state.value.startswith("BLOCKED") else None,
    }
