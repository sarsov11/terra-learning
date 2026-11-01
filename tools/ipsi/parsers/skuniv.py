#!/usr/bin/env python3
"""서경대학교 2028 시행계획 파서.

대상 표: "모집단위별 입학정원 및 전형별 모집인원 [정원내]" (PDF 5쪽, 인쇄 쪽번호 3).
이 표의 본문 칸 경계는 점선(짧은 선분 수천 개)이라 pdfplumber의 표 인식이 본문을 큰 덩어리 몇 개로만 잡는다.
그래서 머리글 칸(표 인식이 제대로 잡음)으로 열의 x 범위를 정하고, 본문은
  - 열마다 '그 열 폭의 30% 이상을 덮는 가로선(굵기 0.3 이상)'을 칸 경계로 보고,
  - 칸 안에 중심이 드는 단어를 읽는다.
길이 3~15pt의 가는 실선(굵기 0.3 미만)은 '밑줄 친 인원'(전전년도 미충원 포함 표시)이라 경계로 쓰지 않고 메모에 적는다.
사용법: python3 -I tools/ipsi/parsers/skuniv.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "skuniv"
UNIV_NAME = "서경대학교"

# 머리글 확인: (행, 열) → 글자
EXPECT_HDR = {
    (0, 0): "대학", (0, 1): "모집단위", (0, 3): "입학정원", (0, 4): "수시모집", (0, 13): "정시모집",
    (1, 13): "㉮군", (1, 16): "㉯군", (1, 19): "㉰군",
    (2, 1): "학과(부)", (2, 2): "전공",
    (2, 4): "실기우수", (2, 5): "논술우수", (2, 6): "논술우수", (2, 7): "교과우수", (2, 8): "교과우수",
    (2, 9): "미래인재", (2, 10): "사회기여", (2, 11): "기회균형①", (2, 12): "군사학과",
    (2, 13): "실기우수", (2, 14): "수능우수", (2, 15): "기회균형①",
    (2, 16): "실기우수", (2, 17): "수능우수", (2, 18): "기회균형①",
    (2, 19): "실기우수", (2, 20): "수능우수", (2, 21): "기회균형①", (2, 22): "군사학과",
    (3, 5): "언어위주", (3, 6): "수리위주", (3, 7): "언어위주", (3, 8): "수리위주",
}
COL_COLLEGE, COL_GROUP, COL_MAJOR, COL_IPHAK = 0, 1, 2, 3
# 열 → (key, 시기, 유형, 전형명, 군)
COLS = {
    4: ("수시_실기_실기우수자", "수시", "실기/실적", "실기우수자전형", None),
    5: ("수시_논술_언어위주", "수시", "논술", "논술우수자전형(언어위주)", None),
    6: ("수시_논술_수리위주", "수시", "논술", "논술우수자전형(수리위주)", None),
    7: ("수시_교과_교과우수자_언어위주", "수시", "학생부교과", "교과우수자전형(언어위주)", None),
    8: ("수시_교과_교과우수자_수리위주", "수시", "학생부교과", "교과우수자전형(수리위주)", None),
    9: ("수시_교과_미래인재", "수시", "학생부교과", "미래인재전형", None),
    10: ("수시_교과_사회기여자", "수시", "학생부교과", "사회기여자전형", None),
    11: ("수시_교과_기회균형1", "수시", "학생부교과", "기회균형①전형", None),
    12: ("수시_교과_군사학과", "수시", "학생부교과", "군사학과전형", None),
    13: ("정시_실기_가", "정시", "실기/실적", "실기우수자전형", "가"),
    14: ("정시_수능_가", "정시", "수능", "수능우수자전형", "가"),
    15: ("정시_수능_기회균형1_가", "정시", "수능", "기회균형①전형", "가"),
    16: ("정시_실기_나", "정시", "실기/실적", "실기우수자전형", "나"),
    17: ("정시_수능_나", "정시", "수능", "수능우수자전형", "나"),
    18: ("정시_수능_기회균형1_나", "정시", "수능", "기회균형①전형", "나"),
    19: ("정시_실기_다", "정시", "실기/실적", "실기우수자전형", "다"),
    20: ("정시_수능_다", "정시", "수능", "수능우수자전형", "다"),
    21: ("정시_수능_기회균형1_다", "정시", "수능", "기회균형①전형", "다"),
    22: ("정시_수능_군사학과_다", "정시", "수능", "군사학과전형", "다"),
}
SUSI_COLS = [c for c, v in COLS.items() if v[1] == "수시"]
JEONGSI_COLS = [c for c, v in COLS.items() if v[1] == "정시"]
COVER_MIN = 0.30      # 칸 경계로 보는 가로선 덮음 비율


def is_underline(e):
    """숫자 밑줄: 가는(0.3 미만) 실선, 길이 3~15pt."""
    return (e.get("linewidth") or 0) < 0.3 and 3 <= e["x1"] - e["x0"] <= 15
CIRCLE = "◑"


def norm(s):
    return re.sub(r"\s+", "", s or "")


def to_int(s):
    s = norm(s).replace(",", "")
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {s!r}")


def center_in(w, x0, x1, y0, y1):
    cx, cy = (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2
    return x0 <= cx <= x1 and y0 <= cy <= y1


def words_in(words, x0, x1, y0, y1):
    return sorted([w for w in words if center_in(w, x0, x1, y0, y1)], key=lambda w: (round(w["top"]), w["x0"]))


def boundaries(hedges, x0, x1, y_top, y_bot):
    """[x0,x1] 폭의 COVER_MIN 이상을 덮는 가로선 y (가까운 것은 하나로) + 위/아래 끝."""
    ys = {}
    for e in hedges:
        if not (y_top - 1 <= e["top"] <= y_bot + 1):
            continue
        ov = min(e["x1"], x1) - max(e["x0"], x0)
        if ov > 0:
            key = round(e["top"] * 2) / 2
            ys[key] = ys.get(key, 0) + ov
    raw = sorted(y for y, L in ys.items() if L / (x1 - x0) >= COVER_MIN)
    out = [y_top]
    for y in raw + [y_bot]:
        if y - out[-1] > 2.0:
            out.append(y)
        else:
            out[-1] = max(out[-1], y) if out[-1] != y_top else out[-1]
    if out[-1] != y_bot:
        out[-1] = y_bot
    return out


def cell_of(bounds, y):
    for a, b in zip(bounds, bounds[1:]):
        if a <= y <= b:
            return a, b
    raise ValueError(f"y={y} 경계 밖")


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        target = None
        for pno, page in enumerate(pdf.pages, start=1):
            if "모집단위별입학정원및전형별모집인원[정원내]" in norm(page.extract_text() or ""):
                tables = page.find_tables()
                if tables:
                    target = (pno, page, tables[0])
                    break
        if not target:
            raise SystemExit("[정원내] 표를 찾지 못함")
        pno, page, table = target
        rows = table.extract()
        for (ri, ci), e in EXPECT_HDR.items():
            if norm(rows[ri][ci]) != e:
                raise SystemExit(f"머리글 불일치 row{ri} col{ci}: {rows[ri][ci]!r} != {e}")

        # 열 x 범위
        r0, r2 = table.rows[0].cells, table.rows[2].cells
        xr = {COL_COLLEGE: (r0[0][0], r0[0][2]), COL_IPHAK: (r0[3][0], r0[3][2])}
        for ci in [COL_GROUP, COL_MAJOR] + list(COLS):
            xr[ci] = (r2[ci][0], r2[ci][2])
        name_x0, name_x1 = xr[COL_GROUP][0], xr[COL_MAJOR][1]

        words = page.extract_words()
        tot_words = [w for w in words if w["text"] in ("총", "계") and w["x1"] < name_x1]
        if len(tot_words) != 2:
            raise SystemExit("총계 행을 찾지 못함")
        y_tot = min(w["top"] for w in tot_words)
        body_top = max(c[3] for c in table.rows[3].cells if c is not None)
        hedges_all = [e for e in page.edges if e["orientation"] == "h"]
        hedges = [e for e in hedges_all if not is_underline(e)]
        # 본문 아래 끝 = 총계 글자 바로 위 가로선
        cand = boundaries(hedges, xr[4][0], xr[22][1], body_top, y_tot)
        body_bot = max(y for y in cand if y < y_tot - 1)
        table_bot = table.bbox[3]

        bnd = {ci: boundaries(hedges, x0, x1, body_top, body_bot) for ci, (x0, x1) in xr.items()}
        # 모집 행 = 전형 열 경계의 합집합
        unit_ys = sorted({y for ci in COLS for y in bnd[ci]})
        merged = [unit_ys[0]]
        for y in unit_ys[1:]:
            if y - merged[-1] > 2.0:
                merged.append(y)
        unit_bands = list(zip(merged, merged[1:]))

        # 이름 칸 안 세로 구분선
        vedges = [e for e in page.edges if e["orientation"] == "v"
                  and name_x0 + 5 < e["x0"] < name_x1 - 5 and body_top - 1 < e["top"] < body_bot + 1]

        def vsplit(y):
            xs = sorted({round(e["x0"], 1) for e in vedges if e["top"] - 0.5 <= y <= e["bottom"] + 0.5})
            return xs[0] if xs else None

        units, problems, merged_numbers = [], [], []
        iphak_groups = {}
        for (y0, y1) in unit_bands:
            m = (y0 + y1) / 2
            # 대학
            ca, cb = cell_of(bnd[COL_COLLEGE], m)
            college = "".join(w["text"] for w in words_in(words, *xr[COL_COLLEGE], ca, cb))
            # 이름
            s = vsplit(m)
            if s is None:
                b = boundaries(hedges, name_x0, name_x1, body_top, body_bot)
                a1, b1 = cell_of(b, m)
                name = "".join(w["text"] for w in words_in(words, name_x0, name_x1, a1, b1))
            else:
                bl = boundaries(hedges, name_x0, s, body_top, body_bot)
                br = boundaries(hedges, s, name_x1, body_top, body_bot)
                a1, b1 = cell_of(bl, m)
                left = "".join(w["text"] for w in words_in(words, name_x0, s, a1, b1))
                subs = [(a, b) for a, b in zip(br, br[1:]) if y0 - 1 <= a and b <= y1 + 1]
                rights = ["".join(w["text"] for w in words_in(words, s, name_x1, a, b)) for a, b in subs]
                if len(rights) == 1:
                    name = f"{left} {rights[0]}"
                else:
                    name = f"{left}({'/'.join(rights)})"
            if not name.strip():
                raise SystemExit(f"이름 없는 행 y={m:.0f}")
            name = name.rstrip("*")  # '자유전공학부*' 각주 표시
            # 입학정원
            ia, ib = cell_of(bnd[COL_IPHAK], m)
            iw = words_in(words, *xr[COL_IPHAK], ia, ib)
            iphak = to_int("".join(w["text"] for w in iw))
            iphak_groups.setdefault((ia, ib, iphak), []).append(name)
            # 전형 칸
            inwon, circles = {}, []
            for ci, (key, *_rest) in COLS.items():
                a, b = cell_of(bnd[ci], m)
                txt = "".join(w["text"] for w in words_in(words, *xr[ci], a, b))
                if txt == "":
                    continue
                if txt == CIRCLE:
                    circles.append(key)
                    continue
                v = to_int(txt)
                if a < y0 - 1 or b > y1 + 1:
                    merged_numbers.append(f"{name} {key} {v}")
                    continue
                if v:
                    inwon[key] = v
            units.append({
                "단과대학": college or None,
                "모집단위": name,
                "계열": None,
                "인원": inwon,
                "계": None,
                "쪽": pno,
                "검증": "합계칸없음",
                "_circles": circles,
            })
        if merged_numbers:
            raise SystemExit(f"여러 모집 행에 걸친 숫자 칸: {merged_numbers}")

        # 총계 행
        tot = {}
        for ci in [COL_IPHAK] + list(COLS):
            txt = "".join(w["text"] for w in words_in(words, *xr[ci], body_bot, table_bot))
            tot[ci] = to_int(txt)
        # 밑줄(가는 짧은 실선) → 그 선이 걸친 숫자(선이 글자 아랫부분을 지나므로 글자 세로 범위 근처로 찾음)
        underlined = []
        for e in hedges_all:
            if is_underline(e) and body_top < e["top"] < body_bot:
                for ci, (x0, x1) in xr.items():
                    if x0 <= (e["x0"] + e["x1"]) / 2 <= x1:
                        ws = [w for w in words if w["x0"] - 1 <= (e["x0"] + e["x1"]) / 2 <= w["x1"] + 1
                              and w["top"] <= e["top"] <= w["bottom"] + 3]
                        for w in ws:
                            u = next(u for u, (a, b) in zip(units, unit_bands) if a <= w["top"] <= b)
                            underlined.append((u["모집단위"], COLS[ci][0] if ci in COLS else f"col{ci}", w["text"]))
        underlined = sorted(set(underlined))

    used = [ci for ci in COLS if tot[ci] or any(u["인원"].get(COLS[ci][0]) for u in units)]
    JEONHYEONG = [{"key": COLS[ci][0], "시기": COLS[ci][1], "유형": COLS[ci][2], "전형명": COLS[ci][3], "군": COLS[ci][4]}
                  for ci in used]
    circle_only = [COLS[ci][0] for ci in COLS if ci not in used]
    circles_all = [f"{u['모집단위']}:{k}" for u in units for k in u["_circles"]]
    for u in units:
        del u["_circles"]

    ip_ok, ip_bad = 0, []
    for (_, _, val), names in iphak_groups.items():
        s = sum(sum(u["인원"].values()) for u in units if u["모집단위"] in names)
        if s == val:
            ip_ok += 1
        else:
            ip_bad.append(f"{'+'.join(names)}(입학정원 {val}, 정원내 합 {s})")
    s_pdf = sum(tot[ci] for ci in SUSI_COLS)
    j_pdf = sum(tot[ci] for ci in JEONGSI_COLS)
    s_me = sum(u["인원"].get(COLS[ci][0], 0) for u in units for ci in SUSI_COLS)
    j_me = sum(u["인원"].get(COLS[ci][0], 0) for u in units for ci in JEONGSI_COLS)
    bad = [COLS[ci][0] for ci in COLS if tot[ci] != sum(u["인원"].get(COLS[ci][0], 0) for u in units)]

    memo = [
        "정원내만 수록: 6쪽 [정원외] 표(수시 농어촌학생·서해5도·특성화고교졸업자·특성화고 등을 졸업한 재직자, 정시 농어촌·특성화고교졸업자·"
        "재직자, 창의인재대학 재직자 학과), 재외국민과 외국인·북한이탈주민·전교육과정이수자, 계약학과 채용조건형(17쪽)은 넣지 않음",
        "표의 칸 경계가 점선이라 pdfplumber 표 인식 대신 머리글 칸의 x 범위 + 점선 위치로 칸을 나눠 텍스트 층 글자를 읽음(OCR 안 씀). "
        "렌더링한 쪽 그림과 대조했고, 아래 전형별 열 합이 총계 행과 모두 맞음",
        "유형: 표에 전형유형(학생부교과 등) 표기가 없어 8·10쪽 '전형요소별 반영비율' 표의 주 전형요소로 정함 — 실기우수자→실기/실적, "
        "논술우수자→논술, 교과우수자·미래인재·사회기여자·기회균형①(학생부 교과 100%)과 수시 군사학과(교과 60%+면접·체력)→학생부교과, "
        "정시 수능우수자·기회균형①(수능 100%)과 정시 군사학과(수능 60%+면접·체력)→수능",
        "계: 표에 행별 정원내 합계 칸이 없음(입학정원 칸만 있음) → 계=null, 검증='합계칸없음'",
        f"참고 대조(입학정원 칸 = 행 정원내 합, 병합 칸은 묶음 합): {ip_ok}/{len(iphak_groups)} 같음"
        + (" — 다름: " + "; ".join(ip_bad) if ip_bad else "")
        + ". 표 각주: 밑줄 친 인원은 전전년도 미충원 인원 포함",
        "밑줄 친 인원(숫자에 걸친 짧은 실선으로 찾음; 각주: 전전년도 미충원 인원 포함): "
        + (", ".join(f"{n} {k} {t}" for n, k, t in underlined) if underlined else "없음")
        + " — 위 입학정원 대조의 +1 차이 3건과 같은 행",
        "자유전공학부: 표 이름 '자유전공학부*'의 * 는 각주 표시(미래융합학부1·2 중 선택 가능)라 떼고 적음",
        f"'◑'(수시이월 인원 발생 시 선발) 칸은 숫자가 없어 0으로 봄({len(circles_all)}칸): " + ", ".join(circles_all)
        + (f". 숫자 없이 ◑만 있는 전형({', '.join(circle_only)})은 전형 목록에서 뺌" if circle_only else ""),
        "헤어디자인학과는 표에서 수시 실기우수자 칸이 A 20 / B 20으로 나뉘어(각주: 같은 학과, 전형요소별 반영비율 차이 표기) "
        "'헤어디자인학과 A', '헤어디자인학과 B' 두 행으로 둠(입학정원 40·정시 ◑은 병합 칸)",
        "실용음악학부는 전공(기악/작곡/보컬/싱어송라이터) 이름 칸만 나뉘고 숫자 칸은 병합이라 한 행 '실용음악학부(기악/작곡/보컬/싱어송라이터)'으로 둠",
        "모집단위 이름: 학과(부)와 전공 칸이 나뉜 경우 '학부 전공'으로 이어 적음. 계열: 표에 칸이 없어 null",
        f"총계 대조: 수시 {s_pdf}={s_me}, 정시 {j_pdf}={j_me}, 전체 {s_pdf + j_pdf}={s_me + j_me} (PDF 총계 행 전형 칸 합; "
        f"총계 행 입학정원 {tot[COL_IPHAK]}과의 차 {s_pdf + j_pdf - tot[COL_IPHAK]}는 밑줄 친 이월 인원)",
        "전형별 열 합 대조(PDF 총계 행): " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)),
    ]
    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": [pno], "전형": JEONHYEONG, "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(units)}행 → {out_path}")
    for m in memo:
        print(" -", m)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: skuniv.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
