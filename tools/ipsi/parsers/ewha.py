#!/usr/bin/env python3
"""이화여자대학교 2028 시행계획 파서.

이 PDF는 텍스트층이 없다(글자가 모두 벡터 도형으로 그려져 있음, 'Microsoft: Print To PDF').
그래서 OCR 대신 pdfplumber가 주는 도형 정보로 직접 읽는다.
  - 숫자: 글자 윤곽선(path 명령 순서)의 서명 → 숫자 대응표(DIGIT)로 판독. 추정 없음, 모르는 도형이면 중단.
  - 모집단위·대학 이름: 칸 안 도형 묶음의 모양 해시 → 이름 대응표(NAME_BY_HASH).
    대응표는 해당 쪽을 렌더링한 이미지를 눈으로 읽어 만든 것. 모르는 해시면 중단(다른 PDF에 잘못 적용되지 않게).
대상 표: "02 전형별 모집인원 – 전형별·모집단위별 모집인원(정원 내 기준)" (PDF 5~6쪽),
총계 대조: "01 입학전형 개요" 표(PDF 3쪽) 모집인원 칸.
사용법: python3 -I tools/ipsi/parsers/ewha.py <pdf> <out.json> [--dump]
"""
import hashlib
import json
import sys

import pdfplumber

UNIV_ID = "ewha"
UNIV_NAME = "이화여자대학교"
PAGES = (5, 6)
OVERVIEW_PAGE = 3

TS = dict(vertical_strategy="lines", horizontal_strategy="lines", edge_min_length_prefilter=9,
          edge_min_length=9, snap_tolerance=2, join_tolerance=2, intersection_tolerance=2)

# 글자 도형 서명(가장 큰 윤곽의 path 명령 + 나머지 윤곽 명령 정렬) → 문자
DIGIT = {
    "R": "-",
    "mlccllllh": "1",
    "mlclccclccclclh": "2", "mclccclclllclcch": "2",
    "mccclcccclcccclccch": "3",
    "mllllllllllh/mllh": "4",
    "mcllllllcccclccch": "5", "mcllllllccccclccch": "5",
    "mcccclcccccch/mcccch": "6",
    "mllcclcclh": "7",
    "mcccccccch/mcccch/mcccch": "8",
    "mcccccclcccch/mcccch": "9", "mcccccclcccch/mccccch": "9",
    "mcccch/mcccch": "0",
    "mllclcclh": ",",
    "mcclcch": "P",  # 괄호 ( )
}

# 수시 8열 + 정시 7열(5~6쪽 표 왼→오 순서)
SUSI_COLS = [
    ("수시_교과_고교추천", "학생부교과", "고교추천전형"),
    ("수시_종합_미래인재서류", "학생부종합", "미래인재전형-서류형"),
    ("수시_종합_미래인재면접", "학생부종합", "미래인재전형-면접형"),
    ("수시_종합_고른기회", "학생부종합", "고른기회전형"),
    ("수시_종합_사회기여자", "학생부종합", "사회기여자전형"),
    ("수시_논술", "논술", "논술전형"),
    ("수시_실기_예체능실기", "실기/실적", "예체능실기전형"),
    ("수시_종합_예체능서류", "학생부종합", "예체능서류전형"),
]
JEONGSI_COLS = [("수능", "가"), ("수능", "나"), ("수능", "다"), ("수능학생부", "가"), ("수능학생부", "나"),
                ("예체능실기", "가"), ("예체능실기", "나")]
JEONGSI_DEF = {
    "수능": ("정시_수능", "수능", "수능전형"),
    "수능학생부": ("정시_수능학생부", "수능", "수능-학생부전형"),
    "수능예체능실기": ("정시_수능예체능실기", "수능", "예체능실기전형(수능)"),
    "실기예체능실기": ("정시_실기예체능실기", "실기/실적", "예체능실기전형(실기/실적)"),
}
# 정시 '예체능실기' 열은 PDF p3·p16~17 기준 두 전형이 섞여 있음:
#   수능(예체능실기전형) 226 = 조형예술학부 각 전공 + 디자인학부(수능위주) + 체육과학부
#   실기/실적(예체능실기전형) 142 = 음악대학(건반악기·관현악·성악·작곡) + 디자인학부(실기위주)
YECHE_BY_COLLEGE = {"음악대학": "실기예체능실기", "조형예술대학": "수능예체능실기", "신산업융합대학": "수능예체능실기"}
ANNOT_TO_KIND = {"수능위주": "수능예체능실기", "실기위주": "실기예체능실기"}

