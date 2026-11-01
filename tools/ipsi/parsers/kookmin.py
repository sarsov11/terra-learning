#!/usr/bin/env python3
"""국민대학교 2028 시행계획 파서.

대상 표: "2028학년도 모집시기별 모집인원" (PDF 12~13쪽, 인쇄 10~11쪽).
  - 12쪽: 인문·자연 계열, 13쪽: 예체능·전공자율 계열(머리글 열 구성이 12쪽과 다름)
  - 표의 칸(cell)을 pdfplumber 선 격자로 잡고, 글자는 중심 좌표로 칸에 넣는다.
  - 머리글은 세로쓰기라 두 줄이 섞여 읽히므로, 전형 이름을 '글자 순서 부분열'로 찾는다.
대조용: 7쪽 모집 요약(수시 정원내·정시 총계), 14쪽 수시모집 주요사항(전형별 모집인원).
사용법: python3 -I tools/ipsi/parsers/kookmin.py <pdf> <out.json>
"""
import json
import re
import sys

import pdfplumber

UNIV_ID = "kookmin"
UNIV_NAME = "국민대학교"

JEONHYEONG = [
    {"key": "수시_교과_교과우수자1", "시기": "수시", "유형": "학생부교과", "전형명": "교과우수자(학교장추천)Ⅰ", "군": None},
    {"key": "수시_교과_교과우수자2", "시기": "수시", "유형": "학생부교과", "전형명": "교과우수자(학교장추천)Ⅱ", "군": None},
    {"key": "수시_종합_국민프런티어", "시기": "수시", "유형": "학생부종합", "전형명": "국민프런티어전형", "군": None},
    {"key": "수시_종합_국제인재", "시기": "수시", "유형": "학생부종합", "전형명": "국제인재전형", "군": None},
    {"key": "수시_종합_알고리즘우수자", "시기": "수시", "유형": "학생부종합", "전형명": "알고리즘우수자전형", "군": None},
    {"key": "수시_종합_기회균형1", "시기": "수시", "유형": "학생부종합", "전형명": "기회균형Ⅰ전형", "군": None},
    {"key": "수시_종합_성인학습자", "시기": "수시", "유형": "학생부종합", "전형명": "성인학습자전형", "군": None},
    {"key": "수시_논술", "시기": "수시", "유형": "논술", "전형명": "논술전형", "군": None},
    {"key": "수시_실기_특기자", "시기": "수시", "유형": "실기/실적", "전형명": "특기자전형", "군": None},
    {"key": "수시_실기_실기우수자", "시기": "수시", "유형": "실기/실적", "전형명": "실기우수자전형", "군": None},
    {"key": "정시_수능_일반_가", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "가"},
    {"key": "정시_수능_일반_나", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "나"},
    {"key": "정시_수능_일반_다", "시기": "정시", "유형": "수능", "전형명": "일반전형", "군": "다"},
]
SUSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "수시"]
JEONGSI_KEYS = [j["key"] for j in JEONHYEONG if j["시기"] == "정시"]
OUT = "정원외"


def norm(s):
    return re.sub(r"\s+", "", s or "")


def to_int(s):
    s = norm(s).replace(",", "")
    if s in ("", "-"):
        return 0
    if re.fullmatch(r"\d+", s):
        return int(s)
    raise ValueError(f"숫자 아님: {s!r}")


def subseq(word, s):
    """word의 글자가 s 안에 순서대로(떨어져도 됨) 모두 있는가."""
    it = iter(s)
    return all(ch in it for ch in word)


DOT_GAPS = []  # (원문 이름, 쪽) — 가운뎃점 글리프가 텍스트층에 없어 '·'을 넣은 곳


def cell_text(chars, box, line_sep="", dots=False):
    """중심점이 칸 안에 드는 글자를 줄 단위로 이어 붙인다.

    dots=True: 한 줄 안에서 한글 사이 간격이 1.2~2.5pt면 가운뎃점(·) 글리프가 빠진 자리로 보고 '·'을 넣는다
    (이 PDF는 이름 속 '·'이 텍스트층에 없고 그 자리만 비어 있음 — 8~9쪽 입학정원 표에는 '·'이 글자로 있음).
    """
    x0, top, x1, bot = box
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
            if i and dots:
                p = lc[i - 1]
                g = c["x0"] - p["x1"]
                if 1.2 <= g <= 2.5 and re.match(r"[가-힣]", p["text"]) and re.match(r"[가-힣]", c["text"]):
                    s += "·"
            s += c["text"]
        out.append(re.sub(r"\s+", " ", s).strip())
    res = ""
    for o in (o for o in out if o):
        # 줄을 붙일 때 영문끼리 만나면 공백(International + College)
        sep = " " if res and re.search(r"[A-Za-z]$", res) and re.match(r"[A-Za-z]", o) else (line_sep if res else "")
        res += sep + o
    return res


