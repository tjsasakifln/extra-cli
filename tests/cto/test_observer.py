from scripts.cto.observer import observe


def test_observe_writes_json(cto_repo):
    obs = observe(cto_repo, write=True)
    assert obs["schema_version"] in {"1.0", "1.1"}
    assert "git" in obs
    assert "dod" in obs
    assert obs["dod"]["total"] >= 2
    assert obs["dod"]["checked"] >= 1
    path = cto_repo / "output" / "cto" / "current" / "observation.json"
    assert path.is_file()
    # no secrets key material
    text = path.read_text(encoding="utf-8")
    assert "sk-" not in text or "sk-" not in text  # noop safety
