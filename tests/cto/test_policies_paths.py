from scripts.cto.policies import path_allowed


def test_path_allowed_glob():
    assert path_allowed("scripts/cto/cli.py", ["scripts/cto/**"], [".env"])
    assert not path_allowed(".env", ["scripts/cto/**"], [".env"])
    assert not path_allowed("DOD.md", ["scripts/cto/**"], [".env"])
    assert path_allowed("tests/cto/test_x.py", ["tests/cto/**"], [])
