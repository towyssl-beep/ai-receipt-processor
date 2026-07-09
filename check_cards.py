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

API_KEYWORDS = ("auto-recharge", "one-time credit", "api")

for p in res["pairs"]:
    r, a = p["receipt"], p["approval"]
    if r.get("merchant_key") != "ANTHROPIC/CLAUDE":
        continue
    desc = (r.get("description") or "").lower()
    fname = r["file"].lower()
    is_api = any(k in desc for k in API_KEYWORDS) or (desc == "" and "invoice" in fname)
    if not is_api:
        continue
    card_r = r.get("card_last4") or "(없음)"
    card_a = a.get("card_last4") or "(없음)"
    match_mark = "✓" if card_a == "8043" else "✗"
    print(f"{match_mark} {r['file'][:42]}  영수증:{card_r}  승인:{card_a}")
