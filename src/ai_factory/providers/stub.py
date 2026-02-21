"""
Stub provider for testing and demonstration
"""
import time
from ..config import Config
from ..result import ProviderResponse, ModelInfo, RetryRecord
from .base import BaseProvider


class StubProvider(BaseProvider):
    """
    Stub provider for testing.
    
    Behavior:
    - Normal prompts: echo with "STUB: " prefix
    - Prompts containing "__FAIL__": fail all attempts
    - Prompts containing "__FLAKE__": fail first attempt, succeed on retry
    """
    
    def call(self, prompt: str) -> ProviderResponse:
        """
        Call stub provider with retry logic.
        
        Args:
            prompt: Input prompt
            
        Returns:
            ProviderResponse
        """
        retry_history = []
        attempts = 0
        
        # Determine behavior based on prompt content
        should_always_fail = "__FAIL__" in prompt
        should_flake = "__FLAKE__" in prompt
        
        for attempt in range(self.config.max_retries + 1):
            attempts += 1
            
            # Simulate failure conditions
            should_fail_this_attempt = False
            if should_always_fail:
                should_fail_this_attempt = True
            elif should_flake and attempt == 0:
                should_fail_this_attempt = True
            
            if should_fail_this_attempt:
                error_type = "SimulatedError"
                error_message = "Simulated transient failure"
                
                # If this is not the last attempt, record retry and backoff
                if attempt < self.config.max_retries:
                    backoff_ms = int(
                        self.config.backoff_base_ms * 
                        (self.config.backoff_multiplier ** attempt)
                    )
                    retry_history.append(RetryRecord(
                        attempt=attempt + 1,
                        error_type=error_type,
                        error_message=error_message,
                        backoff_ms=backoff_ms
                    ))
                    # Simulate backoff sleep
                    time.sleep(backoff_ms / 1000.0)
                else:
                    # Final attempt failed
                    return ProviderResponse(
                        text="",
                        metadata={"stub": True},
                        attempts=attempts,
                        retry_history=retry_history,
                        error=f"{error_type}: {error_message}"
                    )
            else:
                # Success
                response_text = f"STUB: {prompt}"
                return ProviderResponse(
                    text=response_text,
                    metadata={"stub": True},
                    attempts=attempts,
                    retry_history=retry_history,
                    error=None
                )
        
        # Should never reach here
        return ProviderResponse(
            text="",
            metadata={"stub": True},
            attempts=attempts,
            retry_history=retry_history,
            error="Unexpected error: exhausted retries"
        )
    
    def list_models(self) -> list[ModelInfo]:
        """
        List stub models.
        
        Returns:
            List of two stub models
        """
        return [
            ModelInfo(
                name="stub-1",
                context_window=8192,
                input_cost_per_1k=0.001,
                output_cost_per_1k=0.002,
                metadata={"description": "First stub model"}
            ),
            ModelInfo(
                name="stub-2",
                context_window=16384,
                input_cost_per_1k=0.002,
                output_cost_per_1k=0.004,
                metadata={"description": "Second stub model"}
            ),
        ]
