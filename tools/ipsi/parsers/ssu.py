#!/usr/bin/env python3
"""숭실대학교 2028 시행계획 파서.

대상 표: 'Ⅰ-3. 모집단위별 모집인원' 가. 수시모집(PDF 8쪽), 나. 정시모집(PDF 9쪽).
열 뜻은 머리글 칸 경로(모집인원|학생부종합|SSU미래인재|면접형|내 …)로 정한다.
머리글에 '(외)' 또는 '외'로 적힌 열은 정원외라 넣지 않는다.
숫자는 열 x 범위·행 y 범위 안 글자로 읽는다(정시 소계 열은 데이터 행 오른쪽 세로선이 없어 셀로 잡히지 않음).
사용법: python3 -I tools/ipsi/parsers/ssu.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "ssu"
UNIV_NAME = "숭실대학교"

# 머리글 경로 → ("in", key) / ("out", 이름) / ("sum", 이름)
SUSI_COLS = {
    "모집인원|학생부종합|SSU미래인재|면접형|내": ("in", "수시_종합_SSU미래인재면접형"),
    "모집인원|학생부종합|SSU미래인재|면접형|외": ("out", "SSU미래인재(면접형) 정원외"),
    "모집인원|학생부종합|SSU미래인재|서류형": ("in", "수시_종합_SSU미래인재서류형"),
    "모집인원|학생부종합|기회균형": ("in", "수시_종합_기회균형"),
    "모집인원|학생부종합|AI우수자": ("in", "수시_종합_AI우수자"),
    "모집인원|학생부종합|특수교육(외)": ("out", "특수교육대상자(외)"),
    "모집인원|교과우수자(학교장추천)": ("in", "수시_교과_교과우수자"),
    "모집인원|논술우수자": ("in", "수시_논술_논술우수자"),
    "모집인원|예체능우수인재|축구": ("in", "수시_실기_예체능우수인재_축구"),
    "모집인원|예체능우수인재|체육": ("in", "수시_실기_예체능우수인재_체육"),
    "모집인원|예체능우수인재|연출": ("in", "수시_실기_예체능우수인재_연출"),
    "모집인원|예체능우수인재|연기": ("in", "수시_실기_예체능우수인재_연기"),
    "모집인원|재직자(외)": ("out", "특성화고등을졸업한재직자(외)"),
    "모집인원|수시소계(내외)": ("sum", "수시소계"),
}
JEONGSI_COLS = {
    "모집인원|가군|일반": ("in", "정시_수능_일반_가"),
    "모집인원|가군|특성화(외)": ("out", "가 특성화(외)"),
    "모집인원|가군|농어촌(외)": ("out", "가 농어촌(외)"),
    "모집인원|가군|기초생활(외)": ("out", "가 기초생활(외)"),
    "모집인원|나군|일반": ("in", "정시_수능_일반_나"),
    "모집인원|나군|특성화(외)": ("out", "나 특성화(외)"),
    "모집인원|나군|농어촌(외)": ("out", "나 농어촌(외)"),
    "모집인원|다군|일반|내": ("in", "정시_수능_일반_다"),
    "모집인원|다군|일반|외": ("out", "다 일반 정원외"),
    "모집인원|다군|실기/실적": ("in", "정시_실기_일반_다"),
    "모집인원|다군|특성화(외)": ("out", "다 특성화(외)"),
    "모집인원|다군|농어촌(외)": ("out", "다 농어촌(외)"),
    "모집인원|다군|기초생활(외)": ("out", "다 기초생활(외)"),
    "모집인원|정시소계(내외)": ("sum", "정시소계"),
}
JEONHYEONG = [
    {"key": "수시_종합_SSU미래인재면접형", "시기": "수시", "유형": "학생부종합", "전형명": "SSU미래인재전형(면접형)", "군": None},
    {"key": "수시_종합_SSU미래인재서류형", "시기": "수시", "유형": "학생부종합", "전형명": "SSU미래인재전형(서류형)", "군": None},
    {"key": "수시_종합_기회균형", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형전형", "군": None},
    {"key": "수시_종합_AI우수자", "시기": "수시", "유형": "학생부종합", "전형명": "AI우수자전형", "군": None},
    {"key": "수시_교과_교과우수자", "시기": "수시", "유형": "학생부교과", "전형명": "교과우수자전형(학교장추천)", "군": None},
    {"key": "수시_논술_논술우수자", "시기": "수시", "유형": "논술", "전형명": "논술우수자전형", "군": None},
    {"key": "수시_실기_예체능우수인재_축구", "시기": "수시", "유형": "실기/실적", "전형명": "예체능우수인재전형(축구)", "군": None},
    {"key": "수시_실기_예체능우수인재_체육", "시기": "수시", "유형": "실기/실적", "전형명": "예체능우수인재전형(체육)", "군": None},
    {"key": "수시_실기_예체능우수인재_연출", "시기": "수시", "유형": "실기/실적", "전형명": "예체능우수인재전형(연출)", "군": None},
    {"key": "수시_실기_예체능우수인재_연기", "시기": "수시", "유형": "실기/실적", "전형명": "예체능우수인재전형(연기)", "군": None},
    {"key": "정시_수능_일반_가", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "가"},
    {"key": "정시_수능_일반_나", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "나"},
    {"key": "정시_수능_일반_다", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "다"},
    {"key": "정시_실기_일반_다", "시기": "정시", "유형": "실기/실적", "전형명": "실기/실적(일반전형)", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]


def norm(s):
    return re.sub(r"\s+", "", (s or "").replace("　", " "))


def text_in(chars, box):
    sel = [c for c in chars
           if box[0] <= (c["x0"] + c["x1"]) / 2 <= box[2] and box[1] <= (c["top"] + c["bottom"]) / 2 <= box[3]]
    sel.sort(key=lambda c: (round(c["top"]), c["x0"]))
    return norm("".join(c["text"] for c in sel))


def num(t):
    t = t.replace(",", "")
    if t in ("", "-"):
        return 0
    if re.fullmatch(r"\d+", t):
        return int(t)
    raise ValueError(t)


def read_table(page, table, colmap, label):
    chars = page.chars
    cells = table.cells
    tx0 = table.bbox[0]
    hdr_name = next(c for c in cells if text_in(chars, c) == "모집단위")
    hdr_gye = next(c for c in cells if text_in(chars, c) == "계열")
    hdr_bottom = hdr_name[3]
    name_x0, name_x1 = hdr_name[0], hdr_name[2]
    hcells = [c for c in cells if c[3] <= hdr_bottom + 0.5 and c[0] >= name_x1 - 1]
    # 맨 아래 머리글 칸(바로 아래가 데이터) = 열
    leaf = [c for c in hcells if abs(c[3] - hdr_bottom) < 1]
    leaf.sort(key=lambda c: c[0])
    cols = []
    for c in leaf:
        cx = (c[0] + c[2]) / 2
        path = "|".join(text_in(chars, h) for h in sorted([h for h in hcells if h[0] - 0.5 <= cx <= h[2] + 0.5],
                                                          key=lambda h: h[1]) if text_in(chars, h))
        if path not in colmap:
            raise SystemExit(f"{label}: 알 수 없는 머리글 {path}")
        cols.append((c[0], c[2], path, colmap[path]))
    if sorted(p for *_x, p, _m in cols) != sorted(colmap):
        raise SystemExit(f"{label}: 머리글 수 다름")

    # 계열 묶음(표 전체 폭 가로선)
    hl = sorted({round(e["top"], 1) for e in page.edges
                 if e["orientation"] == "h" and e["x0"] <= hdr_gye[0] + 3 and e["x1"] >= table.bbox[2] - 8
                 and e["top"] >= hdr_bottom - 1})
    first_num_x = cols[0][0]
    rows_out, total = [], None
    for r in table.rows:
        anchor = next((c for c in r.cells if c and abs(c[0] - first_num_x) < 1), None)
        if anchor is None or anchor[1] < hdr_bottom - 0.5:
            continue
        top, bottom = anchor[1], anchor[3]
        cy = (top + bottom) / 2
        name = text_in(chars, (name_x0, top, name_x1, bottom))
        merged = False
        if not name:
            name = text_in(chars, (tx0, top, name_x1, bottom))
            merged = True
        vals = {}
        for x0, x1, path, _m in cols:
            t = text_in(chars, (x0, top, x1, bottom))
            try:
                vals[path] = num(t)
            except ValueError:
                raise SystemExit(f"{label}: {name} {path} 숫자 아님 {t!r}")
        raw = {path: text_in(chars, (x0, top, x1, bottom)) for x0, x1, path, _m in cols}
        if name == "총계":
            total = vals
            continue
        gyeyeol = None
        if not merged:
            gt = max([h for h in hl if h <= cy], default=None)
            gb = min([h for h in hl if h >= cy], default=None)
            if gt is not None and gb is not None:
                gyeyeol = text_in(chars, (hdr_gye[0], gt, hdr_gye[2], gb)) or None
        rows_out.append({"name": name, "vals": vals, "raw": raw, "계열": gyeyeol})
    if total is None:
        raise SystemExit(f"{label}: 총계 행 못 찾음")
    return rows_out, total, cols


def find(pdf, title, first_hdr):
    for pno, page in enumerate(pdf.pages, start=1):
        if title not in norm(page.extract_text() or ""):
            continue
        for t in page.find_tables():
            rows = t.extract()
            if rows and norm(rows[0][0]) == "계열" and norm(rows[0][1]) == "모집단위" and first_hdr in norm(" ".join(
                    c or "" for c in rows[1])):
                return pno, page, t
    raise SystemExit(f"표 못 찾음: {title}")


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        sp, spage, stab = find(pdf, "가.수시모집(특성화고등을졸업한재직자전형포함)", "학생부종합")
        jp, jpage, jtab = find(pdf, "나.정시모집", "가군")
        s_rows, s_tot, s_cols = read_table(spage, stab, SUSI_COLS, "수시")
        j_rows, j_tot, j_cols = read_table(jpage, jtab, JEONGSI_COLS, "정시")
        p4 = {}
        for page in pdf.pages:
            t = page.extract_text() or ""
            if "전형유형별 모집인원" in t and "소 계(A)" in t:
                for lab, a, b in re.findall(r"소\s*계\((A|B)\)\s*([\d,]+)\s+([\d,]+)", t):
                    p4[lab] = int(b.replace(",", ""))
                break

    s_names = [r["name"] for r in s_rows]
    j_names = [r["name"] for r in j_rows]
    if s_names != j_names:
        raise SystemExit(f"수시/정시 모집단위 다름: {set(s_names) ^ set(j_names)}")

    units, excluded, zero_cells = [], [], []
    sub_ok = {"수시소계": 0, "정시소계": 0}
    sub_bad = []
    for sr, jr in zip(s_rows, j_rows):
        name = sr["name"]
        inwon = {}
        for rows_, colmap in ((sr, SUSI_COLS), (jr, JEONGSI_COLS)):
            for path, (kind, key) in colmap.items():
                if kind == "in" and rows_["vals"][path]:
                    inwon[key] = rows_["vals"][path]
                if kind == "in" and rows_["raw"][path] == "0":
                    zero_cells.append(f"{name} {path.split('|', 1)[1]}")
            ssum = sum(v for p, v in rows_["vals"].items() if colmap[p][0] in ("in", "out"))
            sname = next(m[1] for m in colmap.values() if m[0] == "sum")
            spath = next(p for p, m in colmap.items() if m[0] == "sum")
            if ssum == rows_["vals"][spath]:
                sub_ok[sname] += 1
            else:
                sub_bad.append(f"{name} {sname} {rows_['vals'][spath]}≠{ssum}")
        if sr["계열"] != jr["계열"]:
            raise SystemExit(f"계열 다름: {name} {sr['계열']} / {jr['계열']}")
        if not inwon:
            outs = [f"{colmap[p][1]} {v}" for rows_, colmap in ((sr, SUSI_COLS), (jr, JEONGSI_COLS))
                    for p, v in rows_["vals"].items() if colmap[p][0] == "out" and v]
            excluded.append(f"{name}(정원외만: {', '.join(outs)})")
            continue
        units.append({
            "단과대학": None,
            "모집단위": name,
            "계열": sr["계열"],
            "인원": inwon,
            "계": None,
            "쪽": sp,
            "검증": "합계칸없음",
        })

    col_bad = []
    for tot, colmap in ((s_tot, SUSI_COLS), (j_tot, JEONGSI_COLS)):
        for path, (kind, key) in colmap.items():
            if kind == "in" and tot[path] != sum(u["인원"].get(key, 0) for u in units):
                col_bad.append(key)
    s_pdf = sum(s_tot[p] for p, m in SUSI_COLS.items() if m[0] == "in")
    j_pdf = sum(j_tot[p] for p, m in JEONGSI_COLS.items() if m[0] == "in")
    s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
    j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
    s_out = sum(s_tot[p] for p, m in SUSI_COLS.items() if m[0] == "out")
    j_out = sum(j_tot[p] for p, m in JEONGSI_COLS.items() if m[0] == "out")
    s_sub = s_tot["모집인원|수시소계(내외)"]
    j_sub = j_tot["모집인원|정시소계(내외)"]
    jaejik = s_tot["모집인원|재직자(외)"]

    memo = [
        "정원내만 수록: 머리글에 '(외)'/'외'로 적힌 열(수시 SSU미래인재(면접형) 외, 특수교육(외), 재직자(외); 정시 가·나·다군 "
        "특성화(외)·농어촌(외)·기초생활(외), 다군 일반 외)과 재외국민·순수외국인 특별전형(표에 없음)은 넣지 않음",
        "수시 학생부종합 기회균형전형과 정시 다군 실기/실적 열은 머리글에 정원내/외 표시가 없음(표가 정원외 열마다 '(외)'를 "
        "적음) → 정원내로 수록. PDF 본문에 기회균형전형의 정원내/외를 따로 밝힌 문장은 찾지 못함",
        "계: 행 합계 칸 '수시 소계(내외)'·'정시 소계(내외)'는 정원외를 포함해 정원내 계가 아님 → null(검증 '합계칸없음')",
        f"보조 대조(행의 소계(내외) 칸 = 그 표 정원내+정원외 칸 합): 수시 {sub_ok['수시소계']}/{len(s_rows)}행, "
        f"정시 {sub_ok['정시소계']}/{len(j_rows)}행 일치" + (f" (불일치: {'; '.join(sub_bad)})" if sub_bad else ""),
        "정원내 인원이 없어 뺀 행: " + "; ".join(excluded),
        "정원내 칸에 '0'이 적힌 곳은 0으로 봄(인원에서 뺌): " + (", ".join(zero_cells) or "없음"),
        "정시 열: 가·나·다군 '일반'은 수능(일반전형), 다군 '실기/실적'은 실기/실적(일반전형)(예술창작학부(문예창작전공)·스포츠학부) "
        "— 목차 'Ⅲ-1 수능(일반전형) 가,나,다군', 'Ⅲ-2 실기/실적(일반전형) 다군'",
        "수시 예체능우수인재 축구·체육·연출·연기는 표에서 열이 나뉘어 있어 key를 나눔",
        "계열: 표의 계열 칸 그대로(인문/경상/자연). 자유전공학부(인문)·(자연)은 계열 칸과 모집단위 칸이 합쳐져 null. "
        "단과대학: 표에 칸이 없어 null",
        "전형별 열 합 대조(수시·정시 총계 행): " + ("모두 일치" if not col_bad else "불일치 " + ", ".join(col_bad)),
        f"총계 대조: 수시 {s_pdf}={s_me}, 정시 {j_pdf}={j_me}, 전체 {s_pdf + j_pdf}={s_me + j_me} "
        f"(각 총계 행의 정원내 칸 합. 수시 소계(내외) {s_sub} = 정원내 {s_pdf} + 정원외 {s_out}: "
        f"{'일치' if s_sub == s_pdf + s_out else '불일치'}; 정시 소계(내외) {j_sub} = 정원내 {j_pdf} + 정원외 {j_out}: "
        f"{'일치' if j_sub == j_pdf + j_out else '불일치'}"
        + (f"; p4 전형유형별 모집인원 소계(A) {p4.get('A')} = 수시 소계(내외) − 재직자 {s_sub - jaejik}: "
           f"{'일치' if p4.get('A') == s_sub - jaejik else '불일치'}, 소계(B) {p4.get('B')} = 정시 소계(내외) {j_sub}: "
           f"{'일치' if p4.get('B') == j_sub else '불일치'}" if p4 else "") + ")",
    ]

    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": [sp, jp], "전형": JEONHYEONG, "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(units)}행 → {out_path}")
    for m in memo:
        print(" -", m)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: ssu.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
