// Set default theme to dark mode when the page loads
function setDarkTheme() {
  if (localStorage.getItem(":solara:theme.variant") === null) {
    localStorage.setItem(":solara:theme.variant", '"dark"');
  }
}
setDarkTheme();
