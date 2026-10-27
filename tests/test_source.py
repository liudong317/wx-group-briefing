import json
import subprocess
from datetime import date

import pytest

from wechat_daily.config import WechatConfig
from wechat_daily.errors import WechatSourceError
from wechat_daily.source import WechatCliSource


def _config() -> WechatConfig:
    return WechatConfig("fake-wechat", (), 2, 10, 10)


def test_fetch_paginates_and_sorts_chronologically() -> None:
    def runner(command, **_kwargs):
        offset = int(command[command.index("--offset") + 1])
        batches = {
            0: ["[2026-07-22 10:00] 阿甲: 新", "[2026-07-22 11:00] 阿乙: 更新"],
            2: ["[2026-07-22 08:00] 阿甲: 早", "[2026-07-22 09:00] 阿乙: 中"],
            4: [],
        }
        payload = {
            "chat": "测试群",
            "username": "123@chatroom",
            "is_group": True,
            "messages": batches[offset],
            "failures": None,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    result = WechatCliSource(_config(), runner=runner).fetch_group_day("测试群", date(2026, 7, 22))
    assert "08:00" in result.messages[0]
    assert "09:00" in result.messages[1]
    assert "10:00" in result.messages[2]
    assert "11:00" in result.messages[-1]
    assert result.truncated is False


def test_private_chat_is_rejected() -> None:
    def runner(command, **_kwargs):
        payload = {"chat": "某人", "username": "wxid_x", "is_group": False, "messages": []}
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    with pytest.raises(WechatSourceError, match="不是群聊"):
        WechatCliSource(_config(), runner=runner).fetch_group_day("某人", date(2026, 7, 22))
