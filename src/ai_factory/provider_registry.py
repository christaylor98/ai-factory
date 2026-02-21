"""
Provider registry for ai-factory
"""
from typing import Type, Optional
from .config import Config
from .providers.base import BaseProvider
from .providers.stub import StubProvider

# Import Gemini provider if available
try:
    from .providers.gemini import GeminiProvider
    _has_gemini = True
except ImportError:
    _has_gemini = False

# Import OpenRouter provider if available
try:
    from .providers.openrouter import OpenRouterProvider
    _has_openrouter = True
except ImportError:
    _has_openrouter = False

# Import OpenAI provider if available
try:
    from .providers.openai import OpenAIProvider
    _has_openai = True
except ImportError:
    _has_openai = False

# Import Anthropic provider if available
try:
    from .providers.anthropic import AnthropicProvider
    _has_anthropic = True
except ImportError:
    _has_anthropic = False

# Import Copilot CLI provider if available
try:
    from .providers.copilot_cli import CopilotCLIProvider
    _has_copilot_cli = True
except ImportError:
    _has_copilot_cli = False


# Registry of available providers
_PROVIDER_REGISTRY: dict[str, Type[BaseProvider]] = {
    "stub": StubProvider,
}

# Register Gemini if available
if _has_gemini:
    _PROVIDER_REGISTRY["gemini"] = GeminiProvider

# Register OpenRouter if available
if _has_openrouter:
    _PROVIDER_REGISTRY["openrouter"] = OpenRouterProvider

# Register OpenAI if available
if _has_openai:
    _PROVIDER_REGISTRY["openai"] = OpenAIProvider

# Register Anthropic if available
if _has_anthropic:
    _PROVIDER_REGISTRY["anthropic"] = AnthropicProvider

# Register Copilot CLI if available
if _has_copilot_cli:
    _PROVIDER_REGISTRY["copilot_cli"] = CopilotCLIProvider


def register_provider(name: str, provider_class: Type[BaseProvider]) -> None:
    """
    Register a new provider.
    
    Args:
        name: Provider name
        provider_class: Provider class (must inherit from BaseProvider)
    """
    if not issubclass(provider_class, BaseProvider):
        raise TypeError(f"Provider class must inherit from BaseProvider")
    _PROVIDER_REGISTRY[name] = provider_class


def get_provider(name: str, config: Config) -> BaseProvider:
    """
    Get a provider instance by name.
    
    Args:
        name: Provider name
        config: Configuration object
        
    Returns:
        Provider instance
        
    Raises:
        ValueError: If provider not found
    """
    provider_class = _PROVIDER_REGISTRY.get(name)
    if provider_class is None:
        available = ", ".join(_PROVIDER_REGISTRY.keys())
        raise ValueError(
            f"Provider '{name}' not found. Available providers: {available}"
        )
    return provider_class(config)


def list_provider_names() -> list[str]:
    """
    List all registered provider names.
    
    Returns:
        List of provider names
    """
    return list(_PROVIDER_REGISTRY.keys())