def classify(path):
    """머리글 경로(위→아래 칸 글자) → 전형 key / OUT / None(모르는 열)."""
    s = "".join(norm(p) for p in path)
    leaf = norm(path[-1]) if path else ""
    if subseq("정원외", s) or leaf in ("재외국민", "농어촌") or "Ⅱ" in leaf and subseq("기회균형", leaf) \
            or leaf.startswith("특고졸"):
        return OUT
    if subseq("교과우수자Ⅰ", s) and subseq("학교장추천", s):
        return "수시_교과_교과우수자1"
    if subseq("교과우수자Ⅱ", s) and subseq("학교장추천", s):
        return "수시_교과_교과우수자2"
    for word, key in (("국민프런티어", "수시_종합_국민프런티어"), ("국제인재", "수시_종합_국제인재"),
                      ("알고리즘우수자", "수시_종합_알고리즘우수자"), ("성인학습자", "수시_종합_성인학습자"),
                      ("논술", "수시_논술"), ("특기자", "수시_실기_특기자"), ("실기우수자", "수시_실기_실기우수자")):
        if leaf == word:
            return key
    if leaf in ("기회균형I", "기회균형Ⅰ"):
        return "수시_종합_기회균형1"
    if leaf == "일반전형":
        for g in "가나다":
            if f"{g}군" in s:
                return f"정시_수능_일반_{g}"
    return None


def find_tables(pdf):
    """머리글 첫 칸이 계열/대학/모집단위이고 수시모집·정시모집이 있는 표."""
    found = []
    for pno, page in enumerate(pdf.pages, start=1):
        for t in page.find_tables():
            rows = t.extract()
            if not rows or norm(rows[0][0]) != "계열" or norm(rows[0][1]) != "대학" or norm(rows[0][2]) != "모집단위":
                continue
            flat = norm("".join(c or "" for c in rows[0]))
            if "수시모집" in flat and "정시모집" in flat:
                found.append((pno, page, t))
    return found


def parse_table(pno, page, t, units, skipped):
    chars = page.chars
    cells = t.cells
    # 머리글/데이터 경계: 모집단위 머리글 칸의 아래선
    name_hdr = [c for c in cells if norm(cell_text(chars, c)) == "모집단위"]
    if len(name_hdr) != 1:
        raise SystemExit(f"{pno}쪽 모집단위 머리글 칸 {len(name_hdr)}개")
    nh = name_hdr[0]
    data_top = nh[3]
    gy_hdr = [c for c in cells if norm(cell_text(chars, c)) == "계열" and c[3] <= data_top + 0.5][0]
    dh_hdr = [c for c in cells if norm(cell_text(chars, c)) == "대학" and c[3] <= data_top + 0.5][0]
    # 데이터 열 = 머리글 맨 아래 칸(아래선 = data_top) 중 모집단위 오른쪽
    leaves = sorted([c for c in cells if abs(c[3] - data_top) < 0.5 and c[0] >= nh[2] - 0.5], key=lambda c: c[0])
    cols = []
    for lf in leaves:
        xm = (lf[0] + lf[2]) / 2
        path = [cell_text(chars, c) for c in sorted(cells, key=lambda c: c[1])
                if c[0] <= xm <= c[2] and c[3] <= data_top + 0.5]
        key = classify(path)
        if key is None:
            raise SystemExit(f"{pno}쪽 모르는 머리글 열 x={lf[0]:.0f}: {path}")
        cols.append((lf[0], lf[2], key, "/".join(norm(p) for p in path)))
    keys_here = [k for *_, k, _ in cols if k != OUT]
    if len(keys_here) != len(set(keys_here)):
        raise SystemExit(f"{pno}쪽 같은 전형 열 중복: {keys_here}")
    data_x0 = cols[0][0]

    def covering(x0, x1, ym):
        xm = (x0 + x1) / 2
        cs = [c for c in cells if c[0] <= xm <= c[2] and c[1] - 0.5 <= ym <= c[3] + 0.5 and c[1] >= data_top - 0.5]
        return cs[0] if cs else None

    # 행 경계: 데이터 영역 칸들의 위·아래 선 y(중복 제거). t.rows의 bbox는 병합 칸 높이까지 넓어져 쓰지 않음
    ys = []
    for v in sorted([c[1] for c in cells if c[1] >= data_top - 0.5] + [c[3] for c in cells if c[3] > data_top + 0.5]):
        if not ys or v - ys[-1] > 1.0:
            ys.append(v)
    for top, bot in zip(ys, ys[1:]):
        ym = (top + bot) / 2
        # 모집단위 이름: 이름 영역(모집단위 머리글 왼끝 ~ 첫 데이터 열) 안의 칸 1~2개
        ncells = sorted([c for c in cells if c[0] >= nh[0] - 0.5 and c[2] <= data_x0 + 0.5
                         and c[1] - 0.5 <= ym <= c[3] + 0.5 and c[1] >= data_top - 0.5], key=lambda c: c[0])
        parts = [cell_text(chars, c, line_sep=" ", dots=True) for c in ncells]
        parts = [p for p in parts if p]
        if not parts:
            raise SystemExit(f"{pno}쪽 y={top:.0f} 이름 없음")
        name = parts[0] if len(parts) == 1 else f"{parts[0]}({parts[1]})"
        if len(parts) > 2:
            raise SystemExit(f"{pno}쪽 이름 칸 3개 이상: {parts}")
        raw = "".join(cell_text(chars, c, line_sep=" ") for c in ncells)
        if "·" in name and "·" not in raw:
            DOT_GAPS.append(name)
        gc = covering(gy_hdr[0], gy_hdr[2], ym)
        dc = covering(dh_hdr[0], dh_hdr[2], ym)
        gyeyeol = norm(cell_text(chars, gc)) if gc else ""
        college = cell_text(chars, dc, dots=True) if dc else ""
        inwon = {}
        out_vals = []
        for x0, x1, key, _ in cols:
            c = covering(x0, x1, ym)
            if c is None:
                raise SystemExit(f"{pno}쪽 {name}: x={x0:.0f} 칸 없음")
            txt = cell_text(chars, c)
            if key == OUT:
                if norm(txt):
                    out_vals.append(norm(txt))
                continue
            if c[1] < top - 0.5 or c[3] > bot + 0.5:
                raise SystemExit(f"{pno}쪽 {name}: 정원내 열 {key} 칸이 세로 병합")
            v = to_int(txt)
            if v:
                inwon[key] = v
        if not inwon:
            skipped.append(f"{name}(정원내 칸 비어 있음, 정원외 칸 {'/'.join(out_vals) or '없음'})")
            continue
        units.append({
            "단과대학": college or None,
            "모집단위": name,
            "계열": gyeyeol or None,
            "인원": inwon,
            "계": None,
            "쪽": pno,
            "검증": "합계칸없음",
        })
    return [c[3] for c in cols]


