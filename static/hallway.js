(function () {
  function doors() {
    return Array.from(document.querySelectorAll(".hall-door"));
  }

  function activate(door) {
    doors().forEach((d) => d.classList.remove("hall-door-active"));
    door.classList.add("hall-door-active");
    window.setTimeout(() => {
      door.classList.remove("hall-door-active");
    }, 850);
  }

  function init() {
    doors().forEach((door) => {
      door.addEventListener("mouseenter", () => {
        door.classList.add("hall-door-hover");
      });

      door.addEventListener("mouseleave", () => {
        door.classList.remove("hall-door-hover");
      });

      door.addEventListener("click", () => {
        activate(door);
      });

      door.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") activate(door);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
