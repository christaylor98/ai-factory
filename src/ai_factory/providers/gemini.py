"""
Gemini provider for ai-factory
"""
import os
import time
from typing import Optional

try:
    # Try new google.genai package first
    import google.genai as genai
    _using_new_sdk = True
except ImportError:
    try:
        # Fall back to legacy google.generativeai
        import google.generativeai as genai
        _using_new_sdk = False
    except ImportError:
        genai = None
        _using_new_sdk = None

from ..config import Config
from ..result import ProviderResponse, ModelInfo, RetryRecord, EmbedResult, Metrics
from .base import BaseProvider


class GeminiProvider(BaseProvider):
    """
    Google Gemini provider.
    
    Requires GEMINI_API_KEY environment variable.
    """
    
    def __init__(self, config: Config):
        """Initialize Gemini provider."""
        super().__init__(config)
        
        if genai is None:
            raise ImportError(
                "google-genai or google-generativeai package not installed. "
                "Install with: pip install google-genai"
            )
        
        # Read API key from environment
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable not set. "
                "Either set it directly or add it to your .env file."
            )
        
        # Configure SDK based on which version we have
        if _using_new_sdk:
            # New google.genai SDK
            self.client = genai.Client(api_key=self.api_key)
            # New SDK requires models/ prefix
            if not config.model.startswith('models/'):
                self.model_name = f'models/{config.model}'
            else:
                self.model_name = config.model
        else:
            # Legacy google.generativeai SDK
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(config.model)
            self.model_name = None
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error is retryable."""
        error_str = str(error).lower()
        
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
        
        return any(pattern in error_str for pattern in retryable_patterns)
    
    def call(self, prompt: str) -> ProviderResponse:
        """
        Call Gemini with a prompt.
        
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
                if _using_new_sdk:
                    # New SDK
                    response = self.client.models.generate_content(
                        model=self.model_name,
                        contents=prompt
                    )
                else:
                    # Legacy SDK
                    response = self.model.generate_content(prompt)
                
                # Extract text
                text = response.text if hasattr(response, 'text') else ""
                
                # Extract metadata - capture full raw API response
                metadata = {}
                
                # Convert response to dict for full capture
                try:
                    # Gemini response objects may have to_dict or similar
                    if hasattr(response, 'to_dict'):
                        metadata = response.to_dict()
                    elif hasattr(response, '__dict__'):
                        # Fallback: serialize all attributes
                        raw_dict = {}
                        for key, value in response.__dict__.items():
                            if not key.startswith('_'):
                                try:
                                    # Try to serialize value
                                    if hasattr(value, 'to_dict'):
                                        raw_dict[key] = value.to_dict()
                                    elif hasattr(value, '__dict__'):
                                        raw_dict[key] = str(value)
                                    else:
                                        raw_dict[key] = value
                                except:
                                    raw_dict[key] = str(value)
                        metadata = raw_dict
                except Exception:
                    metadata = {'error': 'Failed to serialize full response'}
                
                # Extract key fields for backwards compatibility
                if hasattr(response, 'usage_metadata'):
                    usage = response.usage_metadata
                    if hasattr(usage, 'prompt_token_count'):
                        metadata['prompt_tokens'] = usage.prompt_token_count
                    if hasattr(usage, 'candidates_token_count'):
                        metadata['completion_tokens'] = usage.candidates_token_count
                    if hasattr(usage, 'total_token_count'):
                        metadata['total_tokens'] = usage.total_token_count
                
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'finish_reason'):
                        metadata['finish_reason'] = str(candidate.finish_reason)
                
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
        List available Gemini models.
        
        Returns:
            List of ModelInfo objects
        """
        try:
            models = []
            
            # List models from SDK
            if _using_new_sdk:
                # New SDK - list models
                for model in self.client.models.list():
                    models.append(ModelInfo(
                        name=model.name.replace('models/', ''),
                        context_window=getattr(model, 'input_token_limit', None),
                        metadata={
                            'display_name': getattr(model, 'display_name', ''),
                            'description': getattr(model, 'description', ''),
                        }
                    ))
            else:
                # Legacy SDK
                for model in genai.list_models():
                    # Only include generative models
                    if 'generateContent' in model.supported_generation_methods:
                        models.append(ModelInfo(
                            name=model.name.replace('models/', ''),
                            context_window=getattr(model, 'input_token_limit', None),
                            metadata={
                                'display_name': getattr(model, 'display_name', ''),
                                'description': getattr(model, 'description', ''),
                            }
                        ))
            
            return models if models else self._get_fallback_models()
        
        except Exception as e:
            # If model listing fails, return fallback models
            return self._get_fallback_models()
    
    def _get_fallback_models(self) -> list[ModelInfo]:
        """Return a basic set of known models as fallback."""
        return [
            ModelInfo(
                name="gemini-1.5-pro",
                context_window=1048576,
                metadata={"description": "Gemini 1.5 Pro model"}
            ),
            ModelInfo(
                name="gemini-1.5-flash",
                context_window=1048576,
                metadata={"description": "Gemini 1.5 Flash model"}
            ),
            ModelInfo(
                name="gemini-pro",
                context_window=30720,
                metadata={"description": "Gemini Pro model"}
            ),
        ]
    
    def embed(self, text: str) -> EmbedResult:
        """
        Generate embeddings using Gemini embedding model.
        
        Uses the configured model from Config. Currently available:
        - gemini-embedding-001 (3072-dimensional embeddings)
        
        Args:
            text: Input text to embed
            
        Returns:
            EmbedResult with vector, success, error, and metrics
        """
        start_time = time.perf_counter()
        
        try:
            # Use configured embedding model
            # For new SDK, self.model_name already has "models/" prefix
            # For legacy SDK, construct from config.model
            if _using_new_sdk:
                if hasattr(self, 'model_name') and self.model_name:
                    embedding_model = self.model_name
                else:
                    # Fallback: construct from config
                    cfg_model = self.config.model
                    embedding_model = cfg_model if cfg_model.startswith('models/') else f'models/{cfg_model}'
            else:
                # Legacy SDK
                cfg_model = self.config.model
                embedding_model = cfg_model if cfg_model.startswith('models/') else f'models/{cfg_model}'
            
            # Call embedding API
            if _using_new_sdk:
                # New SDK
                response = self.client.models.embed_content(
                    model=embedding_model,
                    contents=text
                )
                # Extract embedding from response
                # New SDK returns embeddings (plural) array
                if hasattr(response, 'embeddings') and response.embeddings:
                    vector = response.embeddings[0].values
                elif hasattr(response, 'embedding'):
                    vector = response.embedding.values
                else:
                    raise ValueError(f"Unexpected response structure: {dir(response)}")
            else:
                # Legacy SDK
                result = genai.embed_content(
                    model=embedding_model,
                    content=text
                )
                vector = result['embedding']
            
            # Calculate metrics
            end_time = time.perf_counter()
            latency_ms = max(1, int((end_time - start_time) * 1000))
            
            metrics = Metrics(
                input_chars=len(text),
                output_chars=0,  # Embeddings don't produce text output
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
