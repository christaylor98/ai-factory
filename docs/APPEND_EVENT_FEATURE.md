# append_event Feature Summary

## Overview

Added programmatic ledger access via the `append_event` function, allowing external Python scripts to write custom events to AI Factory ledgers.

## API

### Function Signature

```python
def append_event(
    ledger_path: str,
    event_type: str,
    data: dict,
    ledger_format: str = "is"
) -> None
```

### Parameters

- **ledger_path**: Path to the ledger file (can be relative or absolute)
- **event_type**: Type of event (e.g., "workflow", "checkpoint", "deployment")
- **data**: Dictionary containing event data (any JSON-serializable values)
- **ledger_format**: "is" (default) or "json"

### Import

```python
from ai_factory import append_event
```

## Features

### Supported Data Types

- **Booleans**: Serialized as `true`/`false` in IS format
- **Numbers**: Integer and float values
- **Strings**: Properly escaped and quoted
- **Lists/Dicts**: Serialized as JSON strings

### Automatic Timestamp

Every event automatically includes a UTC timestamp in ISO 8601 format.

### Error Handling

Failures are logged to stderr but do not raise exceptions (same philosophy as core ledger writes).

### Directory Creation

The function automatically creates parent directories if they don't exist.

## Examples

### Basic Usage

```python
from ai_factory import append_event

append_event(
    ledger_path="./LEDGER.is",
    event_type="workflow",
    data={
        "role": "coder",
        "run_id": "abc123",
        "step_id": 4,
        "status": "completed"
    }
)
```

### JSON Format

```python
append_event(
    ledger_path="./LEDGER.jsonl",
    event_type="deployment",
    data={
        "environment": "production",
        "version": "2.1.0"
    },
    ledger_format="json"
)
```

### Complex Data

```python
append_event(
    ledger_path="./LEDGER.is",
    event_type="experiment",
    data={
        "experiment_id": "exp-001",
        "parameters": {"learning_rate": 0.01},
        "results": {"accuracy": 0.95},
        "completed": True
    }
)
```

## Output Format

### IS Format (Default)

```lisp
(workflow
  (timestamp "2026-02-14T02:44:35.719335Z")
  (role "coder")
  (run_id "workflow-abc123")
  (step_id 4)
  (step_size "small")
  (status "completed")
)
```

### JSON Format

```json
{"timestamp": "2026-02-14T02:44:35.719335Z", "event_type": "workflow", "role": "coder", "run_id": "workflow-abc123", "step_id": 4, "step_size": "small", "status": "completed"}
```

## Files Modified

1. **src/ai_factory/ledger.py**: Added `append_event` function (75 lines)
2. **src/ai_factory/__init__.py**: Exported `append_event` in public API
3. **README.md**: Added documentation section for programmatic ledger access
4. **tests/test_append_event.py**: Comprehensive test suite (5 test cases)
5. **examples/append_event_demo.py**: Basic usage examples
6. **examples/workflow_tracking.py**: Workflow integration example

## Use Cases

- **Workflow tracking**: Mark stages of multi-step processes
- **Checkpoints**: Record progress milestones
- **Custom metrics**: Log application-specific events
- **Integration**: Combine with other tools that also log to the same ledger
- **Debugging**: Add custom debug markers to execution logs
- **Auditing**: Track deployment, configuration changes, etc.

## Testing

All tests pass:
- IS format serialization
- JSON format serialization
- Complex data types
- Multiple entries
- Directory creation
- Integration with existing ledger files

```bash
pytest tests/test_append_event.py -v
# 5 passed in 1.04s
```

## Backward Compatibility

This is a purely additive change:
- No existing functionality modified
- No breaking changes
- New function is opt-in
- Existing ledger format unchanged
