#!/usr/bin/env python3
"""성공회대학교 2028 시행계획 파서.

대상 표(모두 1. 모집인원 절):
  나. 2028학년도 정원 내 모집단위별 모집인원 (계열·모집단위·전공·인원)  → 계
  다. 2028학년도 수시 모집 인원 (정원 내)                              → 수시 전형별 인원
  마. 2028학년도 정시 모집 인원(정원 내)                               → 정시 군별 인원
  가. 모집시기별 모집인원 요약                                          → 총계 대조
정원 외 표(라·바)는 읽지 않는다.
사용법: python3 -I tools/ipsi/parsers/skhu.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "skhu"
UNIV_NAME = "성공회대학교"

# 수시(정원 내) 표: 머리글(줄바꿈 제거) → key
SUSI_HDR = {
    "열린인재": "수시_종합_열린인재",
    "대안학교출신자": "수시_종합_대안학교출신자",
    "교과성적": "수시_교과_교과성적",
    "국가보훈대상자": "수시_교과_국가보훈대상자",
    "사회기여자및배려대상자": "수시_교과_사회기여자및배려대상자",
    "특성화고교교과성적": "수시_교과_특성화고교교과성적",
}
SUSI_GROUP = {"수시_종합": "학생부위주(종합)", "수시_교과": "학생부위주(교과)"}
JEONGSI_HDR = {"정시가군": "정시_수능_일반학생_가", "정시나군": "정시_수능_일반학생_나", "정시다군": "정시_수능_일반학생_다"}

JEONHYEONG = [
    {"key": "수시_종합_열린인재", "시기": "수시", "유형": "학생부종합", "전형명": "열린인재", "군": None},
    {"key": "수시_종합_대안학교출신자", "시기": "수시", "유형": "학생부종합", "전형명": "대안학교출신자", "군": None},
    {"key": "수시_교과_교과성적", "시기": "수시", "유형": "학생부교과", "전형명": "교과성적", "군": None},
    {"key": "수시_교과_국가보훈대상자", "시기": "수시", "유형": "학생부교과", "전형명": "국가보훈대상자", "군": None},
    {"key": "수시_교과_사회기여자및배려대상자", "시기": "수시", "유형": "학생부교과", "전형명": "사회기여자 및 배려대상자", "군": None},
    {"key": "수시_교과_특성화고교교과성적", "시기": "수시", "유형": "학생부교과", "전형명": "특성화고교교과성적", "군": None},
    {"key": "정시_수능_일반학생_가", "시기": "정시", "유형": "수능", "전형명": "일반학생전형", "군": "가"},
    {"key": "정시_수능_일반학생_나", "시기": "정시", "유형": "수능", "전형명": "일반학생전형", "군": "나"},
    {"key": "정시_수능_일반학생_다", "시기": "정시", "유형": "수능", "전형명": "일반학생전형", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]


def norm(s):
    return re.sub(r"\s+", "", s or "")


def to_int(cell):
    s = norm(cell).replace(",", "").rstrip("명")
    if s in ("", "-"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {cell!r}")


def title_above(page, table, h=28):
    x0, top, x1, _ = table.bbox
    return norm(page.crop((0, max(0, top - h), page.width, top)).extract_text() or "")


def main(pdf_path, out_path):
    found = {}
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            for t in page.find_tables():
                rows = t.extract()
                if not rows:
                    continue
                title = title_above(page, t)
                if "정원내모집단위별모집인원" in title and [norm(c) for c in rows[1]] == ["계열", "모집단위", "전공", "인원"]:
                    found.setdefault("total", (pno, rows))
                elif "수시모집인원(정원내)" in title:
                    found.setdefault("susi", (pno, rows))
                elif "정시모집인원(정원내)" in title:
                    found.setdefault("jeongsi", (pno, rows))
                elif "모집시기별모집인원요약" in title:
                    found.setdefault("summary", (pno, rows))
    for k in ("total", "susi", "jeongsi"):
        if k not in found:
            raise SystemExit(f"표를 찾지 못함: {k}")

    # ---- 정원 내 모집단위별 모집인원(계) ----
    tp, trows = found["total"]
    gye, gyeyeol, order = {}, {}, []
    total_sum_pdf = None
    for r in trows[2:]:
        if norm(r[0]) == "입학정원합계":
            total_sum_pdf = to_int(r[3])
            continue
        name = norm(r[1])
        if not name:
            raise SystemExit(f"모집단위 이름 없음: {r}")
        gye[name] = to_int(r[3])
        gyeyeol[name] = norm(r[0]) or None
        order.append(name)

    # ---- 수시(정원 내) ----
    sp, srows = found["susi"]
    hdr = [norm(c) for c in srows[1]]
    if hdr[0] != "모집단위":
        raise SystemExit(f"수시 머리글 다름: {hdr}")
    grp_row = [norm(c) for c in srows[0]]
    col_key = {}
    cur_grp = None
    for i, h in enumerate(hdr):
        if grp_row[i]:
            cur_grp = grp_row[i]
        if h in SUSI_HDR:
            key = SUSI_HDR[h]
            exp_grp = SUSI_GROUP["_".join(key.split("_")[:2])]
            if cur_grp != exp_grp:
                raise SystemExit(f"수시 유형 머리글 다름: {h} 아래 {cur_grp}")
            col_key[i] = key
    if sorted(col_key.values()) != sorted(SUSI_KEYS):
        raise SystemExit(f"수시 열 못 찾음: {col_key}")
    susi, susi_sub = {}, None
    for r in srows[2:]:
        name = norm(r[0])
        vals = {k: to_int(r[i]) for i, k in col_key.items()}
        if name == "소계":
            susi_sub = vals
            continue
        if name in susi:
            raise SystemExit(f"수시 중복 행: {name}")
        susi[name] = vals

    # ---- 정시(정원 내) ----
    jp, jrows = found["jeongsi"]
    if norm(jrows[0][0]) != "모집시기" or norm(jrows[1][2]) != "수능위주" or norm(jrows[2][2]) != "일반학생전형":
        raise SystemExit(f"정시 머리글 다름: {jrows[:3]}")
    jcol = {i: JEONGSI_HDR[norm(c)] for i, c in enumerate(jrows[0]) if norm(c) in JEONGSI_HDR}
    if sorted(jcol.values()) != sorted(JEONGSI_KEYS):
        raise SystemExit(f"정시 열 못 찾음: {jrows[0]}")
    jeongsi, jeongsi_sub, jeongsi_all = {}, None, None
    for r in jrows[3:]:
        name = norm(r[0])
        if name == "소계":
            jeongsi_sub = {k: to_int(r[i]) for i, k in jcol.items()}
            continue
        if name == "모집총인원":
            jeongsi_all = to_int(r[2])
            continue
        if name in jeongsi:
            raise SystemExit(f"정시 중복 행: {name}")
        jeongsi[name] = {k: to_int(r[i]) for i, k in jcol.items()}

    names_s, names_j, names_t = set(susi), set(jeongsi), set(gye)
    if not (names_s <= names_t and names_j <= names_t):
        raise SystemExit(f"모집단위 이름 불일치: 수시 {names_s - names_t}, 정시 {names_j - names_t}")

    units = []
    for name in order:
        inwon = {}
        for k, v in list(susi.get(name, {}).items()) + list(jeongsi.get(name, {}).items()):
            if v:
                inwon[k] = v
        units.append({
            "단과대학": None,
            "모집단위": name,
            "계열": gyeyeol[name],
            "인원": inwon,
            "계": gye[name],
            "쪽": tp,
            "검증": "합계일치" if sum(inwon.values()) == gye[name] else "합계불일치",
        })

    memo = [
        "정원내만 수록: 수시 정원 외(기회균형선발·농어촌학생·특성화고교졸업자·북한이탈주민), 정시 정원 외(농어촌학생·기회균형선발·"
        "특성화고교졸업자, 모두 0명), 재외국민(정원 외)은 넣지 않음",
        f"계 = '나. 2028학년도 정원 내 모집단위별 모집인원' 표(p{tp})의 '인원' 칸. 표 각주: 모집인원은 입학정원 및 2026학년도 "
        "초과모집에 따른 감축인원 포함",
        f"전형별 인원: 수시 = '다. 수시 모집 인원(정원 내)' 표(p{sp}), 정시 = '마. 정시 모집 인원(정원 내)' 표(p{jp}). "
        "'쪽'은 계 표 쪽",
        "모집단위는 학부 단위(표의 '전공' 칸 목록은 학부 안 전공 안내라 행을 나누지 않음)",
        "계열: '나.' 표의 계열 칸 그대로(인문사회/공학/광역). 단과대학: 표에 칸이 없어 null",
        "수시 국가보훈대상자·사회기여자및배려대상자·특성화고교교과성적은 PDF 표에서 학생부위주(교과) 아래 정원 내 열 → 학생부교과로 수록",
    ]
    # 소계 대조
    bad = [k for k in SUSI_KEYS if susi_sub is None or susi_sub[k] != sum(u["인원"].get(k, 0) for u in units)]
    bad += [k for k in JEONGSI_KEYS if jeongsi_sub is None or jeongsi_sub[k] != sum(u["인원"].get(k, 0) for u in units)]
    memo.append("전형별 열 합 대조(수시·정시 표 소계 행): " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)))
    s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
    j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
    s_pdf = sum(susi_sub.values()) if susi_sub else None
    tot = f"총계 대조: 수시 {s_pdf}={s_me}, 정시 {jeongsi_all}={j_me}, 전체 {total_sum_pdf}={s_me + j_me}"
    if "summary" in found:
        _, sm = found["summary"]
        lab = [norm(c) for c in sm[1]]
        top = [norm(c) for c in sm[0]]
        vals = [norm(c) for c in sm[2]]
        try:
            i_s = next(i for i, c in enumerate(lab) if c == "정원내")
            i_j = next(i for i, c in enumerate(top) if c.startswith("정시") and "정원내" in c)
            tot += f" (요약표 p{found['summary'][0]}: 수시 정원 내 {to_int(vals[i_s])}, 정시 정원 내 {to_int(vals[i_j])})"
        except (StopIteration, ValueError):
            pass
    memo.append(tot + " — 수시는 수시 표 소계 행 합, 정시는 '모집 총 인원', 전체는 '입학정원 합계'")

    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": sorted({tp, sp, jp}), "전형": JEONHYEONG,
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


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: skhu.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
