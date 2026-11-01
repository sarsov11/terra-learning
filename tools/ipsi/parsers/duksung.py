#!/usr/bin/env python3
"""덕성여자대학교 2028 시행계획 파서.

대상 표(둘 다 같은 행 구성):
  - 4쪽: 수시모집 모집인원(정원내/정원외/전형기간 자율화)
  - 16쪽: 정시모집 모집인원(가·나·다군)
표에는 전공이 한 행씩 나열되지만, 입학정원·모집인원 칸은 여러 전공 행에 걸쳐 세로 병합돼 있다
(예: 글로벌융합대학 21개 전공 → 칸 하나). 숫자가 붙은 단위가 실제 모집단위이므로
'입학정원 칸 하나 = 모집단위 하나'로 읽는다. 칸 경계는 pdfplumber 표 칸(cell)으로 잡는다.
사용법: python3 -I tools/ipsi/parsers/duksung.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "duksung"
UNIV_NAME = "덕성여자대학교"

JEONHYEONG = [
    {"key": "수시_교과_고교추천", "시기": "수시", "유형": "학생부교과", "전형명": "고교추천전형", "군": None},
    {"key": "수시_종합_덕성인재1", "시기": "수시", "유형": "학생부종합", "전형명": "덕성인재전형Ⅰ(서류형)", "군": None},
    {"key": "수시_종합_덕성인재2", "시기": "수시", "유형": "학생부종합", "전형명": "덕성인재전형Ⅱ(서류 및 면접형)", "군": None},
    {"key": "수시_종합_기회균형1_농어촌", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형전형Ⅰ_농어촌학생", "군": None},
    {"key": "수시_종합_기회균형2_사회통합", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형전형Ⅱ_사회통합", "군": None},
    {"key": "수시_논술", "시기": "수시", "유형": "논술", "전형명": "논술전형", "군": None},
    {"key": "수시_실기_미술실기", "시기": "수시", "유형": "실기/실적", "전형명": "미술실기전형", "군": None},
    {"key": "정시_수능_수능우수1_가", "시기": "정시", "유형": "수능", "전형명": "수능우수전형Ⅰ", "군": "가"},
    {"key": "정시_수능_수능우수1_나", "시기": "정시", "유형": "수능", "전형명": "수능우수전형Ⅰ", "군": "나"},
    {"key": "정시_실기_미술실기_나", "시기": "정시", "유형": "실기/실적", "전형명": "미술실기전형", "군": "나"},
    {"key": "정시_실기_체육실기_나", "시기": "정시", "유형": "실기/실적", "전형명": "체육실기전형", "군": "나"},
    {"key": "정시_수능_수능우수2_다", "시기": "정시", "유형": "수능", "전형명": "수능우수전형Ⅱ", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]

# 머리글 경로(위→아래 칸 글자, 공백 제거) → 역할
SUSI_COLS = {
    ("입학정원",): "입학정원",
    ("정원내", "학생부위주(교과)", "고교추천"): "수시_교과_고교추천",
    ("정원내", "학생부위주(종합)", "덕성인재Ⅰ"): "수시_종합_덕성인재1",
    ("정원내", "학생부위주(종합)", "덕성인재Ⅱ"): "수시_종합_덕성인재2",
    ("정원내", "학생부위주(종합)", "기회균형Ⅰ", "농어촌학생"): "수시_종합_기회균형1_농어촌",
    ("정원내", "학생부위주(종합)", "기회균형Ⅱ", "사회통합"): "수시_종합_기회균형2_사회통합",
    ("정원내", "논술위주", "논술"): "수시_논술",
    ("정원내", "실기위주", "미술실기"): "수시_실기_미술실기",
    ("정원내", "소계"): "정원내소계",
    ("정원외", "학생부위주(종합)", "기회균형Ⅰ", "특성화고교"): "정원외",
    ("정원외", "학생부위주(종합)", "기회균형Ⅰ", "기초생활수급자등"): "정원외",
    ("정원외", "학생부위주(종합)", "기회균형Ⅰ", "장애인등대상자"): "정원외",
    ("정원외", "소계"): "정원외",
    ("수시모집합계",): "수시합계",
    ("전형기간자율화특별전형", "기회균형Ⅰ", "특성화고등을졸업한재직자"): "정원외",
}
JEONGSI_COLS = {
    ("입학정원",): "입학정원",
    ("가군", "수능위주", "수능우수Ⅰ"): "정시_수능_수능우수1_가",
    ("가군", "소계"): "가소계",
    ("나군", "수능위주", "수능우수Ⅰ"): "정시_수능_수능우수1_나",
    ("나군", "실기위주", "미술실기"): "정시_실기_미술실기_나",
    ("나군", "실기위주", "체육실기"): "정시_실기_체육실기_나",
    ("나군", "소계"): "나소계",
    ("다군", "수능위주", "수능우수Ⅱ"): "정시_수능_수능우수2_다",
    ("다군", "소계"): "다소계",
    ("정시모집합계",): "정시합계",
}


def norm(s):
    return re.sub(r"\s+", "", s or "")


def to_int(s):
    s = norm(s).replace(",", "")
    if s in ("", "-"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {s!r}")


def cell_text(chars, box):
    x0, top, x1, bot = box
    cs = [c for c in chars
          if x0 <= (c["x0"] + c["x1"]) / 2 <= x1 and top <= (c["top"] + c["bottom"]) / 2 <= bot]
    lines = []
    for c in sorted(cs, key=lambda c: (c["top"], c["x0"])):
        if lines and abs(lines[-1][0] - c["top"]) <= 2:
            lines[-1][1].append(c)
        else:
            lines.append([c["top"], [c]])
    return "".join("".join(c["text"] for c in sorted(lc, key=lambda c: c["x0"])) for _, lc in lines)


def college_name(s):
    s = norm(s)
    # 'Art & Design대학'은 칸 안에서 줄이 끊겨 있어(Art & / Desi / gn / 대학) 본문(17쪽) 표기로 띄어 씀
    return "Art & Design대학" if s == "Art&Design대학" else s


def read_table(pdf, colspec, title_word):
    """colspec 머리글을 가진 표를 찾아 그룹(입학정원 칸) 목록과 합계 행을 돌려준다."""
    for pno, page in enumerate(pdf.pages, start=1):
        if "입학" not in (page.extract_text() or ""):
            continue
        for t in page.find_tables():
            chars = page.chars
            cells = t.cells
            jg = [c for c in cells if norm(cell_text(chars, c)) == "전공"]
            dg = [c for c in cells if norm(cell_text(chars, c)) == "대학"]
            if len(jg) != 1 or len(dg) != 1:
                continue
            jh, dh = jg[0], dg[0]
            data_top = jh[3]
            leaves = sorted([c for c in cells if abs(c[3] - data_top) < 0.6 and c[0] >= jh[2] - 0.5],
                            key=lambda c: c[0])
            cols, paths = [], []
            for lf in leaves:
                xm = (lf[0] + lf[2]) / 2
                path = tuple(norm(cell_text(chars, c)) for c in sorted(cells, key=lambda c: c[1])
                             if c[0] <= xm <= c[2] and c[3] <= data_top + 0.6)
                paths.append(path)
                if path in colspec:
                    cols.append((lf[0], lf[2], colspec[path]))
            if not any(p[0] == title_word for p in paths):
                continue  # 다른 표
            unknown = [p for p in paths if p not in colspec]
            if unknown:
                raise SystemExit(f"{pno}쪽 모르는 머리글 {unknown}")
            if sorted(r for *_, r in cols) != sorted(colspec.values()):
                raise SystemExit(f"{pno}쪽 머리글 열 구성 다름: {[r for *_, r in cols]}")

            def covering(x0, x1, ym):
                xm = (x0 + x1) / 2
                cs = [c for c in cells if c[0] <= xm <= c[2] and c[1] - 0.5 <= ym <= c[3] + 0.5
                      and c[1] >= data_top - 0.5]
                if len(cs) != 1:
                    return None
                return cs[0]

            # 전공 열의 행(칸) 목록
            jrows = sorted([c for c in cells if abs(c[0] - jh[0]) < 1 and abs(c[2] - jh[2]) < 1 and c[1] >= data_top - 0.5],
                           key=lambda c: c[1])
            ip = [c for c in cols if c[2] == "입학정원"][0]
            groups, order = {}, []
            total = None
            for jr in jrows:
                ym = (jr[1] + jr[3]) / 2
                jname = norm(cell_text(chars, jr))
                ipc = covering(ip[0], ip[1], ym)
                if ipc is None:
                    raise SystemExit(f"{pno}쪽 {jname}: 입학정원 칸 없음")
                key = tuple(round(v, 1) for v in ipc)
                if key not in groups:
                    groups[key] = {"전공": [], "box": ipc, "y": ym}
                    order.append(key)
                groups[key]["전공"].append(jname)
            # 합계 행: 대학 칸 왼끝에서 전공 칸까지 덮는 '합계' 칸
            tot_cells = [c for c in cells if norm(cell_text(chars, c)) == "합계" and c[1] >= data_top - 0.5]
            if len(tot_cells) != 1:
                raise SystemExit(f"{pno}쪽 합계 행 {len(tot_cells)}개")
            tc = tot_cells[0]
            ty = (tc[1] + tc[3]) / 2
            total = {}
            for x0, x1, role in cols:
                c = covering(x0, x1, ty)
                total[role] = total.get(role, []) + [to_int(cell_text(chars, c)) if c else None]
            # 대학 칸: 데이터 영역에 세로선이 없어 칸(cell)으로 안 잡힘 → 대학 열 가운데를 지나는 가로선으로 띠를 나눔
            dxm = (dh[0] + dh[2]) / 2
            hy = []
            for v in sorted(e["top"] for e in page.edges if e["orientation"] == "h"
                            and e["x0"] - 0.5 <= dxm <= e["x1"] + 0.5 and data_top - 1 <= e["top"] <= tc[1] + 1):
                if not hy or v - hy[-1] > 1.0:
                    hy.append(v)

            def college_at(ym):
                for a, b in zip(hy, hy[1:]):
                    if a <= ym <= b:
                        # 4쪽은 '글로벌' 글자가 표 왼쪽 선 밖으로 1~2pt 삐져나와 있어 왼쪽을 5pt 넓혀 읽음
                        return college_name(cell_text(chars, (dh[0] - 5, a, dh[2], b)))
                return ""

            out = []
            for key in order:
                g = groups[key]
                box = g["box"]
                vals = {}
                for x0, x1, role in cols:
                    c = covering(x0, x1, g["y"])
                    if c is None:
                        vals.setdefault(role, []).append(None)
                        continue
                    if role not in ("정원외",) and (c[1] < box[1] - 1 or c[3] > box[3] + 1 or c[1] > box[1] + 1 or c[3] < box[3] - 1):
                        raise SystemExit(f"{pno}쪽 {g['전공'][0]}: {role} 칸 범위가 입학정원 칸과 다름")
                    txt = cell_text(chars, c)
                    vals.setdefault(role, []).append(txt if role == "정원외" else to_int(txt))
                out.append({"대학": college_at((box[1] + box[3]) / 2), "전공": g["전공"],
                            "box": box, "vals": vals})
            return pno, out, total
    raise SystemExit(f"'{title_word}' 표를 찾지 못함")


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        s_pno, s_groups, s_total = read_table(pdf, SUSI_COLS, "정원내")
        j_pno, j_groups, j_total = read_table(pdf, JEONGSI_COLS, "가군")

    if [g["전공"] for g in s_groups] != [g["전공"] for g in j_groups]:
        raise SystemExit("수시/정시 표의 모집단위 구성이 다름")

    units, aux_bad, ip_diff, members = [], [], [], []
    aux_ok = 0
    for sg, jg in zip(s_groups, j_groups):
        sv, jv = sg["vals"], jg["vals"]
        if sv["입학정원"] != jv["입학정원"] or sg["대학"] != jg["대학"]:
            raise SystemExit(f"{sg['전공'][0]}: 수시/정시 표 입학정원·대학 다름")
        inwon = {}
        for k in SUSI_KEYS:
            if sv[k][0]:
                inwon[k] = sv[k][0]
        for k in JEONGSI_KEYS:
            if jv[k][0]:
                inwon[k] = jv[k][0]
        jlist_names = sg["전공"]
        if len(jlist_names) == 1:
            name = jlist_names[0]
        else:
            name = sg["대학"]
            members.append(f"{name} = {', '.join(jlist_names)} ({len(jlist_names)}개 전공·학부 행)")
        # 보조 대조: 수시 정원내 소계 칸, 정시 군별 소계·정시모집합계 칸
        s_sum = sum(inwon.get(k, 0) for k in SUSI_KEYS)
        g_sum = {g: sum(v for k, v in inwon.items() if k.startswith("정시_") and k.endswith("_" + g)) for g in "가나다"}
        ok = (s_sum == sv["정원내소계"][0] and g_sum["가"] == jv["가소계"][0] and g_sum["나"] == jv["나소계"][0]
              and g_sum["다"] == jv["다소계"][0] and sum(g_sum.values()) == jv["정시합계"][0])
        if ok:
            aux_ok += 1
        else:
            aux_bad.append(name)
        ipw = sv["입학정원"][0]
        if ipw != sum(inwon.values()):
            ip_diff.append(f"{name}(입학정원 {ipw}, 정원내 모집인원 합 {sum(inwon.values())})")
        units.append({
            "단과대학": sg["대학"] or None,
            "모집단위": name,
            "계열": None,
            "인원": inwon,
            "계": None,
            "쪽": s_pno,
            "검증": "합계칸없음",
        })

    used = {k for u in units for k in u["인원"]}
    jlist = [j for j in JEONHYEONG if j["key"] in used]
    memo = [
        f"출처: p{s_pno} 수시모집 모집인원 표, p{j_pno} 정시모집 모집인원 표(같은 행 구성). 쪽 = 수시 표 쪽",
        "정원내만 수록: 수시 정원외(기회균형전형Ⅰ_특성화고교·기초생활수급자 등·장애인 등 대상자), 전형기간 자율화 "
        "기회균형전형Ⅰ_특성화고 등을 졸업한 재직자(p6 '정원외'), 재외국민과 외국인(p21)은 넣지 않음",
        "기회균형전형Ⅰ_농어촌학생·기회균형전형Ⅱ_사회통합은 표의 '정원내' 열 → 수록",
        "모집단위: 표는 전공을 한 행씩 나열하지만 입학정원·모집인원 칸이 여러 행에 걸쳐 병합돼 있어, 병합 칸 하나를 모집단위 하나로 봄. "
        "여러 행을 묶는 단위는 이름을 표의 대학 칸 글자로 적음(p6·p10·p21은 글로벌융합대학 묶음을 '글로벌융합대학(인문사회)'로 부름)",
        "계: 표에 행별 정원내 전체 합계 칸 없음(수시 '정원내 소계', 정시 '정시모집 합계'는 각 모집시기 합계) → 계=null(합계칸없음)",
        "계열: 표에 계열 칸 없음 → null",
        "정시 미술실기·체육실기는 p16 머리글 '실기위주' → 유형 실기/실적",
    ]
    memo.extend("묶음 모집단위: " + m for m in members)
    memo.append(f"보조 대조(수시 '정원내 소계' 칸, 정시 가·나·다군 소계·'정시모집 합계' 칸 = 전형 칸 합): {aux_ok}행 일치"
                + (", 불일치 " + ", ".join(aux_bad) if aux_bad else ""))
    if ip_diff:
        memo.append("참고 대조(입학정원 칸 vs 정원내 모집인원 합): " + str(len(units) - len(ip_diff)) + "행 같음, 다름: "
                    + "; ".join(ip_diff) + " — 이 PDF에 이월 인원 설명은 없음")
    s_pdf = s_total["정원내소계"][0]
    j_pdf = j_total["정시합계"][0]
    s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
    j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
    memo.append(f"총계 대조: 수시 {s_pdf}={s_me}, 정시 {j_pdf}={j_me}, 전체 {s_pdf + j_pdf}={s_me + j_me} "
                f"(p{s_pno} 합계 행 '정원내 소계', p{j_pno} 합계 행 '정시모집 합계'; 입학정원 합계 {s_total['입학정원'][0]})")
    bad = []
    for k in SUSI_KEYS:
        if s_total[k][0] != sum(u["인원"].get(k, 0) for u in units):
            bad.append(k)
    for k in JEONGSI_KEYS:
        if j_total[k][0] != sum(u["인원"].get(k, 0) for u in units):
            bad.append(k)
    memo.append("전형별 열 합 대조(합계 행): " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)))

    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": [s_pno, j_pno], "전형": jlist, "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(units)}행 → {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: duksung.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
