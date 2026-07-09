"""신규 구독(연간 기안 미커버) 기안서 .hwpx 자동 생성.

- 제외 대상: _EXCL_EMAILS / _EXCL_PERSONAL / _EXCL_DEPT 에 등록된 계정(연간 기안 커버)
- 일반 항목: 동일 사용자 기준 30만원 미만은 묶음 기안서 (최대 5행)
- Claude API (Auto-recharge, jongwoo4u@gmail.com):
    user = "회사 공용 API", 30만원 미만이면 전체 묶음 기안서 1건
"""
import os
import re
import hwpx_fill
from collections import defaultdict
from datetime import date
from parse_master import resolve_user
from fx import get_rate

# ── 상수 ────────────────────────────────────────────────────────────────────
_CLAUDE_API_EMAIL = "jongwoo4u@gmail.com"
_BUNDLE_LIMIT     = 300_000   # 묶음 기준: 합계 < 300,000원
_MAX_BUNDLE_ROWS  = 5         # 템플릿 최대 행 수 (Row 1 + 4 빈 행)

# ── vendor 자체 제외 ─────────────────────────────────────────────────────────
_EXCL_VENDOR = {"Midjourney"}

# ── 이메일 기반 제외 ─────────────────────────────────────────────────────────
_EXCL_EMAILS = {
    "aumleeai@gmail.com",  "aumleeai2@gmail.com",
    "aumleeai3@gmail.com", "aumleeai4@gmail.com",
    "aumleeax01@aumlee.com", "aumleeax02@aumlee.com",
    "aumleeax03@aumlee.com", "aumleeax04@aumlee.com",
    "aumleeax05@aumlee.com", "aumleeax06@aumlee.com",
    "aumleeax07@aumlee.com", "aumleeax08@aumlee.com",
    "aumleeax09@aumlee.com", "aumleeax10@aumlee.com",
}

# ── 부서/개인별 제외 ─────────────────────────────────────────────────────────
_EXCL_PERSONAL = {
    "박종우": {"OpenAI", "Google Play", "Google", "Google Cloud", "Midjourney"},
    "김은주": {"OpenAI", "Google Play", "Google", "Midjourney"},
    "서동연": {"Anthropic"},
}
_EXCL_DEPT = {
    "설계1사업부 1본부":        {"Anthropic", "Google Play", "Google"},
    "설계1사업부 D.Lab":        {"OpenAI"},
    "해외사업본부":             {"Google Play", "Google"},
    "설계2사업부 1본부":        {"Anthropic", "Google Play", "Google"},
    "설계2사업부 주거사업본부": {"Anthropic", "Google Play", "Google"},
    "비서팀":                   {"OpenAI"},
    "부설연구소":               {"OpenAI"},
}


def _is_excluded(user, vendor):
    for name, vs in _EXCL_PERSONAL.items():
        if name in user and vendor in vs:
            return True
    if user in _EXCL_DEPT and vendor in _EXCL_DEPT[user]:
        return True
    return False


def _is_claude100(it):
    return it.get("vendor") == "Anthropic" and abs((it.get("usd") or 0) - 100.0) < 0.01


def _extract_tier(desc):
    if re.search(r"auto.?recharge|one.?time.?credit|credit.?purchase", desc or "", re.I):
        return "API"
    return ""


def _desc_to_prods(desc, vendor=""):
    """영수증 description → (품명, 구독플랜, 수량)."""
    v_lower = (vendor or "").lower()
    u = (desc or "").strip()

    if u:
        if re.search(r"auto.?recharge", u, re.I):
            return ("Claude", "API", "")
        if re.search(r"claude|max plan|anthropic", u, re.I):
            tier_m = re.search(r"\b(Max|Pro)\b", u, re.I)
            tier = tier_m.group(1).capitalize() if tier_m else ""
            nx_m = re.search(r"(\d+\s*x)", u, re.I)
            prod2 = f"{tier} {nx_m.group(1).replace(' ', '')}" if (tier and nx_m) else tier
            return ("Claude", prod2.strip(), "1")
        if re.search(r"chatgpt|openai", u, re.I):
            tier_m = re.search(r"\b(Plus|Pro|Team)\b", u, re.I)
            prod2 = tier_m.group(1).capitalize() if tier_m else ""
            return ("ChatGPT", prod2, "1")
        if "supabase" in u.lower() or "supabase" in v_lower:
            return ("Supabase", "Pro", "1")
        if "google cloud" in u.lower() or "google cloud" in v_lower:
            return ("Google", "Cloud", "1")

    if "google cloud" in v_lower:
        return ("Google", "Cloud", "1")
    if "google play" in v_lower or vendor == "Google Play":
        return ("Google", "Play", "1")
    if "google" in v_lower:
        return ("Google", "", "1")
    if "supabase" in v_lower:
        return ("Supabase", "Pro", "1")
    if vendor == "Anthropic":
        return ("Claude", "", "1")
    if vendor == "OpenAI":
        return ("ChatGPT", "", "")
    if vendor:
        return (vendor, "", "")
    return ("", "", "")


