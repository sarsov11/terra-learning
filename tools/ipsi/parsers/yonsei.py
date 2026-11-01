#!/usr/bin/env python3
"""연세대학교(서울) 2028학년도 입학전형 시행계획 → 모집단위별 정원내 모집인원.

표: 'III 모집단위별 모집인원' 1. 수시모집(PDF 10~11쪽), 2. 정시모집(PDF 12~13쪽).
수시 열: 대학|모집단위|계열|모집인원|추천형|종합인재형|탐구인재형 일반|국제|기회균형|논술|특기자|(정원외)특수교육
정시 열: 대학|모집단위|계열|수능유형|모집인원|일반 '가'군|'나'군|(정원외 4열)
행 경계는 각 열의 가로 괘선으로 잡고, 병합 칸은 괘선 칸 단위로 읽는다.

사용: python3 -I tools/ipsi/parsers/yonsei.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

ID = "yonsei"
NAME = "연세대학교"


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
    """괘선 기반 표 읽기: 열 경계 xs, 열별 가로 괘선, 단어."""

    def __init__(self, page, ncols):
        self.page = page
        self.bbox, self.xs = main_table(page)
        if len(self.xs) != ncols + 1:
            raise SystemExit(f"{page.page_number}쪽: 열 경계 {len(self.xs)}개({ncols + 1} 기대) {self.xs}")
        self.words = page.extract_words()
        t, b = self.bbox[1], self.bbox[3]
        self.rules = [h_rules(page, self.xs[i], self.xs[i + 1], t, b) for i in range(ncols)]
        self.hb = self.rules[0][1]  # 머리글 아래 괘선

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


# ---------------------------------------------------------------- 연세대 전용
SUSI_COLS = {  # 열 번호 → (key, 시기, 유형, 전형명)
    4: ("수시_교과_추천형", "수시", "학생부교과", "학생부교과전형[추천형]"),
    5: ("수시_종합_종합인재형", "수시", "학생부종합", "학생부종합전형[종합인재형]"),
    6: ("수시_종합_탐구인재형일반", "수시", "학생부종합", "학생부종합전형[탐구인재형(일반)]"),
    7: ("수시_종합_탐구인재형국제", "수시", "학생부종합", "학생부종합전형[탐구인재형(국제)]"),
    8: ("수시_종합_기회균형", "수시", "학생부종합", "학생부종합전형[기회균형]"),
    9: ("수시_논술", "수시", "논술", "논술전형"),
    10: ("수시_실기_특기자체육인재", "수시", "실기/실적", "특기자전형(체육인재)"),
}
JEONGSI_COLS = {
    5: None,  # '가'군: 계열에 따라 일반계열/체능계열로 나눔
    6: ("정시_실기_예능_나", "정시", "실기/실적", "일반전형(예능계열)", "나"),
}
JS_GA_GENERAL = ("정시_수능_일반계열_가", "정시", "수능", "일반전형(일반계열)", "가")
JS_GA_SPORTS = ("정시_수능_체능계열_가", "정시", "수능", "일반전형(체능계열)", "가")


def read_table(pdf, pno, kind, memo):
    page = pdf.pages[pno - 1]
    if kind == "수시":
        g = Grid(page, 12)
        expect = {0: "대학", 1: "모집단위", 2: "계열", 3: "모집인원", 4: "추천형", 5: "종합인재형",
                  6: "일반", 7: "국제", 8: "기회균형", 9: "논술", 10: "특기자", 11: "특수교육"}
        c_total, num_cols = 3, list(SUSI_COLS)
    else:
        g = Grid(page, 11)
        expect = {0: "대학", 1: "모집단위", 2: "계열", 3: "수능유형", 4: "모집인원", 5: "'가'군", 6: "'나'군",
                  7: "연세한마음", 8: "농어촌", 9: "특성화고교", 10: "특수교육"}
        c_total, num_cols = 4, [5, 6]
    for ci, s in expect.items():
        if s not in g.header(ci):
            raise SystemExit(f"{pno}쪽 헤더 확인 실패: 열{ci} '{s}' 없음 → '{g.header(ci)}'")
    out = []
    for ya, yb in g.rows(c_total):
        mid = (ya + yb) / 2
        college, _ = g.text(0, mid)
        unit, ucell = g.text(1, mid)
        series, _ = g.text(2, mid)
        raw = {}
        span_bad = False
        for ci in [c_total] + num_cols:
            txt, c = g.text(ci, mid, sep=" ")
            raw[ci] = txt
            if c and (abs(c[0] - ya) > 1 or abs(c[1] - yb) > 1):
                span_bad = True
        out.append({"쪽": pno, "college": college, "unit": unit, "ucell": ucell, "row": (ya, yb),
                    "계열": series, "raw": raw, "span_bad": span_bad})
    return out, c_total, num_cols


def contract_units(pdf, pages):
    """각주 '… 계약학과이며 정원 외로 선발함' 에서 단위 이름을 모은다."""
    names = set()
    for pno in pages:
        t = pdf.pages[pno - 1].extract_text() or ""
        for m in re.finditer(r"\d+\)\s*(?:\S+대학\s+)?(\S+?)는 [^\n]*정원 외로 선발함", t):
            names.add(clean_name(m.group(1)))
    return names


def overview_counts(pdf):
    """II 모집시기 및 전형별 모집인원(정시 '가'군: 일반계열/체능계열) 숫자."""
    for p in pdf.pages:
        t = p.extract_text() or ""
        if "II 모집시기 및 전형별 모집인원" not in t:
            continue
        m1 = re.search(r"일반계열 연세한마음\n([\d,]+)명", t)
        m2 = re.search(r"체능계열 농어촌학생\n([\d,]+)명", t)
        if m1 and m2:
            return int(m1.group(1).replace(",", "")), int(m2.group(1).replace(",", ""))
    return None


def main():
    if len(sys.argv) != 3:
        raise SystemExit("사용: yonsei.py <pdf> <out.json>")
    src, out = sys.argv[1], sys.argv[2]
    memo_bad = []
    with pdfplumber.open(src) as pdf:
        susi_pages, js_pages = [], []
        for i, p in enumerate(pdf.pages, 1):
            t = p.extract_text() or ""
            if "대학 모집단위 계열" in t and "추천형" in t and "탐구인재형" in t:
                susi_pages.append(i)
            if re.search(r"수능 모집 일반전형 고른기회전형", t):
                js_pages.append(i)
        if not susi_pages or not js_pages:
            raise SystemExit(f"표 쪽 찾기 실패: 수시 {susi_pages} 정시 {js_pages}")
        rows_s, rows_j = [], []
        for pno in susi_pages:
            r, cts, ncs = read_table(pdf, pno, "수시", memo_bad)
            rows_s += r
        for pno in js_pages:
            r, ctj, ncj = read_table(pdf, pno, "정시", memo_bad)
            rows_j += r
        contracts = contract_units(pdf, susi_pages + js_pages)
        ov = overview_counts(pdf)

    def split(rows):
        body, total = [], None
        for r in rows:
            if r["college"].replace(" ", "") == "합계":
                if r["unit"].replace(" ", "") == "정원내":
                    total = r
                continue
            body.append(r)
        return body, total

    body_s, tot_s = split(rows_s)
    body_j, tot_j = split(rows_j)

    def unit_key(r):
        name = clean_name(r["unit"])
        college = clean_name(r["college"]) or name
        # 모집단위 칸이 여러 행에 걸치면(진리자유학부: 인문/자연) 계열로 구분
        ya, yb = r["row"]
        if r["ucell"] and (r["ucell"][1] - r["ucell"][0]) > (yb - ya) + 2:
            name = f"{name}({r['계열']})"
        return college, name

    units = {}
    order = []
    excluded = {}

    def add(r, part, c_total, cols):
        college, name = unit_key(r)
        base = re.sub(r"\(.*\)$", "", name)
        vals = {ci: parse_num(r["raw"][ci]) for ci in [c_total] + cols}
        if r["span_bad"] or any(v is None for v in vals.values()):
            memo_bad.append(f"{r['쪽']}쪽 '{name}' 행 판독 불가({part}): {r['raw']}")
            return
        if base in contracts:
            excluded.setdefault(name, {})[part] = vals[c_total]
            return
        key = (college, name)
        if key not in units:
            units[key] = {"단과대학": college, "모집단위": name, "계열": r["계열"] or None,
                          "인원": {}, "parts": {}, "쪽": r["쪽"], "pages": []}
            order.append(key)
        u = units[key]
        u["pages"].append(r["쪽"])
        if u["계열"] != (r["계열"] or None):
            u.setdefault("계열_정시", r["계열"])
        part_sum = 0
        for ci in cols:
            v = vals[ci]
            if not v:
                continue
            if part == "수시":
                k = SUSI_COLS[ci][0]
            elif ci == 5:
                k = (JS_GA_SPORTS if r["계열"] == "체능" else JS_GA_GENERAL)[0]
            else:
                k = JEONGSI_COLS[ci][0]
            u["인원"][k] = u["인원"].get(k, 0) + v
            part_sum += v
        u["parts"][part] = (vals[c_total], part_sum)

    for r in body_s:
        add(r, "수시", 3, list(SUSI_COLS))
    for r in body_j:
        add(r, "정시", 4, [5, 6])

    전형 = []
    for ci in SUSI_COLS:
        k, a, b, c = SUSI_COLS[ci]
        전형.append({"key": k, "시기": a, "유형": b, "전형명": c, "군": None})
    for k, a, b, c, d in (JS_GA_GENERAL, JS_GA_SPORTS, JEONGSI_COLS[6]):
        전형.append({"key": k, "시기": a, "유형": b, "전형명": c, "군": d})

    out_units, part_bad = [], []
    for key in order:
        u = units[key]
        계 = sum(t for t, _ in u["parts"].values())
        ok = all(t == s for t, s in u["parts"].values()) and sum(u["인원"].values()) == 계
        if not ok:
            part_bad.append(u["모집단위"] + " " + ", ".join(
                f"{k} 모집인원 칸 {t} vs 전형별 합 {s}" for k, (t, s) in u["parts"].items() if t != s))
        series = u["계열"]
        if "계열_정시" in u and u["계열_정시"] != series:
            memo_bad.append(f"{u['모집단위']}: 수시 계열 '{series}' / 정시 계열 '{u['계열_정시']}' 다름 → 수시 표기 사용")
        out_units.append({"단과대학": u["단과대학"], "모집단위": u["모집단위"], "계열": series,
                          "인원": u["인원"], "계": 계, "쪽": u["쪽"], "검증": "합계일치" if ok else "합계불일치"})

    # 총계 대조
    def colsum(keys):
        return sum(u["인원"].get(k, 0) for u in out_units for k in keys)
    susi_keys = [SUSI_COLS[c][0] for c in SUSI_COLS]
    memo_tot = []
    if tot_s:
        tv = {ci: parse_num(tot_s["raw"][ci]) for ci in [3] + list(SUSI_COLS)}
        parts = ", ".join(f"{SUSI_COLS[ci][3]} {tv[ci]}={colsum([SUSI_COLS[ci][0]])}" for ci in SUSI_COLS)
        mcol = sum(u["parts"]["수시"][0] for u in units.values() if "수시" in u["parts"])
        memo_tot.append(f"총계 대조: 수시 {tv[3]}={colsum(susi_keys)} ({parts}); "
                        f"수시 '모집인원' 열(행 합계 칸) 합 {mcol} vs PDF 합계 {tv[3]}")
    else:
        memo_tot.append("총계 대조: 수시 합계(정원 내) 행 읽기 실패")
    if tot_j:
        tv = {ci: parse_num(tot_j["raw"][ci]) for ci in (4, 5, 6)}
        ga = colsum([JS_GA_GENERAL[0], JS_GA_SPORTS[0]])
        na = colsum([JEONGSI_COLS[6][0]])
        mcol = sum(u["parts"]["정시"][0] for u in units.values() if "정시" in u["parts"])
        s = (f"총계 대조: 정시 {tv[4]}={ga + na} ('가'군 {tv[5]}={ga}, '나'군 {tv[6]}={na}); "
             f"정시 '모집인원' 열 합 {mcol} vs PDF 합계 {tv[4]}")
        if ov:
            s += f"; II장 '가'군 일반계열 {ov[0]}={colsum([JS_GA_GENERAL[0]])}, 체능계열 {ov[1]}={colsum([JS_GA_SPORTS[0]])}"
        memo_tot.append(s)
    else:
        memo_tot.append("총계 대조: 정시 합계(정원 내) 행 읽기 실패")

    pages = sorted(set(susi_pages + js_pages))
    exc = "; ".join(f"{k} 수시 {v.get('수시', 0)}·정시 {v.get('정시', 0)}" for k, v in excluded.items())
    메모 = [
        "정원내만 수록",
        "정원외 미수록: 수시 학생부종합[특수교육대상자], 정시 고른기회전형(연세한마음·농어촌학생·특성화고교졸업자·특수교육대상자), 재외국민·외국인 특별전형",
        f"정원외 계약학과(각주 '정원 외로 선발함') 행 제외: {exc}",
        "계 = 수시 표 '모집인원' + 정시 표 '모집인원'(각 표의 행 합계 칸). 검증은 수시·정시 각각 행 합 == 모집인원일 때만 합계일치",
        "정시 '가'군은 계열 칸이 '체능'인 행을 일반전형(체능계열), 나머지를 일반전형(일반계열)으로 나눔(V장 전형 구분)",
        "진리자유학부는 계열(인문/자연)별로 따로 모집 → '진리자유학부(인문)', '진리자유학부(자연)'",
        "모집단위 이름 끝 †(교직과정)·*(각주) 표시는 제거",
        "쪽 = 해당 단위가 처음 나온 PDF 파일 쪽 번호(1부터)",
    ] + memo_tot + ([] if not part_bad else [
        "합계불일치 상세: " + "; ".join(part_bad) + " — 숫자는 PDF 그대로 두었음(전형별 열 합계는 PDF 합계 행과 모두 일치)"]) + memo_bad

    data = {"id": ID, "이름": NAME, "출처쪽": pages, "전형": 전형, "모집단위": out_units, "메모": 메모}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    cnt = {}
    for u in out_units:
        cnt[u["검증"]] = cnt.get(u["검증"], 0) + 1
    print(f"{ID}: 행 {len(out_units)}개, 검증 {cnt}, 출처쪽 {pages}")
    for m in 메모[2:3] + memo_tot + memo_bad:
        print(" ", m)


if __name__ == "__main__":
    main()
