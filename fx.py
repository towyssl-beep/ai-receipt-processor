"""환율 조회. 기안서 금액 = $금액 × 결제일 환율.

우선순위: ① 환율.json 오버라이드(date→rate) ② 온라인 조회(매매기준율, PC 실행시)
③ 폴백(카드 적용환율). 사용한 환율과 출처를 함께 반환.
"""
import json
import os

_ONLINE_CACHE = {}


def load_override(path):
    if path and os.path.exists(path):
        return {k: float(v) for k, v in json.load(open(path, encoding="utf-8")).items()}
    return {}


def _online(date_iso):
    """exchangerate.host 등에서 USD→KRW. 사내망/샌드박스에서 막히면 None."""
    if date_iso in _ONLINE_CACHE:
        return _ONLINE_CACHE[date_iso]
    import urllib.request
    # 1) 키 없는 무료 API: 현재(오늘) 환율 — open.er-api.com
    for url, path in [
        ("https://open.er-api.com/v6/latest/USD", ("rates", "KRW")),
        (f"https://api.exchangerate.host/{date_iso}?base=USD&symbols=KRW", ("rates", "KRW")),
    ]:
        try:
            with urllib.request.urlopen(url, timeout=6) as r:
                data = json.load(r)
            rate = float(data[path[0]][path[1]])
            _ONLINE_CACHE[date_iso] = rate
            return rate
        except Exception:
            continue
    return None


def get_rate(date_iso, override=None, fallback=None, use_online=True):
    """return (rate, source)."""
    override = override or {}
    if date_iso in override:
        return override[date_iso], "override"
    if use_online:
        r = _online(date_iso)
        if r:
            return round(r, 2), "online"
    if fallback:
        return fallback, "card_rate"
    return None, "none"
