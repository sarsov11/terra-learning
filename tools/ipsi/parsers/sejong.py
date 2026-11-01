#!/usr/bin/env python3
"""세종대학교 2028 시행계획 파서.

대상 표:
  '3 전형별 모집인원(수시모집)' (PDF 6쪽)  → 수시 전형별 인원, 단과대학, 계열
  '4 전형별 모집인원(정시모집)' (PDF 7쪽)  → 정시 전형별 인원
  '2 모집단위·전공(입학정원)'   (PDF 5쪽)  → 보조 대조용(계로 쓰지 않음)
열 뜻은 머리글 칸(모집시기/군 + 전형명(정원내/정원외)) 글자로 정한다.
모집단위 이름 옆 작은 글자(첨단·육군계약 등, 5.2pt)는 지우고 이름만 쓴다.
사용법: python3 -I tools/ipsi/parsers/sejong.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "sejong"
UNIV_NAME = "세종대학교"
SMALL = 5.5  # 이 크기 미만 글자(5.2pt)는 위첨자 표시(첨단, ○○계약). 머리글은 6~7pt, 본문 8pt

# (머리글 묶음, 전형 칸 글자) → key. '(정원외)'가 붙은 칸은 넣지 않는다.
SUSI_MAP = {
    ("학생부교과", "지역균형(정원내)"): "수시_교과_지역균형",
    ("학생부종합", "세종인재(면접형)(정원내)"): "수시_종합_세종인재면접형",
    ("학생부종합", "세종인재(서류형)(정원내)"): "수시_종합_세종인재서류형",
    ("학생부종합", "기회균형(정원내)"): "수시_종합_기회균형",
    ("학생부종합", "사회기여및배려자(정원내)"): "수시_종합_사회기여및배려자",
    ("논술", "논술우수자(정원내)"): "수시_논술_논술우수자",
    ("실기/실적", "실기우수자(정원내)"): "수시_실기_실기우수자",
    ("실기/실적", "예체능특기자(정원내)"): "수시_실기_예체능특기자",
}
JEONGSI_MAP = {
    ("가군", "일반학생(수능형)(정원내)"): "정시_수능_일반수능형_가",
    ("가군", "일반학생(융합형)(정원내)"): "정시_수능_일반융합형_가",
    ("가군", "예체능특기자"): "정시_실기_예체능특기자_가",
    ("나군", "일반학생(수능형)(정원내)"): "정시_수능_일반수능형_나",
    ("나군", "일반학생(융합형)(정원내)"): "정시_수능_일반융합형_나",
    ("나군", "실기우수자"): "정시_실기_실기우수자_나",
    ("다군", "일반학생(수능형)(정원내)"): "정시_수능_일반수능형_다",
    ("다군", "일반학생(융합형)(정원내)"): "정시_수능_일반융합형_다",
}
JEONHYEONG = [
    {"key": "수시_교과_지역균형", "시기": "수시", "유형": "학생부교과", "전형명": "지역균형 전형", "군": None},
    {"key": "수시_종합_세종인재면접형", "시기": "수시", "유형": "학생부종합", "전형명": "세종인재 전형(면접형)", "군": None},
    {"key": "수시_종합_세종인재서류형", "시기": "수시", "유형": "학생부종합", "전형명": "세종인재 전형(서류형)", "군": None},
    {"key": "수시_종합_기회균형", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형 전형", "군": None},
    {"key": "수시_종합_사회기여및배려자", "시기": "수시", "유형": "학생부종합", "전형명": "사회기여 및 배려자 전형", "군": None},
    {"key": "수시_논술_논술우수자", "시기": "수시", "유형": "논술", "전형명": "논술우수자 전형", "군": None},
    {"key": "수시_실기_실기우수자", "시기": "수시", "유형": "실기/실적", "전형명": "실기우수자 전형", "군": None},
    {"key": "수시_실기_예체능특기자", "시기": "수시", "유형": "실기/실적", "전형명": "예체능특기자 전형", "군": None},
    {"key": "정시_수능_일반수능형_가", "시기": "정시", "유형": "수능", "전형명": "일반학생 전형(수능형)", "군": "가"},
    {"key": "정시_수능_일반융합형_가", "시기": "정시", "유형": "수능", "전형명": "일반학생 전형(융합형)", "군": "가"},
    {"key": "정시_실기_예체능특기자_가", "시기": "정시", "유형": "실기/실적", "전형명": "예체능특기자 전형", "군": "가"},
    {"key": "정시_수능_일반수능형_나", "시기": "정시", "유형": "수능", "전형명": "일반학생 전형(수능형)", "군": "나"},
    {"key": "정시_수능_일반융합형_나", "시기": "정시", "유형": "수능", "전형명": "일반학생 전형(융합형)", "군": "나"},
    {"key": "정시_실기_실기우수자_나", "시기": "정시", "유형": "실기/실적", "전형명": "실기우수자 전형", "군": "나"},
    {"key": "정시_수능_일반수능형_다", "시기": "정시", "유형": "수능", "전형명": "일반학생 전형(수능형)", "군": "다"},
    {"key": "정시_수능_일반융합형_다", "시기": "정시", "유형": "수능", "전형명": "일반학생 전형(융합형)", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]


def norm(s):
    return re.sub(r"\s+", "", s or "")


def center_in(o, box):
    return box[0] <= (o["x0"] + o["x1"]) / 2 <= box[2] and box[1] <= (o["top"] + o["bottom"]) / 2 <= box[3]


def text_in(chars, box, big_only=True):
    sel = [c for c in chars if center_in(c, box) and (not big_only or c["size"] >= SMALL)]
    sel.sort(key=lambda c: (round(c["top"]), c["x0"]))
    return norm("".join(c["text"] for c in sel))


def small_in(chars, box):
    sel = [c for c in chars if center_in(c, box) and c["size"] < SMALL]
    sel.sort(key=lambda c: (round(c["top"]), c["x0"]))
    return norm("".join(c["text"] for c in sel))


def val(t):
    """'' → (0, None), '이월' → (0, '이월'), 숫자 → (n, None). 그 밖은 ValueError."""
    t = t.replace(",", "")
    if t in ("", "-"):
        return 0, None
    if t == "이월":
        return 0, "이월"
    if re.fullmatch(r"\d+", t):
        return int(t), None
    raise ValueError(t)


def find_table(pdf, title):
    for pno, page in enumerate(pdf.pages, start=1):
        if title not in norm(page.extract_text() or ""):
            continue
        for t in page.find_tables():
            rows = t.extract()
            if rows and norm(rows[0][0]) in ("계열", "단과대학"):
                return pno, page, t, rows
    raise SystemExit(f"표를 찾지 못함: {title}")


def read_plan(pno, page, table, colmap, label):
    """시기별 표 → {이름: {...}} (순서 유지)."""
    chars = page.chars
    cells = table.cells
    rows = table.rows

    def cell_text(c):
        return text_in(chars, c)

    hdr = {cell_text(c): c for c in cells if c[1] < table.bbox[1] + 2}
    name_hdr = hdr.get("모집단위")
    dangwa_hdr = hdr.get("단과대학")
    gye_hdr = hdr.get("계열")
    if not (name_hdr and dangwa_hdr and gye_hdr):
        raise SystemExit(f"{label}: 머리글(계열/단과대학/모집단위) 못 찾음")
    hdr_bottom = name_hdr[3]
    name_x0, name_x1 = name_hdr[0], name_hdr[2]
    # 전형 칸 머리글: 머리글 영역의 셀 중 모집단위 오른쪽에 있는 것
    grp_cells = [c for c in cells if c[1] < table.bbox[1] + 2 and c[0] >= name_x1 - 1]
    col_cells = [c for c in cells if c[1] > table.bbox[1] + 2 and c[3] <= hdr_bottom + 1 and c[0] >= name_x1 - 1]
    cols = []  # (x0, x1, key or None, 머리글)
    for g in grp_cells:
        gname = cell_text(g)
        subs = sorted([c for c in col_cells if g[0] - 1 <= c[0] and c[2] <= g[2] + 1], key=lambda c: c[0])
        if not subs:  # 묶음 없이 한 칸(재외국민과 외국인(정원외))
            subs, gname = [g], None
        for c in subs:
            lab = cell_text(c) if gname else cell_text(g)
            if "(정원외)" in lab:
                cols.append((c[0], c[2], None, f"{gname}|{lab}"))
                continue
            key = colmap.get((gname, lab))
            if key is None:
                raise SystemExit(f"{label}: 알 수 없는 머리글 {gname}|{lab}")
            cols.append((c[0], c[2], key, f"{gname}|{lab}"))
    if sorted(k for *_x, k, _h in cols if k) != sorted(colmap.values()):
        raise SystemExit(f"{label}: 정원내 열 수 다름 {[(h, k) for *_x, k, h in cols]}")

    # 계열 묶음: 계열 칸을 가로지르는 가로선
    gx0, gx1 = gye_hdr[0], gye_hdr[2]
    hl = sorted({round(e["top"], 1) for e in page.edges
                 if e["orientation"] == "h" and e["x0"] <= gx0 + 2 and e["x1"] >= gx1 - 2 and e["top"] >= hdr_bottom - 1})
    dangwa_cells = [c for c in cells if abs(c[0] - dangwa_hdr[0]) < 1 and abs(c[2] - dangwa_hdr[2]) < 1 and c[1] >= hdr_bottom - 1]

    out, order, total = {}, [], None
    flags = []
    prev_main_bottom = hdr_bottom
    parent = None
    for r in rows:
        rc = [c for c in r.cells if c]
        if not rc:
            continue
        top, bottom = r.bbox[1], r.bbox[3]
        cy = (top + bottom) / 2
        if top < hdr_bottom - 1:
            continue
        lead = next((c for c in rc if c[0] < name_x0 - 1), None)  # 계열 칸부터 시작하는 칸(계 행은 모집단위까지 병합)
        if lead is not None and lead[2] >= name_x1 - 1 and cell_text(lead) == "계":
            total = {}
            for x0, x1, key, h in cols:
                if key:
                    c = next((c for c in rc if abs(c[0] - x0) < 1 and abs(c[2] - x1) < 1), None)
                    v, f = val(cell_text(c) if c else "")
                    total[key] = total.get(key, 0) + v
                    if f:
                        flags.append(f"계 행 {h}: {f}")
            break
        ncell = next((c for c in rc if abs(c[2] - name_x1) < 1 and c[0] >= name_x0 - 1), None)
        if ncell is None:
            continue
        # 행 bbox는 세로 병합 칸(단과대학 등)까지 넓어질 수 있어 이름 칸의 위아래를 행 범위로 씀
        top, bottom = ncell[1], ncell[3]
        cy = (top + bottom) / 2
        is_sub = ncell[0] > name_x0 + 3
        if is_sub:
            if parent is None or parent[1] != prev_main_bottom:
                # 학부 이름 줄: 앞 모집단위 행 아래 ~ 첫 하위 전공 칸 위, 모집단위 칸 전체 폭
                pt = text_in(chars, (name_x0, prev_main_bottom - 0.5, name_x1, ncell[1] + 0.5))
                if not pt:
                    raise SystemExit(f"{label}: 하위 전공의 학부 이름 못 읽음 y={top:.0f}")
                parent = (pt, prev_main_bottom)
            name = f"{parent[0]}({cell_text(ncell)})"
        else:
            if ncell[2] - ncell[0] > (name_x1 - name_x0) + 5:
                continue  # 이름 칸이 숫자 칸까지 합쳐진 행(학부 머리 행)
            name = cell_text(ncell)
            prev_main_bottom = bottom
            parent = None
        if not name:
            raise SystemExit(f"{label}: 이름 없는 행 y={top:.0f}")
        tag = small_in(chars, ncell)
        vals, ewol = {}, []
        for x0, x1, key, h in cols:
            if not key:
                continue
            c = next((c for c in rc if abs(c[0] - x0) < 1 and abs(c[2] - x1) < 1), None)
            t = cell_text(c) if c else text_in(chars, (x0, top, x1, bottom))
            try:
                v, f = val(t)
            except ValueError:
                raise SystemExit(f"{label}: {name} {h} 숫자 아님 {t!r}")
            if f:
                ewol.append(h.split("|")[0] + " " + h.split("|")[1].replace("(정원내)", ""))
            vals[key] = vals.get(key, 0) + v
        # 단과대학/계열
        dc = next((c for c in dangwa_cells if c[1] - 0.5 <= cy <= c[3] + 0.5), None)
        dangwa = cell_text(dc) if dc else ""
        gt = max([h for h in hl if h <= cy], default=None)
        gb = min([h for h in hl if h >= cy], default=None)
        gyeyeol = text_in(chars, (gx0, gt, gx1, gb)) if gt is not None and gb is not None else ""
        if name in out:
            raise SystemExit(f"{label}: 중복 이름 {name}")
        out[name] = {"vals": vals, "이월": ewol, "단과대학": dangwa, "계열": gyeyeol, "tag": tag,
                     "out_any": any(text_in(chars, (x0, top, x1, bottom)) for x0, x1, k, _h in cols if not k)}
        order.append(name)
    if total is None:
        raise SystemExit(f"{label}: 계 행 못 찾음")
    return order, out, total, flags


def read_capacity(pdf):
    """'모집단위·전공(입학정원)' 표: {학부: {전공: 입학정원}}. 숫자 칸은 세로선이 없어 글자로 읽고,
    학부·전공 이름은 그 숫자 높이를 덮는 표 칸에서 읽는다."""
    pno, page, table, rows = find_table(pdf, "모집단위·전공(입학정원)")
    chars = page.chars
    cells = table.cells
    hdr = {text_in(chars, c): c for c in cells if c[1] < table.bbox[1] + 2}
    dan, hak, jeon, cap = hdr["단과대학"], hdr["학부(과)"], hdr["전공"], hdr["입학정원"]

    def col_cell(h, y):
        return next((c for c in cells if abs(c[0] - h[0]) < 1 and c[1] > h[3] - 1 and c[1] - 0.5 <= y <= c[3] + 0.5), None)

    words = page.crop(table.bbox).extract_words()
    res, total = {}, None
    for n in words:
        if not (cap[0] <= n["x0"] and n["x1"] <= cap[2] + 1 and n["top"] > cap[3]):
            continue
        if not re.fullmatch(r"[\d,]+", n["text"]):
            continue  # '별도정원(71)' 등
        y = (n["top"] + n["bottom"]) / 2
        v = int(n["text"].replace(",", ""))
        dc = col_cell(dan, y)
        if dc and text_in(chars, dc) == "계" and dc[2] >= hak[2] - 1:
            total = v
            continue
        hc, jc = col_cell(hak, y), col_cell(jeon, y)
        h = text_in(chars, hc) if hc else ""
        j = text_in(chars, jc) if jc else ""
        res.setdefault(h, {})[j] = v
    # 학부(과) → 단과대학. 단과대학 칸은 세로 병합인데 셀로 잡히지 않는 묶음이 있어,
    # 단과대학 칸을 가로지르는 가로선 사이의 글자로 읽는다.
    hl = sorted({round(e["top"], 1) for e in page.edges
                 if e["orientation"] == "h" and e["x0"] <= dan[0] + 2 and e["x1"] >= dan[2] - 2 and e["top"] >= dan[3] - 1})
    dan_of = {}
    for hc in [c for c in cells if abs(c[0] - hak[0]) < 1 and c[1] > hak[3] - 1]:
        y = (hc[1] + hc[3]) / 2
        gt = max([h for h in hl if h <= y], default=None)
        gb = min([h for h in hl if h >= y], default=None)
        if gt is not None and gb is not None:
            dan_of[text_in(chars, hc)] = text_in(chars, (dan[0], gt, dan[2], gb))
    return pno, res, total, dan_of


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        sp, spage, stab, _ = find_table(pdf, "전형별모집인원(수시모집)")
        jp, jpage, jtab, _ = find_table(pdf, "전형별모집인원(정시모집)")
        s_order, susi, s_total, s_flags = read_plan(sp, spage, stab, SUSI_MAP, "수시")
        j_order, jeong, j_total, j_flags = read_plan(jp, jpage, jtab, JEONGSI_MAP, "정시")
        cp, cap, cap_total, cap_dan = read_capacity(pdf)

    only_s = [n for n in s_order if n not in jeong]
    only_j = [n for n in j_order if n not in susi]
    # 정시표에만 있는 행은 정시표 순서대로 앞 행 뒤에 끼움
    order = list(s_order)
    for n in only_j:
        i = j_order.index(n)
        prev = next((p for p in reversed(j_order[:i]) if p in order), None)
        order.insert(order.index(prev) + 1 if prev else len(order), n)
    blank = {"vals": {}, "이월": [], "단과대학": "", "계열": "", "tag": "", "out_any": False}

    units, excluded, ewol_notes, dangwa_diff, gye_diff, cap_res = [], [], [], [], [], []
    for name in order:
        s, j = susi.get(name, blank), jeong.get(name, blank)
        src_pg = sp if name in susi else jp
        if name not in susi:
            s = dict(s, 단과대학=j["단과대학"], 계열=j["계열"])
        if name not in jeong:
            j = dict(j, 단과대학=s["단과대학"], 계열=s["계열"])
        inwon = {k: v for k, v in list(s["vals"].items()) + list(j["vals"].items()) if v}
        dangwa = s["단과대학"]
        if norm(j["단과대학"]) != norm(dangwa):
            base = re.sub(r"\(.*\)$", "", name)
            p5 = next((v for k, v in cap_dan.items()
                       if re.sub(r"(첨단학과|성인학습자전담학과|.{1,3}계약학과)$", "", k) == base), "")
            p5s = re.sub(r"대학$", "", p5)
            pick = dangwa if p5s == dangwa else (j["단과대학"] if p5s == j["단과대학"] else None)
            if pick is None:
                raise SystemExit(f"단과대학 수시/정시표 다르고 p5로도 못 정함: {name}")
            dangwa_diff.append(f"{name}(수시표 {dangwa or '-'}, 정시표 {j['단과대학'] or '-'}, p{cp} 입학정원 표 {p5} → {pick})")
            dangwa = pick
        if j["계열"] != s["계열"]:
            gye_diff.append(f"{name}(수시표 {s['계열']}, 정시표 {j['계열']})")
        if not inwon:
            excluded.append(f"{name}" + (f"[{s['tag'] or j['tag']}]" if (s["tag"] or j["tag"]) else ""))
            continue
        if j["이월"] or s["이월"]:
            ewol_notes.append(f"{name}({', '.join(s['이월'] + j['이월'])})")
        # 입학정원 대조
        m = re.fullmatch(r"(.+?)\((.+)\)", name)
        c = None
        capn = {re.sub(r"(첨단학과|성인학습자전담학과|.{1,3}계약학과)$", "", k): v for k, v in cap.items()}
        if name in capn and len(capn[name]) == 1:
            c = sum(capn[name].values())  # 학부 한 줄(전공 여러 개여도 입학정원은 학부 단위 한 칸)
        elif m and m.group(1) in capn:
            sub = m.group(2)
            c = next((v for k, v in capn[m.group(1)].items() if k.startswith(sub)), None)
        cap_res.append((name, c, sum(inwon.values())))
        units.append({
            "단과대학": None if dangwa in ("", "-") else dangwa,
            "모집단위": name,
            "계열": None if s["계열"] in ("", "-") else s["계열"],
            "인원": inwon,
            "계": None,
            "쪽": src_pg,
            "검증": "합계칸없음",
        })

    def col_sum(keys):
        return {k: sum(u["인원"].get(k, 0) for u in units) for k in keys}

    s_me, j_me = col_sum(SUSI_KEYS), col_sum(JEONGSI_KEYS)
    bad = [k for k in SUSI_KEYS if s_me[k] != s_total.get(k, 0)] + \
          [k for k in JEONGSI_KEYS if j_me[k] != j_total.get(k, 0)]
    cap_ok = [x for x in cap_res if x[1] is not None and x[1] == x[2]]
    cap_bad = [x for x in cap_res if x[1] is not None and x[1] != x[2]]
    cap_none = [x[0] for x in cap_res if x[1] is None]
    memo = [
        "정원내만 수록: 머리글에 '(정원외)'로 적힌 전형(수시 항공시스템공학·서해5도학생·특성화고교졸재직자·사이버국방·"
        "국방AI융합시스템공학·국방AI로봇융합공학·재외국민과 외국인, 정시 항공시스템공학·사이버국방·국방AI융합시스템공학·"
        "국방AI로봇융합공학·농어촌학생·특성화고교졸업자·전형기간자율화 특성화고교졸재직자)은 넣지 않음",
        "정시 '예체능특기자'(가군)·'실기우수자'(나군) 칸은 머리글에 정원내/외 표시가 없으나 수시 표의 같은 전형이 '(정원내)'이고 "
        f"p{cp} 입학정원 계({cap_total}) = 수시+정시 정원내 합({sum(s_me.values()) + sum(j_me.values())})이 되는 것으로 정원내로 봄",
        f"계: 수시·정시 표 모두 행별 합계 칸이 없음 → null(검증 '합계칸없음'). 별도 표(p{cp} 모집단위·전공(입학정원))의 "
        "입학정원은 모집인원 합계 칸이 아니라 계로 쓰지 않고 아래 보조 대조에만 씀",
        f"'이월'(수시 미충원 이월 인원 선발 표시, 숫자 아님)은 0으로 봄: " + "; ".join(ewol_notes),
        "계열 모집단위(인문사회계열·경상호텔관광계열·자연생명계열·IT계열·첨단융합계열·공과계열)는 표에서 단과대학 칸이 '-'인 "
        "실제 모집 행이라 그대로 수록(단과대학 null)",
        "하위 전공 행(창의소프트학부·우주항공시스템공학부)은 '학부(전공)' 형식으로 적음",
        "한 표에만 있는 행: 수시표만 " + (", ".join(only_s) or "없음") + " / 정시표만 " + (", ".join(only_j) or "없음")
        + " (정시표만 있는 행의 단과대학·계열·쪽은 정시표 값)",
        "모집단위 이름 옆 작은 글자(첨단, 육군계약·공군계약·해군계약·해병대계약)는 지움",
        "정원내 인원이 없어 뺀 행(성인학습자 전담학과·계약학과, 정원외 전형만 있음): " + ", ".join(excluded),
        f"단과대학: 수시 표(p{sp})의 단과대학 칸 글자 그대로('-'은 null). 계열: 같은 표의 계열 칸 그대로(인문/자연/예체능, "
        "자유전공학부는 '-'라 null)",
        "단과대학 칸 수시표·정시표 차이(입학정원 표 단과대학으로 정함): " + ("; ".join(dangwa_diff) if dangwa_diff else "없음"),
        "계열 칸 수시표·정시표 차이: " + ("; ".join(gye_diff) if gye_diff else "없음"),
        f"보조 대조(p{cp} 입학정원 = 행의 정원내 수시+정시 합): {len(cap_ok)}행 일치"
        + (f", 불일치 {len(cap_bad)}행: " + "; ".join(f"{n}(입학정원 {c}, 합 {s})" for n, c, s in cap_bad) if cap_bad else "")
        + (f", 입학정원 못 찾음: {', '.join(cap_none)}" if cap_none else ""),
        "전형별 열 합 대조(수시·정시 표 계 행): " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)),
        f"총계 대조: 수시 {sum(s_total.values())}={sum(s_me.values())}, 정시 {sum(j_total.values())}={sum(j_me.values())}, "
        f"전체 {cap_total}={sum(s_me.values()) + sum(j_me.values())} "
        f"(수시·정시는 각 표 계 행의 정원내 칸 합, 전체는 p{cp} 입학정원 계; 정시 계 행 예체능특기자 칸은 '이월')",
    ] + s_flags + j_flags

    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": [sp, jp], "전형": JEONHYEONG, "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(units)}행 → {out_path}")
    for m in memo:
        print(" -", m)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: sejong.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
