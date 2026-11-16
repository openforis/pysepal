<template>
  <div
    v-if="visible && hasContent"
    class="sepal-legend"
    :class="{
      'sepal-legend--collapsed': isCollapsed,
      'sepal-legend--dark': isDark,
      'sepal-legend--light': !isDark,
    }"
  >
    <!-- Expanded body -->
    <div v-if="!isCollapsed" class="sepal-legend__body">
      <!-- Layer selector (only with 2+ options) -->
      <div v-if="showSelector" class="sepal-legend__selector">
        <select
          class="sepal-legend__select"
          :value="selected"
          @change="onSelect($event)"
          aria-label="Choose which layer legend to show"
        >
          <option
            v-for="(opt, oi) in selector_options"
            :key="'o-' + oi"
            :value="opt.value"
          >
            {{ opt.text }}
          </option>
        </select>
        <!-- Arrow is drawn by .sepal-legend__selector::after, not a <v-icon>:
             Vuetify's `.v-icon.v-icon` sets position:relative at specificity
             (0,2,0), which drags an absolutely-positioned icon back into flow. -->
      </div>

      <!-- Gradient sections -->
      <div
        v-for="(grad, gi) in parsedGradients"
        :key="'g-' + gi"
        class="sepal-legend__gradient-section"
      >
        <div v-if="grad.title" class="sepal-legend__gradient-title">
          {{ grad.title }}
        </div>
        <div
          class="sepal-legend__gradient-bar"
          :style="{ background: grad.cssGradient }"
        ></div>
        <div class="sepal-legend__gradient-labels">
          <span v-for="(lbl, li) in grad.labels" :key="'gl-' + li">{{
            lbl
          }}</span>
        </div>
      </div>

      <!-- Discrete items -->
      <div
        v-if="parsedItems.length > 0"
        class="sepal-legend__items"
        :class="{ 'sepal-legend__items--detailed': hasDetail }"
      >
        <div
          v-for="(item, ii) in parsedItems"
          :key="'i-' + ii"
          class="sepal-legend__item"
        >
          <span
            v-if="item.color"
            class="sepal-legend__chip"
            :style="{ backgroundColor: item.color }"
          ></span>
          <!-- Colorless entries (a totals row) keep the chip's footprint so
               every label still starts on the same column. -->
          <span
            v-else
            class="sepal-legend__chip sepal-legend__chip--empty"
          ></span>
          <span class="sepal-legend__label">{{ item.label }}</span>
          <!-- Rendered for every row once any row has a detail: the detailed
               layout is a grid whose columns would shift if a row emitted
               fewer cells than its neighbours. -->
          <span v-if="hasDetail" class="sepal-legend__detail">{{
            item.detail
          }}</span>
        </div>
      </div>
    </div>

    <!-- Toggle bar: always rendered in the same spot (bottom-center of the
         legend), so the same click target both opens and closes it. Exposed as
         a real button to the a11y tree — focusable and Enter/Space operable. -->
    <div
      class="sepal-legend__bar"
      role="button"
      tabindex="0"
      @click="toggleCollapse"
      @keydown.enter="toggleCollapse"
      @keydown.space.prevent="toggleCollapse"
      :title="isCollapsed ? 'Show legend' : 'Hide legend'"
      :aria-label="isCollapsed ? 'Show legend' : 'Hide legend'"
      :aria-expanded="String(!isCollapsed)"
    >
      <!-- px: the named icon sizes scale with the font; the icons take the
           bar's themed text colour -->
      <v-icon :size="16">mdi-map-legend</v-icon>
      <v-icon :size="12">{{
        isCollapsed ? "mdi-chevron-up" : "mdi-chevron-down"
      }}</v-icon>
    </div>
  </div>
</template>

