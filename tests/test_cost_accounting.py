"""
Tests for hybrid token accounting and cost computation.

The contract under test: exact counts are used when the provider reports
them, character estimates otherwise, and every number carries provenance so
an estimate is never mistaken for a measurement.
"""
import pytest

from ai_factory import run
from ai_factory.config import Config
from ai_factory.ledger_analysis import analyze_ledger, format_summary
from ai_factory.metrics import (
    DEFAULT_CHARS_PER_TOKEN,
    build_metrics,
    compute_cost,
    estimate_tokens,
)
from ai_factory.pricing import SOURCE_TABLE, ModelPrice
from ai_factory.result import TOKENS_ESTIMATED, TOKENS_PROVIDER


PRICE = ModelPrice(
    input_per_1m=5.0,
    output_per_1m=25.0,
    cache_write_per_1m=6.25,
    cache_read_per_1m=0.5,
    source=SOURCE_TABLE,
)

TABLE = """
[meta]
fetched_at = 2999-01-01

[stub."stub-1"]
input_per_1m = 1000000.0
output_per_1m = 1000000.0
"""


@pytest.fixture
def table_path(tmp_path):
    path = tmp_path / "pricing.toml"
    path.write_text(TABLE)
    return str(path)


# --- estimation -----------------------------------------------------------

def test_estimate_tokens_uses_ratio():
    assert estimate_tokens(400, 4.0) == 100
    assert estimate_tokens(0) == 0
    assert estimate_tokens(1) == 1  # never rounds a non-empty string to zero


def test_estimate_tokens_rejects_bad_ratio():
    with pytest.raises(ValueError):
        estimate_tokens(100, 0)


# --- token source ---------------------------------------------------------

def test_provider_tokens_are_used_when_reported():
    m = build_metrics(
        input_chars=4000, output_chars=400, latency_ms=10, success=True,
        provider_metadata={"prompt_tokens": 17, "completion_tokens": 3},
    )
    # Exact counts win over the character estimate, which would say 1000/100.
    assert m.prompt_tokens == 17
    assert m.completion_tokens == 3
    assert m.total_tokens == 20
    assert m.token_source == TOKENS_PROVIDER
    assert m.tokens_estimated is False


def test_falls_back_to_estimate_when_provider_is_silent():
    m = build_metrics(
        input_chars=400, output_chars=40, latency_ms=10, success=True,
        provider_metadata={"exit_code": 0},  # copilot_cli shape: no usage
    )
    assert m.prompt_tokens == 100
    assert m.completion_tokens == 10
    assert m.token_source == TOKENS_ESTIMATED
    assert m.tokens_estimated is True


def test_failed_run_does_not_invent_tokens():
    m = build_metrics(input_chars=400, output_chars=0, latency_ms=10, success=False)
    # Billing a call that may never have happened would overstate spend.
    assert m.prompt_tokens is None
    assert m.token_source is None
    assert m.cost_usd is None


def test_custom_chars_per_token_is_respected():
    m = build_metrics(input_chars=300, output_chars=0, latency_ms=1,
                      success=True, chars_per_token=3.0)
    assert m.prompt_tokens == 100


# --- cache accounting -----------------------------------------------------

def test_cache_tokens_are_lifted_from_raw_usage():
    m = build_metrics(
        input_chars=10, output_chars=10, latency_ms=1, success=True,
        provider_metadata={
            "prompt_tokens": 12,
            "completion_tokens": 5,
            "usage": {
                "input_tokens": 12,
                "output_tokens": 5,
                "cache_creation_input_tokens": 1000,
                "cache_read_input_tokens": 8000,
            },
        },
    )
    assert m.cache_creation_input_tokens == 1000
    assert m.cache_read_input_tokens == 8000


def test_absent_cache_fields_stay_none_not_zero():
    m = build_metrics(input_chars=10, output_chars=10, latency_ms=1, success=True,
                      provider_metadata={"prompt_tokens": 5, "completion_tokens": 5})
    # None means "provider said nothing"; zero would claim a measured miss.
    assert m.cache_creation_input_tokens is None
    assert m.cache_read_input_tokens is None


# --- cost -----------------------------------------------------------------

