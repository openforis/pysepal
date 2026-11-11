// Keep every binding inside the exported object: that object is all ipyvue is
// guaranteed to evaluate.
//
// `value` and `available_locales` are synced traits that ipyvue injects as
// data. ipyvue 1 ignores a `props` block; ipyvue 3 would warn that the two clash.

module.exports = {
  name: "LocaleSelect",

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
