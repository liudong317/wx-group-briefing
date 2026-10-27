class WechatDailyError(RuntimeError):
    """Base error shown to the command-line user."""


class ConfigError(WechatDailyError):
    """Configuration is missing or invalid."""


class WechatSourceError(WechatDailyError):
    """Local WeChat history could not be read."""


class CodexError(WechatDailyError):
    """The configured AI summarizer failed or returned an invalid response."""
