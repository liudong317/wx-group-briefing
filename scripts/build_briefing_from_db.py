# -*- coding: utf-8 -*-
"""从本机 wechat-cli 读库 → 结构化日报 → 参考图风格 HTML/PNG（不调用任何 AI API）。

官方唯一生成器：微信群日报（Quant 等），「需要你留意的」仅统计指向 317 的 @/引用。
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

SELF_ALIASES = ("317", "我", "me")
SELF_DISPLAY = "317"

MSG_PAT = re.compile(
    r"^\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})\]\s*([^:：]+)[:：]\s*(.*)$",
    re.S,
)
URL_RE = re.compile(r"https?://[^\s\)\]>\"']+")
# WeChat @ 后常跟普通空格 / 窄空格 / 不间断空格
AT_SELF_RE = re.compile(r"@(?:317|我|me)(?=$|[\s\u2000-\u200b\u202f\u3000，。！？,.!?:：；;])")
REPLY_SELF_RE = re.compile(r"↳\s*回复\s*(?:317|我|me)\s*[:：]")
REPLY_SELF_ALT_RE = re.compile(r"(?:^|\n)\s*回复\s*(?:317|我|me)\s*[:：]")
QUESTION_MARKERS = (
    "?",
    "？",
    "吗",
    "么",
    "呢",
    "怎么",
    "如何",
    "什么",
    "啥",
    "哪",
    "谁",
    "为何",
    "为啥",
    "可否",
    "能否",
    "是不是",
    "有没有",
    "要不要",
    "好不好",
    "行不行",
    "能不能",
    "可不可以",
)


def find_daily() -> Path:
    here = Path(__file__).resolve().parent.parent
    if (here / "scripts" / "build_briefing_from_db.py").exists():
        return here
    raise SystemExit("project not found: put this script under <repo>/scripts/")


def venv_python(daily: Path) -> Path:
    win = daily / ".venv" / "Scripts" / "python.exe"
    unix = daily / ".venv" / "bin" / "python"
    if win.exists():
        return win
    if unix.exists():
        return unix
    raise SystemExit("未找到项目 .venv，请先 uv sync")


def wechat_cli_exe(daily: Path) -> Path:
    win = daily / ".venv" / "Scripts" / "wechat-cli.exe"
    unix = daily / ".venv" / "bin" / "wechat-cli"
    if win.exists():
        return win
    if unix.exists():
        return unix
    raise SystemExit("未找到 wechat-cli，请先 uv sync")


def fetch_messages(daily: Path, group: str, day: str) -> dict:
    exe = wechat_cli_exe(daily)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [
            str(exe),
            "history",
            group,
            "--limit",
            "1000",
            "--start-time",
            f"{day} 00:00:00",
            "--end-time",
            f"{day} 23:59:59",
            "--format",
            "json",
        ],
        cwd=str(daily),
        env=env,
        capture_output=True,
    )
    if r.returncode != 0:
        raise SystemExit(r.stderr.decode("utf-8", errors="replace")[:1000])
    return json.loads(r.stdout.decode("utf-8"))


def normalize_speaker(speaker: str) -> str:
    speaker = speaker.strip()
    speaker = re.sub(r"[\ue000-\uf8ff]", "", speaker).strip() or "匿名"
    if speaker in SELF_ALIASES:
        return SELF_DISPLAY
    return speaker


def parse_rows(messages: list[str]) -> list[dict]:
    rows = []
    for m in messages:
        match = MSG_PAT.match(m.strip())
        if not match:
            continue
        day, hm, speaker, content = match.groups()
        rows.append(
            {
                "day": day,
                "time": hm,
                "speaker": normalize_speaker(speaker),
                "content": content.strip(),
            }
        )
    return rows


def weekday_cn(d: date) -> str:
    return "一二三四五六日"[d.weekday()]


def extract_links(rows: list[dict]) -> list[dict]:
    """从消息中提取链接卡片：标题 + URL（wechat-cli 现会把 url 附在下一行）。"""
    links: list[dict] = []
    for r in rows:
        c = r["content"].strip()
        urls = [u.rstrip("，。；;,") for u in URL_RE.findall(c)]
        is_card = (
            c.startswith("[链接]")
            or c.startswith("[链接/文件]")
            or c.startswith("[小程序]")
        )
        if not is_card and not urls:
            continue

        title = ""
        if is_card:
            first = c.splitlines()[0]
            title = re.sub(r"^\[(链接(/文件)?|小程序)\]\s*", "", first).strip()
            if title.startswith("http"):
                urls = [title.rstrip("，。；;,")] + urls
                title = ""

        url = urls[0] if urls else ""
        if not title and url:
            title = re.sub(r"^https?://(www\.)?", "", url).split("?")[0][:80] or url
        if not title:
            title = "（未解析标题）"

        links.append(
            {
                "time": r["time"],
                "speaker": r["speaker"],
                "title": title,
                "url": url,
            }
        )

    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for item in links:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        if (not url) and (not title or title in {"（未解析标题）", "未解析标题"}):
            continue
        key = (item["time"], url or title)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _main_text(content: str) -> str:
    """取引用前的正文（不含 ↳ 回复行）。"""
    if "↳" in content:
        return content.split("↳", 1)[0].strip()
    return content.strip()


def _is_question_like(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    return any(m in t for m in QUESTION_MARKERS)


def _points_to_self(content: str) -> tuple[bool, bool]:
    """返回 (has_at, has_reply_quote)。"""
    has_at = bool(AT_SELF_RE.search(content))
    has_reply = bool(REPLY_SELF_RE.search(content) or REPLY_SELF_ALT_RE.search(content))
    return has_at, has_reply


def extract_attentions(rows: list[dict]) -> list[dict]:
    """仅他人消息中 @317/@我/@me，或回复/引用 317（↳ 回复 317: / 回复 我:）。"""
    attentions: list[dict] = []
    for r in rows:
        if r["speaker"] == SELF_DISPLAY:
            continue
        content = r["content"]
        has_at, has_reply = _points_to_self(content)
        if not has_at and not has_reply:
            continue

        main = _main_text(content)
        display = re.sub(r"\s+", " ", main).strip()
        if len(display) > 180:
            display = display[:180] + "…"
        if not display:
            display = re.sub(r"\s+", " ", content).strip()[:180]

        if _is_question_like(main):
            status = "待回应"
        elif has_reply and not _is_question_like(main):
            # 纯引用/回复、没有追问
            status = "无需处理"
        else:
            status = "需留意"

        attentions.append(
            {
                "time": r["time"],
                "speaker": r["speaker"],
                "content": f"{r['speaker']}：{display}",
                "status": status,
            }
        )
    return attentions


def topics_quant() -> tuple[list[dict], list[str], str]:
    topics = [
        {
            "title": "高开低走：祖训应验",
            "tag": "盘面",
            "color": "#dbeafe",
            "time": "09:03 - 10:59",
            "bullets": [
                "开盘前唐某某盼反弹，往事如云报高开；星钧映禾主张高开就跑路做 T。不吃辣给「颜面」标准：指数不跌或超两千家上涨。",
                "destiny 称科技只是小高开；Weird Girl 对比韩国涨到熔断。初爻预感上午冲高套人，下午按进土里——10:03 自嘲「果然高开低走」。",
                "木木大土原统计：今年创业板指高开超 1% 共 28 次，28 次盘中跌破开盘价。科技 ETF 高开两个多点后翻绿；半导体由早盘流入转为流出第一。",
            ],
            "summary": "外围偏强、A 股高开低走成共识；群内把「祖训」当交易纪律，而不是等下午奇迹。",
        },
        {
            "title": "选股、workbuddy 与「2:30 不来了」",
            "tag": "交易",
            "color": "#ffedd5",
            "time": "11:00 - 13:44",
            "bullets": [
                "不吃辣对比 workbuddy 与 DeepSeek Harness，认为后者更好；并晒今日观察票、自称没买。草帽boy 卖银行已赚 1 个点。",
                "陈智猜测：美元加息预期下高层怕资金套现出海，3500 狗队会救、3600–3700 不管、3800 带刹车。",
                "午后 不吃辣 15.73 轻仓宁波动力练手；木木称买啥都没用、准备割了休息。不吃辣判断没放量则两点半没有奇迹，destiny 改口等 3600 再抄一点。",
            ],
            "summary": "午间从工具/选股滑向空仓与抄底位讨论；对「神奇 2:30」的期待明显降温。",
        },
        {
            "title": "宁王电网轮动、德子砸盘与尾盘加速",
            "tag": "个股",
            "color": "#dcfce7",
            "time": "13:45 - 15:35",
            "bullets": [
                "木木留意恩捷抗跌、宁王/电池与电网轮动：拉电池指数动一下，拉电网指数几乎不动。destiny 评国电南瑞为「究极老登」，劝等跌下来再看。",
                "德明利跌约 7%，群内解读为业绩利好出货。燕京啤酒未出三季报先跌停。destiny 提醒不吃辣别在回调小票上做左侧。",
                "尾盘上涨家数掉到约 600；木木先割，星钧映禾称亏两个多点再被尾盘砸。刘熠看「拉宁王」心碎；destiny 称最后十分钟加速下跌。",
            ],
            "summary": "指数靠权重轮动勉强撑着，个股与科技继续受伤；收盘情绪接近「崩盘式下跌」。",
        },
        {
            "title": "底在哪：3300 / 3600 与新和成",
            "tag": "预期",
            "color": "#fce7f3",
            "time": "15:05 - 17:55",
            "bullets": [
                "James 给 10–15% 空间、3300 算合理；刘熠看 3100–3300。destiny 称没银行指数大概也就 3300；木木料明天 3600，高开只会低走。",
                "刘熠用月线 MACD 绿柱映射「恐怖谷」，称沪深 300 约 3500 才是区间，现在约 4050。destiny 觉得 3500「有点恐怖」，也夸股民抗压没极限。",
                "不吃辣问新和成成本，destiny 报 27+ 已减仓，建议 24–25 再考虑，并劝空仓别火中取栗。盘点亏损：不吃辣约 30%，星钧映禾/草帽boy 自称腰斩。",
            ],
            "summary": "抄底位分歧很大；共识更接近「先空仓、等稳定」，而不是今天接飞刀。",
        },
        {
            "title": "融资市、炼丹黑话与社保缺口",
            "tag": "叙事",
            "color": "#e0e7ff",
            "time": "17:16 - 19:49",
            "bullets": [
                "往事如云转发证监会原党委委员王会民受贿 4.36 亿余元一审死缓、终身监禁的链接。刘熠对比恒生/A 股「融资市」与美日「投资市」，称已定投纳指。",
                "不吃辣请教 924 / 炼丹 / 凤队等黑话；草帽boy 用长文拆解，并强调是圈子寓言不是情报。往事如云把炼丹解成化债，钟先生认为就是补养老金缺口。",
                "木木称正儿八经题材没活口，只有无人注意的小微盘在涨；destiny 说散户少、主力才好控盘。陈智收尾：能跑就跑，套住的好票躺平。",
            ],
            "summary": "收工后从盘面滑到制度叙事：融资市、社保缺钱、小票角落行情；交易建议仍是少动。",
        },
    ]
    takeaways = [
        "今日再次高开低走：外围强、A 股软；创业板「高开必破开盘价」的统计被反复拿出当祖训。",
        "个股比指数更痛：科技/德子类业绩票被砸，上涨家数收到约 600；有人盘中割肉、有人轻仓练手。",
        "对明日预期偏空：高开低走、大幅低开才有反弹窗口；新和成等票被明确标了更低的考虑区间。",
        "晚间黑话与社保缺口讨论热闹，但共识仍是「别当真实情报、别火中取栗」。",
    ]
    overview_tpl = (
        "今日主线是高开低走与个股杀跌，穿插宁王/电网轮动、抄底位争论，以及晚间「炼丹」黑话与社保缺口叙事；"
        "活跃发言前三为 {top}。"
    )
    return topics, takeaways, overview_tpl


def topics_opc() -> tuple[list[dict], list[str], str]:
    """得否·OPC交流群 今日归纳（按库内消息）。"""
    topics = [
        {
            "title": "地方监测传闻与群内降温",
            "tag": "舆情",
            "color": "#ffedd5",
            "time": "09:22 - 10:23",
            "bullets": [
                "李帅称县城摸排相关设备用户、并提到苏州采购监测设备的传闻；Marx、石磊等追问规模是否合理。",
                "壬子辰提醒换话题；AAA网站开发张朋与「。。。」强调不信谣不传谣；季浩田调侃或与近期舆论有关。",
                "果子狸称采购通知上周已有、检测细节不清，并指管理更偏向关键机构内部而非普通人；李帅随后表示自己是瞎说的。",
            ],
            "summary": "早间热点偏敏感传闻，群内迅速转向「不信谣不传谣」与范围澄清后降温。",
        },
        {
            "title": "模型可用性：GLM / Claude",
            "tag": "模型",
            "color": "#dbeafe",
            "time": "13:28 - 18:01",
            "bullets": [
                "localhost 问群里有没有在用 GLM；空白菌调侃「还敢用」。",
                "Li 问 Claude 是否对大陆用户放开；localhost 建议自行注册试封禁，并提到对「敌对国家」的表述。",
                "localhost 建议用模型本身、不必绑特定客户端；295 另起话头问「小黄鸭」相关玩法。",
            ],
            "summary": "下午讨论集中在大模型能不能用、怎么用，偏经验分享与风险提示。",
        },
        {
            "title": "得否出镜、证书报考与 A 社 IPO",
            "tag": "企服",
            "color": "#dcfce7",
            "time": "18:26 - 21:31",
            "bullets": [
                "得否发图自称「又来当导师」，并提到澳门公司；多人刷强表示认可。",
                "李帅问人社部「人工智能训练师」怎么报、是否线上；得否答走人工智能产业协会等渠道，考点多在省会（他本人在广州考）。",
                "皆大欢喜 @得否 追问考点；晚间 Omni 提到 A 社拟 IPO 且仍亏损，龚振江称亏损不影响 IPO。",
            ],
            "summary": "晚间转向证书路径与得否经验分享，并以 A 社 IPO 讨论收尾。",
        },
    ]
    takeaways = [
        "早间敏感传闻很快被「不信谣」与范围说明压住，未继续深挖操作细节。",
        "模型侧关心 GLM / Claude 可用性与风控，建议自行验证账号策略。",
        "证书：人工智能训练师可走地方人工智能产业/协会渠道，考点多在省会城市。",
        "收尾出现 A 社 IPO 与亏损话题，群内观点是亏损不必然挡住上市。",
    ]
    overview_tpl = (
        "今日 OPC 群从地方监测传闻降温，转到 GLM/Claude 可用性，"
        "晚间围绕得否的证书报考经验与 A 社 IPO；活跃发言前三为 {top}。"
    )
    return topics, takeaways, overview_tpl


def topics_for_group(group: str) -> tuple[list[dict], list[str], str]:
    if "OPC" in group or "得否" in group:
        return topics_opc()
    if "Quant" in group or "量化" in group:
        return topics_quant()
    # 通用兜底：无手工话题时给空列表，overview 用统计句
    return [], [], "今日共有讨论；活跃发言前三为 {top}。"


def build_briefing(group: str, day: date, rows: list[dict]) -> dict:
    """基于本机消息人工结构化（非 DeepSeek）。"""
    speakers = Counter(r["speaker"] for r in rows)
    links = extract_links(rows)
    attentions = extract_attentions(rows)
    first = rows[0]["time"] if rows else "00:00"
    last = rows[-1]["time"] if rows else "00:00"

    topics, takeaways, overview_tpl = topics_for_group(group)

    top3 = speakers.most_common(3)
    if rows and top3:
        top = "、".join(n for n, _ in top3[:3])
        overview = overview_tpl.format(top=top) if "{top}" in overview_tpl else overview_tpl
    elif rows:
        overview = f"今日共 {len(rows)} 条消息，{len(speakers)} 人发言。"
    else:
        overview = "今日暂无消息。"
        takeaways = takeaways or ["今日暂无消息可归纳。"]

    if not topics and rows:
        # 无专用模板时，用一条总览话题兜底
        topics = [
            {
                "title": "今日讨论概览",
                "tag": "概览",
                "color": "#dbeafe",
                "time": f"{first} - {last}",
                "bullets": [
                    f"共 {len(rows)} 条消息，{len(speakers)} 人发言。",
                    f"发言最多：{top3[0][0]}（{top3[0][1]} 条）。" if top3 else "暂无发言排行。",
                ],
                "summary": overview,
            }
        ]

    return {
        "group": group,
        "day": day.isoformat(),
        "weekday": weekday_cn(day),
        "first": first,
        "last": last,
        "overview": overview,
        "stats": {
            "messages": len(rows),
            "speakers": len(speakers),
            "topics": len(topics),
            "links": len(links),
        },
        "rank": speakers.most_common(10),
        "topics": topics,
        "takeaways": takeaways,
        "attentions": attentions,
        "links": links,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def render_html(brief: dict) -> str:
    max_cnt = brief["rank"][0][1] if brief["rank"] else 1

    def bars() -> str:
        parts = []
        for name, cnt in brief["rank"]:
            pct = max(8, int(cnt / max_cnt * 100))
            parts.append(
                "<div class=\"bar-row\">"
                f"<div class=\"bar-name\">{html.escape(name)}</div>"
                f"<div class=\"bar-track\"><div class=\"bar-fill\" style=\"width:{pct}%\"></div></div>"
                f"<div class=\"bar-cnt\">{cnt}</div>"
                "</div>"
            )
        return "".join(parts)

    def topics() -> str:
        parts = []
        for t in brief["topics"]:
            bullets = "".join(f"<li>{html.escape(b)}</li>" for b in t["bullets"])
            parts.append(
                "<article class=\"topic\">"
                "<div class=\"topic-head\">"
                f"<span class=\"tag\" style=\"background:{t['color']}\">{html.escape(t['tag'])}</span>"
                f"<h3>{html.escape(t['title'])}</h3>"
                f"<span class=\"time\">{html.escape(t['time'])}</span>"
                "</div>"
                f"<ul>{bullets}</ul>"
                f"<div class=\"topic-sum\"><strong>总结</strong>：{html.escape(t['summary'])}</div>"
                "</article>"
            )
        return "".join(parts)

    def takeaways() -> str:
        return "".join(f"<li>{html.escape(x)}</li>" for x in brief["takeaways"])

    def attentions_section() -> str:
        items = brief.get("attentions") or []
        if not items:
            return ""
        n = len(items)
        tip = (
            f"今天检测到 {n} 条明确指向你（{SELF_DISPLAY}）的消息"
            "（@ 或引用/回复你）。可按状态优先处理。"
        )
        rows_html = []
        for a in items:
            rows_html.append(
                "<tr>"
                f"<td>{html.escape(a['time'])}</td>"
                f"<td>{html.escape(a['content'])}</td>"
                f"<td><span class=\"pill\">{html.escape(a['status'])}</span></td>"
                "</tr>"
            )
        body = "".join(rows_html)
        return (
            "<section class=\"card\">"
            "<h2>需要你留意的</h2>"
            f"<p class=\"att-tip\">{html.escape(tip)}</p>"
            "<table>"
            "<thead><tr>"
            "<th style=\"width:70px\">时间</th>"
            "<th>内容</th>"
            "<th style=\"width:90px\">状态</th>"
            "</tr></thead>"
            f"<tbody>{body}</tbody>"
            "</table>"
            "</section>"
        )

    def links() -> str:
        if not brief["links"]:
            return "<p class=\"empty\">今日未解析到可展示链接卡片。</p>"
        parts = []
        for item in brief["links"]:
            title = html.escape(item["title"])
            url = (item.get("url") or "").strip()
            if url:
                esc_url = html.escape(url)
                title_html = (
                    f'<a class="link-name" href="{esc_url}" '
                    f'target="_blank" rel="noopener">{title}</a>'
                )
                url_html = (
                    f'<div class="link-url"><a href="{esc_url}" '
                    f'target="_blank" rel="noopener">{esc_url}</a></div>'
                )
            else:
                title_html = f'<span class="link-name">{title}</span>'
                url_html = '<div class="link-url muted">（库内未带可点击地址）</div>'
            parts.append(
                "<div class=\"link-item\">"
                f"<div class=\"link-meta\">{html.escape(item['time'])} · "
                f"{html.escape(item['speaker'])}</div>"
                f"<div class=\"link-title\">{title_html}</div>"
                f"{url_html}"
                "</div>"
            )
        return "".join(parts)

    s = brief["stats"]
    css = """
  :root {
    --bg: #eef1f6;
    --card: #ffffff;
    --ink: #1f2937;
    --muted: #6b7280;
    --line: #e5e7eb;
    --blue: #3b82f6;
    --blue-dark: #1d4ed8;
    --soft: #f8fafc;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", sans-serif;
    line-height: 1.65;
  }
  .page {
    width: 780px;
    margin: 0 auto;
    padding: 20px 16px 28px;
  }
  .card {
    background: var(--card);
    border-radius: 16px;
    padding: 18px 18px 16px;
    margin-bottom: 14px;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
  }
  .hero h1 {
    margin: 0 0 8px;
    font-size: 24px;
    font-weight: 800;
    letter-spacing: 0.01em;
  }
  .hero .range {
    color: var(--muted);
    font-size: 13px;
    margin-bottom: 10px;
  }
  .hero .overview {
    font-size: 14px;
    color: #334155;
    background: var(--soft);
    border-radius: 12px;
    padding: 12px 14px;
  }
  .stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 14px;
  }
  .stat {
    background: var(--card);
    border-radius: 14px;
    padding: 14px 10px;
    text-align: center;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
  }
  .stat .n {
    font-size: 28px;
    font-weight: 800;
    color: var(--blue-dark);
    line-height: 1.1;
  }
  .stat .l {
    margin-top: 4px;
    font-size: 12px;
    color: var(--muted);
  }
  h2 {
    margin: 0 0 12px;
    font-size: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  h2::before {
    content: "";
    width: 4px;
    height: 16px;
    border-radius: 4px;
    background: var(--blue);
  }
  .bar-row {
    display: grid;
    grid-template-columns: 118px 1fr 36px;
    gap: 8px;
    align-items: center;
    margin: 7px 0;
  }
  .bar-name {
    font-size: 13px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .bar-track {
    height: 10px;
    background: #e8eefc;
    border-radius: 999px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #60a5fa, #2563eb);
    border-radius: 999px;
  }
  .bar-cnt {
    text-align: right;
    font-size: 12px;
    color: var(--muted);
  }
  .topic {
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 12px 14px;
    margin: 0 0 12px;
    background: #fff;
  }
  .topic-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }
  .topic-head h3 {
    margin: 0;
    font-size: 15px;
    flex: 1;
  }
  .tag {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 999px;
    color: #1f2937;
    font-weight: 700;
  }
  .time {
    font-size: 12px;
    color: var(--muted);
  }
  .topic ul {
    margin: 6px 0 8px;
    padding-left: 1.1em;
  }
  .topic li {
    margin: 4px 0;
    font-size: 13.5px;
  }
  .topic-sum {
    background: #f3f4f6;
    border-radius: 10px;
    padding: 10px 12px;
    font-size: 13px;
    color: #374151;
  }
  .att-tip {
    margin: 0 0 12px;
    font-size: 13px;
    color: #475569;
    background: #eff6ff;
    border-radius: 10px;
    padding: 10px 12px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  th, td {
    border-bottom: 1px solid var(--line);
    padding: 9px 8px;
    text-align: left;
    vertical-align: top;
  }
  th {
    background: #f8fafc;
    color: #475569;
    font-weight: 700;
  }
  .pill {
    display: inline-block;
    background: #eff6ff;
    color: #1d4ed8;
    border-radius: 999px;
    padding: 2px 8px;
    font-size: 12px;
  }
  .link-item {
    padding: 10px 0;
    border-bottom: 1px dashed var(--line);
  }
  .link-item:last-child { border-bottom: none; }
  .link-meta {
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 2px;
  }
  .link-title {
    font-size: 14px;
    font-weight: 650;
    word-break: break-word;
  }
  .link-name { color: #1d4ed8; }
  .link-url {
    margin-top: 3px;
    font-size: 12px;
    word-break: break-all;
  }
  .link-url a { color: #64748b; }
  .link-url.muted { color: #94a3b8; }
  a { color: #2563eb; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .footer {
    text-align: center;
    color: var(--muted);
    font-size: 12px;
    padding: 8px 12px 4px;
    line-height: 1.7;
  }
  .empty { color: var(--muted); font-size: 13px; }
"""

    parts = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8"/>',
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>',
        f"<title>{html.escape(brief['group'])} 今日内容总结</title>",
        "<style>",
        css,
        "</style>",
        "</head>",
        "<body>",
        '  <div class="page" id="sheet">',
        '    <section class="card hero">',
        f"      <div class=\"range\">{brief['day']}（周{brief['weekday']}） "
        f"{brief['first']} - {brief['last']}</div>",
        f"      <h1>{html.escape(brief['group'])}｜今日内容总结</h1>",
        f"      <div class=\"overview\">{html.escape(brief['overview'])}</div>",
        "    </section>",
        "",
        '    <section class="stats">',
        f"      <div class=\"stat\"><div class=\"n\">{s['messages']}</div>"
        '<div class="l">条消息</div></div>',
        f"      <div class=\"stat\"><div class=\"n\">{s['speakers']}</div>"
        '<div class="l">人发言</div></div>',
        f"      <div class=\"stat\"><div class=\"n\">{s['topics']}</div>"
        '<div class="l">个话题</div></div>',
        f"      <div class=\"stat\"><div class=\"n\">{s['links']}</div>"
        '<div class="l">个链接</div></div>',
        "    </section>",
        "",
        '    <section class="card">',
        "      <h2>活跃度</h2>",
        f"      {bars()}",
        "    </section>",
        "",
        '    <section class="card">',
        "      <h2>话题</h2>",
        f"      {topics()}",
        "    </section>",
        "",
        '    <section class="card">',
        "      <h2>讨论点回顾与探索</h2>",
        f"      <ul>{takeaways()}</ul>",
        "    </section>",
        "",
        f"    {attentions_section()}",
        "",
        '    <section class="card">',
        "      <h2>今日链接</h2>",
        f"      {links()}",
        "    </section>",
        "",
        '    <div class="footer">',
        "      以上内容由「微信AI助手」群聊日报Skill整理。"
        "如有需求或建议，请联系WX: ziyouxiaoqi123<br/>",
        f"      生成时间：{brief['generated_at']} 中国标准时间",
        "    </div>",
        "  </div>",
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(parts)


def screenshot(daily: Path, html_path: Path, png_path: Path) -> None:
    os.environ["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"
    py = venv_python(daily)
    html_uri = html_path.resolve().as_uri()
    png_str = str(png_path.resolve())

    code_lines = [
        "import os",
        "os.environ['PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD'] = '1'",
        "from playwright.sync_api import sync_playwright",
        "from pathlib import Path",
        f"html = {html_uri!r}",
        f"png = Path({png_str!r})",
        "with sync_playwright() as p:",
        "    browser = p.chromium.launch(channel='chrome', headless=True)",
        "    page = browser.new_page(viewport={'width': 820, 'height': 1400}, device_scale_factor=2)",
        "    page.goto(html, wait_until='networkidle')",
        "    page.locator('#sheet').screenshot(path=str(png), type='png')",
        "    browser.close()",
        "print('png', png.stat().st_size)",
    ]
    code = "\n".join(code_lines)
    r = subprocess.run(
        [str(py), "-c", code],
        cwd=str(daily),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0:
        raise SystemExit(f"screenshot failed: {r.stderr}\n{r.stdout}")
    print(r.stdout.strip())


def render_md(brief: dict) -> str:
    group = brief["group"]
    lines = [
        f"# {group}｜今日内容总结",
        "",
        f"{brief['day']}（周{brief['weekday']}） {brief['first']} - {brief['last']}",
        "",
        brief["overview"],
        "",
        (
            f"- 消息 {brief['stats']['messages']} · 发言 {brief['stats']['speakers']} · "
            f"话题 {brief['stats']['topics']} · 链接 {brief['stats']['links']}"
        ),
        "",
        "## 活跃度",
    ]
    for name, cnt in brief["rank"]:
        lines.append(f"- {name}: {cnt}")
    lines += ["", "## 话题"]
    for t in brief["topics"]:
        lines += [f"### {t['title']}（{t['time']}）", ""]
        for b in t["bullets"]:
            lines.append(f"- {b}")
        lines += ["", f"**总结**：{t['summary']}", ""]
    lines += ["## 讨论点回顾与探索", ""]
    for x in brief["takeaways"]:
        lines.append(f"- {x}")

    attentions = brief.get("attentions") or []
    if attentions:
        n = len(attentions)
        lines += [
            "",
            "## 需要你留意的",
            "",
            f"今天检测到 {n} 条明确指向你（{SELF_DISPLAY}）的消息（@ 或引用/回复你）。",
            "",
        ]
        for a in attentions:
            lines.append(f"- {a['time']}｜{a['content']}｜{a['status']}")

    lines += ["", "## 今日链接", ""]
    for item in brief["links"]:
        if item.get("url"):
            lines.append(
                f"- {item['time']} {item['speaker']}｜[{item['title']}]({item['url']})"
            )
        else:
            lines.append(f"- {item['time']} {item['speaker']}｜{item['title']}")
    lines += [
        "",
        "---",
        "",
        "以上内容由「微信AI助手」群聊日报Skill整理。如有需求或建议，请联系WX: ziyouxiaoqi123",
        f"生成时间：{brief['generated_at']} 中国标准时间",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="本机微信群卡片日报（无 AI）")
    parser.add_argument(
        "--group",
        default="Quant量化交流",
        help='群名，须与微信完全一致，例如 "得否·OPC交流群"',
    )
    parser.add_argument(
        "--day",
        default=None,
        help="日期 YYYY-MM-DD，默认今天",
    )
    args = parser.parse_args()

    daily = find_daily()
    group = args.group
    day = date.fromisoformat(args.day) if args.day else date.today()
    print("fetching", group, day.isoformat())
    raw = fetch_messages(daily, group, day.isoformat())
    rows = parse_rows(raw.get("messages", []))
    print("parsed", len(rows))
    brief = build_briefing(group, day, rows)
    att_n = len(brief.get("attentions") or [])
    print("attentions", att_n)

    reports = daily / "reports"
    reports.mkdir(exist_ok=True)
    stem = f"{day.isoformat()}_{group}_今日内容总结"
    html_path = reports / f"{stem}.html"
    png_path = reports / f"{stem}.png"
    json_path = reports / f"{stem}.json"
    md_path = reports / f"{stem}.md"

    html_path.write_text(render_html(brief), encoding="utf-8")
    json_path.write_text(
        json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path.write_text(render_md(brief), encoding="utf-8")

    screenshot(daily, html_path, png_path)
    print("html", html_path)
    print("png", png_path)
    print("md", md_path)
    print("json", json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
