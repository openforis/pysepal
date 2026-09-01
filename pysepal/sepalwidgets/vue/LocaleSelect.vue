<template>
  <div>
    <v-btn
      depressed
      @click="openDialog"
      style="background-color: unset !important"
    >
      <v-icon small left>mdi-translate</v-icon>
      {{ currentLanguage }}
    </v-btn>

    <v-dialog v-model="dialogOpen" max-width="400">
      <v-card>
        <v-card-title class="headline d-flex justify-space-between">
          <span>Select your language</span>
          <v-btn icon @click="closeDialog">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-divider></v-divider>
        <v-card-text>
          <v-list>
            <v-list-item
              v-for="(locale, index) in available_locales"
              :key="index"
              @click="selectLanguage(locale.code)"
            >
              <v-list-item-content>
                <v-list-item-title
                  >{{ locale.name }} ({{ locale.code }})</v-list-item-title
                >
              </v-list-item-content>
              <v-list-item-action v-if="locale.code === currentLanguage">
                <v-icon color="primary">mdi-check</v-icon>
              </v-list-item-action>
            </v-list-item>
          </v-list>
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
// Browser-owned locale resolution, mirroring Theming.vue's ownership model.
//
// Resolution order on mount (each candidate validated via matchOffered):
//   1. localStorage[":sepalUi:locale"]  -- a previous explicit pick
//   2. navigator.language               -- browser auto-detection
//   3. "en"
//
// The ladder runs only ONCE per tab: after it has resolved, remounts adopt the
// value Python already holds (see mounted()).
//
// The result is pushed to Python by DIRECT trait assignment
// (this.selected_locale = code). Never use $emit("update:selected_locale"):
// that is the Vue .sync convention, which requires a binding parent and is
// silently dropped when this widget is a root widget -- which is why picks
// did not survive a refresh before pysepal 4.
//
// matchOffered transcribes pysepal._locale.match_offered_locale. The two are
// held in parity by tests/fixtures/locale_matching.json, which both run.
//
// The storage key is written out at each use rather than hoisted into a const:
// ipyvue evaluates the object below, not this file as a module, so a binding
// declared out here is undefined inside methods. Theming.vue inlines its key
// for the same reason. tests/test_sepalwidgets/test_vue_templates.py guards it.

export default {
  name: "LocaleSelect",

  props: {
    available_locales: {
      type: [String, Array, Object],
      required: true,
      default: () => [{ code: "en", name: "English", flag: "gb" }],
    },
    selected_locale: { type: String, required: true, default: "en" },
  },

  data() {
    // ipyvue calls this script's data() unbound, so `this` is the exported
    // options object -- never the component instance. Initialisers must be
    // literals (see Theming.vue); mounted() sets the real value.
    return {
      dialogOpen: false,
      currentLanguage: "",
    };
  },

  watch: {
    selected_locale(newValue) {
      this.currentLanguage = newValue;
    },
  },

  created() {
    if (!window.sepalUi) {
      window.sepalUi = {};
    }
  },

  mounted() {
    const offered = this.offeredCodes();
    // MapApp.vue destroys and recreates this widget on every drawer
    // expand/collapse, so mounted() runs many times per page. Once the ladder
    // has resolved a locale for this tab, Python owns the value: re-running
    // the ladder would revert a live pick (and, with two tabs sharing one
    // localStorage, adopt the *other* tab's pick). Same ownership handoff as
    // Theming.vue.
    if (
      this.localeResolved() &&
      this.selected_locale &&
      offered.includes(this.selected_locale)
    ) {
      this.apply(this.selected_locale);
      return;
    }
    const stored = this.matchOffered(this.storageGet(), offered);
    if (stored) {
      this.apply(stored);
      return;
    }
    const nav = this.matchOffered(
      (typeof navigator !== "undefined" && navigator.language) || "",
      offered
    );
    this.apply(nav || (offered.includes("en") ? "en" : offered[0] || "en"));
  },

  methods: {
    offeredCodes() {
      return (this.available_locales || []).map((locale) => locale.code);
    },
    normalizeLocale(code) {
      if (!code) return "";
      const [primary, ...rest] = String(code).replace(/_/g, "-").split("-");
      const canonical = [primary.toLowerCase()];
      for (const subtag of rest) {
        if (/^[A-Za-z]{4}$/.test(subtag)) {
          canonical.push(
            subtag[0].toUpperCase() + subtag.slice(1).toLowerCase()
          );
        } else if (/^[A-Za-z]{2}$/.test(subtag)) {
          canonical.push(subtag.toUpperCase());
        } else {
          canonical.push(subtag.toLowerCase());
        }
      }
      return canonical.join("-");
    },
    matchOffered(candidate, offered) {
      const wanted = this.normalizeLocale(candidate);
      if (!wanted) return "";
      const byCanonical = new Map();
      for (const code of offered) {
        const canonical = this.normalizeLocale(code);
        if (!byCanonical.has(canonical)) byCanonical.set(canonical, code);
      }
      if (byCanonical.has(wanted)) return byCanonical.get(wanted);
      const primary = wanted.split("-")[0];
      if (byCanonical.has(primary)) return byCanonical.get(primary);
      for (const [canonical, code] of byCanonical) {
        if (canonical.split("-")[0] === primary) return code;
      }
      return "";
    },
    storageGet() {
      // Never swallow silently: these catches are for a blocked-storage
      // SecurityError, and an empty one hid a ReferenceError that stopped
      // every pick from persisting.
      try {
        return localStorage.getItem(":sepalUi:locale") || "";
      } catch (e) {
        console.warn("[pysepal] cannot read the stored locale:", e);
        return "";
      }
    },
    storageSet(code) {
      try {
        localStorage.setItem(":sepalUi:locale", code);
      } catch (e) {
        console.warn("[pysepal] cannot persist the locale:", e);
      }
    },
    localeResolved() {
      // Per-tab (not per-widget) marker: survives widget destruction, resets
      // on a real page load so browser auto-detection stays live.
      return !!(window.sepalUi && window.sepalUi.localeResolved);
    },
    markLocaleResolved() {
      if (window.sepalUi) {
        window.sepalUi.localeResolved = true;
      }
    },
    apply(code) {
      this.markLocaleResolved();
      this.currentLanguage = code;
      if (this.selected_locale !== code) {
        // eslint-disable-next-line vue/no-mutating-props
        this.selected_locale = code;
      }
    },
    openDialog() {
      this.dialogOpen = true;
    },
    closeDialog() {
      this.dialogOpen = false;
    },
    selectLanguage(code) {
      if (code !== this.currentLanguage) {
        this.storageSet(code);
        this.apply(code);
      }
      this.dialogOpen = false;
    },
  },
};
</script>
