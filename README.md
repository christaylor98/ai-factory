# ai-factory

Minimal, deterministic single-prompt LLM runner (library + CLI) with mechanical retries and an append-only execution ledger.

## What this is

- Run a single prompt against a configured provider/model.
- Retry transient failures with simple exponential backoff.
- Log every run to an append-only ledger (IS by default, JSONL optional).
- Keep configuration immutable once loaded.
- Capture provider metadata (raw API response data) for traceability.

## What this is not

- A multi-turn chat framework.
- A workflow/orchestration or agent framework.
- Async-first (execution is synchronous).

## Install

Requirements: Python 3.9+.

From PyPI (once published):

```bash
pip install ai-factory
```

From source (this repo):

```bash
pip install .
```

For development:

```bash
pip install -e ".[dev]"
```

Note: This project currently declares provider SDKs as normal dependencies (Anthropic/OpenAI/Gemini). If you are vendoring or slimming dependencies, adjust your installation strategy accordingly.

## Quickstart (CLI)

1) Export a provider key (example: Gemini):

```bash
export GEMINI_API_KEY=...  # required for provider=gemini
```

2) Create `aifactory.toml` in your working directory:

```toml
[default]
provider = "gemini"
model = "gemini-2.5-flash"

[ledger]
enabled = true
path = "./LEDGER.is"
format = "is"           # "is" (default) or "json"
capture_prompt = false
capture_output = false
capture_limit_chars = 20000
```

3) Run a prompt:

```bash
ai-factory run --prompt "Explain quantum computing in one sentence."
```

Override config from the CLI:

```bash
ai-factory run \
  --provider gemini \
  --model gemini-2.5-flash \
  --prompt "Hello, world!" \
  --max-retries 3 \
  --capture-prompt \
  --capture-output
```

List models (when supported by the provider):

```bash
ai-factory models --provider openai
ai-factory models --provider anthropic
ai-factory models --provider gemini
```

Summarize a ledger:

```bash
ai-factory ledger-summary
ai-factory ledger-summary --path ./LEDGER.is
```

## Configuration

### Precedence

Later sources override earlier sources:

1. Defaults (built-in)
2. Global config: `~/.aifactory/config.toml`
3. Local config: `./aifactory.toml` (current working directory)
4. Environment variables: `AIFACTORY_*`
5. CLI arguments (highest priority)

### Environment variables

Core config:

```bash
export AIFACTORY_PROVIDER=gemini
export AIFACTORY_MODEL=gemini-2.5-flash
export AIFACTORY_MAX_RETRIES=2
export AIFACTORY_BACKOFF_BASE_MS=250
export AIFACTORY_BACKOFF_MULTIPLIER=2.0

export AIFACTORY_LEDGER_ENABLED=true
export AIFACTORY_LEDGER_PATH=./LEDGER.is
export AIFACTORY_LEDGER_FORMAT=is   # or json
export AIFACTORY_CAPTURE_PROMPT=false
export AIFACTORY_CAPTURE_OUTPUT=false
export AIFACTORY_CAPTURE_LIMIT_CHARS=20000
```

Provider secrets (always via environment):

```bash
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
export GEMINI_API_KEY=...
export OPENROUTER_API_KEY=...
```

OpenRouter optional identification headers:

```bash
export OPENROUTER_HTTP_REFERER=https://example.com
export OPENROUTER_X_TITLE=ai-factory
```

### `.env` loading

`ai_factory` calls `python-dotenv`’s `load_dotenv()` on import (and the CLI entrypoint imports the package), so a `.env` file in your current working directory is typically enough for local development.

## Providers

Provider names are the exact strings used in config/CLI.

| Provider | Auth | `ai-factory models` | Notes |
|---|---|---:|---|
| `gemini` | `GEMINI_API_KEY` | ✅ | Uses `google.genai` (preferred) or legacy `google.generativeai` |
| `openai` | `OPENAI_API_KEY` | ✅ | Uses the OpenAI SDK (`OpenAI` client) |
| `anthropic` | `ANTHROPIC_API_KEY` | ✅ | Uses a fallback list (Anthropic has no public models API) |
| `openrouter` | `OPENROUTER_API_KEY` | ❌ | Model listing is not supported (raises `NotImplementedError`) |
| `copilot_cli` | `copilot` CLI login | ❌ | Requires the `copilot` binary in `PATH`; model listing not supported |
| `stub` | none | ✅ | For tests/demos (`__FAIL__`, `__FLAKE__` behaviors) |

## Ledger

Every `run` can append an entry to a ledger (unless disabled).

- Default format: IS (Indented S-expressions), path `./LEDGER.is`.
- Optional format: JSON Lines, via `ledger.format = "json"` or `--ledger-format json`.
- Prompt/output are *not* captured by default; enable with `--capture-prompt` / `--capture-output`.

Example IS entry:

