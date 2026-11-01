"""숙명여자대학교 2028 시행계획 → norm JSON.

표: PDF 7~8쪽 '2. 수시/정시모집 모집단위 및 모집인원' (pdfplumber 선 기반 표 추출).
정시 유형 구분(가군·나군 '일반학생' 열에 수능과 실기/실적이 섞임)은 같은 PDF 6쪽
'정시모집 전형방법 총괄표'를 읽어 대조한다.

사용: python3 -I tools/ipsi/parsers/sookmyung.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

ID = "sookmyung"
NAME = "숙명여자대학교"
TABLE_PAGES = [7, 8]
SUMMARY_PAGE = 6  # 정시모집 전형방법 총괄표

# 헤더(세로쓰기 글자를 이어 붙인 것) → (key, 시기, 유형, 전형명, 군)
# '정원외'가 헤더에 적힌 열은 자동으로 제외한다.
SUSI_COLS = {
    "숙명인재︵면접형︶": ("수시_종합_숙명인재면접형", "수시", "학생부종합", "숙명인재(면접형)전형", None),
    "소프트웨어인재": ("수시_종합_소프트웨어인재", "수시", "학생부종합", "소프트웨어인재전형", None),
    "기회균형": ("수시_종합_기회균형", "수시", "학생부종합", "기회균형전형", None),
    "지역균형선발": ("수시_교과_지역균형선발", "수시", "학생부교과", "지역균형선발전형", None),
    "논술우수자": ("수시_논술_논술우수자", "수시", "논술", "논술우수자전형", None),
    "예능창의인재": ("수시_실기_예능창의인재", "수시", "실기/실적", "예능창의인재전형", None),
}
# 정시 '일반학생' 열: 군별로 수능/실기실적 key를 둔다.
JEONGSI = {
    "가": {"수능": ("정시_수능_가", "정시", "수능", "수능(일반학생전형)", "가"),
          "실기": ("정시_실기_가", "정시", "실기/실적", "실기/실적(일반학생전형)", "가")},
    "나": {"수능": ("정시_수능_나", "정시", "수능", "수능(일반학생전형)", "나"),
          "실기": ("정시_실기_나", "정시", "실기/실적", "실기/실적(일반학생전형)", "나")},
    "다": {"수능": ("정시_수능_다", "정시", "수능", "수능(일반학생전형)", "다")},
}


def flat(s):
    """셀 글자 정리: NUL(공백 글리프)→공백, 줄바꿈 제거, Wingdings 'w'(◆) 표시 정리."""
    if s is None:
        return None
    s = s.replace("\x00", " ")
    s = "".join(part.strip() for part in s.split("\n"))
    return s.strip()


def num(s):
    """'-'·빈칸 → 0, 숫자 → int, 그 밖 → None(읽을 수 없음/숫자 아님)."""
    if s is None:
        return 0
    t = s.replace("\x00", "").replace("\n", "").replace(" ", "")
    if t in ("", "-"):
        return 0
    if re.fullmatch(r"\d{1,3}(,\d{3})*|\d+", t):
        return int(t.replace(",", ""))
    return None


def find_main_table(page):
    for t in page.extract_tables():
        if t and t[0] and t[0][0] and flat(t[0][0]) == "계열" and len(t[0]) == 23:
            return t
    raise SystemExit(f"p{page.page_number}: 모집단위 표를 찾지 못함")


def header_map(tbl):
    """헤더 3행(세로 전형명)과 1~2행(시기·군)을 읽어 열별 정의를 만든다."""
    names = [flat(c) or "" for c in tbl[3]]
    cols = {}
    gun_by_col = {15: "가", 16: "가", 17: "가", 18: "가", 19: "가", 20: "나", 21: "나", 22: "다"}
    # 군 머리글 확인
    row1 = [flat(c) for c in tbl[1]]
    assert row1[15] == "가군" and row1[20] == "나군" and row1[22] == "다군", row1
    assert flat(tbl[0][5]) == "수시모집" and flat(tbl[0][15]) == "정시모집"
    for i in range(5, 23):
        n = names[i]
        if "정원외" in n:
            cols[i] = None
            continue
        if i < 15:
            if n not in SUSI_COLS:
                raise SystemExit(f"알 수 없는 수시 열 머리글: {n!r}")
            cols[i] = SUSI_COLS[n]
        else:
            if n != "일반학생":
                raise SystemExit(f"알 수 없는 정시 열 머리글: {n!r}")
            cols[i] = ("JEONGSI", gun_by_col[i])
    return cols


# 6쪽 총괄표에서 실기/실적(일반학생전형)으로 적힌 모집단위(학부 이름 기준)를 읽는다.
def read_summary(page):
    tbls = page.extract_tables()
    tbl = None
    for t in tbls:
        if t and flat(t[0][0]) == "군":
            tbl = t
    if tbl is None:
        raise SystemExit("6쪽 정시 총괄표를 찾지 못함")
    out = []  # (군, 유형('수능'/'실기'), 인원 or None, [단위들])
    gun = jh = None
    for r in tbl[2:]:
        if r[0]:
            gun = flat(r[0]).replace("군", "")
        if r[1]:
            jh = r[1]
        if "정원외" in (jh or ""):
            continue
        typ = "실기" if flat(jh).startswith("실기") else "수능"
        units = [u.strip() for u in (r[3] or "").replace("\x00", " ").split("\n") if u.strip()]
        out.append((gun, typ, num(r[2]), units))
    return out


def main(pdf_path, out_path):
    memo = []
    rows = []
    subtotals = []  # (이름, {key: n}, 입학정원)
    grand = None
    unread = []
    notes_cells = []
    with pdfplumber.open(pdf_path) as pdf:
        summary = read_summary(pdf.pages[SUMMARY_PAGE - 1])
        silgi_units = {"가": set(), "나": set()}
        for gun, typ, n, units in summary:
            if typ == "실기":
                silgi_units[gun].update(units)
        gyeyeol = dept = None
        for pno in TABLE_PAGES:
            page = pdf.pages[pno - 1]
            tbl = find_main_table(page)
            cols = header_map(tbl)
            hakbu = None
            for r in tbl[5:]:
                lab0 = flat(r[0])
                if lab0 and ("소계" in lab0 or lab0.endswith("계")):
                    vals = {}
                    for i, d in cols.items():
                        vals[i] = r[i]
                    if lab0.startswith("모집인원"):
                        grand = (lab0, r)
                    else:
                        subtotals.append((lab0, r))
                    continue
                # 계열(0열): 새 셀이면 갱신. 쪽 첫 행의 빈 셀은 앞 쪽에서 이어지는 칸(자연계 소계로 확인).
                if r[0] is not None:
                    if lab0:
                        gyeyeol = lab0
                # 단과대학(1열)·학부(2열)·전공(3열)
                c1, c2, c3 = flat(r[1]), flat(r[2]), flat(r[3])
                if r[0] is not None and lab0 and r[1] is None and c2:
                    # 계열+단과대학 칸이 합쳐진 경우(순헌칼리지)
                    dept = lab0
                    gyeyeol_row = None
                    hakbu = c2
                    major = c3
                else:
                    gyeyeol_row = gyeyeol
                    if r[1] is not None:
                        if r[2] is None:
                            # 단과대학 칸이 학부 칸까지 합쳐짐 → 그 글자는 학부 이름(단과대학 미기재)
                            dept = None
                            hakbu = c1
                        else:
                            dept = c1 or None
                            hakbu = c2
                    elif r[2] is not None:
                        hakbu = c2
                    major = c3
                if dept is not None and lab0 == "순헌칼리지":
                    gyeyeol_row = None
                if r[0] is not None and lab0 == "순헌칼리지":
                    gyeyeol = None
                    gyeyeol_row = None
                cap = num(r[4])
                if cap is None:
                    unread.append(f"p{pno} {hakbu} {major}: 입학정원 칸 {r[4]!r}")
                    continue
                if not hakbu:
                    raise SystemExit(f"p{pno}: 모집단위 이름 없음 {r}")
                hakbu_clean = hakbu.replace("w악기별모집", "")
                unit = hakbu_clean if not major else f"{hakbu_clean} {major}"
                inwon = {}
                bad = False
                for i, d in cols.items():
                    if d is None:
                        continue
                    v = num(r[i])
                    if v is None:
                        raw = flat(r[i])
                        if raw == "수시미충원인원":
                            notes_cells.append((unit, i, raw))
                            continue
                        unread.append(f"p{pno} {unit}: {i}열 {raw!r}")
                        bad = True
                        continue
                    if v == 0:
                        continue
                    if d[0] == "JEONGSI":
                        gun = d[1]
                        kind = "실기" if (gun in silgi_units and hakbu_clean in silgi_units[gun]) else "수능"
                        key = JEONGSI[gun][kind][0]
                    else:
                        key = d[0]
                    inwon[key] = inwon.get(key, 0) + v
                if bad:
                    continue
                rows.append({
                    "단과대학": dept,
                    "모집단위": unit,
                    "계열": gyeyeol_row,
                    "인원": inwon,
                    "계": None,
                    "쪽": pno,
                    "검증": None,
                    "_hakbu": hakbu_clean,
                    "_cap": cap,
                })
            if "w악기별모집" in "".join(flat(x) or "" for rr in tbl for x in rr):
                memo.append("관현악과: PDF 표기 '관현악과◆악기별모집'(◆=Wingdings 글리프) → 모집단위 이름은 '관현악과'로 적음")

    # 전형 목록
    jeonhyeong = []
    seen = set()
    for v in SUSI_COLS.values():
        jeonhyeong.append(v)
    for g in ("가", "나", "다"):
        for kind in ("수능", "실기"):
            if kind in JEONGSI[g]:
                jeonhyeong.append(JEONGSI[g][kind])
    used = {k for r in rows for k in r["인원"]}
    jlist = []
    for k, si, ty, nm, gun in jeonhyeong:
        if k in seen or k not in used:
            continue
        seen.add(k)
        jlist.append({"key": k, "시기": si, "유형": ty, "전형명": nm, "군": gun})

    # 행 검증: 표에 행별 모집인원 합계 칸이 없음 → 계=null. '입학정원' 칸과의 비교는 보조 대조로만 메모에 남김.
    for r in rows:
        s = sum(r["인원"].values())
        if r["계"] is None:
            r["검증"] = "합계칸없음"
        else:
            r["검증"] = "합계일치" if s == r["계"] else "합계불일치"
    cap_same = sum(1 for r in rows if sum(r["인원"].values()) == r["_cap"])
    mismatch = [f"{r['모집단위']}(입학정원 {r['_cap']}, 정원내 합 {sum(r['인원'].values())})"
                for r in rows if sum(r["인원"].values()) != r["_cap"]]

    # 소계·총계 대조 (정원내 열만)
    def colsum(rs, pred):
        return sum(v for r in rs for k, v in r["인원"].items() if pred(k))

    susi = colsum(rows, lambda k: k.startswith("수시"))
    jeong = colsum(rows, lambda k: k.startswith("정시"))
    # 총계 행: 열 순서대로 정원내 열만 합
    def row_sum(raw, cols_def, which):
        tot = 0
        for i, d in cols_def.items():
            if d is None:
                continue
            is_susi = d[0] != "JEONGSI"
            if (which == "수시") != is_susi:
                continue
            v = num(raw[i])
            if v is None:
                v = 0
            tot += v
        return tot

    with pdfplumber.open(pdf_path) as pdf:
        cols_def = header_map(find_main_table(pdf.pages[TABLE_PAGES[-1] - 1]))
    g_susi = row_sum(grand[1], cols_def, "수시")
    g_jeong = row_sum(grand[1], cols_def, "정시")
    g_cap = num(grand[1][4])
    memo.insert(0, "정원내만 수록: 수시 농어촌학생·특성화고교출신자·특성화고졸재직자·특수교육대상자(정원외), "
                   "정시 가군 사회배려·농어촌학생·특성화고교출신자·특성화고졸재직자(정원외), 나군 사회배려(정원외)는 넣지 않음")
    memo.append("수시 학생부종합 기회균형전형은 정원외 표시가 없는 정원내 전형 → 수록")
    memo.append("표에 행별 모집인원 합계 칸이 없음(입학정원 칸만 있음) → 계=null, 검증='합계칸없음'")
    memo.append(f"보조 대조(입학정원 칸 vs 행 정원내 합): {cap_same}행 같음"
                + (", 다름(PDF 숫자 그대로, 보정 안 함): " + "; ".join(mismatch) if mismatch else ""))
    memo.append(f"총계 대조: 수시 {susi}={g_susi}, 정시 {jeong}={g_jeong} "
                f"(PDF '모집인원 계' 행 정원내 열 합 = 정리 데이터 합; 같은 행 입학정원 칸 {g_cap}, 정원내 합 {g_susi + g_jeong})")
    # 소계 행 대조
    sub_ok, sub_bad = 0, []
    # 계열별 소계: 인문계/자연계/예·체능계/순헌칼리지
    groups = {"인문계소계": lambda r: r["계열"] == "인문", "자연계소계": lambda r: r["계열"] == "자연",
              "예·체능계소계": lambda r: r["계열"] == "예·체능", "순헌칼리지소계": lambda r: r["단과대학"] == "순헌칼리지"}
    for lab, raw in subtotals:
        key = lab.replace(" ", "")
        if key not in groups:
            sub_bad.append(f"{lab}: 알 수 없는 소계")
            continue
        rs = [r for r in rows if groups[key](r)]
        for which in ("수시", "정시"):
            a = colsum(rs, lambda k: k.startswith(which))
            b = row_sum(raw, cols_def, which)
            if a == b:
                sub_ok += 1
            else:
                sub_bad.append(f"{lab} {which} {a}≠{b}")
    memo.append(f"계열 소계 행 대조(정원내 수시·정시): {sub_ok}건 일치" + (", 불일치: " + "; ".join(sub_bad) if sub_bad else ""))
    memo.append("계열: 표의 계열 칸 그대로(인문/자연/예·체능). 8쪽 첫 3행(의류학과·식품영양학과·약학부)은 7쪽에서 이어지는 '자연' 칸(8쪽 '자연계 소계'에 포함). "
                "순헌칼리지 자유전공학부는 계열 칸이 단과대학 칸과 합쳐져 계열 null")
    memo.append("단과대학: 표의 단과대학 칸 그대로(문과·생활과학·사회과학·법과·경상·이과·공과·약학·음악·미술·순헌칼리지). "
                "글로벌서비스학부·영어영문학부·미디어학부는 단과대학 칸이 학부 칸과 합쳐져 단과대학 null")
    # 정시 유형 대조 (6쪽 총괄표)
    checks = []
    for gun, typ, n, units in summary:
        if n is None:
            checks.append(f"{gun}군 {typ} {'/'.join(units)}: 총괄표 인원 '수시 미충원인원'(숫자 없음)")
            continue
        key = JEONGSI[gun]["실기" if typ == "실기" else "수능"][0]
        tot = 0
        for u in units:
            if u in ("인문계", "자연계"):
                rs = [r for r in rows if r["계열"] == u[:2]]
            else:
                rs = [r for r in rows if r["_hakbu"] == u]
            tot += sum(r["인원"].get(key, 0) for r in rs)
        checks.append(f"{gun}군 {'실기/실적' if typ == '실기' else '수능'} {'/'.join(units)} {tot}={n}" + ("" if tot == n else " 불일치"))
    memo.append("정시 '일반학생' 열은 6쪽 정시 총괄표에 따라 피아노과·성악과·회화과·무용과(가군), 관현악과·작곡과(나군)를 실기/실적, 나머지를 수능으로 나눔. "
                "총괄표 대조: " + "; ".join(checks))
    for unit, i, raw in notes_cells:
        memo.append(f"{unit}: 정시 가군 일반학생 칸이 '수시미충원인원'(숫자 아님) → 정시 인원 미수록")
    if unread:
        memo.append("읽지 못해 뺀 칸/행: " + "; ".join(unread))

    for r in rows:
        r.pop("_hakbu")
        r.pop("_cap")
    out = {"id": ID, "이름": NAME, "출처쪽": TABLE_PAGES + [SUMMARY_PAGE], "전형": jlist, "모집단위": rows, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    from collections import Counter
    print(ID, len(rows), "rows", dict(Counter(r["검증"] for r in rows)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
