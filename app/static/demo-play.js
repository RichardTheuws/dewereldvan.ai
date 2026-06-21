/* Gedeelde demo-choreografie — de agent bouwt een profiel vóór je ogen.
 *
 * Eén bron voor zowel de homepage-hero (_home_demo.html, autoplay één keer in
 * beeld) als de volledige /demo-showcase (knop-getriggerd). Root-gescoped via
 * [data-demo] zodat meerdere demo's op één pagina elkaar niet raken. Honoreert
 * prefers-reduced-motion: dan verschijnt alles direct, mechanisme blijft leesbaar
 * (geen blur-loop, geen lege before/after).
 *
 * Per root, opt-in via attributen:
 *   [data-demo]                 — de root (verplicht)
 *   [data-demo-autoplay]        — speel één keer af zodra de root in beeld komt
 *   [data-demo-type="..."]      — typ deze tekst char-voor-char in dit element
 *   [data-demo-reasoning]       — de scan-/reasoning-regel (materialiseert eerst)
 *   .demo-step                  — elke sectie die één voor één in-materialiseert
 *   [data-demo-play]            — knop die de demo start (alternatief voor autoplay)
 *   [data-demo-hint]            — hint die bij start verdwijnt
 */
(function () {
  "use strict";
  var reduce = window.matchMedia("(prefers-reduced-motion:reduce)").matches;

  function wire(root) {
    var steps = Array.prototype.slice.call(root.querySelectorAll(".demo-step"));
    var reasoning = root.querySelector("[data-demo-reasoning]");
    var typeEl = root.querySelector("[data-demo-type]");
    var playBtn = root.querySelector("[data-demo-play]");
    var hint = root.querySelector("[data-demo-hint]");
    var reasonsOut = root.querySelector("[data-demo-reasons]");
    var played = false;

    // Causaliteit zichtbaar maken: als een stap een data-demo-reason draagt,
    // verschijnt die regel synchroon met het veld ("homepage gelezen → naam"),
    // zodat je ZIET dat dit veld uit de scan kwam (anti-"blinde timer").
    function emitReason(el) {
      if (!reasonsOut || !el.getAttribute) return;
      var reason = el.getAttribute("data-demo-reason");
      if (!reason) return;
      var line = document.createElement("div");
      line.className = "fetch-line fetch-line--ok";
      line.textContent = "·· " + reason;
      reasonsOut.appendChild(line);
    }

    function showNow(el) { el.style.opacity = "1"; }

    function materialize(el) {
      el.style.opacity = "";
      el.classList.add("field--materializing");
      var done = function () {
        el.classList.remove("field--materializing");
        el.classList.add("field--ready");
      };
      el.addEventListener("animationend", done, { once: true });
      setTimeout(done, 1000); // failsafe als animationend niet vuurt
    }

    function typeText(el, text, cb) {
      var i = 0;
      el.textContent = "";
      (function tick() {
        if (i <= text.length) {
          el.textContent = text.slice(0, i);
          i++;
          setTimeout(tick, 55);
        } else if (cb) {
          cb();
        }
      })();
    }

    function runSteps() {
      var t = 250;
      if (reasoning) setTimeout(function () { materialize(reasoning); }, t);
      t += 1100;
      steps.forEach(function (el) {
        setTimeout(function () { materialize(el); emitReason(el); }, t);
        t += 750;
      });
    }

    function play() {
      if (played) return;
      played = true;
      if (playBtn) playBtn.style.display = "none";
      if (hint) hint.style.display = "none";
      if (reduce) {
        if (typeEl) typeEl.textContent = typeEl.getAttribute("data-demo-type");
        if (reasoning) showNow(reasoning);
        // Reduced-motion: toon alles direct MAAR behoud de causaliteit (de
        // reason-regels) zodat het mechanisme ook hier leesbaar blijft.
        steps.forEach(function (el) { showNow(el); emitReason(el); });
        return;
      }
      if (typeEl) {
        typeText(typeEl, typeEl.getAttribute("data-demo-type"), function () {
          setTimeout(runSteps, 400);
        });
      } else {
        runSteps();
      }
    }

    if (playBtn) playBtn.addEventListener("click", play);

    if (root.hasAttribute("data-demo-autoplay")) {
      if (reduce || !("IntersectionObserver" in window)) {
        // Geen scroll-gestuurde trigger mogelijk → toon direct (geen jank-loop).
        play();
      } else {
        var io = new IntersectionObserver(function (entries) {
          entries.forEach(function (e) {
            if (e.isIntersecting) {
              setTimeout(play, 500);
              io.disconnect();
            }
          });
        }, { threshold: 0.35 });
        io.observe(root);
      }
    }
  }

  function init() {
    document.querySelectorAll("[data-demo]").forEach(wire);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
