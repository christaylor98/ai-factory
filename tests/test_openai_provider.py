"""
Test OpenAI provider
"""
import os
import pytest
from ai_factory import Config
from ai_factory.providers.openai import OpenAIProvider


def test_openai_requires_api_key():
    """Test that OpenAI provider requires OPENAI_API_KEY."""
    # Save original value
    original_key = os.environ.get("OPENAI_API_KEY")
    
    try:
        # Remove key from environment
        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]
        
        config = Config(
            provider="openai",
            model="gpt-4o-mini",
        )
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            OpenAIProvider(config)
    
    finally:
        # Restore original value
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key
        elif "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]


def test_openai_accepts_api_key_from_env():
    """Test that OpenAI provider accepts API key from environment."""
    # Save original value
    original_key = os.environ.get("OPENAI_API_KEY")
    
    try:
        # Set a dummy key
        os.environ["OPENAI_API_KEY"] = "sk-test-api-key-12345"
        
        config = Config(
            provider="openai",
            model="gpt-4o-mini",
        )
        
        # Should not raise
        provider = OpenAIProvider(config)
        assert provider.api_key == "sk-test-api-key-12345"
    
    finally:
        # Restore original value
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key
        elif "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set - skipping integration test"
)
def test_openai_integration_basic():
    """Integration test: basic OpenAI call (only runs if API key is set)."""
    from ai_factory import run
    
    config = Config(
        provider="openai",
        model="gpt-4o-mini",
        ledger_enabled=False,
    )
    
    result = run("Say 'hello' and nothing else.", config)
    
    # Should get a response
    assert result.success is True
    assert len(result.output) > 0
    assert result.metrics.input_chars > 0
    assert result.metrics.output_chars > 0


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set - skipping integration test"
)
def test_openai_integration_list_models():
    """Integration test: list OpenAI models (only runs if API key is set)."""
    from ai_factory import list_models
    
    config = Config(
        provider="openai",
        model="gpt-4o-mini",
    )
    
    models = list_models("openai", config)
    
    # Should have at least one model
    assert len(models) > 0
    
    # Check structure
    for model in models:
        assert model.name is not None
        assert isinstance(model.name, str)


def test_openai_retryable_error_detection():
    """Test that OpenAI provider correctly identifies retryable errors."""
    config = Config(
        provider="openai",
        model="gpt-4o-mini",
    )
    
    # Set dummy key to avoid key error
    original_key = os.environ.get("OPENAI_API_KEY")
    try:
        os.environ["OPENAI_API_KEY"] = "sk-test-key"
        provider = OpenAIProvider(config)
        
        # Test retryable errors
        assert provider._is_retryable_error(Exception("429 rate limit exceeded"))
        assert provider._is_retryable_error(Exception("500 internal error"))
        assert provider._is_retryable_error(Exception("503 service unavailable"))
        assert provider._is_retryable_error(Exception("Quota exceeded"))
        assert provider._is_retryable_error(Exception("Connection timeout"))
        
        # Test non-retryable errors
        assert not provider._is_retryable_error(Exception("401 unauthorized"))
        assert not provider._is_retryable_error(Exception("403 forbidden"))
        assert not provider._is_retryable_error(Exception("Invalid API key"))
    
    finally:
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key
        elif "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]
