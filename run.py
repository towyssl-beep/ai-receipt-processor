"""AI 영수증 처리 — 실행 진입점.

VSCode 터미널에서:  python run.py            (config.json + 이번 달 자동)
              또는:  python run.py --period 2026-05

폴더(분리 구조):
  기준/   2026 AI.xlsx, 기안서_템플릿.hwpx   (고정, 거의 안 바뀜)
  입력/영수증/    그 달 영수증                (매달 교체)
  입력/승인내역/  우리카드 승인내역 PDF        (매달 교체, 국내는 파일명에 (1))
  출력/<기간>/    결과물 자동 생성
경로는 config.json 으로 한 번만 설정.
"""
import argparse
import glob
import json
import os
from datetime import datetime

from parse_receipt import parse_folder
from parse_approval import parse_pdf as parse_overseas
from parse_domestic import parse_pdf as parse_domestic
from parse_master import load_master
from match import match_all
import build_pdf
import gen_gianseo_hwpx as G
from fx import load_override

ROOT = os.path.dirname(os.path.abspath(__file__))

DEFAULT_CFG = {
    "receipts": "입력/영수증",
    "approvals": "입력/승인내역",
    "master": "기준/2026 AI.xlsx",
    "template": "기준/기안서_템플릿.hwpx",
    "out": "출력",
    "online": True,
    "fx": "환율.json",
}


