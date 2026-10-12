/* 테라러닝 베타 기록 — 앱에 한 줄로 붙인다
 *   <script src="https://sarsov11.github.io/terra-learning/beta/beta.js" data-app="gisa" defer></script>
 * 하는 일: 초대 코드 연결 · 일별 활동(방문·푼 문항·정답·학습 분) · 진단 점수 1회 · 의견 단추 · 시험 뒤 설문 · 합격 인증.
 * 정답·오답은 짜잔(zzajan.js)이 내는 zz:sfx 신호에서 읽는다(앱 코드 수정 없음). 짜잔이 없는 앱은 TerraBeta.answer(true|false).
 * 진단: 연결 뒤 처음 푼 10문항 정답률. 앱에 진짜 진단이 있으면 TerraBeta.diag(맞힌 수, 전체) 가 우선.
 * 연결 안 한 사람에게는 아무것도 안 뜨고 아무것도 안 보낸다. 네트워크가 끊겨도 쌓아 두었다 다음에 보낸다.
 * 연결 방법: 앱 주소 뒤에 ?beta=JC-AB3CD (신청 페이지가 이 주소를 준다) 또는 ?beta 로 열어 코드 입력. */
(function () {
  "use strict";
  var W = window, D = document;
  if (W.TerraBeta) return;
  var me = D.currentScript;
  var BAKED = "https://terra-beta.teralearning.workers.dev";   /* 허브 사이트 사본은 베타배포.py 가 서버 주소로 바꿔 쓴다. Worker 사본은 자기 주소를 쓴다 */
  var API = (me && me.getAttribute("data-api")) || (BAKED.indexOf("http") === 0 ? BAKED : (me && me.src ? me.src.replace(/\/[^\/]*$/, "") : ""));
  var APP = ((me && me.getAttribute("data-app")) || location.pathname.split("/")[1] || location.hostname).slice(0, 40);
  var KEY = "tbeta1", DIAG_N = 10;

  function load() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } }
  var S = load();
  function save() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { } }
  function day(t) { var d = new Date(t || Date.now()); return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2); }
  function rid(n) { var a = "abcdefghijkmnpqrstuvwxyz23456789", s = "", b = new Uint8Array(n); (W.crypto || W.msCrypto).getRandomValues(b); for (var i = 0; i < n; i++) s += a[b[i] % a.length]; return s; }
  function joined() { return !!(S.tok && S.uid); }
  function today() {
    var d = day(); S.days = S.days || {}; var t = S.days[d] = S.days[d] || {};
    return t[APP] = t[APP] || { visits: 0, solved: 0, correct: 0, minutes: 0 };
  }
  function visit() {   /* 기사·공시처럼 화면마다 페이지가 바뀌는 앱이 많아 30분 안의 재진입은 한 번으로 센다 */
    var now = Date.now(), last = S.lastSeen || 0;
    if (now - last > 30 * 60000 || day(last) !== day(now)) today().visits++;
    S.lastSeen = now; dirty(); save();
  }
  function dirty() { S.dirty = S.dirty || {}; S.dirty[day()] = 1; }
  function screen() { return (W.TerraBeta && W.TerraBeta.screen) || ((D.title || "").slice(0, 40) + " " + (location.hash || location.pathname.split("/").pop() || "")).trim().slice(0, 80); }

  /* ── 서버 ── */
  function post(path, data, cb) {
    if (!API) return cb && cb(null);
    var done = false, t = setTimeout(function () { if (!done) { done = true; cb && cb(null); } }, 12000);
    try {
      fetch(API + path, { method: "POST", headers: { "content-type": "text/plain" }, body: JSON.stringify(data), keepalive: path === "/api/sync" })
        .then(function (r) { return r.json(); })
        .then(function (j) { if (!done) { done = true; clearTimeout(t); cb && cb(j); } })
        ["catch"](function () { if (!done) { done = true; clearTimeout(t); cb && cb(null); } });
    } catch (e) { done = true; clearTimeout(t); cb && cb(null); }
  }
  function payload() {
    var act = [], ds = Object.keys(S.dirty || {});
    ds.forEach(function (d) { var t = (S.days || {})[d] || {}; Object.keys(t).forEach(function (a) { var x = t[a]; act.push({ day: d, app: a, visits: x.visits, solved: x.solved, correct: x.correct, minutes: Math.round(x.minutes * 100) / 100 }); }); });
    var p = { uid: S.uid, tok: S.tok, act: act, ev: (S.q || []).slice(0, 50) };
    if (S.diag && !S.diagSent) p.diag = S.diag;
    return { p: p, days: ds, evn: p.ev.length };
  }
  var syncing = false;
  function sync() {
    if (!joined() || syncing) return;
    var x = payload(); if (!x.p.act.length && !x.evn && !x.p.diag) return;
    syncing = true;
    post("/api/sync", x.p, function (j) {
      syncing = false;
      if (!j) return;                       /* 끊김: 그대로 두고 다음에 */
      if (j.err === "연결 안 된 기기") { S.tok = null; save(); return; }
      if (!j.ok) return;
      var cur = day(); x.days.forEach(function (d) { if (d !== cur) delete S.dirty[d]; });
      if (x.days.indexOf(cur) >= 0) S.sentAt = Date.now();
      S.q = (S.q || []).slice(x.evn);
      if (x.p.diag || j.diag) S.diagSent = true;
      prune(); save();
    });
  }
  function beacon() {
    if (!joined() || !navigator.sendBeacon) return;
    var x = payload(); if (!x.p.act.length && !x.evn) return;
    try { navigator.sendBeacon(API + "/api/sync", new Blob([JSON.stringify(x.p)], { type: "text/plain" })); } catch (e) { }
  }
  function prune() { var ks = Object.keys(S.days || {}).sort(); while (ks.length > 45) { var k = ks.shift(); if (!(S.dirty || {})[k]) delete S.days[k]; } }
  /* 문항 오류 신고: 가입 전에도 받는다(기기 익명 id). 실패하면 S.rq 에 쌓았다 다음에 보낸다 */
  var reporting = false;
  function flushReports() {
    if (reporting || !(S.rq && S.rq.length)) return;
    reporting = true; var r = S.rq[0];
    post("/api/report", { uid: S.uid, tok: S.tok || null, eid: r.eid, ctx: r.ctx, reason: r.reason, text: r.text }, function (j) {
      reporting = false;
      if (j && (j.ok || j.err === "사유를 고르세요")) { S.rq.shift(); save(); flushReports(); }
    });
  }
  function queue(kind, body) { S.q = S.q || []; S.q.push({ eid: rid(16), kind: kind, screen: screen(), body: body, at: new Date().toISOString() }); save(); sync(); }

  /* ── 연결 ── */
  function join(code, cb) {
    code = String(code || "").toUpperCase().replace(/\s/g, "");
    if (S.code && S.code !== code) { S = {}; }
    S.uid = S.uid || rid(20);
    post("/api/join", { code: code, uid: S.uid, app: APP }, function (j) {
      if (j && j.ok) {
        S.code = code; S.tok = j.tok; S.track = j.track; S.name = j.name; S.exam = j.exam; S.announce = j.announce; S.levels = j.levels;
        if (j.diag) S.diagSent = true;
        S.joinedAt = S.joinedAt || Date.now(); S.ans = S.ans || [];
        visit(); pill(); sync();
      }
      cb && cb(j);
    });
  }

  /* ── 활동 ── */
  var lastAns = 0, manual = false, lastAct = Date.now(), hiddenAt = 0;
  function answer(ok, fromApp) {
    if (!joined()) return;
    if (fromApp) manual = true; else if (manual) return;
    var now = Date.now(); if (now - lastAns < 250) return; lastAns = now;
    var t = today(); t.solved++; if (ok) t.correct++;
    if (!S.diag && S.ans) { S.ans.push(ok ? 1 : 0); if (S.ans.length >= DIAG_N) { S.diag = { score: S.ans.reduce(function (a, b) { return a + b; }, 0), total: S.ans.length, auto: 1 }; S.ans = null; } }
    lastAct = now; dirty(); save();
  }
  W.addEventListener("zz:sfx", function (e) {
    var d = e.detail || {};
    if (d.name === "ok" && !d.delay) answer(true);
    else if (d.name === "no" && !d.delay) answer(false);
  });
  ["pointerdown", "keydown", "scroll", "touchstart"].forEach(function (k) { W.addEventListener(k, function () { lastAct = Date.now(); }, { passive: true, capture: true }); });
  setInterval(function () {
    if (!joined() || D.visibilityState !== "visible" || Date.now() - lastAct > 90000) return;
    today().minutes += 0.25; S.lastSeen = Date.now(); dirty(); save();
  }, 15000);
  setInterval(function () { if (Date.now() - (S.sentAt || 0) > 110000) sync(); flushReports(); }, 30000);
  D.addEventListener("visibilitychange", function () {
    if (D.visibilityState === "hidden") { hiddenAt = Date.now(); save(); beacon(); }
    else if (joined()) visit();
  });
  W.addEventListener("online", function () { sync(); flushReports(); });

  /* ── 화면 ── */
  var host, root, panelEl;
  var CSS = ":host{all:initial}*{box-sizing:border-box;font-family:Pretendard,'Apple SD Gothic Neo','Malgun Gothic',system-ui,sans-serif}" +
    ".pill{position:fixed;left:0;bottom:88px;z-index:2147483000;background:#1d2433;color:#fff;border:0;border-radius:0 10px 10px 0;padding:7px 9px 7px 7px;font-size:12px;font-weight:700;opacity:.82;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.25)}" +
    ".pill:hover{opacity:1}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#f5c518;margin-right:5px;vertical-align:1px}" +
    ".wrap{position:fixed;inset:0;z-index:2147483001;background:rgba(10,14,22,.55);display:flex;align-items:flex-end;justify-content:center}" +
    ".box{background:#fff;color:#1b1f27;width:min(440px,100%);max-height:88vh;overflow:auto;border-radius:16px 16px 0 0;padding:20px 18px 22px}" +
    "@media(min-width:600px){.wrap{align-items:center}.box{border-radius:16px}}" +
    "h3{margin:0 0 4px;font-size:17px}p{margin:6px 0;font-size:13.5px;line-height:1.55;color:#4a5160}" +
    "label{display:block;font-size:13px;font-weight:700;margin:14px 0 6px}" +
    "input,textarea,select{width:100%;font-size:15px;padding:10px;border:1px solid #cfd5df;border-radius:10px;background:#fff;color:#1b1f27}textarea{min-height:90px;resize:vertical}" +
    ".opts{display:flex;flex-wrap:wrap;gap:6px}.opt{border:1px solid #cfd5df;background:#fff;color:#1b1f27;border-radius:999px;padding:8px 12px;font-size:13.5px;cursor:pointer}.opt.on{background:#1d2433;color:#fff;border-color:#1d2433}" +
    ".row{display:flex;gap:8px;margin-top:16px}.btn{flex:1;border:0;border-radius:10px;padding:12px;font-size:15px;font-weight:700;cursor:pointer;background:#e9edf3;color:#1b1f27}.btn.go{background:#1d2433;color:#fff}" +
    ".list .btn{display:block;width:100%;text-align:left;margin-top:8px;font-weight:600}.muted{font-size:12px;color:#7a8291}.err{color:#c0392b;font-size:13px;min-height:18px;margin-top:8px}" +
    ".stat{display:flex;gap:10px;margin:10px 0}.stat div{flex:1;background:#f3f5f8;border-radius:10px;padding:10px;text-align:center;font-size:12px;color:#5b6372}.stat b{display:block;font-size:19px;color:#1b1f27}" +
    "@media(prefers-color-scheme:dark){.box{background:#1b2130;color:#e8ecf3}p{color:#aab3c2}input,textarea,select,.opt{background:#121722;color:#e8ecf3;border-color:#394256}.btn{background:#2a3244;color:#e8ecf3}.btn.go,.opt.on{background:#f5c518;color:#151a24;border-color:#f5c518}.stat div{background:#232a3a;color:#aab3c2}.stat b{color:#fff}}";
  function mount() {
    if (root) return root;
    host = D.createElement("div"); host.id = "terra-beta"; host.setAttribute("data-zz-skip", "");
    (D.body || D.documentElement).appendChild(host);
    root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;
    var st = D.createElement("style"); st.textContent = CSS; root.appendChild(st);
    return root;
  }
  function el(tag, cls, txt) { var e = D.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
  function pill() {
    if (!joined()) return; mount();
    if (root.querySelector(".pill")) return;
    var b = el("button", "pill"); b.innerHTML = '<span class="dot"></span>베타'; b.onclick = menu; root.appendChild(b);
  }
  function close() { if (panelEl) { panelEl.remove(); panelEl = null; } }
  function sheet(build) {
    mount(); close();
    var w = el("div", "wrap"), bx = el("div", "box"); w.appendChild(bx);
    w.addEventListener("click", function (e) { if (e.target === w) close(); });
    build(bx); root.appendChild(w); panelEl = w;
    var f = bx.querySelector("input,textarea"); if (f && !("ontouchstart" in W)) f.focus();
    return bx;
  }
  function buttons(bx, okText, onOk, cancelText) {
    var err = el("div", "err"), r = el("div", "row"), c = el("button", "btn", cancelText || "닫기"), o = el("button", "btn go", okText);
    c.onclick = close; o.onclick = function () { onOk(err, o); }; r.appendChild(c); r.appendChild(o); bx.appendChild(err); bx.appendChild(r);
  }
  function choice(bx, label, opts, multiKey, store) {
    bx.appendChild(el("label", null, label)); var g = el("div", "opts");
    opts.forEach(function (o) { var b = el("button", "opt", o); b.type = "button"; b.onclick = function () { [].forEach.call(g.children, function (x) { x.classList.remove("on"); }); b.classList.add("on"); store[multiKey] = o; }; g.appendChild(b); });
    bx.appendChild(g);
  }
  function after(d, hour) { if (!d) return false; var t = day(); return t > d || (t === d && new Date().getHours() >= (hour || 0)); }

  function codeSheet(pre) {
    sheet(function (bx) {
      bx.appendChild(el("h3", null, "베타 초대 코드"));
      bx.appendChild(el("p", null, "신청하고 받은 코드를 넣으면 이 기기의 풀이 기록이 베타 집계에 들어갑니다. 폰과 PC 에 같은 코드를 넣어도 됩니다."));
      var i = el("input"); i.placeholder = "예: JC-AB3CD"; i.value = pre || ""; i.autocapitalize = "characters"; bx.appendChild(i);
      buttons(bx, "연결", function (err, o) {
        o.disabled = true; err.textContent = "";
        join(i.value, function (j) {
          o.disabled = false;
          if (j && j.ok) { close(); toast(j.name + " 베타에 연결됐습니다"); }
          else err.textContent = j ? j.err : "인터넷 연결을 확인해 주세요";
        });
      });
    });
  }
  function toast(t) {
    mount(); var x = el("div"); x.textContent = t;
    x.style.cssText = "position:fixed;left:50%;top:18px;transform:translateX(-50%);z-index:2147483002;background:#1d2433;color:#fff;padding:10px 16px;border-radius:999px;font:600 14px system-ui,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.3)";
    root.appendChild(x); setTimeout(function () { x.remove(); }, 2600);
  }
  function menu() {
    sheet(function (bx) {
      bx.appendChild(el("h3", null, (S.name || "베타") + " 베타"));
      var t = today(), tot = 0; Object.keys(S.days || {}).forEach(function (d) { var a = S.days[d]; Object.keys(a).forEach(function (k) { tot += a[k].solved; }); });
      var st = el("div", "stat");
      st.innerHTML = "<div><b>" + t.solved + "</b>오늘 푼 문항</div><div><b>" + (t.solved ? Math.round(100 * t.correct / t.solved) : 0) + "%</b>오늘 정답률</div><div><b>" + tot + "</b>최근 누적</div>";
      bx.appendChild(st);
      var l = el("div", "list");
      var add = function (txt, fn) { var b = el("button", "btn", txt); b.onclick = fn; l.appendChild(b); };
      add("의견 보내기 · 틀린 문제 신고", feedback);
      if (after(S.exam, 13)) add(S.done && S.done.survey ? "시험 후기 다시 보내기" : "시험 후기 설문 (5문항)", survey);
      if (after(S.announce, 9)) add(S.done && S.done.pass ? "합격 인증 고치기" : "합격 인증", pass);
      add("참여 그만두기 · 내 기록 지우기", quit);
      bx.appendChild(l);
      bx.appendChild(el("p", "muted", "코드 " + (S.code || "") + " · 기록은 하루 단위 숫자(방문·문항·정답·분)만 보냅니다." + (S.q && S.q.length ? " 보내지 못한 글 " + S.q.length + "건은 연결되면 보냅니다." : "")));
      var r = el("div", "row"), c = el("button", "btn", "닫기"); c.onclick = close; r.appendChild(c); bx.appendChild(r);
    });
  }
  function feedback() {
    var scr = screen();
    sheet(function (bx) {
      bx.appendChild(el("h3", null, "의견 보내기"));
      bx.appendChild(el("p", null, "불편한 점, 틀린 정답, 있었으면 하는 기능을 적어 주세요. 지금 화면 이름(" + scr + ")이 같이 갑니다."));
      var tx = el("textarea"); tx.maxLength = 1500; bx.appendChild(tx);
      buttons(bx, "보내기", function (err) {
        if (tx.value.trim().length < 2) { err.textContent = "내용을 적어 주세요"; return; }
        queue("feedback", { text: tx.value.trim() }); close(); toast("받았습니다. 고마워요");
      });
    });
  }
  var REASONS = ["정답이 틀림", "문제·보기 오타", "해설이 틀림", "그림·표가 안 보임", "법령 개정 반영 안 됨", "기타"];
  function reportSheet(ctx) {
    ctx = ctx || {}; var a = {};
    var info = [ctx.과목, ctx.유형, ctx.id].filter(Boolean).join(" · ");
    sheet(function (bx) {
      bx.appendChild(el("h3", null, "문항 오류 신고"));
      if (info) bx.appendChild(el("p", "muted", info));
      choice(bx, "무엇이 문제인가요", REASONS, "reason", a);
      bx.appendChild(el("label", null, "한 줄 설명 (선택)")); var tx = el("input"); tx.maxLength = 500; tx.placeholder = "예: 정답이 ③ 이어야 합니다"; bx.appendChild(tx);
      buttons(bx, "신고", function (err) {
        if (!a.reason) { err.textContent = "사유를 골라 주세요"; return; }
        S.uid = S.uid || rid(20); S.rq = S.rq || [];
        S.rq.push({ eid: rid(16), ctx: ctx, reason: a.reason, text: tx.value.trim() }); save(); flushReports();
        close(); toast("신고 받았습니다. 확인 후 고칩니다");
      });
    });
  }
  function survey() {
    var a = {};
    sheet(function (bx) {
      bx.appendChild(el("h3", null, "시험 후기 (5문항)"));
      bx.appendChild(el("p", null, "1분이면 끝납니다. 다음 회차 앱을 고치는 데 씁니다."));
      choice(bx, "1. 결과 예상", ["붙었을 것 같다", "반반", "떨어졌을 것 같다", "시험 안 봄"], "expect", a);
      choice(bx, "2. 이 앱이 시험 준비에 얼마나 도움이 됐나요", ["1 전혀", "2", "3 보통", "4", "5 아주 많이"], "help", a);
      bx.appendChild(el("label", null, "3. 가장 도움이 된 것")); var b3 = el("input"); b3.maxLength = 300; bx.appendChild(b3);
      choice(bx, "4. 돈을 내고도 쓰겠다? 다음 시험 때 유료라면", ["안 쓴다", "월 5천 원까지", "월 1만 원까지", "월 2만 원 이상도 낸다"], "pay", a);
      bx.appendChild(el("label", null, "5. 고쳤으면 하는 것")); var b5 = el("textarea"); b5.maxLength = 1000; bx.appendChild(b5);
      buttons(bx, "보내기", function (err) {
        if (!a.expect || !a.help || !a.pay) { err.textContent = "1·2·4번은 골라 주세요"; return; }
        a.help = a.help.charAt(0); a.best = b3.value.trim(); a.worst = b5.value.trim();
        queue("survey", a); S.done = S.done || {}; S.done.survey = 1; save(); close(); toast("후기 고마워요");
      });
    });
  }
  function pass() {
    var a = {}, lv = S.levels && S.levels.length ? S.levels : ["실기"];
    sheet(function (bx) {
      bx.appendChild(el("h3", null, "합격 인증"));
      bx.appendChild(el("p", null, "결과와 상관없이 알려 주세요. 불합격 응답도 앱이 실제로 도움이 됐는지 가리는 데 똑같이 중요합니다."));
      if (lv.length > 1) choice(bx, "응시한 시험", lv, "level", a); else a.level = lv[0];
      choice(bx, "결과", ["합격", "불합격", "시험 안 봄"], "result", a);
      bx.appendChild(el("label", null, "점수 (선택, 100점 만점 기준)")); var sc = el("input"); sc.type = "number"; sc.min = 0; sc.max = 100; sc.inputMode = "decimal"; bx.appendChild(sc);
      buttons(bx, "보내기", function (err) {
        if (!a.level || !a.result) { err.textContent = "시험과 결과를 골라 주세요"; return; }
        if (sc.value !== "") { var n = +sc.value; if (!(n >= 0 && n <= 100)) { err.textContent = "점수는 0~100"; return; } a.score = n; }
        queue("pass", a); S.done = S.done || {}; S.done.pass = 1; save(); close(); toast(a.result === "합격" ? "축하합니다!" : "알려 줘서 고마워요");
      });
    });
  }
  function quit() {
    sheet(function (bx) {
      bx.appendChild(el("h3", null, "참여 그만두기"));
      bx.appendChild(el("p", null, "서버에 있는 내 신청 정보와 풀이 기록을 모두 지웁니다. 되돌릴 수 없습니다. 앱은 그대로 쓸 수 있습니다."));
      buttons(bx, "기록 지우기", function (err, o) {
        o.disabled = true;
        post("/api/leave", { uid: S.uid, tok: S.tok }, function (j) {
          o.disabled = false;
          if (j && j.ok) { S = {}; save(); try { localStorage.removeItem(KEY); } catch (e) { } close(); if (root) { var p = root.querySelector(".pill"); if (p) p.remove(); } toast("지웠습니다"); }
          else err.textContent = j ? j.err : "인터넷 연결이 필요합니다";
        });
      });
    });
  }
  function nudge() {   /* 시험 뒤 설문·발표 뒤 합격 인증을 하루 한 번, 세 번까지 띄운다 */
    if (!joined() || panelEl) return;
    S.nag = S.nag || {}; var t = day(), done = S.done || {};
    var k = after(S.announce, 9) && !done.pass ? "pass" : after(S.exam, 13) && !done.survey ? "survey" : null;
    if (!k) return; var n = S.nag[k] || { n: 0, d: "" };
    if (n.d === t || n.n >= 3) return;
    S.nag[k] = { n: n.n + 1, d: t }; save();
    (k === "pass" ? pass : survey)();
  }

  /* ── 시작 ── */
  function start() {
    var m = location.search.match(/[?&]beta(?:=([^&#]*))?/) || location.hash.match(/[#&]beta(?:=([^&]*))?/);
    if (m) {
      try { var u = new URL(location.href); u.searchParams.delete("beta"); if (/^#beta/.test(u.hash)) u.hash = ""; history.replaceState(history.state, "", u.toString()); } catch (e) { }
      var code = decodeURIComponent(m[1] || "");
      if (code && code !== S.code) join(code, function (j) { if (j && j.ok) toast(j.name + " 베타에 연결됐습니다"); else codeSheet(code); });
      else if (!joined()) codeSheet(code);
    }
    if (joined()) { visit(); pill(); setTimeout(sync, 3000); setTimeout(nudge, 8000); }
    slots(); setTimeout(flushReports, 4000);
  }

  /* 앱이 마련한 자리(<div class="beta-slot" data-beta="home|result|settings">)에 작은 줄을 그린다 — 중개사 사이트틀이 이 규약을 쓴다 */
  function mountSlot(slot, ctx) {
    var name = (ctx && ctx.slot) || slot.getAttribute("data-beta");
    slot.setAttribute("data-on", "1"); slot.textContent = "";
    var a = D.createElement("button"); a.type = "button";
    a.style.cssText = "display:block;width:100%;margin:12px 0;padding:11px 14px;border:1px dashed currentColor;border-radius:12px;background:transparent;color:inherit;font:inherit;font-size:14px;opacity:.8;text-align:left;cursor:pointer";
    if (joined()) {
      var t = today();
      a.textContent = name === "result" ? "베타 · 이 세트에 대한 의견 보내기" : "베타 · 오늘 " + t.solved + "문항 · 의견 · 후기";
      a.onclick = name === "result" ? feedback : menu;
    } else if (name === "settings") { a.textContent = "베타 초대 코드 넣기"; a.onclick = function () { codeSheet(""); }; }
    else return;
    slot.appendChild(a);
  }
  function slots() {
    [].forEach.call(D.querySelectorAll(".beta-slot[data-beta]:not([data-on])"), function (s) { try { mountSlot(s); } catch (e) { } });
  }
  if (D.readyState === "loading") D.addEventListener("DOMContentLoaded", start); else start();

  W.TerraBeta = {
    screen: null,
    answer: function (ok) { answer(!!ok, true); },
    diag: function (score, total) { if (!joined() || S.diagSent || !(total > 0)) return; S.diag = { score: +score, total: +total }; S.ans = null; save(); sync(); },
    open: function () { joined() ? menu() : codeSheet(""); },
    /* 문항 오류 신고: TerraBeta.report({app, 종목, id, 과목, 유형, 화면}) — 문맥이 채워진 신고 시트가 뜬다. 가입 전에도 된다 */
    report: function (ctx) { ctx = ctx || {}; ctx.app = ctx.app || APP; ctx.화면 = ctx.화면 || screen(); reportSheet(ctx); },
    /* 지표용 이벤트: TerraBeta.event("set_done", {종류, 테마, 맞, 총}) · event("rec_follow", {추천테마}). 베타 참가자만 쌓인다 */
    event: function (name, data) { if (!joined() || !name) return; S.q = S.q || []; if (S.q.length > 400) return; S.q.push({ eid: rid(16), kind: "ev", screen: screen(), body: { name: String(name).slice(0, 40), data: data || {} }, at: new Date().toISOString() }); save(); },
    joined: joined,
    _state: function () { return S; }, _sync: sync,
  };
  /* 중개사 사이트틀 규약(window.TERRA_BETA.mount/track) */
  W.TERRA_BETA = W.TERRA_BETA || {
    mount: function (el, ctx) { try { mountSlot(el, ctx); } catch (e) { } },
    track: function (name, d) { if (name === "answer" && d && "ok" in d) answer(!!d.ok, true); else W.TerraBeta.event(name, d); },
  };
})();