# ── vendor 표기 ──────────────────────────────────────────────────────────────
_VENDOR_DISPLAY = {
    "Anthropic":    "Claude",
    "Google Cloud": "Google Cloud",
    "Supabase":     "Supabase",
    "OpenAI":       "ChatGPT",
    "Google":       "Google",
    "Google Play":  "Google",
}
_VENDOR_SUPPLIER = {
    "Anthropic":    "Anthropic PBC",
    "Google Cloud": "Google LLC",
    "Supabase":     "Supabase Inc.",
    "OpenAI":       "OpenAI OpCo LLC",
    "Google":       "Google LLC",
    "Google Play":  "Google LLC",
}


def _get_title(vendor, is_api=False):
    if is_api:
        return " Claude API 결제(안)"
    name = _VENDOR_DISPLAY.get(vendor, vendor)
    return f" {name} 구독 결제(안)"


def _get_supplier(vendor):
    name = _VENDOR_SUPPLIER.get(vendor, vendor)
    return f"공급 업체 : {name}"


def _item_label(it):
    """제목/내용용 구독 라벨 (e.g. 'Claude Max 5x')."""
    p1, p2, _ = _desc_to_prods(it.get("desc"), it.get("vendor", ""))
    return f"{p1} {p2}".strip()


# ── 템플릿 hp:t 인덱스 (기안서_템플릿.hwpx, 0-기준, 총 41개) ──────────────
# [0~12]  문서 헤더 / 결재란
# [13]    제목
# [14]    내용(body)
# [15]    공백
# [16]    ■ 구입 품목
# [17~23] 테이블 헤더 (품명/구독/수량/기간/단가/(vat포함)/사용자)
# [24]    Row1 품명   [25] Row1 구독line1  [26] Row1 구독line2
# [27]    Row1 수량   [28] Row1 기간      [29] Row1 기간(1개월)
# [30]    Row1 단가   [31] Row1 사용자
# [32]    합계 KRW   [33] 환율기준  [34] 공백
# [35]    USD금액    [36] 원화금액
# [37~39] 구분 불릿  [40] 공급업체
IDX = dict(
    title=13,     # 제목
    body=14,      # 내용
    prod1=24,     # 품명 (Row 1)
    prod2=25,     # 구독 plan (Row 1 line 1)
    prod2b=26,    # 구독 line 2 — 항상 ""로 초기화
    prod3=27,     # 수량 (Row 1)
    period=28,    # 기간 YYYY. M (Row 1)
    unit=30,      # 단가 (Row 1)
    user=31,      # 사용자 (Row 1)
    krw_won=32,   # 합계 KRW
    rate=33,      # 환율기준
    usd2=35,      # USD 금액
    won2=36,      # 원화 금액
    supplier=40,  # 공급업체
)


def _kdate(iso):
    y, m, d = iso.split("-")
    return y, int(m), int(d)


def _rate_str(it):
    if it.get("rate"):
        return f"({it['asof_y']}.{it['asof_m']}.{it['asof_d']} 환율기준 1$ = {it['rate']:,.0f}원)"
    return "(환율 확인필요)"


# ── 단일 항목 edits ──────────────────────────────────────────────────────────
def _split_plan(p2):
    """구독 플랜 텍스트를 2단락으로 분리. 공백 기준 첫 단어/나머지."""
    if p2 and ' ' in p2:
        a, b = p2.split(' ', 1)
        return a, b
    return p2, ""


