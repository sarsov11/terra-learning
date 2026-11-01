"""동국대학교(서울) 2028 시행계획 → norm JSON.

표: PDF 7~8쪽 '[수시모집] 전형 및 모집단위별 모집인원', 9~10쪽 '[정시모집] 전형 및 모집단위별 모집인원'.

이 PDF의 표는 글자가 텍스트가 아니라 채워진 벡터 윤곽선(path)으로 그려져 있어 extract_text/extract_tables로
숫자를 읽을 수 없다. 그래서
  1) 표 격자: 회색 선(page.lines)으로 열·행 경계를 잡고,
  2) 숫자: 윤곽선의 경로 명령 순서(m/l/c/h)와 구멍(안쪽 윤곽) 수로 0~9를 판별한다
     (같은 글꼴 같은 글자는 크기와 무관하게 명령 순서가 같다 — 결정적, 추정 없음).
     알 수 없는 윤곽이 숫자 칸에 있으면 그 칸은 읽지 않은 것으로 처리한다.
  3) 칸 안 '일반/승려', '인문/자연', '실기/특기' 같은 앞말은 윤곽 서명으로만 판별한다.
  4) 모집단위·대학 이름은 숫자가 아니고 윤곽선이라 판별표를 만들 수 없어, 렌더링한 쪽에서 옮겨 적은
     이름 목록(아래 NAMES)을 쓰고, 수시표·정시표의 같은 행 이름 칸 윤곽 구성이 같은지로 행 정렬을 검증한다.
  5) 같은 PDF의 텍스트 쪽(14~30쪽 전형별 '모집인원 : n명', 23쪽 실기 모집단위별 인원, 17쪽 특수교육대상자
     모집단위)으로 열 합계를 따로 대조한다.

사용: python3 -I tools/ipsi/parsers/dongguk.py <pdf> <out.json>
"""
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict

import pdfplumber

ID = "dongguk"
NAME = "동국대학교"
BLACK = (0.0, 0.0, 0.0)

# (외곽 윤곽 경로 명령, 구멍 수) → 글자
DIGITS = {
    ("mcclcccccccclllllllcccccccch", 0): "2",
    ("mlcclllllccch", 0): "1",
    ("mccccccccclllcccccccccclcccccccccclcccccccccccclcch", 0): "3",
    ("mcccccccccccllllllcccccccccccclcch", 0): "5",
    ("mllllllh", 0): "7",
    ("mllllllllllh", 1): "4",
    ("mcccccccccccch", 1): "0",
    ("mcccccclcccccccccccccccccccclcch", 1): "6",
    ("mcccccclcccccccccccccccccccccclch", 1): "9",
    ("mcccccclcccccccccccclcccccch", 2): "8",
    ("mcccccclccccch", 0): ",",
}
# 칸 안 앞말(숫자 앞 글자) 윤곽 서명(sha1 앞 12자리) → 앞말
LABELS = {}  # 실행 시 아래 LABEL_SIGS로 채움
LABEL_SIGS = {
    "일반": None, "승려": None, "인문": None, "자연": None, "실기": None, "특기": None,
}

