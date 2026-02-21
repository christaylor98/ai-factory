"""
Test Copilot CLI provider
"""
import os
import subprocess
from unittest.mock import Mock, patch, MagicMock
import pytest

from ai_factory.config import Config
from ai_factory.providers.copilot_cli import CopilotCLIProvider
from ai_factory.result import ProviderResponse


def test_copilot_cli_requires_binary():
    """Test that CopilotCLIProvider requires copilot binary."""
    config = Config(provider="copilot_cli", model="default")
    
    with patch("shutil.which", return_value=None):
        with pytest.raises(ValueError, match="GitHub Copilot CLI not found"):
            CopilotCLIProvider(config)


def test_copilot_cli_finds_binary():
    """Test that CopilotCLIProvider finds copilot binary."""
    config = Config(provider="copilot_cli", model="default")
    
    with patch("shutil.which", return_value="/usr/local/bin/copilot"):
        provider = CopilotCLIProvider(config)
        assert provider.copilot_path == "/usr/local/bin/copilot"


def test_copilot_cli_call_success():
    """Test successful Copilot CLI call."""
    config = Config(provider="copilot_cli", model="default")
    
    with patch("shutil.which", return_value="/usr/local/bin/copilot"):
        provider = CopilotCLIProvider(config)
        
        # Mock subprocess.run to return success
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Hello from Copilot!\n"
        mock_result.stderr = ""
        
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            response = provider.call("test prompt")
            
            # Verify call
            assert mock_run.call_count == 1
            args = mock_run.call_args[0][0]
            assert args[0] == "/usr/local/bin/copilot"
            assert args[1] == "-p"
            assert args[2] == "test prompt"
            assert "--yolo" in args
            assert "--silent" in args
            
            # Verify response
            assert response.text == "Hello from Copilot!"
            assert response.attempts == 1
            assert response.error is None
            assert response.metadata["exit_code"] == 0
            assert "runtime_ms" in response.metadata
            assert len(response.retry_history) == 0


def test_copilot_cli_call_with_model():
    """Test Copilot CLI call with specific model."""
    config = Config(provider="copilot_cli", model="gpt-5.2")
    
    with patch("shutil.which", return_value="/usr/local/bin/copilot"):
        provider = CopilotCLIProvider(config)
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Response with gpt-5.2"
        mock_result.stderr = ""
        
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            response = provider.call("test prompt")
            
            # Verify model flag included
            args = mock_run.call_args[0][0]
            assert "--model" in args
            assert "gpt-5.2" in args
            
            assert response.text == "Response with gpt-5.2"
            assert response.error is None


def test_copilot_cli_call_failure_non_retryable():
    """Test Copilot CLI call with non-retryable failure."""
    config = Config(provider="copilot_cli", model="default", max_retries=2)
    
    with patch("shutil.which", return_value="/usr/local/bin/copilot"):
        provider = CopilotCLIProvider(config)
        
        # Mock subprocess.run to return auth error
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: Not authenticated. Please run 'copilot login'."
        
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            response = provider.call("test prompt")
            
            # Should not retry auth errors
            assert mock_run.call_count == 1
            assert response.attempts == 1
            assert response.error is not None
            assert "CopilotCLIError" in response.error
            assert response.text == ""
            assert len(response.retry_history) == 0


def test_copilot_cli_call_failure_retryable():
    """Test Copilot CLI call with retryable failure then success."""
    config = Config(
        provider="copilot_cli",
        model="default",
        max_retries=2,
        backoff_base_ms=10,  # Fast for testing
    )
    
    with patch("shutil.which", return_value="/usr/local/bin/copilot"):
        provider = CopilotCLIProvider(config)
        
        # First call fails with timeout, second succeeds
        call_count = 0
        
        def mock_subprocess_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            result = Mock()
            if call_count == 1:
                # First attempt: timeout error
                result.returncode = 1
                result.stdout = ""
                result.stderr = "Error: Connection timed out"
            else:
                # Second attempt: success
                result.returncode = 0
                result.stdout = "Success after retry"
                result.stderr = ""
            
            return result
        
        with patch("subprocess.run", side_effect=mock_subprocess_run):
            response = provider.call("test prompt")
            
            # Should retry once then succeed
            assert call_count == 2
            assert response.attempts == 2
            assert response.text == "Success after retry"
            assert response.error is None
            assert len(response.retry_history) == 1
            assert response.retry_history[0].error_type == "ExitCode1"
            assert "timed out" in response.retry_history[0].error_message.lower()


