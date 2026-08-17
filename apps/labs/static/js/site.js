const labsMenu = document.querySelector(".labs-menu");
const labsMenuTrigger = document.querySelector("[data-labs-menu-trigger]");
const labsMenuPanel = document.querySelector("[data-labs-menu-panel]");

if (labsMenu && labsMenuTrigger && labsMenuPanel) {
  const setMenuOpen = (open) => {
    labsMenuTrigger.setAttribute("aria-expanded", String(open));
    labsMenuPanel.hidden = !open;
  };

  labsMenuTrigger.addEventListener("click", () => {
    setMenuOpen(labsMenuTrigger.getAttribute("aria-expanded") !== "true");
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !labsMenuPanel.hidden) {
      setMenuOpen(false);
      labsMenuTrigger.focus();
    }
  });

  document.addEventListener("pointerdown", (event) => {
    if (!labsMenuPanel.hidden && !labsMenu.contains(event.target)) {
      setMenuOpen(false);
    }
  });
}
