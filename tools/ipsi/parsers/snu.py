#!/usr/bin/env python3
"""서울대학교 2028학년도 입학전형 시행계획 → 모집단위별 정원내 모집인원.

표: '2028학년도 모집단위와 모집인원' (PDF 3~5쪽).
열: 대학 | 모집단위 | 수시 지역균형 | 수시 일반 | 수시 기회균형(사회통합) | 정시'나' 일반 | 합계 | (정원외 3열)
행 구분선이 점선이라 점선 커버리지(30%)로 행 경계를 잡는다.

사용: python3 -I tools/ipsi/parsers/snu.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

ID = "snu"
NAME = "서울대학교"


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


def h_rules(page, xa, xb, y0, y1, cov):
    """열 [xa,xb] 안에서 폭의 cov 이상을 덮는 가로선 y 좌표."""
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


def lead_num(s):
    s = s.replace(" ", "")
    if s in ("", "-", "·"):
        return 0
    m = NUM_RE.match(s)
    return int(m.group(0).replace(",", "")) if m else None


# ---------------------------------------------------------------- 서울대 전용
HEADER_SIG = "사회통합 농어촌 저소득 특수·북한"
# 데이터 열 인덱스(표 열 경계 xs 기준)
C_COLLEGE, C_UNIT, C_JG, C_SI, C_GH, C_JS, C_SUM, C_OUT1 = 0, 1, 2, 3, 4, 5, 6, 7


def find_music_practical(pdf):
    """실기위주전형 쪽의 '수시모집 일반전형(음악대학 …)', '정시모집 ‘나’군 일반전형(음악대학 …)' 단위 목록."""
    susi, jeongsi = set(), set()
    for p in pdf.pages:
        t = p.extract_text() or ""
        if not t.startswith("실기위주전형"):
            continue
        m = re.search(r"수시모집 일반전형\(음악대학 ([^)]+)\)", t)
        if m:
            susi |= {x.strip() for x in m.group(1).split(",")}
        m = re.search(r"정시모집 .나.군 일반전형\(음악대학 ([^)]+)\)", t)
        if m:
            jeongsi |= {x.strip() for x in m.group(1).split(",")}
    return susi, jeongsi


def check_header(words, xs, top, hb):
    def h(i):
        return text_in(words, xs[i], xs[i + 1], top, hb).replace(" ", "")
    expect = {C_UNIT: "모집단위", C_JG: "지역균형", C_SI: "일반", C_GH: "사회통합",
              C_JS: "정시모집", C_SUM: "합계", C_OUT1: "농어촌"}
    for i, s in expect.items():
        if s not in h(i):
            raise SystemExit(f"헤더 확인 실패: 열{i}에 '{s}' 없음 → '{h(i)}'")
    if "기회균형" not in h(C_GH):
        raise SystemExit("헤더 확인 실패: 기회균형 열")


def parse_page(page, pno, memo_bad):
    bbox, xs = main_table(page)
    if len(xs) != 11:
        raise SystemExit(f"{pno}쪽: 열 경계 {len(xs)}개(11 기대) {xs}")
    words = page.extract_words()
    top, bot = bbox[1], bbox[3]
    col0 = h_rules(page, xs[0], xs[1], top, bot, 0.9)
    hb = col0[1]
    check_header(words, xs, top, hb)
    drv = [y for y in h_rules(page, xs[C_SI], xs[C_SI + 1], top, bot, 0.3) if y >= hb - 0.5]
    sub_x = (xs[C_UNIT] + xs[C_UNIT + 1]) / 2  # 학부 | 전공 하위칸 경계
    rows = []
    last_parent, last_cell = None, None
    for ya, yb in zip(drv, drv[1:]):
        mid = (ya + yb) / 2
        cc = cell_of(col0, mid)
        college = clean_name(text_in(words, xs[0], xs[1], cc[0], cc[1])) if cc else ""
        uws = words_in(words, xs[C_UNIT], xs[C_UNIT + 1], ya, yb)
        parent = " ".join(lines_of([w for w in uws if w["x0"] < sub_x]))
        sub = " ".join(lines_of([w for w in uws if w["x0"] >= sub_x]))
        if cc != last_cell:
            last_parent = None
            last_cell = cc
        if sub and not parent:
            parent = last_parent or ""
        if sub and parent:
            last_parent = parent
        elif not sub:
            last_parent = None
        unit = clean_name(parent) + (" " + clean_name(sub) if sub else "")
        unit = unit.strip()
        raw = {c: "".join(w["text"] for w in sorted(words_in(words, xs[c], xs[c + 1], ya, yb), key=lambda w: w["x0"]))
               for c in (C_JG, C_SI, C_GH, C_JS, C_SUM)}
        rows.append({"쪽": pno, "단과대학": college or unit, "모집단위": unit, "raw": raw})
    return rows


def main():
    if len(sys.argv) != 3:
        raise SystemExit("사용: snu.py <pdf> <out.json>")
    src, out = sys.argv[1], sys.argv[2]
    memo_bad = []
    with pdfplumber.open(src) as pdf:
        pages = [i + 1 for i, p in enumerate(pdf.pages) if HEADER_SIG in (p.extract_text() or "")]
        if len(pages) != 3:
            raise SystemExit(f"모집인원 표 쪽을 찾지 못함: {pages}")
        prac_susi, prac_jeongsi = find_music_practical(pdf)
        rows = []
        for pno in pages:
            rows += parse_page(pdf.pages[pno - 1], pno, memo_bad)

    전형 = [
        {"key": "수시_종합_지역균형", "시기": "수시", "유형": "학생부종합", "전형명": "지역균형전형", "군": None},
        {"key": "수시_종합_일반", "시기": "수시", "유형": "학생부종합", "전형명": "일반전형", "군": None},
        {"key": "수시_실기_일반", "시기": "수시", "유형": "실기/실적", "전형명": "일반전형(음악대학 " + ", ".join(sorted(prac_susi)) + ")", "군": None},
        {"key": "수시_종합_기회균형", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형특별전형(사회통합)", "군": None},
        {"key": "정시_수능_일반_나", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "나"},
        {"key": "정시_실기_일반_나", "시기": "정시", "유형": "실기/실적", "전형명": "일반전형(음악대학 " + ", ".join(sorted(prac_jeongsi)) + ")", "군": "나"},
    ]

    units, total_row, subtot_bad, subtot_ok = [], None, [], 0
    acc = {}  # 단과대학 → 열별 단위 합(소계 대조용)
    for r in rows:
        name = r["모집단위"]
        if name == "합계":
            total_row = r
            continue
        if name == "소계":
            cols = (C_JG, C_SI, C_GH, C_JS, C_SUM)
            vals = {c: lead_num(r["raw"][c]) for c in cols}
            got = acc.get(r["단과대학"], {c: 0 for c in cols})
            if vals != got:
                subtot_bad.append(f"{r['단과대학']} 소계 PDF {vals} vs 단위합 {got}")
            else:
                subtot_ok += 1
            continue
        vals = {c: parse_num(r["raw"][c]) for c in (C_JG, C_SI, C_GH, C_JS, C_SUM)}
        if any(v is None for v in vals.values()) or not name:
            memo_bad.append(f"{r['쪽']}쪽 '{name}' 행 숫자 판독 불가: {r['raw']}")
            continue
        a = acc.setdefault(r["단과대학"], {c: 0 for c in (C_JG, C_SI, C_GH, C_JS, C_SUM)})
        for c in a:
            a[c] += vals[c]
        unit_base = name.split(" ")[-1]
        k_si = "수시_실기_일반" if unit_base in prac_susi else "수시_종합_일반"
        k_js = "정시_실기_일반_나" if unit_base in prac_jeongsi else "정시_수능_일반_나"
        인원 = {}
        for k, c in (("수시_종합_지역균형", C_JG), (k_si, C_SI), ("수시_종합_기회균형", C_GH), (k_js, C_JS)):
            if vals[c]:
                인원[k] = vals[c]
        계 = vals[C_SUM]
        검증 = "합계일치" if sum(인원.values()) == 계 else "합계불일치"
        units.append({"단과대학": r["단과대학"], "모집단위": name, "계열": None,
                      "인원": 인원, "계": 계, "쪽": r["쪽"], "검증": 검증})

    # 총계 대조
    memo_total = "총계 대조: 합계 행 없음"
    if total_row:
        tv = {c: lead_num(total_row["raw"][c]) for c in (C_JG, C_SI, C_GH, C_JS, C_SUM)}
        def colsum(keys):
            return sum(u["인원"].get(k, 0) for u in units for k in keys)
        s_jg = colsum(["수시_종합_지역균형"])
        s_si = colsum(["수시_종합_일반", "수시_실기_일반"])
        s_gh = colsum(["수시_종합_기회균형"])
        s_js = colsum(["정시_수능_일반_나", "정시_실기_일반_나"])
        s_all = sum(u["계"] for u in units)
        susi_pdf = tv[C_JG] + tv[C_SI] + tv[C_GH]
        memo_total = (f"총계 대조: 수시 {susi_pdf}={s_jg + s_si + s_gh}, 정시 {tv[C_JS]}={s_js}, 전체 {tv[C_SUM]}={s_all} "
                      f"(열별: 지역균형 {tv[C_JG]}={s_jg}, 일반 {tv[C_SI]}={s_si}, 기회균형 {tv[C_GH]}={s_gh}; "
                      f"PDF 합계 행 기준, 수시 계는 세 열 합)")

    메모 = [
        "정원내만 수록",
        "정원외 미수록: 정시 기회균형특별전형(농어촌·저소득·특수교육대상자/북한이탈주민), 수시 기회균형(사회통합) 농업생명과학대학 정원외 4명 이내(각주 8)",
        "계 = PDF 표 '합계' 열(정원내 수시+정시)",
        f"유형 구분: 실기위주전형 쪽 제목 기준 — 수시 일반전형 실기/실적 단위 {sorted(prac_susi)}, 정시 일반전형 실기/실적 단위 {sorted(prac_jeongsi)}; 나머지 수시 일반은 학생부종합, 정시 일반은 수능위주",
        "계열: PDF에 표기 없음 → null",
        "모집단위 이름 끝 각주 번호(예: 광역1))는 제거; 학부·전공 2칸 단위는 '학부 전공'으로 이어 씀; 대학 칸과 모집단위 칸이 병합된 행(간호대학, 경영대학, 첨단융합학부 등)은 단과대학=모집단위 이름",
        "쪽 = PDF 파일 쪽 번호(1부터)",
        memo_total,
        (f"소계 대조: 소계 행 {subtot_ok}개 모두 단위 합과 일치" if not subtot_bad else "소계 대조 불일치: " + "; ".join(subtot_bad)),
    ] + memo_bad

    data = {"id": ID, "이름": NAME, "출처쪽": pages, "전형": 전형, "모집단위": units, "메모": 메모}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    cnt = {}
    for u in units:
        cnt[u["검증"]] = cnt.get(u["검증"], 0) + 1
    print(f"{ID}: 행 {len(units)}개, 검증 {cnt}")
    print(memo_total)
    for m in 메모[-1 - len(memo_bad):]:
        print(" ", m)


if __name__ == "__main__":
    main()
