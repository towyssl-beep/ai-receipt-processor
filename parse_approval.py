"""해외카드 매출내역(카드 승인내역) PDF 파서.

우리카드(우리BC카드) '해외카드 매출내역' 형식의 PDF에서 거래 레코드를 구조화 추출한다.
각 레코드는 텍스트 줄바꿈으로 여러 줄에 걸쳐 있어, 헤더줄(거래일+카드번호)과
금액줄([840]USD 포함)을 앵커로 잡아 블록 단위로 파싱한다.
"""
import re
import sys
import json
import pdfplumber

# 헤더줄: 접수일자 박*우 카드번호 현지거래일자 승인번호 [840] 미국 ...
HEADER_RE = re.compile(
    r"(?P<recv>\d{4}\.\d{2}\.\d{2})\s+\S+\s+"
    r"(?P<card>\d{4}-\d{4}-\*{4}-(?P<last4>\d{4}))\s*"
    r"(?P<txdate>\d{4}\.\d{2}\.\d{2})\s+(?P<appno>\d+)\s*"
    r"\[\d+\]\s+\S+\s+(?P<rest>.*)"
)
# 금액줄: 현지금액 [840]USD 매출종류 미화매출 적용환율 수수료 단기 청구금액(원)
AMOUNT_RE = re.compile(
    r"(?P<local>-?[\d,]+(?:\.\d+)?)\s*\[\d+\]\S+\s+(?P<type>\S+)\s+"
    r"(?P<usd>-?[\d,]+(?:\.\d+)?)\s+(?P<rate>-?[\d,]+(?:\.\d+)?)\s+"
    r"(?P<fee>-?[\d,]+)\s+(?P<short>-?[\d,]+)\s+(?P<krw>-?[\d,]+)\s*$"
)


def _num(s):
    return float(s.replace(",", ""))


def parse_pdf(path):
    records = []
    with pdfplumber.open(path) as pdf:
        lines = []
        for page in pdf.pages:
            txt = page.extract_text() or ""
            lines.extend(txt.split("\n"))

    # 헤더줄 인덱스 수집
    n = len(lines)
    header_idx = [i for i, ln in enumerate(lines) if HEADER_RE.search(ln)]
    for k, hi in enumerate(header_idx):
        h = HEADER_RE.search(lines[hi])
        end = header_idx[k + 1] if k + 1 < len(header_idx) else n
        block = lines[hi:end]
        # 금액줄 찾기
        amt = None
        merchant_lines = []
        for ln in block[1:]:
            m = AMOUNT_RE.search(ln)
            if m:
                amt = m
                break
            merchant_lines.append(ln)
        if not amt:
            continue
        # 가맹점: 헤더줄 rest(보통 도메인/도시) + 이후 줄에서 업종/한글조각 제거
        rest = h.group("rest").strip()
        # merchant_lines 에는 'OPENAI *CHATGPT 어', 'SUBSCR' 같은 조각 → 합쳐 정리
        merchant_raw = " ".join([rest] + merchant_lines)
        # 업종명 조각 '[5734] 컴퓨터소프트웨', '어' 제거
        merchant = re.sub(r"\[\d+\]\s*컴퓨터소프트웨?어?", "", merchant_raw)
        merchant = re.sub(r"\s+", " ", merchant).strip()
        records.append({
            "merchant_key": normalize_merchant(merchant),
            "card_last4": h.group("last4"),
            "recv_date": h.group("recv"),
            "tx_date": h.group("txdate"),
            "approval_no": h.group("appno"),
            "merchant": merchant,
            "sale_type": amt.group("type"),
            "usd_local": _num(amt.group("local")),
            "usd_billed": _num(amt.group("usd")),
            "rate": _num(amt.group("rate")),
            "krw": int(_num(amt.group("krw"))),
            "is_refund": "취소" in amt.group("type"),
        })
    return records


def normalize_merchant(m):
    """가맹점명을 매칭용 키워드로 정규화."""
    u = m.upper()
    if "ANTHROPIC" in u or "CLAUDE" in u:
        return "ANTHROPIC/CLAUDE"
    if "OPENAI" in u or "CHATGPT" in u:
        return "OPENAI"
    if "SUPABASE" in u:
        return "SUPABASE"
    return u


if __name__ == "__main__":
    files = sys.argv[1:] or ["6571.pdf", "8043.pdf"]
    allrecs = []
    for f in files:
        recs = parse_pdf(f)
        for r in recs:
            r["source_file"] = f
            r["merchant_key"] = normalize_merchant(r["merchant"])
        allrecs.extend(recs)
        print(f"\n### {f}: {len(recs)} 건")
        for r in recs:
            print(f"  {r['tx_date']} | {r['card_last4']} | {r['merchant_key']:16} "
                  f"| ${r['usd_billed']:>8} | {r['krw']:>9,}원 | {r['sale_type']}")
    print(json.dumps(allrecs, ensure_ascii=False, indent=2))
