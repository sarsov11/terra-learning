"""경상국립대학교 2028 시행계획 → norm JSON.

표: 'Ⅳ. 모집인원' (PDF 18~23쪽) 한 장짜리 격자표가 6쪽에 걸쳐 이어진다.
열 위치는 쪽마다 조금 달라서(23쪽은 빈 열이 하나 더 있음) 열 번호가 아니라
머리글 칸의 x 범위로 각 숫자 칸의 뜻을 정한다.

사용: python3 -I tools/ipsi/parsers/gnu.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

ID = "gnu"
NAME = "경상국립대학교"

# 머리글 경로(줄바꿈 제거, '|'로 연결) → 의미
# ("in", key) 정원내 전형 / ("out", name) 정원외 / ("self", name) 기간자율 정원내 / ("meta", name)
COLS = {
    "대학": ("meta", "대학"),
    "계열": ("meta", "계열"),
    "모집단위": ("meta", "모집단위"),
    "모집인원|전체": ("meta", "전체"),
    "모집인원|정원내": ("meta", "정원내"),
    "모집인원|정원외": ("meta", "정원외"),
    "수시모집|학생부교과|정원내|일반": ("in", "수시_교과_일반"),
    "수시모집|학생부교과|정원내|지역": ("in", "수시_교과_지역인재"),
    "수시모집|학생부교과|정원내|기초생활": ("in", "수시_교과_기초생활"),
    "수시모집|학생부교과|정원외|기초생활": ("out", "수시_교과_기초생활_정원외"),
    "수시모집|학생부교과|정원외|특성화": ("out", "수시_교과_특성화고_정원외"),
    "수시모집|실기|정원내|실기/특기": ("in", "수시_실기_실기특기"),
    "수시모집|학생부종합|정원내|일반(일괄)": ("in", "수시_종합_일반일괄"),
    "수시모집|학생부종합|정원내|일반(면접)": ("in", "수시_종합_일반면접"),
    "수시모집|학생부종합|정원내|지역|지역": ("in", "수시_종합_지역인재"),
    "수시모집|학생부종합|정원내|지역|지역의사": ("in", "수시_종합_지역의사"),
    "수시모집|학생부종합|정원내|지역|지역기초": ("in", "수시_종합_지역인재기초"),
    "수시모집|학생부종합|정원내|국가": ("in", "수시_종합_국가보훈"),
    "수시모집|학생부종합|정원내|사회": ("in", "수시_종합_사회통합"),
    "수시모집|학생부종합|정원외|농어촌": ("out", "수시_종합_농어촌_정원외"),
    "수시모집|학생부종합|정원외|장애인등": ("out", "수시_종합_장애인등_정원외"),
    "수시모집모집인원합계": ("meta", "수시합계"),
    "정시모집|수능|정원내|㉮군|일반": ("in", "정시_수능_가_일반"),
    "정시모집|수능|정원내|㉮군|지역": ("in", "정시_수능_가_지역인재"),
    "정시모집|수능|정원내|㉯군|일반": ("in", "정시_수능_나_일반"),
    "정시모집|수능|정원내|㉰군|일반": ("in", "정시_수능_다_일반"),
    "정시모집모집인원합계": ("meta", "정시합계"),
    "기간자율|학생부교과|정원내|평생": ("self", "기간자율_교과_평생학습자"),
    "기간자율|학생부교과|정원외|재직자": ("out", "기간자율_교과_재직자_정원외"),
}

JEONHYEONG = [
    {"key": "수시_교과_일반", "시기": "수시", "유형": "학생부교과", "전형명": "학생부교과(일반전형)", "군": None},
    {"key": "수시_교과_지역인재", "시기": "수시", "유형": "학생부교과", "전형명": "학생부교과(지역인재전형)", "군": None},
    {"key": "수시_교과_기초생활", "시기": "수시", "유형": "학생부교과", "전형명": "학생부교과(기초생활수급자등전형) 정원내", "군": None},
    {"key": "수시_실기_실기특기", "시기": "수시", "유형": "실기/실적", "전형명": "실기/실적(실기전형·특기자전형)", "군": None},
    {"key": "수시_종합_일반일괄", "시기": "수시", "유형": "학생부종합", "전형명": "학생부종합(일반전형)_일괄", "군": None},
    {"key": "수시_종합_일반면접", "시기": "수시", "유형": "학생부종합", "전형명": "학생부종합(일반전형)_면접", "군": None},
    {"key": "수시_종합_지역인재", "시기": "수시", "유형": "학생부종합", "전형명": "학생부종합(지역인재전형)", "군": None},
    {"key": "수시_종합_지역의사", "시기": "수시", "유형": "학생부종합", "전형명": "학생부종합(지역의사선발전형)", "군": None},
    {"key": "수시_종합_지역인재기초", "시기": "수시", "유형": "학생부종합", "전형명": "학생부종합(지역인재 기초생활수급자등전형)", "군": None},
    {"key": "수시_종합_국가보훈", "시기": "수시", "유형": "학생부종합", "전형명": "학생부종합(국가보훈대상자전형)", "군": None},
    {"key": "수시_종합_사회통합", "시기": "수시", "유형": "학생부종합", "전형명": "학생부종합(사회통합전형)", "군": None},
    {"key": "정시_수능_가_일반", "시기": "정시", "유형": "수능", "전형명": "수능(일반전형)", "군": "가"},
    {"key": "정시_수능_가_지역인재", "시기": "정시", "유형": "수능", "전형명": "수능(지역인재전형)", "군": "가"},
    {"key": "정시_수능_나_일반", "시기": "정시", "유형": "수능", "전형명": "수능(일반전형)", "군": "나"},
    {"key": "정시_수능_다_일반", "시기": "정시", "유형": "수능", "전형명": "수능(일반전형)", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]
NUM_RE = re.compile(r"^\d{1,3}(,\d{3})*$")


def flat(s):
    return (s or "").replace("\n", "").strip()


def join_name(s):
    """여러 줄 모집단위명: 괄호 안에서 끊긴 줄은 붙이고, 괄호 밖이면 띄어 쓴다."""
    out = ""
    for part in (s or "").split("\n"):
        part = part.strip()
        if not part:
            continue
        if out and out.count("(") <= out.count(")"):
            out += " " + part
        else:
            out += part
    return out


def num(cell):
    """칸 값 → (int|None, 상태). 빈칸/'-' → 0, '◇' → 0(정시 미선발 표시)."""
    t = flat(cell)
    if t in ("", "-"):
        return 0, "blank"
    if t == "◇":
        return 0, "diamond"
    if NUM_RE.match(t):
        return int(t.replace(",", "")), "num"
    return None, "bad"


def header_paths(table, rows_text, n_header):
    """각 머리글 줄의 (x0, x1, text) 칸 목록."""
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
    units, subtotals, memo_rows, pages_used = [], [], [], []
    total_row = None
    college = None
    diamonds = 0
    unknown_paths = set()

    for pno, page in enumerate(pdf.pages, 1):
        tables = page.find_tables()
        tbl = None
        for t in tables:
            ex = t.extract()
            if ex and flat(ex[0][0]) == "대학" and any(flat(c) == "모집단위" for c in ex[0] if c):
                tbl, rows_text = t, ex
                break
        if tbl is None:
            continue
        pages_used.append(pno)
        # 머리글 줄 수: 숫자 칸이 처음 나오는 줄 앞까지
        n_header = next(i for i, r in enumerate(rows_text) if any(NUM_RE.match(flat(c)) for c in r if c))
        levels = header_paths(tbl, rows_text, n_header)

        for ri in range(n_header, len(rows_text)):
            rec = {}
            for bbox, txt in zip(tbl.rows[ri].cells, rows_text[ri]):
                if bbox is None:
                    continue
                path = path_for(levels, (bbox[0] + bbox[2]) / 2)
                rec.setdefault(path, txt)
            texts = [flat(v) for v in rec.values()]
            if "총계" in texts:
                total_row = (pno, rec)
                break  # 뒤는 지역의사 권역표
            if flat(rec.get("대학")):
                college = flat(rec.get("대학"))
            is_sub = "소계" in texts
            vals, bad = {}, []
            for path, txt in rec.items():
                if path not in COLS:
                    if flat(txt):
                        unknown_paths.add(path)
                    continue
                kind, name = COLS[path]
                if name in ("대학", "계열", "모집단위"):
                    continue
                v, st = num(txt)
                if st == "bad":
                    bad.append((name, flat(txt)))
                    continue
                if st == "diamond":
                    diamonds += 1
                vals[name] = v
            row = {
                "쪽": pno,
                "대학": college,
                "계열": flat(rec.get("계열")) or None,
                "모집단위": join_name(rec.get("모집단위")),
                "vals": vals,
                "bad": bad,
            }
            (subtotals if is_sub else units).append(row)

    if unknown_paths:
        raise SystemExit(f"알 수 없는 머리글 경로: {sorted(unknown_paths)}")

    # ---- 정리 + 검증 ----
    out_units = []
    checks = {"전체=정원내+정원외": 0, "수시합계": 0, "정시합계": 0}
    fails = []
    excluded = []
    for u in units:
        v = u["vals"]
        if u["bad"]:
            excluded.append(f"{u['모집단위']}(p{u['쪽']}): 읽을 수 없는 칸 {u['bad']}")
            continue
        inn = {k: v.get(k, 0) for k in SUSI_KEYS + JEONGSI_KEYS}
        outs = {n: v.get(n, 0) for _, (kind, n) in COLS.items() if kind == "out"}
        selfp = v.get("기간자율_교과_평생학습자", 0)
        # 보조 검증(보고용)
        if v["전체"] == v["정원내"] + v["정원외"]:
            checks["전체=정원내+정원외"] += 1
        else:
            fails.append(f"{u['모집단위']}: 전체≠정원내+정원외")
        susi_all = sum(inn[k] for k in SUSI_KEYS) + sum(x for n, x in outs.items() if n.startswith("수시"))
        if susi_all == v["수시합계"]:
            checks["수시합계"] += 1
        else:
            fails.append(f"{u['모집단위']}: 수시합계 {v['수시합계']}≠{susi_all}")
        if sum(inn[k] for k in JEONGSI_KEYS) == v["정시합계"]:
            checks["정시합계"] += 1
        else:
            fails.append(f"{u['모집단위']}: 정시합계 불일치")
        if sum(outs.values()) != v["정원외"]:
            fails.append(f"{u['모집단위']}: 정원외 칸 합 불일치")

        인원 = {k: x for k, x in inn.items() if x}
        if not 인원:
            # 수시·정시 정원내 인원이 없고 기간자율(평생학습자)만 있는 단위
            excluded.append(
                f"{u['모집단위']}(p{u['쪽']}): 정원내 {v['정원내']}명이 모두 기간자율 학생부교과(평생학습자전형)이라 제외"
            )
            continue
        if selfp:
            excluded.append(f"{u['모집단위']}: 기간자율 평생학습자 {selfp}명은 인원에서 뺌")
        계 = v["정원내"]
        s = sum(인원.values())
        out_units.append({
            "단과대학": u["대학"],
            "모집단위": u["모집단위"],
            "계열": u["계열"],
            "인원": 인원,
            "계": 계,
            "쪽": u["쪽"],
            "검증": "합계일치" if s == 계 else "합계불일치",
        })

    # 단과대학 소계 대조(모든 단위 행, 제외 행 포함)
    sub_ok, sub_bad = 0, []
    for st in subtotals:
        members = [u for u in units if u["대학"] == st["대학"]]
        ok = True
        for name, x in st["vals"].items():
            if sum(u["vals"].get(name, 0) for u in members) != x:
                ok = False
                sub_bad.append(f"{st['대학']} 소계 {name}")
        sub_ok += ok

    # 총계 대조
    memo_total = []
    if total_row:
        pno, rec = total_row
        tv = {}
        for path, txt in rec.items():
            if path in COLS and COLS[path][1] not in ("대학", "계열", "모집단위"):
                n, st = num(txt)
                if st == "num":
                    tv[COLS[path][1]] = n
        susi_pdf = sum(tv.get(k, 0) for k in SUSI_KEYS)
        jeongsi_pdf = sum(tv.get(k, 0) for k in JEONGSI_KEYS)
        susi_ours = sum(u["인원"].get(k, 0) for u in out_units for k in SUSI_KEYS)
        jeongsi_ours = sum(u["인원"].get(k, 0) for u in out_units for k in JEONGSI_KEYS)
        self_pdf = tv.get("기간자율_교과_평생학습자", 0)
        memo_total.append(
            f"총계 대조(PDF {pno}쪽 총계 행 정원내 칸 합=정리 데이터 합): 수시 {susi_pdf}={susi_ours}, "
            f"정시 {jeongsi_pdf}={jeongsi_ours}, 기간자율 정원내(평생학습자) {self_pdf}명은 제외, "
            f"PDF 정원내 총계 {tv.get('정원내')} = 수시+정시+기간자율 {susi_pdf + jeongsi_pdf + self_pdf}"
        )
        per_key = [k for k in SUSI_KEYS + JEONGSI_KEYS
                   if tv.get(k, 0) != sum(u["인원"].get(k, 0) for u in out_units)]
        memo_total.append("전형별 총계 대조: " + ("모두 일치" if not per_key else f"불일치 {per_key}"))

    memo = [
        "정원내만 수록. 정원외(학생부교과 기초생활수급자등·특성화고교졸업자, 학생부종합 농어촌학생·장애인등대상자, 기간자율 재직자)는 넣지 않음",
        "계 = PDF 표의 '모집인원 정원내' 칸(수시·정시·기간자율 정원내 합)",
        "전형기간 자율화 학생부교과(평생학습자전형, 정원내 10명)는 PDF에 수시/정시 시기가 없어 넣지 않음",
        "PDF 표에서 실기/실적(실기전형 49)과 실기/실적(특기자전형 20)은 '실기/특기' 한 칸으로 합쳐져 있어 수시_실기_실기특기 하나로 둠",
        f"정시 칸의 '◇'(정시 미선발 모집단위 표시, 17쪽 각주) {diamonds}칸은 0으로 봄 — 해당 행 정시합계도 0",
        "계열은 PDF 표의 계열 칸 그대로(인문/자연/예체능/광역)",
        f"행 보조검증: 전체=정원내+정원외 {checks['전체=정원내+정원외']}/{len(units)}, "
        f"수시합계 칸 {checks['수시합계']}/{len(units)}, 정시합계 칸 {checks['정시합계']}/{len(units)}"
        + (f" (불일치: {fails})" if fails else ""),
        f"단과대학 소계 행 대조: {sub_ok}/{len(subtotals)} 일치" + (f" (불일치: {sub_bad})" if sub_bad else ""),
    ] + memo_total + excluded

    out = {
        "id": ID,
        "이름": NAME,
        "출처쪽": pages_used,
        "전형": JEONHYEONG,
        "모집단위": out_units,
        "메모": memo,
    }
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
