"""
Configuration dataclass for ai-factory
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Config:
    """
    Configuration for AI Factory execution.
    
    This dataclass is frozen (immutable) to ensure configuration
    cannot be modified after construction.
    """
    
    provider: str
    model: str
    max_retries: int = 2
    backoff_base_ms: int = 250
    backoff_multiplier: float = 2.0
    ledger_enabled: bool = True
    ledger_path: str = "./LEDGER.is"
    ledger_format: str = "is"
    capture_prompt: bool = False
    capture_output: bool = False
    capture_limit_chars: int = 20000
    base_url: str = None  # Optional: override default provider base URL (e.g., for Ollama)
    temperature: Optional[float] = None  # Optional: sampling temperature passthrough (provider default if unset)
    max_tokens: Optional[int] = None  # Optional: output token cap (provider default if unset)
    timeout_s: Optional[float] = None  # Optional: per-request timeout (SDK default if unset)
    thinking: bool = False  # local provider: let the chat template think; off spends max_tokens on answers only
    # A system prompt and a JSON schema for the answer. Only providers that declare SUPPORTS_SYSTEM /
    # SUPPORTS_SCHEMA take them (claude_code, openai, local, openrouter, stub); run() refuses them elsewhere
    # rather than dropping them silently. With a schema, RunResult.output is the answer as a JSON string.
    system_prompt: Optional[str] = None
    json_schema: Optional[dict] = None

    # Cost accounting.
    #   chars_per_token       divisor used only when a provider reports no usage
    #   pricing_path          override for ~/.aifactory/pricing.toml
    #   pricing_max_age_days  table age past which prices are marked stale and
    #                         a one-time warning is printed (0 disables ageing)
    #   pricing_enabled       set False to skip price lookup entirely
    chars_per_token: float = 4.0
    pricing_path: str = None
    pricing_max_age_days: int = 10
    pricing_enabled: bool = True

    def __post_init__(self):
        """Validate configuration."""
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.backoff_base_ms <= 0:
            raise ValueError("backoff_base_ms must be > 0")
        if self.backoff_multiplier < 1.0:
            raise ValueError("backoff_multiplier must be >= 1.0")
        if self.capture_limit_chars <= 0:
            raise ValueError("capture_limit_chars must be > 0")
        if self.temperature is not None and self.temperature < 0:
            raise ValueError("temperature must be >= 0")
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError("max_tokens must be > 0")
        if self.timeout_s is not None and self.timeout_s <= 0:
            raise ValueError("timeout_s must be > 0")
        if self.ledger_format not in ("is", "json"):
            raise ValueError("ledger_format must be 'is' or 'json'")
        if self.chars_per_token <= 0:
            raise ValueError("chars_per_token must be > 0")
        if self.pricing_max_age_days < 0:
            raise ValueError("pricing_max_age_days must be >= 0")
