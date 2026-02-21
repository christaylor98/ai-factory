#!/usr/bin/env python3
"""
Example of using append_event to add custom events to the AI Factory ledger.
"""
from ai_factory import append_event

# Example 1: Basic workflow event
append_event(
    ledger_path="./LEDGER.is",
    event_type="workflow",
    data={
        "role": "coder",
        "run_id": "workflow-abc123",
        "step_id": 4,
        "step_size": "small",
        "status": "completed"
    }
)

# Example 2: Custom checkpoint event
append_event(
    ledger_path="./LEDGER.is",
    event_type="checkpoint",
    data={
        "name": "feature_implementation",
        "files_modified": 5,
        "tests_passing": True,
        "notes": "Implemented user authentication"
    }
)

# Example 3: Using JSON format
append_event(
    ledger_path="./LEDGER.jsonl",
    event_type="deployment",
    data={
        "environment": "production",
        "version": "2.1.0",
        "status": "success",
        "services": ["api", "worker", "frontend"]
    },
    ledger_format="json"
)

# Example 4: Complex nested data
append_event(
    ledger_path="./LEDGER.is",
    event_type="experiment",
    data={
        "experiment_id": "exp-001",
        "parameters": {"learning_rate": 0.01, "batch_size": 32},
        "results": {"accuracy": 0.95, "loss": 0.12},
        "completed": True
    }
)

print("Events appended successfully to ledger files!")
