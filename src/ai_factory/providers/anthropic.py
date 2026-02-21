"""
Anthropic provider for ai-factory
"""
import os
import time
from typing import Optional

try:
    from anthropic import Anthropic
    _has_anthropic_sdk = True
except ImportError:
    _has_anthropic_sdk = False

from ..config import Config
from ..result import ProviderResponse, ModelInfo, RetryRecord
from .base import BaseProvider


class AnthropicProvider(BaseProvider):
    """
    Anthropic provider.
    
    Requires ANTHROPIC_API_KEY environment variable.
    """
    
    def __init__(self, config: Config):
        """Initialize Anthropic provider."""
        super().__init__(config)
        
        if not _has_anthropic_sdk:
            raise ImportError(
                "anthropic package not installed. "
                "Install with: pip install anthropic"
            )
        
        # Read API key from environment
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable not set. "
                "Either set it directly or add it to your .env file."
            )
        
        # Initialize Anthropic client
        self.client = Anthropic(api_key=self.api_key)
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error is retryable."""
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        # Retry on rate limit, server errors, and transient network errors
        retryable_patterns = [
            "429",
            "rate limit",
            "quota",
            "500",
            "502",
            "503",
            "504",
            "overloaded",
            "internal error",
            "timeout",
            "connection",
            "network",
        ]
        
        # Do NOT retry auth errors
        non_retryable_patterns = [
            "401",
            "403",
            "unauthorized",
            "forbidden",
            "invalid api key",
            "authentication",
        ]
        
        # Check for non-retryable errors first
        if any(pattern in error_str for pattern in non_retryable_patterns):
            return False
        
        # Check for retryable errors
        return any(pattern in error_str for pattern in retryable_patterns)
    
    def call(self, prompt: str) -> ProviderResponse:
        """
        Call Anthropic with a prompt.
        
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
            
            try:
                # Make the API call using messages API
                response = self.client.messages.create(
                    model=self.config.model,
                    max_tokens=4096,  # Required parameter for Anthropic
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                
                # Extract text from content blocks
                text = ""
                if hasattr(response, 'content') and response.content:
                    # Anthropic returns a list of content blocks
                    for block in response.content:
                        if hasattr(block, 'type') and block.type == 'text':
                            if hasattr(block, 'text'):
                                text += block.text
                
                # Extract metadata - capture full raw API response
                metadata = {}
                
                # Convert response to dict for full capture
                try:
                    if hasattr(response, 'model_dump'):
                        # Pydantic v2 style
                        metadata = response.model_dump()
                    elif hasattr(response, 'dict'):
                        # Pydantic v1 style
                        metadata = response.dict()
                    else:
                        # Fallback: extract key attributes
                        metadata = {
                            'id': getattr(response, 'id', None),
                            'model': getattr(response, 'model', None),
                            'role': getattr(response, 'role', None),
                            'stop_reason': getattr(response, 'stop_reason', None),
                            'stop_sequence': getattr(response, 'stop_sequence', None),
                            'type': getattr(response, 'type', None),
                        }
                        if hasattr(response, 'usage'):
                            usage = response.usage
                            metadata['usage'] = {
                                'input_tokens': getattr(usage, 'input_tokens', None),
                                'output_tokens': getattr(usage, 'output_tokens', None),
                            }
                        if hasattr(response, 'content'):
                            # Store content structure without duplicating text
                            metadata['content'] = [{'type': getattr(block, 'type', None)} for block in response.content]
                except Exception:
                    # If serialization fails, fallback to basic metadata
                    metadata = {'error': 'Failed to serialize full response'}
                
                # Extract key fields for backwards compatibility
                if hasattr(response, 'usage') and response.usage:
                    usage = response.usage
                    if hasattr(usage, 'input_tokens'):
                        metadata['prompt_tokens'] = usage.input_tokens
                    if hasattr(usage, 'output_tokens'):
                        metadata['completion_tokens'] = usage.output_tokens
                    if hasattr(usage, 'input_tokens') and hasattr(usage, 'output_tokens'):
                        metadata['total_tokens'] = usage.input_tokens + usage.output_tokens
                
                # Success
                return ProviderResponse(
                    text=text,
                    metadata=metadata,
                    attempts=attempts,
                    retry_history=retry_history,
                    error=None
                )
            
            except Exception as e:
                last_error = e
                error_type = type(e).__name__
                error_message = str(e)
                
                # Check if we should retry
                if attempt < self.config.max_retries and self._is_retryable_error(e):
                    # Calculate backoff
                    backoff_ms = int(
                        self.config.backoff_base_ms * 
                        (self.config.backoff_multiplier ** attempt)
                    )
                    
                    # Record retry
                    retry_history.append(RetryRecord(
                        attempt=attempt + 1,
                        error_type=error_type,
                        error_message=error_message,
                        backoff_ms=backoff_ms
                    ))
                    
                    # Sleep for backoff
                    time.sleep(backoff_ms / 1000.0)
                else:
                    # Don't retry auth errors or non-retryable errors
                    # or if we've exhausted retries
                    return ProviderResponse(
                        text="",
                        metadata={},
                        attempts=attempts,
                        retry_history=retry_history,
                        error=f"{error_type}: {error_message}"
                    )
        
        # Should never reach here, but just in case
        return ProviderResponse(
            text="",
            metadata={},
            attempts=attempts,
            retry_history=retry_history,
            error=f"{type(last_error).__name__}: {str(last_error)}" if last_error else "Unknown error"
        )
    
    def list_models(self) -> list[ModelInfo]:
        """
        List available Anthropic models.
        
        Returns:
            List of ModelInfo objects (fallback list, as Anthropic doesn't have a models API)
        """
        # Anthropic doesn't have a public models listing API
        # Return known models as fallback
        return self._get_fallback_models()
    
    def _get_fallback_models(self) -> list[ModelInfo]:
        """Return a basic set of known models as fallback."""
        return [
            ModelInfo(
                name="claude-sonnet-4",
                context_window=200000,
                metadata={"description": "Claude Sonnet 4"}
            ),
            ModelInfo(
                name="claude-haiku-4.5",
                context_window=200000,
                metadata={"description": "Claude Haiku 4.5"}
            ),
            ModelInfo(
                name="claude-3-5-sonnet-20241022",
                context_window=200000,
                metadata={"description": "Claude 3.5 Sonnet"}
            ),
            ModelInfo(
                name="claude-3-opus-20240229",
                context_window=200000,
                metadata={"description": "Claude 3 Opus"}
            ),
        ]
