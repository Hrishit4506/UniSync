(function () {
  const STORAGE_KEY = "unisync-theme";

  function getPreferredTheme() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(STORAGE_KEY, theme);
    const icon = document.getElementById("themeIcon");
    if (icon) {
      icon.className = theme === "dark" ? "fas fa-moon" : "fas fa-sun";
    }
    const label = document.getElementById("themeLabel");
    if (label) {
      label.textContent = theme === "dark" ? "Dark" : "Light";
    }
  }

  function toggleTheme() {
    const current =
      document.documentElement.getAttribute("data-theme") ||
      getPreferredTheme();
    setTheme(current === "dark" ? "light" : "dark");
  }

  // Initialize early to avoid FOUC
  setTheme(getPreferredTheme());

  // Expose toggle for click handler
  window.__toggleTheme = toggleTheme;
})();
