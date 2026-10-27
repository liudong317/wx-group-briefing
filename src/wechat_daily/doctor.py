from __future__ import annotations

import os
import platform
import plistlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .ai_client import create_ai_client
from .codex import CodexCliClient
from .config import AppConfig
from .source import WechatCliSource


@dataclass(frozen=True)
class Check:
    level: str
    name: str
    detail: str


def run_checks(config: AppConfig) -> list[Check]:
    checks: list[Check] = []
    system = platform.system()
    if system == "Darwin":
        checks.append(Check("ok", "设备", f"macOS {platform.mac_ver()[0]} / {platform.machine()}"))
        wechat_app = Path("/Applications/WeChat.app")
        version = _wechat_version(wechat_app)
        if not wechat_app.exists():
            checks.append(Check("error", "微信", "未找到 /Applications/WeChat.app"))
        else:
            running = _wechat_running(system)
            checks.append(
                Check(
                    "ok" if running else "warn",
                    "微信",
                    f"版本 {version or '未知'}；{'正在运行' if running else '未运行'}",
                )
            )
    elif system == "Windows":
        checks.append(
            Check("ok", "设备", f"Windows {platform.release()} / {platform.machine()}")
        )
        running = _wechat_running(system)
        checks.append(
            Check(
                "ok" if running else "warn",
                "微信",
                "Weixin.exe 正在运行" if running else "Weixin.exe 未运行；请打开并登录微信",
            )
        )
    else:
        checks.append(Check("error", "设备", f"当前只支持 macOS 和 Windows；检测到 {system}"))

    source = WechatCliSource(config.wechat)
    if not source.is_installed():
        checks.append(Check("error", "wechat-cli", "未安装；执行 uv sync"))
    else:
        try:
            checks.append(Check("ok", "wechat-cli", source.version()))
        except Exception as exc:
            checks.append(Check("error", "wechat-cli", str(exc)))

    cli_state = Path.home() / ".wechat-cli" / "config.json"
    init_command = (
        r"以管理员身份运行 .\.venv\Scripts\wechat-cli.exe init"
        if system == "Windows"
        else "微信保持登录后执行 sudo ./.venv/bin/wechat-cli init"
    )
    checks.append(
        Check(
            "ok" if cli_state.is_file() else "error",
            "数据库密钥",
            "已初始化"
            if cli_state.is_file()
            else f"未初始化；{init_command}",
        )
    )

    if not config.wechat.groups:
        checks.append(Check("error", "目标群", "wechat.groups 为空"))
    elif any("请改成" in group for group in config.wechat.groups):
        checks.append(Check("error", "目标群", "仍是示例群名，请修改 config.toml"))
    else:
        checks.append(Check("ok", "目标群", f"已配置 {len(config.wechat.groups)} 个群"))

    if config.codex.provider == "codex":
        codex = CodexCliClient(config.codex)
        if not codex.is_installed():
            checks.append(Check("error", "AI 总结", "未找到 Codex CLI"))
        else:
            try:
                checks.append(Check("ok", "AI 总结", codex.check()))
            except Exception as exc:
                checks.append(Check("error", "AI 总结", str(exc)))
    else:
        try:
            detail = create_ai_client(config.codex).check()
            checks.append(Check("ok", "AI 总结", detail))
        except Exception as exc:
            checks.append(Check("error", "AI 总结", str(exc)))

    parent = (
        config.report.output_dir if config.report.output_dir.exists() else config.report.output_dir.parent
    )
    writable = parent.exists() and os.access(parent, os.W_OK)
    checks.append(Check("ok" if writable else "error", "输出目录", str(config.report.output_dir)))

    if system == "Darwin" and platform.mac_ver()[0].startswith("15."):
        checks.append(
            Check(
                "warn",
                "上游兼容性",
                "wechat-cli 0.2.4 文档标注 macOS >= 26.3.1；本机 15.x 需以实际 dry-run 为准",
            )
        )
    elif system == "Windows":
        checks.append(
            Check(
                "warn",
                "上游兼容性",
                "wechat-cli 通过读取 Weixin.exe 内存工作；微信升级后请重新 init，并先用 dry-run 验证",
            )
        )
    return checks


def _wechat_version(app: Path) -> str:
    info = app / "Contents" / "Info.plist"
    try:
        with info.open("rb") as handle:
            data = plistlib.load(handle)
        return str(data.get("CFBundleShortVersionString", ""))
    except (OSError, plistlib.InvalidFileException):
        return ""


def _wechat_running(system: str) -> bool:
    if system == "Windows":
        completed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Weixin.exe", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.returncode == 0 and "Weixin.exe" in completed.stdout
    completed = subprocess.run(
        ["pgrep", "-x", "WeChat"], capture_output=True, text=True, check=False
    )
    return completed.returncode == 0
