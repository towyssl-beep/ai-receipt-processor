import sys; sys.stdout.reconfigure(encoding="utf-8")
import glob, os
from parse_receipt import parse_folder
from parse_master import load_master, resolve_user

receipts = parse_folder("입력/영수증")
master = load_master("기준/2026 AI.xlsx")

print("=== D.Lab 이메일 목록 (마스터) ===")
for e, u in master["email_to_user"].items():
    if "D.Lab" in u or "D.lab" in u:
        print(f"  {e} → {u}")

print()
print("=== 전체 영수증 사용자 분포 ===")
from collections import Counter
users = Counter()
for r in receipts:
    if r.get("usd") is not None:
        user = resolve_user(master, r.get("account_email"), r.get("payee"))
        users[user] += 1

for u, cnt in sorted(users.items()):
    print(f"  {u}: {cnt}건")