# 모양 해시 → 이름 (렌더링 이미지로 확인)
NAME_BY_HASH = {}  # 아래 _NAMES에서 채움
_NAMES = """
d770c48b4acc 인문과학대학
d4cd3c51b328 사회과학대학
d324d628cc3d 자연과학대학
8f238568cf0f 공과대학
18d345839237 경영대학
963a72dd9166 신산업융합대학
56bbb3ccae93 인공지능대학
9f3a0c9ce300 국어국문학과
ed8acf604a33 중어중문학과
65cfb4d2b856 불어불문학과
8c3dc98f351c 독어독문학과
abd07169bed1 사학과
3800e6be4f8f 철학과
55af23a15dec 기독교학과
cbadd701728f 영어영문학부
206ff2c965ed 정치외교학과
ec630ff9a05f 행정학과
d0632237a67b 경제학과
280c34cf327b 문헌정보학과
a21af6e3ca32 사회학과
87bb70c4a382 사회복지학과
c0087bd35c31 심리학과
1aa251e0a787 소비자학과
3604d1737730 커뮤니케이션·미디어학부
796cb044cf5a 수학과
6fe83be7bc25 통계학과
addfa4e84f88 물리학과
37a644887e21 화학·나노과학과
ef643e937014 생명과학과
f1a2e8789f1b 식품생명공학과
27fd376256fa 화공신소재공학과
99ae1b747f54 건축학과
dd972cebc12d 건축도시시스템공학과
9010d0865dd6 환경공학과
1e42832df300 기후에너지시스템공학과
cc77281a0d20 휴먼기계바이오공학과
e9eb608eae3b 경영학부
24f5dda3979d 융합콘텐츠학과
c60a57650f06 의류산업학과
af94b720d648 국제사무학과
cef97ec45d79 식품영양학과
e087e35bf8b4 융합보건학과
0125d158451a 컴퓨터공학과
3365cbfef1b8 사이버보안학과
cd724980dd15 공과대학
40c190f6aee8 사범대학
bc6817905e2b 의과대학
1b7d9f031b20 간호대학
50530d767191 약학대학
0580226ff7f9 스크랜튼대학
6551a01dfa8d 음악대학
156a43a1d412 조형예술대학
f2134dd67edb 신산업융합대학
a34bcea3d70e 교육학과
0055f624635a 유아교육과
09315e16d13f 초등교육과
0f843a639295 교육공학과
8cbfaa19dec8 특수교육과
07f3177dd4d5 영어교육과
18d5280bb979 국어교육과
806c9aa9b9b4 과학교육과
ad75205b71c4 수학교육과
840d2fd7713f 의예과
9f607793420b 간호학부
d7321bfd9790 스크랜튼학부
b168d81e5709 뇌·인지과학부
9d99c461a2ee 국제학부
260b9c63c3de 인공지능데이터사이언스학부
e4e6042a8d63 건반악기과
e0de9626c8a6 관현악과
2abcbd299c9d 성악과
f9cb48197d96 작곡과
02c7b7b9ac53 한국음악과
58c05c2dd22c 무용과
53d273f96f23 디자인학부
63325da34944 체육과학부
0e40d552d578 융합전자반도체공학부
60aa0cd0aa23 사회과교육과
5b79f54c0c77 약학부
42699fdb2510 조형예술학부
b8e4e65c67a8 전자전기공학전공
7e94f16b48c5 지능형반도체공학전공
62088ed6fb5f 역사교육전공
9904084567fb 사회교육전공
1d742a535866 지리교육전공
e3e5c3f8dbac 약학전공
2f8957a4b286 미래산업약학전공
b28c2dac0b65 동양화전공
46138e2fa60a 서양화전공
3eb1c21dd03c 조소전공
d6704b4dce03 도자예술전공
9baa29131178 섬유예술전공
b7fce35a9052 패션예술전공
3337e6ffff10 수능위주
4b1f4d52c3e7 실기위주
"""


