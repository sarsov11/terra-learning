#!/usr/bin/env python3
"""총신대학교 2028 시행계획 파서.

대상 표: "1. 모집시기 및 전형별 모집인원(정원 내)" (PDF 3쪽).
이 표는 학과가 열, 전형이 행인 '가로 학과' 표다. 교회음악과의 실기 전형은 전공(성악(남)·피아노 등)별
하위 행으로 나뉘어 있어 교회음악과는 전공 단위로 적는다.
사용법: python3 -I tools/ipsi/parsers/chongshin.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "chongshin"
UNIV_NAME = "총신대학교"

FIRST_UNIT_COL = 4
LAST_UNIT_COL = 13
COL_ROWSUM = 14  # 전형별 모집인원 합계
MUSIC = "교회음악과"
MUSIC_MAJORS = ["성악(남)", "성악(여)", "피아노", "오르간", "작곡", "지휘", "관현악"]

# (시기 블록, 전형유형 칸, 전형명 칸) → key
ROWMAP = {
    ("수시", "학생부교과", "교과우수자"): "수시_교과_교과우수자",
    ("수시", "학생부종합", "목회자추천자"): "수시_종합_목회자추천자",
    ("수시", "학생부종합", "코람데오인재"): "수시_종합_코람데오인재",
    ("수시", "학생부종합", "총신고른기회"): "수시_종합_총신고른기회",
    ("수시", "학생부종합", "대안학교출신자"): "수시_종합_대안학교출신자",
    ("수시", "실기/실적위주", "성경지식우수자"): "수시_실기_성경지식우수자",
    ("수시", "실기/실적위주", "외국어(영어)우수자"): "수시_실기_외국어우수자",
    ("수시", "실기/실적위주", "실기우수자"): "수시_실기_실기우수자",
    ("정시", "수능위주(‘가’군)", "CS인재"): "정시_수능_가_CS인재",
    ("정시", "실기/실적위주(‘다’군)", "CS인재"): "정시_실기_다_CS인재",
}
MAJOR_KEYS = {"수시_실기_실기우수자", "정시_실기_다_CS인재"}  # 전공별 하위 행이 있는 전형

JEONHYEONG = [
    {"key": "수시_교과_교과우수자", "시기": "수시", "유형": "학생부교과", "전형명": "교과우수자", "군": None},
    {"key": "수시_종합_목회자추천자", "시기": "수시", "유형": "학생부종합", "전형명": "목회자추천자", "군": None},
    {"key": "수시_종합_코람데오인재", "시기": "수시", "유형": "학생부종합", "전형명": "코람데오인재", "군": None},
    {"key": "수시_종합_총신고른기회", "시기": "수시", "유형": "학생부종합", "전형명": "총신고른기회", "군": None},
    {"key": "수시_종합_대안학교출신자", "시기": "수시", "유형": "학생부종합", "전형명": "대안학교출신자", "군": None},
    {"key": "수시_실기_성경지식우수자", "시기": "수시", "유형": "실기/실적", "전형명": "성경지식우수자", "군": None},
    {"key": "수시_실기_외국어우수자", "시기": "수시", "유형": "실기/실적", "전형명": "외국어(영어)우수자", "군": None},
    {"key": "수시_실기_실기우수자", "시기": "수시", "유형": "실기/실적", "전형명": "실기우수자", "군": None},
    {"key": "정시_수능_가_CS인재", "시기": "정시", "유형": "수능", "전형명": "CS인재", "군": "가"},
    {"key": "정시_실기_다_CS인재", "시기": "정시", "유형": "실기/실적", "전형명": "CS인재", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]
assert set(ROWMAP.values()) == {j["key"] for j in JEONHYEONG}


def flat(s):
    return re.sub(r"\s+", "", s or "")


def to_int(cell):
    s = (cell or "").strip().replace(",", "")
    if s in ("", "-", "–"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {cell!r}")


def find_table(pdf):
    for pno, page in enumerate(pdf.pages, start=1):
        txt = page.extract_text() or ""
        if "전형별 모집인원(정원 내)" not in txt:
            continue
        for t in page.find_tables():
            rows = t.extract()
            if rows and flat(rows[0][0]) == "모집시기" and flat(rows[0][1]) == "전형구분":
                return pno, page, t, rows
    raise SystemExit("전형별 모집인원(정원 내) 표를 찾지 못함")


def rowsum_words(page, table, ri):
    """'전형별 모집인원 합계' 열은 데이터 행에 셀 경계가 잡히지 않아, 그 열 x 범위 + 행 y 범위의 단어로 읽는다."""
    hdr = table.rows[0].cells[COL_ROWSUM]
    ref = table.rows[ri].cells[LAST_UNIT_COL]
    return [w["text"] for w in page.extract_words()
            if hdr[0] <= (w["x0"] + w["x1"]) / 2 <= hdr[2] and ref[1] <= (w["top"] + w["bottom"]) / 2 <= ref[3]]


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        pno, page, table, rows = find_table(pdf)
        rs_words = {ri: rowsum_words(page, table, ri) for ri in range(2, len(rows))}

    if flat(rows[0][COL_ROWSUM]) != "전형별모집인원합계":
        raise SystemExit(f"합계 열 위치 다름: {rows[0][COL_ROWSUM]!r}")

    # 학과(열) 이름과 계열
    hdr0_cells = [(c, t) for c, t in zip(table.rows[0].cells, rows[0]) if c is not None]
    units_col = {}
    for ci in range(FIRST_UNIT_COL, LAST_UNIT_COL + 1):
        if rows[1][ci] is None:  # 두 머리줄에 걸친 학과 칸(자율전공학부) → 계열 칸 없음
            name, gyeyeol = flat(rows[0][ci]), None
        else:
            name = flat(rows[1][ci])
            cell = table.rows[1].cells[ci]
            cx = (cell[0] + cell[2]) / 2
            g = [t for c, t in hdr0_cells if c[0] - 0.5 <= cx <= c[2] + 0.5]
            if len(g) != 1:
                raise SystemExit(f"계열 칸 못 찾음 col{ci}")
            gyeyeol = flat(g[0])
            if not gyeyeol.endswith("계열"):
                raise SystemExit(f"계열 머리글 이상 col{ci}: {gyeyeol}")
            gyeyeol = gyeyeol[: -len("계열")]
        if not re.search(r"(과|부)$", name):
            raise SystemExit(f"학과 이름 이상 col{ci}: {name}")
        units_col[ci] = (name, gyeyeol)
    music_col = next(ci for ci, (n, _) in units_col.items() if n == MUSIC)

    # 행 읽기
    data = {}            # (학과, 전공|None) → {key: n}
    rowsum_check = []    # (key/전공, 표 합계칸, 계산)
    subtotal = {}        # '수시모집소계' 등 → {col: n}
    sigi = cur_type = cur_name = None
    jeong_major_vals, jeong_major_words = [], []
    for ri, r in enumerate(rows[2:], start=2):
        label = flat(r[0])
        if label in ("수시모집소계", "정시모집소계", "학과별정원내모집인원합계"):
            subtotal[label] = {ci: to_int(r[ci]) for ci in units_col}
            subtotal[label]["합"] = to_int(r[COL_ROWSUM])
            if label == "수시모집소계":
                sigi = "정시"
            continue
        if sigi is None:
            sigi = "수시"
        if r[1] is not None:
            cur_type = flat(r[1])
        if r[2] is not None:
            cur_name = flat(r[2])
        key = ROWMAP.get((sigi, cur_type, cur_name))
        if key is None:
            raise SystemExit(f"알 수 없는 전형 행: {sigi} {cur_type} {cur_name}")
        major = flat(r[3]) if r[3] else None
        if (key in MAJOR_KEYS) != (major is not None):
            raise SystemExit(f"전공 칸 이상: {key} {major}")
        vals = {ci: to_int(r[ci]) for ci in units_col}
        if major:
            if major not in MUSIC_MAJORS:
                raise SystemExit(f"알 수 없는 전공: {major}")
            others = [ci for ci, v in vals.items() if v and ci != music_col]
            if others:
                raise SystemExit(f"전공 행에 교회음악과 밖 숫자: {major} {others}")
            data.setdefault((MUSIC, major), {})[key] = vals[music_col]
        else:
            for ci, v in vals.items():
                data.setdefault((units_col[ci][0], None), {})
                if v:
                    data[(units_col[ci][0], None)][key] = v
        tag = f"{key}{'/' + major if major else ''}"
        if key == "정시_실기_다_CS인재":
            # 이 블록의 합계 칸은 7개 전공 행에 걸친 병합 칸 하나 → 블록 합으로 대조
            jeong_major_vals.append(sum(vals.values()))
            jeong_major_words += rs_words[ri]
            continue
        w = rs_words[ri]
        if len(w) != 1:
            raise SystemExit(f"합계 칸 단어 이상: {tag} {w}")
        rowsum_check.append((tag, to_int(w[0]), sum(vals.values())))
    if len(jeong_major_words) != 1:
        raise SystemExit(f"정시 실기 합계 병합칸 단어 이상: {jeong_major_words}")
    rowsum_check.append(("정시_실기_다_CS인재(7전공 병합칸)", to_int(jeong_major_words[0]), sum(jeong_major_vals)))

    for lab in ("수시모집소계", "정시모집소계", "학과별정원내모집인원합계"):
        if lab not in subtotal:
            raise SystemExit(f"{lab} 행 없음")
    gye_row = subtotal["학과별정원내모집인원합계"]

    units = []
    for ci, (name, gyeyeol) in units_col.items():
        if ci == music_col:
            for m in MUSIC_MAJORS:
                inwon = {k: v for k, v in data.get((MUSIC, m), {}).items() if v}
                units.append({"단과대학": None, "모집단위": f"{MUSIC} {m}", "계열": gyeyeol, "인원": inwon,
                              "계": None, "쪽": pno, "검증": "합계칸없음"})
            # 교회음악과 열에 전공 행이 아닌 전형 숫자가 있으면 안 됨
            if data.get((MUSIC, None)):
                raise SystemExit(f"교회음악과 전공 밖 숫자: {data[(MUSIC, None)]}")
            continue
        inwon = data[(name, None)]
        gye = gye_row[ci]
        units.append({"단과대학": None, "모집단위": name, "계열": gyeyeol, "인원": inwon, "계": gye, "쪽": pno,
                      "검증": "합계일치" if sum(inwon.values()) == gye else "합계불일치"})

    # 보조 대조
    sub_bad = []
    for ci, (name, _) in units_col.items():
        us = [u for u in units if u["모집단위"] == name or u["모집단위"].startswith(name + " ")]
        s = sum(u["인원"].get(k, 0) for u in us for k in SUSI_KEYS)
        j = sum(u["인원"].get(k, 0) for u in us for k in JEONGSI_KEYS)
        if s != subtotal["수시모집소계"][ci] or j != subtotal["정시모집소계"][ci] or s + j != gye_row[ci]:
            sub_bad.append(f"{name}(수시소계 {subtotal['수시모집소계'][ci]}/{s}, 정시소계 {subtotal['정시모집소계'][ci]}/{j}, "
                           f"합계 {gye_row[ci]}/{s + j})")
    rs_bad = [f"{k}({a}≠{b})" for k, a, b in rowsum_check if a != b]
    music_units = [u for u in units if u["모집단위"].startswith(MUSIC + " ")]
    music_j_total = sum(u["인원"].get("정시_실기_다_CS인재", 0) for u in music_units)

    s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
    j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
    memo = [
        "정원내만 수록(PDF 3쪽 '모집시기 및 전형별 모집인원(정원 내)' 표). 정원외(기초생활수급자및차상위계층, 특수교육대상자, "
        "재외국민외국인(정원의2%·비제한), 북한이탈주민·전교육과정이수자·부모모두외국인인외국인)는 넣지 않음",
        "총신고른기회는 정원내 표에 있어 수록",
        "이 표는 학과가 열, 전형이 행인 형태. 계 = '학과별 정원 내 모집인원 합계' 행의 그 학과 칸",
        f"{MUSIC}는 실기우수자(수시)·CS인재 실기(정시 다군) 인원이 전공별(성악(남)·성악(여)·피아노·오르간·작곡·지휘·관현악) "
        f"행으로만 나와 전공 단위 7행으로 적음 → 행별 합계 칸이 없어 계=null(합계칸없음). "
        f"전공 7행 합: 수시 {sum(u['인원'].get('수시_실기_실기우수자', 0) for u in music_units)}"
        f"(표 수시모집 소계 {subtotal['수시모집소계'][music_col]}), 정시 {music_j_total}"
        f"(표 정시모집 소계 {subtotal['정시모집소계'][music_col]}, 정시 실기 '전형별 모집인원 합계' 병합칸 {jeong_major_words[0]}), "
        f"전체 {gye_row[music_col]}",
        "계열: 표 머리글의 인문사회계열/사범계열/예능계열에서 '계열'을 뗀 값. 자율전공학부는 계열 머리글 밖이라 null",
        "단과대학: 표에 단과대학 칸이 없어 null",
        "'-'는 0으로 봄",
        f"보조 대조(학과별 수시모집 소계·정시모집 소계·학과별 합계 행 = 정리 데이터 합): "
        + ("모든 학과 일치" if not sub_bad else "불일치 " + "; ".join(sub_bad)),
        f"보조 대조(전형 행의 '전형별 모집인원 합계' 칸 = 학과 칸 합): {len(rowsum_check) - len(rs_bad)}/{len(rowsum_check)} 일치"
        + (" — 불일치 " + ", ".join(rs_bad) if rs_bad else "")
        + " (이 열은 셀 경계가 안 잡혀 단어 위치로 읽음; 정시 실기 7전공은 병합 칸 하나라 블록 합으로 대조)",
        f"총계 대조(PDF 수시모집 소계·정시모집 소계·학과별 합계 행의 합계 칸): 수시 {subtotal['수시모집소계']['합']}={s_me}, "
        f"정시 {subtotal['정시모집소계']['합']}={j_me}, 전체 {gye_row['합']}={s_me + j_me} "
        "(2쪽 주요변경사항의 2028 정원 내 수시 267명·정시 40명과도 같음)",
    ]
    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": [pno], "전형": JEONHYEONG, "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    cnt = {}
    for u in units:
        cnt[u["검증"]] = cnt.get(u["검증"], 0) + 1
    print(f"{UNIV_ID}: {len(units)}행 {cnt} → {out_path}")
    for m in memo:
        print(" -", m)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: chongshin.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
