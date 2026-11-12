<template>
  <span class="sepal-color-scheme-bridge" style="display: none"></span>
</template>

<script>
// ipyvue keeps only the standard component options, so the storage key is a method.
module.exports = {
  mounted() {
    this.media = window.matchMedia
      ? window.matchMedia("(prefers-color-scheme: dark)")
      : null;
    this.onChange = () =>
      this.prefers_dark(!!(this.media && this.media.matches));
    if (this.media && this.media.addEventListener) {
      this.media.addEventListener("change", this.onChange);
    } else if (this.media && this.media.addListener) {
      this.media.addListener(this.onChange);
    }
    this.onChange();
    let stored = null;
    try {
      stored = JSON.parse(localStorage.getItem(this.storageKey()));
    } catch (e) {
      stored = null;
    }
    if (stored) this.stored_mode(stored);
    this.applyDark(this.dark);
  },
  beforeDestroy() {
    this.teardown();
  },
  watch: {
    dark(value) {
      this.applyDark(value);
    },
    mode(value) {
      if (!value) return;
      try {
        localStorage.setItem(this.storageKey(), JSON.stringify(value));
      } catch (e) {
        // storage can be unavailable (private window, blocked site data)
      }
    },
  },
  methods: {
    applyDark(dark) {
      // Set on the page, not only through a Python theme widget: under Voila the
      // page follows ipyvuetify's own theme, not Solara's per-kernel one.
      const theme = this.$vuetify && this.$vuetify.theme;
      if (dark === null || dark === undefined || !theme) return;
      theme.dark = dark;
    },
    storageKey() {
      // the legacy ThemeToggle's key, so a user's choice carries over
      return ":sepalUi:theme.variant";
    },
    teardown() {
      if (!this.media) return;
      if (this.media.removeEventListener) {
        this.media.removeEventListener("change", this.onChange);
      } else if (this.media.removeListener) {
        this.media.removeListener(this.onChange);
      }
      this.media = null;
    },
  },
};
</script>
