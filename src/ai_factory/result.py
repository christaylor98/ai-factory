"""
Result dataclasses for ai-factory
"""
from dataclasses import dataclass, field
from typing import Optional

# Token provenance markers. Exposed as constants so callers compare against
# these rather than hardcoding strings that can drift.
TOKENS_PROVIDER = "provider"
TOKENS_ESTIMATED = "char_estimate"


@dataclass
class RetryRecord:
    """Record of a single retry attempt."""
    
    attempt: int
    error_type: str
    error_message: str
    backoff_ms: int


@dataclass
class ProviderResponse:
    """Response from a provider call."""
    
    text: str
    metadata: dict = field(default_factory=dict)
    attempts: int = 1
    retry_history: list[RetryRecord] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class ModelInfo:
    """Information about a model."""
    
    name: str
    context_window: Optional[int] = None
    input_cost_per_1k: Optional[float] = None
    output_cost_per_1k: Optional[float] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Metrics:
    """Metrics from a run."""
    
    # Required fields
    input_chars: int
    output_chars: int
    latency_ms: int
    success: bool
    
    # Optional fields
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    finish_reason: Optional[str] = None
    provider_metadata: Optional[dict] = None

    # Cache accounting. Populated only by providers that report it
    # (Anthropic today). None means "provider said nothing", which is not
    # the same as zero.
    cache_creation_input_tokens: Optional[int] = None
    cache_read_input_tokens: Optional[int] = None

    # Tokens the provider counted in its total but reported under neither
    # prompt nor completion - thinking/reasoning tokens on Gemini and the
    # OpenAI reasoning models. They are billed at the output rate, so leaving
    # them out under-reports cost, often by several times.
    reasoning_tokens: Optional[int] = None

    # Provenance. Never infer accuracy from the numbers alone - read these.
    #   token_source: TOKENS_PROVIDER  - exact counts reported by the provider
    #                 TOKENS_ESTIMATED - derived from character count
    #                 None             - no tokens at all
    #   price_source: "provider_api" | "pricing_table" | None
    #   cost_estimated: True when cost_usd rests on estimated token counts.
    token_source: Optional[str] = None
    price_source: Optional[str] = None
    cost_estimated: Optional[bool] = None

    @property
    def tokens_estimated(self) -> bool:
        """True when token counts are character-derived rather than reported."""
        return self.token_source == TOKENS_ESTIMATED


@dataclass
class RunResult:
    """Result of a run() call."""
    
    output: str
    success: bool
    metrics: Metrics


@dataclass
class EmbedResult:
    """Result of an embed() call."""
    
    vector: list[float]
    success: bool
    error: Optional[str]
    metrics: Metrics
