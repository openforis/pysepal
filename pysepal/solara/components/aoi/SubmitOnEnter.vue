<template>
  <span class="sepal-submit-on-enter" style="display: none"></span>
</template>

<script>
module.exports = {
  mounted() {
    this.onKeydown = (event) => this.handleKeydown(event);
    // Capture, so the decision is made before Vuetify reacts to the key.
    document.addEventListener("keydown", this.onKeydown, true);
  },
  beforeDestroy() {
    document.removeEventListener("keydown", this.onKeydown, true);
  },
  methods: {
    handleKeydown(event) {
      if (event.key !== "Enter" || event.isComposing) return;
      if (event.shiftKey || event.ctrlKey || event.altKey || event.metaKey)
        return;

      const input = event.target;
      if (!(input instanceof HTMLInputElement) || input.readOnly) return;
      if (!["text", "search", "number"].includes(input.type)) return;
      const scope = input.closest("." + this.scope);
      if (!scope || !scope.contains(this.$el)) return;

      // An open list owns Enter: Vuetify picks the highlighted item.
      const field = input.closest(".v-input");
      const classes = field ? field.classList : { contains: () => false };
      if (classes.contains("v-select--is-menu-active")) return;

      // A closed autocomplete would open its list again.
      if (
        classes.contains("v-autocomplete") &&
        !classes.contains("v-combobox")
      ) {
        event.preventDefault();
        event.stopPropagation();
      }

      // A combobox commits the typed text on this Enter in a microtask; the
      // timeout sends the submit after that value reaches Python.
      setTimeout(() => this.submit(null), 0);
    },
  },
};
</script>
