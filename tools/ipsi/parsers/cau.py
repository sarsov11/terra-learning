#!/usr/bin/env python3
"""중앙대학교 2028 시행계획 -> norm JSON.

원천: '2028학년도 신입학 모집인원 총괄표' (3쪽, 수시+정시 한 표).
- 열마다 머리글 글자를 확인한 뒤 고정 의미를 붙인다(아래 COLS). 머리글이 다르면 멈춘다.
- 정원외 열: 재외국민, 수시 기회균형(장애인 등 대상자, 특성화고졸재직), 정시 계약정원, 정시 기회균형 전부.
- 수시 기회균형(농어촌학생, 수급자및차상위) 열은 모집단위별로 정원 내/외가 갈리며 정원외 칸은 음영으로 표시된다
  (표 각주). 음영 칸(채움색 CMYK 0,0.2,0.2,0)은 정원외로 보고 뺀다. 음영 판정은 '한눈에 보는 입학전형'의
  정원내/정원외 인원(농어촌 71/70, 수급자 44/30)과 대조한다.
- 행 '합계' 칸은 수시 합계·정시 합계로 나뉘고 둘 다 정원외를 포함하므로 정원내 '계'로 쓸 수 없다 -> 계 null.
  대신 행마다 '수시 합계 = 수시 전 칸(정원외 포함) 합', '정시 합계 = 정시 전 칸 합'을 확인해 메모에 남긴다.
- 'O' 표기(수시 장애인등: 선발 가능 표시, 정시 실기/실적: 수시 이월 시 선발)는 인원이 아니므로 0.

usage: python3 -I tools/ipsi/parsers/cau.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "cau"
UNIV_NAME = "중앙대학교"
SHADE = (0.0, 0.2, 0.2, 0.0)

# 열 번호 -> (기대 머리글(5행 또는 6행, 공백 제거), 의미)
#   의미: ("in", 시기, 유형, 전형명, key접두) 정원내(수시 기회균형 2열은 음영이면 정원외)
#         ("out",) 정원외, ("sum_susi",), ("sum_jeong",), ("gun",)
COLS = {
    6: ("중고교과정", ("out",)),
    7: ("지역균형", ("in", "수시", "학생부교과", "학생부교과(지역균형)", "수시_교과_지역균형")),
    8: ("탐구하는학종(Core)", ("in", "수시", "학생부종합", "학생부종합(탐구하는 학종(Core))", "수시_종합_Core")),
    9: ("모두의학종(All)", ("in", "수시", "학생부종합", "학생부종합(모두의 학종(All))", "수시_종합_All")),
    10: ("최저있는학종(Up)", ("in", "수시", "학생부종합", "학생부종합(최저 있는 학종(Up))", "수시_종합_Up")),
    11: ("어울림", ("in", "수시", "학생부종합", "학생부종합(어울림)", "수시_종합_어울림")),
    12: ("농어촌학생", ("in", "수시", "학생부종합", "학생부종합(기회균형-농어촌학생) 정원내", "수시_종합_기회균형_농어촌")),
    13: ("수급자및차상위", ("in", "수시", "학생부종합", "학생부종합(기회균형-기초생활수급자및차상위계층) 정원내", "수시_종합_기회균형_수급자")),
    14: ("장애인등대상자1)", ("out",)),
    15: ("특성화고졸재직자", ("out",)),
    16: ("모두의논술", ("in", "수시", "논술", "논술(모두의 논술)", "수시_논술_모두의논술")),
    17: ("재학생논술", ("in", "수시", "논술", "논술(재학생 논술)", "수시_논술_재학생논술")),
    18: ("실기", ("in", "수시", "실기/실적", "실기/실적(실기)", "수시_실기_실기")),
    19: ("특기", ("in", "수시", "실기/실적", "실기/실적(특기)", "수시_실기_특기")),
    20: (None, ("sum_susi",)),
    21: (None, ("gun",)),
    22: ("수능89", ("in", "정시", "수능", "수능위주(수능89)", "정시_수능89")),
    23: ("수능67", ("in", "정시", "수능", "수능위주(수능67)", "정시_수능67")),
    24: ("계약정원", ("out",)),
    25: ("실기", ("in", "정시", "수능", "수능위주(실기)", "정시_수능위주실기")),
    26: ("실기", ("in", "정시", "실기/실적", "실기/실적위주(실기)", "정시_실기")),
    27: ("특성화고교졸업자", ("out",)),
    28: ("농어촌학생", ("out",)),
    29: ("수급자및차상위", ("out",)),
    30: ("특성화고졸재직자", ("out",)),
    31: (None, ("sum_jeong",)),
}
SUSI_COLS = list(range(6, 20))
JEONG_COLS = list(range(22, 31))
# 표 3행(상위 머리글) 확인용
TOP_EXPECT = {7: "학생부", 16: "논술", 18: "실기/실적", 20: "합계", 21: "모집군", 22: "수능", 26: "실기/실적",
              27: "기회균형", 31: "합계"}
# PDF 글리프 오류 보정(이름만): 'ᆞ'(U+119E)가 '·' 자리에 잘못 들어가 순서가 뒤바뀐 경우.
# 10쪽 '개설전공' 표의 '생활·레저스포츠전공' 표기로 확인.
NAME_FIX = {"생활레ᆞ저스포츠,스포츠산업": "생활·레저스포츠,스포츠산업"}


def norm(s):
    return re.sub(r"\s+", "", s or "")


def to_int(s):
    t = norm(s)
    if t in ("", "-", "O"):
        return 0
    if not re.fullmatch(r"\d{1,3}(,\d{3})*|\d+", t):
        raise ValueError(f"숫자 아님: {s!r}")
    return int(t.replace(",", ""))


def find_pages(pdf):
    pages = [i for i, p in enumerate(pdf.pages, 1)
             if "신입학 모집인원 총괄표" in (p.extract_text() or "") and "모집단위명" in (p.extract_text() or "")]
    if not pages:
        raise SystemExit("총괄표 쪽을 찾지 못함")
    return pages


def get_table(page):
    base = max(page.find_tables(), key=lambda t: len(t.rows))
    x0, _, x1, _ = base.bbox
    # 좌우 바깥선이 일부 행에서 빠져 있어 명시적으로 넣는다.
    return max(page.find_tables({"explicit_vertical_lines": [x0, x1]}), key=lambda t: len(t.rows))


def check_header(rows, pno):
    if len(rows[0]) != 32:
        raise SystemExit(f"{pno}쪽 열 수 {len(rows[0])} != 32")
    hi = next(i for i, r in enumerate(rows) if norm(r[0]) == "단과대학")
    top = rows[hi + 1]
    filled, last = [], None
    for c in top:
        last = norm(c) if c is not None else last
        filled.append(last)
    for j, exp in TOP_EXPECT.items():
        if filled[j] != exp:
            raise SystemExit(f"{pno}쪽 상위 머리글 col{j} {filled[j]!r} != {exp!r}")
    r5, r6 = rows[hi + 3], rows[hi + 4]
    for j, (exp, _) in COLS.items():
        if exp is None:
            continue
        got = norm(r6[j]) if 12 <= j <= 15 else norm(r5[j])
        if got != exp:
            raise SystemExit(f"{pno}쪽 머리글 col{j} {got!r} != {exp!r}")
    return hi + 5


def is_shaded(page, bbox):
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    for r in page.rects:
        col = tuple(round(v, 3) for v in (r.get("non_stroking_color") or ()))
        if r.get("fill") and col == SHADE and r["x0"] <= cx <= r["x1"] and r["top"] <= cy <= r["bottom"]:
            return True
    return False


def find_totals(pdf):
    """한눈에 보는 입학전형(정원내/정원외) + 개설전공 표 총계."""
    res = {}
    for i, p in enumerate(pdf.pages, 1):
        t = p.extract_text() or ""
        if "한눈에 보는 2028학년도 입학전형" in t:
            ms = re.search(r"수시 계 ([\d,]+) ([\d,]+) ([\d,]+)", t)
            mj = re.search(r"정시 계 ([\d,]+) ([\d,]+) ([\d,]+)", t)
            mn = re.search(r"농어촌학생 ([\d,]+) ([\d,]+) ([\d,]+)", t)
            mg = re.search(r"종합 ([\d,]+) ([\d,]+) ([\d,]+) 서류 100", t)
            if ms and mj:
                res["page"] = i
                res["수시"] = to_int(ms.group(1))
                res["정시"] = to_int(mj.group(1))
            if mn:
                res["농어촌"] = (to_int(mn.group(1)), to_int(mn.group(2)))
            if mg:
                res["수급자"] = (to_int(mg.group(1)), to_int(mg.group(2)))
        if "개설전공 및 모집인원" in t:
            m = re.search(r"총계 ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+)", t)
            if m:
                res["전체"] = to_int(m.group(2))
                res["전체page"] = i
    return res


def main(pdf_path, out_path):
    pdf = pdfplumber.open(pdf_path)
    pages = find_pages(pdf)

    units, problems = [], []
    rowsum_ok, rowsum_bad = 0, []
    shaded_cells = []
    excluded_units = []
    o_marks = []
    colsum = {j: 0 for j in list(SUSI_COLS) + list(JEONG_COLS) + [20, 31]}
    shade_sum = {12: 0, 13: 0}
    total_row = None
    jeonhyeong = {}

    for pno in pages:
        page = pdf.pages[pno - 1]
        table = get_table(page)
        rows = table.extract()
        start = check_header(rows, pno)
        college = None
        group = None
        for i in range(start, len(rows)):
            r = rows[i]
            cells = table.rows[i].cells
            if norm(r[0]) == "합계":
                total_row = r
                break
            if r[0]:
                college = norm(r[0])
            c1, c2 = (norm(r[1]) or None), (norm(r[2]) or None)
            if c1 and c2:
                group, label = c1, c2
            elif c1:
                group, label = None, c1
            elif c2 and group:
                label = c2
            else:
                problems.append(f"{pno}쪽 이름 없는 행: {r[:8]}")
                continue
            label = NAME_FIX.get(label, label)
            dept = f"{group}({label})" if group else label

            try:
                vals = {j: to_int(r[j]) for j in colsum if r[j] is not None}
            except ValueError as e:
                problems.append(f"{dept}: {e}")
                continue
            for j in colsum:
                if r[j] is not None and norm(r[j]) == "O":
                    if COLS.get(j, (None, ("",)))[1][0] == "in":
                        o_marks.append(f"{dept}[{COLS[j][1][3]}]")
            for j, v in vals.items():
                colsum[j] += v

            # 행 합계칸 대조(정원외 포함)
            ss = sum(vals.get(j, 0) for j in SUSI_COLS if j != 6)
            sj = sum(vals.get(j, 0) for j in JEONG_COLS)
            if ss == vals.get(20, 0) and sj == vals.get(31, 0):
                rowsum_ok += 1
            else:
                rowsum_bad.append(f"{dept}(수시 {ss}/{vals.get(20)}, 정시 {sj}/{vals.get(31)})")

            gun = norm(r[21]) or None
            inwon = {}
            for j, (_, meaning) in COLS.items():
                if meaning[0] != "in":
                    continue
                v = vals.get(j, 0)
                if not v:
                    continue
                if j in (12, 13) and is_shaded(page, cells[j]):
                    shaded_cells.append(f"{dept}:{meaning[4].split('_')[-1]} {v}")
                    shade_sum[j] += v
                    continue
                _, sg, yh, nm, kp = meaning
                if sg == "정시":
                    if gun not in ("가", "나", "다"):
                        problems.append(f"{dept}: 정시 인원이 있는데 모집군 없음")
                        continue
                    key, g = f"{kp}_{gun}", gun
                else:
                    key, g = kp, None
                jeonhyeong.setdefault(key, {"key": key, "시기": sg, "유형": yh, "전형명": nm, "군": g, "_col": j})
                inwon[key] = inwon.get(key, 0) + v
            if not inwon:
                excluded_units.append(dept)
                continue
            units.append({
                "단과대학": college,
                "모집단위": dept,
                "계열": None,
                "인원": inwon,
                "계": None,
                "쪽": pno,
                "검증": "합계칸없음",
            })

    if total_row is None:
        raise SystemExit("합계 행을 찾지 못함")

    jh = sorted(jeonhyeong.values(), key=lambda d: (d["_col"], d["key"]))
    for d in jh:
        d.pop("_col")

    memo = [
        "정원내만 수록. 재외국민, 수시 기회균형(장애인 등 대상자·특성화고졸재직자), 정시 계약정원·기회균형"
        "(특성화고교졸업자·농어촌학생·수급자및차상위·특성화고졸재직자)은 정원외라 넣지 않음",
        "수시 기회균형(농어촌학생·수급자및차상위)은 모집단위별로 정원 내/외가 갈림. 표에서 음영(정원외) 칸 "
        f"{len(shaded_cells)}개는 뺌: " + ", ".join(shaded_cells),
        "계: 표의 행 합계칸이 수시 합계·정시 합계로 나뉘고 둘 다 정원외를 포함해 정원내 계로 쓸 수 없으므로 null(검증=합계칸없음). "
        "'입학정원' 칸은 모집인원이 아니라 쓰지 않음",
        f"행 합계칸 대조(정원외 포함 모든 칸 합 == 수시 합계·정시 합계): {rowsum_ok}행 일치"
        + (f", 불일치 {len(rowsum_bad)}행: " + "; ".join(rowsum_bad) if rowsum_bad else ", 불일치 0"),
        "정시 키는 '<전형>_<모집군>' (모집군은 표의 행별 '모집군' 칸). '수능위주(실기)'는 PDF가 수능위주로 분류해 유형=수능",
        "'O' 표기는 인원이 아니므로 0으로 봄(정시 실기/실적: 수시 이월 시 선발 표시): " + (", ".join(o_marks) or "없음"),
        "정원내 모집인원에는 2026학년도 미충원 이월인원 25명이 포함됨(표 각주)",
        "단과대학은 표의 '단과대학' 칸 글자 그대로(예: 인문, 사회과학, 경영경제). 계열은 표에 없어 null",
        "스포츠과학부 '생활레ᆞ저스포츠' 칸은 PDF 글리프 오류로 보고 10쪽 표기대로 '생활·레저스포츠'로 이름만 고침",
    ]
    if excluded_units:
        memo.append("정원내 인원이 없어 뺀 행(정원외 전용): " + ", ".join(excluded_units))

    # 표 합계 행과 열 합 대조(정원외 포함) — 추출 누락 확인
    # 장애인등(col14)은 행마다 'O'(선발 가능)만 있고 인원 10명은 합계행에만 있으므로 열합 0, 수시 합계(col20)는 그만큼 차이 난다.
    bad = []
    d14 = (to_int(total_row[14]) or 0) - colsum[14]
    for j in colsum:
        tv = to_int(total_row[j]) if total_row[j] is not None else None
        if tv is None:
            continue
        diff = tv - colsum[j]
        if j in (14, 20) and diff == d14:
            continue
        if diff:
            bad.append(f"col{j} 합계행 {tv} != 열합 {colsum[j]}")
    memo.append("표 합계행과 열별 합(정원외 포함) 대조: " + ("모두 일치" if not bad else "; ".join(bad))
                + f" (단, 정원외 장애인등 대상자 {d14}명은 행별 'O' 표시만 있고 합계행에만 숫자가 있어 수시 합계 차이 {d14}로 확인)")

    tot = find_totals(pdf)
    su = sum(v for u in units for k, v in u["인원"].items() if k.startswith("수시_"))
    jo = sum(v for u in units for k, v in u["인원"].items() if k.startswith("정시_"))
    src = []
    if "수시" in tot:
        ok = (su, jo) == (tot["수시"], tot["정시"])
        line = f"총계 대조: 수시 {su}={tot['수시']}, 정시 {jo}={tot['정시']}"
        src.append(tot["page"])
        if "전체" in tot:
            line += f", 전체 {su + jo}={tot['전체']}"
            ok = ok and su + jo == tot["전체"]
            src.append(tot["전체page"])
        memo.append(line + ("" if ok else " (불일치)") + f" (출처 {sorted(set(src))}쪽)")
    else:
        memo.append(f"총계 대조: 정원내 총계를 찾지 못함 (파싱 합 수시 {su}, 정시 {jo})")
    for name, j, key in (("농어촌", 12, "수시_종합_기회균형_농어촌"), ("수급자", 13, "수시_종합_기회균형_수급자")):
        if name in tot:
            pin = sum(u["인원"].get(key, 0) for u in units)
            exp_in, exp_out = tot[name]
            memo.append(f"음영 판정 대조({name}): 정원내 {pin}={exp_in}, 정원외(음영) {shade_sum[j]}={exp_out}"
                        + ("" if (pin, shade_sum[j]) == (exp_in, exp_out) else " (불일치)"))
    if problems:
        memo.append("읽지 못한/확인 필요 행: " + "; ".join(problems))

    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": sorted(set(pages + src)),
           "전형": jh, "모집단위": units, "메모": memo}
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
