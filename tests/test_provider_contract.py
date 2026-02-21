"""
Provider contract compliance test suite for ai-factory.

This suite validates that all providers (stub, gemini, openrouter) conform
strictly to the BaseProvider contract without modifying runner, ledger, or metrics.

Contract requirements:
- call() returns ProviderResponse object
- ProviderResponse.text is always a string (even on failure)
- ProviderResponse.attempts >= 1
- ProviderResponse.retry_history length == attempts - 1 when success after retries
- On failure, error field is non-null
- On success, error field is null
- Retry history entries contain attempt, error_type, error_message, backoff_ms
- No provider leaks raw SDK exceptions
- Providers never write to ledger
- Providers do not mutate Config object
"""
import os
import copy
import pytest
from unittest.mock import Mock, patch, MagicMock
from ai_factory import Config
from ai_factory.result import ProviderResponse, ModelInfo, RetryRecord
from ai_factory.providers.stub import StubProvider
from ai_factory.providers.gemini import GeminiProvider
from ai_factory.providers.openrouter import OpenRouterProvider


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def base_config():
    """Provide a base configuration for testing."""
    return Config(
        provider="stub",
        model="stub-1",
        max_retries=2,
        backoff_base_ms=100,
        backoff_multiplier=2.0,
        ledger_enabled=False,
    )


@pytest.fixture
def stub_provider(base_config):
    """Provide a stub provider instance."""
    return StubProvider(base_config)


# ═══════════════════════════════════════════════════════════════════════
# Core Contract Tests - apply to all providers
# ═══════════════════════════════════════════════════════════════════════

class TestProviderResponseContract:
    """Test that all providers return proper ProviderResponse objects."""
    
    def test_stub_returns_provider_response(self, stub_provider):
        """Stub provider must return ProviderResponse."""
        result = stub_provider.call("test")
        assert isinstance(result, ProviderResponse)
    
    def test_stub_text_is_always_string(self, stub_provider):
        """Stub provider must always return string text, even on failure."""
        # Success case
        result = stub_provider.call("hello")
        assert isinstance(result.text, str)
        assert len(result.text) > 0
        
        # Failure case
        result = stub_provider.call("__FAIL__")
        assert isinstance(result.text, str)
        # On failure, text should be empty string
        assert result.text == ""
    
    def test_stub_attempts_always_positive(self, stub_provider):
        """Stub provider must have attempts >= 1."""
        result = stub_provider.call("test")
        assert result.attempts >= 1
        assert isinstance(result.attempts, int)
    
    def test_stub_error_null_on_success(self, stub_provider):
        """Stub provider must have error=None on success."""
        result = stub_provider.call("hello")
        assert result.error is None
    
    def test_stub_error_nonnull_on_failure(self, stub_provider):
        """Stub provider must have error!=None on failure."""
        result = stub_provider.call("__FAIL__")
        assert result.error is not None
        assert isinstance(result.error, str)
        assert len(result.error) > 0


class TestRetryHistoryContract:
    """Test retry history behavior across all providers."""
    
    def test_stub_retry_history_is_list(self, stub_provider):
        """Retry history must always be a list."""
        result = stub_provider.call("test")
        assert isinstance(result.retry_history, list)
    
    def test_stub_no_retries_means_empty_history(self, stub_provider):
        """Success on first attempt means empty retry history."""
        result = stub_provider.call("hello")
        assert result.attempts == 1
        assert len(result.retry_history) == 0
    
    def test_stub_retry_history_length_matches_attempts(self, stub_provider):
        """Retry history length == attempts - 1 when success after retries."""
        # Flake: fails first, succeeds on retry
        result = stub_provider.call("__FLAKE__")
        assert result.attempts == 2
        assert len(result.retry_history) == 1
        assert result.error is None
    
    def test_stub_retry_record_structure(self, stub_provider):
        """Retry records must contain required fields."""
        result = stub_provider.call("__FLAKE__")
        assert len(result.retry_history) == 1
        
        record = result.retry_history[0]
        assert isinstance(record, RetryRecord)
        assert hasattr(record, 'attempt')
        assert hasattr(record, 'error_type')
        assert hasattr(record, 'error_message')
        assert hasattr(record, 'backoff_ms')
        
        assert isinstance(record.attempt, int)
        assert isinstance(record.error_type, str)
        assert isinstance(record.error_message, str)
        assert isinstance(record.backoff_ms, int)
        
        assert record.attempt == 1
        assert len(record.error_type) > 0
        assert len(record.error_message) > 0
        assert record.backoff_ms > 0
    
    def test_stub_backoff_calculation(self, stub_provider):
        """Backoff must match config formula: base * (multiplier ** attempt)."""
        result = stub_provider.call("__FLAKE__")
        record = result.retry_history[0]
        
        # First retry (attempt 0): 100 * (2.0 ** 0) = 100
        expected_backoff = int(
            stub_provider.config.backoff_base_ms * 
            (stub_provider.config.backoff_multiplier ** 0)
        )
        assert record.backoff_ms == expected_backoff
    
    def test_stub_exhausted_retries(self, base_config):
        """When retries exhausted, attempts == max_retries + 1."""
        provider = StubProvider(base_config)
        result = provider.call("__FAIL__")
        
        # max_retries=2, so should try 3 times total (0, 1, 2)
        assert result.attempts == base_config.max_retries + 1
        assert result.error is not None
        # Retry history should have max_retries entries (not attempts - 1 because all failed)
        assert len(result.retry_history) == base_config.max_retries