def color_ok(c, allow_green):
    if not (isinstance(c, tuple) and len(c) == 3):
        return False
    if allow_green:
        return min(c) < 0.6
    return max(c) < 0.5 and not (c[1] > c[0] + 0.2)


def ink(page, bbox, allow_green=False, maxw=40):
    x0, y0, x1, y1 = bbox
    out = []
    for kind in ("curves", "rects"):
        for o in getattr(page, kind):
            if not o.get("fill") or not color_ok(o.get("non_stroking_color"), allow_green):
                continue
            if o["width"] > maxw or o["height"] > 12:
                continue
            if o["x0"] >= x0 - .3 and o["x1"] <= x1 + .3 and o["top"] >= y0 - .3 and o["bottom"] <= y1 + .3:
                out.append(o)
    return out


def cmd(o):
    return "".join(x[0] for x in (o.get("path") or [])) if o["object_type"] == "curve" else "R"


def text_lines(objs):
    objs = sorted(objs, key=lambda o: o["top"])
    lines = []
    for o in objs:
        if lines and o["top"] < lines[-1]["bottom"] + 0.5:
            ln = lines[-1]
            ln["o"].append(o)
            ln["bottom"] = max(ln["bottom"], o["bottom"])
        else:
            lines.append({"top": o["top"], "bottom": o["bottom"], "o": [o]})
    return lines


def glyphs(objs):
    gl = []
    for o in sorted(objs, key=lambda o: o["x0"]):
        if gl and o["x0"] < gl[-1]["x1"] - 0.2:
            gl[-1]["o"].append(o)
            gl[-1]["x1"] = max(gl[-1]["x1"], o["x1"])
        else:
            gl.append({"x0": o["x0"], "x1": o["x1"], "o": [o]})
    return gl


def glyph_key(g):
    os_ = sorted(g["o"], key=lambda o: -(o["width"] * o["height"]))
    return "/".join([cmd(os_[0])] + sorted(cmd(o) for o in os_[1:]))


def decode_line(objs, where):
    out = ""
    for g in glyphs(objs):
        k = glyph_key(g)
        if k not in DIGIT:
            raise SystemExit(f"{where}: 모르는 숫자 도형 {k}")
        out += DIGIT[k]
    return out


def shape_hash(objs):
    if not objs:
        return None
    gx, gy = min(o["x0"] for o in objs), min(o["top"] for o in objs)
    items = sorted((cmd(o), round((o["x0"] - gx) * 2), round((o["top"] - gy) * 2),
                    round(o["width"] * 2), round(o["height"] * 2)) for o in objs)
    return hashlib.sha1(repr(items).encode()).hexdigest()[:12]


def read_cell_number(page, cell, where):
    """칸 → (숫자문자열, 주석해시). 첫 줄은 숫자, 그 아래 줄들은 주석(모양 해시)."""
    lines = text_lines(ink(page, cell))
    if not lines:
        return "", None
    num = decode_line(lines[0]["o"], where)
    rest = [o for ln in lines[1:] for o in ln["o"]]
    ann = None
    if rest:
        ann = shape_hash(ink(page, (cell[0], lines[1]["top"] - .2, cell[2], cell[3]), allow_green=True, maxw=30))
    return num, ann


def to_int(s, where):
    s = s.replace(",", "")
    if s in ("", "-"):
        return 0
    if s.isdigit():
        return int(s)
    raise SystemExit(f"{where}: 숫자 아님 {s!r}")


def name_of(page, cell, dump, label):
    h = shape_hash(ink(page, cell, allow_green=True, maxw=30))
    if dump:
        print(f"DUMP p{page.page_number} {label} {[round(v, 1) for v in cell]} {h}")
        return f"?{h}"
    if h not in NAME_BY_HASH:
        raise SystemExit(f"p{page.page_number} {label} {[round(v, 1) for v in cell]}: 모르는 이름 도형 {h}")
    return NAME_BY_HASH[h]


