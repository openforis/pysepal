<template>
  <span class="sepal-viewport-bridge" style="display: none"></span>
</template>

<script>
module.exports = {
  mounted() {
    this.appliedVars = [];
    this.appliedClass = "";
    this.lastSize = null;
    this.frame = 0;
    // one report per frame, and only when the size changed: each report is a
    // round trip and a render of the shell
    this.onResize = () => {
      if (this.frame) return;
      this.frame = window.requestAnimationFrame(() => {
        this.frame = 0;
        const w = window.innerWidth;
        const h = window.innerHeight;
        if (this.lastSize && this.lastSize.w === w && this.lastSize.h === h)
          return;
        this.lastSize = { w, h };
        this.window_size({ w, h });
      });
    };
    window.addEventListener("resize", this.onResize);
    this.onResize();
    this.applyVars(this.css_vars);
    this.applyBodyClass(this.body_class);
  },
  beforeUnmount() {
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
      this.appliedVars
        .filter((name) => !(name in next))
        .forEach((name) => root.style.removeProperty(name));
      Object.entries(next).forEach(([name, value]) =>
        root.style.setProperty(name, value)
      );
      this.appliedVars = Object.keys(next);
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
      if (this.frame) window.cancelAnimationFrame(this.frame);
      this.frame = 0;
      this.applyVars({});
      this.applyBodyClass("");
    },
  },
};
</script>
