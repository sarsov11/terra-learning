#!/usr/bin/env python3
"""한국외국어대학교 2028 시행계획 파서.

대상 표: "3 모집단위 및 모집인원(안)" (PDF 5~6쪽, 서울·글로벌 캠퍼스).
사용법: python3 -I tools/ipsi/parsers/hufs.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "hufs"
UNIV_NAME = "한국외국어대학교"

# 표 머리글(3번째 머리줄) → 정원내 전형 key. 정원외(재외국민, 농어촌학생, 기초차상위)는 제외.
HEADER_TO_KEY = {
    "학생부교과(추천)": "수시_교과_학교장추천",
    "학생부종합(면접)": "수시_종합_면접형",
    "학생부종합(SW인재)": "수시_종합_SW인재",
    "학생부종합(서류)": "수시_종합_서류형",
    "기회균형": "수시_종합_기회균형",
    "논술": "수시_논술",
    "일반(가군)": "정시_수능_가",
    "일반(나군)": "정시_수능_나",
    "일반(다군)": "정시_수능_다",
}
OUT_OF_QUOTA_HEADERS = ("재외국민", "농어촌학생", "기초차상위")

JEONHYEONG = [
    {"key": "수시_교과_학교장추천", "시기": "수시", "유형": "학생부교과", "전형명": "학교장추천전형", "군": None},
    {"key": "수시_종합_면접형", "시기": "수시", "유형": "학생부종합", "전형명": "학생부종합전형(면접형)", "군": None},
    {"key": "수시_종합_SW인재", "시기": "수시", "유형": "학생부종합", "전형명": "학생부종합전형(SW인재)", "군": None},
    {"key": "수시_종합_서류형", "시기": "수시", "유형": "학생부종합", "전형명": "학생부종합전형(서류형)", "군": None},
    {"key": "수시_종합_기회균형", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형전형", "군": None},
    {"key": "수시_논술", "시기": "수시", "유형": "논술", "전형명": "논술전형", "군": None},
    {"key": "정시_수능_가", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "가"},
    {"key": "정시_수능_나", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "나"},
    {"key": "정시_수능_다", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]

CAMPUS = {"서울": "서울캠퍼스", "글로벌": "글로벌캠퍼스"}


def join_lines(s):
    """셀 안 줄바꿈 제거. 앞뒤가 모두 한글이 아닌 문자면 공백 하나를 둔다."""
    if s is None:
        return None
    parts = [p.strip() for p in s.split("\n") if p.strip()]
    out = ""
    for p in parts:
        if out and not _is_hangul(out[-1]) and not _is_hangul(p[0]):
            out += " " + p
        else:
            out += p
    return out


def _is_hangul(ch):
    return "가" <= ch <= "힣"


def to_int(cell):
    """'' / '-' → 0, 숫자 → int, 그 밖은 ValueError."""
    s = (cell or "").strip().replace(",", "")
    if s in ("", "-"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {cell!r}")


def find_table(page):
    for t in page.find_tables():
        rows = t.extract()
        if rows and rows[0] and (rows[0][0] or "").strip() == "캠퍼스" and "모집단위" in (rows[0][2] or ""):
            return rows
    return None


def column_map(rows):
    """3번째 머리줄의 전형명으로 열 번호를 찾는다."""
    hdr = [join_lines(c) if c else "" for c in rows[2]]
    hdr = [h.replace(" ", "") for h in hdr]
    colmap = {}
    for i, h in enumerate(hdr):
        if h in HEADER_TO_KEY:
            colmap[HEADER_TO_KEY[h]] = i
    missing = [k for k in HEADER_TO_KEY.values() if k not in colmap]
    if missing:
        raise SystemExit(f"머리글에서 열을 못 찾음: {missing} / {hdr}")
    top = [join_lines(c) or "" for c in rows[0]]
    if top[3].replace(" ", "") != "입학정원":
        raise SystemExit(f"입학정원 열 위치 다름: {top}")
    return colmap


def main(pdf_path, out_path):
    memo = [
        "정원내만 수록: 정원외(재외국민특별전형, 정시 농어촌학생·기초생활수급자및차상위계층 특별전형)는 넣지 않음",
        "수시 기회균형전형은 PDF 표에서 '정원 내' 열 → 수록",
        "표에 행별 정원내 합계 칸 없음(입학정원 칸만 있음, 2026 미충원 이월 포함 모집인원과 다를 수 있음) → 계=null",
        "단과대학 = '<캠퍼스> · <대학>'. 대학 칸이 모집단위까지 병합된 독립 모집단위는 캠퍼스만 적고, "
        "'[통합모집]' 단위는 이름에 적힌 대학명을 단과대학에 씀",
        "계열: PDF가 밝힌 경우(자유전공학부(글로벌)[인문]/[자연])만 기재, 나머지 null",
    ]
    units = []
    pages_used = []
    pdf_total = None
    ipak_check = []  # (이름, 입학정원, 정원내합)

    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            rows = find_table(page)
            if rows is None:
                continue
            pages_used.append(pno)
            colmap = column_map(rows)
            data = rows[3:]
            campus = None
            college = None
            parsed = []  # dict(name, college, cells(row), merged_cols)
            for r in data:
                c0 = join_lines(r[0])
                if c0 == "계":
                    pdf_total = {k: to_int(r[i]) for k, i in colmap.items()}
                    pdf_total["입학정원"] = to_int(r[3])
                    continue
                if c0:
                    if c0 not in CAMPUS:
                        raise SystemExit(f"{pno}쪽: 알 수 없는 캠퍼스 {c0!r}")
                    campus = CAMPUS[c0]
                c1 = join_lines(r[1])
                c2 = join_lines(r[2])
                if c2:  # 일반 행: 대학 + 모집단위
                    if c1:
                        college = c1
                    if college is None:
                        raise SystemExit(f"{pno}쪽: 대학 미상 행 {r}")
                    name, coll = c2, f"{campus} · {college}"
                elif c1:  # 대학 칸이 모집단위까지 병합된 독립 모집단위
                    college = None
                    name = c1
                    m = re.fullmatch(r"(.+)\[통합모집\]", name)
                    coll = f"{campus} · {m.group(1)}" if m else campus
                else:
                    raise SystemExit(f"{pno}쪽: 이름 없는 행 {r}")
                parsed.append({"name": name, "college": coll, "row": r, "page": pno})

            # 세로 병합 칸 처리: 다음 행의 정원내 칸이 None이면 그 칸은 윗행과 병합(공유).
            i = 0
            while i < len(parsed):
                grp = [parsed[i]]
                j = i + 1
                while j < len(parsed) and any(parsed[j]["row"][c] is None for c in colmap.values()):
                    grp.append(parsed[j])
                    j += 1
                if len(grp) == 1:
                    units.append(make_unit(grp[0], colmap))
                    ipak_check.append((grp[0]["name"], to_int(grp[0]["row"][3]), sum(units[-1]["인원"].values())))
                else:
                    units.extend(split_merged_group(grp, colmap, memo))
                i = j

    if not units:
        raise SystemExit("모집단위 표를 찾지 못함")

    # 검증
    for u in units:
        u["검증"] = "합계칸없음" if u["계"] is None else ("합계일치" if sum(u["인원"].values()) == u["계"] else "합계불일치")

    if pdf_total:
        s_pdf = sum(pdf_total[k] for k in SUSI_KEYS)
        j_pdf = sum(pdf_total[k] for k in JEONGSI_KEYS)
        s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
        j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
        memo.append(f"총계 대조: 수시 {s_pdf}={s_me}, 정시 {j_pdf}={j_me} (PDF 표 '계' 행 정원내 열 합 = 정리 데이터 합)")
        bad = [k for k in SUSI_KEYS + JEONGSI_KEYS
               if pdf_total[k] != sum(u["인원"].get(k, 0) for u in units)]
        memo.append("전형별 열 합 대조: " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)))
        memo.append(f"참고: PDF '계' 행 입학정원 {pdf_total['입학정원']} (모집인원에는 2026 미충원 이월 포함)")

    diff = [f"{n}(입학정원 {a}, 정원내합 {b})" for n, a, b in ipak_check if a != b]
    memo.append(f"참고 대조(입학정원 칸 vs 행 정원내 합): {len(ipak_check) - len(diff)}행 같음"
                + (", 다름: " + "; ".join(diff) if diff else ""))

    out = {
        "id": UNIV_ID,
        "이름": UNIV_NAME,
        "출처쪽": pages_used,
        "전형": JEONHYEONG,
        "모집단위": units,
        "메모": memo,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(units)}행 → {out_path}")


def make_unit(p, colmap, cols=None, name=None, gyeyeol=None):
    r = p["row"]
    inwon = {}
    for k, i in colmap.items():
        if cols is not None and i not in cols:
            continue
        v = to_int(r[i])
        if v:
            inwon[k] = v
    return {
        "단과대학": p["college"],
        "모집단위": name or p["name"],
        "계열": gyeyeol,
        "인원": inwon,
        "계": None,
        "쪽": p["page"],
    }


def split_merged_group(grp, colmap, memo):
    """세로 병합 칸을 공유하는 연속 행 묶음.

    공유 칸 값은 공통 이름(괄호 꼬리표 '[...]' 뗀 이름)의 행 하나에,
    각 행 고유 칸 값은 그 행 이름으로 따로 적는다. 합치거나 나누어 계산하지 않는다.
    """
    bases = {re.sub(r"\[[^\]]*\]$", "", g["name"]) for g in grp}
    if len(bases) != 1:
        raise SystemExit(f"병합 행 묶음 이름이 서로 다름: {[g['name'] for g in grp]}")
    base = bases.pop()
    shared = {i for i in colmap.values() if all(g["row"][i] is None for g in grp[1:])}
    own = set(colmap.values()) - shared
    out = [make_unit(grp[0], colmap, cols=shared, name=base)]
    for g in grp:
        m = re.search(r"\[(인문|자연)\]$", g["name"])
        out.append(make_unit(g, colmap, cols=own, gyeyeol=m.group(1) if m else None))
    names = ", ".join(g["name"] for g in grp)
    shared_keys = [k for k, i in colmap.items() if i in shared]
    memo.append(f"{base}: PDF에서 {names} 행이 {', '.join(shared_keys)} 칸을 병합 공유 → "
                f"공유 인원은 '{base}' 행에, 행별 고유 인원(그 밖의 전형)은 각 행에 따로 기재(합산·배분 안 함)")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: hufs.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
