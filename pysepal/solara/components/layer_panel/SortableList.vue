<template>
  <div
    class="pysepal-sortable"
    :class="{ 'pysepal-sortable--sorting': sorting }"
  >
    <div
      v-for="(child, index) in children"
      :key="ids[index] || index"
      class="pysepal-sortable__row"
      :class="{ 'pysepal-sortable__row--placeholder': placeholder === index }"
      :style="
        shifts && shifts[index]
          ? { transform: 'translateY(' + shifts[index] + 'px)' }
          : null
      "
      :data-layer-id="ids[index]"
    >
      <span
        class="pysepal-sortable__handle"
        :class="{ 'pysepal-sortable__handle--locked': isLocked(index) }"
        role="button"
        :tabindex="isLocked(index) ? -1 : 0"
        :aria-disabled="isLocked(index) ? 'true' : null"
        :aria-keyshortcuts="
          isLocked(index) ? null : 'Alt+ArrowUp Alt+ArrowDown'
        "
        :aria-label="(!isLocked(index) && handle_label) || null"
        :title="(!isLocked(index) && handle_label) || null"
        @pointerdown="onPointerDown(index, $event)"
        @keydown="onHandleKey(index, $event)"
      >
        <v-icon size="18">mdi-drag</v-icon>
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
  // ipyvue drops any code above the exported options, so the constants live in them.
  sortable: {
    grabbing: "pysepal-sortable-grabbing",
    // a press that moves less than this (px) is not a drag
    threshold: 4,
    glideMs: 140,
    // how long a dropped order waits for the new ids before it gives up
    settleMs: 2000,
  },
  data() {
    return { placeholder: null, shifts: null, sorting: false };
  },
  created() {
    // Pointer state stays out of Vue's reactivity: it holds DOM nodes.
    this.drag = null;
    this.refocus = null;
    this.settleTimer = null;
  },
  watch: {
    ids() {
      if (this.drag) this.endDrag(false);
      this.reset();
      if (this.refocus !== null) {
        const id = this.refocus;
        this.refocus = null;
        // Reordering the keyed rows moves their nodes, which drops the focus.
        this.$nextTick(() => {
          const row = this.rows().find((r) => r.dataset.layerId === id);
          if (row) row.querySelector(".pysepal-sortable__handle").focus();
        });
      }
    },
  },
  beforeUnmount() {
    if (this.drag) this.endDrag(false);
    clearTimeout(this.settleTimer);
  },
  methods: {
    isLocked(index) {
      return (this.locked || []).includes(this.ids[index]);
    },
    // The locked rows lead the list and keep their place: no row goes above them.
    firstFree() {
      let index = 0;
      while (index < this.ids.length && this.isLocked(index)) index += 1;
      return index;
    },
    rows() {
      return Array.from(this.$el.children).filter((e) =>
        e.classList.contains("pysepal-sortable__row")
      );
    },
    targetIndex(mids, from, center) {
      // The drop index is the number of other rows whose middle is above the dragged row's.
      let to = 0;
      mids.forEach((mid, i) => {
        if (i !== from && mid < center) to += 1;
      });
      return to;
    },
    shiftsFor(tops, heights, from, to) {
      const order = tops.map((_, i) => i).filter((i) => i !== from);
      order.splice(to, 0, from);
      const gap = tops.length > 1 ? tops[1] - tops[0] - heights[0] : 0;
      const shifts = new Array(tops.length);
      let y = tops[0];
      order.forEach((i) => {
        shifts[i] = y - tops[i];
        y += heights[i] + gap;
      });
      return shifts;
    },
    reset() {
      clearTimeout(this.settleTimer);
      this.settleTimer = null;
      this.placeholder = null;
      this.shifts = null;
      this.sorting = false;
    },
    onHandleKey(index, event) {
      if (
        !event.altKey ||
        (event.key !== "ArrowUp" && event.key !== "ArrowDown")
      )
        return;
      event.preventDefault();
      const to = index + (event.key === "ArrowUp" ? -1 : 1);
      if (this.isLocked(index)) return;
      if (this.drag || to < this.firstFree() || to >= this.ids.length) return;
      this.refocus = this.ids[index];
      this.move({ id: this.ids[index], to });
    },
    onPointerDown(index, event) {
      if (this.drag || event.button !== 0 || !event.isPrimary) return;
      if (this.isLocked(index)) return;
      event.preventDefault();
      this.reset();
      const handle = event.currentTarget;
      handle.setPointerCapture(event.pointerId);
      const drag = {
        index,
        handle,
        pointerId: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        to: index,
        started: false,
      };
      drag.listeners = {
        pointermove: (e) => this.onPointerMove(e),
        pointerup: (e) => e.pointerId === drag.pointerId && this.endDrag(true),
        pointercancel: () => this.endDrag(false),
        lostpointercapture: () => this.endDrag(false),
      };
      Object.entries(drag.listeners).forEach(([name, fn]) =>
        handle.addEventListener(name, fn)
      );
      drag.onKey = (e) => {
        if (e.key !== "Escape") return;
        e.preventDefault();
        e.stopPropagation();
        this.endDrag(false);
      };
      window.addEventListener("keydown", drag.onKey, true);
      document.documentElement.classList.add(this.$options.sortable.grabbing);
      this.drag = drag;
    },
    onPointerMove(event) {
      const drag = this.drag;
      if (!drag || event.pointerId !== drag.pointerId) return;
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      if (!drag.started) {
        if (Math.hypot(dx, dy) < this.$options.sortable.threshold) return;
        this.startDrag(drag);
      }
      drag.ghost.style.transform = `translate(${dx}px, ${dy}px)`;
      // Layout coordinates, so a scroll of the panel during the drag is followed.
      const listTop = this.$el.getBoundingClientRect().top;
      const center =
        drag.mids[drag.index] + (event.clientY - listTop) - drag.grabY;
      const to = Math.max(
        this.firstFree(),
        this.targetIndex(drag.mids, drag.index, center)
      );
      if (to !== drag.to) {
        drag.to = to;
        this.shifts = this.shiftsFor(drag.tops, drag.heights, drag.index, to);
      }
    },
    startDrag(drag) {
      const rows = this.rows();
      // offsetTop is the layout position, which the shifts (transforms) do not change.
      drag.tops = rows.map((r) => r.offsetTop);
      drag.heights = rows.map((r) => r.offsetHeight);
      drag.mids = drag.tops.map((top, i) => top + drag.heights[i] / 2);
      drag.grabY = drag.y - this.$el.getBoundingClientRect().top;
      drag.ghost = this.makeGhost(rows[drag.index]);
      drag.started = true;
      this.sorting = true;
      this.placeholder = drag.index;
      this.shifts = drag.tops.map(() => 0);
    },
    makeGhost(row) {
      const rect = row.getBoundingClientRect();
      const css = getComputedStyle(row);
      // Outside the app the theme variables and the font are not inherited: carry them over.
      const themed = row.closest("[class*='v-theme--']");
      const theme =
        themed &&
        Array.from(themed.classList).find((c) => c.startsWith("v-theme--"));
      const ghost = document.createElement("div");
      ghost.className =
        "pysepal-sortable pysepal-sortable--ghost" + (theme ? " " + theme : "");
      ghost.setAttribute("aria-hidden", "true");
      Object.assign(ghost.style, {
        position: "fixed",
        left: rect.left + "px",
        top: rect.top + "px",
        width: rect.width + "px",
        margin: "0",
        zIndex: "2400",
        pointerEvents: "none",
        fontFamily: css.fontFamily,
        fontSize: css.fontSize,
        lineHeight: css.lineHeight,
        letterSpacing: css.letterSpacing,
        color: css.color,
      });
      const copy = row.cloneNode(true);
      copy.removeAttribute("style");
      copy.classList.add("pysepal-sortable__row--ghost");
      copy
        .querySelectorAll("[id]")
        .forEach((node) => node.removeAttribute("id"));
      ghost.appendChild(copy);
      document.body.appendChild(ghost);
      return ghost;
    },
    endDrag(commit) {
      const drag = this.drag;
      if (!drag) return;
      this.drag = null;
      Object.entries(drag.listeners).forEach(([name, fn]) =>
        drag.handle.removeEventListener(name, fn)
      );
      window.removeEventListener("keydown", drag.onKey, true);
      document.documentElement.classList.remove(
        this.$options.sortable.grabbing
      );
      if (drag.handle.hasPointerCapture(drag.pointerId)) {
        drag.handle.releasePointerCapture(drag.pointerId);
      }
      if (!drag.started) return;

      const from = drag.index;
      const to = commit ? drag.to : from;
      if (to !== from) this.move({ id: this.ids[from], to });

      // Glide the ghost onto the slot it lands in, then show the row there until the
      // new order arrives from Python.
      this.shifts = this.shiftsFor(drag.tops, drag.heights, from, to);
      const landing =
        this.$el.getBoundingClientRect().top +
        drag.tops[from] +
        this.shifts[from];
      const ghost = drag.ghost;
      const { glideMs, settleMs } = this.$options.sortable;
      ghost.style.transition = `transform ${glideMs}ms ease-out`;
      ghost.style.transform = `translate(0px, ${
        landing - parseFloat(ghost.style.top)
      }px)`;
      setTimeout(() => {
        ghost.remove();
        // a new press already owns the list state
        if (this.drag) return;
        this.placeholder = null;
        this.sorting = false;
        if (to === from) this.shifts = null;
      }, glideMs);
      if (to !== from)
        this.settleTimer = setTimeout(() => this.reset(), settleMs);
    },
  },
};
</script>

