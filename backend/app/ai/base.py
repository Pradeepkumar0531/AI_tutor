"""AI provider boundary. Domain services must depend on these protocols, never raw SDKs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ChatRequest:
    messages: list[ChatMessage]
    model: str = "openai/gpt-oss-20b"
    temperature: float = 0.2
    max_tokens: int = 1024


@dataclass
class ChatResponse:
    content: str
    model: str
    usage: dict = field(default_factory=dict)


@dataclass
class EmbedRequest:
    texts: list[str]
    model: str = "models/gemini-embedding-001"


@dataclass
class EmbedResponse:
    embeddings: list[list[float]]
    model: str


class ChatProvider(Protocol):
    async def chat(self, request: ChatRequest) -> ChatResponse: ...


class EmbeddingProvider(Protocol):
    async def embed(self, request: EmbedRequest) -> EmbedResponse: ...
