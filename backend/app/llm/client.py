"""OpenAI-compatible client for Tencent Cloud TokenHub (ADR-006, ADR-005).

One small interface so the model can be swapped by configuration. `embed` is
the shared embedding function: connectors (chunks) and the query pipeline
(questions) must both use it, so vectors come from the same model.
"""
import os
from collections.abc import Sequence
from dataclasses import dataclass

import httpx

EMBEDDING_DIM = 1024          # must match chunks.embedding vector(1024)
EMBEDDING_MAX_CHARS = 2000    # TokenHub limit per input string
EMBEDDING_BATCH = 128         # TokenHub recommended maximum per request
DEFAULT_EMBEDDING_MODEL = "kinfra-text-embedding-0.6b"

_http = httpx.Client()  # shared: keeps connections to TokenHub alive between calls (thread-safe)


class LLMNotConfigured(RuntimeError):
    pass


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatResult:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class LLMClient:
    base_url: str
    api_key: str
    chat_model: str
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    timeout_s: float = 60.0

    @classmethod
    def from_env(cls) -> "LLMClient":
        values = {k: os.environ.get(k, "").strip() for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")}
        missing = [k for k, v in values.items() if not v]
        if missing:
            raise LLMNotConfigured(f"missing environment variables: {', '.join(missing)}")
        return cls(
            base_url=values["LLM_BASE_URL"].rstrip("/"),
            api_key=values["LLM_API_KEY"],
            chat_model=values["LLM_MODEL"],
            embedding_model=os.environ.get("EMBEDDING_MODEL", "").strip() or DEFAULT_EMBEDDING_MODEL,
        )

    def _post(self, path: str, payload: dict) -> dict:
        try:
            resp = _http.post(
                f"{self.base_url}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout_s,
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"could not reach the model provider: {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise LLMError(f"model provider returned HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def chat(self, messages: list[dict], temperature: float = 0.2) -> ChatResult:
        data = self._post(
            "/chat/completions",
            {"model": self.chat_model, "messages": messages, "temperature": temperature},
        )
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("unexpected chat response shape") from exc
        usage = data.get("usage") or {}
        return ChatResult(
            content=content,
            model=data.get("model", self.chat_model),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts in order. Each text must be at most 2,000 characters."""
        too_long = [i for i, t in enumerate(texts) if len(t) > EMBEDDING_MAX_CHARS]
        if too_long:
            raise ValueError(f"texts at positions {too_long} exceed {EMBEDDING_MAX_CHARS} characters")
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBEDDING_BATCH):
            batch = list(texts[start:start + EMBEDDING_BATCH])
            data = self._post("/embeddings", {"model": self.embedding_model, "input": batch})
            items = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
            if len(items) != len(batch):
                raise LLMError(f"expected {len(batch)} embeddings, got {len(items)}")
            for item in items:
                vec = item.get("embedding") or []
                if len(vec) != EMBEDDING_DIM:
                    raise LLMError(f"expected {EMBEDDING_DIM}-dimension embeddings, got {len(vec)}")
                vectors.append([float(x) for x in vec])
        return vectors
