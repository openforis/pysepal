<template>
  <div>
    <v-btn
      depressed
      @click="openDialog"
      style="background-color: unset !important"
    >
      <v-icon small left>mdi-translate</v-icon>
      {{ value }}
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
              <v-list-item-action v-if="isSelected(locale.code)">
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
// ipyvue evaluates only the exported object, so storage keys stay inside it.
// Direct value assignment also works when the selector is a root widget.

export default {
  name: "LocaleSelect",

  props: {
    available_locales: {
      type: [String, Array, Object],
      required: true,
      default: () => [{ code: "en", name: "English", flag: "gb" }],
    },
    value: { type: String, required: true, default: "en" },
  },

  data() {
    return {
      dialogOpen: false,
    };
  },

  created() {
    if (!window.sepalUi) {
      window.sepalUi = {};
    }
  },

  mounted() {
    const offered = this.offeredCodes();
    // Drawer changes remount this widget. After the first browser resolution,
    // preserve Python's value instead of adopting another tab's stored pick.
    if (this.localeResolved() && this.matchOffered(this.value, offered)) {
      this.apply(this.value);
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
    isSelected(code) {
      return this.matchOffered(this.value, this.offeredCodes()) === code;
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
      if (this.value !== code) {
        // eslint-disable-next-line vue/no-mutating-props
        this.value = code;
      }
    },
    openDialog() {
      this.dialogOpen = true;
    },
    closeDialog() {
      this.dialogOpen = false;
    },
    selectLanguage(code) {
      if (!this.isSelected(code)) {
        this.storageSet(code);
        this.apply(code);
      }
      this.dialogOpen = false;
    },
  },
};
</script>
