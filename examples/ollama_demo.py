"""
Example: Using Ollama with ai-factory

Ollama is a local LLM provider that runs models on your machine.
No API key required - just a running Ollama server.

Setup:
1. Install Ollama: https://ollama.ai
2. Start Ollama: ollama serve
3. Pull a model: ollama pull qwen2.5:14b
4. Run this example
"""
from ai_factory import run, Config


def basic_example():
    """Basic Ollama usage."""
    print("Basic Ollama Example")
    print("-" * 60)
    
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
        ledger_enabled=True,
    )
    
    result = run(
        "Return 2-3 topic labels: Ancient Egypt flourished along the Nile",
        config
    )
    
    if result.success:
        print(f"✓ Success!")
        print(f"Output: {result.output}")
        print(f"Latency: {result.metrics.latency_ms}ms")
        
        if result.metrics.prompt_tokens:
            print(f"Prompt tokens: {result.metrics.prompt_tokens}")
        if result.metrics.completion_tokens:
            print(f"Completion tokens: {result.metrics.completion_tokens}")
    else:
        print(f"✗ Failed")
        print("Make sure Ollama is running: ollama serve")
    
    print()


def custom_port_example():
    """Using Ollama on a non-default port."""
    print("Custom Port Example")
    print("-" * 60)
    
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
        base_url="http://localhost:8080",  # Custom port
        ledger_enabled=False,
    )
    
    result = run("What is machine learning?", config)
    
    print(f"Success: {result.success}")
    if result.success:
        print(f"Output: {result.output[:100]}...")
    print()


def retry_example():
    """Demonstrates automatic retry on transient failures."""
    print("Retry on Failure Example")
    print("-" * 60)
    
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
        max_retries=3,
        backoff_base_ms=500,
        backoff_multiplier=2.0,
        ledger_enabled=False,
    )
    
    result = run("Hello!", config)
    
    print(f"Success: {result.success}")
    print(f"Attempts would have been made with exponential backoff if needed")
    print()


def list_models_example():
    """List available Ollama models."""
    print("List Models Example")
    print("-" * 60)
    
    from ai_factory.providers.ollama import OllamaProvider
    
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
    )
    
    provider = OllamaProvider(config)
    models = provider.list_models()
    
    if models:
        print(f"Found {len(models)} models:")
        for model in models:
            print(f"  - {model.name}")
            if 'parameter_size' in model.metadata:
                print(f"    Parameters: {model.metadata['parameter_size']}")
    else:
        print("No models found. Make sure Ollama is running.")
    
    print()


def ledger_tracking_example():
    """Demonstrates ledger tracking for local inference."""
    print("Ledger Tracking Example")
    print("-" * 60)
    
    config = Config(
        provider="ollama",
        model="qwen2.5:14b",
        ledger_enabled=True,
        ledger_path="./LEDGER_OLLAMA_DEMO.is",
        capture_prompt=True,
        capture_output=True,
    )
    
    result = run("Explain quantum computing in one sentence.", config)
    
    print(f"Success: {result.success}")
    print(f"Output: {result.output}")
    print()
    print("Check LEDGER_OLLAMA_DEMO.is for recorded metrics!")
    print("Ledger tracks latency, tokens, and cost (0.0 for local)")
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("Ollama Provider Examples")
    print("=" * 60)
    print()
    
    basic_example()
    custom_port_example()
    retry_example()
    list_models_example()
    ledger_tracking_example()
    
    print("=" * 60)
    print("All examples complete!")
    print("=" * 60)
