(function () {
  "use strict";

  var deck = document.getElementById("deck");
  var stage = document.getElementById("stage");
  var slides = Array.prototype.slice.call(stage.querySelectorAll(".slide"));
  var countEl = document.getElementById("count");
  var progressEl = document.getElementById("progress");
  var notesBody = document.getElementById("notesBody");
  var notesTitle = document.getElementById("notesTitle");
  var timerEl = document.getElementById("timer");
  var overviewGrid = document.getElementById("overviewGrid");
  var current = 0;
  var startedAt = null;

  function fit() {
    var scale = Math.min(window.innerWidth / 1600, window.innerHeight / 900);
    stage.style.setProperty("--scale", String(scale));
  }

  function slideFromHash() {
    var n = parseInt((location.hash || "").replace("#", ""), 10);
    return isNaN(n) ? 0 : Math.min(Math.max(n - 1, 0), slides.length - 1);
  }

  function show(index, fromHash) {
    index = Math.min(Math.max(index, 0), slides.length - 1);
    current = index;
    slides.forEach(function (slide, i) {
      slide.classList.toggle("active", i === index);
      slide.classList.toggle("past", i < index);
      slide.setAttribute("aria-hidden", i === index ? "false" : "true");
    });
    restartSvgAnimations(slides[index]);
    countEl.textContent = (index + 1) + " / " + slides.length;
    progressEl.style.width = ((index + 1) / slides.length * 100) + "%";
    var notes = slides[index].querySelector(".notes");
    notesBody.innerHTML = notes ? notes.innerHTML : "<p>No notes for this slide.</p>";
    notesTitle.textContent = (index + 1) + ". " + (slides[index].dataset.title || "");
    Array.prototype.forEach.call(overviewGrid.children, function (button, i) {
      button.classList.toggle("current", i === index);
    });
    if (!fromHash) history.replaceState(null, "", "#" + (index + 1));
    if (startedAt === null && index > 0) startedAt = Date.now();
  }

  function restartSvgAnimations(slide) {
    slide.querySelectorAll("svg").forEach(function (svg) {
      if (typeof svg.setCurrentTime === "function") svg.setCurrentTime(0);
    });
  }

  function next() { show(current + 1); }
  function prev() { show(current - 1); }

  function toggleFullscreen() {
    if (!document.fullscreenElement) {
      (document.documentElement.requestFullscreen || function () {}).call(document.documentElement);
    } else if (document.exitFullscreen) {
      document.exitFullscreen();
    }
  }

  function toggle(cls) { deck.classList.toggle(cls); }

  function buildOverview() {
    slides.forEach(function (slide, i) {
      var button = document.createElement("button");
      button.type = "button";
      var label = document.createElement("span");
      label.textContent = String(i + 1).padStart(2, "0");
      button.appendChild(label);
      button.appendChild(document.createTextNode(slide.dataset.title || "Slide " + (i + 1)));
      button.addEventListener("click", function () {
        deck.classList.remove("show-overview");
        show(i);
      });
      overviewGrid.appendChild(button);
    });
  }

  document.addEventListener("keydown", function (event) {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
      case "PageDown":
      case " ":
      case "Enter":
        event.preventDefault();
        next();
        break;
      case "ArrowLeft":
      case "ArrowUp":
      case "PageUp":
      case "Backspace":
        event.preventDefault();
        prev();
        break;
      case "Home": show(0); break;
      case "End": show(slides.length - 1); break;
      case "f":
      case "F": toggleFullscreen(); break;
      case "n":
      case "N":
      case "s":
      case "S": toggle("show-notes"); break;
      case "o":
      case "O": toggle("show-overview"); break;
      case "Escape":
        deck.classList.remove("show-overview", "show-notes");
        break;
      default:
        break;
    }
  });

  document.getElementById("prevBtn").addEventListener("click", prev);
  document.getElementById("nextBtn").addEventListener("click", next);
  document.getElementById("fsBtn").addEventListener("click", toggleFullscreen);
  document.getElementById("notesBtn").addEventListener("click", function () { toggle("show-notes"); });
  document.getElementById("gridBtn").addEventListener("click", function () { toggle("show-overview"); });

  stage.addEventListener("click", function (event) {
    if (event.target.closest("a, button")) return;
    var rect = stage.getBoundingClientRect();
    if (event.clientX < rect.left + rect.width * 0.25) prev();
    else next();
  });

  var touchX = null;
  document.addEventListener("touchstart", function (event) {
    touchX = event.touches[0].clientX;
  }, { passive: true });
  document.addEventListener("touchend", function (event) {
    if (touchX === null) return;
    var dx = event.changedTouches[0].clientX - touchX;
    if (Math.abs(dx) > 50) {
      if (dx < 0) next();
      else prev();
    }
    touchX = null;
  });

  var idleTimer;
  function wake() {
    deck.classList.remove("idle");
    clearTimeout(idleTimer);
    idleTimer = setTimeout(function () { deck.classList.add("idle"); }, 2500);
  }
  document.addEventListener("mousemove", wake);
  wake();

  setInterval(function () {
    if (startedAt === null) {
      timerEl.textContent = "00:00";
      return;
    }
    var seconds = Math.floor((Date.now() - startedAt) / 1000);
    timerEl.textContent = String(Math.floor(seconds / 60)).padStart(2, "0") + ":" + String(seconds % 60).padStart(2, "0");
  }, 1000);

  window.addEventListener("resize", fit);
  window.addEventListener("hashchange", function () { show(slideFromHash(), true); });

  buildOverview();
  fit();
  show(slideFromHash(), true);
})();
