"""
Test basic successful run
"""
import os
import tempfile
from ai_factory import run, Config


def test_run_success():
    """Test that run() returns success for a normal prompt."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.is")
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=ledger_path,
        )
        
        result = run("hello world", config)
        
        assert result.success is True
        assert result.output == "STUB: hello world"
        assert result.metrics.success is True
        assert result.metrics.input_chars == len("hello world")
        assert result.metrics.output_chars == len("STUB: hello world")
        assert result.metrics.latency_ms > 0


def test_run_creates_ledger():
    """Test that run() creates a ledger file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.is")
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=ledger_path,
        )
        
        run("test prompt", config)
        
        # Ledger should exist
        assert os.path.exists(ledger_path)
        
        # Read and verify basic structure
        with open(ledger_path, "r") as f:
            content = f.read()
        
        assert "(run" in content
        assert "(provider \"stub\")" in content
        assert "(model \"stub-1\")" in content
        assert "(success true)" in content


def test_run_without_ledger():
    """Test that run() works with ledger disabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "should_not_exist.is")
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_enabled=False,
            ledger_path=ledger_path,
        )
        
        result = run("test", config)
        
        assert result.success is True
        assert not os.path.exists(ledger_path)