# 행 이름(렌더링한 7~10쪽에서 옮겨 적음). 수시표(7,8쪽)와 정시표(9,10쪽)는 같은 순서.
NAMES = {
    "A": [  # 7쪽(수시) / 9쪽(정시)
        "불교학부", "문화유산학과",
        "국어국문·문예창작학부", "영어영문학부", "일본학과", "중어중문학과", "철학과", "사학과",
        "수학과", "화학과", "통계학과", "물리학과",
        "법학과",
        "정치외교학전공", "행정학전공", "북한학전공", "경제학과", "국제통상학과", "사회학전공",
        "미디어커뮤니케이션학전공", "식품산업관리학과", "광고홍보학과", "사회복지학과",
        "경찰행정학부",
        "경영대학★",
        "바이오시스템대학★", "융합환경과학과", "생명과학과", "식품바이오융합공학과", "의생명공학과",
        "전자전기공학부", "정보통신공학과",
    ],
    "B": [  # 8쪽(수시) / 10쪽(정시)
        "건설환경공학과", "화공생물공학과", "기계로봇에너지공학과", "건축공학부", "산업시스템공학과", "에너지신소재공학과",
        "컴퓨터·AI학부", "시스템반도체학부", "의료인공지능공학과", "지능형네트워크융합학과",
        "교육학과", "국어교육과", "역사교육과", "지리교육과", "수학교육과", "가정교육과", "체육교육과",
        "불교미술전공", "한국화전공", "서양화전공", "조소전공", "연극학부", "영화영상학과", "스포츠문화학과", "한국음악과",
        "약학과",
        "열린전공학부★",
    ],
}
# 대학 칸 띠(위→아래)
DAE = {
    "A": [("불교", 2), ("문과", 6), ("이과", 4), ("법과", 1), ("사회과학", 10), ("경찰사법", 1), ("경영", 1),
          ("바이오시스템", 5), ("공과", 2)],
    "B": [("공과", 6), ("첨단융합", 4), ("사범", 7), ("예술", 8), ("약학", 1), (None, 1)],  # 열린전공학부: 대학 칸과 합쳐짐
}
PAGES = {"A": (7, 9), "B": (8, 10)}

# 열 정의(이름 칸 다음부터, 마지막은 '계')
SUSI_COLS = [
    ("수시_종합_DoDream", "수시", "학생부종합", "Do Dream", None),
    ("수시_종합_불교추천인재", "수시", "학생부종합", "불교추천인재", None),
    "정원외:학생부종합 기회균형 특성화고교졸업자",
    "정원외:학생부종합 기회균형 특수교육대상자",
    ("수시_교과_학교장추천인재", "수시", "학생부교과", "학교장추천인재", None),
    ("수시_교과_기회균형통합", "수시", "학생부교과", "기회균형통합", None),
    ("수시_논술", "수시", "논술", "논술", None),
    ("수시_실기", "수시", "실기/실적", "실기", None),
    "정원외:재외국민 중고교과정국외이수자",
    "계",
]
JEONGSI_COLS = [
    ("정시_수능_가", "정시", "수능", "일반", "가"),
    ("정시_수능_나", "정시", "수능", "일반", "나"),
    ("정시_수능_다", "정시", "수능", "일반", "다"),
    "정원외:농어촌학생 가군", "정원외:농어촌학생 나군", "정원외:농어촌학생 다군",
    "정원외:기초생활수급자및차상위계층 가군", "정원외:기초생활수급자및차상위계층 나군", "정원외:기초생활수급자및차상위계층 다군",
    "계",
]


# ---------------------------------------------------------------- 윤곽 → 글자
def contours(page, box=None):
    out = []
    for o in page.curves:
        if o.get("fill") and tuple(o.get("non_stroking_color") or ()) == BLACK:
            out.append(dict(x0=o["x0"], x1=o["x1"], top=o["top"], bottom=o["bottom"],
                            ops="".join(p[0] for p in o["path"])))
    for o in page.rects:
        if o.get("fill") and tuple(o.get("non_stroking_color") or ()) == BLACK and o["width"] < 15 and o["height"] < 15:
            out.append(dict(x0=o["x0"], x1=o["x1"], top=o["top"], bottom=o["bottom"], ops="R"))
    if box:
        x0, t, x1, b = box
        out = [c for c in out if x0 <= (c["x0"] + c["x1"]) / 2 <= x1 and t <= (c["top"] + c["bottom"]) / 2 <= b]
    return out


def _inside(a, b, tol=0.05):
    return (a["x0"] >= b["x0"] - tol and a["x1"] <= b["x1"] + tol and a["top"] >= b["top"] - tol
            and a["bottom"] <= b["bottom"] + tol
            and (a["x1"] - a["x0"]) * (a["bottom"] - a["top"]) < (b["x1"] - b["x0"]) * (b["bottom"] - b["top"]))


