/* 첫 설정(학생 조사) — 테라러닝 공용 (2026-11-05)
 *  대표님: 「서비스에 들어왔는데 학생 조사 없이 바로 과목 설명부터 갈기는 거 싫다. 마이메르시 첫 화면처럼 사용자 세팅 이후 과목 전략」
 *          「KB국민은행 앱처럼 하나 쓰고 나면 그게 위로 밀리면서 가운데서 새로운 걸 묻고, 또 한 칸 위로 밀리면서 계속 가운데서 묻는 방식」
 *
 *  화면: 흰 바탕 + 연회색 판 + 진한 글씨 + 포인트 한 색(1110 밝은 화면으로 바꿈). 질문은 늘 화면 가운데. 답하면 「질문 · 답」 한 줄이 위로 밀려 쌓이고
 *        새 질문이 가운데에 올라온다. 위에 쌓인 답을 누르면 그 질문으로 돌아가 고칠 수 있다. 답할 때마다 손에 짧은 진동.
 *
 *  ZZSETUP.run("ncs", {
 *     이름: "진격의 NCS",
 *     steps: [
 *       { id: "group", k: "기업군", q: "어느 쪽 공기업을 준비하세요?", options: [{ v: "power5", label: "발전 5사", sub: "남동·남부·동서·서부·중부" }, …] },
 *       { id: "org", k: "기관", q: function (a) { return … }, options: function (a) { return […] }, when: function (a) { return a.group !== "etc"; } },
 *       { id: "nick", k: "이름", q: "뭐라고 부를까요?", type: "text", placeholder: "닉네임", optional: true }
 *     ],
 *     done: function (ans) { … }          // ans = { group: "power5", org: "kosep", … } · ans._label = { group: "발전 5사", … }
 *  })
 *  ZZSETUP.get(key) → 저장된 답(없으면 null) · ZZSETUP.reset(key) · ZZSETUP.common(전략데이터) → 공통 질문(경험·시험 시기·하루 시간·목표)
 *  저장: localStorage terra.setup.<key>
 */