def _abs(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def load_config():
    cfg = dict(DEFAULT_CFG)
    p = os.path.join(ROOT, "config.json")
    if os.path.exists(p):
        cfg.update(json.load(open(p, encoding="utf-8")))
    return cfg


def _find(path, folder, ext):
    """지정 파일이 있으면 그대로, 없으면 folder에서 ext 첫 파일 자동탐지."""
    ap = _abs(path)
    if os.path.isfile(ap):
        return ap
    hits = sorted(glob.glob(os.path.join(_abs(folder), f"*{ext}")))
    return hits[0] if hits else ap


def main():
    cfg = load_config()
    ap = argparse.ArgumentParser(description="AI 영수증 처리")
    ap.add_argument("--period", default=datetime.now().strftime("%Y-%m"),
                    help="처리 기간 (기본: 이번 달)")
    ap.add_argument("--offline", action="store_true", help="환율 온라인 조회 끄기")
    args = ap.parse_args()

    receipts_dir = _abs(cfg["receipts"])
    approvals_dir = _abs(cfg["approvals"])
    master = _find(cfg["master"], "기준", ".xlsx")
    template = _find(cfg["template"], "기준", ".hwpx")
    out_dir = os.path.join(_abs(cfg["out"]), args.period)
    fx_path = _abs(cfg.get("fx", "환율.json"))
    use_online = cfg.get("online", True) and not args.offline

    # 입력 점검
    missing = []
    if not os.path.isdir(receipts_dir):
        missing.append(f"영수증 폴더 없음: {receipts_dir}")
    if not os.path.isdir(approvals_dir):
        missing.append(f"승인내역 폴더 없음: {approvals_dir}")
    if not os.path.isfile(master):
        missing.append("마스터 엑셀(.xlsx) 없음 → 기준/ 에 넣으세요")
    if not os.path.isfile(template):
        missing.append("기안서 양식(.hwpx) 없음 → 기준/ 에 넣으세요")
    if missing:
        print("[!] 입력 확인 필요:")
        for m in missing:
            print("   -", m)
        return

    os.makedirs(out_dir, exist_ok=True)

    # 승인내역: '국내' 포함=국내, '해외' 포함=해외, 그 외 '(1)'=국내, 나머지=해외
    appr = sorted(glob.glob(os.path.join(approvals_dir, "*.pdf")))
    overseas, domestic = [], []
    for f in appr:
        basename = os.path.basename(f)
        if "국내" in basename:
            domestic += parse_domestic(f)
        elif "해외" in basename:
            overseas += parse_overseas(f)
        elif "(1)" in basename:
            domestic += parse_domestic(f)
        else:
            overseas += parse_overseas(f)

    receipts = parse_folder(receipts_dir)
    master_data = load_master(master)
    res = match_all(receipts, overseas, domestic, master_data)

    # ─ 선행 점검: 영수증 없는 승인 건 ────────────────────────────────────────
    no_receipt = res["unmatched_approvals"]
    if no_receipt:
        lines = ["=" * 60,
                 "  [!] 아래 승인 건의 영수증이 누락되어 있습니다.",
                 "  영수증을 입력/영수증/ 에 추가한 뒤 다시 실행하세요.",
                 "-" * 60]
        for a in no_receipt:
            date     = a.get("tx_date", "?")
            merchant = a.get("merchant_key") or "?"
            if a.get("currency") == "KRW":
                amt = f"{a.get('krw', 0):,}원  (국내)"
            else:
                usd = a.get("usd_billed", "?")
                amt = f"${usd}  ({a.get('krw', 0):,}원)  (해외)"
            lines.append(f"  {date}  |  {merchant}  |  {amt}")
        lines.append("=" * 60)
        print("\n".join(lines))
        return

    # ① 60% 표기 PDF
    ann = {a["file"]: a for a in res["annotations"]}
    order = sorted(ann, key=lambda f: (not ann[f]["matched"], str(ann[f]["card_last4"]), f))
    rmap = {os.path.basename(p): p for p in glob.glob(os.path.join(receipts_dir, "*"))}
    paths = [rmap[f] for f in order if f in rmap]
    pdf_out = os.path.join(out_dir, f"영수증_60퍼_표기_{args.period}.pdf")
    build_pdf.build(paths, ann, pdf_out)

    # ② 기안서 hwpx
    override = load_override(fx_path) if os.path.exists(fx_path) else {}
    items = G.build_items(res, master_data, override=override, use_online=use_online)
    gdir = os.path.join(out_dir, "기안서")
    made = G.generate(items, template, gdir) if items else []

    # 점검 리포트
    fx_src = {"online": "인터넷 자동조회", "override": "환율.json 직접지정",
              "none": "조회실패(환율.json에 입력 필요)"}
    fx_line = (f"  환율: 1$={items[0]['rate'] or '?'}원  "
               f"({fx_src.get(items[0]['rate_src'], items[0]['rate_src'])})") if items else ""
    n_un = len(res["unmatched_receipts"]) + len(res["unmatched_approvals"])
    n_miss = sum(1 for a in res["annotations"] if a["user"] == "(미지정)")
    L = ["=" * 56, f"  AI 영수증 처리 완료 - {args.period}", "=" * 56,
         f"  영수증 {len(receipts)}건 / 승인내역 해외 {len(overseas)} 국내 {len(domestic)}",
         f"  매칭 {len(res['pairs'])} (해외 {len(res['overseas_pairs'])}, 국내 {len(res['domestic_pairs'])})",
         f"  미매칭 영수증 {len(res['unmatched_receipts'])} / 미매칭 승인 {len(res['unmatched_approvals'])} / 환불 {len(res['refunds'])}",
         f"  기안서 {len(made)}건" + (f" (30만원이상 {sum(1 for _, it in made if it['over_300k'])})" if made else ""),
         "-" * 56, f"  [1] {pdf_out}", f"  [2] 기안서: {gdir} ({len(made)}건)"]
    if fx_line:
        L.append(fx_line)
    if n_un:
        L += ["-" * 56, f"  [!] 미매칭 {n_un}건 -> 회계팀 내역 보완 필요"]
    if n_miss:
        L.append(f"  [!] 사용자 미지정 {n_miss}건 -> 마스터 엑셀에 이메일 추가")
    L.append("=" * 56)
    report = "\n".join(L)
    print(report)
    open(os.path.join(out_dir, f"점검_{args.period}.txt"), "w", encoding="utf-8").write(report)


if __name__ == "__main__":
    main()
