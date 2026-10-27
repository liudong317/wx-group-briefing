from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

from .config import AppConfig
from .errors import WechatDailyError


def runtime_dir(config: AppConfig, *, system: str | None = None) -> Path:
    current_system = system or platform.system()
    if current_system == "Windows":
        local_app_data = os.getenv("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / config.schedule.label
    if current_system == "Darwin":
        return Path.home() / "Library" / "Application Support" / config.schedule.label
    return Path.home() / ".local" / "share" / config.schedule.label


def venv_python(project_dir: Path, *, system: str | None = None) -> Path:
    current_system = system or platform.system()
    if current_system == "Windows":
        return project_dir / ".venv" / "Scripts" / "python.exe"
    return project_dir / ".venv" / "bin" / "python3"


def prepare_runtime(config: AppConfig, *, system: str | None = None) -> Path:
    """Install an isolated project copy in a scheduler-friendly user directory."""
    current_system = system or platform.system()
    project_dir = config.path.parent.resolve()
    destination = runtime_dir(config, system=current_system)
    destination.mkdir(parents=True, exist_ok=True)

    source_package = project_dir / "src"
    if not source_package.is_dir():
        raise WechatDailyError(f"找不到项目源码目录: {source_package}")

    runtime_source = destination / "src"
    if runtime_source.exists():
        shutil.rmtree(runtime_source)
    shutil.copytree(source_package, runtime_source)

    for filename in ("pyproject.toml", "uv.lock", "README.md"):
        source = project_dir / filename
        if not source.is_file():
            raise WechatDailyError(f"找不到定时运行所需文件: {source}")
        shutil.copy2(source, destination / filename)

    runtime_config = destination / "config.toml"
    shutil.copy2(config.path, runtime_config)
    try:
        runtime_config.chmod(0o600)
    except OSError:
        pass
    (destination / "logs").mkdir(exist_ok=True)
    (destination / "reports").mkdir(exist_ok=True)

    uv = shutil.which("uv")
    if not uv:
        raise WechatDailyError("找不到 uv，无法准备定时任务的独立运行环境")
    completed = subprocess.run(
        [uv, "sync", "--project", str(destination), "--frozen", "--no-dev"],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise WechatDailyError(f"准备定时任务独立运行环境失败: {detail}")

    python_executable = venv_python(destination, system=current_system)
    if not python_executable.is_file():
        raise WechatDailyError(f"定时任务 Python 环境创建失败: {python_executable}")
    return destination