(function () {
  "use strict";
  if (window.ZZSETUP) return;
  var D = document, W = window, KEY = "terra.setup.";
  var RM = false; try { RM = W.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) { }
  var POINTS = { sky: "#0E7490", lime: "#4D7C0F", amber: "#B45309", coral: "#E5322D" };
  /* 흰 바탕에서 읽히도록 밝은 포인트색은 어둡게 눌러 준다(밝기 0.28 이하) */
  function deep(c) {
    var m = /^#([0-9a-f]{6})$/i.exec(String(c)); if (!m) return c;
    var n = parseInt(m[1], 16), r = n >> 16 & 255, g = n >> 8 & 255, b = n & 255;
    function L(r, g, b) { return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255; }
    for (var i = 0; i < 20 && L(r, g, b) > 0.28; i++) { r = Math.round(r * .9); g = Math.round(g * .9); b = Math.round(b * .9); }
    return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
  }

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function get(k) { try { var v = JSON.parse(localStorage.getItem(KEY + k) || "null"); return v && v.ans ? v.ans : null; } catch (e) { return null; } }
  function save(k, ans) { try { localStorage.setItem(KEY + k, JSON.stringify({ ans: ans, at: Date.now() })); } catch (e) { } }
  function reset(k) { try { localStorage.removeItem(KEY + k); } catch (e) { } }
  function val(x, a) { return typeof x === "function" ? x(a) : x; }

  /* 진동 — zzstrat.js 와 같은 방식(안드로이드 vibrate, 아이폰은 스위치 체크박스 햅틱) */
  var HAP = null;
  function haptic(ms) {
    if (W.TERRA_HAPTIC) return W.TERRA_HAPTIC(ms);
    if (RM) return;
    try { if (navigator.vibrate) { navigator.vibrate(ms || 14); return; } } catch (e) { }
    try {
      if (!HAP || !HAP.isConnected) {
        HAP = D.createElement("label"); HAP.setAttribute("aria-hidden", "true");
        HAP.style.cssText = "position:fixed;left:-9999px;top:0;width:1px;height:1px;opacity:0;pointer-events:none;overflow:hidden";
        var i = D.createElement("input"); i.type = "checkbox"; i.setAttribute("switch", ""); i.tabIndex = -1; HAP.appendChild(i); D.body.appendChild(HAP);
      }
      HAP.click();
    } catch (e) { }
  }

  var css = [
    ":host{all:initial}",
    "#zsu{--bg:#FFFFFF;--card:#F6F7F9;--line:#E6E8EC;--tx:#111419;--sub:#4B5563;--dim:#5F6670;--ink:#FFFFFF;",
    " position:fixed;inset:0;z-index:2147481800;color:var(--tx);background:#FFFFFF;",
    " font:500 16px/1.6 var(--zf);letter-spacing:-.01em;display:flex;flex-direction:column;-webkit-tap-highlight-color:transparent;animation:uIn .35s ease-out}",
    "@keyframes uIn{0%{opacity:0}100%{opacity:1}}",
    "#zsu *{box-sizing:border-box}",
    "#zsu .tp{display:flex;align-items:center;gap:12px;padding:max(14px,env(safe-area-inset-top)) 20px 0}",
    "#zsu .nm{font:700 13px/1.3 var(--zf);color:var(--sub)}",
    "#zsu .pg{flex:1;height:3px;border-radius:3px;background:#EFF1F4;overflow:hidden}#zsu .pg i{display:block;height:100%;width:0;background:var(--pt);transition:width .4s}",
    "#zsu .stage{flex:1;display:flex;flex-direction:column;min-height:0;padding:0 22px;max-width:560px;width:100%;margin:0 auto}",
    /* 위로 밀려 쌓이는 답. 위쪽은 서서히 사라진다 */
    "#zsu .hist{flex:1 1 0;min-height:0;display:flex;flex-direction:column;justify-content:flex-end;overflow:hidden;padding-bottom:18px;",
    " -webkit-mask-image:linear-gradient(transparent 0,#000 46%);mask-image:linear-gradient(transparent 0,#000 46%)}",
    "#zsu .h{display:flex;align-items:baseline;gap:10px;padding:9px 0;border:0;background:none;color:inherit;font:inherit;text-align:left;cursor:pointer;width:100%;opacity:.8;transition:opacity .2s}",
    "#zsu .h:last-child{opacity:1}#zsu .h:hover{opacity:1}",
    "#zsu .h span{flex:none;font:700 13px/1.3 var(--zf);color:var(--sub);min-width:4.5em}",
    "#zsu .h b{font:800 18px/1.35 var(--zf);color:var(--tx);word-break:keep-all}",
    "#zsu .h i{margin-left:auto;font:700 12px/1 var(--zf);color:var(--dim);font-style:normal;flex:none}",
    /* 가운데 질문 */
    "#zsu .cur{flex:0 0 auto;min-height:54%;display:flex;flex-direction:column;padding-bottom:max(18px,env(safe-area-inset-bottom))}",
    "#zsu .q{margin:0;font:800 clamp(23px,6.2vw,28px)/1.42 var(--zf);letter-spacing:-.03em;word-break:keep-all}",
    "#zsu .q b{color:var(--pt)}",
    "#zsu .qs{margin:8px 0 0;font:600 14px/1.5 var(--zf);color:var(--sub);word-break:keep-all}",
    "#zsu .ops{display:grid;gap:10px;margin-top:20px;overflow-y:auto;max-height:46vh;padding:2px 2px 6px;-webkit-overflow-scrolling:touch}",
    "#zsu .ops.c2{grid-template-columns:1fr 1fr}",
    "#zsu .op{display:block;width:100%;text-align:left;background:var(--card);border:0;border-radius:18px;padding:14px 16px;cursor:pointer;color:var(--tx);font:inherit;box-shadow:0 1px 2px rgba(17,20,25,.05),0 0 0 1px #E6E8EC;transition:box-shadow .15s,background .15s,transform .1s}",
    "#zsu .op:active{transform:scale(.985)}",
    "#zsu .op b{display:block;font:800 16.5px/1.3 var(--zf);word-break:keep-all}#zsu .op small{display:block;font:600 13px/1.45 var(--zf);color:var(--sub);margin-top:3px;word-break:keep-all}",
    "#zsu .op.on{box-shadow:0 0 0 1.5px var(--pt);background:color-mix(in srgb,var(--pt) 9%,#FFFFFF)}",
    "#zsu .op.soon{opacity:.6;cursor:default}#zsu .op.soon small::after{content:' · 준비 중'}",
    "#zsu .tx{display:flex;gap:8px;margin-top:20px}",
    "#zsu .tx input{flex:1;min-width:0;background:#fff;border:0;box-shadow:inset 0 0 0 1.5px #D3D7DD;border-radius:14px;padding:14px 16px;color:var(--tx);font:700 17px/1.2 var(--zf);outline:none}",
    "#zsu .tx input:focus{box-shadow:inset 0 0 0 1.5px var(--pt)}",
    "#zsu .go{background:var(--pt);color:var(--ink);border:0;border-radius:16px;padding:0 20px;font:800 16px/1 var(--zf);cursor:pointer;white-space:nowrap}",
    "#zsu .later{align-self:flex-start;margin-top:14px;background:none;border:0;color:var(--sub);font:700 13.5px/1 var(--zf);padding:8px 0;cursor:pointer}",
    "#zsu .cur.in .q,#zsu .cur.in .qs{animation:qIn .45s cubic-bezier(.2,.8,.2,1) both}",
    "#zsu .cur.in .ops,#zsu .cur.in .tx,#zsu .cur.in .later{animation:qIn .45s .08s cubic-bezier(.2,.8,.2,1) both}",
    "@keyframes qIn{0%{opacity:0;transform:translateY(22px)}100%{opacity:1;transform:none}}",
    "#zsu .fly{position:fixed;z-index:3;pointer-events:none;margin:0;font:800 clamp(23px,6.2vw,28px)/1.42 var(--zf);letter-spacing:-.03em;color:var(--tx);",
    " transition:transform .5s cubic-bezier(.2,.8,.2,1),opacity .5s,font-size .5s;transform-origin:left top}",
    "#zsu .end{font:800 clamp(23px,6.2vw,28px)/1.42 var(--zf);text-align:left;margin:0;word-break:keep-all}",
    "@media (prefers-reduced-motion:reduce){#zsu,#zsu .cur.in *{animation:none!important}#zsu .fly{transition:none}}"
  ].join("\n");

  function appFont() { try { var f = getComputedStyle(D.body).fontFamily; return f && f !== "initial" ? f : ""; } catch (e) { return ""; } }
  function point(cfg) {
    var q = ""; try { q = (location.search.match(/[?&]zsc=([a-z]+)/) || [])[1] || ""; } catch (e) { }
    var p = cfg.포인트색 || W.ZZSTRAT_POINT || q || "sky"; return deep(POINTS[p] || p);
  }

  /* 공통 질문 — 전략 데이터(d)가 있으면 목표 고르기까지. 앱이 자기 질문 앞에 붙여 쓴다 */
  function common(d) {
    var out = [
      { id: "exp", k: "공부", q: "이 시험, 공부해 본 적 있어요?", options: [
        { v: "new", label: "처음이에요" }, { v: "some", label: "조금 해 봤어요", sub: "강의나 기출을 일부 봤어요" }, { v: "retry", label: "시험을 본 적 있어요", sub: "점수를 알고 있어요" }] },
      { id: "when", k: "시험", q: "언제 시험을 볼 생각이에요?", options: [
        { v: "next", label: "다음 시험" }, { v: "after", label: "그다음 시험" }, { v: "unk", label: "아직 몰라요" }] },
      { id: "time", k: "하루", q: "하루에 얼마나 낼 수 있어요?", options: (W.ZZSTRAT_TIMES && W.ZZSTRAT_TIMES.length ? W.ZZSTRAT_TIMES : [
        { v: "1", label: "1시간 안쪽" }, { v: "3", label: "1~3시간" }, { v: "5", label: "3시간 넘게" }]), cols: W.ZZSTRAT_TIMES ? 2 : 1 }
    ];
    if (d && d.선택 && d.선택.length) out.push({
      id: "goal", k: "목표", q: "어디까지 노릴까요?", sub: "나중에 합격전략에서 바꿀 수 있어요.",
      options: d.선택.map(function (c) { return { v: c.id, label: c.이름 + (c.목표 ? " · " + c.목표 + ((d.합격선 || {}).단위 != null ? d.합격선.단위 : "점") : ""), sub: c.설명 ? String(c.설명).split(/(?<=[.。])\s/)[0] : "" }; })
    });
    return out;
  }

  var cur = null;
  function close() {
    if (!cur) return; var h = cur.host; D.documentElement.style.overflow = cur.ov || ""; cur = null;
    try { h.remove(); } catch (e) { }
  }

  function run(key, cfg) {
    cfg = cfg || {};
    close();
    var steps = cfg.steps || [], ans = {}, lab = {}, path = [];
    var old = get(key); if (old && cfg.keep) { ans = old; }
    var host = D.createElement("div"); host.id = "zsu-host"; host.style.cssText = "all:initial"; D.body.appendChild(host);
    var SR = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;
    var st = D.createElement("style"); st.textContent = css + "\n#zsu{--pt:" + point(cfg) + ";--zf:" + (appFont() || "'Pretendard','Noto Sans KR',system-ui,sans-serif") + "}"; SR.appendChild(st);
    var box = D.createElement("div"); box.id = "zsu"; box.setAttribute("role", "dialog"); box.setAttribute("aria-label", cfg.이름 || "첫 설정");
    box.innerHTML = '<div class="tp"><span class="nm">' + esc(cfg.이름 || "") + '</span><span class="pg"><i></i></span></div>' +
      '<div class="stage"><div class="hist" aria-live="polite"></div><div class="cur"></div></div>';
    SR.appendChild(box);
    cur = { host: host, ov: D.documentElement.style.overflow }; D.documentElement.style.overflow = "hidden";
    var hist = box.querySelector(".hist"), curEl = box.querySelector(".cur"), bar = box.querySelector(".pg i");

    function live() { return steps.filter(function (s) { return !s.when || s.when(ans); }); }
    function nextStep() { var L = live(); for (var i = 0; i < L.length; i++) if (!(L[i].id in ans)) return L[i]; return null; }
    function progress() { var L = live(), n = L.filter(function (s) { return s.id in ans; }).length; bar.style.width = Math.round(n / Math.max(L.length, 1) * 100) + "%"; }

    function render() {
      progress();
      var s = nextStep();
      if (!s) return finish();
      var q = val(s.q, ans) || "", opts = val(s.options, ans) || [];
      var o = '<p class="q">' + esc(q).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>") + '</p>' + (s.sub ? '<p class="qs">' + esc(val(s.sub, ans)) + '</p>' : '');
      if (s.type === "text") {
        o += '<form class="tx"><input type="text" maxlength="' + (s.max || 20) + '" placeholder="' + esc(s.placeholder || "") + '" autocomplete="off"><button class="go" type="submit">확인</button></form>';
      } else {
        o += '<div class="ops' + ((s.cols || (opts.length >= 6 && opts.every(function (x) { return !x.sub; }) ? 2 : 1)) === 2 ? ' c2' : '') + '">' + opts.map(function (x, i) {
          return '<button type="button" class="op' + (x.soon ? ' soon' : '') + (ans[s.id] === x.v ? ' on' : '') + '" data-i="' + i + '"' + (x.soon ? ' aria-disabled="true"' : '') + '><b>' + esc(x.label) + '</b>' + (x.sub ? '<small>' + esc(x.sub) + '</small>' : '') + '</button>';
        }).join("") + '</div>';
      }
      if (s.optional) o += '<button type="button" class="later">건너뛰기</button>';
      curEl.className = "cur"; curEl.innerHTML = o; void curEl.offsetWidth; curEl.classList.add("in");
      curEl._s = s; curEl._opts = opts;
      var inp = curEl.querySelector("input"); if (inp && !("ontouchstart" in W)) setTimeout(function () { try { inp.focus(); } catch (e) { } }, RM ? 0 : 420);
    }

    /* 답을 「질문 · 답」 한 줄로 바꿔 위로 밀어 올린다(질문 글자가 그 자리에서 작아지며 올라감) */
    function push(s, v, label) {
      ans[s.id] = v; lab[s.id] = label; path.push(s.id);
      haptic(14);
      var qEl = curEl.querySelector(".q"), from = qEl ? qEl.getBoundingClientRect() : null;
      var h = D.createElement("button"); h.type = "button"; h.className = "h"; h.setAttribute("data-id", s.id);
      h.innerHTML = '<span>' + esc(s.k || "") + '</span><b>' + esc(label) + '</b><i>바꾸기</i>';
      /* 이미 쌓인 줄들은 위로 한 칸 — FLIP */
      var olds = [].slice.call(hist.children), before = olds.map(function (x) { return x.getBoundingClientRect().top; });
      hist.appendChild(h);
      if (!RM) {
        olds.forEach(function (x, k) { var dy = before[k] - x.getBoundingClientRect().top; if (!dy) return; x.style.transition = "none"; x.style.transform = "translateY(" + dy + "px)"; void x.offsetWidth; x.style.transition = "transform .5s cubic-bezier(.2,.8,.2,1),opacity .2s"; x.style.transform = ""; });
        if (from) {
          var to = h.getBoundingClientRect();
          h.style.transition = "none"; h.style.transform = "translateY(" + (from.top - to.top) + "px)"; h.style.opacity = "0"; void h.offsetWidth;
          h.style.transition = "transform .5s cubic-bezier(.2,.8,.2,1),opacity .35s .1s"; h.style.transform = ""; h.style.opacity = "";
        }
      }
      curEl.innerHTML = "";
      setTimeout(render, RM ? 0 : 260);
    }

    function finish() {
      save(key, Object.assign({ _label: lab }, ans));
      bar.style.width = "100%";
      var end = cfg.끝말 ? val(cfg.끝말, ans) : "";
      function go() { close(); if (cfg.done) try { cfg.done(Object.assign({ _label: lab }, ans)); } catch (e) { console.error(e); } }
      if (end) { curEl.className = "cur"; curEl.innerHTML = '<p class="end">' + esc(end).replace(/\*\*(.+?)\*\*/g, "<b style=\"color:var(--pt)\">$1</b>") + '</p>'; void curEl.offsetWidth; curEl.classList.add("in"); haptic(20); setTimeout(go, RM ? 300 : 1300); }
      else go();
    }

    box.addEventListener("click", function (e) {
      var h = e.target.closest(".h");
      if (h) {   /* 위에 쌓인 답을 누르면 그 질문부터 다시 */
        var id = h.getAttribute("data-id"), k = path.indexOf(id); if (k < 0) return;
        path.slice(k).forEach(function (x) { delete ans[x]; delete lab[x]; });
        path = path.slice(0, k);
        var hs = [].slice.call(hist.children); hs.slice(k).forEach(function (x) { x.remove(); });
        haptic(8); render(); return;
      }
      var op = e.target.closest(".op");
      if (op && curEl._s) {
        var x = curEl._opts[+op.getAttribute("data-i")]; if (!x || x.soon) return;
        op.classList.add("on"); return push(curEl._s, x.v, x.label);
      }
      if (e.target.closest(".later") && curEl._s) return push(curEl._s, "", "건너뜀");
    });
    box.addEventListener("submit", function (e) {
      e.preventDefault(); var inp = curEl.querySelector("input"), v = (inp && inp.value || "").trim();
      if (!v) { if (inp) inp.focus(); return; } push(curEl._s, v, v);
    });
    setTimeout(render, RM ? 0 : 200);
    return true;
  }

  W.ZZSETUP = { run: run, get: get, reset: reset, common: common, close: close, haptic: haptic };
})();
