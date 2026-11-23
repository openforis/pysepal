<template>
  <div
    id="map-container"
    class="map-background sepal-mapapp__map"
    @click="onClick"
  >
    <jupyter-widget v-for="child in children" :key="child" :widget="child" />
  </div>
</template>

<script>
module.exports = {
  methods: {
    onClick() {
      if (this.collapsible) this.collapse(null);
    },
  },
};
</script>
