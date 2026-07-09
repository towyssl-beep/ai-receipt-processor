import sys; sys.stdout.reconfigure(encoding="utf-8")
import glob, os
from parse_receipt import parse_folder
from parse_approval import parse_pdf as parse_overseas
from parse_domestic import parse_pdf as parse_domestic_fn
from parse_master import load_master
from match import match_all

appr = sorted(glob.glob("입력/승인내역/*.pdf"))
overseas, domestic = [], []
for f in appr:
    bn = os.path.basename(f)
    if "국내" in bn:
        domestic += parse_domestic_fn(f)
    elif "해외" in bn:
        overseas += parse_overseas(f)
    elif "(1)" in bn:
        domestic += parse_domestic_fn(f)
    else:
        overseas += parse_overseas(f)

receipts = parse_folder("입력/영수증")
master = load_master("기준/2026 AI.xlsx")
res = match_all(receipts, overseas, domestic, master)

API_KEYWORDS = ("auto-recharge", "one-time credit", "api", "invoice")

receipt_map = {r["file"]: r for r in receipts}

print("=== Claude API 건 ===")
total_usd = 0.0
total_krw = 0

for p in res["pairs"]:
    r, a = p["receipt"], p["approval"]
    if r.get("merchant_key") != "ANTHROPIC/CLAUDE":
        continue
    desc = (r.get("description") or "").lower()
    fname = r["file"].lower()
    is_api = any(k in desc for k in API_KEYWORDS) or desc == "" and "invoice" in fname
    if not is_api:
        continue
    usd = r.get("usd", 0) or 0
    krw = a.get("krw", 0) or 0
    total_usd += usd
    total_krw += krw
    user = next((an["user"] for an in res["annotations"] if an["file"] == r["file"]), "?")
    print(f"  {r['file'][:45]}")
    print(f"    {user} | {r.get('description','(없음)')} | ${usd} → {krw:,}원")

print(f"\n총 합계: ${total_usd:.2f}  /  {total_krw:,}원")
