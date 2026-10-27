import subprocess
from pathlib import Path

from wechat_daily.config import (
    AppConfig,
    CodexConfig,
    PrivacyConfig,
    ReportConfig,
    ScheduleConfig,
    SummaryConfig,
    WechatConfig,
)
from wechat_daily.runtime import runtime_dir, venv_python
from wechat_daily.windows_scheduler import (
    build_schtasks_args,
    build_windows_launcher,
    install_windows_task,
)


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        tmp_path / "config.toml",
        WechatConfig("wechat-cli", ("测试群",), 100, 1000, 60),
        CodexConfig("codex", "claude-opus-4-8", 60),
        SummaryConfig(2000, "简体中文", ""),
        PrivacyConfig(True, True, True, True),
        ReportConfig(tmp_path / "reports", "{date}_{group}.md", False),
        ScheduleConfig("com.test.wechat-daily", 21, 30),
    )


def test_windows_runtime_and_python_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local App Data"))
    config = _config(tmp_path)
    assert runtime_dir(config, system="Windows") == tmp_path / "Local App Data/com.test.wechat-daily"
    assert venv_python(tmp_path, system="Windows") == tmp_path / ".venv/Scripts/python.exe"


def test_windows_launcher_and_schtasks_arguments(tmp_path: Path) -> None:
    config = _config(tmp_path)
    task_runtime = tmp_path / "Runtime With Spaces"
    launcher = task_runtime / "run-daily.cmd"
    payload = build_windows_launcher(config, task_runtime)
    args = build_schtasks_args(config, launcher)

    assert ".venv" in payload and "Scripts" in payload and "python.exe" in payload
    assert "wechat_daily.cli" in payload
    assert "scheduler.out.log" in payload
    assert args[args.index("/ST") + 1] == "21:30"
    assert args[args.index("/TN") + 1] == "com.test.wechat-daily"
    assert args[args.index("/TR") + 1] == f'cmd.exe /D /C ""{launcher}""'


def test_install_windows_task_writes_launcher_and_registers(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    task_runtime = tmp_path / "runtime"
    (task_runtime / "logs").mkdir(parents=True)
    captured = {}

    monkeypatch.setattr(
        "wechat_daily.windows_scheduler.prepare_runtime",
        lambda _config, system: task_runtime,
    )

    def runner(command, **_kwargs):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, "SUCCESS", "")

    launcher = install_windows_task(config, runner=runner)
    assert launcher.is_file()
    assert "wechat_daily.cli" in launcher.read_text(encoding="utf-8")
    assert captured["command"][0] == "schtasks.exe"
