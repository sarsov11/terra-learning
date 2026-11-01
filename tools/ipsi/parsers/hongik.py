"""홍익대학교 2028 시행계획 → norm JSON.

표: '2028학년도 모집인원' — 서울캠퍼스 PDF 8쪽(인쇄 7쪽), 세종캠퍼스 PDF 35쪽(인쇄 34쪽).
pdfplumber 선(線) 격자의 칸(cell)으로 행·열 경계를 잡고, 글자는 중심 좌표로 칸에 넣는다.
정원외 열은 표 각주('정원외 모집전형과 인원은 회색 음영부분 참조')대로 회색 음영 칸으로 판별한다.

사용: python3 -I tools/ipsi/parsers/hongik.py <pdf> <out.json>
"""
import json
import re
import sys
from collections import Counter

import pdfplumber

ID = "hongik"
NAME = "홍익대학교"

# 캠퍼스별: (PDF 쪽, 캠퍼스 이름, key 접두어, 머리글 경로 → 전형 정의)
# 머리글 경로 = 위에서 아래로 쌓인 머리글 칸 글자(공백 제거). 정의 None = 정원내가 아니거나 숫자가 없는 열(아래에서 따로 확인).
SEOUL = {
    ("수시모집", "학생부위주", "학교장추천자"): ("수시_교과_학교장추천자", "수시", "학생부교과", "학교장추천자전형", None),
    ("수시모집", "학생부위주", "학교생활우수자(서류형)"): ("수시_종합_학교생활우수자서류형", "수시", "학생부종합", "학교생활우수자(서류형)전형", None),
    ("수시모집", "학생부위주", "학교생활우수자(면접형)"): ("수시_종합_학교생활우수자면접형", "수시", "학생부종합", "학교생활우수자(면접형)전형", None),
    ("수시모집", "학생부위주", "고른기회I"): ("수시_종합_고른기회1", "수시", "학생부종합", "고른기회Ⅰ전형", None),
    ("수시모집", "학생부위주", "고른기회II"): ("수시_종합_고른기회2", "수시", "학생부종합", "고른기회Ⅱ전형", None),
    ("수시모집", "학생부위주", "기초생활수급자·차상위계층"): "정원외",
    ("수시모집", "학생부위주", "농어촌학생"): "정원외",
    ("수시모집", "학생부위주", "특성화고등을졸업한재직자", "정원내"): ("수시_교과_특성화고졸재직자", "수시", "학생부교과", "특성화고등을졸업한재직자전형(정원내)", None),
    ("수시모집", "학생부위주", "특성화고등을졸업한재직자", "정원외"): "정원외",
    ("수시모집", "논술위주", "논술"): ("수시_논술", "수시", "논술", "논술전형", None),
    ("수시모집", "실기/실적위주", "미술우수자"): ("수시_실기_미술우수자", "수시", "실기/실적", "미술우수자전형", None),
    ("수시모집", "실기/실적위주", "공연예술우수자"): ("수시_실기_공연예술우수자", "수시", "실기/실적", "공연예술우수자전형", None),
    ("정시모집", "수능위주", "수능우수자", "㉯군"): ("정시_수능_나", "정시", "수능", "수능우수자전형", "나"),
    ("정시모집", "수능위주", "수능우수자", "㉰군"): ("정시_수능_다", "정시", "수능", "수능우수자전형", "다"),
    ("정시모집", "수능위주", "기초생활수급자·차상위계층"): "미정열",
    ("정시모집", "수능위주", "농어촌학생"): "정원외",
    ("정시모집", "수능위주", "특성화고졸업(예정)자"): "정원외",
    ("정시모집", "실기/실적위주", "공연예술우수자㉯군"): ("정시_실기_나", "정시", "실기/실적", "공연예술우수자전형", "나"),
    ("정시모집", "학생부위주", "특성화고등을졸업한재직자㉰군"): "정원외",
}
SEJONG = {
    ("수시모집", "학생부위주", "교과우수자"): ("세종_수시_교과_교과우수자", "수시", "학생부교과", "교과우수자전형(세종)", None),
    ("수시모집", "학생부위주", "학교생활우수자(서류형)"): ("세종_수시_종합_학교생활우수자서류형", "수시", "학생부종합", "학교생활우수자(서류형)전형(세종)", None),
    ("수시모집", "학생부위주", "고른기회I"): ("세종_수시_종합_고른기회1", "수시", "학생부종합", "고른기회Ⅰ전형(세종)", None),
    ("수시모집", "학생부위주", "고른기회II"): ("세종_수시_종합_고른기회2", "수시", "학생부종합", "고른기회Ⅱ전형(세종)", None),
    ("수시모집", "학생부위주", "기초생활수급자·차상위계층"): "정원외",
    ("수시모집", "학생부위주", "농어촌학생"): "정원외",
    ("수시모집", "논술위주", "논술"): ("세종_수시_논술", "수시", "논술", "논술전형(세종)", None),
    ("수시모집", "실기/실적위주", "미술우수자"): ("세종_수시_실기_미술우수자", "수시", "실기/실적", "미술우수자전형(세종)", None),
    ("수시모집", "실기/실적위주", "체육우수자"): ("세종_수시_실기_체육우수자", "수시", "실기/실적", "체육우수자전형(세종)", None),
    ("정시모집", "수능위주", "수능우수자", "㉮군"): ("세종_정시_수능_가", "정시", "수능", "수능우수자전형(세종)", "가"),
    ("정시모집", "수능위주", "수능우수자", "㉰군"): ("세종_정시_수능_다", "정시", "수능", "수능우수자전형(세종)", "다"),
    ("정시모집", "수능위주", "기초생활수급자·차상위계층"): "미정열",
    ("정시모집", "수능위주", "농어촌학생"): "정원외",
    ("정시모집", "수능위주", "특성화고졸업(예정)자"): "정원외",
    ("정시모집", "수능위주", "체육우수자㉰군"): "미정열",
}
CAMPUSES = [(8, "서울캠퍼스", SEOUL), (35, "세종캠퍼스", SEJONG)]
GRAY = "0.851"  # 회색 음영(정원외) 채움색


