import streamlit as st
import os, glob, sys, io, zipfile, tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

st.set_page_config(page_title="AI 영수증 처리", layout="centered",
                   initial_sidebar_state="auto")

st.markdown("""
<style>
/* 버튼 각지게 */
.stButton > button,
.stDownloadButton > button {
    border-radius: 0 !important;
}

/* 파일 업로더 각지게 */
[data-testid="stFileUploaderDropzone"] {
    border-radius: 0 !important;
}

/* metric 왼쪽 포인트 라인 */
[data-testid="stMetric"] {
    border-left: 3px solid #FF7E1C;
    padding-left: 1rem;
}
</style>
""", unsafe_allow_html=True)


# ── 사이드바: 기준 파일 업데이트 ────────────────────────────
with st.sidebar:
    st.markdown("## 기준 파일")
    try:
        import supabase_storage as _ss
        files = {f["name"]: f.get("updated_at", "")[:10] for f in _ss.list_files()}
        st.caption(f"📄 마스터 엑셀: `{files.get('2026 AI.xlsx', '없음')}`")
        st.caption(f"📄 기안서 템플릿: `{files.get('template.hwpx', '없음')}`")
    except Exception:
        st.caption("Supabase 연결 확인 필요")

    st.markdown("---")
    new_master = st.file_uploader("마스터 엑셀 교체", type=["xlsx"], key="sb_master")
    if st.button("업로드", key="btn_sb_master", disabled=not new_master):
        with st.spinner("업로드 중..."):
            _ss.upload("2026 AI.xlsx", new_master.getvalue())
        st.success("마스터 엑셀 업데이트 완료")
        st.rerun()

    new_tpl = st.file_uploader("기안서 템플릿 교체", type=["hwpx"], key="sb_tpl")
    if st.button("업로드", key="btn_sb_tpl", disabled=not new_tpl):
        with st.spinner("업로드 중..."):
            _ss.upload("기안서_템플릿.hwpx", new_tpl.getvalue())
        st.success("기안서 템플릿 업데이트 완료")
        st.rerun()


# ── 헤더 ────────────────────────────────────────────────────
st.markdown("# AI 영수증 처리")
st.markdown("### 영수증 업로드 후 실행하면 60% 표기 PDF와 기안서를 생성합니다.")
st.markdown("---")


# ── 파일 업로드 ──────────────────────────────────────────────
c1, c2 = st.columns(2)
with c1:
    receipts = st.file_uploader("영수증", type=["pdf", "html", "htm", "png", "jpg", "jpeg"],
                                accept_multiple_files=True)
with c2:
    approvals = st.file_uploader("승인내역", type=["pdf"],
                                 accept_multiple_files=True)

st.markdown("---")


# ── 버튼 ────────────────────────────────────────────────────
b1, b2 = st.columns(2)
check = b1.button("영수증 누락 확인", disabled=not (receipts and approvals))
run   = b2.button("실행",           disabled=not (receipts and approvals))


def _get_base_files(tmp_dir):
    """기준 파일 경로 반환 — Supabase 우선, 실패하면 로컬 기준/ 폴더 사용."""
    local_master   = os.path.join(ROOT, "기준", "2026 AI.xlsx")
    local_template = os.path.join(ROOT, "기준", "기안서_템플릿.hwpx")
    try:
        import supabase_storage as ss
        master_path = os.path.join(tmp_dir, "2026 AI.xlsx")
        open(master_path, "wb").write(ss.download("2026 AI.xlsx"))
        template_path = os.path.join(tmp_dir, "기안서_템플릿.hwpx")
        open(template_path, "wb").write(ss.download("기안서_템플릿.hwpx"))
        return master_path, template_path
    except Exception:
        return local_master, local_template


def _parse_inputs(receipts, approvals, rec_dir, apr_dir, master_path):
    for f in receipts:
        open(os.path.join(rec_dir, f.name), "wb").write(f.getvalue())
    for f in approvals:
        open(os.path.join(apr_dir, f.name), "wb").write(f.getvalue())

    from parse_receipt import parse_folder
    from parse_approval import parse_pdf as parse_overseas
    from parse_domestic import parse_pdf as parse_domestic_fn
    from parse_master import load_master
    from match import match_all

    rec_list = parse_folder(rec_dir)
    overseas, domestic = [], []
    for fp in sorted(glob.glob(os.path.join(apr_dir, "*.pdf"))):
        b = os.path.basename(fp)
        if "국내" in b:
            domestic += parse_domestic_fn(fp)
        elif "해외" in b:
            overseas += parse_overseas(fp)
        elif "(1)" in b:
            domestic += parse_domestic_fn(fp)
        else:
            overseas += parse_overseas(fp)

    master = load_master(master_path)
    res = match_all(rec_list, overseas, domestic, master)
    return rec_list, overseas, domestic, master, res


def _missing_rows(unmatched_approvals):
    rows = []
    for a in unmatched_approvals:
        date     = a.get("tx_date", "?")
        merchant = a.get("merchant_key") or "?"
        if a.get("currency") == "KRW":
            amt = f"{a.get('krw', 0):,}원  (국내)"
        else:
            usd = a.get("usd_billed", "?")
            amt = f"${usd}  ({a.get('krw', 0):,}원)  (해외)"
        rows.append(f"{date}  |  {merchant}  |  {amt}")
    return rows


