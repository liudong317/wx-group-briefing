from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from .config import CodexConfig
from .credentials import resolve_api_key
from .errors import CodexError

KeyResolver = Callable[[], str]
UrlOpener = Callable[..., Any]


class OpenAICompatibleClient:
    """Summarize through an OpenAI-compatible gateway."""

    def __init__(
        self,
        config: CodexConfig,
        *,
        opener: UrlOpener = urllib.request.urlopen,
        key_resolver: KeyResolver | None = None,
    ):
        self.config = config
        self.opener = opener
        self.key_resolver = key_resolver or (lambda: resolve_api_key(self.config))

    @property
    def display_name(self) -> str:
        return f"OpenAI 兼容中转（{self.config.model}）"

    def check(self) -> str:
        self.key_resolver()
        return f"OpenAI 兼容中转已配置；模型 {self.config.model}；密钥可读取"

    def complete(self, system_prompt: str, user_prompt: str, *, max_tokens: int | None = None) -> str:
        del max_tokens  # Different gateways support different token-limit field names.
        endpoint = self._chat_completions_endpoint()
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.key_resolver()}",
                "Content-Type": "application/json",
                "User-Agent": "wechat-group-daily/0.4",
            },
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.config.command_timeout_seconds) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[-1200:]
            raise CodexError(f"中转站请求失败（HTTP {exc.code}）: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise CodexError(f"中转站连接失败: {exc}") from exc

        try:
            data = json.loads(body)
            output = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise CodexError("中转站返回格式不是标准 OpenAI Chat Completions 响应") from exc
        if not isinstance(output, str) or not output.strip():
            raise CodexError("中转站没有返回日报内容")
        return output.strip()

    def _chat_completions_endpoint(self) -> str:
        base_url = (self.config.base_url or "").rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"
