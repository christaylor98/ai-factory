"""
Base provider interface for ai-factory
"""
from abc import ABC, abstractmethod
from typing import Optional

from ..config import Config
from ..result import ProviderResponse, ModelInfo, EmbedResult


def chat_messages(config: Config, prompt: str) -> list[dict]:
    """OpenAI-style messages: the system prompt (if any), then the prompt."""
    system = [{"role": "system", "content": config.system_prompt}] if config.system_prompt else []
    return system + [{"role": "user", "content": prompt}]


def response_format(config: Config) -> Optional[dict]:
    """OpenAI-style structured output for config.json_schema, or None."""
    if not config.json_schema:
        return None
    return {"type": "json_schema", "json_schema": {"name": "answer", "schema": config.json_schema, "strict": False}}


class BaseProvider(ABC):
    """Base class for all AI providers."""

    # Whether call() honours config.system_prompt / config.json_schema. run() refuses a config that sets one
    # for a provider that does not, instead of the provider silently ignoring it.
    SUPPORTS_SYSTEM = False
    SUPPORTS_SCHEMA = False
    
    def __init__(self, config: Config):
        """
        Initialize provider with configuration.
        
        Args:
            config: Configuration object
        """
        self.config = config
    
    @abstractmethod
    def call(self, prompt: str) -> ProviderResponse:
        """
        Call the provider with a prompt.
        
        This method should implement retry logic internally using
        config.max_retries, config.backoff_base_ms, and config.backoff_multiplier.
        
        Args:
            prompt: Input prompt
            
        Returns:
            ProviderResponse with text, metadata, attempts, and retry_history
        """
        pass
    
    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """
        List available models for this provider.
        
        Returns:
            List of ModelInfo objects
        """
        pass
    
    @abstractmethod
    def embed(self, text: str) -> EmbedResult:
        """
        Generate embeddings for the given text.
        
        Args:
            text: Input text to embed
            
        Returns:
            EmbedResult with vector, success flag, error (if any), and metrics
        """
        pass
