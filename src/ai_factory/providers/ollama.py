"""
Ollama provider for ai-factory

Ollama is a local LLM provider that runs models on your machine.
No API key required - just a running Ollama server.
"""
import json
import time
import urllib.request
import urllib.error

from ..config import Config
from ..result import ProviderResponse, ModelInfo, RetryRecord, EmbedResult, Metrics
from .base import BaseProvider


class OllamaProvider(BaseProvider):
    """
    Ollama provider for local LLM inference.
    
    Requires Ollama to be running locally (default: http://localhost:11434)
    Start with: ollama serve
    """
    
    def __init__(self, config: Config):
        """Initialize Ollama provider."""
        super().__init__(config)
        
        # Set base_url from config or use default
        self.base_url = config.base_url if hasattr(config, 'base_url') and config.base_url else "http://localhost:11434"
        
        # Ensure base_url doesn't have trailing slash
        self.base_url = self.base_url.rstrip('/')
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error is retryable."""
        error_str = str(error).lower()
        
        # Retry on connection errors and transient failures
        retryable_patterns = [
            "connection refused",
            "connection reset",
            "timeout",
            "temporary failure",
            "503",
            "504",
        ]
        
        # Do NOT retry on:
        # - Model not found (404)
        # - Bad request (400)
        # - Ollama not running (connection refused on first try is not retryable)
        non_retryable_patterns = [
            "404",
            "400",
            "model",
            "not found",
        ]
        
        # Check for non-retryable errors first
        if any(pattern in error_str for pattern in non_retryable_patterns):
            return False
        
        # Check for retryable errors
        return any(pattern in error_str for pattern in retryable_patterns)
    
    def call(self, prompt: str) -> ProviderResponse:
        """
        Call Ollama with a prompt.
        
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
                # Prepare request
                url = f"{self.base_url}/api/generate"
                data = {
                    "model": self.config.model,
                    "prompt": prompt,
                    "stream": False  # MUST be false as per spec
                }
                
                # Make the API call
                req = urllib.request.Request(
                    url,
                    data=json.dumps(data).encode('utf-8'),
                    headers={'Content-Type': 'application/json'}
                )
                
                with urllib.request.urlopen(req, timeout=300) as response:
                    response_data = json.loads(response.read().decode('utf-8'))
                
                # Extract text from response
                text = response_data.get('response', '')
                
                # Extract metadata
                metadata = {
                    'model': response_data.get('model', self.config.model),
                    'created_at': response_data.get('created_at'),
                    'done': response_data.get('done', True),
                }
                
                # Extract token counts if available
                if 'prompt_eval_count' in response_data:
                    metadata['prompt_tokens'] = response_data['prompt_eval_count']
                
                if 'eval_count' in response_data:
                    metadata['completion_tokens'] = response_data['eval_count']
                
                if 'prompt_tokens' in metadata and 'completion_tokens' in metadata:
                    metadata['total_tokens'] = metadata['prompt_tokens'] + metadata['completion_tokens']
                
                # Extract timing information (in nanoseconds, convert to ms)
                if 'total_duration' in response_data:
                    metadata['total_duration_ms'] = response_data['total_duration'] / 1_000_000
                
                if 'load_duration' in response_data:
                    metadata['load_duration_ms'] = response_data['load_duration'] / 1_000_000
                
                if 'prompt_eval_duration' in response_data:
                    metadata['prompt_eval_duration_ms'] = response_data['prompt_eval_duration'] / 1_000_000
                
                if 'eval_duration' in response_data:
                    metadata['eval_duration_ms'] = response_data['eval_duration'] / 1_000_000
                
                # Store full response for debugging
                metadata['raw_response'] = response_data
                
                # Success
                return ProviderResponse(
                    text=text,
                    metadata=metadata,
                    attempts=attempts,
                    retry_history=retry_history,
                    error=None
                )
            
            except urllib.error.HTTPError as e:
                # HTTP error from Ollama (handle before URLError since HTTPError is a subclass)
                last_error = e
                error_type = f"HTTPError_{e.code}"
                try:
                    error_body = e.read().decode('utf-8')
                    error_data = json.loads(error_body)
                    error_message = error_data.get('error', str(e))
                except Exception:
                    error_message = str(e)
                
                # Model not found - don't retry
                if e.code == 404:
                    return ProviderResponse(
                        text="",
                        metadata={},
                        attempts=attempts,
                        retry_history=retry_history,
                        error=f"Model '{self.config.model}' not found. Pull with: ollama pull {self.config.model}"
                    )
                
            except urllib.error.URLError as e:
                # Connection refused - Ollama not running
                if isinstance(e.reason, ConnectionRefusedError):
                    error_message = (
                        "Ollama is not running. "
                        f"Start with: ollama serve (tried {self.base_url})"
                    )
                    return ProviderResponse(
                        text="",
                        metadata={},
                        attempts=attempts,
                        retry_history=retry_history,
                        error=error_message
                    )
                
                last_error = e
                error_type = type(e).__name__
                error_message = str(e)
            
            except Exception as e:
                last_error = e
                error_type = type(e).__name__
                error_message = str(e)
            
            # Check if we should retry
            if attempt < self.config.max_retries and self._is_retryable_error(last_error):
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
                # Don't retry or exhausted retries
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
        List available Ollama models.
        
        Returns:
            List of ModelInfo objects
        """
        try:
            # List models using Ollama API
            url = f"{self.base_url}/api/tags"
            req = urllib.request.Request(url)
            
            with urllib.request.urlopen(req, timeout=10) as response:
                response_data = json.loads(response.read().decode('utf-8'))
            
            models = []
            for model_data in response_data.get('models', []):
                model_name = model_data.get('name', '')
                
                model_info = ModelInfo(
                    name=model_name,
                    metadata={
                        'size': model_data.get('size'),
                        'modified_at': model_data.get('modified_at'),
                        'digest': model_data.get('digest'),
                    }
                )
                
                # Add details if available
                if 'details' in model_data:
                    details = model_data['details']
                    model_info.metadata['format'] = details.get('format')
                    model_info.metadata['family'] = details.get('family')
                    model_info.metadata['parameter_size'] = details.get('parameter_size')
                    model_info.metadata['quantization_level'] = details.get('quantization_level')
                
                models.append(model_info)
            
            return models
            
        except urllib.error.URLError as e:
            if isinstance(e.reason, ConnectionRefusedError):
                # Ollama not running
                return []
            raise
        
        except Exception:
            # If listing fails, return empty list
            return []
    
    def embed(self, text: str) -> EmbedResult:
        """
        Generate embeddings using Ollama embedding model.
        
        Args:
            text: Input text to embed
            
        Returns:
            EmbedResult with vector, success, error, and metrics
        """
        start_time = time.perf_counter()
        
        try:
            # Use Ollama embedding API
            url = f"{self.base_url}/api/embeddings"
            data = {
                "model": self.config.model,
                "prompt": text
            }
            
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            
            with urllib.request.urlopen(req, timeout=60) as response:
                response_data = json.loads(response.read().decode('utf-8'))
            
            # Extract vector from response
            vector = response_data.get('embedding', [])
            
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
                vector=vector,
                success=True,
                error=None,
                metrics=metrics
            )
        
        except urllib.error.URLError as e:
            if isinstance(e.reason, ConnectionRefusedError):
                error_message = f"Ollama is not running. Start with: ollama serve (tried {self.base_url})"
            else:
                error_message = str(e)
            
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
                error=error_message,
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
