#!/usr/bin/env python3
"""한양대학교(서울) 2028 시행계획 -> norm JSON.

원천: '2028학년도 신입학 모집인원' 의 '□ 정원 내 모집인원' 표(2쪽에 걸침).
  열: 대학 | 계열 | 모집단위 | 모집인원 | 수시(교과 추천형, 종합 학업형/면접형/고른기회/사회통합/체육인재, 논술, 실기/실적 특기자, 수시계)
      | 정시(가군 수능∙실기/실적, 나군 수능∙실기/실적, 다군 수능, 정시계)
- 정시 가·나군 칸은 수능과 실기/실적이 한 칸에 섞여 있다. 정시 전형방법 표(수능(가/나/다군 일반) 등)에서
  '실기/실적(가군)'으로 분류된 성악과·작곡과·피아노과, '실기/실적(나군)'인 관현악과만 실기/실적으로 나누고
  나머지는 수능으로 둔다. 나눈 결과를 '주요 변경사항'의 2028 정시 실기/실적 인원(가군 58, 나군 21)과 대조한다.
- ( ) 안 숫자는 계약학과 입학정원(정원 외, 반도체공학과) -> 제외.
- 한양인터칼리지학부(자연)/(인문)은 모집인원·추천형·정시 다군 칸이 두 행에 걸친 병합 셀이라
  단위별로 나눌 수 없으므로 한 행으로 합쳐 싣는다(합친 값은 PDF 칸 값의 합).

usage: python3 -I tools/ipsi/parsers/hanyang.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "hanyang"
UNIV_NAME = "한양대학교"

SUSI_COLS = {
    ("학생부교과", "추천형"): ("수시_교과_추천형", "수시", "학생부교과", "학생부교과(추천형)", None),
    ("학생부종합", "학업형"): ("수시_종합_학업형", "수시", "학생부종합", "학생부종합(학업형)", None),
    ("학생부종합", "면접형"): ("수시_종합_면접형", "수시", "학생부종합", "학생부종합(면접형)", None),
    ("학생부종합", "고른기회"): ("수시_종합_고른기회", "수시", "학생부종합", "학생부종합(고른기회)", None),
    ("학생부종합", "사회통합"): ("수시_종합_사회통합", "수시", "학생부종합", "학생부종합(사회통합)", None),
    ("학생부종합", "체육인재"): ("수시_종합_체육인재", "수시", "학생부종합", "학생부종합(체육인재)", None),
    ("논술", None): ("수시_논술", "수시", "논술", "논술", None),
    ("실기/실적", "특기자"): ("수시_실기_특기자", "수시", "실기/실적", "실기/실적(특기자)", None),
}
JEONG = {
    "수능_가": ("정시_수능_가", "정시", "수능", "수능(가군)", "가"),
    "실기_가": ("정시_실기_가", "정시", "실기/실적", "실기/실적(가군)", "가"),
    "수능_나": ("정시_수능_나", "정시", "수능", "수능(나군)", "나"),
    "실기_나": ("정시_실기_나", "정시", "실기/실적", "실기/실적(나군)", "나"),
    "수능_다": ("정시_수능_다", "정시", "수능", "수능(다군)", "다"),
}
# 정시 전형방법 표의 '실기/실적(가군)' / '실기/실적(나군)' 모집단위 (PDF에서 존재 확인함)
JEONG_SILGI = {"가": ["성악과", "작곡과", "피아노과"], "나": ["관현악과"]}


def norm(s):
    return re.sub(r"\s+", "", s or "")


def to_int(s):
    t = norm(s)
    if t in ("", "-"):
        return 0
    if not re.fullmatch(r"\d{1,3}(,\d{3})*|\d+", t):
        raise ValueError(f"숫자 아님: {s!r}")
    return int(t.replace(",", ""))


def is_paren(s):
    return bool(re.fullmatch(r"\(\d[\d,]*\)", norm(s)))


def find_pages(pdf):
    first = None
    for i, p in enumerate(pdf.pages, 1):
        t = p.extract_text() or ""
        if "정원 내 모집인원" in t and "모집단위(학과)" in t:
            first = i
            break
    if first is None:
        raise SystemExit("'정원 내 모집인원' 표를 찾지 못함")
    pages = [first]
    for i in range(first + 1, min(first + 4, len(pdf.pages) + 1)):
        t = pdf.pages[i - 1].extract_text() or ""
        if "정원 외 모집인원" in t:
            break
        if "모집단위(학과)" in t and "추천형" in t:
            pages.append(i)
    return pages


def page_table(page):
    base = max(page.find_tables(), key=lambda t: len(t.rows))
    x0, _, x1, _ = base.bbox
    # 좌우 바깥선이 일부 행에서 빠져 있어 명시적으로 넣는다.
    return max(page.find_tables({"explicit_vertical_lines": [x0, x1]}), key=lambda t: len(t.rows)).extract()


def map_header(rows):
    r0, r1, r2 = rows[0], rows[1], rows[2]
    if [norm(c) for c in r0[:4]] != ["대학", "계열", "모집단위(학과)", "모집인원"]:
        raise SystemExit(f"앞 4열 헤더가 예상과 다름: {r0[:4]}")
    cols = {}
    top = None
    for j in range(4, len(r0)):
        if r1[j] is not None:
            top = norm(r1[j])
        sub = norm(r2[j]) if r2[j] else None
        if top in ("수시계", "정시계"):
            cols[j] = top
        elif top.startswith("수능(가군)"):
            cols[j] = "가"
        elif top.startswith("수능(나군)"):
            cols[j] = "나"
        elif top == "수능(다군)":
            cols[j] = "다"
        elif (top, sub) in SUSI_COLS:
            cols[j] = SUSI_COLS[(top, sub)]
        elif (top, sub) == ("실기/실적", None):
            # 둘째 쪽 머리글에는 '특기자' 글자가 없다. 첫 쪽과 열 구성이 같은지 main에서 확인한다.
            cols[j] = SUSI_COLS[("실기/실적", "특기자")]
        else:
            raise SystemExit(f"알 수 없는 열 헤더: col{j} ({top}, {sub})")
    return cols


def merge_names(names):
    if len(names) == 1:
        return names[0]
    ms = [re.fullmatch(r"(.+)\((.+)\)", n) for n in names]
    if all(ms) and len({m.group(1) for m in ms}) == 1:
        return f"{ms[0].group(1)}({'+'.join(m.group(2) for m in ms)})"
    return "+".join(names)


def find_jeong_check(pdf):
    """'주요 변경사항' 2028 행에서 정시 가군 실기/실적, 나군 실기/실적 인원을 읽는다."""
    for i, p in enumerate(pdf.pages, 1):
        t = p.extract_text() or ""
        if "2028학년도 전형별 모집인원" not in t:
            continue
        m = re.search(r"^2028 ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+) [\d.]+% ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+)",
                      t, re.M)
        if m:
            return i, to_int(m.group(6)), to_int(m.group(8))
    return None


def verify_silgi_source(pdf):
    for i, p in enumerate(pdf.pages, 1):
        t = p.extract_text() or ""
        if "실기/실적" in t and "전형방법" in t and all(d in t for d in JEONG_SILGI["가"] + ["관현악과"]) \
                and "선발 계열/학과" in t:
            return i
    raise SystemExit("정시 실기/실적 모집단위 근거 쪽을 찾지 못함")


def main(pdf_path, out_path):
    pdf = pdfplumber.open(pdf_path)
    pages = find_pages(pdf)
    silgi_page = verify_silgi_source(pdf)

    raw = []  # (page, row, cols)
    cols = None
    total_row = None
    for pno in pages:
        rows = page_table(pdf.pages[pno - 1])
        c = map_header(rows)
        if cols is None:
            cols = c
        elif c != cols:
            raise SystemExit(f"{pno}쪽 열 구성이 첫 쪽과 다름")
        college = None
        for r in rows[3:]:
            if r[0] and norm(r[0]).startswith("합계"):
                total_row = r
                break
            if r[0]:
                college = norm(r[0])
            raw.append((pno, college, r))

    num_cols = [j for j in cols]
    # 세로 병합 셀(다음 행 값이 None) 묶기
    groups = []
    for pno, college, r in raw:
        if groups and any(r[j] is None for j in num_cols) and r[3] is None:
            groups[-1].append((pno, college, r))
        else:
            groups.append([(pno, college, r)])

    units, excluded, problems, merged_notes = [], [], [], []
    for g in groups:
        pno, college, r0 = g[0]
        names = [norm(r[2]) for _, _, r in g]
        if any(is_paren(r[3]) for _, _, r in g):
            excluded.append(f"{merge_names(names)}{norm(r0[3])}")
            continue
        series = [norm(r[1]) for _, _, r in g if r[1]]
        series = series[0] if series else None
        dept = merge_names(names)
        try:
            total = to_int(r0[3])
            vals = {}
            for j, kind in cols.items():
                v = sum(to_int(r[j]) for _, _, r in g if r[j] is not None)
                vals[j] = v
        except ValueError as e:
            problems.append(f"{dept}: {e}")
            continue
        inwon = {}
        for j, kind in cols.items():
            v = vals[j]
            if not v or kind in ("수시계", "정시계"):
                continue
            if isinstance(kind, tuple):
                k = kind[0]
            else:  # 정시 군
                is_silgi = any(names[0].startswith(d) for d in JEONG_SILGI.get(kind, []))
                k = JEONG[("실기_" if is_silgi else "수능_") + kind][0]
            inwon[k] = inwon.get(k, 0) + v
        s = sum(inwon.values())
        # 행 안의 수시계/정시계 칸도 대조
        sj = {cols[j]: vals[j] for j in cols if cols[j] in ("수시계", "정시계")}
        su = sum(v for k, v in inwon.items() if k.startswith("수시_"))
        jo = sum(v for k, v in inwon.items() if k.startswith("정시_"))
        if (su, jo) != (sj.get("수시계"), sj.get("정시계")):
            problems.append(f"{dept}: 수시계/정시계 칸({sj}) != 전형별 합(수시 {su}, 정시 {jo})")
        if len(g) > 1:
            merged_notes.append(
                f"{dept}: 모집인원·일부 전형 칸이 병합 셀이라 한 행으로 합침 — PDF 행별 값: "
                + "; ".join(
                    names[i] + " " + ", ".join(
                        f"{(cols[j][0] if isinstance(cols[j], tuple) else '정시' + cols[j] + '군')} {norm(r[j])}"
                        for j in cols if isinstance(cols[j], tuple) or cols[j] in ("가", "나", "다")
                        if r[j] not in (None, "") and to_int(r[j]))
                    for i, (_, _, r) in enumerate(g))
                + " (병합 칸 값은 첫 행에 표시)")
        units.append({
            "단과대학": college,
            "모집단위": dept,
            "계열": series,
            "인원": inwon,
            "계": total,
            "쪽": pno,
            "검증": "합계일치" if s == total else "합계불일치",
        })

    jeonhyeong = [{"key": v[0], "시기": v[1], "유형": v[2], "전형명": v[3], "군": v[4]}
                  for v in list(SUSI_COLS.values()) + list(JEONG.values())]
    used = {k for u in units for k in u["인원"]}
    jeonhyeong = [j for j in jeonhyeong if j["key"] in used]

    memo = [
        "정원내만 수록. 정원외(기회균형선발·특성화고교졸업자·특수교육대상자·농어촌학생·특성화고졸재직자 등)와 재외국민은 넣지 않음",
        "정원외 채용조건형 계약학과(괄호 숫자) 제외: " + ", ".join(excluded),
        f"정시 가·나군 칸은 수능·실기/실적 공용 칸임. {silgi_page}쪽 전형방법 표에 따라 성악과·작곡과·피아노과(가군), "
        "관현악과(나군)만 실기/실적으로, 나머지는 수능으로 분류(연극영화학과 연출및스탭·연기, 스포츠사이언스전공은 표상 '수능' 구분)",
        "계는 표의 '모집인원' 칸, 쪽 번호는 PDF 파일 기준 1부터. 단과대학은 표의 '대학' 칸 그대로(예: 공과, 인문과학)",
        "계열은 표의 '계열' 칸 그대로(자연/인문/상경/예체능/인문/자연 등)",
    ] + merged_notes

    jc = find_jeong_check(pdf)
    sg = sum(u["인원"].get("정시_실기_가", 0) for u in units)
    sn = sum(u["인원"].get("정시_실기_나", 0) for u in units)
    if jc:
        memo.append(f"정시 실기/실적 분류 대조({jc[0]}쪽 2028 전형별 모집인원): 가군 {sg}={jc[1]}, 나군 {sn}={jc[2]}"
                    + ("" if (sg, sn) == (jc[1], jc[2]) else " (불일치)"))

    # 총계 대조: 같은 표의 '합계' 행(괄호 안 계약학과 인원은 별도 표기)
    su = sum(v for u in units for k, v in u["인원"].items() if k.startswith("수시_"))
    jo = sum(v for u in units for k, v in u["인원"].items() if k.startswith("정시_"))
    if total_row is not None:
        def first_num(s):
            m = re.match(r"\s*([\d,]+)", s or "")
            return to_int(m.group(1)) if m else None
        jt = {cols[j]: first_num(total_row[j]) for j in cols if cols[j] in ("수시계", "정시계")}
        tt = first_num(total_row[3])
        memo.append(f"총계 대조: 수시 {su}={jt.get('수시계')}, 정시 {jo}={jt.get('정시계')}, 전체 {su + jo}={tt}"
                    + ("" if (su, jo, su + jo) == (jt.get("수시계"), jt.get("정시계"), tt) else " (불일치)")
                    + f" (표 합계행, {pages[-1]}쪽)")
        colbad = []
        for j, kind in cols.items():
            if not isinstance(kind, tuple):
                continue
            tv = first_num(total_row[j])
            pv = sum(u["인원"].get(kind[0], 0) for u in units)
            if tv != pv:
                colbad.append(f"{kind[0]} {pv}!={tv}")
        memo.append("전형별 열 합계 대조: " + ("모두 일치" if not colbad else "불일치 " + ", ".join(colbad)))
    else:
        memo.append("총계 대조: 합계 행을 찾지 못함")
    if problems:
        memo.append("확인 필요: " + "; ".join(problems))

    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": sorted(set(pages + [silgi_page] + ([jc[0]] if jc else []))),
           "전형": jeonhyeong, "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    n_ok = sum(u["검증"] == "합계일치" for u in units)
    n_bad = sum(u["검증"] == "합계불일치" for u in units)
    n_none = sum(u["검증"] == "합계칸없음" for u in units)
    print(f"{UNIV_ID}: {len(units)}행 (합계일치 {n_ok}, 불일치 {n_bad}, 합계칸없음 {n_none})")
    for m in memo:
        print(" -", m)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
