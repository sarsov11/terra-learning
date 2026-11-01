"""대학별 파서를 돌려 ipsi/data/2028.json 하나로 묶는다.

python tools/ipsi/build.py <PDF폴더>
- 파서가 실패하거나 빈 결과를 내면 이전 정리본(norm/<id>.json)을 그대로 두고 상태에 적는다.
- 숫자는 파서가 낸 그대로 쓴다. 여기서는 합치기·집계만 한다.
"""
import datetime, json, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PDF = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "_pdf"
NORM = HERE / "norm"
OUT = ROOT / "ipsi" / "data" / "2028.json"
NORM.mkdir(exist_ok=True)
OUT.parent.mkdir(parents=True, exist_ok=True)

src = json.loads((HERE / "sources.json").read_text(encoding="utf-8"))
mf_path = HERE / "raw" / "manifest.json"
manifest = json.loads(mf_path.read_text(encoding="utf-8")) if mf_path.exists() else {}
KST = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(KST).isoformat(timespec="seconds")
유형들 = {"학생부교과", "학생부종합", "논술", "실기/실적", "수능", "기타"}


def valid(d):
    try:
        keys = {t["key"] for t in d["전형"]}
        assert all(t["유형"] in 유형들 and t["시기"] in ("수시", "정시") for t in d["전형"])
        assert len(d["모집단위"]) > 0
        for r in d["모집단위"]:
            assert r["모집단위"] and isinstance(r["인원"], dict)
            assert set(r["인원"]) <= keys
            assert all(isinstance(v, int) and v >= 0 for v in r["인원"].values())
        return True
    except Exception:
        return False


대학, 행 = [], []
for u in src["대학"]:
    uid = u["id"]
    parser, pdf, norm = HERE / "parsers" / f"{uid}.py", PDF / f"{uid}.pdf", NORM / f"{uid}.json"
    상태 = "파서 없음"
    if parser.exists() and pdf.exists():
        tmp = NORM / f"{uid}.new.json"
        try:
            subprocess.run([sys.executable, "-I", str(parser), str(pdf), str(tmp)], check=True, timeout=600,
                           capture_output=True)
            d = json.loads(tmp.read_text(encoding="utf-8"))
            if valid(d):
                tmp.replace(norm)
                상태 = "정리됨"
            else:
                상태 = "파서 결과 이상 — 이전 정리본 유지"
        except Exception as e:  # noqa
            상태 = f"파서 실패({type(e).__name__}) — 이전 정리본 유지"
        finally:
            if tmp.exists():
                tmp.unlink()
    elif norm.exists():
        상태 = "정리됨(이전 실행분)"

    m = manifest.get(uid, {})
    info = {"id": uid, "이름": u["이름"], "묶음": u["묶음"], "PDF": m.get("주소"), "받은때": m.get("받은때"),
            "확인한때": m.get("확인한때"), "상태": 상태}
    if norm.exists():
        d = json.loads(norm.read_text(encoding="utf-8"))
        if not valid(d):
            info["상태"] = "정리본 형식 오류 — 표시 안 함"
            대학.append(info)
            continue
        ok = sum(1 for r in d["모집단위"] if r.get("검증") == "합계일치")
        bad = sum(1 for r in d["모집단위"] if r.get("검증") == "합계불일치")
        info.update({"출처쪽": d.get("출처쪽", []), "전형": d["전형"], "메모": d.get("메모", []),
                     "행수": len(d["모집단위"]), "합계일치": ok, "합계불일치": bad})
        for r in d["모집단위"]:
            행.append({"u": uid, "단과": r.get("단과대학"), "단위": r["모집단위"], "계열": r.get("계열"),
                       "인원": r["인원"], "계": r.get("계"), "쪽": r.get("쪽"), "검증": r.get("검증")})
    대학.append(info)

OUT.write_text(json.dumps({"학년도": 2028, "만든때": now, "대학": 대학, "모집단위": 행},
                          ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"{len(대학)}개 대학, {len(행)}개 모집단위 → {OUT.relative_to(ROOT)}")
for i in 대학:
    print(" ", i["이름"], i["상태"], i.get("행수", 0), "행", "불일치", i.get("합계불일치", 0))