def find_main_table(page):
    # 표 본문 오른쪽 끝에 세로선이 없어(머리글 초록 칸만 539까지) 마지막 열이 칸으로 안 잡힌다.
    # 머리글 초록 채움 칸의 오른쪽 끝 x를 명시적 세로선으로 더한다.
    green = [r for r in page.rects if r.get("fill") and r["width"] > 15 and r["height"] > 10
             and isinstance(r.get("non_stroking_color"), tuple) and len(r["non_stroking_color"]) == 3
             and r["non_stroking_color"][1] > r["non_stroking_color"][0] + 0.2 and r["x1"] < page.width - 50]
    # 표 왼쪽 바깥 테두리도 없어(대학 칸) 머리글 왼쪽 끝 x를 세로선으로 더한다.
    settings = dict(TS)
    if green:
        top = min(r["top"] for r in green)
        bot = page.height - 40
        settings["explicit_vertical_lines"] = [
            {"object_type": "line", "x0": x, "x1": x, "top": top, "bottom": bot, "width": 0, "height": bot - top}
            for x in (min(r["x0"] for r in green), max(r["x1"] for r in green))]
    ts = [t for t in page.find_tables(settings) if t.bbox[2] - t.bbox[0] > 300]
    if len(ts) != 1:
        raise SystemExit(f"p{page.page_number}: 표를 하나로 특정 못함({len(ts)})")
    return ts[0]


def near(a, b, tol=0.8):
    return abs(a - b) <= tol


def parse_page(page, dump):
    t = find_main_table(page)
    cells = sorted({tuple(c) for c in t.cells}, key=lambda c: (c[1], c[0]))
    left = min(c[0] for c in cells)
    right = max(c[2] for c in cells)
    # 숫자 열 시작 x: 이름 칸 오른쪽 끝(= 데이터 행의 첫 숫자 칸 x0). 이름 칸은 93.8에서 시작.
    name_x0 = sorted({round(c[0], 1) for c in cells})[1]
    # 데이터 행 후보: 숫자만 들어 있는 칸 중 가장 왼쪽 열
    num_x0 = None
    for c in cells:
        if c[0] <= name_x0 + 1:
            continue
        objs = ink(page, c)
        if not objs:
            continue
        try:
            decode_line(text_lines(objs)[0]["o"], "")
        except SystemExit:
            continue
        num_x0 = c[0] if num_x0 is None else min(num_x0, c[0])
    col0 = [c for c in cells if near(c[0], num_x0)]
    rows = []
    for c in col0:
        objs = ink(page, c)
        try:
            v = decode_line(text_lines(objs)[0]["o"], "") if objs else None
        except SystemExit:
            v = None
        if v is not None:
            rows.append((c[1], c[3]))
    body_top = rows[0][0]
    # 열 구간: 본문 칸들의 (x0,x1) 중 다른 구간에 포함되지 않는 것
    ivs = sorted({(round(c[0], 1), round(c[2], 1)) for c in cells if c[1] >= body_top - .5 and c[0] >= num_x0 - .5})
    cols = [iv for iv in ivs if not any(o != iv and o[0] <= iv[0] + .3 and o[1] >= iv[1] - .3 for o in ivs)]
    if len(cols) != 15:
        raise SystemExit(f"p{page.page_number}: 숫자 열 {len(cols)}개(15개여야 함): {cols}")
    return t, cells, rows, cols, left, name_x0, num_x0


