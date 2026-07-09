import sys; sys.stdout.reconfigure(encoding="utf-8")
from parse_master import load_master

master = load_master("기준/2026 AI.xlsx")
print("=== 기안서 대상 (마스터 엑셀 노란 형광펜) ===")
for t in master["gianseo_targets"]:
    print(f"  {t['user']:28} | {t['ai']} {t['plan']} | {t['email']} | 카드 {t['card']}")
