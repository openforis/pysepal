<template>
  <div class="pysepal-sortable">
    <div
      v-for="(child, index) in children"
      :key="ids[index] || index"
      class="pysepal-sortable__row"
      :class="{ 'pysepal-sortable__row--over': overIndex === index }"
      :data-layer-id="ids[index]"
      @dragover.prevent="onDragOver(index)"
      @drop.prevent="onDrop(index)"
    >
      <span
        class="pysepal-sortable__handle"
        draggable="true"
        @dragstart="onDragStart(index, $event)"
        @dragend="onDragEnd"
      >
        <v-icon size="small">mdi-drag</v-icon>
      </span>
      <div class="pysepal-sortable__content">
        <jupyter-widget :widget="child" />
      </div>
    </div>
  </div>
</template>

<script>
module.exports = {
  name: "SortableList",
  data() {
    return { dragIndex: null, overIndex: null };
  },
  methods: {
    onDragStart(index, event) {
      this.dragIndex = index;
      if (event && event.dataTransfer) {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", String(this.ids[index]));
      }
    },
    onDragOver(index) {
      if (this.dragIndex !== null) this.overIndex = index;
    },
    onDrop(index) {
      const from = this.dragIndex;
      this.onDragEnd();
      if (from === null || from === index) return;
      this.move({ id: this.ids[from], to: index });
    },
    onDragEnd() {
      this.dragIndex = null;
      this.overIndex = null;
    },
  },
};
</script>

<style scoped>
.pysepal-sortable > .pysepal-sortable__row {
  display: flex;
  align-items: center;
  border-top: 2px solid transparent;
}
.pysepal-sortable > .pysepal-sortable__row--over {
  border-top-color: rgb(var(--v-theme-primary));
}
.pysepal-sortable > .pysepal-sortable__row > .pysepal-sortable__handle {
  cursor: grab;
  opacity: 0.6;
}
.pysepal-sortable > .pysepal-sortable__row > .pysepal-sortable__content {
  flex: 1 1 auto;
  min-width: 0;
}
</style>
