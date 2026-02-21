"""
Test JSON ledger format
"""
import os
import json
import tempfile
from ai_factory import run, Config


def test_json_ledger_basic():
    """Test that JSON ledger format works and creates valid JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.jsonl")
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=ledger_path,
            ledger_format="json",
        )
        
        result = run("hello world", config)
        
        assert result.success is True
        assert os.path.exists(ledger_path)
        
        # Read and parse JSON
        with open(ledger_path, "r") as f:
            lines = f.readlines()
        
        assert len(lines) == 1
        entry = json.loads(lines[0])
        
        # Verify structure
        assert entry["provider"] == "stub"
        assert entry["model"] == "stub-1"
        assert entry["success"] is True
        assert entry["attempts"] == 1
        assert "timestamp" in entry
        assert "metrics" in entry
        assert entry["metrics"]["input_chars"] == len("hello world")
        assert entry["metrics"]["output_chars"] == len("STUB: hello world")


def test_json_ledger_with_captures():
    """Test JSON ledger with prompt and output capture."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.jsonl")
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=ledger_path,
            ledger_format="json",
            capture_prompt=True,
            capture_output=True,
        )
        
        result = run("test prompt", config)
        
        assert result.success is True
        
        with open(ledger_path, "r") as f:
            entry = json.loads(f.read())
        
        assert entry["prompt"] == "test prompt"
        assert entry["output"] == "STUB: test prompt"
        assert "prompt_truncated" not in entry
        assert "output_truncated" not in entry


def test_json_ledger_multiple_entries():
    """Test that JSON ledger appends multiple entries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.jsonl")
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=ledger_path,
            ledger_format="json",
        )
        
        run("first", config)
        run("second", config)
        run("third", config)
        
        with open(ledger_path, "r") as f:
            lines = f.readlines()
        
        assert len(lines) == 3
        
        # Verify each entry is valid JSON
        for line in lines:
            entry = json.loads(line)
            assert "timestamp" in entry
            assert "provider" in entry
            assert "model" in entry


def test_json_ledger_default_path():
    """Test that JSON format defaults to .jsonl extension."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = os.getcwd()
        os.chdir(tmpdir)
        
        try:
            from ai_factory.config_loader import load_config
            
            config = load_config(
                provider="stub",
                model="stub-1",
                ledger_format="json",
            )
            
            assert config.ledger_path == "./LEDGER.jsonl"
            
        finally:
            os.chdir(original_dir)


def test_json_and_is_ledger_same_data():
    """Test that JSON and IS formats contain the same data fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        is_path = os.path.join(tmpdir, "test.is")
        json_path = os.path.join(tmpdir, "test.jsonl")
        
        prompt = "test prompt"
        
        # Run with IS format
        is_config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=is_path,
            ledger_format="is",
            capture_prompt=True,
            capture_output=True,
        )
        run(prompt, is_config)
        
        # Run with JSON format
        json_config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=json_path,
            ledger_format="json",
            capture_prompt=True,
            capture_output=True,
        )
        run(prompt, json_config)
        
        # Parse JSON entry
        with open(json_path, "r") as f:
            json_entry = json.loads(f.read())
        
        # Read IS entry
        with open(is_path, "r") as f:
            is_content = f.read()
        
        # Verify key fields exist in both
        assert "(provider \"stub\")" in is_content
        assert json_entry["provider"] == "stub"
        
        assert "(model \"stub-1\")" in is_content
        assert json_entry["model"] == "stub-1"
        
        assert "(success true)" in is_content
        assert json_entry["success"] is True
        
        assert "(prompt \"test prompt\")" in is_content
        assert json_entry["prompt"] == "test prompt"
        
        assert "(output \"STUB: test prompt\")" in is_content
        assert json_entry["output"] == "STUB: test prompt"


def test_json_ledger_utf8():
    """Test that JSON ledger handles UTF-8 correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.jsonl")
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=ledger_path,
            ledger_format="json",
            capture_prompt=True,
        )
        
        # Use UTF-8 characters
        prompt = "Hello 世界 🌍"
        run(prompt, config)
        
        with open(ledger_path, "r", encoding="utf-8") as f:
            entry = json.loads(f.read())
        
        assert entry["prompt"] == prompt


def test_is_ledger_still_works():
    """Test that IS ledger format still works as default."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.is")
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=ledger_path,
            # ledger_format defaults to 'is'
        )
        
        result = run("test", config)
        
        assert result.success is True
        assert os.path.exists(ledger_path)
        
        with open(ledger_path, "r") as f:
            content = f.read()
        
        # Should be IS format
        assert "(run" in content
        assert "(provider \"stub\")" in content
        assert "(model \"stub-1\")" in content


def test_invalid_ledger_format():
    """Test that invalid ledger format raises error."""
    try:
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_format="xml",  # Invalid
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "ledger_format must be 'is' or 'json'" in str(e)
