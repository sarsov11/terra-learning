"""부산대학교 2028 시행계획 → norm JSON.

표: PDF 7~9쪽 '모집단위 및 모집인원'
  1. 인문·사회계열 / 자연계열 / 광역 / 체육계열(스포츠과학과)  (7, 8, 9쪽)
  2. 예술계열 / 체육계열(체육교육과)                             (9쪽)
pdfplumber 선 기반 표 추출(extract_tables)로 읽는다.

사용: python3 -I tools/ipsi/parsers/pnu.py <pdf> <out.json>
"""
import json
import re
import sys
from collections import Counter

import pdfplumber

ID = "pnu"
NAME = "부산대학교"
PAGES = [7, 8, 9]

# 표 1 열(0-based) → 전형 정의. "정원외" = 표 위 안내문의 정원외 전형.
T1_HEADER = ["교과우수", "교과지역", "농어촌학생", "지역저소득층학생", "탐구", "서류", "면접", "면접지역",
             "지역의사전형", "사회배려자", "저소득층학생", "특성화고교졸업자", "특수교육대상자",
             "수능우수", "수능지역", "수능우수", "수능지역", "수능우수"]
T1_DEFS = [
    ("수시_교과_교과우수", "수시", "학생부교과", "교과우수전형", None),
    ("수시_교과_교과지역", "수시", "학생부교과", "교과지역전형", None),
    "정원외",  # 농어촌학생
    ("수시_교과_지역저소득층", "수시", "학생부교과", "지역저소득층학생전형", None),
    ("수시_교과_탐구", "수시", "학생부교과", "탐구전형", None),
    ("수시_종합_서류", "수시", "학생부종합", "서류전형", None),
    ("수시_종합_면접", "수시", "학생부종합", "면접전형", None),
    ("수시_종합_면접지역", "수시", "학생부종합", "면접지역전형", None),
    ("수시_종합_지역의사", "수시", "학생부종합", "지역의사선발전형", None),
    ("수시_종합_사회배려자", "수시", "학생부종합", "사회배려자전형", None),
    "정원외",  # 저소득층학생
    "정원외",  # 특성화고교졸업자
    "정원외",  # 특수교육대상자
    ("정시_수능_가_수능우수", "정시", "수능", "수능우수전형", "가"),
    ("정시_수능_가_수능지역", "정시", "수능", "수능지역전형", "가"),
    ("정시_수능_나_수능우수", "정시", "수능", "수능우수전형", "나"),
    ("정시_수능_나_수능지역", "정시", "수능", "수능지역전형", "나"),
    ("정시_수능_다_수능우수", "정시", "수능", "수능우수전형", "다"),
]
T2_HEADER = ["실기", "농어촌학생", "저소득층학생", "특성화고교졸업자", "체육특기자", "수능우수"]
T2_DEFS = [
    ("수시_실기_실기", "수시", "실기/실적", "실기전형", None),
    "정원외",
    "정원외",
    "정원외",
    ("수시_실기_체육특기자", "수시", "실기/실적", "체육특기자전형", None),
    ("정시_수능_가_수능우수", "정시", "수능", "수능우수전형", "가"),
]
# 정원외 계약학과(각주 2): '모집인원' 전체가 정원외 → 정원내 데이터에서 뺀다.
OUTSIDE_UNITS = {"스마트가전공학과"}


def flat(s):
    if s is None:
        return None
    return re.sub(r"\s+", "", s.replace("\x00", ""))


def num(s):
    t = flat(s)
    if t in (None, "", "-"):
        return 0
    if re.fullmatch(r"\d{1,3}(,\d{3})+|\d+", t):
        return int(t.replace(",", ""))
    return None