<style scoped>
.pysepal-sortable {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.pysepal-sortable > .pysepal-sortable__row {
  display: flex;
  align-items: center;
  min-height: 32px;
  border-radius: 6px;
}
.pysepal-sortable > .pysepal-sortable__row:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.pysepal-sortable--sorting > .pysepal-sortable__row {
  transition: transform 150ms ease;
}
.pysepal-sortable--sorting > .pysepal-sortable__row:hover {
  background: none;
}
.pysepal-sortable > .pysepal-sortable__row.pysepal-sortable__row--placeholder {
  background: rgba(var(--v-theme-primary), 0.1);
  outline: 1px dashed rgba(var(--v-theme-primary), 0.7);
  outline-offset: -1px;
}
.pysepal-sortable > .pysepal-sortable__row--placeholder > * {
  visibility: hidden;
}
.pysepal-sortable > .pysepal-sortable__row > .pysepal-sortable__handle {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 28px;
  border-radius: 4px;
  cursor: grab;
  touch-action: none;
  opacity: 0.45;
}
.pysepal-sortable > .pysepal-sortable__row:hover > .pysepal-sortable__handle,
.pysepal-sortable
  > .pysepal-sortable__row
  > .pysepal-sortable__handle:focus-visible {
  opacity: 1;
}
/* After the hover rule, which it ties with. */
.pysepal-sortable
  > .pysepal-sortable__row
  > .pysepal-sortable__handle.pysepal-sortable__handle--locked {
  cursor: default;
  opacity: 0.2;
}
.pysepal-sortable
  > .pysepal-sortable__row
  > .pysepal-sortable__handle:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.pysepal-sortable > .pysepal-sortable__row > .pysepal-sortable__content {
  flex: 1 1 auto;
  min-width: 0;
}
.pysepal-sortable--ghost > .pysepal-sortable__row--ghost {
  background: rgb(var(--v-theme-surface));
  outline: 1px solid rgba(var(--v-theme-primary), 0.7);
  outline-offset: -1px;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.32), 0 2px 6px rgba(0, 0, 0, 0.2);
  opacity: 0.92;
}
.pysepal-sortable--ghost
  > .pysepal-sortable__row--ghost
  > .pysepal-sortable__handle {
  opacity: 1;
}
</style>

<style>
/* Not scoped: while a row is held, every element under the pointer shows the closed hand. */
html.pysepal-sortable-grabbing,
html.pysepal-sortable-grabbing * {
  cursor: grabbing !important;
  user-select: none !important;
}
</style>
