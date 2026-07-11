(function () {
  const scenes = document.querySelectorAll(".scene");
  const progressFill = document.getElementById("progress-fill");
  let current = 0;
  const total = scenes.length;
  const sceneDuration = 5000;
  let autoAdvanceTimer = null;

  function showScene(index) {
    scenes.forEach((s, i) => {
      s.classList.toggle("active", i === index);
    });
    progressFill.style.width = ((index + 1) / total * 100) + "%";
  }

  function next() {
    current = (current + 1) % total;
    showScene(current);
    resetAutoAdvance();
  }

  function resetAutoAdvance() {
    if (autoAdvanceTimer) {
      clearTimeout(autoAdvanceTimer);
    }
    autoAdvanceTimer = setTimeout(next, sceneDuration);
  }

  showScene(0);
  autoAdvanceTimer = setTimeout(next, sceneDuration);

  document.addEventListener("click", (e) => {
    if (e.target.closest(".back-link")) return;
    next();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === " ") {
      e.preventDefault();
      next();
    }
  });

  // Cleanup on page unload
  window.addEventListener("beforeunload", () => {
    if (autoAdvanceTimer) {
      clearTimeout(autoAdvanceTimer);
    }
  });
})();
