from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .config import PrivacyConfig


@dataclass(frozen=True)
class RedactionResult:
    lines: tuple[str, ...]
    counts: dict[str, int]


_PATTERNS = {
    "手机号": (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[手机号已隐藏]"),
    "邮箱": (
        re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![\w.-])"),
        "[邮箱已隐藏]",
    ),
    "身份证号": (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[身份证号已隐藏]"),
    "银行卡号": (re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)"), "[银行卡号已隐藏]"),
}


def redact_lines(lines: tuple[str, ...], config: PrivacyConfig) -> RedactionResult:
    enabled = {
        "手机号": config.redact_phone,
        "邮箱": config.redact_email,
        "身份证号": config.redact_id_card,
        "银行卡号": config.redact_bank_card,
    }
    counts: Counter[str] = Counter()
    output: list[str] = []

    for original in lines:
        line = original
        for name, (pattern, replacement) in _PATTERNS.items():
            if not enabled[name]:
                continue
            line, count = pattern.subn(replacement, line)
            counts[name] += count
        output.append(line)
    return RedactionResult(tuple(output), dict(counts))
