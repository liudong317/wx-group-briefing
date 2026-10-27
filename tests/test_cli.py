import importlib


def test_main_preserves_click_exit_code(monkeypatch) -> None:
    cli_module = importlib.import_module("wechat_daily.cli")
    monkeypatch.setattr(cli_module, "cli", lambda **_kwargs: 1)
    assert cli_module.main() == 1
