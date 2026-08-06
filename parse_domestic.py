"""국내 우리BC카드 승인내역 파서.

두 가지 형식 지원:
- 표 형식(구형): BC카드 리스트 형태, 카드번호 접두사로 블록 분할
- 매출전표 형식(신형): 비씨카드 매출전표 개별 영수증 형태
"""
import re
import os
import sys
import json
import pdfplumber


def normalize_merchant(name):
    n = name.replace(" ", "")
    if "구글클라우드" in n or "googlecloud" in n.lower():
        return "GOOGLE CLOUD"
    if "구글플레이" in n or "googleplay" in n.lower() or "페이먼트" in n or "이먼트" in n:
        return "GOOGLE PLAY"
    if "구글" in n or "google" in n.lower():
        return "GOOGLE"
    return name.strip()


def parse_pdf(path):
    with pdfplumber.open(path) as pdf:
        lines = []
        for page in pdf.pages:
            txt = page.extract_text() or ""
            lines.extend(txt.split("\n"))

    full = "\n".join(lines)

    if "비씨카드 매출전표" in full:
        return _parse_slip(path, full)
    else:
        return _parse_table(path, full)


def _parse_slip(path, full):
    """신형: 비씨카드 매출전표 개별 영수증 형식."""
    records = []
    bname = os.path.basename(path)

    last4s    = re.findall(r"4101-2020-\*{4}-(\d{4})", full)
    datetimes = re.findall(r"(\d{4})년\s*(\d{2})월\s*(\d{2})일\s*(\d{2})시\s*(\d{2})분", full)
    totals    = re.findall(r"총액\s+([\d,]+)원", full)
    appnos    = re.findall(r"승인번호\s+(\d+)", full)
    # 2열 레이아웃으로 가맹점명 라벨·값이 뒤섞이므로, 문서 전체에서
    # "구글XX" 같은 가맹점 키워드를 위치 순으로 수집하여 승인번호와 1:1 매칭.
    # "구글클라우드코리아-구글클라우드코리"처럼 이름 내부에 하이픈+반복이 있어도
    # \S+ 단위로 한 토큰씩 잡히므로 슬립 1건 = 매치 1개.
    merch_hits = []
    for m in re.finditer(r"구글\S+", full):
        key = normalize_merchant(m.group())
        merch_hits.append((m.start(), key))
    merch_hits.sort(key=lambda x: x[0])
    merchant_keys = [k for _, k in merch_hits]

    n = min(len(last4s), len(datetimes), len(totals), len(appnos))

    for i in range(n):
        y, mo, d, h, mi = datetimes[i]
        tx_date = f"{y}.{mo}.{d}"
        dt_str  = f"{tx_date} {h}:{mi}:00"
        krw     = int(totals[i].replace(",", ""))

        merch_key = merchant_keys[i] if i < len(merchant_keys) else ""

        records.append({
            "source_file": bname,
            "card_last4":  last4s[i],
            "datetime":    dt_str,
            "tx_date":     tx_date,
            "sale_type":   "일시불",
            "krw":         krw,
            "approval_no": appnos[i],
            "merchant":    merch_key,
            "merchant_key": merch_key,
            "is_refund":   False,
            "currency":    "KRW",
        })

    return records


def _parse_table(path, full):
    """구형: BC카드 표 형식."""
    records = []
    bname = os.path.basename(path)

    card_prefix_re = re.compile(r"4101-2020-\*{4}-")
    splits = list(card_prefix_re.finditer(full))
    if not splits:
        return records

    for i, start_m in enumerate(splits):
        block_start = start_m.end()
        block_end   = splits[i + 1].start() if i + 1 < len(splits) else len(full)
        block       = full[block_start:block_end]

        date_m = re.search(r"^\s*(\d{4}\.\d{2}\.\d{2})", block)
        if not date_m:
            continue
        date = date_m.group(1)

        last4_time_m = re.search(r"(?<!\d)(\d{4})\s+(\d{2}:\d{2}:\d{2})(?!\d)", block)
        if not last4_time_m:
            continue
        last4    = last4_time_m.group(1)
        time_str = last4_time_m.group(2)

        appno_m = re.search(r"(?:국내|해외)\s+(\d{6,9})", block)
        appno   = appno_m.group(1) if appno_m else ""

        pre  = block[:last4_time_m.start()]
        amts = re.findall(r"([\d,]+)", pre)
        krw  = None
        for s in reversed(amts):
            v = int(s.replace(",", ""))
            if 1000 <= v <= 10_000_000:
                krw = v
                break
        if not krw:
            continue

        prev_block = full[splits[i - 1].end() if i > 0 else 0:start_m.start()]
        prev_lts   = list(re.finditer(r"(?<!\d)\d{4}\s+\d{2}:\d{2}:\d{2}(?!\d)", prev_block))
        merch_prefix = prev_block[prev_lts[-1].end():].strip() if prev_lts else prev_block[-80:].strip()

        merch_suffix = ""
        if appno_m:
            raw = block[appno_m.end():last4_time_m.start()]
            merch_suffix = re.sub(r"[\d,]+", "", raw).strip()

        merch_raw = (merch_prefix + " " + merch_suffix).strip()
        merch_key = normalize_merchant(merch_raw)
        saletype  = "일시불취소" if "취소" in block else "일시불"

        records.append({
            "source_file": bname,
            "card_last4":  last4,
            "datetime":    f"{date} {time_str}",
            "tx_date":     date,
            "sale_type":   saletype,
            "krw":         krw,
            "approval_no": appno,
            "merchant":    merch_raw,
            "merchant_key": merch_key,
            "is_refund":   "취소" in saletype,
            "currency":    "KRW",
        })

    return records


if __name__ == "__main__":
    for f in sys.argv[1:]:
        recs = parse_pdf(f)
        print(f"\n### {f}: {len(recs)}건")
        for r in recs:
            print(f"  {r['datetime']} | {r['card_last4']} | {r['merchant_key']:12} "
                  f"| {r['krw']:>9,}원 | {r['sale_type']} | 승인 {r['approval_no']}")
        print("합계:", f"{sum(r['krw'] for r in recs):,}원")
