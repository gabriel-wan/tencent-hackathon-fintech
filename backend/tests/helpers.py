"""Shared test helpers (no fixtures here; see conftest.py)."""
from collections.abc import Sequence
from contextlib import contextmanager

from app.llm.client import EMBEDDING_DIM, ChatResult


def within(conn):
    """A `Tx` (app.db) on the test's own connection: each use is a savepoint, rolled back with the test."""
    @contextmanager
    def tx():
        with conn.begin_nested():
            yield conn
    return tx


def unit_vector(index: int) -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    vec[index] = 1.0
    return vec


class FakeLLM:
    """Records every chat call so tests can assert what the model was (not) shown."""

    def __init__(self, reply: str = "", embedding: Sequence[float] | None = None,
                 embed_error: Exception | None = None, chat_error: Exception | None = None):
        self.reply = reply
        self.embedding = list(embedding) if embedding is not None else unit_vector(0)
        self.embed_error = embed_error
        self.chat_error = chat_error
        self.chat_calls: list[list[dict]] = []

    def chat(self, messages: list[dict]) -> ChatResult:
        self.chat_calls.append(messages)
        if self.chat_error:
            raise self.chat_error
        return ChatResult(self.reply, "fake-model", 100, 20)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self.embed_error:
            raise self.embed_error
        return [self.embedding for _ in texts]

    def all_prompt_text(self) -> str:
        return "\n".join(m["content"] for call in self.chat_calls for m in call)
