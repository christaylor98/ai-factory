# AI Factory

## Overview

AI Factory is a minimal, production-ready LLM execution library with mechanical retries, provider model listing, and an append-only human-readable ledger system.

**Key Features:**
- **Simple API**: Both importable Python library and CLI wrapper
- **Mechanical Retries**: Configurable exponential backoff with full logging
- **Provider System**: Extensible provider architecture (stub provider included)
- **Append-Only Ledger**: Human-readable IS-format execution log with optional capture
- **Zero Orchestration**: No workflow engine, no background threads, no caching
- **Observability**: Comprehensive metrics and retry tracking

## Installation

```bash
# Install in development mode
pip install -e .

# With dev dependencies
pip install -e ".[dev]"
```

## Library Usage

```python
from ai_factory_ import run, list_models, Config

# Basic usage
config = Config(
    provider="stub",
    model="stub-1"
)

result = run("What is the capital of France?", config)
print(result.output)
print(f"Success: {result.success}")
print(f"Latency: {result.metrics.latency_ms}ms")

# With custom retry settings
config = Config(
    provider="stub",
    model="stub-1",
    max_retries=3,
    backoff_base_ms=500,
    backoff_multiplier=2.0,
    capture_prompt=True,
    capture_output=True,
)

result = run("My prompt", config)

# List available models
models = list_models("stub", config)
for model in models:
    print(f"{model.name}: {model.context_window} tokens")
```

## CLI Usage

```bash
# Run a prompt
ai-factory run \
  --provider stub \
  --model stub-1 \
  --prompt "hello world"

# Run with capture enabled
ai-factory run \
  --provider stub \
  --model stub-1 \
  --prompt "test" \
  --capture-prompt \
  --capture-output

# Run with custom retry settings
ai-factory run \
  --provider stub \
  --model stub-1 \
  --prompt "test" \
  --max-retries 3 \
  --backoff-base-ms 500

# List models
ai-factory models --provider stub

# Disable ledger
ai-factory run \
  --provider stub \
  --model stub-1 \
  --prompt "test" \
  --no-ledger
```

## Configuration

### Config Object

```python
@dataclass
class Config:
    provider: str                    # Provider name (e.g., "stub")
    model: str                       # Model name (e.g., "stub-1")
    max_retries: int = 2             # Mechanical retries (default: 2)
    backoff_base_ms: int = 250       # Base backoff in ms (default: 250)
    backoff_multiplier: float = 2.0  # Backoff multiplier (default: 2.0)
    ledger_enabled: bool = True      # Enable ledger (default: True)
    ledger_path: str = "./LEDGER.is" # Ledger file path
    capture_prompt: bool = False     # Capture prompt in ledger
    capture_output: bool = False     # Capture output in ledger
    capture_limit_chars: int = 20000 # Capture limit in chars
```

## Ledger Format

The ledger uses IS (Indented S-expressions) format and is append-only. Each run creates one entry:

```lisp
(run
  (timestamp "2026-02-13T12:34:56.789Z")
  (provider "stub")
  (model "stub-1")
  (success true)
  (attempts 1)
  (metrics
    (input_chars 11)
    (output_chars 17)
    (latency_ms 42))
)
```

With retries:

```lisp
(run
  (timestamp "2026-02-13T12:34:56.789Z")
  (provider "stub")
  (model "stub-1")
  (success true)
  (attempts 2)
  (metrics
    (input_chars 20)
    (output_chars 26)
    (latency_ms 350))
  (retries
    (retry (attempt 1) (error_type "SimulatedError") (error_message "Simulated transient failure") (backoff_ms 250))
  )
)
```

With capture enabled:

```lisp
(run
  (timestamp "2026-02-13T12:34:56.789Z")
  (provider "stub")
  (model "stub-1")
  (success true)
  (attempts 1)
  (prompt "hello world")
  (output "STUB: hello world")
  (metrics
    (input_chars 11)
    (output_chars 17)
    (latency_ms 42))
)
```

### Ledger Rules

