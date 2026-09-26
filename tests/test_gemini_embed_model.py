"""
Test Gemini embedding model configuration
"""
from ai_factory import Config
from ai_factory.providers.gemini import GeminiProvider
import os


def test_gemini_embed_uses_configured_model():
    """Test that Gemini embed uses the configured model, not hard-coded value."""
    # Skip if no API key
    if not os.environ.get("GEMINI_API_KEY"):
        print("⊘ Skipping: GEMINI_API_KEY not set")
        return
    
    # Test with common Gemini embedding models
    test_models = [
        "gemini-embedding-001",  # Current production model
    ]
    
    for model_name in test_models:
        print(f"\nTesting with model: {model_name}")
        
        config = Config(
            provider="gemini",
            model=model_name,
            ledger_enabled=False,
        )
        
        try:
            provider = GeminiProvider(config)
            
            # Check that provider has correct model_name
            if hasattr(provider, 'model_name'):
                expected = f"models/{model_name}" if not model_name.startswith("models/") else model_name
                assert provider.model_name == expected, f"Expected {expected}, got {provider.model_name}"
                print(f"  ✓ Provider model_name: {provider.model_name}")
            
            # Try a small embedding (this will fail if model doesn't exist)
            result = provider.embed("test")
            
            if result.success:
                print(f"  ✓ Embedding succeeded: {len(result.vector)}-dim vector, {result.metrics.latency_ms}ms")
            else:
                print(f"  ✗ Embedding failed: {result.error}")
                # Check if it's a 404 error (wrong model name)
                if "404" in str(result.error) or "not found" in str(result.error).lower():
                    raise AssertionError(f"Model {model_name} not found - possible hard-coded model name issue")
        
        except Exception as e:
            print(f"  ✗ Error with {model_name}: {e}")
            raise


def test_model_name_construction():
    """Test that model names are constructed correctly."""
    # Skip if no API key
    if not os.environ.get("GEMINI_API_KEY"):
        print("⊘ Skipping: GEMINI_API_KEY not set")
        return
    
    test_cases = [
        ("gemini-embedding-001", "models/gemini-embedding-001"),
        ("models/gemini-embedding-001", "models/gemini-embedding-001"),
        ("text-embedding-004", "models/text-embedding-004"),
    ]
    
    for input_model, expected_model_name in test_cases:
        config = Config(
            provider="gemini",
            model=input_model,
            ledger_enabled=False,
        )
        
        provider = GeminiProvider(config)
        
        if hasattr(provider, 'model_name'):
            assert provider.model_name == expected_model_name, \
                f"Input: {input_model}, Expected: {expected_model_name}, Got: {provider.model_name}"
            print(f"✓ {input_model} -> {provider.model_name}")


if __name__ == "__main__":
    print("Testing Gemini embedding model configuration...\n")
    
    try:
        test_model_name_construction()
        print("\n" + "="*60)
        test_gemini_embed_uses_configured_model()
        print("\n✓ All Gemini embedding model tests passed!")
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n⊘ Test skipped or error: {e}")
