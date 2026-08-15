"""Static contract for the private SearXNG deploy kit and HTTP-only boundary."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "deploy" / "searxng"


def test_pinned_images_use_digest_not_latest() -> None:
    pinned = (KIT / "PINNED.env").read_text(encoding="utf-8")
    compose = (KIT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "SEARXNG_IMAGE=" in pinned
    assert "VALKEY_IMAGE=" in pinned
    assert "@sha256:" in pinned
    assert "searxng/searxng:latest" not in pinned
    assert "valkey/valkey:latest" not in pinned
    assert "image: ${SEARXNG_IMAGE}" in compose
    assert "image: ${VALKEY_IMAGE}" in compose
    assert "searxng/searxng:latest" not in compose


def test_settings_enable_json_and_conservative_public_engines_only() -> None:
    settings = (KIT / "core-config" / "settings.yml").read_text(encoding="utf-8")
    assert "formats:" in settings
    assert "- json" in settings
    assert "keep_only:" in settings
    for engine in ("duckduckgo", "brave", "mojeek", "qwant", "wikipedia", "wikidata"):
        assert engine in settings
    assert "google" not in settings
    assert "linkedin" not in settings
    assert "proxy" not in settings.lower() or "image_proxy: false" in settings
    assert "No proxies" in settings
    limiter = (KIT / "core-config" / "limiter.toml").read_text(encoding="utf-8")
    assert "pass_searxng_org = false" in limiter


def test_launch_entry_point_and_rollback_exist_and_bind_privately() -> None:
    launch = (KIT / "launch.sh").read_text(encoding="utf-8")
    rollback = (KIT / "rollback.sh").read_text(encoding="utf-8")
    compose = (KIT / "docker-compose.yml").read_text(encoding="utf-8")
    example = (KIT / ".env.example").read_text(encoding="utf-8")
    assert "docker compose" in launch
    assert "format=json" in launch
    assert "PINNED.prev.env" in rollback
    assert "127.0.0.1" in compose
    assert "18888" in compose
    assert "768m" in compose
    assert "SEARXNG_SECRET=replace-with-openssl-rand-hex-32" in example
    gitignore = (KIT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore.splitlines()
    if (KIT / ".env").exists():
        secret = (KIT / ".env").read_text(encoding="utf-8")
        assert "replace-with-openssl-rand-hex-32" not in secret


def test_requirements_and_tree_do_not_vendor_searxng() -> None:
    requirement_pkgs = [
        line.split("#", 1)[0].strip().lower()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    ]
    assert not any(pkg.startswith(("searxng", "searx", "searx-")) for pkg in requirement_pkgs)
    scripts_root = ROOT / "scripts"
    leaked = [
        path
        for path in scripts_root.rglob("*searxng*")
        if path.is_dir() and path.name == "searxng"
    ]
    assert leaked == []
    client = (ROOT / "scripts" / "decision_unit_intelligence" / "search_http.py").read_text(encoding="utf-8")
    assert "httpx" in client
    assert "/search" in client
    assert "format" in client
    assert "import searx" not in client
    assert "from searx" not in client
