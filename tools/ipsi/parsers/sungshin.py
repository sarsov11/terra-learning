#!/usr/bin/env python3
"""성신여자대학교 2028 시행계획 파서.

대상 표: '전형별 모집인원 ■ 정원내 선발인원' (PDF 4쪽, 인쇄 쪽번호 2).
- 표 오른쪽 끝 '다군 전공선발' 열과 맨 왼쪽 '단과대학' 열은 데이터 행에 바깥 세로선이 없어
  셀로 잡히지 않으므로, 다군 값은 그 열 x 범위 안 단어로, 단과대학은 왼쪽 가로선 묶음 안 단어로 읽는다.
- '자유전공'/'첨단분야전공'이 적힌 세로 병합 칸은 인원이 아니라 '창의융합학부에서 무전공 선발' 표시라 0으로 본다.
- 창의융합학부 두 행의 학생부교과 무전공선발 칸은 지역균형 I·II 두 열이 합쳐진 한 칸(54, 72)이라
  표 아래 각주(*** 지역균형 I/II 모집단위별 인원)로 나누고, 나눈 값의 합 == 그 칸 값 인지 확인한다.
사용법: python3 -I tools/ipsi/parsers/sungshin.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "sungshin"
UNIV_NAME = "성신여자대학교"

JEONHYEONG = [
    {"key": "수시_종합_자기주도인재", "시기": "수시", "유형": "학생부종합", "전형명": "자기주도인재전형", "군": None},
    {"key": "수시_종합_기회균형1", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형Ⅰ전형", "군": None},
    {"key": "수시_교과_지역균형1", "시기": "수시", "유형": "학생부교과", "전형명": "지역균형Ⅰ전형", "군": None},
    {"key": "수시_교과_지역균형2", "시기": "수시", "유형": "학생부교과", "전형명": "지역균형Ⅱ전형", "군": None},
    {"key": "수시_논술_논술우수자", "시기": "수시", "유형": "논술", "전형명": "논술우수자전형", "군": None},
    {"key": "수시_실기_일반학생", "시기": "수시", "유형": "실기/실적", "전형명": "일반학생전형", "군": None},
    {"key": "정시_수능_일반학생_가", "시기": "정시", "유형": "수능", "전형명": "일반학생전형", "군": "가"},
    {"key": "정시_수능_일반학생_나", "시기": "정시", "유형": "수능", "전형명": "일반학생전형", "군": "나"},
    {"key": "정시_수능_일반학생_다", "시기": "정시", "유형": "수능", "전형명": "일반학생전형", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]

# 합계 행 셀 순서(왼→오) = 논리 열. (이름, 인원 key 또는 None, 머리글 경로에 들어 있어야 할 글자)
LOGICAL = [
    ("모집정원", None, ["모집정원"]),
    ("자기주도인재", "수시_종합_자기주도인재", ["수시모집", "학생부종합", "자기주도인재"]),
    ("기회균형Ⅰ", "수시_종합_기회균형1", ["수시모집", "학생부종합", "기회균형Ⅰ"]),
    ("지역균형전공I", "수시_교과_지역균형1", ["수시모집", "학생부교과", "지역균형I,II", "전공선발", "I"]),
    ("무전공I_a", "수시_교과_지역균형1", ["수시모집", "학생부교과", "지역균형I,II", "무전공선발***", "I"]),
    ("무전공II_a", "수시_교과_지역균형2", ["수시모집", "학생부교과", "지역균형I,II", "무전공선발***", "II"]),
    ("무전공I_b", "수시_교과_지역균형1", ["수시모집", "학생부교과", "지역균형I,II", "무전공선발***", "I"]),
    ("무전공II_b", "수시_교과_지역균형2", ["수시모집", "학생부교과", "지역균형I,II", "무전공선발***", "II"]),
    ("논술우수자", "수시_논술_논술우수자", ["수시모집", "논술", "논술우수자"]),
    ("실기일반학생", "수시_실기_일반학생", ["수시모집", "실기/실적", "일반학생"]),
    ("가전공", "정시_수능_일반학생_가", ["정시모집", "수능", "일반학생", "가군", "전공선발"]),
    ("가무전공", "정시_수능_일반학생_가", ["정시모집", "수능", "일반학생", "가군", "무전공선발"]),
    ("나전공", "정시_수능_일반학생_나", ["정시모집", "수능", "일반학생", "나군", "전공선발"]),
    ("나무전공", "정시_수능_일반학생_나", ["정시모집", "수능", "일반학생", "나군", "무전공선발"]),
    ("다전공", "정시_수능_일반학생_다", ["정시모집", "수능", "일반학생", "다군", "전공선발"]),
]
LABELS = {"자유전공", "첨단분야전공"}  # 병합 칸 표시(인원 아님)


def norm(s):
    return re.sub(r"\s+", "", s or "")


def num(s):
    """'-'/빈칸 → 0, '4**' → 4(각주 표시 제거). 숫자가 아니면 None."""
    t = norm(s).replace(",", "").rstrip("*")
    if t in ("", "-"):
        return 0
    if re.fullmatch(r"\d+", t):
        return int(t)
    return None


def unit_name(s):
    return norm(s).replace("*", "")


def covering(cells, x, y):
    for c in cells:
        if c[0] - 0.5 <= x <= c[2] + 0.5 and c[1] - 0.5 <= y <= c[3] + 0.5:
            return c
    return None


def words_in(words, x0, x1, top, bottom):
    sel = [w for w in words
           if x0 <= (w["x0"] + w["x1"]) / 2 <= x1 and top <= (w["top"] + w["bottom"]) / 2 <= bottom]
    return sorted(sel, key=lambda w: (round(w["top"]), w["x0"]))


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        target = None
        for pno, page in enumerate(pdf.pages, start=1):
            txt = page.extract_text() or ""
            if "정원내 선발인원" not in txt:
                continue
            for t in page.find_tables():
                rows = t.extract()
                if rows and norm(rows[0][0]) == "단과대학" and norm(rows[0][2]) == "모집단위(부)":
                    target = (pno, page, t, rows, txt)
                    break
            if target:
                break
        if not target:
            raise SystemExit("정원내 선발인원 표를 찾지 못함")
        pno, page, table, rows, page_txt = target
        cells = table.cells
        words = page.extract_words()

        chars = page.chars

        def text_of(c):
            """중심점이 칸 안에 드는 글자만(옆 칸 글자가 조금 걸쳐도 섞이지 않게)."""
            sel = [ch for ch in chars
                   if c[0] <= (ch["x0"] + ch["x1"]) / 2 <= c[2] and c[1] <= (ch["top"] + ch["bottom"]) / 2 <= c[3]]
            sel.sort(key=lambda ch: (round(ch["top"]), ch["x0"]))
            return norm("".join(ch["text"] for ch in sel))

        # 합계 행 → 논리 열 x 범위
        ti = next(i for i, r in enumerate(rows) if norm(r[0]) == "합계")
        total_cells = [c for c in table.rows[ti].cells if c is not None]
        if len(total_cells) != len(LOGICAL) + 1:
            raise SystemExit(f"합계 행 칸 수 다름: {len(total_cells)}")
        col_x = [(c[0], c[2]) for c in total_cells[1:]]
        hdr_bottom = None
        # 머리글 경로 확인(열 중심 x 아래로 머리글 셀 글자 모으기)
        name_cell_hdr = next(c for c in cells if text_of(c) == "모집단위(부)")
        hdr_bottom = name_cell_hdr[3]
        for (lname, _key, expect), (x0, x1) in zip(LOGICAL, col_x):
            cx = (x0 + x1) / 2
            hcells = sorted([c for c in cells if c[3] <= hdr_bottom + 0.5 and c[0] - 0.5 <= cx <= c[2] + 0.5],
                            key=lambda c: c[1])
            path = [text_of(c) for c in hcells if text_of(c)]
            # 다군 열은 머리글 아래쪽 세로선이 있어 셀이 잡힘(데이터 행만 빠짐)
            if path != expect and not (lname == "모집정원" and path == ["모집정원"]):
                raise SystemExit(f"머리글 다름 {lname}: {path} != {expect}")
        name_x = (name_cell_hdr[0], name_cell_hdr[2])
        dangwa_cell = next(c for c in cells if text_of(c) == "단과대학")
        gyeyeol_cell = next(c for c in cells if text_of(c) == "계열")

        # 단과대학 묶음: 단과대학 칸을 가로지르는 가로선
        dx0, dx1 = dangwa_cell[0], dangwa_cell[2]
        hlines = sorted({round(e["top"], 1) for e in page.edges
                         if e["orientation"] == "h" and e["x0"] <= dx0 + 2 and e["x1"] >= dx1 - 2
                         and e["top"] >= hdr_bottom - 0.5})

        # 각주: 지역균형 I/II 창의융합학부 무전공 인원
        foot = {}
        for lv, roman in (("I", "1"), ("II", "2")):
            m = re.search(r"지역균형\s*" + lv + r"\s*:\s*([^\n]+)", page_txt)
            if not m:
                raise SystemExit(f"각주(지역균형 {lv}) 못 찾음")
            for nm, n in re.findall(r"(창의융합학부\([^)]+\))\s*(\d+)명", m.group(1)):
                foot[(norm(nm), roman)] = int(n)

        units, excluded, merged_notes, star_notes = [], [], [], []
        dagun_word_rows = 0
        for ri in range(len(rows)):
            if ri == ti:
                continue
            trow = table.rows[ri]
            ncell = next((c for c in trow.cells if c and abs(c[0] - name_x[0]) < 1 and abs(c[2] - name_x[1]) < 1), None)
            if ncell is None or ncell[1] < hdr_bottom - 0.5:
                continue
            top, bottom = ncell[1], ncell[3]
            cy = (top + bottom) / 2
            raw_name = " ".join(w["text"] for w in words_in(words, ncell[0], ncell[2], top, bottom))
            name = unit_name(raw_name)
            if not name:
                raise SystemExit(f"이름 없는 행 y={top:.0f}")
            if "*" in raw_name:
                star_notes.append(name)
            # 계열
            gc = covering([c for c in cells if abs(c[0] - gyeyeol_cell[0]) < 1 and abs(c[2] - gyeyeol_cell[2]) < 1],
                          (gyeyeol_cell[0] + gyeyeol_cell[2]) / 2, cy)
            gyeyeol = text_of(gc) if gc else None
            # 단과대학
            gt = max([h for h in hlines if h <= cy], default=None)
            gb = min([h for h in hlines if h >= cy], default=None)
            dangwa = "".join(w["text"] for w in words_in(words, dx0, dx1, gt, gb)) if gt and gb else ""
            # 숫자 칸
            vals, bad, merged = {}, [], {}
            for (lname, key, _), (x0, x1) in zip(LOGICAL, col_x):
                cx = (x0 + x1) / 2
                c = covering(cells, cx, cy)
                if c is None:
                    if lname != "다전공":
                        bad.append(lname)
                        continue
                    t = "".join(w["text"] for w in words_in(words, x0, x1, top, bottom))
                    dagun_word_rows += 1
                    v = num(t)
                    if v is None:
                        bad.append(f"{lname}:{t}")
                        continue
                    vals[lname] = v
                    continue
                t = text_of(c)
                if t in LABELS:
                    vals[lname] = 0
                    continue
                v = num(t)
                if v is None:
                    bad.append(f"{lname}:{t}")
                    continue
                multi_row = c[1] < top - 1 or c[3] > bottom + 1
                multi_col = c[0] < x0 - 1 or c[2] > x1 + 1
                if v and multi_row:
                    bad.append(f"{lname}:여러 행 병합 숫자 {t}")
                    continue
                if v and multi_col:
                    merged[(c[0], c[2])] = (v, t)
                    vals[lname] = None  # 아래에서 각주로 나눔
                    continue
                vals[lname] = v
            # 지역균형 무전공 I+II 병합 칸
            for (mx0, mx1), (v, t) in merged.items():
                covered = [ln for (ln, _k, _e), (x0, x1) in zip(LOGICAL, col_x) if mx0 - 1 <= x0 and x1 <= mx1 + 1]
                if len(covered) != 2 or sorted(c.split("_")[0] for c in covered) != ["무전공I", "무전공II"]:
                    bad.append(f"예상 밖 병합 칸 {covered}={t}")
                    continue
                i1 = foot.get((name, "1"))
                i2 = foot.get((name, "2"))
                if i1 is None or i2 is None or i1 + i2 != v:
                    bad.append(f"무전공 병합 칸 {v} ≠ 각주 I {i1} + II {i2}")
                    continue
                for ln in covered:
                    vals[ln] = i1 if ln.startswith("무전공I_") else i2
                merged_notes.append(f"{name}: 무전공선발 병합 칸 {v} = 각주 지역균형 I {i1} + II {i2}")
            if bad:
                excluded.append(f"{name}: 읽을 수 없는 칸 {bad}")
                continue
            gye = vals.pop("모집정원")
            inwon = {}
            for (lname, key, _e) in LOGICAL[1:]:
                if vals.get(lname):
                    inwon[key] = inwon.get(key, 0) + vals[lname]
            units.append({
                "단과대학": dangwa or None,
                "모집단위": name,
                "계열": gyeyeol or None,
                "인원": inwon,
                "계": gye,
                "쪽": pno,
                "검증": "합계일치" if sum(inwon.values()) == gye else "합계불일치",
                "_vals": vals,
            })

        # 주요 변경사항 쪽의 정원내 모집인원(2027 → 2028, 두 번째 값이 2028)
        summary = []
        for p2 in pdf.pages:
            t2 = p2.extract_text() or ""
            if "주요 변경사항" in t2 and "정원내" in t2:
                summary = [int(b.replace(",", "")) for _a, b in
                           re.findall(r"모집\s+([\d,]+)명\([\d.]+%\)\s+([\d,]+)명\([\d.]+%\)", t2)]
                break

        # 합계 행
        tot = {}
        for (lname, _k, _e), c in zip(LOGICAL, total_cells[1:]):
            v = num(text_of(c))
            if v is None:
                raise SystemExit(f"합계 행 읽기 실패: {lname}")
            tot[lname] = v

    col_bad = [ln for (ln, _k, _e) in LOGICAL[1:] if tot[ln] != sum(u["_vals"].get(ln, 0) for u in units)]
    gye_sum = sum(u["계"] for u in units)
    for u in units:
        del u["_vals"]
    s_pdf = sum(tot[ln] for (ln, k, _e) in LOGICAL[1:] if k in SUSI_KEYS)
    j_pdf = sum(tot[ln] for (ln, k, _e) in LOGICAL[1:] if k in JEONGSI_KEYS)
    s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
    j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
    summary_note = ""
    if len(summary) == 2:
        ok = "같음" if summary == [s_me, j_me] else "다름"
        summary_note = f"; 주요 변경사항 쪽 2028 정원내 모집인원 수시 {summary[0]}·정시 {summary[1]}과 {ok}"
    memo = [
        "정원내만 수록: 수시 학생부종합 특성화고 등을 졸업한 재직자·특수교육대상자, 정시 수능 농·어촌학생·특성화고교출신자·"
        "기회균형Ⅱ(모두 정원외)와 재외국민과 외국인 전형은 넣지 않음",
        "수시 학생부종합 기회균형Ⅰ전형은 '정원내 선발인원' 표에 있음 → 수록",
        f"계 = '정원내 선발인원' 표(p{pno})의 '모집정원' 칸",
        "학생부교과 지역균형 I·II: 학과 행은 '전공선발 I' 열(지역균형 II는 전공선발 없음, 각주 ***), 창의융합학부 두 행은 "
        "'무전공선발' 칸. 학과 행의 무전공 칸과 정시 무전공 칸에 세로로 병합된 '자유전공'/'첨단분야전공' 글자는 인원이 아니라 "
        "창의융합학부에서 선발한다는 표시라 0으로 봄",
        "창의융합학부 두 행의 무전공선발 칸은 지역균형 I·II 두 열이 한 칸으로 합쳐져 있어 표 아래 각주 숫자로 나눔: "
        + "; ".join(merged_notes),
        "정시 열은 모두 PDF 머리글 '수능 > 일반학생' 아래(예체능 실기고사 반영 단위 포함) → 유형=수능. 같은 군의 전공선발·"
        "무전공선발 열은 한 행에 하나만 값이 있어 군별 key 하나로 합침",
        "기회균형Ⅰ 칸의 '**'(특성화고교출신자 지원 가능 표시), 모집단위 이름의 '*'(교직과정 설치 표시)는 지우고 숫자·이름만 적음"
        + (f" — '*' 표시 단위: {', '.join(star_notes)}" if star_notes else ""),
        f"다군 열은 데이터 행 오른쪽 세로선이 없어 셀 대신 그 열 x 범위 안 글자로 읽음({dagun_word_rows}행)",
        "단과대학: 표의 단과대학 칸 글자 그대로(왼쪽 세로선이 없어 단과대학 칸을 가로지르는 가로선 묶음 안 글자로 읽음). "
        "계열: 표의 계열 칸 그대로(인문/예체능/자연/자연(첨단)/자연(간호)/인문(사범)/전체)",
        "이름의 공백은 지움(예: '수리통계데이터 사이언스학부' → '수리통계데이터사이언스학부', 3쪽 정원외 표 표기와 같음)",
        "전형별 열 합 대조(합계 행 15칸): " + ("모두 일치" if not col_bad else "불일치 " + ", ".join(col_bad)),
        f"총계 대조: 수시 {s_pdf}={s_me}, 정시 {j_pdf}={j_me}, 전체 {tot['모집정원']}={s_me + j_me} "
        f"(PDF 합계 행; 모집정원 칸 합 {gye_sum})" + summary_note,
    ] + excluded

    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": [pno], "전형": JEONHYEONG, "모집단위": units, "메모": memo}
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
        raise SystemExit("usage: sungshin.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
