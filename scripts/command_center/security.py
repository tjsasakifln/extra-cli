"""Security helpers: CSRF, path sanitization, allowlist enforcement."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Iterable

from fastapi import Header, HTTPException, Request, Response


def issue_csrf_token(response: Response, cookie_name: str) -> str:
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        key=cookie_name,
        value=token,
        httponly=False,
        samesite="strict",
        secure=False,  # localhost HTTP
        path="/",
    )
    return token


def require_csrf(
    request: Request,
    *,
    cookie_name: str,
    header_name: str,
    x_csrf: str | None = Header(default=None, alias="X-CC-CSRF"),
) -> None:
    cookie = request.cookies.get(cookie_name)
    header = x_csrf or request.headers.get(header_name)
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="CSRF token ausente ou inválido.")


def safe_join(root: Path, user_path: str) -> Path:
    """Resolve user_path under root; reject traversal."""
    root = root.resolve()
    # Strip leading slashes so join stays relative
    cleaned = user_path.lstrip("/\\")
    if ".." in Path(cleaned).parts:
        raise HTTPException(status_code=400, detail="Path traversal não permitido.")
    candidate = (root / cleaned).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path fora da raiz permitida.") from exc
    return candidate


def resolve_under_roots(user_path: str, roots: Iterable[Path]) -> Path:
    raw = Path(user_path).expanduser()
    # Absolute path must still fall under an allowed root
    if raw.is_absolute():
        resolved = raw.resolve()
        for root in roots:
            root = root.resolve()
            try:
                resolved.relative_to(root)
                if not resolved.exists():
                    raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
                return resolved
            except ValueError:
                continue
        raise HTTPException(status_code=403, detail="Arquivo fora das raízes permitidas.")
    # Relative: try each root
    for root in roots:
        try:
            candidate = safe_join(root, user_path)
        except HTTPException:
            continue
        if candidate.exists():
            return candidate
    raise HTTPException(status_code=404, detail="Arquivo não encontrado nas raízes permitidas.")


def assert_argv_list(argv: list[str]) -> list[str]:
    if not argv or not isinstance(argv, list):
        raise ValueError("argv must be a non-empty list")
    if any(not isinstance(x, str) for x in argv):
        raise ValueError("argv items must be strings")
    if any("\x00" in x for x in argv):
        raise ValueError("argv contains NUL")
    # Reject shell metacharacters as whole tokens that would only make sense with shell=True
    return list(argv)
