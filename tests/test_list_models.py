"""
Test model listing functionality
"""
from ai_factory import list_models, Config


def test_list_models_stub():
    """Test that list_models returns stub models."""
    config = Config(
        provider="stub",
        model="stub-1",
    )
    
    models = list_models("stub", config)
    
    # Should have at least 2 models
    assert len(models) >= 2
    
    # Check first model
    model_names = [m.name for m in models]
    assert "stub-1" in model_names
    assert "stub-2" in model_names
    
    # Verify structure
    for model in models:
        assert model.name is not None
        assert isinstance(model.name, str)


def test_list_models_has_metadata():
    """Test that models include expected metadata."""
    config = Config(
        provider="stub",
        model="stub-1",
    )
    
    models = list_models("stub", config)
    
    stub1 = next(m for m in models if m.name == "stub-1")
    
    # Verify optional fields are populated for stub
    assert stub1.context_window == 8192
    assert stub1.input_cost_per_1k == 0.001
    assert stub1.output_cost_per_1k == 0.002
    assert isinstance(stub1.metadata, dict)


def test_list_models_invalid_provider():
    """Test that list_models raises error for invalid provider."""
    config = Config(
        provider="nonexistent",
        model="dummy",
    )
    
    try:
        list_models("nonexistent", config)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "not found" in str(e).lower()