def glyphs(cs):
    """윤곽을 외곽+구멍으로 묶고 숫자를 판별한다."""
    cs = sorted(cs, key=lambda c: -(c["x1"] - c["x0"]) * (c["bottom"] - c["top"]))
    outers = []
    for c in cs:
        host = [o for o in outers if _inside(c, o)]
        if host and c["ops"] != "R":
            host[0]["holes"].append(c)
        else:
            outers.append(dict(c, holes=[]))
    res = []
    for o in outers:
        w, h = o["x1"] - o["x0"], o["bottom"] - o["top"]
        if o["ops"] == "R" and w < 1.2 and h < 1.2:
            ch = "·"  # 빈 칸 표시용 작은 점
        elif o["ops"] == "R" and w > 2 and h < 1.2:
            ch = "–"
        else:
            ch = DIGITS.get((o["ops"], len(o["holes"])))
        if ch in ("6", "9"):  # 구멍 위치로 한 번 더 확인
            hy = (o["holes"][0]["top"] + o["holes"][0]["bottom"]) / 2
            my = (o["top"] + o["bottom"]) / 2
            if (ch == "6") != (hy > my):
                ch = None
        res.append(dict(o, ch=ch))
    return res


def text_lines(gs):
    gs = sorted(gs, key=lambda g: g["top"])
    lines = []
    for g in gs:
        cy = (g["top"] + g["bottom"]) / 2
        for ln in lines:
            if ln["t"] - 0.5 <= cy <= ln["b"] + 0.5:
                ln["m"].append(g)
                ln["t"] = min(ln["t"], g["top"])
                ln["b"] = max(ln["b"], g["bottom"])
                break
        else:
            lines.append(dict(t=g["top"], b=g["bottom"], m=[g]))
    return [sorted(ln["m"], key=lambda g: g["x0"]) for ln in lines]


def label_sig(gl):
    parts = sorted(o for g in gl for o in [g["ops"]] + [h["ops"] for h in g["holes"]])
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def read_cell(page, box):
    """칸 → [(앞말 서명 or None, 정수)] 또는 [] (빈칸/'-'/'·') 또는 None(읽을 수 없음)."""
    out = []
    for ln in text_lines(glyphs(contours(page, box))):
        ln = [g for g in ln if g["ch"] != "·"]  # 빈칸 표시 점(숫자 옆에 남은 점 포함)은 버림
        if not ln:
            continue
        # 맨 오른쪽부터 숫자/쉼표 연속 구간
        k = len(ln)
        while k > 0 and ln[k - 1]["ch"] is not None and (ln[k - 1]["ch"].isdigit() or ln[k - 1]["ch"] == ","):
            k -= 1
        digits = ln[k:]
        lab = [g for g in ln[:k] if g["ch"] != "·"]
        if not digits:
            if all(g["ch"] in ("·", "–") for g in ln):
                continue
            return None
        s = "".join(g["ch"] for g in digits)
        if not re.fullmatch(r"\d{1,3}(,\d{3})*|\d+", s):
            return None
        # 숫자 사이 간격 확인(떨어진 숫자 둘을 붙여 읽지 않도록): 글자 중심 간격이 한 글자 폭(약 4.5pt) 안팎이어야 함
        for a, b in zip(digits, digits[1:]):
            if (b["x0"] + b["x1"]) / 2 - (a["x0"] + a["x1"]) / 2 > 6.5:
                return None
        out.append((label_sig(lab) if lab else None, int(s.replace(",", ""))))
    return out


# ---------------------------------------------------------------- 표 격자
def _merge(xs, tol=1.6):
    out = []
    for x in sorted(xs):
        if not out or x - out[-1] > tol:
            out.append(x)
    return out


