from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from .config import AppConfig
from .errors import WechatDailyError
from .runtime import prepare_runtime, venv_python

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _cmd_value(value: str) -> str:
    return value.replace("%", "%%")


def build_windows_launcher(config: AppConfig, task_runtime: Path) -> str:
    python_executable = venv_python(task_runtime, system="Windows")
    config_path = task_runtime / "config.toml"
    logs = task_runtime / "logs"
    stdout_path = logs / "scheduler.out.log"
    stderr_path = logs / "scheduler.err.log"
    scripts_dir = python_executable.parent
    home = Path.home()
    lines = [
        "@echo off",
        "setlocal",
        f'set "HOME={_cmd_value(str(home))}"',
        f'set "PATH={_cmd_value(str(scripts_dir))};%PATH%"',
        f'cd /d "{_cmd_value(str(task_runtime))}"',
        (
            f'"{_cmd_value(str(python_executable))}" -m wechat_daily.cli '
            f'--config "{_cmd_value(str(config_path))}" run '
            f'1>> "{_cmd_value(str(stdout_path))}" '
            f'2>> "{_cmd_value(str(stderr_path))}"'
        ),
        "endlocal",
        "",
    ]
    return "\r\n".join(lines)


def build_schtasks_args(config: AppConfig, launcher: Path) -> list[str]:
    task_command = f'cmd.exe /D /C ""{launcher}""'
    return [
        "schtasks.exe",
        "/Create",
        "/TN",
        config.schedule.label,
        "/TR",
        task_command,
        "/SC",
        "DAILY",
        "/ST",
        f"{config.schedule.hour:02d}:{config.schedule.minute:02d}",
        "/RL",
        "LIMITED",
        "/F",
    ]


def install_windows_task(
    config: AppConfig,
    *,
    load: bool = True,
    runner: Runner = subprocess.run,
) -> Path:
    task_runtime = prepare_runtime(config, system="Windows")
    launcher = task_runtime / "run-daily.cmd"
    payload = build_windows_launcher(config, task_runtime)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{launcher.name}.", suffix=".tmp", dir=task_runtime
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, launcher)
    finally:
        temporary.unlink(missing_ok=True)

    if not load:
        return launcher

    try:
        completed = runner(
            build_schtasks_args(config, launcher),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        raise WechatDailyError("找不到 Windows 任务计划程序 schtasks.exe") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise WechatDailyError(f"Windows 定时任务创建失败: {detail}")
    return launcher
