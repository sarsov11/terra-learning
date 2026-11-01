#!/usr/bin/env python3
"""충남대학교 2028학년도 대학입학전형 모집단위별 모집인원 -> 정원내 모집인원.

사용: python3 -I tools/ipsi/parsers/cnu.py <pdf> <out.json>

원문 '2028학년도 대학입학전형 모집단위별 모집인원' 표(가로 쪽 1~3):
  단과 | 모집단위 | 2026학년도 미충원 이월 인원 |
  수시: [정원내] 학생부교과 4 · 학생부종합Ⅰ 2 · 학생부종합Ⅱ 6 · 실기 2 |
        [머리칸 빈칸] 학생부종합Ⅱ 국가안보[해양] · 학생부종합Ⅲ 농어촌~정부위탁 |
  전형기간 자율화(학생부종합Ⅲ 특성화고졸재직자·만학도, 실기 만학도) | 소계 |
  정시: [정원내] 수능 가군일반·가군지역인재·나군일반, 실기 나군일반 | 소계 | 합계
'정원내'라고 적힌 머리칸 아래 칸만 넣는다.
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "cnu"
UNIV_NAME = "충남대학교"

COLS = [
    ("단과", "college"),
    ("모집단위", "name"),
    ("2026학년도미충원이월인원", "carry"),
    ("일반전형", "수시_교과_일반"),
    ("지역인재", "수시_교과_지역인재"),
    ("지역저소득", "수시_교과_지역인재저소득층"),
    ("기회균형Ⅰ", "수시_교과_기회균형1"),
    ("면접", "수시_종합1_면접"),
    ("서류", "수시_종합1_서류"),
    ("소프트웨어", "수시_종합2_소프트웨어인재"),
    ("지역인재", "수시_종합2_지역인재"),
    ("지역의사선발", "수시_종합2_지역의사선발"),
    ("영농창업인재", "수시_종합2_영농창업인재"),
    ("기회균형Ⅱ", "수시_종합2_기회균형2"),
    ("국가안보[국토]", "수시_종합2_국가안보국토"),
    ("일반", "수시_실기_일반"),
    ("체육특기자", "수시_실기_체육특기자"),
    ("국가안보[해양]", "x"),
    ("농어촌", "x"),
    ("특성화고출신자", "x"),
    ("저소득층학생", "x"),
    ("특수교육대상자", "x"),
    ("정부위탁", "x"),
    ("특성화고졸재직자", "x"),
    ("만학도", "x"),
    ("만학도", "x"),
    ("", "susi_sub"),
    ("가군일반", "정시_수능_가_일반"),
    ("가군지역인재", "정시_수능_가_지역인재"),
    ("나군일반", "정시_수능_나_일반"),
    ("나군일반", "정시_실기_나_일반"),
    ("", "js_sub"),
    ("", "total"),
]
# 머리 행 번호 -> 있어야 할 (글자, 첫 칸, 끝 칸)
GROUPS = {
    0: [("수시", 3, 22), ("전형기간자율화", 23, 25), ("정시", 27, 31), ("합계", 32, 32)],
    1: [("정원내", 3, 16), ("", 17, 25), ("소계", 26, 26), ("정원내", 27, 30), ("소계", 31, 31)],
    2: [("학생부교과", 3, 6), ("학생부종합Ⅰ", 7, 8), ("학생부종합Ⅱ", 9, 14), ("실기", 15, 16),
        ("학생부종합Ⅱ", 17, 17), ("학생부종합Ⅲ", 18, 24), ("실기", 25, 25), ("수능", 27, 29), ("실기", 30, 30)],
}
JEONHYEONG = {
    "수시_교과_일반": ("수시", "학생부교과", "일반전형", None),
    "수시_교과_지역인재": ("수시", "학생부교과", "지역인재전형", None),
    "수시_교과_지역인재저소득층": ("수시", "학생부교과", "지역인재 저소득층학생전형", None),
    "수시_교과_기회균형1": ("수시", "학생부교과", "기회균형선발Ⅰ전형", None),
    "수시_종합1_면접": ("수시", "학생부종합", "학생부종합Ⅰ(면접)", None),
    "수시_종합1_서류": ("수시", "학생부종합", "학생부종합Ⅰ(서류)", None),
    "수시_종합2_소프트웨어인재": ("수시", "학생부종합", "학생부종합Ⅱ(소프트웨어인재)", None),
    "수시_종합2_지역인재": ("수시", "학생부종합", "학생부종합Ⅱ(지역인재)", None),
    "수시_종합2_지역의사선발": ("수시", "학생부종합", "학생부종합Ⅱ(지역의사선발)", None),
    "수시_종합2_영농창업인재": ("수시", "학생부종합", "학생부종합Ⅱ(영농창업인재)", None),
    "수시_종합2_기회균형2": ("수시", "학생부종합", "학생부종합Ⅱ(기회균형선발Ⅱ)", None),
    "수시_종합2_국가안보국토": ("수시", "학생부종합", "학생부종합Ⅱ(국가안보융합인재)[국토]", None),
    "수시_실기_일반": ("수시", "실기/실적", "실기 일반", None),
    "수시_실기_체육특기자": ("수시", "실기/실적", "실적 체육특기자", None),
    "정시_수능_가_일반": ("정시", "수능", "수능(일반)", "가"),
    "정시_수능_가_지역인재": ("정시", "수능", "수능(지역인재·지역인재 저소득층학생)", "가"),
    "정시_수능_나_일반": ("정시", "수능", "수능(일반)", "나"),
    "정시_실기_나_일반": ("정시", "실기/실적", "수능(실기)", "나"),
}


def nospace(s):
    return re.sub(r"\s+", "", s or "")


def num(s):
    s = nospace(s).replace(",", "")
    if s in ("", "-"):
        return 0
    if s.isdigit():
        return int(s)
    return None


def parse_page(page):
    tabs = page.find_tables()
    if not tabs:
        raise SystemExit(f"p{page.page_number}: 표 없음")
    tab = max(tabs, key=lambda t: len(t.rows))
    data = tab.extract()
    first = tab.rows[4]
    if len(first.cells) != len(COLS) or any(c is None for c in first.cells):
        raise SystemExit(f"p{page.page_number}: 첫 데이터 행 칸 수 이상")
    edges = [c[0] for c in first.cells] + [first.cells[-1][2]]

    def ci(x):
        for i, e in enumerate(edges):
            if abs(e - x) < 1.5:
                return i
        return None

    for i, (exp, _) in enumerate(COLS):
        txt = ""
        for r in range(4):
            if data[r][i]:
                txt = data[r][i]
        if exp and exp not in nospace(txt):
            raise SystemExit(f"p{page.page_number}: {i}번째 칸 머리글 '{nospace(txt)}'에 '{exp}' 없음")
    for r, groups in GROUPS.items():
        found = []
        for cell, txt in zip(tab.rows[r].cells, data[r]):
            if cell is None:
                continue
            b = ci(cell[2])
            found.append((nospace(txt), ci(cell[0]), None if b is None else b - 1))
        for g in groups:
            if g not in found:
                raise SystemExit(f"p{page.page_number}: 머리 묶음 {g} 없음 (찾은 것: {found})")
    rows = []
    for ri in range(4, len(data)):
        d = data[ri]
        rows.append({"college": nospace(d[0]), "name": nospace(d[1]), "vals": [num(v) for v in d[2:]],
                     "page": page.page_number})
    return rows


def main():
    if len(sys.argv) != 3:
        raise SystemExit("사용: cnu.py <pdf> <out.json>")
    pdf = pdfplumber.open(sys.argv[1])
    pages = []
    for p in pdf.pages[:10]:
        t = nospace(p.extract_text())
        if "모집단위별모집인원" in t and "정원내" in t and "합계" in t:
            pages.append(p.page_number)
    if not pages:
        raise SystemExit("모집인원 표 쪽을 찾지 못함")
    allrows = []
    for pno in pages:
        allrows.extend(parse_page(pdf.pages[pno - 1]))
    pdf.close()

    roles = [r for _, r in COLS[2:]]  # vals 기준 번호
    ri = {r: i for i, r in enumerate(roles) if r not in ("x",)}
    in_keys = [(i, r) for i, r in enumerate(roles) if r in JEONHYEONG]
    x_idx = [i for i, r in enumerate(roles) if r == "x"]
    susi_cols = list(range(ri["carry"] + 1, ri["susi_sub"]))
    js_cols = list(range(ri["susi_sub"] + 1, ri["js_sub"]))

    bad = [f"p{r['page']} {r['name']}" for r in allrows if any(v is None for v in r["vals"])]
    if bad:
        raise SystemExit("숫자 아닌 칸: " + "; ".join(bad))
    total_rows = [r for r in allrows if r["college"] == "합계"]
    if len(total_rows) != 1:
        raise SystemExit("합계 행을 찾지 못함")
    tot = total_rows[0]["vals"]
    units = [r for r in allrows if r["college"] != "합계"]
    if any(not r["college"] or not r["name"] for r in units):
        raise SystemExit("단과/모집단위 빈칸 행 있음")

    ok = {"susi": 0, "js": 0, "all": 0}
    mism = []
    for r in units:
        v = r["vals"]
        if sum(v[i] for i in susi_cols) == v[ri["susi_sub"]]:
            ok["susi"] += 1
        else:
            mism.append(f"{r['name']} 수시소계")
        if sum(v[i] for i in js_cols) == v[ri["js_sub"]]:
            ok["js"] += 1
        else:
            mism.append(f"{r['name']} 정시소계")
        if v[ri["susi_sub"]] + v[ri["js_sub"]] == v[ri["total"]]:
            ok["all"] += 1
        else:
            mism.append(f"{r['name']} 합계")
    colsum = [sum(r["vals"][i] for r in units) for i in range(len(tot))]
    col_bad = [COLS[2 + i][0] or roles[i] for i in range(len(tot)) if colsum[i] != tot[i]]

    out, excluded, carry = [], [], []
    sum_in = {k: 0 for k in JEONHYEONG}
    for r in units:
        v = r["vals"]
        if v[ri["carry"]]:
            carry.append(f"{r['name']} {v[ri['carry']]}")
        insw = {k: v[i] for i, k in in_keys if v[i]}
        if not insw:
            xs = sum(v[i] for i in x_idx)
            excluded.append(f"{r['name']}(정원내 칸 0, 빈 머리칸 아래 {xs}명)")
            continue
        for k, n in insw.items():
            sum_in[k] += n
        out.append({
            "단과대학": r["college"],
            "모집단위": r["name"],
            "계열": None,
            "인원": insw,
            "계": None,
            "쪽": r["page"],
            "검증": "합계칸없음",
        })
    pdf_tot = {k: tot[i] for i, k in in_keys}
    susi_pdf = sum(pdf_tot[k] for k in pdf_tot if k.startswith("수시_"))
    susi_ours = sum(sum_in[k] for k in sum_in if k.startswith("수시_"))
    js_pdf = sum(pdf_tot[k] for k in pdf_tot if k.startswith("정시_"))
    js_ours = sum(sum_in[k] for k in sum_in if k.startswith("정시_"))
    k_bad = [k for k in pdf_tot if pdf_tot[k] != sum_in[k]]
    x_labels = ["국가안보[해양]", "농어촌", "특성화고출신자", "저소득층학생", "특수교육대상자", "정부위탁",
                "특성화고졸재직자", "만학도", "실기 만학도"]
    x_desc = ", ".join(f"{lab} {tot[i]}" for lab, i in zip(x_labels, x_idx))

    memo = [
        "정원내만 수록: 표 머리에 '정원내'라고 적힌 칸(수시 학생부교과~실기 14칸, 정시 수능·실기 4칸)만 넣음.",
        "수시 학생부종합Ⅱ 국가안보[해양], 학생부종합Ⅲ 농어촌·특성화고출신자·저소득층학생·특수교육대상자·정부위탁, "
        "전형기간 자율화 특성화고졸재직자·만학도·실기 만학도 9칸은 '정원내' 머리칸 밖(그 위 머리칸이 빈칸)이라 정원내로 "
        f"확인되지 않아 넣지 않음(합계 행: {x_desc}). PDF 어디에도 '정원외' 글자는 없음.",
        "'2026학년도 미충원 이월 인원' 칸(" + ", ".join(carry) + ")은 수시 소계·합계에 들어가지 않는 별도 숫자라 넣지 않음.",
        "'계'는 null: 행의 수시 소계·합계는 빈 머리칸 아래 9칸을 포함하므로 정원내 합계 칸이 아님.",
        f"행 대조(원문 숫자끼리): 수시 소계 = 수시·자율화 23칸 합 {ok['susi']}/{len(units)}행, 정시 소계 = 정시 4칸 합 "
        f"{ok['js']}/{len(units)}행, 합계 = 수시 소계+정시 소계 {ok['all']}/{len(units)}행 일치"
        + ("" if not mism else f"; 불일치: {mism}")
        + "; 모집단위 행 칸별 합 = '합계' 행 " + ("33칸 모두 일치" if not col_bad else f"불일치 {col_bad}") + ".",
        f"총계 대조: 수시 {susi_ours}={susi_pdf}, 정시 {js_ours}={js_pdf}('합계' 행 정원내 칸 합; 정시 소계 칸 "
        f"{tot[ri['js_sub']]})" + ("" if not k_bad else f"; 전형별 불일치: {k_bad}") + ".",
        "정시 사범대학 체육교육과 14명은 PDF에서 '수능 가군 일반' 칸에 있음(본문상 실기고사 병행) — 칸 그대로 수능으로 둠. "
        "정시 '실기 나군 일반' 칸은 디자인창의학과 2개 모집단위뿐.",
        "계열: 표에 계열 칸이 없어 null.",
    ]
    if excluded:
        memo.append("정원내 인원이 없어 뺀 모집단위: " + "; ".join(excluded))

    used = {k for u in out for k in u["인원"]}
    data = {
        "id": UNIV_ID,
        "이름": UNIV_NAME,
        "출처쪽": pages,
        "전형": [{"key": k, "시기": t[0], "유형": t[1], "전형명": t[2], "군": t[3]}
                 for k, t in JEONHYEONG.items() if k in used],
        "모집단위": out,
        "메모": memo,
    }
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(out)} rows -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
