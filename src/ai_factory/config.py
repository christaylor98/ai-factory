"""
Configuration dataclass for ai-factory
"""
from dataclasses import dataclass, field


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
        if self.ledger_format not in ("is", "json"):
            raise ValueError("ledger_format must be 'is' or 'json'")
