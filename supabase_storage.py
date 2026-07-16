"""Supabase Storage 연동 — 기준 파일 업·다운로드."""
import json
import os

BUCKET = "gianseo"


def _creds():
    """Streamlit secrets → config.json 순으로 인증 정보 탐색."""
    try:
        import streamlit as st
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        if url and key:
            return url, key
    except Exception:
        pass
    cfg = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(cfg):
        d = json.load(open(cfg, encoding="utf-8"))
        if d.get("SUPABASE_URL") and d.get("SUPABASE_KEY"):
            return d["SUPABASE_URL"], d["SUPABASE_KEY"]
    raise RuntimeError("Supabase 인증 정보 없음 — config.json 또는 secrets.toml 확인")


def _client():
    from supabase import create_client
    url, key = _creds()
    return create_client(url, key)


_NAME_MAP = {
    "기안서_템플릿.hwpx": "template.hwpx",
}


def download(name: str) -> bytes:
    return bytes(_client().storage.from_(BUCKET).download(_NAME_MAP.get(name, name)))


def upload(name: str, data: bytes) -> None:
    sb = _client().storage.from_(BUCKET)
    try:
        sb.remove([name])
    except Exception:
        pass
    sb.upload(name, data, {"content-type": "application/octet-stream"})


def list_files() -> list:
    try:
        return _client().storage.from_(BUCKET).list() or []
    except Exception:
        return []
