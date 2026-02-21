"""
Ledger writing for ai-factory

Supports two ledger formats:
- IS (Indented S-expressions) - default, append-only
- JSON Lines (JSONL) - one JSON object per line

Ledger format is selected based on Config.ledger_format.
Ledger failures must NOT fail the run.
"""
import os
import json
from datetime import datetime
from typing import Optional, Protocol
from .config import Config
from .result import ProviderResponse, Metrics


def _truncate_with_metadata(
    text: str, 
    limit: int
) -> tuple[str, bool, int]:
    """
    Truncate text to limit if needed.
    
    Returns:
        (truncated_text, was_truncated, original_length)
    """
    original_length = len(text)
    if original_length > limit:
        return (text[:limit], True, original_length)
    return (text, False, original_length)


def _escape_is_string(s: str) -> str:
    """
    Escape a string for IS format.
    
    Always quote strings to ensure consistent parsing.
    Escape quotes and backslashes inside quoted strings.
    """
    escaped = s.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def _format_retry_records(retry_history: list) -> str:
    """Format retry history as IS format."""
    if not retry_history:
        return ""
    
    lines = []
    for record in retry_history:
        lines.append(
            f'    (retry '
            f'(attempt {record.attempt}) '
            f'(error_type {_escape_is_string(record.error_type)}) '
            f'(error_message {_escape_is_string(record.error_message)}) '
            f'(backoff_ms {record.backoff_ms}))'
        )
    return "\n".join(lines)


class LedgerSerializer(Protocol):
    """Protocol for ledger serializers."""
    
    def serialize(
        self,
        config: Config,
        prompt: str,
        response: ProviderResponse,
        metrics: Metrics,
        success: bool,
        prompt_text: str,
        prompt_truncated: bool,
        prompt_original_length: int,
        output_text: str,
        output_truncated: bool,
        output_original_length: int,
    ) -> str:
        """Serialize a run entry to string format."""
        ...


class ISSerializer:
    """IS (Indented S-expressions) ledger serializer."""
    
    def serialize(
        self,
        config: Config,
        prompt: str,
        response: ProviderResponse,
        metrics: Metrics,
        success: bool,
        prompt_text: str,
        prompt_truncated: bool,
        prompt_original_length: int,
        output_text: str,
        output_truncated: bool,
        output_original_length: int,
    ) -> str:
        """Serialize run entry to IS format."""
        timestamp = datetime.utcnow().isoformat() + "Z"
        lines = [
            "(run",
            f"  (timestamp {_escape_is_string(timestamp)})",
            f"  (provider {_escape_is_string(config.provider)})",
            f"  (model {_escape_is_string(config.model)})",
            f"  (success {str(success).lower()})",
            f"  (attempts {response.attempts})",
        ]
        
        if config.capture_prompt:
            lines.append(f"  (prompt {_escape_is_string(prompt_text)})")
            if prompt_truncated:
                lines.append(f"  (prompt_truncated true)")
                lines.append(f"  (prompt_original_length {prompt_original_length})")
        
        if config.capture_output:
            lines.append(f"  (output {_escape_is_string(output_text)})")
            if output_truncated:
                lines.append(f"  (output_truncated true)")
                lines.append(f"  (output_original_length {output_original_length})")
        
        lines.append("  (metrics")
        lines.append(f"    (input_chars {metrics.input_chars})")
        lines.append(f"    (output_chars {metrics.output_chars})")
        lines.append(f"    (latency_ms {metrics.latency_ms})")
        if metrics.prompt_tokens is not None:
            lines.append(f"    (prompt_tokens {metrics.prompt_tokens})")
        if metrics.completion_tokens is not None:
            lines.append(f"    (completion_tokens {metrics.completion_tokens})")
        if metrics.total_tokens is not None:
            lines.append(f"    (total_tokens {metrics.total_tokens})")
        if metrics.cost_usd is not None:
            lines.append(f"    (cost_usd {metrics.cost_usd})")
        if metrics.finish_reason is not None:
            lines.append(f"    (finish_reason {_escape_is_string(metrics.finish_reason)})")
        if metrics.provider_metadata is not None:
            try:
                metadata_json = json.dumps(metrics.provider_metadata, indent=None)
                lines.append(f"    (provider_metadata {_escape_is_string(metadata_json)})")
            except Exception:
                pass
        lines.append("  )")
        
        if response.retry_history:
            lines.append("  (retries")
            lines.append(_format_retry_records(response.retry_history))
            lines.append("  )")
        
        if response.error:
            lines.append(f"  (error {_escape_is_string(response.error)})")
        
        lines.append(")")
        return "\n".join(lines)


