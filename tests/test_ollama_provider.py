"""
Test Ollama provider
"""
import pytest
from ai_factory import Config
from ai_factory.providers.ollama import OllamaProvider


def test_ollama_no_api_key_required():
    """Test that Ollama provider does not require API key."""
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
    )
    
    # Should not raise - no API key required
    provider = OllamaProvider(config)
    assert provider.base_url == "http://localhost:11434"


def test_ollama_default_base_url():
    """Test that Ollama uses default base_url."""
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
    )
    
    provider = OllamaProvider(config)
    assert provider.base_url == "http://localhost:11434"


def test_ollama_custom_base_url():
    """Test that Ollama accepts custom base_url."""
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
        base_url="http://localhost:8080",
    )
    
    provider = OllamaProvider(config)
    assert provider.base_url == "http://localhost:8080"


def test_ollama_base_url_strips_trailing_slash():
    """Test that trailing slash is stripped from base_url."""
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
        base_url="http://localhost:11434/",
    )
    
    provider = OllamaProvider(config)
    assert provider.base_url == "http://localhost:11434"


def test_ollama_connection_refused_error():
    """Test graceful handling when Ollama is not running."""
    from ai_factory import run
    
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
        base_url="http://localhost:99999",  # Invalid port
        ledger_enabled=False,
    )
    
    result = run("Test prompt", config)
    
    # Should fail gracefully without raising exception
    assert result.success is False
    assert result.output == ""
    # Should have clear error message


def test_ollama_provider_contract():
    """Test that Ollama provider implements BaseProvider contract."""
    from ai_factory.providers.base import BaseProvider
    
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
    )
    
    provider = OllamaProvider(config)
    
    # Should be instance of BaseProvider
    assert isinstance(provider, BaseProvider)
    
    # Should have required methods
    assert hasattr(provider, 'call')
    assert hasattr(provider, 'list_models')
    assert hasattr(provider, 'embed')


def test_ollama_retryable_errors():
    """Test that Ollama correctly identifies retryable errors."""
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
    )
    
    provider = OllamaProvider(config)
    
    # Connection errors should be retryable
    class ConnectionError(Exception):
        pass
    
    error = ConnectionError("connection refused")
    assert provider._is_retryable_error(error) is True
    
    # 404 errors should NOT be retryable
    class HTTPError(Exception):
        pass
    
    error = HTTPError("404 not found")
    assert provider._is_retryable_error(error) is False


def test_ollama_list_models_when_not_running():
    """Test list_models returns empty list when Ollama not running."""
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
        base_url="http://localhost:99999",  # Invalid port
    )
    
    provider = OllamaProvider(config)
    models = provider.list_models()
    
    # Should return empty list, not raise exception
    assert models == []


# Integration tests (only run if Ollama is actually running)
@pytest.mark.skipif(
    True,  # Skip by default - user can enable manually
    reason="Ollama integration test - enable manually when Ollama is running"
)
def test_ollama_integration_basic():
    """Integration test: basic Ollama call (only runs if Ollama is running)."""
    from ai_factory import run
    
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
        ledger_enabled=False,
    )
    
    result = run("Return 2-3 topic labels: Ancient Egypt flourished along the Nile", config)
    
    # Should get a response
    assert result.success is True
    assert len(result.output) > 0
    
    # Should have metrics
    assert result.metrics.latency_ms > 0
    assert result.metrics.input_chars > 0
    assert result.metrics.output_chars > 0


@pytest.mark.skipif(
    True,  # Skip by default
    reason="Ollama integration test - enable manually when Ollama is running"
)
def test_ollama_integration_token_tracking():
    """Integration test: verify token counts are tracked."""
    from ai_factory import run
    
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
        ledger_enabled=False,
    )
    
    result = run("What is 2+2?", config)
    
    assert result.success is True
    
    # Token counts should be present (if Ollama provides them)
    # Note: This depends on Ollama version and model
    if result.metrics.prompt_tokens:
        assert result.metrics.prompt_tokens > 0
    if result.metrics.completion_tokens:
        assert result.metrics.completion_tokens > 0


@pytest.mark.skipif(
    True,  # Skip by default
    reason="Ollama integration test - enable manually when Ollama is running"
)
def test_ollama_integration_list_models():
    """Integration test: list available Ollama models."""
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
    )
    
    provider = OllamaProvider(config)
    models = provider.list_models()
    
    # Should return some models if Ollama is running
    assert len(models) > 0
    
    # Each model should have a name
    for model in models:
        assert model.name
        assert isinstance(model.metadata, dict)
