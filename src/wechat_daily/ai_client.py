from __future__ import annotations

from typing import Protocol

from .codex import CodexCliClient
from .config import CodexConfig
from .openai_compatible import OpenAICompatibleClient


class AIClient(Protocol):
    @property
    def display_name(self) -> str: ...

    def check(self) -> str: ...

    def complete(self, system_prompt: str, user_prompt: str, *, max_tokens: int | None = None) -> str: ...


def create_ai_client(config: CodexConfig) -> AIClient:
    if config.provider == "openai-compatible":
        return OpenAICompatibleClient(config)
    return CodexCliClient(config)