<script>
module.exports = {
  // legend_data, visible, collapsed, selector_options and selected are traits:
  // ipyvue adds them as data, and declaring them as props too makes Vue warn
  // about the duplicate.
  data() {
    return {
      internalCollapsed: false,
    };
  },
  // Not in data(): ipyvue calls it before the traits exist.
  created() {
    this.internalCollapsed = !!this.collapsed;
  },
  computed: {
    isDark() {
      // Reactive: changes when the user toggles the Vuetify theme at runtime.
      const theme = this.$vuetify && this.$vuetify.theme;
      if (!theme) return false;
      const current = theme.global.current;
      // A ref, unless the reactive $vuetify has already unwrapped it.
      const definition =
        current && "value" in current ? current.value : current;
      return !!(definition && definition.dark);
    },
    isCollapsed() {
      return this.internalCollapsed;
    },
    hasContent() {
      if (!this.legend_data) return false;
      var g = this.legend_data.gradients || [];
      var i = this.legend_data.items || [];
      // The selector counts as content: without this a layer whose legend is
      // empty would unmount the dropdown that lets you switch away from it.
      return g.length > 0 || i.length > 0 || this.showSelector;
    },
    parsedGradients() {
      if (!this.legend_data || !this.legend_data.gradients) return [];
      return this.legend_data.gradients.map(function (g) {
        var stops = g.colors
          .map(function (c, i) {
            var pct =
              g.colors.length === 1 ? 0 : (i / (g.colors.length - 1)) * 100;
            return c + " " + pct + "%";
          })
          .join(", ");
        return {
          title: g.title || "",
          labels: g.labels || [],
          cssGradient: "linear-gradient(to right, " + stops + ")",
        };
      });
    },
    parsedItems() {
      if (!this.legend_data || !this.legend_data.items) return [];
      return this.legend_data.items;
    },
    hasDetail() {
      return this.parsedItems.some(function (it) {
        return it.detail;
      });
    },
    showSelector() {
      return (
        Array.isArray(this.selector_options) && this.selector_options.length > 1
      );
    },
  },
  watch: {
    collapsed(newValue) {
      this.internalCollapsed = newValue;
    },
  },
  methods: {
    toggleCollapse() {
      const nextCollapsed = !this.internalCollapsed;
      this.internalCollapsed = nextCollapsed;
      if (typeof this.set_collapsed === "function") {
        this.set_collapsed(nextCollapsed);
      }
    },
    onSelect(e) {
      var val = e && e.target ? e.target.value : null;
      if (val != null && typeof this.set_selected === "function") {
        this.set_selected(val);
      }
    },
  },
};
</script>

