from __future__ import annotations

import html
import os
import re
import tempfile
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    FrameBreak,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .errors import WechatDailyError

_NAVY = colors.HexColor("#102A43")
_BLUE = colors.HexColor("#1D5F8A")
_PALE_BLUE = colors.HexColor("#EAF3F8")
_INK = colors.HexColor("#243B53")
_MUTED = colors.HexColor("#627D98")
_RULE = colors.HexColor("#D9E2EC")


def _register_fonts() -> tuple[str, str]:
    regular_name = "WechatDailyCJK"
    bold_name = "WechatDailyCJKBold"
    if regular_name in pdfmetrics.getRegisteredFontNames():
        return regular_name, bold_name

    candidates = (
        (
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/msyhbd.ttc"),
        ),
        (
            Path("C:/Windows/Fonts/simhei.ttf"),
            Path("C:/Windows/Fonts/simhei.ttf"),
        ),
        (
            Path("/System/Library/Fonts/STHeiti Light.ttc"),
            Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        ),
        (
            Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
            Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
    )
    for regular_path, bold_path in candidates:
        if not regular_path.is_file() or not bold_path.is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont(regular_name, regular_path, subfontIndex=0))
            pdfmetrics.registerFont(TTFont(bold_name, bold_path, subfontIndex=0))
            return regular_name, bold_name
        except Exception:
            continue

    fallback = "STSong-Light"
    if fallback not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(fallback))
    return fallback, fallback


def _inline_markdown(value: str) -> str:
    value = re.sub(r"\[([^]]+)]\(([^)]+)\)", r"\1 (\2)", value)
    escaped = html.escape(value, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"`(.+?)`", r'<font color="#1D5F8A">\1</font>', escaped)
    return escaped


