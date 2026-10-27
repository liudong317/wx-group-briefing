from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from .config import CodexConfig
from .errors import CodexError

Runner = Callable[..., subprocess.CompletedProcess[str]]


class CodexCliClient:
    """Use the locally authenticated Codex CLI as a text-only summarizer."""

    def __init__(self, config: CodexConfig, runner: Runner = subprocess.run):
        self.config = config
        self.runner = runner
        self.command = self._resolve_command(config.command)

    @property
    def display_name(self) -> str:
        model = self.config.model or "当前默认模型"
        return f"Codex CLI（{model}）"

    @staticmethod
    def _resolve_command(command: str) -> str:
        candidate = Path(command).expanduser()
        if candidate.parent != Path(".") or candidate.is_absolute():
            return str(candidate.resolve())
        located = shutil.which(command)
        if located:
            return located
        app_candidates = (
            Path("/Applications/ChatGPT.app/Contents/Resources/codex"),
            Path("/Applications/Codex.app/Contents/Resources/codex"),
        )
        for app_candidate in app_candidates:
            if app_candidate.is_file():
                return str(app_candidate)
        return command

    def is_installed(self) -> bool:
        return Path(self.command).is_file() or shutil.which(self.command) is not None

    def version(self) -> str:
        return self._run_simple(["--version"]).stdout.strip()

    def login_status(self) -> str:
        completed = self._run_simple(["login", "status"])
        return (completed.stdout or completed.stderr).strip()

    def check(self) -> str:
        return f"{self.version()}；{self.login_status()}"

    def complete(self, system_prompt: str, user_prompt: str, *, max_tokens: int | None = None) -> str:
        del max_tokens  # codex exec currently has no output-token-limit flag.
        prompt = (
            "你现在只执行文本总结。不得调用任何工具、命令、网络或读取文件；"
            "不得修改任何文件。只处理下面提供的文本并直接返回最终 Markdown。\n\n"
            f"<系统规则>\n{system_prompt}\n</系统规则>\n\n"
            f"<用户任务>\n{user_prompt}\n</用户任务>\n"
        )
        args = [
            self.command,
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--color",
            "never",
        ]
        if self.config.model:
            args.extend(["--model", self.config.model])
        args.append("-")

        env = os.environ.copy()
        env.setdefault("NO_COLOR", "1")
        try:
            with tempfile.TemporaryDirectory(prefix="wechat-daily-codex-") as temporary_dir:
                completed = self.runner(
                    args,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self.config.command_timeout_seconds,
                    cwd=temporary_dir,
                    env=env,
                    check=False,
                )
        except FileNotFoundError as exc:
            raise CodexError("找不到 Codex CLI；请先安装/打开 Codex 或 ChatGPT，并完成登录") from exc
        except subprocess.TimeoutExpired as exc:
            raise CodexError(f"Codex 总结超过 {self.config.command_timeout_seconds:g} 秒") from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise CodexError(f"Codex 执行失败（exit={completed.returncode}）: {detail[-1500:]}")
        output = completed.stdout.strip()
        if not output:
            raise CodexError("Codex 没有返回日报内容")
        return output

    def _run_simple(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            completed = self.runner(
                [self.command, *args],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise CodexError(f"Codex CLI 检查失败: {exc}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise CodexError(f"Codex CLI 检查失败: {detail[-1000:]}")
        return completed
