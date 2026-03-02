document.addEventListener("DOMContentLoaded", () => {
  const doors = document.querySelectorAll("[data-href]");
  doors.forEach((d) => {
    d.addEventListener("click", () => {
      doors.forEach(x => x.classList.remove("on"));
      d.classList.add("on");
      const href = d.getAttribute("data-href");
      // small delay so the “lamp” effect is visible
      setTimeout(() => { window.location.href = href; }, 180);
    });
  });
});
