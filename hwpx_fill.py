"""HWPX(.hwpx) 기안서 텍스트 채우기.

HWPX = zip(+XML). Contents/section0.xml 안의 <hp:t> 텍스트 요소를
인덱스로 지정해 교체한다(양식·표·서식 100% 보존).
mimetype 항목은 반드시 첫번째 & 무압축으로 유지.
"""
import re
import zipfile
from xml.sax.saxutils import escape

HPT_RE = re.compile(r"(<hp:t>)(.*?)(</hp:t>)", re.S)
EMPTY_RUN = '<hp:run charPrIDRef="17"/>'


def list_texts(section_xml):
    return [m.group(2) for m in HPT_RE.finditer(section_xml)]


def replace_texts(section_xml, edits):
    """edits: {index: new_text}. <hp:t> 등장 순서 기준."""
    out = []
    last = 0
    for i, m in enumerate(HPT_RE.finditer(section_xml)):
        out.append(section_xml[last:m.start()])
        if i in edits:
            out.append(m.group(1) + escape(str(edits[i])) + m.group(3))
        else:
            out.append(m.group(0))
        last = m.end()
    out.append(section_xml[last:])
    return "".join(out)


def _fill_row(row_xml, values):
    """빈 행의 6개 셀(품명·구독·수량·기간·단가·사용자)에 값을 주입.

    빈 셀은 <hp:run charPrIDRef="17"/> (self-closing) 으로 표시됨.
    값이 있으면 <hp:run charPrIDRef="17"><hp:t>값</hp:t></hp:run> 으로 교체.
    """
    parts = row_xml.split(EMPTY_RUN)
    if len(parts) < len(values) + 1:
        return row_xml
    result = parts[0]
    for i, val in enumerate(values):
        safe = escape(str(val)) if val else ""
        if safe:
            result += f'<hp:run charPrIDRef="17"><hp:t>{safe}</hp:t></hp:run>'
        else:
            result += EMPTY_RUN
        result += parts[i + 1]
    for part in parts[len(values) + 1:]:
        result += EMPTY_RUN + part
    return result


def _update_tbl_rowcnt(xml, tbl_pos, delta):
    """hp:tbl 의 rowCnt 속성을 delta만큼 조정."""
    end = xml.find('>', tbl_pos)
    tag = xml[tbl_pos:end]
    m = re.search(r'rowCnt="(\d+)"', tag)
    if not m:
        return xml
    new_cnt = max(1, int(m.group(1)) + delta)
    new_tag = tag[:m.start()] + f'rowCnt="{new_cnt}"' + tag[m.end():]
    return xml[:tbl_pos] + new_tag + xml[end:]


def _fix_single_line_subscription(xml, hpt25_start, hpt26_start):
    """1줄 구독 플랜 처리:
    1) 빈 2단락(para2, hp:t[26] 포함) 전체를 제거
    2) 1단락 lineseg vertpos → 셀 중앙(1021)으로 설정
    셀 높이=3225, 마진 141×2 → 콘텐츠=2943, 1행 높이=900 → 중앙=(2943-900)//2=1021
    """
    # 1. para2 제거 (hp:t[26] 직전의 <hp:p 부터 </hp:p> 까지)
    para2_start = xml.rfind('<hp:p ', 0, hpt26_start)
    if para2_start != -1:
        para2_end = xml.find('</hp:p>', hpt26_start) + len('</hp:p>')
        xml = xml[:para2_start] + xml[para2_end:]
        # para2는 para1 뒤에 있으므로 hpt25_start 위치는 유효

    # 2. para1 lineseg vertpos → 1021
    run_end = xml.find('</hp:run>', hpt25_start)
    if run_end != -1:
        seg_start = xml.find('<hp:lineseg ', run_end)
        if seg_start != -1:
            seg_end = xml.find('/>', seg_start) + 2
            new_seg = re.sub(r'\bvertpos="[0-9]+"', 'vertpos="1021"', xml[seg_start:seg_end])
            xml = xml[:seg_start] + new_seg + xml[seg_end:]
    return xml


def _renumber_summary_rows(xml, tbl_pos, num_extra):
    """행 삭제 후 요약 행(원래 rowAddr=6,7,8)을 순차 번호로 재번호 매김.

    원본 품목 테이블 구조:
      rowAddr 0 = 헤더, 1 = 데이터, 2-5 = 빈 행(삭제 대상), 6-8 = 합계/환율 등 요약 행
    삭제 후 요약 행의 새 rowAddr = num_extra+2, num_extra+3, num_extra+4
    """
    old_start = 6
    new_start = num_extra + 2
    if old_start == new_start:
        return xml
    tbl_end = xml.find('</hp:tbl>', tbl_pos)
    if tbl_end == -1:
        return xml
    tbl_end += len('</hp:tbl>')
    segment = xml[tbl_pos:tbl_end]
    for i in range(3):  # 요약 행 3개(rowAddr 6,7,8)
        segment = segment.replace(f'rowAddr="{old_start + i}"',
                                  f'rowAddr="{new_start + i}"')
    return xml[:tbl_pos] + segment + xml[tbl_end:]