class TestMetadataContract:
    """Test metadata consistency across providers."""
    
    def test_stub_metadata_is_dict(self, stub_provider):
        """Metadata must always be a dict."""
        result = stub_provider.call("test")
        assert isinstance(result.metadata, dict)
    
    def test_stub_token_fields_numeric_if_present(self, stub_provider):
        """Token usage fields must be numeric if present."""
        result = stub_provider.call("test")
        
        for field in ['prompt_tokens', 'completion_tokens', 'total_tokens']:
            if field in result.metadata:
                assert isinstance(result.metadata[field], (int, float))


class TestConfigImmutability:
    """Test that providers do not mutate Config objects."""
    
    def test_stub_does_not_mutate_config(self, base_config):
        """Provider must not modify config object."""
        original_config = copy.deepcopy(base_config)
        provider = StubProvider(base_config)
        
        provider.call("test")
        
        # Config should remain unchanged
        assert base_config.provider == original_config.provider
        assert base_config.model == original_config.model
        assert base_config.max_retries == original_config.max_retries
        assert base_config.backoff_base_ms == original_config.backoff_base_ms
        assert base_config.backoff_multiplier == original_config.backoff_multiplier


class TestExceptionHandling:
    """Test that providers never leak raw SDK exceptions."""
    
    def test_stub_never_raises_on_failure(self, stub_provider):
        """Provider must never raise exceptions; must return error in response."""
        # This should fail but not raise
        result = stub_provider.call("__FAIL__")
        assert isinstance(result, ProviderResponse)
        assert result.error is not None


class TestModelListingContract:
    """Test model listing behavior."""
    
    def test_stub_list_models_returns_list(self, stub_provider):
        """list_models must return a list."""
        models = stub_provider.list_models()
        assert isinstance(models, list)
    
    def test_stub_model_info_structure(self, stub_provider):
        """ModelInfo objects must have required structure."""
        models = stub_provider.list_models()
        assert len(models) > 0
        
        for model in models:
            assert isinstance(model, ModelInfo)
            assert hasattr(model, 'name')
            assert hasattr(model, 'metadata')
            assert isinstance(model.name, str)
            assert len(model.name) > 0
            assert isinstance(model.metadata, dict)


# ═══════════════════════════════════════════════════════════════════════
# Gemini Provider Tests (with mocking)
# ═══════════════════════════════════════════════════════════════════════