# ── 영수증 누락 확인 ─────────────────────────────────────────
if check:
    from parse_receipt import parse_folder
    from parse_approval import parse_pdf as parse_overseas
    from parse_domestic import parse_pdf as parse_domestic_fn
    from parse_master import load_master
    from match import match_all

    with tempfile.TemporaryDirectory() as tmp:
        rec_dir = os.path.join(tmp, "영수증");  os.makedirs(rec_dir)
        apr_dir = os.path.join(tmp, "승인내역"); os.makedirs(apr_dir)

        with st.spinner("확인 중..."):
            master_path, _ = _get_base_files(tmp)
            _, _, _, _, res = _parse_inputs(receipts, approvals, rec_dir, apr_dir, master_path)
            no_receipt = res["unmatched_approvals"]
            n_appr = len(res["pairs"]) + len(no_receipt)

        if no_receipt:
            st.session_state["check"] = {
                "ok": False,
                "rows": _missing_rows(no_receipt),
                "n_appr": n_appr,
                "n_missing": len(no_receipt),
            }
        else:
            st.session_state["check"] = {
                "ok": True,
                "n_appr": n_appr,
            }


# ── 처리 ────────────────────────────────────────────────────
if run:
    from parse_receipt import parse_folder
    from parse_approval import parse_pdf as parse_overseas
    from parse_domestic import parse_pdf as parse_domestic_fn
    from parse_master import load_master
    from match import match_all
    import build_pdf
    import gen_gianseo_hwpx as G
    from fx import load_override

    period = datetime.now().strftime("%Y-%m")
    master_path  = os.path.join(ROOT, "기준", "2026 AI.xlsx")
    template_path = os.path.join(ROOT, "기준", "기안서_템플릿.hwpx")
    fx_path = os.path.join(ROOT, "환율.json")

    with tempfile.TemporaryDirectory() as tmp:
        rec_dir = os.path.join(tmp, "영수증");  os.makedirs(rec_dir)
        apr_dir = os.path.join(tmp, "승인내역"); os.makedirs(apr_dir)
        out_dir = os.path.join(tmp, "출력");     os.makedirs(out_dir)

        with st.spinner("처리 중..."):
            master_path, template_path = _get_base_files(tmp)
            rec_list, _, _, master, res = _parse_inputs(
                receipts, approvals, rec_dir, apr_dir, master_path)

            import build_pdf
            import gen_gianseo_hwpx as G
            from fx import load_override

            # ─ 선행 점검: 영수증 없는 승인 건 ───────────────────────────────
            no_receipt = res["unmatched_approvals"]
            if no_receipt:
                st.session_state["result"] = {
                    "missing_approvals": _missing_rows(no_receipt)}
            else:
                ann   = {a["file"]: a for a in res["annotations"]}
                order = sorted(ann, key=lambda fn: (not ann[fn]["matched"],
                                                    str(ann[fn]["card_last4"]), fn))
                rmap  = {os.path.basename(p): p
                         for p in glob.glob(os.path.join(rec_dir, "*"))}
                paths = [rmap[fn] for fn in order if fn in rmap]

                pdf_out = os.path.join(out_dir, f"영수증_60퍼_표기_{period}.pdf")
                build_pdf.build(paths, ann, pdf_out)

                fx_path  = os.path.join(ROOT, "환율.json")
                override = load_override(fx_path) if os.path.exists(fx_path) else {}
                items    = G.build_items(res, master, override=override, use_online=True)
                gdir     = os.path.join(out_dir, "기안서")
                made     = G.generate(items, template_path, gdir) if items else []

                pdf_bytes = open(pdf_out, "rb").read()

                zip_buf = io.BytesIO()
                if made:
                    with zipfile.ZipFile(zip_buf, "w") as zf:
                        for fpath, _ in made:
                            zf.write(fpath, os.path.basename(fpath))

                rate     = items[0]["rate"] if items else None
                rate_str = f"1$ = {rate:,.0f}원" if rate else "환율 조회 실패"

                st.session_state["result"] = {
                    "pdf_bytes":  pdf_bytes,
                    "zip_bytes":  zip_buf.getvalue() if made else None,
                    "period":     period,
                    "n_rec":      len(rec_list),
                    "n_matched":  len(res["pairs"]),
                    "n_unmatched":len(res["unmatched_receipts"]),
                    "n_made":     len(made),
                    "rate_str":   rate_str,
                }


# ── 누락 확인 결과 ──────────────────────────────────────────
if "check" in st.session_state:
    c = st.session_state["check"]
    st.markdown("---")
    if c["ok"]:
        st.success(f"승인내역 {c['n_appr']}건 전부 영수증 있음 — 실행 버튼을 눌러 진행하세요.")
    else:
        st.error(f"승인내역 {c['n_appr']}건 중 {c['n_missing']}건 영수증 누락")
        for row in c["rows"]:
            st.markdown(f"- `{row}`")


# ── 결과 ────────────────────────────────────────────────────
if "result" in st.session_state:
    r = st.session_state["result"]
    st.markdown("---")

    if r.get("missing_approvals"):
        st.error("영수증 누락 — 아래 항목의 영수증을 추가한 뒤 다시 실행하세요.")
        for row in r["missing_approvals"]:
            st.markdown(f"- `{row}`")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("매칭",   f"{r['n_matched']}건")
        m2.metric("미매칭", f"{r['n_unmatched']}건")
        m3.metric("기안서", f"{r['n_made']}건")
        st.caption(f"환율  {r['rate_str']}")

        st.markdown("---")

        st.download_button(
            "영수증 PDF 다운로드",
            r["pdf_bytes"],
            file_name=f"영수증_60퍼_표기_{r['period']}.pdf",
            mime="application/pdf",
        )

        if r["zip_bytes"]:
            st.download_button(
                f"기안서 ZIP 다운로드  ({r['n_made']}건)",
                r["zip_bytes"],
                file_name=f"기안서_{r['period']}.zip",
                mime="application/zip",
            )
