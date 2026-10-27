from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import AppConfig
from .errors import WechatDailyError
from .runtime import prepare_runtime


def build_plist(config: AppConfig, *, launchd_runtime: Path | None = None) -> bytes:
    project_dir = (launchd_runtime or config.path.parent).resolve()
    config_path = project_dir / "config.toml" if launchd_runtime else config.path
    log_dir = project_dir / "logs"
    python_executable = (
        project_dir / ".venv" / "bin" / "python3" if launchd_runtime else Path(sys.executable)
    )
    venv_bin = python_executable.parent
    path_value = ":".join(
        [
            str(venv_bin),
            "/Applications/ChatGPT.app/Contents/Resources",
            "/Applications/Codex.app/Contents/Resources",
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
        ]
    )
    data = {
        "Label": config.schedule.label,
        "ProgramArguments": [
            str(python_executable),
            "-m",
            "wechat_daily.cli",
            "--config",
            str(config_path),
            "run",
        ],
        "WorkingDirectory": str(project_dir),
        "EnvironmentVariables": {
            "HOME": str(Path.home()),
            "PATH": path_value,
            "PYTHONUNBUFFERED": "1",
        },
        "StartCalendarInterval": {"Hour": config.schedule.hour, "Minute": config.schedule.minute},
        "RunAtLoad": False,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(log_dir / "launchd.out.log"),
        "StandardErrorPath": str(log_dir / "launchd.err.log"),
    }
    return plistlib.dumps(data, fmt=plistlib.FMT_XML, sort_keys=False)


def install_launch_agent(config: AppConfig, *, load: bool = True) -> Path:
    launchd_runtime = prepare_runtime(config, system="Darwin")
    agents_dir = Path.home() / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    destination = agents_dir / f"{config.schedule.label}.plist"
    payload = build_plist(config, launchd_runtime=launchd_runtime)

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=agents_dir)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)

    if load:
        domain = f"gui/{os.getuid()}"
        subprocess.run(
            ["launchctl", "bootout", domain, str(destination)], capture_output=True, text=True, check=False
        )
        completed = subprocess.run(
            ["launchctl", "bootstrap", domain, str(destination)], capture_output=True, text=True, check=False
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise WechatDailyError(f"plist 已写入，但 launchctl 加载失败: {detail}")
    return destination