def test_cost_from_exact_tokens():
    cost, defaulted = compute_cost(PRICE, prompt_tokens=1_000_000,
                                   completion_tokens=1_000_000)
    assert cost == pytest.approx(30.0)  # 5 + 25
    assert defaulted is False


def test_cost_includes_cache_tokens_separately():
    cost, _ = compute_cost(
        PRICE, prompt_tokens=0, completion_tokens=0,
        cache_creation_input_tokens=1_000_000,
        cache_read_input_tokens=1_000_000,
    )
    assert cost == pytest.approx(6.25 + 0.5)


def test_default_cache_rates_mark_cost_as_estimated():
    bare = ModelPrice(input_per_1m=10.0, output_per_1m=20.0)  # no cache rates
    cost, defaulted = compute_cost(bare, prompt_tokens=0, completion_tokens=0,
                                   cache_read_input_tokens=1_000_000)
    assert defaulted is True
    assert cost == pytest.approx(1.0)  # 10.0 * 0.10 read multiplier


def test_no_price_means_no_cost():
    m = build_metrics(input_chars=400, output_chars=400, latency_ms=1,
                      success=True, price=None)
    assert m.cost_usd is None
    assert m.price_source is None


def test_estimated_tokens_make_cost_estimated():
    m = build_metrics(input_chars=400, output_chars=400, latency_ms=1,
                      success=True, price=PRICE)
    assert m.cost_usd is not None
    assert m.cost_estimated is True
    assert m.price_source == SOURCE_TABLE


def test_exact_tokens_make_cost_exact():
    m = build_metrics(
        input_chars=400, output_chars=400, latency_ms=1, success=True, price=PRICE,
        provider_metadata={"prompt_tokens": 100, "completion_tokens": 100},
    )
    assert m.cost_estimated is False


# --- end to end -----------------------------------------------------------

def test_run_records_estimated_cost_and_provenance(tmp_path, table_path):
    ledger = tmp_path / "LEDGER.is"
    config = Config(
        provider="stub", model="stub-1",
        ledger_path=str(ledger), pricing_path=table_path,
    )
    result = run("hello world", config)

    assert result.success is True
    # The stub reports no usage, so this must be estimated and labelled.
    assert result.metrics.token_source == TOKENS_ESTIMATED
    assert result.metrics.cost_estimated is True
    assert result.metrics.cost_usd is not None

    text = ledger.read_text()
    assert "(token_source \"char_estimate\")" in text
    assert "(cost_estimated true)" in text
    assert "(cost_usd" in text


def test_summary_separates_estimated_from_measured(tmp_path, table_path):
    ledger = tmp_path / "LEDGER.is"
    config = Config(
        provider="stub", model="stub-1",
        ledger_path=str(ledger), pricing_path=table_path,
    )
    run("hello world", config)
    run("hello again", config)

    summary = analyze_ledger(str(ledger))
    assert summary.cost_entries == 2
    assert summary.estimated_cost_entries == 2
    assert summary.exact_cost_entries == 0
    assert summary.estimated_cost_usd == pytest.approx(summary.total_cost_usd)

    rendered = format_summary(summary)
    assert "ESTIMATED" in rendered


def test_reasoning_tokens_recovered_from_provider_total():
    # Gemini shape: total exceeds prompt+completion because thinking tokens
    # are counted but not broken out.
    m = build_metrics(
        input_chars=10, output_chars=10, latency_ms=1, success=True, price=PRICE,
        provider_metadata={"prompt_tokens": 5, "completion_tokens": 20,
                           "total_tokens": 107},
    )
    assert m.reasoning_tokens == 82
    # Billed at the output rate along with the visible completion.
    expected = 5 / 1e6 * 5.0 + (20 + 82) / 1e6 * 25.0
    assert m.cost_usd == pytest.approx(expected)


def test_no_reasoning_tokens_when_total_matches():
    m = build_metrics(
        input_chars=10, output_chars=10, latency_ms=1, success=True,
        provider_metadata={"prompt_tokens": 5, "completion_tokens": 20,
                           "total_tokens": 25},
    )
    assert m.reasoning_tokens is None
