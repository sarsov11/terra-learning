#!/usr/bin/env python3
"""경북대학교 2028학년도 대학입학전형시행계획 -> 모집단위별 정원내 모집인원.

사용: python3 -I tools/ipsi/parsers/knu.py <pdf> <out.json>

표 구조(원문 'Ⅲ 모집단위 및 모집인원'):
  - 1. 수시모집 표(4~8쪽): 대학(계열) | 모집단위 | 계 | 정원내 15칸 | 정원외 7칸
  - 2. 정시모집 표(9~12쪽): 대학(계열) | 모집단위 | 가군(일반·지역인재·지역의사선발) | 나군(일반) | 총모집인원(수시+정시)
칸 경계는 표의 세로선, 행 경계는 가로선(점선 포함)에서 읽는다. 머리칸 글자와 묶음(정원내/정원외, 가군/나군)
범위를 대조해 칸 배치가 예상과 다르면 멈춘다.
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "knu"
UNIV_NAME = "경북대학교"


# ---------------------------------------------------------------- geometry helpers
def _groups(items, key, tol):
    items = sorted(items, key=key)
    out = []
    for it in items:
        if out and key(it) - key(out[-1][-1]) <= tol:
            out[-1].append(it)
        else:
            out.append([it])
    return out


def hbounds(page, xa, xb, cover=0.8, tol=1.2, gap=1.0):
    """y of horizontal rules covering >= cover of [xa, xb] (dashed rules bridged)."""
    segs = [(e["top"], e["x0"], e["x1"]) for e in page.edges if e["orientation"] == "h"]
    ys = []
    for g in _groups(segs, lambda s: s[0], tol):
        ivs = sorted((max(x0, xa), min(x1, xb)) for _, x0, x1 in g if x1 > xa and x0 < xb)
        tot, cur = 0.0, None
        for a, b in ivs:
            if b <= a:
                continue
            if cur is None:
                cur = [a, b]
            elif a <= cur[1] + gap:
                cur[1] = max(cur[1], b)
            else:
                tot += cur[1] - cur[0]
                cur = [a, b]
        if cur:
            tot += cur[1] - cur[0]
        if tot >= cover * (xb - xa):
            ys.append(sum(s[0] for s in g) / len(g))
    return ys


def vbounds(page, y, tol=1.2):
    xs = [e["x0"] for e in page.edges if e["orientation"] == "v" and e["top"] - 0.5 <= y <= e["bottom"] + 0.5]
    return [sum(g) / len(g) for g in _groups(xs, lambda v: v, tol)]


def chars_in(chars, x0, x1, y0, y1):
    out = []
    for c in chars:
        if not c["text"].strip():
            continue
        xc = (c["x0"] + c["x1"]) / 2
        yc = (c["top"] + c["bottom"]) / 2
        if x0 <= xc < x1 and y0 <= yc < y1:
            out.append(c)
    return out


def lines_of(chars):
    """Group chars into visual lines (top-to-bottom), each line left-to-right."""
    cs = sorted(chars, key=lambda c: (c["top"], c["x0"]))
    lines = []
    for c in cs:
        if lines and abs(c["top"] - lines[-1][0]) <= max(1.5, c["size"] * 0.4):
            lines[-1][1].append(c)
        else:
            lines.append([c["top"], [c]])
    out = []
    for _, lc in lines:
        lc.sort(key=lambda c: c["x0"])
        s, prev = "", None
        for c in lc:
            if prev is not None and c["x0"] - prev["x1"] > 0.3 * c["size"]:
                s += " "
            s += c["text"]
            prev = c
        out.append(s)
    return out


def nospace(s):
    return re.sub(r"\s+", "", s)


def num(lines):
    s = nospace("".join(lines)).replace(",", "")
    if s in ("", "-"):
        return 0
    if s.isdigit():
        return int(s)
    return None  # 숫자가 아님


def main_table(page):
    tabs = page.find_tables()
    if not tabs:
        raise SystemExit(f"p{page.page_number}: 표 없음")
    return max(tabs, key=lambda t: (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1])).bbox


def header_layout(page, label_re, bbox):
    """Return (cols, hdr_top, hdr_bottom) using the header label of the name column."""
    ms = [m for m in page.search(label_re, regex=True) if bbox[1] - 1 <= m["top"] <= bbox[3]]
    if not ms:
        raise SystemExit(f"p{page.page_number}: 머리칸 '{label_re}' 없음")
    m = ms[0]
    xc, yc = (m["x0"] + m["x1"]) / 2, (m["top"] + m["bottom"]) / 2
    vb = vbounds(page, yc)
    xa = max(x for x in vb if x <= xc)
    xb = min(x for x in vb if x >= xc)
    hb = hbounds(page, xa, xb)
    hdr_bottom = min(y for y in hb if y > m["bottom"])
    hdr_top = max(y for y in hb if y < m["top"])
    xs = [x for x in vbounds(page, hdr_bottom - 2) if bbox[0] - 2 <= x <= bbox[2] + 2]
    cols = list(zip(xs[:-1], xs[1:]))
    return cols, hdr_top, hdr_bottom


def col_index(cols, x, side):
    for i, c in enumerate(cols):
        if abs(c[side] - x) < 1.5:
            return i
    return None


def group_spans(page, pattern, cols, y0, y1):
    spans = []
    for m in page.search(pattern, regex=True):
        if not (y0 <= m["top"] <= y1):
            continue
        xc, yc = (m["x0"] + m["x1"]) / 2, (m["top"] + m["bottom"]) / 2
        vb = vbounds(page, yc)
        left = max(x for x in vb if x <= xc)
        right = min(x for x in vb if x >= xc)
        spans.append((col_index(cols, left, 0), col_index(cols, right, 1)))
    return spans


def check_headers(page, cols, expected, y0, y1, where):
    if len(cols) != len(expected):
        raise SystemExit(f"{where}: 칸 수 {len(cols)} != 예상 {len(expected)}")
    for i, (c, exp) in enumerate(zip(cols, expected)):
        t = nospace("".join(lines_of(chars_in(page.chars, c[0], c[1], y0, y1))))
        if exp not in t:
            raise SystemExit(f"{where}: {i}번째 칸 머리글 '{t}'에 '{exp}' 없음")


def strip_note(name):
    """'건축학부(건축학전공)4)' -> '건축학부(건축학전공)': 짝 없는 닫는 괄호로 끝나는 주석 번호 제거."""
    m = re.search(r"\d+\)$", name)
    if m and name.count(")") > name.count("("):
        return name[:m.start()]
    return name


# ---------------------------------------------------------------- 전형 정의
JEONHYEONG = {
    "수시_교과_교과우수자": ("수시", "학생부교과", "교과우수자전형", None),
    "수시_교과_지역인재": ("수시", "학생부교과", "지역인재전형", None),
    "수시_교과_지역인재기초생활": ("수시", "학생부교과", "지역인재 기초생활수급자등대상자전형", None),
    "수시_교과_사회통합": ("수시", "학생부교과", "사회통합전형", None),
    "수시_종합_일반학생": ("수시", "학생부종합", "일반학생전형", None),
    "수시_종합_지역인재": ("수시", "학생부종합", "지역인재전형", None),
    "수시_종합_지역의사선발": ("수시", "학생부종합", "지역의사선발전형", None),
    "수시_종합_지역인재학교장추천": ("수시", "학생부종합", "지역인재 학교장추천전형", None),
    "수시_종합_사회배려자": ("수시", "학생부종합", "사회배려자전형", None),
    "수시_종합_AI특별": ("수시", "학생부종합", "AI특별전형", None),
    "수시_종합_고졸재직자": ("수시", "학생부종합", "고졸재직자전형", None),
    "수시_종합_영농창업인재": ("수시", "학생부종합", "영농창업인재전형", None),
    "수시_논술_AAT": ("수시", "논술", "논술(AAT)전형", None),
    "수시_실기_예체능": ("수시", "실기/실적", "실기/실적(예체능)전형", None),
    "수시_특기자_체육": ("수시", "실기/실적", "특기자(체육)전형", None),
    "정시_수능_가_일반학생": ("정시", "수능", "일반학생전형", "가"),
    "정시_수능_가_지역인재": ("정시", "수능", "지역인재전형", "가"),
    "정시_수능_나_일반학생": ("정시", "수능", "일반학생전형", "나"),
}

# 수시 표 칸: (머리글에 반드시 들어있어야 할 글자, 역할)
SUSI_COLS = [
    ("대학", "college"), ("모집단위", "name"), ("계", "total"),
    ("교과우수자", "수시_교과_교과우수자"),
    ("지역인재", "수시_교과_지역인재"),
    ("기초생활", "수시_교과_지역인재기초생활"),
    ("사회통합", "수시_교과_사회통합"),
    ("일반학생", "수시_종합_일반학생"),
    ("지역인재", "수시_종합_지역인재"),
    ("지역의사선발", "수시_종합_지역의사선발"),
    ("인재추천", "수시_종합_지역인재학교장추천"),
    ("사회배려자", "수시_종합_사회배려자"),
    ("AI특별", "수시_종합_AI특별"),
    ("고졸재직자", "수시_종합_고졸재직자"),
    ("영농창업인재", "수시_종합_영농창업인재"),
    ("논술", "수시_논술_AAT"),
    ("실적", "수시_실기_예체능"),
    ("특기자", "수시_특기자_체육"),
    ("특성화고졸업자", "out"),
    ("농어촌학생", "out"),
    ("기초생활", "out"),
    ("고졸재직자", "out"),
    ("모바일과학인재", "out"),
    ("장애인등", "out_merged"),  # 대학별로 세로 병합된 칸(행 '계'에 들어가지 않음)
    ("논술", "out"),
]
JS_COLS = [
    ("대학", "college"), ("모집단위", "name"),
    ("일반", "정시_수능_가_일반학생"),
    ("지역인재", "정시_수능_가_지역인재"),
    ("지역의사선발", "jisa"),
    ("일반", "정시_수능_나_일반학생"),
    ("총모집인원", "grand"),
]

SANGJU_COLLEGES = ("생태환경대학", "과학기술대학", "자율미래인재학부")
SANGJU_NOTE = "생태환경대학, 과학기술대학, 자율미래인재학부: 경상북도 상주시"
MOBILE_NOTE = "전자공학부 모바일공학전공은 삼성전자와 협약을 체결한 계약학과(정원외)임"


def parse_college_cell(lines):
    joined = nospace("".join(lines))
    keyeol = re.findall(r"\(([^)]*)\)", joined)
    name = re.sub(r"\([^)]*\)", "", joined)
    if name == "공대농대":  # 원문 두 줄 '공대'/'농대' (정시 표 표기: 공대·농대)
        name = "공대·농대"
    return name, (keyeol[-1] if keyeol else None)


def parse(pdf_path):
    pdf = pdfplumber.open(pdf_path)
    susi_pages, js_pages = [], []
    for p in pdf.pages[:15]:
        t = nospace(p.extract_text() or "")
        if "모집단위" not in t or "(계열)" not in t:
            continue
        if "총모집인원" in t and "(수시+정시)" in t and "가군" in t:
            js_pages.append(p.page_number)
        elif "정원내" in t and "정원외" in t and "우수자" in t:
            susi_pages.append(p.page_number)
    if not susi_pages or not js_pages:
        raise SystemExit("모집인원 표 쪽을 찾지 못함")
    notes_text = nospace(pdf.pages[js_pages[-1] - 1].extract_text() or "")
    if nospace(SANGJU_NOTE) not in notes_text or nospace(MOBILE_NOTE) not in notes_text:
        raise SystemExit("상주캠퍼스/모바일공학전공 주석 문구를 찾지 못함")

    rows, susi_total = [], None
    cur_college, cur_keyeol = None, None
    nonnum = []
    for pno in susi_pages:
        page = pdf.pages[pno - 1]
        bbox = main_table(page)
        cols, hdr_top, hdr_bottom = header_layout(page, r"모\s*집\s*단\s*위", bbox)
        check_headers(page, cols, [e for e, _ in SUSI_COLS], hdr_top - 40, hdr_bottom, f"p{pno} 수시")
        if group_spans(page, r"정원내", cols, hdr_top - 40, hdr_bottom) != [(3, 17)] or \
                group_spans(page, r"정원외", cols, hdr_top - 40, hdr_bottom) != [(18, 24)]:
            raise SystemExit(f"p{pno}: 정원내/정원외 묶음 범위가 예상과 다름")
        tot_col = cols[2]
        yb = [y for y in hbounds(page, *tot_col) if hdr_bottom - 0.5 <= y <= bbox[3] + 1]
        mcol = cols[3 + [r for _, r in SUSI_COLS[3:]].index("out_merged")]
        myb = [y for y in hbounds(page, *mcol) if hdr_bottom - 0.5 <= y <= bbox[3] + 1]
        cyb = [y for y in hbounds(page, *cols[0]) if hdr_bottom - 0.5 <= y <= bbox[3] + 1]
        col0_cells = []
        for y0, y1 in zip(cyb[:-1], cyb[1:]):
            col0_cells.append((y0, y1, lines_of(chars_in(page.chars, cols[0][0], cols[0][1], y0, y1))))
        for y0, y1 in zip(yb[:-1], yb[1:]):
            yc = (y0 + y1) / 2
            merged = not any(abs(x - cols[0][1]) < 1.5 for x in vbounds(page, yc))
            if merged:
                nlines = lines_of(chars_in(page.chars, cols[0][0], cols[1][1], y0, y1))
            else:
                nlines = lines_of(chars_in(page.chars, cols[1][0], cols[1][1], y0, y1))
            name = nospace("".join(nlines))
            vals = [num(lines_of(chars_in(page.chars, c[0], c[1], y0, y1))) for c in cols[2:]]
            if name == "소계":
                susi_total = vals
                continue
            if merged:
                college, keyeol = parse_college_cell(nlines)
                name = college
                cur_college, cur_keyeol = college, keyeol
            else:
                cell = [c for c in col0_cells if c[0] <= yc < c[1]]
                if len(cell) != 1:
                    raise SystemExit(f"p{pno}: '{name}' 대학칸을 찾지 못함")
                cname, ckeyeol = parse_college_cell(cell[0][2])
                if cname:
                    cur_college, cur_keyeol = cname, ckeyeol
                elif ckeyeol:
                    cur_keyeol = ckeyeol
            name = strip_note(name)
            for i, v in enumerate(vals):
                if v is None:
                    nonnum.append(f"p{pno} {name} {SUSI_COLS[i + 2][0]}")
            own = any(abs(a - y0) < 1.5 for a in myb) and any(abs(b - y1) < 1.5 for b in myb)
            rows.append({"college": cur_college, "keyeol": cur_keyeol, "name": name, "page": pno,
                         "susi": vals, "merged_own": own})

    js = {}
    js_total = None
    js_nonnum = []
    for pno in js_pages:
        page = pdf.pages[pno - 1]
        bbox = main_table(page)
        cols, hdr_top, hdr_bottom = header_layout(page, r"모\s*집\s*단\s*위", bbox)
        check_headers(page, cols, [e for e, _ in JS_COLS], hdr_top, hdr_bottom, f"p{pno} 정시")
        if group_spans(page, r"가군", cols, hdr_top, hdr_bottom) != [(2, 4)] or \
                group_spans(page, r"나군", cols, hdr_top, hdr_bottom) != [(5, 5)]:
            raise SystemExit(f"p{pno}: 가군/나군 묶음 범위가 예상과 다름")
        yb = [y for y in hbounds(page, *cols[1]) if hdr_bottom - 0.5 <= y <= bbox[3] + 1]
        for y0, y1 in zip(yb[:-1], yb[1:]):
            yc = (y0 + y1) / 2
            merged = not any(abs(x - cols[0][1]) < 1.5 for x in vbounds(page, yc))
            nx0 = cols[0][0] if merged else cols[1][0]
            name = strip_note(nospace("".join(lines_of(chars_in(page.chars, nx0, cols[1][1], y0, y1)))))
            raw = [lines_of(chars_in(page.chars, c[0], c[1], y0, y1)) for c in cols[2:]]
            vals = [num(r) for r in raw]
            if name == "소계":
                js_total = vals
                continue
            for i, v in enumerate(vals):
                if v is None:
                    js_nonnum.append((name, JS_COLS[i + 2][0], nospace("".join(raw[i]))))
            if name in js:
                raise SystemExit(f"정시 표 모집단위 이름 중복: {name}")
            js[name] = (vals, pno)
    pdf.close()
    return rows, susi_total, js, js_total, susi_pages, js_pages, nonnum, js_nonnum


def build(pdf_path):
    rows, susi_total, js, js_total, susi_pages, js_pages, nonnum, js_nonnum = parse(pdf_path)
    if susi_total is None or js_total is None:
        raise SystemExit("소계 행을 찾지 못함")
    names = [r["name"] for r in rows]
    if len(set(names)) != len(names):
        raise SystemExit("수시 표 모집단위 이름 중복")
    unmatched = [n for n in js if n not in names]
    if unmatched:
        raise SystemExit(f"정시 표 모집단위가 수시 표에 없음: {unmatched}")

    in_idx = [i for i, (_, role) in enumerate(SUSI_COLS[3:]) if role.startswith("수시_")]
    out_idx = [i for i, (_, role) in enumerate(SUSI_COLS[3:]) if role == "out"]
    merged_idx = [i for i, (_, role) in enumerate(SUSI_COLS[3:]) if role == "out_merged"]
    js_keys = [(i, role) for i, (_, role) in enumerate(JS_COLS[2:]) if role.startswith("정시_")]

    units = []
    chk_row = [0, 0]  # 수시 '계' 칸 대조 (일치, 불일치)
    chk_grand = [0, 0, 0]  # 총모집인원 대조 (일치, 불일치, 칸 비어 있음)
    mismatches = []
    excluded = []
    ex_rows = []
    sum_in = {k: 0 for k in JEONHYEONG}
    for r in rows:
        v = r["susi"]
        gye = v[0]
        rest = v[1:]
        row_sum = sum(rest[i] or 0 for i in in_idx + out_idx)
        if r["merged_own"]:  # 장애인등대상자 칸이 이 행 하나에만 걸친 경우만 행 합에 포함
            row_sum += sum(rest[i] or 0 for i in merged_idx)
        if gye is not None and row_sum == gye:
            chk_row[0] += 1
        else:
            chk_row[1] += 1
            mismatches.append(f"수시 {r['name']}: 계 {gye} vs 칸합 {row_sum}")
        jv, jp = js.get(r["name"], (None, None))
        if jv is not None:
            js_sum = sum(x or 0 for x in jv[:4])
            if jv[4] == 0:
                chk_grand[2] += 1
            elif gye is not None and gye + js_sum == jv[4]:
                chk_grand[0] += 1
            else:
                chk_grand[1] += 1
                mismatches.append(f"총모집인원 {r['name']}: {jv[4]} vs 수시계+정시 {gye}+{js_sum}")
        insw = {}
        for i in in_idx:
            if rest[i]:
                insw[SUSI_COLS[3 + i][1]] = rest[i]
        if jv is not None:
            for i, key in js_keys:
                if jv[i]:
                    insw[key] = jv[i]
        if "모바일공학전공" in r["name"]:
            ex_rows.append((rest, jv))
            excluded.append(f"{r['name']}(주석6 '계약학과(정원외)': 수시 {gye}, 정시 가군 일반 {jv[0] if jv else 0} 모두 제외)")
            continue
        if not insw:
            excluded.append(f"{r['name']}(정원내 인원 없음)")
            continue
        for k, n in insw.items():
            sum_in[k] += n
        college = r["college"]
        if college in SANGJU_COLLEGES:
            college = f"{college}(상주캠퍼스)"
        units.append({
            "단과대학": college,
            "모집단위": r["name"],
            "계열": r["keyeol"],
            "인원": insw,
            "계": None,
            "쪽": r["page"],
            "검증": "합계칸없음",
        })

    # 총계 대조
    pdf_in_tot = {}
    for i in in_idx:
        pdf_in_tot[SUSI_COLS[3 + i][1]] = susi_total[1 + i]
    for i, key in js_keys:
        pdf_in_tot[key] = js_total[i]
    # 제외한 정원외 학과(모바일공학전공)가 정원내 칸·정시 칸에 넣은 숫자는 PDF 소계에서 뺀 뒤 비교
    ex_adj = {k: 0 for k in pdf_in_tot}
    for rest, jv in ex_rows:
        for i in in_idx:
            ex_adj[SUSI_COLS[3 + i][1]] += rest[i] or 0
        if jv is not None:
            for i, key in js_keys:
                ex_adj[key] += jv[i] or 0
    col_bad = [f"{k}: PDF {pdf_in_tot[k]}-{ex_adj[k]} vs {sum_in[k]}" for k in pdf_in_tot
               if pdf_in_tot[k] - ex_adj[k] != sum_in[k]]
    susi_pdf = sum(pdf_in_tot[k] for k in pdf_in_tot if k.startswith("수시_"))
    susi_ours = sum(sum_in[k] for k in sum_in if k.startswith("수시_"))
    js_pdf = sum(pdf_in_tot[k] for k in pdf_in_tot if k.startswith("정시_"))
    js_ours = sum(sum_in[k] for k in sum_in if k.startswith("정시_"))
    mobile_js = sum(js[n][0][0] for n in js if "모바일공학전공" in n)

    memo = [
        "정원내만 수록. 수시 표의 정원외 7칸(학생부교과 특성화고졸업자, 학생부종합 농어촌학생·기초생활수급자등대상자·"
        "특성화고졸재직자·모바일과학인재·장애인등대상자, 논술(AAT) 정원외)은 넣지 않음.",
        "전자공학부 모바일공학전공은 12쪽 주석6 '계약학과(정원외)'이므로 수시·정시 모두 제외"
        f"(정시 표 가군 일반 소계 {js_total[0]}에는 이 학과 {mobile_js}명이 들어 있음).",
        "'계'는 null: PDF 수시 표의 행 '계'는 정원외를 포함한 수시 합계이고, 정시 표 '총모집인원(수시+정시)'도 "
        "정원외를 포함하므로 정원내 합계 칸이 없음.",
        f"행 대조(정원외 포함, 원문 숫자끼리): 수시 '계' = 정원내+정원외 칸 합(장애인등대상자 칸은 대학별로 세로 병합돼 "
        f"있어 그 행에만 걸친 경우만 더함) {chk_row[0]}행 일치/{chk_row[1]}행 불일치; 총모집인원 = 수시 계 + 정시 {chk_grand[0]}행 일치/"
        f"{chk_grand[1]}행 불일치/{chk_grand[2]}행 총모집인원 칸 비어 있음.",
        f"총계 대조: 수시 {susi_ours}={susi_pdf}(8쪽 소계 행 정원내 15칸 합), "
        f"정시 {js_ours}={js_pdf}-{mobile_js}(12쪽 소계 행에서 모바일공학전공 정원외 {mobile_js}명 뺌)"
        + ("; 전형별 18칸 모두 일치" if not col_bad else f"; 전형별 불일치 칸: {col_bad}"),
        "정시 가군 지역의사선발 칸은 의예과에 '수시 이월인원'으로만 적혀 있고 숫자가 없어 넣지 않음.",
        "생태환경대학·과학기술대학·자율미래인재학부는 12쪽 주석9에 따라 상주캠퍼스로 표시.",
        "계열은 표의 '대학(계열)' 칸 괄호 표기(인문/자연/예능/체능/인문·자연) 그대로.",
        "정시 '수능' 유형에는 실기고사를 함께 보는 예체능 모집단위(음악·디자인·체육교육 등)도 포함(원문 '정시모집(수능전형)').",
    ]
    if excluded:
        memo.append("제외한 행: " + "; ".join(excluded))
    if nonnum:
        memo.append("수시 표 숫자 아닌 칸: " + "; ".join(nonnum))
    other_nonnum = [f"{n} {c}='{t}'" for n, c, t in js_nonnum]
    if other_nonnum:
        memo.append("정시 표 숫자 아닌 칸(0으로 봄): " + "; ".join(other_nonnum))
    if mismatches:
        memo.append("행 대조 불일치 목록: " + "; ".join(mismatches))

    used = sorted({k for u in units for k in u["인원"]})
    order = list(JEONHYEONG)
    jh = [{"key": k, "시기": JEONHYEONG[k][0], "유형": JEONHYEONG[k][1], "전형명": JEONHYEONG[k][2],
           "군": JEONHYEONG[k][3]} for k in order if k in used]
    return {
        "id": UNIV_ID,
        "이름": UNIV_NAME,
        "출처쪽": susi_pages + js_pages,
        "전형": jh,
        "모집단위": units,
        "메모": memo,
    }


def main():
    if len(sys.argv) != 3:
        raise SystemExit("사용: knu.py <pdf> <out.json>")
    data = build(sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(data['모집단위'])} rows -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
