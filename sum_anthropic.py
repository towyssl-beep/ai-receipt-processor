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

print("=== ANTHROPIC/CLAUDE 매칭 건 ===")
total_krw = 0
for p in res["pairs"]:
    r, a = p["receipt"], p["approval"]
    if r.get("merchant_key") == "ANTHROPIC/CLAUDE":
        krw = a.get("krw", 0)
        total_krw += krw
        user = next((an["user"] for an in res["annotations"] if an["file"] == r["file"]), "?")
        print(f"  {r['file'][:40]}")
        print(f"    {user} | ${r.get('usd')} | {krw:,}원 | {r.get('date_paid')}")

print(f"\n합계: {total_krw:,}원")
