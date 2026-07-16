"""기준 파일 관리 페이지 — Supabase Storage 업로드 UI."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import streamlit as st

st.set_page_config(page_title="기준 파일 관리", layout="centered")

st.markdown("""
<style>
.stButton > button,
.stDownloadButton > button   { border-radius: 0 !important; }
[data-testid="stFileUploaderDropzone"] { border-radius: 0 !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("# 기준 파일 관리")
st.markdown("---")


# ── 비밀번호 확인 ─────────────────────────────────────────────────────────────
def _admin_pw():
    try:
        pw = st.secrets.get("ADMIN_PASSWORD", "")
        if pw:
            return pw
    except Exception:
        pass
    cfg = os.path.join(ROOT, "config.json")
    if os.path.exists(cfg):
        return json.load(open(cfg, encoding="utf-8")).get("ADMIN_PASSWORD", "")
    return ""


ADMIN_PW = _admin_pw()
if not ADMIN_PW:
    st.warning("config.json 또는 .streamlit/secrets.toml에 ADMIN_PASSWORD를 설정하세요.")
    st.stop()

pw = st.text_input("관리자 비밀번호", type="password", placeholder="비밀번호를 입력하세요")
if pw != ADMIN_PW:
    if pw:
        st.error("비밀번호가 틀렸습니다.")
    st.stop()


# ── 인증 완료 ─────────────────────────────────────────────────────────────────
import supabase_storage as ss

st.success("인증되었습니다.")
st.markdown("---")

# 현재 Supabase 파일 목록
st.markdown("### 현재 Supabase 파일")
files = ss.list_files()
if files:
    for f in files:
        name = f.get("name", "")
        ts   = f.get("updated_at") or f.get("created_at") or "?"
        st.markdown(f"- **{name}** — 마지막 업데이트: `{ts}`")
else:
    st.info("아직 업로드된 파일이 없습니다.")

st.markdown("---")

# ── 마스터 엑셀 업데이트 ──────────────────────────────────────────────────────
st.markdown("### 마스터 엑셀 (`2026 AI.xlsx`)")
st.caption("사용자 정보 · 기안서 대상 목록이 담긴 파일. 수정할 때마다 업로드하세요.")
new_master = st.file_uploader("새 파일 선택", type=["xlsx"], key="master")
if st.button("Supabase에 업로드", key="btn_master", disabled=not new_master):
    with st.spinner("업로드 중..."):
        ss.upload("2026 AI.xlsx", new_master.getvalue())
    st.success("마스터 엑셀 업데이트 완료")
    st.rerun()

st.markdown("---")

# ── 기안서 템플릿 업데이트 ───────────────────────────────────────────────────
st.markdown("### 기안서 템플릿 (`기안서_템플릿.hwpx`)")
st.caption("HWPX 양식 파일. 서식이 바뀔 때만 업로드하면 됩니다.")
new_tpl = st.file_uploader("새 파일 선택", type=["hwpx"], key="template")
if st.button("Supabase에 업로드", key="btn_tpl", disabled=not new_tpl):
    with st.spinner("업로드 중..."):
        ss.upload("기안서_템플릿.hwpx", new_tpl.getvalue())
    st.success("기안서 템플릿 업데이트 완료")
    st.rerun()
