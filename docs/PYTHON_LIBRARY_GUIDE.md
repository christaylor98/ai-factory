# AI Factory Python Library Guide

Complete guide for integrating AI Factory as a Python library in your applications.

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration Methods](#configuration-methods)
- [Core Operations](#core-operations)
- [Embedding Support](#embedding-support)
- [Provider-Specific Examples](#provider-specific-examples)
- [Error Handling](#error-handling)
- [Ledger Integration](#ledger-integration)
- [Advanced Patterns](#advanced-patterns)

---

## Installation

```bash
# Install from PyPI (when published)
pip install ai-factory

# Install from local directory (development)
pip install -e /path/to/ai-factory

# With development dependencies
pip install -e "/path/to/ai-factory[dev]"
```

**Requirements:**
- Python 3.9+
- API keys for the providers you want to use (set via environment variables or config)

---

## Quick Start

### Minimal Example

```python
from ai_factory import run, Config

# Create a configuration
config = Config(
    provider="openai",
    model="gpt-4o-mini",
    ledger_enabled=False,  # Disable ledger for quick tests
)

# Run a prompt
result = run("What is 2+2?", config)

# Check result
if result.success:
    print(result.output)  # "4" (or similar)
else:
    print(f"Error: {result.error}")
```

### With Environment Variables

Set your API keys in environment variables (recommended):

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GEMINI_API_KEY="..."
export OPENROUTER_API_KEY="sk-or-..."
```

Then use without hardcoding keys:

```python
from ai_factory import run, Config

config = Config(
    provider="anthropic",
    model="claude-3-5-sonnet-20241022",
)

result = run("Explain quantum entanglement in simple terms", config)
print(result.output)
```

---

## Configuration Methods

AI Factory supports three configuration approaches:

1. **Direct `Config` construction** (simplest)
2. **Config loader (`load_config`) with overrides** (recommended)
3. **TOML files + environment variables** (most flexible)

### Method 1: Direct Config Construction

```python
from ai_factory import Config, run

config = Config(
    provider="gemini",
    model="gemini-2.0-flash-exp",
    max_retries=3,
    backoff_base_ms=500,
    backoff_multiplier=2.0,
    ledger_enabled=True,
    ledger_path="./my-app-ledger.is",
    ledger_format="json",  # or "is" (default)
    capture_prompt=True,
    capture_output=True,
    capture_limit_chars=10000,
)

result = run("Your prompt here", config)
```

### Method 2: Config Loader (Recommended)

The config loader combines TOML files, environment variables, and runtime arguments:

```python
from ai_factory.config_loader import load_config
from ai_factory import run

# Load from default locations with overrides
config = load_config(
    provider="openai",  # Override provider
    model="gpt-4o",     # Override model
    max_retries=5,      # Override retries
)

result = run("Your prompt", config)
```

**Config precedence within `load_config()` (highest to lowest):**
1. Function arguments to `load_config()`
2. Environment variables (e.g., `AIFACTORY_PROVIDER`)
3. `./aifactory.toml` file
4. `~/.aifactory/config.toml` file
5. Built-in defaults

### Method 3: TOML Configuration File

Create `aifactory.toml` in your project directory:

```toml
# Default settings
[default]
provider = "anthropic"
model = "claude-3-5-sonnet-20241022"
max_retries = 3
backoff_base_ms = 250
backoff_multiplier = 2.0

[ledger]
enabled = true
path = "./my-project-ledger.is"
format = "json"  # or "is"
capture_prompt = true
capture_output = true
capture_limit_chars = 20000
```

Provider API keys are always read from environment variables (or a local `.env` file), not from TOML.

Then use the loader:

```python
from ai_factory.config_loader import load_config
from ai_factory import run

# Automatically loads from ./aifactory.toml
config = load_config()

result = run("Your prompt", config)
```

---

## Core Operations

### 1. Running Prompts

```python
from ai_factory import run, Config

config = Config(
    provider="openai",
    model="gpt-4o-mini",
)

result = run("Translate 'hello' to Spanish", config)

# Access results
print(f"Output: {result.output}")
print(f"Success: {result.success}")
print(f"Metrics: {result.metrics}")
```

### 2. Accessing Metrics

```python
result = run("What is AI?", config)

metrics = result.metrics

print(f"Input chars: {metrics.input_chars}")
print(f"Output chars: {metrics.output_chars}")
print(f"Latency: {metrics.latency_ms}ms")
print(f"Success: {metrics.success}")

# Token metrics (if available from provider)
if metrics.prompt_tokens:
    print(f"Prompt tokens: {metrics.prompt_tokens}")
if metrics.completion_tokens:
    print(f"Completion tokens: {metrics.completion_tokens}")
if metrics.total_tokens:
    print(f"Total tokens: {metrics.total_tokens}")
if metrics.cost_usd:
    print(f"Cost: ${metrics.cost_usd:.6f}")
```

### 3. Listing Available Models

```python
from ai_factory import list_models, Config

config = Config(
    provider="openai",
    model="dummy",  # Model doesn't matter for listing
)

models = list_models("openai", config)

for model in models:
    print(f"\nModel: {model.name}")
    if model.context_window:
        print(f"  Context: {model.context_window:,} tokens")
    if model.input_cost_per_1k:
        print(f"  Input: ${model.input_cost_per_1k:.4f}/1k tokens")
    if model.output_cost_per_1k:
        print(f"  Output: ${model.output_cost_per_1k:.4f}/1k tokens")
    if model.metadata:
        print(f"  Metadata: {model.metadata}")
```

### 4. Retry Handling

Retries are automatic and logged. Access retry history:

```python
config = Config(
    provider="anthropic",
    model="claude-3-5-sonnet-20241022",
    max_retries=3,
    backoff_base_ms=250,
    backoff_multiplier=2.0,
)

result = run("Your prompt", config)

# Check retry history
if result.retry_history:
    print(f"Total attempts: {len(result.retry_history) + 1}")
    for i, retry in enumerate(result.retry_history, 1):
        print(f"Retry {i}: waited {retry.backoff_ms}ms, error: {retry.error_message}")
```

---

## Embedding Support

AI Factory supports generating text embeddings through supported providers. Embeddings are vector representations of text that can be used for semantic search, clustering, and similarity comparisons.

### Supported Providers

- ✅ **OpenAI**: Uses `text-embedding-3-small` or `text-embedding-3-large` models
- ✅ **Google Gemini**: Uses `gemini-embedding-001` model (3072-dimensional)
- ✅ **Stub**: Returns deterministic 8-dimensional zero vector for testing
- ❌ **Anthropic**: Not supported (returns error)
- ❌ **OpenRouter**: Not supported (returns error)
- ❌ **Copilot CLI**: Not supported (returns error)

### Basic Embedding Usage

```python
from ai_factory import embed, Config

# Configure for OpenAI embeddings
config = Config(
    provider="openai",
    model="text-embedding-3-small",
    ledger_enabled=False,
)

# Generate embedding
result = embed("Hello, world!", config)

if result.success:
    print(f"Vector dimension: {len(result.vector)}")
    print(f"First 5 values: {result.vector[:5]}")
    print(f"Latency: {result.metrics.latency_ms}ms")
else:
    print(f"Error: {result.error}")
```

### Using Gemini for Embeddings

```python
from ai_factory import embed, Config

config = Config(
    provider="gemini",
    model="gemini-embedding-001",  # 3072-dimensional embeddings
)

result = embed("Artificial intelligence and machine learning", config)

if result.success:
    print(f"Generated {len(result.vector)}-dimensional embedding")
    # Gemini gemini-embedding-001 produces 3072-dimensional embeddings
```

### EmbedResult Structure

```python
from ai_factory import embed, Config

config = Config(provider="openai", model="text-embedding-3-small")
result = embed("Sample text", config)

# Access result fields
print(f"Vector: {result.vector}")              # list[float]
print(f"Success: {result.success}")            # bool
print(f"Error: {result.error}")                # Optional[str]
print(f"Metrics: {result.metrics}")           # Metrics object

# Access metrics
print(f"Input chars: {result.metrics.input_chars}")
print(f"Latency: {result.metrics.latency_ms}ms")
print(f"Success: {result.metrics.success}")
```

### Embedding with Ledger

Embeddings are automatically logged to the ledger when enabled. The ledger records metadata but does **not** store the full vector or raw input text for efficiency.

```python
from ai_factory import embed, Config

config = Config(
    provider="openai",
    model="text-embedding-3-small",
    ledger_enabled=True,
    ledger_path="./embeddings.is",
)

result = embed("Document content to embed", config)

# Ledger entry includes:
# - Timestamp
# - Provider and model
# - Input character count
# - Vector dimension
# - Latency
# - Success status
# - SHA256 hash of input (for reproducibility verification)
```

**Example ledger entry (IS format):**
```lisp
(embed
  (timestamp "2026-02-22T19:52:41.915984Z")
  (provider "gemini")
  (model "gemini-embedding-001")
  (input_chars 26)
  (vector_dim 3072)
  (latency_ms 145)
  (success true)
  (input_hash "06ffc5c5745c814e9bae12e67691e0891d17a2ac04e5b390c3db59e0856204cb")
)
```

**Example ledger entry (JSON format):**
```json
{
  "type": "embed",
  "timestamp": "2026-02-22T19:52:41.917236Z",
  "provider": "gemini",
  "model": "gemini-embedding-001",
  "input_chars": 26,
  "vector_dim": 3072,
  "latency_ms": 145,
  "success": true,
  "input_hash": "06ffc5c5745c814e9bae12e67691e0891d17a2ac04e5b390c3db59e0856204cb"
}
```

### CLI Usage for Embeddings

```bash
# Embed text directly
ai_factory embed --provider openai --model text-embedding-3-small --text "Hello world"

# Or using Python module syntax
python -m ai_factory.cli embed --provider openai --model text-embedding-3-small --text "Your text"

# Read text from a file
ai_factory embed --provider gemini --model models/embedding-001 --text-file input.txt

# Save vector to file
ai_factory embed --provider openai --text "Sample" --output vector.json

# With ledger enabled (default)
ai_factory embed --provider openai --text "Test" --ledger-path embeddings.is

# Without ledger
ai_factory embed --provider openai --text "Test" --no-ledger
```

### Batch Embedding Example

```python
from ai_factory import embed, Config
import json

def embed_documents(documents: list[str], output_file: str = "embeddings.json"):
    """Generate embeddings for multiple documents."""
    config = Config(
        provider="openai",
        model="text-embedding-3-small",
        ledger_enabled=True,
        ledger_path="./batch-embeddings.is",
    )
    
    embeddings = []
    
    for i, doc in enumerate(documents, 1):
        print(f"Processing document {i}/{len(documents)}...")
        result = embed(doc, config)
        
        if result.success:
            embeddings.append({
                "text": doc,
                "vector": result.vector,
                "dimension": len(result.vector),
                "latency_ms": result.metrics.latency_ms,
            })
        else:
            print(f"Failed to embed document {i}: {result.error}")
    
    # Save to file
    with open(output_file, 'w') as f:
        json.dump(embeddings, f, indent=2)
    
    print(f"Saved {len(embeddings)} embeddings to {output_file}")
    return embeddings

# Use it
documents = [
    "Machine learning is a subset of artificial intelligence.",
    "Deep learning uses neural networks with multiple layers.",
    "Natural language processing enables computers to understand text.",
]

embeddings = embed_documents(documents)
```

### Semantic Similarity Example

```python
from ai_factory import embed, Config
import numpy as np

def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

def find_similar_texts(query: str, corpus: list[str], top_k: int = 3):
    """Find most similar texts to the query using embeddings."""
    config = Config(
        provider="openai",
        model="text-embedding-3-small",
        ledger_enabled=False,
    )
    
    # Embed query
    query_result = embed(query, config)
    if not query_result.success:
        print(f"Failed to embed query: {query_result.error}")
        return []
    
    # Embed corpus
    similarities = []
    for text in corpus:
        result = embed(text, config)
        if result.success:
            similarity = cosine_similarity(query_result.vector, result.vector)
            similarities.append((text, similarity))
    
    # Sort by similarity
    similarities.sort(key=lambda x: x[1], reverse=True)
    
    return similarities[:top_k]

# Use it
query = "How do neural networks work?"
corpus = [
    "Neural networks are inspired by biological neurons.",
    "Python is a popular programming language.",
    "Deep learning models require large datasets.",
    "The weather today is sunny and warm.",
    "Backpropagation is used to train neural networks.",
]

results = find_similar_texts(query, corpus, top_k=3)

print(f"Query: {query}\n")
for text, score in results:
    print(f"Similarity: {score:.4f} - {text}")
```

### Testing with Stub Provider

```python
from ai_factory import embed, Config

def test_embedding_logic():
    """Test your embedding logic without API calls."""
    config = Config(
        provider="stub",
        model="stub-1",
        ledger_enabled=False,
    )
    
    result = embed("Test text", config)
    
    # Stub provider returns deterministic zero vector
    assert result.success
    assert len(result.vector) == 8  # Stub returns 8-dimensional vector
    assert result.vector == [0.0] * 8
    assert result.error is None
    print("✓ Embedding test passed")

test_embedding_logic()
```

### Error Handling for Embeddings

```python
from ai_factory import embed, Config

config = Config(
    provider="anthropic",  # Anthropic doesn't support embeddings
    model="claude-3-5-sonnet-20241022",
)

result = embed("Some text", config)

if not result.success:
    print(f"Embedding failed: {result.error}")
    # Output: "Anthropic provider does not support embedding generation"
    
    # Vector will be empty on failure
    assert result.vector == []
```

### Key Differences from run()

1. **Separate operation**: `embed()` is independent from `run()` - no shared state
2. **No prompt scaffolding**: Direct text-to-vector conversion
3. **Different ledger entry**: Uses `type="embed"` instead of `type="run"`
4. **No retry logic**: Currently embeddings don't retry on failure (future enhancement)
5. **Synchronous only**: No background processing or caching
6. **Deterministic**: Same input always produces same vector (per provider/model)

---

## Provider-Specific Examples

### OpenAI

```python
from ai_factory import run, Config

config = Config(
    provider="openai",
    model="gpt-4o",  # or "gpt-4o-mini", "gpt-4-turbo", etc.
)

result = run("Write a haiku about programming", config)
print(result.output)

# Access OpenAI-specific metadata
metadata = result.metrics.provider_metadata
if metadata:
    print(f"Model used: {metadata.get('model')}")
    print(f"Finish reason: {metadata.get('finish_reason')}")
    print(f"Request ID: {metadata.get('id')}")
```

### Anthropic (Claude)

```python
from ai_factory import run, Config

config = Config(
    provider="anthropic",
    model="claude-3-5-sonnet-20241022",  # or haiku, opus variants
)

result = run("Explain photosynthesis briefly", config)
print(result.output)

# Access Claude-specific metadata
metadata = result.metrics.provider_metadata
if metadata:
    print(f"Stop reason: {metadata.get('stop_reason')}")
    print(f"Model: {metadata.get('model')}")
```

### Google Gemini

```python
from ai_factory import run, Config

config = Config(
    provider="gemini",
    model="gemini-2.0-flash-exp",  # or "gemini-1.5-pro", etc.
)

result = run("What are the main clouds types?", config)
print(result.output)

# Access Gemini-specific metadata
metadata = result.metrics.provider_metadata
if metadata:
    print(f"Model: {metadata.get('model_name')}")
    print(f"Safety ratings: {metadata.get('safety_ratings')}")
```

### OpenRouter

```python
from ai_factory import run, Config

config = Config(
    provider="openrouter",
    model="anthropic/claude-3.5-sonnet",  # OpenRouter model format
)

result = run("What is the meaning of life?", config)
print(result.output)
```

### Copilot CLI

```python
from ai_factory import run, Config

# Requires GitHub Copilot CLI installed: gh extension install github/gh-copilot
config = Config(
    provider="copilot_cli",
    model="default",  # Model is managed by Copilot
)

result = run("How do I list files in a directory?", config)
print(result.output)
```

### Local server (llama-server, ollama /v1)

```python
from ai_factory import run, Config

# No key. model="" uses the one model the server lists, and records it.
config = Config(provider="local", model="", max_tokens=300)

result = run("Summarise: ...", config)
if not result.success:
    print(result.error)  # e.g. "local server not reachable at http://localhost:8089/v1 ..."
print(result.output, result.metrics.cost_usd)  # cost_usd == 0.0
```

### Ollama

```python
from ai_factory import run, Config

# Requires `ollama serve`; see docs/OLLAMA_PROVIDER.md
config = Config(provider="ollama", model="llama3.2")

result = run("Why is the sky blue?", config)
print(result.output)
```

### Claude Code

```python
from ai_factory import run, Config

# Uses the authenticated `claude` CLI; model is an alias or full model id
config = Config(provider="claude_code", model="haiku")

result = run("Name three sorting algorithms.", config)
print(result.output)
```

---

## Error Handling

### Basic Error Handling

```python
from ai_factory import run, Config

config = Config(provider="openai", model="gpt-4o-mini")

result = run("Your prompt", config)

if result.success:
    print(f"Success: {result.output}")
else:
    print(f"Failed after {result.metrics.latency_ms}ms")
    print(f"Error: {result.error}")
    
    # Check retry history
    if result.retry_history:
        print(f"Failed after {len(result.retry_history) + 1} attempts")
```

### Handling Specific Scenarios

```python
from ai_factory import run, Config

config = Config(
    provider="anthropic",
    model="claude-3-5-sonnet-20241022",
    max_retries=5,
)

result = run("Complex analysis task...", config)

if not result.success:
    # Check if we exhausted retries
    if result.retry_history and len(result.retry_history) >= config.max_retries:
        print("Failed after exhausting all retries")
        print(f"Last error: {result.error}")
    else:
        print("Failed without retries (non-retryable error)")
        print(f"Error: {result.error}")
else:
    print(f"Success after {len(result.retry_history) + 1} attempts")
    print(result.output)
```

### Validation Errors

```python
from ai_factory import Config

try:
    config = Config(
        provider="openai",
        model="gpt-4o-mini",
        max_retries=-1,  # Invalid!
    )
except ValueError as e:
    print(f"Configuration error: {e}")
```

---

## Ledger Integration

### Basic Ledger Usage

```python
from ai_factory import run, Config

config = Config(
    provider="openai",
    model="gpt-4o-mini",
    ledger_enabled=True,
    ledger_path="./my-app-ledger.is",
    capture_prompt=True,
    capture_output=True,
)

# Every run is automatically logged
result = run("First prompt", config)
result = run("Second prompt", config)
result = run("Third prompt", config)

# Ledger now contains 3 entries in ./my-app-ledger.is
```

### JSON Ledger Format

```python
from ai_factory import run, Config

config = Config(
    provider="anthropic",
    model="claude-3-5-sonnet-20241022",
    ledger_enabled=True,
    ledger_path="./my-app-ledger.jsonl",
    ledger_format="json",  # Use JSON Lines format
    capture_prompt=True,
    capture_output=True,
)

result = run("Test prompt", config)
# Creates one JSON object per line in the ledger file
```

### Analyzing the Ledger

```python
from ai_factory.ledger_analysis import analyze_ledger, format_summary

# Analyze the ledger
summary = analyze_ledger("./my-app-ledger.is")

# Print formatted summary
output = format_summary(summary)
print(output)

# Or access data programmatically
print(f"Total runs: {summary.total_runs}")
print(f"Success rate: {summary.success_rate:.1%}")
print(f"Total cost: ${summary.total_cost:.4f}")
print(f"Avg latency: {summary.avg_latency_ms:.0f}ms")

# Per-provider breakdown
for provider, stats in summary.provider_breakdown.items():
    print(f"\n{provider}:")
    print(f"  Runs: {stats['runs']}")
    print(f"  Success: {stats['success']}")
    print(f"  Cost: ${stats['cost']:.4f}")
```

### Disabling Ledger for Specific Runs

```python
from ai_factory import run, Config

# Global config with ledger enabled
config_with_ledger = Config(
    provider="openai",
    model="gpt-4o-mini",
    ledger_enabled=True,
)

# Temporary config without ledger
config_no_ledger = Config(
    provider="openai",
    model="gpt-4o-mini",
    ledger_enabled=False,
)

run("This is logged", config_with_ledger)
run("This is NOT logged", config_no_ledger)
run("This is logged again", config_with_ledger)
```

### Programmatic Ledger Access

You can append custom events to the ledger from your application:

```python
from ai_factory import append_event

# Add a workflow checkpoint
append_event(
    ledger_path="./my-app-ledger.is",
    event_type="workflow",
    data={
        "role": "coder",
        "run_id": "abc123",
        "step_id": 4,
        "step_size": "small",
        "status": "completed"
    }
)

# Add custom metrics
append_event(
    ledger_path="./my-app-ledger.is",
    event_type="checkpoint",
    data={
        "name": "feature_implementation",
        "files_modified": 5,
        "tests_passing": True,
        "notes": "Implemented user authentication"
    }
)

# Use JSON format
append_event(
    ledger_path="./my-app-ledger.jsonl",
    event_type="deployment",
    data={
        "environment": "production",
        "version": "2.1.0",
        "status": "success",
        "services": ["api", "worker", "frontend"]
    },
    ledger_format="json"
)
```

**Supported data types:**
- **Booleans**: Serialized as `true`/`false`
- **Numbers**: Integer and float values
- **Strings**: Properly escaped and quoted
- **Lists/Dicts**: Serialized as JSON strings

**Features:**
- Automatic UTC timestamp in ISO 8601 format
- Automatic directory creation if needed
- Safe error handling (failures logged but don't raise exceptions)

**Example output (IS format):**
```lisp
(workflow
  (timestamp "2026-02-14T02:44:35.719335Z")
  (role "coder")
  (run_id "abc123")
  (step_id 4)
  (step_size "small")
  (status "completed")
)
```

**Example output (JSON format):**
```json
{"timestamp": "2026-02-14T02:44:35.719335Z", "event_type": "workflow", "role": "coder", "run_id": "abc123", "step_id": 4, "step_size": "small", "status": "completed"}
```

### Workflow Tracking Example

```python
import uuid
from ai_factory import run, Config, append_event

# Generate unique workflow ID
workflow_id = str(uuid.uuid4())[:8]

config = Config(
    provider="gemini",
    model="gemini-2.5-flash",
    ledger_enabled=True,
    ledger_path="./workflow-ledger.is",
)

# Mark workflow start
append_event(
    ledger_path=config.ledger_path,
    event_type="workflow",
    data={
        "workflow_id": workflow_id,
        "stage": "start",
        "total_steps": 3
    }
)

# Step 1: Generate code
result1 = run("Write a Python function to calculate fibonacci", config)

append_event(
    ledger_path=config.ledger_path,
    event_type="workflow",
    data={
        "workflow_id": workflow_id,
        "stage": "step_1",
        "step_name": "generate_code",
        "success": result1.success,
        "output_length": len(result1.output) if result1.success else 0
    }
)

# Step 2: Review code
if result1.success:
    result2 = run(f"Review this code:\n\n{result1.output}", config)
    
    append_event(
        ledger_path=config.ledger_path,
        event_type="workflow",
        data={
            "workflow_id": workflow_id,
            "stage": "step_2",
            "step_name": "review_code",
            "success": result2.success
        }
    )

# Mark completion
append_event(
    ledger_path=config.ledger_path,
    event_type="workflow",
    data={
        "workflow_id": workflow_id,
        "stage": "complete",
        "overall_success": result1.success and result2.success
    }
)
```

This creates a ledger with both AI Factory run entries and your custom workflow events, making it easy to track complex multi-step processes.

---

## Advanced Patterns

### 1. Multi-Provider Fallback

```python
from ai_factory import run, Config

def run_with_fallback(prompt: str) -> str:
    """Try multiple providers in sequence."""
    providers = [
        ("openai", "gpt-4o-mini"),
        ("anthropic", "claude-3-5-haiku-20241022"),
        ("gemini", "gemini-2.0-flash-exp"),
    ]
    
    for provider, model in providers:
        config = Config(
            provider=provider,
            model=model,
            max_retries=2,
            ledger_enabled=False,
        )
        
        result = run(prompt, config)
        
        if result.success:
            print(f"Success with {provider}/{model}")
            return result.output
    
    raise Exception("All providers failed")

# Use it
output = run_with_fallback("What is the capital of France?")
print(output)
```

### 2. Batch Processing with Rate Limiting

```python
import time
from ai_factory import run, Config

def process_batch(prompts: list[str], delay_ms: int = 100):
    """Process multiple prompts with rate limiting."""
    config = Config(
        provider="openai",
        model="gpt-4o-mini",
        ledger_enabled=True,
        ledger_path="./batch-processing.is",
    )
    
    results = []
    for i, prompt in enumerate(prompts, 1):
        print(f"Processing {i}/{len(prompts)}...")
        result = run(prompt, config)
        results.append(result)
        
        if i < len(prompts):
            time.sleep(delay_ms / 1000.0)
    
    return results

# Use it
prompts = [
    "What is AI?",
    "What is ML?",
    "What is deep learning?",
]

results = process_batch(prompts, delay_ms=200)

for i, result in enumerate(results, 1):
    if result.success:
        print(f"{i}. {result.output[:100]}...")
```

### 3. Building a Simple Chat Loop

```python
from ai_factory import run, Config

def chat_loop():
    """Simple chat interface with conversation history."""
    config = Config(
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
        ledger_enabled=True,
        capture_prompt=True,
        capture_output=True,
    )
    
    conversation = []
    
    print("Chat started. Type 'quit' to exit.\n")
    
    while True:
        user_input = input("You: ").strip()
        
        if user_input.lower() in ["quit", "exit"]:
            break
        
        # Build context from conversation history
        conversation.append(f"User: {user_input}")
        
        # Create prompt with context
        context = "\n".join(conversation[-10:])  # Last 5 exchanges
        prompt = f"Conversation so far:\n{context}\n\nRespond to the last user message."
        
        result = run(prompt, config)
        
        if result.success:
            print(f"Assistant: {result.output}\n")
            conversation.append(f"Assistant: {result.output}")
        else:
            print(f"Error: {result.error}\n")

# Run the chat
chat_loop()
```

### 4. Testing with Stub Provider

```python
from ai_factory import run, Config

def test_my_application():
    """Test your app logic without calling real APIs."""
    config = Config(
        provider="stub",
        model="stub-1",
        ledger_enabled=False,
    )
    
    # Stub provider echoes the prompt with "STUB: " prefix
    result = run("test input", config)
    
    assert result.success
    assert result.output == "STUB: test input"
    assert result.metrics.latency_ms < 100  # Stub is very fast

# Run tests
test_my_application()
print("Tests passed!")
```

### 5. Custom Retry Strategy

```python
from ai_factory import run, Config

def aggressive_retry(prompt: str) -> str:
    """Use aggressive retry settings for critical operations."""
    config = Config(
        provider="openai",
        model="gpt-4o",
        max_retries=10,
        backoff_base_ms=1000,  # Start with 1 second
        backoff_multiplier=2.0,  # Double each time
        ledger_enabled=True,
    )
    
    result = run(prompt, config)
    
    if not result.success:
        raise Exception(f"Failed after {len(result.retry_history) + 1} attempts: {result.error}")
    
    return result.output

# Use it
output = aggressive_retry("Critical analysis task...")
```

### 6. Monitoring and Metrics Collection

```python
from ai_factory import run, Config
from dataclasses import asdict
import json

class MetricsCollector:
    def __init__(self, output_file: str = "metrics.jsonl"):
        self.output_file = output_file
    
    def run_and_collect(self, prompt: str, config: Config):
        """Run a prompt and collect detailed metrics."""
        result = run(prompt, config)
        
        # Serialize metrics
        metrics_data = {
            "success": result.success,
            "prompt_length": len(prompt),
            "output_length": len(result.output) if result.output else 0,
            "metrics": asdict(result.metrics),
            "retry_count": len(result.retry_history),
        }
        
        # Append to JSONL file
        with open(self.output_file, "a") as f:
            f.write(json.dumps(metrics_data) + "\n")
        
        return result

# Use it
collector = MetricsCollector("my-app-metrics.jsonl")

config = Config(provider="openai", model="gpt-4o-mini")

collector.run_and_collect("First prompt", config)
collector.run_and_collect("Second prompt", config)
```

---

## Best Practices

1. **Use Config Loader**: Prefer `load_config()` over direct `Config()` construction for flexibility
2. **Set API Keys via Environment**: Never hardcode API keys in your code
3. **Enable Ledger for Production**: Keep an audit trail of all LLM calls
4. **Use JSON Ledger for Parsing**: If you need to programmatically analyze logs
5. **Handle Failures Gracefully**: Always check `result.success` before using output
6. **Set Appropriate Retries**: More retries for critical operations, fewer for interactive use
7. **Use Stub Provider for Tests**: Fast, deterministic, no API costs
8. **Monitor Costs**: Check `result.metrics.cost_usd` and use ledger analysis
9. **Capture Selectively**: Only enable `capture_prompt`/`capture_output` when needed for debugging

---

## Troubleshooting

### API Key Not Found

```python
# Error: Provider requires API key
# Solution: Set environment variable

import os
os.environ["OPENAI_API_KEY"] = "sk-..."  # Better: set in shell

config = Config(provider="openai", model="gpt-4o-mini")
```

### Config Immutability Error

```python
# Error: Cannot modify frozen Config
# Solution: Create a new config

config1 = Config(provider="openai", model="gpt-4o-mini")
# config1.model = "gpt-4o"  # This raises an error!

# Instead:
config2 = Config(provider="openai", model="gpt-4o")
```

### Ledger File Permissions

```python
# Error: Permission denied writing to ledger
# Solution: Use a writable path

config = Config(
    provider="openai",
    model="gpt-4o-mini",
    ledger_path="./my-ledger.is",  # Current directory (usually writable)
)
```

---

## Reference

### Main Functions

- `run(prompt: str, config: Config) -> RunResult`: Execute a prompt
- `list_models(provider: str, config: Config) -> list[ModelInfo]`: List available models
- `load_config(**kwargs) -> Config`: Load configuration with precedence

### Main Classes

- `Config`: Immutable configuration dataclass
- `RunResult`: Result with output, success, metrics, retry_history
- `Metrics`: Performance and cost metrics
- `ModelInfo`: Model metadata (name, context, costs)

### Supported Providers

- `openai`: OpenAI GPT models
- `anthropic`: Anthropic Claude models
- `gemini`: Google Gemini models
- `openrouter`: OpenRouter (multi-model gateway)
- `copilot_cli`: GitHub Copilot CLI
- `local`: OpenAI-compatible local server (llama-server, ollama `/v1`)
- `ollama`: Ollama native API
- `claude_code`: the `claude` CLI (`claude -p`)
- `stub`: Testing provider

---

## Additional Resources

- **README.md**: Quick start and CLI usage
- **docs/ARCHITECTURE.md**: System design and provider contract
- **Configuration examples**: See `aifactory.toml.example` and `aifactory.toml.json-example`
