#!/usr/bin/env python3
"""서강대학교 2028학년도 대학입학전형 시행계획 → 모집단위별 정원내 모집인원.

표: '2-1. 수시모집 모집인원'(PDF 5쪽), '2-2. 정시모집 모집인원'(PDF 6쪽).
수시 열: 모집단위|학과·학부|입학정원|지역균형|일반Ⅰ|일반Ⅱ|기회균형|서강가치|특성화고교졸업자|논술 일반|모집단위별 모집인원
정시 열: 모집단위|학과·학부|입학정원|일반(나)|일반(다)|지역균형(나)|농어촌|기초생활|장애인|특성화|모집단위별 모집인원
여러 학과가 한 모집단위로 묶인 경우(인문학부 등) 모집단위 칸이 병합되고, 수시 일반Ⅰ만 학과별로 나뉜다.
→ 행 = 모집단위(왼쪽 칸). 일반Ⅰ 학과별 인원은 합해 넣고 내역은 메모에 남긴다.
'( )' 안 인원은 표 각주대로 정원 외.

사용: python3 -I tools/ipsi/parsers/sogang.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

ID = "sogang"
NAME = "서강대학교"


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
PAREN_RE = re.compile(r"\((\d{1,3}(?:,\d{3})*|\d+)\)(?:\d+\))?")


def parse_cell(s):
    """('in', n) 정원내 숫자 / ('out', n) 괄호(정원외) / None 판독 불가. '-'·빈칸은 ('in', 0)."""
    s = s.replace(" ", "")
    if s in ("", "-", "·", "–", "−"):
        return ("in", 0)
    if NUM_RE.fullmatch(s):
        return ("in", int(s.replace(",", "")))
    m = PAREN_RE.fullmatch(s)
    if m:
        return ("out", int(m.group(1).replace(",", "")))
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

    def header(self, ci):
        return text_in(self.words, self.xs[ci], self.xs[ci + 1], self.bbox[1], self.hb).replace(" ", "")

    def cells(self, ci, ya=None, yb=None):
        out = []
        for a, b in zip(self.rules[ci], self.rules[ci][1:]):
            if a < self.hb - 0.5:
                continue
            if ya is not None and (b <= ya + 0.5 or a >= yb - 0.5):
                continue
            out.append((a, b))
        return out

    def text(self, ci, a, b, sep=""):
        return text_in(self.words, self.xs[ci], self.xs[ci + 1], a, b, sep)


# ---------------------------------------------------------------- 서강대 전용
SUSI_HDR = {0: "모집단위", 1: "학과·학부", 2: "입학정원", 3: "지역균형", 4: "일반Ⅰ", 5: "일반Ⅱ", 6: "기회균형",
            7: "서강가치", 8: "특성화", 9: "논술", 10: "모집단위별"}
SUSI_IN = {
    3: ("수시_교과_지역균형", "수시", "학생부교과", "학생부교과(지역균형)", None),
    4: ("수시_종합_일반1", "수시", "학생부종합", "학생부종합(일반Ⅰ)", None),
    5: ("수시_종합_일반2", "수시", "학생부종합", "학생부종합(일반Ⅱ)", None),
    6: ("수시_종합_기회균형", "수시", "학생부종합", "학생부종합(기회균형)", None),
    7: ("수시_종합_서강가치", "수시", "학생부종합", "학생부종합(서강가치)", None),
    9: ("수시_논술_일반", "수시", "논술", "논술(일반)", None),
}
SUSI_OUT = {8: "학생부종합(특성화고교졸업자)"}
JS_HDR = {0: "모집단위", 1: "학과·학부", 2: "입학정원", 3: "(나)군", 4: "(다)군", 5: "지역균형", 6: "농어촌",
          7: "기초생활", 8: "장애인", 9: "특성화", 10: "모집단위별"}
JS_IN = {
    3: ("정시_수능_일반_나", "정시", "수능", "수능(일반-나군)", "나"),
    4: ("정시_수능_일반_다", "정시", "수능", "수능(일반-다군)", "다"),
    5: ("정시_수능_지역균형_나", "정시", "수능", "수능(지역균형)", "나"),
}
JS_OUT = {6: "수능(농어촌학생)", 7: "수능(기초생활보장대상자)", 8: "수능(장애인대상자)", 9: "수능(특성화고교졸업자)"}


def read_table(pdf, pno, hdr, cols_in, cols_out, memo_bad):
    g = Grid(pdf.pages[pno - 1], 11)
    for ci, s in hdr.items():
        if s not in g.header(ci):
            raise SystemExit(f"{pno}쪽 헤더 확인 실패: 열{ci} '{s}' 없음 → '{g.header(ci)}'")
    rows = []
    for ya, yb in g.cells(0):
        name0 = g.text(0, ya, yb)
        subs = [(clean_name(g.text(1, a, b)), a, b) for a, b in g.cells(1, ya, yb)]
        r = {"쪽": pno, "name": name0, "subs": [s[0] for s in subs], "vals": {}, "detail": {}, "bad": []}
        for ci in [2, 10] + list(cols_in):
            cs = g.cells(ci, ya, yb)
            got, det = [], []
            for a, b in cs:
                if a < ya - 1 or b > yb + 1:
                    r["bad"].append(f"열{ci} 칸이 모집단위 경계를 넘음")
                    continue
                v = parse_cell(g.text(ci, a, b, sep=" "))
                if v is None:
                    r["bad"].append(f"열{ci} '{g.text(ci, a, b)}' 판독 불가")
                    continue
                got.append(v)
                sub = [s[0] for s in subs if s[1] >= a - 1 and s[2] <= b + 1]
                det.append(("/".join(sub), v))
            r["vals"][ci] = got
            if len(cs) > 1:
                r["detail"][ci] = det
        is_total = (name0 + "".join(r["subs"])).replace(" ", "") == "총계"
        for ci in ([] if is_total else cols_out):  # 정원외 열: 괄호 아닌 숫자가 있으면 기록만
            for a, b in g.cells(ci, ya, yb):
                v = parse_cell(g.text(ci, a, b, sep=" "))
                if v is None or (v[0] == "in" and v[1]):
                    memo_bad.append(f"{pno}쪽 '{name0}' 정원외 열 {cols_out[ci]} 칸 '{g.text(ci, a, b)}' (괄호 없음, 미수록)")
        rows.append(r)
    return rows


def main():
    if len(sys.argv) != 3:
        raise SystemExit("사용: sogang.py <pdf> <out.json>")
    src, out = sys.argv[1], sys.argv[2]
    memo_bad = []
    with pdfplumber.open(src) as pdf:
        susi_p = js_p = None
        for i, p in enumerate(pdf.pages, 1):
            t = p.extract_text() or ""
            if "2-1. 수시모집 모집인원" in t:
                susi_p = i
            if "2-2. 정시모집 모집인원" in t:
                js_p = i
        if not susi_p or not js_p:
            raise SystemExit(f"표 쪽 찾기 실패: 수시 {susi_p} 정시 {js_p}")
        rows_s = read_table(pdf, susi_p, SUSI_HDR, SUSI_IN, SUSI_OUT, memo_bad)
        rows_j = read_table(pdf, js_p, JS_HDR, JS_IN, JS_OUT, memo_bad)

    def split(rows):
        body, total = [], None
        for r in rows:
            if (r["name"] + "".join(r["subs"])).replace(" ", "") == "총계":
                total = r
            else:
                body.append(r)
        return body, total

    body_s, tot_s = split(rows_s)
    body_j, tot_j = split(rows_j)

    units, order, excluded, breakdown = {}, [], {}, []

    def add(r, part, cols_in):
        name = clean_name(r["name"])
        if r["bad"] or not name:
            memo_bad.append(f"{r['쪽']}쪽 '{name}' 행 판독 불가({part}): {r['bad']}")
            return
        cap = r["vals"][2]
        is_contract = len(cap) == 1 and cap[0][0] == "out"
        if is_contract:
            ex = excluded.setdefault(name, {})
            for ci, spec in cols_in.items():
                n = sum(v for _, v in r["vals"][ci])
                if n:
                    ex[spec[0]] = n
            return
        if name not in units:
            units[name] = {"단과대학": None, "모집단위": name, "계열": None, "인원": {}, "parts": {}, "쪽": r["쪽"]}
            order.append(name)
        u = units[name]
        s = 0
        for ci, spec in cols_in.items():
            vs = r["vals"][ci]
            if any(k == "out" for k, _ in vs):
                memo_bad.append(f"'{name}' {spec[3]} 칸에 괄호(정원외) 숫자 {vs} — 미수록")
            n = sum(v for k, v in vs if k == "in")
            if n:
                u["인원"][spec[0]] = n
                s += n
            if ci in r["detail"] and n:
                breakdown.append(f"{name} {spec[3]} " + ", ".join(f"{a} {v}" for a, (k, v) in r["detail"][ci]))
        tot = r["vals"][10]
        if len(tot) != 1 or tot[0][0] != "in":
            memo_bad.append(f"'{name}' {part} 모집단위별 모집인원 칸 판독 이상: {tot}")
            u["parts"][part] = (None, s)
        else:
            u["parts"][part] = (tot[0][1], s)

    for r in body_s:
        add(r, "수시", SUSI_IN)
    for r in body_j:
        add(r, "정시", JS_IN)

    out_units, part_bad = [], []
    for name in order:
        u = units[name]
        totals = [t for t, _ in u["parts"].values()]
        계 = None if any(t is None for t in totals) else sum(totals)
        if 계 is None:
            검증 = "합계칸없음"
        else:
            ok = all(t == s for t, s in u["parts"].values()) and sum(u["인원"].values()) == 계
            검증 = "합계일치" if ok else "합계불일치"
            if not ok:
                part_bad.append(name + " " + ", ".join(f"{k} 칸 {t} vs 합 {s}" for k, (t, s) in u["parts"].items() if t != s))
        if set(u["parts"]) != {"수시", "정시"}:
            memo_bad.append(f"'{name}' 수시/정시 표 한쪽에만 있음: {sorted(u['parts'])}")
        out_units.append({"단과대학": None, "모집단위": name, "계열": None, "인원": u["인원"], "계": 계,
                          "쪽": u["쪽"], "검증": 검증})

    def colsum(key):
        return sum(u["인원"].get(key, 0) for u in out_units)

    def exsum(key):
        return sum(v.get(key, 0) for v in excluded.values())

    def tot_val(r, ci):
        v = r["vals"][ci]
        return v[0][1] if len(v) == 1 and v[0][0] == "in" else None

    tot_lines = []
    for part, tr, cols in (("수시", tot_s, SUSI_IN), ("정시", tot_j, JS_IN)):
        if not tr:
            tot_lines.append(f"총계 대조: {part} 총 계 행 읽기 실패")
            continue
        p_sum = g_sum = e_sum = 0
        parts = []
        for ci, spec in cols.items():
            pv = tot_val(tr, ci)
            got, ex = colsum(spec[0]), exsum(spec[0])
            parts.append(f"{spec[3]} {pv}-{ex}={got}" + ("" if pv == got + ex else " 불일치"))
            p_sum += pv or 0
            g_sum += got
            e_sum += ex
        allcol = tot_val(tr, 10)
        tot_lines.append(f"총계 대조: {part} {p_sum - e_sum}={g_sum} (PDF 총 계 행 정원내 전형 합 {p_sum}, 모집단위별 모집인원 총계 {allcol}, "
                         f"둘 다 괄호 계약학과 {e_sum} 포함 → 뺀 값과 비교; " + ", ".join(parts) + ")")

    전형 = [dict(zip(("key", "시기", "유형", "전형명", "군"), v)) for v in list(SUSI_IN.values()) + list(JS_IN.values())]
    pages = sorted({susi_p, js_p})
    exc = "; ".join(f"{k} {v}" for k, v in excluded.items())
    메모 = [
        "정원내만 수록",
        "정원외 미수록: 수시 학생부종합(특성화고교졸업자), 정시 수능(농어촌학생·기초생활보장대상자·장애인대상자·특성화고교졸업자) — 전형 안내 쪽 제목에 [정원 외] 표기, 표에는 '( )' 숫자로 표기; 재외국민 특별전형",
        f"정원외 계약학과('( )안의 인원은 정원 외 선발', SK하이닉스 채용조건형) 행 제외: {exc}",
        "모집단위 = 표 왼쪽 '모집단위' 칸. 인문학부·사회과학부·지식융합미디어학부는 여러 학과를 묶은 모집단위이고 수시 일반Ⅰ만 학과별로 나뉘어 있어, 학과별 숫자를 합해 넣음(내역 아래)",
        "일반Ⅰ 학과별 내역: " + ("; ".join(breakdown) if breakdown else "없음"),
        "계 = 수시 표 '모집단위별 모집인원(수시-지정)' + 정시 표 '모집단위별 모집인원(정시-지정)'. 검증은 수시·정시 각각 전형별 합 == 그 칸일 때만 합계일치",
        "단과대학: 표에 단과대학 칸이 없음 → null. 계열: 표기 없음 → null",
        "모집단위 이름 끝 *(교직과정)·각주 번호는 제거",
        "쪽 = 해당 단위가 처음 나온 PDF 파일 쪽 번호(1부터)",
    ] + tot_lines + ([] if not part_bad else ["합계불일치 상세: " + "; ".join(part_bad)]) + memo_bad

    data = {"id": ID, "이름": NAME, "출처쪽": pages, "전형": 전형, "모집단위": out_units, "메모": 메모}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    cnt = {}
    for u in out_units:
        cnt[u["검증"]] = cnt.get(u["검증"], 0) + 1
    print(f"{ID}: 행 {len(out_units)}개, 검증 {cnt}, 출처쪽 {pages}")
    for m in 메모[2:3] + 메모[4:5] + tot_lines + memo_bad:
        print(" ", m)


if __name__ == "__main__":
    main()
