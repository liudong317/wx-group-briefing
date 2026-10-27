from __future__ import annotations

import getpass
import os

import keyring
from keyring.errors import KeyringError

from .config import CodexConfig
from .errors import CodexError


def credential_account(config: CodexConfig) -> str:
    return config.api_key_keychain_account or getpass.getuser()


def store_api_key(config: CodexConfig, api_key: str) -> None:
    value = api_key.strip()
    if not value:
        raise CodexError("API Key 不能为空")
    try:
        keyring.set_password(
            config.api_key_keychain_service,
            credential_account(config),
            value,
        )
    except KeyringError as exc:
        raise CodexError(f"无法写入系统凭据库: {exc}") from exc


def resolve_api_key(config: CodexConfig) -> str:
    from_env = os.getenv(config.api_key_env, "").strip()
    if from_env:
        return from_env

    try:
        value = keyring.get_password(
            config.api_key_keychain_service,
            credential_account(config),
        )
    except KeyringError as exc:
        raise CodexError(f"无法读取系统凭据库: {exc}") from exc
    if not value or not value.strip():
        raise CodexError(
            f"找不到中转站 API Key；请执行 uv run wechat-daily set-api-key，"
            f"或设置 {config.api_key_env}"
        )
    return value.strip()