class JSONSerializer:
    """JSON Lines ledger serializer."""
    
    def serialize(
        self,
        config: Config,
        prompt: str,
        response: ProviderResponse,
        metrics: Metrics,
        success: bool,
        prompt_text: str,
        prompt_truncated: bool,
        prompt_original_length: int,
        output_text: str,
        output_truncated: bool,
        output_original_length: int,
    ) -> str:
        """Serialize run entry to JSON Lines format."""
        timestamp = datetime.utcnow().isoformat() + "Z"
        entry = {
            "timestamp": timestamp,
            "provider": config.provider,
            "model": config.model,
            "success": success,
            "attempts": response.attempts,
        }
        
        if config.capture_prompt:
            entry["prompt"] = prompt_text
            if prompt_truncated:
                entry["prompt_truncated"] = True
                entry["prompt_original_length"] = prompt_original_length
        
        if config.capture_output:
            entry["output"] = output_text
            if output_truncated:
                entry["output_truncated"] = True
                entry["output_original_length"] = output_original_length
        
        entry["metrics"] = {
            "input_chars": metrics.input_chars,
            "output_chars": metrics.output_chars,
            "latency_ms": metrics.latency_ms,
        }
        if metrics.prompt_tokens is not None:
            entry["metrics"]["prompt_tokens"] = metrics.prompt_tokens
        if metrics.completion_tokens is not None:
            entry["metrics"]["completion_tokens"] = metrics.completion_tokens
        if metrics.total_tokens is not None:
            entry["metrics"]["total_tokens"] = metrics.total_tokens
        if metrics.cost_usd is not None:
            entry["metrics"]["cost_usd"] = metrics.cost_usd
        if metrics.finish_reason is not None:
            entry["metrics"]["finish_reason"] = metrics.finish_reason
        if metrics.provider_metadata is not None:
            entry["metrics"]["provider_metadata"] = metrics.provider_metadata
        
        if response.retry_history:
            entry["retry_history"] = [
                {
                    "attempt": r.attempt,
                    "error_type": r.error_type,
                    "error_message": r.error_message,
                    "backoff_ms": r.backoff_ms,
                }
                for r in response.retry_history
            ]
        
        if response.error:
            entry["error"] = response.error
        
        return json.dumps(entry, ensure_ascii=False)


def write_run_to_ledger(
    config: Config,
    prompt: str,
    response: ProviderResponse,
    metrics: Metrics,
    success: bool
) -> None:
    """
    Write a run entry to the ledger.
    Ledger failures are logged but do not raise exceptions.
    """
    if not config.ledger_enabled:
        return
    
    try:
        prompt_text = ""
        prompt_truncated = False
        prompt_original_length = 0
        if config.capture_prompt:
            prompt_text, prompt_truncated, prompt_original_length = _truncate_with_metadata(
                prompt, config.capture_limit_chars
            )
        
        output_text = ""
        output_truncated = False
        output_original_length = 0
        if config.capture_output:
            output_text, output_truncated, output_original_length = _truncate_with_metadata(
                response.text, config.capture_limit_chars
            )
        
        serializer = JSONSerializer() if config.ledger_format == "json" else ISSerializer()
        ledger_entry = serializer.serialize(
            config=config,
            prompt=prompt,
            response=response,
            metrics=metrics,
            success=success,
            prompt_text=prompt_text,
            prompt_truncated=prompt_truncated,
            prompt_original_length=prompt_original_length,
            output_text=output_text,
            output_truncated=output_truncated,
            output_original_length=output_original_length,
        )
        
        with open(config.ledger_path, "a", encoding="utf-8") as f:
            f.write(ledger_entry)
            f.write("\n")
    
    except Exception as e:
        print(f"Warning: Failed to write to ledger: {e}", flush=True)


def append_event(
    ledger_path: str,
    event_type: str,
    data: dict,
    ledger_format: str = "is"
) -> None:
    """
    Append a custom event to the ledger.
    
    This function allows external scripts to write custom events to the AI Factory ledger.
    Failures are logged but do not raise exceptions.
    
    Args:
        ledger_path: Path to the ledger file
        event_type: Type of event (e.g., "workflow", "custom", "checkpoint")
        data: Dictionary containing event data
        ledger_format: Format of the ledger ("is" or "json", default: "is")
    
    Example:
        ```python
        from ai_factory import append_event
        
        append_event(
            ledger_path="./LEDGER.is",
            event_type="workflow",
            data={
                "role": "coder",
                "run_id": "abc123",
                "step_id": 4,
                "step_size": "small",
                "status": "completed"
            }
        )
        ```
    """
    try:
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        if ledger_format == "json":
            # JSON Lines format
            entry = {
                "timestamp": timestamp,
                "event_type": event_type,
                **data
            }
            ledger_entry = json.dumps(entry, ensure_ascii=False)
        else:
            # IS format (default)
            lines = [f"({event_type}"]
            lines.append(f'  (timestamp {_escape_is_string(timestamp)})')
            
            # Add all data fields
            for key, value in data.items():
                if isinstance(value, bool):
                    lines.append(f"  ({key} {str(value).lower()})")
                elif isinstance(value, (int, float)):
                    lines.append(f"  ({key} {value})")
                elif isinstance(value, str):
                    lines.append(f"  ({key} {_escape_is_string(value)})")
                elif isinstance(value, (list, dict)):
                    # Serialize complex types as JSON
                    json_str = json.dumps(value, ensure_ascii=False)
                    lines.append(f"  ({key} {_escape_is_string(json_str)})")
                else:
                    # Convert to string for other types
                    lines.append(f"  ({key} {_escape_is_string(str(value))})")
            
            lines.append(")")
            ledger_entry = "\n".join(lines)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(ledger_path)), exist_ok=True)
        
        # Append to ledger
        with open(ledger_path, "a", encoding="utf-8") as f:
            f.write(ledger_entry)
            f.write("\n")
    
    except Exception as e:
        print(f"Warning: Failed to append event to ledger: {e}", flush=True)
