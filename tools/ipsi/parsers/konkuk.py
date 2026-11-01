#!/usr/bin/env python3
"""건국대학교(서울캠퍼스) 2028 시행계획 파서.

대상 표:
  - "Ⅳ-2. 전형별 모집인원(정원내외)" (PDF 14~15쪽): 모집단위별 전형 인원
  - "Ⅳ-1. 모집단위별 모집정원" (PDF 12~13쪽): 모집단위별 '모집정원(정원내)' → 계
사용법: python3 -I tools/ipsi/parsers/konkuk.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "konkuk"
UNIV_NAME = "건국대학교"

# 3번째 머리줄(세로 글자 합친 것) → (key 앞부분, 시기, 유형, 전형명). None = 정원외(제외)
HEADER = {
    "KU지역균형": ("수시_교과_KU지역균형", "수시", "학생부교과", "KU지역균형"),
    "KU자기추천": ("수시_종합_KU자기추천", "수시", "학생부종합", "KU자기추천"),
    "기회균형": ("수시_종합_기회균형", "수시", "학생부종합", "기회균형"),
    "특수교육대상자": None,
    "KU논술": ("수시_논술_KU논술", "수시", "논술", "KU논술"),
    "연기실기": ("수시_실기_연기실기", "수시", "실기/실적", "연기실기"),
    "체육특기": ("수시_실기_체육특기", "수시", "실기/실적", "체육특기"),
    "재외국민전형": None,
    "KU일반": ("정시_수능_KU일반", "정시", "수능", "KU일반"),
    "실기": ("정시_수능_실기", "정시", "수능", "실기"),
    "기초생활및차상위": None,
    "농어촌학생": None,
    "특성화고교졸업자": None,
    "특성화고졸재직자": None,
}
# 정원외 중 행의 '모집인원(정원내외)'에 들어가는 열(재외국민·특수교육대상자는 표 각주대로 미포함)
OUT_IN_ROWTOTAL = ("기초생활및차상위", "농어촌학생", "특성화고교졸업자", "특성화고졸재직자")


def join_cell(s):
    if s is None:
        return None
    return "".join(p.strip() for p in s.split("\n"))


def to_int(cell):
    s = (cell or "").strip().replace(",", "").rstrip("*")
    if s in ("", "-"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {cell!r}")


def name_key(s):
    s = re.sub(r"\[[^\]]*\]", "", s or "")
    return re.sub(r"\s+", "", s)


def read_quota(pdf):
    """Ⅳ-1 모집정원(정원내) 표 → {모집단위 키: (값, 쪽, 원문)}, 합계."""
    quota, total, pages = {}, None, []
    for pno, page in enumerate(pdf.pages, start=1):
        for t in page.extract_tables():
            if not t or not t[0]:
                continue
            hdr_idx = None
            for i, r in enumerate(t):
                if r and (r[0] or "").strip() == "단과대학" and "모집정원(정원내)" in [join_cell(c) for c in r]:
                    hdr_idx = i
                    break
            if hdr_idx is None:
                continue
            hdr = [join_cell(c) for c in t[hdr_idx]]
            ci_name, ci_q = hdr.index("모집단위"), hdr.index("모집정원(정원내)")
            pages.append(pno)
            for r in t[hdr_idx + 1:]:
                if (r[0] or "").strip() == "합계":
                    total = to_int(r[ci_q])
                    continue
                nm = join_cell(r[ci_name])
                if not nm:
                    continue
                quota[name_key(nm)] = (r[ci_q].strip(), pno, nm)
    return quota, total, pages


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        quota, quota_total, quota_pages = read_quota(pdf)
        if not quota:
            raise SystemExit("모집정원(정원내) 표를 찾지 못함")

        units, pages_used = [], []
        jeonhyeong = {}
        pdf_total = None
        college = None
        aux_ok, aux_bad = 0, []
        skipped = []
        for pno, page in enumerate(pdf.pages, start=1):
            for t in page.extract_tables():
                if not t or (t[0][0] or "").strip() != "단과대학" or "정원내외" not in (join_cell(t[0][3]) or ""):
                    continue
                pages_used.append(pno)
                h3 = [join_cell(c) for c in t[2]]
                h1 = [join_cell(c) for c in t[1]]
                ci_gun = h1.index("모집군")
                colmap = {}
                for i, h in enumerate(h3):
                    if h in HEADER:
                        colmap[h] = i
                if set(colmap) != set(HEADER):
                    raise SystemExit(f"{pno}쪽 머리글 누락: {set(HEADER) - set(colmap)}")
                for r in t[3:]:
                    c0 = join_cell(r[0])
                    if c0 == "합계":
                        pdf_total = {h: to_int(r[i]) for h, i in colmap.items()}
                        pdf_total["모집인원"] = r[3]
                        continue
                    if c0:
                        college = c0
                    name = join_cell(r[1])
                    gyeyeol = join_cell(r[2]) or None
                    gun = (r[ci_gun] or "").strip()
                    inwon = {}
                    for h, i in colmap.items():
                        spec = HEADER[h]
                        if spec is None:
                            continue
                        if r[i] is None:
                            raise SystemExit(f"{pno}쪽 {name}: 정원내 칸 {h} 병합/누락")
                        v = to_int(r[i])
                        if not v:
                            continue
                        key, sigi, yuhyeong, jname = spec
                        g = None
                        if sigi == "정시":
                            if gun not in ("가", "나", "다"):
                                raise SystemExit(f"{pno}쪽 {name}: 정시 인원 있는데 모집군 {gun!r}")
                            g = gun
                            key = f"{key}_{gun}"
                        jeonhyeong[key] = {"key": key, "시기": sigi, "유형": yuhyeong, "전형명": jname, "군": g}
                        inwon[key] = v
                    # 보조 대조: 모집인원(정원내외) = 정원내 합 + 기초·농어촌·특성화고교졸업자·특성화고졸재직자
                    rowtotal = to_int(r[3])
                    out_sum = sum(to_int(r[colmap[h]]) for h in OUT_IN_ROWTOTAL)
                    if sum(inwon.values()) + out_sum == rowtotal:
                        aux_ok += 1
                    else:
                        aux_bad.append(f"{name}({rowtotal} vs {sum(inwon.values())}+{out_sum})")
                    if not inwon:
                        skipped.append(f"{name}(정원내 인원 없음, 정원외 {out_sum}명만)")
                        continue
                    q = quota.get(name_key(name))
                    gye = None
                    if q is not None and re.fullmatch(r"[\d,]+", q[0]):
                        gye = int(q[0].replace(",", ""))
                    units.append({
                        "단과대학": college,
                        "모집단위": name,
                        "계열": gyeyeol,
                        "인원": inwon,
                        "계": gye,
                        "쪽": pno,
                    })

    for u in units:
        u["검증"] = "합계칸없음" if u["계"] is None else (
            "합계일치" if sum(u["인원"].values()) == u["계"] else "합계불일치")

    order = list(dict.fromkeys(spec[0] for spec in HEADER.values() if spec))
    jlist = sorted(jeonhyeong.values(), key=lambda j: (order.index(j["key"].rsplit("_", 1)[0]) if j["시기"] == "정시"
                                                         else order.index(j["key"]), j["군"] or ""))

    memo = [
        "정원내만 수록: 정원외(재외국민전형, 학생부종합 특수교육대상자, 전형기간자율화 특성화고졸재직자, "
        "정시 기초생활및차상위·농어촌학생·특성화고교졸업자)는 넣지 않음",
        "학생부종합 기회균형은 정원내(p6 요약표 '내') → 수록",
        "계 = Ⅳ-1 '모집단위별 모집정원' 표(p12~13)의 '모집정원(정원내)' 칸 값(2026 이월 인원 없음). "
        "Ⅳ-2 표의 '모집인원(정원내외)' 칸은 정원외가 섞여 있어 계로 쓰지 않음",
        "정시 '실기' 전형은 PDF가 정시 '수능' 유형 아래 둔 전형(수능+실기)이라 유형=수능, 전형명=실기로 적음",
        "정시 전형 key는 모집군별로 나눔(표의 '모집군' 칸 값)",
    ]
    if skipped:
        memo.append("제외 행: " + "; ".join(skipped))
    memo.append(f"보조 대조(모집인원(정원내외) 칸 = 정원내 합 + 기초·농어촌·특성화고교졸업자·특성화고졸재직자): "
                f"{aux_ok}행 일치" + (", 불일치 " + "; ".join(aux_bad) if aux_bad else ""))
    unmatched = [u["모집단위"] for u in units if u["계"] is None]
    if unmatched:
        memo.append("모집정원(정원내) 표에서 못 찾은 모집단위(계=null): " + ", ".join(unmatched))
    if pdf_total:
        susi_keys = [j["key"] for j in jlist if j["시기"] == "수시"]
        jeong_keys = [j["key"] for j in jlist if j["시기"] == "정시"]
        s_me = sum(u["인원"].get(k, 0) for u in units for k in susi_keys)
        j_me = sum(u["인원"].get(k, 0) for u in units for k in jeong_keys)
        s_pdf = sum(pdf_total[h] for h, spec in HEADER.items() if spec and spec[1] == "수시")
        j_pdf = sum(pdf_total[h] for h, spec in HEADER.items() if spec and spec[1] == "정시")
        memo.append(f"총계 대조: 수시 {s_pdf}={s_me}, 정시 {j_pdf}={j_me}, 전체 {quota_total}={s_me + j_me} "
                    f"(Ⅳ-2 표 합계 행 정원내 열 / Ⅳ-1 모집정원 합계)")
        bad = []
        for h, spec in HEADER.items():
            if not spec:
                continue
            mine = sum(v for u in units for k, v in u["인원"].items()
                       if k == spec[0] or k.startswith(spec[0] + "_"))
            if mine != pdf_total[h]:
                bad.append(f"{h}({pdf_total[h]} vs {mine})")
        memo.append("전형별 열 합 대조: " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)))
        for base, label in (("정시_수능_KU일반", "KU일반"), ("정시_수능_실기", "실기")):
            per = {g: sum(u["인원"].get(f"{base}_{g}", 0) for u in units) for g in "가나다"}
            memo.append(f"군별 합({label}): 가 {per['가']}, 나 {per['나']}, 다 {per['다']}")

    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": sorted(set(quota_pages + pages_used)),
           "전형": jlist, "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(units)}행 → {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: konkuk.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