- **Append-only**: Never modifies existing entries
- **Observational**: Ledger failures do NOT fail the run
- **Optional**: Can be disabled with `ledger_enabled=False`
- **Bounded**: Captures are truncated with metadata if exceeding `capture_limit_chars`

## Retry Behavior

Retries are **mechanical only** (no prompt rewriting):

1. **Exponential Backoff**: `backoff_base_ms * (backoff_multiplier ** attempt)`
2. **Retry History**: Each failed attempt is logged with error details and backoff time
3. **Transparent**: All retries appear in the ledger and response metadata

### Stub Provider Test Modes

The stub provider supports special test modes:

- **`__FLAKE__`**: Fails first attempt, succeeds on retry
- **`__FAIL__`**: Fails all attempts (exhausts retries)
- Normal prompts: Echo with `"STUB: "` prefix

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=ai_factory_ --cov-report=term-missing

# Run specific test file
pytest tests_/test_run_success.py
```

## Architecture

### Module Structure

```
src/ai_factory_/
├── __init__.py           # Public API exports
├── config.py             # Config dataclass
├── result.py             # Result/response dataclasses
├── metrics.py            # Metrics utilities
├── ledger.py             # Ledger writing (IS format)
├── provider_registry.py  # Provider registration
├── runner.py             # Main run() logic
├── cli.py                # CLI wrapper (thin)
└── providers/
    ├── base.py           # BaseProvider interface
    └── stub.py           # Stub provider
```

### Design Principles

1. **Single Intent**: Each module has one clear purpose
2. **Small Modules**: No file > 300 LOC
3. **No Silent Failures**: Errors surface in RunResult and ledger
4. **Mechanical Simplicity**: No orchestration, planning, or background tasks
5. **Observable**: Full metrics and retry logging

## Data Contracts

### RunResult

```python
@dataclass
class RunResult:
    output: str          # Output text (empty if failed)
    success: bool        # Whether run succeeded
    metrics: Metrics     # Execution metrics
```

### Metrics

```python
@dataclass
class Metrics:
    # Required
    input_chars: int
    output_chars: int
    latency_ms: int
    success: bool
    
    # Optional
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]
    cost_usd: Optional[float]
    finish_reason: Optional[str]
    provider_metadata: Optional[dict]
```

### ProviderResponse

```python
@dataclass
class ProviderResponse:
    text: str                        # Response text
    metadata: dict                   # Provider-specific metadata
    attempts: int                    # Total attempts performed
    retry_history: list[RetryRecord] # Retry records
    error: Optional[str]             # Error message if failed
```

### ModelInfo

```python
@dataclass
class ModelInfo:
    name: str
    context_window: Optional[int]
    input_cost_per_1k: Optional[float]
    output_cost_per_1k: Optional[float]
    metadata: dict
```

## Adding New Providers

```python
from ai_factory_.providers.base import BaseProvider
from ai_factory_.result import ProviderResponse, ModelInfo
from ai_factory_.provider_registry import register_provider

class MyProvider(BaseProvider):
    def call(self, prompt: str) -> ProviderResponse:
        # Implement with retry logic using:
        # - self.config.max_retries
        # - self.config.backoff_base_ms
        # - self.config.backoff_multiplier
        pass
    
    def list_models(self) -> list[ModelInfo]:
        # Return available models
        pass

# Register
register_provider("myprovider", MyProvider)
```

## Constraints

- **No legacy modification**: Does not touch existing `src/ai_factory/` code
- **No orchestration**: No workflow engine, director, or planning concepts
- **IS format only**: Ledger is not JSON
- **Synchronous**: No async, threads, or background tasks
- **Observable**: All provider errors surface in RunResult and ledger

## Acceptance Criteria ✓

- ✓ Command works: `ai-factory run --provider stub --model stub-1 --prompt "hello"`
- ✓ Ledger created: `./LEDGER.is` contains `(run ...)` entry
- ✓ Retry behavior: `__FLAKE__` causes one retry, appears in ledger
- ✓ Model listing: `ai-factory models --provider stub` prints models
- ✓ Tests pass: All tests in `tests_/` pass

## License

MIT