def main(pdf_path, out_path, dump=False):
    for line in _NAMES.strip().splitlines():
        h, nm = line.split(None, 1)
        NAME_BY_HASH[h] = nm.strip()

    units, memo_extra = [], []
    total_row = None
    jeonhyeong_used = set()
    with pdfplumber.open(pdf_path) as pdf:
        for pno in PAGES:
            page = pdf.pages[pno - 1]
            t, cells, rows, cols, left, name_x0, num_x0 = parse_page(page, dump)
            page_rows = []
            for (y0, y1) in rows:
                yc = (y0 + y1) / 2
                where = f"p{pno} y={y0:.1f}"
                # 합계 행: 대학 칸부터 이름 칸까지 하나로 합쳐진 칸
                is_total = any(near(c[0], left) and near(c[2], num_x0) and c[1] <= yc <= c[3] for c in cells)
                vals = []
                for ci, (cx0, cx1) in enumerate(cols):
                    inside = [c for c in cells if c[0] >= cx0 - .3 and c[2] <= cx1 + .3 and c[1] <= yc <= c[3]]
                    if not inside:
                        raise SystemExit(f"{where}: {ci}열 칸 없음")
                    parts = []
                    for c in sorted(inside, key=lambda c: c[0]):
                        num, ann = read_cell_number(page, c, f"{where} {ci}열")
                        own = near(c[1], y0) and near(c[3], y1)
                        parts.append({"cell": c, "num": num, "ann": ann, "own": own})
                    vals.append(parts)
                if is_total:
                    total_row = vals
                    continue
                college_cell = [c for c in cells if near(c[0], left) and near(c[2], name_x0) and c[1] <= yc <= c[3]]
                if len(college_cell) != 1:
                    raise SystemExit(f"{where}: 대학 칸 못 찾음")
                college = name_of(page, college_cell[0], dump, "대학")
                ncells = sorted([c for c in cells if c[0] >= name_x0 - .5 and c[2] <= num_x0 + .5 and c[1] <= yc <= c[3]],
                                key=lambda c: c[0])
                if len(ncells) == 1:
                    group, gcell = None, None
                    name = name_of(page, ncells[0], dump, "모집단위")
                elif len(ncells) == 2:
                    gcell = ncells[0]
                    group = name_of(page, gcell, dump, "묶음")
                    name = f"{group}({name_of(page, ncells[1], dump, '전공')})"
                else:
                    raise SystemExit(f"{where}: 이름 칸 {len(ncells)}개")
                page_rows.append({"y0": y0, "y1": y1, "college": college, "group": group, "gcell": gcell,
                                  "name": name, "vals": vals, "page": pno})
            units.extend(build_units(page_rows, pno, memo_extra))

        overview = read_overview(pdf.pages[OVERVIEW_PAGE - 1])

    if dump:
        return
    for u in units:
        u["검증"] = "합계칸없음"
        jeonhyeong_used.update(u["인원"])

    # 전형 목록
    jlist = [{"key": k, "시기": "수시", "유형": y, "전형명": n, "군": None} for k, y, n in SUSI_COLS]
    for kind in ("수능", "수능학생부", "수능예체능실기", "실기예체능실기"):
        base, y, n = JEONGSI_DEF[kind]
        for g in "가나다":
            k = f"{base}_{g}"
            if k in jeonhyeong_used:
                jlist.append({"key": k, "시기": "정시", "유형": y, "전형명": n, "군": g})

    def colsum(k):
        return sum(u["인원"].get(k, 0) for u in units)

    memo = [
        "이 PDF는 텍스트층이 없음(글자가 벡터 도형). 숫자는 글자 윤곽 서명으로 판독, 모집단위·대학 이름은 "
        "도형 모양 해시 → 이름 대응표(쪽 렌더링 이미지를 눈으로 읽어 작성)로 판독. OCR 미사용",
        "정원내만 수록: 정시 기회균형전형(정원 외: 농어촌학생, 특성화고교졸업자, 기초생활수급자·차상위계층·한부모가족, "
        "장애인등 대상자)과 재외국민·외국인 특별전형은 넣지 않음. 표 자체가 '정원 내 기준'",
        "수시 학생부종합 고른기회전형·사회기여자전형은 정원내(p3 수시 소계(정원 내)에 포함) → 수록",
        "표에 행별 합계 칸 없음 → 계=null(합계칸없음)",
        "계열: 표에 계열 표시 없음 → null",
        "정시 '예체능실기' 열은 p3·p16~17에 따라 두 전형으로 나눔: 음악대학 → 실기/실적(예체능실기전형), "
        "조형예술학부·체육과학부 → 수능(예체능실기전형), 디자인학부는 칸 안 표기대로 '(수능위주)' 36 → 수능, '(실기위주)' 20 → 실기/실적",
    ] + memo_extra

    # 총계 대조
    if total_row:
        tot = []
        for parts in total_row:
            tot.append(to_int(parts[0]["num"], "계 행") if len(parts) == 1 else None)
        bad = []
        for i, (k, _, _) in enumerate(SUSI_COLS):
            if tot[i] != colsum(k):
                bad.append(f"{k}({tot[i]} vs {colsum(k)})")
        for i, (kind, g) in enumerate(JEONGSI_COLS, start=8):
            if kind == "예체능실기":
                mine = colsum(f"정시_수능예체능실기_{g}") + colsum(f"정시_실기예체능실기_{g}")
            else:
                mine = colsum(f"{JEONGSI_DEF[kind][0]}_{g}")
            if tot[i] != mine:
                bad.append(f"{kind}{g}({tot[i]} vs {mine})")
        memo.append("표 '계' 행 열별 대조: " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)))
    if overview:
        s_me = sum(colsum(k) for k, _, _ in SUSI_COLS)
        jkeys = [j["key"] for j in jlist if j["시기"] == "정시"]
        j_me = sum(colsum(k) for k in jkeys)
        ov = overview
        memo.append(f"총계 대조: 수시 {ov['수시계']}={s_me}, 정시 {ov['정시계']}={j_me}, 전체 {ov['총계']}={s_me + j_me} (p3 개요표, 정원 내)")
        det = []
        for i, (k, _, _) in enumerate(SUSI_COLS):
            if ov["수시"][i] != colsum(k):
                det.append(f"{k}({ov['수시'][i]} vs {colsum(k)})")
        mine_j = [sum(colsum(f"정시_수능_{g}") for g in "가나다"),
                  sum(colsum(f"정시_수능학생부_{g}") for g in "가나다"),
                  sum(colsum(f"정시_수능예체능실기_{g}") for g in "가나다"),
                  sum(colsum(f"정시_실기예체능실기_{g}") for g in "가나다")]
        for lbl, a, b in zip(("수능(수능전형)", "수능(수능-학생부전형)", "수능(예체능실기전형)", "실기/실적(예체능실기전형)"),
                             ov["정시"], mine_j):
            if a != b:
                det.append(f"{lbl}({a} vs {b})")
        memo.append("p3 전형별 대조: " + ("모두 일치" if not det else "불일치 " + ", ".join(det)))

    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": list(PAGES), "전형": jlist, "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(units)}행 → {out_path}")


