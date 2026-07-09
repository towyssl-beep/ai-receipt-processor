import sys; sys.stdout.reconfigure(encoding="utf-8")
import glob, os
from parse_receipt import parse_folder
from parse_approval import parse_pdf as parse_overseas
from parse_domestic import parse_pdf as parse_domestic
from parse_master import load_master, resolve_user
from match import match_all

appr = sorted(glob.glob("입력/승인내역/*.pdf"))
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

receipts = parse_folder("입력/영수증")
master = load_master("기준/2026 AI.xlsx")
res = match_all(receipts, overseas, domestic, master)

print("=== 사용자 미지정 항목 ===")
for a in res["annotations"]:
    if a["user"] == "(미지정)":
        print(f"파일: {a['file']}")
        print(f"  merchant_key : {a.get('merchant_key')}")
        print(f"  matched      : {a.get('matched')}")
        print(f"  krw          : {a.get('krw')}")
        print(f"  usd          : {a.get('usd')}")
        print(f"  card_last4   : {a.get('card_last4')}")
        # 원본 영수증에서 email 찾기
        for r in receipts:
            if r.get("file") == a["file"]:
                print(f"  account_email: {r.get('account_email')}")
                print(f"  payee        : {r.get('payee')}")
        print()
