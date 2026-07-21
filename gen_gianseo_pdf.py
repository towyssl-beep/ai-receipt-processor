"""기안서 PDF 생성 (ReportLab) — HWPX와 동일한 데이터로 PDF 직접 출력."""
import io
import os
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                 Paragraph, Spacer, HRFlowable)
from reportlab.lib.styles import ParagraphStyle

_NANUM = [
    "C:/Windows/Fonts/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/nanum/NanumGothic.ttf",
    os.path.join(os.path.dirname(__file__), "NanumGothic.ttf"),
]
_NANUM_BOLD = [
    "C:/Windows/Fonts/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/nanum/NanumGothicBold.ttf",
    os.path.join(os.path.dirname(__file__), "NanumGothicBold.ttf"),
]


def _register():
    for p in _NANUM_BOLD:
        if os.path.exists(p):
            try:
                pdfmetrics.registerFont(TTFont("KF", p))
                pdfmetrics.registerFont(TTFont("KFB", p))
                return "KF", "KFB"
            except Exception:
                pass
    for p in _NANUM:
        if os.path.exists(p):
            try:
                pdfmetrics.registerFont(TTFont("KF", p))
                pdfmetrics.registerFont(TTFont("KFB", p))
                return "KF", "KFB"
            except Exception:
                pass
    pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
    return "HYGothic-Medium", "HYGothic-Medium"


_FONT, _FONT_B = _register()
_NAVY = colors.HexColor("#172484")
_GRAY = colors.HexColor("#555555")
_LINE = colors.HexColor("#CCCCCC")


def _style(name, font=None, size=10, bold=False, color=None, align="LEFT", leading=None):
    return ParagraphStyle(
        name,
        fontName=font or (_FONT_B if bold else _FONT),
        fontSize=size,
        textColor=color or colors.black,
        alignment={"LEFT": 0, "CENTER": 1, "RIGHT": 2}.get(align, 0),
        leading=leading or size * 1.4,
    )


def _para(text, **kw):
    return Paragraph(str(text).replace("\n", "<br/>"), _style("_", **kw))


def _safe(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", s)


def _build_story(it):
    from gen_gianseo_hwpx import item_to_edits, IDX, _desc_to_prods, _split_plan
    edits = item_to_edits(it)

    title    = edits.get(IDX["title"], "기안서").strip()
    body     = edits.get(IDX["body"], "").strip()
    prod1    = edits.get(IDX["prod1"], "")
    prod2    = edits.get(IDX["prod2"], "")
    prod2b   = edits.get(IDX["prod2b"], "")
    prod3    = edits.get(IDX["prod3"], "")
    period   = edits.get(IDX["period"], "")
    unit     = edits.get(IDX["unit"], "")
    user     = edits.get(IDX["user"], "")
    krw_won  = edits.get(IDX["krw_won"], "")
    rate     = edits.get(IDX["rate"], "")
    usd2     = edits.get(IDX["usd2"], "")
    won2     = edits.get(IDX["won2"], "")
    supplier = edits.get(IDX["supplier"], "")

    plan_text = f"{prod2} {prod2b}".strip()

    story = []
    story.append(_para(title, size=14, bold=True, color=_NAVY, align="CENTER"))
    story.append(Spacer(1, 6*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=_NAVY))
    story.append(Spacer(1, 4*mm))
    story.append(_para(body, size=10))
    story.append(Spacer(1, 6*mm))

    # 품목 테이블
    t_data = [
        [_para("품명", bold=True, align="CENTER"),
         _para("구독 플랜", bold=True, align="CENTER"),
         _para("수량", bold=True, align="CENTER"),
         _para("기간", bold=True, align="CENTER"),
         _para("단가", bold=True, align="CENTER"),
         _para("사용자", bold=True, align="CENTER")],
        [_para(prod1, align="CENTER"),
         _para(plan_text, align="CENTER"),
         _para(prod3, align="CENTER"),
         _para(period, align="CENTER"),
         _para(unit, align="CENTER"),
         _para(user, align="CENTER")],
    ]
    col_w = [25*mm, 35*mm, 15*mm, 22*mm, 28*mm, 35*mm]
    tbl = Table(t_data, colWidths=col_w, rowHeights=[8*mm, 12*mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#E8ECF8")),
        ("TEXTCOLOR",   (0, 0), (-1, 0), _NAVY),
        ("GRID",        (0, 0), (-1, -1), 0.5, _LINE),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME",    (0, 0), (-1, -1), _FONT),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 5*mm))

    # 합계 정보
    for line in [krw_won, usd2, won2, rate]:
        if line and line.strip():
            story.append(_para(line.strip(), size=9, color=_GRAY))
    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_LINE))
    story.append(Spacer(1, 3*mm))
    story.append(_para(supplier, size=9, color=_GRAY))

    return story


def generate_pdf(it, out_path):
    """단일 기안서 item → PDF 파일 저장."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    doc.build(_build_story(it))
    with open(out_path, "wb") as f:
        f.write(buf.getvalue())
    return out_path


def generate_all(made, out_dir):
    """made: [(hwpx_path, item), ...] → PDF 목록 반환."""
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for hwpx_path, it in made:
        base = os.path.splitext(os.path.basename(hwpx_path))[0]
        pdf_path = os.path.join(out_dir, base + ".pdf")
        try:
            generate_pdf(it, pdf_path)
            results.append(pdf_path)
        except Exception:
            pass
    return results
