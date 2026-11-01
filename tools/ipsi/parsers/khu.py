#!/usr/bin/env python3
"""경희대학교 2028 시행계획 -> norm JSON (OCR).

이 PDF는 글자가 모두 벡터 곡선으로 그려져 텍스트 층이 없다(pdfplumber chars = 0). 그래서
- 표의 칸 경계는 PDF 괘선(벡터)에서 직접 구한다.
- 칸 안의 글자는 pdfplumber(to_image)로 렌더링해 tesseract(kor/eng)로 OCR 한다.
- 숫자 검증:
  1) 칸 안 글리프(곡선 묶음) 수 == OCR 자릿수
  2) 같은 모양 글리프(곡선 점 수·크기 서명)는 표 전체에서 늘 같은 숫자여야 함(어긋나면 메모)
  3) 정원내 열마다 행 합 == '총합계' 행, 총합계의 정원내 수시/정시 합 == 2쪽 '[정원 내] 수시 n명 : 정시 n명'
- 이름(계열·단과대학·모집단위)은 OCR이 흔들리므로 아래 NAMES(쪽 이미지에서 옮겨 적은 닫힌 목록)와
  맞춰 정한다. 목록의 모집단위가 표에서 정확히 한 번씩 대응되는지 확인한다(숫자는 목록과 무관하게 PDF에서만 읽음).
원천 표: '2. 전형별 모집인원'(열 머리글 아래 '정원내/정원외' 행).

usage: python3 -I tools/ipsi/parsers/khu.py <pdf> <out.json>
필요: tesseract 실행 파일(kor, eng 언어 데이터)
"""
import difflib
import io
import unicodedata
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict

import pdfplumber

UNIV_ID = "khu"
UNIV_NAME = "경희대학교"
NUM_DPI = 400
LAB_DPI = 300

NUM_X = [179, 209, 239, 269, 299, 330, 359, 390, 420, 450, 480, 510, 540, 570, 600, 630, 660, 690, 720, 750, 780, 810]
LABEL_X = [34, 55, 88, 179]  # 계열 | 단과대학 | 모집단위
COLS = [  # (정원내/외, key, 시기, 유형, 전형명, 군)
    ("정원내", "수시_교과_지역균형", "수시", "학생부교과", "학생부교과(지역균형전형)", None),
    ("정원외", None, None, None, "학생부교과(기회균형전형I-특성화고 등을 졸업한 재직자)", None),
    ("정원내", "수시_종합_네오르네상스_면접형", "수시", "학생부종합", "학생부종합(네오르네상스전형) 면접형", None),
    ("정원내", "수시_종합_네오르네상스_서류형", "수시", "학생부종합", "학생부종합(네오르네상스전형) 서류형", None),
    ("정원내", "수시_종합_기회균형I", "수시", "학생부종합", "학생부종합(기회균형전형I-국가보훈·수급자·농어촌·자립아동 등)", None),
    ("정원외", None, None, None, "학생부종합(기회균형전형I-장애인 등 대상자)", None),
    ("정원내", "수시_종합_기회균형II", "수시", "학생부종합", "학생부종합(기회균형전형II)", None),
    ("정원내", "수시_논술_논술우수자", "수시", "논술", "논술우수자전형", None),
    ("정원내", "수시_실기_실기우수자", "수시", "실기/실적", "실기우수자전형", None),
    ("정원내", "정시_수능학생부형_가", "정시", "수능", "수능위주 일반전형(수능·학생부형)", "가"),
    ("정원내", "정시_수능형_가", "정시", "수능", "수능위주 일반전형(수능형)", "가"),
    ("정원외", None, None, None, "정시 가군 기회균형(농어촌학생)", "가"),
    ("정원외", None, None, None, "정시 가군 기회균형(수급자 등)", "가"),
    ("정원외", None, None, None, "정시 가군 기회균형(특성화고교졸업자)", "가"),
    ("정원내", "정시_실기_가", "정시", "실기/실적", "실기위주전형", "가"),
    ("정원내", "정시_수능학생부형_나", "정시", "수능", "수능위주 일반전형(수능·학생부형)", "나"),
    ("정원내", "정시_수능형_나", "정시", "수능", "수능위주 일반전형(수능형)", "나"),
    ("정원외", None, None, None, "정시 나군 기회균형(농어촌학생)", "나"),
    ("정원외", None, None, None, "정시 나군 기회균형(수급자 등)", "나"),
    ("정원외", None, None, None, "정시 나군 기회균형(특성화고교졸업자)", "나"),
    ("정원내", "정시_실기_나", "정시", "실기/실적", "실기위주전형", "나"),
]
IN_COLS = [c for c, m in enumerate(COLS) if m[0] == "정원내"]

