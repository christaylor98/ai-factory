"""
Result dataclasses for ai-factory
"""
from dataclasses import dataclass, field
from typing import Optional


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


@dataclass
class RunResult:
    """Result of a run() call."""
    
    output: str
    success: bool
    metrics: Metrics
