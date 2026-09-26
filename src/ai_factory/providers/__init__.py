"""
Provider __init__ for ai-factory
"""
from .base import BaseProvider
from .stub import StubProvider

try:
    from .gemini import GeminiProvider
except ImportError:
    pass

try:
    from .openrouter import OpenRouterProvider
except ImportError:
    pass

try:
    from .openai import OpenAIProvider
except ImportError:
    pass

try:
    from .anthropic import AnthropicProvider
except ImportError:
    pass

try:
    from .ollama import OllamaProvider
except ImportError:
    pass

try:
    from .copilot_cli import CopilotCLIProvider
except ImportError:
    pass

__all__ = ["BaseProvider", "StubProvider"]
