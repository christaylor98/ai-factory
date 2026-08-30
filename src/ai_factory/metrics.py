"""
Metrics construction utilities.

Pure functions only: no IO, no network, no provider imports
(docs/ARCHITECTURE.md 6.6). Prices are resolved in pricing.py and passed in
here as plain numbers.

Token accounting is hybrid and always labelled:

  * If the provider reported usage, those exact counts are used and
    ``token_source`` is ``"provider"``.
  * Otherwise counts are derived from character length and ``token_source``
    is ``"char_estimate"``. Character division is a rough proxy - it runs
    high on prose and low on code, JSON and non-Latin scripts - so anything
    downstream that presents a cost must surface the marker with it.
"""
from typing import Optional, Tuple

from .result import Metrics, TOKENS_PROVIDER, TOKENS_ESTIMATED

# Rough English-prose ratio. Deliberately a single obvious default rather
# than a per-provider table, because a fabricated per-provider ratio would
# imply a precision this method does not have.
DEFAULT_CHARS_PER_TOKEN = 4.0

# Anthropic's published cache multipliers, used only when a price entry
# omits explicit cache rates. Applying them marks the cost as estimated.
_CACHE_WRITE_MULTIPLIER = 1.25
_CACHE_READ_MULTIPLIER = 0.10


def estimate_tokens(chars: int, chars_per_token: float = DEFAULT_CHARS_PER_TOKEN) -> int:
    """Estimate a token count from a character count."""
    if chars <= 0:
        return 0
    if chars_per_token <= 0:
        raise ValueError("chars_per_token must be > 0")
    return max(1, round(chars / chars_per_token))


def _provider_tokens(metadata: Optional[dict]) -> Tuple[
    Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]
]:
    """
    Pull exact token counts out of provider metadata.

    Every provider adapter normalises its own usage shape to the flat
    ``prompt_tokens`` / ``completion_tokens`` / ``total_tokens`` keys.
    Anthropic additionally carries the raw ``usage`` object (via
    ``model_dump()``), which is where the cache counters live.

    Returns:
        (prompt, completion, total, cache_creation, cache_read); each None
        when the provider did not report it.
    """
    if not isinstance(metadata, dict):
        return (None, None, None, None, None)

    def as_int(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    prompt = as_int(metadata.get("prompt_tokens"))
    completion = as_int(metadata.get("completion_tokens"))
    total = as_int(metadata.get("total_tokens"))

    cache_creation = None
    cache_read = None
    usage = metadata.get("usage")
    if isinstance(usage, dict):
        cache_creation = as_int(usage.get("cache_creation_input_tokens"))
        cache_read = as_int(usage.get("cache_read_input_tokens"))

    return (prompt, completion, total, cache_creation, cache_read)


def compute_cost(
    price,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    cache_creation_input_tokens: Optional[int] = None,
    cache_read_input_tokens: Optional[int] = None,
    reasoning_tokens: Optional[int] = None,
) -> Tuple[Optional[float], bool]:
    """
    Compute cost in USD from token counts and a ModelPrice.

    Cached tokens are billed separately from ordinary input: providers that
    report caching exclude cache reads and cache writes from the plain input
    count, so the three are summed rather than overlapping.

    Returns:
        (cost_usd, used_default_cache_rates). The second element is True when
        a cache rate had to be inferred from the input rate, which makes the
        resulting cost an approximation.
    """
    if price is None:
        return (None, False)
    if prompt_tokens is None and completion_tokens is None:
        return (None, False)

    used_default_cache_rates = False
    cost = 0.0

    cost += (prompt_tokens or 0) / 1_000_000.0 * price.input_per_1m
    # Reasoning tokens are billed at the output rate alongside the visible
    # completion, so they are added here rather than ignored.
    cost += ((completion_tokens or 0) + (reasoning_tokens or 0)) / 1_000_000.0 * price.output_per_1m

    if cache_creation_input_tokens:
        rate = price.cache_write_per_1m
        if rate is None:
            rate = price.input_per_1m * _CACHE_WRITE_MULTIPLIER
            used_default_cache_rates = True
        cost += cache_creation_input_tokens / 1_000_000.0 * rate

    if cache_read_input_tokens:
        rate = price.cache_read_per_1m
        if rate is None:
            rate = price.input_per_1m * _CACHE_READ_MULTIPLIER
            used_default_cache_rates = True
        cost += cache_read_input_tokens / 1_000_000.0 * rate

    return (cost, used_default_cache_rates)


def build_metrics(
    input_chars: int,
    output_chars: int,
    latency_ms: int,
    success: bool,
    price=None,
    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
    **optional_fields
) -> Metrics:
    """
    Build a Metrics object, resolving tokens and cost.

    Args:
        input_chars: Number of input characters.
        output_chars: Number of output characters.
        latency_ms: Latency in milliseconds.
        success: Whether the run succeeded.
        price: Optional ModelPrice (from pricing.resolve_price).
        chars_per_token: Divisor used only when the provider reports nothing.
        **optional_fields: ``provider_metadata``, plus explicit overrides for
            any token field (an explicitly passed count wins over both the
            provider metadata and the estimate).

    Returns:
        Metrics, with token_source / price_source / cost_estimated set so a
        reader can tell exactly how each number was arrived at.
    """
    metadata = optional_fields.get("provider_metadata")

    meta_prompt, meta_completion, meta_total, cache_creation, cache_read = \
        _provider_tokens(metadata)

    # Explicit arguments beat metadata; metadata beats estimation.
    prompt_tokens = optional_fields.get("prompt_tokens", meta_prompt)
    completion_tokens = optional_fields.get("completion_tokens", meta_completion)
    total_tokens = optional_fields.get("total_tokens", meta_total)

    if prompt_tokens is not None or completion_tokens is not None:
        token_source = TOKENS_PROVIDER
    elif success:
        # Nothing reported. Fall back to characters and say so.
        prompt_tokens = estimate_tokens(input_chars, chars_per_token)
        completion_tokens = estimate_tokens(output_chars, chars_per_token)
        token_source = TOKENS_ESTIMATED
    else:
        # A failed run has no meaningful output to estimate from, and
        # inventing input tokens for a call that may never have been billed
        # would overstate spend.
        token_source = None

    # A provider-reported total larger than prompt+completion means it counted
    # tokens it did not break out - reasoning/thinking tokens. Recover them so
    # they are costed rather than silently dropped.
    reasoning_tokens = None
    if (token_source == TOKENS_PROVIDER and total_tokens is not None
            and prompt_tokens is not None and completion_tokens is not None):
        remainder = total_tokens - prompt_tokens - completion_tokens
        if remainder > 0:
            reasoning_tokens = remainder

    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

    cost_usd = optional_fields.get("cost_usd")
    price_source = None
    cost_estimated = None

    if cost_usd is None and token_source is not None:
        cost_usd, used_default_cache_rates = compute_cost(
            price,
            prompt_tokens,
            completion_tokens,
            cache_creation,
            cache_read,
            reasoning_tokens,
        )
        if cost_usd is not None:
            price_source = price.source
            cost_estimated = (
                token_source == TOKENS_ESTIMATED or used_default_cache_rates
            )

    return Metrics(
        input_chars=input_chars,
        output_chars=output_chars,
        latency_ms=latency_ms,
        success=success,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        finish_reason=optional_fields.get("finish_reason"),
        provider_metadata=metadata,
        cache_creation_input_tokens=cache_creation,
        cache_read_input_tokens=cache_read,
        reasoning_tokens=reasoning_tokens,
        token_source=token_source,
        price_source=price_source,
        cost_estimated=cost_estimated,
    )
