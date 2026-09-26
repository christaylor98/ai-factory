"""
Claude Code provider for ai-factory

Routes prompts through the local `claude` CLI in non-interactive mode
(`claude -p ... --output-format json`) instead of calling the Anthropic API
directly. Reuses whatever Claude Code login/subscription is already
authenticated on this machine, so calls aren't billed per-token through the
API - they ride on the existing `claude` session's plan.

Each call is a fresh, stateless `claude -p` invocation; there is no
conversation/session continuity between calls. `config.model` is passed
straight through to `claude --model` (an alias like "sonnet"/"opus"/
"haiku"/"fable", or a full model name).

Requires the `claude` CLI on PATH (or CLAUDE_CODE_CLI_PATH pointing at it)
and an already-authenticated `claude` login - this provider does not handle
login itself.
"""
import json
import os
import shutil
import subprocess
import time
from typing import Optional

from ..config import Config
from ..result import ProviderResponse, ModelInfo, RetryRecord, EmbedResult, Metrics
from .base import BaseProvider


DEFAULT_TIMEOUT_SECONDS = 300.0

# `claude --model` aliases; not a live API, so this is a fixed reference
# list rather than a real lookup.
_MODEL_ALIASES = ["fable", "opus", "sonnet", "haiku"]

# Fallback used when config.model isn't a recognized alias or a full Claude
# model id (starts with "claude-"). Callers commonly share one Config across
# providers (e.g. an MCP launcher's global AIFACTORY_MODEL default meant for
# a different provider such as "gemini-2.5-flash"); passing that straight
# through to `claude --model` fails instantly with "unrecognized_model", so
# fall back instead of blindly forwarding a foreign model name.
_DEFAULT_MODEL = "sonnet"


