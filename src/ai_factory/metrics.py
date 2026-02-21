"""
Metrics construction utilities
"""
from .result import Metrics


def build_metrics(
    input_chars: int,
    output_chars: int,
    latency_ms: int,
    success: bool,
    **optional_fields
) -> Metrics:
    """
    Build a Metrics object with required and optional fields.
    
    Args:
        input_chars: Number of input characters
        output_chars: Number of output characters
        latency_ms: Latency in milliseconds
        success: Whether the run succeeded
        **optional_fields: Optional metric fields (prompt_tokens, completion_tokens, etc.)
    
    Returns:
        Metrics object
    """
    return Metrics(
        input_chars=input_chars,
        output_chars=output_chars,
        latency_ms=latency_ms,
        success=success,
        prompt_tokens=optional_fields.get("prompt_tokens"),
        completion_tokens=optional_fields.get("completion_tokens"),
        total_tokens=optional_fields.get("total_tokens"),
        cost_usd=optional_fields.get("cost_usd"),
        finish_reason=optional_fields.get("finish_reason"),
        provider_metadata=optional_fields.get("provider_metadata"),
    )
