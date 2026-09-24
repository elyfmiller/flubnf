/* The "?" explainers (templates/_tips.html; styles in nau.css ".tip").
   CSS shows a tip on hover and keyboard focus; this adds click/tap
   toggling (WebKit, and so the pywebview window, never focuses a clicked
   button) and Escape to dismiss, and places the tooltip. The box is
   position:fixed, so a card's overflow never clips it: it sits under its
   button (above when there is no room below), inside the viewport. */
(function () {
  function place(t) {
    var btn = t.querySelector('.tipbtn'), b = t.querySelector('.tipbox');
    if (!btn || !b) return;
    var br = btn.getBoundingClientRect(),
        W = document.documentElement.clientWidth, H = window.innerHeight,
        w = b.offsetWidth, h = b.offsetHeight;
    var x = br.left + br.width / 2 - w / 2;
    x = Math.max(8, Math.min(x, W - 8 - w));
    var y = br.bottom + 6;
    if (y + h > H - 8 && br.top - 6 - h > 8) y = br.top - 6 - h;
    b.style.left = Math.round(x) + 'px';
    b.style.top = Math.round(y) + 'px';
  }
  function tipOf(e) {
    return e.target && e.target.closest ? e.target.closest('.tip') : null;
  }
  function closeAll(except) {
    document.querySelectorAll('.tip.open').forEach(function (t) {
      if (t !== except) t.classList.remove('open');
    });
  }
  document.addEventListener('mouseover', function (e) {
    var t = tipOf(e); if (t) place(t);
  });
  document.addEventListener('focusin', function (e) {
    var t = tipOf(e); if (t) { t.classList.remove('dismissed'); place(t); }
  });
  document.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('.tipbtn') : null;
    var t = btn ? btn.parentNode : null;
    closeAll(t);
    if (!t) return;
    e.preventDefault();                  // a tip inside a <label> or <summary>
    t.classList.remove('dismissed');
    t.classList.toggle('open');
    place(t);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    closeAll(null);
    var a = document.activeElement;
    if (a && a.classList && a.classList.contains('tipbtn'))
      a.parentNode.classList.add('dismissed');
  });
  // a shown tip follows its button on scroll and resize
  function replace() {
    document.querySelectorAll('.tip.open, .tip:focus-within, .tip:hover')
      .forEach(place);
  }
  window.addEventListener('scroll', replace, true);
  window.addEventListener('resize', replace);
})();