def item_to_edits(it):
    vendor = it.get("vendor", "")
    p1, p2, p3 = _desc_to_prods(it.get("desc"), vendor)
    p2a, p2b = _split_plan(p2)

    if it.get("is_krw_only"):
        krw = it["krw"]
        won = f"{krw:,}" if krw is not None else "확인필요"
        return {
            IDX["title"]:   _get_title(vendor),
            IDX["body"]:    f"내       용 : {it['user']} 구독 결제 요청드리오니 검토 후 재가바랍니다.",
            IDX["prod1"]:   p1,
            IDX["prod2"]:   p2a,
            IDX["prod2b"]:  p2b,
            IDX["prod3"]:   p3,
            IDX["period"]:  f"{it['year']}. {it['month']}",
            IDX["unit"]:    f"₩ {won}",
            IDX["user"]:    it["user"],
            IDX["krw_won"]: f"금액 : {won} 원",
            IDX["rate"]:    "",
            IDX["usd2"]:    "",
            IDX["won2"]:    f"원화 : {won}원 ",
            IDX["supplier"]: _get_supplier(vendor),
        }

    krw = it["krw"]
    won = f"{krw:,}" if krw is not None else "확인필요"
    usd_s = f"{it['usd']:g}"
    is_api = it.get("is_api", False)

    body = (f"내       용 : {it['user']} Claude API 결제 요청드리오니 검토 후 재가바랍니다."
            if is_api else
            f"내       용 : {it['user']} 구독 결제 요청드리오니 검토 후 재가바랍니다.")

    return {
        IDX["title"]:   _get_title(vendor, is_api),
        IDX["body"]:    body,
        IDX["prod1"]:   p1,
        IDX["prod2"]:   p2a,
        IDX["prod2b"]:  p2b,
        IDX["prod3"]:   p3,
        IDX["period"]:  f"{it['year']}. {it['month']}",
        IDX["unit"]:    f"$ {usd_s}",
        IDX["user"]:    it["user"],
        IDX["krw_won"]: f"금액 : {won} 원",
        IDX["rate"]:    _rate_str(it),
        IDX["usd2"]:    f"금액 : $ {usd_s} ",
        IDX["won2"]:    f"원화 : {won}원 ",
        IDX["supplier"]: _get_supplier(vendor),
    }


# ── API 묶음 edits ───────────────────────────────────────────────────────────
def _api_bundle_edits(api_items):
    total_usd = sum(it["usd"] for it in api_items)
    total_krw = sum(it.get("krw") or 0 for it in api_items)
    won = f"{total_krw:,}"
    usd_s = f"{total_usd:.2f}"
    it0 = api_items[0]
    return {
        IDX["title"]:   " Claude API 결제(안)",
        IDX["body"]:    "내       용 : 회사 공용 API Claude API 결제 요청드리오니 검토 후 재가바랍니다.",
        IDX["prod1"]:   "Claude",
        IDX["prod2"]:   "API",
        IDX["prod2b"]:  "",   # "API"는 1줄 → 빈 문자열로 centering 트리거
        IDX["prod3"]:   f"{len(api_items)}건",
        IDX["period"]:  f"{it0['year']}. {it0['month']}",
        IDX["unit"]:    f"$ {usd_s}",
        IDX["user"]:    "회사 공용 API",
        IDX["krw_won"]: f"금액 : {won} 원",
        IDX["rate"]:    _rate_str(it0),
        IDX["usd2"]:    f"금액 : $ {usd_s} ",
        IDX["won2"]:    f"원화 : {won}원 ",
        IDX["supplier"]: "공급 업체 : Anthropic PBC",
    }


# ── 묶음 기안서 제목/내용/공급업체 ──────────────────────────────────────────
def _bundle_title(bundle_items):
    labels = [_item_label(it) for it in bundle_items]
    n = len(labels)
    if n == 1:
        return f" {labels[0]} 구독 결제(안)"
    if n == 2:
        return f" {labels[0]} / {labels[1]} 구독 결제(안)"
    return f" {labels[0]} 외 {n - 1}건 구독 결제(안)"


def _bundle_body(user, bundle_items):
    labels = [_item_label(it) for it in bundle_items]
    n = len(labels)
    svc = ", ".join(labels) if n <= 3 else f"{labels[0]} 외 {n - 1}건"
    return f"내       용 : {user} {svc} 구독 결제 요청드리오니 검토 후 재가바랍니다."


def _bundle_suppliers(bundle_items):
    seen, names = set(), []
    for it in bundle_items:
        nm = _VENDOR_SUPPLIER.get(it.get("vendor", ""), it.get("vendor", ""))
        if nm and nm not in seen:
            seen.add(nm); names.append(nm)
    return "공급 업체 : " + " / ".join(names) if names else "공급 업체 : -"


