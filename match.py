"""매칭 엔진 (해외+국내 통합).

- USD 영수증(Stripe) ↔ 해외 승인내역 : 카드+가맹점그룹+USD금액+날짜
- KRW 영수증(GCloud/GooglePlay/이미지) ↔ 국내 승인내역 : 가맹점그룹+원화금액+날짜
- 각 승인내역은 1회만 매칭(1:1). 승인내역이 기준(정답지).
- 매칭 결과에 사용자(마스터 엑셀) 결합.
- 안 맞는 영수증/승인내역 모두 표시(완전매칭 점검용).
"""
from datetime import datetime
from parse_master import resolve_user

DATE_TOL = 7


def _d(s):
    s = (s or "").replace(".", "-").strip()
    for fmt in ("%Y-%m-%d",):
        try:
            return datetime.strptime(s[:10], fmt)
        except ValueError:
            pass
    return None


def _amt(r):
    return r.get("usd") if r.get("usd") is not None else r.get("krw")


def _match_pool(receipts, approvals, amount_field, tol=DATE_TOL):
    """amount_field: 'usd' or 'krw'. approvals: 해당 통화 승인내역."""
    used = set()
    pairs, unmatched_r = [], []
    for r in receipts:
        rb = r.get(amount_field)
        rdate = _d(r.get("date_paid"))
        cands = []
        for i, a in enumerate(approvals):
            if i in used or a.get("is_refund"):
                continue
            if a["merchant_key"] != r["merchant_key"]:
                continue
            av = a.get("usd_local") if amount_field == "usd" else a.get("krw")
            if rb is None or av is None:
                continue
            # GOOGLE CLOUD: 크레딧 반영으로 영수증 금액 ≠ 승인금액인 경우가 있어 상대 오차 50% 허용
            if r.get("merchant_key") == "GOOGLE CLOUD":
                rel = abs(av - rb) / max(av, rb) if max(av, rb) > 0 else 0
                if rel > 0.5:
                    continue
            elif abs(av - rb) > 0.01:
                continue
            if r.get("card_last4") and a.get("card_last4") and r["card_last4"] != a["card_last4"]:
                continue
            diff = 0
            adate = _d(a.get("tx_date"))
            if rdate and adate:
                diff = abs((adate - rdate).days)
                if diff > tol:
                    continue
            cands.append((diff, i, a))
        if cands:
            cands.sort(key=lambda x: x[0])
            diff, i, a = cands[0]
            used.add(i)
            pairs.append({"receipt": r, "approval": a, "date_diff": diff})
        else:
            unmatched_r.append(r)
    unmatched_a = [a for i, a in enumerate(approvals)
                   if i not in used and not a.get("is_refund")]
    refunds = [a for a in approvals if a.get("is_refund")]
    return pairs, unmatched_r, unmatched_a, refunds


def match_all(receipts, overseas, domestic, master=None):
    usd_receipts = [r for r in receipts if (r.get("usd") is not None)]
    krw_receipts = [r for r in receipts if (r.get("usd") is None and r.get("krw") is not None)]

    # 해외 카드 PDF에 원화(KRW) 결제가 섞여있는 경우(ex. Google Play) 국내와 함께 처리
    overseas_usd = [a for a in overseas if a.get("currency") != "KRW"]
    overseas_krw = [a for a in overseas if a.get("currency") == "KRW"]
    all_krw_approvals = domestic + overseas_krw

    op, our, oua, oref = _match_pool(usd_receipts, overseas_usd, "usd")
    dp, dur, dua, dref = _match_pool(krw_receipts, all_krw_approvals, "krw")

    pairs = op + dp
    # 사용자 결합 + 표기데이터 생성
    annotations = []
    for p in pairs:
        r, a = p["receipt"], p["approval"]
        if r.get("merchant_key") == "GOOGLE CLOUD":
            user = "회사 공용API"
        else:
            user = resolve_user(master, r.get("account_email"), r.get("payee")) if master else "(미지정)"
        is_overseas = r.get("usd") is not None
        annotations.append({
            "file": r["file"],
            "card_last4": a.get("card_last4") or r.get("card_last4"),
            "user": user,
            "krw": a.get("krw"),
            "usd": r.get("usd"),
            "is_overseas": is_overseas,
            "show_amount": is_overseas,        # 국내는 금액 표기 생략
            "matched": True,
            "merchant_key": r["merchant_key"],
        })
    for r in (our + dur):
        if r.get("merchant_key") == "GOOGLE CLOUD":
            user = "회사 공용API"
        else:
            user = resolve_user(master, r.get("account_email"), r.get("payee")) if master else "(미지정)"
        annotations.append({
            "file": r["file"],
            "card_last4": r.get("card_last4"),
            "user": user,
            "krw": r.get("krw"),
            "usd": r.get("usd"),
            "is_overseas": r.get("usd") is not None,
            "show_amount": r.get("usd") is not None,
            "matched": False,
            "merchant_key": r.get("merchant_key"),
        })
    return {
        "pairs": pairs,
        "annotations": annotations,
        "unmatched_receipts": our + dur,
        "unmatched_approvals": oua + dua,
        "refunds": oref + dref,
        "overseas_pairs": op, "domestic_pairs": dp,
    }


if __name__ == "__main__":
    import sys
    from parse_receipt import parse_folder
    from parse_approval import parse_pdf as parse_os
    from parse_domestic import parse_pdf as parse_dom
    from parse_master import load_master
    rf, master_xlsx = sys.argv[1], sys.argv[2]
    os_pdfs = [f for f in sys.argv[3:] if "(1)" not in f]
    dom_pdfs = [f for f in sys.argv[3:] if "(1)" in f]
    receipts = parse_folder(rf)
    overseas = []
    for f in os_pdfs:
        overseas += parse_os(f)
    domestic = []
    for f in dom_pdfs:
        domestic += parse_dom(f)
    master = load_master(master_xlsx)
    res = match_all(receipts, overseas, domestic, master)
    print(f"매칭 {len(res['pairs'])}건 (해외 {len(res['overseas_pairs'])}, 국내 {len(res['domestic_pairs'])})")
    print(f"미매칭 영수증 {len(res['unmatched_receipts'])} / 미매칭 승인 {len(res['unmatched_approvals'])} / 환불 {len(res['refunds'])}")
    print("\n--- 표기 데이터(영수증 위에 얹을 내용) ---")
    for an in res["annotations"]:
        amt = (f"₩{an['krw']:,}" if an["show_amount"] and an["krw"] else
               ("(국내·원화생략)" if not an["is_overseas"] else "(미매칭)"))
        mk = "" if an["matched"] else " ⚠️미매칭"
        print(f"  {an['file'][:34]:36} card{an['card_last4']} | {an['user']:18} | {amt}{mk}")
