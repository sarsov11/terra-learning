#!/usr/bin/env python3
"""성균관대학교 2028 시행계획 -> norm JSON.

원천: '2028학년도 모집단위 및 모집인원 총괄표' (일반전형, 수시+정시 한 표, 행별 '모집인원' 계 칸 있음).
총계 대조: '2028학년도 모집시기 및 전형유형별 선발 개요' 표의 '수시 계 / 정시 계 / 총 계' 정원내 값.
정원외 계약학과(반도체시스템공학과, 지능형소프트웨어학과, 배터리학과)는 이 표에 섞여 있으므로 제외한다.

usage: python3 -I tools/ipsi/parsers/skku.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "skku"
UNIV_NAME = "성균관대학교"

# (상위 유형 헤더, 전형 헤더, 군) -> 전형 정의
COLMAP = {
    ("학생부종합(서류형)", "융합인재", None): ("수시_종합_융합인재", "수시", "학생부종합", "학생부종합(서류형) 융합인재", None),
    ("학생부종합(서류형)", "탐구인재", None): ("수시_종합_탐구인재", "수시", "학생부종합", "학생부종합(서류형) 탐구인재", None),
    ("학생부종합(서류형)", "기회균형", None): ("수시_종합_기회균형", "수시", "학생부종합", "학생부종합(서류형) 기회균형", None),
    ("학생부종합(면접형)", "성균인재", None): ("수시_종합_성균인재", "수시", "학생부종합", "학생부종합(면접형) 성균인재", None),
    ("학생부종합(면접형)", "과학인재", None): ("수시_종합_과학인재", "수시", "학생부종합", "학생부종합(면접형) 과학인재", None),
    ("학생부교과", "추천인재", None): ("수시_교과_추천인재", "수시", "학생부교과", "학생부교과 추천인재", None),
    ("논술위주", "언어형", None): ("수시_논술_언어형", "수시", "논술", "논술위주 언어형", None),
    ("논술위주", "수리형", None): ("수시_논술_수리형", "수시", "논술", "논술위주 수리형", None),
    ("실기/실적위주", "예체능특기자", None): ("수시_실기_예체능특기자", "수시", "실기/실적", "실기/실적(특기형) 예체능특기자", None),
    ("실기/실적위주", "예체능실기우수자", None): ("수시_실기_예체능실기우수자", "수시", "실기/실적", "실기/실적(실기형) 예체능실기우수자", None),
}
for g in ("가", "나", "다"):
    COLMAP[("수능위주", "일반형", g)] = (f"정시_수능_일반형_{g}", "정시", "수능", "일반전형(수능위주) 일반형", g)
    COLMAP[("수능위주", "특화형", g)] = (f"정시_수능_특화형_{g}", "정시", "수능", "일반전형(수능위주) 특화형", g)
    COLMAP[("학생부종합(서류형)", "융합인재", g)] = (f"정시_종합_융합인재_{g}", "정시", "학생부종합", "학생부종합(서류형) 융합인재", g)

CONTRACT_DEPTS = ["반도체시스템공학과", "지능형소프트웨어학과", "배터리학과"]


def norm(s):
    return re.sub(r"\s+", "", s or "")


def to_int(s):
    """'' / None / '-' -> 0, '1,234' -> 1234, 그 밖은 ValueError."""
    t = norm(s)
    if t in ("", "-"):
        return 0
    if not re.fullmatch(r"\d{1,3}(,\d{3})*|\d+", t):
        raise ValueError(f"숫자 아님: {s!r}")
    return int(t.replace(",", ""))


def fill_right(row):
    out, last = [], None
    for c in row:
        if c is not None:
            last = c
        out.append(last)
    return out


def find_summary_page(pdf):
    hits = []
    for i, p in enumerate(pdf.pages, 1):
        t = p.extract_text() or ""
        if ("2028학년도 모집단위 및 모집인원 총괄표" in t and "일반전형" in t
                and "언어형" in t and "정시모집" in t and "합계" in t):
            hits.append(i)
    if len(hits) != 1:
        raise SystemExit(f"총괄표(일반전형) 쪽을 하나로 특정하지 못함: {hits}")
    return hits[0]


def find_totals(pdf):
    for i, p in enumerate(pdf.pages, 1):
        t = p.extract_text() or ""
        if "모집시기 및 전형유형별 선발 개요" not in t:
            continue
        num = r"([\d,]+)"
        ms = re.search(r"수시 계 " + num + " " + num + " " + num, t)
        mj = re.search(r"정시 계 " + num + " " + num + " " + num, t)
        mt = re.search(r"총 계 " + num + " " + num + " " + num, t)
        if ms and mj and mt:
            return i, to_int(ms.group(1)), to_int(mj.group(1)), to_int(mt.group(1))
    return None


def check_contract_footnotes(pdf):
    """계약학과 이름이 '정원외 계약학과' 각주에 실제로 있는지 확인하고 그 쪽을 돌려준다."""
    found = {}
    for i, p in enumerate(pdf.pages, 1):
        for line in (p.extract_text() or "").split("\n"):
            if "정원외 계약학과" in line:
                for d in CONTRACT_DEPTS:
                    if d in line:
                        found.setdefault(d, i)
    missing = [d for d in CONTRACT_DEPTS if d not in found]
    if missing:
        raise SystemExit(f"계약학과 각주 확인 실패: {missing}")
    return found


def main(pdf_path, out_path):
    pdf = pdfplumber.open(pdf_path)
    pno = find_summary_page(pdf)
    page = pdf.pages[pno - 1]
    base = max(page.find_tables(), key=lambda t: len(t.rows))
    x0, _, x1, _ = base.bbox
    # 표 좌우 바깥선이 데이터 영역에서 빠져 있어 명시적으로 넣어 준다.
    table = max(page.find_tables({"explicit_vertical_lines": [x0, x1]}), key=lambda t: len(t.rows))
    rows = table.extract()

    # ---- 헤더 ----
    hdr_end = next(i for i, r in enumerate(rows) if any(norm(c) == "가" for c in r if c))
    h_type = fill_right(rows[1])
    h_name = fill_right(rows[2])
    h_grp = rows[3]
    ncol = len(rows[0])
    if norm(rows[0][2]) != "모집인원":
        raise SystemExit(f"모집인원 칸 위치가 예상과 다름: {rows[0][2]!r}")
    colinfo = {}
    for j in range(3, ncol):
        key = (norm(h_type[j]), norm(h_name[j]), norm(h_grp[j]) or None)
        if key not in COLMAP:
            raise SystemExit(f"알 수 없는 열 헤더: col{j} {key}")
        colinfo[j] = COLMAP[key]

    jeonhyeong = []
    seen = set()
    for j in sorted(colinfo):
        k, sg, yh, nm, gun = colinfo[j]
        if k not in seen:
            seen.add(k)
            jeonhyeong.append({"key": k, "시기": sg, "유형": yh, "전형명": nm, "군": gun})

    contract_pages = check_contract_footnotes(pdf)

    units, excluded, problems = [], [], []
    group = None
    colsum_all = {j: 0 for j in colinfo}
    total_row = None
    for r in rows[hdr_end + 1:]:
        c0, c1 = norm(r[0]) if r[0] else None, norm(r[1]) if r[1] else None
        if c0 == "합계":
            total_row = r
            break
        if c0 and c1:
            group = c0
            label = c1
        elif c0 and not c1:
            group = None
            label = c0
        elif c1 and not c0:
            if group is None:
                problems.append(f"상위 묶음 없는 하위행: {c1}")
                continue
            label = c1
        else:
            problems.append(f"이름 없는 행: {r}")
            continue
        if group and re.search(r"(학과|학부)$", group):
            dept, college = f"{group}({label})", None
        else:
            dept, college = label, group
        try:
            total = to_int(r[2])
            vals = {j: to_int(r[j]) for j in colinfo}
        except ValueError as e:
            problems.append(f"{dept}: {e}")
            continue
        for j, v in vals.items():
            colsum_all[j] += v
        if dept in CONTRACT_DEPTS:
            excluded.append(f"{dept}({total})")
            continue
        inwon = {}
        for j, v in vals.items():
            if v:
                k = colinfo[j][0]
                inwon[k] = inwon.get(k, 0) + v
        s = sum(inwon.values())
        units.append({
            "단과대학": college,
            "모집단위": dept,
            "계열": None,
            "인원": inwon,
            "계": total,
            "쪽": pno,
            "검증": "합계일치" if s == total else "합계불일치",
        })

    if total_row is None:
        raise SystemExit("합계 행을 찾지 못함")
    # 표의 합계 행(계약학과 포함)과 열 합 대조 — 추출 누락 확인용
    col_mismatch = []
    for j in colinfo:
        tv = to_int(total_row[j])
        if tv != colsum_all[j]:
            col_mismatch.append(f"{colinfo[j][0]} 합계행 {tv} != 행합 {colsum_all[j]}")

    memo = [
        "정원내만 수록. 정원외 특별전형(농어촌·이웃사랑·특성화고교졸업자·장애인등·특성화고졸재직자 등)과 재외국민은 넣지 않음",
        "정원외 채용조건형 계약학과(" + ", ".join(CONTRACT_DEPTS) + ")는 총괄표에 함께 실려 있으나 제외함: " + ", ".join(excluded)
        + f" (근거 각주 {sorted(set(contract_pages.values()))}쪽)",
        "학생부종합(면접형) 성균인재의 의예과 24명은 일반형 20명 + 성균인재-지역인재 4명을 합친 표 값 그대로임(표 각주)",
        "계는 표의 '모집인원' 칸(행 합계), 쪽 번호는 PDF 파일 기준 1부터",
        "계열: 표에 인문/자연 구분 칸이 없어 null",
    ]
    if col_mismatch:
        memo.append("열 합계 불일치: " + "; ".join(col_mismatch))
    else:
        memo.append("표 합계행(계약학과 포함)과 열별 합 모두 일치")

    pages = {pno}
    tot = find_totals(pdf)
    su = sum(v for u in units for k, v in u["인원"].items() if k.startswith("수시_"))
    jo = sum(v for u in units for k, v in u["인원"].items() if k.startswith("정시_"))
    if tot:
        tp, ts, tj, tt = tot
        pages.add(tp)
        memo.append(f"총계 대조: 수시 {su}={ts}, 정시 {jo}={tj}, 전체 {su + jo}={tt}"
                    + ("" if (su, jo, su + jo) == (ts, tj, tt) else " (불일치)")
                    + f" (정원내 총계 출처 {tp}쪽)")
    else:
        memo.append(f"총계 대조: PDF 정원내 총계를 찾지 못함 (파싱 합 수시 {su}, 정시 {jo})")
    if problems:
        memo.append("읽지 못한 행: " + "; ".join(problems))

    out = {
        "id": UNIV_ID,
        "이름": UNIV_NAME,
        "출처쪽": sorted(pages),
        "전형": jeonhyeong,
        "모집단위": units,
        "메모": memo,
    }
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