def norm_txt(s):
    return re.sub(r"[\s　]+", "", s or "").replace("・", "·")


def text_in(page, box, sep=None):
    """칸 안 글자를 줄 단위로 이어 붙인다.

    글자는 왼쪽 끝(x0+1.5)과 세로 중심으로 칸에 넣는다(계열 칸 글자가 오른쪽 칸으로 삐져나오는 경우가 있어서).
    sep=None: 칸 안 줄바꿈은 붙여 쓰되, 앞 줄이 '학부'/'대학'으로 끝나고 다음 줄이 '('로 시작하지 않으면 공백.
    """
    x0, top, x1, bot = box
    cs = [c for c in page.chars
          if x0 <= c["x0"] + 1.5 <= x1 and top <= (c["top"] + c["bottom"]) / 2 <= bot]
    lines = []
    for c in sorted(cs, key=lambda c: (c["top"], c["x0"])):
        for ln in lines:
            if abs(ln[0] - c["top"]) <= 2:
                ln[1].append(c)
                break
        else:
            lines.append([c["top"], [c]])
    parts = ["".join(ch["text"] for ch in sorted(ln[1], key=lambda c: c["x0"])).strip() for ln in lines]
    parts = [p for p in parts if p]
    if sep is not None:
        return sep.join(parts)
    out = ""
    for p in parts:
        if out and re.search(r"(학부|대학)$", out) and not p.startswith("("):
            out += " " + p
        else:
            out += p
    return out


def num(s):
    t = norm_txt(s)
    if t in ("", "-"):
        return 0
    if re.fullmatch(r"\d{1,3}(,\d{3})+|\d+", t):
        return int(t.replace(",", ""))
    return None


def overlap(a0, a1, b0, b1):
    return min(a1, b1) - max(a0, b0)


