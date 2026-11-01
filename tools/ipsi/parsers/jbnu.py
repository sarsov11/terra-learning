#!/usr/bin/env python3
"""전북대학교 2028학년도 대학입학전형시행계획 -> 모집단위별 정원내 모집인원.

사용: python3 -I tools/ipsi/parsers/jbnu.py <pdf> <out.json>

원문 '3 모집단위 및 전형별 모집인원' 표(가로 쪽 4~7, PDF 6~9쪽):
  모집단위 | 입학정원 내(수시 학생부종합 6칸, 학생부교과 11칸, 일반학생(예체능-실기)) |
  입학정원 외(학생부종합 농어촌·기회균형선발·특성화고교졸업자·특수교육대상자, 전형기간자율화 특성화고졸재직자·만학도(정원외)) |
  입학정원 내(전형기간자율화 만학도(정원내), 정시 ㉮군 2칸, ㉯군 3칸) | 합계
단과대학 소계 행(굵은 글씨, 예: 간호대학)은 그 위 모집단위 행들의 합이며 넣지 않는다.
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "jbnu"
UNIV_NAME = "전북대학교"

# (머리글에 들어 있어야 할 글자, 역할 key 또는 'out'/'jayul_in'/'total')
COLS = [
    ("모집단위", "name"),
    ("큰사람", "수시_종합_큰사람"),
    ("지역인재1유형(호남)", "수시_종합_지역인재1유형"),
    ("지역인재2유형(전북)", "수시_종합_지역인재2유형"),
    ("SW인재", "수시_종합_SW인재"),
    ("사회통합", "수시_종합_사회통합"),
    ("국가보훈대상자", "수시_종합_국가보훈대상자"),
    ("일반학생", "수시_교과_일반학생"),
    ("지역인재1유형(호남)", "수시_교과_지역인재1유형"),
    ("지역인재2유형(전북)", "수시_교과_지역인재2유형"),
    ("지역인재기회균형(호남)", "수시_교과_지역인재기회균형"),
    ("농어촌학생", "수시_교과_농어촌학생"),
    ("지역의사선발(광역권)", "수시_교과_지역의사선발_광역권"),
    ("지역의사선발(전주권)", "수시_교과_지역의사선발_전주권"),
    ("지역의사선발(군산권)", "수시_교과_지역의사선발_군산권"),
    ("지역의사선발(익산권)", "수시_교과_지역의사선발_익산권"),
    ("지역의사선발(정읍권)", "수시_교과_지역의사선발_정읍권"),
    ("지역의사선발(남원권)", "수시_교과_지역의사선발_남원권"),
    ("일반학생(예체능-실기)", "수시_실기_예체능실기"),
    ("농어촌학생", "out"),
    ("기회균형선발", "out"),
    ("특성화고교졸업자", "out"),
    ("특수교육대상자", "out"),
    ("특성화고졸재직자", "out"),
    ("만학도(정원외)", "out"),
    ("만학도(정원내)", "jayul_in"),
    ("일반학생(수능)", "정시_수능_가_일반학생"),
    ("지역인재2유형(전북)(수능)", "정시_수능_가_지역인재2유형"),
    ("일반학생(수능)", "정시_수능_나_일반학생"),
    ("지역인재2유형(전북)(수능)", "정시_수능_나_지역인재2유형"),
    ("일반학생(예체능-실기)", "정시_실기_나_예체능실기"),
    ("합계", "total"),
]
# 머리글 묶음: 표 머리 행 번호 -> [(글자, 첫 칸, 끝 칸)]
GROUPS = {
    0: [("입학정원내", 1, 18), ("입학정원외", 19, 24), ("입학정원내", 25, 30), ("합계", 31, 31)],
    1: [("수시모집", 1, 22), ("전형기간자율화", 23, 25), ("정시모집", 26, 30)],
    2: [("학생부종합", 1, 6), ("학생부교과", 7, 17), ("학생부종합", 19, 25), ("㉮군", 26, 27), ("㉯군", 28, 30)],
}
JEONHYEONG = {
    "수시_종합_큰사람": ("수시", "학생부종합", "큰사람전형", None),
    "수시_종합_지역인재1유형": ("수시", "학생부종합", "지역인재1유형(호남)전형", None),
    "수시_종합_지역인재2유형": ("수시", "학생부종합", "지역인재2유형(전북)전형", None),
    "수시_종합_SW인재": ("수시", "학생부종합", "SW인재전형", None),
    "수시_종합_사회통합": ("수시", "학생부종합", "사회통합전형", None),
    "수시_종합_국가보훈대상자": ("수시", "학생부종합", "국가보훈대상자전형", None),
    "수시_교과_일반학생": ("수시", "학생부교과", "일반학생전형", None),
    "수시_교과_지역인재1유형": ("수시", "학생부교과", "지역인재1유형(호남)전형", None),
    "수시_교과_지역인재2유형": ("수시", "학생부교과", "지역인재2유형(전북)전형", None),
    "수시_교과_지역인재기회균형": ("수시", "학생부교과", "지역인재기회균형(호남)전형", None),
    "수시_교과_농어촌학생": ("수시", "학생부교과", "농어촌학생전형", None),
    "수시_교과_지역의사선발_광역권": ("수시", "학생부교과", "지역의사선발전형(광역권)", None),
    "수시_교과_지역의사선발_전주권": ("수시", "학생부교과", "지역의사선발전형(전주권)", None),
    "수시_교과_지역의사선발_군산권": ("수시", "학생부교과", "지역의사선발전형(군산권)", None),
    "수시_교과_지역의사선발_익산권": ("수시", "학생부교과", "지역의사선발전형(익산권)", None),
    "수시_교과_지역의사선발_정읍권": ("수시", "학생부교과", "지역의사선발전형(정읍권)", None),
    "수시_교과_지역의사선발_남원권": ("수시", "학생부교과", "지역의사선발전형(남원권)", None),
    "수시_실기_예체능실기": ("수시", "실기/실적", "일반학생(예체능-실기)전형", None),
    "정시_수능_가_일반학생": ("정시", "수능", "일반학생(수능)전형", "가"),
    "정시_수능_가_지역인재2유형": ("정시", "수능", "지역인재2유형(전북)(수능)전형", "가"),
    "정시_수능_나_일반학생": ("정시", "수능", "일반학생(수능)전형", "나"),
    "정시_수능_나_지역인재2유형": ("정시", "수능", "지역인재2유형(전북)(수능)전형", "나"),
    "정시_실기_나_예체능실기": ("정시", "실기/실적", "일반학생(예체능-실기)전형", "나"),
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


def col_of(edges, x, tol=1.5):
    for i, e in enumerate(edges):
        if abs(e - x) < tol:
            return i
    return None


def parse_page(page):
    tabs = page.find_tables()
    if not tabs:
        raise SystemExit(f"p{page.page_number}: 표 없음")
    tab = max(tabs, key=lambda t: len(t.rows))
    data = tab.extract()
    # 칸 경계: 첫 데이터 행('전체 모집인원' 또는 첫 모집단위 행)은 칸이 모두 나뉘어 있음
    first = tab.rows[4]
    if len(first.cells) != len(COLS) or any(c is None for c in first.cells):
        raise SystemExit(f"p{page.page_number}: 첫 데이터 행 칸 수 이상")
    edges = [c[0] for c in first.cells] + [first.cells[-1][2]]
    edges = sorted(set(round(e, 1) for e in edges))
    if len(edges) != len(COLS) + 1:
        raise SystemExit(f"p{page.page_number}: 칸 경계 수 이상")
    # 머리글 확인(4번째 행 + 세로 병합된 칸은 위 행에서)
    for i, (exp, _) in enumerate(COLS):
        txt = ""
        for r in range(4):
            if data[r][i]:
                txt = data[r][i]
        if exp not in nospace(txt):
            raise SystemExit(f"p{page.page_number}: {i}번째 칸 머리글 '{nospace(txt)}'에 '{exp}' 없음")
    for r, groups in GROUPS.items():
        found = []
        for cell, txt in zip(tab.rows[r].cells, data[r]):
            if cell is None or not nospace(txt):
                continue
            a, b = col_of(edges, cell[0]), col_of(edges, cell[2])
            found.append((nospace(txt), a, None if b is None else b - 1))
        for g in groups:
            if g not in found:
                raise SystemExit(f"p{page.page_number}: 머리 묶음 {g} 없음 (찾은 것: {found})")
    rows = []
    for ri in range(4, len(data)):
        cells = tab.rows[ri].cells
        if cells[0] is None:
            raise SystemExit(f"p{page.page_number}: {ri}행 이름칸 없음")
        x0, top, x1, bottom = cells[0]
        nm_chars = [c for c in page.chars if c["text"].strip() and x0 <= (c["x0"] + c["x1"]) / 2 < x1
                    and top <= (c["top"] + c["bottom"]) / 2 < bottom]
        bold = bool(nm_chars) and all("Bold" in c["fontname"] for c in nm_chars)
        name = nospace(data[ri][0])
        vals = [num(v) for v in data[ri][1:]]
        rows.append({"name": name, "bold": bold, "vals": vals, "raw": data[ri][1:], "page": page.page_number})
    return rows


def main():
    if len(sys.argv) != 3:
        raise SystemExit("사용: jbnu.py <pdf> <out.json>")
    pdf = pdfplumber.open(sys.argv[1])
    pages = []
    for p in pdf.pages[:15]:
        t = nospace(p.extract_text())
        if "입학정원내" in t and "입학정원외" in t and "모집단위" in t and "정시모집" in t:
            pages.append(p.page_number)
    if not pages:
        raise SystemExit("모집인원 표 쪽을 찾지 못함")
    allrows = []
    for pno in pages:
        allrows.extend(parse_page(pdf.pages[pno - 1]))
    overview = ""
    for p in pdf.pages[:pages[0] - 1]:
        t = p.extract_text() or ""
        if "모집인원 및 모집비율" in t:
            overview = t
            break
    pdf.close()

    roles = [r for _, r in COLS[1:]]
    in_keys = [(i, r) for i, r in enumerate(roles) if r in JEONHYEONG]
    out_idx = [i for i, r in enumerate(roles) if r == "out"]
    jay_idx = [i for i, r in enumerate(roles) if r == "jayul_in"]
    tot_idx = roles.index("total")
    ncol = tot_idx

    problems = []
    for r in allrows:
        bad = [COLS[1 + i][0] for i, v in enumerate(r["vals"]) if v is None]
        if bad:
            problems.append(f"p{r['page']} {r['name']}: 숫자 아닌 칸 {bad}")
    if problems:
        raise SystemExit("; ".join(problems))

    # 행 구분: 전체/합계, 단과대학 소계(굵은 글씨), 모집단위
    grand_top = grand_bot = None
    units, pending, subtot_ok, subtot_bad = [], [], 0, []
    row_ok, row_bad = 0, []
    for r in allrows:
        v = r["vals"]
        s = sum(v[:ncol])
        if s == v[tot_idx]:
            row_ok += 1
        else:
            row_bad.append(f"{r['name']}: 칸합 {s} vs 합계 {v[tot_idx]}")
        if r["name"] == "전체모집인원":
            grand_top = v
            continue
        if r["name"] == "합계":
            grand_bot = v
            continue
        if r["bold"]:
            if not pending:
                raise SystemExit(f"소계 행 '{r['name']}' 앞에 모집단위 행 없음")
            colsum = [sum(u["vals"][i] for u in pending) for i in range(len(v))]
            if colsum == v:
                subtot_ok += 1
            else:
                subtot_bad.append(r["name"])
            for u in pending:
                u["college"] = r["name"]
            units.extend(pending)
            pending = []
        else:
            m = re.match(r"^본부(.+)$", r["name"])
            if m and r["page"] == pages[-1]:
                # 마지막 쪽 '본부 ○○학과' 행: 소계 행 없이 이름칸에 '본부'가 앞에 붙어 있음
                r["college"] = "본부"
                r["name"] = m.group(1)
                units.append(r)
            else:
                pending.append(r)
    if pending:
        raise SystemExit(f"소계 행 없이 끝난 모집단위: {[u['name'] for u in pending]}")
    if grand_top is None or grand_bot is None:
        raise SystemExit("전체 모집인원/합계 행을 찾지 못함")
    unit_colsum = [sum(u["vals"][i] for u in units) for i in range(len(grand_bot))]

    out_units, excluded, jayul_rows = [], [], []
    sum_in = {k: 0 for k in JEONHYEONG}
    for u in units:
        v = u["vals"]
        insw = {k: v[i] for i, k in in_keys if v[i]}
        jay = sum(v[i] for i in jay_idx)
        outn = sum(v[i] for i in out_idx)
        if jay:
            jayul_rows.append(f"{u['name']} {jay}명")
        if not insw:
            why = []
            if outn:
                why.append(f"정원외 {outn}명")
            if jay:
                why.append(f"전형기간자율화 만학도(정원내) {jay}명")
            excluded.append(f"{u['name']}({', '.join(why) or '인원 없음'})")
            continue
        for k, n in insw.items():
            sum_in[k] += n
        out_units.append({
            "단과대학": u["college"],
            "모집단위": u["name"],
            "계열": None,
            "인원": insw,
            "계": None,
            "쪽": u["page"],
            "검증": "합계칸없음",
        })

    pdf_tot = {k: grand_bot[i] for i, k in in_keys}
    col_bad = [k for k in pdf_tot if pdf_tot[k] != sum_in[k]]
    susi_pdf = sum(pdf_tot[k] for k in pdf_tot if k.startswith("수시_"))
    susi_ours = sum(sum_in[k] for k in sum_in if k.startswith("수시_"))
    js_pdf = sum(pdf_tot[k] for k in pdf_tot if k.startswith("정시_"))
    js_ours = sum(sum_in[k] for k in sum_in if k.startswith("정시_"))
    jay_tot = sum(grand_bot[i] for i in jay_idx)
    in_all = susi_pdf + js_pdf + jay_tot
    ov_nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", overview)]
    if in_all in ov_nums and js_pdf in ov_nums:
        ov_msg = (f"개요표('모집인원 및 모집비율') 정원내 {in_all:,} = 수시 {susi_pdf} + 정시 {js_pdf} + 자율화 "
                  f"만학도(정원내) {jay_tot}, 정시 {js_pdf} 숫자 확인")
    else:
        ov_msg = f"개요표에서 정원내 {in_all:,}·정시 {js_pdf}를 찾지 못해 대조 못 함"

    memo = [
        "정원내만 수록. 입학정원 외 6칸(학생부종합 농어촌학생·기회균형선발·☆특성화고교졸업자·특수교육대상자, "
        "전형기간자율화 ★특성화고졸재직자·만학도(정원외))은 넣지 않음.",
        f"전형기간자율화 학생부종합 만학도(정원내) {jay_tot}명({', '.join(jayul_rows)})은 PDF가 수시·정시와 따로 "
        "'전형기간 자율화'로 분류해 시기를 정할 수 없어 넣지 않음.",
        "'계'는 null: 표의 행 '합계'는 정원외·전형기간자율화를 포함한 숫자라 정원내 합계 칸이 아님.",
        f"행 대조(원문 숫자끼리, 정원외 포함): 각 행 31칸 합 = '합계' 칸 {row_ok}행 일치/{len(row_bad)}행 불일치"
        f"(전체·소계 행 포함 {len(allrows)}행); 단과대학 소계 행 = 위 모집단위 행 합 {subtot_ok}개 일치/"
        f"{len(subtot_bad)}개 불일치; 모집단위 행 칸별 합 = '합 계' 행 "
        + ("일치" if unit_colsum == grand_bot else "불일치")
        + "; '전체 모집인원' 행 = '합 계' 행 " + ("일치" if grand_top == grand_bot else "불일치") + ".",
        f"총계 대조: 수시 {susi_ours}={susi_pdf}, 정시 {js_ours}={js_pdf}('합 계' 행 정원내 칸 합); {ov_msg}"
        + ("" if not col_bad else f"; 전형별 불일치 칸: {col_bad}"),
        "단과대학은 각 모집단위 아래 굵은 글씨 소계 행 이름(예: '공과대학 / AI대학'). 마지막 쪽 '본부 ○○' 행은 "
        "소계 행이 없고 이름 앞에 '본부'가 붙어 있어 단과대학을 '본부'로 둠.",
        "계열: 표에 계열 구분 칸이 없어 null(모집단위 이름의 '인문계열·공학계열1' 등은 이름 그대로 둠).",
    ]
    if excluded:
        memo.append("정원내(수시·정시) 인원이 없어 뺀 모집단위: " + "; ".join(excluded))
    if row_bad:
        memo.append("행 대조 불일치: " + "; ".join(row_bad))
    if subtot_bad:
        memo.append("소계 불일치: " + "; ".join(subtot_bad))

    used = {k for u in out_units for k in u["인원"]}
    data = {
        "id": UNIV_ID,
        "이름": UNIV_NAME,
        "출처쪽": pages,
        "전형": [{"key": k, "시기": t[0], "유형": t[1], "전형명": t[2], "군": t[3]}
                 for k, t in JEONHYEONG.items() if k in used],
        "모집단위": out_units,
        "메모": memo,
    }
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(out_units)} rows -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