def _extract_title(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "微信群日报"


def _styles(scale: float, regular: str, bold: str) -> dict[str, ParagraphStyle]:
    return {
        "section": ParagraphStyle(
            "Section",
            fontName=bold,
            fontSize=10.2 * scale,
            leading=12.6 * scale,
            textColor=colors.white,
            backColor=_BLUE,
            borderPadding=(3.2 * scale, 4.5 * scale, 3.2 * scale, 4.5 * scale),
            spaceBefore=4.2 * scale,
            spaceAfter=3.2 * scale,
            keepWithNext=True,
            splitLongWords=True,
        ),
        "subsection": ParagraphStyle(
            "Subsection",
            fontName=bold,
            fontSize=8.9 * scale,
            leading=11.2 * scale,
            textColor=_BLUE,
            spaceBefore=3.3 * scale,
            spaceAfter=1.5 * scale,
            keepWithNext=True,
            splitLongWords=True,
        ),
        "body": ParagraphStyle(
            "Body",
            fontName=regular,
            fontSize=8.15 * scale,
            leading=10.7 * scale,
            textColor=_INK,
            alignment=TA_LEFT,
            spaceAfter=2.5 * scale,
            splitLongWords=True,
            wordWrap="CJK",
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            fontName=regular,
            fontSize=7.95 * scale,
            leading=10.4 * scale,
            textColor=_INK,
            leftIndent=7 * scale,
            firstLineIndent=-6 * scale,
            spaceAfter=1.4 * scale,
            splitLongWords=True,
            wordWrap="CJK",
        ),
        "meta": ParagraphStyle(
            "Meta",
            fontName=regular,
            fontSize=7.25 * scale,
            leading=9.4 * scale,
            textColor=_MUTED,
            backColor=_PALE_BLUE,
            borderPadding=3 * scale,
            spaceBefore=2 * scale,
            spaceAfter=2 * scale,
            splitLongWords=True,
            wordWrap="CJK",
        ),
    }


def _content_flowables(markdown: str, styles: dict[str, ParagraphStyle]) -> list[object]:
    flowables: list[object] = []
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()
        index += 1
        if not line or line == "---" or line.startswith("# "):
            continue
        if line.startswith("|") and line.endswith("|"):
            table_lines = [line]
            while index < len(lines):
                candidate = lines[index].strip()
                if not (candidate.startswith("|") and candidate.endswith("|")):
                    break
                table_lines.append(candidate)
                index += 1
            rows = [[cell.strip() for cell in row.strip("|").split("|")] for row in table_lines]
            if len(rows) >= 3 and all(re.fullmatch(r":?-{3,}:?", cell) for cell in rows[1]):
                headers = rows[0]
                for row in rows[2:]:
                    cells = row + [""] * (len(headers) - len(row))
                    details = [
                        f"{header}：{value}"
                        for header, value in zip(headers[1:], cells[1:], strict=False)
                        if value
                    ]
                    compact = f"**{cells[0]}**"
                    if details:
                        compact += " · " + " · ".join(details)
                    flowables.append(
                        Paragraph(f"• {_inline_markdown(compact)}", styles["bullet"])
                    )
                continue
            for table_line in table_lines:
                flowables.append(Paragraph(_inline_markdown(table_line), styles["body"]))
            continue
        if line.startswith("## "):
            flowables.append(Paragraph(_inline_markdown(line[3:]), styles["section"]))
        elif line.startswith("### "):
            flowables.append(Paragraph(_inline_markdown(line[4:]), styles["subsection"]))
        elif line.startswith("> "):
            flowables.append(Paragraph(_inline_markdown(line[2:]), styles["meta"]))
        elif re.match(r"^[-*+]\s+", line):
            text = re.sub(r"^[-*+]\s+", "", line)
            flowables.append(Paragraph(f"• {_inline_markdown(text)}", styles["bullet"]))
        elif match := re.match(r"^(\d+)[.)]\s+(.+)", line):
            flowables.append(
                Paragraph(f"{match.group(1)}. {_inline_markdown(match.group(2))}", styles["bullet"])
            )
        else:
            flowables.append(Paragraph(_inline_markdown(line), styles["body"]))
    return flowables


def _banner(title: str, regular: str, bold: str, width: float, scale: float) -> Table:
    title_style = ParagraphStyle(
        "PdfTitle",
        fontName=bold,
        fontSize=17.5 * scale,
        leading=21 * scale,
        textColor=colors.white,
        spaceAfter=2 * scale,
        wordWrap="CJK",
    )
    cell = Paragraph(_inline_markdown(title), title_style)
    table = Table([[cell]], colWidths=[width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _NAVY),
                ("BOX", (0, 0), (-1, -1), 0, _NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 8 * scale),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8 * scale),
                ("TOPPADDING", (0, 0), (-1, -1), 6 * scale),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6 * scale),
            ]
        )
    )
    return table


