# AI-Factory — Modular Architecture (Authoritative Design)

---

# 1. System Purpose

AI-Factory is:

> A deterministic execution engine for one model interaction: a single prompt, or one streamed agent run
> With mechanical retry
> With append-only human-readable ledger logging (`is` format)
> And provider capability discovery (model listing)

Single-prompt `run()` is the first and simplest entry point, and adding agent runs changed nothing about it.
`start_agent()` (agent.py, since 1.1) runs one `claude -p` session with tools: it streams events, can be steered
and cancelled, and writes one ledger row. It starts one process and reports what happened. Deciding what to do
next stays with the caller, so it is not a workflow engine.

It is **not**:

* A workflow engine
* A planning system
* A state machine
* A multi-step orchestrator
* A governance substrate

It is a clean execution kernel.

---

# 2. Core Capabilities

AI-Factory supports:

1. Single prompt execution
2. Mechanical retry with exponential backoff
3. Append-only structured ledger logging
4. Optional prompt/output capture with limits
5. Provider metadata capture
6. Model discovery per provider
7. Importable Python API
8. Thin CLI wrapper

---

# 3. High-Level Module Structure

```
ai_factory/
│
├── cli.py
├── runner.py
├── config.py
├── result.py
├── metrics.py
├── ledger.py
├── provider_registry.py
│
└── providers/
    ├── base.py
    ├── anthropic.py
    ├── openai.py
    ├── gemini.py
    └── stub.py
```

---

# 4. Core Architectural Principles

### 4.1 Single Intent Per Module

Each module must have one responsibility only.

### 4.2 One Entry / One Exit

Public interfaces are minimal and explicit.

### 4.3 Observational Ledger

Ledger records execution results only.
Ledger never influences execution.

### 4.4 No Cross-Coupling

* Providers do not know about ledger.
* Ledger does not know about providers.
* Metrics does not know about providers.
* CLI does not contain business logic.

### 4.5 Deterministic Execution

No hidden state.
No background processes.
No implicit caching.

---

# 5. Public API

## 5.1 Prompt Execution

```python
run(prompt: str, config: Config) -> RunResult
```

## 5.2 Model Discovery

```python
list_models(provider_name: str, config: Config) -> list[ModelInfo]
```

These are the only public entry points.

---

# 6. Module Responsibilities

---

## 6.1 `config.py`

### Responsibility

Represent validated runtime configuration.

### Owns

* provider
* model
* retry policy
* ledger settings
* capture limits

### Structure

```python
class Config:
    provider: str
    model: str
    max_retries: int
    backoff_base_ms: int
    backoff_multiplier: float

    ledger_enabled: bool
    ledger_path: str
    capture_prompt: bool
    capture_output: bool
    capture_limit_chars: int
```

No IO in config.

---

## 6.2 `runner.py`

### Responsibility

Execute exactly one prompt.

### Flow

```
1. Select provider
2. Execute provider.call()
3. Measure latency
4. Compute metrics
5. Append ledger (if enabled)
6. Return RunResult
```

### Public API

```python
def run(prompt: str, config: Config) -> RunResult
```

Runner does NOT:

* Implement retry
* Serialize ledger
* Call provider SDK directly
* Perform model listing

---

## 6.3 `provider_registry.py`

### Responsibility

Resolve provider name → provider instance.

### Public API

```python
def get_provider(config: Config) -> BaseProvider

def list_models(provider_name: str, config: Config) -> list[ModelInfo]
```

Registry does NOT:

* Execute prompts
* Write ledger
* Cache results

---

## 6.4 `providers/base.py`

### Responsibility

Define provider contract.

### Interfaces

```python
class ProviderResponse:
    text: str
    metadata: dict
    attempts: int
    retry_history: list
    error: Optional[str]

class ModelInfo:
    name: str
    context_window: Optional[int]
    input_cost_per_1k: Optional[float]
    output_cost_per_1k: Optional[float]
    metadata: dict

class BaseProvider:
    def call(self, prompt: str, config: Config) -> ProviderResponse

    def list_models(self, config: Config) -> list[ModelInfo]
```

### Rules

* `call()` must implement mechanical retry.
* `list_models()` may raise `NotImplementedError`.
* Providers never write ledger.
* Providers never compute metrics.
* Providers never modify config.

