#!/usr/bin/env python3
"""명지대학교 2028 시행계획 파서.

대상 표: "Ⅲ. 2028학년도 전형별 모집인원" — 1. 인문캠퍼스(PDF 8쪽), 2. 자연캠퍼스(PDF 9쪽).
  - 칸은 pdfplumber 선 격자(cell), 글자는 중심 좌표로 칸에 넣는다.
  - 크기 6.5pt 미만 글자(각주 번호 위첨자 '5)', '2)' 등)는 숫자에서 뺀다.
  - 정원내 전형 칸이 여러 모집단위 행에 걸쳐 세로 병합된 경우(크리스천리더, 사회적배려대상자, 정시 일반 등 단과대학 단위 선발)
    개별 행에 나누지 않고 그 병합 범위(단과대학)를 모집단위로 한 행을 따로 만든다.
  - 데이터 영역에 세로선이 없는 '단과대학' 열은 가로선 띠로 읽는다.
대조: 9쪽 '총 계' 행, 각 쪽 캠퍼스 소계 행, 3쪽 대학입학전형 요약.
사용법: python3 -I tools/ipsi/parsers/mju.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "mju"
UNIV_NAME = "명지대학교"
SMALL = 6.5  # 이보다 작은 글자 = 각주 위첨자
OUT = "정원외"

JEONHYEONG = [
    {"key": "수시_교과_학교장추천", "시기": "수시", "유형": "학생부교과", "전형명": "학교장추천전형", "군": None},
    {"key": "수시_교과_교과면접", "시기": "수시", "유형": "학생부교과", "전형명": "교과면접전형", "군": None},
    {"key": "수시_교과_기회균형", "시기": "수시", "유형": "학생부교과", "전형명": "기회균형전형", "군": None},
    {"key": "수시_교과_만학도", "시기": "수시", "유형": "학생부교과", "전형명": "만학도전형", "군": None},
    {"key": "수시_종합_명지인재면접", "시기": "수시", "유형": "학생부종합", "전형명": "명지인재면접전형", "군": None},
    {"key": "수시_종합_명지인재서류", "시기": "수시", "유형": "학생부종합", "전형명": "명지인재서류전형", "군": None},
    {"key": "수시_종합_크리스천리더", "시기": "수시", "유형": "학생부종합", "전형명": "크리스천리더전형", "군": None},
    {"key": "수시_종합_사회적배려대상자", "시기": "수시", "유형": "학생부종합", "전형명": "사회적배려대상자전형", "군": None},
    {"key": "수시_실기_실기우수자", "시기": "수시", "유형": "실기/실적", "전형명": "실기우수자전형", "군": None},
    {"key": "수시_실기_체육특기자", "시기": "수시", "유형": "실기/실적", "전형명": "체육특기자전형", "군": None},
    {"key": "정시_수능_일반_가", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "가"},
    {"key": "정시_수능_일반_나", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "나"},
    {"key": "정시_수능_실기_나", "시기": "정시", "유형": "수능", "전형명": "실기전형", "군": "나"},
    {"key": "정시_실기_실기우수자_나", "시기": "정시", "유형": "실기/실적", "전형명": "실기우수자전형", "군": "나"},
    {"key": "정시_수능_일반_다", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "다"},
    {"key": "정시_수능_실기_다", "시기": "정시", "유형": "수능", "전형명": "실기전형", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]
# 3쪽 요약표 전형명 → key (정원외는 대조에서 뺌)
SUMMARY = {"학교장추천": "수시_교과_학교장추천", "교과면접": "수시_교과_교과면접", "기회균형": "수시_교과_기회균형",
           "만학도": "수시_교과_만학도", "명지인재면접": "수시_종합_명지인재면접", "명지인재서류": "수시_종합_명지인재서류",
           "크리스천리더": "수시_종합_크리스천리더", "사회적배려대상자": "수시_종합_사회적배려대상자",
           "실기우수자": "수시_실기_실기우수자", "체육특기자": "수시_실기_체육특기자"}

SUSI_NAMES = [  # (머리글 이름 부분열, key) — 머리글 칸에 옆 칸 글자가 섞여 들어와 부분열로 비교
    ("학교장추천", "수시_교과_학교장추천"), ("교과면접", "수시_교과_교과면접"), ("기회균형", "수시_교과_기회균형"),
    ("특성화고등졸재직자", OUT), ("특성화고교", OUT), ("만학도", "수시_교과_만학도"), ("특수교육대상자", OUT),
    ("명지인재면접", "수시_종합_명지인재면접"), ("명지인재서류", "수시_종합_명지인재서류"),
    ("크리스천리더", "수시_종합_크리스천리더"), ("사회적배려대상자", "수시_종합_사회적배려대상자"),
    ("농어촌학생", OUT), ("실기우수자", "수시_실기_실기우수자"), ("체육특기자", "수시_실기_체육특기자"),
    ("재외국민", OUT),
]


def norm(s):
    return re.sub(r"\s+", "", s or "")


def subseq(word, s):
    it = iter(s)
    return all(ch in it for ch in word)


def to_int(s):
    s = norm(s).replace(",", "")
    if s in ("", "-"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {s!r}")


def dedup(vals, tol=1.0):
    out = []
    for v in sorted(vals):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def cell_text(chars, box, small=True):
    """칸 안 글자를 줄 단위로 이어 붙인다. small=False면 각주 위첨자(작은 글자)를 뺀다."""
    x0, top, x1, bot = box
    cs = [c for c in chars
          if x0 <= (c["x0"] + c["x1"]) / 2 <= x1 and top <= (c["top"] + c["bottom"]) / 2 <= bot
          and (small or c["size"] >= SMALL)]
    lines = []
    for c in sorted(cs, key=lambda c: (c["top"], c["x0"])):
        if lines and abs(lines[-1][0] - c["top"]) <= 2:
            lines[-1][1].append(c)
        else:
            lines.append([c["top"], [c]])
    return "".join("".join(c["text"] for c in sorted(lc, key=lambda c: c["x0"])) for _, lc in lines).strip()


def has_small(chars, box):
    x0, top, x1, bot = box
    return [c["text"] for c in chars if x0 <= (c["x0"] + c["x1"]) / 2 <= x1
            and top <= (c["top"] + c["bottom"]) / 2 <= bot and c["size"] < SMALL]


def classify(path):
    p = [norm(x) for x in path]
    if not p:
        return None
    if p[0] == "수시":
        name = p[2] if p[1] != "재외국민" else "재외국민"
        jw = p[-1]
        for word, key in SUSI_NAMES:
            if subseq(word, name):
                if key != OUT and "정원내" not in jw:
                    raise SystemExit(f"정원내 아닌 열인데 정원외 목록에 없음: {path}")
                if key == OUT and "정원외" not in jw:
                    raise SystemExit(f"정원외 표시 없는 열: {path}")
                return key
        return None
    if p[0] == "정시" and len(p) >= 5:
        gun, typ, name, jw = p[1], p[2], p[3], p[4]
        if gun not in ("가", "나", "다") or "정원내" not in jw:
            return None
        if typ == "수능" and subseq("일반", name):
            return f"정시_수능_일반_{gun}"
        if typ == "수능" and name == "실기":
            return f"정시_수능_실기_{gun}"
        if typ == "실기/실적" and name == "실기우수자":
            return f"정시_실기_실기우수자_{gun}"
    return None


def read_page(pno, page, t, full_text, notes):
    chars, cells, edges = page.chars, t.cells, page.edges
    m = re.search(r"\d\.\s*(인문캠퍼스|자연캠퍼스)", page.extract_text() or "")
    if not m:
        raise SystemExit(f"{pno}쪽 캠퍼스 제목 없음")
    campus = m.group(1)
    mh = [c for c in cells if norm(cell_text(chars, c)) == "모집단위"]
    dh = [c for c in cells if norm(cell_text(chars, c)) == "단과대학"]
    if len(mh) != 1 or len(dh) != 1:
        raise SystemExit(f"{pno}쪽 머리글 칸(모집단위/단과대학) 못 찾음")
    mh, dh = mh[0], dh[0]
    # 머리글 맨 아래 줄 = 정원내/정원외 칸들의 아래선
    leaves0 = [c for c in cells if c[0] >= mh[2] - 0.5 and norm(cell_text(chars, c)) in ("정원내", "정원외")]
    data_top = max(c[3] for c in leaves0)
    leaves = sorted([c for c in cells if abs(c[3] - data_top) < 0.6 and c[0] >= mh[2] - 0.5], key=lambda c: c[0])
    cols = []
    for lf in leaves:
        xm = (lf[0] + lf[2]) / 2
        path = [cell_text(chars, c) for c in sorted(cells, key=lambda c: c[1])
                if c[0] <= xm <= c[2] and c[3] <= data_top + 0.6]
        key = classify(path)
        if key is None:
            raise SystemExit(f"{pno}쪽 모르는 머리글 x={lf[0]:.0f}: {path}")
        cols.append((lf[0], lf[2], key))
    in_keys = [k for *_, k in cols if k != OUT]
    if len(in_keys) != len(set(in_keys)):
        raise SystemExit(f"{pno}쪽 같은 전형 열 중복 {in_keys}")
    name_x0, name_x1 = mh[0], mh[2]

    # 행 띠: 이름 영역 안에 완전히 들어가는 칸들의 위·아래 선
    name_cells = [c for c in cells if c[0] >= name_x0 - 0.5 and c[2] <= name_x1 + 0.5 and c[1] >= data_top - 0.5]
    ys = dedup([c[1] for c in name_cells] + [c[3] for c in name_cells])
    total_cells = [c for c in cells if c[0] < name_x0 - 0.5 and c[1] >= data_top - 0.5]  # 소계·총계 행 이름 칸
    ys = dedup(ys + [c[1] for c in total_cells] + [c[3] for c in total_cells])
    bands = list(zip(ys, ys[1:]))

    # 단과대학 열 가로선 띠
    dxm = (dh[0] + dh[2]) / 2
    hy = dedup([e["top"] for e in edges if e["orientation"] == "h" and e["x0"] - 0.5 <= dxm <= e["x1"] + 0.5
                and data_top - 1 <= e["top"] <= ys[-1] + 1])
    cbands = list(zip(hy, hy[1:]))

    def college_band(ym):
        for a, b in cbands:
            if a <= ym <= b:
                return a, b
        return None

    def college_name(band):
        raw = norm(cell_text(chars, (dh[0] - 3, band[0], dh[2], band[1])))
        if not raw:
            return ""
        full = raw + "대학"
        return full if not raw.endswith("칼리지") and full in full_text else raw

    def covering(x0, x1, ym):
        xm = (x0 + x1) / 2
        cs = [c for c in cells if c[0] <= xm <= c[2] and c[1] - 0.5 <= ym <= c[3] + 0.5 and c[1] >= data_top - 0.5]
        return cs[0] if len(cs) == 1 else None

    rows, groups, sums = [], {}, {}
    for top, bot in bands:
        ym = (top + bot) / 2
        tc = [c for c in total_cells if c[1] - 0.5 <= ym <= c[3] + 0.5]
        vals = {}
        cellmap = {}
        for x0, x1, key in cols:
            c = covering(x0, x1, ym)
            if c is None:
                # 칸 테두리 선이 빠진 곳: 열 x 범위 × 행 띠에서 바로 읽음
                box = (x0, top, x1, bot)
                txt = cell_text(chars, box, small=False)
                if key != OUT and norm(txt) not in ("", "-"):
                    notes.append(f"{pno}쪽 y={top:.0f} {key}: 칸 테두리 없음 → 열·행 범위 글자 '{txt}' 사용")
                c = box
            cellmap[key] = c
            txt = cell_text(chars, c, small=False)
            if key == OUT:
                continue
            if has_small(chars, c):
                notes.append(f"{pno}쪽 {key} 칸 각주 위첨자 '{''.join(has_small(chars, c))}' 뺌 (본문 숫자 {txt})")
            vals[key] = (to_int(txt), c)
        if tc:
            label = norm(cell_text(chars, tc[0]))
            sums[label] = {k: v for k, (v, _) in vals.items()}
            continue
        parts = [cell_text(chars, c) for c in sorted([c for c in name_cells if c[1] - 0.5 <= ym <= c[3] + 0.5],
                                                       key=lambda c: c[0])]
        parts = [re.sub(r"\s*<", " <", re.sub(r",(?=\S)", ", ", p)) for p in parts if p]
        if not parts:
            raise SystemExit(f"{pno}쪽 y={top:.0f} 이름 없음")
        name = " ".join(parts)
        cb = college_band(ym)
        college = college_name(cb) if cb else ""
        inwon = {}
        for key, (v, c) in vals.items():
            if not v:
                continue
            if c[1] < top - 1 or c[3] > bot + 1:
                gk = (round(c[1], 1), round(c[3], 1))
                g = groups.setdefault(gk, {"인원": {}, "rows": [], "box": c, "college": college, "cband": cb})
                if key in g["인원"] and g["인원"][key] != v:
                    raise SystemExit(f"{pno}쪽 병합 칸 값 충돌 {key}")
                g["인원"][key] = v
                continue
            inwon[key] = v
        rows.append({"단과대학": f"{campus} · {college}" if college else campus, "모집단위": name,
                     "인원": inwon, "y": ym, "college": college, "cband": cb})

    # 병합 칸 그룹 → 그 범위에 든 행 이름, 그룹 이름
    out = []
    group_rows = []
    for gk, g in groups.items():
        members = [r for r in rows if gk[0] - 1 <= r["y"] <= gk[1] + 1]
        g["rows"] = members
        cb = g["cband"]
        if cb and abs(cb[0] - gk[0]) < 1.5 and abs(cb[1] - gk[1]) < 1.5 and g["college"]:
            gname = g["college"]
        else:
            gname = f"{members[0]['모집단위']}~{members[-1]['모집단위']}"
        group_rows.append((max(r["y"] for r in members), {
            "단과대학": f"{campus} · {g['college']}" if g["college"] else campus,
            "모집단위": gname, "인원": g["인원"], "y": max(r["y"] for r in members) + 0.01,
            "members": [r["모집단위"] for r in members]}))
    allrows = rows + [gr for _, gr in group_rows]
    allrows.sort(key=lambda r: r["y"])
    return campus, allrows, sums


def read_summary(pdf):
    """3쪽 대학입학전형 요약: 전형명 → 모집인원, 수시 합계, 정시 소계."""
    for pno, page in enumerate(pdf.pages, start=1):
        txt = page.extract_text() or ""
        if "대학입학전형 요약" not in txt or "수시 합계" not in txt:  # 목차 쪽 제외
            continue
        per = {}
        for line in txt.split("\n"):
            for name in SUMMARY:
                m = re.match(rf"^(?:\S+\s+){{0,2}}{name}\s+(\d+)\b", line.strip())
                if m and name not in per:
                    per[name] = int(m.group(1))
        mj = re.search(r"정시 소계\s+([\d,]+)", txt)
        jeong = int(mj.group(1).replace(",", "")) if mj else None
        return pno, per, jeong
    return None, {}, None


def main(pdf_path, out_path):
    notes = []
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "".join(norm(p.extract_text() or "") for p in pdf.pages)
        units, pages, all_sums, group_memo = [], [], {}, []
        for pno, page in enumerate(pdf.pages, start=1):
            txt = page.extract_text() or ""
            # 9쪽(자연캠퍼스)에는 장 제목이 없으므로 캠퍼스 소제목 + 표 머리글로 찾는다
            if not re.search(r"\d\.\s*(인문|자연)캠퍼스", txt) or "캠퍼스 소계" not in txt:
                continue
            for t in page.find_tables():
                hdr = norm("".join(c or "" for c in (t.extract() or [[]])[0]))
                if "모집단위" not in hdr or "수시" not in hdr:
                    continue
                campus, rows, sums = read_page(pno, page, t, full_text, notes)
                pages.append(pno)
                all_sums.update(sums)
                for r in rows:
                    if not r["인원"]:
                        raise SystemExit(f"{pno}쪽 {r['모집단위']}: 정원내 인원 없음")
                    if "members" in r:
                        group_memo.append(f"{r['단과대학']} '{r['모집단위']}' = {', '.join(r['members'])} 공통 병합 칸 "
                                          + ", ".join(f"{k} {v}" for k, v in r["인원"].items()))
                    units.append({"단과대학": r["단과대학"], "모집단위": r["모집단위"], "계열": None,
                                  "인원": r["인원"], "계": None, "쪽": pno, "검증": "합계칸없음"})
        s_pno, per, jeong_sum = read_summary(pdf)
    if len(pages) != 2:
        raise SystemExit(f"캠퍼스 표 {len(pages)}개")

    used = {k for u in units for k in u["인원"]}
    jlist = [j for j in JEONHYEONG if j["key"] in used]
    memo = [
        f"출처: p{pages[0]} 인문캠퍼스, p{pages[1]} 자연캠퍼스 '전형별 모집인원' 표. 단과대학 = '<캠퍼스> · <단과대학>'",
        "정원내만 수록(표 맨 아래 머리글 '정원내' 열). 정원외 열(학생부교과 특성화고교·특성화고등졸재직자·특수교육대상자, "
        "학생부종합 농어촌학생, 재외국민)과 정시 이월 전용 전형(수능 농어촌학생·특성화고교, 학생부교과 만학도·특성화고등졸재직자: "
        "3쪽 '◎' 수시 미충원 시 이월 선발, 표에 열 없음)은 넣지 않음",
        "학생부교과 기회균형·만학도는 표 머리글이 '정원내' → 수록",
        "정시 '수능 > 실기'(나·다군)는 PDF가 수능 아래 둔 전형(수능 50%+실기 45%+출결 5%)이라 유형=수능, "
        "나군 '실기/실적 > 실기우수자'(뮤지컬공연전공)는 유형=실기/실적",
        "크리스천리더·사회적배려대상자·정시 일반(일부 실기) 칸은 단과대학(또는 학부) 범위로 세로 병합돼 있어 개별 모집단위에 나누지 않고 "
        "그 범위를 모집단위로 한 행을 따로 둠(범위가 단과대학 띠와 같으면 단과대학 이름). 같은 단과대학의 학과 행에는 그 전형이 없음",
        "단과대학 이름: 표 칸 글자(예: '인문', '반도체·ICT')에 '대학'을 붙인 이름이 PDF 본문에 있으면 그 이름, 아니면 칸 글자 그대로(아너칼리지)",
        "모집단위 이름: 학부 칸 + 전공 칸을 띄어 이어 씀(학부 칸이 없거나 병합된 행은 그 칸 글자). "
        "스포츠지도학전공[야] 체육특기자 종목 행은 '학부 전공 종목'으로 적고, '테이스(남/여)'는 표 표기 그대로(28쪽 본문은 '테니스')",
        "숫자 칸에 붙은 각주 위첨자(1)~6), 6.5pt 미만 글자)는 뺌. 각주 내용: 교과면접 연극·영화전공=영화(12), 실기우수자 "
        "아트앤멀티미디어음악 피아노10·성악10·싱어송라이터7·작곡8, 연극·영화=연극(7), 뮤지컬공연=보컬10·댄스10, "
        "체육특기자 체육학·스포츠산업학=수영2·스키1·빙상1·피겨1",
        "표에 행별 합계 칸 없음 → 계=null(합계칸없음). 계열: 표에 계열 칸 없음 → null",
    ]
    memo.extend("병합 칸 행: " + g for g in group_memo)
    memo.extend(dict.fromkeys(n for n in notes if "칸 테두리 없음" in n))
    # 대조
    tot = all_sums.get("총계")
    s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
    j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
    if tot:
        s_pdf = sum(tot[k] for k in SUSI_KEYS if k in tot)
        j_pdf = sum(tot[k] for k in JEONGSI_KEYS if k in tot)
        memo.append(f"총계 대조: 수시 {s_pdf}={s_me}, 정시 {j_pdf}={j_me}, 전체 {s_pdf + j_pdf}={s_me + j_me} "
                    f"(p{pages[-1]} '총 계' 행 정원내 열 합)")
        bad = [f"{k}({tot[k]} vs {sum(u['인원'].get(k, 0) for u in units)})" for k in tot
               if tot[k] != sum(u["인원"].get(k, 0) for u in units)]
        memo.append("전형별 열 합 대조(총 계 행): " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)))
    for label in ("인문캠퍼스소계", "자연캠퍼스소계"):
        sv = all_sums.get(label)
        if not sv:
            memo.append(f"{label} 행 못 찾음")
            continue
        camp = label.replace("소계", "")
        bad = [k for k in sv if sv[k] != sum(u["인원"].get(k, 0) for u in units if u["단과대학"].startswith(camp))]
        memo.append(f"{camp} 소계 행 대조: " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)))
    if per:
        bad = [f"{n}({v} vs {sum(u['인원'].get(SUMMARY[n], 0) for u in units)})" for n, v in per.items()
               if v != sum(u["인원"].get(SUMMARY[n], 0) for u in units)]
        memo.append(f"p{s_pno} 요약표 수시 정원내 전형별 대조({len(per)}개 전형): " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad))
                    + (f"; 정시 소계 {jeong_sum}={j_me}" if jeong_sum is not None else ""))
    ipw = re.findall(r"(인문|자연)캠퍼스계\([^)]*\)([\d,]+)", full_text)
    if ipw:
        memo.append("참고: p7 입학정원 " + " + ".join(f"{a}캠퍼스 {b}" for a, b in ipw)
                    + f" = {sum(int(b.replace(',', '')) for _, b in ipw)}, 정원내 모집인원 합 {s_me + j_me} "
                    "(차이는 PDF에 설명 없음)")

    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": pages, "전형": jlist, "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(units)}행 → {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: mju.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
