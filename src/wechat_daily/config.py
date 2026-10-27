from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigError


@dataclass(frozen=True)
class WechatConfig:
    command: str
    groups: tuple[str, ...]
    page_size: int
    max_messages_per_group: int
    command_timeout_seconds: float


@dataclass(frozen=True)
class CodexConfig:
    command: str
    model: str | None
    command_timeout_seconds: float
    provider: str = "codex"
    base_url: str | None = None
    api_key_env: str = "WECHAT_DAILY_API_KEY"
    api_key_keychain_service: str = "wechat-group-daily-xuedingtoken"
    api_key_keychain_account: str | None = None


@dataclass(frozen=True)
class SummaryConfig:
    chunk_chars: int
    language: str
    custom_instructions: str


@dataclass(frozen=True)
class PrivacyConfig:
    redact_phone: bool
    redact_email: bool
    redact_id_card: bool
    redact_bank_card: bool


@dataclass(frozen=True)
class ReportConfig:
    output_dir: Path
    filename: str
    save_raw_transcript: bool
    generate_pdf: bool = False
    generate_image: bool = True
    pdf_max_pages: int = 2


@dataclass(frozen=True)
class ScheduleConfig:
    label: str
    hour: int
    minute: int


@dataclass(frozen=True)
class AppConfig:
    path: Path
    wechat: WechatConfig
    codex: CodexConfig
    summary: SummaryConfig
    privacy: PrivacyConfig
    report: ReportConfig
    schedule: ScheduleConfig


def _table(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"配置段 [{name}] 必须是 TOML table")
    return value


