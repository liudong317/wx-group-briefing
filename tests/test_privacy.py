from wechat_daily.config import PrivacyConfig
from wechat_daily.privacy import redact_lines


def test_sensitive_values_are_redacted() -> None:
    config = PrivacyConfig(True, True, True, True)
    result = redact_lines(
        (
            "电话 13800138000，邮箱 foo@example.com",
            "身份证 11010519491231002X，卡号 6222 0200 0000 0000 000",
        ),
        config,
    )
    text = "\n".join(result.lines)
    assert "13800138000" not in text
    assert "foo@example.com" not in text
    assert result.counts == {"手机号": 1, "邮箱": 1, "身份证号": 1, "银行卡号": 1}
