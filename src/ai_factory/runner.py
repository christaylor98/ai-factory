"""
Main runner for ai-factory
"""
import time
from .config import Config
from .result import RunResult, ModelInfo
from .metrics import build_metrics
from .provider_registry import get_provider
from .ledger import write_run_to_ledger


def run(prompt: str, config: Config) -> RunResult:
    """
    Run a prompt through the AI provider.
    
    Args:
        prompt: Input prompt
        config: Configuration
        
    Returns:
        RunResult with output, success, and metrics
    """
    start_time = time.time()
    
    try:
        # Get provider
        provider = get_provider(config.provider, config)
        
        # Call provider (retry logic is internal to provider)
        response = provider.call(prompt)
        
        # Calculate metrics
        end_time = time.time()
        latency_ms = max(1, int((end_time - start_time) * 1000))
        
        success = response.error is None
        output = response.text if success else ""
        
        metrics = build_metrics(
            input_chars=len(prompt),
            output_chars=len(response.text),
            latency_ms=latency_ms,
            success=success,
            provider_metadata=response.metadata
        )
        
        # Write to ledger (failures here don't fail the run)
        write_run_to_ledger(
            config=config,
            prompt=prompt,
            response=response,
            metrics=metrics,
            success=success
        )
        
        return RunResult(
            output=output,
            success=success,
            metrics=metrics
        )
    
    except Exception as e:
        # Handle unexpected errors
        end_time = time.time()
        latency_ms = max(1, int((end_time - start_time) * 1000))
        
        metrics = build_metrics(
            input_chars=len(prompt),
            output_chars=0,
            latency_ms=latency_ms,
            success=False
        )
        
        return RunResult(
            output="",
            success=False,
            metrics=metrics
        )


def list_models(provider_name: str, config: Config) -> list[ModelInfo]:
    """
    List available models for a provider.
    
    Note: Model listing does NOT write to ledger.
    
    Args:
        provider_name: Name of the provider
        config: Configuration (provider field may be overridden)
        
    Returns:
        List of ModelInfo objects
    """
    # Create a config copy with the specified provider
    # (We don't modify the original config)
    provider_config = Config(
        provider=provider_name,
        model=config.model,
        max_retries=config.max_retries,
        backoff_base_ms=config.backoff_base_ms,
        backoff_multiplier=config.backoff_multiplier,
        ledger_enabled=False,  # Model listing doesn't log
        ledger_path=config.ledger_path,
        capture_prompt=config.capture_prompt,
        capture_output=config.capture_output,
        capture_limit_chars=config.capture_limit_chars,
    )
    
    provider = get_provider(provider_name, provider_config)
    return provider.list_models()