# ── 묶음 edits + extra_rows ─────────────────────────────────────────────────
def _bundle_edits_and_rows(bundle_items):
    it0 = bundle_items[0]
    user = it0["user"]

    total_krw = sum(it.get("krw") or 0 for it in bundle_items)
    total_usd = sum((it.get("usd") or 0) for it in bundle_items)
    won = f"{total_krw:,}"
    it_rate = next((it for it in bundle_items if it.get("rate")), it0)

    p1, p2, p3 = _desc_to_prods(it0.get("desc"), it0.get("vendor", ""))
    p2a, p2b = _split_plan(p2)
    unit_s = (f"$ {it0['usd']:g}" if it0.get("usd")
              else (f"₩ {it0['krw']:,}" if it0.get("krw") else ""))

    edits = {
        IDX["title"]:   _bundle_title(bundle_items),
        IDX["body"]:    _bundle_body(user, bundle_items),
        IDX["prod1"]:   p1,
        IDX["prod2"]:   p2a,
        IDX["prod2b"]:  p2b,
        IDX["prod3"]:   p3,
        IDX["period"]:  f"{it0['year']}. {it0['month']}",
        IDX["unit"]:    unit_s,
        IDX["user"]:    user,
        IDX["krw_won"]: f"금액 : {won} 원",
        IDX["rate"]:    (_rate_str(it_rate) if total_usd else ""),
        IDX["usd2"]:    (f"금액 : $ {total_usd:.2f} " if total_usd else ""),
        IDX["won2"]:    f"원화 : {won}원 ",
        IDX["supplier"]: _bundle_suppliers(bundle_items),
    }

    extra_rows = []
    for it in bundle_items[1:]:
        ep1, ep2, ep3 = _desc_to_prods(it.get("desc"), it.get("vendor", ""))
        eu = (f"$ {it['usd']:g}" if it.get("usd")
              else (f"₩ {it['krw']:,}" if it.get("krw") else ""))
        extra_rows.append({
            "prod1": ep1, "prod2": ep2, "prod3": ep3,
            "period": f"{it['year']}. {it['month']}",
            "unit": eu, "user": user,
        })

    return edits, extra_rows


# ── 묶음 생성 로직 ───────────────────────────────────────────────────────────
def _create_bundles(items_for_user):
    """동일 공급업체 우선, 30만원 미만 greedy 묶음.

    같은 공급업체(vendor)끼리 먼저 그룹화한 뒤, 각 그룹 내에서
    합계 300K 미만이 될 때까지 greedy 묶음.
    부득이 공급업체가 다른 항목이 한 기안서에 묶이면
    _bundle_suppliers 가 공급업체를 빠짐없이 나열한다.
    """
    by_vendor = defaultdict(list)
    for it in items_for_user:
        by_vendor[it.get("vendor", "")].append(it)

    all_bundles = []
    for vendor_items in by_vendor.values():
        bundles, current, total = [], [], 0
        for it in vendor_items:
            krw = it.get("krw") or 0
            if current and total + krw >= _BUNDLE_LIMIT:
                bundles.append(current)
                current, total = [], 0
            current.append(it)
            total += krw
        if current:
            bundles.append(current)
        all_bundles.extend(bundles)
    return all_bundles


