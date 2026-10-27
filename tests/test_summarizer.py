from datetime import date

from wechat_daily.config import SummaryConfig
from wechat_daily.summarizer import DailySummarizer, chunk_lines


class FakeClient:
    def __init__(self):
        self.prompts = []

    def complete(self, system_prompt, user_prompt, *, max_tokens=None):
        self.prompts.append((system_prompt, user_prompt, max_tokens))
        if "完整日报" in user_prompt or "生成日报" in user_prompt:
            return "## 今日概览\n\n- 完成测试"
        return "- 分段事实"


def test_long_history_uses_map_reduce() -> None:
    client = FakeClient()
    config = SummaryConfig(chunk_chars=20, language="简体中文", custom_instructions="")
    result = DailySummarizer(client, config).summarize(
        "测试群", date(2026, 7, 22), ("a" * 15, "b" * 15, "c" * 15)
    )
    assert result.api_calls >= 4
    assert result.markdown.startswith("## 今日概览")


def test_chunk_lines_never_drops_text() -> None:
    lines = ("abc", "d" * 12, "ef")
    chunks = chunk_lines(lines, 5)
    assert "".join(chunks).replace("\n", "") == "".join(lines)


def test_empty_history_does_not_call_api() -> None:
    client = FakeClient()
    result = DailySummarizer(client, SummaryConfig(2000, "简体中文", "")).summarize(
        "测试群", date(2026, 7, 22), ()
    )
    assert result.api_calls == 0
    assert client.prompts == []