<style scoped>
.sepal-legend {
  position: fixed;
  bottom: calc(var(--sepal-bottom-reserved, 0px) + 16px);
  left: calc(
    var(--sepal-drawer-width, 0px) +
      (
        100vw - var(--sepal-drawer-width, 0px) -
          var(--sepal-right-panel-width, 0px)
      ) / 2
  );
  transform: translateX(-50%);
  /* Below vuetify's modal baseline on purpose -- see the layering contract at
     the top of frontend/css/base.css. The scrim then dims it during a modal. */
  z-index: 150;
  pointer-events: auto;
  font-family: Roboto, sans-serif;
  /* Stack body over the toggle bar and keep everything centered. Because the
     element is bottom-anchored, the bar (last child) stays fixed at the bottom
     whether or not the body is shown. */
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.sepal-legend__body,
.sepal-legend__bar {
  backdrop-filter: blur(4px);
}

.sepal-legend__body {
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  max-width: min(380px, 92vw);
}

.sepal-legend__bar {
  border-radius: 16px;
  padding: 2px 10px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* --- Dark theme --- */
.sepal-legend--dark .sepal-legend__body,
.sepal-legend--dark .sepal-legend__bar {
  background: rgba(33, 33, 33, 0.85);
  color: #fff;
}

/* --- Light theme --- */
.sepal-legend--light .sepal-legend__body,
.sepal-legend--light .sepal-legend__bar {
  background: rgba(255, 255, 255, 0.9);
  color: rgba(0, 0, 0, 0.87);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12), 0 1px 2px rgba(0, 0, 0, 0.08);
}

/* --- Gradient --- */
.sepal-legend__gradient-section {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-self: stretch;
}

.sepal-legend__gradient-title {
  font-size: 11px;
  opacity: 0.8;
  text-align: center;
}

.sepal-legend__gradient-bar {
  height: 12px;
  border-radius: 3px;
  min-width: 200px;
}

.sepal-legend__gradient-labels {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  opacity: 0.85;
}

/* --- Discrete items --- */
.sepal-legend__items {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  align-items: center;
  justify-content: center;
}

.sepal-legend__item {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Detailed mode is a three-column table -- chip, label, value. `display:
   contents` dissolves each row box so its spans become grid cells directly,
   which is what makes the columns size against every row instead of each row
   sizing itself. The value column is `auto`: as wide as the widest value, and
   identical for all rows. */
.sepal-legend__items--detailed {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  flex-wrap: nowrap;
  gap: 3px 10px;
  align-self: stretch;
}
.sepal-legend__items--detailed .sepal-legend__item {
  display: contents;
}
/* Detailed rows can't wrap, so a long label has to yield rather than push the
   row past the body's max-width. The value column keeps its full text. */
.sepal-legend__items--detailed .sepal-legend__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sepal-legend__detail {
  text-align: right;
  opacity: 0.7;
  font-size: 11px;
  /* Digits share one advance width, so the values line up figure by figure. */
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.sepal-legend__selector {
  align-self: stretch;
  position: relative;
}
/* The "this is a dropdown" affordance, replacing the UA arrow we turned off.
   A borders triangle on our own element rather than a <v-icon>, so no Vuetify
   rule can outrank it, and currentColor themes it without dark/light props. */
.sepal-legend__selector::after {
  content: "";
  position: absolute;
  right: 8px;
  top: 50%;
  margin-top: -2px;
  width: 0;
  height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid currentColor;
  opacity: 0.7;
  /* The arrow is decoration; the click belongs to the select underneath. */
  pointer-events: none;
}
.sepal-legend__select {
  width: 100%;
  font-family: inherit;
  font-size: 12px;
  /* Right padding reserves room for our own arrow. */
  padding: 3px 22px 3px 6px;
  border-radius: 6px;
  border: 1px solid transparent;
  background: transparent;
  color: inherit;
  cursor: pointer;
  /* Drop the UA arrow: it differs per browser and OS, and half of them ignore
     the surrounding theme. `.sepal-legend__selector-icon` replaces it. */
  -webkit-appearance: none;
  appearance: none;
}
/* The dropdown popup does not inherit the legend's surface, and the select's
   own translucent background composites to white behind it -- so the options
   need opaque colors of their own or dark mode renders white on white.
   `color-scheme` covers the platforms where the popup is an OS-drawn menu that
   ignores CSS (macOS) rather than a browser-painted list. */
.sepal-legend--dark .sepal-legend__select {
  border-color: rgba(255, 255, 255, 0.25);
  background: rgba(255, 255, 255, 0.06);
  color-scheme: dark;
}
.sepal-legend--dark .sepal-legend__select option {
  background-color: #212121;
  color: #fff;
}
.sepal-legend--light .sepal-legend__select {
  border-color: rgba(0, 0, 0, 0.2);
  background: rgba(0, 0, 0, 0.03);
  color-scheme: light;
}
.sepal-legend--light .sepal-legend__select option {
  background-color: #fff;
  color: rgba(0, 0, 0, 0.87);
}

.sepal-legend__chip {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  flex-shrink: 0;
}

.sepal-legend--dark .sepal-legend__chip {
  border: 1px solid rgba(255, 255, 255, 0.3);
}

.sepal-legend--light .sepal-legend__chip {
  border: 1px solid rgba(0, 0, 0, 0.2);
}

/* Two classes so this outranks the themed `.sepal-legend--dark .sepal-legend__chip`
   border. The border stays, just invisible, so the box keeps its exact size. */
.sepal-legend__chip.sepal-legend__chip--empty {
  background: transparent;
  border-color: transparent;
}

.sepal-legend__label {
  white-space: nowrap;
  font-size: 12px;
}
</style>
