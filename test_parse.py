from parse_domestic import parse_pdf as parse_domestic
from parse_approval import parse_pdf as parse_overseas
import glob, os

print("=== 국내 ===")
for f in sorted(glob.glob("입력/승인내역/*.pdf")):
    bn = os.path.basename(f)
    if "국내" in bn:
        recs = parse_domestic(f)
        print(f"{bn}: {len(recs)}건")
        for r in recs:
            print(f"  {r['tx_date']} | {r['card_last4']} | {r['merchant_key']} | {r['krw']:,}원 | 승인 {r['approval_no']}")

print()
print("=== 해외 ===")
for f in sorted(glob.glob("입력/승인내역/*.pdf")):
    bn = os.path.basename(f)
    if "해외" in bn:
        recs = parse_overseas(f)
        print(f"{bn}: {len(recs)}건")
        for r in recs:
            print(f"  {r['tx_date']} | {r['card_last4']} | {r['merchant_key']} | ${r['usd_billed']} | {r['krw']:,}원")
