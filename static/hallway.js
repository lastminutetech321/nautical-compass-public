// hallway.js — "lamp above the door" + light-on-click + title glow
// Works with plain HTML/CSS. No frameworks. Safe.

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

  function clearActive() {
    allDoors().forEach((d) => d.classList.remove(ACTIVE_CLASS));
  }

  function pulseDoor(door) {
    clearActive();
    door.classList.add(ACTIVE_CLASS);
    window.setTimeout(() => door.classList.remove(ACTIVE_CLASS), 900);
  }

  function addHoverFlicker(door) {
    let t = null;
    function flicker() {
      if (t) window.clearTimeout(t);
      door.classList.add("door-hover");
      t = window.setTimeout(() => door.classList.remove("door-hover"), 350);
    }
    door.addEventListener("mouseenter", flicker, { passive: true });
    door.addEventListener("focus", flicker, { passive: true });
  }

  function wireDoor(door) {
    ensureLamp(door);
    addHoverFlicker(door);

    door.addEventListener(
      "click",
      () => {
        pulseDoor(door);
      },
      { passive: true }
    );

    door.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") pulseDoor(door);
    });
  }

  function init() {
    const doors = allDoors();
    if (!doors.length) return;

    doors.forEach(wireDoor);

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