def read_summary(pdf):
    """7쪽 모집 요약: 수시 정원내, 정시 총계. 14쪽 수시 전형별 인원."""
    susi_in = jeong = None
    s_pno = None
    for pno, page in enumerate(pdf.pages, start=1):
        t = norm(page.extract_text() or "")
        if "모집요약" in t:
            m1 = re.search(r"수시모집<[\d,]+명>정원내([\d,]+)명", t)
            m2 = re.search(r"정시모집<([\d,]+)명>", t)
            if m1 and m2:
                susi_in, jeong, s_pno = int(m1.group(1).replace(",", "")), int(m2.group(1).replace(",", "")), pno
                break
    per = {}
    p_pno = None
    for pno, page in enumerate(pdf.pages, start=1):
        if "수시모집 주요사항" not in (page.extract_text() or ""):
            continue
        for t in page.extract_tables():
            if not t or norm(t[0][0]) != "전형구분":
                continue
            group = None
            kyo = []
            for r in t[2:]:
                a, b, n = norm(r[1]), norm(r[2]), to_int(r[3])
                if a:
                    group = a
                if group == "교과우수자(학교장추천)":
                    kyo.append(n)
                elif group in ("국민프런티어", "국제인재", "알고리즘우수자", "기회균형", "성인학습자", "논술"):
                    per[group] = n
                elif group in ("특기자", "실기우수자"):
                    per[group] = per.get(group, 0) + n
            per["교과우수자"] = kyo
            p_pno = pno
            break
        if p_pno:
            break
    return susi_in, jeong, s_pno, per, p_pno


