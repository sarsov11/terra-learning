#!/usr/bin/env python3
"""서울한영대학교 2028 시행계획 파서.

대상 표(PDF 2쪽, 세 표):
  - "모집단위별 모집인원": 모집단위·계열·입학정원·2026 이월인원·합계 → 계열, 계
  - "가. 수시모집": 정원내 일반/만학도/국가보훈대상자 전형 (정원외 3전형은 병합 칸, 제외)
  - "나. 정시모집": 나군 일반전형 (농어촌·기초생활 정원외는 제외)
사용법: python3 -I tools/ipsi/parsers/hytu.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "hytu"
UNIV_NAME = "서울한영대학교"

JEONHYEONG = [
    {"key": "수시_교과_일반", "시기": "수시", "유형": "학생부교과", "전형명": "일반전형", "군": None},
    {"key": "수시_교과_만학도", "시기": "수시", "유형": "학생부교과", "전형명": "만학도전형", "군": None},
    {"key": "수시_교과_국가보훈", "시기": "수시", "유형": "학생부교과", "전형명": "국가보훈대상자전형", "군": None},
    {"key": "정시_수능_나_일반", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "나"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]

# 수시 표: 열 → key. 머리글(1행)로 위치 확인
SUSI_COLS = {"수시_교과_일반": 3, "수시_교과_만학도": 4, "수시_교과_국가보훈": 5}
SUSI_HDR = {(0, 2): "수시모집인원", (0, 3): "정원내", (0, 6): "정원외",
            (1, 3): "일반전형", (1, 4): "만학도전형", (1, 5): "국가보훈대상자전형",
            (1, 6): "농어촌학생전형", (1, 8): "장애인등대상자전형"}
SUSI_OUT_COLS = [6, 7, 8]
JEONG_COLS = {"정시_수능_나_일반": 3}
JEONG_HDR = {(0, 2): "정시모집인원", (0, 3): "나군", (1, 3): "일반전형", (1, 4): "농어촌학생"}
JEONG_OUT_COLS = [4, 5]


def flat(s):
    return re.sub(r"\s+", "", s or "")


def to_int(cell):
    s = (cell or "").strip().replace(",", "")
    if s in ("", "-"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {cell!r}")


def check_hdr(rows, hdr, what):
    for (r, c), exp in hdr.items():
        if flat(rows[r][c]) != exp:
            raise SystemExit(f"{what} 머리글 불일치 ({r},{c}): {rows[r][c]!r} != {exp}")


def main(pdf_path, out_path):
    base = susi = jeong = None
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            for t in page.find_tables():
                rows = t.extract()
                if not rows:
                    continue
                h = [flat(c) for c in rows[0]]
                if h[:3] == ["No", "계열", "모집단위"] and "입학정원" in h and base is None:
                    base = (pno, rows)
                elif "수시모집인원" in h and susi is None:
                    susi = (pno, rows)
                elif "정시모집인원" in h and jeong is None:
                    jeong = (pno, rows)
    if not (base and susi and jeong):
        raise SystemExit("표 3개(모집단위별 모집인원/수시/정시)를 다 찾지 못함")

    # 1) 모집단위별 모집인원(입학정원 표)
    pno_b, rows = base
    h = [flat(c) for c in rows[0]]
    if h[3] != "입학정원" or h[4] != "2026학년도이월인원" or h[5] != "합계":
        raise SystemExit(f"입학정원 표 머리글 다름: {h}")
    order, info = [], {}
    base_total = None
    for r in rows[1:]:
        if flat(r[0]) == "합계인원":
            base_total = {"입학정원": to_int(r[3]), "합계": to_int(r[5])}
            continue
        name = flat(r[2])
        g = flat(r[1])
        gyeyeol = g[: -len("계열")] if g.endswith("계열") else (g or None)
        order.append(name)
        info[name] = {"계열": gyeyeol, "입학정원": to_int(r[3]), "이월": to_int(r[4]), "합계": to_int(r[5])}

    # 2) 수시
    pno_s, rows = susi
    check_hdr(rows, SUSI_HDR, "수시")
    data = {n: {} for n in order}
    susi_cnt, susi_total = {}, None
    for r in rows[2:]:
        if flat(r[0]) == "계":
            susi_total = {k: to_int(r[i]) for k, i in SUSI_COLS.items()}
            susi_total["수시모집인원"] = to_int(r[2])
            susi_total["정원외"] = [to_int(r[i]) for i in SUSI_OUT_COLS]
            continue
        name = flat(r[1])
        if name not in data:
            raise SystemExit(f"수시 표의 모르는 모집단위: {name}")
        for k, i in SUSI_COLS.items():
            v = to_int(r[i])
            if v:
                data[name][k] = v
        susi_cnt[name] = to_int(r[2])

    # 3) 정시
    pno_j, rows = jeong
    check_hdr(rows, JEONG_HDR, "정시")
    jeong_cnt, jeong_total = {}, None
    for r in rows[2:]:
        if flat(r[0]) == "계":
            jeong_total = {k: to_int(r[i]) for k, i in JEONG_COLS.items()}
            jeong_total["정시모집인원"] = to_int(r[2])
            continue
        name = flat(r[1])
        if name not in data:
            raise SystemExit(f"정시 표의 모르는 모집단위: {name}")
        for k, i in JEONG_COLS.items():
            v = to_int(r[i])
            if v:
                data[name][k] = v
        jeong_cnt[name] = to_int(r[2])
    if not (susi_total and jeong_total and base_total):
        raise SystemExit("계 행을 찾지 못함")

    units, sub_bad = [], []
    for name in order:
        inwon = data[name]
        gye = info[name]["합계"]
        s = sum(inwon.get(k, 0) for k in SUSI_KEYS)
        j = sum(inwon.get(k, 0) for k in JEONGSI_KEYS)
        if s != susi_cnt.get(name) or j != jeong_cnt.get(name):
            sub_bad.append(f"{name}(수시모집인원 {susi_cnt.get(name)}/{s}, 정시모집인원 {jeong_cnt.get(name)}/{j})")
        units.append({"단과대학": None, "모집단위": name, "계열": info[name]["계열"], "인원": inwon, "계": gye,
                      "쪽": pno_s, "검증": "합계일치" if s + j == gye else "합계불일치"})

    s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
    j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
    per_bad = [k for k, i in list(SUSI_COLS.items()) + list(JEONG_COLS.items())
               if (susi_total if k in SUSI_COLS else jeong_total)[k] != sum(u["인원"].get(k, 0) for u in units)]
    memo = [
        "정원내만 수록. 정원외(수시 농어촌학생 3·기초생활수급자,차상위계층,한부모가족지원대상자 5·장애인 등 대상자 18 — "
        "표에서 전 모집단위 병합 칸, 정시 농어촌학생·기초생활수급자 등 0(수시 미충원 시 이월), "
        "전형기간자율 부모가 모두 외국인인 외국인(모집인원 제한없음))는 넣지 않음",
        "수시 만학도전형·국가보훈대상자전형은 표의 '정원내' 열 → 수록",
        "계 = '모집단위별 모집인원' 표의 '합계' 칸(입학정원 + 2026학년도 이월인원, 이월은 모두 '-'). "
        "수시·정시 표에는 모집단위별 수시+정시 합계 칸이 따로 없음",
        "계열: '모집단위별 모집인원' 표의 계열 칸(인문사회계열)에서 '계열'을 뗀 값. 단과대학 칸 없음 → null",
        "정시 일반전형은 표에 정원내 표기가 없으나 4쪽 전형요소별 반영비율 표에서 '정원내 일반'으로 적혀 있어 정원내로 봄",
        "쪽 = 수시·정시 표가 있는 PDF 쪽",
        "보조 대조(행별 수시모집인원·정시모집인원 칸 = 정원내 전형 합): "
        + ("모두 일치" if not sub_bad else "불일치 " + "; ".join(sub_bad)),
        f"총계 대조(수시 표 계 행·정시 표 계 행·모집단위별 표 합계인원): 수시 {susi_total['수시모집인원']}={s_me}, "
        f"정시 {jeong_total['정시모집인원']}={j_me}, 전체 {base_total['합계']}={s_me + j_me}",
        "전형별 열 합 대조(계 행): " + ("모두 일치" if not per_bad else "불일치 " + ", ".join(per_bad)),
    ]
    pages = sorted({pno_b, pno_s, pno_j})
    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": pages, "전형": JEONHYEONG, "모집단위": units, "메모": memo}
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
        raise SystemExit("usage: hytu.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
