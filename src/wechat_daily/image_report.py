"""把 Markdown 日报渲染成精美 HTML，并用本机 Chrome/Edge 截成 PNG。"""

from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

from .errors import WechatDailyError

_SELF_BROWSER_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)


def _md_inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )
    return text


def markdown_to_html(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    body: list[str] = []
    in_table = False
    in_ul = False
    table_header_done = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\|.+\|$", line):
            if not in_table:
                if in_ul:
                    body.append("</ul>")
                    in_ul = False
                body.append('<div class="table-wrap"><table>')
                in_table = True
                table_header_done = False
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.match(r"^:?-+:?$", c.replace(" ", "")) for c in cells):
                i += 1
                continue
            tag = "th" if not table_header_done else "td"
            body.append(
                "<tr>" + "".join(f"<{tag}>{_md_inline(c)}</{tag}>" for c in cells) + "</tr>"
            )
            table_header_done = True
            i += 1
            continue
        if in_table:
            body.append("</table></div>")
            in_table = False

        if line.startswith("# "):
            if in_ul:
                body.append("</ul>")
                in_ul = False
            body.append(f'<header class="hero"><h1>{_md_inline(line[2:])}</h1></header>')
        elif line.startswith("## "):
            if in_ul:
                body.append("</ul>")
                in_ul = False
            body.append(f"<h2>{_md_inline(line[3:])}</h2>")
        elif line.startswith("### "):
            if in_ul:
                body.append("</ul>")
                in_ul = False
            body.append(f"<h3>{_md_inline(line[4:])}</h3>")
        elif line.startswith("---"):
            if in_ul:
                body.append("</ul>")
                in_ul = False
            body.append("<hr/>")
        elif line.startswith("> "):
            if in_ul:
                body.append("</ul>")
                in_ul = False
            body.append(f'<p class="meta">{_md_inline(line[2:])}</p>')
        elif line.startswith("- "):
            if not in_ul:
                body.append("<ul>")
                in_ul = True
            body.append(f"<li>{_md_inline(line[2:])}</li>")
        elif line.strip() == "":
            if in_ul:
                body.append("</ul>")
                in_ul = False
        else:
            if in_ul:
                body.append("</ul>")
                in_ul = False
            body.append(f"<p>{_md_inline(line)}</p>")
        i += 1
    if in_table:
        body.append("</table></div>")
    if in_ul:
        body.append("</ul>")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)}</title>
<style>
  :root {{
    --ink: #1c1915;
    --muted: #6f675d;
    --line: #e7dfd2;
    --paper: #fffdf8;
    --wash: #f4efe6;
    --accent: #0d5c52;
    --accent-soft: #dceeea;
    --shadow: 0 22px 60px rgba(48, 34, 12, 0.10);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    color: var(--ink);
    background:
      radial-gradient(1200px 500px at 10% -10%, #e8f3ef 0%, transparent 55%),
      radial-gradient(900px 420px at 100% 0%, #f7e9d6 0%, transparent 50%),
      linear-gradient(180deg, #efe8dc 0%, var(--wash) 45%, #f6f3ed 100%);
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
    line-height: 1.7;
  }}
  .sheet {{
    width: 920px;
    margin: 28px auto 48px;
    background: var(--paper);
    border: 1px solid var(--line);
    border-radius: 22px;
    overflow: clip;
    box-shadow: var(--shadow);
  }}
  .hero {{
    margin: 0;
    padding: 30px 36px 24px;
    background: linear-gradient(135deg, #0d5c52 0%, #174a6b 58%, #2b3f63 100%);
    color: #fff;
  }}
  .hero h1 {{
    margin: 0;
    font-size: 24px;
    letter-spacing: 0.01em;
    font-weight: 700;
    line-height: 1.4;
    white-space: normal;
    overflow-wrap: anywhere;
    word-break: break-word;
  }}
  .sheet > :not(.hero) {{
    margin-left: 40px;
    margin-right: 40px;
  }}
  .sheet > :last-child {{
    margin-bottom: 36px;
  }}
  h2 {{
    margin: 26px 0 10px;
    font-size: 18px;
    color: var(--accent);
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  h2::before {{
    content: "";
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 0 4px var(--accent-soft);
  }}
  h3 {{
    margin: 18px 0 8px;
    font-size: 15.5px;
    color: #244a44;
  }}
  p, li {{
    font-size: 14.5px;
    margin: 6px 0;
  }}
  p.meta {{
    color: var(--muted);
    font-size: 12.5px;
    background: #f7f2ea;
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 10px 12px;
  }}
  ul {{
    margin: 6px 0 12px;
    padding-left: 1.15em;
  }}
  li {{
    margin: 5px 0;
  }}
  .table-wrap {{
    overflow: auto;
    margin: 12px 0 16px;
    border: 1px solid var(--line);
    border-radius: 12px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13.5px;
  }}
  th, td {{
    padding: 9px 11px;
    border-bottom: 1px solid var(--line);
    text-align: left;
    vertical-align: top;
  }}
  th {{
    background: #f3ebe0;
    font-weight: 700;
  }}
  tr:last-child td {{ border-bottom: none; }}
  code {{
    background: #f1ebe1;
    border-radius: 5px;
    padding: 1px 5px;
    font-size: 0.92em;
  }}
  a {{ color: #0b5cad; word-break: break-all; }}
  hr {{
    border: none;
    border-top: 1px dashed var(--line);
    margin: 22px 0 14px;
  }}
</style>
</head>
<body>
  <div class="sheet" id="sheet">
    {"".join(body)}
  </div>
</body>
</html>
"""


def _find_local_browser() -> tuple[str, str]:
    """返回 (playwright_channel, executable_path)。优先本机 Chrome/Edge，不下载 Chromium。"""
    for path in _SELF_BROWSER_CANDIDATES:
        if Path(path).is_file():
            channel = "chrome" if path.lower().endswith("chrome.exe") else "msedge"
            return channel, path
    chrome = shutil.which("chrome") or shutil.which("msedge")
    if chrome:
        channel = "chrome" if "chrome" in chrome.lower() else "msedge"
        return channel, chrome
    raise WechatDailyError(
        "未找到本机 Chrome/Edge。请安装 Chrome 或 Edge，或把浏览器加入 PATH。"
        "本流程不会下载 Playwright Chromium。"
    )


def write_image_report(markdown_path: Path, content: str | None = None) -> list[Path]:
    """根据 Markdown 生成同目录 HTML + PNG，返回生成的文件路径。"""
    source = markdown_path.expanduser().resolve()
    text = content if content is not None else source.read_text(encoding="utf-8")
    title = source.stem
    html_path = source.with_suffix(".html")
    png_path = source.with_suffix(".png")
    html_path.write_text(markdown_to_html(text, title), encoding="utf-8")

    channel, _executable = _find_local_browser()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise WechatDailyError(
            "缺少 playwright 包。请在项目目录执行: uv pip install playwright"
            "（只需装库，不要执行 playwright install；将使用本机 Chrome/Edge）"
        ) from exc

    try:
        with sync_playwright() as playwright:
            # channel=chrome/msedge 走本机已安装浏览器，不下载 Playwright Chromium
            browser = playwright.chromium.launch(channel=channel, headless=True)
            page = browser.new_page(
                viewport={"width": 1000, "height": 1400},
                device_scale_factor=2,
            )
            page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            page.locator("#sheet").screenshot(path=str(png_path), type="png")
            browser.close()
    except Exception as exc:  # noqa: BLE001 - 转成业务错误
        raise WechatDailyError(f"本机浏览器截图失败（{channel}）: {exc}") from exc

    return [html_path, png_path]
