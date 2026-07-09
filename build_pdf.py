"""60% 축소 + 표기(카드뒷자리·사용자·원화) PDF 생성.

- 표기는 영수증 빈 공간(텍스트 없는 가장 큰 가로 밴드)에 배치.
- 글자색: 짙은 파랑. 글꼴: 나눔고딕(있으면) → 없으면 내장 한글 고딕(HYGothic).
- 원본에 표기를 먼저 얹은 뒤 전체를 60%로 축소.
- 국내(원화) 영수증은 금액 생략. 미매칭은 '미매칭' 표시.
"""
import io
import os
import pdfplumber
from pypdf import PdfReader, PdfWriter, PageObject, Transformation
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

SCALE = 0.6
NAVY = (0.09, 0.16, 0.52)     # 짙은 파랑

# 나눔고딕 우선, 없으면 내장 한글 고딕
_NANUM_REG = [
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/nanum/NanumGothic.ttf",
    "C:/Windows/Fonts/NanumGothic.ttf",
    os.path.join(os.path.dirname(__file__), "NanumGothic.ttf"),
]
_NANUM_BOLD = [
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/nanum/NanumGothicBold.ttf",
    "C:/Windows/Fonts/NanumGothicBold.ttf",
    os.path.join(os.path.dirname(__file__), "NanumGothicBold.ttf"),
]


def _register_font():
    """반환 (font_name, is_real_bold). 나눔고딕Bold 우선 → 나눔고딕 → 내장고딕."""
    for p in _NANUM_BOLD:
        if os.path.exists(p):
            try:
                pdfmetrics.registerFont(TTFont("KFONT", p)); return "KFONT", True
            except Exception:
                pass
    for p in _NANUM_REG:
        if os.path.exists(p):
            try:
                pdfmetrics.registerFont(TTFont("KFONT", p)); return "KFONT", False
            except Exception:
                pass
    pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
    return "HYGothic-Medium", False


KFONT, KFONT_BOLD = _register_font()


def _draw_bold(c, x, y, lines, fs, lh):
    """볼드 표기. 실제 볼드폰트면 그대로, 아니면 스트로크로 가짜볼드."""
    t = c.beginText(x, y)
    t.setFont(KFONT, fs)
    t.setFillColorRGB(*NAVY)
    if not KFONT_BOLD:
        t.setStrokeColorRGB(*NAVY)
        t.setTextRenderMode(2)          # fill+stroke = 굵게
        c.setLineWidth(max(0.4, fs * 0.045))
    t.setLeading(lh)
    for ln in lines:
        t.textLine(ln)
    c.drawText(t)


def _ann_lines(ann):
    lines = [f"카드 뒷자리 : {ann.get('card_last4') or '확인필요'}",
             f"사용자 : {ann.get('user') or '(미지정)'}"]
    if ann.get("show_amount") and ann.get("krw"):
        lines.append(f"원화 : {ann['krw']:,}원" +
                     (f"  (${ann['usd']:g})" if ann.get("usd") else ""))
    return lines


def _blank_band(words, ph):
    """텍스트 없는 가장 큰 가로 밴드(top좌표) 반환 (top0, top1). 상단 12%는 제외."""
    occ = sorted((float(w["top"]), float(w["bottom"])) for w in words)
    gaps = []
    cur = ph * 0.12
    for t, b in occ:
        if t > cur:
            gaps.append((cur, t))
        cur = max(cur, b)
    if cur < ph:
        gaps.append((cur, ph))
    if not gaps:
        return (ph * 0.9, ph)
    gaps.sort(key=lambda g: (g[1] - g[0]), reverse=True)
    return gaps[0]


def _overlay_after_scale(path, page_index, w, h, ann):
    """PDF 60% 축소 후 좌표계에 10pt 표기 오버레이 생성 (글씨는 축소 안 됨)."""
    lines = _ann_lines(ann)
    tx_x = w * 0.04
    tx_y = h * (1 - SCALE) - h * 0.03
    try:
        with pdfplumber.open(path) as pdf:
            words = pdf.pages[page_index].extract_words()
        band = _blank_band(words, h)
    except Exception:
        band = (h * 0.86, h)
    top0, top1 = band
    # pdfplumber top-down → PDF y-up → scale+translate 적용
    y_top = (h - top0) * SCALE + tx_y
    y_bot = (h - top1) * SCALE + tx_y
    bh = y_top - y_bot
    pad = bh * 0.12
    fs = 10.0
    lh = fs * 1.5
    n = len(lines)
    block_h = lh * n
    y = y_top - pad - max(0, (bh - 2 * pad - block_h) / 2) - fs

    # x 배치: 밴드가 페이지 상단부(top0 < 40%)에 있으면 오른쪽 여백 사용
    # (Gmail 영수증은 상단 로고 영역이 blank band으로 잡히나 이미지가 있어 텍스트 겹침)
    x_frac = 0.60 if top0 < h * 0.40 else 0.10
    x = tx_x + w * SCALE * x_frac
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    _draw_bold(c, x, y, lines, fs, lh)
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]



def build(receipt_paths, annotations_by_file, out_path):
    writer = PdfWriter()
    for path in receipt_paths:
        fname = os.path.basename(path)
        ann = annotations_by_file.get(fname, {"user": "(미지정)", "matched": False})
        src = PdfReader(path)
        page = src.pages[0]
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        newp = PageObject.create_blank_page(width=w, height=h)
        tx = Transformation().scale(SCALE).translate(w * 0.04, h * (1 - SCALE) - h * 0.03)
        newp.merge_transformed_page(page, tx)           # ① 60% 축소
        newp.merge_page(_overlay_after_scale(path, 0, w, h, ann))  # ② 10pt 글씨
        writer.add_page(newp)
    with open(out_path, "wb") as f:
        writer.write(f)
    return out_path