# 닫힌 이름 목록(쪽 이미지에서 옮겨 적음). 표기는 PDF 그대로(각주 * 포함).
NAMES = {
    "계열": ["인문", "자연", "예술", "체육"],
    "단과대학": ["문과대학", "외국어대학", "국제대학", "정경대학", "경영대학", "호텔관광대학", "생활과학대학", "이과대학",
              "한의과대학", "공과대학", "전자정보대학", "소프트웨어융합대학", "응용과학대학", "생명과학대학", "의과대학",
              "치과대학", "약학대학", "간호과학대학", "음악대학", "미술대학", "예술디자인대학", "체육대학"],
    "묶음": ["미술학부", "무용학부", "연극영화학과"],
    "세부": ["한국화", "회화", "조소", "한국무용", "현대무용", "발레", "영화연출및제작", "연극및뮤지컬연기", "연극및뮤지컬연출"],
    "모집단위": [
        "자율전공학부", "자유전공학부", "국어국문학과", "영어영문학과", "응용영어통번역학과", "사학과", "철학과",
        "프랑스어학과", "스페인어학과", "러시아어학과", "중국어학과", "일본어학과", "한국어학과", "글로벌커뮤니케이션학부",
        "국제학과", "정치외교학과", "행정학과", "사회학과", "경제학과", "무역학과", "미디어학과", "국제통상·금융투자학부",
        "경영회계계열**", "빅데이터응용학과", "Hospitality경영학과", "조리&푸드디자인학과", "관광·엔터테인먼트학부",
        "글로벌Hospitality·관광학과", "문화관광산업학과", "조리산업학과", "아동가족학과", "주거환경학과", "의상학과",
        "지리학과(인문)", "한의예과(인문)", "식품영양학과", "수학과", "물리학과", "화학과", "생물학과", "지리학과(자연)",
        "미래정보디스플레이학부", "기계공학부**", "산업경영공학과", "원자력공학과", "화학공학과", "신소재공학과",
        "사회기반시스템공학과", "건축공학과", "환경학및환경공학과", "건축학과", "전자공학부 전자공학과",
        "전자공학부 반도체공학과", "지능형전자시스템학과", "생체의공학과", "컴퓨터공학부 컴퓨터공학과",
        "컴퓨터공학부 인공지능학과", "소프트웨어융합학과", "응용수학과", "응용물리학과", "응용화학과", "우주과학과",
        "유전생명공학과", "식품생명공학과", "융합바이오·신소재공학과", "스마트팜과학과", "의예과", "한의예과(자연)",
        "치의예과", "약학과(6년제)", "한약학과", "약과학과", "간호학과", "작곡과", "성악과", "기악과",
        "산업디자인학과", "시각디자인학과", "환경조경디자인학과", "의류디자인학과", "디지털콘텐츠학과", "도예학과",
        "PostModern음악학과***", "체육학과", "스포츠의학과", "골프산업학과", "스포츠지도학과***", "태권도학과",
    ],
}


# ---------------------------------------------------------------- 벡터 도형
def is_black_fill(o):
    return bool(o.get("fill")) and str(o.get("non_stroking_color")) in ("0", "0.0", "(0,)", "(0.0,)", "[0]")