def parse_campus(page, campus, spec):
    tables = page.find_tables()
    t = max(tables, key=lambda t: len(t.cells))
    cells = t.cells
    # 데이터 시작: '캠퍼스자율전공' 칸의 윗변
    first = [c for c in cells if "캠퍼스자율전공" in text_in(page, c)]
    data_top = min(c[1] for c in first)
    total_cell = [c for c in cells if norm_txt(text_in(page, c)) == f"{campus}계"]
    assert len(total_cell) == 1, total_cell
    total_cell = total_cell[0]
    data_bot = total_cell[1]

    # 머리글 칸 → 잎 열
    head = [c for c in cells if c[3] <= data_top + 1.5]
    leaves = sorted([c for c in head if abs(c[3] - data_top) < 1.5], key=lambda c: c[0])
    cols = []
    for lf in leaves:
        xc = (lf[0] + lf[2]) / 2
        path = tuple(norm_txt(text_in(page, c)).replace("*", "") for c in sorted(
            [c for c in head if c[0] <= xc <= c[2]], key=lambda c: c[1]))
        cols.append((lf[0], lf[2], path))
    assert [p for _, _, p in cols[:4]] == [("계열",), ("대학",), ("모집단위",), ("모집인원(정원내)",)], cols[:4]
    x_gye, x_dae, x_unit, x_cap = cols[0], cols[1], cols[2], cols[3]

    # 회색 음영 열 판별(데이터 영역)
    gray_cols = set()
    for i, (a, b, path) in enumerate(cols[4:], start=4):
        n = sum(1 for r in page.rects
                if str(r.get("non_stroking_color")) == GRAY and r["top"] >= data_top - 1 and r["bottom"] <= data_bot + 1
                and overlap(r["x0"], r["x1"], a, b) > (b - a) * 0.6)
        if n:
            gray_cols.add(i)

    defs = {}
    problems = []
    for i, (a, b, path) in enumerate(cols[4:], start=4):
        if path not in spec:
            raise SystemExit(f"{campus}: 알 수 없는 머리글 {path}")
        d = spec[path]
        is_gray = i in gray_cols
        if d == "정원외":
            if not is_gray:
                problems.append(f"{'/'.join(path)}: 정원외로 보았으나 음영 아님")
        elif is_gray:
            problems.append(f"{'/'.join(path)}: 음영(정원외)인데 정원내로 정의됨")
        defs[i] = d

    # 행 경계: 모집인원 열의 칸
    cap_cells = sorted([c for c in cells if abs(c[0] - x_cap[0]) < 1.5 and abs(c[2] - x_cap[1]) < 1.5
                        and c[1] >= data_top - 1 and c[3] <= data_bot + 1], key=lambda c: c[1])
    bands = [(c[1], c[3]) for c in cap_cells]

    def merged_text(xa, xb, top, bot):
        """열 범위 [xa,xb]에서 이 행과 겹치는 칸들의 글자(왼→오)."""
        cs = [c for c in cells if overlap(c[0], c[2], xa, xb) > 1 and overlap(c[1], c[3], top, bot) > 1
              and c[1] >= data_top - 1]
        return [(c, text_in(page, c)) for c in sorted(cs, key=lambda c: c[0])]

    # 계열 칸: 표 왼쪽 세로선이 없어 칸이 잡히지 않음 → 그 열을 가로지르는 가로선으로 띠를 나눈다.
    xm = (x_gye[0] + x_gye[1]) / 2
    ys = sorted({round(e["top"], 1) for e in page.edges
                 if e["orientation"] == "h" and e["x0"] <= xm <= e["x1"] and data_top - 2 <= e["top"] <= data_bot + 2})
    ys2 = []
    for y in ys:
        if not ys2 or y - ys2[-1] > 2:
            ys2.append(y)
    gye_bands = [(a, b, norm_txt(text_in(page, (x_gye[0], a, x_gye[1], b)))) for a, b in zip(ys2, ys2[1:])]

    rows = []
    merged_notes = []
    for top, bot in bands:
        # 계열
        ym = (top + bot) / 2
        gb = [g for g in gye_bands if g[0] <= ym <= g[1]]
        gye = gb[0][2] if gb else ""
        # 대학 / 모집단위
        dae_cells = merged_text(x_dae[0], x_dae[1], top, bot)
        dae = None
        unit_parts = []
        span_dae_unit = False
        if dae_cells:
            c, tx = dae_cells[0]
            if c[2] > x_unit[0] + 5:  # 대학 칸이 모집단위 칸까지 합쳐짐
                span_dae_unit = True
            dae = norm_txt(tx).replace("・", "·") or None
        for c, tx in merged_text(x_unit[0], x_unit[1], top, bot):
            if c[0] < x_unit[0] - 1:
                continue
            unit_parts.append(tx.replace("・", "·"))
        if span_dae_unit:
            unit = dae
        else:
            unit = " ".join(p for p in unit_parts if p)
        cap = num(text_in(page, (x_cap[0], top, x_cap[1], bot)))
        vals = {}
        bad = []
        for i, d in defs.items():
            a, b, path = cols[i]
            # 이 칸이 여러 행에 걸친 병합 칸인지
            cc = [c for c in cells if overlap(c[0], c[2], a, b) > 1 and overlap(c[1], c[3], top, bot) > 1]
            multi = [c for c in cc if (c[3] - c[1]) > (bot - top) + 2]
            raw = text_in(page, (a, top, b, bot))
            if d == "정원외":
                continue
            if multi:
                mt = norm_txt(text_in(page, multi[0]))
                if d == "미정열" and mt == "미정":
                    merged_notes.append((unit, "/".join(path), mt))
                    continue
                bad.append(f"{'/'.join(path)} 병합칸 '{mt}'")
                continue
            if d == "미정열":
                rt = norm_txt(raw)
                if rt == "미정":
                    merged_notes.append((unit, "/".join(path), rt))
                elif num(raw) != 0:
                    bad.append(f"{'/'.join(path)} '{rt}'(숫자 없어야 할 열)")
                continue
            v = num(raw)
            if v is None:
                bad.append(f"{'/'.join(path)} '{norm_txt(raw)}'")
                continue
            if v == 0:
                continue
            vals[d[0]] = v
        rows.append({"gye": gye, "dae": dae, "unit": unit, "cap": cap, "vals": vals, "bad": bad})

    # 총계 행
    tot = {}
    for i, d in defs.items():
        a, b, path = cols[i]
        tot[i] = norm_txt(text_in(page, (a, total_cell[1], b, total_cell[3])))
    tot_cap = num(text_in(page, (x_cap[0], total_cell[1], x_cap[1], total_cell[3])))
    return cols, defs, gray_cols, rows, tot, tot_cap, problems, merged_notes