def main(pdf_path, out_path):
    with pdfplumber.open(pdf_path) as pdf:
        tables = find_tables(pdf)
        if not tables:
            raise SystemExit("모집시기별 모집인원 표를 찾지 못함")
        units, skipped, pages = [], [], []
        for pno, page, t in tables:
            parse_table(pno, page, t, units, skipped)
            pages.append(pno)
        susi_in, jeong, s_pno, per, p_pno = read_summary(pdf)

    used = {k for u in units for k in u["인원"]}
    jlist = [j for j in JEONHYEONG if j["key"] in used]
    memo = [
        f"출처: p{pages[0]}~{pages[-1]} '2028학년도 모집시기별 모집인원' 표(정원내 열만). 정원외(재외국민, 농어촌, 기회균형Ⅱ, "
        "특성화고등을졸업한재직자(특고졸), 13쪽 [정원외] 표시 열)와 공무원·군위탁, 부모 모두 외국인 전형은 넣지 않음",
        "학생부종합 기회균형Ⅰ·성인학습자는 표의 '정원내' 열 → 수록(성인학습자는 전형기간 자율화 전형이나 표의 수시 정원내 열에 있음)",
        "표에 행별 합계 칸 없음 → 계=null(합계칸없음). 8~10쪽 입학정원 표는 모집인원과 다른 숫자(이월 등)라 계로 쓰지 않음",
        "정시 '일반전형'은 표·39쪽에서 수능/실기 구분 없이 가·나·다군 '일반전형' 하나로 적혀 있어 유형=수능으로 둠. "
        "단 조형대학·미술학부·음악학부·체육대학 등 예체능 모집단위는 41~49쪽에 실기고사를 함께 반영한다고 되어 있음",
        "★ 표시 칸(수시 미충원 시에만 이월 인원 모집: 13쪽 각주)은 숫자가 없어 0으로 봄. ★ 기호는 텍스트층에 없어 따로 기록하지 못함",
        "'-' 칸(국제통상금융학과 논술)은 0",
        "계열: 표의 계열 칸 그대로(인문/자연/예체능/전공자율)",
        "단과대학: 표의 대학 칸 글자를 이어 씀",
        "음악학부 성악전공(남자/여자), 공연예술학부 무용전공(발레/한국무용/현대무용)은 표에서 행이 나뉘어 있어 '이름(세부)'로 따로 적음",
    ]
    if DOT_GAPS:
        memo.append("이름 속 가운뎃점(·)은 텍스트층에 글자가 없고 자리만 비어 있어(8~9쪽 입학정원 표에는 '·' 글자 있음) 그 자리에 '·'을 넣음: "
                    + ", ".join(dict.fromkeys(DOT_GAPS)))
    if skipped:
        memo.append("제외 행(정원내 인원 없음): " + "; ".join(skipped))
    s_me = sum(u["인원"].get(k, 0) for u in units for k in SUSI_KEYS)
    j_me = sum(u["인원"].get(k, 0) for u in units for k in JEONGSI_KEYS)
    if susi_in is not None:
        memo.append(f"총계 대조: 수시 {susi_in}={s_me}, 정시 {jeong}={j_me}, 전체 {susi_in + jeong}={s_me + j_me} "
                    f"(p{s_pno} 모집 요약 '수시 정원내'·'정시모집')")
    else:
        memo.append("총계 대조: 모집 요약 쪽에서 총계를 읽지 못함")
    if per:
        def col(k):
            return sum(u["인원"].get(k, 0) for u in units)
        checks = []
        kyo = per.get("교과우수자", [])
        if len(kyo) == 2:
            checks.append(("교과우수자Ⅰ", kyo[0], col("수시_교과_교과우수자1")))
            checks.append(("교과우수자Ⅱ", kyo[1], col("수시_교과_교과우수자2")))
        for name, key in (("국민프런티어", "수시_종합_국민프런티어"), ("국제인재", "수시_종합_국제인재"),
                          ("알고리즘우수자", "수시_종합_알고리즘우수자"), ("기회균형", "수시_종합_기회균형1"),
                          ("성인학습자", "수시_종합_성인학습자"), ("논술", "수시_논술"),
                          ("특기자", "수시_실기_특기자"), ("실기우수자", "수시_실기_실기우수자")):
            checks.append((name, per.get(name), col(key)))
        bad = [f"{n}({a} vs {b})" for n, a, b in checks if a != b]
        memo.append(f"수시 전형별 대조(p{p_pno} 수시모집 주요사항 모집인원; 교과우수자 Ⅰ/Ⅱ는 표기 글자가 텍스트층에 없어 행 순서로 대응): "
                    + ("모두 일치" if not bad else "불일치 " + ", ".join(bad))
                    + " — " + ", ".join(f"{n} {a}" for n, a, _ in checks))
    per_gun = {g: sum(u["인원"].get(f"정시_수능_일반_{g}", 0) for u in units) for g in "가나다"}
    memo.append(f"정시 군별 합: 가 {per_gun['가']}, 나 {per_gun['나']}, 다 {per_gun['다']}")

    out = {"id": UNIV_ID, "이름": UNIV_NAME, "출처쪽": pages, "전형": jlist, "모집단위": units, "메모": memo}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{UNIV_ID}: {len(units)}행 → {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: kookmin.py <pdf> <out.json>")
    main(sys.argv[1], sys.argv[2])
