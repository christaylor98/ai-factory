"""
OpenAI provider for ai-factory
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
from ..result import ProviderResponse, ModelInfo, RetryRecord, EmbedResult, Metrics
from .base import BaseProvider, chat_messages, response_format


class OpenAIProvider(BaseProvider):
    """
    OpenAI provider.
    
    Requires OPENAI_API_KEY environment variable.
    """

    SUPPORTS_SYSTEM = SUPPORTS_SCHEMA = True
    
    def __init__(self, config: Config):
        """Initialize OpenAI provider."""
        super().__init__(config)
        
        if not _has_openai_sdk:
            raise ImportError(
                "openai package not installed. "
                "Install with: pip install openai"
            )
        
        # Read API key from environment
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable not set. "
                "Either set it directly or add it to your .env file."
            )
        
        # base_url points the SDK at any OpenAI-compatible server. Dropping it
        # silently sends the call, and the bill, to api.openai.com.
        self.client = OpenAI(**self._client_kwargs(self.api_key))

    def _client_kwargs(self, api_key: str) -> dict:
        """Constructor arguments for the OpenAI client."""
        kwargs = {"api_key": api_key}
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        if self.config.timeout_s is not None:
            kwargs["timeout"] = self.config.timeout_s
        return kwargs

    def _create_kwargs(self, prompt: str) -> dict:
        """Arguments for chat.completions.create."""
        kwargs = {
            "model": self.config.model,
            "messages": chat_messages(self.config, prompt),
        }
        if response_format(self.config):
            kwargs["response_format"] = response_format(self.config)
        if self.config.temperature is not None:
            kwargs["temperature"] = self.config.temperature
        if self.config.max_tokens is not None:
            kwargs["max_tokens"] = self.config.max_tokens
        return kwargs

    def _empty_output_error(self, response, text: str) -> Optional[str]:
        """
        Why an empty answer is a failure, or None when the answer is not empty.

        An empty string with success=True reads as "the model had nothing to
        say" when the budget actually ran out.
        """
        if text:
            return None
        choice = response.choices[0] if response.choices else None
        message = getattr(choice, "message", None)
        reasoning = getattr(message, "reasoning_content", None) if message else None
        if reasoning:
            return "reasoning exhausted max_tokens"
        if getattr(choice, "finish_reason", None) == "length":
            return "output truncated at max_tokens before any content"
        return "empty response"

    def _describe_error(self, error: Exception) -> str:
        """Error text recorded for a failed call."""
        return f"{type(error).__name__}: {str(error)}"
    
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
        Call OpenAI with a prompt.
        
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
                    **self._create_kwargs(prompt)
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
                
                if response.choices and len(response.choices) > 0:
                    choice = response.choices[0]
                    if hasattr(choice, 'finish_reason') and choice.finish_reason:
                        metadata['finish_reason'] = choice.finish_reason
                
                # Usage is kept on an empty answer too: those tokens were spent.
                return ProviderResponse(
                    text=text,
                    metadata=metadata,
                    attempts=attempts,
                    retry_history=retry_history,
                    error=self._empty_output_error(response, text)
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
                        error=self._describe_error(e)
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
        List available OpenAI models.
        
        Returns:
            List of ModelInfo objects
        """
        try:
            # List models using OpenAI API
            models_response = self.client.models.list()
            
            models = []
            for model in models_response.data:
                model_info = ModelInfo(
                    name=model.id,
                    metadata={}
                )
                
                # Try to extract additional fields if available
                if hasattr(model, 'context_window'):
                    model_info.context_window = model.context_window
                
                # Add created timestamp to metadata
                if hasattr(model, 'created'):
                    model_info.metadata['created'] = model.created
                
                # Add owned_by to metadata
                if hasattr(model, 'owned_by'):
                    model_info.metadata['owned_by'] = model.owned_by
                
                models.append(model_info)
            
            return models
            
        except Exception as e:
            # If listing fails, return fallback models
            return self._get_fallback_models()
    
    def _get_fallback_models(self) -> list[ModelInfo]:
        """Return a basic set of known models as fallback."""
        return [
            ModelInfo(
                name="gpt-4o",
                context_window=128000,
                metadata={"description": "GPT-4o model"}
            ),
            ModelInfo(
                name="gpt-4o-mini",
                context_window=128000,
                metadata={"description": "GPT-4o mini model"}
            ),
            ModelInfo(
                name="gpt-4-turbo",
                context_window=128000,
                metadata={"description": "GPT-4 Turbo model"}
            ),
            ModelInfo(
                name="gpt-3.5-turbo",
                context_window=16385,
                metadata={"description": "GPT-3.5 Turbo model"}
            ),
        ]
    
    def embed(self, text: str) -> EmbedResult:
        """
        Generate embeddings using OpenAI embedding model.
        
        Uses text-embedding-3-small by default.
        
        Args:
            text: Input text to embed
            
        Returns:
            EmbedResult with vector, success, error, and metrics
        """
        start_time = time.perf_counter()
        
        try:
            # Use OpenAI embedding model
            response = self.client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            
            # Extract vector from response
            vector = response.data[0].embedding
            
            # Calculate metrics
            end_time = time.perf_counter()
            latency_ms = max(1, int((end_time - start_time) * 1000))
            
            metrics = Metrics(
                input_chars=len(text),
                output_chars=0,
                latency_ms=latency_ms,
                success=True
            )
            
            return EmbedResult(
                vector=list(vector),
                success=True,
                error=None,
                metrics=metrics
            )
        
        except Exception as e:
            # Calculate metrics for failure
            end_time = time.perf_counter()
            latency_ms = max(1, int((end_time - start_time) * 1000))
            
            metrics = Metrics(
                input_chars=len(text),
                output_chars=0,
                latency_ms=latency_ms,
                success=False
            )
            
            return EmbedResult(
                vector=[],
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                metrics=metrics
            )
