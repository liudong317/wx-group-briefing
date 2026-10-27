from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .config import WechatConfig
from .errors import WechatSourceError

Runner = Callable[..., subprocess.CompletedProcess[str]]
_TIMESTAMP_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})]")


@dataclass(frozen=True)
class FetchResult:
    group: str
    username: str
    messages: tuple[str, ...]
    failures: tuple[str, ...]
    truncated: bool


class WechatCliSource:
    def __init__(self, config: WechatConfig, runner: Runner = subprocess.run):
        self.config = config
        self.runner = runner
        self.command = self._resolve_command(config.command)

    @staticmethod
    def _resolve_command(command: str) -> str:
        candidate = Path(command).expanduser()
        if candidate.parent != Path(".") or candidate.is_absolute():
            return str(candidate.resolve())
        located = shutil.which(command)
        if located:
            return located
        # launchd 没有交互式 shell 的 PATH，但 console script 与 venv Python 在同一目录。
        siblings = [Path(sys.executable).parent / command]
        if sys.platform == "win32" and not command.lower().endswith(".exe"):
            siblings.insert(0, Path(sys.executable).parent / f"{command}.exe")
        for sibling in siblings:
            if sibling.exists():
                return str(sibling)
        return command

    def is_installed(self) -> bool:
        return Path(self.command).is_file() or shutil.which(self.command) is not None

    def version(self) -> str:
        completed = self._run(["--version"])
        return completed.stdout.strip()

    def list_groups(self, limit: int = 200) -> list[dict[str, Any]]:
        payload = self._run_json(["sessions", "--limit", str(limit), "--format", "json"])
        if not isinstance(payload, list):
            raise WechatSourceError("wechat-cli sessions 返回的不是 JSON 数组")
        return [item for item in payload if isinstance(item, dict) and item.get("is_group") is True]

    def fetch_group_day(self, group: str, day: date) -> FetchResult:
        start = f"{day.isoformat()} 00:00:00"
        end = f"{day.isoformat()} 23:59:59"
        collected: list[tuple[int, str]] = []
        failures: list[str] = []
        username = ""
        offset = 0
        truncated = False

        while offset < self.config.max_messages_per_group:
            limit = min(self.config.page_size, self.config.max_messages_per_group - offset)
            payload = self._run_json(
                [
                    "history",
                    group,
                    "--limit",
                    str(limit),
                    "--offset",
                    str(offset),
                    "--start-time",
                    start,
                    "--end-time",
                    end,
                    "--format",
                    "json",
                ]
            )
            if not isinstance(payload, dict):
                raise WechatSourceError("wechat-cli history 返回的不是 JSON 对象")
            if payload.get("is_group") is not True:
                raise WechatSourceError(f"“{group}”不是群聊；为避免误传私聊，任务已停止")

            payload_group = payload.get("chat")
            if isinstance(payload_group, str) and payload_group.strip():
                group = payload_group.strip()
            payload_username = payload.get("username")
            if isinstance(payload_username, str):
                username = payload_username

            batch = payload.get("messages", [])
            if not isinstance(batch, list) or not all(isinstance(item, str) for item in batch):
                raise WechatSourceError("wechat-cli history 的 messages 字段格式不正确")
            for message in batch:
                collected.append((len(collected), message))

            batch_failures = payload.get("failures") or []
            if isinstance(batch_failures, list):
                failures.extend(str(item) for item in batch_failures)

            offset += len(batch)
            if len(batch) < limit:
                break
            if offset >= self.config.max_messages_per_group:
                truncated = True

        ordered = sorted(collected, key=lambda item: self._sort_key(item[1], item[0]))
        return FetchResult(
            group=group,
            username=username,
            messages=tuple(message for _, message in ordered),
            failures=tuple(dict.fromkeys(failures)),
            truncated=truncated,
        )

    @staticmethod
    def _sort_key(message: str, original_index: int) -> tuple[str, int]:
        match = _TIMESTAMP_RE.match(message)
        return (match.group(1) if match else "9999-99-99 99:99", original_index)

    def _run_json(self, args: list[str]) -> Any:
        completed = self._run(args)
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            preview = completed.stdout.strip().replace("\n", " ")[:300]
            raise WechatSourceError(f"wechat-cli 没有返回有效 JSON: {preview or '(空输出)'}") from exc

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.setdefault("LANG", "zh_CN.UTF-8")
        try:
            completed = self.runner(
                [self.command, *args],
                capture_output=True,
                text=True,
                timeout=self.config.command_timeout_seconds,
                env=env,
                check=False,
            )
        except FileNotFoundError as exc:
            raise WechatSourceError(
                f"找不到 {self.config.command}；请先在项目目录执行 uv sync --extra dev"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise WechatSourceError(
                f"wechat-cli 执行超过 {self.config.command_timeout_seconds:g} 秒"
            ) from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise WechatSourceError(f"wechat-cli 执行失败（exit={completed.returncode}）: {detail[:1000]}")
        return completed
