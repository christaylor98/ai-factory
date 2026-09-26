"""
Test the local (OpenAI-compatible server) provider and the openai
provider's base_url handling.
"""
import socket
from types import SimpleNamespace

import pytest

from ai_factory import Config
from ai_factory.config_loader import load_config
from ai_factory.pricing import resolve_price
from ai_factory.providers.local import LocalProvider, DEFAULT_LOCAL_BASE_URL
from ai_factory.providers.openai import OpenAIProvider
from ai_factory.runner import run


def _closed_port_url() -> str:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


def _completion(content, reasoning=None, finish_reason="stop"):
    message = SimpleNamespace(content=content, reasoning_content=reasoning)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    return SimpleNamespace(choices=[choice], usage=usage, model_dump=lambda: {})


class _FakeClient:
    """Stands in for OpenAI(): records create() kwargs, serves a model list."""

    def __init__(self, response, model_ids=("gemma.gguf",)):
        self.sent = None
        self.models = SimpleNamespace(
            list=lambda: SimpleNamespace(data=[SimpleNamespace(id=i) for i in model_ids])
        )

        def create(**kwargs):
            self.sent = kwargs
            return response

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def _local(response, model="", model_ids=("gemma.gguf",), **config):
    provider = LocalProvider(Config(provider="local", model=model, max_retries=0, **config))
    provider.client = _FakeClient(response, model_ids)
    return provider


def test_local_defaults_to_llama_server():
    provider = LocalProvider(Config(provider="local", model=""))
    assert provider.base_url == DEFAULT_LOCAL_BASE_URL
    assert str(provider.client.base_url).rstrip("/") == DEFAULT_LOCAL_BASE_URL


def test_local_bare_host_gets_v1():
    provider = LocalProvider(Config(provider="local", model="", base_url="http://gpu:11434"))
    assert provider.base_url == "http://gpu:11434/v1"


def test_local_resolves_the_single_served_model():
    provider = _local(_completion("hi"))
    response = provider.call("hello")
    assert response.error is None
    assert provider.config.model == "gemma.gguf"
    assert provider.client.sent["model"] == "gemma.gguf"


def test_local_refuses_to_guess_between_several_models():
    provider = _local(_completion("hi"), model_ids=("a", "b"))
    response = provider.call("hello")
    assert "serves 2 models (a, b); pass model=" in response.error


def test_local_explicit_model_skips_listing():
    provider = _local(_completion("hi"), model="named", model_ids=())
    assert provider.call("hello").error is None
    assert provider.client.sent["model"] == "named"


def test_local_thinking_off_by_default():
    provider = _local(_completion("hi"))
    provider.call("hello")
    kwargs = provider.client.sent["extra_body"]["chat_template_kwargs"]
    assert kwargs == {"enable_thinking": False}


def test_local_thinking_flag_turns_it_on():
    provider = _local(_completion("hi"), thinking=True)
    provider.call("hello")
    assert provider.client.sent["extra_body"]["chat_template_kwargs"]["enable_thinking"] is True


def test_local_passes_temperature_and_max_tokens():
    provider = _local(_completion("hi"), temperature=0.2, max_tokens=64)
    provider.call("hello")
    assert provider.client.sent["temperature"] == 0.2
    assert provider.client.sent["max_tokens"] == 64


def test_reasoning_without_content_is_a_failure():
    provider = _local(_completion("", reasoning="let me think...", finish_reason="length"))
    response = provider.call("hello")
    assert response.error == "reasoning exhausted max_tokens"
    assert response.metadata["completion_tokens"] == 5


def test_truncated_empty_output_is_a_failure():
    provider = _local(_completion("", finish_reason="length"))
    assert provider.call("hello").error == "output truncated at max_tokens before any content"


def test_refused_connection_fails_fast_with_clear_message():
    url = _closed_port_url()
    provider = LocalProvider(Config(provider="local", model="m", base_url=url, max_retries=2))
    response = provider.call("hello")
    assert response.error == f"local server not reachable at {url}/v1 (is llama-server running?)"
    assert response.attempts == 1
    assert response.retry_history == []


def test_list_models_reads_v1_models():
    provider = _local(_completion("hi"), model_ids=("x.gguf",))
    assert [m.name for m in provider.list_models()] == ["x.gguf"]


def test_list_models_down_server_raises_not_fallback():
    provider = LocalProvider(Config(provider="local", model="", base_url=_closed_port_url()))
    with pytest.raises(RuntimeError, match="local server not reachable"):
        provider.list_models()


def test_local_is_free():
    price = resolve_price("local", "anything.gguf", allow_network=False)
    assert price.input_per_1m == 0.0 and price.output_per_1m == 0.0


def test_run_records_resolved_model_and_zero_cost(tmp_path, monkeypatch):
    fake = _FakeClient(_completion("hi"))
    monkeypatch.setattr(
        "ai_factory.providers.local.OpenAI", lambda **kwargs: fake
    )
    ledger = tmp_path / "LEDGER.jsonl"
    config = Config(provider="local", model="", ledger_path=str(ledger), ledger_format="json")
    result = run("hello", config)
    assert result.success and result.output == "hi"
    assert result.metrics.cost_usd == 0.0
    assert '"model": "gemma.gguf"' in ledger.read_text()


def test_run_surfaces_the_failure_reason(tmp_path):
    config = Config(provider="local", model="m", base_url=_closed_port_url(),
                    ledger_path=str(tmp_path / "L.is"))
    result = run("hello", config)
    assert result.success is False
    assert result.error.startswith("local server not reachable")


def test_load_config_local_ignores_default_model(monkeypatch):
    monkeypatch.setenv("AIFACTORY_MODEL", "gemini-2.5-flash")
    assert load_config(provider="local").model == ""
    assert load_config(provider="local", model="named").model == "named"


def test_load_config_reads_local_section(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "aifactory.toml").write_text(
        '[local]\nbase_url = "http://gpu:8089/v1"\nmodel = "g.gguf"\nthinking = true\n'
    )
    config = load_config(provider="local")
    assert (config.base_url, config.model, config.thinking) == ("http://gpu:8089/v1", "g.gguf", True)


def test_openai_honours_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    provider = OpenAIProvider(Config(provider="openai", model="m", base_url="http://127.0.0.1:9/v1"))
    assert str(provider.client.base_url).rstrip("/") == "http://127.0.0.1:9/v1"


def test_metrics_carry_finish_reason(tmp_path, monkeypatch):
    fake = _FakeClient(_completion("one two", finish_reason="length"))
    monkeypatch.setattr("ai_factory.providers.local.OpenAI", lambda **kwargs: fake)
    config = Config(provider="local", model="", ledger_path=str(tmp_path / "L.is"))
    result = run("count", config)
    assert result.success and result.metrics.finish_reason == "length"
