import subprocess

import pytest

from wechat_daily.codex import CodexCliClient
from wechat_daily.config import CodexConfig
from wechat_daily.errors import CodexError


def _config() -> CodexConfig:
    return CodexConfig("fake-codex", None, 60)


def test_complete_uses_ephemeral_read_only_stdin() -> None:
    captured = {}

    def runner(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "## 今日概览\n\n- 完成", "progress")

    result = CodexCliClient(_config(), runner=runner).complete("系统规则", "用户任务")
    assert result.startswith("## 今日概览")
    assert "--ephemeral" in captured["command"]
    assert captured["command"][captured["command"].index("--sandbox") + 1] == "read-only"
    assert captured["command"][-1] == "-"
    assert "系统规则" in captured["input"]
    assert "用户任务" in captured["input"]


def test_complete_reports_nonzero_exit() -> None:
    def runner(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, "", "not logged in")

    with pytest.raises(CodexError, match="not logged in"):
        CodexCliClient(_config(), runner=runner).complete("系统", "任务")


def test_explicit_model_is_passed() -> None:
    captured = []

    def runner(command, **_kwargs):
        captured.extend(command)
        return subprocess.CompletedProcess(command, 0, "ok", "")

    CodexCliClient(CodexConfig("fake-codex", "gpt-example", 60), runner=runner).complete("s", "u")
    assert captured[captured.index("--model") + 1] == "gpt-example"


def test_login_status_accepts_codex_stderr_output() -> None:
    def runner(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, "", "Logged in using ChatGPT")

    assert CodexCliClient(_config(), runner=runner).login_status() == "Logged in using ChatGPT"
