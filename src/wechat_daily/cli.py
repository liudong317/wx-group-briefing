from __future__ import annotations

import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import click

from . import __version__
from .ai_client import create_ai_client
from .config import AppConfig, load_config
from .credentials import credential_account, store_api_key
from .doctor import run_checks
from .errors import ConfigError, WechatDailyError
from .pdf_report import write_pdf_report
from .privacy import redact_lines
from .image_report import write_image_report
from .report import (
    normalize_message_lines,
    render_report,
    report_path,
    write_raw_transcript,
    write_report,
)
from .scheduler import install_platform_schedule
from .source import WechatCliSource
from .summarizer import DailySummarizer

DEFAULT_CONFIG = Path("config.toml")


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=DEFAULT_CONFIG,
    envvar="WECHAT_DAILY_CONFIG",
    show_default=True,
)
@click.version_option(__version__, prog_name="wechat-daily")
@click.pass_context
def cli(ctx: click.Context, config_path: Path) -> None:
    """从本机微信读取指定群聊，并用 AI 生成 Markdown 和 PDF 日报。"""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


def _config(ctx: click.Context) -> AppConfig:
    return load_config(ctx.obj["config_path"])


@cli.command("init-config")
@click.pass_context
def init_config(ctx: click.Context) -> None:
    """从示例创建 config.toml（不会覆盖已有文件）。"""
    destination = Path(ctx.obj["config_path"]).expanduser().resolve()
    project_dir = Path(__file__).resolve().parents[2]
    example_config = project_dir / "config.example.toml"
    if destination.exists():
        raise click.ClickException(f"文件已存在，不覆盖: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example_config, destination)
    click.echo(f"已创建: {destination}")
    click.echo(f"请填写 [wechat].groups，并按 README 完成 [ai] 配置: {destination}")


@cli.command("set-api-key")
@click.pass_context
def set_api_key(ctx: click.Context) -> None:
    """把中转站 API Key 安全保存到系统凭据库。"""
    config = _config(ctx)
    api_key = click.prompt("请输入薛定Token API Key", hide_input=True, confirmation_prompt=True)
    store_api_key(config.codex, api_key)
    click.echo(
        f"✅ API Key 已保存到系统凭据库: "
        f"{config.codex.api_key_keychain_service} / {credential_account(config.codex)}"
    )


@cli.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """检查设备、微信、数据库密钥、群名和 AI 总结配置。"""
    config = _config(ctx)
    checks = run_checks(config)
    icons = {"ok": "✅", "warn": "⚠️", "error": "❌"}
    for check in checks:
        click.echo(f"{icons[check.level]} {check.name}: {check.detail}")
    if any(check.level == "error" for check in checks):
        raise click.exceptions.Exit(1)


@cli.command("groups")
@click.option("--limit", default=200, show_default=True, type=click.IntRange(1, 2000))
@click.pass_context
def groups_command(ctx: click.Context, limit: int) -> None:
    """列出最近出现的微信群，方便复制准确群名。"""
    config = _config(ctx)
    groups = WechatCliSource(config.wechat).list_groups(limit)
    if not groups:
        click.echo("没有读取到群聊。")
        return
    for item in groups:
        click.echo(f"- {item.get('chat', '(未命名)')}  [{item.get('time', '')}]")


@cli.command()
@click.option(
    "--date", "date_value", default="today", show_default=True, help="today、yesterday 或 YYYY-MM-DD"
)
@click.option("--group", "group_overrides", multiple=True, help="临时覆盖配置，可重复传入多个群")
@click.option("--dry-run", is_flag=True, help="只读取和脱敏，不调用 AI、不写日报")
@click.pass_context
def run(ctx: click.Context, date_value: str, group_overrides: tuple[str, ...], dry_run: bool) -> None:
    """生成指定日期的微信群日报。"""
    config = _config(ctx)
    day = parse_day(date_value)
    groups = tuple(group.strip() for group in group_overrides if group.strip()) or config.wechat.groups
    if not groups:
        raise ConfigError("没有配置目标群，请填写 wechat.groups 或使用 --group")
    if any("请改成" in group for group in groups):
        raise ConfigError("目标群仍是示例值；先修改 config.toml，或使用 --group 指定")

    source = WechatCliSource(config.wechat)
    failures = 0

    for requested_group in groups:
        try:
            click.echo(f"读取 {requested_group} / {day.isoformat()} …")
            fetched = source.fetch_group_day(requested_group, day)
            normalized = normalize_message_lines(fetched.messages)
            redacted = redact_lines(normalized, config.privacy)
            click.echo(
                f"  读取 {len(fetched.messages)} 条，脱敏 {sum(redacted.counts.values())} 处"
                + ("，已达到消息上限" if fetched.truncated else "")
            )
            for failure in fetched.failures[:3]:
                click.echo(f"  ⚠️ 局部读取失败: {failure}", err=True)
            if dry_run:
                continue

            if config.report.save_raw_transcript:
                raw_path = write_raw_transcript(config.report, fetched.group, day, fetched.messages)
                click.echo(f"  原始记录已保存（未脱敏，仅本地）: {raw_path}")

            client = create_ai_client(config.codex)
            summarized = DailySummarizer(client, config.summary).summarize(fetched.group, day, redacted.lines)
            content = render_report(
                group=fetched.group,
                day=day,
                summary_markdown=summarized.markdown,
                message_count=len(fetched.messages),
                engine=client.display_name,
                api_calls=summarized.api_calls,
                redaction_counts=redacted.counts,
                truncated=fetched.truncated,
            )
            destination = report_path(config.report, fetched.group, day)
            write_report(destination, content)
            click.echo(f"  ✅ Markdown 已保存: {destination}")
            if config.report.generate_image:
                image_paths = write_image_report(destination, content)
                for image_path in image_paths:
                    click.echo(f"  ✅ 图片已保存: {image_path}")
            if config.report.generate_pdf:
                pdf_destination = destination.with_suffix(".pdf")
                pages = write_pdf_report(
                    pdf_destination,
                    content,
                    max_pages=config.report.pdf_max_pages,
                )
                click.echo(f"  ✅ PDF 已保存（{pages} 页）: {pdf_destination}")
        except WechatDailyError as exc:
            failures += 1
            click.echo(f"  ❌ {exc}", err=True)

    if failures:
        raise click.exceptions.Exit(1)


@cli.command("render-pdf")
@click.argument(
    "markdown_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False, readable=True),
)
@click.option("--output", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--max-pages", default=2, show_default=True, type=click.IntRange(1, 5))
def render_pdf_command(markdown_path: Path, output: Path | None, max_pages: int) -> None:
    """把已有 Markdown 日报转换为紧凑的人类阅读版 PDF。"""
    source = markdown_path.expanduser().resolve()
    destination = output.expanduser().resolve() if output else source.with_suffix(".pdf")
    content = source.read_text(encoding="utf-8")
    pages = write_pdf_report(destination, content, max_pages=max_pages)
    click.echo(f"✅ PDF 已保存（{pages} 页）: {destination}")


@cli.command("install-schedule")
@click.option("--no-load", is_flag=True, help="只生成定时运行文件，不立即注册任务")
@click.pass_context
def install_schedule(ctx: click.Context, no_load: bool) -> None:
    """安装当前用户的每日定时任务。"""
    config = _config(ctx)
    if not config.wechat.groups or any("请改成" in group for group in config.wechat.groups):
        raise ConfigError("先在 config.toml 中填写真实群名")
    create_ai_client(config.codex).check()
    installed = install_platform_schedule(config, load=not no_load)
    click.echo(f"✅ {installed.scheduler}配置已安装: {installed.path}")
    click.echo(f"自动日报目录: {installed.runtime / 'reports'}")
    click.echo(f"后台日志目录: {installed.runtime / 'logs'}")
    if not no_load:
        click.echo(f"每天 {config.schedule.hour:02d}:{config.schedule.minute:02d} 自动执行。")


def parse_day(value: str, timezone: str = "Asia/Shanghai") -> date:
    today = datetime.now(ZoneInfo(timezone)).date()
    normalized = value.strip().lower()
    if normalized == "today":
        return today
    if normalized == "yesterday":
        return today - timedelta(days=1)
    try:
        return date.fromisoformat(normalized)
    except ValueError as exc:
        raise ConfigError(f"日期格式错误: {value}；请用 today、yesterday 或 YYYY-MM-DD") from exc


def main() -> int:
    try:
        result = cli(standalone_mode=False)
        return result if isinstance(result, int) else 0
    except click.exceptions.Exit as exc:
        return exc.exit_code
    except WechatDailyError as exc:
        click.echo(f"错误: {exc}", err=True)
        return 1
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
