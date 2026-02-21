"""
GitHub Copilot CLI provider for ai-factory

Executes the copilot CLI in non-interactive mode via subprocess.
"""
import os
import shutil
import subprocess
import time
from typing import Optional

from ..config import Config
from ..result import ProviderResponse, ModelInfo, RetryRecord
from .base import BaseProvider


class CopilotCLIProvider(BaseProvider):
    """
    GitHub Copilot CLI provider.
    
    Executes 'copilot -p "<prompt>" --yolo --silent' to get responses.
    Requires the copilot CLI to be installed and authenticated.
    """
    
    def __init__(self, config: Config):
        """Initialize Copilot CLI provider."""
        super().__init__(config)
        
        # Check if copilot CLI is available
        self.copilot_path = shutil.which("copilot")
        if not self.copilot_path:
            raise ValueError(
                "GitHub Copilot CLI not found. "
                "Install it from: https://github.com/github/copilot-cli "
                "and ensure it's in your PATH."
            )
        
        # Set default timeout (60 seconds, configurable via environment)
        self.timeout = int(os.environ.get("COPILOT_TIMEOUT", "60"))
    
    def _is_retryable_error(self, exit_code: int, stderr: str) -> bool:
        """
        Check if an error is retryable.
        
        Args:
            exit_code: Process exit code
            stderr: Standard error output
            
        Returns:
            True if error is retryable, False otherwise
        """
        # Don't retry if binary not found (shouldn't happen after __init__)
        if exit_code == 127:
            return False
        
        # Check stderr for retryable patterns
        stderr_lower = stderr.lower()
        
        # Non-retryable patterns (auth, config errors)
        non_retryable_patterns = [
            "not authenticated",
            "authentication failed",
            "invalid token",
            "unauthorized",
            "forbidden",
            "not found",
            "command not found",
        ]
        
        if any(pattern in stderr_lower for pattern in non_retryable_patterns):
            return False
        
        # Retryable patterns (network, rate limit, server errors)
        retryable_patterns = [
            "timeout",
            "timed out",
            "connection",
            "network",
            "rate limit",
            "429",
            "500",
            "502",
            "503",
            "504",
            "internal error",
            "service unavailable",
            "bad gateway",
        ]
        
        # Any non-zero exit code with retryable patterns in stderr
        if any(pattern in stderr_lower for pattern in retryable_patterns):
            return True
        
        # For other non-zero exit codes, be conservative and don't retry
        return False
    
    def call(self, prompt: str) -> ProviderResponse:
        """
        Call Copilot CLI with a prompt.
        
        Args:
            prompt: Input prompt
            
        Returns:
            ProviderResponse with mechanical retry logic
        """
        retry_history = []
        attempts = 0
        last_error = None
        
        for attempt in range(self.config.max_retries + 1):
            attempts += 1
            start_time = time.time()
            
            try:
                # Build command
                # Use --yolo for all permissions, --silent for clean output
                cmd = [
                    self.copilot_path,
                    "-p", prompt,
                    "--yolo",
                    "--silent",
                ]
                
                # Add model if specified and not "default"
                if self.config.model and self.config.model != "default":
                    cmd.extend(["--model", self.config.model])
                
                # Execute subprocess
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False,  # Don't raise on non-zero exit
                )
                
                runtime_ms = int((time.time() - start_time) * 1000)
                
                # Check exit code
                if result.returncode == 0:
                    # Success
                    output_text = result.stdout.strip()
                    return ProviderResponse(
                        text=output_text,
                        metadata={
                            "exit_code": result.returncode,
                            "runtime_ms": runtime_ms,
                        },
                        attempts=attempts,
                        retry_history=retry_history,
                        error=None,
                    )
                else:
                    # Non-zero exit code
                    stderr = result.stderr.strip()
                    error_message = stderr if stderr else f"Exit code {result.returncode}"
                    
                    # Check if retryable
                    is_retryable = self._is_retryable_error(result.returncode, stderr)
                    
                    if is_retryable and attempt < self.config.max_retries:
                        # Retry with backoff
                        backoff_ms = int(
                            self.config.backoff_base_ms *
                            (self.config.backoff_multiplier ** attempt)
                        )
                        retry_history.append(RetryRecord(
                            attempt=attempt + 1,
                            error_type=f"ExitCode{result.returncode}",
                            error_message=error_message,
                            backoff_ms=backoff_ms,
                        ))
                        time.sleep(backoff_ms / 1000.0)
                        continue
                    else:
                        # Final failure (non-retryable or exhausted retries)
                        return ProviderResponse(
                            text="",
                            metadata={
                                "exit_code": result.returncode,
                                "runtime_ms": runtime_ms,
                            },
                            attempts=attempts,
                            retry_history=retry_history,
                            error=f"CopilotCLIError: {error_message}",
                        )
            
            except subprocess.TimeoutExpired:
                # Timeout occurred
                runtime_ms = int((time.time() - start_time) * 1000)
                error_message = f"Command timed out after {self.timeout}s"
                
                if attempt < self.config.max_retries:
                    # Retry with backoff
                    backoff_ms = int(
                        self.config.backoff_base_ms *
                        (self.config.backoff_multiplier ** attempt)
                    )
                    retry_history.append(RetryRecord(
                        attempt=attempt + 1,
                        error_type="TimeoutError",
                        error_message=error_message,
                        backoff_ms=backoff_ms,
                    ))
                    time.sleep(backoff_ms / 1000.0)
                    continue
                else:
                    # Final timeout failure
                    return ProviderResponse(
                        text="",
                        metadata={
                            "runtime_ms": runtime_ms,
                            "timeout": self.timeout,
                        },
                        attempts=attempts,
                        retry_history=retry_history,
                        error=f"TimeoutError: {error_message}",
                    )
            
            except Exception as e:
                # Unexpected error
                runtime_ms = int((time.time() - start_time) * 1000)
                error_type = type(e).__name__
                error_message = str(e)
                
                # Don't retry unexpected errors
                return ProviderResponse(
                    text="",
                    metadata={
                        "runtime_ms": runtime_ms,
                    },
                    attempts=attempts,
                    retry_history=retry_history,
                    error=f"{error_type}: {error_message}",
                )
        
        # Should never reach here
        return ProviderResponse(
            text="",
            metadata={},
            attempts=attempts,
            retry_history=retry_history,
            error="Unexpected error: exhausted retries",
        )
    
    def list_models(self) -> list[ModelInfo]:
        """
        List available models.
        
        The Copilot CLI does not support programmatic model listing.
        See available models in the --help output.
        
        Raises:
            NotImplementedError: Model listing not supported
        """
        raise NotImplementedError(
            "Copilot CLI does not support programmatic model listing. "
            "Available models: claude-sonnet-4.5, claude-haiku-4.5, "
            "gpt-5.2-codex, gpt-5.2, gpt-5.1, gpt-5, gpt-5-mini, gpt-4.1, etc. "
            "Use --model flag or see 'copilot --help' for full list."
        )
