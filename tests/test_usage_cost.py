"""A3 (axChat CONTROLLER_SPEC §6.2): cache writes priced by duration, from a raw per-call usage block."""
import pytest

from ai_factory.metrics import usage_cost
from ai_factory.pricing import ModelPrice, load_pricing_table

# A real Sonnet 5 segment (axChat finops.py): its usage priced by hand equalled its total_cost_usd.
REAL = {"input_tokens": 6, "cache_creation_input_tokens": 12888, "cache_read_input_tokens": 18558,
        "output_tokens": 5319, "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 12888}}
SONNET = ModelPrice(2.0, 10.0, cache_write_per_1m=2.5, cache_read_per_1m=0.2, cache_write_1h_per_1m=4.0)


def test_a_real_segment_prices_to_its_billed_total():
    cost, defaulted = usage_cost(SONNET, REAL)
    assert cost == pytest.approx(0.1084656) and not defaulted


def test_missing_cache_rates_use_anthropics_multipliers_and_say_so():
    cost, defaulted = usage_cost(ModelPrice(2.0, 10.0), REAL)
    assert cost == pytest.approx(0.1084656) and defaulted


def test_one_hour_writes_cost_more_than_five_minute_ones():
    five = {"cache_creation_input_tokens": 1_000_000, "cache_creation": {"ephemeral_5m_input_tokens": 1_000_000}}
    hour = {"cache_creation_input_tokens": 1_000_000, "cache_creation": {"ephemeral_1h_input_tokens": 1_000_000}}
    unsplit = {"cache_creation_input_tokens": 1_000_000}          # no split reported: priced as 5-minute
    assert usage_cost(SONNET, five)[0] == pytest.approx(2.5)
    assert usage_cost(SONNET, hour)[0] == pytest.approx(4.0)
    assert usage_cost(SONNET, unsplit)[0] == pytest.approx(2.5)


def test_no_price_or_no_usage_is_no_cost():
    assert usage_cost(None, REAL) == (None, False)
    assert usage_cost(SONNET, None) == (None, False)


def test_the_table_reads_the_one_hour_rate(tmp_path):
    p = tmp_path / "pricing.toml"
    p.write_text('[anthropic."claude-sonnet-5"]\ninput_per_1m = 2\noutput_per_1m = 10\ncache_write_1h_per_1m = 4\n')
    assert load_pricing_table(str(p)).prices[("anthropic", "claude-sonnet-5")].cache_write_1h_per_1m == 4.0
