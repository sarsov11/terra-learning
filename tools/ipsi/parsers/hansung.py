#!/usr/bin/env python3
"""한성대학교 2028 시행계획 파서.

대상 표: "Ⅰ-1. 전형별 모집인원 (정원내)" (PDF 2쪽) 한 장.
단과대학·학부 칸은 세로 병합이 많아서, 열 경계와 행 경계로 각 칸을 덮는 셀을 찾아 이름을 읽는다.
사용법: python3 -I tools/ipsi/parsers/hansung.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "hansung"
UNIV_NAME = "한성대학교"

# 열 번호 → 전형 key (머리글 문구로 위치를 확인한다)
COLS = {
    "수시_논술": 3,
    "수시_교과_교과우수": 4,
    "수시_교과_지역균형": 5,
    "수시_종합_한성인재": 6,
    "수시_종합_고른기회": 7,
    "수시_종합_성인학습자": 8,
    "수시_실기": 9,
    "정시_수능_가": 11,
    "정시_수능_나": 12,
    "정시_수능_다": 13,
    "정시_실기_다": 14,
}
COL_SUSI_SUM = 10
COL_JEONGSI_SUM = 15
COL_TOTAL = 16
# (행, 열) → 기대 머리글(공백·줄바꿈 제거)
EXPECT_HDR = {
    (0, 3): "논술위주", (0, 4): "수시모집", (0, 10): "수시소계(A)", (0, 11): "정시모집",
    (0, 15): "정시소계(B)", (0, 16): "합계(A+B)",
    (1, 4): "학생부교과", (1, 6): "학생부종합", (1, 9): "실기위주", (1, 11): "수능", (1, 14): "실기위주",
    (2, 3): "논술", (2, 4): "교과우수", (2, 5): "지역균형", (2, 6): "한성인재", (2, 7): "기회균형",
    (2, 9): "실기", (2, 11): "가군", (2, 12): "나군", (2, 13): "다군", (2, 14): "다군",
    (3, 7): "고른기회", (3, 8): "성인학습자",
}
N_HEADER = 4

JEONHYEONG = [
    {"key": "수시_논술", "시기": "수시", "유형": "논술", "전형명": "논술전형", "군": None},
    {"key": "수시_교과_교과우수", "시기": "수시", "유형": "학생부교과", "전형명": "교과우수전형", "군": None},
    {"key": "수시_교과_지역균형", "시기": "수시", "유형": "학생부교과", "전형명": "지역균형전형", "군": None},
    {"key": "수시_종합_한성인재", "시기": "수시", "유형": "학생부종합", "전형명": "한성인재전형", "군": None},
    {"key": "수시_종합_고른기회", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형(고른기회)전형", "군": None},
    {"key": "수시_종합_성인학습자", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형(성인학습자)전형", "군": None},
    {"key": "수시_실기", "시기": "수시", "유형": "실기/실적", "전형명": "실기우수자전형", "군": None},
    {"key": "정시_수능_가", "시기": "정시", "유형": "수능", "전형명": "일반학생전형", "군": "가"},
    {"key": "정시_수능_나", "시기": "정시", "유형": "수능", "전형명": "일반학생전형", "군": "나"},
    {"key": "정시_수능_다", "시기": "정시", "유형": "수능", "전형명": "일반학생전형", "군": "다"},
    {"key": "정시_실기_다", "시기": "정시", "유형": "실기/실적", "전형명": "일반학생전형(실기)", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]
assert [j["key"] for j in JEONHYEONG] == list(COLS)


def norm(s):
    return re.sub(r"\s+", "", s or "")


def to_int(cell):
    """빈칸·'-' → 0, '♣…'(수시 미충원 이월 표시) → 0, 숫자 → int. 그 밖은 오류."""
    s = (cell or "").strip().replace(",", "")
    if s in ("", "-"):
        return 0, "blank"
    if s.startswith("♣"):
        return 0, "club"
    if re.fullmatch(r"\d+", s):
        return int(s), "num"
    raise ValueError(f"숫자 아님: {cell!r}")


def find_table(pdf):
    for pno, page in enumerate(pdf.pages, start=1):
        txt = page.extract_text() or ""
        if "전형별 모집인원 (정원내)" not in txt:
            continue
        for t in page.find_tables():
            rows = t.extract()
            if rows and norm(rows[0][0]) == "단과대학" and norm(rows[0][1]) == "모집단위":
                return pno, page, t, rows
    raise SystemExit("전형별 모집인원(정원내) 표를 찾지 못함")


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        pno, page, table, rows = find_table(pdf)

        for (r, c), exp in EXPECT_HDR.items():
            if norm(rows[r][c]) != exp:
                raise SystemExit(f"머리글 불일치 ({r},{c}): {rows[r][c]!r} != {exp}")

        # 셀 bbox → 글자
        text_of = {}
        for trow, rtext in zip(table.rows, rows):
            for bbox, txt in zip(trow.cells, rtext):
                if bbox is not None:
                    text_of[tuple(bbox)] = txt or ""
        xs = sorted({round(c[0], 1) for c in table.cells} | {round(table.bbox[2], 1)})
        if len(xs) != len(rows[0]) + 1:
            raise SystemExit(f"열 경계 수 다름: {len(xs)}")

        def cover(ri, ci):
            """(행, 열) 칸을 덮는 셀의 (bbox, 글자)."""
            # 행의 세로 범위는 맨 오른쪽 합계 칸(병합 없음)으로 정한다. Row.bbox는 병합 칸까지 넓어짐.
            rb = table.rows[ri].cells[COL_TOTAL]
            if rb is None:
                raise SystemExit(f"행 {ri}: 합계 칸 없음")
            cx = (xs[ci] + xs[ci + 1]) / 2
            cy = (rb[1] + rb[3]) / 2
            for bbox, txt in text_of.items():
                if bbox[0] - 0.5 <= cx <= bbox[2] + 0.5 and bbox[1] - 0.5 <= cy <= bbox[3] + 0.5:
                    return bbox, txt
            return None, ""

        units, memo_rows = [], []
        pdf_total = None
        club_rows, sub_ok, sub_bad = [], 0, []
        for ri in range(N_HEADER, len(rows)):
            r = rows[ri]
            c0_bbox, c0 = cover(ri, 0)
            if norm(c0) == "합계":
                pdf_total = {k: to_int(r[i])[0] for k, i in COLS.items()}
                pdf_total["수시소계"] = to_int(r[COL_SUSI_SUM])[0]
                pdf_total["정시소계"] = to_int(r[COL_JEONGSI_SUM])[0]
                pdf_total["합계"] = to_int(r[COL_TOTAL])[0]
                continue
            college = norm(c0)
            g_bbox, grp = cover(ri, 1)
            s_bbox, sub = cover(ri, 2)
            grp_lines = [x.strip() for x in grp.split("\n") if x.strip()]
            if g_bbox == s_bbox:
                # 모집단위 칸이 두 열에 걸침 → 하위 칸 없음
                name = " ".join(grp_lines)
                sub_lines = []
            else:
                sub_lines = [x.strip() for x in sub.split("\n") if x.strip()]
                grp_name = "".join(grp_lines)
                if len(sub_lines) > 1:
                    # 한 숫자 행에 여러 학부가 적힌 통합 모집단위(IT공과대학)
                    name = grp_name
                    memo_rows.append(f"{name}: 한 행에 {'·'.join(sub_lines)}가 함께 적힌 통합 모집단위 → 1행으로 둠")
                elif re.search(r"(학과|학부)$", sub_lines[0]):
                    name = sub_lines[0]  # 학부 아래 학과(이름만으로 완결)
                else:
                    name = f"{grp_name}({sub_lines[0]})"  # 예술학부 아래 전공
            if name.endswith(" 자율전공"):
                memo_rows.append(f"{name}: 표의 '자율전공' 표시 상자는 이름에서 뺌")
                name = name[: -len(" 자율전공")]
            if not name or not college:
                raise SystemExit(f"이름 없는 행 {ri}: {r}")

            inwon = {}
            for k, i in COLS.items():
                v, st = to_int(r[i])
                if v:
                    inwon[k] = v
            js, js_st = to_int(r[COL_JEONGSI_SUM])
            if js_st == "club":
                club_rows.append(f"{name}({norm(r[COL_JEONGSI_SUM])})")
            susi = to_int(r[COL_SUSI_SUM])[0]
            gye = to_int(r[COL_TOTAL])[0]
            s_me = sum(inwon.get(k, 0) for k in SUSI_KEYS)
            j_me = sum(inwon.get(k, 0) for k in JEONGSI_KEYS)
            if s_me == susi and j_me == js:
                sub_ok += 1
            else:
                sub_bad.append(f"{name}(수시소계 {susi} vs {s_me}, 정시소계 {js} vs {j_me})")
            units.append({
                "단과대학": college,
                "모집단위": name,
                "계열": None,
                "인원": inwon,
                "계": gye,
                "쪽": pno,
                "검증": "합계일치" if sum(inwon.values()) == gye else "합계불일치",
            })

    memo = [
        "정원내만 수록(PDF 2쪽 '전형별 모집인원 (정원내)' 표). 정원외(농어촌학생·특성화고교졸업자·특성화고교졸재직자, "
        "재외국민·전교육과정이수자·북한이탈주민·부모모두외국인, 글로벌인재대학 정원외 전담 모집단위)는 넣지 않음",
        "계 = 표의 '합계(A+B)' 칸",
        "수시 학생부종합 기회균형(고른기회·성인학습자)은 정원내 표에 있어 수록. 성인학습자(미래플러스대학 AI디지털융합인재학부 21명)는 "
        "표 각주상 '전형기간자율화' 전형이지만 표에서 수시모집 열·수시 소계(A)에 들어 있어 시기=수시로 둠",
        "정시 칸의 '♣'(수시모집 미충원 시 이월 인원 선발 표시)는 숫자가 없어 0으로 봄: " + ", ".join(club_rows),
        "단과대학 = 표의 단과대학 칸(줄바꿈 이어 붙임). 계열: 표에 계열 칸이 없어 null",
        "예술학부 아래 전공(동양화 등)은 '예술학부(전공)'으로, AI학부·AI융합학부 아래 학과는 학과 이름만 적음",
        f"보조 대조(행별 수시 소계(A)·정시 소계(B) 칸 = 전형 칸 합): {sub_ok}/{len(units)}행 일치"
        + (" — 불일치 " + "; ".join(sub_bad) if sub_bad else ""),
    ] + memo_rows
    if pdf_total:
        s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
        j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
        memo.append(f"총계 대조(PDF 합계 행): 수시 {pdf_total['수시소계']}={s_me}, 정시 {pdf_total['정시소계']}={j_me}, "
                    f"전체 {pdf_total['합계']}={s_me + j_me}")
        bad = [k for k in COLS if pdf_total[k] != sum(u["인원"].get(k, 0) for u in units)]
        memo.append("전형별 열 합 대조(합계 행): " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)))
    else:
        raise SystemExit("합계 행을 찾지 못함")

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
        raise SystemExit("usage: hansung.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
