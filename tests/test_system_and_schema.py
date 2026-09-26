"""A4 (axChat CONTROLLER_SPEC §6.2): run() takes a system prompt and a JSON schema, on the providers that can honour
them; elsewhere it refuses instead of dropping them. Nothing changes for a config that sets neither (A9)."""
import json
import stat
from unittest import mock

from ai_factory import Config, run
from ai_factory.providers.base import chat_messages, response_format

SCHEMA = {"type": "object", "properties": {"intent": {"enum": ["ask", "do"]}}, "required": ["intent"]}


def cfg(**kw):
    return Config(**{"provider": "stub", "model": "m", "ledger_enabled": False, "pricing_enabled": False, **kw})


def test_a_plain_run_is_unchanged():
    r = run("hello", cfg())
    assert r.success and r.output == "STUB: hello"


def test_openai_style_messages_and_response_format():
    assert chat_messages(cfg(), "p") == [{"role": "user", "content": "p"}]
    assert chat_messages(cfg(system_prompt="S"), "p") == [{"role": "system", "content": "S"},
                                                          {"role": "user", "content": "p"}]
    assert response_format(cfg()) is None
    assert response_format(cfg(json_schema=SCHEMA))["json_schema"]["schema"] == SCHEMA


def test_the_openai_family_sends_them():
    from ai_factory.providers.local import LocalProvider
    p = LocalProvider(cfg(provider="local", model="gemma", system_prompt="S", json_schema=SCHEMA))
    kw = p._create_kwargs("p")
    assert kw["messages"][0] == {"role": "system", "content": "S"}
    assert kw["response_format"]["type"] == "json_schema"


def test_a_provider_that_cannot_honour_them_refuses():
    from ai_factory.providers.ollama import OllamaProvider
    assert not OllamaProvider.SUPPORTS_SYSTEM
    r = run("p", cfg(provider="ollama", system_prompt="S"))
    assert not r.success and "does not support system_prompt" in r.error


def test_claude_code_passes_them_and_returns_the_structured_answer(tmp_path, monkeypatch):
    seen = tmp_path / "argv.json"
    fake = tmp_path / "claude"
    fake.write_text(f"""#!/usr/bin/env python3
import json, sys
json.dump(sys.argv[1:], open({str(seen)!r}, "w"))
print(json.dumps({{"result": "", "structured_output": {{"intent": "do"}}, "usage": {{"input_tokens": 3, "output_tokens": 2}}}}))
""")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CLAUDE_CODE_CLI_PATH", str(fake))
    r = run("fix it", cfg(provider="claude_code", model="haiku", system_prompt="classify", json_schema=SCHEMA))
    assert r.success, r.error
    assert json.loads(r.output) == {"intent": "do"}
    argv = json.loads(seen.read_text())
    assert argv[argv.index("--system-prompt") + 1] == "classify"
    assert json.loads(argv[argv.index("--json-schema") + 1]) == SCHEMA
