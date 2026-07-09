import sys; sys.stdout.reconfigure(encoding="utf-8")
from parse_receipt import parse_folder
from parse_master import load_master, resolve_user

receipts = parse_folder("입력/영수증")
master = load_master("기준/2026 AI.xlsx")

print("=== ANTHROPIC/CLAUDE 영수증 전체 ===")
for r in receipts:
    if r.get("merchant_key") == "ANTHROPIC/CLAUDE":
        user = resolve_user(master, r.get("account_email"), r.get("payee"))
        flag = " ← 미지정" if user == "(미지정)" else ""
        print(f"파일: {r['file']}")
        print(f"  account_email : {r.get('account_email')}")
        print(f"  card_last4    : {r.get('card_last4')}")
        print(f"  usd           : {r.get('usd')}")
        print(f"  date_paid     : {r.get('date_paid')}")
        print(f"  → 사용자      : {user}{flag}")
        print()
