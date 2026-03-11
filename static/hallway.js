// hallway.js — lamp above the door + light-on-click + title glow (reliable)
// No frameworks. Mobile-safe.
//
// Expected per door:
// <a class="door" data-lane="nc" href="/services">
//   <span class="lamp"></span>
//   <span class="door-title">Legal / Compliance (NC)</span>
//   <span class="door-sub">Intake → Risk Flags → Next Steps</span>
// </a>

(function () {
  const ACTIVE_CLASS = "door-active";
  const HOVER_CLASS = "door-hover";

  function allDoors() {
    return Array.from(document.querySelectorAll(".door"));
  }

  function ensureLamp(door) {
    let lamp = door.querySelector(".lamp");
    if (!lamp) {
      lamp = document.createElement("span");
      lamp.className = "lamp";
      door.insertBefore(lamp, door.firstChild);
    }
    return lamp;
  }

  function ensureTitle(door) {
    return (
      door.querySelector(".door-title") ||
      door.querySelector("h3, h2, strong, b") ||
      door.querySelector(".title") ||
      null
    );
  }

  function clearActive() {
    allDoors().forEach((d) => d.classList.remove(ACTIVE_CLASS));
  }

  function pulseDoor(door) {
    clearActive();
    door.classList.add(ACTIVE_CLASS);

    window.setTimeout(() => {
      door.classList.remove(ACTIVE_CLASS);
    }, 900);
  }

  function flickerDoor(door) {
    door.classList.add(HOVER_CLASS);
    window.setTimeout(() => {
      door.classList.remove(HOVER_CLASS);
    }, 350);
  }

  function wireDoor(door) {
    ensureLamp(door);
    ensureTitle(door);

    // hover/focus shimmer
    door.addEventListener("mouseenter", () => flickerDoor(door), { passive: true });
    door.addEventListener("focus", () => flickerDoor(door), { passive: true });

    // Click/tap: SHOW lamp + title glow, then navigate.
    door.addEventListener("click", (e) => {
      const href = door.getAttribute("href");
      if (!href) return;

      // Let user see the effect before route.
      e.preventDefault();
      pulseDoor(door);

      // Navigate after a tiny delay (fast but visible).
      window.setTimeout(() => {
        window.location.href = href;
      }, 220);
    });

    // Keyboard support
    door.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        const href = door.getAttribute("href");
        if (!href) return;
        e.preventDefault();
        pulseDoor(door);
        window.setTimeout(() => {
          window.location.href = href;
        }, 220);
      }
    });
  }

  function init() {
    const doors = allDoors();
    if (!doors.length) return;

    doors.forEach(wireDoor);

    // optional: /hall#avpt highlights that door on load
    const hash = (window.location.hash || "").replace("#", "");
    if (hash) {
      const match = doors.find((d) => d.id === hash || d.dataset.lane === hash);
      if (match) pulseDoor(match);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