def rule_segments(page):
    H, V = [], []
    for o in list(page.lines) + list(page.rects):
        if o.get("object_type") == "rect" and not is_black_fill(o):
            continue
        w, h = o["x1"] - o["x0"], o["bottom"] - o["top"]
        if h < 1.5 and w > 12:
            H.append((o["x0"], o["x1"], (o["top"] + o["bottom"]) / 2))
        elif w < 1.5 and h > 12:
            V.append(((o["x0"] + o["x1"]) / 2, o["top"], o["bottom"]))
    return H, V


def merge_close(vals, tol=1.6):
    out = []
    for v in sorted(vals):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def h_lines_in(H, x0, x1):
    """x0~x1 구간을 (토막을 이어서라도) 빈틈 없이 가로지르는 가로선 y."""
    by_y = defaultdict(list)
    for s in H:
        if s[1] > x0 and s[0] < x1:
            by_y[round(s[2] * 2) / 2].append((s[0], s[1]))
    ys = []
    for y, spans in by_y.items():
        pos = x0 + 1
        for a, b in sorted(spans):
            if a > pos + 1.0:
                break
            pos = max(pos, b)
        if pos >= x1 - 1:
            ys.append(y)
    return merge_close(ys)


def glyph_objs(page):
    return [o for o in list(page.curves) + list(page.rects)
            if is_black_fill(o) and (o["x1"] - o["x0"]) < 14 and (o["bottom"] - o["top"]) < 14]


def objs_in(objs, x0, y0, x1, y1):
    return [o for o in objs if x0 + 0.5 < (o["x0"] + o["x1"]) / 2 < x1 - 0.5 and y0 + 0.5 < (o["top"] + o["bottom"]) / 2 < y1 - 0.5]


def clusters(objs):
    groups = []
    for o in sorted(objs, key=lambda o: o["x0"]):
        if groups and o["x0"] < groups[-1]["x1"] - 0.05:
            groups[-1]["objs"].append(o)
            groups[-1]["x1"] = max(groups[-1]["x1"], o["x1"])
        else:
            groups.append({"x0": o["x0"], "x1": o["x1"], "objs": [o]})
    for g in groups:
        g["top"] = min(o["top"] for o in g["objs"])
        g["bottom"] = max(o["bottom"] for o in g["objs"])
    return groups


def signature(g):
    return tuple(sorted((len(o.get("pts") or []), round(o["x1"] - o["x0"], 1), round(o["bottom"] - o["top"], 1))
                        for o in g["objs"]))


def text_lines(objs):
    """글리프 도형을 세로 구간이 겹치는 것끼리 묶어 줄로 나눈다."""
    out = []
    for o in sorted(objs, key=lambda o: o["top"]):
        if out and o["top"] < out[-1]["b"] + 0.6:
            out[-1]["b"] = max(out[-1]["b"], o["bottom"])
            out[-1]["o"].append(o)
        else:
            out.append({"t": o["top"], "b": o["bottom"], "o": [o]})
    return out


# ---------------------------------------------------------------- OCR
class Renders:
    def __init__(self, page):
        self.page = page
        self.imgs = {}

    def img(self, dpi):
        if dpi not in self.imgs:
            self.imgs[dpi] = self.page.to_image(resolution=dpi).original.convert("L")
        return self.imgs[dpi]

    def ocr(self, box, dpi, lang, psm, whitelist=None, border=20):
        from PIL import Image  # pdfplumber 의존성
        sc = dpi / 72.0
        crop = self.img(dpi).crop(tuple(int(v * sc) for v in box))
        w, h = crop.size
        canvas = Image.new("L", (w + 2 * border, h + 2 * border), 255)
        canvas.paste(crop, (border, border))
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        cmd = ["tesseract", "stdin", "stdout", "-l", lang, "--psm", str(psm)]
        if whitelist:
            cmd += ["-c", f"tessedit_char_whitelist={whitelist}"]
        r = subprocess.run(cmd, input=buf.getvalue(), capture_output=True, check=True)
        return r.stdout.decode("utf-8").strip()


def bbox_of(objs, pad=1.5):
    return (min(o["x0"] for o in objs) - pad, min(o["top"] for o in objs) - pad,
            max(o["x1"] for o in objs) + pad, max(o["bottom"] for o in objs) + pad)


