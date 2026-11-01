"""대학별 2028 시행계획 PDF를 받아 '모집단위·전형별 모집인원' 표를 날것 그대로 뽑는다.

GitHub Actions에서 돈다(이 저장소의 .github/workflows/ipsi.yml).
- PDF 자체는 저장소에 올리지 않는다. 받은 주소·크기·sha256만 manifest.json에 남긴다.
- 표는 pdfplumber 선(線) 기준으로 뽑고, 쪽 번호와 함께 raw/<id>.json에 그대로 남긴다.
  숫자를 손대지 않는다. 정리·검증은 build.py가 한다.
"""
import datetime, hashlib, json, pathlib, re, sys, urllib.parse

import pdfplumber
import requests

HERE = pathlib.Path(__file__).resolve().parent
RAW = HERE / "raw"
PDF = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "_pdf"
RAW.mkdir(exist_ok=True)
PDF.mkdir(parents=True, exist_ok=True)

src = json.loads((HERE / "sources.json").read_text(encoding="utf-8"))
mf_path = RAW / "manifest.json"
manifest = json.loads(mf_path.read_text(encoding="utf-8")) if mf_path.exists() else {}
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds")
UA = {"User-Agent": "Mozilla/5.0 (teralearning ipsi updater)"}

NUM = re.compile(r"^\(?\d{1,4}\)?$|^\d{1,3}(,\d{3})+$|^-$")


def fetch(u):
    tried = []
    for d in u["후보"]:
        for tpl in src["주소틀"]:
            url = tpl.replace("{d}", urllib.parse.quote(d))
            try:
                r = requests.get(url, headers=UA, timeout=60)
            except Exception as e:  # noqa
                tried.append([url, "error " + type(e).__name__])
                continue
            ok = r.status_code == 200 and r.content[:5] == b"%PDF-"
            tried.append([url, r.status_code])
            if ok:
                return url, r.content, tried
    return None, None, tried


def numeric_rows(tbl):
    n = 0
    for row in tbl:
        cells = [(c or "").strip() for c in row]
        if sum(1 for c in cells if NUM.match(c.replace(" ", ""))) >= 3:
            n += 1
    return n


def section_pages(pdf):
    """'모집인원' 표가 몰린 쪽을 찾는다: 앞 60쪽 안에서 숫자 행이 많은 표가 있는 쪽."""
    out = []
    for i, page in enumerate(pdf.pages[:60]):
        text = page.extract_text() or ""
        if "모집" not in text:
            continue
        tables = page.extract_tables()
        score = sum(numeric_rows(t) for t in tables)
        if score >= 5 and ("모집단위" in text or "학과" in text or "모집인원" in text):
            out.append((i, text, tables, score))
    return out


report = {}
for u in src["대학"]:
    url, data, tried = fetch(u)
    if not data:
        report[u["id"]] = {"상태": "받기 실패", "시도": tried}
        print(u["이름"], "받기 실패")
        continue
    sha = hashlib.sha256(data).hexdigest()
    (PDF / f"{u['id']}.pdf").write_bytes(data)
    prev = manifest.get(u["id"], {})
    changed = prev.get("sha256") != sha
    with pdfplumber.open(PDF / f"{u['id']}.pdf") as pdf:
        pages = section_pages(pdf)
        npages = len(pdf.pages)
    raw = {
        "id": u["id"], "이름": u["이름"], "주소": url, "sha256": sha,
        "쪽": [{"쪽": i + 1, "점수": s, "글": t, "표": tb} for i, t, tb, s in pages],
    }
    (RAW / f"{u['id']}.json").write_text(json.dumps(raw, ensure_ascii=False, indent=0), encoding="utf-8")
    manifest[u["id"]] = {
        "이름": u["이름"], "주소": url, "sha256": sha, "바이트": len(data), "총쪽수": npages,
        "표쪽": [i + 1 for i, *_ in pages],
        "받은때": now if changed else prev.get("받은때", now),
        "확인한때": now,
    }
    report[u["id"]] = {"상태": "바뀜" if changed else "그대로", "표쪽": manifest[u["id"]]["표쪽"]}
    print(u["이름"], report[u["id"]]["상태"], "표쪽", manifest[u["id"]]["표쪽"])

mf_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
(RAW / "last_run.json").write_text(json.dumps({"때": now, "결과": report}, ensure_ascii=False, indent=1), encoding="utf-8")
