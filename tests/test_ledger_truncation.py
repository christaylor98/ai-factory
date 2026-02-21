"""
Test ledger truncation behavior
"""
import os
import tempfile
from ai_factory import run, Config


def test_prompt_truncation():
    """Test that prompts are truncated when exceeding capture limit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.is")
        
        # Create a large prompt
        large_prompt = "x" * 1000
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=ledger_path,
            capture_prompt=True,
            capture_limit_chars=500,  # Limit to 500 chars
        )
        
        run(large_prompt, config)
        
        # Read ledger
        with open(ledger_path, "r") as f:
            content = f.read()
        
        # Should have truncation markers
        assert "(prompt_truncated true)" in content
        assert "(prompt_original_length 1000)" in content
        
        # The actual prompt in ledger should be truncated
        # (harder to verify exact length in IS format due to escaping)


def test_output_truncation():
    """Test that outputs are truncated when exceeding capture limit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.is")
        
        # Create a prompt that will generate large output
        # The stub will add "STUB: " prefix, so we need to account for that
        prompt = "y" * 500
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=ledger_path,
            capture_output=True,
            capture_limit_chars=100,  # Small limit
        )
        
        run(prompt, config)
        
        # Read ledger
        with open(ledger_path, "r") as f:
            content = f.read()
        
        # Should have truncation markers
        assert "(output_truncated true)" in content
        # Output is "STUB: " + prompt, so 506 chars
        assert "(output_original_length 506)" in content


def test_no_truncation_when_under_limit():
    """Test that small prompts/outputs are not marked as truncated."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.is")
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=ledger_path,
            capture_prompt=True,
            capture_output=True,
            capture_limit_chars=1000,
        )
        
        run("small prompt", config)
        
        # Read ledger
        with open(ledger_path, "r") as f:
            content = f.read()
        
        # Should NOT have truncation markers
        assert "(prompt_truncated" not in content
        assert "(output_truncated" not in content
        assert "(prompt_original_length" not in content
        assert "(output_original_length" not in content


def test_capture_disabled_by_default():
    """Test that prompts/outputs are not captured by default."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.is")
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=ledger_path,
            # capture_prompt and capture_output default to False
        )
        
        run("test prompt", config)
        
        # Read ledger
        with open(ledger_path, "r") as f:
            content = f.read()
        
        # Should NOT have prompt or output in ledger
        assert "(prompt " not in content
        assert "(output " not in content
