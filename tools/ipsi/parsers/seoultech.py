#!/usr/bin/env python3
"""서울과학기술대학교 2028 시행계획 파서.

대상 표 (Ⅱ. 2028학년도 모집단위 및 전형유형별 모집인원):
  - "1. 모집단위별 모집인원" (PDF 5쪽): 모집정원 합계/정원내/정원외 → 계 = 정원내 칸
  - "2. 전형유형별 모집인원" 수시 (PDF 6쪽), 정시 (PDF 7쪽)
세 표의 모집단위 이름이 같아 이름으로 맞춘다. 계열은 계열 칸 경계선으로 묶어 읽는다.
사용법: python3 -I tools/ipsi/parsers/seoultech.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "seoultech"
UNIV_NAME = "서울과학기술대학교"

SUSI_COLS = {  # 6쪽 표 열 번호 → key
    3: "수시_교과_고교추천",
    4: "수시_종합_서울텍인재",
    5: "수시_종합_서울텍미래",
    6: "수시_논술",
    7: "수시_실기",
    8: "수시_종합_국가보훈대상자",
    9: "수시_종합_기회균등",
    10: "수시_종합_평생학습자",
}
SUSI_OUT = {11: "농어촌학생", 12: "특성화고재직자", 13: "특수교육대상자", 14: "군위탁"}
SUSI_SUM = 15
SUSI_HDR = {
    1: {3: "정원내", 11: "정원외", 15: "합계"},
    2: {3: "학생부교과", 4: "학생부종합", 6: "논술위주", 7: "실기위주", 8: "학생부위주(기회균형)", 14: "군위탁"},
    3: {3: "고교추천", 4: "서울텍인재", 5: "서울텍미래", 8: "국가보훈대상자", 9: "기회균등", 10: "평생학습자",
        11: "농어촌학생", 12: "특성화고재직자", 13: "특수교육대상자"},
}
JEONG_COLS = {3: "정시_수능_가", 4: "정시_수능_나", 5: "정시_수능실기_나", 6: "정시_수능_다"}
JEONG_SUM = 7
JEONG_HDR = {
    1: {3: "정원내", 7: "합계"},
    2: {3: "수능위주"},
    3: {3: "가군", 4: "나군", 6: "다군"},
    4: {3: "수능100%", 4: "수능100%", 5: "수능+실기", 6: "수능100%"},
}

JEONHYEONG = [
    {"key": "수시_교과_고교추천", "시기": "수시", "유형": "학생부교과", "전형명": "고교추천전형", "군": None},
    {"key": "수시_종합_서울텍인재", "시기": "수시", "유형": "학생부종합", "전형명": "서울텍인재전형", "군": None},
    {"key": "수시_종합_서울텍미래", "시기": "수시", "유형": "학생부종합", "전형명": "서울텍미래전형", "군": None},
    {"key": "수시_논술", "시기": "수시", "유형": "논술", "전형명": "논술전형", "군": None},
    {"key": "수시_실기", "시기": "수시", "유형": "실기/실적", "전형명": "실기전형", "군": None},
    {"key": "수시_종합_국가보훈대상자", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형전형(국가보훈대상자)", "군": None},
    {"key": "수시_종합_기회균등", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형전형(기회균등)", "군": None},
    {"key": "수시_종합_평생학습자", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형전형(평생학습자)", "군": None},
    {"key": "정시_수능_가", "시기": "정시", "유형": "수능", "전형명": "일반전형(수능 100%)", "군": "가"},
    {"key": "정시_수능_나", "시기": "정시", "유형": "수능", "전형명": "일반전형(수능 100%)", "군": "나"},
    {"key": "정시_수능실기_나", "시기": "정시", "유형": "수능", "전형명": "일반전형_예체능계열(수능+실기)", "군": "나"},
    {"key": "정시_수능_다", "시기": "정시", "유형": "수능", "전형명": "일반전형(수능 100%)", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]


def norm(s):
    return re.sub(r"\s+", "", s or "")


def to_int(cell):
    s = norm(cell).replace(",", "")
    if s in ("", "-"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {cell!r}")


def words_in(words, x0, x1, top, bottom):
    sel = [w for w in words
           if x0 <= (w["x0"] + w["x1"]) / 2 <= x1 and top <= (w["top"] + w["bottom"]) / 2 <= bottom]
    return sorted(sel, key=lambda w: (round(w["top"]), w["x0"]))


def find_table(pdf, title, pred):
    for pno, page in enumerate(pdf.pages, start=1):
        if title and title not in norm(page.extract_text() or ""):
            continue
        for t in page.find_tables():
            rows = t.extract()
            if rows and pred(rows):
                return pno, page, t, rows
    raise SystemExit(f"표를 찾지 못함: {title}")


def check_hdr(rows, hdr, label):
    for ri, exp in hdr.items():
        for ci, e in exp.items():
            if norm(rows[ri][ci]) != e:
                raise SystemExit(f"{label} 머리글 불일치 row{ri} col{ci}: {rows[ri][ci]!r} != {e}")


def read_rows(page, table, rows, n_header):
    """데이터 행 → [(이름, 단과대학, 계열, row, trow)] 와 합계 행."""
    words = page.extract_words()
    hc = table.rows[0].cells[0]  # '계열' 머리글 칸 → 계열 칸 x 범위
    g_x0, g_x1 = hc[0], hc[2]
    lines = sorted({round(e["top"], 1) for e in page.edges
                    if e["orientation"] == "h" and e["x0"] <= g_x0 + 2 and e["x1"] >= g_x1 - 2})
    out, total, college = [], None, None
    for ri in range(n_header, len(rows)):
        r, trow = rows[ri], table.rows[ri]
        if norm(r[0]).startswith("합계인원"):
            total = (r, trow)
            continue
        if norm(r[0]).startswith("합계비율"):
            continue
        name = (r[2] or "").strip()
        if not name:
            raise SystemExit(f"이름 없는 행 row{ri}")
        if r[1]:
            college = norm(r[1])
        c = trow.cells[2]
        mid = (c[1] + c[3]) / 2
        gtop = max(h for h in lines if h <= mid)
        gbot = min(h for h in lines if h >= mid)
        g = " ".join(w["text"] for w in words_in(words, g_x0, g_x1, gtop, gbot))
        out.append((name, college, g, r, trow))
    return out, total, words


def sum_col_value(words, hdr_cell, trow):
    """합계 열이 데이터 행에서 셀로 잡히지 않아 머리글 칸의 x 범위와 행 y 범위 안 단어로 읽는다."""
    ref = trow.cells[2]  # 모집단위 칸(행마다 하나)
    ws = words_in(words, hdr_cell[0], hdr_cell[2], ref[1], ref[3])
    return to_int("".join(w["text"] for w in ws))


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        p_q, pg_q, t_q, r_q = find_table(pdf, "모집단위별모집인원",
                                         lambda rows: norm(rows[0][0]) == "계열" and norm(rows[0][3]) == "모집정원")
        if [norm(x) for x in r_q[1][3:6]] != ["합계", "정원내", "정원외"]:
            raise SystemExit("모집정원 표 머리글 다름")
        p_s, pg_s, t_s, r_s = find_table(pdf, "전형유형별모집인원",
                                         lambda rows: norm(rows[0][0]) == "계열" and norm(rows[0][3]) == "수시")
        check_hdr(r_s, SUSI_HDR, "수시")
        p_j, pg_j, t_j, r_j = find_table(pdf, None,
                                         lambda rows: norm(rows[0][0]) == "계열" and norm(rows[0][3]) == "정시")
        check_hdr(r_j, JEONG_HDR, "정시")

        q_rows, q_total, _ = read_rows(pg_q, t_q, r_q, 2)
        s_rows, s_total, s_words = read_rows(pg_s, t_s, r_s, 4)
        j_rows, j_total, j_words = read_rows(pg_j, t_j, r_j, 5)
        s_sum_cell = t_s.rows[1].cells[SUSI_SUM]
        j_sum_cell = t_j.rows[1].cells[JEONG_SUM]

        names = [x[0] for x in q_rows]
        if names != [x[0] for x in s_rows] or names != [x[0] for x in j_rows]:
            raise SystemExit("세 표의 모집단위 목록이 다름")

        units, excluded, aux_bad = [], [], []
        aux_ok = {"수시합계": 0, "정시합계": 0}
        for (name, college, g, rq, _), (_, c2, g2, rs, ts), (_, c3, g3, rj, tj) in zip(q_rows, s_rows, j_rows):
            if (college, g) != (c2, g2) or (college, g) != (c3, g3):
                raise SystemExit(f"{name}: 대학/계열이 표마다 다름 {(college, g)} {(c2, g2)} {(c3, g3)}")
            if rq[4] is None:
                excluded.append(f"{name}: 세 표 모두 숫자 칸이 비어 있음(모집인원 없음) → 넣지 않음")
                continue
            inwon = {}
            for ci, k in SUSI_COLS.items():
                v = to_int(rs[ci])
                if v:
                    inwon[k] = v
            for ci, k in JEONG_COLS.items():
                v = to_int(rj[ci])
                if v:
                    inwon[k] = v
            gye = to_int(rq[4])
            out_s = sum(to_int(rs[ci]) for ci in SUSI_OUT if rs[ci] is not None and re.fullmatch(r"\d*", norm(rs[ci])))
            if not inwon and not gye:
                excluded.append(f"{name}: 정원내 인원 없음(수시 정원외 특성화고재직자 {to_int(rs[12])}명만) → 넣지 않음")
                continue
            # 보조 대조
            ssum = sum(v for k, v in inwon.items() if k in SUSI_KEYS)
            jsum = sum(v for k, v in inwon.items() if k in JEONGSI_KEYS)
            s_cell = sum_col_value(s_words, s_sum_cell, ts)
            j_cell = sum_col_value(j_words, j_sum_cell, tj)
            if s_cell == ssum + out_s:
                aux_ok["수시합계"] += 1
            else:
                aux_bad.append(f"{name}: 수시 합계 칸 {s_cell} vs 정원내 {ssum}+정원외 {out_s}")
            if j_cell == jsum:
                aux_ok["정시합계"] += 1
            else:
                aux_bad.append(f"{name}: 정시 합계 칸 {j_cell} vs {jsum}")
            m = re.search(r"_(인문|자연)$", name)
            gyeyeol = m.group(1) if (m and g == "인문, 자연") else g
            units.append({
                "단과대학": college,
                "모집단위": name,
                "계열": gyeyeol,
                "인원": inwon,
                "계": gye,
                "쪽": p_s,
                "검증": "합계일치" if sum(inwon.values()) == gye else "합계불일치",
            })

    st = s_total[0]
    jt = j_total[0]
    s_pdf = sum(to_int(st[ci]) for ci in SUSI_COLS)
    j_pdf = to_int(jt[JEONG_SUM])
    j_pdf_cols = sum(to_int(jt[ci]) for ci in JEONG_COLS)
    q_pdf = to_int(q_total[0][4])
    s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
    j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
    bad = [k for ci, k in list(SUSI_COLS.items()) if to_int(st[ci]) != sum(u["인원"].get(k, 0) for u in units)]
    bad += [k for ci, k in JEONG_COLS.items() if to_int(jt[ci]) != sum(u["인원"].get(k, 0) for u in units)]

    memo = [
        "정원내만 수록: 수시 정원외(학생부위주(기회균형) 농어촌학생 68, 특성화고재직자 168, 특수교육대상자 10, 군위탁 0)는 넣지 않음. "
        "미래융합대학 7개 학과(융합기계공학과·건설환경융합공학과·헬스피트니스학과·문화예술학과·영어과·벤처경영학과·정보통신융합공학과)는 "
        "정원외 특성화고재직자만 모집해 행 자체를 넣지 않음",
        "기회균형 중 국가보훈대상자·기회균등·평생학습자는 표의 '정원내' 아래 열 → 수록(3쪽 표 기준 학생부종합)",
        "계 = 5쪽 '1. 모집단위별 모집인원' 표의 '모집정원 정원내' 칸(2026학년도 미충원 모집이월 인원 포함, 표 각주)",
        "정시 나군 '수능+실기' 열은 PDF가 수능위주(일반전형_예체능계열) 아래에 둬서 유형 '수능', key 정시_수능실기_나로 따로 둠",
        "단과대학·계열: 표의 대학·계열 칸 그대로. 기술경영융합대학 묶음은 계열 칸이 '인문, 자연'이라 이름 끝에 _인문/_자연이 붙은 "
        "모집단위는 그 표기를 계열로, 나머지(MSDE학과, 경영학과(경영학전공), 자유전공학부(기술경영융합대학))는 '인문, 자연' 그대로 둠",
        f"쪽: 수시 전형유형별 표 쪽({p_s}). 같은 행의 정시 인원은 {p_j}쪽, 계(모집정원 정원내)는 {p_q}쪽",
        f"보조 대조: 수시 표 합계 칸(정원내+정원외) {aux_ok['수시합계']}/{len(units)}행 일치, 정시 표 합계 칸 "
        f"{aux_ok['정시합계']}/{len(units)}행 일치" + (" — 불일치: " + "; ".join(aux_bad) if aux_bad else ""),
        f"총계 대조: 수시 {s_pdf}={s_me}, 정시 {j_pdf}={j_me} (정시 열 합 {j_pdf_cols}), 전체 정원내 {q_pdf}={s_me + j_me} "
        f"(수시 = 6쪽 합계 인원 행의 정원내 8칸 합(수시 합계 {to_int(st[SUSI_SUM])} − 정원외 "
        f"{sum(to_int(st[ci]) for ci in SUSI_OUT)}); 정시 = 7쪽 합계 인원; 전체 = 5쪽 정원내 합계)",
        "전형별 열 합 대조(합계 인원 행): " + ("모두 일치" if not bad else "불일치 " + ", ".join(bad)),
    ] + excluded

    pages = [p_q, p_s, p_j]
    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": pages, "전형": JEONHYEONG, "모집단위": units, "메모": memo}
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
        raise SystemExit("usage: seoultech.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
