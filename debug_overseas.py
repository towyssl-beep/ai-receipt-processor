import pdfplumber, re

HEADER_RE = re.compile(
    r"(?P<recv>\d{4}\.\d{2}\.\d{2})\s+\S+\s+"
    r"(?P<card>\d{4}-\d{4}-\*{4}-(?P<last4>\d{4}))\s*"
    r"(?P<txdate>\d{4}\.\d{2}\.\d{2})\s+(?P<appno>\d+)\s*"
    r"\[\d+\]\s+\S+\s+(?P<rest>.*)"
)

for fname in ["입력/승인내역/6571해외 (1).pdf", "입력/승인내역/8043해외 (1).pdf"]:
    print(f"\n=== {fname} ===")
    with pdfplumber.open(fname) as pdf:
        lines = []
        for page in pdf.pages:
            txt = page.extract_text() or ""
            lines.extend(txt.split("\n"))

    matched = [ln for ln in lines if HEADER_RE.search(ln)]
    print(f"헤더 매칭: {len(matched)}건")
    for ln in matched[:3]:
        m = HEADER_RE.search(ln)
        print(f"  last4={m.group('last4')} date={m.group('txdate')} appno={m.group('appno')}")

    print("미매칭 (날짜 있는 줄):")
    for ln in lines:
        if re.search(r"\d{4}\.\d{2}\.\d{2}", ln) and not HEADER_RE.search(ln):
            print(f"  {repr(ln[:120])}")
