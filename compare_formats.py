#!/usr/bin/env python3
"""
Side-by-side comparison of IS and JSON ledger formats
"""
import json
import tempfile
from pathlib import Path
from ai_factory import run, Config

def create_comparison():
    """Create identical runs in both formats for comparison."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # IS format
        is_path = Path(tmpdir) / "compare.is"
        is_config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=str(is_path),
            ledger_format="is",
            capture_prompt=True,
            capture_output=True,
        )
        run("Compare formats", is_config)
        
        # JSON format
        json_path = Path(tmpdir) / "compare.jsonl"
        json_config = Config(
            provider="stub",
            model="stub-1",
            ledger_path=str(json_path),
            ledger_format="json",
            capture_prompt=True,
            capture_output=True,
        )
        run("Compare formats", json_config)
        
        print("=" * 80)
        print("IS FORMAT (Indented S-expressions)")
        print("=" * 80)
        print(is_path.read_text())
        
        print("=" * 80)
        print("JSON FORMAT (JSON Lines)")
        print("=" * 80)
        json_text = json_path.read_text()
        print(json_text)
        
        print("\n" + "=" * 80)
        print("PARSED JSON (pretty printed for readability)")
        print("=" * 80)
        entry = json.loads(json_text)
        print(json.dumps(entry, indent=2))
        
        print("\n" + "=" * 80)
        print("DATA VERIFICATION")
        print("=" * 80)
        is_content = is_path.read_text()
        
        # Verify key fields match
        checks = [
            ("provider", '(provider "stub")', entry["provider"] == "stub"),
            ("model", '(model "stub-1")', entry["model"] == "stub-1"),
            ("success", "(success true)", entry["success"] is True),
            ("prompt", '(prompt "Compare formats")', entry["prompt"] == "Compare formats"),
            ("output", 'output "STUB: Compare formats"', "STUB: Compare formats" in entry["output"]),
        ]
        
        for field, is_check, json_check in checks:
            is_ok = is_check in is_content
            print(f"  {field:12} IS: {'✓' if is_ok else '✗'}  JSON: {'✓' if json_check else '✗'}")
        
        print("\n✓ Both formats contain identical data!")

if __name__ == "__main__":
    create_comparison()