```lisp
(run
  (timestamp "2026-02-13T10:30:00.000000Z")
  (provider "gemini")
  (model "gemini-2.5-flash")
  (success true)
  (attempts 1)
  (metrics
    (input_chars 42)
    (output_chars 156)
    (latency_ms 847)
    (total_tokens 57)
    (provider_metadata "{...json...}")
  )
)
```

Example JSONL entry:

```json
{"timestamp":"2026-02-13T10:30:00.000000Z","provider":"gemini","model":"gemini-2.5-flash","success":true,"attempts":1,"metrics":{"input_chars":42,"output_chars":156,"latency_ms":847}}
```

## Library usage

### Run a prompt

```python
from ai_factory import run
from ai_factory.config_loader import load_config

config = load_config(provider="gemini", model="gemini-2.5-flash")
result = run("What is the speed of light?", config)

if result.success:
    print(result.output)
    print(f"Latency: {result.metrics.latency_ms}ms")
else:
    raise RuntimeError("Request failed")
```

### List models

```python
from ai_factory import list_models
from ai_factory.config_loader import load_config

config = load_config(provider="openai", model="gpt-4o")
for m in list_models("openai", config):
    print(m.name)
```

### Append custom ledger events

```python
from ai_factory import append_event

append_event(
    ledger_path="./LEDGER.is",
    event_type="workflow",
    data={
        "role": "coder",
        "run_id": "abc123",
        "step_id": 4,
        "status": "completed",
    },
)
```

## Retry behavior

- Retryable errors: typically rate-limit, 5xx, and transient network failures (provider-dependent).
- Backoff: `backoff_ms = backoff_base_ms * (backoff_multiplier ^ attempt)`.
- Max attempts: `max_retries + 1` (initial attempt + retries).

## Testing

```bash
pytest
```

## More docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/AI_FACTORY.md](docs/AI_FACTORY.md)
- [docs/APPEND_EVENT_FEATURE.md](docs/APPEND_EVENT_FEATURE.md)

## License

MIT — see [LICENSE](LICENSE).

The ledger uses IS (Indented S-expressions) format:

```lisp
(run
  (timestamp "2026-02-13T10:30:00.000000Z")
  (provider "gemini")
  (model "gemini-2.5-flash")
  (success true)
  (attempts 1)
  (metrics
    (input_chars 42)
    (output_chars 156)
    (latency_ms 847)
    (prompt_tokens 12)
    (completion_tokens 45)
    (total_tokens 57)
    (provider_metadata "{\"id\":\"msg_123\",\"model\":\"gemini-2.5-flash\",\"usage\":{...}}")
  )
)
```

## Retry Behavior

- **Retryable errors**: 429 (rate limit), 500-504 (server errors), network errors
- **Non-retryable errors**: 401/403 (auth), 400 (bad request)
- **Backoff calculation**: `backoff_ms = backoff_base_ms * (backoff_multiplier ^ attempt)`
- **Max attempts**: `max_retries + 1` (initial attempt + retries)

Example with default config (max_retries=2, backoff_base_ms=250, backoff_multiplier=2.0):
- Attempt 1: Immediate
- Attempt 2: Wait 250ms
- Attempt 3: Wait 500ms

## Testing

```bash
# Run all tests
pytest tests_/

# Run specific test modules
pytest tests_/test_config_loader.py
pytest tests_/test_provider_metadata.py

# Run with coverage
pytest tests_/ --cov=src/ai_factory_
```

## Project Structure

```
src/ai_factory_/
  __init__.py          # Package exports
  cli.py               # CLI interface
  config.py            # Immutable Config dataclass
  config_loader.py     # TOML and precedence logic
  ledger.py            # Append-only ledger writer
  ledger_analysis.py   # Ledger statistics and parsing
  metrics.py           # Metrics construction utilities
  provider_registry.py # Provider factory
  result.py            # Result dataclasses
  runner.py            # Main execution logic
  providers/
    base.py            # BaseProvider interface
    anthropic.py       # Anthropic implementation
    openai.py          # OpenAI implementation
    gemini.py          # Google Gemini implementation
    openrouter.py      # OpenRouter implementation
    copilot_cli.py     # GitHub Copilot CLI
    stub.py            # Testing stub
```

## Configuration Immutability

The `Config` dataclass is frozen after construction:

```python
config = load_config(provider="gemini", model="gemini-2.5-flash")

# This will raise FrozenInstanceError
config.provider = "openai"  # ❌ Error!
config.max_retries = 10     # ❌ Error!
```

This ensures:
- No accidental config mutation
- Predictable behavior across executions
- Thread-safe config sharing (if using threads)

## Version

Current version: **1.0.0-rc1**

Ready for production use after final validation.

## License

See LICENSE file.

## Contributing

This is a finalized, stable implementation. Extensions should:
1. Not break existing behavior
2. Maintain deterministic execution
3. Preserve immutability guarantees
4. Include comprehensive tests

---

**Philosophy**: ai-factory does one thing well - execute single prompts with retry logic and logging. It is intentionally minimal. For complex workflows, orchestration, or multi-turn conversations, compose this library with other tools.
