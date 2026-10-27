from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path

from .config import ReportConfig
from .errors import ConfigError


def safe_group_name(group: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", group)
    value = re.sub(r"\s+", " ", value).strip(" ._")
    return (value or "未命名群聊")[:80]


def normalize_self_name(text: str) -> str:
    """把微信里表示自己的昵称 me 统一成「我」。"""
    return re.sub(r"(?<![A-Za-z0-9_])me(?![A-Za-z0-9_])", "我", text)


def normalize_message_lines(lines: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(normalize_self_name(line) for line in lines)


def render_report(
    *,
    group: str,
    day: date,
    summary_markdown: str,
    message_count: int,
    engine: str,
    api_calls: int,
    redaction_counts: dict[str, int],
    truncated: bool,
) -> str:
    del message_count, engine, api_calls, redaction_counts  # 页脚仅保留生成时间
    warning = "\n> 注意：消息达到配置上限，本日报可能只覆盖部分聊天记录。" if truncated else ""
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    body = normalize_self_name(summary_markdown.strip())
    return (
        f"# {group} · {day.isoformat()} 微信群日报\n\n"
        f"{body}\n\n"
        "---\n\n"
        f"> 生成时间：{generated_at}。"
        f"{warning}\n"
    )


def report_path(config: ReportConfig, group: str, day: date) -> Path:
    try:
        name = config.filename.format(date=day.isoformat(), group=safe_group_name(group))
    except (KeyError, ValueError) as exc:
        raise ConfigError(f"report.filename 无法格式化: {exc}") from exc
    return config.output_dir / name


def write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, content)


def write_raw_transcript(config: ReportConfig, group: str, day: date, messages: tuple[str, ...]) -> Path:
    raw_dir = config.output_dir / "raw"
    path = raw_dir / f"{day.isoformat()}_{safe_group_name(group)}_raw.json"
    payload = json.dumps(
        {"group": group, "date": day.isoformat(), "count": len(messages), "messages": messages},
        ensure_ascii=False,
        indent=2,
    )
    raw_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, payload + "\n")
    return path


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
