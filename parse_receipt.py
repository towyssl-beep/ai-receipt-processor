"""영수증 파서 (다유형 + 범용 폴백).

유형:
  A) Stripe (Receipt-XXXX.pdf): OpenAI / Anthropic. USD, 카드 뒷4자리 포함.
  B) Google Cloud 명세서 PDF: 원화(₩).
  C) Gmail Google Play 영수증 PDF: 원화(₩), Google One/Gemini.
  D) 이미지(PNG/JPG) 스크린샷: Tesseract OCR → 범용 파싱.
  E) 그 외 모르는 형식: 범용 폴백 추출(금액/날짜/카드/통화/이메일).
★ 원칙: 모르는 형식도 실패하지 말고 추출 → 승인내역과 매칭되는 것만 찾으면 됨.
"""
import re
import sys
import json
import glob
import os
import pdfplumber

import shutil as _shutil
TESSERACT_CMD = (_shutil.which("tesseract")
                 or r"C:\Program Files\Tesseract-OCR\tesseract.exe")

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 1)}
MONTHS.update({m[:3]: v for m, v in list(MONTHS.items())})


def _iso_date(s):
    m = re.match(r"([A-Za-z]+)\s+(\d+),\s+(\d{4})", s)
    if not m:
        return s
    return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"


def _account_email(text):
    emails = re.findall(r"[\w.\-]+@[\w.\-]+", text)
    emails = [e for e in emails if "anthropic" not in e.lower() and "openai" not in e.lower()
              and "google" not in e.lower()]
    return emails[0] if emails else ""


def parse_stripe(text, fname):
    vendor = "Anthropic" if "Anthropic" in text else ("OpenAI" if "OpenAI" in text else "?")
    paid = re.search(r"\$([\d,]+\.\d{2})\s+paid on\s+([A-Za-z]+ \d+, \d{4})", text)
    card = re.search(r"(?:Visa|Mastercard|Amex|Master)\s*-\s*(\d{4})", text)
    rcpt = re.search(r"Receipt number\s+([\d ]+)", text)
    inv = re.search(r"Invoice number\s+(\S+)", text)
    desc = ""
    dm = re.search(r"Description.*?\n(.+)", text)
    if dm:
        line = dm.group(1)
        desc = re.split(r"\s+\d+\s+\$|\s+\$", line)[0].strip()
    return {
        "type": "stripe",
        "file": fname,
        "vendor": vendor,
        "merchant_key": "ANTHROPIC/CLAUDE" if vendor == "Anthropic" else "OPENAI",
        "receipt_no": rcpt.group(1).strip() if rcpt else "",
        "invoice_no": inv.group(1) if inv else "",
        "date_paid": _iso_date(paid.group(2)) if paid else "",
        "usd": float(paid.group(1).replace(",", "")) if paid else None,
        "card_last4": card.group(1) if card else None,
        "account_email": _account_email(text),
        "description": desc,
        "currency": "USD",
    }


def parse_gcloud(text, fname):
    payee = (re.search(r"받는사람\s*\n(\S+)", text) or
             re.search(r"이름\s*\n(\S+)", text))
    final = (re.search(r"최종 잔액\(KRW\)\s*₩([\d,]+)", text) or
             re.search(r"최종 잔액:\s*₩([\d,]+)", text))
    newwork = re.search(r"새 작업 합계\s*₩([\d,]+)", text)
    # 콘솔 화면 형식: "월별 청구: Visa ... −₩59,296"
    payment = re.search(r"월별 청구.*?[−\-]₩([\d,]+)", text)
    period = re.search(r"(\d{4}년 \d+월 \d+일~\d{4}년 \d+월 \d+일)", text)
    # 결제일: 월별 청구 앞 날짜
    date_m = re.search(r"(\d{4})년\s*(\d+)월\s*(\d+)일\s*월별 청구", text)
    date_paid = (f"{date_m.group(1)}-{int(date_m.group(2)):02d}-{int(date_m.group(3)):02d}"
                 if date_m else "")
    # 실결제액: 월별청구 > 새작업합계 순으로 우선
    krw_val = (int(payment.group(1).replace(",", "")) if payment else
               int(newwork.group(1).replace(",", "")) if newwork else None)
    return {
        "type": "gcloud",
        "file": fname,
        "vendor": "Google Cloud",
        "merchant_key": "GOOGLE CLOUD",
        "payee": payee.group(1) if payee else "",
        "period": period.group(1) if period else "",
        "date_paid": date_paid,
        "krw": krw_val,
        "krw_final": int(final.group(1).replace(",", "")) if final else None,
        "account_email": _account_email(text),
        "currency": "KRW",
    }