def squash(s):
    return re.sub(r"[\s　]", "", s or "")


def label_candidates(rd, box, objs):
    """칸 글자의 OCR 후보 문자열들(해상도·분할 방식을 바꿔 가며)."""
    lines = text_lines(objs)
    cands = set()
    for dpi in (300, 400, 500):
        cands.add(squash(rd.ocr(box, dpi, "kor", 6)))
        parts = [rd.ocr(bbox_of(L["o"]), dpi, "kor", 7) for L in lines]
        cands.add(squash("".join(parts)))
    cands.add(squash(rd.ocr(box, LAB_DPI, "kor+eng", 6)))
    return [c for c in cands if c]


def jamo(s):
    return unicodedata.normalize("NFD", s)


def scores(cands, vocab):
    cj = [jamo(c) for c in cands]
    return {v: max((difflib.SequenceMatcher(None, c, jamo(squash(v))).ratio() for c in cj), default=0.0) for v in vocab}


def best_name(cands, vocab, floor=0.5, margin=0.08):
    sc = sorted(scores(cands, vocab).items(), key=lambda kv: -kv[1])
    (n1, s1), (n2, s2) = sc[0], sc[1] if len(sc) > 1 else (None, 0.0)
    if s1 < floor or s1 - s2 < margin:
        return None, s1
    return n1, s1


def assign_unique(items, vocab, floor=0.45):
    """각 칸(items: id -> 후보들)에 목록 이름을 하나씩, 서로 겹치지 않게 점수 높은 순으로 붙인다."""
    pairs = []
    for i, cands in items.items():
        for v, s in scores(cands, vocab).items():
            pairs.append((s, i, v))
    pairs.sort(key=lambda t: -t[0])
    got, used = {}, set()
    for s, i, v in pairs:
        if i in got or v in used or s < floor:
            continue
        got[i] = (v, s)
        used.add(v)
    return got


def is_dash_or_dot(objs):
    gs = clusters(objs)
    return all((g["bottom"] - g["top"]) < 1.6 for g in gs)


# ---------------------------------------------------------------- 표 쪽 찾기
def table_pages(pdf):
    pages = []
    for i, p in enumerate(pdf.pages, 1):
        if p.width < p.height:
            continue
        _, V = rule_segments(p)
        xs = merge_close([v[0] for v in V if v[2] - v[1] > 100], 2.5)
        if sum(any(abs(x - nx) < 2 for x in xs) for nx in NUM_X) >= len(NUM_X) - 1:
            pages.append(i)
    return pages


