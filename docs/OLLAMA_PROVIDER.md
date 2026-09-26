# Ollama Provider

The Ollama provider enables ai-factory to use locally running Ollama models for inference. Unlike cloud providers, Ollama requires no API key and runs entirely on your local machine.

## Overview

- **Provider name**: `ollama`
- **Authentication**: None (local inference)
- **Default endpoint**: `http://localhost:11434`
- **Cost**: Free (local compute)
- **Supported methods**: `run()`, `list_models()`, `embed()`

## Setup

### 1. Install Ollama

Visit [https://ollama.ai](https://ollama.ai) and follow the installation instructions for your platform:

```bash
# macOS/Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Or download from website for other platforms
```

### 2. Start Ollama Server

```bash
ollama serve
```

Ollama will start on `http://localhost:11434` by default.

### 3. Pull a Model

```bash
# Pull a model (e.g., Qwen 2.5 14B)
ollama pull qwen2.5:14b

# Or smaller models
ollama pull qwen2.5:7b
ollama pull llama3.2:3b

# List available models
ollama list
```

## Basic Usage

```python
from ai_factory import run, Config

config = Config(
    provider="ollama",
    model="qwen2.5:14b",
    ledger_enabled=True,
)

result = run("What is machine learning?", config)
print(result.output)
```

## Configuration Options

### Standard Config Fields

```python
Config(
    provider="ollama",           # Required: must be "ollama"
    model="qwen2.5:14b",         # Required: Ollama model name
    max_retries=2,               # Optional: retry on transient failures
    backoff_base_ms=250,         # Optional: initial backoff delay
    backoff_multiplier=2.0,      # Optional: backoff multiplier
    ledger_enabled=True,         # Optional: track local inference
    ledger_path="./LEDGER.is",   # Optional: ledger file path
    capture_prompt=False,        # Optional: save prompts in ledger
    capture_output=False,        # Optional: save outputs in ledger
)
```

### Ollama-Specific Config

```python
Config(
    provider="ollama",
    model="qwen2.5:14b",
    base_url="http://localhost:8080",  # Custom Ollama port/host
)
```

Use `base_url` to connect to:
- Non-default ports: `http://localhost:8080`
- Remote Ollama instances: `http://192.168.1.100:11434`
- Docker containers: `http://ollama-container:11434`

## Features

### ✅ No API Key Required

Ollama runs locally, so no authentication or API keys are needed:

```python
config = Config(
    provider="ollama",
    model="qwen2.5:14b",
)

# Just works - no environment variables needed
result = run("Hello!", config)
```

### ✅ Automatic Retry Logic

Same retry behavior as cloud providers:

```python
config = Config(
    provider="ollama",
    model="qwen2.5:14b",
    max_retries=3,
    backoff_base_ms=500,
)

# Retries on connection errors with exponential backoff
result = run("Test", config)
```

### ✅ Ledger Tracking

Track local inference metrics just like cloud providers:

```python
config = Config(
    provider="ollama",
    model="qwen2.5:14b",
    ledger_enabled=True,
)

result = run("Explain quantum computing", config)

# Ledger records:
# - Latency
# - Token counts (if provided by Ollama)
# - Cost: $0.00 (local inference)
# - Model name
# - Success/failure status
```

### ✅ Token Tracking

Ollama provides detailed token counts in metadata:

```python
result = run("Hello!", config)

print(result.metrics.prompt_tokens)      # Input tokens
print(result.metrics.completion_tokens)  # Output tokens
print(result.metrics.latency_ms)         # Response time
```

### ✅ List Available Models

```python
from ai_factory.providers.ollama import OllamaProvider

config = Config(provider="ollama", model="qwen2.5:14b")
provider = OllamaProvider(config)

models = provider.list_models()
for model in models:
    print(f"{model.name}")
    print(f"  Size: {model.metadata.get('size')}")
    print(f"  Family: {model.metadata.get('family')}")
```

### ✅ Embeddings

Generate embeddings using Ollama embedding models:

```python
from ai_factory.providers.ollama import OllamaProvider

config = Config(
    provider="ollama",
    model="nomic-embed-text",  # Embedding model
)

provider = OllamaProvider(config)
result = provider.embed("Ancient Egypt flourished along the Nile")

print(f"Vector dimensions: {len(result.vector)}")
print(f"Success: {result.success}")
```

## Error Handling

### Ollama Not Running

When Ollama is not running, ai-factory returns a clean error:

```python
result = run("Test", config)

if not result.success:
    # Error message: "Ollama is not running. Start with: ollama serve"
    print("Start Ollama server first!")
```

No exceptions raised - failure is returned as `RunResult` with `success=False`.

### Model Not Found

If the specified model hasn't been pulled:

```python
config = Config(
    provider="ollama",
    model="nonexistent-model",
)

result = run("Test", config)
# Error: "Model 'nonexistent-model' not found. Pull with: ollama pull nonexistent-model"
```

### Connection Refused

Handled gracefully with automatic retry (transient) or immediate failure (permanent):

```python
config = Config(
    provider="ollama",
    model="qwen2.5:14b",
    max_retries=2,
)

result = run("Test", config)
# Retries connection errors automatically
# Returns failure after exhausting retries
```

## Comparison with Cloud Providers

| Feature | Ollama | Cloud Providers |
|---------|--------|----------------|
| API Key | ❌ Not required | ✅ Required |
| Cost | $0.00 (local) | Pay per token |
| Latency | Local speed | Network + API |
| Privacy | 100% local | Sent to cloud |
| Retry Logic | ✅ Yes | ✅ Yes |
| Ledger Tracking | ✅ Yes | ✅ Yes |
| Token Counts | ✅ Yes | ✅ Yes |
| Embeddings | ✅ Yes | ✅ Yes |

## Provider Contract Compliance

Ollama implements the complete BaseProvider interface:

```python
class OllamaProvider(BaseProvider):
    def call(self, prompt: str) -> ProviderResponse:
        """Make API call with retry logic"""
        
    def list_models(self) -> list[ModelInfo]:
        """List available Ollama models"""
        
    def embed(self, text: str) -> EmbedResult:
        """Generate embeddings"""
```

All standard ai-factory features work identically:
- ✅ Retry logic
- ✅ Ledger tracking
- ✅ Metrics collection
- ✅ Error handling
- ✅ RunResult interface

## Common Use Cases

### Development & Testing

Use Ollama for free local testing before deploying with cloud providers:

```python
# Development
dev_config = Config(provider="ollama", model="qwen2.5:14b")

# Production
prod_config = Config(provider="openai", model="gpt-4o-mini")

# Same code works for both
result = run(prompt, dev_config)  # or prod_config
```

### Privacy-Sensitive Applications

Keep data local when processing sensitive information:

```python
config = Config(
    provider="ollama",
    model="qwen2.5:14b",
)

# Medical records, legal documents, etc. never leave your machine
result = run(sensitive_prompt, config)
```

### Offline Environments

Run inference without internet connectivity:

```python
# Pull models once while online
# ollama pull qwen2.5:14b

# Then use offline
config = Config(provider="ollama", model="qwen2.5:14b")
result = run("Works offline!", config)
```

### Cost Optimization

Mix local and cloud providers based on use case:

```python
def get_config(task_type):
    if task_type == "simple":
        # Use local Ollama for simple tasks
        return Config(provider="ollama", model="qwen2.5:7b")
    else:
        # Use cloud for complex tasks
        return Config(provider="anthropic", model="claude-sonnet-4")
```

## Troubleshooting

### "Ollama is not running"

Start the Ollama server:

```bash
ollama serve
```

### Model Not Found

Pull the model first:

```bash
ollama pull qwen2.5:14b
ollama list  # Verify installation
```

### Connection Timeout

Increase timeout in future versions, or ensure Ollama is running:

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags
```

### Wrong Port

Specify custom port in config:

```python
config = Config(
    provider="ollama",
    model="qwen2.5:14b",
    base_url="http://localhost:8080",  # Custom port
)
```

## Examples

See [examples/ollama_demo.py](../examples/ollama_demo.py) for complete examples:
- Basic usage
- Custom ports
- Retry logic
- Model listing
- Ledger tracking
- Error handling

## API Reference

### Ollama REST API

The provider uses these Ollama endpoints:

#### Generate Completion
```
POST /api/generate
{
  "model": "qwen2.5:14b",
  "prompt": "Hello!",
  "stream": false
}
```

#### List Models
```
GET /api/tags
```

#### Generate Embeddings
```
POST /api/embeddings
{
  "model": "nomic-embed-text",
  "prompt": "Text to embed"
}
```

## Further Reading

- [Ollama Documentation](https://github.com/ollama/ollama/blob/main/docs/README.md)
- [Ollama Model Library](https://ollama.ai/library)
- [AI Factory Python Library Guide](./PYTHON_LIBRARY_GUIDE.md)
- [Provider Contract](./ARCHITECTURE.md)