def unit_name(s):
    """모집단위 칸: 줄바꿈 이어 붙이고, 각주 번호 ' 1)', '3)', ' 4)' 를 뗀다."""
    t = (s or "").replace("\x00", " ")
    parts = [p.strip() for p in t.split("\n") if p.strip()]
    t = ""
    for p in parts:  # 줄바꿈: '('로 시작하는 줄은 붙이고, 그 밖은 공백으로 잇는다
        t = p if not t else (t + p if p.startswith("(") else t + " " + p)
    foot = re.search(r"\s*(\d)\)$", t)
    note = None
    if foot:
        note = foot.group(1)
        t = t[:foot.start()]
    return t.strip(), note


def main(pdf_path, out_path):
    rows, memo, unread = [], [], []
    totals = {}
    jdefs = {}
    excluded = []
    t1_count = t2_count = 0
    with pdfplumber.open(pdf_path) as pdf:
        for pno in PAGES:
            page = pdf.pages[pno - 1]
            for tbl in page.extract_tables():
                if not tbl or flat(tbl[0][0]) != "대학명":
                    continue
                if len(tbl[0]) == 22:
                    kind = 1
                    hdr = [flat(c) for c in tbl[2][4:17]] + [flat(c) for c in tbl[3][17:22]]
                    assert hdr == T1_HEADER, hdr
                    gun = [flat(tbl[2][17]), flat(tbl[2][19]), flat(tbl[2][21])]
                    assert gun == ["가군", "나군", "다군"], gun
                    defs, first_data, ncol0 = T1_DEFS, 4, 4
                elif len(tbl[0]) == 11:
                    kind = 2
                    hdr = [flat(c) for c in tbl[2][5:11]]
                    assert hdr == T2_HEADER, hdr
                    assert flat(tbl[1][10]) == "수능가군", tbl[1]
                    defs, first_data, ncol0 = T2_DEFS, 3, 5
                else:
                    raise SystemExit(f"p{pno}: 알 수 없는 표 모양 {len(tbl[0])}열")
                for d in defs:
                    if isinstance(d, tuple):
                        jdefs.setdefault(d[0], d)
                dae = gye = hak = None
                for r in tbl[first_data:]:
                    if flat(r[0]) == "합계":
                        totals[kind] = r
                        continue
                    if r[0] is not None and flat(r[0]):
                        dae = flat(r[0])
                    if r[1] is not None and flat(r[1]):
                        gye = flat(r[1])
                    if kind == 1:
                        name, note = unit_name(r[2])
                        cap_raw = r[3]
                        vals_raw = r[4:22]
                    else:
                        if r[2] is not None and flat(r[2]):
                            hak = flat(r[2])
                        major = flat(r[3])
                        name, note = (f"{hak} {major}" if major else hak), None
                        cap_raw = r[4]
                        vals_raw = r[5:11]
                    cap = num(cap_raw)
                    if cap is None:
                        unread.append(f"p{pno} {name}: 모집인원 칸 {cap_raw!r}")
                        continue
                    inwon = {}
                    bad = []
                    for d, v in zip(defs, vals_raw):
                        if d == "정원외":
                            continue
                        n = num(v)
                        if n is None:
                            bad.append(f"{d[0]} {v!r}")
                            continue
                        if n:
                            inwon[d[0]] = inwon.get(d[0], 0) + n
                    if bad:
                        unread.append(f"p{pno} {name}: " + ", ".join(bad))
                        continue
                    rec = {
                        "단과대학": dae,
                        "모집단위": name,
                        "계열": gye,
                        "인원": inwon,
                        "계": None,
                        "_cap": cap,
                        "쪽": pno,
                        "검증": None,
                        "_kind": kind,
                        "_raw": vals_raw,
                        "_defs": defs,
                    }
                    if name in OUTSIDE_UNITS:
                        excluded.append(rec)
                        continue
                    rows.append(rec)
                    if kind == 1:
                        t1_count += 1
                    else:
                        t2_count += 1

    # 각 행의 정원외 열 합(특수교육대상자 병합 칸 제외)
    def outside_sum(r):
        return sum(num(v) or 0 for h, d, v in zip(T1_HEADER if r["_kind"] == 1 else T2_HEADER, r["_defs"], r["_raw"])
                   if d == "정원외" and h != "특수교육대상자")

    # 행 검증: 표의 '모집인원' 칸은 정원내+정원외(특수교육대상자 제외) 합이라 정원내 합계 칸이 아님 → 계=null.
    # 보조 대조: 모집인원 칸 == 정원내 전형 합 + 같은 행 정원외 칸 합
    aux_ok, aux_bad = 0, []
    for r in rows + excluded:
        s = sum(r["인원"].values())
        r["검증"] = "합계칸없음"
        if s + outside_sum(r) == r["_cap"]:
            aux_ok += 1
        else:
            aux_bad.append(f"{r['모집단위']}(모집인원 {r['_cap']}, 정원내 {s}, 정원외 {outside_sum(r)})")
    bad_rows = []

    # 총계 대조
    def total_check(kind):
        raw = totals[kind]
        if kind == 1:
            cap_raw, vals = raw[3], raw[4:22]
            defs = T1_DEFS
        else:
            cap_raw, vals = raw[4], raw[5:11]
            defs = T2_DEFS
        out = {"수시": [0, 0], "정시": [0, 0]}
        col_bad = []
        rs = [r for r in rows if r["_kind"] == kind]
        exc = [r for r in excluded if r["_kind"] == kind]
        outside_total = 0
        for d, v in zip(defs, vals):
            pv = num(v)
            if d == "정원외":
                outside_total += pv or 0
                continue
            mine = sum(r["인원"].get(d[0], 0) for r in rs)
            mine_exc = sum(r["인원"].get(d[0], 0) for r in exc)
            out[d[1]][0] += mine
            out[d[1]][1] += pv
            if mine + mine_exc != pv:
                col_bad.append(f"{d[0]} {mine}+{mine_exc}≠{pv}")
        return out, num(cap_raw), outside_total, col_bad

    t1, cap1, out1, bad1 = total_check(1)
    t2, cap2, out2, bad2 = total_check(2)
    exc_s = {"수시": sum(v for r in excluded for k, v in r["인원"].items() if k.startswith("수시")),
             "정시": sum(v for r in excluded for k, v in r["인원"].items() if k.startswith("정시"))}

    jlist = []
    used = {k for r in rows for k in r["인원"]}
    order = [d for d in T1_DEFS + T2_DEFS if isinstance(d, tuple)]
    seen = set()
    for d in order:
        if d[0] in used and d[0] not in seen:
            seen.add(d[0])
            jlist.append({"key": d[0], "시기": d[1], "유형": d[2], "전형명": d[3], "군": d[4]})

    memo.append("정원내만 수록: 수시 농어촌학생·저소득층학생·특성화고교졸업자·특수교육대상자(표 위 안내 '정원외 전형임', 예술·체육 표의 농어촌학생·저소득층학생·특성화고교졸업자 포함)는 넣지 않음")
    memo.append("학생부교과 지역저소득층학생전형(10명)은 정원외 목록에 없고 3쪽 전형 구성표에서 괄호 없는 정원내 인원 → 수록")
    memo.append("스마트가전공학과(8쪽, 각주 2 'LG전자 협약 채용조건형 정원외 계약학과', 3쪽 '스마트가전공학과 정원외 30명 포함')는 행 전체가 정원외라 넣지 않음 "
                f"(PDF 행: 모집인원 30 = 교과지역 5, 탐구 6, 서류 6, 면접지역 5, 다군 수능우수 8)")
    memo.append("표의 행별 '모집인원' 칸은 정원내+정원외(농어촌학생·저소득층학생·특성화고교졸업자) 합이라 정원내 합계 칸이 아님 → 계=null, 검증='합계칸없음'")
    memo.append(f"보조 대조(모집인원 칸 = 정원내 전형 합 + 같은 행 정원외 칸 합, 특수교육대상자 병합 칸 제외): {aux_ok}/{len(rows) + len(excluded)}행 일치"
                + (", 불일치: " + "; ".join(aux_bad) if aux_bad else ""))
    memo.append("계열: 표의 '모집계열' 칸 그대로(인문·사회/자연/광역/체육/예술)")
    memo.append("예술·체육 표(9쪽 표 2)는 학과+전공 두 칸 → '학과 전공'으로 적음. 정시 열은 '수능 가군 / 수능우수'")
    memo.append("의예과 등 각주 번호(1)~4))는 모집단위 이름에서 뺌(건축학과 5년 과정, 정보컴퓨터공학부(인공지능전공) 경북대 공동학과, 한의학전문대학원 학·석사통합과정 7년)")
    rowcap1 = sum(r["_cap"] for r in rows + excluded if r["_kind"] == 1)
    memo.append(f"총계 대조(표 1 합계 행, 정원내 열): 수시 {t1['수시'][0]}+{exc_s['수시']}(스마트가전)={t1['수시'][1]}, "
                f"정시 {t1['정시'][0]}+{exc_s['정시']}(스마트가전)={t1['정시'][1]}; "
                + ("전형별 열 합(정원외 열 포함) 모두 일치" if not bad1 else "전형별 열 불일치: " + "; ".join(bad1)))
    allcols1 = t1["수시"][1] + t1["정시"][1] + out1
    memo.append(f"참고(PDF 안에서 설명되지 않는 차이): 표 1 합계 행 '모집인원' 칸 {cap1} ≠ 합계 행 전 열(정원외·특수교육대상자 포함) 합 {allcols1} "
                f"(행 모집인원 칸 합 {rowcap1}; 각주 '모집인원 합계에 한해 특수교육대상자전형 모집인원을 포함함'). "
                "전형별 열 합계는 모두 맞으므로 정리 데이터에는 영향 없음")
    memo.append(f"총계 대조(표 2 합계 행, 정원내 열): 수시 {t2['수시'][0]}={t2['수시'][1]}, 정시 {t2['정시'][0]}={t2['정시'][1]}; "
                f"PDF 모집인원 합계 {cap2} = 정원내+정원외 열 합 {t2['수시'][1] + t2['정시'][1] + out2}"
                + ("; 전형별 열 합 모두 일치" if not bad2 else "; 전형별 열 불일치: " + "; ".join(bad2)))
    all_s = t1["수시"][0] + t2["수시"][0]
    all_j = t1["정시"][0] + t2["정시"][0]
    all_s_pdf = t1["수시"][1] + t2["수시"][1]
    all_j_pdf = t1["정시"][1] + t2["정시"][1]
    memo.append(f"전체 정원내(스마트가전공학과 제외): 수시 {all_s}, 정시 {all_j}, 계 {all_s + all_j}. "
                f"참고: 3쪽 전형 구성표 수시모집 소계 3,658·정시 1,439·합계 5,097은 정원외 전형과 스마트가전공학과까지 포함한 수치 "
                f"(표 1+2 합계 행 전 열 합: 수시 {all_s_pdf + out1 + out2}, 정시 {all_j_pdf})")
    if bad_rows:
        memo.append("합계불일치 행(PDF 숫자 그대로): " + "; ".join(
            f"{r['모집단위']}(모집인원 {r['계']}, 전형 합 {sum(r['인원'].values())}, 같은 행 정원외 칸 합 {outside_sum(r)})" for r in bad_rows))
    if unread:
        memo.append("읽지 못해 뺀 행/칸: " + "; ".join(unread))

    for r in rows:
        for k in ("_kind", "_raw", "_defs", "_cap"):
            r.pop(k)
    out = {"id": ID, "이름": NAME, "출처쪽": PAGES, "전형": jlist, "모집단위": rows, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(ID, len(rows), "rows", dict(Counter(r["검증"] for r in rows)), "t1", t1_count, "t2", t2_count)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
