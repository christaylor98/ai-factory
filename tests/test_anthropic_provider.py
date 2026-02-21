"""
Test Anthropic provider
"""
import os
import pytest
from ai_factory import Config
from ai_factory.providers.anthropic import AnthropicProvider


def test_anthropic_requires_api_key():
    """Test that Anthropic provider requires ANTHROPIC_API_KEY."""
    # Save original value
    original_key = os.environ.get("ANTHROPIC_API_KEY")
    
    try:
        # Remove key from environment
        if "ANTHROPIC_API_KEY" in os.environ:
            del os.environ["ANTHROPIC_API_KEY"]
        
        config = Config(
            provider="anthropic",
            model="claude-haiku-4.5",
        )
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            AnthropicProvider(config)
    
    finally:
        # Restore original value
        if original_key:
            os.environ["ANTHROPIC_API_KEY"] = original_key
        elif "ANTHROPIC_API_KEY" in os.environ:
            del os.environ["ANTHROPIC_API_KEY"]


def test_anthropic_accepts_api_key_from_env():
    """Test that Anthropic provider accepts API key from environment."""
    # Save original value
    original_key = os.environ.get("ANTHROPIC_API_KEY")
    
    try:
        # Set a dummy key
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-api-key-12345"
        
        config = Config(
            provider="anthropic",
            model="claude-haiku-4.5",
        )
        
        # Should not raise
        provider = AnthropicProvider(config)
        assert provider.api_key == "sk-ant-test-api-key-12345"
    
    finally:
        # Restore original value
        if original_key:
            os.environ["ANTHROPIC_API_KEY"] = original_key
        elif "ANTHROPIC_API_KEY" in os.environ:
            del os.environ["ANTHROPIC_API_KEY"]


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set - skipping integration test"
)
def test_anthropic_integration_basic():
    """Integration test: basic Anthropic call (only runs if API key is set)."""
    from ai_factory import run
    
    config = Config(
        provider="anthropic",
        model="claude-haiku-4.5",
        ledger_enabled=False,
    )
    
    result = run("Say 'hello' and nothing else.", config)
    
    # Should get a response
    assert result.success is True
    assert len(result.output) > 0
    assert result.metrics.input_chars > 0
    assert result.metrics.output_chars > 0


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set - skipping integration test"
)
def test_anthropic_integration_list_models():
    """Integration test: list Anthropic models (only runs if API key is set)."""
    from ai_factory import list_models
    
    config = Config(
        provider="anthropic",
        model="claude-haiku-4.5",
    )
    
    models = list_models("anthropic", config)
    
    # Should have at least one model (from fallback list)
    assert len(models) > 0
    
    # Check structure
    for model in models:
        assert model.name is not None
        assert isinstance(model.name, str)


def test_anthropic_retryable_error_detection():
    """Test that Anthropic provider correctly identifies retryable errors."""
    config = Config(
        provider="anthropic",
        model="claude-haiku-4.5",
    )
    
    # Set dummy key to avoid key error
    original_key = os.environ.get("ANTHROPIC_API_KEY")
    try:
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key"
        provider = AnthropicProvider(config)
        
        # Test retryable errors
        assert provider._is_retryable_error(Exception("429 rate limit exceeded"))
        assert provider._is_retryable_error(Exception("500 internal error"))
        assert provider._is_retryable_error(Exception("503 service unavailable"))
        assert provider._is_retryable_error(Exception("overloaded"))
        assert provider._is_retryable_error(Exception("Quota exceeded"))
        assert provider._is_retryable_error(Exception("Connection timeout"))
        
        # Test non-retryable errors
        assert not provider._is_retryable_error(Exception("401 unauthorized"))
        assert not provider._is_retryable_error(Exception("403 forbidden"))
        assert not provider._is_retryable_error(Exception("Invalid API key"))
    
    finally:
        if original_key:
            os.environ["ANTHROPIC_API_KEY"] = original_key
        elif "ANTHROPIC_API_KEY" in os.environ:
            del os.environ["ANTHROPIC_API_KEY"]
