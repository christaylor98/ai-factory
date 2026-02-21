"""
OpenRouter provider for ai-factory

Uses OpenRouter's OpenAI-compatible API.
"""
import os
import time
from typing import Optional

try:
    from openai import OpenAI
    _has_openai_sdk = True
except ImportError:
    _has_openai_sdk = False

from ..config import Config
from ..result import ProviderResponse, ModelInfo, RetryRecord
from .base import BaseProvider


class OpenRouterProvider(BaseProvider):
    """
    OpenRouter provider using OpenAI-compatible API.
    
    Requires OPENROUTER_API_KEY environment variable.
    Optional: OPENROUTER_HTTP_REFERER, OPENROUTER_X_TITLE for identification.
    """
    
    def __init__(self, config: Config):
        """Initialize OpenRouter provider."""
        super().__init__(config)
        
        if not _has_openai_sdk:
            raise ImportError(
                "openai package not installed. "
                "Install with: pip install openai"
            )
        
        # Read API key from environment
        self.api_key = os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable not set. "
                "Either set it directly or add it to your .env file."
            )
        
        # Read optional headers
        self.http_referer = os.environ.get("OPENROUTER_HTTP_REFERER")
        self.x_title = os.environ.get("OPENROUTER_X_TITLE")
        
        # Build extra headers dict
        extra_headers = {}
        if self.http_referer:
            extra_headers["HTTP-Referer"] = self.http_referer
        if self.x_title:
            extra_headers["X-Title"] = self.x_title
        
        # Initialize OpenAI client with OpenRouter base URL
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers=extra_headers if extra_headers else None
        )
    
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
        Call OpenRouter with a prompt.
        
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
                # Make the API call
                response = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                
                # Extract text from first choice
                text = ""
                if response.choices and len(response.choices) > 0:
                    message = response.choices[0].message
                    if message and message.content:
                        text = message.content
                
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
                        # Fallback to dict conversion
                        metadata = dict(response)
                except Exception:
                    # If serialization fails, fallback to basic metadata
                    metadata = {'error': 'Failed to serialize full response'}
                
                # Extract key fields for backwards compatibility
                if hasattr(response, 'usage') and response.usage:
                    usage = response.usage
                    if hasattr(usage, 'prompt_tokens'):
                        metadata['prompt_tokens'] = usage.prompt_tokens
                    if hasattr(usage, 'completion_tokens'):
                        metadata['completion_tokens'] = usage.completion_tokens
                    if hasattr(usage, 'total_tokens'):
                        metadata['total_tokens'] = usage.total_tokens
                
                # Add finish reason if available
                if response.choices and len(response.choices) > 0:
                    choice = response.choices[0]
                    if hasattr(choice, 'finish_reason') and choice.finish_reason:
                        metadata['finish_reason'] = choice.finish_reason
                
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
        List available OpenRouter models.
        
        Returns:
            List of ModelInfo objects
            
        Raises:
            NotImplementedError: OpenRouter models endpoint requires different approach
        """
        try:
            # Try to list models using OpenRouter's models endpoint
            # Note: This may require different API structure than OpenAI
            models_response = self.client.models.list()
            
            models = []
            for model in models_response.data:
                model_info = ModelInfo(
                    name=model.id,
                    metadata={}
                )
                
                # Try to extract additional fields if available
                if hasattr(model, 'context_length'):
                    model_info.context_window = model.context_length
                
                # Add raw model data to metadata
                if hasattr(model, 'model_dump'):
                    model_info.metadata = model.model_dump()
                elif hasattr(model, 'dict'):
                    model_info.metadata = model.dict()
                
                models.append(model_info)
            
            return models
            
        except Exception as e:
            # If models listing isn't supported or fails, raise NotImplementedError
            raise NotImplementedError(
                f"Model listing not supported for OpenRouter: {str(e)}"
            )
