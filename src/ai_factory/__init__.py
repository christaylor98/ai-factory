"""
ai-factory - Minimal LLM execution library

Public API:
    - run(prompt, config) -> RunResult
    - list_models(provider_name, config) -> list[ModelInfo]
    - Config (configuration dataclass)
    - load_env() -> bool: read a .env file into the environment (opt-in)

Importing ai_factory changes nothing in os.environ. Up to 1.0 it loaded a .env on import, which put any
ANTHROPIC_API_KEY found up the tree into the importing process -- and into every subprocess it started, which
silently switched `claude` from its login to API billing. The CLI and the MCP server call load_env() themselves;
a library user calls it when they want it.
"""

from .env import load_env
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
    "load_env",
]
