"""HWPX → PDF 변환 (LibreOffice headless 사용)."""
import os
import shutil
import subprocess
import tempfile


def convert(hwpx_path: str, out_dir: str) -> str | None:
    """hwpx_path를 PDF로 변환해 out_dir에 저장. 성공 시 PDF 경로 반환, 실패 시 None."""
    lo = shutil.which("libreoffice") or shutil.which("soffice")
    if not lo:
        return None
    try:
        # LibreOffice는 변환 중 사용자 프로필 디렉터리가 필요 — 임시 경로 사용
        with tempfile.TemporaryDirectory() as profile_dir:
            env = os.environ.copy()
            env["HOME"] = profile_dir
            result = subprocess.run(
                [lo, "--headless", "--norestore",
                 "--convert-to", "pdf", "--outdir", out_dir, hwpx_path],
                capture_output=True, timeout=60, env=env,
            )
        if result.returncode != 0:
            return None
        base = os.path.splitext(os.path.basename(hwpx_path))[0]
        pdf_path = os.path.join(out_dir, base + ".pdf")
        return pdf_path if os.path.exists(pdf_path) else None
    except Exception:
        return None


def convert_all(hwpx_paths: list[str], out_dir: str) -> list[str]:
    """여러 HWPX 파일을 PDF로 변환. 변환 성공한 PDF 경로 목록 반환."""
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for p in hwpx_paths:
        pdf = convert(p, out_dir)
        if pdf:
            results.append(pdf)
    return results
