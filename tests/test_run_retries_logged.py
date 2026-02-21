"""
Test retry behavior and logging
"""
import os
import tempfile
from ai_factory import run, Config


def test_flake_causes_one_retry():
    """Test that __FLAKE__ in prompt causes exactly one retry."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.is")
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=ledger_path,
            capture_prompt=True,
            capture_output=True,
        )
        
        result = run("test __FLAKE__ prompt", config)
        
        # Should succeed after retry
        assert result.success is True
        assert "STUB: test __FLAKE__ prompt" in result.output
        
        # Check ledger for retry entry
        with open(ledger_path, "r") as f:
            content = f.read()
        
        assert "(success true)" in content
        assert "(attempts 2)" in content
        assert "(retries" in content
        assert "(retry" in content
        assert "(attempt 1)" in content
        assert "(error_type \"SimulatedError\")" in content
        assert "(backoff_ms" in content


def test_fail_exhausts_retries():
    """Test that __FAIL__ causes all retries to be exhausted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.is")
        
        config = Config(
            provider="stub",
            model="stub-1",
            max_retries=2,
            ledger_path=ledger_path,
        )
        
        result = run("test __FAIL__ prompt", config)
        
        # Should fail
        assert result.success is False
        assert result.output == ""
        assert result.metrics.success is False
        
        # Check ledger
        with open(ledger_path, "r") as f:
            content = f.read()
        
        assert "(success false)" in content
        assert "(attempts 3)" in content  # 1 initial + 2 retries
        assert "(retries" in content
        assert "(error" in content


def test_retry_backoff_progression():
    """Test that retry backoff follows the exponential pattern."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.is")
        
        config = Config(
            provider="stub",
            model="stub-1",
            max_retries=2,
            backoff_base_ms=100,
            backoff_multiplier=3.0,
            ledger_path=ledger_path,
        )
        
        run("__FAIL__", config)
        
        # Read ledger and check backoff values
        with open(ledger_path, "r") as f:
            content = f.read()
        
        # First retry: 100 * (3.0 ** 0) = 100ms
        # Second retry: 100 * (3.0 ** 1) = 300ms
        assert "(backoff_ms 100)" in content
        assert "(backoff_ms 300)" in content
