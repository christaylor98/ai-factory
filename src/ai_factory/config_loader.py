"""
Configuration loader with TOML support and precedence resolution.

Load order (later overrides earlier):
1. ~/.aifactory/config.toml
2. ./aifactory.toml
3. Environment variables
4. CLI arguments
5. Defaults
"""
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Use tomllib (Python 3.11+) or fallback to tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

from .config import Config


def _load_toml_file(path: Path) -> Optional[Dict[str, Any]]:
    """Load TOML file if it exists."""
    if not tomllib:
        return None
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return None


def _merge_config(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge override config into base config."""
    result = base.copy()
    for key, value in override.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = _merge_config(result[key], value)
        else:
            result[key] = value
    return result


def _env_to_config_dict() -> Dict[str, Any]:
    """Extract configuration from environment variables."""
    config = {}
    
    if "AIFACTORY_PROVIDER" in os.environ:
        config["provider"] = os.environ["AIFACTORY_PROVIDER"]
    if "AIFACTORY_MODEL" in os.environ:
        config["model"] = os.environ["AIFACTORY_MODEL"]
    if "AIFACTORY_MAX_RETRIES" in os.environ:
        try:
            config["max_retries"] = int(os.environ["AIFACTORY_MAX_RETRIES"])
        except ValueError:
            pass
    if "AIFACTORY_BACKOFF_BASE_MS" in os.environ:
        try:
            config["backoff_base_ms"] = int(os.environ["AIFACTORY_BACKOFF_BASE_MS"])
        except ValueError:
            pass
    if "AIFACTORY_BACKOFF_MULTIPLIER" in os.environ:
        try:
            config["backoff_multiplier"] = float(os.environ["AIFACTORY_BACKOFF_MULTIPLIER"])
        except ValueError:
            pass
    
    if "AIFACTORY_LEDGER_ENABLED" in os.environ:
        value = os.environ["AIFACTORY_LEDGER_ENABLED"].lower()
        config["ledger_enabled"] = value in ("true", "1", "yes")
    if "AIFACTORY_LEDGER_PATH" in os.environ:
        config["ledger_path"] = os.environ["AIFACTORY_LEDGER_PATH"]
    if "AIFACTORY_LEDGER_FORMAT" in os.environ:
        config["ledger_format"] = os.environ["AIFACTORY_LEDGER_FORMAT"]
    if "AIFACTORY_CAPTURE_PROMPT" in os.environ:
        value = os.environ["AIFACTORY_CAPTURE_PROMPT"].lower()
        config["capture_prompt"] = value in ("true", "1", "yes")
    if "AIFACTORY_CAPTURE_OUTPUT" in os.environ:
        value = os.environ["AIFACTORY_CAPTURE_OUTPUT"].lower()
        config["capture_output"] = value in ("true", "1", "yes")
    if "AIFACTORY_CAPTURE_LIMIT_CHARS" in os.environ:
        try:
            config["capture_limit_chars"] = int(os.environ["AIFACTORY_CAPTURE_LIMIT_CHARS"])
        except ValueError:
            pass
    
    return config


def _flatten_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten nested TOML config to flat structure for Config constructor.
    
    Converts:
        {
            "default": {"provider": "gemini"},
            "ledger": {"enabled": true}
        }
    To:
        {
            "provider": "gemini",
            "ledger_enabled": true
        }
    
    Args:
        data: Nested TOML data
        
    Returns:
        Flattened configuration dict
    """
    result = {}
    
    # Extract from [default] section
    if "default" in data:
        default = data["default"]
        if "provider" in default:
            result["provider"] = default["provider"]
        if "model" in default:
            result["model"] = default["model"]
        if "max_retries" in default:
            result["max_retries"] = default["max_retries"]
        if "backoff_base_ms" in default:
            result["backoff_base_ms"] = default["backoff_base_ms"]
        if "backoff_multiplier" in default:
            result["backoff_multiplier"] = default["backoff_multiplier"]
    
    # Extract from [ledger] section
    if "ledger" in data:
        ledger = data["ledger"]
        if "enabled" in ledger:
            result["ledger_enabled"] = ledger["enabled"]
        if "path" in ledger:
            result["ledger_path"] = ledger["path"]
        if "format" in ledger:
            result["ledger_format"] = ledger["format"]
        if "capture_prompt" in ledger:
            result["capture_prompt"] = ledger["capture_prompt"]
        if "capture_output" in ledger:
            result["capture_output"] = ledger["capture_output"]
        if "capture_limit_chars" in ledger:
            result["capture_limit_chars"] = ledger["capture_limit_chars"]
    
    provider_sections = {}
    for key in data:
        if key not in ("default", "ledger"):
            provider_sections[key] = data[key]
    if provider_sections:
        result["_provider_configs"] = provider_sections
    return result


def load_config(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_retries: Optional[int] = None,
    backoff_base_ms: Optional[int] = None,
    backoff_multiplier: Optional[float] = None,
    ledger_enabled: Optional[bool] = None,
    ledger_path: Optional[str] = None,
    ledger_format: Optional[str] = None,
    capture_prompt: Optional[bool] = None,
    capture_output: Optional[bool] = None,
    capture_limit_chars: Optional[int] = None,
) -> Config:
    """
    Load configuration with proper precedence.
    Load order: defaults, ~/.aifactory/config.toml, ./aifactory.toml, env vars, CLI args.
    """
    config_dict = {
        "max_retries": 2,
        "backoff_base_ms": 250,
        "backoff_multiplier": 2.0,
        "ledger_enabled": True,
        "ledger_path": "./LEDGER.is",
        "ledger_format": "is",
        "capture_prompt": False,
        "capture_output": False,
        "capture_limit_chars": 20000,
    }
    
    global_config_path = Path.home() / ".aifactory" / "config.toml"
    global_toml = _load_toml_file(global_config_path)
    if global_toml:
        global_flat = _flatten_config(global_toml)
        config_dict.update(global_flat)
    
    local_config_path = Path.cwd() / "aifactory.toml"
    local_toml = _load_toml_file(local_config_path)
    if local_toml:
        local_flat = _flatten_config(local_toml)
        config_dict.update(local_flat)
    
    env_config = _env_to_config_dict()
    config_dict.update(env_config)
    
    if provider is not None:
        config_dict["provider"] = provider
    if model is not None:
        config_dict["model"] = model
    if max_retries is not None:
        config_dict["max_retries"] = max_retries
    if backoff_base_ms is not None:
        config_dict["backoff_base_ms"] = backoff_base_ms
    if backoff_multiplier is not None:
        config_dict["backoff_multiplier"] = backoff_multiplier
    if ledger_enabled is not None:
        config_dict["ledger_enabled"] = ledger_enabled
    if ledger_path is not None:
        config_dict["ledger_path"] = ledger_path
    if ledger_format is not None:
        config_dict["ledger_format"] = ledger_format
    if capture_prompt is not None:
        config_dict["capture_prompt"] = capture_prompt
    if capture_output is not None:
        config_dict["capture_output"] = capture_output
    if capture_limit_chars is not None:
        config_dict["capture_limit_chars"] = capture_limit_chars
    
    config_dict.pop("_provider_configs", None)
    
    if config_dict.get("ledger_format") == "json" and config_dict.get("ledger_path") == "./LEDGER.is":
        config_dict["ledger_path"] = "./LEDGER.jsonl"
    
    if "provider" not in config_dict:
        raise ValueError("provider is required (set via config file, env, or CLI)")
    if "model" not in config_dict:
        raise ValueError("model is required (set via config file, env, or CLI)")
    
    return Config(**config_dict)
