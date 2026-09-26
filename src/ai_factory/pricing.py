"""
Model price resolution for ai-factory.

Two sources, in priority order:

1. The provider's own API, where it publishes prices. Only OpenRouter does
   (``GET /api/v1/models`` returns a per-model ``pricing`` object). Anthropic,
   OpenAI and Gemini model endpoints carry no price fields at all.
2. A user-maintained TOML table, by default ``~/.aifactory/pricing.toml``.

A model absent from both resolves to ``None`` and the run records no cost
rather than a guessed one - a stale price is worse than a missing one because
it looks authoritative.

Staleness
---------
The table carries a ``[meta] fetched_at`` date. Past ``max_age_days``
(default 10) prices are still used - useful beats exact - but every stale
lookup is marked ``pricing_table_stale`` in the run record, and a one-time
warning is printed per process. Refresh is never automatic: ``run()`` making
surprise outbound HTTP would break the determinism ARCHITECTURE.md 4.5
promises. Refresh explicitly with ``ai-factory pricing refresh``, which reads
OpenRouter's JSON API rather than scraping vendor pricing pages - those are
marketing HTML that changes layout silently, and a mis-parse yields a
confidently wrong number.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


DEFAULT_PRICING_PATH = Path.home() / ".aifactory" / "pricing.toml"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

DEFAULT_MAX_AGE_DAYS = 10

# Live prices are fetched at most once per process per this interval.
_OPENROUTER_CACHE_TTL_S = 3600.0

# Price provenance markers, recorded on every run so a reader can tell where
# a number came from without re-deriving it.
SOURCE_PROVIDER_API = "provider_api"
SOURCE_TABLE = "pricing_table"
SOURCE_TABLE_STALE = "pricing_table_stale"

# OpenRouter namespaces its ids as "<vendor>/<model>". These map onto
# ai-factory provider names so one refresh populates first-party entries too.
_VENDOR_TO_PROVIDER = {
    "anthropic": "anthropic",
    "openai": "openai",
    "google": "gemini",
}

_warned_stale = False


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1,000,000 tokens."""

    input_per_1m: float
    output_per_1m: float
    cache_write_per_1m: Optional[float] = None      # a 5-minute cache write (Anthropic: 1.25x input)
    cache_read_per_1m: Optional[float] = None
    source: str = SOURCE_TABLE
    cache_write_1h_per_1m: Optional[float] = None   # a 1-hour cache write (Anthropic: 2x input)


