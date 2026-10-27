import plistlib
from datetime import date
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
from wechat_daily.launchd import build_plist
from wechat_daily.pdf_report import write_pdf_report
from wechat_daily.report import report_path, safe_group_name, write_report


def test_report_filename_is_safe_and_write_is_atomic(tmp_path: Path) -> None:
    config = ReportConfig(tmp_path, "{date}_{group}.md", False)
    destination = report_path(config, '群/聊:"测试"', date(2026, 7, 22))
    write_report(destination, "hello\n")
    assert destination.read_text(encoding="utf-8") == "hello\n"
    assert "/" not in destination.name
    assert safe_group_name("../") == "未命名群聊"


def test_pdf_report_renders_chinese_in_two_pages(tmp_path: Path) -> None:
    markdown = """# 测试群 · 2026-07-22 微信群日报

## 今日概览

这是供人类阅读的中文摘要。

## 待办事项

- 张三：完成产品原型。
- 李四：确认发布日期。

> 数据：本机微信只读提取，共 12 条。
"""
    destination = tmp_path / "report.pdf"
    pages = write_pdf_report(destination, markdown, max_pages=2)
    assert 1 <= pages <= 2
    assert destination.read_bytes().startswith(b"%PDF-")


def test_launchd_plist_has_calendar_and_absolute_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config = AppConfig(
        config_path,
        WechatConfig("wechat-cli", ("群",), 100, 1000, 60),
        CodexConfig("codex", None, 60),
        SummaryConfig(2000, "简体中文", ""),
        PrivacyConfig(True, True, True, True),
        ReportConfig(tmp_path / "reports", "{date}_{group}.md", False),
        ScheduleConfig("com.test.daily", 22, 0),
    )
    payload = plistlib.loads(build_plist(config))
    assert payload["StartCalendarInterval"] == {"Hour": 22, "Minute": 0}
    assert str(config_path) in payload["ProgramArguments"]

    runtime = tmp_path / "Application Support" / "com.test.daily"
    background_payload = plistlib.loads(build_plist(config, launchd_runtime=runtime))
    assert str(runtime / "config.toml") in background_payload["ProgramArguments"]
    assert background_payload["ProgramArguments"][0] == str(runtime / ".venv/bin/python3")
    assert background_payload["WorkingDirectory"] == str(runtime)
