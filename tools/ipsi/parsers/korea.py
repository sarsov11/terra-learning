#!/usr/bin/env python3
"""고려대학교(서울) 2028학년도 입학전형시행계획 → 모집단위별 정원내 모집인원.

표: '2-1. 수시모집 모집인원'(PDF 5~6쪽), '2-2. 정시모집 모집인원'(PDF 7~8쪽).
수시 열: 대학(학부)|계열|모집단위|입학정원|학교추천|학업우수|계열적합|고른기회|다문화|재직자|사이버국방|논술|특기자
정시 열: 대학(학부)|계열|모집단위|입학정원|일반|교과우수|농어촌|사회배려|특수교육|특성화고(뒤 4열 = 최대선발가능인원)
행 합계 칸이 없으므로 계는 null(합계칸없음). 정원내/외 판단 근거는 메모에 남긴다.

사용: python3 -I tools/ipsi/parsers/korea.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

ID = "korea"
NAME = "고려대학교"


# ---------------------------------------------------------------- 공통 도우미
def dedupe(vals, tol=3.0):
    out = []
    for v in sorted(vals):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def main_table(page):
    ts = page.find_tables()
    t = max(ts, key=lambda t: (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1]))
    xs = dedupe([c[0] for c in t.cells] + [c[2] for c in t.cells])
    return t.bbox, xs


def h_rules(page, xa, xb, y0, y1, cov=0.9):
    lo, hi = xa + 2, xb - 2
    by = {}
    for e in page.edges:
        if e["orientation"] != "h":
            continue
        y = e["top"]
        if y < y0 - 2 or y > y1 + 2:
            continue
        a, b = max(e["x0"], lo), min(e["x1"], hi)
        if b > a:
            by.setdefault(round(y * 2) / 2, []).append((a, b))
    out = []
    for y in sorted(by):
        total, cur = 0.0, None
        for a, b in sorted(by[y]):
            if cur is None or a > cur[1]:
                if cur:
                    total += cur[1] - cur[0]
                cur = [a, b]
            else:
                cur[1] = max(cur[1], b)
        if cur:
            total += cur[1] - cur[0]
        if total >= cov * (hi - lo):
            if out and y - out[-1] <= 2.0:
                continue
            out.append(y)
    return out


def cell_of(rules, y):
    for a, b in zip(rules, rules[1:]):
        if a <= y < b:
            return a, b
    return None


def cx(w):
    return (w["x0"] + w["x1"]) / 2


def cy(w):
    return (w["top"] + w["bottom"]) / 2


def words_in(words, xa, xb, ya, yb):
    return [w for w in words if xa <= cx(w) < xb and ya <= cy(w) < yb]


def lines_of(ws):
    ws = sorted(ws, key=lambda w: (round(w["top"]), w["x0"]))
    lines = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1][0]) <= 2.5:
            lines[-1][1].append(w)
        else:
            lines.append([w["top"], [w]])
    return [" ".join(x["text"] for x in sorted(l[1], key=lambda w: w["x0"])) for l in lines]


def text_in(words, xa, xb, ya, yb, sep=""):
    return sep.join(lines_of(words_in(words, xa, xb, ya, yb))).strip()


def clean_name(s):
    s = s.strip()
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\d+\)$", "", s).strip()
        s = re.sub(r"[†*]+$", "", s).strip()
    return s


NUM_RE = re.compile(r"\d{1,3}(?:,\d{3})+|\d+")


def parse_num(s):
    s = s.replace(" ", "")
    if s in ("", "-", "·", "–", "−"):
        return 0
    if NUM_RE.fullmatch(s):
        return int(s.replace(",", ""))
    return None


class Grid:
    def __init__(self, page, ncols):
        self.page = page
        self.bbox, self.xs = main_table(page)
        if len(self.xs) != ncols + 1:
            raise SystemExit(f"{page.page_number}쪽: 열 경계 {len(self.xs)}개({ncols + 1} 기대) {self.xs}")
        self.words = page.extract_words()
        t, b = self.bbox[1], self.bbox[3]
        self.rules = [h_rules(page, self.xs[i], self.xs[i + 1], t, b) for i in range(ncols)]
        self.hb = self.rules[0][1]

    def cell(self, ci, y):
        return cell_of(self.rules[ci], y)

    def text(self, ci, y, sep=""):
        c = self.cell(ci, y)
        if not c:
            return "", None
        return text_in(self.words, self.xs[ci], self.xs[ci + 1], c[0], c[1], sep), c

    def header(self, ci):
        return text_in(self.words, self.xs[ci], self.xs[ci + 1], self.bbox[1], self.hb).replace(" ", "")

    def rows(self, ci):
        return [(a, b) for a, b in zip(self.rules[ci], self.rules[ci][1:]) if a >= self.hb - 0.5]


# ---------------------------------------------------------------- 고려대 전용
# 열 번호 → (key, 시기, 유형, 전형명, 군)  — 정원내로 넣는 열
SUSI_IN = {
    4: ("수시_교과_학교추천", "수시", "학생부교과", "학생부교과(학교추천전형)", None),
    5: ("수시_종합_학업우수", "수시", "학생부종합", "학생부종합(학업우수전형)", None),
    6: ("수시_종합_계열적합", "수시", "학생부종합", "학생부종합(계열적합전형)", None),
    7: ("수시_종합_고른기회", "수시", "학생부종합", "학생부종합(고른기회전형)", None),
    8: ("수시_종합_다문화", "수시", "학생부종합", "학생부종합(다문화전형)", None),
    11: ("수시_논술", "수시", "논술", "논술(논술전형)", None),
    12: ("수시_실기_특기자", "수시", "실기/실적", "실기/실적(특기자전형)", None),
}
SUSI_OUT = {9: "학생부종합(재직자전형)", 10: "학생부종합(사이버국방전형)"}
JS_IN = {
    4: ("정시_수능_일반_가", "정시", "수능", "수능(일반전형)", "가"),
    5: ("정시_수능_교과우수_가", "정시", "수능", "수능(교과우수전형)", "가"),
}
JS_OUT = {6: "수능(농어촌전형)", 7: "수능(사회배려전형)", 8: "수능(특수교육전형)", 9: "수능(특성화고전형)"}

SUSI_HDR = {0: "대학", 1: "계열", 2: "모집단위", 3: "입학정원", 4: "학교추천", 5: "학업우수", 6: "계열적합",
            7: "고른기회", 8: "다문화", 9: "재직자", 10: "사이버국방", 11: "논술", 12: "특기자"}
JS_HDR = {0: "대학", 1: "계열", 2: "모집단위", 3: "입학정원", 4: "일반전형", 5: "교과우수", 6: "농어촌",
          7: "사회배려", 8: "특수교육", 9: "특성화고"}


def read_table(pdf, pno, ncols, hdr, num_cols):
    g = Grid(pdf.pages[pno - 1], ncols)
    for ci, s in hdr.items():
        if s not in g.header(ci):
            raise SystemExit(f"{pno}쪽 헤더 확인 실패: 열{ci} '{s}' 없음 → '{g.header(ci)}'")
    rows = []
    for ya, yb in g.rows(3):
        mid = (ya + yb) / 2
        college, _ = g.text(0, mid)
        series, _ = g.text(1, mid)
        unit, _ = g.text(2, mid)
        raw, span_bad = {}, False
        for ci in [3] + num_cols:
            txt, c = g.text(ci, mid, sep=" ")
            raw[ci] = txt
            if c and (abs(c[0] - ya) > 1 or abs(c[1] - yb) > 1):
                span_bad = True
        rows.append({"쪽": pno, "college": college, "계열": series, "unit": unit, "raw": raw, "span_bad": span_bad})
    return rows


def contract_units(pdf, pages):
    names = set()
    for pno in pages:
        t = pdf.pages[pno - 1].extract_text() or ""
        for m in re.finditer(r"\d+\)\s*(\S+?)는 [^\n]*정원 외로 선발함", t):
            names.add(clean_name(m.group(1)))
    return names


def main():
    if len(sys.argv) != 3:
        raise SystemExit("사용: korea.py <pdf> <out.json>")
    src, out = sys.argv[1], sys.argv[2]
    memo_bad = []
    with pdfplumber.open(src) as pdf:
        susi_pages, js_pages = [], []
        for i, p in enumerate(pdf.pages, 1):
            t = p.extract_text() or ""
            if "학교추천 학업우수 계열적합" in t and "모집단위" in t:
                susi_pages.append(i)
            if "농어촌전형 사회배려전형 특수교육전형 특성화고전형" in t and "입학정원" in t and "최대선발가능인원" in t:
                js_pages.append(i)
        if not susi_pages or not js_pages:
            raise SystemExit(f"표 쪽 찾기 실패: 수시 {susi_pages} 정시 {js_pages}")
        rows_s, rows_j = [], []
        for pno in susi_pages:
            rows_s += read_table(pdf, pno, 13, SUSI_HDR, list(SUSI_IN) + list(SUSI_OUT))
        for pno in js_pages:
            rows_j += read_table(pdf, pno, 10, JS_HDR, list(JS_IN) + list(JS_OUT))
        contracts = contract_units(pdf, susi_pages + js_pages)

    def split(rows):
        body, total = [], None
        for r in rows:
            if "합계" in (r["college"] + r["계열"] + r["unit"]).replace(" ", ""):
                total = r
                continue
            body.append(r)
        return body, total

    body_s, tot_s = split(rows_s)
    body_j, tot_j = split(rows_j)

    units, order = {}, []
    excluded = {}            # 계약학과(정원외) 행: name → {key: n}
    out_nonzero = []         # 정원외 열에 값이 있는 일반 행
    jaejik = []              # 재직자 ◉ 표시 단위
    cap = {}                 # 입학정원

    def add(r, part, cols_in, cols_out):
        name = clean_name(r["unit"])
        college = clean_name(r["college"]) or name
        vals = {ci: parse_num(r["raw"][ci]) for ci in [3] + list(cols_in)}
        if r["span_bad"] or any(v is None for v in vals.values()) or not name:
            memo_bad.append(f"{r['쪽']}쪽 '{name}' 행 판독 불가({part}): {r['raw']}")
            return
        if name in contracts:
            ex = excluded.setdefault(name, {})
            for ci, spec in cols_in.items():
                if vals[ci]:
                    ex[spec[0]] = vals[ci]
            for ci in cols_out:
                v = parse_num(r["raw"][ci])
                if v:
                    ex[cols_out[ci]] = v
            return
        for ci, label in cols_out.items():
            t = r["raw"][ci].replace(" ", "")
            if t == "◉":
                if part == "수시" and ci == 9:
                    jaejik.append(name)
                else:
                    memo_bad.append(f"{r['쪽']}쪽 '{name}' {label} 칸 '◉' (정원외 열, 미수록)")
            elif parse_num(t) is None:
                memo_bad.append(f"{r['쪽']}쪽 '{name}' {label} 칸 판독 불가 '{t}' (정원외 열, 미수록)")
            elif parse_num(t):
                out_nonzero.append((name, label, parse_num(t)))
        key = name
        if key not in units:
            units[key] = {"단과대학": college, "모집단위": name, "계열": r["계열"] or None,
                          "인원": {}, "쪽": r["쪽"]}
            order.append(key)
            cap[key] = vals[3]
        u = units[key]
        if (r["계열"] or None) != u["계열"]:
            memo_bad.append(f"{name}: 수시 계열 '{u['계열']}' / 정시 계열 '{r['계열']}' 다름 → 수시 표기 사용")
        if cap[key] != vals[3]:
            memo_bad.append(f"{name}: 입학정원 수시표 {cap[key]} / 정시표 {vals[3]} 다름")
        for ci, spec in cols_in.items():
            if vals[ci]:
                u["인원"][spec[0]] = vals[ci]

    for r in body_s:
        add(r, "수시", SUSI_IN, SUSI_OUT)
    for r in body_j:
        add(r, "정시", JS_IN, JS_OUT)

    out_units = [dict(units[k], 계=None, 검증="합계칸없음") for k in order]

    # 입학정원 대조(정원내 판단 근거)
    eq, diff = 0, []
    for k in order:
        s = sum(units[k]["인원"].values())
        if s == cap[k]:
            eq += 1
        else:
            diff.append(f"{k} {s}(입학정원 {cap[k]}, {s - cap[k]:+d})")

    # 총계 대조: PDF 합계 행(계약학과 포함) − 계약학과 행 = 정리된 합
    def colsum(key):
        return sum(u["인원"].get(key, 0) for u in out_units)

    def exsum(key):
        return sum(v.get(key, 0) for v in excluded.values())

    tot_lines = []
    s_pdf = s_ex = s_got = 0
    if tot_s:
        parts = []
        for ci, spec in SUSI_IN.items():
            pv = parse_num(tot_s["raw"][ci])
            got, ex = colsum(spec[0]), exsum(spec[0])
            parts.append(f"{spec[3]} {pv}-{ex}={got}" + ("" if pv == got + ex else " 불일치"))
            s_pdf += pv or 0
            s_ex += ex
            s_got += got
        tot_lines.append(f"총계 대조: 수시 {s_pdf - s_ex}={s_got} (PDF 합계 행 정원내 7개 전형 {s_pdf} − 계약학과 {s_ex}; " + ", ".join(parts) + ")")
    j_pdf = j_ex = j_got = 0
    if tot_j:
        parts = []
        for ci, spec in JS_IN.items():
            pv = parse_num(tot_j["raw"][ci])
            got, ex = colsum(spec[0]), exsum(spec[0])
            parts.append(f"{spec[3]} {pv}-{ex}={got}" + ("" if pv == got + ex else " 불일치"))
            j_pdf += pv or 0
            j_ex += ex
            j_got += got
        tot_lines.append(f"총계 대조: 정시 {j_pdf - j_ex}={j_got} (PDF 합계 행 {j_pdf} − 계약학과 {j_ex}; " + ", ".join(parts) + ")")

    전형 = [dict(zip(("key", "시기", "유형", "전형명", "군"), v)) for v in list(SUSI_IN.values()) + list(JS_IN.values())]
    pages = sorted(set(susi_pages + js_pages))
    exc = "; ".join(f"{k} {v}" for k, v in excluded.items())
    메모 = [
        "정원내만 수록",
        "PDF 표에 전형별 정원내/외 구분 표기가 없음. 정원내 = 학교추천·학업우수·계열적합·고른기회·다문화·논술·특기자(수시), 일반·교과우수(정시)로 봄. "
        f"근거: 이 9개 전형 합이 표의 '입학정원'과 같은 단위 {eq}/{len(order)}개, 다른 단위는 모두 + 방향(수시표 각주 1 '2026학년도 미충원 인원 반영')",
        "입학정원과 다른 단위: " + ("; ".join(diff) if diff else "없음"),
        "정원외 미수록: 수시 재직자전형(표에 단위별 숫자 없이 ◉ 표시, 총 18명 이내 — ◉ 단위 " + str(len(jaejik)) + "개), "
        "사이버국방전형(사이버국방학과 계약학과 전용), 정시 농어촌·사회배려·특수교육·특성화고전형(표에 '최대선발가능인원'으로 표기), "
        "재외국민(3년)·북한이탈주민·전교육과정해외이수자 특별전형",
        f"정원외 계약학과(각주 '정원 외로 선발함') 행 제외: {exc}",
        "계: 표에 행 합계 칸이 없음('입학정원'은 모집인원 합계가 아님) → null, 검증 '합계칸없음'",
        "특기자전형: 체육교육과(9-1)·디자인조형학부(9-2); 정시는 모두 '가'군",
        "모집단위 이름 끝 *(전공자율선택제) 표시는 제거; 두 줄로 쪼개진 이름(바이오시스템/의과학부 등)은 붙여 씀",
        "쪽 = 해당 단위가 처음 나온 PDF 파일 쪽 번호(1부터)",
    ] + tot_lines
    if out_nonzero:
        agg = {}
        for _, label, n in out_nonzero:
            agg[label] = agg.get(label, 0) + n
        pdf_out = {}
        if tot_j:
            for ci, label in JS_OUT.items():
                pdf_out[label] = parse_num(tot_j["raw"][ci])
        메모.append("미수록 정원외 열 단위별 숫자 합(참고): " + ", ".join(
            f"{k} {v}" + (f"(PDF 합계 행 {pdf_out[k]})" if k in pdf_out else "") for k, v in agg.items()))
    메모 += memo_bad

    data = {"id": ID, "이름": NAME, "출처쪽": pages, "전형": 전형, "모집단위": out_units, "메모": 메모}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{ID}: 행 {len(out_units)}개, 검증 합계칸없음 {len(out_units)}, 출처쪽 {pages}")
    for m in 메모[1:3] + 메모[4:5] + tot_lines + memo_bad:
        print(" ", m)


if __name__ == "__main__":
    main()
