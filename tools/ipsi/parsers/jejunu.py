"""제주대학교 2028 시행계획 → norm JSON.

표: 'Ⅱ 모집단위 및 모집인원' (PDF 5~8쪽) 격자표. 머리글이 6줄이고 빈칸이 많아서
열 번호 대신 머리글 칸의 x 범위로 각 숫자 칸의 뜻을 정한다.

이 표에는 '정원내만의 합계' 칸이 없다(합계 칸은 정원외 포함). 그래서 `계`는 null,
`검증`은 '합계칸없음'으로 두고, 대신 표 안의 소계/계/합계 칸으로 행마다 따로 대조해
결과를 `메모`에 남긴다.

사용: python3 -I tools/ipsi/parsers/jejunu.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

ID = "jejunu"
NAME = "제주대학교"

S = "수시모집"
G = "정시모집"
A = "전형기간 자율화"
COLS = {
    "대학": ("meta", "대학"),
    "계열": ("meta", "계열"),
    "모집단위": ("meta", "모집단위"),
    "입학정원": ("meta", "입학정원"),
    "모집정원유보": ("meta", "유보"),
    "'26.이월인원": ("meta", "이월"),
    f"{S}|학생부교과|정원내|일반학생": ("in", "수시_교과_일반학생"),
    f"{S}|학생부교과|정원내|지역인재": ("in", "수시_교과_지역인재"),
    f"{S}|학생부교과|정원내|지역인재고른기회": ("in", "수시_교과_지역인재고른기회"),
    f"{S}|학생부교과|정원내|지역의사|진료권|제주시": ("in", "수시_교과_지역의사_제주시"),
    f"{S}|학생부교과|정원내|지역의사|진료권|서귀포시": ("in", "수시_교과_지역의사_서귀포시"),
    f"{S}|학생부교과|정원내|지역의사|광역권": ("in", "수시_교과_지역의사_광역권"),
    f"{S}|학생부교과|소계": ("meta", "교과소계"),
    f"{S}|학생부종합|정원내|일반학생": ("in", "수시_종합_일반학생"),
    f"{S}|학생부종합|정원내|지역인재": ("in", "수시_종합_지역인재"),
    f"{S}|학생부종합|정원내|지역의사|광역권": ("in", "수시_종합_지역의사_광역권"),
    f"{S}|학생부종합|정원내|사회통합": ("in", "수시_종합_사회통합"),
    f"{S}|학생부종합|정원내|고른기회": ("in", "수시_종합_고른기회"),
    f"{S}|학생부종합|정원외|농어촌학생": ("out", "수시_종합_농어촌학생"),
    f"{S}|학생부종합|정원외|특성화고졸업자": ("out", "수시_종합_특성화고졸업자"),
    f"{S}|학생부종합|정원외|특수교육대상자": ("out", "수시_종합_특수교육대상자"),
    f"{S}|학생부종합|소계": ("meta", "종합소계"),
    f"{S}|실기/실적|정원내|일반학생": ("in", "수시_실기_일반학생"),
    f"{S}|실기/실적|정원내|체육특기자": ("in", "수시_실기_체육특기자"),
    f"{S}|실기/실적|소계": ("meta", "실기소계"),
    f"{S}|계": ("meta", "수시계"),
    f"{A}|학생부종합|정원외|평생학습자": ("out", "자율화_종합_평생학습자"),
    f"{A}|학생부종합|정원외|재직자": ("out", "자율화_종합_재직자"),
    f"{A}|학생부종합|소계": ("meta", "자율화소계"),
    f"{G}|나군|정원내|일반학생": ("in", "정시_나_일반학생"),
    f"{G}|나군|정원내|지역인재": ("in", "정시_나_지역인재"),
    f"{G}|나군|정원내|지역의사|진료권|제주시": ("in", "정시_나_지역의사_제주시"),
    f"{G}|나군|정원내|지역의사|진료권|서귀포시": ("in", "정시_나_지역의사_서귀포시"),
    f"{G}|나군|정원내|지역의사|광역권": ("in", "정시_나_지역의사_광역권"),
    f"{G}|다군|정원내|일반학생": ("in", "정시_다_일반학생"),
    f"{G}|계": ("meta", "정시계"),
    "합계": ("meta", "합계"),
    "재외국민과외국인|정원외|1유형": ("text", "재외1"),
    "재외국민과외국인|정원외|2유형": ("text", "재외2"),
}


def J(key, 시기, 유형, 전형명, 군=None):
    return {"key": key, "시기": 시기, "유형": 유형, "전형명": 전형명, "군": 군}


JEONHYEONG = [
    J("수시_교과_일반학생", "수시", "학생부교과", "학생부교과(일반학생)"),
    J("수시_교과_지역인재", "수시", "학생부교과", "학생부교과(지역인재)"),
    J("수시_교과_지역인재고른기회", "수시", "학생부교과", "학생부교과(지역인재고른기회)"),
    J("수시_교과_지역의사_제주시", "수시", "학생부교과", "학생부교과(지역의사(진료권 제주시))"),
    J("수시_교과_지역의사_서귀포시", "수시", "학생부교과", "학생부교과(지역의사(진료권 서귀포시))"),
    J("수시_교과_지역의사_광역권", "수시", "학생부교과", "학생부교과(지역의사(광역권 제주))"),
    J("수시_종합_일반학생", "수시", "학생부종합", "학생부종합(일반학생)"),
    J("수시_종합_지역인재", "수시", "학생부종합", "학생부종합(지역인재)"),
    J("수시_종합_지역의사_광역권", "수시", "학생부종합", "학생부종합(지역의사(광역권 제주))"),
    J("수시_종합_사회통합", "수시", "학생부종합", "학생부종합(사회통합)"),
    J("수시_종합_고른기회", "수시", "학생부종합", "학생부종합(고른기회)"),
    J("수시_실기_일반학생", "수시", "실기/실적", "실기/실적(일반학생)"),
    J("수시_실기_체육특기자", "수시", "실기/실적", "실기/실적(체육특기자)"),
    J("정시_나_일반학생", "정시", "수능", "일반학생", "나"),
    J("정시_나_지역인재", "정시", "수능", "지역인재", "나"),
    J("정시_나_지역의사_제주시", "정시", "수능", "지역의사진료권(제주시)", "나"),
    J("정시_나_지역의사_서귀포시", "정시", "수능", "지역의사진료권(서귀포시)", "나"),
    J("정시_나_지역의사_광역권", "정시", "수능", "지역의사광역권(제주)", "나"),
    J("정시_다_일반학생", "정시", "수능", "일반학생", "다"),
]
IN_KEYS = [j["key"] for j in JEONHYEONG]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]
OUT_KEYS = [n for k, n in COLS.values() if k == "out"]
NUM_RE = re.compile(r"^-?\d{1,3}(,\d{3})*$")


def flat(s):
    return (s or "").replace("\n", "").strip()


def num(cell):
    t = flat(cell)
    if t in ("", "-"):
        return 0, "blank"
    if NUM_RE.match(t):
        return int(t.replace(",", "")), "num"
    return None, "bad"


def header_levels(table, rows_text, n_header):
    levels = []
    for r in range(n_header):
        cells = []
        for bbox, txt in zip(table.rows[r].cells, rows_text[r]):
            if bbox is None or not flat(txt):
                continue
            cells.append((bbox[0], bbox[2], flat(txt)))
        levels.append(cells)
    return levels


def path_for(levels, cx):
    parts = []
    for cells in levels:
        for x0, x1, t in cells:
            if x0 - 0.5 <= cx <= x1 + 0.5:
                parts.append(t)
                break
    return "|".join(parts)


def main(pdf_path, out_path):
    pdf = pdfplumber.open(pdf_path)
    rows, pages_used = [], []
    total_row = None
    college = gyeyeol = None
    unknown = set()

    for pno, page in enumerate(pdf.pages, 1):
        tbl = None
        for t in page.find_tables():
            ex = t.extract()
            if ex and flat(ex[0][0]) == "대학" and len(ex[0]) > 2 and flat(ex[0][2]) == "모집단위":
                tbl, rows_text = t, ex
                break
        if tbl is None:
            continue
        pages_used.append(pno)
        # 머리글 줄 수: 0번 줄 다음으로 모집단위 칸에 글자가 처음 나오는 줄 앞까지
        n_header = next(i for i in range(1, len(rows_text)) if flat(rows_text[i][2]))
        levels = header_levels(tbl, rows_text, n_header)
        first = True
        for ri in range(n_header, len(rows_text)):
            rec = {}
            for bbox, txt in zip(tbl.rows[ri].cells, rows_text[ri]):
                if bbox is None:
                    continue
                rec.setdefault(path_for(levels, (bbox[0] + bbox[2]) / 2), txt)
            for p in rec:
                if p not in COLS and flat(rec[p]):
                    unknown.add(p)
            c_raw = rec.get("대학")
            # '계' 행: 대학·계열·모집단위가 한 칸으로 합쳐져 있어 어느 칸에 걸릴지 모름
            if any(flat(rec.get(k)) == "계" for k in ("대학", "계열", "모집단위")):
                total_row = (pno, rec)
                break
            # 단과대학: 병합 칸이라 None/''이면 앞 값을 잇는다. 쪽이 바뀌며 이름이 잘린 경우
            # (예: 6쪽 '자연과학' + 7쪽 '대학')는 앞 이름이 '대학'으로 끝나지 않을 때만 붙인다.
            if flat(c_raw):
                if first and college and not college.endswith("대학"):
                    college = college + flat(c_raw)
                else:
                    college = flat(c_raw)
                    gyeyeol = None
            g_raw = rec.get("계열")
            if flat(g_raw):
                gyeyeol = flat(g_raw)
            first = False
            vals, bad = {}, []
            for p, txt in rec.items():
                if p not in COLS:
                    continue
                kind, name = COLS[p]
                if kind in ("text",) or name in ("대학", "계열", "모집단위"):
                    continue
                v, st = num(txt)
                if st == "bad":
                    bad.append((name, flat(txt)))
                else:
                    vals[name] = v
            rows.append({"쪽": pno, "대학": college, "계열": gyeyeol,
                         "모집단위": flat(rec.get("모집단위")), "vals": vals, "bad": bad})

    if unknown:
        raise SystemExit(f"알 수 없는 머리글 경로: {sorted(unknown)}")
    if total_row is None:
        raise SystemExit("'계' 행을 찾지 못함")

    # 쪽 경계에서 잘린 단과대학 이름(예: 6쪽 '자연과학' → 7쪽에서 '자연과학대학')을 앞 행에도 반영
    for i in range(len(rows) - 2, -1, -1):
        a, b = rows[i]["대학"], rows[i + 1]["대학"]
        if a and b and a != b and not a.endswith("대학") and b.startswith(a):
            rows[i]["대학"] = b

    # 학부 머리 행(숫자 없음) 다음의 '…전공' 행은 '학부 전공'으로 이름을 붙인다.
    parent = None
    out_units, skipped, excluded = [], [], []
    chk = {k: 0 for k in ("교과소계", "종합소계", "실기소계", "수시계", "자율화소계", "정시계", "합계", "입학정원+이월-유보")}
    fails = []
    n_checked = 0
    for r in rows:
        v = r["vals"]
        name = r["모집단위"]
        has_num = any(v.get(k, 0) for k in IN_KEYS + OUT_KEYS) or v.get("입학정원", 0)
        if not has_num:
            if name.endswith("학부"):
                parent = name
            skipped.append(f"{name}(p{r['쪽']})")
            continue
        if parent and name.endswith("전공"):
            full = f"{parent} {name}"
        else:
            parent = None
            full = name
        if r["bad"]:
            excluded.append(f"{full}(p{r['쪽']}): 읽을 수 없는 칸 {r['bad']}")
            continue
        inn = {k: v.get(k, 0) for k in IN_KEYS}
        out = {k: v.get(k, 0) for k in OUT_KEYS}
        n_checked += 1
        gyo = sum(inn[k] for k in SUSI_KEYS if k.startswith("수시_교과"))
        jong = sum(inn[k] for k in SUSI_KEYS if k.startswith("수시_종합")) + sum(out[k] for k in OUT_KEYS if k.startswith("수시_종합"))
        silgi = sum(inn[k] for k in SUSI_KEYS if k.startswith("수시_실기"))
        auto = sum(out[k] for k in OUT_KEYS if k.startswith("자율화"))
        jeongsi = sum(inn[k] for k in JEONGSI_KEYS)
        tests = {
            "교과소계": (gyo, v.get("교과소계", 0)),
            "종합소계": (jong, v.get("종합소계", 0)),
            "실기소계": (silgi, v.get("실기소계", 0)),
            "수시계": (gyo + jong + silgi, v.get("수시계", 0)),
            "자율화소계": (auto, v.get("자율화소계", 0)),
            "정시계": (jeongsi, v.get("정시계", 0)),
            "합계": (gyo + jong + silgi + auto + jeongsi, v.get("합계", 0)),
            "입학정원+이월-유보": (sum(inn.values()), v.get("입학정원", 0) + v.get("이월", 0) - v.get("유보", 0)),
        }
        for k, (a, b) in tests.items():
            if a == b:
                chk[k] += 1
            else:
                fails.append(f"{full}: {k} 칸 {b} ≠ 계산 {a}")
        인원 = {k: x for k, x in inn.items() if x}
        if not 인원:
            excluded.append(f"{full}(p{r['쪽']}): 정원내 인원 없음")
            continue
        out_units.append({
            "단과대학": r["대학"],
            "모집단위": full,
            "계열": r["계열"],
            "인원": 인원,
            "계": None,
            "쪽": r["쪽"],
            "검증": "합계칸없음",
        })

    memo = [
        "정원내만 수록. 정원외(학생부종합 농어촌학생·특성화고졸업자·특수교육대상자, 전형기간 자율화 학생부종합 평생학습자·재직자, 재외국민과 외국인 1·2유형)는 넣지 않음",
        "PDF 표에 정원내만의 합계 칸이 없어(합계 칸은 정원외 포함) 계=null, 검증='합계칸없음'으로 둠. 대신 아래 행별 대조를 함",
        f"행별 대조({n_checked}행): " + ", ".join(f"{k} {n}/{n_checked}" for k, n in chk.items())
        + (" — 모두 일치" if not fails else f" — 불일치 {fails}"),
        "'입학정원+이월-유보'는 정원내 전형 칸 합이 입학정원 칸에 '26.이월인원 칸을 더한 값과 같은지 본 것(PDF 그대로의 두 칸 사용)",
        "정시 '일반학생' 유형은 '수능'으로 둠. 단 4쪽 요약에 체육계열은 수능60%+실기40%, 예능계열은 수능40%+실기60%라고 되어 있음",
        "계열은 PDF 표의 계열 칸 그대로(병합 칸은 위 값을 이어 씀)",
        "숫자 없는 학부 머리 행은 넣지 않고, 그 아래 '…전공' 행 이름을 '학부 전공'으로 붙임. 숫자 없어 뺀 행: " + ", ".join(skipped),
    ] + excluded

    if total_row:
        pno, rec = total_row
        tv = {}
        for p, txt in rec.items():
            if p in COLS and COLS[p][0] in ("in", "out", "meta") and COLS[p][1] not in ("대학", "계열", "모집단위"):
                n, st = num(txt)
                if st == "num":
                    tv[COLS[p][1]] = n
        susi_pdf = sum(tv.get(k, 0) for k in SUSI_KEYS)
        jeongsi_pdf = tv.get("정시계")
        susi_ours = sum(u["인원"].get(k, 0) for u in out_units for k in SUSI_KEYS)
        jeongsi_ours = sum(u["인원"].get(k, 0) for u in out_units for k in JEONGSI_KEYS)
        per_key = [k for k in IN_KEYS if tv.get(k, 0) != sum(u["인원"].get(k, 0) for u in out_units)]
        memo.append(
            f"총계 대조(PDF {pno}쪽 '계' 행): 수시 정원내 {susi_pdf}={susi_ours}, 정시 {jeongsi_pdf}={jeongsi_ours}"
            f" (PDF 수시 계 {tv.get('수시계')}는 정원외 학생부종합 {sum(tv.get(k, 0) for k in OUT_KEYS if k.startswith('수시'))} 포함)"
        )
        memo.append("전형별 총계 대조: " + ("모두 일치" if not per_key else f"불일치 {per_key}"))
        memo.append(
            f"정원내 전체 {susi_ours + jeongsi_ours} = PDF 입학정원 계 {tv.get('입학정원')} + '26.이월 계 {tv.get('이월', 0)}"
            f" → {'일치' if susi_ours + jeongsi_ours == tv.get('입학정원', 0) + tv.get('이월', 0) else '불일치'}"
        )

    out = {"id": ID, "이름": NAME, "출처쪽": pages_used, "전형": JEONHYEONG, "모집단위": out_units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    cnt = {}
    for u in out_units:
        cnt[u["검증"]] = cnt.get(u["검증"], 0) + 1
    print(f"{ID}: {len(out_units)}행 {cnt}", file=sys.stderr)
    for m in memo:
        print(" -", m, file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
