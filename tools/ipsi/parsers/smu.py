#!/usr/bin/env python3
"""상명대학교(서울캠퍼스) 2028 시행계획 파서.

대상 표: "2028학년도 신입학전형 모집인원 총괄표" (PDF 8쪽, 인쇄 쪽번호 1) — 수시·정시가 한 표에 있다.
이 PDF는 서울캠퍼스 자료이며 천안캠퍼스 표는 없다.
모집단위 이름은 1~3단(학부/전공/세부전공) 병합 셀이라 셀 위치로 읽고, 모집계열은 계열 칸 경계선으로 묶는다.
사용법: python3 -I tools/ipsi/parsers/smu.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "smu"
UNIV_NAME = "상명대학교"

COL_IPHAK = 4
COLS = {
    "수시_교과_고교추천": 5,
    "수시_종합_상명인재": 6,
    "수시_종합_기회균형": 7,
    "수시_종합_특성화고졸재직자": 8,
    "수시_논술_논술": 9,
    "수시_실기_실기": 10,
    "정시_수능_나": 15,
}
COLS_TRIANGLE_ONLY = {16: "정시 학생부종합(특성화고졸재직자전형) 정원내", 17: "정시 실기/실적(실기전형)"}
COLS_OUT = {11: "수시 서해5도학생", 12: "수시 특성화고졸재직자(정원외)", 13: "수시 특수교육대상자",
            18: "정시 농어촌학생", 19: "정시 특성화고교졸업자", 20: "정시 특성화고졸재직자(정원외)"}
EXPECT_HDR = {
    0: {0: "모집계열", 1: "모집단위", 4: "입학정원", 5: "수시모집", 15: "정시모집", 21: "계"},
    1: {5: "정원내", 11: "정원외", 14: "계", 15: "나군"},
    2: {5: "학생부교과", 6: "학생부종합", 9: "논술", 10: "실기/실적", 11: "학생부교과", 12: "학생부종합",
        15: "정원내", 18: "정원외"},
    3: {15: "수능", 16: "학생부종합", 17: "실기/실적", 18: "수능", 20: "학생부종합"},
    4: {5: "고교추천전형", 6: "상명인재전형", 7: "기회균형전형", 8: "특성화고졸재직자전형*", 9: "논술전형",
        10: "실기전형", 11: "서해5도학생전형", 12: "특성화고졸재직자전형*", 13: "특수교육대상자전형",
        15: "수능전형", 16: "특성화고졸재직자전형*", 17: "실기전형", 18: "농어촌학생전형",
        19: "특성화고교졸업자전형", 20: "특성화고졸재직자전형*"},
}
N_HEADER = 5

JEONHYEONG = [
    {"key": "수시_교과_고교추천", "시기": "수시", "유형": "학생부교과", "전형명": "고교추천전형", "군": None},
    {"key": "수시_종합_상명인재", "시기": "수시", "유형": "학생부종합", "전형명": "상명인재전형", "군": None},
    {"key": "수시_종합_기회균형", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형전형", "군": None},
    {"key": "수시_종합_특성화고졸재직자", "시기": "수시", "유형": "학생부종합",
     "전형명": "특성화고졸재직자전형(전형기간 자율화모집, 정원내)", "군": None},
    {"key": "수시_논술_논술", "시기": "수시", "유형": "논술", "전형명": "논술전형", "군": None},
    {"key": "수시_실기_실기", "시기": "수시", "유형": "실기/실적", "전형명": "실기전형", "군": None},
    {"key": "정시_수능_나", "시기": "정시", "유형": "수능", "전형명": "수능전형", "군": "나"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]
GYEYEOL = {"인문", "자연", "예체능"}


def norm(s):
    return re.sub(r"\s+", "", s or "")


def to_int(cell):
    s = norm(cell).replace(",", "")
    if s in ("", "-"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {cell!r}")


def is_triangle(cell):
    return norm(cell) == "△"


def words_in(words, x0, x1, top, bottom):
    sel = [w for w in words
           if x0 <= (w["x0"] + w["x1"]) / 2 <= x1 and top <= (w["top"] + w["bottom"]) / 2 <= bottom]
    return sorted(sel, key=lambda w: (round(w["top"]), w["x0"]))


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        target = None
        for pno, page in enumerate(pdf.pages, start=1):
            if "모집인원총괄표" not in norm(page.extract_text() or ""):
                continue
            for t in page.find_tables():
                rows = t.extract()
                if rows and norm(rows[0][0]) == "모집계열" and len(rows[0]) == 22:
                    target = (pno, page, t, rows)
                    break
            if target:
                break
        if not target:
            raise SystemExit("모집인원 총괄표를 찾지 못함")
        pno, page, table, rows = target
        for ri, exp in EXPECT_HDR.items():
            for ci, e in exp.items():
                if norm(rows[ri][ci]) != e:
                    raise SystemExit(f"머리글 불일치 row{ri} col{ci}: {rows[ri][ci]!r} != {e}")

        words = page.extract_words()
        # 열 경계
        col_x = [(c.bbox[0], c.bbox[2]) for c in table.columns]
        g_x0, g_x1 = table.bbox[0], col_x[1][0]          # 모집계열 칸
        n_x0, n_x1 = col_x[1][0], col_x[COL_IPHAK][0]   # 모집단위 칸(1~3단)
        # 모집계열 묶음 경계: 계열 칸 폭 전체를 덮는 가로선
        g_lines = sorted({round(e["top"], 1) for e in page.edges
                          if e["orientation"] == "h" and e["x0"] <= g_x0 + 2 and e["x1"] >= g_x1 - 2})
        # 모집단위 칸 안의 셀(병합 포함)
        name_cells = [c for c in table.cells if n_x0 - 1 <= c[0] and c[2] <= n_x1 + 1]

        units, triangles, out_nonzero = [], [], []
        pdf_total = pdf_total2 = None
        iphak_groups = {}  # 입학정원 셀 bbox → (값, [모집단위])
        last_iphak = None
        for ri in range(N_HEADER, len(rows)):
            r, trow = rows[ri], table.rows[ri]
            if norm(r[0]) == "계":
                pdf_total, pdf_total2 = r, rows[ri + 1]
                break
            ref = next(c for c in trow.cells[COL_IPHAK + 1:] if c is not None)
            top, bottom = ref[1], ref[3]
            mid = (top + bottom) / 2
            parts = []
            for c in sorted([c for c in name_cells if c[1] - 0.5 <= mid <= c[3] + 0.5], key=lambda c: c[0]):
                txt = "".join(w["text"] for w in words_in(words, c[0], c[2], c[1], c[3]))
                if txt:
                    parts.append(txt)
            if not parts:
                raise SystemExit(f"이름 없는 행 row{ri}")
            name = parts[0] if len(parts) == 1 else " ".join(parts[:2]) + "".join(f"({p})" for p in parts[2:])
            # 모집계열
            gtop = max(h for h in g_lines if h <= mid)
            gbot = min(h for h in g_lines if h >= mid)
            gtxt = "".join(w["text"] for w in words_in(words, g_x0, g_x1, gtop, gbot))
            gyeyeol = gtxt if gtxt in GYEYEOL else None
            if gyeyeol is None:
                raise SystemExit(f"{name}: 계열 못 읽음 {gtxt!r}")

            inwon = {}
            for k, ci in COLS.items():
                if is_triangle(r[ci]):
                    triangles.append(f"{name} {k}")
                    continue
                v = to_int(r[ci])
                if v:
                    inwon[k] = v
            for ci, lab in COLS_TRIANGLE_ONLY.items():
                if r[ci] is not None and norm(r[ci]) not in ("", "△"):
                    raise SystemExit(f"{name}: {lab} 칸에 △ 아닌 값 {r[ci]!r}")
                if is_triangle(r[ci]):
                    triangles.append(f"{name} {lab}")
            for ci, lab in COLS_OUT.items():
                if r[ci] is not None and norm(r[ci]) not in ("", "△"):
                    out_nonzero.append(f"{name}:{lab} {norm(r[ci])}")
            # 입학정원(병합 셀이면 묶어서 대조)
            ic = trow.cells[COL_IPHAK]
            if ic is not None:
                last_iphak = (round(ic[1], 1), to_int(r[COL_IPHAK]))
                iphak_groups[last_iphak] = []
            iphak_groups[last_iphak].append(name)

            units.append({
                "단과대학": None,
                "모집단위": name,
                "계열": gyeyeol,
                "인원": inwon,
                "계": None,
                "쪽": pno,
                "검증": "합계칸없음",
            })

    if pdf_total is None:
        raise SystemExit("계 행 없음")
    # 입학정원 대조
    by_name = {u["모집단위"]: u for u in units}
    ip_ok, ip_bad = 0, []
    for (_, val), names in iphak_groups.items():
        s = sum(sum(by_name[n]["인원"].values()) for n in names)
        if s == val:
            ip_ok += 1
        else:
            ip_bad.append(f"{'+'.join(names)}: 입학정원 {val} vs 정원내 합 {s}")

    tot = {k: (None if is_triangle(pdf_total[ci]) else to_int(pdf_total[ci])) for k, ci in COLS.items()}
    s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
    j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
    s_pdf = to_int(pdf_total2[5])   # 수시 정원내 소계(둘째 줄)
    j_pdf = to_int(pdf_total2[15])  # 정시 정원내 소계(둘째 줄)
    bad_cols = [k for k in COLS if tot[k] != sum(u["인원"].get(k, 0) for u in units)]

    memo = [
        "서울캠퍼스 자료(표지 '[서울캠퍼스]'). 이 PDF에 천안캠퍼스 표는 없음",
        "정원내만 수록: 수시 정원외(서해5도학생 6, 특성화고졸재직자 143, 특수교육대상자 7), 정시 정원외(농어촌학생 52, "
        "특성화고교졸업자 20, 특성화고졸재직자 △)는 넣지 않음",
        "수시_종합_특성화고졸재직자(융합경영학과 1명): 표 각주상 전형기간 자율화모집이지만 표가 수시모집 정원내 학생부종합 열에 두고 "
        "수시 정원내 소계 811에 포함하므로 수시로 수록",
        "'△'(수시 미충원 이월인원만 정시에서 선발) 칸은 숫자가 없어 0으로 봄: 국가안보학과 정시 수능전형, 정시 실기전형(예체능 "
        "실기 모집단위 전부), 정시 특성화고졸재직자(정원내) 등 — 정시 실기전형·특성화고졸재직자(정원내)는 숫자가 하나도 없어 전형 목록에서 뺌",
        "계: 표에 행별 정원내 합계 칸이 없음(수시 계 967·정시 계 563은 전체 병합 칸이고 정원외 포함) → 계=null, 검증='합계칸없음'",
        f"참고 대조(입학정원 칸 = 행 정원내 합, 무용예술전공·음악학부처럼 입학정원이 병합된 경우 묶음 합): "
        f"{ip_ok}/{len(iphak_groups)} 일치" + (" — 불일치: " + "; ".join(ip_bad) if ip_bad else ""),
        "모집단위 이름: '학부 전공(세부)' 형식. 무용예술전공(한국무용/현대무용/발레), 음악학부(피아노/성악 남·여/뉴미디어작곡/관현악)는 "
        "표가 세부전공별 실기전형 인원을 따로 적어 세부전공별 행으로 둠",
        "계열: 표의 '모집계열' 칸 그대로(인문/자연/예체능). 단과대학: 표에 칸이 없어 null",
        f"총계 대조: 수시 {s_pdf}={s_me}, 정시 {j_pdf}={j_me}, 전체 정원내 {to_int(pdf_total[COL_IPHAK])}(입학정원 계)={s_me + j_me} (PDF 계 행)",
        "전형별 열 합 대조(PDF 계 행): " + ("모두 일치" if not bad_cols else "불일치 " + ", ".join(bad_cols)),
    ]

    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": [pno], "전형": JEONHYEONG, "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(units)}행 → {out_path}")
    for m in memo:
        print(" -", m)
    print(" - (확인용) 정원외 칸 값:", out_nonzero)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: smu.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
