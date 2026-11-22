// 밝게 · 어둡게 단추. 고른 값은 이 브라우저에만 남는다(없어도 화면은 그대로 나온다).
(function () {
  var root = document.documentElement;
  var btn = document.querySelector(".theme");
  if (!btn) return;
  function current() {
    var t = root.getAttribute("data-theme");
    if (t === "light" || t === "dark") return t;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  btn.addEventListener("click", function () {
    var next = current() === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) {}
  });
})();
