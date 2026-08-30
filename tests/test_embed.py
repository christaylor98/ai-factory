"""
Test embedding functionality with stub provider
"""
from ai_factory import embed, Config

def test_embed_with_stub():
    """Test embedding with stub provider."""
    config = Config(
        provider="stub",
        model="stub-1",
        ledger_enabled=False
    )
    
    result = embed("Hello, world!", config)
    
    assert result.success, "Embedding should succeed"
    assert len(result.vector) == 8, "Stub should return 8-dimensional vector"
    assert result.vector == [0.0] * 8, "Stub vector should be all zeros"
    assert result.error is None, "Should have no error"
    assert result.metrics.input_chars == 13, "Should count input chars"
    assert result.metrics.success is True, "Metrics should show success"
    
    print("✓ Stub embedding test passed")
    print(f"  Vector: {result.vector}")
    print(f"  Latency: {result.metrics.latency_ms}ms")


def test_embed_with_ledger():
    """Test embedding with ledger enabled."""
    import os
    import tempfile
    
    # Create temporary ledger file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.is') as f:
        ledger_path = f.name
    
    try:
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_enabled=True,
            ledger_path=ledger_path,
            ledger_format="is"
        )
        
        result = embed("Test text for ledger", config)
        
        assert result.success, "Embedding should succeed"
        
        # Check ledger was written
        assert os.path.exists(ledger_path), "Ledger should be created"
        
        with open(ledger_path, 'r') as f:
            ledger_content = f.read()
        
        assert "(embed" in ledger_content, "Ledger should contain embed entry"
        assert "(provider" in ledger_content, "Ledger should contain provider"
        assert "(vector_dim 8)" in ledger_content, "Ledger should contain vector dimension"
        assert "(input_hash" in ledger_content, "Ledger should contain input hash"
        assert "Test text for ledger" not in ledger_content, "Ledger should NOT contain raw text"
        
        print("✓ Ledger embedding test passed")
        print(f"  Ledger entry:\n{ledger_content}")
    
    finally:
        # Clean up
        if os.path.exists(ledger_path):
            os.unlink(ledger_path)


def test_embed_json_ledger():
    """Test embedding with JSON ledger format."""
    import os
    import tempfile
    import json
    
    # Create temporary ledger file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl') as f:
        ledger_path = f.name
    
    try:
        config = Config(
            provider="stub",
            model="stub-1",
            ledger_enabled=True,
            ledger_path=ledger_path,
            ledger_format="json"
        )
        
        result = embed("JSON test", config)
        
        assert result.success, "Embedding should succeed"
        
        # Check ledger was written
        assert os.path.exists(ledger_path), "Ledger should be created"
        
        with open(ledger_path, 'r') as f:
            line = f.readline()
            entry = json.loads(line)
        
        assert entry["type"] == "embed", "Entry type should be embed"
        assert entry["provider"] == "stub", "Provider should be stub"
        assert entry["vector_dim"] == 8, "Vector dimension should be 8"
        assert "input_hash" in entry, "Should contain input hash"
        assert entry["success"] is True, "Should be successful"
        
        print("✓ JSON ledger embedding test passed")
        print(f"  JSON entry: {json.dumps(entry, indent=2)}")
    
    finally:
        # Clean up
        if os.path.exists(ledger_path):
            os.unlink(ledger_path)


if __name__ == "__main__":
    test_embed_with_stub()
    test_embed_with_ledger()
    test_embed_json_ledger()
    print("\n✓ All embedding tests passed!")
