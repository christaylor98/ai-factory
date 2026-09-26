"""
Main runner for ai-factory
"""
import time
from dataclasses import replace
from .config import Config
from .result import RunResult, ModelInfo, EmbedResult
from .metrics import build_metrics
from .provider_registry import get_provider
from .ledger import write_run_to_ledger, write_embed_to_ledger
from .pricing import resolve_price


def _resolve_price(config: Config):
    """
    Look up the price for this run's provider/model.

    Price lookup must never break a run: an unreadable table or an offline
    price API means cost is simply not recorded.
    """
    if not config.pricing_enabled:
        return None
    try:
        return resolve_price(
            provider=config.provider,
            model=config.model,
            pricing_path=config.pricing_path,
            max_age_days=config.pricing_max_age_days,
        )
    except Exception:
        return None


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

        # A provider may settle the model itself (local: the id the server
        # lists when none was named); price and record that, not the request.
        if provider.config.model != config.model:
            config = replace(config, model=provider.config.model)

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
            provider_metadata=response.metadata,
            price=_resolve_price(config),
            chars_per_token=config.chars_per_token,
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
            metrics=metrics,
            error=response.error
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
            metrics=metrics,
            error=f"{type(e).__name__}: {str(e)}"
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
    # replace() keeps base_url and the rest, so a listing asks the same
    # server a run would.
    provider_config = replace(
        config,
        provider=provider_name,
        ledger_enabled=False,  # Model listing doesn't log
    )
    
    provider = get_provider(provider_name, provider_config)
    return provider.list_models()


def embed(text: str, config: Config) -> EmbedResult:
    """
    Generate embeddings for text using the configured provider.
    
    This is a separate operation from run() and uses provider abstraction.
    Records a ledger entry synchronously.
    
    Args:
        text: Input text to embed
        config: Configuration
        
    Returns:
        EmbedResult with vector, success, error, and metrics
    """
    try:
        # Get provider
        provider = get_provider(config.provider, config)
        
        # Call provider embed method
        result = provider.embed(text)
        
        # Write to ledger (failures here don't fail the embed operation)
        write_embed_to_ledger(
            config=config,
            text=text,
            result=result
        )
        
        return result
    
    except Exception as e:
        # Handle unexpected errors
        from .result import Metrics
        
        metrics = Metrics(
            input_chars=len(text),
            output_chars=0,
            latency_ms=1,
            success=False
        )
        
        return EmbedResult(
            vector=[],
            success=False,
            error=f"{type(e).__name__}: {str(e)}",
            metrics=metrics
        )
