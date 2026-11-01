#!/usr/bin/env python3
"""삼육대학교 2028 시행계획 파서.

대상 표: "Ⅲ. 2028학년도 수시/정시 모집단위 및 모집인원" (PDF 4쪽, 인쇄 쪽번호 3).
모집단위 칸은 데이터 행에 세로선이 없어 셀로 잡히지 않으므로, 입학정원 칸 셀의
세로 범위 안에 있는 단어로 모집단위 이름을 읽는다.
한 칸에 여러 전형이 '22(학교장)' 처럼 괄호 표시와 함께 들어 있는 경우가 있어 괄호 표시로 전형을 나눈다.
사용법: python3 -I tools/ipsi/parsers/syu.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "syu"
UNIV_NAME = "삼육대학교"

COL_IPHAK = 1
COL_SUSI_SUB = 9      # 수시 정원내 소계
COL_SUSI_ALL = 19     # 수시 계(정원내+정원외)
COL_JEONGSI_SUM = 23  # 정시 계
COL_IN_TOTAL = 24     # 전체(수시+정시) 정원내
COL_OUT_TOTAL = 25    # 전체(수시+정시) 정원외
COLS_OUT = [10, 11, 12, 13, 14, 15, 16]  # 수시 정원외(재외국민 17은 세로 병합 총계라 제외)

# 머리글 확인용
EXPECT = {
    1: {COL_IPHAK: "입학정원"},
    2: {2: "정원내", 10: "정원외", 19: "수시계", 20: "정원내", 23: "정시계", 24: "정원내", 25: "정원외", 26: "합계"},
    3: {2: "학생부교과", 3: "학생부종합", 7: "논술", 8: "실기/실적", 9: "소계", 10: "학생부교과", 14: "학생부종합",
        16: "실기", 17: "재외국민", 18: "소계", 20: "가군", 21: "나군", 22: "다군"},
    4: {2: "학교장추천", 3: "세움인재", 4: "재림목회자/신학특별", 5: "기회균형Ⅰ", 6: "S/W인재", 7: "논술우수자",
        8: "실기우수/학교장/재림/예체능인재", 10: "농어촌", 11: "특성화고", 12: "서해5도", 13: "특성화고졸재직자",
        14: "기회균형Ⅱ", 15: "특수교육", 16: "특수교육", 20: "일반(수능)"},
}

# (열, 괄호표시) → key. 괄호표시 None = 표시 없는 숫자
CELL_KEYS = {
    (2, None): "수시_교과_학교장추천",
    (3, None): "수시_종합_세움인재",
    (4, None): "수시_종합_재림교회목회자추천",
    (4, "신학"): "수시_종합_신학특별",
    (5, None): "수시_종합_기회균형1",
    (6, None): "수시_종합_SW인재",
    (7, None): "수시_논술_논술우수자",
    (8, "실기"): "수시_실기_실기우수자",
    (8, "학교장"): "수시_실기_학교장추천",
    (8, "재림"): "수시_실기_재림교회목회자추천",
    (8, "예체능"): "수시_실기_예체능인재",
    (20, None): "정시_수능_가",
    (20, "실기"): "정시_실기_가",
    (21, None): "정시_수능_나",
    (21, "실기"): "정시_실기_나",
    (22, None): "정시_수능_다",
    (22, "실기"): "정시_실기_다",
}
SUSI_COLS = [2, 3, 4, 5, 6, 7, 8]
JEONGSI_COLS = [20, 21, 22]

JEONHYEONG = [
    {"key": "수시_교과_학교장추천", "시기": "수시", "유형": "학생부교과", "전형명": "학교장추천전형", "군": None},
    {"key": "수시_종합_세움인재", "시기": "수시", "유형": "학생부종합", "전형명": "세움인재전형", "군": None},
    {"key": "수시_종합_재림교회목회자추천", "시기": "수시", "유형": "학생부종합", "전형명": "재림교회목회자추천전형", "군": None},
    {"key": "수시_종합_신학특별", "시기": "수시", "유형": "학생부종합", "전형명": "신학특별전형", "군": None},
    {"key": "수시_종합_기회균형1", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형Ⅰ전형", "군": None},
    {"key": "수시_종합_SW인재", "시기": "수시", "유형": "학생부종합", "전형명": "S/W인재전형", "군": None},
    {"key": "수시_논술_논술우수자", "시기": "수시", "유형": "논술", "전형명": "논술우수자전형", "군": None},
    {"key": "수시_실기_실기우수자", "시기": "수시", "유형": "실기/실적", "전형명": "실기우수자전형", "군": None},
    {"key": "수시_실기_학교장추천", "시기": "수시", "유형": "실기/실적", "전형명": "학교장추천전형(실기/실적 열)", "군": None},
    {"key": "수시_실기_재림교회목회자추천", "시기": "수시", "유형": "실기/실적", "전형명": "재림교회목회자추천전형(실기/실적 열)", "군": None},
    {"key": "수시_실기_예체능인재", "시기": "수시", "유형": "실기/실적", "전형명": "예체능인재전형", "군": None},
    {"key": "정시_수능_가", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "가"},
    {"key": "정시_실기_가", "시기": "정시", "유형": "실기/실적", "전형명": "일반전형(실기)", "군": "가"},
    {"key": "정시_수능_나", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "나"},
    {"key": "정시_실기_나", "시기": "정시", "유형": "실기/실적", "전형명": "일반전형(실기)", "군": "나"},
    {"key": "정시_수능_다", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "다"},
    {"key": "정시_실기_다", "시기": "정시", "유형": "실기/실적", "전형명": "일반전형(실기)", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]


def norm(s):
    return re.sub(r"\s+", "", s or "")


def to_int(cell):
    s = norm(cell).replace(",", "")
    if s in ("", "-", "—", "–"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {cell!r}")


def parse_cell(cell):
    """'22(학교장)\\n3(재림)' → [(22,'학교장'), (3,'재림')], '12' → [(12, None)], '' → []."""
    s = norm(cell).replace(",", "")
    if s in ("", "-", "—", "–"):
        return []
    items = re.findall(r"(\d+)(?:\(([^)]*)\))?", s)
    rebuilt = "".join(n + (f"({lab})" if lab else "") for n, lab in items)
    if rebuilt != s:
        raise ValueError(f"칸 해석 실패: {cell!r}")
    return [(int(n), lab or None) for n, lab in items]


def words_in(words, x0, x1, top, bottom):
    sel = [w for w in words
           if x0 <= (w["x0"] + w["x1"]) / 2 <= x1 and top <= (w["top"] + w["bottom"]) / 2 <= bottom]
    return sorted(sel, key=lambda w: (round(w["top"]), w["x0"]))


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        target = None
        for pno, page in enumerate(pdf.pages, start=1):
            txt = page.extract_text() or ""
            if "수시/정시모집단위및모집인원" in norm(txt):
                for t in page.find_tables():
                    rows = t.extract()
                    if rows and norm(rows[0][0]) == "모집단위" and len(rows[0]) == 27:
                        target = (pno, page, t, rows)
                        break
            if target:
                break
        if not target:
            raise SystemExit("모집단위 및 모집인원 표를 찾지 못함")
        pno, page, table, rows = target

        for level, exp in EXPECT.items():
            r = rows[level - 1]
            for i, e in exp.items():
                if norm(r[i]) != e:
                    raise SystemExit(f"머리글 불일치 row{level - 1} col{i}: {r[i]!r} != {e}")

        words = page.extract_words()
        tx0 = table.bbox[0]
        n_header = 4
        units, excluded, aux_bad = [], [], []
        aux_ok = {"수시소계": 0, "정시계": 0, "수시계": 0}
        pdf_total = None
        for trow, r in zip(table.rows[n_header:], rows[n_header:]):
            c_ip = trow.cells[COL_IPHAK]
            top, bottom = c_ip[1], c_ip[3]
            name = "".join(w["text"] for w in words_in(words, tx0, c_ip[0], top, bottom))
            if not name:
                raise SystemExit(f"이름 없는 행 y={top:.0f}")
            if name == "총계":
                pdf_total = r
                continue
            inwon = {}
            for col in SUSI_COLS + JEONGSI_COLS:
                for n, lab in parse_cell(r[col]):
                    key = CELL_KEYS.get((col, lab))
                    if key is None:
                        raise SystemExit(f"{name}: 알 수 없는 표시 col{col} {lab!r}")
                    if key in inwon:
                        raise SystemExit(f"{name}: {key} 중복")
                    if n:
                        inwon[key] = n
            gye = to_int(r[COL_IN_TOTAL])
            if not inwon and not gye:
                excluded.append(f"{name}: 입학정원 '{norm(r[COL_IPHAK])}', 모집인원 칸 모두 빈칸 → 모집 없음, 넣지 않음")
                continue
            # 보조 대조
            s = sum(v for k, v in inwon.items() if k in SUSI_KEYS)
            j = sum(v for k, v in inwon.items() if k in JEONGSI_KEYS)
            out_s = sum(sum(n for n, _ in parse_cell(r[c])) for c in COLS_OUT)
            if s == to_int(r[COL_SUSI_SUB]):
                aux_ok["수시소계"] += 1
            else:
                aux_bad.append(f"{name}: 수시 정원내 소계 {r[COL_SUSI_SUB]} vs {s}")
            if j == to_int(r[COL_JEONGSI_SUM]):
                aux_ok["정시계"] += 1
            else:
                aux_bad.append(f"{name}: 정시계 {r[COL_JEONGSI_SUM]} vs {j}")
            if s + out_s == to_int(r[COL_SUSI_ALL]):
                aux_ok["수시계"] += 1
            else:
                aux_bad.append(f"{name}: 수시계 {r[COL_SUSI_ALL]} vs 정원내 {s}+정원외 {out_s}")
            units.append({
                "단과대학": None,
                "모집단위": name,
                "계열": None,
                "인원": inwon,
                "계": gye,
                "쪽": pno,
                "검증": "합계일치" if sum(inwon.values()) == gye else "합계불일치",
                "_입학정원": to_int(r[COL_IPHAK]),
            })

    iphak_diff = [f"{u['모집단위']}(입학정원 {u['_입학정원']}, 정원내 {u['계']})" for u in units if u["_입학정원"] != u["계"]]
    for u in units:
        del u["_입학정원"]

    memo = [
        "정원내만 수록: 수시 정원외(농어촌, 특성화고, 서해5도, 특성화고졸재직자, 기회균형Ⅱ, 특수교육(종합·실기), "
        "재외국민 23)는 넣지 않음. 입학정원 제한없는 외국인 전형도 표에 없어 넣지 않음",
        "기회균형Ⅰ은 표의 '정원내' 열 → 수록",
        "계 = 표의 '전체(수시+정시) 정원내' 칸",
        "단과대학·계열: 표에 단과대학·계열 칸이 없어 null",
        "'재림목회자/신학특별' 열: 신학과의 '38(신학)'은 신학특별전형, 나머지 숫자는 재림교회목회자추천전형으로 나눔",
        "'실기우수/학교장/재림/예체능인재' 열: '22(학교장)·3(재림)·3(예체능)·25(실기)'처럼 괄호 표시대로 "
        "학교장추천·재림교회목회자추천·예체능인재·실기우수자 전형으로 나눔(아트앤디자인학과, 체육학과, 음악학과). "
        "이 열의 학교장추천·재림교회목회자추천은 실기/실적 열에 있어 유형을 실기/실적으로 둠",
        "정시 '일반(수능)' 열 숫자 중 '(실기)' 표시가 붙은 것(음악학과 다군 10, 아트앤디자인학과 가군 15, 체육학과 가군 15)은 "
        "정시_실기_<군>(유형 실기/실적)으로 따로 둠",
        "건축학과(4년제), 글로벌문화예술융합학부, 글로벌자유전공학부는 입학정원 '—'에 모집인원이 없어 넣지 않음",
        f"보조 대조: 수시 정원내 소계 칸 {aux_ok['수시소계']}/{len(units)}행 일치, 정시계 칸 {aux_ok['정시계']}/{len(units)}행 일치, "
        f"수시계(정원내+정원외, 재외국민 제외) 칸 {aux_ok['수시계']}/{len(units)}행 일치"
        + (" — 불일치: " + "; ".join(aux_bad) if aux_bad else ""),
        "참고: 입학정원 칸과 정원내 모집인원이 다른 행: " + (", ".join(iphak_diff) if iphak_diff else "없음")
        + " (표 각주: 2026학년도 초과모집 인원 2명(아트앤디자인학과) 감소)",
    ] + excluded

    if pdf_total:
        tot = {}
        for col in SUSI_COLS + JEONGSI_COLS:
            tot[col] = to_int(pdf_total[col])
        s_pdf = to_int(pdf_total[COL_SUSI_SUB])
        j_pdf = to_int(pdf_total[COL_JEONGSI_SUM])
        all_pdf = to_int(pdf_total[COL_IN_TOTAL])
        s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
        j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
        memo.append(f"총계 대조: 수시 {s_pdf}={s_me}, 정시 {j_pdf}={j_me}, 전체 정원내 {all_pdf}={s_me + j_me} (PDF 총계 행)")
        col_keys = {}
        for (col, _), k in CELL_KEYS.items():
            col_keys.setdefault(col, set()).add(k)
        bad = [f"col{col}" for col, ks in col_keys.items()
               if tot[col] != sum(u["인원"].get(k, 0) for u in units for k in ks)]
        memo.append("열별 총계 대조(PDF 총계 행 각 열 = 그 열에서 나온 전형들의 합): " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)))

    used = {k for u in units for k in u["인원"]}
    jeonhyeong = [j for j in JEONHYEONG if j["key"] in used]
    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": [pno], "전형": jeonhyeong, "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    cnt = {}
    for u in units:
        cnt[u["검증"]] = cnt.get(u["검증"], 0) + 1
    print(f"{UNIV_ID}: {len(units)}행 {cnt} → {out_path}")
    for m in memo:
        print(" -", m)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: syu.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
