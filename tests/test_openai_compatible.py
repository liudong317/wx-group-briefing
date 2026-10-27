import json

import pytest

from wechat_daily.config import CodexConfig
from wechat_daily.errors import CodexError
from wechat_daily.openai_compatible import OpenAICompatibleClient


class FakeResponse:
    def __init__(self, payload: object):
        self.body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.body


def _config(base_url: str = "https://gateway.example/v1") -> CodexConfig:
    return CodexConfig(
        "codex",
        "example-model",
        60,
        provider="openai-compatible",
        base_url=base_url,
    )


def test_complete_calls_standard_chat_completions_without_leaking_key() -> None:
    captured = {}

    def opener(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse({"choices": [{"message": {"content": "  ## 日报\n\n完成  "}}]})

    client = OpenAICompatibleClient(_config(), opener=opener, key_resolver=lambda: "secret-key")
    assert client.complete("系统", "聊天记录") == "## 日报\n\n完成"

    request = captured["request"]
    payload = json.loads(request.data)
    assert request.full_url == "https://gateway.example/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer secret-key"
    assert captured["timeout"] == 60
    assert payload == {
        "model": "example-model",
        "messages": [
            {"role": "system", "content": "系统"},
            {"role": "user", "content": "聊天记录"},
        ],
        "temperature": 0.2,
    }


def test_complete_accepts_full_chat_completions_url() -> None:
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        return FakeResponse({"choices": [{"message": {"content": "完成"}}]})

    client = OpenAICompatibleClient(
        _config("https://gateway.example/v1/chat/completions"),
        opener=opener,
        key_resolver=lambda: "secret-key",
    )
    client.complete("系统", "任务")
    assert captured["url"] == "https://gateway.example/v1/chat/completions"


def test_complete_rejects_nonstandard_response() -> None:
    client = OpenAICompatibleClient(
        _config(),
        opener=lambda *_args, **_kwargs: FakeResponse({"output": "wrong-shape"}),
        key_resolver=lambda: "secret-key",
    )
    with pytest.raises(CodexError, match="标准 OpenAI"):
        client.complete("系统", "任务")


def test_check_only_confirms_key_is_readable() -> None:
    called = []
    client = OpenAICompatibleClient(_config(), key_resolver=lambda: called.append(True) or "key")
    assert "密钥可读取" in client.check()
    assert called == [True]
