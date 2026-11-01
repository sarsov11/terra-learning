#!/usr/bin/env python3
"""서울여자대학교 2028 시행계획 파서.

대상 표: "2028학년도 전형별 모집인원" (PDF 5쪽, 인쇄 쪽번호 4) — 수시·정시·기타가 한 표에 있다.
대학 칸은 세로 병합이고 글자가 줄마다 끊겨 있어, 대학 칸 폭 전체를 덮는 가로선으로 묶어 읽는다.
사용법: python3 -I tools/ipsi/parsers/swu.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "swu"
UNIV_NAME = "서울여자대학교"

COL_GYE = 3
COLS = {
    "수시_종합_바롬인재서류": 4,
    "수시_종합_바롬인재면접": 5,
    "수시_종합_AI융합인재": 6,
    "수시_종합_기독교지도자": 7,
    "수시_종합_사회통합지원": 8,
    "수시_교과_교과우수자": 11,
    "수시_교과_교과우수자체육": 12,
    "수시_논술_논술우수자": 13,
    "수시_실기_실기우수자미술": 14,
    "수시_실기_실기우수자체육": 15,
    "정시_수능_가": 16,
    "정시_수능_나": 17,
    "정시_수능_다": 18,
}
COLS_OUT = {9: "농어촌학생(정원외)", 10: "특성화고교졸업자(정원외)", 19: "특성화고 등 재직자(정원외)"}
EXPECT_HDR = {
    0: {0: "대학", 1: "모집단위", 3: "모집인원(정원내)", 4: "수시", 16: "정시", 19: "기타"},
    1: {4: "학생부종합", 11: "학생부교과", 13: "논술", 14: "실기/실적", 16: "[가]군", 17: "[나]군", 18: "[다]군"},
    2: {4: "바롬인재서류", 5: "바롬인재면접", 6: "AI융합인재", 7: "기독교지도자", 8: "기회균형", 11: "교과우수자★",
        12: "교과우수자(체육)", 13: "논술우수자", 14: "실기우수자(미술)", 15: "실기우수자(체육)", 16: "일반학생",
        17: "일반학생", 18: "일반학생"},
    3: {8: "사회통합지원(정원내)", 9: "농어촌학생(정원외)", 10: "특성화고교졸업자(정원외)"},
}
N_HEADER = 4

JEONHYEONG = [
    {"key": "수시_종합_바롬인재서류", "시기": "수시", "유형": "학생부종합", "전형명": "바롬인재서류전형", "군": None},
    {"key": "수시_종합_바롬인재면접", "시기": "수시", "유형": "학생부종합", "전형명": "바롬인재면접전형", "군": None},
    {"key": "수시_종합_AI융합인재", "시기": "수시", "유형": "학생부종합", "전형명": "AI융합인재전형", "군": None},
    {"key": "수시_종합_기독교지도자", "시기": "수시", "유형": "학생부종합", "전형명": "기독교지도자전형", "군": None},
    {"key": "수시_종합_사회통합지원", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형전형(사회통합지원)", "군": None},
    {"key": "수시_교과_교과우수자", "시기": "수시", "유형": "학생부교과", "전형명": "교과우수자전형", "군": None},
    {"key": "수시_교과_교과우수자체육", "시기": "수시", "유형": "학생부교과", "전형명": "교과우수자전형_체육", "군": None},
    {"key": "수시_논술_논술우수자", "시기": "수시", "유형": "논술", "전형명": "논술우수자전형", "군": None},
    {"key": "수시_실기_실기우수자미술", "시기": "수시", "유형": "실기/실적", "전형명": "실기우수자전형_미술", "군": None},
    {"key": "수시_실기_실기우수자체육", "시기": "수시", "유형": "실기/실적", "전형명": "실기우수자전형_체육", "군": None},
    {"key": "정시_수능_가", "시기": "정시", "유형": "수능", "전형명": "일반학생전형", "군": "가"},
    {"key": "정시_수능_나", "시기": "정시", "유형": "수능", "전형명": "일반학생전형", "군": "나"},
    {"key": "정시_수능_다", "시기": "정시", "유형": "수능", "전형명": "일반학생전형", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]


def norm(s):
    return re.sub(r"[\s\x00]+", "", s or "")


def join_lines(s):
    return "".join(p.strip() for p in (s or "").split("\n")).strip()


def to_int(cell):
    s = norm(cell).replace(",", "")
    if s in ("", "-"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {cell!r}")


def words_in(words, x0, x1, top, bottom):
    sel = [w for w in words
           if x0 <= (w["x0"] + w["x1"]) / 2 <= x1 and top <= (w["top"] + w["bottom"]) / 2 <= bottom]
    return sorted(sel, key=lambda w: (round(w["top"]), w["x0"]))


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        target = None
        for pno, page in enumerate(pdf.pages, start=1):
            if "전형별모집인원" not in norm(page.extract_text() or ""):
                continue
            for t in page.find_tables():
                rows = t.extract()
                if rows and norm(rows[0][0]) == "대학" and norm(rows[0][1]) == "모집단위" and len(rows[0]) == 20:
                    target = (pno, page, t, rows)
                    break
            if target:
                break
        if not target:
            raise SystemExit("전형별 모집인원 표를 찾지 못함")
        pno, page, table, rows = target
        for ri, exp in EXPECT_HDR.items():
            for ci, e in exp.items():
                if norm(rows[ri][ci]) != e:
                    raise SystemExit(f"머리글 불일치 row{ri} col{ci}: {rows[ri][ci]!r} != {e}")

        words = page.extract_words()
        hc = table.rows[0].cells[0]
        c_x0, c_x1 = hc[0], hc[2]
        c_lines = sorted({round(e["top"], 1) for e in page.edges
                          if e["orientation"] == "h" and e["x0"] <= c_x0 + 2 and e["x1"] >= c_x1 - 2})

        units, excluded, out_vals = [], [], []
        pdf_total = None
        group = None
        for ri in range(N_HEADER, len(rows)):
            r, trow = rows[ri], table.rows[ri]
            if norm(r[COL_GYE]) == "1,613" or (r[1] is None and r[2] is None and norm(r[COL_GYE])):
                pdf_total = r
                continue
            if r[2] is not None:          # 2단(학부 + 전공)
                if r[1] is not None:
                    group = join_lines(r[1])
                if not group:
                    raise SystemExit(f"row{ri}: 묶음 이름 없음")
                name = f"{group} {join_lines(r[2])}"
            else:
                group = None
                name = join_lines(r[1])
            if not name:
                raise SystemExit(f"row{ri}: 이름 없음")
            ref = trow.cells[COL_GYE]
            mid = (ref[1] + ref[3]) / 2
            ctop = max(h for h in c_lines if h <= mid)
            cbot = min(h for h in c_lines if h >= mid)
            college = "".join(w["text"] for w in words_in(words, c_x0, c_x1, ctop, cbot))
            for ci, lab in COLS_OUT.items():
                if r[ci] is not None and to_int(r[ci]):
                    out_vals.append(f"{name}:{lab} {to_int(r[ci])}")
            if norm(r[COL_GYE]) == "-":
                if any(to_int(r[ci]) for ci in COLS.values()):
                    raise SystemExit(f"{name}: 정원내 '-'인데 전형 인원 있음")
                excluded.append(name)
                continue
            inwon = {}
            for k, ci in COLS.items():
                v = to_int(r[ci])
                if v:
                    inwon[k] = v
            gye = to_int(r[COL_GYE])
            units.append({
                "단과대학": college if college not in ("", "-") else None,
                "모집단위": name,
                "계열": None,
                "인원": inwon,
                "계": gye,
                "쪽": pno,
                "검증": "합계일치" if sum(inwon.values()) == gye else "합계불일치",
            })
    if pdf_total is None:
        raise SystemExit("계 행 없음")

    tot = {k: to_int(pdf_total[ci]) for k, ci in COLS.items()}
    s_pdf = sum(tot[k] for k in SUSI_KEYS)
    j_pdf = sum(tot[k] for k in JEONGSI_KEYS)
    s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
    j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
    bad = [k for k in COLS if tot[k] != sum(u["인원"].get(k, 0) for u in units)]
    memo = [
        "정원내만 수록: 수시 학생부종합 기회균형 농어촌학생(정원외 63)·특성화고교졸업자(정원외 23), 기타 학생부종합 기회균형 "
        "특성화고 등 재직자(정원외 89), 재외국민과 외국인전형(정원외 15, 표에 없음)은 넣지 않음",
        "기회균형 사회통합지원은 표의 '(정원내)' 열 → 수록",
        "계 = 표의 '모집인원(정원내)' 칸(자유전공학부(인문)은 2026학년도 미충원 이월 1명 포함, 표 각주)",
        "넣지 않은 행(정원내 '-'): " + ", ".join(excluded)
        + " — 첨단융합학부 3개 전공은 정원외 특성화고 등 재직자만 모집, 글로벌 통상학부(정원무관)는 외국인전형만 별도 선발(표 각주)",
        "정시 일반학생 칸에는 수능 60%+실기 40% 모집단위(가군 산업디자인학과·공예_컬렉터블디자인전공 28, 나군 스포츠운동과학과·"
        "현대미술전공·시각디자인전공 45; 3쪽 표)도 들어 있음 — 표가 나누지 않아 유형 '수능' 하나로 둠",
        "자유전공학부(광역) 논술 120은 인문사회계열 70 + 자연계열 50(표 각주)이나 표에 계열별 칸이 없어 120 그대로",
        "단과대학: 표의 대학 칸(아트앤디자인스쿨·첨단융합학부·글로벌 통상학부는 대학 칸이 '-'라 null). 계열: 표에 칸이 없어 null",
        "모집단위 이름: 2단 칸(학부+전공)은 '학부 전공'으로 이어 적음",
        f"총계 대조: 수시 {s_pdf}={s_me}, 정시 {j_pdf}={j_me}, 전체 정원내 {to_int(pdf_total[COL_GYE])}={s_me + j_me} "
        f"(PDF 계 행; 3쪽 '정원 내 884명', '정원 내 729명'과 같음)",
        "전형별 열 합 대조(PDF 계 행): " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)),
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
    print(" - (확인용) 정원외 칸 값:", out_vals)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: swu.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
