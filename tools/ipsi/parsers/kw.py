#!/usr/bin/env python3
"""광운대학교 2028 시행계획 파서.

대상 표: "Ⅲ. 전형별 모집인원 / 1. 정원 내 모집인원" (PDF 6쪽).
이 표는 pdfplumber find_tables()로 잡히지 않는다(머리글 선 일부가 흰색). 그래서
  - 열 경계: 데이터 영역을 위아래로 가로지르는 세로선 x 위치(+ 표 좌우 끝)
  - 칸 경계: 열마다 그 열 가운데 x를 지나는 가로선 y 위치(세로 병합 칸은 선이 없음)
  - 글자: 중심 좌표가 들어가는 칸에 넣음
으로 읽는다.
사용법: python3 -I tools/ipsi/parsers/kw.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "kw"
UNIV_NAME = "광운대학교"
PAGE_TITLE = "정원 내 모집인원"

# 열 번호(왼쪽부터 0) → 전형 key. 머리글 글자로 위치를 확인한다.
COL_COLLEGE, COL_GYEYEOL, COL_NAME = 0, 1, 2
COLS = {
    3: "수시_종합_참빛인재1면접형",
    4: "수시_종합_참빛인재2서류형",
    5: "수시_종합_소프트웨어우수인재",
    6: "수시_종합_특성화고재직자",
    7: "수시_교과_지역균형",
    8: "수시_논술_논술우수자",
    9: "수시_실기_체육특기자",
    11: "정시_수능_일반학생_가",
    12: "정시_수능_일반학생_나",
    13: "정시_수능_일반학생_다",
    14: "정시_수능_스포츠융합과학과_다",
    15: "정시_수능_기회균형_가",
    16: "정시_수능_기회균형_나",
    17: "정시_수능_기회균형_다",
}
COL_SUSI_SUM, COL_JEONGSI_SUM, COL_TOTAL = 10, 18, 19
NCOLS = 20
# 열별 머리글(공백 제거)에 들어 있어야 하는 글자
EXPECT_HDR = {
    0: "대학", 1: "계열", 2: "모집단위", 3: "면접형", 4: "서류형", 5: "소프트웨어우수인재",
    6: "재직자", 7: "지역균형", 8: "논술", 9: "체육", 10: "소계", 14: "스포츠융합과학과",
    18: "소계", 19: "총계",
}
EXPECT_GUN = {11: "가", 12: "나", 13: "다", 14: "다", 15: "가", 16: "나", 17: "다"}
# 여러 열에 걸친 머리글: (글자, 첫 열, 끝 열)
EXPECT_SPAN = [("수시모집", 3, 10), ("정시모집", 11, 18), ("일반학생전형", 11, 14), ("기회균형", 15, 17)]

JEONHYEONG = [
    {"key": "수시_종합_참빛인재1면접형", "시기": "수시", "유형": "학생부종합", "전형명": "광운참빛인재전형Ⅰ-면접형", "군": None},
    {"key": "수시_종합_참빛인재2서류형", "시기": "수시", "유형": "학생부종합", "전형명": "광운참빛인재전형Ⅱ-서류형", "군": None},
    {"key": "수시_종합_소프트웨어우수인재", "시기": "수시", "유형": "학생부종합", "전형명": "소프트웨어우수인재전형", "군": None},
    {"key": "수시_종합_특성화고재직자", "시기": "수시", "유형": "학생부종합",
     "전형명": "특성화고등을졸업한재직자전형(정원내)", "군": None},
    {"key": "수시_교과_지역균형", "시기": "수시", "유형": "학생부교과", "전형명": "지역균형전형", "군": None},
    {"key": "수시_논술_논술우수자", "시기": "수시", "유형": "논술", "전형명": "논술우수자전형", "군": None},
    {"key": "수시_실기_체육특기자", "시기": "수시", "유형": "실기/실적", "전형명": "체육특기자전형", "군": None},
    {"key": "정시_수능_일반학생_가", "시기": "정시", "유형": "수능", "전형명": "일반학생전형", "군": "가"},
    {"key": "정시_수능_일반학생_나", "시기": "정시", "유형": "수능", "전형명": "일반학생전형", "군": "나"},
    {"key": "정시_수능_일반학생_다", "시기": "정시", "유형": "수능", "전형명": "일반학생전형", "군": "다"},
    {"key": "정시_수능_스포츠융합과학과_다", "시기": "정시", "유형": "수능",
     "전형명": "일반학생전형-스포츠융합과학과", "군": "다"},
    {"key": "정시_수능_기회균형_가", "시기": "정시", "유형": "수능", "전형명": "기회균형전형", "군": "가"},
    {"key": "정시_수능_기회균형_나", "시기": "정시", "유형": "수능", "전형명": "기회균형전형", "군": "나"},
    {"key": "정시_수능_기회균형_다", "시기": "정시", "유형": "수능", "전형명": "기회균형전형", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]


def norm(s):
    return re.sub(r"\s+", "", s or "")


def to_int(s):
    s = norm(s).replace(",", "")
    if s in ("", "-"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {s!r}")


def dedup(vals, tol=0.8):
    out = []
    for v in sorted(vals):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def text_in(chars, x0, x1, top, bot, line_sep=""):
    """중심점이 사각형 안에 드는 글자를 줄 단위로 이어 붙인다. 줄 안에서 글자 간격이 넓으면 공백."""
    cs = [c for c in chars
          if x0 <= (c["x0"] + c["x1"]) / 2 <= x1 and top <= (c["top"] + c["bottom"]) / 2 <= bot]
    lines = []
    for c in sorted(cs, key=lambda c: (c["top"], c["x0"])):
        if lines and abs(lines[-1][0] - c["top"]) <= 2:
            lines[-1][1].append(c)
        else:
            lines.append([c["top"], [c]])
    out = []
    for _, lc in lines:
        lc.sort(key=lambda c: c["x0"])
        s = ""
        for i, c in enumerate(lc):
            if i and c["x0"] - lc[i - 1]["x1"] > 1.0:
                s += " "
            s += c["text"]
        out.append(re.sub(r"\s+", " ", s).strip())
    return line_sep.join(o for o in out if o)


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        pno = None
        for i, page in enumerate(pdf.pages, start=1):
            t = page.extract_text() or ""
            if PAGE_TITLE in t and "전형별 모집인원" in t and "총계" in t:
                pno = i
                break
        if pno is None:
            raise SystemExit("정원 내 모집인원 표 쪽을 찾지 못함")
        page = pdf.pages[pno - 1]
        chars = page.chars
        edges = page.edges

        # 표 아래 끝(총계 행 아래 굵은 선)과 데이터 시작선
        hs = [e for e in edges if e["orientation"] == "h" and e["x1"] - e["x0"] > 400]
        bottom_line = max(hs, key=lambda e: e["top"])
        tx0, tx1, tbot = bottom_line["x0"], bottom_line["x1"], bottom_line["top"]
        # 세로선: 데이터 영역(머리글 아래 ~ 표 끝)을 거의 다 덮는 것
        long_v = [e for e in edges if e["orientation"] == "v" and e["bottom"] >= tbot - 30
                  and e["bottom"] - e["top"] > 300]
        data_top = min(e["top"] for e in long_v)
        vx = dedup([e["x0"] for e in long_v if tx0 + 3 < e["x0"] < tx1 - 3])
        xs = [tx0] + vx + [tx1]
        if len(xs) != NCOLS + 1:
            raise SystemExit(f"열 수 {len(xs) - 1} != {NCOLS}")
        cols = list(zip(xs, xs[1:]))
        head_top = min(e["top"] for e in edges if e["orientation"] == "v" and tx0 + 3 < e["x0"] < tx1 - 3)

        # 머리글 확인
        for ci, exp in EXPECT_HDR.items():
            h = norm(text_in(chars, *cols[ci], head_top, data_top))
            if exp not in h:
                raise SystemExit(f"머리글 불일치 col{ci}: {h!r}에 {exp!r} 없음")
        gun_row = [w for w in page.extract_words() if head_top < w["top"] < data_top and w["text"] in "가나다"]
        for ci, exp in EXPECT_GUN.items():
            got = [w["text"] for w in gun_row if cols[ci][0] <= (w["x0"] + w["x1"]) / 2 <= cols[ci][1]]
            if got != [exp]:
                raise SystemExit(f"모집군 머리글 불일치 col{ci}: {got}")
        words = page.extract_words()
        for txt, a, b in EXPECT_SPAN:
            ws = [w for w in words if head_top < w["top"] < data_top and w["text"].startswith(txt)]
            if not ws or not all(cols[a][0] <= (w["x0"] + w["x1"]) / 2 <= cols[b][1] for w in ws):
                raise SystemExit(f"묶음 머리글 {txt} 위치 다름")

        def hlines_at(ci):
            xm = (cols[ci][0] + cols[ci][1]) / 2
            ys = [e["top"] for e in edges if e["orientation"] == "h" and e["x0"] - 0.5 <= xm <= e["x1"] + 0.5
                  and data_top - 1 <= e["top"] <= tbot + 1]
            return dedup(ys)

        def band_of(ci, y):
            ys = hlines_at(ci)
            for a, b in zip(ys, ys[1:]):
                if a <= y <= b:
                    return a, b
            raise SystemExit(f"col{ci} y={y:.0f} 칸 없음")

        row_lines = hlines_at(COL_NAME)
        bands = list(zip(row_lines, row_lines[1:]))

        units, skipped, merged_total = [], [], []
        pdf_total = None
        aux_bad = []
        aux_ok = 0
        for top, bot in bands:
            ym = (top + bot) / 2
            name = text_in(chars, *cols[COL_NAME], top, bot, line_sep=" ")
            vals = {}
            for ci in range(3, NCOLS):
                b = band_of(ci, ym)
                vals[ci] = (text_in(chars, *cols[ci], *b), b)
            if norm(name) == "총계":
                pdf_total = {ci: to_int(v[0]) for ci, v in vals.items()}
                continue
            if not name:
                raise SystemExit(f"이름 없는 행 y={top:.0f}")
            # 전형 칸이 여러 행에 걸쳐 병합돼 있으면 멈춤(이 표에는 없어야 함)
            for ci in list(COLS) + [COL_SUSI_SUM, COL_JEONGSI_SUM]:
                b = vals[ci][1]
                if b[0] < top - 1 or b[1] > bot + 1:
                    raise SystemExit(f"{name}: col{ci} 병합 칸")
            college = text_in(chars, *cols[COL_COLLEGE], *band_of(COL_COLLEGE, ym))
            gyeyeol = text_in(chars, *cols[COL_GYEYEOL], *band_of(COL_GYEYEOL, ym)) or None
            inwon = {}
            for ci, key in COLS.items():
                v = to_int(vals[ci][0])
                if v:
                    inwon[key] = v
            # 보조 대조: 수시 소계·정시 소계 칸
            s = sum(inwon.get(k, 0) for k in SUSI_KEYS)
            j = sum(inwon.get(k, 0) for k in JEONGSI_KEYS)
            if s == to_int(vals[COL_SUSI_SUM][0]) and j == to_int(vals[COL_JEONGSI_SUM][0]):
                aux_ok += 1
            else:
                aux_bad.append(f"{name}(수시소계 {vals[COL_SUSI_SUM][0]} vs {s}, 정시소계 {vals[COL_JEONGSI_SUM][0]} vs {j})")
            tb = vals[COL_TOTAL][1]
            if tb[0] < top - 1 or tb[1] > bot + 1:
                gye = None
                merged_total.append((tb, name, sum(inwon.values()), vals[COL_TOTAL][0]))
            else:
                gye = to_int(vals[COL_TOTAL][0])
            if not inwon:
                skipped.append(f"{name}(정원내 모든 칸 0, 총계 {vals[COL_TOTAL][0]})")
                continue
            units.append({
                "단과대학": college or None,
                "모집단위": name,
                "계열": gyeyeol,
                "인원": inwon,
                "계": gye,
                "쪽": pno,
                "검증": "합계칸없음" if gye is None else (
                    "합계일치" if sum(inwon.values()) == gye else "합계불일치"),
            })

    used = {k for u in units for k in u["인원"]}
    jlist = [j for j in JEONHYEONG if j["key"] in used]
    unused = [f"{j['전형명']}({j['군']}군)" if j["군"] else j["전형명"] for j in JEONHYEONG if j["key"] not in used]

    memo = [
        "정원내만 수록: p6 '1. 정원 내 모집인원' 표만 읽음. p7 '2. 정원 외 모집인원'(농어촌학생·특성화고졸업자·특성화고등을졸업한재직자(정원외)·"
        "서해5도출신자·재외국민, 정시 이월인원)은 넣지 않음",
        "학생부종합 특성화고등을졸업한재직자전형은 정원내 열(금융부동산법무학과 1, 게임콘텐츠학과 1)만 수록",
        "정시 기회균형전형은 p6 정원 내 표·p8 '정원 내' 열에 있는 정원내 전형 → 수록. "
        "일반학생전형-스포츠융합과학과(수능40+학생부30+실기30)는 PDF가 정시 '수능' 아래 둔 전형이라 유형=수능",
        "계 = 표의 '총계' 칸(행별 정원내 수시+정시 합계)",
        "계열: 표의 계열 칸 그대로(세로 병합 칸은 걸친 행 모두에 같은 값). 자율전공학부 두 행은 칸 글자 그대로 '자연/인문'",
        "단과대학: 표의 대학 칸 글자를 이어 씀",
    ]
    if unused:
        memo.append("PDF 표에 열은 있으나 인원이 0인 전형(전형 목록에서 뺌): " + ", ".join(unused))
    if skipped:
        memo.append("제외 행(정원내 인원 없음, p5 각주 '정원 외 전담학과'): " + "; ".join(skipped))
    groups = {}
    for tb, name, s, v in merged_total:
        groups.setdefault((round(tb[0]), round(tb[1]), v), []).append((name, s))
    for (_, _, v), lst in groups.items():
        tot = sum(s for _, s in lst)
        memo.append(f"총계 칸 세로 병합({v}): {', '.join(n for n, _ in lst)} → 각 행 계=null(합계칸없음). "
                    f"두 행 정원내 합 {tot} {'=' if str(tot) == norm(v).replace(',', '') else '≠'} 병합 칸 {v}")
    memo.append(f"보조 대조(행별 수시 소계·정시 소계 칸 = 전형 칸 합): {aux_ok}행 일치"
                + (", 불일치 " + "; ".join(aux_bad) if aux_bad else ""))
    if pdf_total is None:
        raise SystemExit("총계 행 없음")
    s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
    j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
    memo.append(f"총계 대조: 수시 {pdf_total[COL_SUSI_SUM]}={s_me}, 정시 {pdf_total[COL_JEONGSI_SUM]}={j_me}, "
                f"전체 {pdf_total[COL_TOTAL]}={s_me + j_me} (p6 표 '총계' 행)")
    bad = [f"{COLS[ci]}({pdf_total[ci]} vs {sum(u['인원'].get(COLS[ci], 0) for u in units)})"
           for ci in COLS if pdf_total[ci] != sum(u["인원"].get(COLS[ci], 0) for u in units)]
    memo.append("전형별 열 합 대조(총계 행): " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)))

    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": [pno], "전형": jlist, "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(units)}행 → {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: kw.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