def _try_kor_date(text):
    """한국어 날짜 "2026년 6월 27일" 또는 "6월 27일" 형식 파싱."""
    m = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", text)
    if m:
        ym = re.search(r"(202\d)", text)
        year = ym.group(1) if ym else "2026"
        return f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return ""


def parse_gmail_play(text, fname):
    email = re.search(r"내\s*계정\s*[:：]\s*(\S+@\S+)", text) or \
        re.search(r"받는사람\s*[:：]\s*(\S+@\S+)", text)
    prod = re.search(r"(Google[^\n(]*\([^\n]*\))", text)
    # 금액: PDF "₩29,000" / OCR "¥#36,000" / OCR ₩→4 "429,000"(=₩29,000) 모두 처리
    # 합계 라인에서 4? 로 ₩→4 OCR 노이즈 제거 후 XX,XXX 또는 XXX,XXX 형식 추출
    krw = (re.search(r"합계[^\n]*?4?(\d{2,3},\d{3})\b", text)
           or re.search(r"매월\s*4?(\d{2,3},\d{3})\b", text)
           or re.search(r"매월\s*[¥₩]\s*([\d,]+)", text)
           or re.search(r"[¥₩]\s*([\d,]+)", text))
    # 카드: "Visa - 1234" / "Visa •••• 1234" / OCR 노이즈 "Visa 1 1234" 등 모두 처리
    card = re.search(r"(?:Visa|VISA|Master|Amex)[^\n]{1,20}?(\d{4})\b", text)
    # 날짜: PDF 형식 "2026. 6. 2." 또는 이미지 OCR 형식 "6월 27일"
    d = re.search(r"주문\s*날짜\s*[:：]\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", text) or \
        re.search(r"\((\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\)", text) or \
        re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", text)
    date_paid = (f"{d.group(1)}-{int(d.group(2)):02d}-{int(d.group(3)):02d}" if d
                 else _try_kor_date(text))
    order = re.search(r"(SOP\.[\d\-\.]+)", text)
    return {
        "type": "gmail_play",
        "file": fname,
        "vendor": "Google Play",
        "merchant_key": "GOOGLE PLAY",
        "product": (prod.group(1).strip() if prod else "Google Play"),
        "date_paid": date_paid,
        "krw": int(krw.group(1).replace(",", "")) if krw else None,
        "card_last4": card.group(1) if card else None,
        "account_email": email.group(1) if email else _account_email(text),
        "order_no": order.group(1) if order else "",
        "currency": "KRW",
    }


def generic_extract(text, fname, source="generic"):
    u = text.lower()
    if "anthropic" in u or "claude" in u:
        mk, vendor = "ANTHROPIC/CLAUDE", "Anthropic"
    elif "openai" in u or "chatgpt" in u:
        mk, vendor = "OPENAI", "OpenAI"
    elif "supabase" in u or "realtime messages" in u or "monthly active users" in u:
        mk, vendor = "SUPABASE", "Supabase"
    elif "solapi" in u:
        mk, vendor = "SOLAPI", "Solapi"
    elif "google cloud" in u or "구글클라우드" in text:
        mk, vendor = "GOOGLE CLOUD", "Google Cloud"
    elif "google play" in u or "구글플레이" in text or "google one" in u or "google ai" in u:
        mk, vendor = "GOOGLE PLAY", "Google"
    elif "google" in u or "구글" in text or "gemini" in u:
        mk, vendor = "GOOGLE", "Google"
    else:
        mk, vendor = "?", "?"
    usd = re.search(r"\$\s?([\d,]+\.\d{2})", text)
    krw = (re.search(r"[₩¥\\]\s*([\d,]{3,})\s*KRW", text) or   # SOLAPI: ₩가 \로 추출
           re.search(r"[₩¥]+\s?([\d,]{3,})", text) or re.search(r"([\d,]{3,})\s*원", text)
           or (re.search(r"\b(\d{2},\d{3})\b", text) if source=="image_ocr" else None))
    card = re.search(r"(?:Visa|Master|Amex|VISA|visa[Cc]ard)\s*[-–(]?\s*[•*\s]*(\d{4})\b", text)
    email = _account_email(text)
    date = ""
    for pat in [r"([A-Za-z]+ \d{1,2}, \d{4})", r"(\d{4})[.\-]\s*(\d{1,2})[.\-]\s*(\d{1,2})"]:
        m = re.search(pat, text)
        if m:
            date = _iso_date(m.group(1)) if m.lastindex == 1 else \
                f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            break
    return {
        "type": source,
        "file": fname,
        "vendor": vendor,
        "merchant_key": mk,
        "date_paid": date,
        "usd": float(usd.group(1).replace(",", "")) if usd else None,
        "krw": int(krw.group(1).replace(",", "")) if krw else None,
        "card_last4": card.group(1) if card else None,
        "account_email": email,
        "currency": "USD" if usd and not krw else ("KRW" if krw else "?"),
        "raw_excerpt": re.sub(r"\s+", " ", text)[:200],
    }


