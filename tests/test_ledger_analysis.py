"""
Tests for ledger analysis functionality.

Tests parsing, statistics computation, and edge cases.
"""
import os
import tempfile
import pytest
from ai_factory.ledger_analysis import (
    parse_ledger,
    compute_summary,
    format_summary,
    analyze_ledger,
    RunRecord,
)


def test_parse_empty_ledger():
    """Test parsing an empty ledger file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.is', delete=False) as f:
        ledger_path = f.name
        f.write("")
    
    try:
        records = parse_ledger(ledger_path)
        assert len(records) == 0
        
        summary = compute_summary(records)
        assert summary.total_runs == 0
        assert summary.success_rate_percent == 0.0
    finally:
        os.unlink(ledger_path)


def test_parse_missing_ledger():
    """Test parsing a non-existent ledger file."""
    records = parse_ledger("/nonexistent/path/LEDGER.is")
    assert len(records) == 0


def test_parse_single_successful_run():
    """Test parsing a single successful run."""
    ledger_content = """(run
  (timestamp "2026-02-12T20:25:03.351474Z")
  (provider "stub")
  (model "stub-1")
  (success true)
  (attempts 1)
  (metrics
    (input_chars 5)
    (output_chars 11)
    (latency_ms 100)
  )
)
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.is', delete=False) as f:
        ledger_path = f.name
        f.write(ledger_content)
    
    try:
        records = parse_ledger(ledger_path)
        assert len(records) == 1
        
        r = records[0]
        assert r.provider == "stub"
        assert r.model == "stub-1"
        assert r.success is True
        assert r.attempts == 1
        assert r.input_chars == 5
        assert r.output_chars == 11
        assert r.latency_ms == 100
        assert r.cost_usd is None
        assert r.retry_count == 0
    finally:
        os.unlink(ledger_path)


def test_parse_run_with_retries():
    """Test parsing a run with retry records."""
    ledger_content = """(run
  (timestamp "2026-02-12T20:25:12.602740Z")
  (provider "stub")
  (model "stub-1")
  (success true)
  (attempts 2)
  (metrics
    (input_chars 21)
    (output_chars 27)
    (latency_ms 250)
  )
  (retries
    (retry (attempt 1) (error_type "SimulatedError") (error_message "Simulated transient failure") (backoff_ms 250))
  )
)
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.is', delete=False) as f:
        ledger_path = f.name
        f.write(ledger_content)
    
    try:
        records = parse_ledger(ledger_path)
        assert len(records) == 1
        
        r = records[0]
        assert r.success is True
        assert r.attempts == 2
        assert r.retry_count == 1
    finally:
        os.unlink(ledger_path)


def test_parse_run_with_cost():
    """Test parsing a run with cost information."""
    ledger_content = """(run
  (timestamp "2026-02-12T21:41:20.693674Z")
  (provider "gemini")
  (model "gemini-2.5-flash")
  (success true)
  (attempts 1)
  (metrics
    (input_chars 28)
    (output_chars 18)
    (latency_ms 2447)
    (cost_usd 0.00125)
  )
)
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.is', delete=False) as f:
        ledger_path = f.name
        f.write(ledger_content)
    
    try:
        records = parse_ledger(ledger_path)
        assert len(records) == 1
        
        r = records[0]
        assert r.provider == "gemini"
        assert r.cost_usd == 0.00125
    finally:
        os.unlink(ledger_path)


