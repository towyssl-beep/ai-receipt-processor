import streamlit as st
import os, glob, sys, io, zipfile, tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

st.set_page_config(page_title="AI 영수증 처리", layout="centered",
                   initial_sidebar_state="collapsed")

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


# ── 헤더 ────────────────────────────────────────────────────
st.markdown("# AI 영수증 처리")
st.markdown("### 영수증 업로드 후 실행하면 60% 표기 PDF와 기안서를 생성합니다.")
st.markdown("---")


# ── 파일 업로드 ──────────────────────────────────────────────
c1, c2 = st.columns(2)
with c1:
    receipts = st.file_uploader("영수증", type=["pdf", "html", "htm"],
                                accept_multiple_files=True)
with c2:
    approvals = st.file_uploader("승인내역", type=["pdf"],
                                 accept_multiple_files=True)

st.markdown("---")


# ── 실행 버튼 ────────────────────────────────────────────────
run = st.button("실행", disabled=not (receipts and approvals))


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

        for f in receipts:
            open(os.path.join(rec_dir, f.name), "wb").write(f.getvalue())
        for f in approvals:
            open(os.path.join(apr_dir, f.name), "wb").write(f.getvalue())

        with st.spinner("처리 중..."):
            rec_list = parse_folder(rec_dir)

            overseas, domestic = [], []
            for fp in sorted(glob.glob(os.path.join(apr_dir, "*.pdf"))):
                if "(1)" in os.path.basename(fp):
                    domestic += parse_domestic_fn(fp)
                else:
                    overseas += parse_overseas(fp)

            master = load_master(master_path)
            res    = match_all(rec_list, overseas, domestic, master)

            ann   = {a["file"]: a for a in res["annotations"]}
            order = sorted(ann, key=lambda fn: (not ann[fn]["matched"],
                                                str(ann[fn]["card_last4"]), fn))
            rmap  = {os.path.basename(p): p
                     for p in glob.glob(os.path.join(rec_dir, "*"))}
            paths = [rmap[fn] for fn in order if fn in rmap]

            pdf_out = os.path.join(out_dir, f"영수증_60퍼_표기_{period}.pdf")
            build_pdf.build(paths, ann, pdf_out)

            override = load_override(fx_path) if os.path.exists(fx_path) else {}
            items    = G.build_items(res, master, override=override, use_online=True)
            gdir     = os.path.join(out_dir, "기안서")
            made     = G.generate(items, template_path, gdir) if items else []

            # 결과물을 bytes로 메모리에 읽기 (temp dir 닫히기 전)
            pdf_bytes = open(pdf_out, "rb").read()

            zip_buf = io.BytesIO()
            if made:
                with zipfile.ZipFile(zip_buf, "w") as zf:
                    for fpath, _ in made:
                        zf.write(fpath, os.path.basename(fpath))

            rate     = items[0]["rate"] if items else None
            rate_str = f"1$ = {rate:,.0f}원" if rate else "환율 조회 실패"

        # session_state에 저장 (temp dir 닫힌 후에도 유지)
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


# ── 결과 ────────────────────────────────────────────────────
if "result" in st.session_state:
    r = st.session_state["result"]

    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    m1.metric("매칭",   f"{r['n_matched']}건")
    m2.metric("미매칭", f"{r['n_unmatched']}건")
    m3.metric("기안서", f"{r['n_made']}건")
    st.caption(f"환율  {r['rate_str']}")

    st.markdown("---")

    st.download_button(
        f"영수증 PDF 다운로드",
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