class ClaudeCodeProvider(BaseProvider):
    """
    Claude Code CLI provider: shells out to `claude -p` for each call.

    Tool use that would normally prompt for permission is auto-denied
    (`--permission-prompts none`) since there is no one here to answer it -
    a bare subprocess call has no TTY. Plain conversational prompts are
    unaffected.
    """

    SUPPORTS_SYSTEM = SUPPORTS_SCHEMA = True

    def __init__(self, config: Config):
        """Initialize Claude Code CLI provider."""
        super().__init__(config)

        self.claude_bin = os.environ.get("CLAUDE_CODE_CLI_PATH") or shutil.which("claude")
        if not self.claude_bin:
            raise ValueError(
                "`claude` CLI not found on PATH. Install Claude Code, or "
                "set CLAUDE_CODE_CLI_PATH to its binary."
            )

        self.timeout = float(
            os.environ.get("CLAUDE_CODE_CLI_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)
        )

        # ai_factory's own .env commonly sets ANTHROPIC_API_KEY for the
        # `anthropic` provider, and subprocess.run() inherits the parent
        # environment by default. If present, `claude` silently switches
        # from the subscription login to API-key billing (defeating the
        # point of this provider) - strip it, and other auth-source
        # overrides, so the CLI always uses its own logged-in session.
        self.subprocess_env = os.environ.copy()
        for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"):
            self.subprocess_env.pop(var, None)

    def _is_retryable(self, stderr: str) -> bool:
        """Check if a nonzero exit looks like a transient CLI/auth hiccup."""
        stderr_lower = stderr.lower()
        retryable_patterns = [
            "429", "rate limit", "overloaded", "500", "502", "503", "504",
            "timeout", "connection", "network", "econnreset",
        ]
        return any(pattern in stderr_lower for pattern in retryable_patterns)

    def call(self, prompt: str) -> ProviderResponse:
        """
        Run `prompt` through `claude -p --output-format json`.

        Args:
            prompt: Input prompt

        Returns:
            ProviderResponse. A CLI process timeout is treated as
            non-retryable (an agentic turn may still be running/side-
            effecting; resending is not safe like an idempotent HTTP
            retry). Nonzero exits that look transient are retried per
            config.max_retries / backoff.
        """
        model = self.config.model
        if model and model not in _MODEL_ALIASES and not model.startswith("claude-"):
            model = _DEFAULT_MODEL

        cmd = [self.claude_bin, "-p", prompt, "--output-format", "json", "--permission-prompts", "none"]
        if model:
            cmd += ["--model", model]
        if self.config.system_prompt:
            cmd += ["--system-prompt", self.config.system_prompt]
        if self.config.json_schema:
            cmd += ["--json-schema", json.dumps(self.config.json_schema)]

        retry_history = []
        attempts = 0

        for attempt in range(self.config.max_retries + 1):
            attempts += 1
            start = time.time()

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    env=self.subprocess_env,
                    stdin=subprocess.DEVNULL,
                )
            except subprocess.TimeoutExpired:
                return ProviderResponse(
                    text="",
                    metadata={"cmd": cmd},
                    attempts=attempts,
                    retry_history=retry_history,
                    error=f"claude -p timed out after {self.timeout:.0f}s",
                )
            except Exception as e:
                return ProviderResponse(
                    text="",
                    metadata={"cmd": cmd},
                    attempts=attempts,
                    retry_history=retry_history,
                    error=f"{type(e).__name__}: {str(e)}",
                )

            latency_ms = int((time.time() - start) * 1000)

            if proc.returncode != 0:
                stderr = proc.stderr.strip()
                if attempt < self.config.max_retries and self._is_retryable(stderr):
                    backoff_ms = int(
                        self.config.backoff_base_ms
                        * (self.config.backoff_multiplier ** attempt)
                    )
                    retry_history.append(RetryRecord(
                        attempt=attempt + 1,
                        error_type="NonZeroExit",
                        error_message=stderr[:2000] or f"exit code {proc.returncode}",
                        backoff_ms=backoff_ms,
                    ))
                    time.sleep(backoff_ms / 1000.0)
                    continue
                return ProviderResponse(
                    text="",
                    metadata={"cmd": cmd, "returncode": proc.returncode, "stderr": stderr[-4000:]},
                    attempts=attempts,
                    retry_history=retry_history,
                    error=f"claude exited {proc.returncode}: {stderr[:2000] or '(no stderr)'}",
                )

            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError as e:
                return ProviderResponse(
                    text="",
                    metadata={"cmd": cmd, "stdout": proc.stdout[-4000:]},
                    attempts=attempts,
                    retry_history=retry_history,
                    error=f"Could not parse claude output as JSON: {e}",
                )

            metadata = dict(payload)
            metadata["latency_ms"] = latency_ms
            usage = payload.get("usage") or {}
            if "input_tokens" in usage:
                metadata["prompt_tokens"] = usage["input_tokens"]
            if "output_tokens" in usage:
                metadata["completion_tokens"] = usage["output_tokens"]
            if "input_tokens" in usage and "output_tokens" in usage:
                metadata["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
            if "total_cost_usd" in payload:
                metadata["cost_usd"] = payload["total_cost_usd"]

            if payload.get("is_error"):
                return ProviderResponse(
                    text="",
                    metadata=metadata,
                    attempts=attempts,
                    retry_history=retry_history,
                    error=payload.get("result") or "claude reported is_error=true",
                )

            text = payload.get("result", "")
            if self.config.json_schema:   # the answer is the schema'd object, as a JSON string
                if payload.get("structured_output") is None:
                    return ProviderResponse(text="", metadata=metadata, attempts=attempts,
                                            retry_history=retry_history,
                                            error="claude returned no structured_output for the json_schema")
                text = json.dumps(payload["structured_output"])
            return ProviderResponse(
                text=text,
                metadata=metadata,
                attempts=attempts,
                retry_history=retry_history,
                error=None,
            )

        # Should never reach here, but just in case
        return ProviderResponse(
            text="",
            metadata={"cmd": cmd},
            attempts=attempts,
            retry_history=retry_history,
            error="Exhausted retries",
        )

    def list_models(self) -> list[ModelInfo]:
        """
        Return the known `claude --model` aliases.

        Not a live models API - the CLI doesn't expose one - just the
        documented aliases you can pass to `--model`.
        """
        return [
            ModelInfo(name=alias, metadata={"kind": "alias"})
            for alias in _MODEL_ALIASES
        ]

    def embed(self, text: str) -> EmbedResult:
        """Claude Code CLI provider does not support embedding generation."""
        metrics = Metrics(
            input_chars=len(text),
            output_chars=0,
            latency_ms=1,
            success=False,
        )
        return EmbedResult(
            vector=[],
            success=False,
            error="Claude Code CLI provider does not support embedding generation",
            metrics=metrics,
        )
