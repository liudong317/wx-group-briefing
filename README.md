# wx-group-briefing · 微信群卡片简报

本机只读微信 4.x 本地库，把指定群当天的聊天整理成 **HTML / PNG / Markdown** 卡片简报。不调用微信官方 API，默认也不走 AI。

上游编排层来自 [Leobai03/wechat-group-daily](https://github.com/Leobai03/wechat-group-daily)（MIT）；本仓是卡片风格定制，公开仓库名：**wx-group-briefing**。读库依赖 [huohuoer/wechat-cli](https://github.com/huohuoer/wechat-cli)。

## 正式用法（卡片简报）

唯一推荐入口：

```text
scripts/build_briefing_from_db.py
```

```powershell
cd <本仓库>
$env:PYTHONUTF8 = "1"
$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1"
.\.venv\Scripts\python.exe scripts\build_briefing_from_db.py --group "你的群名"
```

产物在 `reports/`（已 gitignore）：

- `*_今日内容总结.html`
- `*_今日内容总结.png`
- `*_今日内容总结.md`
- `*_今日内容总结.json`

「需要你留意的」仅在**别人 @ / 引用你**时出现；没有则整块不渲染。默认识别微信名 `317`（可在脚本里改 `SELF_ALIASES`）。

页脚联系：`WX: ziyouxiaoqi123`。

更细的本机步骤见 [本机部署与使用说明.md](本机部署与使用说明.md)。

## 依赖摆放

本机 `pyproject.toml` 把 `wechat-cli` 指到同级目录（GitHub 直连不稳时用）：

```text
父目录/
├── wx-group-briefing/   # 本仓（本地夹名仍可能是 wechat-group-daily）
└── wechat-cli/
```

```bash
uv sync
# 截图用本机 Chrome，不必再下 Chromium
pip install playwright   # 若 .venv 里还没有
```

微信需已登录。Windows 上 `wechat-cli init` 通常要管理员权限。

## 上游 AI / PDF 路线（可选）

`uv run wechat-daily run` 仍可用：脱敏后调 OpenAI 兼容接口，出 Markdown / PDF。配置见 `config.example.toml`。**不要把 `config.toml` 和 API Key 提交进 Git。**

- [macOS 教程](docs/macOS使用教程.md)
- [Windows 教程](docs/Windows使用教程.md)

## 隐私

- 只读本地库，不发消息、不改库。
- `config.toml`、`reports/`、`logs/` 已排除。
- 公开仓不要放真实群聊截图或日报成品。

## License

[MIT](LICENSE)