def _positive_int(value: Any, field: str, *, minimum: int = 1, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{field} 必须是整数")
    if value < minimum or (maximum is not None and value > maximum):
        suffix = f" 到 {maximum}" if maximum is not None else ""
        raise ConfigError(f"{field} 必须在 {minimum}{suffix} 之间")
    return value


def _number(value: Any, field: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{field} 必须是数字")
    result = float(value)
    if not minimum <= result <= maximum:
        raise ConfigError(f"{field} 必须在 {minimum} 到 {maximum} 之间")
    return result


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{field} 必须是 true 或 false")
    return value


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{field} 不能为空")
    return value.strip()


def _optional_string(value: Any, field: str) -> str | None:
    if value is None or value == "":
        return None
    return _string(value, field)


def _provider(value: Any, field: str) -> str:
    normalized = _string(value, field).lower().replace("_", "-")
    aliases = {
        "codex": "codex",
        "openai": "openai-compatible",
        "gateway": "openai-compatible",
        "openai-compatible": "openai-compatible",
    }
    if normalized not in aliases:
        raise ConfigError(f"{field} 只支持 codex 或 openai-compatible")
    return aliases[normalized]


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise ConfigError(f"找不到配置文件: {config_path}\n先执行: cp config.example.toml config.toml")

    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"config.toml 格式错误: {exc}") from exc

    wechat = _table(data, "wechat")
    raw_groups = wechat.get("groups", [])
    if not isinstance(raw_groups, list) or not all(
        isinstance(item, str) and item.strip() for item in raw_groups
    ):
        raise ConfigError("wechat.groups 必须是非空字符串数组")
    groups = tuple(dict.fromkeys(item.strip() for item in raw_groups))

    if "ai" in data and "codex" in data:
        raise ConfigError("[ai] 和旧版 [codex] 不能同时出现；请只保留 [ai]")
    ai_table_name = "ai" if "ai" in data else "codex"
    codex = _table(data, ai_table_name)
    summary = _table(data, "summary")
    privacy = _table(data, "privacy")
    report = _table(data, "report")
    schedule = _table(data, "schedule")

    output_value = Path(str(report.get("output_dir", "reports"))).expanduser()
    if not output_value.is_absolute():
        output_value = config_path.parent / output_value

    provider = _provider(codex.get("provider", "codex"), f"{ai_table_name}.provider")
    model = _optional_string(codex.get("model"), f"{ai_table_name}.model")
    base_url = _optional_string(codex.get("base_url"), f"{ai_table_name}.base_url")
    if provider == "openai-compatible":
        if not model or "请从" in model:
            raise ConfigError(f"使用中转站时必须在 {ai_table_name}.model 填写后台显示的准确模型名")
        if not base_url or "请从" in base_url:
            raise ConfigError(
                f"使用中转站时必须在 {ai_table_name}.base_url 填写后台提供的 OpenAI Base URL"
            )
        if not base_url.startswith("https://"):
            raise ConfigError(f"{ai_table_name}.base_url 必须使用 https://")

    result = AppConfig(
        path=config_path,
        wechat=WechatConfig(
            command=_string(wechat.get("command", "wechat-cli"), "wechat.command"),
            groups=groups,
            page_size=_positive_int(wechat.get("page_size", 500), "wechat.page_size", maximum=5000),
            max_messages_per_group=_positive_int(
                wechat.get("max_messages_per_group", 5000),
                "wechat.max_messages_per_group",
                maximum=100_000,
            ),
            command_timeout_seconds=_number(
                wechat.get("command_timeout_seconds", 120),
                "wechat.command_timeout_seconds",
                minimum=1,
                maximum=3600,
            ),
        ),
        codex=CodexConfig(
            command=_string(codex.get("command", "codex"), f"{ai_table_name}.command"),
            model=model,
            command_timeout_seconds=_number(
                codex.get("command_timeout_seconds", 600),
                f"{ai_table_name}.command_timeout_seconds",
                minimum=1,
                maximum=3600,
            ),
            provider=provider,
            base_url=base_url,
            api_key_env=_string(
                codex.get("api_key_env", "WECHAT_DAILY_API_KEY"), f"{ai_table_name}.api_key_env"
            ),
            api_key_keychain_service=_string(
                codex.get(
                    "api_key_service",
                    codex.get("api_key_keychain_service", "wechat-group-daily-xuedingtoken"),
                ),
                f"{ai_table_name}.api_key_service",
            ),
            api_key_keychain_account=_optional_string(
                codex.get("api_key_account", codex.get("api_key_keychain_account")),
                f"{ai_table_name}.api_key_account",
            ),
        ),
        summary=SummaryConfig(
            chunk_chars=_positive_int(
                summary.get("chunk_chars", 18_000), "summary.chunk_chars", minimum=2000
            ),
            language=_string(summary.get("language", "简体中文"), "summary.language"),
            custom_instructions=str(summary.get("custom_instructions", "")).strip(),
        ),
        privacy=PrivacyConfig(
            redact_phone=_boolean(privacy.get("redact_phone", True), "privacy.redact_phone"),
            redact_email=_boolean(privacy.get("redact_email", True), "privacy.redact_email"),
            redact_id_card=_boolean(privacy.get("redact_id_card", True), "privacy.redact_id_card"),
            redact_bank_card=_boolean(privacy.get("redact_bank_card", True), "privacy.redact_bank_card"),
        ),
        report=ReportConfig(
            output_dir=output_value.resolve(),
            filename=_string(report.get("filename", "{date}_{group}_微信群日报.md"), "report.filename"),
            save_raw_transcript=_boolean(
                report.get("save_raw_transcript", False), "report.save_raw_transcript"
            ),
            generate_pdf=_boolean(report.get("generate_pdf", False), "report.generate_pdf"),
            generate_image=_boolean(report.get("generate_image", True), "report.generate_image"),
            pdf_max_pages=_positive_int(
                report.get("pdf_max_pages", 2), "report.pdf_max_pages", maximum=5
            ),
        ),
        schedule=ScheduleConfig(
            label=_string(schedule.get("label", "com.local.wechat-group-daily"), "schedule.label"),
            hour=_positive_int(schedule.get("hour", 22), "schedule.hour", minimum=0, maximum=23),
            minute=_positive_int(schedule.get("minute", 0), "schedule.minute", minimum=0, maximum=59),
        ),
    )

    if "{date}" not in result.report.filename or "{group}" not in result.report.filename:
        raise ConfigError("report.filename 必须同时包含 {date} 和 {group}")
    return result
