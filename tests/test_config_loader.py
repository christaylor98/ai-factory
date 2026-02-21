"""
Tests for configuration loading with TOML and precedence resolution.
"""
import os
import sys
import tempfile
from pathlib import Path
import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ai_factory.config import Config
from ai_factory.config_loader import load_config, _flatten_config, _env_to_config_dict


class TestConfigPrecedence:
    """Test configuration precedence resolution."""
    
    def test_defaults_only(self):
        """Test that defaults work when no other config sources exist."""
        config = load_config(provider="test", model="test-model")
        
        assert config.provider == "test"
        assert config.model == "test-model"
        assert config.max_retries == 2
        assert config.backoff_base_ms == 250
        assert config.backoff_multiplier == 2.0
        assert config.ledger_enabled == True
        assert config.ledger_path == "./LEDGER.is"
        assert config.capture_prompt == False
        assert config.capture_output == False
        assert config.capture_limit_chars == 20000
    
    def test_cli_overrides_defaults(self):
        """Test that CLI arguments override defaults."""
        config = load_config(
            provider="cli-provider",
            model="cli-model",
            max_retries=5,
            backoff_base_ms=500,
            ledger_enabled=False,
        )
        
        assert config.provider == "cli-provider"
        assert config.model == "cli-model"
        assert config.max_retries == 5
        assert config.backoff_base_ms == 500
        assert config.ledger_enabled == False
    
    def test_env_overrides_defaults(self, monkeypatch):
        """Test that environment variables override defaults."""
        monkeypatch.setenv("AIFACTORY_PROVIDER", "env-provider")
        monkeypatch.setenv("AIFACTORY_MODEL", "env-model")
        monkeypatch.setenv("AIFACTORY_MAX_RETRIES", "7")
        monkeypatch.setenv("AIFACTORY_LEDGER_ENABLED", "false")
        
        config = load_config()
        
        assert config.provider == "env-provider"
        assert config.model == "env-model"
        assert config.max_retries == 7
        assert config.ledger_enabled == False
    
    def test_cli_overrides_env(self, monkeypatch):
        """Test that CLI arguments override environment variables."""
        monkeypatch.setenv("AIFACTORY_PROVIDER", "env-provider")
        monkeypatch.setenv("AIFACTORY_MODEL", "env-model")
        monkeypatch.setenv("AIFACTORY_MAX_RETRIES", "7")
        
        config = load_config(
            provider="cli-provider",
            model="cli-model",
            max_retries=3,
        )
        
        assert config.provider == "cli-provider"
        assert config.model == "cli-model"
        assert config.max_retries == 3
    
    def test_required_fields_missing(self):
        """Test that missing required fields raise error."""
        with pytest.raises(ValueError, match="provider is required"):
            load_config(model="test-model")
        
        with pytest.raises(ValueError, match="model is required"):
            load_config(provider="test-provider")


class TestConfigImmutability:
    """Test that Config is immutable."""
    
    def test_config_is_frozen(self):
        """Test that Config cannot be modified after creation."""
        config = load_config(provider="test", model="test-model")
        
        with pytest.raises(Exception):  # FrozenInstanceError in Python 3.11+
            config.provider = "modified"
        
        with pytest.raises(Exception):
            config.max_retries = 999
        
        with pytest.raises(Exception):
            config.ledger_enabled = False
    
    def test_config_validation(self):
        """Test that Config validates inputs."""
        with pytest.raises(ValueError, match="max_retries must be >= 0"):
            load_config(provider="test", model="test", max_retries=-1)
        
        with pytest.raises(ValueError, match="backoff_base_ms must be > 0"):
            load_config(provider="test", model="test", backoff_base_ms=0)
        
        with pytest.raises(ValueError, match="backoff_multiplier must be >= 1.0"):
            load_config(provider="test", model="test", backoff_multiplier=0.5)


class TestTOMLLoading:
    """Test TOML configuration loading."""
    
    def test_flatten_config_default_section(self):
        """Test flattening of [default] section."""
        toml_data = {
            "default": {
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "max_retries": 3,
            }
        }
        
        flat = _flatten_config(toml_data)
        
        assert flat["provider"] == "gemini"
        assert flat["model"] == "gemini-2.5-flash"
        assert flat["max_retries"] == 3
    
    def test_flatten_config_ledger_section(self):
        """Test flattening of [ledger] section."""
        toml_data = {
            "ledger": {
                "enabled": False,
                "path": "/custom/ledger.is",
                "capture_prompt": True,
                "capture_output": True,
            }
        }
        
        flat = _flatten_config(toml_data)
        
        assert flat["ledger_enabled"] == False
        assert flat["ledger_path"] == "/custom/ledger.is"
        assert flat["capture_prompt"] == True
        assert flat["capture_output"] == True
    
    def test_flatten_config_preserves_provider_sections(self):
        """Test that provider-specific sections are preserved."""
        toml_data = {
            "default": {"provider": "openrouter"},
            "openrouter": {
                "http_referer": "https://example.com",
                "x_title": "ai-factory",
            }
        }
        
        flat = _flatten_config(toml_data)
        
        assert flat["provider"] == "openrouter"
        assert "_provider_configs" in flat
        assert "openrouter" in flat["_provider_configs"]


class TestEnvVarMapping:
    """Test environment variable to config mapping."""
    
    def test_env_to_config_dict_basic(self, monkeypatch):
        """Test basic environment variable mapping."""
        monkeypatch.setenv("AIFACTORY_PROVIDER", "test-provider")
        monkeypatch.setenv("AIFACTORY_MODEL", "test-model")
        monkeypatch.setenv("AIFACTORY_MAX_RETRIES", "5")
        
        config_dict = _env_to_config_dict()
        
        assert config_dict["provider"] == "test-provider"
        assert config_dict["model"] == "test-model"
        assert config_dict["max_retries"] == 5
    
    def test_env_to_config_dict_ledger(self, monkeypatch):
        """Test ledger-related environment variables."""
        monkeypatch.setenv("AIFACTORY_LEDGER_ENABLED", "false")
        monkeypatch.setenv("AIFACTORY_LEDGER_PATH", "/tmp/test.is")
        monkeypatch.setenv("AIFACTORY_CAPTURE_PROMPT", "true")
        
        config_dict = _env_to_config_dict()
        
        assert config_dict["ledger_enabled"] == False
        assert config_dict["ledger_path"] == "/tmp/test.is"
        assert config_dict["capture_prompt"] == True
    
    def test_env_to_config_dict_boolean_parsing(self, monkeypatch):
        """Test that boolean environment variables are parsed correctly."""
        # Test true values
        for true_val in ["true", "True", "TRUE", "1", "yes", "Yes"]:
            monkeypatch.setenv("AIFACTORY_LEDGER_ENABLED", true_val)
            config_dict = _env_to_config_dict()
            assert config_dict["ledger_enabled"] == True
        
        # Test false values
        for false_val in ["false", "False", "FALSE", "0", "no"]:
            monkeypatch.setenv("AIFACTORY_LEDGER_ENABLED", false_val)
            config_dict = _env_to_config_dict()
            assert config_dict["ledger_enabled"] == False
    
    def test_env_to_config_dict_invalid_numbers(self, monkeypatch):
        """Test that invalid number values are ignored."""
        monkeypatch.setenv("AIFACTORY_MAX_RETRIES", "not-a-number")
        
        config_dict = _env_to_config_dict()
        
        # Should not have max_retries if it can't be parsed
        assert "max_retries" not in config_dict


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
