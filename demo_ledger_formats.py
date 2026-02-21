#!/usr/bin/env python3
"""
Demonstration of JSON and IS ledger formats in ai-factory
"""
import json
import tempfile
from pathlib import Path
from ai_factory import run, Config

def demo_is_format():
    """Demonstrate IS format (default)."""
    print("=== IS Format Demo ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "demo.is"
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=str(ledger_path),
            ledger_format="is",  # Explicitly set (default anyway)
            capture_prompt=True,
            capture_output=True,
        )
        
        result = run("Hello, world!", config)
        print(f"Success: {result.success}")
        print(f"Output: {result.output}")
        
        print("\nLedger content (IS format):")
        print(ledger_path.read_text())


def demo_json_format():
    """Demonstrate JSON format."""
    print("\n=== JSON Format Demo ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "demo.jsonl"
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=str(ledger_path),
            ledger_format="json",
            capture_prompt=True,
            capture_output=True,
        )
        
        result = run("Hello, JSON!", config)
        print(f"Success: {result.success}")
        print(f"Output: {result.output}")
        
        print("\nLedger content (JSON format):")
        ledger_text = ledger_path.read_text()
        print(ledger_text)
        
        print("\nParsed JSON:")
        entry = json.loads(ledger_text)
        print(json.dumps(entry, indent=2))


def demo_multiple_entries():
    """Demonstrate multiple entries in JSON format."""
    print("\n=== Multiple JSON Entries Demo ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "multi.jsonl"
        
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=str(ledger_path),
            ledger_format="json",
        )
        
        # Run three times
        for i in range(1, 4):
            run(f"Test {i}", config)
        
        print(f"Created {len(ledger_path.read_text().splitlines())} entries")
        print("\nAll entries are valid JSON:")
        for i, line in enumerate(ledger_path.read_text().splitlines(), 1):
            entry = json.loads(line)
            print(f"  Entry {i}: provider={entry['provider']}, success={entry['success']}")


if __name__ == "__main__":
    demo_is_format()
    demo_json_format()
    demo_multiple_entries()
    print("\n✓ All demos completed successfully!")