def _classify_and_parse(text, fname):
    if "Receipt number" in text and ("Anthropic" in text or "OpenAI" in text):
        return parse_stripe(text, fname)
    if "Google Play" in text or "구글플레이" in text or "Google One" in text:
        return parse_gmail_play(text, fname)
    if "Google Cloud" in text and ("Statement" in text or "결제 프로필" in text or "최종 잔액" in text):
        return parse_gcloud(text, fname)
    return generic_extract(text, fname)


def _ocr_text(img):
    """PIL 이미지 → OCR 텍스트 (kor+eng 우선, 실패 시 기본값)."""
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    try:
        return pytesseract.image_to_string(img, lang="kor+eng")
    except Exception:
        return pytesseract.image_to_string(img)


def parse_image(path, fname):
    """PNG/JPG 이미지를 Tesseract OCR로 읽어 파싱."""
    try:
        from PIL import Image
        img = Image.open(path)
        text = _ocr_text(img)
        if not text.strip():
            return {"file": fname, "error": "OCR 텍스트 없음"}
        return _classify_and_parse(text, fname)
    except Exception as e:
        return {"file": fname, "error": f"이미지 OCR 실패: {e}"}


def _parse_pdf_with_ocr(path, fname):
    """텍스트 없는 이미지 스캔 PDF를 OCR로 파싱."""
    try:
        text_parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                img = page.to_image(resolution=200).original
                text_parts.append(_ocr_text(img))
        text = "\n".join(text_parts)
        if not text.strip():
            return {"file": fname, "error": "OCR 텍스트 없음 (이미지 PDF)"}
        return _classify_and_parse(text, fname)
    except Exception as e:
        return {"file": fname, "error": f"이미지 PDF OCR 실패: {e}"}


# 파일명으로 계정 이메일을 특정할 수 없을 때 수동 매핑
_FNAME_EMAIL_OVERRIDE = {
    "do-messenger_screenshot_2026-07-06_10_28_56.png": "jongwoo4u@gmail.com",
}


def parse_receipt(path):
    fname = os.path.basename(path)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg"):
        result = parse_image(path, fname)
        if fname in _FNAME_EMAIL_OVERRIDE and not result.get("account_email"):
            result["account_email"] = _FNAME_EMAIL_OVERRIDE[fname]
        return result
    if ext in (".html", ".htm"):
        import html as _h
        raw = open(path, encoding="utf-8", errors="replace").read()
        raw = re.sub(r"<(script|style).*?</\1>", " ", raw, flags=re.S)
        text = _h.unescape(re.sub(r"<[^>]+>", " ", raw))
        return _classify_and_parse(text, fname)
    with pdfplumber.open(path) as pdf:
        pages = pdf.pages
        text = "\n".join((p.extract_text() or "") for p in pages)
        # 2열 레이아웃 등으로 텍스트가 짧게 추출된 경우 단어 위치 기반 재구성
        if len(text.strip()) < 300:
            all_words = []
            for p in pages:
                all_words.extend(p.extract_words(x_tolerance=5, y_tolerance=5) or [])
            if all_words:
                from collections import defaultdict
                rows = defaultdict(list)
                for w in all_words:
                    rows[round(w["top"] / 4)].append(w)
                text = "\n".join(
                    " ".join(w["text"] for w in sorted(row, key=lambda w: w["x0"]))
                    for row in (rows[k] for k in sorted(rows))
                )
    if not text.strip() or len(text.strip()) < 300:
        return _parse_pdf_with_ocr(path, fname)
    return _classify_and_parse(text, fname)


def _dedup_key(r):
    return (r.get("type"), r.get("vendor"), r.get("date_paid"),
            r.get("usd"), r.get("krw"), r.get("card_last4"),
            r.get("receipt_no"), r.get("order_no"))


def parse_folder(folder, dedup=True):
    out = []
    pats = ["*.pdf", "*.html", "*.htm", "*.png", "*.jpg", "*.jpeg"]
    files = []
    for p in pats:
        files += glob.glob(os.path.join(folder, p))
    for f in sorted(set(files)):
        try:
            out.append(parse_receipt(f))
        except Exception as e:
            out.append({"file": os.path.basename(f), "error": str(e)})
    if dedup:
        seen = {}
        deduped = []
        for r in out:
            k = _dedup_key(r)
            if k in seen:
                continue
            seen[k] = True
            deduped.append(r)
        return deduped
    return out


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    for r in parse_folder(folder):
        print(r.get("type"), "|", r.get("merchant_key"), "|", r.get("date_paid"),
              "| usd=", r.get("usd"), "| krw=", r.get("krw"),
              "| card", r.get("card_last4"), "|", r.get("account_email"))
