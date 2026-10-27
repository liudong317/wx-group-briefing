import pytest

from wechat_daily.config import CodexConfig
from wechat_daily.credentials import resolve_api_key, store_api_key
from wechat_daily.errors import CodexError


def _config() -> CodexConfig:
    return CodexConfig(
        "codex",
        "claude-opus-4-8",
        60,
        provider="openai-compatible",
        base_url="https://xuedingtoken1.com/v1",
        api_key_env="WECHAT_DAILY_TEST_KEY",
        api_key_keychain_service="wechat-group-daily-test",
        api_key_keychain_account="tester",
    )


def test_resolve_api_key_prefers_environment(monkeypatch) -> None:
    monkeypatch.setenv("WECHAT_DAILY_TEST_KEY", "  env-key  ")
    monkeypatch.setattr("wechat_daily.credentials.keyring.get_password", lambda *_args: None)
    assert resolve_api_key(_config()) == "env-key"


def test_store_and_resolve_api_key_with_system_keyring(monkeypatch) -> None:
    stored = {}
    monkeypatch.delenv("WECHAT_DAILY_TEST_KEY", raising=False)
    monkeypatch.setattr(
        "wechat_daily.credentials.keyring.set_password",
        lambda service, account, value: stored.update(
            {"service": service, "account": account, "value": value}
        ),
    )
    monkeypatch.setattr(
        "wechat_daily.credentials.keyring.get_password",
        lambda service, account: stored["value"]
        if (service, account) == (stored["service"], stored["account"])
        else None,
    )

    store_api_key(_config(), "  saved-key  ")
    assert stored == {
        "service": "wechat-group-daily-test",
        "account": "tester",
        "value": "saved-key",
    }
    assert resolve_api_key(_config()) == "saved-key"


def test_missing_api_key_has_cross_platform_command(monkeypatch) -> None:
    monkeypatch.delenv("WECHAT_DAILY_TEST_KEY", raising=False)
    monkeypatch.setattr("wechat_daily.credentials.keyring.get_password", lambda *_args: None)
    with pytest.raises(CodexError, match="set-api-key"):
        resolve_api_key(_config())
