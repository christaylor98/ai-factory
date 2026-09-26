"""
FastMCP server exposing ai-factory's library API.

Each tool is a thin wrapper around an ai-factory function. Configuration
falls through `ai_factory.config_loader.load_config()` so the server inherits
the same precedence (env vars + ~/.aifactory/config.toml + ./aifactory.toml)
that the CLI uses; per-call arguments override the loaded values.
"""
from dataclasses import asdict, replace
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from ..config import Config
from ..config_loader import load_config
from ..env import load_env
from ..ledger import append_event as _append_event
from ..ledger_analysis import analyze_ledger as _analyze_ledger
from ..runner import embed as _embed
from ..runner import list_models as _list_models
from ..runner import run as _run


mcp = FastMCP("ai-factory")


def _drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def _load_config_or_ledger_only(**overrides) -> Config:
    """Like load_config, but for ledger-only operations: if no provider/model
    are configured anywhere, fall back to a Config with placeholder values
    so we can still read `ledger_path` / `ledger_format` defaults.
    """
    try:
        return load_config(**overrides)
    except ValueError:
        overrides.setdefault("provider", "stub")
        overrides.setdefault("model", "unused")
        return load_config(**overrides)


@mcp.tool()
def run_prompt(
    prompt: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_retries: Optional[int] = None,
    capture_prompt: Optional[bool] = None,
    capture_output: Optional[bool] = None,
    ledger_enabled: Optional[bool] = None,
    ledger_path: Optional[str] = None,
    ledger_format: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout_s: Optional[float] = None,
    thinking: Optional[bool] = None,
) -> dict[str, Any]:
    """Execute a single prompt via the configured (or specified) provider/model.

    Returns the model output, success flag, `error` (why, when success is
    false), and full metrics. The call is recorded to the ai-factory ledger
    unless `ledger_enabled=False`.

    For routine prompts - summarise, classify, extract, reformat, short
    rewrites - pass `provider="local"`: a model on the local GPU, $0 in the
    ledger. It needs no `model` (the server's own model is used and recorded)
    and fails fast with "local server not reachable" when the server is down.
    Keep frontier providers for reasoning-heavy work.

    `base_url`: OpenAI-compatible endpoint for the openai and local providers
    (local defaults to http://localhost:8089/v1).
    `temperature`, `max_tokens`: passthrough for anthropic, openrouter, openai
    and local; other providers use their SDK default.
    `timeout_s`: per-request timeout for openai and local.
    `thinking`: local only; off by default so max_tokens goes to the answer.
    """
    overrides = _drop_none({
        "provider": provider,
        "model": model,
        "max_retries": max_retries,
        "capture_prompt": capture_prompt,
        "capture_output": capture_output,
        "ledger_enabled": ledger_enabled,
        "ledger_path": ledger_path,
        "ledger_format": ledger_format,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout_s": timeout_s,
        "thinking": thinking,
    })
    config = load_config(**overrides)
    if base_url is not None:
        config = replace(config, base_url=base_url)
    return asdict(_run(prompt, config))


@mcp.tool()
def list_models(provider: Optional[str] = None, base_url: Optional[str] = None) -> dict[str, Any]:
    """List available models for a provider.

    If `provider` is omitted, uses the configured default. `provider="local"`
    reads the local server's /v1/models. Does not write to the ledger.
    """
    overrides = _drop_none({"provider": provider})
    if "provider" not in overrides:
        config = load_config()
        provider_name = config.provider
    else:
        # `load_config` requires a `model` to instantiate Config; supply a
        # placeholder since list_models() ignores it.
        config = load_config(provider=overrides["provider"], model="unused")
        provider_name = overrides["provider"]
    if base_url is not None:
        config = replace(config, base_url=base_url)
    models = _list_models(provider_name, config)
    return {"provider": provider_name, "models": [asdict(m) for m in models]}


@mcp.tool()
def embed(
    text: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    ledger_enabled: Optional[bool] = None,
    ledger_path: Optional[str] = None,
    ledger_format: Optional[str] = None,
    include_vector: bool = True,
) -> dict[str, Any]:
    """Generate an embedding for `text` using the configured provider.

    Set `include_vector=False` to omit the vector and only return its
    dimension and metrics (useful for large batch calls).
    """
    overrides = _drop_none({
        "provider": provider,
        "model": model,
        "ledger_enabled": ledger_enabled,
        "ledger_path": ledger_path,
        "ledger_format": ledger_format,
    })
    config = load_config(**overrides)
    result = _embed(text, config)
    response: dict[str, Any] = {
        "success": result.success,
        "error": result.error,
        "dim": len(result.vector),
        "metrics": asdict(result.metrics),
    }
    if include_vector:
        response["vector"] = result.vector
    return response


@mcp.tool()
def append_ledger_event(
    event_type: str,
    data: dict[str, Any],
    ledger_path: Optional[str] = None,
    ledger_format: Optional[str] = None,
) -> dict[str, Any]:
    """Append a custom event to the ai-factory ledger.

    `event_type` becomes the s-expression tag (or JSON `event_type` field).
    `data` is the event payload — strings, numbers, bools, lists, and dicts
    are all supported.
    """
    overrides = _drop_none({
        "ledger_path": ledger_path,
        "ledger_format": ledger_format,
    })
    config = _load_config_or_ledger_only(**overrides)
    target_path = ledger_path or config.ledger_path
    target_format = ledger_format or config.ledger_format
    _append_event(
        ledger_path=target_path,
        event_type=event_type,
        data=data,
        ledger_format=target_format,
    )
    return {"ledger_path": target_path, "ledger_format": target_format}


@mcp.tool()
def analyze_ledger(ledger_path: Optional[str] = None) -> dict[str, Any]:
    """Summarise a ledger file: run counts, success rate, latency, token use,
    per-provider breakdown, and most-used model.
    """
    if ledger_path is None:
        config = _load_config_or_ledger_only()
        ledger_path = config.ledger_path
    summary = _analyze_ledger(ledger_path)
    base = asdict(summary)
    base["success_rate_percent"] = summary.success_rate_percent
    base["average_latency_ms"] = summary.average_latency_ms
    base["average_input_chars"] = summary.average_input_chars
    base["average_output_chars"] = summary.average_output_chars
    base["most_used_model"] = summary.most_used_model
    base["total_cost_usd_if_available"] = summary.total_cost_usd_if_available
    base["ledger_path"] = ledger_path
    return base


def main() -> None:
    """Entry point for `ai-factory-mcp` and `python -m ai_factory.mcp_server`."""
    load_env()   # the server reads .env for provider keys, as it always has (the launcher cd's for this)
    mcp.run()
