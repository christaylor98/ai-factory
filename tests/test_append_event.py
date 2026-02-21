"""Tests for append_event function."""
import os
import tempfile
import json
from ai_factory import append_event


def test_append_event_is_format():
    """Test appending event in IS format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.is")
        
        append_event(
            ledger_path=ledger_path,
            event_type="workflow",
            data={
                "role": "coder",
                "run_id": "test-123",
                "step_id": 4,
                "step_size": "small",
                "status": "completed"
            }
        )
        
        # Verify file exists and has content
        assert os.path.exists(ledger_path)
        
        with open(ledger_path, "r") as f:
            content = f.read()
        
        assert "(workflow" in content
        assert "(role" in content
        assert '"coder"' in content
        assert "(step_id 4)" in content
        assert "(status" in content
        assert '"completed"' in content


def test_append_event_json_format():
    """Test appending event in JSON format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.jsonl")
        
        append_event(
            ledger_path=ledger_path,
            event_type="workflow",
            data={
                "role": "coder",
                "run_id": "test-123",
                "step_id": 4,
                "step_size": "small",
                "status": "completed"
            },
            ledger_format="json"
        )
        
        # Verify file exists and has content
        assert os.path.exists(ledger_path)
        
        with open(ledger_path, "r") as f:
            line = f.readline()
        
        entry = json.loads(line)
        assert entry["event_type"] == "workflow"
        assert entry["role"] == "coder"
        assert entry["run_id"] == "test-123"
        assert entry["step_id"] == 4
        assert entry["step_size"] == "small"
        assert entry["status"] == "completed"
        assert "timestamp" in entry


def test_append_event_complex_data():
    """Test appending event with complex data types."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.is")
        
        append_event(
            ledger_path=ledger_path,
            event_type="custom",
            data={
                "boolean_field": True,
                "int_field": 42,
                "float_field": 3.14,
                "string_field": "hello world",
                "list_field": [1, 2, 3],
                "dict_field": {"nested": "value"}
            }
        )
        
        # Verify file exists and has content
        assert os.path.exists(ledger_path)
        
        with open(ledger_path, "r") as f:
            content = f.read()
        
        assert "(custom" in content
        assert "(boolean_field true)" in content
        assert "(int_field 42)" in content
        assert "(float_field 3.14)" in content
        assert "(string_field" in content
        assert "hello world" in content


def test_append_event_multiple_entries():
    """Test appending multiple events to the same ledger."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "test.is")
        
        # Append first event
        append_event(
            ledger_path=ledger_path,
            event_type="workflow",
            data={"step": 1, "status": "started"}
        )
        
        # Append second event
        append_event(
            ledger_path=ledger_path,
            event_type="workflow",
            data={"step": 2, "status": "completed"}
        )
        
        # Verify both entries exist
        with open(ledger_path, "r") as f:
            content = f.read()
        
        assert content.count("(workflow") == 2
        assert "(step 1)" in content
        assert "(step 2)" in content


def test_append_event_creates_directory():
    """Test that append_event creates parent directory if needed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = os.path.join(tmpdir, "subdir", "nested", "test.is")
        
        append_event(
            ledger_path=ledger_path,
            event_type="test",
            data={"message": "hello"}
        )
        
        # Verify directory was created
        assert os.path.exists(os.path.dirname(ledger_path))
        assert os.path.exists(ledger_path)
