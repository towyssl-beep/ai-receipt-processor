import glob, os, sys
sys.stdout.reconfigure(encoding="utf-8")
from parse_receipt import parse_folder
from parse_approval import parse_pdf as parse_overseas
from parse_domestic import parse_pdf as parse_domestic
from parse_master import load_master
from match import match_all

receipts_dir = "입력/영수증"
approvals_dir = "입력/승인내역"
master = "기준/2026 AI.xlsx"

appr = sorted(glob.glob(os.path.join(approvals_dir, "*.pdf")))
overseas, domestic = [], []
for f in appr:
    bn = os.path.basename(f)
    if "국내" in bn:
        domestic += parse_domestic(f)
    elif "해외" in bn:
        overseas += parse_overseas(f)
    elif "(1)" in bn:
        domestic += parse_domestic(f)
    else:
        overseas += parse_overseas(f)

receipts = parse_folder(receipts_dir)
master_data = load_master(master)
res = match_all(receipts, overseas, domestic, master_data)

print("=== 미매칭 영수증 ===")
for r in res["unmatched_receipts"]:
    print(f"  파일: {r['file']}")
    print(f"  가맹점: {r.get('merchant','?')}  금액: {r.get('amount','?')}  날짜: {r.get('date','?')}")
    print()

print("=== 미매칭 승인내역 ===")
for a in res["unmatched_approvals"]:
    if a.get("currency") == "KRW":
        print(f"  [국내] {a['tx_date']} | {a['card_last4']} | {a['merchant_key']} | {a['krw']:,}원 | 승인 {a['approval_no']}")
    else:
        print(f"  [해외] {a['tx_date']} | {a['card_last4']} | {a['merchant_key']} | ${a.get('usd_billed','?')} | {a['krw']:,}원 | 승인 {a['approval_no']}")