---

## 6.5 `providers/*.py`

Each provider:

### Owns

* SDK/API calls
* Mechanical retry loop
* Backoff calculation
* Provider-specific error classification
* Extraction of provider metadata

### Retry Policy

```
for attempt in range(max_retries):
    try:
        call API
        return success
    except transient_error:
        record retry
        sleep(backoff)
return failure
```

No semantic retries.
No prompt rewriting.

---

## 6.6 `metrics.py`

### Responsibility

Compute execution metrics.

### Always Computes

* input_chars
* output_chars
* latency_ms
* success

### Optionally Captures (if provided)

* prompt_tokens
* completion_tokens
* total_tokens
* cost_usd
* finish_reason
* provider metadata

### API

```python
def compute(prompt: str, response: ProviderResponse, latency_ms: int) -> Metrics
```

Pure function. No IO.

---

## 6.7 `ledger.py`

### Responsibility

Append structured `(run ...)` entries to `LEDGER.is`.

### Characteristics

* Append-only
* No read capability
* No state management
* No aggregation
* No parsing

### Handles

* Retry history serialization
* Prompt/output capture (optional)
* Capture truncation rules

### Truncation Policy

If text exceeds `capture_limit_chars`:

```
(store first N chars)
(prompt_truncated true)
(prompt_original_length X)
```

Same for response.

Ledger must never fail execution.
If ledger write fails → warn but continue.

---

## 6.8 `result.py`

### Responsibility

Return structured result to caller.

```python
class RunResult:
    output: str
    metrics: Metrics
    success: bool
```

No logic.

---

## 6.9 `cli.py`

### Responsibility

Thin command-line interface.

### Commands

```
ai-factory run --provider anthropic --model claude-3-opus
ai-factory models --provider anthropic
```

CLI does:

* Parse arguments
* Build Config
* Call public API
* Print formatted output

CLI does not:

* Execute providers directly
* Write ledger
* Compute metrics

---

# 7. Data Flow

---

## 7.1 Prompt Execution Flow

```
User
  ↓
CLI or Library
  ↓
Config
  ↓
runner.run()
  ↓
provider_registry.get_provider()
  ↓
provider.call()   (retry inside)
  ↓
ProviderResponse
  ↓
metrics.compute()
  ↓
ledger.append()   (optional)
  ↓
RunResult
  ↓
Return to caller
```

---

## 7.2 Model Discovery Flow

```
User
  ↓
CLI or Library
  ↓
provider_registry.list_models()
  ↓
provider.list_models()
  ↓
list[ModelInfo]
  ↓
Return to caller
```

No ledger interaction.
No metrics computation.

---

# 8. Ledger Data Model

Each run appends:

```
(run
  (timestamp ...)
  (provider ...)
  (model ...)

  (input_chars ...)
  (output_chars ...)
  (latency_ms ...)
  (success ...)

  (attempts N)

  (retry ...)
  (retry ...)

  (provider_metadata ...)

  (prompt ...)    ;; optional
  (response ...)  ;; optional
)
```

No root wrapper.
Pure append-only.

---

# 9. Dependency Rules

Allowed:

```
cli → runner
runner → provider_registry
runner → metrics
runner → ledger
provider_registry → providers
providers → config
metrics → none
ledger → none
```

Forbidden:

```
providers → ledger
ledger → providers
metrics → providers
runner → provider implementation directly
config → provider implementation
```

---

# 10. Failure Boundaries

### Provider Failure

Returned as structured error.
Logged in ledger.
Returned to caller.

### Ledger Failure

Must not abort execution.

### Model Listing Failure

Raises provider error.
No ledger write.

---

# 11. Extension Model

To add new provider:

1. Add file in `providers/`
2. Implement `BaseProvider`
3. Register in registry
4. Done

No other modules modified.

---

# 12. System Guarantees

AI-Factory guarantees:

* Deterministic prompt execution
* Mechanical retry only
* Human-readable append-only ledger
* Bounded ledger growth
* Provider metadata capture
* Model discovery support
* Clean importable interface
* No orchestration contamination

---

This is now the frozen architecture.

You are safe to implement.