def build_units(page_rows, pno, memo):
    """행별 값 → 모집단위 목록. 여러 행에 걸친 병합 칸(값 있음)은 별도 행으로 뽑는다."""
    units = []
    shared = {}  # (cell) -> dict(rows=[...], col, num)
    for r in page_rows:
        r["inwon"] = {}
        for ci, parts in enumerate(r["vals"]):
            for p in parts:
                v = to_int(p["num"], f"p{pno} {r['name']} {ci}열")
                if not v:
                    continue
                key = col_key(ci, r, p)
                if p["own"]:
                    if key in r["inwon"]:
                        raise SystemExit(f"p{pno} {r['name']}: {key} 중복")
                    r["inwon"][key] = v
                else:
                    s = shared.setdefault(p["cell"], {"rows": [], "key": key, "num": v})
                    s["rows"].append(r)
    emitted = set()
    for r in page_rows:
        for cell, s in shared.items():
            if s["rows"][0] is r and cell not in emitted:
                emitted.add(cell)
                grp = s["rows"]
                gnames = {g["group"] for g in grp}
                gcells = {g["gcell"] for g in grp}
                if len(gnames) == 1 and None not in gnames and len(gcells) == 1 and \
                        near(next(iter(gcells))[1], cell[1]) and near(next(iter(gcells))[3], cell[3]):
                    name = next(iter(gnames))
                elif pno == 5 and len(grp) == len(page_rows):
                    # 표 안에는 이름 없이 5쪽 전 행(인문과학대학~인공지능대학)에 걸친 병합 칸.
                    # p4 '정시모집 모집군' 표의 2028 나군 '통합선발' 표기를 이름으로 씀.
                    name = "통합선발"
                    memo.append("'통합선발' 이름은 p4 정시모집 모집군 표(2028 나군 '통합선발')에서 가져옴")
                else:
                    raise SystemExit(f"p{pno}: 병합 칸 {s['key']}={s['num']} 묶음 이름 못 정함")
                key_name = (name, tuple(sorted({g['college'] for g in grp})))
                u = next((x for x in units if x.get("_k") == key_name), None)
                if u is None:
                    colleges = {g["college"] for g in grp}
                    u = {"_k": key_name, "단과대학": colleges.pop() if len(colleges) == 1 else None,
                         "모집단위": name, "계열": None, "인원": {}, "계": None, "쪽": pno}
                    units.append(u)
                u["인원"][s["key"]] = s["num"]
                memo.append(f"p{pno} 병합 칸 {s['key']}={s['num']}: {grp[0]['name']}~{grp[-1]['name']} "
                            f"{len(grp)}행 공통 → '{name}' 별도 행으로 기재(개별 행에 배분 안 함)")
        units.append({"단과대학": r["college"], "모집단위": r["name"], "계열": None, "인원": r["inwon"],
                      "계": None, "쪽": pno})
    for u in units:
        u.pop("_k", None)
    return units