class TestGeminiProviderContract:
    """Test Gemini provider contract compliance with mocking."""
    
    @pytest.fixture
    def mock_gemini_config(self):
        """Config for Gemini provider."""
        return Config(
            provider="gemini",
            model="gemini-pro",
            max_retries=2,
            backoff_base_ms=100,
            backoff_multiplier=2.0,
            ledger_enabled=False,
        )
    
    def test_gemini_returns_provider_response(self, mock_gemini_config):
        """Gemini must return ProviderResponse."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch('ai_factory.providers.gemini.genai') as mock_genai:
                # Mock the SDK
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.text = "Test response"
                mock_response.usage_metadata = None
                mock_response.candidates = []
                
                mock_client.models.generate_content.return_value = mock_response
                mock_genai.Client.return_value = mock_client
                
                provider = GeminiProvider(mock_gemini_config)
                result = provider.call("test")
                
                assert isinstance(result, ProviderResponse)
                assert isinstance(result.text, str)
                assert result.attempts >= 1
    
    def test_gemini_error_handling(self, mock_gemini_config):
        """Gemini must handle errors without raising."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch('ai_factory.providers.gemini.genai') as mock_genai:
                mock_client = MagicMock()
                mock_client.models.generate_content.side_effect = Exception("API Error")
                mock_genai.Client.return_value = mock_client
                
                provider = GeminiProvider(mock_gemini_config)
                result = provider.call("test")
                
                assert isinstance(result, ProviderResponse)
                assert result.error is not None
                assert "API Error" in result.error or "Exception" in result.error
    
    def test_gemini_retry_on_transient_error(self, mock_gemini_config):
        """Gemini must retry on transient errors."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch('ai_factory.providers.gemini.genai') as mock_genai:
                with patch('time.sleep'):  # Don't actually sleep
                    mock_client = MagicMock()
                    mock_success = MagicMock()
                    mock_success.text = "Success"
                    mock_success.usage_metadata = None
                    mock_success.candidates = []
                    
                    # Fail once with 429, then succeed
                    mock_client.models.generate_content.side_effect = [
                        Exception("429 Rate limit"),
                        mock_success
                    ]
                    mock_genai.Client.return_value = mock_client
                    
                    provider = GeminiProvider(mock_gemini_config)
                    result = provider.call("test")
                    
                    assert result.attempts == 2
                    assert len(result.retry_history) == 1
                    assert result.error is None
                    assert result.text == "Success"


# ═══════════════════════════════════════════════════════════════════════
# OpenRouter Provider Tests (with mocking)
# ═══════════════════════════════════════════════════════════════════════

class TestOpenRouterProviderContract:
    """Test OpenRouter provider contract compliance with mocking."""
    
    @pytest.fixture
    def mock_openrouter_config(self):
        """Config for OpenRouter provider."""
        return Config(
            provider="openrouter",
            model="openai/gpt-3.5-turbo",
            max_retries=2,
            backoff_base_ms=100,
            backoff_multiplier=2.0,
            ledger_enabled=False,
        )
    
    def test_openrouter_returns_provider_response(self, mock_openrouter_config):
        """OpenRouter must return ProviderResponse."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            with patch('ai_factory.providers.openrouter.OpenAI') as mock_openai:
                # Mock the client
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_message = MagicMock()
                mock_message.content = "Test response"
                mock_choice = MagicMock()
                mock_choice.message = mock_message
                mock_choice.finish_reason = "stop"
                mock_response.choices = [mock_choice]
                mock_response.id = "test-id"
                mock_response.model = "openai/gpt-3.5-turbo"
                mock_response.usage = None
                
                mock_client.chat.completions.create.return_value = mock_response
                mock_openai.return_value = mock_client
                
                provider = OpenRouterProvider(mock_openrouter_config)
                result = provider.call("test")
                
                assert isinstance(result, ProviderResponse)
                assert isinstance(result.text, str)
                assert result.attempts >= 1
    
    def test_openrouter_error_handling(self, mock_openrouter_config):
        """OpenRouter must handle errors without raising."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            with patch('ai_factory.providers.openrouter.OpenAI') as mock_openai:
                mock_client = MagicMock()
                mock_client.chat.completions.create.side_effect = Exception("API Error")
                mock_openai.return_value = mock_client
                
                provider = OpenRouterProvider(mock_openrouter_config)
                result = provider.call("test")
                
                assert isinstance(result, ProviderResponse)
                assert result.error is not None
                assert "API Error" in result.error or "Exception" in result.error
    
    def test_openrouter_retry_on_transient_error(self, mock_openrouter_config):
        """OpenRouter must retry on transient errors."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            with patch('ai_factory.providers.openrouter.OpenAI') as mock_openai:
                with patch('time.sleep'):  # Don't actually sleep
                    mock_client = MagicMock()
                    mock_response = MagicMock()
                    mock_message = MagicMock()
                    mock_message.content = "Success"
                    mock_choice = MagicMock()
                    mock_choice.message = mock_message
                    mock_response.choices = [mock_choice]
                    mock_response.usage = None
                    
                    # Fail once with 503, then succeed
                    mock_client.chat.completions.create.side_effect = [
                        Exception("503 Service unavailable"),
                        mock_response
                    ]
                    mock_openai.return_value = mock_client
                    
                    provider = OpenRouterProvider(mock_openrouter_config)
                    result = provider.call("test")
                    
                    assert result.attempts == 2
                    assert len(result.retry_history) == 1
                    assert result.error is None
                    assert result.text == "Success"