def main(pdf_path, out_path):
    out_rows, jlist, memo = [], [], []
    seen = set()
    tot_memo = []
    with pdfplumber.open(pdf_path) as pdf:
        for pno, campus, spec in CAMPUSES:
            page = pdf.pages[pno - 1]
            cols, defs, gray, rows, tot, tot_cap, problems, merged = parse_campus(page, campus, spec)
            if problems:
                memo.append(f"{campus} 열 판별 경고: " + "; ".join(problems))
            for i, d in defs.items():
                if isinstance(d, tuple) and d[0] not in seen:
                    seen.add(d[0])
                    jlist.append({"key": d[0], "시기": d[1], "유형": d[2], "전형명": d[3], "군": d[4]})
            skipped = []
            for r in rows:
                if r["bad"]:
                    skipped.append(f"{r['unit']}({', '.join(r['bad'])})")
                    continue
                if r["cap"] is None:
                    skipped.append(f"{r['unit']}(모집인원 칸 읽기 실패)")
                    continue
                s = sum(r["vals"].values())
                dae = f"{campus} · {r['dae']}" if r["dae"] else campus
                out_rows.append({
                    "단과대학": dae,
                    "모집단위": r["unit"],
                    "계열": r["gye"] or None,
                    "인원": r["vals"],
                    "계": r["cap"],
                    "쪽": pno,
                    "검증": "합계일치" if s == r["cap"] else "합계불일치",
                })
            if skipped:
                memo.append(f"{campus} 읽지 못해 뺀 행: " + "; ".join(skipped))
            # 병합 칸 메모
            mg = Counter((p, t) for _, p, t in merged)
            for (p, t), n in mg.items():
                memo.append(f"{campus}: '{p}' 열(음영 없음)은 {n}행에 걸쳐 '{t}'(수시 미충원 이월)만 적혀 있어 숫자 없음 → 넣지 않음. 표의 '모집인원(정원내)'·계 행 합에도 들어 있지 않음")
            # 총계 대조
            camp_rows = [r for r in out_rows if r["단과대학"].startswith(campus)]
            ssum = {"수시": 0, "정시": 0}
            tsum = {"수시": 0, "정시": 0}
            col_bad = []
            for i, d in defs.items():
                if not isinstance(d, tuple):
                    continue
                mine = sum(r["인원"].get(d[0], 0) for r in camp_rows)
                pv = num(tot[i])
                if pv is None:
                    col_bad.append(f"{d[0]}: PDF 계 '{tot[i]}'")
                    continue
                ssum[d[1]] += mine
                tsum[d[1]] += pv
                if mine != pv:
                    col_bad.append(f"{d[0]} {mine}≠{pv}")
            capsum = sum(r["계"] for r in camp_rows)
            tot_memo.append(f"총계 대조({campus} 계 행): 수시 {ssum['수시']}={tsum['수시']}, 정시 {ssum['정시']}={tsum['정시']}, "
                            f"전체 {ssum['수시'] + ssum['정시']}={tot_cap} (모집인원(정원내) 칸 합 {capsum})"
                            + ("; 전형별 열 불일치: " + "; ".join(col_bad) if col_bad else "; 전형별 열 합 모두 일치"))

    memo.insert(0, "정원내만 수록: 회색 음영(정원외) 열 — 서울 수시 기초생활수급자·차상위계층·농어촌학생·특성화고등을졸업한재직자(정원외 186), "
                   "정시 농어촌학생·특성화고졸업(예정)자·특성화고등을졸업한재직자㉰군(15); 세종 수시 기초생활수급자·차상위계층·농어촌학생, "
                   "정시 농어촌학생·특성화고졸업(예정)자 — 는 넣지 않음")
    memo.insert(1, "고른기회Ⅰ·Ⅱ(수시)는 음영 없는 정원내 열이고 '모집인원(정원내)' 합계에 포함 → 수록")
    memo.insert(2, "서울 특성화고등을졸업한재직자전형은 전형기간 자율화(수시/정시㉰군) 전형이나 표가 수시 학생부위주 아래 정원내 4/정원외 186으로 나눠 적음 → 정원내 4만 수시_교과_특성화고졸재직자로 수록(PDF 29쪽 학생부위주(교과))")
    memo.insert(3, "계 = 표의 '모집인원(정원내)' 칸(행별 정원내 합계)")
    memo.insert(4, "단과대학 = '<캠퍼스> · <대학>'. 대학 칸이 비어 있는 행(캠퍼스자율전공, 경제학부, 디자인·예술경영학부 등)은 캠퍼스만 적음. "
                   "세종 '조형대학'은 대학 칸과 모집단위 칸이 합쳐져 있어 둘 다 '조형대학'")
    memo.insert(5, "계열: 표의 계열 칸 그대로(자연/인문/미술/공연예술/체육). 계열 칸이 빈 행(캠퍼스자율전공 등)은 null")
    memo.insert(6, "유형: 표 머리글의 '~위주' 구분 그대로(수시 미술우수자·공연예술우수자·체육우수자 = 실기/실적위주, 정시 공연예술우수자㉯군 = 실기/실적위주, 정시 수능우수자 = 수능위주)")
    memo.insert(7, "세종캠퍼스 전형 key는 '세종_' 접두어로 서울과 구분")
    memo.extend(tot_memo)
    out = {"id": ID, "이름": NAME, "출처쪽": [p for p, _, _ in CAMPUSES], "전형": jlist, "모집단위": out_rows, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(ID, len(out_rows), "rows", dict(Counter(r["검증"] for r in out_rows)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