def main(pdf_path, out_path):
    if not shutil.which("tesseract"):
        raise SystemExit("tesseract 실행 파일이 없어 OCR 불가")
    langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout.split()
    if "kor" not in langs or "eng" not in langs:
        raise SystemExit("tesseract kor/eng 언어 데이터 없음")

    pdf = pdfplumber.open(pdf_path)
    pages = table_pages(pdf)
    if not pages:
        raise SystemExit("전형별 모집인원 표 쪽을 찾지 못함")

    rows, cells = [], []
    sig_votes = defaultdict(Counter)
    total_row = None
    header_issues, name_issues, marks = [], [], []
    carried = []
    prev = {"계열": None, "단과대학": None, "묶음": None}

    for pno in pages:
        page = pdf.pages[pno - 1]
        H, V = rule_segments(page)
        rd = Renders(page)
        gobjs = glyph_objs(page)
        vxs = merge_close([v[0] for v in V if v[2] - v[1] > 100], 2.5)
        for nx in NUM_X + LABEL_X:
            if not any(abs(x - nx) < 2 for x in vxs):
                raise SystemExit(f"{pno}쪽 세로선 x={nx} 없음 — 표 구조가 다름")
        full = h_lines_in(H, LABEL_X[0], NUM_X[-1])
        top, hdr_bottom, bottom = full[0], full[1], full[-1]
        ys = merge_close([y for y in h_lines_in(H, NUM_X[0], NUM_X[1]) if hdr_bottom - 0.5 <= y <= bottom + 0.5])
        sub_top = max(y for y in h_lines_in(H, NUM_X[0], NUM_X[1]) if top < y < hdr_bottom - 2)
        for c, meta in enumerate(COLS):
            o = objs_in(gobjs, NUM_X[c], sub_top, NUM_X[c + 1], hdr_bottom)
            t = squash(rd.ocr(bbox_of(o), LAB_DPI, "kor", 7)) if o else ""
            if difflib.SequenceMatcher(None, t, meta[0]).ratio() < 0.6 or ("내" in t) != (meta[0] == "정원내"):
                header_issues.append(f"{pno}쪽 col{c} '{t}'(기대 {meta[0]})")
        lab_lines = {k: h_lines_in(H, LABEL_X[k] + 2, LABEL_X[k + 1] - 2) for k in range(3)}
        cache = {}

        def cell_text(kind, k, y0, y1, xa=None, xb=None):
            xa = LABEL_X[k] if xa is None else xa
            xb = LABEL_X[k + 1] if xb is None else xb
            ls = lab_lines[k] if (xa, xb) == (LABEL_X[k], LABEL_X[k + 1]) else h_lines_in(H, xa + 2, xb - 2)
            a = max([y for y in ls if y <= y0 + 1] or [y0])
            b = min([y for y in ls if y >= y1 - 1] or [y1])
            key = (kind, round(xa), round(a), round(b))
            if key in cache:
                return cache[key]
            o = objs_in(gobjs, xa, a, xb, b)
            if not o:
                res = ("빈칸", a <= hdr_bottom + 1, (pno,) + key)
            elif is_dash_or_dot(o):
                res = ("없음", None, (pno,) + key)
            else:
                res = ("후보", label_candidates(rd, (xa + 1.5, a + 1.5, xb - 1.5, b - 1.5), o), (pno,) + key)
            cache[key] = res
            return res

        for r in range(len(ys) - 1):
            y0, y1 = ys[r], ys[r + 1]
            if y1 - y0 < 5:
                continue
            row_objs = objs_in(gobjs, LABEL_X[0], y0, LABEL_X[3], y1)
            # 총합계 행: 모집단위 칸 경계가 사라지고 가운데 굵은 글자
            split = [v[0] for v in V if LABEL_X[2] + 5 < v[0] < LABEL_X[3] - 5 and v[1] <= y0 + 1 and v[2] >= y1 - 1]
            lab_cell_lines = [x for x in (LABEL_X[1], LABEL_X[2]) if any(abs(v[0] - x) < 1.5 and v[1] <= y0 + 1 and v[2] >= y1 - 1 for v in V)]
            is_total = not lab_cell_lines and row_objs and r == len(ys) - 2

            vals, raw_cells = [], []
            for c in range(len(COLS)):
                o = objs_in(gobjs, NUM_X[c], y0, NUM_X[c + 1], y1)
                gs = [g for g in clusters(o) if not ((g["x1"] - g["x0"]) < 0.6 and (g["bottom"] - g["top"]) < 0.6)]
                if not gs:
                    vals.append(0)
                    continue
                if all((g["bottom"] - g["top"]) < 4.5 for g in gs):
                    vals.append(None)  # 숫자가 아닌 작은 표시(예: ****)
                    continue
                t = squash(rd.ocr(bbox_of([x for g in gs for x in g["objs"]]), NUM_DPI, "eng", 7, "0123456789"))
                if not t and len(gs) == 1:
                    t = squash(rd.ocr(bbox_of(gs[0]["objs"]), NUM_DPI, "eng", 10, "0123456789"))
                sigs = [signature(g) for g in gs]
                if re.fullmatch(r"\d+", t) and len(t) == len(gs):
                    vals.append(int(t))
                    if COLS[c][0] == "정원내":
                        for s, ch in zip(sigs, t):
                            sig_votes[s][ch] += 1
                else:
                    vals.append("?")
                if COLS[c][0] == "정원내":
                    raw_cells.append((c, sigs, t))
            rec = {"쪽": pno, "vals": vals, "cells": raw_cells}
            if is_total:
                rec["모집단위"] = "총합계"
                total_row = rec
                continue
            lab = {"계열": cell_text("계열", 0, y0, y1), "단과대학": cell_text("단과대학", 1, y0, y1)}
            if split:
                sx = split[0]
                lab["묶음"] = cell_text("묶음", 2, y0, y1, LABEL_X[2], sx)
                lab["세부"] = cell_text("세부", 2, y0, y1, sx, LABEL_X[3])
            else:
                lab["모집단위"] = cell_text("모집단위", 2, y0, y1)
            rec["lab"] = lab
            rows.append(rec)

    # ---------------------------------------------------------- 이름 정하기
    # 모집단위·세부: 표 전체에서 목록 이름을 서로 겹치지 않게 하나씩 붙인다.
    name_log = []
    for kind in ("모집단위", "세부"):
        items = {i: r["lab"][kind][1] for i, r in enumerate(rows) if kind in r["lab"] and r["lab"][kind][0] == "후보"}
        got = assign_unique(items, NAMES[kind])
        for i, r in enumerate(rows):
            if kind not in r["lab"]:
                continue
            if i in got:
                r[kind] = got[i][0]
                name_log.append((got[i][1], r["쪽"], kind, got[i][0], items[i]))
            else:
                r[kind] = None
                name_issues.append(f"{r['쪽']}쪽 {kind} 이름 미확정(OCR {items.get(i)})")
    # 계열·단과대학·묶음: 병합 칸마다 목록에서 가장 가까운 이름. 쪽 첫머리 빈 칸은 앞 행 값을 잇는다.
    resolved = {}
    for r in rows:
        for kind in ("계열", "단과대학", "묶음"):
            if kind not in r["lab"]:
                if kind == "묶음":
                    r["묶음"] = None
                continue
            st, v, ck = r["lab"][kind]
            if st == "후보":
                if ck not in resolved:
                    nm, sc = best_name(v, NAMES[kind], floor=0.4, margin=0.05)
                    resolved[ck] = nm
                    if nm is None:
                        name_issues.append(f"{r['쪽']}쪽 {kind} 칸 이름 미확정(OCR {v})")
                    else:
                        name_log.append((sc, r["쪽"], kind, nm, v))
                r[kind] = resolved[ck]
            elif st == "빈칸" and v and prev[kind]:
                r[kind] = prev[kind]
                carried.append(f"{r['쪽']}쪽 {kind} '{prev[kind]}'")
            else:
                r[kind] = None
            prev[kind] = r[kind]
        if "세부" in r["lab"]:
            r["모집단위"] = r.get("세부")
    low = sorted(name_log, key=lambda t: t[0])[:8]

    # ---------------------------------------------------------- 글리프 서명 대조
    sig_map, sig_conflict = {}, []
    for s, cnt in sig_votes.items():
        (ch, _), *rest = cnt.most_common()
        sig_map[s] = ch
        if rest:
            sig_conflict.append(f"{dict(cnt)}")
    cell_notes = []
    for rec in rows + ([total_row] if total_row else []):
        for c, sigs, t in rec["cells"]:
            decoded = "".join(sig_map.get(s, "?") for s in sigs)
            v = rec["vals"][c]
            label = rec.get("모집단위") or "?"
            if v == "?":
                if "?" not in decoded:
                    rec["vals"][c] = int(decoded)
                    cell_notes.append(f"{rec['쪽']}쪽 {label} col{c}: OCR '{t}' → 글리프 서명으로 {decoded}")
            elif isinstance(v, int) and "?" not in decoded and str(v) != decoded:
                rec["vals"][c] = "?"
                cell_notes.append(f"{rec['쪽']}쪽 {label} col{c}: OCR {v} != 서명 {decoded} → 미확정")

    # ---------------------------------------------------------- 열 합계 대조(정원내)
    col_bad = []
    if total_row is None:
        col_bad.append("총합계 행을 찾지 못함")
    else:
        for c in IN_COLS:
            tv = total_row["vals"][c]
            sv = sum(r["vals"][c] for r in rows if isinstance(r["vals"][c], int))
            if tv != sv or any(r["vals"][c] == "?" for r in rows):
                col_bad.append(f"col{c}({COLS[c][1]}) 총합계 {tv} / 행합 {sv}")

    # ---------------------------------------------------------- 이름 목록 대응
    seen = Counter(r["모집단위"] if not r["묶음"] else f"{r['묶음']}|{r['모집단위']}" for r in rows if r["모집단위"])
    dup = [k for k, n in seen.items() if n > 1]
    plain_used = {r["모집단위"] for r in rows if r["모집단위"] and not r["묶음"]}
    missing = [n for n in NAMES["모집단위"] if n not in plain_used]
    sub_used = {r["모집단위"] for r in rows if r["모집단위"] and r["묶음"]}
    missing += [n for n in NAMES["세부"] if n not in sub_used]

    # ---------------------------------------------------------- 출력
    units, excluded, unread = [], [], []
    for r in rows:
        if not r["모집단위"]:
            unread.append(f"{r['쪽']}쪽 이름 미확정 행")
            continue
        name = re.sub(r"\*+$", "", r["모집단위"])
        dept = f"{r['묶음']}({name})" if r["묶음"] else name
        bad = [c for c in IN_COLS if r["vals"][c] == "?"]
        if bad:
            unread.append(f"{dept}(col{bad})")
            continue
        for c in IN_COLS:
            if r["vals"][c] is None:
                marks.append(f"{dept}({COLS[c][4]} {COLS[c][5]}군)")
        inwon = {}
        for c in IN_COLS:
            v = r["vals"][c]
            if isinstance(v, int) and v:
                inwon[COLS[c][1]] = inwon.get(COLS[c][1], 0) + v
        if not inwon:
            excluded.append(dept)
            continue
        units.append({"단과대학": r["단과대학"], "모집단위": dept, "계열": r["계열"], "인원": inwon,
                      "계": None, "쪽": r["쪽"], "검증": "합계칸없음"})

    # 정원내 총계 문장('[정원 내] 수시 n명 : 정시 n명') — 줄 단위로 잘라 해상도 3가지로 읽고 2번 이상 같을 때만 채택
    tot, tot_page, tot_reads = None, None, []
    pat = re.compile(r"정\s*원\s*[내네](?!\s*외)\s*\]?\s*수\s*시\s*(\d[.,]?\d{3})\s*명.{0,40}?정\s*시\s*(\d[.,]?\d{3})\s*명")
    for i, p in enumerate(pdf.pages[:8], 1):
        if p.width > p.height:
            continue
        rd = Renders(p)
        for L in text_lines(glyph_objs(p)):
            bx = bbox_of(L["o"])
            if bx[2] - bx[0] < 150:
                continue
            first = rd.ocr(bx, LAB_DPI, "kor", 7)
            if not ("수시" in first and "정시" in first and "정원" in first and "외" not in first):
                continue
            reads = []
            for dpi in (300, 400, 500):
                m = pat.search(rd.ocr(bx, dpi, "kor", 7))
                if m:
                    reads.append(tuple(int(re.sub(r"[.,]", "", g)) for g in m.groups()))
            tot_reads = reads
            if reads:
                (val, n), = Counter(reads).most_common(1)
                if n >= 2:
                    tot, tot_page = val, i
            break
        if tot_reads:
            break

    su = sum(v for u in units for k, v in u["인원"].items() if k.startswith("수시_"))
    jo = sum(v for u in units for k, v in u["인원"].items() if k.startswith("정시_"))
    tsu = sum(total_row["vals"][c] for c in IN_COLS if COLS[c][2] == "수시") if total_row else None
    tjo = sum(total_row["vals"][c] for c in IN_COLS if COLS[c][2] == "정시") if total_row else None
    memo = [
        "이 PDF는 텍스트 층이 없어(글자가 벡터 곡선) 칸 경계는 PDF 괘선에서, 글자는 tesseract OCR로 읽음",
        "정원내만 수록. 정원외(학생부교과 기회균형I-특성화고 등을 졸업한 재직자, 학생부종합 기회균형I-장애인 등 대상자, "
        "정시 가·나군 기회균형 농어촌학생·수급자 등·특성화고교졸업자)와 재외국민은 넣지 않음",
        "계: 표에 행 합계 칸이 없어 null(검증=합계칸없음). 대신 정원내 열별 행합을 총합계 행과 대조함",
        "모집단위·단과대학·계열 이름은 OCR 결과를 파서 안 이름 목록(쪽 이미지에서 옮겨 적음)과 맞춰 정함. "
        "모집단위 칸이 둘로 나뉜 행은 '묶음(세부)'(예: 미술학부(한국화)). 각주 표시(*)는 이름에서 뺌",
        "열별 행합 == 총합계(정원내 13열): " + ("모두 일치" if not col_bad else "; ".join(col_bad)),
        f"글리프 서명 {len(sig_map)}종 중 서로 다른 숫자로 읽힌 것: " + ("없음" if not sig_conflict else "; ".join(sig_conflict)),
    ]
    if cell_notes:
        memo.append("OCR 보정/미확정 칸: " + "; ".join(cell_notes))
    memo.append("정원내/정원외 머리글 OCR: " + ("모든 쪽 기대와 일치" if not header_issues else "확인 필요 " + "; ".join(header_issues)))
    if tot:
        ok = (su, jo) == tot and (tsu, tjo) == tot
        memo.append(f"총계 대조: 수시 {su}={tot[0]}, 정시 {jo}={tot[1]}, 전체 {su + jo}={sum(tot)}"
                    + ("" if ok else f" (불일치; 표 총합계행 수시 {tsu}, 정시 {tjo})")
                    + f" (출처 {tot_page}쪽 '[정원 내] 수시 n명 : 정시 n명' OCR, 표 총합계행과도 일치)" * ok)
    else:
        memo.append(f"총계 대조: 정원내 총계 문장을 OCR로 확정하지 못함(읽은 값 {tot_reads}) (파싱 합 수시 {su}, 정시 {jo}; "
                    f"표 총합계행 수시 {tsu}, 정시 {tjo})")
    memo.append("이름 목록 대응: " + ("모집단위 목록 전부 한 번씩 대응" if not (dup or missing) else
                                  f"중복 {dup}, 표에서 못 찾음 {missing}"))
    if carried:
        memo.append("쪽 첫머리 병합 칸이 비어 앞 쪽 값을 이어받음(표가 쪽을 넘어 이어짐): " + ", ".join(sorted(set(carried))))
    if marks:
        memo.append("숫자가 아닌 표시(**** 등, 수시 미충원 시에만 선발)는 0으로 봄: " + ", ".join(marks))
    if excluded:
        memo.append("정원내 인원이 없어 뺀 행(정원외 전담 모집단위): " + ", ".join(excluded))
    memo.append("이름 대응 점수 낮은 순 5개(점수, 쪽, 종류, 정한 이름, OCR 후보 1개): " + "; ".join(
        f"{sc:.2f} {pg}쪽 {k} {nm} ← {sorted(c, key=len)[0] if c else ''}" for sc, pg, k, nm, c in low[:5]))
    if name_issues:
        memo.append("이름 확인 필요: " + "; ".join(name_issues))
    if unread:
        memo.append("읽지 못해 뺀 행: " + "; ".join(unread))

    used = {k for u in units for k in u["인원"]}
    jeonhyeong = []
    for m in COLS:
        if m[0] == "정원내" and m[1] in used and m[1] not in [j["key"] for j in jeonhyeong]:
            jeonhyeong.append({"key": m[1], "시기": m[2], "유형": m[3], "전형명": m[4], "군": m[5]})
    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": sorted(set(pages + ([tot_page] if tot_page else []))),
           "전형": jeonhyeong, "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{UNIV_ID}: {len(units)}행 (합계일치 0, 불일치 0, 합계칸없음 {len(units)})")
    for m in memo:
        print(" -", m)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