def _build_pdf(path: Path, markdown: str, scale: float) -> int:
    regular, bold = _register_fonts()
    styles = _styles(scale, regular, bold)
    body_flowables = _content_flowables(markdown, styles)
    use_single_column = len(body_flowables) <= 32
    page_width, page_height = A4
    margin_x = 10 * mm
    margin_bottom = 10 * mm
    margin_top = 11 * mm
    gutter = 5 * mm
    available_width = page_width - 2 * margin_x
    column_width = (available_width - gutter) / 2
    available_height = page_height - margin_top - margin_bottom
    title_height = 25 * mm
    title_gap = 3.5 * mm
    first_body_height = available_height - title_height - title_gap

    title_frame = Frame(
        margin_x,
        margin_bottom + first_body_height + title_gap,
        available_width,
        title_height,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="title",
    )
    first_left = Frame(
        margin_x,
        margin_bottom,
        column_width,
        first_body_height,
        leftPadding=0,
        rightPadding=2.5 * mm,
        topPadding=0,
        bottomPadding=0,
        id="first-left",
    )
    first_right = Frame(
        margin_x + column_width + gutter,
        margin_bottom,
        column_width,
        first_body_height,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="first-right",
    )
    later_left = Frame(
        margin_x,
        margin_bottom,
        column_width,
        available_height,
        leftPadding=0,
        rightPadding=2.5 * mm,
        topPadding=0,
        bottomPadding=0,
        id="later-left",
    )
    later_right = Frame(
        margin_x + column_width + gutter,
        margin_bottom,
        column_width,
        available_height,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="later-right",
    )

    single_width = min(166 * mm, available_width)
    single_x = (page_width - single_width) / 2
    first_single = Frame(
        single_x,
        margin_bottom,
        single_width,
        first_body_height,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="first-single",
    )
    later_single = Frame(
        single_x,
        margin_bottom,
        single_width,
        available_height,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="later-single",
    )

    title = _extract_title(markdown)

    def decorate(canvas, doc) -> None:  # type: ignore[no-untyped-def]
        canvas.saveState()
        canvas.setTitle(title)
        canvas.setAuthor("WeChat Group Daily")
        canvas.setStrokeColor(_RULE)
        canvas.setLineWidth(0.5)
        canvas.line(margin_x, 7.2 * mm, page_width - margin_x, 7.2 * mm)
        canvas.setFillColor(_MUTED)
        canvas.setFont(regular, 6.5)
        canvas.drawString(margin_x, 4.5 * mm, "WECHAT GROUP DAILY")
        canvas.drawRightString(page_width - margin_x, 4.5 * mm, f"{doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=margin_x,
        rightMargin=margin_x,
        topMargin=margin_top,
        bottomMargin=margin_bottom,
        title=title,
        author="WeChat Group Daily",
        allowSplitting=True,
        pageCompression=True,
    )
    doc.addPageTemplates(
        [
            PageTemplate(
                id="First",
                frames=(
                    [title_frame, first_single]
                    if use_single_column
                    else [title_frame, first_left, first_right]
                ),
                onPage=decorate,
            ),
            PageTemplate(
                id="Later",
                frames=[later_single] if use_single_column else [later_left, later_right],
                onPage=decorate,
            ),
        ]
    )
    story: list[object] = [
        _banner(title, regular, bold, available_width, scale),
        NextPageTemplate("Later"),
        FrameBreak(),
    ]
    story.extend(body_flowables)
    story.append(Spacer(1, 1))
    doc.build(story)
    return doc.page


def write_pdf_report(path: Path, markdown: str, *, max_pages: int = 2) -> int:
    """Render a compact, human-readable PDF and return its page count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    best: tuple[Path, int] | None = None
    fallback: tuple[Path, int] | None = None
    try:
        for scale in (1.0, 0.94, 0.88):
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{path.stem}.", suffix=".pdf", dir=path.parent
            )
            os.close(descriptor)
            temporary = Path(temporary_name)
            pages = _build_pdf(temporary, markdown, scale)
            if pages == 1:
                if best is not None:
                    best[0].unlink(missing_ok=True)
                if fallback is not None:
                    fallback[0].unlink(missing_ok=True)
                os.replace(temporary, path)
                return pages
            if pages <= max_pages:
                if best is None:
                    best = (temporary, pages)
                else:
                    temporary.unlink(missing_ok=True)
                continue
            if fallback is not None:
                fallback[0].unlink(missing_ok=True)
            fallback = (temporary, pages)

        chosen = best or fallback
        if chosen is not None:
            if best is not None and fallback is not None:
                fallback[0].unlink(missing_ok=True)
            os.replace(chosen[0], path)
            return chosen[1]
    except Exception as exc:
        raise WechatDailyError(f"PDF 生成失败: {exc}") from exc
    finally:
        for candidate in (best, fallback):
            if candidate is not None:
                candidate[0].unlink(missing_ok=True)
    raise WechatDailyError("PDF 生成失败：未产生输出文件")
