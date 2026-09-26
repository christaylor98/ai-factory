"""
Local provider for ai-factory: any OpenAI-compatible server on this machine
or LAN (llama-server, ollama's /v1, vLLM). No API key, no marginal cost.
"""
import time
from dataclasses import replace
from typing import Optional
from urllib.parse import urlparse

try:
    from openai import OpenAI, APIConnectionError, APITimeoutError
    _has_openai_sdk = True
except ImportError:
    _has_openai_sdk = False

from ..config import Config
from ..result import ProviderResponse, ModelInfo, EmbedResult, Metrics
from .base import BaseProvider
from .openai import OpenAIProvider

DEFAULT_LOCAL_BASE_URL = "http://localhost:8089/v1"


def _normalize_base_url(url: str) -> str:
    """Add /v1 to a bare host:port; leave any explicit path alone."""
    url = url.rstrip("/")
    if urlparse(url).path in ("", "/"):
        url += "/v1"
    return url


class LocalProvider(OpenAIProvider):
    """
    OpenAI-compatible local inference server.

    base_url defaults to llama-server on :8089. model is optional: when it
    is empty the provider uses the one model the server lists, and that id
    is what the ledger records.
    """

    def __init__(self, config: Config):
        BaseProvider.__init__(self, config)

        if not _has_openai_sdk:
            raise ImportError(
                "openai package not installed. "
                "Install with: pip install openai"
            )

        self.base_url = _normalize_base_url(config.base_url or DEFAULT_LOCAL_BASE_URL)
        self.config = replace(config, base_url=self.base_url)
        # The server ignores the key, but the SDK insists on one.
        self.api_key = "local"
        kwargs = self._client_kwargs(self.api_key)
        # SDK-level retries would retry a refused connection behind our back.
        kwargs["max_retries"] = 0
        self.client = OpenAI(**kwargs)

    def _server_down_message(self) -> str:
        return f"local server not reachable at {self.base_url} (is llama-server running?)"

    def _served_model_ids(self) -> list[str]:
        return [m.id for m in self.client.models.list().data]

    def _resolve_model(self) -> Optional[str]:
        """
        Settle self.config.model when none was given. Returns an error
        message, or None once a model is set.
        """
        if self.config.model:
            return None
        try:
            ids = self._served_model_ids()
        except Exception as e:
            return self._describe_error(e)
        if len(ids) == 1:
            self.config = replace(self.config, model=ids[0])
            return None
        if not ids:
            return f"local server at {self.base_url} lists no models"
        return (
            f"local server at {self.base_url} serves {len(ids)} models "
            f"({', '.join(ids)}); pass model="
        )

    def _create_kwargs(self, prompt: str) -> dict:
        kwargs = super()._create_kwargs(prompt)
        # llama-server hands these to the chat template (Gemma, Qwen3).
        # Other servers ignore them, so thinking may still happen there.
        kwargs["extra_body"] = {
            "chat_template_kwargs": {"enable_thinking": self.config.thinking}
        }
        return kwargs

    def _is_retryable_error(self, error: Exception) -> bool:
        # A down server stays down for the length of a backoff, and a
        # timeout on a local GPU means a slow generation that a retry
        # repeats. Retry only what the server says is transient (503 while
        # loading a model).
        if isinstance(error, (APIConnectionError, APITimeoutError)):
            return False
        return super()._is_retryable_error(error)

    def _describe_error(self, error: Exception) -> str:
        if isinstance(error, APITimeoutError):
            return f"local server at {self.base_url} did not answer within {self.config.timeout_s or 600}s"
        if isinstance(error, APIConnectionError):
            return self._server_down_message()
        return super()._describe_error(error)

    def call(self, prompt: str) -> ProviderResponse:
        error = self._resolve_model()
        if error:
            return ProviderResponse(text="", metadata={}, attempts=1, error=error)
        return super().call(prompt)

    def list_models(self) -> list[ModelInfo]:
        """
        List the models the server serves.

        Unlike the openai provider there is no fallback list: a list of
        models that are not there is worse than an error.
        """
        try:
            models = self.client.models.list().data
        except Exception as e:
            raise RuntimeError(self._describe_error(e)) from e
        return [
            ModelInfo(name=m.id, metadata={"owned_by": getattr(m, "owned_by", None)})
            for m in models
        ]

    def embed(self, text: str) -> EmbedResult:
        """Embed via /v1/embeddings (llama-server needs --embeddings)."""
        start_time = time.perf_counter()
        error = self._resolve_model()
        vector: list[float] = []
        if error is None:
            try:
                response = self.client.embeddings.create(model=self.config.model, input=text)
                vector = list(response.data[0].embedding)
            except Exception as e:
                error = self._describe_error(e)
        latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))
        return EmbedResult(
            vector=vector,
            success=error is None,
            error=error,
            metrics=Metrics(
                input_chars=len(text),
                output_chars=0,
                latency_ms=latency_ms,
                success=error is None,
            ),
        )
