"""
Base provider interface for ai-factory
"""
from abc import ABC, abstractmethod
from typing import Optional

from ..config import Config
from ..result import ProviderResponse, ModelInfo


class BaseProvider(ABC):
    """Base class for all AI providers."""
    
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