@dataclass(frozen=True)
class PricingTable:
    """A loaded price table plus the age metadata needed to judge it."""

    prices: Dict[Tuple[str, str], ModelPrice]
    fetched_at: Optional[date] = None
    path: Optional[str] = None

    def age_days(self) -> Optional[int]:
        if self.fetched_at is None:
            return None
        return (date.today() - self.fetched_at).days

    def is_stale(self, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> bool:
        """
        True when the table is older than max_age_days.

        A table with no ``fetched_at`` counts as stale: an undated table is
        of unknown age, and treating unknown as fresh is how prices rot
        silently.
        """
        if not self.prices:
            return False
        age = self.age_days()
        return True if age is None else age > max_age_days


def _staleness_warning(table: "PricingTable", max_age_days: int) -> str:
    age = table.age_days()
    age_text = f"{age} days old" if age is not None else "undated"
    return (
        f"Warning: ai-factory price table is {age_text} "
        f"(limit {max_age_days}); costs may be wrong. "
        f"Refresh with: ai-factory pricing refresh"
    )


def warn_if_stale(table: "PricingTable",
                  max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> bool:
    """
    Print a staleness warning at most once per process.

    Returns True if the table is stale, whether or not this call printed.
    """
    global _warned_stale
    if not table.is_stale(max_age_days):
        return False
    if not _warned_stale:
        print(_staleness_warning(table, max_age_days), file=sys.stderr, flush=True)
        _warned_stale = True
    return True


# --------------------------------------------------------------------------
# TOML table
# --------------------------------------------------------------------------

def load_pricing_table(path: Optional[str] = None) -> PricingTable:
    """
    Load the TOML price table.

    Shape:

        [meta]
        fetched_at = 2026-08-30

        [anthropic."claude-opus-5"]
        input_per_1m = 5.0
        output_per_1m = 25.0
        cache_read_per_1m = 0.50

    Returns an empty table if the file is absent or unreadable. Missing
    prices are a normal state, not an error.

    Args:
        path: Explicit table path, defaulting to ~/.aifactory/pricing.toml.
              Always pass this explicitly from tests so they never depend on
              the invoking user's real configuration.
    """
    target = Path(path) if path is not None else DEFAULT_PRICING_PATH
    if tomllib is None or not target.exists():
        return PricingTable(prices={}, path=str(target))

    try:
        with open(target, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return PricingTable(prices={}, path=str(target))

    fetched_at = None
    meta = data.get("meta")
    if isinstance(meta, dict):
        raw = meta.get("fetched_at")
        if isinstance(raw, date) and not isinstance(raw, datetime):
            fetched_at = raw
        elif isinstance(raw, datetime):
            fetched_at = raw.date()
        elif isinstance(raw, str):
            try:
                fetched_at = date.fromisoformat(raw[:10])
            except ValueError:
                fetched_at = None

    prices: Dict[Tuple[str, str], ModelPrice] = {}
    for provider, models in data.items():
        if provider == "meta" or not isinstance(models, dict):
            continue
        for model, fields in models.items():
            if not isinstance(fields, dict):
                continue
            if "input_per_1m" not in fields or "output_per_1m" not in fields:
                # A half-specified entry would silently under-report cost.
                continue
            try:
                prices[(provider, model)] = ModelPrice(
                    input_per_1m=float(fields["input_per_1m"]),
                    output_per_1m=float(fields["output_per_1m"]),
                    cache_write_per_1m=(
                        float(fields["cache_write_per_1m"])
                        if "cache_write_per_1m" in fields else None
                    ),
                    cache_read_per_1m=(
                        float(fields["cache_read_per_1m"])
                        if "cache_read_per_1m" in fields else None
                    ),
                    source=SOURCE_TABLE,
                    cache_write_1h_per_1m=(
                        float(fields["cache_write_1h_per_1m"])
                        if "cache_write_1h_per_1m" in fields else None
                    ),
                )
            except (TypeError, ValueError):
                continue

    return PricingTable(prices=prices, fetched_at=fetched_at, path=str(target))


# --------------------------------------------------------------------------
# OpenRouter live prices
# --------------------------------------------------------------------------

_openrouter_cache: Optional[Dict[str, ModelPrice]] = None
_openrouter_fetched_at: float = 0.0


def _per_1m(pricing: dict, key: str) -> Optional[float]:
    """OpenRouter quotes USD per single token, as strings."""
    raw = pricing.get(key)
    if raw in (None, "", "-1"):
        return None
    try:
        return float(raw) * 1_000_000.0
    except (TypeError, ValueError):
        return None


def fetch_openrouter_prices(timeout: float = 20.0,
                            force: bool = False) -> Dict[str, ModelPrice]:
    """
    Fetch live per-model prices from OpenRouter's public JSON API (no key).

    Returns an empty dict on any failure - offline, rate limited, shape
    changed - so cost falls back to the table and then to unknown.
    """
    global _openrouter_cache, _openrouter_fetched_at

    now = time.monotonic()
    if (not force and _openrouter_cache is not None
            and (now - _openrouter_fetched_at) < _OPENROUTER_CACHE_TTL_S):
        return _openrouter_cache

    prices: Dict[str, ModelPrice] = {}
    try:
        req = urllib.request.Request(
            OPENROUTER_MODELS_URL, headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        for entry in payload.get("data", []):
            model_id = entry.get("id")
            pricing = entry.get("pricing") or {}
            if not model_id:
                continue
            inp = _per_1m(pricing, "prompt")
            out = _per_1m(pricing, "completion")
            if inp is None or out is None:
                continue
            prices[model_id] = ModelPrice(
                input_per_1m=inp,
                output_per_1m=out,
                cache_write_per_1m=_per_1m(pricing, "input_cache_write"),
                cache_read_per_1m=_per_1m(pricing, "input_cache_read"),
                source=SOURCE_PROVIDER_API,
            )
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError):
        return _openrouter_cache if _openrouter_cache is not None else {}

    _openrouter_cache = prices
    _openrouter_fetched_at = now
    return prices


# --------------------------------------------------------------------------
# Refresh (explicit only)
# --------------------------------------------------------------------------

def _format_toml(rows: Dict[Tuple[str, str], ModelPrice], today: date) -> str:
    lines = [
        "# ai-factory model prices, USD per 1,000,000 tokens.",
        "#",
        "# Generated by `ai-factory pricing refresh` from OpenRouter's model API,",
        "# which publishes structured prices for its own catalogue and for",
        "# first-party Anthropic / OpenAI / Google models. Figures are indicative:",
        "# a reseller's rate can differ from a vendor's list price. Hand-edit any",
        "# entry to pin an exact contracted rate - refresh overwrites this file.",
        "#",
        "# Model ids must match exactly what you pass as Config.model; there is no",
        "# fuzzy matching, because a near-miss would attach a confidently wrong",
        "# number to a run.",
        "",
        "[meta]",
        f"fetched_at = {today.isoformat()}",
        "",
    ]
    for (provider, model) in sorted(rows):
        price = rows[(provider, model)]
        lines.append(f'[{provider}."{model}"]')
        lines.append(f"input_per_1m = {price.input_per_1m:g}")
        lines.append(f"output_per_1m = {price.output_per_1m:g}")
        if price.cache_write_per_1m is not None:
            lines.append(f"cache_write_per_1m = {price.cache_write_per_1m:g}")
        if price.cache_read_per_1m is not None:
            lines.append(f"cache_read_per_1m = {price.cache_read_per_1m:g}")
        if price.cache_write_1h_per_1m is not None:
            lines.append(f"cache_write_1h_per_1m = {price.cache_write_1h_per_1m:g}")
        lines.append("")
    return "\n".join(lines)


def refresh_pricing_table(path: Optional[str] = None,
                          timeout: float = 20.0) -> Tuple[int, str]:
    """
    Rebuild the TOML price table from OpenRouter's JSON API.

    Populates both the ``openrouter`` namespace (full ``vendor/model`` ids)
    and first-party namespaces (``anthropic``, ``openai``, ``gemini``) by
    stripping the vendor prefix, so a single refresh covers direct API use.

    Returns:
        (number_of_entries, path_written)

    Raises:
        RuntimeError: if the fetch returns nothing, so a transient outage
                      never truncates a good table to an empty one.
    """
    live = fetch_openrouter_prices(timeout=timeout, force=True)
    if not live:
        raise RuntimeError(
            "Could not fetch prices from OpenRouter; existing table left unchanged."
        )

    rows: Dict[Tuple[str, str], ModelPrice] = {}
    for model_id, price in live.items():
        rows[("openrouter", model_id)] = price
        vendor, _, bare = model_id.partition("/")
        provider = _VENDOR_TO_PROVIDER.get(vendor)
        if provider and bare:
            rows[(provider, bare)] = price

    target = Path(path) if path is not None else DEFAULT_PRICING_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_format_toml(rows, date.today()), encoding="utf-8")

    global _warned_stale
    _warned_stale = False
    return (len(rows), str(target))


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------

def resolve_price(
    provider: str,
    model: str,
    pricing_path: Optional[str] = None,
    allow_network: bool = True,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> Optional[ModelPrice]:
    """
    Resolve the price for one provider/model, provider API first.

    Matching is exact - no prefix or fuzzy matching.

    Args:
        provider: Provider name, e.g. "anthropic".
        model: Model id exactly as sent to the provider.
        pricing_path: Override for the TOML table path.
        allow_network: Set False to skip the OpenRouter fetch (tests, offline).
        max_age_days: Table age beyond which prices are marked stale.

    Returns:
        ModelPrice, or None when neither source knows this model. A price
        drawn from a stale table is returned with source
        ``pricing_table_stale`` rather than withheld.
    """
    if provider in ("ollama", "local"):
        # Local inference: no marginal cost. A fact, not a lookup.
        return ModelPrice(0.0, 0.0, 0.0, 0.0, source=SOURCE_PROVIDER_API)

    if provider == "openrouter" and allow_network:
        live = fetch_openrouter_prices()
        if model in live:
            return live[model]

    table = load_pricing_table(pricing_path)
    price = table.prices.get((provider, model))
    if price is None:
        return None

    if warn_if_stale(table, max_age_days):
        return ModelPrice(
            input_per_1m=price.input_per_1m,
            output_per_1m=price.output_per_1m,
            cache_write_per_1m=price.cache_write_per_1m,
            cache_read_per_1m=price.cache_read_per_1m,
            source=SOURCE_TABLE_STALE,
            cache_write_1h_per_1m=price.cache_write_1h_per_1m,
        )
    return price
