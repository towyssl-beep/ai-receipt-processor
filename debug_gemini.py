import sys; sys.stdout.reconfigure(encoding="utf-8")
from parse_receipt import parse_folder
from parse_master import load_master, resolve_user

receipts = parse_folder("입력/영수증")
master = load_master("기준/2026 AI.xlsx")

print("=== GOOGLE PLAY / GEMINI 영수증 ===")
for r in receipts:
    if r.get("merchant_key") in ("GOOGLE PLAY", "GOOGLE"):
        print(f"파일: {r['file']}")
        print(f"  merchant_key: {r.get('merchant_key')}")
        print(f"  account_email: {r.get('account_email')}")
        print(f"  payee: {r.get('payee')}")
        print(f"  krw: {r.get('krw')}")
        print(f"  date_paid: {r.get('date_paid')}")
        user = resolve_user(master, r.get("account_email"), r.get("payee"))
        print(f"  → resolve_user: {user}")
        print()

print("=== 마스터 email_to_user ===")
for e, u in master["email_to_user"].items():
    print(f"  {e} → {u}")

print("=== 마스터 aliases ===")
for k, v in master["aliases"].items():
    print(f"  {k} → {v}")
