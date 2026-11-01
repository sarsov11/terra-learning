#!/usr/bin/env python3
"""서울시립대학교 2028 시행계획 파서.

대상 표: "3. 모집단위별 모집인원" (PDF 5쪽).
표의 모집단위 칸은 데이터 행에 왼쪽 세로선이 없어 셀로 잡히지 않으므로,
숫자 칸(입학정원 열) 셀의 세로 범위 안에 있는 단어로 모집단위 이름을 읽는다.
사용법: python3 -I tools/ipsi/parsers/uos.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "uos"
UNIV_NAME = "서울시립대학교"

# 표 열 번호(extract 결과 기준). 머리글 문구로 위치를 확인한다.
COL_IPHAK = 3
COLS = {
    "수시_논술": 4,
    "수시_교과_지역균형": 5,
    "수시_종합_학생부종합": 6,
    "수시_종합_기회균형1": 7,
    "수시_종합_사회공헌통합": 8,
    "수시_실기": 9,
    "정시_수능_가": 11,
    "정시_실기_가": 12,
    "정시_수능_나": 13,
    "정시_실기_나": 14,
}
COL_SUSI_SUM = 10
COL_JEONGSI_SUM = 19
COLS_OUT = [15, 16, 17]  # 정원외 기회균형Ⅱ: 농어촌, 특성화고교졸업자, 기초생활수급자 등 (장애인 등=18은 세로 병합)
EXPECT_HDR4 = {4: "논술전형", 5: "지역균형선발전형", 6: "학생부종합전형", 7: "기회균형전형Ⅰ",
               8: "사회공헌통합전형", 9: "실기전형", 11: "일반전형", 12: "일반전형", 13: "일반전형",
               14: "일반전형", 15: "농어촌학생", 16: "특성화고교졸업자", 17: "기초생활수급자등", 18: "장애인등"}
EXPECT_HDR2 = {11: "가군", 12: "가군", 13: "나군", 14: "나군"}
EXPECT_HDR3 = {11: "수능위주", 12: "실기/실적위주", 13: "수능위주", 14: "실기/실적위주"}

JEONHYEONG = [
    {"key": "수시_논술", "시기": "수시", "유형": "논술", "전형명": "논술전형", "군": None},
    {"key": "수시_교과_지역균형", "시기": "수시", "유형": "학생부교과", "전형명": "지역균형선발전형", "군": None},
    {"key": "수시_종합_학생부종합", "시기": "수시", "유형": "학생부종합", "전형명": "학생부종합전형", "군": None},
    {"key": "수시_종합_기회균형1", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형전형Ⅰ", "군": None},
    {"key": "수시_종합_사회공헌통합", "시기": "수시", "유형": "학생부종합", "전형명": "사회공헌통합전형", "군": None},
    {"key": "수시_실기", "시기": "수시", "유형": "실기/실적", "전형명": "실기전형", "군": None},
    {"key": "정시_수능_가", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "가"},
    {"key": "정시_실기_가", "시기": "정시", "유형": "실기/실적", "전형명": "일반전형", "군": "가"},
    {"key": "정시_수능_나", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "나"},
    {"key": "정시_실기_나", "시기": "정시", "유형": "실기/실적", "전형명": "일반전형", "군": "나"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]
GYEYEOL = {"인문", "자연", "예체능"}


def norm(s):
    return re.sub(r"\s+", "", s or "")


def to_int(cell):
    s = (cell or "").strip().replace(",", "")
    if s in ("", "-"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {cell!r}")


def words_in(words, x0, x1, top, bottom):
    """중심점이 사각형 안에 드는 단어들을 위→아래, 왼→오 순으로."""
    sel = [w for w in words
           if x0 <= (w["x0"] + w["x1"]) / 2 <= x1 and top <= (w["top"] + w["bottom"]) / 2 <= bottom]
    return sorted(sel, key=lambda w: (round(w["top"]), w["x0"]))


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        target = None
        for pno, page in enumerate(pdf.pages, start=1):
            txt = page.extract_text() or ""
            if "모집단위별 모집인원" in txt:
                for t in page.find_tables():
                    rows = t.extract()
                    if rows and norm(rows[0][0]) == "모집단위":
                        target = (pno, page, t, rows)
                        break
            if target:
                break
        if not target:
            raise SystemExit("모집단위별 모집인원 표를 찾지 못함")
        pno, page, table, rows = target

        # 머리글 확인
        for i, exp in EXPECT_HDR4.items():
            if norm(rows[4][i]) != exp:
                raise SystemExit(f"머리글 불일치 col{i}: {rows[4][i]!r} != {exp}")
        for i, exp in EXPECT_HDR2.items():
            if norm(rows[2][i]) != exp:
                raise SystemExit(f"모집군 머리글 불일치 col{i}: {rows[2][i]!r}")
        for i, exp in EXPECT_HDR3.items():
            if norm(rows[3][i]) != exp:
                raise SystemExit(f"유형 머리글 불일치 col{i}: {rows[3][i]!r}")
        if norm(rows[0][COL_IPHAK]) != "입학정원" or "합계" not in norm(rows[1][COL_SUSI_SUM]) \
                or "합계" not in norm(rows[1][COL_JEONGSI_SUM]):
            raise SystemExit("입학정원/합계 열 위치 다름")
        if norm(rows[1][15]) != "정원외":
            raise SystemExit("정원외 열 위치 다름")

        words = page.extract_words()
        edges = page.edges
        tx0 = table.bbox[0]
        # 열 경계: 계 행(첫 데이터 행)의 셀로 결정
        first_data = table.rows[5]
        c_ip = first_data.cells[COL_IPHAK]
        iphak_x0 = c_ip[0]
        # 계열 열: x 범위는 입학정원 열 왼쪽의 세로 병합 셀들
        gyeyeol_cells = [c for c in table.cells if abs(c[2] - iphak_x0) < 1.5 and c[1] > c_ip[1] - 1]
        gx0 = min(c[0] for c in gyeyeol_cells)
        name_x1 = gx0
        # 이름 칸 안의 세로선(묶음 모집단위: 자유전공학부, 첨단융합학부)
        inner_v = [e for e in edges if e["orientation"] == "v" and tx0 + 5 < e["x0"] < name_x1 - 5]
        # 표 전체 폭 가로선(묶음 경계)
        full_h = sorted({round(e["top"], 1) for e in edges
                         if e["orientation"] == "h" and e["x0"] < tx0 + 5 and e["x1"] > name_x1})

        units, notes_sum = [], []
        pdf_total = None
        susi_sum_ok = susi_sum_bad = jeong_sum_ok = 0
        jeong_bad = []
        data_rows = list(zip(table.rows[5:], rows[5:]))
        for trow, r in data_rows:
            cell = trow.cells[COL_IPHAK]
            top, bottom = cell[1], cell[3]
            # 이름 읽기
            v = [e for e in inner_v if e["top"] <= (top + bottom) / 2 <= e["bottom"]]
            if v:
                vx = v[0]["x0"]
                sub = "".join(w["text"] for w in words_in(words, tx0, vx - 0.5, top, bottom) if w["x0"] >= vx) or \
                      "".join(w["text"] for w in words_in(words, vx, name_x1, top, bottom))
                gtop = max([h for h in full_h if h <= top + 1], default=top)
                gbot = min([h for h in full_h if h >= bottom - 1], default=bottom)
                grp = "".join(w["text"] for w in words_in(words, tx0, vx, gtop, gbot))
                if not sub or not grp:
                    raise SystemExit(f"묶음 모집단위 이름 못 읽음: y={top:.0f}")
                name = f"{grp}({sub})"
            else:
                name = " ".join(w["text"] for w in words_in(words, tx0, name_x1, top, bottom))
            name = name.strip()
            # 계열 읽기
            gcell = [c for c in gyeyeol_cells if c[1] - 1 <= (top + bottom) / 2 <= c[3] + 1]
            gyeyeol = None
            if gcell:
                g = gcell[0]
                joined = "".join(w["text"] for w in words_in(words, g[0], g[2], g[1], g[3]))
                if joined in GYEYEOL:
                    gyeyeol = joined
                else:
                    own = "".join(w["text"] for w in words_in(words, g[0], g[2], top, bottom))
                    gyeyeol = own if own in GYEYEOL else None

            if name in ("계", "합계"):
                tot = {k: to_int(r[i]) for k, i in COLS.items()}
                tot["입학정원"] = to_int(r[COL_IPHAK])
                tot["수시합계"] = to_int(r[COL_SUSI_SUM])
                tot["정시합계"] = to_int(r[COL_JEONGSI_SUM])
                if pdf_total is None:
                    pdf_total = tot
                elif tot != pdf_total:
                    raise SystemExit("계 행과 합계 행 값이 다름")
                continue
            if not name:
                raise SystemExit(f"이름 없는 행 y={top:.0f}: {r}")

            inwon = {}
            for k, i in COLS.items():
                val = to_int(r[i])
                if val:
                    inwon[k] = val
            gye = to_int(r[COL_IPHAK])
            units.append({
                "단과대학": None,
                "모집단위": name,
                "계열": gyeyeol,
                "인원": inwon,
                "계": gye,
                "쪽": pno,
                "검증": "합계일치" if sum(inwon.values()) == gye else "합계불일치",
            })
            # 보조 대조: 수시모집 합계 칸, 정시모집 합계 칸(정원외 포함)
            s = sum(inwon.get(k, 0) for k in SUSI_KEYS)
            if s == to_int(r[COL_SUSI_SUM]):
                susi_sum_ok += 1
            else:
                susi_sum_bad += 1
                notes_sum.append(f"{name}: 수시합계칸 {r[COL_SUSI_SUM]} vs 수시합 {s}")
            j = sum(inwon.get(k, 0) for k in JEONGSI_KEYS) + sum(to_int(r[i]) for i in COLS_OUT)
            if j == to_int(r[COL_JEONGSI_SUM]):
                jeong_sum_ok += 1
            else:
                jeong_bad.append(f"{name}(정시합계칸 {r[COL_JEONGSI_SUM]}, 정원내정시+농어촌+특성화+기초 {j})")

    memo = [
        "정원내만 수록: 정시 정원외 기회균형전형Ⅱ(농어촌학생, 특성화고교졸업자, 기초생활수급자 등, 장애인 등)와 "
        "재외국민·북한이탈주민 특별전형(인원 제한 없음)은 넣지 않음",
        "수시 기회균형전형Ⅰ은 표의 '정원 내' 열 → 수록",
        "계 = 표의 '입학정원' 칸 값. 이 표에는 행별 정원내 전체 합계 칸이 따로 없고, 표의 계/합계 행이 정원내 총계(1,802)를 "
        "입학정원 열에 적고 있어 그 칸을 계로 사용함(p4 '정원 내 소계 1,802'와 같음)",
        "단과대학: 표에 단과대학 칸이 없어 null",
        "자유전공학부·첨단융합학부는 표에서 묶음 이름 + 하위 이름(인문/자연, 전공명)으로 나뉘어 있어 '묶음(하위)' 형식으로 적음",
        "계열: 표의 계열 칸 그대로(자유전공학부는 행마다 인문/자연이 따로 적혀 있음)",
        f"보조 대조(수시모집 합계 칸 = 수시 전형 합): {susi_sum_ok}행 일치, {susi_sum_bad}행 불일치"
        + (" — " + "; ".join(notes_sum) if notes_sum else ""),
        f"보조 대조(정시모집 합계 칸 = 정원내 정시 + 정원외 농어촌·특성화·기초, 장애인 등은 세로 병합 칸이라 제외): "
        f"{jeong_sum_ok}행 일치" + (", 불일치 " + "; ".join(jeong_bad) if jeong_bad else ""),
    ]
    if pdf_total:
        s_pdf = sum(pdf_total[k] for k in SUSI_KEYS)
        j_pdf = sum(pdf_total[k] for k in JEONGSI_KEYS)
        s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
        j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
        memo.append(f"총계 대조: 수시 {s_pdf}={s_me}, 정시 {j_pdf}={j_me}, 전체 {pdf_total['입학정원']}={s_me + j_me} "
                    f"(PDF 계 행; 수시모집 합계 칸 {pdf_total['수시합계']})")
        bad = [k for k in COLS if pdf_total[k] != sum(u["인원"].get(k, 0) for u in units)]
        memo.append("전형별 열 합 대조: " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)))

    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": [pno], "전형": JEONHYEONG, "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(units)}행 → {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: uos.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
