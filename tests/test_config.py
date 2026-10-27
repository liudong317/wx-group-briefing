from pathlib import Path

import pytest

from wechat_daily.config import load_config
from wechat_daily.errors import ConfigError


def _write_config(path: Path, filename: str = "{date}_{group}.md") -> None:
    path.write_text(
        f"""
[wechat]
groups = ["测试群"]
[codex]
command = "codex"
[summary]
[privacy]
[report]
output_dir = "out"
filename = "{filename}"
[schedule]
""",
        encoding="utf-8",
    )


def test_load_config_resolves_relative_output(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write_config(path)
    config = load_config(path)
    assert config.report.output_dir == (tmp_path / "out").resolve()
    assert config.wechat.groups == ("测试群",)


def test_filename_requires_date_and_group(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write_config(path, filename="report.md")
    with pytest.raises(ConfigError, match="必须同时包含"):
        load_config(path)


def test_multiple_groups_are_supported_and_deduplicated(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write_config(path)
    content = path.read_text(encoding="utf-8").replace(
        'groups = ["测试群"]', 'groups = ["产品群", "AI 群", "产品群"]'
    )
    path.write_text(content, encoding="utf-8")
    assert load_config(path).wechat.groups == ("产品群", "AI 群")


def test_openai_compatible_config_uses_ai_table(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write_config(path)
    content = path.read_text(encoding="utf-8").replace(
        '[codex]\ncommand = "codex"',
        '[ai]\nprovider = "openai-compatible"\n'
        'base_url = "https://gateway.example/v1"\nmodel = "example-model"',
    )
    path.write_text(content, encoding="utf-8")
    config = load_config(path)
    assert config.codex.provider == "openai-compatible"
    assert config.codex.base_url == "https://gateway.example/v1"
    assert config.codex.model == "example-model"


@pytest.mark.parametrize(
    ("base_url", "model", "message"),
    [
        ("", "example-model", "Base URL"),
        ("https://gateway.example/v1", "", "模型名"),
        ("http://gateway.example/v1", "example-model", "https"),
    ],
)
def test_openai_compatible_config_rejects_incomplete_values(
    tmp_path: Path, base_url: str, model: str, message: str
) -> None:
    path = tmp_path / "config.toml"
    _write_config(path)
    content = path.read_text(encoding="utf-8").replace(
        '[codex]\ncommand = "codex"',
        f'[ai]\nprovider = "openai-compatible"\nbase_url = "{base_url}"\nmodel = "{model}"',
    )
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError, match=message):
        load_config(path)


def test_ai_and_legacy_codex_tables_cannot_be_combined(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write_config(path)
    path.write_text(
        path.read_text(encoding="utf-8")
        + '\n[ai]\nprovider = "codex"\ncommand = "codex"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="不能同时出现"):
        load_config(path)


def test_public_example_uses_confirmed_xueding_defaults() -> None:
    example = Path(__file__).resolve().parents[1] / "config.example.toml"
    config = load_config(example)
    assert config.codex.base_url == "https://xuedingtoken1.com/v1"
    assert config.codex.model == "claude-opus-4-8"
