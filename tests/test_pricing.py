"""
Tests for price table loading, staleness, and resolution.

Every test passes an explicit pricing_path and allow_network=False so the
suite never depends on the invoking user's ~/.aifactory/pricing.toml or on
network access.
"""
from datetime import date, timedelta

import pytest

from ai_factory import pricing
from ai_factory.pricing import (
    DEFAULT_MAX_AGE_DAYS,
    SOURCE_TABLE,
    SOURCE_TABLE_STALE,
    ModelPrice,
    PricingTable,
    load_pricing_table,
    resolve_price,
)


TABLE = """
[meta]
fetched_at = {fetched_at}

[anthropic."claude-opus-5"]
input_per_1m = 5.0
output_per_1m = 25.0
cache_write_per_1m = 6.25
cache_read_per_1m = 0.5

[gemini."gemini-2.5-flash"]
input_per_1m = 0.3
output_per_1m = 2.5
"""


def write_table(tmp_path, fetched_at="2026-08-30", body=None):
    path = tmp_path / "pricing.toml"
    path.write_text(body if body is not None else TABLE.format(fetched_at=fetched_at))
    return str(path)


@pytest.fixture(autouse=True)
def reset_warning_state():
    """The stale warning fires once per process; reset it between tests."""
    pricing._warned_stale = False
    yield
    pricing._warned_stale = False


def test_load_table_parses_entries(tmp_path):
    table = load_pricing_table(write_table(tmp_path))
    assert len(table.prices) == 2
    price = table.prices[("anthropic", "claude-opus-5")]
    assert price.input_per_1m == 5.0
    assert price.output_per_1m == 25.0
    assert price.cache_read_per_1m == 0.5
    assert price.source == SOURCE_TABLE


def test_missing_table_is_empty_not_an_error(tmp_path):
    table = load_pricing_table(str(tmp_path / "nope.toml"))
    assert table.prices == {}
    assert table.is_stale() is False  # nothing to be stale about


def test_half_specified_entry_is_skipped(tmp_path):
    body = '[meta]\nfetched_at = 2026-08-30\n\n[openai."gpt-x"]\ninput_per_1m = 1.0\n'
    table = load_pricing_table(write_table(tmp_path, body=body))
    # Only an input rate: including it would silently under-report cost.
    assert ("openai", "gpt-x") not in table.prices


def test_fresh_table_is_not_stale(tmp_path):
    recent = (date.today() - timedelta(days=DEFAULT_MAX_AGE_DAYS - 1)).isoformat()
    table = load_pricing_table(write_table(tmp_path, fetched_at=recent))
    assert table.is_stale(DEFAULT_MAX_AGE_DAYS) is False


def test_old_table_is_stale(tmp_path):
    old = (date.today() - timedelta(days=DEFAULT_MAX_AGE_DAYS + 1)).isoformat()
    table = load_pricing_table(write_table(tmp_path, fetched_at=old))
    assert table.is_stale(DEFAULT_MAX_AGE_DAYS) is True
    assert table.age_days() == DEFAULT_MAX_AGE_DAYS + 1


def test_undated_table_counts_as_stale(tmp_path):
    body = '[anthropic."claude-opus-5"]\ninput_per_1m = 5.0\noutput_per_1m = 25.0\n'
    table = load_pricing_table(write_table(tmp_path, body=body))
    assert table.fetched_at is None
    # Unknown age must not be treated as fresh - that is how prices rot.
    assert table.is_stale(DEFAULT_MAX_AGE_DAYS) is True


def test_resolve_price_exact_match(tmp_path):
    price = resolve_price("anthropic", "claude-opus-5",
                          pricing_path=write_table(tmp_path), allow_network=False)
    assert price is not None
    assert price.input_per_1m == 5.0
    assert price.source == SOURCE_TABLE


def test_resolve_price_unknown_model_returns_none(tmp_path):
    price = resolve_price("anthropic", "claude-not-a-model",
                          pricing_path=write_table(tmp_path), allow_network=False)
    # No guess. A confidently wrong price is worse than no price.
    assert price is None


def test_resolve_price_no_fuzzy_matching(tmp_path):
    # A near-miss must not resolve to the full id's price.
    assert resolve_price("anthropic", "claude-opus",
                         pricing_path=write_table(tmp_path), allow_network=False) is None


def test_stale_price_is_returned_but_marked(tmp_path, capsys):
    old = (date.today() - timedelta(days=DEFAULT_MAX_AGE_DAYS + 5)).isoformat()
    price = resolve_price("anthropic", "claude-opus-5",
                          pricing_path=write_table(tmp_path, fetched_at=old),
                          allow_network=False)
    # Useful beats exact: still priced, but flagged.
    assert price is not None
    assert price.input_per_1m == 5.0
    assert price.source == SOURCE_TABLE_STALE

    warning = capsys.readouterr().err
    assert "price table" in warning
    assert "pricing refresh" in warning


def test_stale_warning_prints_only_once(tmp_path, capsys):
    old = (date.today() - timedelta(days=99)).isoformat()
    path = write_table(tmp_path, fetched_at=old)
    for _ in range(3):
        resolve_price("anthropic", "claude-opus-5", pricing_path=path, allow_network=False)
    assert capsys.readouterr().err.count("price table") == 1


def test_ollama_is_free_without_a_table_entry(tmp_path):
    price = resolve_price("ollama", "llama3",
                          pricing_path=str(tmp_path / "absent.toml"), allow_network=False)
    assert price is not None
    assert price.input_per_1m == 0.0
    assert price.output_per_1m == 0.0
