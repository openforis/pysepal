<template>
  <span class="sepal-theme-toggle">
    <v-btn icon text @click="cycle()">
      <v-icon small>{{ icon() }}</v-icon>
    </v-btn>
  </span>
</template>

<script>
// ipyvue keeps only the standard component options, so constants are methods.
module.exports = {
  mounted() {
    this.media = window.matchMedia
      ? window.matchMedia("(prefers-color-scheme: dark)")
      : null;
    this.onSchemeChange = () => {
      if (this.mode === "auto") this.apply();
    };
    if (this.media && this.media.addEventListener) {
      this.media.addEventListener("change", this.onSchemeChange);
    } else if (this.media && this.media.addListener) {
      this.media.addListener(this.onSchemeChange);
    }
    const stored = this.readStored();
    if (stored && stored !== this.mode && this.modes().includes(stored)) {
      this.set_mode(stored);
    } else {
      this.apply();
    }
  },
  beforeDestroy() {
    if (!this.media) return;
    if (this.media.removeEventListener) {
      this.media.removeEventListener("change", this.onSchemeChange);
    } else if (this.media.removeListener) {
      this.media.removeListener(this.onSchemeChange);
    }
    this.media = null;
  },
  watch: {
    mode() {
      try {
        localStorage.setItem(this.storageKey(), JSON.stringify(this.mode));
      } catch (e) {
        // storage can be unavailable (private window, blocked site data)
      }
      this.apply();
    },
  },
  methods: {
    modes() {
      return this.enable_auto ? ["dark", "light", "auto"] : ["dark", "light"];
    },
    cycle() {
      const modes = this.modes();
      this.set_mode(modes[(modes.indexOf(this.mode) + 1) % modes.length]);
    },
    icon() {
      if (this.mode === "dark") return "mdi-weather-night";
      if (this.mode === "light") return "mdi-white-balance-sunny";
      return "mdi-auto-fix";
    },
    apply() {
      const dark =
        this.mode === "auto"
          ? !!(this.media && this.media.matches)
          : this.mode === "dark";
      // Set on the page, not only through Python: under Voila the page follows
      // ipyvuetify's own theme, not Solara's per-kernel one.
      const theme = this.$vuetify && this.$vuetify.theme;
      if (theme) theme.dark = dark;
      this.set_dark(dark);
    },
    readStored() {
      try {
        return JSON.parse(localStorage.getItem(this.storageKey()));
      } catch (e) {
        return null;
      }
    },
    storageKey() {
      // the legacy ThemeToggle's key, so a user's choice carries over
      return ":sepalUi:theme.variant";
    },
  },
};
</script>
