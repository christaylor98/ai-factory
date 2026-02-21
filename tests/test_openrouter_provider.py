"""
Test OpenRouter provider
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from ai_factory import Config
from ai_factory.providers.openrouter import OpenRouterProvider
from ai_factory.result import RetryRecord


def test_openrouter_requires_api_key():
    """Test that OpenRouter provider requires OPENROUTER_API_KEY."""
    # Save original value
    original_key = os.environ.get("OPENROUTER_API_KEY")
    
    try:
        # Remove key from environment
        if "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]
        
        config = Config(
            provider="openrouter",
            model="openai/gpt-3.5-turbo",
        )
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            OpenRouterProvider(config)
    
    finally:
        # Restore original value
        if original_key:
            os.environ["OPENROUTER_API_KEY"] = original_key
        elif "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]


def test_openrouter_accepts_api_key_from_env():
    """Test that OpenRouter provider accepts API key from environment."""
    # Save original value
    original_key = os.environ.get("OPENROUTER_API_KEY")
    
    try:
        # Set a dummy key
        os.environ["OPENROUTER_API_KEY"] = "sk-or-test-12345"
        
        config = Config(
            provider="openrouter",
            model="openai/gpt-3.5-turbo",
        )
        
        # Should not raise
        provider = OpenRouterProvider(config)
        assert provider.api_key == "sk-or-test-12345"
    
    finally:
        # Restore original value
        if original_key:
            os.environ["OPENROUTER_API_KEY"] = original_key
        elif "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]


def test_openrouter_optional_headers():
    """Test that OpenRouter provider sends optional headers when env vars are set."""
    # Save original values
    original_key = os.environ.get("OPENROUTER_API_KEY")
    original_referer = os.environ.get("OPENROUTER_HTTP_REFERER")
    original_title = os.environ.get("OPENROUTER_X_TITLE")
    
    try:
        # Set env vars
        os.environ["OPENROUTER_API_KEY"] = "sk-or-test-12345"
        os.environ["OPENROUTER_HTTP_REFERER"] = "https://example.com"
        os.environ["OPENROUTER_X_TITLE"] = "Test App"
        
        config = Config(
            provider="openrouter",
            model="openai/gpt-3.5-turbo",
        )
        
        provider = OpenRouterProvider(config)
        
        # Check that headers are set
        assert provider.http_referer == "https://example.com"
        assert provider.x_title == "Test App"
        
        # Verify they're passed to the client
        assert provider.client.default_headers is not None
        assert provider.client.default_headers.get("HTTP-Referer") == "https://example.com"
        assert provider.client.default_headers.get("X-Title") == "Test App"
    
    finally:
        # Restore original values
        if original_key:
            os.environ["OPENROUTER_API_KEY"] = original_key
        elif "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]
        
        if original_referer:
            os.environ["OPENROUTER_HTTP_REFERER"] = original_referer
        elif "OPENROUTER_HTTP_REFERER" in os.environ:
            del os.environ["OPENROUTER_HTTP_REFERER"]
        
        if original_title:
            os.environ["OPENROUTER_X_TITLE"] = original_title
        elif "OPENROUTER_X_TITLE" in os.environ:
            del os.environ["OPENROUTER_X_TITLE"]


@patch('ai_factory.providers.openrouter.OpenAI')
def test_openrouter_retry_on_429(mock_openai_class):
    """Test that OpenRouter retries on 429 rate limit error."""
    # Save original key
    original_key = os.environ.get("OPENROUTER_API_KEY")
    
    try:
        os.environ["OPENROUTER_API_KEY"] = "sk-or-test-12345"
        
        config = Config(
            provider="openrouter",
            model="openai/gpt-3.5-turbo",
            max_retries=2,
            backoff_base_ms=100,
            backoff_multiplier=2.0,
        )
        
        # Mock the client and its methods
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # First call fails with 429, second succeeds
        mock_choice = MagicMock()
        mock_choice.message.content = "Hello!"
        mock_choice.finish_reason = "stop"
        
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.id = "chatcmpl-123"
        mock_response.model = "openai/gpt-3.5-turbo"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        
        # Mock model_dump for full metadata capture
        mock_response.model_dump.return_value = {
            'id': 'chatcmpl-123',
            'model': 'openai/gpt-3.5-turbo',
            'choices': [{'finish_reason': 'stop', 'message': {'content': 'Hello!'}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}
        }
        
        # Simulate 429 error on first call, success on second
        error_429 = Exception("429 Rate limit exceeded")
        mock_client.chat.completions.create.side_effect = [
            error_429,
            mock_response
        ]
        
        provider = OpenRouterProvider(config)
        result = provider.call("test prompt")
        
        # Should succeed after retry
        assert result.text == "Hello!"
        assert result.attempts == 2
        assert len(result.retry_history) == 1
        assert result.retry_history[0].attempt == 1
        assert "429" in result.retry_history[0].error_type or "429" in result.retry_history[0].error_message
        assert result.retry_history[0].backoff_ms == 100
        assert result.error is None
        
        # Check metadata (now contains full response)
        assert 'id' in result.metadata
        assert 'prompt_tokens' in result.metadata
        assert 'completion_tokens' in result.metadata
        assert 'finish_reason' in result.metadata
    
    finally:
        if original_key:
            os.environ["OPENROUTER_API_KEY"] = original_key
        elif "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]


@patch('ai_factory.providers.openrouter.OpenAI')
def test_openrouter_no_retry_on_auth_error(mock_openai_class):
    """Test that OpenRouter does not retry on 401 authentication error."""
    # Save original key
    original_key = os.environ.get("OPENROUTER_API_KEY")
    
    try:
        os.environ["OPENROUTER_API_KEY"] = "sk-or-test-12345"
        
        config = Config(
            provider="openrouter",
            model="openai/gpt-3.5-turbo",
            max_retries=2,
        )
        
        # Mock the client
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Simulate 401 auth error
        error_401 = Exception("401 Unauthorized - Invalid API key")
        mock_client.chat.completions.create.side_effect = error_401
        
        provider = OpenRouterProvider(config)
        result = provider.call("test prompt")
        
        # Should fail without retry
        assert result.text == ""
        assert result.attempts == 1
        assert len(result.retry_history) == 0
        assert result.error is not None
        assert "401" in result.error or "Unauthorized" in result.error
    
    finally:
        if original_key:
            os.environ["OPENROUTER_API_KEY"] = original_key
        elif "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]


@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set - skipping integration test"
)
def test_openrouter_integration_basic():
    """Integration test: basic OpenRouter call (only runs if API key is set)."""
    from ai_factory import run
    
    config = Config(
        provider="openrouter",
        model="openai/gpt-3.5-turbo",  # Use a widely available model
        ledger_enabled=False,
    )
    
    result = run("Say 'hello' and nothing else.", config)
    
    # Should get a response
    assert result.success is True
    assert len(result.output) > 0
    assert result.metrics.input_chars > 0
    assert result.metrics.output_chars > 0


@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set - skipping integration test"
)
def test_openrouter_integration_with_retries():
    """Integration test: OpenRouter with retry configuration (only runs if API key is set)."""
    from ai_factory import run
    
    config = Config(
        provider="openrouter",
        model="openai/gpt-3.5-turbo",
        max_retries=3,
        backoff_base_ms=200,
        ledger_enabled=False,
    )
    
    result = run("What is 2+2?", config)
    
    # Should get a response
    assert result.success is True
    assert len(result.output) > 0