# ── 파일 생성 ────────────────────────────────────────────────────────────────
def _safe(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", s)


def _make_individual(it, template_hwpx, out_dir, made):
    edits = item_to_edits(it)
    safe = _safe(it["user"])
    usd  = it.get("usd")
    if it.get("is_krw_only"):
        won_s = f"{it['krw']:,}".replace(",", "_") if it.get("krw") else "0"
        fname = f"기안서_{safe}_GoogleCloud_{won_s}원.hwpx"
    elif it.get("vendor") == "Supabase":
        usd_s = f"{usd:g}".replace(".", "_")
        fname = f"기안서_{safe}_Supabase_{usd_s}불.hwpx"
    elif _is_claude100(it):
        fname = f"기안서_{safe}_Claude_100불.hwpx"
    elif it.get("is_api"):
        usd_s = f"{usd:.2f}".replace(".", "_")
        fname = f"기안서_{safe}_API_{usd_s}불.hwpx"
    elif it["over_300k"]:
        fname = f"기안서_{safe}_{usd:g}불_30만원이상.hwpx"
    else:
        usd_s = f"{usd:g}".replace(".", "_")
        fname = f"기안서_{safe}_{usd_s}불.hwpx"
    out = os.path.join(out_dir, fname)
    hwpx_fill.fill_multi(template_hwpx, out, edits, extra_rows=[])
    made.append((out, it))


def _make_bundle(bundle_items, template_hwpx, out_dir, made):
    if len(bundle_items) == 1:
        _make_individual(bundle_items[0], template_hwpx, out_dir, made)
        return
    edits, extra_rows = _bundle_edits_and_rows(bundle_items)
    safe = _safe(bundle_items[0]["user"])
    n = len(bundle_items)
    total_krw = sum(it.get("krw") or 0 for it in bundle_items)
    won_s = f"{total_krw:,}".replace(",", "_")
    fname = f"기안서_{safe}_묶음{n}건_{won_s}원.hwpx"
    out = os.path.join(out_dir, fname)
    hwpx_fill.fill_multi(template_hwpx, out, edits, extra_rows=extra_rows)
    made.append((out, bundle_items[0]))


# ── 데이터 수집 ──────────────────────────────────────────────────────────────
def build_items(match_result, master, override=None, use_online=True, asof_date=None):
    items = []
    for p in match_result["pairs"]:
        r, a = p["receipt"], p["approval"]

        is_gcloud_krw = (r.get("merchant_key") == "GOOGLE CLOUD" and r.get("usd") is None)
        if r.get("usd") is None and not is_gcloud_krw:
            continue

        vendor = r.get("vendor", "")
        desc   = r.get("description") or ""

        if vendor in _EXCL_VENDOR:
            continue

        if is_gcloud_krw:
            user       = "회사 공용API"
            krw_charge = a.get("krw")
            tx_date    = a.get("tx_date", "") or ""
            y  = tx_date[:4] if len(tx_date) >= 4 else "2026"
            mo = int(tx_date[5:7]) if len(tx_date) >= 7 else 6
            d  = int(tx_date[8:10]) if len(tx_date) >= 10 else 1
            asof = asof_date or date.today().isoformat()
            ay, am, ad = asof.split("-")
            items.append({
                "user": user, "vendor": "Google Cloud",
                "usd": None, "krw": krw_charge,
                "rate": None, "rate_src": None,
                "year": y, "month": mo, "day": d,
                "tier": "", "is_api": False, "is_krw_only": True,
                "desc": desc,
                "asof_y": ay, "asof_m": int(am), "asof_d": int(ad),
                "date_paid": tx_date,
                "over_300k": (krw_charge or 0) >= 300000,
                "receipt_file": r["file"],
            })
            continue

        usd     = r["usd"]
        tier    = _extract_tier(desc)
        is_api  = (tier == "API") or (not desc and "invoice" in r.get("file", "").lower())
        email   = (r.get("account_email") or "").lower().strip()

        if email in _EXCL_EMAILS:
            continue

        if is_api and r.get("account_email") == _CLAUDE_API_EMAIL:
            user = "회사 공용 API"
        elif r.get("merchant_key") == "GOOGLE CLOUD":
            user = "회사 공용API"
        else:
            user = resolve_user(master, r.get("account_email"), r.get("payee"))

        if _is_excluded(user, vendor):
            continue

        asof = asof_date or date.today().isoformat()
        rate, src = get_rate(asof, override, fallback=None, use_online=use_online)
        krw  = round(usd * rate) if rate else None
        ay, am, ad = asof.split("-")
        y, mo, d = _kdate(r["date_paid"]) if r.get("date_paid") else ("2026", 6, 1)

        items.append({
            "user": user, "vendor": vendor, "usd": usd,
            "rate": rate, "rate_src": src, "krw": krw,
            "year": y, "month": mo, "day": d,
            "tier": tier, "is_api": is_api, "desc": desc,
            "asof_y": ay, "asof_m": int(am), "asof_d": int(ad),
            "date_paid": r.get("date_paid"),
            "over_300k": (krw or 0) >= 300000,
            "receipt_file": r["file"],
        })
    return items


# ── 메인 생성 ────────────────────────────────────────────────────────────────
def generate(items, template_hwpx, out_dir):
    """
    - Claude API 항목: 합계 30만원 미만이면 묶음, 이상이면 개별
    - 일반 항목: 동일 사용자 기준 30만원 미만 묶음; 이상이면 개별
    """
    os.makedirs(out_dir, exist_ok=True)
    made = []

    api_items = [it for it in items if it.get("is_api")]
    regular   = [it for it in items if not it.get("is_api")]

    # API 묶음
    if api_items:
        total_api_krw = sum(it.get("krw") or 0 for it in api_items)
        if total_api_krw < _BUNDLE_LIMIT:
            edits = _api_bundle_edits(api_items)
            fname = f"기안서_회사공용API_Claude_API_{len(api_items)}건.hwpx"
            out   = os.path.join(out_dir, fname)
            hwpx_fill.fill_multi(template_hwpx, out, edits, extra_rows=[])
            made.append((out, api_items[0]))
        else:
            for it in api_items:
                _make_individual(it, template_hwpx, out_dir, made)

    # 일반 항목: 사용자별 묶음
    by_user = defaultdict(list)
    for it in regular:
        by_user[it["user"]].append(it)

    for user_items in by_user.values():
        for bundle in _create_bundles(user_items):
            _make_bundle(bundle, template_hwpx, out_dir, made)

    return made
