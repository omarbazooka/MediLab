(() => {
  const toggle = document.querySelector(".nav-toggle");
  const menu = document.querySelector(".nav-menu");
  if (!toggle || !menu) return;
  const close = () => { menu.classList.remove("open"); toggle.setAttribute("aria-expanded", "false"); toggle.setAttribute("aria-label", "Open navigation"); };
  toggle.addEventListener("click", () => {
    const open = !menu.classList.contains("open");
    menu.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") close(); });
  document.addEventListener("click", (event) => { if (!menu.contains(event.target) && !toggle.contains(event.target)) close(); });
})();
