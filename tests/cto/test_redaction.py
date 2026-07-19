from scripts.cto.redaction import REDACTED, redact_obj, redact_text, safe_exception_message


def test_redact_sk_key():
    text = "key is sk-5416845d991e468db42f4e0122945a66 end"
    out = redact_text(text)
    assert "sk-5416845d991e468db42f4e0122945a66" not in out
    assert REDACTED in out


def test_redact_env_assignment():
    text = "DEEPSEEK_API_KEY=sk-abc1234567890 and more"
    out = redact_text(text)
    assert "sk-abc" not in out
    assert "DEEPSEEK_API_KEY" in out


def test_redact_obj_nested():
    obj = {"DEEPSEEK_API_KEY": "secret", "nested": {"token": "abc"}, "ok": 1}
    out = redact_obj(obj)
    assert out["DEEPSEEK_API_KEY"] == REDACTED
    assert out["nested"]["token"] == REDACTED
    assert out["ok"] == 1


def test_safe_exception():
    exc = RuntimeError("failed with sk-abcdefghijklmnopqrstuv")
    msg = safe_exception_message(exc)
    assert "sk-abcdefghijklmnopqrstuv" not in msg