def _delete_rows(xml, row_addrs, search_from=0):
    """rowAddr="N" 을 포함하는 <hp:tr>...</hp:tr> 블록 전체 삭제.

    search_from: 이 위치 이후에서만 검색 (동일 rowAddr이 다른 테이블에 있는 경우 방지).
    """
    result = xml
    for n in row_addrs:
        marker = f'colAddr="0" rowAddr="{n}"'
        pos = result.find(marker, search_from)
        if pos == -1:
            continue
        tr_start = result.rfind("<hp:tr>", 0, pos)
        if tr_start == -1:
            continue
        tr_end = result.find("</hp:tr>", tr_start) + len("</hp:tr>")
        result = result[:tr_start] + result[tr_end:]
    return result


def _write_zip(zin, out_path, section, new_xml_bytes):
    with zipfile.ZipFile(out_path, "w") as zout:
        names = zin.namelist()
        # mimetype: 반드시 첫 번째, 비압축, extra 없음
        if "mimetype" in names:
            zi = zipfile.ZipInfo("mimetype")
            zi.compress_type = zipfile.ZIP_STORED
            zout.writestr(zi, zin.read("mimetype"))
        for n in names:
            if n == "mimetype":
                continue
            orig = zin.getinfo(n)
            data = new_xml_bytes if n == section else zin.read(n)
            zi = zipfile.ZipInfo(n, date_time=orig.date_time)
            # 수정된 섹션은 deflate, 나머지는 원본 압축방식 유지
            zi.compress_type = zipfile.ZIP_DEFLATED if n == section else orig.compress_type
            zi.external_attr = orig.external_attr
            zout.writestr(zi, data)


def fill(template_path, out_path, edits, section="Contents/section0.xml"):
    """단일 행 기안서 (빈 행 전부 삭제)."""
    return fill_multi(template_path, out_path, edits, extra_rows=[], section=section)


def fill_multi(template_path, out_path, edits, extra_rows, section="Contents/section0.xml"):
    """다중 행 기안서.

    edits: {index: text} — Row 1 데이터 + 헤더/합계/공급업체 등
    extra_rows: list of dict(prod1, prod2, prod3, period, unit, user) — Row 2+ 데이터
                (최대 4개; 사용 안 하는 빈 행은 자동 삭제)
    """
    zin = zipfile.ZipFile(template_path, "r")
    xml = zin.read(section).decode("utf-8")

    # ── Row 1 + 고정 필드 교체 ──────────────────────────────────────────────
    new_xml = replace_texts(xml, edits)

    # ── 구독 셀 정렬 조정 (텍스트 교체 직후, 위치 계산 전에 처리) ────────────
    # prod2b(idx=26)가 ""이면 1줄 플랜 → para1 lineseg vertpos를 중앙(1021)으로
    # prod2b가 ""이 아니면 2줄 플랜 → 그대로(템플릿 vertpos 0/1352 유지)
    _PROD2_IDX  = 25
    _PROD2B_IDX = 26
    if edits.get(_PROD2B_IDX) == "":
        _hpt_temp = list(HPT_RE.finditer(new_xml))
        if _PROD2B_IDX < len(_hpt_temp) and _PROD2_IDX < len(_hpt_temp):
            new_xml = _fix_single_line_subscription(
                new_xml,
                _hpt_temp[_PROD2_IDX].start(),
                _hpt_temp[_PROD2B_IDX].start(),
            )

    # ── 데이터 행(Row 1) 끝 위치 파악 — 빈 행 삭제 범위 제한용 ────────────────
    prod1_idx = 24  # 품명 데이터가 있는 hp:t 인덱스
    hpt_positions = [m.start() for m in HPT_RE.finditer(new_xml)]
    if prod1_idx < len(hpt_positions):
        data_row_end = new_xml.find("</hp:tr>", hpt_positions[prod1_idx]) + len("</hp:tr>")
    else:
        data_row_end = 0

    # ── 추가 행 주입 (Row 2~5) ──────────────────────────────────────────────
    num_extra = min(len(extra_rows), 4)
    for i, row_data in enumerate(extra_rows[:4]):
        row_addr = i + 2  # 2, 3, 4, 5
        values = [
            row_data.get("prod1", ""),
            row_data.get("prod2", ""),
            row_data.get("prod3", ""),
            row_data.get("period", ""),
            row_data.get("unit", ""),
            row_data.get("user", ""),
        ]
        marker = f'colAddr="0" rowAddr="{row_addr}"'
        pos = new_xml.find(marker, data_row_end)
        if pos == -1:
            continue
        tr_start = new_xml.rfind("<hp:tr>", 0, pos)
        tr_end = new_xml.find("</hp:tr>", tr_start) + len("</hp:tr>")
        filled = _fill_row(new_xml[tr_start:tr_end], values)
        new_xml = new_xml[:tr_start] + filled + new_xml[tr_end:]

    # ── 미사용 빈 행 삭제 (데이터 행 이후에서만 검색) ──────────────────────
    unused = list(range(num_extra + 2, 6))  # e.g. extra=1 → delete rows 3,4,5
    if unused:
        new_xml = _delete_rows(new_xml, unused, search_from=data_row_end)
        # 품목 테이블의 rowCnt 속성도 삭제한 행 수만큼 감소
        tbl_pos = new_xml.rfind('<hp:tbl ', 0, data_row_end)
        if tbl_pos != -1:
            new_xml = _update_tbl_rowcnt(new_xml, tbl_pos, -len(unused))
            new_xml = _renumber_summary_rows(new_xml, tbl_pos, num_extra)

    _write_zip(zin, out_path, section, new_xml.encode("utf-8"))
    zin.close()
    return out_path