def grid(page):
    L = page.lines
    hs = [l for l in L if abs(l["top"] - l["bottom"]) < 0.1]
    vs = [l for l in L if abs(l["x0"] - l["x1"]) < 0.1 and l["bottom"] - l["top"] > 3]
    t = page.find_tables()[0]
    y0, y1 = t.bbox[1], t.bbox[3]
    cov = defaultdict(float)
    for v in vs:
        cov[round(v["x0"], 1)] += v["bottom"] - v["top"]
    xs = _merge([x for x, c in cov.items() if c > (y1 - y0) * 0.3])
    left = min(h["x0"] for h in hs if y0 - 1 <= h["top"] <= y1 + 1)
    right = max(h["x1"] for h in hs if y0 - 1 <= h["top"] <= y1 + 1)
    xm = (xs[0] + xs[1]) / 2
    ys = _merge([h["top"] for h in hs if h["x0"] <= xm <= h["x1"] and y0 - 1 <= h["top"] <= y1 + 1])
    xd = (left + xs[0]) / 2
    yd = _merge([h["top"] for h in hs if h["x0"] <= xd <= h["x1"] and y0 - 1 <= h["top"] <= y1 + 1])
    if right - xs[-1] < 2:
        xs = xs[:-1]
    return [left] + xs + [right], ys, yd


def ops_multiset(page, box):
    return sorted(c["ops"] for c in contours(page, box))


# ---------------------------------------------------------------- 텍스트 쪽(대조용)
def text_checks(pdf):
    def pt(n):
        return pdf.pages[n - 1].extract_text() or ""
    got = {}
    for n, key in ((14, "수시_종합_DoDream"), (15, "수시_종합_불교추천인재"), (16, "특성화고교졸업자(정원외)"),
                   (17, "특수교육대상자(정원외)"), (18, "수시_교과_학교장추천인재"), (19, "수시_교과_기회균형통합"),
                   (21, "수시_논술"), (23, "수시_실기")):
        m = re.search(r"모집인원\s*:\s*([\d,]+)명", pt(n))
        got[key] = int(m.group(1).replace(",", "")) if m else None
    for n, keys in ((28, ("정시_수능_가", "정시_수능_나", "정시_수능_다")),
                    (29, ("농어촌 가", "농어촌 나", "농어촌 다")),
                    (30, ("기초 가", "기초 나", "기초 다"))):
        m = re.search(r"모집인원\s+(\d+)명\s+(\d+)명\s+(\d+)명", pt(n))
        for k, v in zip(keys, m.groups() if m else (None,) * 3):
            got[k] = int(v) if v else None
    # 23쪽 실기 모집단위별: 국어국문·문예창작학부, 체육교육과, 미술학부(불교미술, 한국화, 서양화),
    # 연극학부(실기형, 특기형), 스포츠문화학과, 한국음악과 순
    m = re.search(r"모집인원\s+((?:\d+명\d?\)?\s*)+)", pt(23))
    silgi = [int(x) for x in re.findall(r"(\d+)명", m.group(1))] if m else []
    # 17쪽 특수교육대상자 모집단위
    t17 = pt(17)
    special = re.findall(r"모집단위\s+(.+)", t17)
    special_units = [u for line in special for u in line.split()]
    return got, silgi, special_units


