import sys
sys.stdout.reconfigure(encoding="utf-8")
from parse_receipt import parse_folder
import os

receipts = parse_folder("입력/영수증")

targets = [
    "Receipt-PATWXM-00002.pdf",
    "내 결제 계정",
    "9891847779657954_20260630",
]

for r in receipts:
    for t in targets:
        if t in r.get("file", ""):
            print(f"파일: {r['file']}")
            for k, v in r.items():
                if k != "file":
                    print(f"  {k}: {v}")
            print()