def test_parse_failed_run():
    """Test parsing a failed run."""
    ledger_content = """(run
  (timestamp "2026-02-12T22:00:00.000000Z")
  (provider "stub")
  (model "stub-1")
  (success false)
  (attempts 1)
  (metrics
    (input_chars 10)
    (output_chars 0)
    (latency_ms 50)
  )
  (error "Connection timeout")
)
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.is', delete=False) as f:
        ledger_path = f.name
        f.write(ledger_content)
    
    try:
        records = parse_ledger(ledger_path)
        assert len(records) == 1
        
        r = records[0]
        assert r.success is False
    finally:
        os.unlink(ledger_path)


def test_parse_malformed_trailing_block():
    """Test that malformed trailing blocks are ignored."""
    ledger_content = """(run
  (timestamp "2026-02-12T20:25:03.351474Z")
  (provider "stub")
  (model "stub-1")
  (success true)
  (attempts 1)
  (metrics
    (input_chars 5)
    (output_chars 11)
    (latency_ms 100)
  )
)
(run
  (timestamp "2026-02-12T20:26:00.000000Z")
  (provider "stub"
  (model "stub-1"
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.is', delete=False) as f:
        ledger_path = f.name
        f.write(ledger_content)
    
    try:
        records = parse_ledger(ledger_path)
        # Should parse only the first complete run, ignore incomplete second
        assert len(records) == 1
        assert records[0].success is True
    finally:
        os.unlink(ledger_path)


def test_compute_summary_statistics():
    """Test computing summary statistics from multiple runs."""
    ledger_content = """(run
  (timestamp "2026-02-12T20:25:03.351474Z")
  (provider "stub")
  (model "stub-1")
  (success true)
  (attempts 1)
  (metrics
    (input_chars 100)
    (output_chars 200)
    (latency_ms 500)
  )
)
(run
  (timestamp "2026-02-12T20:25:12.602740Z")
  (provider "stub")
  (model "stub-1")
  (success true)
  (attempts 2)
  (metrics
    (input_chars 150)
    (output_chars 250)
    (latency_ms 1000)
  )
  (retries
    (retry (attempt 1) (error_type "Error") (error_message "msg") (backoff_ms 250))
  )
)
(run
  (timestamp "2026-02-12T21:41:20.693674Z")
  (provider "gemini")
  (model "gemini-2.5-flash")
  (success false)
  (attempts 1)
  (metrics
    (input_chars 50)
    (output_chars 0)
    (latency_ms 300)
  )
)
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.is', delete=False) as f:
        ledger_path = f.name
        f.write(ledger_content)
    
    try:
        records = parse_ledger(ledger_path)
        summary = compute_summary(records)
        
        assert summary.total_runs == 3
        assert summary.successful_runs == 2
        assert summary.failed_runs == 1
        assert summary.success_rate_percent == pytest.approx(66.67, rel=0.01)
        
        assert summary.total_input_chars == 300
        assert summary.total_output_chars == 450
        assert summary.average_input_chars == 100.0
        assert summary.average_output_chars == 150.0
        
        assert summary.total_latency_ms == 1800
        assert summary.average_latency_ms == 600.0
        assert summary.max_latency_ms == 1000
        assert summary.min_latency_ms == 300
        
        assert summary.total_retry_count == 1
        assert summary.runs_with_retries == 1
        
        assert summary.total_cost_usd_if_available is None
        
        assert "stub" in summary.provider_stats
        assert "gemini" in summary.provider_stats
        
        assert summary.provider_stats["stub"].run_count == 2
        assert summary.provider_stats["stub"].success_count == 2
        assert summary.provider_stats["gemini"].run_count == 1
        assert summary.provider_stats["gemini"].success_count == 0
    finally:
        os.unlink(ledger_path)


def test_per_provider_breakdown():
    """Test per-provider statistics breakdown."""
    ledger_content = """(run
  (provider "stub")
  (model "stub-1")
  (success true)
  (attempts 1)
  (metrics
    (input_chars 100)
    (output_chars 200)
    (latency_ms 500)
    (cost_usd 0.001)
  )
)
(run
  (provider "stub")
  (model "stub-1")
  (success true)
  (attempts 1)
  (metrics
    (input_chars 100)
    (output_chars 200)
    (latency_ms 700)
    (cost_usd 0.002)
  )
)
(run
  (provider "gemini")
  (model "gemini-2.5-flash")
  (success true)
  (attempts 1)
  (metrics
    (input_chars 100)
    (output_chars 200)
    (latency_ms 1000)
    (cost_usd 0.005)
  )
)
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.is', delete=False) as f:
        ledger_path = f.name
        f.write(ledger_content)
    
    try:
        records = parse_ledger(ledger_path)
        summary = compute_summary(records)
        
        stub_stats = summary.provider_stats["stub"]
        assert stub_stats.run_count == 2
        assert stub_stats.success_rate == 100.0
        assert stub_stats.average_latency_ms == 600.0
        assert stub_stats.average_cost_usd == pytest.approx(0.0015, rel=0.01)
        
        gemini_stats = summary.provider_stats["gemini"]
        assert gemini_stats.run_count == 1
        assert gemini_stats.success_rate == 100.0
        assert gemini_stats.average_latency_ms == 1000.0
        assert gemini_stats.average_cost_usd == pytest.approx(0.005, rel=0.01)
    finally:
        os.unlink(ledger_path)


def test_most_used_model():
    """Test identification of most used model."""
    ledger_content = """(run
  (provider "stub")
  (model "model-a")
  (success true)
  (attempts 1)
  (metrics
    (input_chars 10)
    (output_chars 20)
    (latency_ms 100)
  )
)
(run
  (provider "stub")
  (model "model-b")
  (success true)
  (attempts 1)
  (metrics
    (input_chars 10)
    (output_chars 20)
    (latency_ms 100)
  )
)
(run
  (provider "stub")
  (model "model-b")
  (success true)
  (attempts 1)
  (metrics
    (input_chars 10)
    (output_chars 20)
    (latency_ms 100)
  )
)
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.is', delete=False) as f:
        ledger_path = f.name
        f.write(ledger_content)
    
    try:
        records = parse_ledger(ledger_path)
        summary = compute_summary(records)
        
        assert summary.most_used_model == "model-b"
        assert summary.model_counts["model-b"] == 2
        assert summary.model_counts["model-a"] == 1
    finally:
        os.unlink(ledger_path)


def test_format_summary_output():
    """Test that summary formatting produces expected output structure."""
    records = [
        RunRecord(
            provider="stub",
            model="stub-1",
            success=True,
            attempts=1,
            input_chars=100,
            output_chars=200,
            latency_ms=500,
        )
    ]
    
    summary = compute_summary(records)
    output = format_summary(summary)
    
    # Check for expected sections
    assert "AI Factory Ledger Summary" in output
    assert "Total Runs: 1" in output
    assert "Success Rate: 100.00%" in output
    assert "Average Latency: 500 ms" in output
    assert "Per Provider Breakdown:" in output
    assert "stub:" in output


def test_analyze_ledger_integration():
    """Test full integration with analyze_ledger function."""
    ledger_content = """(run
  (provider "stub")
  (model "stub-1")
  (success true)
  (attempts 1)
  (metrics
    (input_chars 50)
    (output_chars 100)
    (latency_ms 250)
  )
)
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.is', delete=False) as f:
        ledger_path = f.name
        f.write(ledger_content)
    
    try:
        summary = analyze_ledger(ledger_path)
        
        assert summary.total_runs == 1
        assert summary.successful_runs == 1
        assert summary.success_rate_percent == 100.0
    finally:
        os.unlink(ledger_path)


def test_runs_with_multiple_retries():
    """Test runs with multiple retry attempts."""
    ledger_content = """(run
  (provider "stub")
  (model "stub-1")
  (success true)
  (attempts 3)
  (metrics
    (input_chars 50)
    (output_chars 100)
    (latency_ms 250)
  )
  (retries
    (retry (attempt 1) (error_type "Error1") (error_message "msg1") (backoff_ms 100))
    (retry (attempt 2) (error_type "Error2") (error_message "msg2") (backoff_ms 200))
  )
)
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.is', delete=False) as f:
        ledger_path = f.name
        f.write(ledger_content)
    
    try:
        records = parse_ledger(ledger_path)
        assert len(records) == 1
        assert records[0].retry_count == 2
        
        summary = compute_summary(records)
        assert summary.total_retry_count == 2
        assert summary.runs_with_retries == 1
    finally:
        os.unlink(ledger_path)


def test_missing_optional_fields():
    """Test handling of runs with missing optional fields."""
    ledger_content = """(run
  (provider "stub")
  (model "stub-1")
  (success true)
  (attempts 1)
  (metrics
  )
)
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.is', delete=False) as f:
        ledger_path = f.name
        f.write(ledger_content)
    
    try:
        records = parse_ledger(ledger_path)
        assert len(records) == 1
        
        r = records[0]
        assert r.input_chars == 0
        assert r.output_chars == 0
        assert r.latency_ms == 0
        assert r.cost_usd is None
    finally:
        os.unlink(ledger_path)