# ---------------------------------------------------------------- 본체
def main(pdf_path, out_path):
    memo, unread = [], []
    label_seen = defaultdict(list)
    with pdfplumber.open(pdf_path) as pdf:
        G = {pn: grid(pdf.pages[pn - 1]) for pn in (7, 8, 9, 10)}
        # 열 개수 확인
        for pn in (7, 8):
            assert len(G[pn][0]) - 1 == 2 + len(SUSI_COLS), (pn, len(G[pn][0]))
        for pn in (9, 10):
            assert len(G[pn][0]) - 1 == 2 + len(JEONGSI_COLS), (pn, len(G[pn][0]))

        cells = {}  # (block, i, 'S'/'J', col) → read_cell 결과
        align = []
        for blk, (ps, pj) in PAGES.items():
            names = NAMES[blk]
            n = len(names)
            xs_s, ys_s, yd_s = G[ps]
            xs_j, ys_j, yd_j = G[pj]
            has_total = blk == "B"
            assert len(ys_s) - 1 == 1 + n + (1 if has_total else 0), (ps, len(ys_s))
            assert len(ys_j) - 1 == 1 + n + (1 if has_total else 0), (pj, len(ys_j))
            # 대학 띠 개수 확인
            assert len(yd_s) - 1 == 1 + len(DAE[blk]) + (1 if has_total else 0), (ps, yd_s)
            assert len(yd_j) - 1 == 1 + len(DAE[blk]) + (1 if has_total else 0), (pj, yd_j)
            for i in range(1, n + 1 + (1 if has_total else 0)):
                # 이름 칸 윤곽 구성 비교(수시표 행 i == 정시표 행 i)
                if i <= n:
                    a = ops_multiset(pdf.pages[ps - 1], (xs_s[1], ys_s[i], xs_s[2], ys_s[i + 1]))
                    b = ops_multiset(pdf.pages[pj - 1], (xs_j[1], ys_j[i], xs_j[2], ys_j[i + 1]))
                    if not a:
                        raise SystemExit(f"p{ps} 행 {i}: 이름 칸이 비어 있음")
                    align.append(a == b)
                for tag, pn, xs, ys, cols in (("S", ps, xs_s, ys_s, SUSI_COLS), ("J", pj, xs_j, ys_j, JEONGSI_COLS)):
                    for j in range(len(cols)):
                        box = (xs[j + 2], ys[i], xs[j + 3], ys[i + 1])
                        cells[(blk, i, tag, j)] = read_cell(pdf.pages[pn - 1], box)
            # 대학 띠 윤곽 비교
            for k in range(1, len(DAE[blk]) + 1):
                a = ops_multiset(pdf.pages[ps - 1], (xs_s[0], yd_s[k], xs_s[1], yd_s[k + 1]))
                b = ops_multiset(pdf.pages[pj - 1], (xs_j[0], yd_j[k], xs_j[1], yd_j[k + 1]))
                align.append(a == b)
            # 대학 띠 행 수 확인
            for k, (dn, cnt) in enumerate(DAE[blk], start=1):
                inside = [r for r in range(1, n + 1) if yd_s[k] - 0.5 <= ys_s[r] and ys_s[r + 1] <= yd_s[k + 1] + 0.5]
                assert len(inside) == cnt, (blk, dn, len(inside), cnt)
        texts, silgi_units, special_units = text_checks(pdf)

    # 앞말 서명 → 이름: 같은 칸 안 줄 순서와 PDF 렌더링(7~10쪽)으로 확인한 대응
    # (불교학부·문화유산학과 불교추천인재 = 일반/승려, 경찰행정학부 논술·열린전공학부 = 인문/자연, 연극학부 실기 = 실기/특기)
    def sig_at(blk, i, tag, j, line):
        v = cells[(blk, i, tag, j)]
        return v[line][0] if v and len(v) > line else None
    iA = NAMES["A"].index
    iB = NAMES["B"].index
    S = {name: j for j, name in enumerate(["DoDream", "불교", "특성화", "특수", "학교장", "기회", "논술", "실기", "재외", "계"])}
    LAB = {
        sig_at("A", iA("불교학부") + 1, "S", S["불교"], 0): "일반",
        sig_at("A", iA("불교학부") + 1, "S", S["불교"], 1): "승려",
        sig_at("A", iA("경찰행정학부") + 1, "S", S["논술"], 0): "인문",
        sig_at("A", iA("경찰행정학부") + 1, "S", S["논술"], 1): "자연",
        sig_at("B", iB("연극학부") + 1, "S", S["실기"], 0): "실기",
        sig_at("B", iB("연극학부") + 1, "S", S["실기"], 1): "특기",
    }
    assert None not in LAB and len(LAB) == 6, LAB

    rows = []
    split_notes = []
    aux_ok, aux_bad = 0, []
    colsum = Counter()   # 정원내+정원외 전 열 합(텍스트 쪽 대조용)
    for blk in ("A", "B"):
        ps, pj = PAGES[blk]
        dae_list = [d for d, c in DAE[blk] for _ in range(c)]
        for idx, raw_name in enumerate(NAMES[blk]):
            i = idx + 1
            name = raw_name.replace("★", "")
            per_label = defaultdict(dict)  # 앞말 → {key: n}  (인문/자연 나눔용)
            inwon = {}
            bad = []
            tot = {}
            for tag, cols in (("S", SUSI_COLS), ("J", JEONGSI_COLS)):
                ssum = 0
                for j, d in enumerate(cols):
                    v = cells[(blk, i, tag, j)]
                    if v is None:
                        bad.append(f"{'수시' if tag == 'S' else '정시'} {d if isinstance(d, str) else d[0]}")
                        continue
                    if d == "계":
                        if len(v) == 1 and v[0][0] is None:
                            tot[tag] = v[0][1]
                        elif not v:
                            tot[tag] = 0  # '–' (모집 안 함)
                        else:
                            bad.append(f"{tag} 계 칸 형식")
                        continue
                    for sig, n in v:
                        lab = LAB.get(sig) if sig else None
                        if sig and lab is None:
                            bad.append(f"{d if isinstance(d, str) else d[0]} 앞말 미확인")
                            continue
                        ssum += n
                        ck = d if isinstance(d, str) else d[0]
                        colsum[(ck, lab)] += n
                        if isinstance(d, str):
                            continue  # 정원외
                        if lab:
                            label_seen[(name, d[0])].append((lab, n))
                        per_label[lab][d[0]] = per_label[lab].get(d[0], 0) + n
                        inwon[d[0]] = inwon.get(d[0], 0) + n
                if tag in tot:
                    if ssum == tot[tag]:
                        aux_ok += 1
                    else:
                        aux_bad.append(f"{name} {'수시' if tag == 'S' else '정시'} 계 {tot[tag]} ≠ 칸 합 {ssum}")
            if bad:
                unread.append(f"{name}: " + ", ".join(bad))
                continue
            dae = dae_list[idx]
            labs = set(per_label) - {None}
            if labs == {"인문", "자연"} and name == "열린전공학부":
                # PDF가 칸마다 인문/자연 인원을 따로 적음 → 계열별 두 행
                assert not per_label.get(None), per_label
                for lab in ("인문", "자연"):
                    rows.append({"단과대학": dae, "모집단위": f"{name}({lab})", "계열": lab,
                                 "인원": dict(per_label[lab]), "계": None, "쪽": ps, "검증": "합계칸없음"})
                split_notes.append(f"{name}: 학교장추천인재·기회균형통합·논술·정시 다군 칸이 '인문 n / 자연 n'으로 나뉘어 있어 "
                                   f"'{name}(인문)', '{name}(자연)' 두 행으로 적음(계열 인문/자연)")
                continue
            rows.append({"단과대학": dae, "모집단위": name, "계열": None, "인원": inwon, "계": None, "쪽": ps,
                         "검증": "합계칸없음"})

    # 한 칸에 앞말 두 줄이 있는 경우(합산) 메모
    for (name, key), lst in label_seen.items():
        if name == "열린전공학부":
            continue
        split_notes.append(f"{name} {key}: 칸에 " + ", ".join(f"{l} {n}" for l, n in lst)
                           + f" 두 줄 → 같은 전형이라 합 {sum(n for _, n in lst)}으로 적음")

    # ---------------- 총계 대조 (8쪽·10쪽 '계' 행)
    def total_row(blk, tag, cols):
        i = len(NAMES[blk]) + 1
        out = {}
        for j, d in enumerate(cols):
            v = cells[(blk, i, tag, j)]
            key = d if isinstance(d, str) else d[0]
            out[key] = v[0][1] if v and len(v) == 1 and v[0][0] is None else None
        return out
    ts = total_row("B", "S", SUSI_COLS)
    tj = total_row("B", "J", JEONGSI_COLS)
    mine = Counter()
    for r in rows:
        for k, v in r["인원"].items():
            mine[k] += v
    col_res = []
    for d in SUSI_COLS + JEONGSI_COLS:
        if d == "계":
            continue
        key = d if isinstance(d, str) else d[0]
        pdfv = ts.get(key) if key in ts else tj.get(key)
        ours = sum(v for (k, _), v in colsum.items() if k == key)
        col_res.append((key, ours, pdfv))
    col_bad = [f"{k} {a}≠{b}" for k, a, b in col_res if a != b]
    susi_in = sum(v for k, v in mine.items() if k.startswith("수시"))
    jeong_in = sum(v for k, v in mine.items() if k.startswith("정시"))
    susi_pdf_in = sum(ts[d[0]] for d in SUSI_COLS if isinstance(d, tuple))
    jeong_pdf_in = sum(tj[d[0]] for d in JEONGSI_COLS if isinstance(d, tuple))
    susi_all = sum(v for v in ts.values() if v is not None) - (ts["계"] or 0)
    jeong_all = sum(v for v in tj.values() if v is not None) - (tj["계"] or 0)

    # ---------------- 텍스트 쪽 대조
    tx = []
    def chk(label, ours, theirs):
        tx.append(f"{label} {ours}={theirs}" if ours == theirs else f"{label} {ours}≠{theirs}(불일치)")
    for key in ("수시_종합_DoDream", "수시_종합_불교추천인재", "수시_교과_학교장추천인재", "수시_교과_기회균형통합",
                "수시_논술", "수시_실기", "정시_수능_가", "정시_수능_나", "정시_수능_다"):
        chk(key, mine[key], texts.get(key))
    for ck, tk in (("정원외:학생부종합 기회균형 특성화고교졸업자", "특성화고교졸업자(정원외)"),
                   ("정원외:학생부종합 기회균형 특수교육대상자", "특수교육대상자(정원외)"),
                   ("정원외:농어촌학생 가군", "농어촌 가"), ("정원외:농어촌학생 나군", "농어촌 나"), ("정원외:농어촌학생 다군", "농어촌 다"),
                   ("정원외:기초생활수급자및차상위계층 가군", "기초 가"), ("정원외:기초생활수급자및차상위계층 나군", "기초 나"),
                   ("정원외:기초생활수급자및차상위계층 다군", "기초 다")):
        chk(tk, sum(v for (k, _), v in colsum.items() if k == ck), texts.get(tk))
    # 23쪽 실기 모집단위별
    def silgi_of(name, lab=None):
        for blk in ("A", "B"):
            if name in NAMES[blk]:
                i = NAMES[blk].index(name) + 1
                v = cells[(blk, i, "S", S["실기"])] or []
                return sum(n for s, n in v if (lab is None or LAB.get(s) == lab))
    ours_silgi = [silgi_of("국어국문·문예창작학부"), silgi_of("체육교육과"), silgi_of("불교미술전공"), silgi_of("한국화전공"),
                  silgi_of("서양화전공"), silgi_of("연극학부", "실기"), silgi_of("연극학부", "특기"),
                  silgi_of("스포츠문화학과"), silgi_of("한국음악과")]
    chk("23쪽 실기 모집단위별(국어국문·문예창작, 체육교육, 불교미술, 한국화, 서양화, 연극 실기형, 연극 특기형, 스포츠문화, 한국음악)",
        ours_silgi, silgi_units)
    # 17쪽 특수교육대상자 모집단위(정원외, 열 판별 확인용)
    sp_ours = []
    for blk in ("A", "B"):
        for idx, nm in enumerate(NAMES[blk]):
            v = cells[(blk, idx + 1, "S", S["특수"])] or []
            if sum(n for _, n in v):
                sp_ours.append(nm.replace("★", "").replace("·", "･"))
    sp_text = [u.split("(")[0] for u in special_units]
    chk("17쪽 특수교육대상자 모집단위", sp_ours, sp_text)

    # ---------------- 전형 목록·메모
    used = {k for r in rows for k in r["인원"]}
    jlist = [{"key": d[0], "시기": d[1], "유형": d[2], "전형명": d[3], "군": d[4]}
             for d in SUSI_COLS + JEONGSI_COLS if isinstance(d, tuple) and d[0] in used]

    memo.append("정원내만 수록: 수시 학생부종합 기회균형(특성화고교졸업자·특수교육대상자), 재외국민(중고교과정국외이수자), "
                "정시 농어촌학생·기초생활수급자및차상위계층(가/나/다군), 전형기간 자율화 특성화고등을졸업한재직자·전교육과정국외이수자/북한이탈주민(11쪽)은 정원외라 넣지 않음")
    memo.append("PDF 7~10쪽 표의 글자가 텍스트가 아닌 벡터 윤곽선이라, 숫자는 윤곽 경로 명령 순서+구멍 수로 0~9를 판별해 읽음(판별표에 없는 윤곽이 있는 칸은 읽지 않음). "
                "모집단위·대학 이름은 렌더링한 쪽에서 옮겨 적은 목록을 쓰고, 수시표·정시표 같은 행 이름 칸 윤곽 구성 일치로 행 정렬 확인: "
                f"{sum(align)}/{len(align)}칸 일치")
    memo.append("표의 '수시모집 계'·'정시모집 계' 칸은 정원외 전형까지 더한 값이고, 수시·정시를 합친 행별 합계 칸은 없음 → 계=null, 검증='합계칸없음'")
    memo.append(f"보조 대조(행의 수시모집 계·정시모집 계 = 같은 표 그 행 전 칸 합, 정원외 포함): {aux_ok}건 일치"
                + (", 불일치: " + "; ".join(aux_bad) if aux_bad else ""))
    memo.append(f"총계 대조(8쪽 수시 '계' 행·10쪽 정시 '계' 행 정원내 열 합 = 정리 데이터 합): 수시 {susi_in}={susi_pdf_in}, 정시 {jeong_in}={jeong_pdf_in}"
                f" (정원외 포함 전 열 합: 수시 {susi_all}={ts['계']}, 정시 {jeong_all}={tj['계']})"
                + ("; 전형별 열 합 모두 일치" if not col_bad else "; 전형별 열 불일치: " + "; ".join(col_bad)))
    memo.append("텍스트 쪽 대조(같은 PDF 14~30쪽 텍스트의 전형별 모집인원): " + "; ".join(tx))
    memo.extend(split_notes)
    memo.append("'★'(2026.04. 기준 광역화 모집단위 표시)는 이름에서 뺌: 경영대학, 바이오시스템대학, 열린전공학부")
    memo.append("단과대학: 표의 '대학' 칸 글자 그대로(불교·문과·이과·법과·사회과학·경찰사법·경영·바이오시스템·공과·첨단융합·사범·예술·약학). "
                "열린전공학부는 대학 칸과 모집단위 칸이 합쳐져 단과대학 null. 모집단위 이름은 표 그대로(23쪽은 불교미술·한국화·서양화를 '미술학부' 아래에 적음)")
    memo.append("계열: 표에 계열 칸이 없어 null(열린전공학부만 PDF가 인문/자연을 밝힘)")
    memo.append("빈칸 안의 작은 점(·)과 회색 칸(조소전공 수시, 불교미술·한국화·서양화·연극학부·스포츠문화학과·한국음악과 정시), 계 칸 '–'는 0으로 봄")
    memo.append("정시 체육교육과(가군)·조소전공(나군)은 수능 60%+실기 40%이나 PDF가 '수능위주 일반' 전형으로 분류 → 유형 수능")
    memo.append("모집인원은 2026학년도 미충원 이월인원을 반영한 2026.04. 기준(5쪽 각주). 수시 정원내 미충원은 정시 일반전형 같은 모집단위로 이월")
    memo.append("쪽 = 수시표 PDF 쪽(7 또는 8). 같은 모집단위의 정시 인원은 PDF 9·10쪽")
    if unread:
        memo.append("읽지 못해 뺀 행: " + "; ".join(unread))

    out = {"id": ID, "이름": NAME, "출처쪽": [7, 8, 9, 10], "전형": jlist, "모집단위": rows, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(ID, len(rows), "rows", dict(Counter(r["검증"] for r in rows)), "unread", len(unread))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
