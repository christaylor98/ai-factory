"""
ai-factory - Minimal LLM execution library

Public API:
    - run(prompt, config) -> RunResult
    - list_models(provider_name, config) -> list[ModelInfo]
    - Config (configuration dataclass)
"""

# Load .env file if present (must be before other imports)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, skip

from .config import Config
from .result import RunResult, ModelInfo, EmbedResult
from .runner import run, list_models, embed
from .ledger import append_event

__all__ = [
    "run",
    "list_models",
    "embed",
    "Config",
    "RunResult",
    "ModelInfo",
    "EmbedResult",
    "append_event",
]
