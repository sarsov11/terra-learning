#!/usr/bin/env python3
"""한국성서대학교 2028 시행계획 파서.

대상 표:
  - "대학별 설치 모집단위 및 입학정원" (PDF 2쪽): 모집단위·계열·입학정원(주/야/합계)·26학년도 이월인원 → 계열, 계
  - "대학별 모집시기 및 전형유형별 모집인원" (PDF 2~3쪽, 한 표가 두 쪽에 이어짐): 전형 블록마다 모집단위 행
사용법: python3 -I tools/ipsi/parsers/bible.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "bible"
UNIV_NAME = "한국성서대학교"

# 전형 표 열 번호
C_SIGI, C_TYPE, C_DAE, C_JUNG, C_NAME, C_INOUT, C_UNIT, C_DAY, C_NIGHT, C_SUM, C_NOTE = range(11)
HDR0 = {C_SIGI: "모집시기", C_TYPE: "전형유형", C_DAE: "전형선발구분", C_INOUT: "정원내외",
        C_UNIT: "모집단위별(전공포함)모집인원", C_DAY: "모집인원", C_NOTE: "비고"}
HDR1 = {C_DAE: "대분류", C_JUNG: "중분류", C_NAME: "대학사용명칭", C_DAY: "주간", C_NIGHT: "야간", C_SUM: "합계"}

# (모집시기 칸, 대학 사용명칭 칸) → key  (정원내 전형만)
ROWMAP = {
    ("수시", "학생부교과(일반학생전형)"): "수시_교과_일반학생",
    ("수시", "학생부교과(목회자추천전형)"): "수시_교과_목회자추천",
    ("수시", "학생부교과(고른기회전형)"): "수시_교과_고른기회",
    ("정시(다)군", "수능(일반학생전형)"): "정시_수능_다_일반학생",
    ("정시(다)군", "학생부교과(일반학생전형)"): "정시_교과_다_일반학생",
}
JEONHYEONG = [
    {"key": "수시_교과_일반학생", "시기": "수시", "유형": "학생부교과", "전형명": "학생부교과(일반학생전형)", "군": None},
    {"key": "수시_교과_목회자추천", "시기": "수시", "유형": "학생부교과", "전형명": "학생부교과(목회자추천전형)", "군": None},
    {"key": "수시_교과_고른기회", "시기": "수시", "유형": "학생부교과", "전형명": "학생부교과(고른기회전형)", "군": None},
    {"key": "정시_수능_다_일반학생", "시기": "정시", "유형": "수능", "전형명": "수능(일반학생전형)", "군": "다"},
    {"key": "정시_교과_다_일반학생", "시기": "정시", "유형": "학생부교과", "전형명": "학생부교과(일반학생전형)", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]
TRIANGLE = "▲"  # 수시모집 미충원 시 이월인원 (숫자 없음)


def flat(s):
    return re.sub(r"\s+", "", s or "")


def to_int(cell):
    s = (cell or "").strip().replace(",", "")
    if s in ("", "-"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {cell!r}")


def main(pdf_path, out_path):
    base = None
    plan_rows, plan_pages = [], []
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            if pno > 6:
                break
            for t in page.find_tables():
                rows = t.extract()
                if not rows:
                    continue
                h0 = [flat(c) for c in rows[0]]
                if h0[:3] == ["대학교", "계열", "모집단위"] and base is None:
                    base = (pno, rows)
                elif h0[:2] == ["모집시기", "전형유형"] and len(rows[0]) == 11 and "정원내외" in h0:
                    for c, exp in HDR0.items():
                        if h0[c] != exp:
                            raise SystemExit(f"전형 표 머리글 불일치 col{c}: {h0[c]} != {exp}")
                    for c, exp in HDR1.items():
                        if flat(rows[1][c]) != exp:
                            raise SystemExit(f"전형 표 2행 머리글 불일치 col{c}: {rows[1][c]} != {exp}")
                    plan_rows += [(pno, r) for r in rows[2:]]
                    plan_pages.append(pno)
                elif plan_pages and pno == plan_pages[-1] + 1 and len(rows[0]) == 11 and not plan_rows_done(rows):
                    # 다음 쪽으로 이어진 표(머리글 없음): 모집단위 칸이 있는 11열 표
                    plan_rows += [(pno, r) for r in rows]
                    plan_pages.append(pno)
    if not base or not plan_rows:
        raise SystemExit("입학정원 표 또는 전형별 모집인원 표를 찾지 못함")

    # 1) 입학정원 표
    pno_b, rows = base
    if flat(rows[0][5]) != "입학정원" or [flat(c) for c in rows[1][5:8]] != ["주", "야", "합계"] \
            or flat(rows[0][8]) != "26학년도이월인원":
        raise SystemExit("입학정원 표 머리글 다름")
    order, info, base_total = [], {}, None
    for r in rows[2:]:
        if flat(r[0]) == "합계":
            base_total = {"주": to_int(r[5]), "야": to_int(r[6]), "합계": to_int(r[7]), "이월": to_int(r[8])}
            continue
        name = flat(r[2])
        order.append(name)
        info[name] = {"계열": flat(r[1]) or None, "주": to_int(r[5]), "야": to_int(r[6]),
                      "합계": to_int(r[7]), "이월": to_int(r[8])}
    if base_total is None:
        raise SystemExit("입학정원 표 합계 행 없음")

    # 2) 전형별 모집인원 표 (병합 칸은 위 값 이어받기)
    cur = {C_SIGI: None, C_NAME: None, C_INOUT: None}
    data = {n: {} for n in order}
    triangles, out_names, row_sum_bad = [], set(), []
    n_in_rows = 0
    for pno, r in plan_rows:
        for c in cur:
            if r[c] is not None and flat(r[c]):
                cur[c] = flat(r[c])
        unit = flat(r[C_UNIT])
        if not unit:
            continue
        if unit not in data:
            raise SystemExit(f"모르는 모집단위: {unit}")
        if cur[C_INOUT] == "정원외":
            out_names.add(cur[C_NAME])
            continue
        if cur[C_INOUT] != "정원내":
            raise SystemExit(f"정원내외 칸 이상: {cur[C_INOUT]}")
        key = ROWMAP.get((cur[C_SIGI], cur[C_NAME]))
        if key is None:
            raise SystemExit(f"모르는 정원내 전형: {cur[C_SIGI]} {cur[C_NAME]}")
        n_in_rows += 1
        day, night, tot = (flat(r[C_DAY]), flat(r[C_NIGHT]), flat(r[C_SUM]))
        if day == TRIANGLE:
            if tot != TRIANGLE or night:
                raise SystemExit(f"▲ 행 이상: {unit} {r}")
            triangles.append(f"{key}/{unit}")
            continue
        d, n, s = to_int(day), to_int(night), to_int(tot)
        if d + n != s:
            row_sum_bad.append(f"{key}/{unit}: 주간 {d}+야간 {n}≠합계 {s}")
        if s:
            if key in data[unit]:
                raise SystemExit(f"같은 전형·모집단위 두 번: {key} {unit}")
            data[unit][key] = s

    units = []
    for name in order:
        if info[name]["이월"] != 0:
            raise SystemExit(f"{name}: 26학년도 이월인원이 0이 아님 → 계 정의 다시 볼 것")
        inwon = data[name]
        gye = info[name]["합계"]
        units.append({"단과대학": None, "모집단위": name, "계열": info[name]["계열"], "인원": inwon, "계": gye,
                      "쪽": plan_pages[0], "검증": "합계일치" if sum(inwon.values()) == gye else "합계불일치"})

    s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
    j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
    per = {k: sum(u["인원"].get(k, 0) for u in units) for k in SUSI_KEYS + JEONGSI_KEYS}
    ilban_nonnurse = sum(u["인원"].get("수시_교과_일반학생", 0) for u in units if u["모집단위"] != "간호학과")
    ilban_nurse = sum(u["인원"].get("수시_교과_일반학생", 0) for u in units if u["모집단위"] == "간호학과")
    p4 = check_p4(pdf_path)
    p13 = check_p13(pdf_path)
    memo = [
        "정원내만 수록. 정원외(농어촌고교출신자, 기초생활수급자및차상위, 특수교육대상자, 재외국민과외국인(2%), "
        "북한이탈주민·12년 과정 이수자·부모 모두 외국인인 외국인)는 넣지 않음: " + ", ".join(sorted(out_names)),
        "고른기회전형(사회통합전형 기회균형 선발 대상자(통합))은 표에서 '정원내' → 수록",
        "계 = '대학별 설치 모집단위 및 입학정원' 표의 입학정원 합계 칸(26학년도 이월인원은 모든 모집단위 0). "
        "전형별 표의 '합계' 칸은 전형·모집단위 칸별 주간+야간 합이라 모집단위 전체 합계가 아님",
        f"'▲'(수시모집 미충원 시 이월인원, 숫자 없음)는 0으로 봄: {', '.join(triangles)}. "
        "그래서 정시_교과_다_일반학생(성서학과 정시 학생부교과)은 인원 0이라 어떤 행에도 없음",
        "계열: 입학정원 표의 계열 칸 그대로(인문사회/공학/자연과학). 단과대학 칸 없음 → null",
        f"보조 대조(전형 칸별 주간+야간=합계): {n_in_rows - len(triangles) - len(row_sum_bad)}칸 일치"
        + (", 불일치 " + "; ".join(row_sum_bad) if row_sum_bad else ""),
    ]
    # 총계 대조: 4쪽 '전형요소별 반영비율' 표의 정원내 모집인원(숫자 칸만)
    p4_susi = sum(int(n) for sg, _, _, n in p4 if sg == "수시" and n.isdigit())
    p4_jeong = sum(int(n) for sg, _, _, n in p4 if sg != "수시" and n.isdigit())
    memo.append(f"총계 대조(4쪽 전형요소별 표 정원내 모집인원 합, ▲ 제외 / 2쪽 입학정원 표 합계): "
                f"수시 {p4_susi}={s_me}, 정시 {p4_jeong}={j_me}, 전체 {base_total['합계']}={s_me + j_me}")
    expect = {("수시", "일반학생", "전모집단위(간호학과제외)"): ilban_nonnurse,
              ("수시", "일반학생", "간호학과"): ilban_nurse,
              ("수시", "목회자추천", "전모집단위"): per["수시_교과_목회자추천"],
              ("수시", "고른기회", "전모집단위"): per["수시_교과_고른기회"],
              ("정시(다)군", "일반학생", "간호학과"): per["정시_수능_다_일반학생"]}
    got = {(sg, n, u): c for sg, n, u, c in p4}
    mism = [f"{k}: 4쪽 {got.get(k)} vs {v}" for k, v in expect.items() if got.get(k) != str(v)]
    memo.append("4쪽 전형별 대조(일반학생 간호제외/간호, 목회자추천, 고른기회, 정시 간호 수능): "
                + ("모두 일치" if not mism else "불일치 " + "; ".join(mism)))
    if p13 is not None and p13 != per["수시_교과_일반학생"]:
        memo.append(f"참고: 13쪽 정원내 지원자격 표는 수시 일반학생 모집인원을 {p13}으로 적고 있어 2쪽 표 합"
                    f"({per['수시_교과_일반학생']})·4쪽 표와 다름. 2쪽 전형별 표를 따름(그 합이 입학정원과 맞음)")
    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": sorted(set([pno_b] + plan_pages)), "전형": JEONHYEONG,
           "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    cnt = {}
    for u in units:
        cnt[u["검증"]] = cnt.get(u["검증"], 0) + 1
    print(f"{UNIV_ID}: {len(units)}행 {cnt} → {out_path}")
    for m in memo:
        print(" -", m)


def plan_rows_done(rows):
    """이어진 쪽 표인지 판단용: 머리글이 다른 표(전형요소별 반영비율 등)는 제외."""
    return flat(rows[0][0]) in ("모집시기", "대학교")


def check_p4(pdf_path):
    """4쪽 '전형요소별 반영비율' 표의 정원내 (모집시기, 전형명, 모집단위, 모집인원) 목록. 모집시기 칸은 병합이라 이어받음."""
    res = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[3:5]:
            for t in page.find_tables():
                rows = t.extract()
                if not rows or flat(rows[0][0]) != "모집시기" or "모집인원" not in [flat(c) for c in rows[0]]:
                    continue
                h = [flat(c) for c in rows[0]]
                ci_n, ci_io, ci_cnt, ci_unit = h.index("전형명"), h.index("정원내외"), h.index("모집인원"), \
                    h.index("모집단위별(전공포함)모집인원")
                sigi = None
                for r in rows[2:]:
                    if r[0] is not None and flat(r[0]):
                        sigi = flat(r[0])
                    if flat(r[ci_io]) == "정원내":
                        res.append((sigi, flat(r[ci_n]), flat(r[ci_unit]), flat(r[ci_cnt])))
                return res
    return res


def check_p13(pdf_path):
    """13쪽 '정원내 전형별 지원자격' 표의 수시 학생부교과(일반학생전형) 모집인원(참고 대조용)."""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[10:]:
            if "정원내 전형별 지원자격" not in (page.extract_text() or ""):
                continue
            for t in page.find_tables():
                rows = t.extract()
                if not rows or "모집인원" not in [flat(c) for c in rows[0]]:
                    continue
                ci = [flat(c) for c in rows[0]].index("모집인원")
                for r in rows[2:]:
                    if flat(r[0]) == "수시" and flat(r[4]) == "학생부교과(일반학생전형)":
                        v = flat(r[ci])
                        return int(v) if v.isdigit() else None
    return None


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: bible.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
