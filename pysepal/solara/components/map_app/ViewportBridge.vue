<template>
  <span class="sepal-viewport-bridge" style="display: none"></span>
</template>

<script>
module.exports = {
  mounted() {
    this.appliedVars = [];
    this.appliedClass = "";
    this.onResize = () =>
      this.window_size({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", this.onResize);
    this.onResize();
    this.applyVars(this.css_vars);
    this.applyBodyClass(this.body_class);
  },
  beforeDestroy() {
    this.teardown();
  },
  watch: {
    css_vars(value) {
      this.applyVars(value);
    },
    body_class(value) {
      this.applyBodyClass(value);
    },
  },
  methods: {
    applyVars(vars) {
      const root = document.documentElement;
      const next = vars || {};
      const bottomBefore = root.style.getPropertyValue(
        "--sepal-bottom-reserved"
      );
      this.appliedVars
        .filter((name) => !(name in next))
        .forEach((name) => root.style.removeProperty(name));
      Object.entries(next).forEach(([name, value]) =>
        root.style.setProperty(name, value)
      );
      this.appliedVars = Object.keys(next);
      // Leaflet only re-measures on a window resize, and the map's height
      // changes when the bottom sheet opens or closes.
      if (
        root.style.getPropertyValue("--sepal-bottom-reserved") !== bottomBefore
      ) {
        this.$nextTick(() => window.dispatchEvent(new Event("resize")));
      }
    },
    applyBodyClass(name) {
      if (this.appliedClass) document.body.classList.remove(this.appliedClass);
      if (name) document.body.classList.add(name);
      this.appliedClass = name || "";
    },
    teardown() {
      if (this.tornDown) return;
      this.tornDown = true;
      window.removeEventListener("resize", this.onResize);
      this.applyVars({});
      this.applyBodyClass("");
    },
  },
};
</script>
