"""국내 우리BC카드 승인내역 파서 (표형식 리스트 버전).

'BC카드' 형식: 1페이지에 여러 건 표 형태.
pdfplumber 텍스트 추출 시 컬럼이 뒤섞이므로, 카드번호 접두사를 앵커로
블록 단위 파싱.
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
    records = []
    with pdfplumber.open(path) as pdf:
        lines = []
        for page in pdf.pages:
            txt = page.extract_text() or ""
            lines.extend(txt.split("\n"))

    full = re.sub(r"\s+", " ", " ".join(lines)).strip()

    # 카드번호 접두사(마지막 4자리 앞까지)로 레코드 경계 구분
    card_prefix_re = re.compile(r"4101-2020-\*{4}-")
    splits = list(card_prefix_re.finditer(full))
    if not splits:
        return records

    for i, start_m in enumerate(splits):
        block_start = start_m.end()
        block_end = splits[i + 1].start() if i + 1 < len(splits) else len(full)
        block = full[block_start:block_end]

        # 날짜: 카드 접두사 바로 뒤 (YYYY.MM.DD)
        date_m = re.search(r"^\s*(\d{4}\.\d{2}\.\d{2})", block)
        if not date_m:
            continue
        date = date_m.group(1)

        # 카드 뒷4자리 + 시각: "6571 17:22:18"
        last4_time_m = re.search(r"(?<!\d)(\d{4})\s+(\d{2}:\d{2}:\d{2})(?!\d)", block)
        if not last4_time_m:
            continue
        last4 = last4_time_m.group(1)
        time_str = last4_time_m.group(2)

        # 승인번호: "국내 52672633" 또는 "해외 ..."
        appno_m = re.search(r"(?:국내|해외)\s+(\d{6,9})", block)
        appno = appno_m.group(1) if appno_m else ""

        # 승인금액: last4+시각 이전의 마지막 1000원 이상 숫자
        pre = block[:last4_time_m.start()]
        amts = re.findall(r"([\d,]+)", pre)
        krw = None
        for s in reversed(amts):
            v = int(s.replace(",", ""))
            if 1000 <= v <= 10_000_000:
                krw = v
                break
        if not krw:
            continue

        # 가맹점: 이전 레코드 last4+시각 이후 ~ 현재 카드 접두사 이전 텍스트(앞부분)
        #         + 현재 블록의 승인번호 뒤 ~ last4+시각 이전 텍스트(뒷부분)
        prev_block = full[splits[i - 1].end() if i > 0 else 0:start_m.start()]
        prev_lts = list(re.finditer(r"(?<!\d)\d{4}\s+\d{2}:\d{2}:\d{2}(?!\d)", prev_block))
        merch_prefix = prev_block[prev_lts[-1].end():].strip() if prev_lts else prev_block[-80:].strip()

        merch_suffix = ""
        if appno_m:
            raw = block[appno_m.end():last4_time_m.start()]
            merch_suffix = re.sub(r"[\d,]+", "", raw).strip()

        merch_raw = (merch_prefix + " " + merch_suffix).strip()
        merch_key = normalize_merchant(merch_raw)

        saletype = "일시불취소" if "취소" in block else "일시불"

        records.append({
            "source_file": os.path.basename(path),
            "card_last4": last4,
            "datetime": f"{date} {time_str}",
            "tx_date": date,
            "sale_type": saletype,
            "krw": krw,
            "approval_no": appno,
            "merchant": merch_raw,
            "merchant_key": merch_key,
            "is_refund": "취소" in saletype,
            "currency": "KRW",
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
