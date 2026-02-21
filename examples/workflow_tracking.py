#!/usr/bin/env python3
"""
Example: Using ai-factory with append_event for workflow tracking.

This demonstrates how to use ai-factory to execute LLM prompts while
tracking workflow progress in the same ledger.
"""
import uuid
from ai_factory import run, Config, append_event

# Generate a unique run ID for this workflow
workflow_id = str(uuid.uuid4())[:8]

# Create configuration
config = Config(
    provider="gemini",
    model="gemini-2.5-flash",
    ledger_enabled=True,
    ledger_path="./workflow-ledger.is",
    capture_prompt=False,
    capture_output=True,
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
print("Step 1: Generating code...")
result1 = run("Write a Python function to calculate fibonacci numbers", config)

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
    print("Step 2: Reviewing code...")
    result2 = run(f"Review this code for bugs:\n\n{result1.output}", config)
    
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

# Step 3: Generate tests
if result1.success and result2.success:
    print("Step 3: Generating tests...")
    result3 = run(f"Write pytest tests for this code:\n\n{result1.output}", config)
    
    append_event(
        ledger_path=config.ledger_path,
        event_type="workflow",
        data={
            "workflow_id": workflow_id,
            "stage": "step_3",
            "step_name": "generate_tests",
            "success": result3.success
        }
    )

# Mark workflow completion
all_success = result1.success and result2.success and result3.success
append_event(
    ledger_path=config.ledger_path,
    event_type="workflow",
    data={
        "workflow_id": workflow_id,
        "stage": "complete",
        "overall_success": all_success,
        "total_latency_ms": (
            result1.metrics.latency_ms +
            result2.metrics.latency_ms +
            result3.metrics.latency_ms
        )
    }
)

print(f"\nWorkflow {workflow_id} completed!")
print(f"Overall success: {all_success}")
print(f"Check {config.ledger_path} for full execution log")