def test_copilot_cli_call_timeout():
    """Test Copilot CLI call with subprocess timeout."""
    config = Config(
        provider="copilot_cli",
        model="default",
        max_retries=2,
        backoff_base_ms=10,
    )
    
    with patch("shutil.which", return_value="/usr/local/bin/copilot"):
        provider = CopilotCLIProvider(config)
        provider.timeout = 1  # Short timeout for testing
        
        # Mock subprocess.run to raise TimeoutExpired
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("copilot", 1)):
            response = provider.call("test prompt")
            
            # Should retry up to max_retries
            assert response.attempts == 3  # 1 initial + 2 retries
            assert response.error is not None
            assert "TimeoutError" in response.error
            assert response.text == ""
            assert len(response.retry_history) == 2


def test_copilot_cli_call_empty_output_success():
    """Test Copilot CLI call with empty output but success exit code."""
    config = Config(provider="copilot_cli", model="default")
    
    with patch("shutil.which", return_value="/usr/local/bin/copilot"):
        provider = CopilotCLIProvider(config)
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "   \n  \n"  # Only whitespace
        mock_result.stderr = ""
        
        with patch("subprocess.run", return_value=mock_result):
            response = provider.call("test prompt")
            
            # Empty output but success
            assert response.text == ""
            assert response.error is None
            assert response.metadata["exit_code"] == 0


def test_copilot_cli_list_models_not_supported():
    """Test that list_models raises NotImplementedError."""
    config = Config(provider="copilot_cli", model="default")
    
    with patch("shutil.which", return_value="/usr/local/bin/copilot"):
        provider = CopilotCLIProvider(config)
        
        with pytest.raises(NotImplementedError, match="not support programmatic model listing"):
            provider.list_models()


def test_copilot_cli_timeout_configurable():
    """Test that timeout is configurable via environment."""
    config = Config(provider="copilot_cli", model="default")
    
    # Test default timeout
    with patch("shutil.which", return_value="/usr/local/bin/copilot"):
        with patch.dict(os.environ, {}, clear=False):
            if "COPILOT_TIMEOUT" in os.environ:
                del os.environ["COPILOT_TIMEOUT"]
            provider = CopilotCLIProvider(config)
            assert provider.timeout == 60  # Default
    
    # Test custom timeout
    with patch("shutil.which", return_value="/usr/local/bin/copilot"):
        with patch.dict(os.environ, {"COPILOT_TIMEOUT": "120"}):
            provider = CopilotCLIProvider(config)
            assert provider.timeout == 120


def test_copilot_cli_retry_history_metadata():
    """Test that retry history records correct metadata."""
    config = Config(
        provider="copilot_cli",
        model="default",
        max_retries=2,
        backoff_base_ms=100,
        backoff_multiplier=2.0,
    )
    
    with patch("shutil.which", return_value="/usr/local/bin/copilot"):
        provider = CopilotCLIProvider(config)
        
        # All attempts fail with retryable error
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: Rate limit exceeded (429)"
        
        with patch("subprocess.run", return_value=mock_result):
            response = provider.call("test prompt")
            
            # Should exhaust all retries
            assert response.attempts == 3
            assert response.error is not None
            assert len(response.retry_history) == 2
            
            # Check backoff progression
            assert response.retry_history[0].backoff_ms == 100
            assert response.retry_history[1].backoff_ms == 200
            assert response.retry_history[0].attempt == 1
            assert response.retry_history[1].attempt == 2
