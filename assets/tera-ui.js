/* 테라러닝 화면 공통 동작 — 브랜드 웹앱 전부가 쓴다 (2026-11-10 허브)
 * 머리띠 그림자, 구역 나타나기, 아래 탭 현재 위치, 서비스 고르기 판, 종목 찾기, 모양 안(?look=) */
(function () {
  var d = document, root = d.documentElement;
  var q = new URLSearchParams(location.search), look = q.get("look");
  if (look && /^[abc]$/.test(look)) { root.setAttribute("data-look", look); try { sessionStorage.setItem("t-look", look); } catch (e) {} }
  else { try { var s = sessionStorage.getItem("t-look"); if (s) root.setAttribute("data-look", s); } catch (e) {} }

  function $(s, el) { return (el || d).querySelector(s); }
  function $$(s, el) { return Array.prototype.slice.call((el || d).querySelectorAll(s)); }

  d.addEventListener("DOMContentLoaded", function () {
    var head = $(".t-head");
    function stuck() { if (head) head.classList.toggle("is-stuck", window.scrollY > 4); }
    stuck(); window.addEventListener("scroll", stuck, { passive: true });

    var rise = $$(".t-rise");
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }); }, { rootMargin: "0px 0px -8% 0px" });
      rise.forEach(function (el) { io.observe(el); });
    } else rise.forEach(function (el) { el.classList.add("in"); });

    // 아래 탭: 보고 있는 구역에 불
    var tabs = $$(".t-tab a[href^='#']");
    if (tabs.length && "IntersectionObserver" in window) {
      var io2 = new IntersectionObserver(function (es) {
        es.forEach(function (e) { if (e.isIntersecting) tabs.forEach(function (a) { a.classList.toggle("on", a.getAttribute("href") === "#" + e.target.id); }); });
      }, { rootMargin: "-40% 0px -55% 0px" });
      tabs.forEach(function (a) { var t = $(a.getAttribute("href")); if (t) io2.observe(t); });
    }

    // 서비스 고르기 판
    var sheet = $(".t-sheet");
    $$("[data-open='fam']").forEach(function (b) { b.addEventListener("click", function () { if (sheet) sheet.classList.add("open"); }); });
    if (sheet) {
      sheet.addEventListener("click", function (e) { if (e.target.classList.contains("dim")) sheet.classList.remove("open"); });
      d.addEventListener("keydown", function (e) { if (e.key === "Escape") sheet.classList.remove("open"); });
    }

    // 종목 찾기
    var box = $("[data-catalog]");
    if (box && window.T_CATALOG) catalog(box, window.T_CATALOG);
  });

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function num(n) { return n == null ? "" : Number(n).toLocaleString("ko-KR"); }

  function catalog(box, data) {
    var input = $("input", box), seg = $(".t-seg", box), out = $(".t-out", box);
    var field = "", grade = "", word = "", open = false, LIMIT = 14;
    var grades = data.grades || [];
    var h = '<button class="on" data-f="">전체</button>';
    data.fields.forEach(function (f) { h += '<button data-f="' + esc(f.name) + '">' + esc(f.name) + "<small>" + f.count + "</small></button>"; });
    seg.innerHTML = h;
    var gsel = $(".t-grade", box);
    if (gsel) {
      gsel.innerHTML = '<button class="on" data-g="">모든 등급</button>' + grades.map(function (g) { return '<button data-g="' + esc(g) + '">' + esc(g) + "</button>"; }).join("");
      gsel.addEventListener("click", function (e) { var b = e.target.closest("button"); if (!b) return; grade = b.dataset.g; $$("button", gsel).forEach(function (x) { x.classList.toggle("on", x === b); }); draw(); });
    }
    seg.addEventListener("click", function (e) { var b = e.target.closest("button"); if (!b) return; field = b.dataset.f; open = false; $$("button", seg).forEach(function (x) { x.classList.toggle("on", x === b); }); draw(); });
    input.addEventListener("input", function () { word = input.value.trim().replace(/\s+/g, ""); open = false; draw(); });
    out.addEventListener("click", function (e) { if (e.target.closest(".t-more")) { open = true; draw(); } });

    function draw() {
      var html = "", shown = 0, total = 0, cut = false;
      data.fields.forEach(function (f) {
        if (field && f.name !== field) return;
        f.subs.forEach(function (s) {
          var rows = "";
          s.items.forEach(function (it) {
            var links = it.links.filter(function (l) { return !grade || l.label === grade; });
            if (!links.length) return;
            if (word && (it.name + s.name + f.name).replace(/\s+/g, "").indexOf(word) < 0) return;
            total++;
            if (!open && !word && shown >= LIMIT) { cut = true; return; }
            shown++;
            rows += '<div class="t-row"><div class="nm">' + esc(it.name) + '</div><div class="gr">' + links.map(function (l) {
              return '<a href="' + esc(l.href) + '"><b>' + esc(l.label) + "</b>" + (l.n ? "<small>O·X " + num(l.n) + "</small>" : "") + "</a>";
            }).join("") + "</div></div>";
          });
          if (rows) html += "<h3>" + esc(f.name) + " · " + esc(s.name) + "</h3>" + rows;
        });
      });
      if (!html) html = '<div class="t-empty">찾는 종목이 없습니다</div>';
      if (cut) html += '<button class="t-more" type="button">' + total + "종목 모두 보기</button>";
      out.innerHTML = '<div class="t-list">' + html + "</div>";
    }
    draw();
  }

  if ("serviceWorker" in navigator && location.protocol === "https:") {
    window.addEventListener("load", function () { navigator.serviceWorker.register("sw.js").catch(function () {}); });
  }
})();
