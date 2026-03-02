(function () {
  const doors = Array.from(document.querySelectorAll(".door"));
  const titleEl = document.getElementById("laneTitle");
  const descEl = document.getElementById("laneDesc");
  const goEl = document.getElementById("laneGo");
  const eyebrowEl = document.getElementById("laneEyebrow");

  function setActive(btn) {
    doors.forEach(d => d.classList.remove("is-active"));
    btn.classList.add("is-active");

    const title = btn.getAttribute("data-title") || "Lane";
    const desc = btn.getAttribute("data-desc") || "";
    const go = btn.getAttribute("data-go") || "#";
    const lane = btn.getAttribute("data-lane") || "lane";

    eyebrowEl.textContent = "Lane • " + lane.toUpperCase();
    titleEl.textContent = title;
    descEl.textContent = desc;

    goEl.href = go;
    goEl.style.pointerEvents = "auto";
    goEl.style.opacity = "1";
  }

  doors.forEach(btn => {
    btn.addEventListener("click", () => setActive(btn));
    btn.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setActive(btn);
      }
    });
  });

  // Auto-select the featured door on first load (nice wow)
  const featured = document.querySelector(".door--feature");
  if (featured) setActive(featured);
})();
