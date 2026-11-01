#!/usr/bin/env python3
"""동덕여자대학교 2028 시행계획 파서.

대상 표: "모집시기별 모집인원 총괄표" (PDF 4쪽, 인쇄 2쪽) — 수시·정시 전형별 인원과 행별 '정원내 모집인원' 칸.
보조 대조: 10쪽 수시 '모집단위별 모집인원'의 행별 합계(정원내), 30쪽 정시 같은 표의 행별 합계(정원내),
          6쪽 '전형별 모집인원 변동사항'의 수시·정시·전체 정원내 합계.
표 칸은 pdfplumber 선 격자(cell)로 잡고, 데이터 영역에 세로선이 없는 '대학' 열은 가로선 띠로 읽는다.
사용법: python3 -I tools/ipsi/parsers/dongduk.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "dongduk"
UNIV_NAME = "동덕여자대학교"
MARK = "◉"  # 수시 미충원 인원이 생길 때만 모집(30쪽 각주)

JEONHYEONG = [
    {"key": "수시_종합_동덕창의리더", "시기": "수시", "유형": "학생부종합", "전형명": "동덕창의리더전형", "군": None},
    {"key": "수시_종합_기회균형", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형 특별전형", "군": None},
    {"key": "수시_종합_특성화고재직자", "시기": "수시", "유형": "학생부종합",
     "전형명": "특성화고 등 고졸재직자 특별전형(정원내)", "군": None},
    {"key": "수시_교과_학생부교과우수자", "시기": "수시", "유형": "학생부교과", "전형명": "학생부교과우수자 특별전형", "군": None},
    {"key": "수시_논술_논술우수자", "시기": "수시", "유형": "논술", "전형명": "논술우수자전형", "군": None},
    {"key": "수시_실기_실기우수자", "시기": "수시", "유형": "실기/실적", "전형명": "실기우수자전형", "군": None},
    {"key": "수시_실기_특기자", "시기": "수시", "유형": "실기/실적", "전형명": "특기자 특별전형", "군": None},
    {"key": "정시_수능_수능우수자_가", "시기": "정시", "유형": "수능", "전형명": "수능우수자전형", "군": "가"},
    {"key": "정시_수능_수능우수자_나", "시기": "정시", "유형": "수능", "전형명": "수능우수자전형", "군": "나"},
    {"key": "정시_수능_실기우수자_나", "시기": "정시", "유형": "수능", "전형명": "실기우수자전형", "군": "나"},
    {"key": "정시_실기_실기우수자_나", "시기": "정시", "유형": "실기/실적", "전형명": "실기우수자전형", "군": "나"},
    {"key": "정시_수능_실기우수자_다", "시기": "정시", "유형": "수능", "전형명": "실기우수자전형", "군": "다"},
    {"key": "정시_실기_실기우수자_다", "시기": "정시", "유형": "실기/실적", "전형명": "실기우수자전형", "군": "다"},
    {"key": "정시_종합_특성화고재직자_다", "시기": "정시", "유형": "학생부종합",
     "전형명": "특성화고 등 고졸재직자 특별전형(정원내)", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]
OUT = "정원외"
MIXED = ("실기우수자_나", "실기우수자_다")  # 표에서 '수능⋅실기/실적' 한 열 → 모집단위별로 유형을 나눔
DIRECT_KEYS = [k for k in SUSI_KEYS + JEONGSI_KEYS if "실기우수자" not in k or k.startswith("수시_")]

COLS_P4 = {
    ("정원내모집인원",): "계",
    ("수시모집", "정원내", "학생부(종합)", "동덕창의리더"): "수시_종합_동덕창의리더",
    ("수시모집", "정원내", "학생부(종합)", "기회균형"): "수시_종합_기회균형",
    ("수시모집", "정원내", "학생부(종합)", "특성화고등고졸재직자"): "수시_종합_특성화고재직자",
    ("수시모집", "정원내", "학생부(교과)", "학생부교과우수자"): "수시_교과_학생부교과우수자",
    ("수시모집", "정원내", "논술", "논술우수자"): "수시_논술_논술우수자",
    ("수시모집", "정원내", "실기/실적", "실기우수자"): "수시_실기_실기우수자",
    ("수시모집", "정원내", "실기/실적", "특기자"): "수시_실기_특기자",
    ("수시모집", "정원외", "학생부(종합)", "특성화고등고졸재직자"): OUT,
    ("정시모집", "가군", "정원내", "수능", "수능우수자"): "정시_수능_수능우수자_가",
    ("정시모집", "가군", "정원외", "수능", "농어촌학생"): OUT,
    ("정시모집", "가군", "정원외", "수능", "특성화고교"): OUT,
    ("정시모집", "가군", "정원외", "수능", "기회균등"): OUT,
    ("정시모집", "나군", "정원내", "수능", "수능우수자"): "정시_수능_수능우수자_나",
    ("정시모집", "나군", "정원내", "수능⋅실기/실적", "실기우수자"): "실기우수자_나",
    ("정시모집", "다군", "정원내", "수능⋅실기/실적", "실기우수자"): "실기우수자_다",
    ("정시모집", "다군", "정원내", "학생부(종합)", "특성화고등고졸재직자"): "정시_종합_특성화고재직자_다",
    ("정시모집", "다군", "정원외", "학생부(종합)", "특성화고등고졸재직자"): OUT,
}


def norm(s):
    return re.sub(r"\s+", "", s or "")


def to_int(s):
    s = norm(s).replace(",", "")
    if s in ("", "-", MARK):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {s!r}")


def cell_text(chars, box, line_sep=""):
    x0, top, x1, bot = box
    cs = [c for c in chars
          if x0 <= (c["x0"] + c["x1"]) / 2 <= x1 and top <= (c["top"] + c["bottom"]) / 2 <= bot]
    lines = []
    for c in sorted(cs, key=lambda c: (c["top"], c["x0"])):
        if lines and abs(lines[-1][0] - c["top"]) <= 2:
            lines[-1][1].append(c)
        else:
            lines.append([c["top"], [c]])
    return line_sep.join("".join(c["text"] for c in sorted(lc, key=lambda c: c["x0"])) for _, lc in lines).strip()


def dedup(vals, tol=1.0):
    out = []
    for v in sorted(vals):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def read_grid(page, t, colspec, label):
    """모집단위 머리글이 있는 표 → (열 목록, 행 목록[{대학, 학부, 모집단위, vals}], 총계 vals)."""
    chars, cells = page.chars, t.cells

    def find_hdr(word):
        cs = [c for c in cells if norm(cell_text(chars, c)) == word]
        return cs[0] if len(cs) == 1 else None

    mh, hh, dh = find_hdr("모집단위"), find_hdr("학부"), find_hdr("대학")
    if not (mh and hh and dh):
        return None
    data_top = mh[3]
    leaves = sorted([c for c in cells if abs(c[3] - data_top) < 0.6 and c[0] >= mh[2] - 0.5], key=lambda c: c[0])
    cols, unknown = [], []
    for lf in leaves:
        xm = (lf[0] + lf[2]) / 2
        path = tuple(norm(cell_text(chars, c)) for c in sorted(cells, key=lambda c: c[1])
                     if c[0] <= xm <= c[2] and c[3] <= data_top + 0.6)
        if path in colspec:
            cols.append((lf[0], lf[2], colspec[path]))
        else:
            unknown.append(path)
    if unknown:
        raise SystemExit(f"{label}: 모르는 머리글 {unknown}")
    roles = [r for *_, r in cols]
    if sorted(set(roles)) != sorted(set(colspec.values())) or len([r for r in roles if r != OUT]) != \
            len(set(r for r in roles if r != OUT)):
        raise SystemExit(f"{label}: 머리글 열 구성 다름 {roles}")

    def covering(x0, x1, ym):
        xm = (x0 + x1) / 2
        cs = [c for c in cells if c[0] <= xm <= c[2] and c[1] - 0.5 <= ym <= c[3] + 0.5 and c[1] >= data_top - 0.5]
        return cs[0] if len(cs) == 1 else None

    ys = dedup([c[1] for c in cells if c[1] >= data_top - 0.5] + [c[3] for c in cells if c[3] > data_top + 0.5])
    # 대학 열: 가로선 띠
    dxm = (dh[0] + dh[2]) / 2
    hy = dedup([e["top"] for e in page.edges if e["orientation"] == "h" and e["x0"] - 0.5 <= dxm <= e["x1"] + 0.5
                and data_top - 1 <= e["top"] <= ys[-1] + 1])

    def college_at(ym):
        for a, b in zip(hy, hy[1:]):
            if a <= ym <= b:
                return cell_text(chars, (dh[0] - 3, a, dh[2], b))
        return ""

    rows, total = [], None
    for top, bot in zip(ys, ys[1:]):
        ym = (top + bot) / 2
        hc = covering(hh[0], hh[2], ym)
        mc = covering(mh[0], mh[2], ym)
        vals = {}
        for x0, x1, role in cols:
            c = covering(x0, x1, ym)
            txt = cell_text(chars, c) if c else ""
            if c and role != OUT and (c[1] < top - 0.5 or c[3] > bot + 0.5):
                raise SystemExit(f"{label} y={top:.0f}: {role} 칸이 세로 병합")
            if role == OUT:
                continue
            vals[role] = txt
        if hc is None and mc is None:
            # 총계 행(대학~모집단위 칸이 비어 있거나 한 칸)
            left = cell_text(chars, (dh[0] - 3, top, mh[2], bot))
            if norm(left) in ("", "총계"):
                if total is not None:
                    raise SystemExit(f"{label}: 총계 행 2개")
                total = vals
                continue
            raise SystemExit(f"{label} y={top:.0f}: 이름 칸 없음")
        if hc is not None and abs(hc[2] - mh[2]) < 1:
            hakbu, name = None, cell_text(chars, hc)  # 학부 칸이 모집단위 칸까지 병합
        else:
            hakbu = cell_text(chars, hc) if hc else None
            name = cell_text(chars, mc) if mc else ""
        if norm(name) == "총계":
            total = vals
            continue
        if not name:
            raise SystemExit(f"{label} y={top:.0f}: 이름 없음")
        rows.append({"대학": college_at(ym), "학부": hakbu, "모집단위": name, "vals": vals})
    return cols, rows, total


def find_page_table(pdf, colspec, label, must_text):
    for pno, page in enumerate(pdf.pages, start=1):
        if must_text not in norm(page.extract_text() or ""):
            continue
        for t in page.find_tables():
            try:
                r = read_grid(page, t, colspec, f"{pno}쪽")
            except SystemExit:
                continue
            if r:
                return pno, r
    raise SystemExit(f"{label} 표를 찾지 못함")


def side_sums(pdf, title, first_hdr):
    """10쪽/30쪽 표: 행별 '합계 > 정원내' 칸 → {모집단위: 값}, 총계."""
    for pno, page in enumerate(pdf.pages, start=1):
        txt = norm(page.extract_text() or "")
        if "모집단위별모집인원" not in txt or title not in txt:
            continue
        for t in page.find_tables():
            chars, cells = page.chars, t.cells
            mh = [c for c in cells if norm(cell_text(chars, c)) == "모집단위"]
            if len(mh) != 1:
                continue
            data_top = mh[0][3]
            leaves = sorted([c for c in cells if abs(c[3] - data_top) < 0.6 and c[0] >= mh[0][2] - 0.5],
                            key=lambda c: c[0])
            col = None
            for lf in leaves:
                xm = (lf[0] + lf[2]) / 2
                path = tuple(norm(cell_text(chars, c)) for c in sorted(cells, key=lambda c: c[1])
                             if c[0] <= xm <= c[2] and c[3] <= data_top + 0.6)
                if path == ("합계", "정원내"):
                    col = lf
                if path and path[0] == first_hdr:
                    found = True
            if col is None:
                continue
            spec = {("2028학년도정원내모집인원",): "계", ("합계", "정원내"): "합계내"}
            # 나머지 열은 정원외로 무시
            for lf in leaves:
                xm = (lf[0] + lf[2]) / 2
                path = tuple(norm(cell_text(chars, c)) for c in sorted(cells, key=lambda c: c[1])
                             if c[0] <= xm <= c[2] and c[3] <= data_top + 0.6)
                spec.setdefault(path, OUT)
            r = read_grid(page, t, spec, f"{pno}쪽")
            if not r:
                continue
            _, rows, total = r
            return pno, {norm(x["모집단위"]): x["vals"]["합계내"] for x in rows}, total["합계내"] if total else None
    return None, {}, None


def silgi_ratio(pdf):
    """정시 '수능 및 실기/실적[실기우수자전형]' 안내의 '3. 전형요소 및 반영비율' 블록들.

    각 블록: '□ <군> <대학> <모집단위들>' 줄 다음 머리글 '... 수능 실기 계', '전형요소별 반영비율 a% b% ...'.
    돌려주는 값: [(군, 모집단위 글자, 수능%, 실기%)], 쪽 목록. 섹션은 제목 줄이 나온 쪽부터 '4. 실기고사' 줄까지.
    """
    out, pages = [], []
    started = False
    for pno, page in enumerate(pdf.pages, start=1):
        lines = (page.extract_text() or "").split("\n")
        if not started:
            if any(l.strip().startswith("수능 및 실기/실적[실기우수자전형]") for l in lines):
                started = True
            else:
                continue
        hit = False
        cur = None
        for k, l in enumerate(lines):
            if l.startswith("4. 실기고사"):
                if hit:
                    pages.append(pno)
                return out, pages
            if l.startswith("□"):
                cur = l[1:].strip()
                continue
            if cur is not None and re.match(r"^[가나다]군\s", l):
                cur += " " + l.strip()  # □ 줄이 두 줄로 이어지는 경우
                continue
            if cur and l.startswith("전형요소별 반영비율"):
                pc = [int(x) for x in re.findall(r"(\d+)%", l)]
                head = " ".join(lines[max(0, k - 3):k])
                if not re.search(r"수능\s+실기", head):
                    raise SystemExit(f"{pno}쪽 반영비율 머리글 순서 다름: {head}")
                for m in re.finditer(r"([가나다])군\s+(\S+대학)\s+(.+?)(?=,?\s*[가나다]군\s|$)", cur):
                    out.append((m.group(1), m.group(3), pc[0], pc[1]))
                hit = True
                cur = None
        if hit:
            pages.append(pno)
    return out, pages


def p6_split(pdf):
    """6쪽 '전형별 모집인원 변동사항': 정시 실기우수자전형의 군별 수능/실기·실적 인원."""
    for pno, page in enumerate(pdf.pages, start=1):
        if "전형별모집인원변동사항" not in norm(page.extract_text() or ""):
            continue
        for t in page.extract_tables():
            gun = typ = None
            res = {}
            for r in t:
                if len(r) < 6:
                    break
                if r[1]:
                    gun = norm(r[1])
                if r[3]:
                    typ = norm(r[3])
                if norm(r[4]) == "실기우수자전형" and gun in ("나군", "다군") and norm(r[2] or "정원내") == "정원내":
                    res[(gun[0], typ)] = to_int(norm(r[5]).rstrip("명"))
            if res:
                return pno, res
    return None, {}


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        pno, (cols, rows, total) = find_page_table(pdf, COLS_P4, "모집시기별 모집인원 총괄표", "총괄표")
        s_pno, s_side, s_side_total = side_sums(pdf, "수시모집", "수시모집")
        j_pno, j_side, j_side_total = side_sums(pdf, "정시모집", "정시모집")
        ratios, ratio_pages = silgi_ratio(pdf)
        split_pno, split = p6_split(pdf)
        p6 = None
        for i, page in enumerate(pdf.pages, start=1):
            t = norm(page.extract_text() or "")
            if "전형별모집인원변동사항" in t:
                m = re.findall(r"정원내:([\d,]+)명정원내:[\d,]+명", t)
                if len(m) >= 3:  # 목차 쪽은 숫자가 없어 건너뜀
                    p6 = (i, [int(x.replace(",", "")) for x in m[:3]])
                    break

    units, marks, aux_bad, typed = [], [], [], []
    aux_ok = 0
    for r in rows:
        v = r["vals"]
        inwon = {}
        for k in DIRECT_KEYS + list(MIXED):
            if norm(v[k]) == MARK:
                marks.append(f"{r['모집단위']} 정시 실기우수자({k[-1]}군)" if k in MIXED else f"{r['모집단위']} {k}")
            n = to_int(v[k])
            if not n:
                continue
            if k in MIXED:
                gun = k[-1]
                base = re.sub(r"\(야\)$", "", r["모집단위"])
                found = [(a, b) for g, names, a, b in ratios if g == gun and base in names]
                if not found or len({(a > b) for a, b in found}) != 1:
                    raise SystemExit(f"{r['모집단위']}: 정시 실기우수자 {gun}군 반영비율 못 찾음/엇갈림 {found}")
                a, b = found[0]
                k2 = f"정시_수능_실기우수자_{gun}" if a > b else f"정시_실기_실기우수자_{gun}"
                typed.append(f"{r['모집단위']} {gun}군 {n}(수능{a}%·실기{b}%→{'수능' if a > b else '실기/실적'})")
                inwon[k2] = n
            else:
                inwon[k] = n
        gye = to_int(v["계"]) if norm(v["계"]) else None
        name = r["모집단위"]
        # 보조 대조: 10쪽 수시 합계(정원내), 30쪽 정시 합계(정원내)
        s = sum(inwon.get(k, 0) for k in SUSI_KEYS)
        j = sum(inwon.get(k, 0) for k in JEONGSI_KEYS)
        sv, jv = s_side.get(norm(name)), j_side.get(norm(name))
        if sv is None or jv is None:
            aux_bad.append(f"{name}(10/30쪽 행 없음)")
        elif to_int(sv) == s and to_int(jv) == j:
            aux_ok += 1
        else:
            aux_bad.append(f"{name}(수시 {sv} vs {s}, 정시 {jv} vs {j})")
        units.append({
            "단과대학": r["대학"] or None,
            "모집단위": name,
            "계열": None,
            "인원": inwon,
            "계": gye,
            "쪽": pno,
            "검증": "합계칸없음" if gye is None else ("합계일치" if sum(inwon.values()) == gye else "합계불일치"),
        })

    used = {k for u in units for k in u["인원"]}
    jlist = [j for j in JEONHYEONG if j["key"] in used]
    unused = [j["key"] for j in JEONHYEONG if j["key"] not in used]
    memo = [
        f"출처: p{pno} '모집시기별 모집인원 총괄표'. 정원내만 수록: 수시 학생부종합 특성화고 등 고졸재직자(정원외), "
        "재외국민과 외국인 특별전형, 정시 가군 농어촌학생·특성화고교·기회균등, 다군 특성화고 등 고졸재직자(정원외)는 넣지 않음",
        "특성화고 등 고졸재직자 특별전형은 정원내 열(금융회계학부 수시 6)만 수록",
        "계 = 표의 '정원내 모집인원' 칸(행별 정원내 수시+정시 합). p3 입학정원 합 1,577과 다르며 p6 각주 '정원내 이월인원 "
        "2026→2028학년도 2명'",
        "정시 나·다군 '수능⋅실기/실적 > 실기우수자' 열은 표에서 한 열이지만 p6 변동사항 표가 수능/실기·실적으로 나눠 적음. "
        f"모집단위별 유형은 p{'~'.join(str(x) for x in ratio_pages)} 실기우수자전형 전형요소 반영비율에서 수능 비율 > 실기 비율이면 수능, "
        "아니면 실기/실적으로 정함(인원 숫자는 표 그대로, 유형만 나눔)",
        "계열: 표에 계열 칸 없음(p3 '자율 인문 자연' 칸은 전공 선택 가능 여부 표시) → null",
        "단과대학: 표의 대학 칸 글자를 이어 씀. 모집단위: 표의 모집단위 칸(학부 칸이 모집단위 칸까지 병합된 행은 그 칸 글자)",
    ]
    if typed:
        memo.append("정시 실기우수자 유형 판정: " + "; ".join(typed))
    if split:
        chk = []
        for (g, typ), n in sorted(split.items()):
            key = f"정시_{'수능' if typ == '수능' else '실기'}_실기우수자_{g}"
            mine = sum(u["인원"].get(key, 0) for u in units)
            chk.append(f"{g}군 {typ} {n}={mine}")
        memo.append(f"p{split_pno} 실기우수자 유형별 인원 대조: " + ", ".join(chk))
    if marks:
        memo.append(f"'{MARK}' 칸(수시 미충원 인원 발생 시에만 모집, 숫자 없음) → 0: " + ", ".join(marks))
    if unused:
        memo.append("표에 열은 있으나 숫자가 없어 전형 목록에서 뺀 key: " + ", ".join(unused))
    memo.append(f"보조 대조(p{s_pno} 수시 표 '합계 정원내' 칸 = 수시 합, p{j_pno} 정시 표 '합계 정원내' 칸 = 정시 합): "
                f"{aux_ok}행 일치" + (", 불일치 " + "; ".join(aux_bad) if aux_bad else ""))
    s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
    j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
    tot_gye = to_int(total["계"]) if total else None
    if p6:
        memo.append(f"총계 대조: 수시 {p6[1][0]}={s_me}, 정시 {p6[1][1]}={j_me}, 전체 {p6[1][2]}={s_me + j_me} "
                    f"(p{p6[0]} 전형별 모집인원 변동사항 정원내 합계; p{pno} 총계 행 정원내 모집인원 {tot_gye}, "
                    f"p{s_pno} 수시 총계 정원내 {s_side_total}, p{j_pno} 정시 총계 정원내 {j_side_total})")
    if total:
        bad = [k for k in DIRECT_KEYS if to_int(total[k]) != sum(u["인원"].get(k, 0) for u in units)]
        for k in MIXED:
            mine = sum(u["인원"].get(f"정시_수능_실기우수자_{k[-1]}", 0) + u["인원"].get(f"정시_실기_실기우수자_{k[-1]}", 0)
                       for u in units)
            if to_int(total[k]) != mine:
                bad.append(k)
        memo.append(f"전형별 열 합 대조(p{pno} 총계 행): " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)))

    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": sorted({pno, s_pno, j_pno, split_pno, *ratio_pages} - {None}), "전형": jlist,
           "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(units)}행 → {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: dongduk.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
