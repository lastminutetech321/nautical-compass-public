// hallway.js — "lamp above the door" + light-on-click + title glow
// Works with plain HTML/CSS. No frameworks. Safe.
//
// Expected HTML structure per door (examples):
// <a class="door" data-lane="nc" href="/services">
//   <span class="lamp"></span>
//   <span class="door-title">Legal / Compliance (NC)</span>
//   <span class="door-sub">Intake → Risk Flags → Next Steps</span>
// </a>
//
// This script:
// - Adds a subtle "lamp flicker" on hover/focus
// - On click/tap: turns lamp "on" + glows the title for a moment
// - Keeps it mobile-friendly (tap = click)
// - Does NOT block navigation (it triggers instantly, then lets link go)

(function () {
  const ACTIVE_CLASS = "door-active";

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
    let title = door.querySelector(".door-title");
    if (!title) {
      title =
        door.querySelector("h3, h2, strong, b") ||
        door.querySelector(".title") ||
        null;
    }
    return title;
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

  function addHoverFlicker(door) {
    let t = null;

    function flicker() {
      if (t) window.clearTimeout(t);
      door.classList.add("door-hover");
      t = window.setTimeout(() => {
        door.classList.remove("door-hover");
      }, 350);
    }

    door.addEventListener("mouseenter", flicker, { passive: true });
    door.addEventListener("focus", flicker, { passive: true });
  }

  function wireDoor(door) {
    ensureLamp(door);
    ensureTitle(door);
    addHoverFlicker(door);

    door.addEventListener(
      "click",
      () => {
        pulseDoor(door);
      },
      { passive: true }
    );

    door.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        pulseDoor(door);
      }
    });
  }

  function init() {
    const doors = allDoors();
    if (!doors.length) return;

    doors.forEach(wireDoor);

    const hash = (window.location.hash || "").replace("#", "");
    if (hash) {
      const match = doors.find(
        (d) => d.id === hash || d.dataset.lane === hash
      );
      if (match) pulseDoor(match);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
