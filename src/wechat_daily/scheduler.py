from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .errors import WechatDailyError
from .launchd import install_launch_agent
from .runtime import runtime_dir
from .windows_scheduler import install_windows_task


@dataclass(frozen=True)
class ScheduleInstall:
    scheduler: str
    path: Path
    runtime: Path


def install_platform_schedule(config: AppConfig, *, load: bool = True) -> ScheduleInstall:
    system = platform.system()
    if system == "Darwin":
        path = install_launch_agent(config, load=load)
        return ScheduleInstall("launchd", path, runtime_dir(config, system="Darwin"))
    if system == "Windows":
        path = install_windows_task(config, load=load)
        return ScheduleInstall("Windows 任务计划程序", path, runtime_dir(config, system="Windows"))
    raise WechatDailyError(f"自动定时目前只支持 macOS 和 Windows；当前系统: {system}")