def col_key(ci, r, p):
    if ci < 8:
        return SUSI_COLS[ci][0]
    kind, g = JEONGSI_COLS[ci - 8]
    if kind == "예체능실기":
        if p["ann"] is not None:
            ann = NAME_BY_HASH.get(p["ann"])
            if ann not in ANNOT_TO_KIND:
                raise SystemExit(f"{r['name']}: 모르는 칸 주석 {p['ann']}")
            kind = ANNOT_TO_KIND[ann]
        else:
            if r["college"] not in YECHE_BY_COLLEGE:
                raise SystemExit(f"{r['name']}({r['college']}): 예체능실기 전형 구분 못함")
            kind = YECHE_BY_COLLEGE[r["college"]]
    return f"{JEONGSI_DEF[kind][0]}_{g}"


def read_overview(page):
    """p3 개요표 모집인원 칸(위→아래) → 수시 8, 수시계, 정시 4, 정시계, 정원외 5, 총계, 정원내외총계."""
    ts = [t for t in page.find_tables(TS) if t.bbox[2] - t.bbox[0] > 300]
    if len(ts) != 1:
        return None
    cells = sorted({tuple(c) for c in ts[0].cells}, key=lambda c: (c[1], c[0]))
    xs = sorted({round(c[0], 1) for c in cells})
    vals = None
    for x in xs:
        col = [c for c in cells if near(c[0], x)]
        seq = []
        try:
            for c in col:
                ln = text_lines(ink(page, c))
                if ln:
                    seq.append(decode_line(ln[0]["o"], ""))
        except SystemExit:
            continue
        if len(seq) == 21:
            vals = seq
            break
    if vals is None:
        return None
    nums = [int(v.replace(",", "").replace("P", "")) for v in vals]
    ov = {"수시": nums[0:8], "수시계": nums[8], "정시": nums[9:13], "정시계": nums[13], "총계": nums[19]}
    if sum(ov["수시"]) != ov["수시계"] or sum(ov["정시"]) != ov["정시계"] or ov["수시계"] + ov["정시계"] != ov["총계"]:
        raise SystemExit(f"p3 개요표 내부 합 불일치: {nums}")
    if not all(v.startswith("P") for v in vals[14:19]):
        raise SystemExit("p3 개요표 정원외 칸 위치 다름")
    return ov


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--dump"]
    if len(args) != 2:
        raise SystemExit("usage: ewha.py <pdf> <out.json> [--dump]")
    main(args[0], args[1], dump="--dump" in sys.argv)
