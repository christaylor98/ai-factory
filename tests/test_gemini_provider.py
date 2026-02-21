"""
Test Gemini provider
"""
import os
import pytest
from ai_factory import Config
from ai_factory.providers.gemini import GeminiProvider


def test_gemini_requires_api_key():
    """Test that Gemini provider requires GEMINI_API_KEY."""
    # Save original value
    original_key = os.environ.get("GEMINI_API_KEY")
    
    try:
        # Remove key from environment
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
        
        config = Config(
            provider="gemini",
            model="gemini-2.5-flash",
        )
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            GeminiProvider(config)
    
    finally:
        # Restore original value
        if original_key:
            os.environ["GEMINI_API_KEY"] = original_key
        elif "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]


def test_gemini_accepts_api_key_from_env():
    """Test that Gemini provider accepts API key from environment."""
    # Save original value
    original_key = os.environ.get("GEMINI_API_KEY")
    
    try:
        # Set a dummy key
        os.environ["GEMINI_API_KEY"] = "test-api-key-12345"
        
        config = Config(
            provider="gemini",
            model="gemini-2.5-flash",
        )
        
        # Should not raise
        provider = GeminiProvider(config)
        assert provider.api_key == "test-api-key-12345"
    
    finally:
        # Restore original value
        if original_key:
            os.environ["GEMINI_API_KEY"] = original_key
        elif "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]


@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set - skipping integration test"
)
def test_gemini_integration_basic():
    """Integration test: basic Gemini call (only runs if API key is set)."""
    from ai_factory import run
    
    config = Config(
        provider="gemini",
        model="gemini-2.5-flash",  # Use a current valid model
        ledger_enabled=False,
    )
    
    result = run("Say 'hello' and nothing else.", config)
    
    # Should get a response
    assert result.success is True
    assert len(result.output) > 0
    assert result.metrics.input_chars > 0
    assert result.metrics.output_chars > 0


@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set - skipping integration test"
)
def test_gemini_integration_list_models():
    """Integration test: list Gemini models (only runs if API key is set)."""
    from ai_factory import list_models
    
    config = Config(
        provider="gemini",
        model="gemini-pro",
    )
    
    models = list_models("gemini", config)
    
    # Should have at least one model
    assert len(models) > 0
    
    # Check structure
    for model in models:
        assert model.name is not None
        assert isinstance(model.name, str)


def test_gemini_retryable_error_detection():
    """Test that Gemini provider correctly identifies retryable errors."""
    config = Config(
        provider="gemini",
        model="gemini-2.5-flash",
    )
    
    # Set dummy key to avoid key error
    original_key = os.environ.get("GEMINI_API_KEY")
    try:
        os.environ["GEMINI_API_KEY"] = "test-key"
        provider = GeminiProvider(config)
        
        # Test retryable errors
        assert provider._is_retryable_error(Exception("429 rate limit exceeded"))
        assert provider._is_retryable_error(Exception("500 internal error"))
        assert provider._is_retryable_error(Exception("503 service unavailable"))
        assert provider._is_retryable_error(Exception("Quota exceeded"))
        assert provider._is_retryable_error(Exception("Connection timeout"))
        
        # Test non-retryable errors
        assert not provider._is_retryable_error(Exception("401 unauthorized"))
        assert not provider._is_retryable_error(Exception("403 forbidden"))
        assert not provider._is_retryable_error(Exception("Invalid argument"))
    
    finally:
        if original_key:
            os.environ["GEMINI_API_KEY"] = original_key
        elif "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
